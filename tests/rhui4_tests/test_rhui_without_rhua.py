"""Tests for RHUI without the RHUA"""

from os import getenv
from os.path import basename
import time

import logging
import nose
import requests
from stitches.expect import Expect
import urllib3
import yaml

from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.rhuimanager import RHUIManager
from rhui4_tests_lib.rhuimanager_client import RHUIManagerClient, \
                                               ContainerSupportDisabledError as CliError
from rhui4_tests_lib.rhuimanager_entitlement import RHUIManagerEntitlements
from rhui4_tests_lib.rhuimanager_instance import RHUIManagerInstance
from rhui4_tests_lib.rhuimanager_repo import RHUIManagerRepo, \
                                             ContainerSupportDisabledError as RepoError
from rhui4_tests_lib.rhuimanager_sync import RHUIManagerSync
from rhui4_tests_lib.helpers import Helpers
from rhui4_tests_lib.util import Util
from rhui4_tests_lib.yummy import Yummy

logging.basicConfig(level=logging.DEBUG)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

RHUA = ConMgr.connect()
# To make this script communicate with a client machine different from cli01.example.com, run:
# export RHUICLI=hostname
# in your shell before running this script, replacing "hostname" with the actual client host name.
# This allows for multiple client machines in one stack.
CLI = ConMgr.connect(getenv("RHUICLI", ConMgr.get_cli_hostnames()[0]))
CDS_HOSTNAME = ConMgr.get_cds_hostnames()[0]
CDS = ConMgr.connect(CDS_HOSTNAME)
CONTAINER_TEST_PATHS = ["/pulp/container/", "/v2", "/extensions/v2/"]
FETCHER = "try_files $uri @fetch_from_rhua;"
RPM_NAME = "test_rhui_without_rhua"
TMPDIR = "/tmp/" + RPM_NAME

def _toggle_support(containers=True, fetcher=True):
    """helper method to enable or disable container and RHUA fetcher support"""
    cmd = "rhui-installer --rerun" \
          f" --container-support-enabled {containers}" \
          f" --fetch-missing-symlinks {fetcher}"
    Expect.expect_retval(RHUA, cmd, timeout=600)

