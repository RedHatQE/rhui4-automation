'''Update Info Tests'''

# To skip the upload of an entitlement certificate and the registration of CDS and HAProxy nodes --
# because you want to save time in each client test case and do this beforehand -- run:
# export RHUISKIPSETUP=1
# in your shell before running this script.
# The cleanup will be skipped, too, so you ought to clean up eventually.

from os import getenv
from os.path import basename, join

import logging
import nose
from stitches.expect import Expect
import yaml

from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.pulp_api import PulpAPI
from rhui4_tests_lib.rhuimanager import RHUIManager
from rhui4_tests_lib.rhuimanager_client import RHUIManagerClient
from rhui4_tests_lib.rhuimanager_cmdline import RHUIManagerCLI
from rhui4_tests_lib.rhuimanager_instance import RHUIManagerInstance
from rhui4_tests_lib.rhuimanager_repo import RHUIManagerRepo
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

class TestClient():
    '''
       class for client tests
    '''

    def __init__(self):
        if Util.fips_enabled(CLI):
            raise nose.SkipTest("This test is unsupported in FIPS mode.")
        self.arch = Util.get_arch(CLI)
        self.version = Util.get_rhel_version(CLI)["major"]
        with open("/etc/rhui4_tests/tested_repos.yaml", encoding="utf-8") as configfile:
            doc = yaml.safe_load(configfile)
            try:
                self.test = doc["updateinfo"][self.version][self.arch]
            except KeyError:
                raise nose.SkipTest(f"No test repo defined for RHEL {self.version} on {self.arch}")\
                from None
            # the special "RHEL 0" repo contains updateinfo.xml instead of *.gz
            self.test["uncompressed_updateinfo"] = doc["updateinfo"][0]["all"]["repo_id"]

    @staticmethod
    def setup_class():
        '''
           announce the beginning of the test run
        '''
        print(f"*** Running {basename(__file__)}: ***")

    @staticmethod
    def test_01_repo_setup():
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
            RHUIManagerInstance.add_instance(RHUA, "cds")

    @staticmethod
    def test_03_add_hap():
        '''
           add an HAProxy Load-balancer
        '''
        if not getenv("RHUISKIPSETUP"):
            RHUIManagerInstance.add_instance(RHUA, "loadbalancers")

    def test_04_add_repo(self):
        '''
           add a custom repo
        '''
        # custom GPG key can have a name, or it can be set to "nokey" (not used with the packages),
        # or it can be undefined altogether, in which case the packages are supposedly signed by RH
        try:
            if self.test["gpg_key"] == "nokey":
                custom_gpg = None
            else:
                custom_gpg = "/tmp/extra_rhui_files/" + \
                             join(self.test["repo_id"], self.test["gpg_key"])
            redhat_gpg = "n"
        except KeyError:
            custom_gpg = None
            redhat_gpg = "y"
        RHUIManagerRepo.add_custom_repo(RHUA,
                                        self.test["repo_id"],
                                        self.test["repo_name"],
                                        redhat_gpg=redhat_gpg,
                                        custom_gpg=custom_gpg)

    def test_05_upload_packages(self):
        '''
           upload packages to the custom repo
        '''
        RHUIManagerRepo.upload_content(RHUA,
                                       [self.test["repo_name"]],
                                       "/tmp/extra_rhui_files/" + self.test["repo_id"])

    def test_06_import_updateinfo(self):
        '''
           import update info
        '''
        # only doable in the CLI
        RHUIManagerCLI.repo_add_errata(RHUA,
                                       self.test["repo_id"],
                                       "/tmp/extra_rhui_files/" +
                                       f"{self.test['repo_id']}/updateinfo.xml.gz")

    def test_07_generate_ent_cert(self):
        '''
           generate an entitlement certificate
        '''
        RHUIManagerClient.generate_ent_cert(RHUA,
                                            [self.test["repo_name"]],
                                            self.test["repo_id"],
                                            "/tmp")

    def test_08_create_cli_rpm(self):
        '''
           create a client configuration RPM from the entitlement certificate
        '''
        RHUIManagerClient.create_conf_rpm(RHUA,
                                          "/tmp",
                                          f"/tmp/{self.test['repo_id']}.crt",
                                          f"/tmp/{self.test['repo_id']}.key",
                                          self.test["repo_id"])

    def test_09_install_conf_rpm(self):
        '''
           install the client configuration RPM
        '''
        # get rid of undesired repos first
        Util.remove_amazon_rhui_conf_rpm(CLI)
        Util.disable_beta_repos(CLI)
        Util.install_pkg_from_rhua(RHUA,
                                   CLI,
                                   f"/tmp/{self.test['repo_id']}-2.0/build/RPMS/noarch/" +
                                   f"{self.test['repo_id']}-2.0-1.noarch.rpm")

    def test_10_install_test_rpm(self):
        '''
           install an old version of an RPM from the repo
        '''
        nvr = f"{self.test['test_package']}-{self.test['old_version']}"
        Yummy.install(CLI, [nvr], timeout=60)

    def test_11_check_updateinfo(self):
        '''
           check if the expected update info is found
        '''
        # yum should print Update ID : RHXA-YYYY:NNNNN
        # dnf should print Update ID: RHXA-YYYY:NNNNN
        Expect.ping_pong(CLI,
                         "yum updateinfo info",
                         "Update ID ?: " + self.test["errata"])

    def test_12_compare_n_of_updates(self):
        '''
           check if the all the updates from the original updateinfo file are available from RHUI
        '''
        errata_pattern = "RH.A-[0-9]*:[0-9]*"
        if self.version <= 7:
            cache = f"/var/cache/yum/{self.arch}/{self.version}Server/" + \
                    f"rhui-custom-{self.test['repo_id']}"
        else:
            cache = f"/var/cache/dnf/rhui-custom-{self.test['repo_id']}*/repodata"

        _, stdout, _ = RHUA.exec_command(f"zgrep -o '{errata_pattern}' " +
                                         f"/tmp/extra_rhui_files/{self.test['repo_id']}" +
                                         "/updateinfo.xml.gz " +
                                         "| sort -u")
        orig_errata = stdout.read().decode().splitlines()

        _, stdout, _ = CLI.exec_command(f"zgrep -o '{errata_pattern}' " +
                                        f"{cache}/*updateinfo.xml.gz " +
                                        "| sort -u")
        processed_errata = stdout.read().decode().splitlines()
        nose.tools.eq_(orig_errata, processed_errata)

    def test_13_uncompressed_xml(self):
        '''
           also check if an uncompressed updateinfo.xml file can be used
        '''
        RHUIManagerCLI.repo_add_errata(RHUA,
                                       self.test["repo_id"],
                                       "/tmp/extra_rhui_files/" +
                                       f"{self.test['uncompressed_updateinfo']}/updateinfo.xml")
        # not going to test that on a client, just checking the log
        Expect.expect_retval(RHUA,
                             "tail -1 ~/.rhui/rhui.log | grep 'Import of erratum.*was successful'")

    def test_99_cleanup(self):
        '''
           remove the repo, uninstall hap, cds, cli rpm artefacts; remove rpms from cli
        '''
        Util.remove_rpm(CLI, [self.test["test_package"], self.test["repo_id"]])
        RHUIManagerRepo.delete_all_repos(RHUA)
        Expect.expect_retval(RHUA, f"rm -rf /tmp/{self.test['repo_id']}*")
        # delete the errata from Pulp
        PulpAPI.delete_orphans(RHUA)
        if not getenv("RHUISKIPSETUP"):
            RHUIManagerInstance.delete_all(RHUA, "loadbalancers")
            RHUIManagerInstance.delete_all(RHUA, "cds")

    @staticmethod
    def teardown_class():
        '''
           announce the end of the test run
        '''
        print(f"*** Finished running {basename(__file__)}. ***")
