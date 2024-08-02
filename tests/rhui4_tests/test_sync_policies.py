"""Tests for Configurable Sync Policies"""

# To skip the registration of CDS and HAProxy nodes --
# because you want to save time in each client test case and do this beforehand -- run:
# export RHUISKIPSETUP=1
# in your shell before running this script.
# The cleanup will be skipped, too, so you ought to clean up eventually.

from os import getenv
from os.path import basename

import logging
import nose
from stitches.expect import Expect
import yaml

from rhui4_tests_lib.cfg import Config
from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.helpers import Helpers
from rhui4_tests_lib.pulp_api import PulpAPI
from rhui4_tests_lib.rhuimanager import RHUIManager
from rhui4_tests_lib.rhuimanager_cmdline import RHUIManagerCLI
from rhui4_tests_lib.rhuimanager_cmdline_instance import RHUIManagerCLIInstance
from rhui4_tests_lib.util import Util

logging.basicConfig(level=logging.DEBUG)

RHUA = ConMgr.connect()
# __reusable_clients_with_cds
# To make this script communicate with a client machine different from cli01.example.com, run:
# export RHUICLI=hostname
# in your shell before running this script, replacing "hostname" with the actual client host name.
# This allows for multiple client machines in one stack.
CLI = ConMgr.connect(getenv("RHUICLI", ConMgr.get_cli_hostnames()[0]))

POLICIES = {"default": "immediate", "nondefault": "on_demand"}
NAME = "test-sync-policies"
WORKDIR = f"/tmp/{NAME}"
DOWNLOAD_CMD = f"yumdownloader --downloaddir {WORKDIR}"

