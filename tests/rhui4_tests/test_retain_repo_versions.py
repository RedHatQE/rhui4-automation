'''Tests for the "retain repo versions" feature'''

import logging
from os.path import basename, join
import time

import nose
import yaml
from stitches.expect import Expect

from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.pulp_api import PulpAPI
from rhui4_tests_lib.rhuimanager import RHUIManager
from rhui4_tests_lib.rhuimanager_cmdline import RHUIManagerCLI
from rhui4_tests_lib.helpers import Helpers

logging.basicConfig(level=logging.DEBUG)

RHUA = ConMgr.connect()

class TestCLI():
    ''' class for the tests '''

    def __init__(self):
        with open("/etc/rhui4_tests/tested_repos.yaml", encoding="utf-8") as configfile:
            doc = yaml.safe_load(configfile)

        self.test_packages = doc["repo_versions"]["test_packages"]
        self.repo_id = "test-versions"
        self.tmpdir = join("/tmp", self.repo_id)
        self.configured_number = int(Helpers.get_from_rhui_tools_conf(RHUA,
                                                                      "rhui",
                                                                      "retain_repo_versions"))

    @staticmethod
    def setup_class():
        ''' announce the beginning of the test run '''
        print(f"*** Running {basename(__file__)}: ***")

    @staticmethod
    def test_01_init():
        '''log in to RHUI'''
        RHUIManager.initial_run(RHUA)

    def test_02_create_repo(self):
        '''create a custom repo'''
        RHUIManagerCLI.repo_create_custom(RHUA, self.repo_id)

    def test_03_check_max_repo_versions(self):
        '''check if the repo was created with the configured number of versions'''
        repos = PulpAPI.list_repos(RHUA)
        actual_number = repos[0]["retain_repo_versions"]
        nose.tools.eq_(actual_number, self.configured_number)

    def test_04_prep_packages_for_upload(self):
        '''prepare packages for upload'''
        Expect.expect_retval(RHUA, "mkdir " + self.tmpdir)
        Expect.expect_retval(RHUA, f"cd {self.tmpdir}; " +
                                   f"yumdownloader {' '.join(self.test_packages)}")

    def test_05_upload_packages(self):
        '''upload the packages, one by one, so as to create multiple repo versions'''
        for package in self.test_packages:
            RHUIManagerCLI.packages_upload(RHUA, self.repo_id, join(self.tmpdir, package) + ".rpm")
            time.sleep(7)

    def test_06_check_versions(self):
        '''check if the current number of repo version did not exceed the limit and 0 is gone'''
        versions = PulpAPI.list_repo_versions(RHUA, self.repo_id)
        # the number of versions should match the setting
        nose.tools.eq_(len(versions), self.configured_number)
        # the last version number should not be 0 anymore
        nose.tools.assert_not_equal(versions[-1]["number"], 0)

    def test_07_check_version_0_gone(self):
        '''also check if its deletion was logged'''
        entry = f"Deleting repository version <Repository: {self.repo_id}; Version: 0>"
        Expect.expect_retval(RHUA, f"grep '{entry}' /var/log/messages")

    def test_08_cleanup(self):
        '''clean up'''
        RHUIManagerCLI.repo_delete(RHUA, self.repo_id)
        Expect.expect_retval(RHUA, "rm -rf " + self.tmpdir)

    @staticmethod
    def teardown_class():
        ''' announce the end of the test run '''
        print(f"*** Finished running {basename(__file__)}. ***")
