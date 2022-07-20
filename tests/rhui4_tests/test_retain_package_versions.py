'''Tests for the "retain package versions" feature'''

import logging
from os.path import basename

import nose
from stitches.expect import Expect
import yaml

from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.rhuimanager import RHUIManager
from rhui4_tests_lib.rhuimanager_cmdline import RHUIManagerCLI
from rhui4_tests_lib.helpers import Helpers

logging.basicConfig(level=logging.DEBUG)

RHUA = ConMgr.connect()

class TestCLI():
    ''' class for the tests '''

    def __init__(self):
        with open("/etc/rhui4_tests/tested_repos.yaml", encoding="utf-8") as configfile:
            doc = yaml.load(configfile)

        self.repo_id = doc["CLI_repo2"]["id"]
        self.test_package = doc["CLI_repo2"]["test_package"]

    @staticmethod
    def setup_class():
        ''' announce the beginning of the test run '''
        print(f"*** Running {basename(__file__)}: ***")

    @staticmethod
    def test_01_init():
        '''log in to RHUI'''
        RHUIManager.initial_run(RHUA)

    @staticmethod
    def test_02_upload_certificate():
        '''upload the Atomic (the small) entitlement certificate'''
        RHUIManagerCLI.cert_upload(RHUA, "/tmp/extra_rhui_files/rhcert_atomic.pem")

    @staticmethod
    def test_03_set_config_1():
        '''set retain package versions to 1'''
        Helpers.edit_rhui_tools_conf(RHUA, "retain_package_versions", "1")

    def test_04_add_repo(self):
        '''add a Red Hat repo'''
        RHUIManagerCLI.repo_add_by_repo(RHUA, [self.repo_id])

    def test_05_sync_repo(self):
        '''sync the repo'''
        RHUIManagerCLI.repo_sync(RHUA, self.repo_id)

    def test_06_check_package(self):
        '''check a package in the repo, expect 1 instance'''
        package_list = RHUIManagerCLI.packages_list(RHUA, self.repo_id)
        test_package_list = [package.rsplit("-", 2)[0] for package in package_list \
                             if package.startswith(self.test_package)]
        nose.tools.eq_(test_package_list, [self.test_package])

    def test_07_delete_repo(self):
        '''delete the repo'''
        RHUIManagerCLI.repo_delete(RHUA, self.repo_id)

    @staticmethod
    def test_08_set_config_2():
        '''set retain package versions to 2'''
        Helpers.edit_rhui_tools_conf(RHUA, "retain_package_versions", "2", False)

    def test_09_add_repo(self):
        '''add a Red Hat repo'''
        RHUIManagerCLI.repo_add_by_repo(RHUA, [self.repo_id])

    def test_10_sync_repo(self):
        '''sync the repo'''
        RHUIManagerCLI.repo_sync(RHUA, self.repo_id)

    def test_11_check_package(self):
        '''check a package in the repo, expect 2 instances'''
        package_list = RHUIManagerCLI.packages_list(RHUA, self.repo_id)
        test_package_list = [package.rsplit("-", 2)[0] for package in package_list \
                             if package.startswith(self.test_package)]
        nose.tools.eq_(len(test_package_list), 2)

    def test_12_cleanup(self):
        '''clean up'''
        RHUIManagerCLI.repo_delete(RHUA, self.repo_id)
        RHUIManager.remove_rh_certs(RHUA)
        Helpers.restore_rhui_tools_conf(RHUA)

    @staticmethod
    def teardown_class():
        ''' announce the end of the test run '''
        print(f"*** Finished running {basename(__file__)}. ***")
