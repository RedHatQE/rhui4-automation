"""Container Management Tests"""

# To skip the upload of an entitlement certificate and the registration of CDS and HAProxy nodes --
# because you want to save time in each client test case and do this beforehand -- run:
# export RHUISKIPSETUP=1
# in your shell before running this script.
# The cleanup will be skipped, too, so you ought to clean up eventually.

from os import getenv
from os.path import basename
import time

import json
import logging
import nose
from stitches.expect import Expect, ExpectFailed
import yaml

from rhui4_tests_lib.cfg import Config
from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.rhuimanager import RHUIManager
from rhui4_tests_lib.rhuimanager_client import RHUIManagerClient
from rhui4_tests_lib.rhuimanager_instance import RHUIManagerInstance
from rhui4_tests_lib.rhuimanager_repo import RHUIManagerRepo
from rhui4_tests_lib.rhuimanager_sync import RHUIManagerSync
from rhui4_tests_lib.util import Util

logging.basicConfig(level=logging.DEBUG)

RHUA = ConMgr.connect()
# __reusable_clients_with_cds
# To make this script communicate with a client machine different from cli01.example.com, run:
# export RHUICLI=hostname
# in your shell before running this script, replacing "hostname" with the actual client host name.
# This allows for multiple client machines in one stack.
CLI = ConMgr.connect(getenv("RHUICLI", ConMgr.get_cli_hostnames()[0]))

HA_HOSTNAME = ConMgr.get_cds_lb_hostname()

CONF_RPM_NAME = "containers-rhui"
CONF_RPM_VERSION = "1"
CONF_RPM_RELEASE = "1ui"
CONF_RPM_PATH = f"/tmp/{CONF_RPM_NAME}-{CONF_RPM_VERSION}/build/RPMS/noarch/" \
                f"{CONF_RPM_NAME}-{CONF_RPM_VERSION}-{CONF_RPM_RELEASE}.noarch.rpm"

