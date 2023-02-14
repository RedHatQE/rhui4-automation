'''CDS management tests'''

from os.path import basename
import random
import re
import time

import logging
import nose
from stitches.expect import Expect

from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.helpers import Helpers
from rhui4_tests_lib.rhuimanager import RHUIManager
from rhui4_tests_lib.rhuimanager_instance import RHUIManagerInstance, NoSuchInstance

logging.basicConfig(level=logging.DEBUG)

CDS_HOSTNAMES = ConMgr.get_cds_hostnames()

RHUA = ConMgr.connect()
CDS = [ConMgr.connect(host) for host in CDS_HOSTNAMES]

def setup():
    '''
       announce the beginning of the test run
    '''
    print(f"*** Running {basename(__file__)}: ***")

def test_01_initial_run():
    '''
        log in to RHUI
    '''
    RHUIManager.initial_run(RHUA)

def test_02_list_empty_cds():
    '''
        check if there are no CDSs
    '''
    cds_list = RHUIManagerInstance.list(RHUA, "cds")
    nose.tools.assert_equal(cds_list, [])

def test_03_add_cds():
    '''
        add all known CDSs
    '''
    for cds in CDS_HOSTNAMES:
        RHUIManagerInstance.add_instance(RHUA, "cds", cds)

def test_04_list_cds():
    '''
        list CDSs, expect as many as there are in /etc/hosts
    '''
    cds_list = RHUIManagerInstance.list(RHUA, "cds")
    nose.tools.assert_equal(len(cds_list), len(CDS_HOSTNAMES))

def test_05_readd_cds():
    '''
        add one of the CDSs again (reapply the configuration)
    '''
    # choose a random CDS hostname from the list
    RHUIManagerInstance.add_instance(RHUA, "cds", random.choice(CDS_HOSTNAMES), update=True)

def test_06_list_cds():
    '''
        check if the CDSs are still tracked
    '''
    cds_list = RHUIManagerInstance.list(RHUA, "cds")
    nose.tools.assert_equal(len(cds_list), len(CDS_HOSTNAMES))

def test_07_delete_nonexisting_cds():
    '''
        try deleting an untracked CDS, should be rejected (by rhui4_tests_lib)
    '''
    nose.tools.assert_raises(NoSuchInstance,
                             RHUIManagerInstance.delete,
                             RHUA,
                             "cds",
                             [CDS_HOSTNAMES[0].replace("cds", "cdsfoo")])

def test_08_delete_cds():
    '''
        delete all CDSs
    '''
    RHUIManagerInstance.delete_all(RHUA, "cds")

def test_09_list_cds():
    '''
        list CDSs, expect none
    '''
    cds_list = RHUIManagerInstance.list(RHUA, "cds")
    nose.tools.assert_equal(cds_list, [])

def test_10_check_cleanup():
    '''
        check if nginx was stopped and the remote file system unmounted on all CDSs
    '''
    service = "nginx"
    mdir = "/var/lib/rhui/remote_share"
    dirty_hosts = {}
    errors = []

    dirty_hosts["nginx"] = [cds.hostname for cds in CDS if Helpers.check_service(cds, service)]
    dirty_hosts["mount"] = [cds.hostname for cds in CDS if Helpers.check_mountpoint(cds, mdir)]

    if dirty_hosts["nginx"]:
        errors.append("nginx is still running on {dirty_hosts['nginx']}")
    if dirty_hosts["mount"]:
        errors.append("The remote file system is still mounted on {dirty_hosts['mount']}")

    nose.tools.ok_(not errors, msg=errors)

def test_11_add_cds_uppercase():
    '''
        add (and delete) a CDS with uppercase characters
    '''
    # for RHBZ#1572623
    # choose a random CDS hostname from the list
    cds_up = random.choice(CDS_HOSTNAMES).replace("cds", "CDS")
    RHUIManagerInstance.add_instance(RHUA, "cds", cds_up)
    cds_list = RHUIManagerInstance.list(RHUA, "cds")
    nose.tools.assert_equal(len(cds_list), 1)
    RHUIManagerInstance.delete(RHUA, "cds", [cds_up])
    cds_list = RHUIManagerInstance.list(RHUA, "cds")
    nose.tools.assert_equal(len(cds_list), 0)

