"""Tests for custom certificates"""

# To keep the custom certificates after installing them, run:
# export RHUIKEEPCUSTOMCERTS=1
# in your shell before running this script.
#
# This will also preserve CDS01 and the HAProxy node.
#
# If you have multiple CDS nodes, run:
# rhuitestsetup --ssl-like-cds-one
# Else, run:
# rhuitestsetup
#
# Regardless of the number of your CDS nodes, run:
# export RHUISKIPSETUP=1
# and continue with client tests using this custom SSL configuration.

from os import getenv
from os.path import basename

import logging
import nose
from stitches.expect import Expect

from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.rhuimanager import RHUIManager
from rhui4_tests_lib.rhuimanager_instance import RHUIManagerInstance
from rhui4_tests_lib.rhuimanager_cmdline_instance import RHUIManagerCLIInstance

logging.basicConfig(level=logging.DEBUG)

RHUA = ConMgr.connect()
CDS_HOSTNAME = ConMgr.get_cds_hostnames()[0]
CDS = ConMgr.connect(CDS_HOSTNAME)
HAPROXY_HOSTNAME = ConMgr.get_cds_lb_hostname()

CUSTOM_CERTS_DIR = "/tmp/extra_rhui_files/custom_certs"
ORIG_CERTS_BASEDIR = "/etc/pki/rhui"
ORIG_CERTS_SUBDIR = "certs"
ORIG_KEYS_SUBDIR = "private"
BACKUPDIR = "/root"

FILES = {
         "rhui": "ca",
         "client_ssl": "client_ssl_ca",
         "client_entitlement": "client_entitlement_ca",
         "cds_ssl": "ssl"
        }

def _check_crt_key():
    """check if the cert and the key are on the CDS"""
    for ext in ["crt", "key"]:
        _, stdout, _ = RHUA.exec_command(f"md5sum {CUSTOM_CERTS_DIR}/{FILES['cds_ssl']}.{ext}")
        expected_sum = stdout.read().decode().split()[0]

        _, stdout, _ = CDS.exec_command(f"md5sum /etc/pki/rhui/certs/{CDS_HOSTNAME}.{ext}")
        actual_sum = stdout.read().decode().split()[0]
        nose.tools.eq_(expected_sum, actual_sum)

def _delete_crt_key():
    """delete the cert and the key from the CDS"""
    for ext in ["crt", "key"]:
        Expect.expect_retval(CDS,
                             f"rm -f /etc/pki/rhui/certs/{CDS_HOSTNAME}.{ext}")

def _check_instance_add_error():
    """check the error message after adding an instance incorrectly"""
    _, stdout, _ = RHUA.exec_command("tail -1 /root/.rhui/rhui.log")
    lastlogline = stdout.read().decode().strip()
    expected_error = f"Error: CDS: {CDS_HOSTNAME} is already configured " \
                     "with different SSL certificates."
    nose.tools.eq_(lastlogline, expected_error)

def setup():
    """announce the beginning of the test run"""
    print(f"*** Running {basename(__file__)}: ***")

def test_01_check_custom_files():
    """check if all the custom certificates and keys exist"""
    for basefile in FILES.values():
        Expect.expect_retval(RHUA, f"test -f {CUSTOM_CERTS_DIR}/{basefile}.crt")
        Expect.expect_retval(RHUA, f"test -f {CUSTOM_CERTS_DIR}/{basefile}.key")

def test_02_backup():
    """back up the original certificates and keys"""
    Expect.expect_retval(RHUA, f"cp -a {ORIG_CERTS_BASEDIR}/{ORIG_CERTS_SUBDIR} {BACKUPDIR}")
    Expect.expect_retval(RHUA, f"cp -a {ORIG_CERTS_BASEDIR}/{ORIG_KEYS_SUBDIR} {BACKUPDIR}")

def test_03_rerun_installer():
    """rerun the installer with the custom certificates and keys"""
    cmd = "rhui-installer --rerun " \
          f"--user-supplied-rhui-ca-crt {CUSTOM_CERTS_DIR}/{FILES['rhui']}.crt " \
          f"--user-supplied-rhui-ca-key {CUSTOM_CERTS_DIR}/{FILES['rhui']}.key " \
          f"--user-supplied-client-ssl-ca-crt {CUSTOM_CERTS_DIR}/{FILES['client_ssl']}.crt " \
          f"--user-supplied-client-ssl-ca-key {CUSTOM_CERTS_DIR}/{FILES['client_ssl']}.key " \
          "--user-supplied-client-entitlement-ca-crt " \
          f"{CUSTOM_CERTS_DIR}/{FILES['client_entitlement']}.crt " \
          "--user-supplied-client-entitlement-ca-key " \
          f"{CUSTOM_CERTS_DIR}/{FILES['client_entitlement']}.key"
    Expect.expect_retval(RHUA, cmd, timeout=300)

def test_04_check_installed_files():
    """check if the custom certificates and keys were really installed"""
    for _, fname in FILES.items():
        # only check CA certs and keys, though
        if not fname.endswith("ca"):
            continue
        Expect.expect_retval(RHUA, "cmp "
                                   f"{CUSTOM_CERTS_DIR}/{fname}.crt "
                                   f"{ORIG_CERTS_BASEDIR}/{ORIG_CERTS_SUBDIR}/{fname}.crt")
        Expect.expect_retval(RHUA, "cmp "
                                   f"{CUSTOM_CERTS_DIR}/{fname}.key "
                                   f"{ORIG_CERTS_BASEDIR}/{ORIG_KEYS_SUBDIR}/{fname}.key")

