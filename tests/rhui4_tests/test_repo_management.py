''' Repository management tests '''

# To check if all entitled repositories can be added and deleted, which takes a huge amount
# of time and can break, run:
# export RHUITESTALLREPOS=1
# in your shell before running this script.

from os import getenv
from os.path import basename, join

import logging
import nose
from stitches.expect import Expect
import yaml

from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.rhuimanager import RHUIManager
from rhui4_tests_lib.rhuimanager_entitlement import RHUIManagerEntitlements
from rhui4_tests_lib.rhuimanager_repo import RHUIManagerRepo
from rhui4_tests_lib.util import Util

logging.basicConfig(level=logging.DEBUG)

RHUA = ConMgr.connect()
# side channel for hacking
RHUA_2 = ConMgr.connect()

CUSTOM_REPOS = ["custom-i386-x86_64", "custom-x86_64-x86_64", "custom-i386-i386"]
CUSTOM_PATHS = [repo.replace("-", "/") for repo in CUSTOM_REPOS]
CUSTOM_RPMS_DIR = "/tmp/extra_rhui_files"

class TestRepo():
    '''
       class for repository manipulation tests
    '''

    def __init__(self):
        self.custom_rpms = Util.get_rpms_in_dir(RHUA, CUSTOM_RPMS_DIR)
        if not self.custom_rpms:
            raise RuntimeError("No custom RPMs to test in " + CUSTOM_RPMS_DIR)
        # Test the RHEL-6 repo for a change
        version = 6
        arch = "x86_64"
        with open("/etc/rhui4_tests/tested_repos.yaml", encoding="utf-8") as configfile:
            doc = yaml.load(configfile)
            self.yum_repo_name = doc["yum_repos"][version][arch]["name"]
            self.yum_repo_version = doc["yum_repos"][version][arch]["version"]
            self.yum_repo_kind = doc["yum_repos"][version][arch]["kind"]
            self.yum_repo_path = doc["yum_repos"][version][arch]["path"]
            self.remote_content = doc["remote_content"]

    @staticmethod
    def setup_class():
        '''
           announce the beginning of the test run
        '''
        print(f"*** Running {basename(__file__)}: ***")

    @staticmethod
    def test_01_repo_setup():
        '''log in to RHUI, upload cert, check if no repo exists'''
        RHUIManager.initial_run(RHUA)
        entlist = RHUIManagerEntitlements.upload_rh_certificate(RHUA)
        nose.tools.ok_(entlist)
        nose.tools.ok_(not RHUIManagerRepo.list(RHUA))

    @staticmethod
    def test_02_create_3_custom_repos():
        '''create 3 custom repos (protected, unprotected, no RH GPG check) '''
        RHUIManagerRepo.add_custom_repo(RHUA,
                                        CUSTOM_REPOS[0],
                                        "",
                                        CUSTOM_PATHS[0],
                                        "1",
                                        "y")
        RHUIManagerRepo.add_custom_repo(RHUA,
                                        CUSTOM_REPOS[1],
                                        "",
                                        CUSTOM_PATHS[1],
                                        "1",
                                        "n")
        RHUIManagerRepo.add_custom_repo(RHUA,
                                        CUSTOM_REPOS[2],
                                        "",
                                        CUSTOM_PATHS[2],
                                        "1",
                                        "y",
                                        "",
                                        "n")

    @staticmethod
    def test_03_check_custom_repo_list():
        '''check if the repolist contains the 3 custom repos'''
        nose.tools.eq_(RHUIManagerRepo.list(RHUA), sorted(CUSTOM_REPOS))