def test_12_delete_unreachable():
    '''
    add a CDS, make it unreachable, and see if it can still be deleted from the RHUA
    '''
    # for RHBZ#1639996
    # choose a random CDS hostname from the list
    cds = random.choice(CDS_HOSTNAMES)
    RHUIManagerInstance.add_instance(RHUA, "cds", cds)
    cds_list = RHUIManagerInstance.list(RHUA, "cds")
    nose.tools.assert_not_equal(cds_list, [])

    Helpers.break_hostname(RHUA, cds)

    # delete it
    RHUIManagerInstance.delete(RHUA, "cds", [cds])
    # check it
    cds_list = RHUIManagerInstance.list(RHUA, "cds")
    nose.tools.assert_equal(cds_list, [])

    Helpers.unbreak_hostname(RHUA)

    # the node remains configured (RHUI mount point, nginx)... unconfigure it properly
    RHUIManagerInstance.add_instance(RHUA, "cds", cds)
    RHUIManagerInstance.delete(RHUA, "cds", [cds])

def test_13_delete_select_0():
    '''
    add a CDS and see if no issue occurs if it and "a zeroth" (ghost) CDSs are selected for deletion
    '''
    # for RHBZ#1305612
    # choose a random CDS and add it
    cds = random.choice(CDS_HOSTNAMES)
    RHUIManagerInstance.add_instance(RHUA, "cds", cds)
    cds_list = RHUIManagerInstance.list(RHUA, "cds")
    nose.tools.assert_not_equal(cds_list, [])

    # try the deletion
    RHUIManager.screen(RHUA, "cds")
    Expect.enter(RHUA, "d")
    Expect.expect(RHUA, "Enter value")
    Expect.enter(RHUA, "0")
    Expect.expect(RHUA, "Enter value")
    Expect.enter(RHUA, "1")
    Expect.expect(RHUA, "Enter value")
    Expect.enter(RHUA, "c")
    state = Expect.expect_list(RHUA,
                               [(re.compile(".*Are you sure.*", re.DOTALL), 1),
                                (re.compile(".*An unexpected error.*", re.DOTALL), 2)])
    if state == 1:
        Expect.enter(RHUA, "y")
        RHUIManager.quit(RHUA, timeout=180)
    else:
        Expect.enter(RHUA, "q")

    # the CDS list ought to be empty now; if not, delete the CDS and fail
    cds_list = RHUIManagerInstance.list(RHUA, "cds")
    if cds_list:
        RHUIManagerInstance.delete_all(RHUA, "cds")
        raise AssertionError("The CDS list is not empty after the deletion attempt: {cds_list}")

def test_14_autoheal():
    '''
    terminate gunicorn processes and expect them to be respawned automatically
    '''
    # add the first CDS
    cds = CDS_HOSTNAMES[0]
    RHUIManagerInstance.add_instance(RHUA, "cds", cds)

    # get the PIDs of gunicorn processes
    _, stdout, _ = CDS[0].exec_command("pidof -x gunicorn")
    old_pids = sorted(list(map(int, stdout.read().decode().split())))

    # make sure there actually are some PIDs
    nose.tools.assert_true(old_pids)

    # kill them all
    Expect.expect_retval(CDS[0], "killall gunicorn")

    # check if there are no gunicorn processed now
    _, stdout, _ = CDS[0].exec_command("pidof -x gunicorn")
    nose.tools.assert_false(stdout.read().decode())

    # wait a bit and get new PIDs
    time.sleep(7)
    _, stdout, _ = CDS[0].exec_command("pidof -x gunicorn")
    new_pids = sorted(list(map(int, stdout.read().decode().split())))

    # delete the CDS to clean up
    RHUIManagerInstance.delete(RHUA, "cds", [cds])

    # check if they were all started again
    nose.tools.assert_equal(len(old_pids), len(new_pids))
    for i, _ in enumerate(old_pids):
        nose.tools.assert_not_equal(old_pids[i], new_pids[i])

def test_15_check_ansible_warnings():
    '''
    check whether instance management did not trigger any Ansible warnings
    '''
    Expect.expect_retval(RHUA, "grep -i warning /var/log/rhui/rhua_ansible.log", 1)

def teardown():
    '''
       announce the end of the test run
    '''
    print(f"*** Finished running {basename(__file__)}. ***")
