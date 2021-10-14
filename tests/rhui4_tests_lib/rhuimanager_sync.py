""" RHUIManager Sync functions """

import re
import time

import nose

from stitches.expect import Expect, CTRL_C

from rhui4_tests_lib.rhuimanager import RHUIManager
from rhui4_tests_lib.util import Util

def _get_repo_status(connection, reponame):
    '''
    display repo sync summary
    '''
    RHUIManager.screen(connection, "sync")
    Expect.enter(connection, "dr")
    result_line = Expect.match(connection,
                               re.compile(fr".*{re.escape(reponame)}\s*\r\n([^\n]*)\r\n.*",
                                          re.DOTALL), [1], 60)[0]
    connection.cli.exec_command("killall -s SIGINT rhui-manager")
    result_chunks = Util.uncolorify(result_line).split()

    Expect.enter(connection, CTRL_C)
    Expect.enter(connection, "q")
    if len(result_chunks) < 3:
        raise RuntimeError(f"Unexpected output from rhui-manager: {result_chunks}")
    return result_chunks[2]

class RHUIManagerSync():
    '''
    Represents -= Synchronization Status =- RHUI screen
    '''
    @staticmethod
    def sync_repo(connection, repolist):
        '''
        sync an individual repository immediately
        '''
        RHUIManager.screen(connection, "sync")
        Expect.enter(connection, "sr")
        Expect.expect(connection, "Select one or more repositories.*for more commands:", 60)
        Expect.enter(connection, "l")
        RHUIManager.select(connection, repolist)
        RHUIManager.proceed_with_check(connection,
                                       "The following repositories will be scheduled " +
                                       "for synchronization:",
                                       repolist)
        RHUIManager.quit(connection)

    @staticmethod
    def check_sync_started(connection, repolist):
        '''ensure that sync started'''
        for repo in repolist:
            status = "Never"
            while status in ["Never", "Unknown"]:
                time.sleep(10)
                status = _get_repo_status(connection, repo)
            if status in ["Running", "Success"]:
                pass
            else:
                raise TypeError("Something went wrong")

    @staticmethod
    def wait_till_repo_synced(connection, repolist):
        '''
        wait until repo is synced
        '''
        for repo in repolist:
            status = "Running"
            while status in ["Running", "Never", "Unknown"]:
                time.sleep(10)
                status = _get_repo_status(connection, repo)
            if status == "Error":
                raise TypeError("The repo sync returned Error")
            nose.tools.assert_equal(status, "Success")
