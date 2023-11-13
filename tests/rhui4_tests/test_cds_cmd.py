'''CDS management tests for the CLI'''

from os.path import basename
import random

import logging
import nose
from stitches.expect import Expect

from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.helpers import Helpers, RHUI_CFG
from rhui4_tests_lib.rhuimanager_cmdline_instance import RHUIManagerCLIInstance
from rhui4_tests_lib.rhuimanager import RHUIManager

logging.basicConfig(level=logging.DEBUG)

CDS_HOSTNAMES = ConMgr.get_cds_hostnames()

RHUA = ConMgr.connect()
CDS = [ConMgr.connect(host) for host in CDS_HOSTNAMES]

def setup():
    '''
    announce the beginning of the test run
    '''
    print(f"*** Running {basename(__file__)}: ***")

def test_01_init():
    '''
    log in to RHUI
    '''
    RHUIManager.initial_run(RHUA)

def test_02_list_cds():
    '''
    check if there are no CDSs
    '''
    cds_list = RHUIManagerCLIInstance.list(RHUA, "cds")
    nose.tools.eq_(cds_list, [])

def test_03_add_safe_unknown_key():
    '''
    try adding a CDS whose SSH key is unknown, without using --unsafe; should fail
    '''
    # for RHBZ#1409460
    # choose a random CDS hostname from the list
    cds = random.choice(CDS_HOSTNAMES)
    # make sure its key is unknown
    ConMgr.remove_ssh_keys(RHUA)
    # try adding the CDS
    status = RHUIManagerCLIInstance.add(RHUA, "cds", cds)
    nose.tools.ok_(not status, msg=f"unexpected {cds} addition status: {status}")
    cds_list = RHUIManagerCLIInstance.list(RHUA, "cds")
    nose.tools.eq_(cds_list, [])

def test_04_add_safe_known_key():
    '''
    add and delete a CDS whose SSH key is known, without using --unsafe; should work
    '''
    # for RHBZ#1409460
    # choose a random CDS hostname from the list
    cds = random.choice(CDS_HOSTNAMES)
    # accept the host's SSH key
    ConMgr.add_ssh_keys(RHUA, [cds])
    # actually add and delete the host
    status = RHUIManagerCLIInstance.add(RHUA, "cds", cds)
    nose.tools.ok_(status, msg=f"unexpected {cds} addition status: {status}")
    cds_list = RHUIManagerCLIInstance.list(RHUA, "cds")
    nose.tools.eq_(cds_list, [cds])
    status = RHUIManagerCLIInstance.delete(RHUA, "cds", [cds], force=True)
    nose.tools.ok_(status, msg=f"unexpected {cds} deletion status: {status}")
    # clean up the SSH key
    ConMgr.remove_ssh_keys(RHUA)

def test_05_add_cds():
    '''
    add all CDSs, with unknown SSH keys, with --unsafe
    '''
    for cds in CDS_HOSTNAMES:
        status = RHUIManagerCLIInstance.add(RHUA, "cds", cds, unsafe=True)
        nose.tools.ok_(status, msg=f"unexpected {cds} installation status: {status}")
    cds_list = RHUIManagerCLIInstance.list(RHUA, "cds")
    nose.tools.eq_(cds_list, CDS_HOSTNAMES)

def test_06_reinstall_cds():
    '''
    add one of the CDSs again by reinstalling it
    '''
    # choose a random CDS hostname from the list
    cds = random.choice(CDS_HOSTNAMES)
    status = RHUIManagerCLIInstance.reinstall(RHUA, "cds", cds)
    nose.tools.ok_(status, msg=f"unexpected {cds} reinstallation status: {status}")
    cds_list = RHUIManagerCLIInstance.list(RHUA, "cds")
    # the reinstalled CDS is now the last one in the list; the list may not be the same, sort it!
    cds_list.sort()
    nose.tools.eq_(cds_list, CDS_HOSTNAMES)