# bug
#    @staticmethod
#    def test_04_repo_id_uniqueness():
#        '''verify that rhui-manager refuses to create a custom repo whose name already exists'''
#        nose.tools.assert_raises(AlreadyExistsError,
#                                 RHUIManagerRepo.add_custom_repo,
#                                 RHUA,
#                                 CUSTOM_REPOS[0])

    def test_05_upload_local_rpms(self):
        '''upload rpms from a local directory to a custom repo'''
        RHUIManagerRepo.upload_content(RHUA,
                                       [CUSTOM_REPOS[0]],
                                       join(CUSTOM_RPMS_DIR, self.custom_rpms[0]))
        RHUIManagerRepo.upload_content(RHUA,
                                       [CUSTOM_REPOS[0]],
                                       CUSTOM_RPMS_DIR)

    def test_06_upload_remote_rpms(self):
        '''upload rpms from remote servers to custom repos'''
        # try single RPMs first
        RHUIManagerRepo.upload_remote_content(RHUA,
                                              [CUSTOM_REPOS[1]],
                                              self.remote_content["rpm"])
        RHUIManagerRepo.upload_remote_content(RHUA,
                                              [CUSTOM_REPOS[1]],
                                              self.remote_content["ftp"])
        # and now an HTML page with links to RPMs
        RHUIManagerRepo.upload_remote_content(RHUA,
                                              [CUSTOM_REPOS[2]],
                                              self.remote_content["html_with_links"])
        # and finally also some bad stuff
        # issues are handled in the TUI libraries -- no packages will be found and uploaded
        rhua = ConMgr.get_rhua_hostname()
        RHUIManagerRepo.upload_remote_content(RHUA, [CUSTOM_REPOS[2]], f"https://{rhua}/")

    def test_07_check_for_package(self):
        '''check package lists'''
        test_rpm_name = self.custom_rpms[0].rsplit('-', 2)[0]
        nose.tools.eq_(RHUIManagerRepo.check_for_package(RHUA,
                                                         CUSTOM_REPOS[0],
                                                         ""),
                       self.custom_rpms)
        nose.tools.eq_(RHUIManagerRepo.check_for_package(RHUA,
                                                         CUSTOM_REPOS[0],
                                                         test_rpm_name),
                       [self.custom_rpms[0]])
        nose.tools.eq_(RHUIManagerRepo.check_for_package(RHUA,
                                                         CUSTOM_REPOS[0],
                                                         "test"),
                       [])
        nose.tools.eq_(RHUIManagerRepo.check_for_package(RHUA,
                                                         CUSTOM_REPOS[1],
                                                         ""),
                       sorted([basename(self.remote_content[p]) for p in ["rpm", "ftp"]]))
        nose.tools.eq_(RHUIManagerRepo.check_for_package(RHUA,
                                                         CUSTOM_REPOS[2],
                                                         ""),
                       sorted(Util.get_rpm_links(self.remote_content["html_with_links"])))

    def test_08_display_custom_repos(self):
        '''check detailed information on the custom repos'''
        # 1st: protected with all custom RPMs
        info = RHUIManagerRepo.check_detailed_information(RHUA, CUSTOM_REPOS[0])
        nose.tools.ok_(info["relativepath"].startswith("protected"))
        nose.tools.eq_(int(info["rpm.package"]), len(self.custom_rpms))


        # 2nd: unprotected with 2 RPMs (from 2 remote hosts)
        info = RHUIManagerRepo.check_detailed_information(RHUA, CUSTOM_REPOS[1])
        nose.tools.ok_(info["relativepath"].startswith("unprotected"))
        nose.tools.eq_(int(info["rpm.package"]), 2)


        # 3rd: no GPG check, RPMs from HTML
        rpm_link_count = len(Util.get_rpm_links(self.remote_content["html_with_links"]))
        info = RHUIManagerRepo.check_detailed_information(RHUA, CUSTOM_REPOS[2])
        nose.tools.eq_(info["gpgcheck"], "No")
        nose.tools.eq_(int(info["rpm.package"]), rpm_link_count)

    def test_09_add_rh_repo_by_repo(self):
        '''add a Red Hat repo by its name'''
        RHUIManagerRepo.add_rh_repo_by_repo(RHUA, [Util.format_repo(self.yum_repo_name,
                                                                    self.yum_repo_version,
                                                                    self.yum_repo_kind)])
        repo_list = RHUIManagerRepo.list(RHUA)
        nose.tools.ok_(Util.format_repo(self.yum_repo_name, self.yum_repo_version) in repo_list,
                       msg=f"The repo wasn't added. Actual repolist: {repo_list}")

    def test_10_display_rh_repo(self):
        '''check detailed information on the Red Hat repo'''
        info = RHUIManagerRepo.check_detailed_information(RHUA,
                                                          Util.format_repo(self.yum_repo_name,
                                                                           self.yum_repo_version))
        nose.tools.eq_(info["type"], "Red Hat")

    def test_11_delete_one_repo(self):
        '''remove the Red Hat repo'''
        RHUIManagerRepo.delete_repo(RHUA,
                                    [Util.format_repo(self.yum_repo_name, self.yum_repo_version)])
        repo_list = RHUIManagerRepo.list(RHUA)
        nose.tools.ok_(Util.format_repo(self.yum_repo_name, self.yum_repo_version) not in repo_list,
                       msg=f"The repo wasn't removed. Actual repolist: {repo_list}")

    def test_12_add_rh_repo_by_product(self):
        '''add a Red Hat repo by the product that contains it, remove it'''
        RHUIManagerRepo.add_rh_repo_by_product(RHUA, [self.yum_repo_name])
        repo_list = RHUIManagerRepo.list(RHUA)
        nose.tools.ok_(Util.format_repo(self.yum_repo_name, self.yum_repo_version) in repo_list,
                       msg=f"The repo wasn't added. Actual repolist: {repo_list}")
        RHUIManagerRepo.delete_all_repos(RHUA)
        nose.tools.ok_(not RHUIManagerRepo.list(RHUA))

    @staticmethod
    def test_13_add_all_rh_repos():
        '''add all Red Hat repos, remove them (takes a lot of time!)'''
        if not getenv("RHUITESTALLREPOS"):
            raise nose.exc.SkipTest("Not explicitly requested.")
        RHUIManagerRepo.add_rh_repo_all(RHUA)
        # it's not feasible to get the repo list if so many repos are present; skip the check
        #nose.tools.ok_(len(RHUIManagerRepo.list(RHUA)) > 100)
        RHUIManagerRepo.delete_all_repos(RHUA)
        nose.tools.ok_(not RHUIManagerRepo.list(RHUA))

    @staticmethod
    def test_17_entitlement_cache():
        '''check if entitlements are cached and evaluated in the blink of an eye'''
        # for RHBZ#1873956
        # the cache was created by the actions of the previous tests
        Expect.ping_pong(RHUA, "ls /var/cache/rhui", "mappings")
        Expect.expect_retval(RHUA, "timeout 2 rhui-manager repo unused")

    @staticmethod
    def test_18_missing_cert_handling():
        '''check if rhui-manager can handle the loss of the RH cert'''
        # for RHBZ#1325390
        RHUIManagerEntitlements.upload_rh_certificate(RHUA)
        # launch rhui-manager in one connection, delete the cert in the other
        RHUIManager.screen(RHUA, "repo")
        RHUIManager.remove_rh_certs(RHUA_2)
        Expect.enter(RHUA, "a")
        # a bit strange response to see in this context, but eh, no == all if you're a geek
        Expect.expect(RHUA, "All entitled products are currently deployed in the RHUI")
        Expect.enter(RHUA, "q")

    @staticmethod
    def test_19_repo_select_0():
        '''check if no repo is chosen if 0 is entered when adding a repo'''
        # for RHBZ#1305612
        # upload the small cert and try entering 0 when the list of repos is displayed
        RHUIManagerEntitlements.upload_rh_certificate(RHUA,
                                                      "/tmp/extra_rhui_files/rhcert_atomic.pem")
        RHUIManager.screen(RHUA, "repo")
        Expect.enter(RHUA, "a")
        Expect.expect(RHUA, "Enter value", 180)
        Expect.enter(RHUA, "3")
        Expect.expect(RHUA, "Enter value")
        Expect.enter(RHUA, "0")
        Expect.expect(RHUA, "Enter value")
        Expect.enter(RHUA, "c")
        Expect.expect(RHUA, "Proceed")
        Expect.enter(RHUA, "y")
        Expect.expect(RHUA, "Content")
        Expect.enter(RHUA, "q")

        # the RHUI repo list ought to be empty now; if not, delete the repo and fail
        repo_list = RHUIManagerRepo.list(RHUA)
        RHUIManager.remove_rh_certs(RHUA)
        if repo_list:
            RHUIManagerRepo.delete_all_repos(RHUA)
            raise AssertionError(f"The repo list is not empty: {repo_list}")

    @staticmethod
    def teardown_class():
        '''
           announce the end of the test run
        '''
        print(f"*** Finished running {basename(__file__)}. ***")
