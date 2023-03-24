"""ACS Client Tests"""

# To skip the registration of CDS and HAProxy nodes --
# because you want to save time in each client test case and do this beforehand -- run:
# export RHUISKIPSETUP=1
# in your shell before running this script.
# The cleanup will be skipped, too, so you ought to clean up eventually.

from os import getenv
from os.path import basename

import json
import logging
import nose
from stitches.expect import Expect
import yaml

from rhui4_tests_lib.conmgr import ConMgr
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

TMPDIR = "/tmp/test_acs_client"
ACS_JSON = "acs-configuration.json"

class TestACSClient():
    """class to test ACS clients"""
    def __init__(self):
        self.version = Util.get_rhel_version(CLI)["major"]
        arch = Util.get_arch(CLI)
        with open("/etc/rhui4_tests/tested_repos.yaml", encoding="utf-8") as configfile:
            doc = yaml.load(configfile)
            self.rh_repo_id = doc["yum_repos"][self.version][arch]["id"]
            self.rh_repo_label = doc["yum_repos"][self.version][arch]["label"]
            self.custom_repo_id = "test-acs"
            self.test_package = doc["yum_repos"][self.version][arch]["test_package"]

    @staticmethod
    def setup_class():
        """announce the beginning of the test run"""
        print(f"*** Running {basename(__file__)}: ***")

    @staticmethod
    def test_01_setup():
        """log in to RHUI, add CDS & HAProxy nodes"""
        if not getenv("RHUISKIPSETUP"):
            RHUIManager.initial_run(RHUA)
            RHUIManagerCLIInstance.add(RHUA, "cds", unsafe=True)
            RHUIManagerCLIInstance.add(RHUA, "haproxy", unsafe=True)

    def test_02_add_repos(self):
        """add a Red Hat and create a custom repo"""
        if not getenv("RHUISKIPSETUP"):
            RHUIManagerCLI.cert_upload(RHUA)
        RHUIManagerCLI.repo_add_by_repo(RHUA, [self.rh_repo_id], True)
        RHUIManagerCLI.repo_create_custom(RHUA, self.custom_repo_id, protected=True)

    def test_03_create_acs_config(self):
        """crete an ACS configuration JSON file"""
        #Expect.expect_retcode(RHUA, f"mkdir -p {TMPDIR}")
        RHUIManagerCLI.client_acs_config(RHUA,
                                         [self.rh_repo_label, self.custom_repo_id],
                                         TMPDIR)

    def test_04_create_yum_conf_from_acs_json(self):
        """create yum configuration from the ACS configuration JSON file"""
        # load the JSON from the RHUA
        _, stdout, _ = RHUA.exec_command(f"cat {TMPDIR}/{ACS_JSON}")
        configuration = json.load(stdout)
        # create a directory with all the necessary files on the client
        Expect.expect_retval(CLI, f"mkdir -p {TMPDIR}")
        # save the CA cert
        stdin, _, _ = CLI.exec_command(f"cat > {TMPDIR}/ca.crt")
        stdin.write(configuration["ca_cert"])
        stdin.close()
        # save the entitlement cert
        stdin, _, _ = CLI.exec_command(f"cat > {TMPDIR}/content.crt")
        stdin.write(configuration["entitlement_cert"])
        stdin.close()
        # save the entitlement key
        stdin, _, _ = CLI.exec_command(f"cat > {TMPDIR}/content.key")
        stdin.write(configuration["private_key"])
        stdin.close()
        # create a yum configuration file
        # first the custom repo
        yum_repo_data = f"[{self.rh_repo_id}]\n"
        yum_repo_data += f"name={self.rh_repo_id}\n"
        cutom_repo_paths = [path for path in configuration["paths"] if path.startswith("protected")]
        yum_repo_data += f"baseurl={configuration['base_url']}{cutom_repo_paths[0]}\n"
        yum_repo_data += f"sslcacert={TMPDIR}/ca.crt\n"
        yum_repo_data += f"sslclientcert={TMPDIR}/content.crt\n"
        yum_repo_data += f"sslclientkey={TMPDIR}/content.key\n"
        # then the RH repo
        yum_repo_data += f"\n[{self.custom_repo_id}]\n"
        yum_repo_data += f"name={self.custom_repo_id}\n"
        rh_repo_paths = [path for path in configuration["paths"] if path.startswith("content")]
        yum_repo_data += f"baseurl={configuration['base_url']}{rh_repo_paths[0]}\n"
        yum_repo_data += f"sslcacert={TMPDIR}/ca.crt\n"
        yum_repo_data += f"sslclientcert={TMPDIR}/content.crt\n"
        yum_repo_data += f"sslclientkey={TMPDIR}/content.key\n"
        stdin, _, _ = CLI.exec_command("cat > /etc/yum.repos.d/acs.repo")
        stdin.write(yum_repo_data)
        stdin.close()

    def test_05_check_repos(self):
        """compare client's available repos with the RHUI repos"""
        # get rid of undesired repos first
        Util.remove_amazon_rhui_conf_rpm(CLI)
        Util.disable_beta_repos(CLI)
        actual_repos = Yummy.yum_repolist(CLI)
        nose.tools.eq_(actual_repos, sorted([self.rh_repo_id, self.custom_repo_id]))

    def test_06_check_test_package(self):
        """check if the client can install a test package"""
        Expect.expect_retval(CLI, f"yum -y install {self.test_package}", timeout=20)

    def test_99_cleanup(self):
        """clean up"""
        # uninstall the test package
        Util.remove_rpm(CLI, [self.test_package])
        # remove the yum configuration from the client
        Expect.expect_retval(CLI, "rm -f /etc/yum.repos.d/acs.repo")
        # remove the certs from the client
        Expect.expect_retval(CLI, f"rm -rf {TMPDIR}")
        # remove the ACS artifacts from the RHUA
        Expect.expect_retval(RHUA, f"rm -rf {TMPDIR}")
        # remove repos
        for repo in [self.rh_repo_id, self.custom_repo_id]:
            RHUIManagerCLI.repo_delete(RHUA, repo)
        # uninstall HAProxy & CDS, forget their keys
        if not getenv("RHUISKIPSETUP"):
            RHUIManagerCLIInstance.delete(RHUA, "haproxy", force=True)
            RHUIManagerCLIInstance.delete(RHUA, "cds", force=True)
            ConMgr.remove_ssh_keys(RHUA)

    @staticmethod
    def teardown_class():
        """announce the end of the test run"""
        print(f"*** Finished running {basename(__file__)}. ***")