class TestRHUIWithoutRHUA():
    """class to test RHUI clients without CDSes contacting the RHUA"""
    def __init__(self):
        self.version = Util.get_rhel_version(CLI)["major"]
        arch = Util.get_arch(CLI)
        with open("/etc/rhui4_tests/tested_repos.yaml", encoding="utf-8") as configfile:
            doc = yaml.load(configfile)
            try:
                self.yum_repo_name = doc["yum_repos"][self.version][arch]["name"]
                self.yum_repo_version = doc["yum_repos"][self.version][arch]["version"]
                self.yum_repo_kind = doc["yum_repos"][self.version][arch]["kind"]
                self.yum_repo_label = doc["yum_repos"][self.version][arch]["label"]
                self.test_package = doc["yum_repos"][self.version][arch]["test_package"]
            except KeyError:
                raise nose.SkipTest(f"No test repo defined for RHEL {self.version} on {arch}") \
                from None

    @staticmethod
    def setup_class():
        """announce the beginning of the test run"""
        print(f"*** Running {basename(__file__)}: ***")

    @staticmethod
    def test_01_init():
        """log in to RHUI, upload cert, add HAProxy"""
        RHUIManager.initial_run(RHUA)
        RHUIManagerEntitlements.upload_rh_certificate(RHUA)
        RHUIManagerInstance.add_instance(RHUA, "loadbalancers")

    @staticmethod
    def test_02_disable_containers():
        """disable support for containers and the RHUA fetcher"""
        _toggle_support(False, False)

    @staticmethod
    def test_03_add_cds():
        """add a CDS"""
        RHUIManagerInstance.add_instance(RHUA, "cds")

    @staticmethod
    def test_04_try_adding_a_container():
        """try adding a container, should not be possible"""
        nose.tools.assert_raises(RepoError,
                                 RHUIManagerRepo.add_container,
                                 RHUA,
                                 RPM_NAME)

    @staticmethod
    def test_05_try_creating_container_conf():
        """try creating a container configuration RPM, should not be possible"""
        nose.tools.assert_raises(CliError,
                                 RHUIManagerClient.create_container_conf_rpm,
                                 RHUA,
                                 TMPDIR,
                                 RPM_NAME)

    @staticmethod
    def test_06_check_conf_containers():
        """check the nginx configuration file for container configuration, should not be there"""
        _, stdout, _ = CDS.exec_command("cat /etc/nginx/conf.d/ssl.conf")
        cfg = stdout.read().decode()
        for path in CONTAINER_TEST_PATHS:
            nose.tools.ok_(path not in cfg)

    @staticmethod
    def test_07_check_container_urls():
        """check container related URLs, should not be available/found"""
        for path in CONTAINER_TEST_PATHS:
            response = requests.head(f"https://{CDS_HOSTNAME}{path}", verify=False)
            nose.tools.eq_(response.status_code, 404)

    @staticmethod
    def test_08_check_conf_fetcher():
        """check the nginx configuration file for RHUA fetcher configuration, should not be there"""
        _, stdout, _ = CDS.exec_command("cat /etc/nginx/conf.d/ssl.conf")
        cfg = stdout.read().decode()
        nose.tools.ok_(FETCHER not in cfg)

    def test_09_add_repo(self):
        """add a repo"""
        RHUIManagerRepo.add_rh_repo_by_repo(RHUA,
                                            [Util.format_repo(self.yum_repo_name,
                                                              self.yum_repo_version,
                                                              self.yum_repo_kind)])

    def test_10_gen_cli_rpm(self):
        """generate a client configuration RPM"""
        RHUIManagerClient.generate_ent_cert(RHUA,
                                            [self.yum_repo_name],
                                            RPM_NAME,
                                            TMPDIR)
        RHUIManagerClient.create_conf_rpm(RHUA,
                                          TMPDIR,
                                          f"{TMPDIR}/{RPM_NAME}.crt",
                                          f"{TMPDIR}/{RPM_NAME}.key",
                                          RPM_NAME)

    @staticmethod
    def test_11_install_cli_rpm():
        """install the client configuration RPM"""
        # get rid of undesired repos first
        Util.remove_amazon_rhui_conf_rpm(CLI)
        Util.disable_beta_repos(CLI)
        Util.install_pkg_from_rhua(RHUA,
                                   CLI,
                                   f"{TMPDIR}/{RPM_NAME}-2.0/build/RPMS/noarch/" +
                                   f"{RPM_NAME}-2.0-1.noarch.rpm")

    def test_12_sync_repo(self):
        """sync the repo"""
        RHUIManagerSync.sync_repo(RHUA,
                                  [Util.format_repo(self.yum_repo_name, self.yum_repo_version)])
        RHUIManagerSync.wait_till_repo_synced(RHUA,
                                              [Util.format_repo(self.yum_repo_name,
                                                                self.yum_repo_version)])

    def test_13_get_unavailable_content(self):
        """check if the repo returns 404 at this point"""
        # make sure the symlinks weren't pre-created
        Expect.expect_retval(RHUA, "rm -rf /export/symlinks/pulp/content/content/")
        Expect.expect_retval(CLI, "yum clean all")
        _, stdout, _ = CLI.exec_command("yum -v repolist 2>&1")
        output = stdout.read().decode()
        nose.tools.ok_("404" in output, msg=f"Unexpected output: {output}")
        Expect.expect_retval(CLI, f"yum -y install {self.test_package}", 1)

    def test_14_export_repo(self):
        """export the repo"""
        RHUIManagerSync.export_repos(RHUA, [Util.format_repo(self.yum_repo_name,
                                                             self.yum_repo_version)])
        time.sleep(30)

    def test_15_get_available_content(self):
        """check if the repo is available now"""
        actual_repos = Yummy.yum_repolist(CLI)
        prefix = Helpers.get_from_rhui_tools_conf(RHUA, "rhui", "client_repo_prefix")
        nose.tools.eq_(actual_repos, [prefix + self.yum_repo_label])
        Expect.expect_retval(CLI, f"yum -y install {self.test_package}", timeout=20)

    def test_99_cleanup(self):
        """clean up"""
        _toggle_support()
        RHUIManagerRepo.delete_all_repos(RHUA)
        RHUIManagerInstance.delete_all(RHUA, "cds")
        RHUIManagerInstance.delete_all(RHUA, "loadbalancers")
        RHUIManager.remove_rh_certs(RHUA)
        Util.remove_rpm(CLI, [RPM_NAME, self.test_package])
        Expect.expect_retval(RHUA, f"rm -rf {TMPDIR}")

    @staticmethod
    def teardown_class():
        """announce the end of the test run"""
        print(f"*** Finished running {basename(__file__)}. ***")