class TestSyncPolicies():
    """class to test sync policies"""
    def __init__(self):
        self.version = Util.get_rhel_version(CLI)["major"]
        arch = Util.get_arch(CLI)
        if arch != "x86_64":
            raise nose.SkipTest(f"This test is not available on {arch}")
        with open("/etc/rhui4_tests/tested_repos.yaml", encoding="utf-8") as configfile:
            doc = yaml.safe_load(configfile)
            try:
                self.regular_repo = doc["sync_policy_repos"][self.version]["regular"]
                self.debug_repo = doc["sync_policy_repos"][self.version]["debug"]
                self.source_repo = doc["sync_policy_repos"][self.version]["source"]
                self.test_package = doc["sync_policy_repos"][self.version]["test_package"]
            except KeyError:
                raise nose.SkipTest(f"Not all test repos defined for RHEL {self.version}") \
                from None

    @staticmethod
    def setup_class():
        """announce the beginning of the test run"""
        print(f"*** Running {basename(__file__)}: ***")

    @staticmethod
    def test_01_setup():
        """log in to RHUI, ensure CDS & HAProxy nodes have been added"""
        if not getenv("RHUISKIPSETUP"):
            RHUIManager.initial_run(RHUA)
            RHUIManagerCLI.cert_upload(RHUA)
            RHUIManagerCLIInstance.add(RHUA, "cds", unsafe=True)
            RHUIManagerCLIInstance.add(RHUA, "haproxy", unsafe=True)
        # check that
        cds_list = RHUIManagerCLIInstance.list(RHUA, "cds")
        nose.tools.ok_(cds_list)
        hap_list = RHUIManagerCLIInstance.list(RHUA, "haproxy")
        nose.tools.ok_(hap_list)

    def test_02_add_check_regular_repo_default(self):
        """add a regular repo and check its default sync policy"""
        RHUIManagerCLI.repo_add_by_repo(RHUA, [self.regular_repo])
        remote_data = PulpAPI.get_remote(RHUA, self.regular_repo)
        actual_policy = remote_data["policy"]
        nose.tools.eq_(actual_policy, POLICIES["default"])

    def test_03_add_check_debug_repo_default(self):
        """add a debug repo and check its default sync policy"""
        RHUIManagerCLI.repo_add_by_repo(RHUA, [self.debug_repo])
        remote_data = PulpAPI.get_remote(RHUA, self.debug_repo)
        actual_policy = remote_data["policy"]
        nose.tools.eq_(actual_policy, POLICIES["default"])

    def test_04_add_check_source_repo_default(self):
        """add a source repo and check its default sync policy"""
        RHUIManagerCLI.repo_add_by_repo(RHUA, [self.source_repo])
        remote_data = PulpAPI.get_remote(RHUA, self.source_repo)
        actual_policy = remote_data["policy"]
        nose.tools.eq_(actual_policy, POLICIES["default"])

    @staticmethod
    def test_05_set_non_default_policy():
        """set the non-default sync policy as the default and trigger repo synchronizations"""
        Config.set_sync_policy(RHUA, "default", POLICIES["nondefault"])
        RHUIManagerCLI.repo_sync_all(RHUA)

    def test_06_check_regular_repo_non_default(self):
        """check if the sync policy of the regular repo is now non-default"""
        remote_data = PulpAPI.get_remote(RHUA, self.regular_repo)
        actual_policy = remote_data["policy"]
        nose.tools.eq_(actual_policy, POLICIES["nondefault"])

    def test_07_check_debug_repo_non_default(self):
        """check if the sync policy of the debug repo is now non-default"""
        remote_data = PulpAPI.get_remote(RHUA, self.debug_repo)
        actual_policy = remote_data["policy"]
        nose.tools.eq_(actual_policy, POLICIES["nondefault"])

    def test_08_check_source_repo_non_default(self):
        """check if the sync policy of the source repo is now non-default"""
        remote_data = PulpAPI.get_remote(RHUA, self.source_repo)
        actual_policy = remote_data["policy"]
        nose.tools.eq_(actual_policy, POLICIES["nondefault"])

    def test_09_readd_repos_non_default_policies(self):
        """remove the repos, set non-default policies, re-add the repos, and sync them"""
        for repo in [self.regular_repo, self.debug_repo, self.source_repo]:
            RHUIManagerCLI.repo_delete(RHUA, repo)
        # reset the default policy to the default value first
        Config.set_sync_policy(RHUA, "default", POLICIES["default"], False)
        # then the individual types
        Config.set_sync_policy(RHUA, "rpm", POLICIES["nondefault"], False)
        Config.set_sync_policy(RHUA, "source", POLICIES["nondefault"], False)
        Config.set_sync_policy(RHUA, "debug", POLICIES["nondefault"], False)
        # add the regular, debug, and source repos again
        RHUIManagerCLI.repo_add_by_repo(RHUA,
                                        [self.regular_repo, self.debug_repo, self.source_repo])
        # sync the repos
        RHUIManagerCLI.repo_sync_all(RHUA)

    def test_10_check_regular_repo_non_default(self):
        """examine the regular repo and check its non-default sync policy"""
        remote_data = PulpAPI.get_remote(RHUA, self.regular_repo)
        actual_policy = remote_data["policy"]
        nose.tools.eq_(actual_policy, POLICIES["nondefault"])

    def test_11_check_debug_repo_non_default(self):
        """examine the debug repo and check its non-default sync policy"""
        remote_data = PulpAPI.get_remote(RHUA, self.debug_repo)
        actual_policy = remote_data["policy"]
        nose.tools.eq_(actual_policy, POLICIES["nondefault"])

    def test_12_check_source_repo_non_default(self):
        """examine the source repo and check its non-default sync policy"""
        remote_data = PulpAPI.get_remote(RHUA, self.source_repo)
        actual_policy = remote_data["policy"]
        nose.tools.eq_(actual_policy, POLICIES["nondefault"])

    def test_13_create_install_cli_config_rpm(self):
        """create and install a client configuration RPM"""
        RHUIManagerCLI.client_rpm(RHUA,
                                  [self.regular_repo, self.debug_repo, self.source_repo],
                                  [NAME, "1"],
                                  WORKDIR)
        # get rid of undesired repos first
        Util.remove_amazon_rhui_conf_rpm(CLI)
        Util.disable_beta_repos(CLI)
        # install the config RPM now
        Util.install_pkg_from_rhua(RHUA,
                                   CLI,
                                   f"{WORKDIR}/{NAME}-1/build/RPMS/noarch/{NAME}-1-1.noarch.rpm")

    def test_14_download_regular_rpm(self):
        """download the regular test RPM"""
        Expect.expect_retval(CLI, f"mkdir -p {WORKDIR}")
        Expect.expect_retval(CLI, f"{DOWNLOAD_CMD} {self.test_package}")

    def test_15_download_debug_rpm(self):
        """download the debug test RPM"""
        Expect.expect_retval(CLI, f"{DOWNLOAD_CMD} --debuginfo {self.test_package}")

    def test_16_download_source_rpm(self):
        """download the source test RPM"""
        Expect.expect_retval(CLI, f"{DOWNLOAD_CMD} --source {self.test_package}")

    def test_99_cleanup(self):
        """clean up"""
        # remove the configuration RPM from the client
        Expect.expect_retval(CLI, "yum clean all")
        Util.remove_rpm(CLI, [NAME])
        Expect.expect_retval(CLI, f"rm -rf {WORKDIR}")
        # remove repos
        for repo in [self.regular_repo, self.debug_repo, self.source_repo]:
            RHUIManagerCLI.repo_delete(RHUA, repo)
        # remove orphans and symlinks
        RHUIManagerCLI.repo_orphan_cleanup(RHUA)
        Helpers.clear_symlinks(RHUA)
        # remove client build artifacts
        Expect.expect_retval(RHUA, f"rm -rf {WORKDIR}*")
        # restore the RHUI configuration file (with the default policies)
        Config.restore_rhui_tools_conf(RHUA)
        # uninstall HAProxy & CDS, forget their keys
        if not getenv("RHUISKIPSETUP"):
            RHUIManager.remove_rh_certs(RHUA)
            RHUIManagerCLIInstance.delete(RHUA, "haproxy", force=True)
            RHUIManagerCLIInstance.delete(RHUA, "cds", force=True)
            ConMgr.remove_ssh_keys(RHUA)

    @staticmethod
    def teardown_class():
        """announce the end of the test run"""
        print(f"*** Finished running {basename(__file__)}. ***")