def test_07_reinstall_all():
    '''
    check the ability to reinstall all CDSes using a generic command
    '''
    # first, modify the RHUI configuration file on all CDSes
    for cds_conn in CDS:
        Helpers.edit_rhui_tools_conf(cds_conn, "unprotected_repo_prefix", "huh")
    # run the reinstallation
    status = RHUIManagerCLIInstance.reinstall(RHUA, "cds", all_nodes=True)
    nose.tools.ok_(status, msg=f"unexpected 'all CDS' reinstallation status: {status}")
    # check if the RHUI configuration file was reset after the reinstallation
    # meaning, the backup copy made while modifying the configuration matches the main file
    verification_cmd = f"diff -u {RHUI_CFG} {RHUI_CFG}.bak"
    for cds_conn in CDS:
        Expect.expect_retval(cds_conn, verification_cmd)

def test_08_readd_cds_noforce():
    '''
    check if rhui refuses to add a CDS again if no extra parameter is used
    '''
    # again choose a random CDS hostname from the list
    cds = random.choice(CDS_HOSTNAMES)
    status = RHUIManagerCLIInstance.add(RHUA, "cds", cds, unsafe=True)
    nose.tools.ok_(not status, msg=f"unexpected {cds} readdition status: {status}")

def test_09_list_cds():
    '''
    check if nothing extra has been added
    '''
    cds_list = RHUIManagerCLIInstance.list(RHUA, "cds")
    # the readded CDS is now the last one in the list; the list may not be the same, sort it!
    cds_list.sort()
    nose.tools.eq_(cds_list, CDS_HOSTNAMES)

def test_10_readd_cds():
    '''
    add one of the CDSs again by using force
    '''
    # again choose a random CDS hostname from the list
    cds = random.choice(CDS_HOSTNAMES)
    status = RHUIManagerCLIInstance.add(RHUA, "cds", cds, force=True, unsafe=True)
    nose.tools.ok_(status, msg=f"unexpected {cds} readdition status: {status}")

def test_11_list_cds():
    '''
    check if the CDSs are still tracked, and nothing extra has appeared
    '''
    cds_list = RHUIManagerCLIInstance.list(RHUA, "cds")
    # the readded CDS is now the last one in the list; the list may not be the same, sort it!
    cds_list.sort()
    nose.tools.eq_(cds_list, CDS_HOSTNAMES)

def test_12_delete_cds_noforce():
    '''
    check if rhui refuses to delete the node when it's the only/last one and force isn't used
    '''
    # delete all but the first node (if there are more nodes to begin with)
    if len(CDS_HOSTNAMES) > 1:
        RHUIManagerCLIInstance.delete(RHUA, "cds", CDS_HOSTNAMES[1:])
    status = RHUIManagerCLIInstance.delete(RHUA, "cds", [CDS_HOSTNAMES[0]])
    nose.tools.ok_(not status, msg=f"unexpected deletion status: {status}")

def test_13_list_cds():
    '''
    check if the last CDS really hasn't been deleted
    '''
    cds_list = RHUIManagerCLIInstance.list(RHUA, "cds")
    nose.tools.eq_(cds_list, [CDS_HOSTNAMES[0]])


def test_14_delete_cds_force():
    '''
    delete the last CDS forcibly
    '''
    status = RHUIManagerCLIInstance.delete(RHUA, "cds", [CDS_HOSTNAMES[0]], force=True)
    nose.tools.ok_(status, msg=f"unexpected deletion status: {status}")

def test_15_list_cds():
    '''
    check if the last CDS has been deleted
    '''
    cds_list = RHUIManagerCLIInstance.list(RHUA, "cds")
    nose.tools.eq_(cds_list, [])

def test_16_add_bad_cds():
    '''
    try adding an incorrect CDS hostname, expect trouble and nothing added
    '''
    status = RHUIManagerCLIInstance.add(RHUA, "cds", "foo" + CDS_HOSTNAMES[0])
    nose.tools.ok_(not status, msg=f"unexpected addition status: {status}")
    cds_list = RHUIManagerCLIInstance.list(RHUA, "cds")
    nose.tools.eq_(cds_list, [])

