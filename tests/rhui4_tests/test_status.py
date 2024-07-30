""" Test case for the RHUI status command"""

# To skip the upload of an entitlement certificate and the registration of a CDS --
# because you want to save time and do this beforehand -- run:
# export RHUISKIPSETUP=1
# in your shell before running this script.
# The cleanup will be skipped, too, so you ought to clean up eventually.

import logging
from os import getenv
from os.path import basename

import json
import nose
from stitches.expect import Expect
import yaml

from rhui4_tests_lib.cfg import Config
from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.rhuimanager import RHUIManager
from rhui4_tests_lib.rhuimanager_cmdline import RHUIManagerCLI
from rhui4_tests_lib.rhuimanager_cmdline_instance import RHUIManagerCLIInstance

logging.basicConfig(level=logging.DEBUG)

# error bits
OK = 0
REPO_SYNC_ERROR = 1
CDS_EMERG_WARN = 2
CERT_WARN = 32
CERT_ERROR = 64
SERVICE_ERROR = 128

RHUA = ConMgr.connect()
HA_HOSTNAME = ConMgr.get_lb_hostname()
HAPROXY = ConMgr.connect(HA_HOSTNAME)
CDS_HOSTNAME = ConMgr.get_cds_hostnames()[0]
CDS = ConMgr.connect(CDS_HOSTNAME)

CMD = "rhui-manager status --code"
TIMEOUT = 60

MACH_READ_CMD = "rhui-manager status --repo_json"
MACH_READ_FILE = "/tmp/repo_status.json"

SSL_CERT = "/etc/pki/rhui/certs/cds_ssl.crt"

