"""Tests for Repository Prefix Customization"""

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

from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.rhuimanager import RHUIManager
from rhui4_tests_lib.rhuimanager_cmdline import RHUIManagerCLI
from rhui4_tests_lib.rhuimanager_cmdline_instance import RHUIManagerCLIInstance
from rhui4_tests_lib.helpers import Helpers
from rhui4_tests_lib.util import Util
from rhui4_tests_lib.yummy import Yummy

logging.basicConfig(level=logging.DEBUG)

RHUA = ConMgr.connect()
# To make this script communicate with a client machine different from cli01.example.com, run:
# export RHUICLI=hostname
# in your shell before running this script, replacing "hostname" with the actual client host name.
# This allows for multiple client machines in one stack.
CLI = ConMgr.connect(getenv("RHUICLI", ConMgr.get_cli_hostnames()[0]))

PREFIXES = ["az-", "ccsp-"]
NAME = "test-prefix"
WORKDIR = "/tmp/" + NAME

class TestRepoPrefix():
    """class to test repository prefixes"""
    def __init__(self):
        self.version = Util.get_rhel_version(CLI)["major"]
        arch = Util.get_arch(CLI)
        with open("/etc/rhui4_tests/tested_repos.yaml", encoding="utf-8") as configfile:
            doc = yaml.load(configfile)
            self.rh_repo_id = doc["yum_repos"][self.version][arch]["id"]
            self.rh_repo_label = doc["yum_repos"][self.version][arch]["label"]
            self.prot_custom_repo_id = "test-prefix-safe"
            self.unprot_custom_repo_id = "test-prefix-unsafe"

    @staticmethod
    def setup_class():
        """announce the beginning of the test run"""
        print(f"*** Running {basename(__file__)}: ***")

    @staticmethod
    def test_01_setup():
        """log in to RHUI, ensure CDS & HAProxy nodes have been added"""
        if not getenv("RHUISKIPSETUP"):
            RHUIManager.initial_run(RHUA)
            RHUIManagerCLIInstance.add(RHUA, "cds", unsafe=True)
            RHUIManagerCLIInstance.add(RHUA, "haproxy", unsafe=True)
        # check that
        cds_list = RHUIManagerCLIInstance.list(RHUA, "cds")
        nose.tools.ok_(cds_list)
        hap_list = RHUIManagerCLIInstance.list(RHUA, "haproxy")
        nose.tools.ok_(hap_list)

    def test_02_add_repos(self):
        """add and sync a Red Hat repo, and create protected and uprotected custom repos"""
        if not getenv("RHUISKIPSETUP"):
            RHUIManagerCLI.cert_upload(RHUA)
        RHUIManagerCLI.repo_add_by_repo(RHUA, [self.rh_repo_id], True)
        RHUIManagerCLI.repo_create_custom(RHUA, self.prot_custom_repo_id, protected=True)
        RHUIManagerCLI.repo_create_custom(RHUA, self.unprot_custom_repo_id)

    @staticmethod
    def test_03_set_custom_prefix():
        """set a custom prefix (by editing the RHUI config file)"""
        Helpers.edit_rhui_tools_conf(RHUA, "client_repo_prefix", PREFIXES[0])

    def test_04_create_cli_config_rpm(self):
        """create the 1st client configuration RPM"""
        RHUIManagerCLI.client_rpm(RHUA,
                                  [self.rh_repo_label, self.prot_custom_repo_id],
                                  [NAME, "1"],
                                  WORKDIR,
                                  [self.unprot_custom_repo_id])

    @staticmethod
    def test_05_install_conf_rpm():
        """install the 1st client configuration RPM on the client"""
        # get rid of undesired repos first
        Util.remove_amazon_rhui_conf_rpm(CLI)
        Util.disable_beta_repos(CLI)
        Util.install_pkg_from_rhua(RHUA,
                                   CLI,
                                   f"{WORKDIR}/{NAME}-1/build/RPMS/noarch/{NAME}-1-1.noarch.rpm")

    def test_06_check_repo_ids(self):
        """check if the repos on the client use the custom prefix"""
        cli_repos = Yummy.yum_repolist(CLI)
        nose.tools.eq_(cli_repos,
                       sorted([f"{PREFIXES[0]}{self.rh_repo_label}",
                               f"{PREFIXES[0]}custom-{self.prot_custom_repo_id}",
                               f"{PREFIXES[0]}custom-{self.unprot_custom_repo_id}"]))

    @staticmethod
    def test_07_set_another_custom_prefix():
        """set another custom prefix (by rerunning the RHUI installer)"""
        cmd = f"rhui-installer --rerun --client-repo-prefix {PREFIXES[1]}"
        Expect.expect_retval(RHUA, cmd, timeout=600)

    @staticmethod
    def test_08_check_prefix():
        """check if the installer changed the prefix in the configuration"""
        current_prefix = Helpers.get_from_rhui_tools_conf(RHUA, "rhui", "client_repo_prefix")
        nose.tools.eq_(current_prefix, PREFIXES[1])

    def test_09_create_cli_config_rpm(self):
        """create the 2nd client configuration RPM"""
        RHUIManagerCLI.client_rpm(RHUA,
                                  [self.rh_repo_label, self.prot_custom_repo_id],
                                  [NAME, "2"],
                                  WORKDIR,
                                  [self.unprot_custom_repo_id])

    @staticmethod
    def test_10_install_conf_rpm():
        """install the 2nd client configuration RPM on the client"""
        Expect.expect_retval(CLI, "yum clean all")
        Util.install_pkg_from_rhua(RHUA,
                                   CLI,
                                   f"{WORKDIR}/{NAME}-2/build/RPMS/noarch/{NAME}-2-1.noarch.rpm",
                                   True)

    def test_11_check_repo_ids(self):
        """check if the repos on the client use the other custom prefix"""
        cli_repos = Yummy.yum_repolist(CLI)
        nose.tools.eq_(cli_repos,
                       sorted([f"{PREFIXES[1]}{self.rh_repo_label}",
                               f"{PREFIXES[1]}custom-{self.prot_custom_repo_id}",
                               f"{PREFIXES[1]}custom-{self.unprot_custom_repo_id}"]))

    @staticmethod
    def test_12_unset_custom_prefix():
        """set no custom prefix (using the installer again)"""
        cmd = "rhui-installer --rerun --client-repo-prefix \"\""
        Expect.expect_retval(RHUA, cmd, timeout=600)

    @staticmethod
    def test_13_check_prefix():
        """check if the installer unset the prefix in the configuration"""
        current_prefix = Helpers.get_from_rhui_tools_conf(RHUA, "rhui", "client_repo_prefix")
        nose.tools.eq_(current_prefix, "")

    @staticmethod
    def test_14_rerun_installer_check_prefix():
        """check if rerunning the installer preserves the prefix setting"""
        # first, change the prefix in the answers file
        ccmd = "sed 's/client_repo_prefix: .*/client_repo_prefix: foo-/' /root/.rhui/answers.yaml"
        Expect.expect_retval(RHUA, ccmd)
        # then rerun the insataller, where answers should yield to rhui-conf
        cmd = "rhui-installer --rerun"
        Expect.expect_retval(RHUA, cmd, timeout=600)
        current_prefix = Helpers.get_from_rhui_tools_conf(RHUA, "rhui", "client_repo_prefix")
        nose.tools.eq_(current_prefix, "")

    def test_15_create_cli_config_rpm(self):
        """create the 3rd client configuration RPM"""
        RHUIManagerCLI.client_rpm(RHUA,
                                  [self.rh_repo_label, self.prot_custom_repo_id],
                                  [NAME, "3"],
                                  WORKDIR,
                                  [self.unprot_custom_repo_id])

    @staticmethod
    def test_16_install_conf_rpm():
        """install the 3rd client configuration RPM on the client"""
        Expect.expect_retval(CLI, "yum clean all")
        Util.install_pkg_from_rhua(RHUA,
                                   CLI,
                                   f"{WORKDIR}/{NAME}-3/build/RPMS/noarch/{NAME}-3-1.noarch.rpm",
                                   True)

    def test_17_check_repo_ids(self):
        """check if the repos on the client do not use any prefix"""
        cli_repos = Yummy.yum_repolist(CLI)
        nose.tools.eq_(cli_repos,
                       sorted([self.rh_repo_label,
                              f"custom-{self.prot_custom_repo_id}",
                              f"custom-{self.unprot_custom_repo_id}"]))

    def test_99_cleanup(self):
        """clean up"""
        # remove the configuration RPM from the client
        Expect.expect_retval(CLI, "yum clean all")
        Util.remove_rpm(CLI, [NAME])
        # remove repos
        for repo in [self.rh_repo_id, self.prot_custom_repo_id, self.unprot_custom_repo_id]:
            RHUIManagerCLI.repo_delete(RHUA, repo)
        # remove client build artifacts
        Expect.expect_retval(RHUA, f"rm -rf {WORKDIR}*")
        # restore the RHUI configuration file (with the default prefix)
        Helpers.restore_rhui_tools_conf(RHUA)
        # uninstall HAProxy & CDS, forget their keys
        if not getenv("RHUISKIPSETUP"):
            RHUIManagerCLIInstance.delete(RHUA, "haproxy", force=True)
            RHUIManagerCLIInstance.delete(RHUA, "cds", force=True)
            ConMgr.remove_ssh_keys(RHUA)

    @staticmethod
    def teardown_class():
        """announce the end of the test run"""
        print(f"*** Finished running {basename(__file__)}. ***")
