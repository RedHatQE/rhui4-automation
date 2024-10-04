"""Tests for changing the RHUI remote share"""

# To test remote shares on containerized CDS nodes, run:
# export RHUICONTCDS=1
# in your shell before running this script.

from os import getenv
from os.path import basename

import logging
import nose
from stitches.expect import Expect

from rhui4_tests_lib.cfg import Config, ANSWERS_BAK, RHUI_ROOT
from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.incontainers import RhuiinContainers
from rhui4_tests_lib.rhuimanager import RHUIManager
from rhui4_tests_lib.rhuimanager_cmdline_instance import RHUIManagerCLIInstance

logging.basicConfig(level=logging.DEBUG)

RHUA_HOSTNAME = ConMgr.get_rhua_hostname()
CDS_HOSTNAME = ConMgr.get_cds_hostnames()[0]

RHUA = ConMgr.connect()
CDS = ConMgr.connect(CDS_HOSTNAME)

NEW_FS_OPTIONS = "timeo=100"
FORCE_FLAG = " --remote-fs-force-change"

USE_CONTAINER = getenv("RHUICONTCDS") is not None

def _check_rhui_mountpoint(connection, fs_server, options="", container=False):
    """check the RHUI mountpoint"""
    cat = RhuiinContainers.exec_cmd("cds", "cat") if container else "cat"
    mount_info_files = ["/proc/mounts"]
    if not container:
        mount_info_files.append("/etc/fstab")
    for mount_info_file in mount_info_files:
        _, stdout, _ = connection.exec_command(f"{cat} {mount_info_file}")
        mounts = stdout.read().decode().splitlines()
        matches = [line for line in mounts if RHUI_ROOT in line]
        # there must be only one such share
        nose.tools.eq_(len(matches), 1,
                       msg=f"unexpected matches in {mount_info_file}: {matches}")
        # and it must be using the expected FS server
        properties = matches[0].split()
        actual_share = properties[0]
        test = actual_share.startswith(fs_server)
        nose.tools.ok_(test,
                       msg=f"{fs_server} not found in {mount_info_file}, found: {actual_share}")
        # if also checking options, find and compare them; options are in the fourth column
        if options:
            # in /proc/mounts, there are many options added by the NFS kernel module,
            # whereas in /etc/fstab the options are standalone
            actual_options = properties[3]
            test = options in actual_options if mount_info_file == "/proc/mounts" else \
                   actual_options == options
            nose.tools.ok_(test,
                           msg=f"{options} not found in {mount_info_file}, found: {actual_options}")

def setup():
    """announce the beginning of the test run"""
    print(f"*** Running {basename(__file__)}: ***")

def test_01_add_cds():
    """add a CDS"""
    RHUIManager.initial_run(RHUA)
    RHUIManagerCLIInstance.add(RHUA, "cds", CDS_HOSTNAME, container=USE_CONTAINER, unsafe=True)
    # check that
    cds_list = RHUIManagerCLIInstance.list(RHUA, "cds")
    nose.tools.ok_(cds_list)

def test_02_prep():
    """back up the answers file"""
    Config.backup_answers(RHUA)

def test_03_rerun_installer():
    """rerun the installer with a different remote FS server"""
    # the FS server is supposed to be on the RHUA, so let's use the RHUA hostname
    # get the actual FS server hostname from the answers file
    current_fs_server = Config.get_from_answers(RHUA, "remote_fs_server")
    fs_hostname = current_fs_server.split(":")[0]
    new_fs_server = current_fs_server.replace(fs_hostname, RHUA_HOSTNAME)
    # first, check if the installer refuses to rerun without the force flag
    installer_cmd = f"rhui-installer --rerun --remote-fs-server {new_fs_server}"
    Expect.expect_retval(RHUA, installer_cmd, 1)
    # then, use the force flag and rerun
    installer_cmd += FORCE_FLAG
    Expect.expect_retval(RHUA, installer_cmd, timeout=300)

def test_04_check_rhua_mountpoint():
    """check if the new remote share has replaced the old one on the RHUA"""
    _check_rhui_mountpoint(RHUA, RHUA_HOSTNAME)

def test_05_reinstall_cds():
    """reinstall the CDS"""
    RHUIManagerCLIInstance.reinstall(RHUA, "cds", CDS_HOSTNAME)

def test_06_check_cds_mountpoint():
    """check if the new remote share is now used on the CDS"""
    _check_rhui_mountpoint(CDS, RHUA_HOSTNAME, container=USE_CONTAINER)

def test_07_rerun_installer():
    """rerun the installer with different mount options"""
    # first check if the installer fails if options change but the force flag isn't used
    installer_cmd = f"rhui-installer --rerun --rhua-mount-options {NEW_FS_OPTIONS}"
    Expect.expect_retval(RHUA, installer_cmd, 1)
    # now with the force flag
    installer_cmd += FORCE_FLAG
    Expect.expect_retval(RHUA, installer_cmd, timeout=300)

def test_08_check_rhua_mountpoint():
    """check if the new options have replaced the old ones on the RHUA"""
    _check_rhui_mountpoint(RHUA, RHUA_HOSTNAME, NEW_FS_OPTIONS)

def test_09_reinstall_cds():
    """reinstall the CDS"""
    RHUIManagerCLIInstance.reinstall(RHUA, "cds", CDS_HOSTNAME)

def test_10_check_cds_mountpoint():
    """check if the new options are now used on the CDS"""
    _check_rhui_mountpoint(CDS, RHUA_HOSTNAME, NEW_FS_OPTIONS, USE_CONTAINER)

def test_99_cleanup():
    """clean up: delete the CDS and rerun the installer with the original remote FS"""
    RHUIManagerCLIInstance.delete(RHUA, "cds", [CDS_HOSTNAME], force=True)
    # get the original FS server hostname from the backed up answers file
    original_fs_server = Config.get_from_answers(RHUA, "remote_fs_server", ANSWERS_BAK)
    fs_hostname = original_fs_server.split(":")[0]
    original_fs_options = Config.get_from_answers(RHUA, "rhua_mount_options", ANSWERS_BAK)
    installer_cmd = f"rhui-installer --rerun " \
                    f"--remote-fs-server {original_fs_server} " \
                    f"--rhua-mount-options {original_fs_options}" \
                    f"{FORCE_FLAG}"
    Expect.expect_retval(RHUA, installer_cmd, timeout=300)
    # did it work?
    _check_rhui_mountpoint(RHUA, fs_hostname, original_fs_options)
    # finish the cleanup
    Config.restore_answers(RHUA)
    ConMgr.remove_ssh_keys(RHUA)

def teardown():
    """announce the end of the test run"""
    print(f"*** Finished running {basename(__file__)}. ***")