class TestRhuiManagerStatus():
    """class for the rhui-manager status tests """
    def __init__(self):
        with open("/etc/rhui4_tests/tested_repos.yaml", encoding="utf-8") as configfile:
            doc = yaml.safe_load(configfile)
            self.good_repo = doc["status_repos"]["good"]
            self.bad_repo = doc["status_repos"]["bad"]

    @staticmethod
    def setup_class():
        """announce the beginning of the test run"""
        print(f"*** Running {basename(__file__)}: ***")

    @staticmethod
    def test_00_rhui_init():
        """log in to RHUI and upload a certificate"""
        if not getenv("RHUISKIPSETUP"):
            RHUIManager.initial_run(RHUA)
            RHUIManagerCLI.cert_upload(RHUA)

    @staticmethod
    def test_01_status():
        """run the status command on the clean RHUA"""
        expected_exit_code = OK
        Expect.expect_retval(RHUA, CMD, expected_exit_code, TIMEOUT)

    def test_02_add_repos(self):
        """add test repos"""
        RHUIManagerCLI.repo_add_by_repo(RHUA, [self.good_repo, self.bad_repo])

    @staticmethod
    def test_03_status():
        """run the status command with unsynced repos"""
        expected_exit_code = OK
        Expect.expect_retval(RHUA, CMD, expected_exit_code, TIMEOUT)

    @staticmethod
    def test_04_add_cds_hap():
        """add a CDS node and an HAProxy Load-Balancer"""
        if not getenv("RHUISKIPSETUP"):
            RHUIManagerCLIInstance.add(RHUA, "cds", unsafe=True)
            RHUIManagerCLIInstance.add(RHUA, "haproxy", unsafe=True)

    @staticmethod
    def test_05_status():
        """run the status command with the added CDS and Load-Balancer"""
        expected_exit_code = OK
        Expect.expect_retval(RHUA, CMD, expected_exit_code, TIMEOUT)

    def test_06_sync_check_good_repo(self):
        """sync the good repo and expect a good status"""
        RHUIManagerCLI.repo_sync(RHUA, self.good_repo)
        expected_exit_code = OK
        Expect.expect_retval(RHUA, CMD, expected_exit_code, TIMEOUT)

    def test_07_sync_check_bad_repo(self):
        """sync the bad repo and expect a bad status"""
        RHUIManagerCLI.repo_sync(RHUA, self.bad_repo, False)
        expected_exit_code = REPO_SYNC_ERROR
        Expect.expect_retval(RHUA, CMD, expected_exit_code, TIMEOUT)

    @staticmethod
    def test_08_check_expiration():
        """change the expiration threshold and expect another bad status"""
        Config.edit_rhui_tools_conf(RHUA, "expiration_warning", "36525")
        expected_exit_code = REPO_SYNC_ERROR + CERT_WARN
        Expect.expect_retval(RHUA, CMD, expected_exit_code, TIMEOUT)

    @staticmethod
    def test_09_check_broken_external_service():
        """turn off the haproxy service, check status, and expect yet another bad status"""
        Expect.expect_retval(HAPROXY, "systemctl stop haproxy")
        expected_exit_code = REPO_SYNC_ERROR + CERT_WARN + SERVICE_ERROR
        Expect.expect_retval(RHUA, CMD, expected_exit_code, TIMEOUT)

    def test_10_repo_status_json(self):
        """generate a machine-readable file with repo states and check it"""
        # for RHBZ#2079391
        Expect.expect_retval(RHUA, f"{MACH_READ_CMD} {MACH_READ_FILE}")
        _, stdout, _ = RHUA.exec_command(f"cat {MACH_READ_FILE}")
        repo_states = json.load(stdout)
        # are both test repos present?
        actual_repo_ids = [repo["id"] for repo in repo_states]
        actual_repo_ids.sort()
        expected_repo_ids = [self.good_repo, self.bad_repo]
        expected_repo_ids.sort()
        nose.tools.eq_(actual_repo_ids, expected_repo_ids)
        # split the output
        if actual_repo_ids[0] == self.good_repo:
            actually_good_repo, actually_bad_repo = repo_states
        else:
            actually_bad_repo, actually_good_repo = repo_states
        # check the good repo
        nose.tools.ok_(not actually_good_repo["last_sync_exception"])
        nose.tools.ok_(not actually_good_repo["last_sync_traceback"])
        nose.tools.ok_(actually_good_repo["last_sync_date"])
        nose.tools.ok_(actually_good_repo["repo_published"])
        nose.tools.eq_(actually_good_repo["group"], "redhat")
        # check the bad repo
        nose.tools.ok_("404" in actually_bad_repo["last_sync_exception"],
                       msg=actually_bad_repo["last_sync_exception"])
        nose.tools.ok_("raise" in actually_bad_repo["last_sync_traceback"],
                       msg=actually_bad_repo["last_sync_traceback"])
        nose.tools.ok_(actually_bad_repo["last_sync_date"])
        nose.tools.ok_(actually_bad_repo["repo_published"])
        nose.tools.eq_(actually_bad_repo["group"], "redhat")

    def test_11_check_broken_ssl_cert(self):
        """remove the SSL cert from the CDS, check status, and expect yet another bad status"""
        Expect.expect_retval(CDS, f"mv {SSL_CERT} /tmp")
        expected_exit_code = REPO_SYNC_ERROR + CDS_EMERG_WARN + CERT_WARN + SERVICE_ERROR
        Expect.expect_retval(RHUA, CMD, expected_exit_code, TIMEOUT)

    def test_12_check_expired_ssl_cert(self):
        """use an expired SSL cert on the CDS, check status, and expect yet another bad status"""
        # fetch the expired entitlement cert from the RHUA
        _, stdout, _ = RHUA.exec_command("cat /tmp/extra_rhui_files/rhcert_expired.pem")
        cert_data = stdout.read().decode()
        stdin, _, _ = CDS.exec_command(f"cat > {SSL_CERT}")
        stdin.write(cert_data)
        stdin.close()
        expected_exit_code = REPO_SYNC_ERROR + CERT_WARN + CERT_ERROR + SERVICE_ERROR
        Expect.expect_retval(RHUA, CMD, expected_exit_code, TIMEOUT)

    def test_13_check_broken_pulp_worker_service(self):
        """fix the environment but turn off a Pulp worker, expect a service error"""
        # for RHBZ#2174633
        Expect.expect_retval(HAPROXY, "systemctl start haproxy")
        RHUIManagerCLI.repo_delete(RHUA, self.bad_repo)
        Config.restore_rhui_tools_conf(RHUA)
        Expect.expect_retval(CDS, f"mv -f /tmp/{basename(SSL_CERT)} {SSL_CERT}")
        Expect.expect_retval(RHUA, "systemctl stop pulpcore-worker@2")
        expected_exit_code = SERVICE_ERROR
        Expect.expect_retval(RHUA, CMD, expected_exit_code, TIMEOUT)

    @staticmethod
    def test_14_check_output_with___code():
        """restart everything, check if the output is only the return code when --code is used"""
        # this test also checks if rhui-services-restart (re)starts a worker which is down
        Expect.expect_retval(RHUA, "rhui-services-restart", timeout=60)
        _, stdout, _ = RHUA.exec_command(CMD)
        output = stdout.read().decode().splitlines()
        nose.tools.eq_(len(output), 1)
        nose.tools.eq_(output[0], str(OK))

    def test_99_cleanup(self):
        """clean up"""
        Expect.expect_retval(RHUA, f"rm -f {MACH_READ_FILE}")
        RHUIManagerCLI.repo_delete(RHUA, self.good_repo)
        if not getenv("RHUISKIPSETUP"):
            RHUIManager.remove_rh_certs(RHUA)
            RHUIManagerCLIInstance.delete(RHUA, "haproxy", force=True)
            RHUIManagerCLIInstance.delete(RHUA, "cds", force=True)
            ConMgr.remove_ssh_keys(RHUA)

    @staticmethod
    def teardown_class():
        """announce the end of the test run"""
        print(f"*** Finished running {basename(__file__)}. ***")
