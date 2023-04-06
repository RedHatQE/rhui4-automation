"""Comps XML (Yum Package Groups) Tests"""

# To skip the registration of CDS and HAProxy nodes --
# because you want to save time in each client test case and do this beforehand -- run:
# export RHUISKIPSETUP=1
# in your shell before running this script.
# The cleanup will be skipped, too, so you ought to clean up eventually.

from os import getenv
from os.path import basename

from bisect import insort
import logging
import nose
from stitches.expect import Expect, ExpectFailed
import yaml

from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.rhuimanager import RHUIManager
from rhui4_tests_lib.rhuimanager_cmdline import RHUIManagerCLI
from rhui4_tests_lib.rhuimanager_cmdline_instance import RHUIManagerCLIInstance
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

TEST_DIR = "/tmp/extra_rhui_files/comps"

class TestCompsXML():
    """class to test comps XML handling"""
    def __init__(self):
        with open("/etc/rhui4_tests/tested_repos.yaml", encoding="utf-8") as configfile:
            doc = yaml.load(configfile)
            self.test_repos = list(doc["comps"].keys())[:2]
            self.test_repo_names = [doc["comps"][repo]["name"] for repo in self.test_repos]
            self.test_groups = [doc["comps"][repo]["test_group"] for repo in self.test_repos]
            self.test_packages = [doc["comps"][repo]["test_package"] for repo in self.test_repos]
            self.test_langpacks = [doc["comps"][repo]["test_langpack"] for repo in self.test_repos]
            self.test_group_mod = doc["comps"][self.test_repos[1]]["test_group_mod"]
            self.other_repos = {"big": doc["comps"]["big_repo"]["id"],
                                "empty": doc["comps"]["no_comps"]["id"],
                                "zip": doc["comps"]["comps_to_zip"]["id"]}

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
        """create custom repos for testing"""
        for repo_id, repo_name in zip(self.test_repos, self.test_repo_names):
            RHUIManagerCLI.repo_create_custom(RHUA,
                                              repo_id,
                                              display_name=repo_name,
                                              protected=True)

    def test_03_add_comps(self):
        """import comps XML files to the repos"""
        for repo in self.test_repos:
            RHUIManagerCLI.repo_add_comps(RHUA, repo, f"{TEST_DIR}/{repo}/comps.xml")

    def test_04_create_cli_config_rpms(self):
        """create client configuration RPMs for the repos"""
        for repo in self.test_repos:
            RHUIManagerCLI.client_rpm(RHUA, [repo], [repo], "/tmp")

    def test_05_install_conf_rpm(self):
        """install the 1st client configuration RPM on the client"""
        # get rid of undesired repos first
        Util.remove_amazon_rhui_conf_rpm(CLI)
        Util.disable_beta_repos(CLI)
        Util.install_pkg_from_rhua(RHUA,
                                   CLI,
                                   f"/tmp/{self.test_repos[0]}-2.0/build/RPMS/noarch/"
                                   f"{self.test_repos[0]}-2.0-1.noarch.rpm")

    def test_06_check_groups(self):
        """compare client's available groups with the 1st original comps file, check a test group"""
        groups_on_client = Yummy.yum_grouplist(CLI)
        original_comps_xml = f"{TEST_DIR}/{self.test_repos[0]}/comps.xml"
        groups_in_xml = Yummy.comps_xml_grouplist(RHUA, original_comps_xml)
        nose.tools.eq_(groups_on_client, groups_in_xml)
        nose.tools.ok_(self.test_groups[0] in groups_on_client)

    def test_07_check_test_package(self):
        """check if the client can see the 1st test package as available in group information"""
        packages = Yummy.yum_group_packages(CLI, self.test_groups[0])
        nose.tools.ok_(self.test_packages[0] in packages,
                       msg=f"{self.test_packages[0]} not found in {packages}")

    def test_08_install_conf_rpm(self):
        """replace the 1st client configuration RPM with the 2nd one on the client"""
        # get rid of the first one before installing the second one
        Util.remove_rpm(CLI, [self.test_repos[0]])
        Util.install_pkg_from_rhua(RHUA,
                                   CLI,
                                   f"/tmp/{self.test_repos[1]}-2.0/build/RPMS/noarch/"
                                   f"{self.test_repos[1]}-2.0-1.noarch.rpm")

    def test_09_check_groups(self):
        """compare client's available groups with the 2nd original comps file, check a test group"""
        Expect.expect_retval(CLI, "yum clean all")
        groups_on_client = Yummy.yum_grouplist(CLI)
        original_comps_xml = f"{TEST_DIR}/{self.test_repos[1]}/comps.xml"
        groups_in_xml = Yummy.comps_xml_grouplist(RHUA, original_comps_xml)
        nose.tools.eq_(groups_on_client, groups_in_xml)
        nose.tools.ok_(self.test_groups[1] in groups_on_client)

    def test_10_check_test_package(self):
        """check if the client can see the 2nd test package as available in group information"""
        packages = Yummy.yum_group_packages(CLI, self.test_groups[1])
        nose.tools.ok_(self.test_packages[1] in packages,
                       msg=f"{self.test_packages[1]} not found in {packages}")

    def test_11_check_langpacks(self):
        """check available langpacks in the processed comps files"""
        for repo, langpack in zip(self.test_repos, self.test_langpacks):
            langpacks = Yummy.comps_xml_langpacks(RHUA,
                                                  Yummy.repodata_location(RHUA,
                                                                          repo,
                                                                          "group"))
            if not langpacks:
                nose.tools.ok_(not langpack,
                               msg="a test langpack is defined, "
                                   f"but there are no langpacks for {repo}")
            else:
                nose.tools.ok_(tuple(langpack.split()) in langpacks,
                               msg=f"{langpack.split()[0]} not found in {langpacks}")

    def test_12_additional_group(self):
        """import a comps file containing one more group and expect the group to be added"""
        # and nothing lost...
        # import the "updated" comps file
        repo = self.test_repos[1]
        modified_comps_xml = f"{TEST_DIR}/{repo}/mod-comps.xml"
        RHUIManagerCLI.repo_add_comps(RHUA, repo, modified_comps_xml)
        Expect.expect_retval(CLI, "yum clean all")
        # compare client's available groups with the *original* comps file,
        # expecting all the original groups plus the extra group
        groups_on_client = Yummy.yum_grouplist(CLI)
        original_comps_xml = f"{TEST_DIR}/{repo}/comps.xml"
        groups_in_xml = Yummy.comps_xml_grouplist(RHUA, original_comps_xml)
        # trick: put the extra group to the right place in the sorted list
        insort(groups_in_xml, self.test_group_mod)
        nose.tools.eq_(groups_on_client, groups_in_xml)
        nose.tools.ok_(self.test_group_mod in groups_on_client)

    def test_13_big_comps(self):
        """import comps for the (big) RHEL 8 repo and check if all its groups get processed"""
        original_comps_xml = f"{TEST_DIR}/{self.other_repos['big']}/comps.xml"
        original_groups = Yummy.comps_xml_grouplist(RHUA, original_comps_xml, False)
        # create a custom repo for the big repo, import the cached comps file
        RHUIManagerCLI.repo_create_custom(RHUA, self.other_repos["big"])
        RHUIManagerCLI.repo_add_comps(RHUA, self.other_repos["big"], original_comps_xml)
        # get all groups from the imported metadata
        processed_comps_xml = Yummy.repodata_location(RHUA, self.other_repos["big"], "group")
        processed_groups = Yummy.comps_xml_grouplist(RHUA, processed_comps_xml, False)
        # compare the groups
        nose.tools.eq_(original_groups, processed_groups)

    def test_14_empty_comps(self):
        """import a comps file containing no group and expect no problem and no repodata refresh"""
        original_comps_xml = f"{TEST_DIR}/{self.other_repos['empty']}/comps.xml"
        # re-use the big repo for testing
        # get the current comps file name for that repo in RHUI
        processed_comps_xml_before = Yummy.repodata_location(RHUA, self.other_repos["big"], "group")
        # import the empty comps; should be accepted
        RHUIManagerCLI.repo_add_comps(RHUA, self.other_repos["big"], original_comps_xml)
        # re-get the comps file in RHUI name after the import
        processed_comps_xml_after = Yummy.repodata_location(RHUA, self.other_repos["big"], "group")
        # should be the same; comparing just the file names as the directory is definitely identical
        nose.tools.eq_(basename(processed_comps_xml_before), basename(processed_comps_xml_after))

    def test_15_gzip(self):
        """try using a compressed comps XML file, should be handled well"""
        # get all groups from the cached file
        original_comps_xml = f"{TEST_DIR}/{self.other_repos['zip']}/comps.xml"
        original_groups = Yummy.comps_xml_grouplist(RHUA, original_comps_xml, False)
        # prepare a temporary file and compress the original comps into it
        compressed_comps_xml = Util.mktemp_remote(RHUA, ".xml.gz")
        Expect.expect_retval(RHUA, f"gzip -c {original_comps_xml} > {compressed_comps_xml}")
        # create another test repo and add the compressed comps to it
        RHUIManagerCLI.repo_create_custom(RHUA, self.other_repos["zip"])
        RHUIManagerCLI.repo_add_comps(RHUA, self.other_repos["zip"], compressed_comps_xml)
        # get all groups from the imported metadata
        processed_comps_xml = Yummy.repodata_location(RHUA, self.other_repos["zip"], "group")
        processed_groups = Yummy.comps_xml_grouplist(RHUA, processed_comps_xml, False)
        # compare the groups
        nose.tools.eq_(original_groups, processed_groups)
        Expect.expect_retval(RHUA, f"rm -f {compressed_comps_xml}")

    def test_16_wrong_input_files(self):
        """try using an invalid XML file and a file with an invalid extension"""
        # create a bad XML file and use a known non-XML file; reuse the big repo
        bad_xml = Util.mktemp_remote(RHUA, ".xml")
        not_xml = "/etc/motd"
        Expect.expect_retval(RHUA, f"echo '<foo></bar>' > {bad_xml}")
        for comps_file in [bad_xml, not_xml]:
            nose.tools.assert_raises(ExpectFailed,
                                     RHUIManagerCLI.repo_add_comps,
                                     RHUA,
                                     self.other_repos["big"],
                                     comps_file)
        Expect.expect_retval(RHUA, f"rm -f {bad_xml}")

    def test_17_wrong_repo(self):
        """try using an invalid repository ID"""
        # a valid XML file is needed anyway (is parsed first), so reuse the first test repo
        nose.tools.assert_raises(ExpectFailed,
                                 RHUIManagerCLI.repo_add_comps,
                                 RHUA,
                                 self.other_repos["big"] + "foo",
                                 f"{TEST_DIR}/{self.test_repos[0]}/comps.xml")

    def test_99_cleanup(self):
        """clean up"""
        # remove the configuration RPM from the client
        Expect.expect_retval(CLI, "yum clean all")
        Util.remove_rpm(CLI, [self.test_repos[1]])
        # remove repos
        for repo in self.test_repos:
            RHUIManagerCLI.repo_delete(RHUA, repo)
            Expect.expect_retval(RHUA, f"rm -rf /tmp/{repo}*")
        RHUIManagerCLI.repo_delete(RHUA, self.other_repos["big"])
        RHUIManagerCLI.repo_delete(RHUA, self.other_repos["zip"])
        # uninstall HAProxy & CDS, forget their keys
        if not getenv("RHUISKIPSETUP"):
            RHUIManagerCLIInstance.delete(RHUA, "haproxy", force=True)
            RHUIManagerCLIInstance.delete(RHUA, "cds", force=True)
            ConMgr.remove_ssh_keys(RHUA)
        # if running RHEL Beta, destroy the non-Beta repos again
        cmd = "if grep -c Beta /etc/redhat-release; then " \
              "rm -f /etc/yum.repos.d/redhat-rhui.repo; fi"
        Expect.expect_retval(RHUA, cmd)

    @staticmethod
    def teardown_class():
        """announce the end of the test run"""
        print(f"*** Finished running {basename(__file__)}. ***")
