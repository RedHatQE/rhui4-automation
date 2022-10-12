"""Tests for changing the RHUI remote share"""

from os.path import basename

import logging
import nose
from stitches.expect import Expect
import yaml

from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.rhuimanager import RHUIManager
from rhui4_tests_lib.rhuimanager_cmdline_instance import RHUIManagerCLIInstance

logging.basicConfig(level=logging.DEBUG)

RHUA_HOSTNAME = ConMgr.get_rhua_hostname()
CDS_HOSTNAME = ConMgr.get_cds_hostnames()[0]

RHUA = ConMgr.connect()
CDS = ConMgr.connect(CDS_HOSTNAME)

ANSWERS = "/root/.rhui/answers.yaml"
ANSWERS_BAK = ANSWERS + ".backup_test"
REMOTE_SHARE = "/var/lib/rhui/remote_share"

def _check_rhui_mountpoint(connection, fs_server):
    """check the RHUI mountpoint"""
    for mount_info_file in ["/proc/mounts", "/etc/fstab"]:
        _, stdout, _ = connection.exec_command(f"cat {mount_info_file}")
        mounts = stdout.read().decode().splitlines()
        matches = [line for line in mounts if REMOTE_SHARE in line]
        # there must be only one such share
        nose.tools.eq_(len(matches), 1,
                       msg=f"unexpected matches in {mount_info_file}: {matches}")
        # and it must be using the expected FS server
        nose.tools.ok_(fs_server in matches[0],
                       msg=f"{fs_server} not found in {mount_info_file}, found: {matches[0]}")

def setup():
    """announce the beginning of the test run"""
    print(f"*** Running {basename(__file__)}: ***")

def test_01_add_cds():
    """add a CDS"""
    RHUIManager.initial_run(RHUA)
    RHUIManagerCLIInstance.add(RHUA, "cds", CDS_HOSTNAME, unsafe=True)
    # check that
    cds_list = RHUIManagerCLIInstance.list(RHUA, "cds")
    nose.tools.ok_(cds_list)

def test_02_prep():
    """stop pulpcore services and back up the answers file"""
    Expect.expect_retval(RHUA, r"systemctl stop pulpcore\*")
    Expect.expect_retval(RHUA, f"cp {ANSWERS} {ANSWERS_BAK}")

def test_03_rerun_installer():
    """rerun the installer with a different remote FS server"""
    # the FS server is supposed to be on the RHUA, so let's use the RHUA hostname
    # get the actual FS server hostname from the answers file
    _, stdout, _ = RHUA.exec_command(f"cat {ANSWERS}")
    answers = yaml.safe_load(stdout)
    current_fs_server = answers["rhua"]["remote_fs_server"]
    fs_hostname = current_fs_server.split(":")[0]
    new_fs_server = current_fs_server.replace(fs_hostname, RHUA_HOSTNAME)
    installer_cmd = f"rhui-installer --rerun --remote-fs-server {new_fs_server}"
    Expect.expect_retval(RHUA, installer_cmd, timeout=300)

def test_04_check_rhua_mountpoint():
    """check if the new remote share has replaced the old one on the RHUA"""
    _check_rhui_mountpoint(RHUA, RHUA_HOSTNAME)

def test_05_reinstall_cds():
    """reinstall the CDS"""
    RHUIManagerCLIInstance.reinstall(RHUA, "cds", CDS_HOSTNAME)

def test_06_check_cds_mountpoint():
    """check if the new remote share is now used on the CDS"""
    _check_rhui_mountpoint(CDS, RHUA_HOSTNAME)

def test_99_cleanup():
    """clean up: delete the CDS and rerun the installer with the original remote FS"""
    RHUIManagerCLIInstance.delete(RHUA, "cds", [CDS_HOSTNAME], force=True)
    # get the original FS server hostname from the backed up answers file
    _, stdout, _ = RHUA.exec_command(f"cat {ANSWERS_BAK}")
    answers = yaml.safe_load(stdout)
    original_fs_server = answers["rhua"]["remote_fs_server"]
    fs_hostname = original_fs_server.split(":")[0]
    installer_cmd = f"rhui-installer --rerun --remote-fs-server {original_fs_server}"
    # stop pulpcore services and rerun the installer with the original FS server
    Expect.expect_retval(RHUA, r"systemctl stop pulpcore\*")
    Expect.expect_retval(RHUA, installer_cmd, timeout=300)
    # did it work?
    _check_rhui_mountpoint(RHUA, fs_hostname)
    # finish the cleanup
    Expect.expect_retval(RHUA, f"rm -f {ANSWERS_BAK}")
    ConMgr.remove_ssh_keys(RHUA)

def teardown():
    """announce the end of the test run"""
    print(f"*** Finished running {basename(__file__)}. ***")
