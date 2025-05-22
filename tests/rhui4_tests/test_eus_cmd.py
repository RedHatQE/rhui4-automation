'''EUS Tests (for the CLI)'''

# To skip the upload of an entitlement certificate and the registration of CDS and HAProxy nodes --
# because you want to save time in each client test case and do this beforehand -- run:
# export RHUISKIPSETUP=1
# in your shell before running this script.
# The cleanup will be skipped, too, so you ought to clean up eventually.

from os import getenv
from os.path import basename
import re

import logging
import nose
from stitches.expect import Expect
import yaml

from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.rhuimanager_cmdline_instance import RHUIManagerCLIInstance
from rhui4_tests_lib.rhuimanager import RHUIManager
from rhui4_tests_lib.rhuimanager_cmdline import RHUIManagerCLI
from rhui4_tests_lib.util import Util
from rhui4_tests_lib.yummy import Yummy

logging.basicConfig(level=logging.DEBUG)

RHUA = ConMgr.connect()
# __reusable_clients_with_cds
# To make this script communicate with a client machine different from cli01.example.com, run:
# export RHUICLI=hostname
# in your shell before running this script, replacing "hostname" with the actual client host name.
# This allows for multiple client machines in one stack.
CLI = ConMgr.connect(getenv("RHUICLI", ConMgr.get_cli_hostnames()[0]))

CONF_RPM_NAME = "eus-rhui"
TMPDIR = "/tmp/" + CONF_RPM_NAME

class TestEUSCLI():
    '''
    class to test EUS repos via the CLI
    '''

    def __init__(self):
        version = Util.get_rhel_version(CLI)["major"]
        arch = Util.get_arch(CLI)
        with open("/etc/rhui4_tests/tested_repos.yaml", encoding="utf-8") as configfile:
            doc = yaml.safe_load(configfile)
            try:
                self.repo_id = doc["EUS_repos"][version][arch]["id"]
                self.repo_label = doc["EUS_repos"][version][arch]["label"]
                self.repo_path = doc["EUS_repos"][version][arch]["path"]
                self.test_package = doc["EUS_repos"][version][arch]["test_package"]
            except KeyError as version:
                raise nose.SkipTest(f"No test repo defined for RHEL {version}")

    @staticmethod
    def setup_class():
        '''
        announce the beginning of the test run
        '''
        print(f"*** Running {basename(__file__)}: ***")

    @staticmethod
    def test_01_initial_run():
        '''
        log in to RHUI
        '''
        if not getenv("RHUISKIPSETUP"):
            RHUIManager.initial_run(RHUA)

    @staticmethod
    def test_02_add_cds():
        '''
        add a CDS
        '''
        if not getenv("RHUISKIPSETUP"):
            RHUIManagerCLIInstance.add(RHUA, "cds", unsafe=True)
        # check that
        cds_list = RHUIManagerCLIInstance.list(RHUA, "cds")
        nose.tools.ok_(cds_list)

    @staticmethod
    def test_03_add_hap():
        '''
        add an HAProxy Load-Balancer
        '''
        if not getenv("RHUISKIPSETUP"):
            RHUIManagerCLIInstance.add(RHUA, "haproxy", unsafe=True)
        # check that
        hap_list = RHUIManagerCLIInstance.list(RHUA, "haproxy")
        nose.tools.ok_(hap_list)

    @staticmethod
    def test_04_upload_certificate():
        '''
        upload an entitlement certificate
        '''
        if not getenv("RHUISKIPSETUP"):
            RHUIManagerCLI.cert_upload(RHUA)

    def test_05_add_repo(self):
        '''
        add the tested repo
        '''
        RHUIManagerCLI.repo_add_by_repo(RHUA, [self.repo_id])

    def test_06_sync_repo(self):
        '''
        sync the repo
        '''
        # try the non-json way to wait for the repo sync
        RHUIManagerCLI.repo_sync(RHUA, self.repo_id, use_json=False)

    def test_08_create_cli_config_rpm(self):
        '''
        create an entitlement certificate and a client configuration RPM (in one step)
        '''
        RHUIManagerCLI.client_rpm(RHUA, [self.repo_label], [CONF_RPM_NAME], "/tmp")

    @staticmethod
    def test_09_install_conf_rpm():
        '''
        install the client configuration RPM
        '''
        # get rid of undesired repos first
        Util.remove_amazon_rhui_conf_rpm(CLI)
        Util.disable_beta_repos(CLI)
        Util.install_pkg_from_rhua(RHUA,
                                   CLI,
                                   f"/tmp/{CONF_RPM_NAME}-2.0/build/RPMS/noarch/" +
                                   f"{CONF_RPM_NAME}-2.0-1.noarch.rpm")

    def test_10_set_eus_release(self):
        '''
        set the tested EUS release in Yum configuration
        '''
        # the repo id is ...rpms-X.Y-ARCH or ...rpms-X.Y
        # so use regex matching to find the release
        eus_release = re.search(r"[0-9]+\.[0-9]+", self.repo_path).group()
        Expect.expect_retval(CLI, "rhui-set-release --set " + eus_release)

    def test_11_check_package_url(self):
        '''
        check if Yum is now working with the EUS URL
        '''
        Util.check_package_url(CLI, self.test_package, self.repo_path)

    def test_12_download_test_rpm(self):
        '''
        download the test package (from the test repo)
        '''
        Yummy.download(CLI, [self.test_package], TMPDIR)
        # check it
        Expect.expect_retval(CLI, f"ls {TMPDIR}/{self.test_package}*")

    def test_99_cleanup(self):
        '''clean up'''
        Expect.expect_retval(CLI, "rhui-set-release --unset")
        Util.remove_rpm(CLI, [CONF_RPM_NAME])
        Expect.expect_retval(CLI, f"rm -rf {TMPDIR}")
        RHUIManagerCLI.repo_delete(RHUA, self.repo_id)
        Expect.expect_retval(RHUA, f"rm -rf /tmp/{CONF_RPM_NAME}*")
        if not getenv("RHUISKIPSETUP"):
            RHUIManager.remove_rh_certs(RHUA)
            RHUIManagerCLIInstance.delete(RHUA, "haproxy", force=True)
            RHUIManagerCLIInstance.delete(RHUA, "cds", force=True)
            ConMgr.remove_ssh_keys(RHUA)

    @staticmethod
    def teardown_class():
        '''
           announce the end of the test run
        '''
        print(f"*** Finished running {basename(__file__)}. ***")