def test_05_add_cds():
    """[TUI] add a CDS with a custom SSL cert and key"""
    RHUIManager.initial_run(RHUA)
    RHUIManagerInstance.add_instance(RHUA,
                                     "cds",
                                     CDS_HOSTNAME,
                                     ssl_crt=f"{CUSTOM_CERTS_DIR}/{FILES['cds_ssl']}.crt",
                                     ssl_key=f"{CUSTOM_CERTS_DIR}/{FILES['cds_ssl']}.key")

def test_06_check_cds():
    """check if the files are on the CDS"""
    _check_crt_key()

def test_07_delete_cds():
    """delete the CDS so it can be added using the CLI"""
    RHUIManagerInstance.delete_all(RHUA, "cds")
    # also delete the files from the CDS
    _delete_crt_key()

def test_08_add_cds():
    """[CLI] add a CDS with a custom SSL cert and key"""
    RHUIManagerCLIInstance.add(RHUA,
                               "cds",
                               CDS_HOSTNAME,
                               ssl_crt=f"{CUSTOM_CERTS_DIR}/{FILES['cds_ssl']}.crt",
                               ssl_key=f"{CUSTOM_CERTS_DIR}/{FILES['cds_ssl']}.key",
                               unsafe=True)

def test_09_check_cert_on_cds():
    """check if the files are on the CDS"""
    _check_crt_key()

def test_10_add_cds_without_custom_ssl():
    """check if another CDS cannot be added without a custom SSL certificate"""
    # first, the function to add a CDS with that configuration should return False
    nose.tools.ok_(not RHUIManagerCLIInstance.add(RHUA, "cds", "foo.example.com", unsafe=True))
    # also, an appropriate error should be logged
    _check_instance_add_error()

def test_11_add_cds_with_other_custom_ssl():
    """check if another CDS cannot be added with a different SSL certificate"""
    # first, the function to add a CDS with that configuration should return False
    keyfile = f"{CUSTOM_CERTS_DIR}/{FILES['cds_ssl']}.key"
    nose.tools.ok_(not RHUIManagerCLIInstance.add(RHUA,
                                                  "cds",
                                                  "foo.example.com",
                                                  ssl_crt="/etc/issue",
                                                  ssl_key=keyfile,
                                                  unsafe=True))
    # also, an appropriate error should be logged
    _check_instance_add_error()

def test_12_add_haproxy():
    """add an HAProxy node (no special parameters)"""
    nose.tools.ok_(RHUIManagerCLIInstance.add(RHUA, "haproxy", unsafe=True))

def test_13_check_nodes():
    """check if only the expected nodes are present"""
    expected_nodes = [CDS_HOSTNAME, HAPROXY_HOSTNAME]
    actual_nodes = RHUIManagerCLIInstance.list(RHUA, "cds") + \
                   RHUIManagerCLIInstance.list(RHUA, "haproxy")
    nose.tools.eq_(expected_nodes, actual_nodes)

def test_99_cleanup():
    """clean up: rerun the installer with the original certificates and keys, remove the nodes"""
    if getenv("RHUIKEEPCUSTOMCERTS"):
        raise nose.SkipTest("Prevented")
    cmd = "rhui-installer --rerun " \
          "--user-supplied-rhui-ca-crt " \
          f"{BACKUPDIR}/{ORIG_CERTS_SUBDIR}/{FILES['rhui']}.crt " \
          "--user-supplied-rhui-ca-key " \
          f"{BACKUPDIR}/{ORIG_KEYS_SUBDIR}/{FILES['rhui']}.key " \
          "--user-supplied-client-ssl-ca-crt " \
          f"{BACKUPDIR}/{ORIG_CERTS_SUBDIR}/{FILES['client_ssl']}.crt " \
          "--user-supplied-client-ssl-ca-key " \
          f"{BACKUPDIR}/{ORIG_KEYS_SUBDIR}/{FILES['client_ssl']}.key " \
          "--user-supplied-client-entitlement-ca-crt" \
          f" {BACKUPDIR}/{ORIG_CERTS_SUBDIR}/{FILES['client_entitlement']}.crt " \
          "--user-supplied-client-entitlement-ca-key" \
          f" {BACKUPDIR}/{ORIG_KEYS_SUBDIR}/{FILES['client_entitlement']}.key"
    Expect.expect_retval(RHUA, cmd, timeout=300)
    Expect.expect_retval(RHUA,
                         "rm -rf "
                         f"{BACKUPDIR}/{ORIG_CERTS_SUBDIR} "
                         f"{BACKUPDIR}/{ORIG_KEYS_SUBDIR}")
    # the user supplied certificate options must be cleared in the answers file now
    cmd = r"sed -i 's/\(user_supplied_[^:]*\).*/\1: null/' /root/.rhui/answers.yaml"
    Expect.expect_retval(RHUA, cmd)
    RHUIManagerCLIInstance.delete(RHUA, "cds", [CDS_HOSTNAME], force=True)
    RHUIManagerCLIInstance.delete(RHUA, "haproxy", [HAPROXY_HOSTNAME], force=True)
    ConMgr.remove_ssh_keys(RHUA)
    _delete_crt_key()

def teardown():
    """announce the end of the test run"""
    print(f"*** Finished running {basename(__file__)}. ***")
