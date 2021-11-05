'''User management tests'''

from os.path import basename
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
    RHUIManager.change_user_password(RHUA, password="new_rhui_pass")

def test_03_login_with_new_pass():
    '''
       log in with the new password
    '''
    RHUIManager.initial_run(RHUA, password="new_rhui_pass")

def test_04_reset_password():
    '''
        change the password back to the default one
    '''
    default_password = Util.get_saved_password(RHUA, CREDS_BACKUP)
    RHUIManager.change_user_password(RHUA, default_password)
    # remove the backup
    Expect.expect_retval(RHUA, "rm -f " + CREDS_BACKUP)

def test_05_login_with_wrong_pass():
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

def test_06_login_logout_tui():
    '''
        log in and then log out in the TUI
    '''
    RHUIManager.initial_run(RHUA)
    RHUIManager.logout(RHUA)
    time.sleep(2)
    nose.tools.ok_(not Util.is_logged_in(RHUA))

def test_07_login_logout_cli():
    '''
        log in and then log out on the command line
    '''
    RHUIManager.initial_run(RHUA)
    RHUIManagerCLI.logout(RHUA)
    time.sleep(2)
    nose.tools.ok_(not Util.is_logged_in(RHUA))

def teardown():
    '''
       announce the end of the test run
    '''
    print(f"*** Finished running {basename(__file__)}. ***")
