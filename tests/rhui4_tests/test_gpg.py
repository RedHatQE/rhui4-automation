'''Tests for working with a custom GPG key in a custom repo'''

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

from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.rhuimanager import RHUIManager
from rhui4_tests_lib.rhuimanager_client import RHUIManagerClient
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

REPO = "custom_gpg"
SIG = "94cce14f"
SIGNED_PACKAGE = "rhui-rpm-upload-trial"
UNSIGNED_PACKAGE = "rhui-rpm-upload-test"
SIGNED_PACKAGE_SIG2 = "rhui-rpm-upload-tryout"
CUSTOM_RPMS_DIR = "/tmp/extra_rhui_files"
KEY_FILENAME = "test_gpg_key"

def setup():
    '''
       announce the beginning of the test run
    '''
    print(f"*** Running {basename(__file__)}: ***")

def test_01_initial_run():
    '''
        log in to RHUI
    '''
    if not getenv("RHUISKIPSETUP"):
        RHUIManager.initial_run(RHUA)

def test_02_add_cds():
    '''
        add a CDS
    '''
    if not getenv("RHUISKIPSETUP"):
        RHUIManagerInstance.add_instance(RHUA, "cds")

def test_03_add_hap():
    '''
        add an HAProxy Load-balancer
    '''
    if not getenv("RHUISKIPSETUP"):
        RHUIManagerInstance.add_instance(RHUA, "loadbalancers")

def test_04_create_custom_repo():
    '''
        add a custom repo using a custom GPG key
    '''
    RHUIManagerRepo.add_custom_repo(RHUA,
                                    REPO,
                                    redhat_gpg="n",
                                    custom_gpg=join(CUSTOM_RPMS_DIR, KEY_FILENAME))

def test_05_upload_to_custom_repo():
    '''
        upload an unsigned and two differently signed packages to the custom repo
    '''
    avail_rpm_names = [pkg.rsplit('-', 2)[0] for pkg in Util.get_rpms_in_dir(RHUA,
                                                                             CUSTOM_RPMS_DIR)]
    nose.tools.eq_(avail_rpm_names, sorted([SIGNED_PACKAGE, UNSIGNED_PACKAGE, SIGNED_PACKAGE_SIG2]),
                   msg=f"Failed to find the packages to upload. Got: {avail_rpm_names}.")
    RHUIManagerRepo.upload_content(RHUA, [REPO], CUSTOM_RPMS_DIR)

def test_06_display_detailed_info():
    '''
        check detailed information on the repo
    '''
    info = RHUIManagerRepo.check_detailed_information(RHUA, REPO)
    nose.tools.eq_(info["name"], REPO)
    nose.tools.eq_(info["type"], "Custom / Yum")
    nose.tools.eq_(info["gpgcheck"], "Yes")
    nose.tools.eq_(info["customgpgkeys"], KEY_FILENAME)

def test_07_generate_ent_cert():
    '''
        generate an entitlement certificate
    '''
    RHUIManagerClient.generate_ent_cert(RHUA, [REPO], REPO, "/tmp")

def test_08_create_cli_rpm():
    '''
        create a client configuration RPM
    '''
    RHUIManagerClient.create_conf_rpm(RHUA,
                                      "/tmp",
                                      f"/tmp/{REPO}.crt",
                                      f"/tmp/{REPO}.key",
                                      REPO)

def test_09_install_conf_rpm():
    '''
       install the client configuration RPM
    '''
    # get rid of undesired repos first
    Util.remove_amazon_rhui_conf_rpm(CLI)
    Util.disable_beta_repos(CLI)
    Util.install_pkg_from_rhua(RHUA,
                               CLI,
                               f"/tmp/{REPO}-2.0/build/RPMS/noarch/{REPO}-2.0-1.noarch.rpm")

def test_10_install_signed_pkg():
    '''
       install the signed package from the custom repo (will import the GPG key)
    '''
    Yummy.install(CLI, [SIGNED_PACKAGE])

def test_11_check_gpg_sig():
    '''
       check the signature in the installed package
    '''
    Expect.expect_retval(CLI, f"rpm -qi {SIGNED_PACKAGE} | grep ^Signature.*{SIG}$")

def test_12_check_gpg_pubkey():
    '''
       check if the public GPG key was imported
    '''
    Expect.expect_retval(CLI, "rpm -q gpg-pubkey-" + SIG)

def test_13_install_unsigned_pkg():
    '''
       try installing the unsigned package, should not work
    '''
    Expect.ping_pong(CLI,
                     "yum -y install " + UNSIGNED_PACKAGE,
                     f"Package {UNSIGNED_PACKAGE}.* is not signed")
    Expect.expect_retval(CLI, "rpm -q " + UNSIGNED_PACKAGE, 1)

def test_14_install_2nd_signed_pkg():
    '''
       try installing the package signed with the key unknown to the client, should not work
    '''
    output = f"The GPG keys.*{REPO}.*are not correct for this package"
    Expect.ping_pong(CLI,
                     "yum -y install " + SIGNED_PACKAGE_SIG2,
                     output)
    Expect.expect_retval(CLI, "rpm -q " + SIGNED_PACKAGE_SIG2, 1)

def test_99_cleanup():
    '''
       clean up
    '''
    Util.remove_rpm(CLI, [SIGNED_PACKAGE, "gpg-pubkey-" + SIG, REPO])
    rhel = Util.get_rhel_version(CLI)["major"]
    if rhel <= 7:
        cache = f"/var/cache/yum/x86_64/{rhel}Server/rhui-custom-{REPO}/"
    else:
        cache = f"/var/cache/dnf/rhui-custom-{REPO}*/"
    Expect.expect_retval(CLI, "rm -rf " + cache)
    RHUIManagerRepo.delete_all_repos(RHUA)
    Expect.expect_retval(RHUA, f"rm -rf /tmp/{REPO}*")
    if not getenv("RHUISKIPSETUP"):
        RHUIManagerInstance.delete_all(RHUA, "loadbalancers")
        RHUIManagerInstance.delete_all(RHUA, "cds")

def teardown():
    '''
       announce the end of the test run
    '''
    print(f"*** Finished running {basename(__file__)}. ***")
