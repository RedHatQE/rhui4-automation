"""Client Tests for Containerized RHUI Nodes"""

from os import getenv
from os.path import basename

import logging
import nose
from stitches.expect import Expect
import yaml

from rhui4_tests_lib.cfg import LEGACY_CA_DIR
from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.helpers import Helpers
from rhui4_tests_lib.incontainers import RhuiinContainers
from rhui4_tests_lib.rhuimanager import RHUIManager
from rhui4_tests_lib.rhuimanager_cmdline import RHUIManagerCLI
from rhui4_tests_lib.rhuimanager_cmdline_instance import RHUIManagerCLIInstance
from rhui4_tests_lib.util import Util
from rhui4_tests_lib.yummy import Yummy

logging.basicConfig(level=logging.DEBUG)

RHUA = ConMgr.connect()
# To make this script communicate with a client machine different from cli01.example.com, run:
# export RHUICLI=hostname
# in your shell before running this script, replacing "hostname" with the actual client host name.
# This allows for multiple client machines in one stack.
CLI = ConMgr.connect(getenv("RHUICLI", ConMgr.get_cli_hostnames()[0]))
CDS = ConMgr.connect(ConMgr.get_cds_hostnames()[0])

LEGACY_CA_FILE = "legacy_ca.crt"
TMPDIR = "/tmp/test_client_of_containerized_rhui"
CONF_RPM_NAME = "test-containerized-nodes"

class TestClientofContainerizedRHUI():
    """class to test containerized RHUI nodes"""
    def __init__(self):
        self.version = Util.get_rhel_version(CLI)["major"]
        arch = Util.get_arch(CLI)
        with open("/etc/rhui4_tests/tested_repos.yaml", encoding="utf-8") as configfile:
            doc = yaml.safe_load(configfile)
            self.repo_id = doc["yum_repos"][self.version][arch]["id"]
            self.repo_label = doc["yum_repos"][self.version][arch]["label"]
            self.test_package = doc["yum_repos"][self.version][arch]["test_package"]

    @staticmethod
    def setup_class():
        """announce the beginning of the test run"""
        print(f"*** Running {basename(__file__)}: ***")

    @staticmethod
    def test_01_setup():
        """log in to RHUI"""
        RHUIManager.initial_run(RHUA)

    @staticmethod
    def test_02_add_cds():
        """add a containerized CDS node"""
        status = RHUIManagerCLIInstance.add(RHUA, "cds", container=True, unsafe=True)
        nose.tools.ok_(status, msg=f"unexpected CDS addition status: {status}")

    @staticmethod
    def test_03_add_hap():
        """add an HAProxy node"""
        # not yet containerized
        status = RHUIManagerCLIInstance.add(RHUA, "haproxy", unsafe=True)
        nose.tools.ok_(status, msg=f"unexpected HAProxy addition status: {status}")

    def test_04_rhui_manager_status(self):
        """check the status of RHUI services"""
        Expect.expect_retval(RHUA, "rhui-manager status --code", 0, 60)

    def test_05_upload_cert(self):
        """upload the entitlement certificate"""
        RHUIManagerCLI.cert_upload(RHUA)

    def test_06_add_sync_repos(self):
        """add a and sync the Red Hat repo"""
        RHUIManagerCLI.repo_add_by_repo(RHUA, [self.repo_id], True)

    def test_07_create_cli_config_rpm(self):
        """create a client configuration RPM for the repo"""
        RHUIManagerCLI.client_rpm(RHUA, [self.repo_label], [CONF_RPM_NAME], TMPDIR)

    @staticmethod
    def test_08_install_config_rpm():
        """install the client configuration RPM"""
        # get rid of undesired repos first
        Util.remove_amazon_rhui_conf_rpm(CLI)
        Util.disable_beta_repos(CLI)
        Util.install_pkg_from_rhua(RHUA,
                                   CLI,
                                   f"{TMPDIR}/{CONF_RPM_NAME}-2.0/build/RPMS/noarch/" +
                                   f"{CONF_RPM_NAME}-2.0-1.noarch.rpm")

    def test_09_install_test_rpm(self):
        """try installing the test package from the test repo"""
        Yummy.install(CLI, [self.test_package])
        # check it
        Expect.expect_retval(CLI, "rpm -q " + self.test_package)

    @staticmethod
    def test_10_legacy_ca():
        """check for proper logs if a legacy CA is used"""
        # get the CA cert from the RHUA and upload it to the CDS
        # the cert is among the extra RHUI files, ie. in the directory also containing custom RPMs
        remote_ca_file = f"/tmp/extra_rhui_files/{LEGACY_CA_FILE}"
        Util.fetch(RHUA, remote_ca_file, f"/tmp/{LEGACY_CA_FILE}")
        Helpers.add_legacy_ca(CDS, f"/tmp/{LEGACY_CA_FILE}")
        # re-fetch repodata on the client to trigger the OID validator on the CDS
        Expect.expect_retval(CLI, "yum clean all ; yum -v repolist enabled")
        Expect.expect_retval(CDS,
                             RhuiinContainers.exec_cmd("cds", "grep") +
                             f" 'Found file {LEGACY_CA_DIR}/{LEGACY_CA_FILE}'" +
                             " /var/log/nginx/gunicorn-auth.log")

    def test_99_cleanup(self):
        """clean up"""
        # uninstall the test package and the client configuration package
        Util.remove_rpm(CLI, [self.test_package, CONF_RPM_NAME])
        # remove the artifacts from the RHUA
        Expect.expect_retval(RHUA, f"rm -rf {TMPDIR}")
        # remove the test repo
        RHUIManagerCLI.repo_delete(RHUA, self.repo_id)
        # remove the entitlement certifite
        RHUIManager.remove_rh_certs(RHUA)
        # uninstall HAProxy & CDS, forget their keys
        Helpers.del_legacy_ca(CDS)
        RHUIManagerCLIInstance.delete(RHUA, "haproxy", force=True)
        RHUIManagerCLIInstance.delete(RHUA, "cds", force=True)
        ConMgr.remove_ssh_keys(RHUA)

    @staticmethod
    def teardown_class():
        """announce the end of the test run"""
        print(f"*** Finished running {basename(__file__)}. ***")