class TestClient():
    """class for container tests"""

    def __init__(self):
        if Util.get_rhel_version(CLI)["major"] < 7:
            raise nose.SkipTest("Unsuppored client RHEL version") from None

        with open("/etc/rhui4_tests/tested_repos.yaml", encoding="utf-8") as configfile:
            doc = yaml.safe_load(configfile)

        self.container_name = doc["container_cli"]["name"]
        self.container_id = self.container_name
        self.container_displayname = doc["container_cli"]["displayname"]

        self.container_quay = doc["container_alt"]["quay"]
        self.container_gitlab = doc["container_alt"]["gitlab"]

    @staticmethod
    def setup_class():
        """announce the beginning of the test run"""
        print(f"*** Running {basename(__file__)}: ***")

    @staticmethod
    def test_01_init():
        """log in to RHUI"""
        if not getenv("RHUISKIPSETUP"):
            RHUIManager.initial_run(RHUA)

    @staticmethod
    def test_02_add_cds():
        """add a CDS"""
        if not getenv("RHUISKIPSETUP"):
            RHUIManagerInstance.add_instance(RHUA, "cds")

    @staticmethod
    def test_03_add_hap():
        """add an HAProxy Load-balancer"""
        if not getenv("RHUISKIPSETUP"):
            RHUIManagerInstance.add_instance(RHUA, "loadbalancers")

    def test_04_add_containers(self):
        """add containers"""
        # first, add a container from RH
        # get credentials and enter them when prompted
        credentials = Config.get_credentials(RHUA)
        RHUIManagerRepo.add_container(RHUA,
                                      self.container_name,
                                      self.container_id,
                                      self.container_displayname,
                                      [""] + credentials)
        # second, add a container from Quay
        # get Quay credentials
        credentials = Config.get_credentials(RHUA, "quay")
        quay_url = Config.get_registry_url("quay")
        RHUIManagerRepo.add_container(RHUA,
                                      self.container_quay["name"],
                                      credentials=[quay_url] + credentials)
        # third, add a container from GitLab
        gitlab_url = Config.get_registry_url("gitlab")
        RHUIManagerRepo.add_container(RHUA,
                                      self.container_gitlab["name"],
                                      credentials=[gitlab_url])

    def test_05_display_info(self):
        """check detailed information on the RH container"""
        info = RHUIManagerRepo.check_detailed_information(RHUA, self.container_displayname)
        nose.tools.ok_("Container" in info["type"])
        nose.tools.eq_(info["id"], self.container_id)

    def test_06_sync_containers(self):
        """sync the containers"""
        quay_repo_name = Util.safe_pulp_repo_name(self.container_quay["name"])
        gitlab_repo_name = Util.safe_pulp_repo_name(self.container_gitlab["name"])

        RHUIManagerSync.sync_repo(RHUA,
                                  [self.container_displayname,
                                   quay_repo_name,
                                   gitlab_repo_name])
        RHUIManagerSync.wait_till_repo_synced(RHUA,
                                              [self.container_displayname,
                                               quay_repo_name,
                                               gitlab_repo_name])

    @staticmethod
    def test_07_create_cli_rpm():
        """create a client configuration RPM"""
        RHUIManagerClient.create_container_conf_rpm(RHUA,
                                                    "/tmp",
                                                    CONF_RPM_NAME,
                                                    CONF_RPM_VERSION,
                                                    CONF_RPM_RELEASE)
        Expect.expect_retval(RHUA, f"test -f {CONF_RPM_PATH}")

    @staticmethod
    def test_08_install_cli_rpm():
        """install the client configuration RPM"""
        Util.install_pkg_from_rhua(RHUA, CLI, CONF_RPM_PATH)

    @staticmethod
    def test_09_check_podman_info():
        """check if RHUI is now a known and the only registry"""
        _, stdout, _ = CLI.exec_command("podman info -f json")
        podman_info = json.load(stdout)
        nose.tools.eq_(podman_info["registries"]["search"], [HA_HOSTNAME])

    def test_10_search(self):
        """search for container images in RHUI"""
        quay_repo_name = Util.safe_pulp_repo_name(self.container_quay["name"])
        gitlab_repo_name = Util.safe_pulp_repo_name(self.container_gitlab["name"])

        _, stdout, _ = CLI.exec_command(f"podman search --format {{{{.Name}}}} {HA_HOSTNAME}/")
        results = stdout.read().decode().splitlines()
        found_images = [line.replace(f"{HA_HOSTNAME}/", "").rstrip() \
                        for line in results if line.startswith(HA_HOSTNAME)]
        nose.tools.eq_(sorted(found_images),
                       sorted([self.container_id, quay_repo_name, gitlab_repo_name]))

    def test_11_pull_images(self):
        """pull the container images"""
        for container in [self.container_id,
                          Util.safe_pulp_repo_name(self.container_quay["name"]),
                          Util.safe_pulp_repo_name(self.container_gitlab["name"])]:
            cmd = f"podman pull {container}"
            # in some cases the container is synced but pulling fails mysteriously
            # if that happens, try again in a minute
            try:
                Expect.expect_retval(CLI, cmd, timeout=30)
            except ExpectFailed:
                time.sleep(60)
                Expect.expect_retval(CLI, cmd, timeout=30)

    def test_12_check_images(self):
        """check if the container images are now available"""
        quay_repo_name = Util.safe_pulp_repo_name(self.container_quay["name"])
        gitlab_repo_name = Util.safe_pulp_repo_name(self.container_gitlab["name"])

        _, stdout, _ = CLI.exec_command("podman images --noheading")
        image_table = stdout.read().decode().splitlines()
        # get just the names (the "repository" column in the image table)
        actual_names = [row.split()[0] for row in image_table]
        nose.tools.eq_(sorted(actual_names),
                       sorted([f"{HA_HOSTNAME}/{name}" for name in \
                               [self.container_id, quay_repo_name, gitlab_repo_name]]))

    def test_13_run_command(self):
        """run a test command (uname) in the RH container"""
        Expect.ping_pong(CLI, f"podman run {self.container_id} uname", "Linux")

    def test_99_cleanup(self):
        """remove the containers from the client and the RHUA, uninstall HAProxy and CDS"""
        ancestor = f"{HA_HOSTNAME}/{self.container_id}:latest"
        Expect.expect_retval(CLI, f"podman rm -f $(podman ps -a -f ancestor={ancestor} -q)")
        for container in [self.container_id,
                          Util.safe_pulp_repo_name(self.container_quay["name"]),
                          Util.safe_pulp_repo_name(self.container_gitlab["name"])]:
            Expect.expect_retval(CLI, f"podman rmi {container}")
        Expect.expect_retval(RHUA, f"rm -rf /tmp/{CONF_RPM_NAME}*")
        RHUIManagerRepo.delete_all_repos(RHUA)
        # check if the repos are no longer listed in search results
        _, stdout, _ = CLI.exec_command(f"podman search {HA_HOSTNAME}/")
        results = stdout.read().decode()
        nose.tools.eq_(results, '')
        Util.remove_rpm(CLI, [CONF_RPM_NAME])
        if not getenv("RHUISKIPSETUP"):
            RHUIManagerInstance.delete_all(RHUA, "loadbalancers")
            RHUIManagerInstance.delete_all(RHUA, "cds")

    @staticmethod
    def teardown_class():
        """announce the end of the test run"""
        print(f"*** Finished running {basename(__file__)}. ***")
