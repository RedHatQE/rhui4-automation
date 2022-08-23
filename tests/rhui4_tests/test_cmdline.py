'''RHUI CLI tests'''

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

from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.rhuimanager import RHUIManager
from rhui4_tests_lib.rhuimanager_cmdline import RHUIManagerCLI, \
                                                CustomRepoAlreadyExists, \
                                                CustomRepoGpgKeyNotFound
from rhui4_tests_lib.util import Util

logging.basicConfig(level=logging.DEBUG)

RHUA = ConMgr.connect()
CUSTOM_REPOS = ["my_custom_repo", "another_custom_repo", "yet_another_custom_repo"]
CR_NAMES = [cr.replace("_", " ").title() for cr in CUSTOM_REPOS]
ALT_CONTENT_SRC_NAME = "atomic_cs"
CLI_CFG = ["test-rhui", "1.0", "0.1"]
DATADIR = "/tmp/extra_rhui_files"
KEYFILE = "test_gpg_key"
TEST_RPM = "rhui-rpm-upload-test-1-1.noarch.rpm"
TEST_RH_RPM = "ostree"
CERTS = {"Atomic": "rhcert_atomic.pem",
         "expired": "rhcert_expired.pem",
         "incompatible": "rhcert_incompatible.pem",
         "partial": "rhcert_partially_invalid.pem",
         "empty": "rhcert_empty.pem"}
TMPDIR = mkdtemp()
YUM_REPO_FILE = join(TMPDIR, "rh-cloud.repo")

