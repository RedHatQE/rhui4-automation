'''RHUI CLI tests'''

import json
import logging
from os.path import basename, getsize, join
import random
import re
from shutil import rmtree
from tempfile import mkdtemp
import time

from configparser import ConfigParser
import nose
from stitches.expect import Expect
import yaml

from rhui4_tests_lib.conmgr import ConMgr, USER_NAME
from rhui4_tests_lib.rhuimanager import RHUIManager
from rhui4_tests_lib.rhuimanager_cmdline import RHUIManagerCLI, \
                                                CustomRepoAlreadyExists, \
                                                CustomRepoGpgKeyNotFound, \
                                                NoValidEntitlementsProvided
from rhui4_tests_lib.helpers import Helpers
from rhui4_tests_lib.util import Util

logging.basicConfig(level=logging.DEBUG)

RHUA = ConMgr.connect()
CUSTOM_REPOS = ["my_custom_repo", "another_custom_repo", "yet_another_custom_repo"]
CR_NAMES = [cr.replace("_", " ").title() for cr in CUSTOM_REPOS]
ALT_CONTENT_SRC_NAME = "test_acs"
CLI_CFG = ["test-rhui", "1.0", "0.1"]
DATADIR = "/tmp/extra_rhui_files"
KEYFILE = "test_gpg_key"
TEST_RPM = "rhui-rpm-upload-test-1-1.noarch.rpm"
TEST_RH_RPM = "sapconf"
CERTS = {"normal": "rhcert.pem",
         "expired": "rhcert_expired.pem",
         "incompatible": "rhcert_incompatible.pem",
         "partial": "rhcert_partially_invalid.pem",
         "empty": "rhcert_empty.pem"}
TMPDIR = mkdtemp()
# the TMPDIR path is also used on the RHUA, where it's automatically created later
YUM_REPO_FILE = join(TMPDIR, "rh-cloud.repo")
IMPORT_REPO_FILES_DIR = join(DATADIR, "repo_files")
IMPORT_REPO_FILES = {"good": join(IMPORT_REPO_FILES_DIR, "good_repos.yaml"),
                     "wrongrepo": join(IMPORT_REPO_FILES_DIR, "wrong_repo_id.yaml"),
                     "noname": join(IMPORT_REPO_FILES_DIR, "no_name.yaml"),
                     "noids": join(IMPORT_REPO_FILES_DIR, "no_repo_ids.yaml"),
                     "badname": join(IMPORT_REPO_FILES_DIR, "bad_name.yaml"),
                     "badids": join(IMPORT_REPO_FILES_DIR, "bad_ids.yaml"),
                     "notafile": join(IMPORT_REPO_FILES_DIR, "not_a_file.yaml")}

