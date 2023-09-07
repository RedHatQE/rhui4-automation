'''User management tests'''

import itertools
from os.path import basename
import shlex
import time

import logging
import nose
from stitches.expect import Expect

from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.rhuimanager import RHUIManager
from rhui4_tests_lib.rhuimanager_cmdline import RHUIManagerCLI
from rhui4_tests_lib.util import Util

logging.basicConfig(level=logging.DEBUG)

CREDS_BACKUP = "/root/rhui-subscription-sync.conf"
TEST_COMMAND = "cert info"
TEST_PASSWORD = "--aw!100%safe $ex, drums&rock'n'roll"
RHUA = ConMgr.connect()

def setup():
    '''
       announce the beginning of the test run
    '''
    print(f"*** Running {basename(__file__)}: ***")

def test_01_initial_run():
    '''
        log in the RHUI (if not logged in, try the saved admin password)
    '''
    RHUIManager.initial_run(RHUA)

def test_02_change_password():
    '''
        change the password (will log the user out automatically)
    '''
    # back up the credentials file first
    Expect.expect_retval(RHUA, "cp -a /etc/rhui/rhui-subscription-sync.conf " + CREDS_BACKUP)
    RHUIManager.change_user_password(RHUA, TEST_PASSWORD)

def test_03_login_with_new_pass():
    '''
       log in with the new password
    '''
    RHUIManager.initial_run(RHUA, password=TEST_PASSWORD)

def test_04_rerun_installer():
    '''
        rerun the RHUI installer while the new password is set
    '''
    Expect.expect_retval(RHUA, "rhui-installer --rerun", timeout=600)

def test_05_reset_password():
    '''
        change the password back to the default one
    '''
    default_password = Util.get_saved_password(RHUA, CREDS_BACKUP)
    RHUIManager.change_user_password(RHUA, default_password)
    # remove the backup
    Expect.expect_retval(RHUA, "rm -f " + CREDS_BACKUP)

def test_06_login_with_wrong_pass():
    '''
        try logging in with the wrong password, should fail gracefully
    '''
    # for RHBZ#1282522
    Expect.enter(RHUA, "rhui-manager")
    Expect.expect(RHUA, ".*RHUI Username:.*")
    Expect.enter(RHUA, "admin")
    Expect.expect(RHUA, "RHUI Password:")
    Expect.enter(RHUA, "wrong_pass")
    Expect.expect(RHUA,
                  ".*Invalid login, please check the authentication credentials and try again.")

def test_07_login_logout_cli():
    '''
        log in and then log out on the command line
    '''
    RHUIManager.initial_run(RHUA)
    RHUIManagerCLI.logout(RHUA)
    time.sleep(2)
    nose.tools.ok_(not Util.is_logged_in(RHUA))

def test_08_login_logout_tui():
    '''
        log in and then log out in the TUI
    '''
    RHUIManager.initial_run(RHUA)
    RHUIManager.logout(RHUA)
    time.sleep(2)
    nose.tools.ok_(not Util.is_logged_in(RHUA))

def test_09_auto_load_password():
    '''
        check if rhui-manager automatically loads credentials in non-interactive mode
    '''
    nose.tools.ok_(not Util.is_logged_in(RHUA))
    Expect.ping_pong(RHUA,
                     f"rhui-manager --noninteractive {TEST_COMMAND}",
                     "Red Hat Entitlements",
                     timeout=5)

def test_10_username_password_options():
    '''
       supply good and bad credentials on the command line, expect corresponding exit codes
    '''
    usernames = ["admin", "baduser"]
    passwords = [shlex.quote(Util.get_saved_password(RHUA)), "badpassword"]
    username_options = ["-u", "--username"]
    password_options = ["-p", "--password"]
    for user, passwd in itertools.product(usernames, passwords):
        for u_opt, p_opt in itertools.product(username_options, password_options):
            Expect.expect_retval(RHUA,
                                 f"rhui-manager {u_opt} {user} {p_opt} {passwd} {TEST_COMMAND}",
                                 0 if user == usernames[0] and passwd == passwords[0] else 1)

def teardown():
    '''
       announce the end of the test run
    '''
    print(f"*** Finished running {basename(__file__)}. ***")