def test_17_delete_bad_cds():
    '''
    try deleting a non-existing CDS hostname, expect trouble
    '''
    # for RHBZ#1409697
    # first try a case where only an unknown (ie. no known) hostname is used on the command line
    status = RHUIManagerCLIInstance.delete(RHUA, "cds", ["bar" + CDS_HOSTNAMES[0]], force=True)
    nose.tools.ok_(not status, msg=f"unexpected deletion status: {status}")

    # and now a combination of a known and an unknown hostname
    # the known hostname should be deleted, the unknown skipped, exit code 1
    # so, add a node first
    cds = random.choice(CDS_HOSTNAMES)
    RHUIManagerCLIInstance.add(RHUA, "cds", cds, unsafe=True)
    cds_list = RHUIManagerCLIInstance.list(RHUA, "cds")
    nose.tools.eq_(cds_list, [cds])
    # deleting now
    status = RHUIManagerCLIInstance.delete(RHUA, "cds", ["baz" + cds, cds], force=True)
    nose.tools.ok_(not status, msg=f"unexpected {cds} deletion status: {status}")
    # check if the valid hostname was deleted and nothing remained
    cds_list = RHUIManagerCLIInstance.list(RHUA, "cds")
    nose.tools.eq_(cds_list, [])

def test_18_add_cds_changed_case():
    '''
    add and delete a CDS with uppercase characters, should work
    '''
    # for RHBZ#1572623
    # choose a random CDS hostname from the list
    cds_up = random.choice(CDS_HOSTNAMES).replace("cds", "CDS")
    status = RHUIManagerCLIInstance.add(RHUA, "cds", cds_up, unsafe=True)
    nose.tools.ok_(status, msg=f"unexpected {cds_up} addition status: {status}")
    cds_list = RHUIManagerCLIInstance.list(RHUA, "cds")
    nose.tools.eq_(cds_list, [cds_up])
    status = RHUIManagerCLIInstance.delete(RHUA, "cds", [cds_up], force=True)
    nose.tools.ok_(status, msg=f"unexpected {cds_up} deletion status: {status}")

def test_19_delete_unreachable():
    '''
    add a CDS, make it unreachable, and see if it can still be deleted from the RHUA
    '''
    # for RHBZ#1639996
    # choose a random CDS hostname from the list
    cds = random.choice(CDS_HOSTNAMES)
    status = RHUIManagerCLIInstance.add(RHUA, "cds", cds, unsafe=True)
    nose.tools.ok_(status, msg=f"unexpected installation status: {status}")
    cds_list = RHUIManagerCLIInstance.list(RHUA, "cds")
    nose.tools.eq_(cds_list, [cds])

    Helpers.break_hostname(RHUA, cds)

    # delete it
    status = RHUIManagerCLIInstance.delete(RHUA, "cds", [cds], force=True)
    nose.tools.ok_(status, msg=f"unexpected deletion status: {status}")
    # check it
    cds_list = RHUIManagerCLIInstance.list(RHUA, "cds")
    nose.tools.eq_(cds_list, [])

    Helpers.unbreak_hostname(RHUA)

    # the node remains configured (RHUI mount point, nginx)... unconfigure it properly
    # do so by adding and deleting it again
    RHUIManagerCLIInstance.add(RHUA, "cds", cds, unsafe=True)
    RHUIManagerCLIInstance.delete(RHUA, "cds", [cds], force=True)

def test_20_check_cleanup():
    '''
    check if nginx was stopped and the remote file system unmounted on all CDSs
    '''
    # for RHBZ#1640002
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

def teardown():
    '''
    announce the end of the test run
    '''
    # also clean up SSH keys left by rhui
    ConMgr.remove_ssh_keys(RHUA)
    print(f"*** Finished running {basename(__file__)}. ***")