class TestCLI():
    '''
        class for CLI tests
    '''

    def __init__(self):
        with open("/etc/rhui4_tests/tested_repos.yaml", encoding="utf-8") as configfile:
            doc = yaml.load(configfile)

        self.yum_repo_names = [doc["CLI_repo1"]["name"], doc["CLI_repo2"]["name"]]
        self.yum_repo_ids = [doc["CLI_repo1"]["id"], doc["CLI_repo2"]["id"]]
        self.yum_repo_labels = [doc["CLI_repo1"]["label"], doc["CLI_repo2"]["label"]]
        self.yum_repo_paths = [doc["CLI_repo1"]["path"], doc["CLI_repo2"]["path"]]
        self.product = doc["CLI_product"]
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

    @staticmethod
    def test_05_upload_local_rpms():
        '''upload content from a local directory to one of the custom repos'''
        RHUIManagerCLI.packages_upload(RHUA, CUSTOM_REPOS[0], join(DATADIR, TEST_RPM))
        # also supply the whole directory
        RHUIManagerCLI.packages_upload(RHUA, CUSTOM_REPOS[0], DATADIR)

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

    def test_07_check_packages(self):
        '''check that the uploaded packages are now in the repos'''
        package_lists = [RHUIManagerCLI.packages_list(RHUA, repo) for repo in CUSTOM_REPOS]
        nose.tools.eq_(package_lists[0], Util.get_rpms_in_dir(RHUA, DATADIR))
        rpm_ftp_combined = sorted([basename(self.remote_content[p]) for p in ["rpm", "ftp"]])
        nose.tools.eq_(package_lists[1], rpm_ftp_combined)
        linked_rpms = sorted(Util.get_rpm_links(self.remote_content["html_with_links"]))
        nose.tools.eq_(package_lists[2], linked_rpms)

    @staticmethod
    def test_08_upload_certificate():
        '''upload the Atomic (the small) entitlement certificate'''
        RHUIManagerCLI.cert_upload(RHUA, join(DATADIR, CERTS["Atomic"]))

    def test_09_check_certificate_info(self):
        '''check certificate info for validity'''
        ent_list = RHUIManagerCLI.cert_info(RHUA)
        nose.tools.ok_(self.yum_repo_names[0] in ent_list,
                       msg=f"{self.yum_repo_names[0]} not found in {ent_list}")

    @staticmethod
    def test_10_check_certificate_exp():
        '''check if the certificate expiration date is OK'''
        RHUIManager.cacert_expiration(RHUA)

    def test_11_check_unused_product(self):
        '''check if a repo is available'''
        unused_repos = RHUIManagerCLI.repo_unused(RHUA)
        nose.tools.ok_(self.yum_repo_names[0] in unused_repos,
                       msg=f"{self.yum_repo_names[0]} not found in {unused_repos}")

    def test_12_add_rh_repo_by_id(self):
        '''add a Red Hat repo by its ID'''
        RHUIManagerCLI.repo_add_by_repo(RHUA, [self.yum_repo_ids[1]])
        # also try an invalid repo ID, expect a non-zero exit code
        RHUIManagerCLI.repo_add_by_repo(RHUA, ["foo"], True)
        # try the already added repo, also expect a non-zero exit code
        RHUIManagerCLI.repo_add_by_repo(RHUA, [self.yum_repo_ids[1]], True)

    def test_13_add_rh_repo_by_product(self):
        '''add a Red Hat repo by its product name'''
        RHUIManagerCLI.repo_add(RHUA, self.yum_repo_names[0])

    def test_14_repo_list(self):
        '''check the added repos'''
        repolist_actual = RHUIManagerCLI.repo_list(RHUA, True, True).splitlines()
        nose.tools.eq_(self.yum_repo_ids, repolist_actual)

    def test_15_start_syncing_repo(self):
        '''sync one of the repos'''
        RHUIManagerCLI.repo_sync(RHUA, self.yum_repo_ids[1])

    def test_16_repo_info(self):
        '''verify that the repo name is part of the information about the specified repo ID'''
        info = RHUIManagerCLI.repo_info(RHUA, self.yum_repo_ids[1])
        nose.tools.eq_(info["name"], Util.format_repo(self.yum_repo_names[1], "x86_64"))

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

    def test_19_generate_certificate(self):
        '''generate an entitlement certificate'''
        # generate it for RH repos and the first protected custom repo
        # the label is the repo ID in the case of custom repos
        RHUIManagerCLI.client_cert(RHUA,
                                   self.yum_repo_labels + [CUSTOM_REPOS[1]],
                                   CLI_CFG[0],
                                   365,
                                   "/tmp")

    @staticmethod
    def test_20_check_cli_crt_sig():
        '''check if SHA-256 is used in the client certificate signature'''
        # for RHBZ#1628957
        sigs_expected = ["sha256", "sha256"]
        _, stdout, _ = RHUA.exec_command("openssl x509 -noout -text -in " +
                                         f"/tmp/{CLI_CFG[0]}.crt")
        cert_details = stdout.read().decode()
        sigs_actual = re.findall("sha[0-9]+", cert_details)
        nose.tools.eq_(sigs_expected, sigs_actual)

    def test_21_check_stray_custom_repo(self):
        '''check if only the wanted repos are in the certificate'''
        repo_labels_expected = [f"custom-{CUSTOM_REPOS[1]}"] + self.yum_repo_labels
        _, stdout, _ = RHUA.exec_command(f"cat /tmp/{CLI_CFG[0]}-extensions.txt")
        extensions = stdout.read().decode()
        repo_labels_actual = re.findall("|".join(["custom-.*"] + self.yum_repo_labels),
                                        extensions)
        nose.tools.eq_(sorted(repo_labels_expected), sorted(repo_labels_actual))

    @staticmethod
    def test_22_create_cli_config_rpm():
        '''create a client configuration RPM'''
        RHUIManagerCLI.client_rpm(RHUA,
                                  [f"/tmp/{CLI_CFG[0]}.key", f"/tmp/{CLI_CFG[0]}.crt"],
                                  CLI_CFG,
                                  "/tmp",
                                  [CUSTOM_REPOS[0]],
                                  "_none_")
        # check if the rpm was created
        conf_rpm = f"/tmp/{CLI_CFG[0]}-{CLI_CFG[1]}/build/RPMS/noarch/" + \
                   f"{CLI_CFG[0]}-{CLI_CFG[1]}-{CLI_CFG[2]}.noarch.rpm"
        Expect.expect_retval(RHUA, f"test -f {conf_rpm}")

    def test_23_ensure_gpgcheck_config(self):
        '''ensure that GPG checking is configured in the client configuration as expected'''
        # for RHBZ#1428756
        # we'll need the repo file in a few tests; fetch it now
        remote_repo_file = f"/tmp/{CLI_CFG[0]}-{CLI_CFG[1]}/build/BUILD/" + \
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
        nose.tools.ok_(all([yum_cfg.get(r, "proxy") == "_none_" for r in yum_cfg.sections()]))

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
        # broken in 4.0; terminate this test now
        raise nose.exc.SkipTest("Not yet implemented.")
        name = ALT_CONTENT_SRC_NAME
        RHUIManagerCLI.client_content_source(RHUA,
                                             self.yum_repo_labels,
                                             [name],
                                             "/tmp")
        # check that
        cmd = f"rpm2cpio /tmp/{name}-2.0/build/RPMS/noarch/{name}-2.0-1.noarch.rpm | " + \
              r"cpio -i --to-stdout \*.conf | " + \
              "sed -n -e '/^paths:/,$p' | " + \
              "sed s/paths://"
        _, stdout, _ = RHUA.exec_command(cmd)
        paths_actual_raw = stdout.read().decode().splitlines()
        # the paths are indented, let's get rid of the formatting
        paths_actual = [p.lstrip() for p in paths_actual_raw]
        # the OSTree repo must not be included
        paths_expected = [p for p in self.yum_repo_paths if "ostree" not in p]
        nose.tools.eq_(paths_expected, paths_actual)

    @staticmethod
    def test_27_upload_expired_cert():
        '''check expired certificate handling'''
        try:
            RHUIManagerCLI.cert_upload(RHUA, join(DATADIR, CERTS["expired"]))
        except RuntimeError as err:
            nose.tools.ok_("The provided certificate is expired or invalid" in str(err),
                           msg=f"unexpected error: {err}")

    @staticmethod
    def test_28_upload_incompat_cert():
        '''check incompatible certificate handling'''
        cert = join(DATADIR, CERTS["incompatible"])
        if Util.cert_expired(RHUA, cert):
            raise nose.exc.SkipTest("The given certificate has already expired.")
        try:
            RHUIManagerCLI.cert_upload(RHUA, cert)
        except RuntimeError as err:
            nose.tools.ok_("does not contain any entitlements" in str(err),
                           msg=f"unexpected error: {err}")

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
                             "rhui-manager repo unused > /tmp/repos.stdout 2> /tmp/repos.stderr",
                             timeout=1200)

    @staticmethod
    def test_40_check_iso_repos():
        '''check if non-RPM repos were ignored'''
        # for RHBZ#1199426
        Expect.expect_retval(RHUA,
                             "egrep 'Containers|Images|ISOs|Kickstart' /tmp/repos.stdout", 1)

    @staticmethod
    def test_41_check_pygiwarning():
        '''check if PyGIWarning was not issued'''
        # for RHBZ#1450430
        Expect.expect_retval(RHUA, "grep PyGIWarning /tmp/repos.stderr", 1)

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
        RHUIManagerCLI.cert_upload(RHUA, join(DATADIR, CERTS["Atomic"]))
        RHUIManagerCLI.repo_add(RHUA, self.product["name"])
        # wait a few seconds for the repo to actually get added
        time.sleep(4)
        repolist_actual = RHUIManagerCLI.repo_list(RHUA, True).splitlines()
        nose.tools.eq_([self.product["id"]], repolist_actual)
        # clean up
        RHUIManagerCLI.repo_delete(RHUA, self.product["id"])
        RHUIManager.remove_rh_certs(RHUA)

    @staticmethod
    def test_47_rhui_scripts():
        '''test argument handling in rhui-* scripts'''
        scripts = ["rhui-export-repos", "rhui-subscription-sync"]
        logs = ["/var/log/rhui/rhui-export-repos.log", "/var/log/rhui-subscription-sync.log"]
        bad_config = "/etc/motd"
        bad_sync_config = "/etc/ansible/ansible.cfg"
        for script, log in zip(scripts, logs):
            Expect.expect_retval(RHUA, f"{script} --config {bad_config}", 1)
            Expect.ping_pong(RHUA, f"tail -2 {log}", "(pulp_api_url|cert_dir) is not valid")
            Expect.expect_retval(RHUA, f"{script} --sync-config {bad_sync_config}", 1)
            Expect.ping_pong(RHUA, f"tail -2 {log}", "username is not valid")

    @staticmethod
    def test_48_rhui_manager_help():
        '''test help handling in rhui-manager'''
        for arg in ["-h", "--help"]:
            Expect.ping_pong(RHUA, f"rhui-manager {arg}", "Usage:.*Options:.*Commands:")
            # -h doesn't work with 1-level subcommands like --help, skip it
            if arg != "-h":
                Expect.ping_pong(RHUA, f"rhui-manager cert {arg}", "upload.*uploads.*info.*display")
            Expect.ping_pong(RHUA, f"rhui-manager cert info {arg}", "info: display")

    @staticmethod
    def test_99_cleanup():
        '''cleanup: remove temporary files'''
        Expect.ping_pong(RHUA,
                         f"rm -rf /tmp/{CLI_CFG[0]}* ; " +
                         f"ls /tmp/{CLI_CFG[0]}* 2>&1",
                         "No such file or directory")
        Expect.ping_pong(RHUA,
                         "rm -f /tmp/repos.std{out,err} ; " +
                         "ls /tmp/repos.std{out,err} 2>&1",
                         "No such file or directory")
        Expect.ping_pong(RHUA,
                         f"rm -rf /tmp/{ALT_CONTENT_SRC_NAME}* ; " +
                         f"ls /tmp/{ALT_CONTENT_SRC_NAME}* 2>&1",
                         "No such file or directory")
        rmtree(TMPDIR)

    @staticmethod
    def teardown_class():
        '''
           announce the end of the test run
        '''
        print(f"*** Finished running {basename(__file__)}. ***")