class TestCLI():
    '''
        class for CLI tests
    '''

    def __init__(self):
        with open("/etc/rhui4_tests/tested_repos.yaml", encoding="utf-8") as configfile:
            doc = yaml.safe_load(configfile)

        self.yum_repo_names = [doc["yum_repos"][6]["x86_64"]["name"],
                               doc["yum_repos"][8]["x86_64"]["name"]]
        self.yum_repo_ids = [doc["yum_repos"][6]["x86_64"]["id"],
                             doc["yum_repos"][8]["x86_64"]["id"]]
        self.yum_repo_labels = [doc["yum_repos"][6]["x86_64"]["label"],
                                doc["yum_repos"][8]["x86_64"]["label"]]
        self.yum_repo_paths = [doc["yum_repos"][6]["x86_64"]["path"],
                               doc["yum_repos"][8]["x86_64"]["path"]]
        self.product_name = doc["product"]["name"]
        self.product_ids = doc["product"]["ids"]
        self.remote_content = doc["remote_content"]

    @staticmethod
    def setup_class():
        '''
           announce the beginning of the test run
        '''
        print(f"*** Running {basename(__file__)}: ***")

    @staticmethod
    def test_01_init_repo_check():
        '''log in to RHUI, check if the repo list is empty'''
        RHUIManager.initial_run(RHUA)
        repolist = RHUIManagerCLI.repo_list(RHUA, True)
        nose.tools.ok_(not repolist, msg=f"there are some repos already: {repolist}")

    @staticmethod
    def test_02_create_custom_repos():
        '''create three custom repos for testing'''
        # the first repo will be unprotected, with default parameters
        RHUIManagerCLI.repo_create_custom(RHUA, CUSTOM_REPOS[0])
        # the second repo will have a lot of custom parameters; it will be a protected repo
        RHUIManagerCLI.repo_create_custom(RHUA,
                                          repo_id=CUSTOM_REPOS[1],
                                          path=f"huh-{CUSTOM_REPOS[1]}",
                                          display_name=CR_NAMES[1],
                                          protected=True,
                                          gpg_public_keys=join(DATADIR, KEYFILE))
        # the third repo will also be protected
        RHUIManagerCLI.repo_create_custom(RHUA,
                                          repo_id=CUSTOM_REPOS[2],
                                          protected=True)
        # test an unrecognized option
        Expect.expect_retval(RHUA,
                             "rhui-manager repo create_custom --repo_id yay --display-name Yay",
                             254)

    @staticmethod
    def test_03_custom_repo_checks():
        '''check if the custom repo cannot be added twice and if the GPG key path is validated'''
        nose.tools.assert_raises(CustomRepoAlreadyExists,
                                 RHUIManagerCLI.repo_create_custom,
                                 RHUA,
                                 CUSTOM_REPOS[0])
        nose.tools.assert_raises(CustomRepoGpgKeyNotFound,
                                 RHUIManagerCLI.repo_create_custom,
                                 RHUA,
                                 CUSTOM_REPOS[0] + "2",
                                 gpg_public_keys="/this_file_cant_be_there")

    @staticmethod
    def test_04_check_custom_repos():
        '''check if the custom repos were actually created'''
        # try a delimiter this time
        delimiter = ","
        repos_expected = delimiter.join(sorted(CUSTOM_REPOS))
        repos_actual = RHUIManagerCLI.repo_list(RHUA, True, False, delimiter)
        nose.tools.eq_(repos_expected, repos_actual)
        # ^ also checks if the repo IDs are sorted
        # test an unrecognized option
        Expect.expect_retval(RHUA, "rhui-manager repo list --redhat", 254)

    @staticmethod
    def test_05_upload_local_rpms():
        '''upload content from a local directory to one of the custom repos'''
        RHUIManagerCLI.packages_upload(RHUA, CUSTOM_REPOS[0], join(DATADIR, TEST_RPM))
        # also supply the whole directory
        RHUIManagerCLI.packages_upload(RHUA, CUSTOM_REPOS[0], DATADIR)
        # test an unrecognized option
        Expect.expect_retval(RHUA, "rhui-manager packages upload --repo_id a --packages / --f", 254)

    def test_06_upload_remote_rpms(self):
        '''upload content from remote servers to the custom repos'''
        # try single RPMs first
        RHUIManagerCLI.packages_remote(RHUA, CUSTOM_REPOS[1], self.remote_content["rpm"])
        RHUIManagerCLI.packages_remote(RHUA, CUSTOM_REPOS[1], self.remote_content["ftp"])
        # and now an HTML page with links to RPMs
        RHUIManagerCLI.packages_remote(RHUA,
                                       CUSTOM_REPOS[2],
                                       self.remote_content["html_with_links"])
        # and finally also some bad stuff
        rhua = ConMgr.get_rhua_hostname()
        try:
            RHUIManagerCLI.packages_remote(RHUA, CUSTOM_REPOS[2], f"https://{rhua}/")
        except RuntimeError as err:
            # the RHUA listens on port 443 and uses a self-signed cert, which should be refused
            nose.tools.ok_("CERTIFICATE_VERIFY_FAILED" in str(err))
        # test an unrecognized option
        Expect.expect_retval(RHUA,
                             "rhui-manager packages remote --repo_id a --url ftp://b.be/c/ --def",
                             254)

    def test_07_check_packages(self):
        '''check that the uploaded packages are now in the repos'''
        package_lists = [RHUIManagerCLI.packages_list(RHUA, repo) for repo in CUSTOM_REPOS]
        nose.tools.eq_(package_lists[0], Util.get_rpms_in_dir(RHUA, DATADIR))
        rpm_ftp_combined = sorted([basename(self.remote_content[p]) for p in ["rpm", "ftp"]])
        nose.tools.eq_(package_lists[1], rpm_ftp_combined)
        linked_rpms = sorted(Util.get_rpm_links(self.remote_content["html_with_links"]))
        nose.tools.eq_(package_lists[2], linked_rpms)
        # test an unrecognized option
        Expect.expect_retval(RHUA, "rhui-manager packages list --repo_id a --meow", 254)

    @staticmethod
    def test_08_upload_certificate():
        '''upload the entitlement certificate'''
        RHUIManagerCLI.cert_upload(RHUA, join(DATADIR, CERTS["normal"]))
        # test an unrecognized option
        Expect.expect_retval(RHUA,
                             "rhui-manager cert upload --cert /tmp/c.crt --lock thedoor",
                             254)

    def test_09_check_certificate_info(self):
        '''check certificate info for validity'''
        ent_list = RHUIManagerCLI.cert_info(RHUA)
        nose.tools.ok_(self.yum_repo_names[0] in ent_list,
                       msg=f"{self.yum_repo_names[0]} not found in {ent_list}")
        # test an unrecognized option
        Expect.expect_retval(RHUA, "rhui-manager cert info --debug", 254)

    @staticmethod
    def test_10_check_certificate_exp():
        '''check if the certificate expiration date is OK'''
        RHUIManager.cacert_expiration(RHUA)

    def test_11_check_unused_product(self):
        '''check if a repo is available'''
        unused_repos = RHUIManagerCLI.repo_unused(RHUA)
        nose.tools.ok_(self.yum_repo_names[0] in unused_repos,
                       msg=f"{self.yum_repo_names[0]} not found in {unused_repos}")
        # test an unrecognized option
        Expect.expect_retval(RHUA, "rhui-manager repo unused --by-repo_id", 254)

    def test_12_add_rh_repo_by_id(self):
        '''add a Red Hat repo by its ID'''
        RHUIManagerCLI.repo_add_by_repo(RHUA, [self.yum_repo_ids[1]])
        # also try an invalid repo ID, expect a non-zero exit code
        RHUIManagerCLI.repo_add_by_repo(RHUA, ["foo"], False, True)
        # try the already added repo, also expect a non-zero exit code
        RHUIManagerCLI.repo_add_by_repo(RHUA, [self.yum_repo_ids[1]], False, False, True)
        # try a combination of both, again expect a non-zero exit code
        RHUIManagerCLI.repo_add_by_repo(RHUA, ["foo", self.yum_repo_ids[1]], False, True, True)
        # test an unrecognized option
        Expect.expect_retval(RHUA, "rhui-manager repo add_by_repo --repo_ids boo --names Boo", 254)

    def test_13_add_rh_repo_by_product(self):
        '''add a Red Hat repo by its product name'''
        RHUIManagerCLI.repo_add(RHUA, self.yum_repo_names[0])
        # test an unrecognized option
        Expect.expect_retval(RHUA, "rhui-manager repo add --product_name All --sync_now", 254)

    def test_14_repo_list(self):
        '''check the added repos'''
        repolist_actual = RHUIManagerCLI.repo_list(RHUA, True, True).splitlines()
        nose.tools.eq_(sorted(self.yum_repo_ids), repolist_actual)
        # test an unrecognized option
        Expect.expect_retval(RHUA, "rhui-manager repo list --ids_only --delimeter ,", 254)

    def test_15_start_syncing_repo(self):
        '''sync one of the repos'''
        RHUIManagerCLI.repo_sync(RHUA, self.yum_repo_ids[1])
        # test an unrecognized option
        Expect.expect_retval(RHUA, "rhui-manager repo sync --repo_id myrepo --progress=dot", 254)

    def test_16_repo_info(self):
        '''verify that the repo name is part of the information about the specified repo ID'''
        info = RHUIManagerCLI.repo_info(RHUA, self.yum_repo_ids[1])
        nose.tools.eq_(info["name"], Util.format_repo(self.yum_repo_names[1], 8))

    def test_17_check_package_in_repo(self):
        '''check a random package in the repo'''
        package_list = RHUIManagerCLI.packages_list(RHUA, self.yum_repo_ids[1])
        test_package_list = [package for package in package_list if package.startswith(TEST_RH_RPM)]
        nose.tools.ok_(test_package_list,
                       msg=f"no {TEST_RH_RPM}* in {package_list}")

    def test_18_list_labels(self):
        '''check repo labels'''
        actual_labels = RHUIManagerCLI.client_labels(RHUA)
        nose.tools.ok_(all(repo in actual_labels for repo in self.yum_repo_labels),
                       msg=f"{self.yum_repo_labels} not found in {actual_labels}")
        # test an unrecognized option
        Expect.expect_retval(RHUA, "rhui-manager client labels --json", 254)

    def test_19_generate_certificate(self):
        '''generate an entitlement certificate'''
        # generate it for RH repos and the first protected custom repo
        # the label is the repo ID in the case of custom repos
        RHUIManagerCLI.client_cert(RHUA,
                                   self.yum_repo_labels + [CUSTOM_REPOS[1]],
                                   CLI_CFG[0],
                                   365,
                                   TMPDIR)
        # test an unrecognized option
        Expect.expect_retval(RHUA, "rhui-manager client cert --auto", 254)

    @staticmethod
    def test_20_check_cli_crt_sig():
        '''check if SHA-256 is used in the client certificate signature'''
        # for RHBZ#1628957
        sigs_expected = ["sha256", "sha256"]
        _, stdout, _ = RHUA.exec_command("openssl x509 -noout -text -in " +
                                         f"{TMPDIR}/{CLI_CFG[0]}.crt")
        cert_details = stdout.read().decode()
        sigs_actual = re.findall("sha[0-9]+", cert_details)
        nose.tools.eq_(sigs_expected, sigs_actual)

    def test_21_check_stray_custom_repo(self):
        '''check if only the wanted repos are in the certificate'''
        repo_labels_expected = [f"custom-{CUSTOM_REPOS[1]}"] + self.yum_repo_labels
        _, stdout, _ = RHUA.exec_command(f"cat {TMPDIR}/{CLI_CFG[0]}-extensions.txt")
        extensions = stdout.read().decode()
        repo_labels_actual = re.findall("|".join(["custom-.*"] + self.yum_repo_labels),
                                        extensions)
        nose.tools.eq_(sorted(repo_labels_expected), sorted(repo_labels_actual))

    @staticmethod
    def test_22_create_cli_config_rpm():
        '''create a client configuration RPM'''
        RHUIManagerCLI.client_rpm(RHUA,
                                  [f"{TMPDIR}/{CLI_CFG[0]}.key", f"{TMPDIR}/{CLI_CFG[0]}.crt"],
                                  CLI_CFG,
                                  TMPDIR,
                                  [CUSTOM_REPOS[0]],
                                  "_none_")
        # check if the rpm was created
        conf_rpm = f"{TMPDIR}/{CLI_CFG[0]}-{CLI_CFG[1]}/build/RPMS/noarch/" + \
                   f"{CLI_CFG[0]}-{CLI_CFG[1]}-{CLI_CFG[2]}.noarch.rpm"
        Expect.expect_retval(RHUA, f"test -f {conf_rpm}")
        # test an unrecognized option
        Expect.expect_retval(RHUA, "rhui-manager client rpm --wizard", 254)

    def test_23_ensure_gpgcheck_config(self):
        '''ensure that GPG checking is configured in the client configuration as expected'''
        # for RHBZ#1428756
        # we'll need the repo file in a few tests; fetch it now
        remote_repo_file = f"{TMPDIR}/{CLI_CFG[0]}-{CLI_CFG[1]}/build/BUILD/" + \
                           f"{CLI_CFG[0]}-{CLI_CFG[1]}/rh-cloud.repo"
        try:
            Util.fetch(RHUA, remote_repo_file, YUM_REPO_FILE)
        except IOError:
            raise RuntimeError("configuration not created, can't test it") from None
        yum_cfg = ConfigParser()
        yum_cfg.read(YUM_REPO_FILE)
        # check RH repos: they all must have GPG checking enabled; get a list of those that don't
        bad = [r for r in self.yum_repo_labels if not yum_cfg.getboolean(f"rhui-{r}", "gpgcheck")]
        # check custom repos: the 2nd must have GPG checking enabled:
        if not yum_cfg.getboolean(f"rhui-custom-{CUSTOM_REPOS[1]}", "gpgcheck"):
            bad.append(CUSTOM_REPOS[1])
        # the first one mustn't:
        if yum_cfg.getboolean(f"rhui-custom-{CUSTOM_REPOS[0]}", "gpgcheck"):
            bad.append(CUSTOM_REPOS[0])
        nose.tools.ok_(not bad, msg=f"Unexpected GPG checking configuration for {bad}")

    @staticmethod
    def test_24_ensure_proxy_config():
        '''ensure that the proxy setting is used in the client configuration'''
        # for RHBZ#1658088
        # reuse the fetched file if possible
        if not getsize(YUM_REPO_FILE):
            raise RuntimeError("configuration not created, can't test it")
        yum_cfg = ConfigParser()
        yum_cfg.read(YUM_REPO_FILE)
        nose.tools.ok_(all(yum_cfg.get(r, "proxy") == "_none_" for r in yum_cfg.sections()))

    @staticmethod
    def test_25_custom_repo_used():
        '''check if the protected custom repo is included in the client configuration'''
        # for RHBZ#1663422
        # reuse the fetched file if possible
        if not getsize(YUM_REPO_FILE):
            raise RuntimeError("configuration not created, can't test it")
        yum_cfg = ConfigParser()
        yum_cfg.read(YUM_REPO_FILE)
        nose.tools.ok_(f"rhui-custom-{CUSTOM_REPOS[1]}" in yum_cfg.sections())

    def test_26_create_acs_config_rpm(self):
        '''create an alternate content source configuration RPM'''
        # for RHBZ#1695464
        name = ALT_CONTENT_SRC_NAME
        RHUIManagerCLI.client_content_source(RHUA,
                                             self.yum_repo_labels,
                                             [name],
                                             TMPDIR)
        # check that
        cmd = f"rpm2cpio {TMPDIR}/{name}-2.0/build/RPMS/noarch/{name}-2.0-1.noarch.rpm | " + \
              r"cpio -i --to-stdout \*.conf | " + \
              "sed -n -e '/^paths:/,$p' | " + \
              "sed s/paths://"
        _, stdout, _ = RHUA.exec_command(cmd)
        paths_actual_raw = stdout.read().decode().splitlines()
        # the paths are indented, let's get rid of the formatting
        paths_actual = [p.lstrip() for p in paths_actual_raw]
        nose.tools.eq_(sorted(self.yum_repo_paths), sorted(paths_actual))
        # test an unrecognized option
        Expect.expect_retval(RHUA,
                             "rhui-manager client content_source --rpm_name cs --dir / " +
                             "--rpm_epoch 2",
                             254)

    def test_27_create_acs_config_json(self):
        '''create an alternate content source configuration JSON file'''
        # for RHBZ#2001087
        ssl_ca_file = f"{DATADIR}/custom_certs/ssl.crt"
        lb_hostname = ConMgr.get_cds_lb_hostname()
        # create the configuration: using labels to generate a new cert, valid for 1 day, custom CA
        RHUIManagerCLI.client_acs_config(RHUA,
                                         self.yum_repo_labels + [CUSTOM_REPOS[2], 1],
                                         TMPDIR,
                                         ssl_ca_file)
        # check that
        _, stdout, _ = RHUA.exec_command(f"cat {TMPDIR}/acs-configuration.json")
        configuration = json.load(stdout)
        # first the base URL
        nose.tools.eq_(configuration["base_url"], f"https://{lb_hostname}/pulp/content/")
        # paths
        nose.tools.eq_(sorted(configuration["paths"]),
                       sorted(self.yum_repo_paths + [f"protected/{CUSTOM_REPOS[2]}"]))
        # other pieces of information
        for field in ["ca_cert", "entitlement_cert", "private_key"]:
            nose.tools.ok_(field in configuration,
                           msg=f"configuration consists of {list(configuration.keys())}")
        # expiration: will it be expired 25 hours from now?
        nose.tools.ok_(Util.cert_expired(RHUA, f"{TMPDIR}/acs-entitlement.crt", 90000))
        # but not 23 hours from now?
        nose.tools.ok_(not Util.cert_expired(RHUA, f"{TMPDIR}/acs-entitlement.crt", 82800))
        # whether the custom CA cert was used
        _, stdout, _ = RHUA.exec_command(f"cat {ssl_ca_file}")
        orig_ca_cert = stdout.read().decode()
        nose.tools.eq_(configuration["ca_cert"], orig_ca_cert)

        # also the scenario with a supplied cert & key (created in test_19), default SSL cert
        base_file_name = join(TMPDIR, CLI_CFG[0])
        custom_cert = base_file_name + ".crt"
        custom_key = base_file_name + ".key"
        RHUIManagerCLI.client_acs_config(RHUA, [custom_key, custom_cert], TMPDIR)
        # check that; load the JSON data first
        _, stdout, _ = RHUA.exec_command(f"cat {TMPDIR}/acs-configuration.json")
        configuration = json.load(stdout)
        # paths
        nose.tools.eq_(sorted(configuration["paths"]),
                       sorted(self.yum_repo_paths + [f"protected/huh-{CUSTOM_REPOS[1]}"]))
        # load the cert and compare it
        _, stdout, _ = RHUA.exec_command(f"cat {custom_cert}")
        orig_ent_cert = stdout.read().decode()
        nose.tools.eq_(configuration["entitlement_cert"], orig_ent_cert)
        # load the key and compare it
        _, stdout, _ = RHUA.exec_command(f"cat {custom_key}")
        orig_ent_key = stdout.read().decode()
        nose.tools.eq_(configuration["private_key"], orig_ent_key)
        # load the default SSL CA cert and compare it
        default_ca_path = Helpers.get_from_rhui_tools_conf(RHUA, "security", "ssl_ca_crt")
        _, stdout, _ = RHUA.exec_command(f"cat {default_ca_path}")
        default_ca_cert = stdout.read().decode()
        nose.tools.eq_(configuration["ca_cert"], default_ca_cert)

        # try using an invalid repo label
        nose.tools.assert_raises(NoValidEntitlementsProvided,
                                 RHUIManagerCLI.client_acs_config,
                                 RHUA,
                                 ["rhel-foo"],
                                 TMPDIR)
        # test an unrecognized option
        Expect.expect_retval(RHUA, "rhui-manager client acs_config --directory /", 254)

    @staticmethod
    def test_28_upload_expired_cert():
        '''check expired certificate handling'''
        try:
            RHUIManagerCLI.cert_upload(RHUA, join(DATADIR, CERTS["expired"]))
        except RuntimeError as err:
            nose.tools.ok_("The provided certificate is expired or invalid" in str(err),
                           msg=f"unexpected error: {err}")

    @staticmethod
    def test_29_upload_incompat_cert():
        '''check incompatible certificate handling'''
        cert = join(DATADIR, CERTS["incompatible"])
        if Util.cert_expired(RHUA, cert):
            raise nose.exc.SkipTest("The given certificate has already expired.")
        try:
            RHUIManagerCLI.cert_upload(RHUA, cert)
        except RuntimeError as err:
            nose.tools.ok_("does not contain any entitlements" in str(err),
                           msg=f"unexpected error: {err}")

    @staticmethod
    def test_30_remove_package():
        '''check if a package can be removed from a custom repo'''
        # export the custom repo first, as the removal of the symlinks must be tested
        RHUIManagerCLI.repo_export(RHUA, CUSTOM_REPOS[0])
        time.sleep(5)
        # make sure the symlink for the packages to be removed exists
        symlink_test = "test -L /var/lib/rhui/remote_share/symlinks/pulp/content/" \
                       f"unprotected/{CUSTOM_REPOS[0]}/Packages/{TEST_RPM[0].lower()}/{TEST_RPM}"
        Expect.expect_retval(RHUA, symlink_test)
        # get a list of repo packages
        before_list = RHUIManagerCLI.packages_list(RHUA, CUSTOM_REPOS[0])
        (name, version, release_arch_ext) = TEST_RPM.rsplit("-", 2)
        release = release_arch_ext.split(".")[0]
        # run the removal command
        RHUIManagerCLI.packages_remove(RHUA,
                                       CUSTOM_REPOS[0],
                                       name,
                                       f"{version}-{release}",
                                       True)
        time.sleep(5)
        # find out what's missing now, should be the removed package
        after_list = RHUIManagerCLI.packages_list(RHUA, CUSTOM_REPOS[0])
        difference = set(before_list) ^ set(after_list)
        nose.tools.eq_(difference, {TEST_RPM})
        # also check if the symlink is gone
        Expect.expect_retval(RHUA, symlink_test, 1)
        # test an unrecognized option
        Expect.expect_retval(RHUA,
                             "rhui-manager packages remove " +
                             "--repo_id z --package a-1-2.noarch.rpm --bruteforce",
                             254)

    def test_31_remove_all_packages(self):
        '''remove all packages from a custom repo'''
        # export the custom repo first, as the removal of the symlinks must be tested
        RHUIManagerCLI.repo_export(RHUA, CUSTOM_REPOS[1])
        time.sleep(5)
        # make sure the symlink for one of the packages to be removed exists
        rpm = basename(self.remote_content["rpm"])
        symlink_test = "test -L /var/lib/rhui/remote_share/symlinks/pulp/content/" \
                       f"protected/huh-{CUSTOM_REPOS[1]}/Packages/{rpm[0].lower()}/{rpm}"
        Expect.expect_retval(RHUA, symlink_test)
        # get a list of repo packages
        before_list = RHUIManagerCLI.packages_list(RHUA, CUSTOM_REPOS[1])
        names = [filename.rsplit("-", 2)[0] for filename in before_list]
        # run the removal commands
        for name in names:
            RHUIManagerCLI.packages_remove(RHUA, CUSTOM_REPOS[1], name, force=True)
            time.sleep(5)
        after_list = RHUIManagerCLI.packages_list(RHUA, CUSTOM_REPOS[1])
        # the package list for the repo should be empty now
        nose.tools.eq_(after_list, [])
        # also check if the symlinks are gone
        symlink_test = "[[ $(find /var/lib/rhui/remote_share/symlinks/pulp/content/" \
                       f"protected/huh-{CUSTOM_REPOS[1]}/Packages -type l | wc -l) == 0 ]]"
        Expect.expect_retval(RHUA, symlink_test)

    def test_37_resync_repo(self):
        '''sync the repo again'''
        RHUIManagerCLI.repo_sync(RHUA, self.yum_repo_ids[1])

    @staticmethod
    def test_38_resync_no_warning():
        '''check if the syncs did not cause known unnecessary warnings'''
        # for RHBZ#1506872
        Expect.expect_retval(RHUA, "grep 'pulp.*metadata:WARNING' /var/log/messages", 1)
        # for RHBZ#1579294
        Expect.expect_retval(RHUA, "grep 'pulp.*publish:WARNING' /var/log/messages", 1)
        # for RHBZ#1487523
        Expect.expect_retval(RHUA,
                             "grep 'pulp.*Purging duplicate NEVRA can' /var/log/messages", 1)

    @staticmethod
    def test_39_list_repos():
        '''get a list of available repos for further examination'''
        Expect.expect_retval(RHUA,
                             f"rhui-manager repo unused > {TMPDIR}/repos.out 2> {TMPDIR}/repos.err",
                             timeout=1200)

    @staticmethod
    def test_40_check_iso_repos():
        '''check if non-RPM repos were ignored'''
        # for RHBZ#1199426
        Expect.expect_retval(RHUA,
                             f"egrep 'Containers|Images|ISOs|Kickstart' {TMPDIR}/repos.out", 1)

    @staticmethod
    def test_41_check_pygiwarning():
        '''check if PyGIWarning was not issued'''
        # for RHBZ#1450430
        Expect.expect_retval(RHUA, f"grep PyGIWarning {TMPDIR}/repos.err", 1)

    def test_42_check_repo_sorting(self):
        '''check if repo lists are sorted'''
        # for RHBZ#1601478
        repolist_expected = sorted(CUSTOM_REPOS + self.yum_repo_ids)
        repolist_actual = RHUIManagerCLI.repo_list(RHUA, True).splitlines()
        nose.tools.eq_(repolist_expected, repolist_actual)

    def test_43_repo_export(self):
        '''test the repo export feature'''
        repo = self.yum_repo_ids[1]
        # export the repo
        RHUIManagerCLI.repo_export(RHUA, repo)
        # wait a bit
        time.sleep(4)
        # get a random package file name from the repo
        package_list = RHUIManagerCLI.packages_list(RHUA, repo)
        test_package = random.choice(package_list)
        # construct the full path to the symlink
        # remember the subpath so it can be deleted in the end (to clean up)
        path = "/var/lib/rhui/remote_share/symlinks/pulp/content/"
        path += self.yum_repo_paths[1]
        repo_path = path
        path += "/Packages/"
        path += test_package[0].lower()
        path += "/"
        path += test_package
        # does the symlink exist?
        Expect.expect_retval(RHUA, "test -h " + path)
        # was the log file updated accordingly?
        Expect.ping_pong(RHUA,
                         "tail /root/.rhui/rhui.log",
                         f"Repo: {repo} .* exported to filesystem")
        # clean up the repo symlink path
        Expect.expect_retval(RHUA, "rm -rf " + repo_path)
        # test an unrecognized option
        Expect.expect_retval(RHUA, "rhui-manager repo export --repo_id bob --log /tmp/exports", 254)

    def test_44_upload_semi_bad_cert(self):
        '''check that a partially invalid certificate can still be accepted'''
        # for RHBZ#1588931 & RHBZ#1584527
        # delete currently used certificates and repos first
        RHUIManager.remove_rh_certs(RHUA)
        for repo in CUSTOM_REPOS + self.yum_repo_ids:
            RHUIManagerCLI.repo_delete(RHUA, repo)
        repolist = RHUIManagerCLI.repo_list(RHUA, True)
        nose.tools.ok_(not repolist, msg=f"can't continue as some repos remain: {repolist}")
        # try uploading the cert now
        cert = join(DATADIR, CERTS["partial"])
        if Util.cert_expired(RHUA, cert):
            raise nose.exc.SkipTest("The given certificate has already expired.")
        RHUIManagerCLI.cert_upload(RHUA, cert)
        # the RHUI log must contain the fact that an invalid path was found in the cert
        Expect.ping_pong(RHUA, "tail /root/.rhui/rhui.log", "Invalid entitlement path")
        RHUIManager.remove_rh_certs(RHUA)

    @staticmethod
    def test_45_upload_empty_cert():
        '''check that an empty certificate is rejected (no traceback)'''
        # for RHBZ#1497028
        cert = join(DATADIR, CERTS["empty"])
        if Util.cert_expired(RHUA, cert):
            raise nose.exc.SkipTest("The given certificate has already expired.")
        try:
            RHUIManagerCLI.cert_upload(RHUA, cert)
        except RuntimeError as err:
            nose.tools.ok_("does not contain any entitlements" in str(err),
                           msg=f"unexpected error: {err}")
    def test_46_multi_repo_product(self):
        '''check that all repos in a multi-repo product get added'''
        # for RHBZ#1651638
        RHUIManagerCLI.cert_upload(RHUA, join(DATADIR, CERTS["normal"]))
        RHUIManagerCLI.repo_add(RHUA, self.product_name)
        # wait a few seconds for the repos to actually get added
        time.sleep(4)
        repolist_actual = RHUIManagerCLI.repo_list(RHUA, True).splitlines()
        nose.tools.eq_(self.product_ids, repolist_actual)
        # clean up
        for repo in self.product_ids:
            RHUIManagerCLI.repo_delete(RHUA, repo)
        RHUIManager.remove_rh_certs(RHUA)

    @staticmethod
    def test_47_add_by_file():
        '''check that all repos defined in an input file get added'''
        # get a list of repos that are expected to be added
        expected_repo_ids = sorted(Helpers.get_repos_from_yaml(RHUA, IMPORT_REPO_FILES["good"]))
        # upload the cert and try adding the repos from the file, sync them all the same time
        RHUIManagerCLI.cert_upload(RHUA, join(DATADIR, CERTS["normal"]))
        RHUIManagerCLI.repo_add_by_file(RHUA, IMPORT_REPO_FILES["good"], True)
        # check the sync status
        for repo in expected_repo_ids:
            info = RHUIManagerCLI.repo_info(RHUA, repo)
            nose.tools.ok_(info["lastsync"] != "Never")
        actual_repo_ids = RHUIManagerCLI.repo_list(RHUA, True).splitlines()
        # ok?
        nose.tools.eq_(expected_repo_ids, actual_repo_ids)
        # re-adding the repos should produce a bad exit code
        RHUIManagerCLI.repo_add_by_file(RHUA, IMPORT_REPO_FILES["good"], False, "already_added")
        # clean up
        for repo in actual_repo_ids:
            RHUIManagerCLI.repo_delete(RHUA, repo)
        RHUIManager.remove_rh_certs(RHUA)
        # also check an input file with an invalid repo ID
        RHUIManagerCLI.repo_add_by_file(RHUA, IMPORT_REPO_FILES["wrongrepo"], trouble="wrong_id")
        # and with no name for the repo set
        RHUIManagerCLI.repo_add_by_file(RHUA, IMPORT_REPO_FILES["noname"], trouble="no_name")
        # and with no repos at all
        RHUIManagerCLI.repo_add_by_file(RHUA, IMPORT_REPO_FILES["noids"], trouble="no_id")
        # and with an incorrectly specified name for the repo set
        RHUIManagerCLI.repo_add_by_file(RHUA, IMPORT_REPO_FILES["badname"], trouble="bad_name")
        # and with an incorrectly specified repo IDs
        RHUIManagerCLI.repo_add_by_file(RHUA, IMPORT_REPO_FILES["badids"], trouble="bad_id")
        # also check a non-existing file
        RHUIManagerCLI.repo_add_by_file(RHUA, IMPORT_REPO_FILES["notafile"], trouble="not_a_file")
        # and a file which isn't valid YAML
        RHUIManagerCLI.repo_add_by_file(RHUA, "/etc/issue", trouble="invalid_yaml")
        # test an unrecognized option
        Expect.expect_retval(RHUA, "rhui-manager repo add_by_file --file repos.yml --sync", 254)

    @staticmethod
    def test_48_rhui_scripts():
        '''test argument handling in rhui-* scripts'''
        scripts = ["rhui-export-repos", "rhui-subscription-sync", "rhui-update-mappings"]
        logs = ["/var/log/rhui/rhui-export-repos.log",
                "/var/log/rhui/rhui-subscription-sync.log",
                "/var/log/rhui/rhui-update-mappings.log"]
        bad_config = "/etc/motd"
        bad_sync_config = "/etc/ansible/ansible.cfg"
        for script, log in zip(scripts, logs):
            Expect.expect_retval(RHUA, f"{script} --config {bad_config}", 1)
            Expect.ping_pong(RHUA,
                             f"tail {log}",
                             "(pulp_api_url|cert_dir|cert_redhat_dir) is not valid")
            if script == "rhui-update-mappings":
                continue # this script doesn't have the --sync-config option
            Expect.expect_retval(RHUA, f"{script} --sync-config {bad_sync_config}", 1)
            Expect.ping_pong(RHUA, f"tail -2 {log}", "username is not valid")

    @staticmethod
    def test_49_rhui_manager_help():
        '''test help handling in rhui-manager'''
        for arg in ["-h", "--help"]:
            Expect.ping_pong(RHUA, f"rhui-manager {arg}", "Usage:.*Options:.*Commands:")
            # -h doesn't work with 1-level subcommands like --help, skip it
            if arg != "-h":
                Expect.ping_pong(RHUA, f"rhui-manager cert {arg}", "upload.*uploads.*info.*display")
            Expect.ping_pong(RHUA, f"rhui-manager cert info {arg}", "info: display")
        # test an unrecognized option
        Expect.expect_retval(RHUA, "rhui-manager --signout", 2)

    @staticmethod
    def test_50_caller_name():
        '''check if rhui-manager gets the caller's login name correctly'''
        # for RHBZ#2156576
        Expect.ping_pong(RHUA,
                         "rhui-manager --noninteractive migrate --help",
                         f"default={USER_NAME}")
        # also check cron logs
        Expect.expect_retval(RHUA, "grep -q 'no login name' /var/log/cron", 1)

    @staticmethod
    def test_51_sync_invalid_repo():
        '''check if rhui-manager correctly handles syncing an invalid repo'''
        RHUIManagerCLI.repo_sync(RHUA, "bobs-your-uncle", is_valid=False)

    @staticmethod
    def test_52_delete_invalid_repo():
        '''check if rhui-manager correctly handles deleting an invalid repo'''
        RHUIManagerCLI.repo_delete(RHUA, "bobs-your-uncle", False)

    def test_53_migrate_repos_already_added(self):
        '''check for a proper exit code if migration is run when a repo already exists'''
        cmd = "rhui-manager migrate --hostname foo.example.com --password foo"
        RHUIManagerCLI.cert_upload(RHUA, join(DATADIR, CERTS["normal"]))
        RHUIManagerCLI.repo_add_by_repo(RHUA, [self.yum_repo_ids[1]])
        Expect.expect_retval(RHUA, cmd, 248)
        RHUIManagerCLI.repo_delete(RHUA, self.yum_repo_ids[1])
        RHUIManager.remove_rh_certs(RHUA)

    @staticmethod
    def test_99_cleanup():
        '''cleanup: remove temporary files'''
        rmtree(TMPDIR)
        Expect.expect_retval(RHUA, f"rm -rf {TMPDIR}")
        Expect.expect_retval(RHUA, f"rm -f /tmp/{CLI_CFG[0]}-{CLI_CFG[1]}.spec")
        Expect.expect_retval(RHUA, f"rm -f /tmp/{ALT_CONTENT_SRC_NAME}-2.0.spec")

    @staticmethod
    def teardown_class():
        '''
           announce the end of the test run
        '''
        print(f"*** Finished running {basename(__file__)}. ***")
