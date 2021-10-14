'''HAProxy management tests for the CLI'''

from os.path import basename

import logging
import nose

from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.helpers import Helpers
from rhui4_tests_lib.rhuimanager_cmdline_instance import RHUIManagerCLIInstance
from rhui4_tests_lib.rhuimanager import RHUIManager

logging.basicConfig(level=logging.DEBUG)

HA_HOSTNAME = ConMgr.get_cds_lb_hostname()

RHUA = ConMgr.connect()
HAPROXY = ConMgr.connect(HA_HOSTNAME)

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

def test_02_list_hap():
    '''
    check if there are no HAProxy Load-balancers
    '''
    hap_list = RHUIManagerCLIInstance.list(RHUA, "haproxy")
    nose.tools.eq_(hap_list, [])

def test_03_add_hap():
    '''
    add an HAProxy Load-balancer
    '''
    status = RHUIManagerCLIInstance.add(RHUA, "haproxy", HA_HOSTNAME, unsafe=True)
    nose.tools.ok_(status, msg=f"unexpected installation status: {status}")

def test_04_list_hap():
    '''
    check if the HAProxy Load-balancer has been added
    '''
    hap_list = RHUIManagerCLIInstance.list(RHUA, "haproxy")
    nose.tools.eq_(hap_list, [HA_HOSTNAME])

def test_05_reinstall_hap():
    '''
    add the HAProxy Load-balancer again by reinstalling it
    '''
    status = RHUIManagerCLIInstance.reinstall(RHUA, "haproxy", HA_HOSTNAME)
    nose.tools.ok_(status, msg=f"unexpected reinstallation status: {status}")

def test_06_list_hap():
    '''
    check if the HAProxy Load-balancer is still tracked, and only once
    '''
    hap_list = RHUIManagerCLIInstance.list(RHUA, "haproxy")
    nose.tools.eq_(hap_list, [HA_HOSTNAME])

def test_07_readd_hap_noforce():
    '''
    check if rhui refuses to add the HAProxy Load-balancer again if no extra parameter is used
    '''
    status = RHUIManagerCLIInstance.add(RHUA, "haproxy", HA_HOSTNAME, unsafe=True)
    nose.tools.ok_(not status, msg=f"unexpected readdition status: {status}")

def test_08_list_hap():
    '''
    check if nothing extra has been added
    '''
    hap_list = RHUIManagerCLIInstance.list(RHUA, "haproxy")
    nose.tools.eq_(hap_list, [HA_HOSTNAME])

def test_09_readd_hap():
    '''
    add the HAProxy Load-balancer again by using force
    '''
    status = RHUIManagerCLIInstance.add(RHUA, "haproxy", HA_HOSTNAME, force=True, unsafe=True)
    nose.tools.ok_(status, msg=f"unexpected readdition status: {status}")

def test_10_list_hap():
    '''
    check if the HAProxy Load-balancer is still tracked, and only once
    '''
    hap_list = RHUIManagerCLIInstance.list(RHUA, "haproxy")
    nose.tools.eq_(hap_list, [HA_HOSTNAME])

def test_11_delete_hap_noforce():
    '''
    check if rhui refuses to delete the node when it's the only/last one and force isn't used
    '''
    status = RHUIManagerCLIInstance.delete(RHUA, "haproxy", [HA_HOSTNAME])
    nose.tools.ok_(not status, msg=f"unexpected deletion status: {status}")

def test_12_list_hap():
    '''
    check if the HAProxy Load-balancer really hasn't been deleted
    '''
    hap_list = RHUIManagerCLIInstance.list(RHUA, "haproxy")
    nose.tools.eq_(hap_list, [HA_HOSTNAME])

def test_13_delete_hap_force():
    '''
    delete the HAProxy Load-balancer forcibly
    '''
    status = RHUIManagerCLIInstance.delete(RHUA, "haproxy", [HA_HOSTNAME], force=True)
    nose.tools.ok_(status, msg=f"unexpected deletion status: {status}")

def test_14_list_hap():
    '''
    check if the HAProxy Load-balancer has been deleted
    '''
    hap_list = RHUIManagerCLIInstance.list(RHUA, "haproxy")
    nose.tools.eq_(hap_list, [])

def test_15_add_bad_hap():
    '''
    try adding an incorrect HAProxy hostname, expect trouble and nothing added
    '''
    status = RHUIManagerCLIInstance.add(RHUA, "haproxy", "foo" + HA_HOSTNAME)
    nose.tools.ok_(not status, msg=f"unexpected addition status: {status}")
    hap_list = RHUIManagerCLIInstance.list(RHUA, "haproxy")
    nose.tools.eq_(hap_list, [])

def test_16_delete_bad_hap():
    '''
    try deleting a non-existing HAProxy hostname, expect trouble
    '''
    # for RHBZ#1409697
    # first try a case where only an unknown (none known) hostname is used
    status = RHUIManagerCLIInstance.delete(RHUA, "haproxy", ["bar" + HA_HOSTNAME], force=True)
    nose.tools.ok_(not status, msg=f"unexpected deletion status: {status}")

    # and now a combination of a known and an unknown hostname,
    # the known hostname should be delete, the unknown skipped, exit code 1
    # so, add a node first
    RHUIManagerCLIInstance.add(RHUA, "haproxy", HA_HOSTNAME, unsafe=True)
    hap_list = RHUIManagerCLIInstance.list(RHUA, "haproxy")
    nose.tools.eq_(hap_list, [HA_HOSTNAME])
    # deleting now
    hostnames = ["baz" + HA_HOSTNAME, HA_HOSTNAME]
    status = RHUIManagerCLIInstance.delete(RHUA, "haproxy", hostnames, force=True)
    nose.tools.ok_(not status, msg=f"unexpected deletion status: {status}")
    # check if the valid hostname was deleted and nothing remained
    hap_list = RHUIManagerCLIInstance.list(RHUA, "haproxy")
    nose.tools.eq_(hap_list, [])

def test_17_add_hap_changed_case():
    '''
    add and delete an HAProxy Load-balancer with uppercase characters, should work
    '''
    # for RHBZ#1572623
    hap_up = HA_HOSTNAME.replace("hap", "HAP")
    status = RHUIManagerCLIInstance.add(RHUA, "haproxy", hap_up, unsafe=True)
    nose.tools.ok_(status, msg=f"unexpected addition status: {status}")
    hap_list = RHUIManagerCLIInstance.list(RHUA, "haproxy")
    nose.tools.eq_(hap_list, [hap_up])
    status = RHUIManagerCLIInstance.delete(RHUA, "haproxy", [hap_up], force=True)
    nose.tools.ok_(status, msg=f"unexpected deletion status: {status}")

def test_18_add_safe_unknown_key():
    '''
    try adding the Load-balancer when its SSH key is unknown, without using --unsafe; should fail
    '''
    # for RHBZ#1409460
    # make sure its key is unknown
    ConMgr.remove_ssh_keys(RHUA, [HA_HOSTNAME])
    # try adding the Load-balancer
    status = RHUIManagerCLIInstance.add(RHUA, "haproxy", HA_HOSTNAME)
    nose.tools.ok_(not status, msg=f"unexpected addition status: {status}")
    hap_list = RHUIManagerCLIInstance.list(RHUA, "haproxy")
    nose.tools.eq_(hap_list, [])

def test_19_add_safe_known_key():
    '''
    add and delete the Load-balancer when its SSH key is known, without using --unsafe; should work
    '''
    # for RHBZ#1409460
    # accept the host's SSH key
    ConMgr.add_ssh_keys(RHUA, [HA_HOSTNAME])
    # actually add and delete the host
    status = RHUIManagerCLIInstance.add(RHUA, "haproxy", HA_HOSTNAME)
    nose.tools.ok_(status, msg=f"unexpected addition status: {status}")
    hap_list = RHUIManagerCLIInstance.list(RHUA, "haproxy")
    nose.tools.eq_(hap_list, [HA_HOSTNAME])
    status = RHUIManagerCLIInstance.delete(RHUA, "haproxy", [HA_HOSTNAME], force=True)
    nose.tools.ok_(status, msg=f"unexpected deletion status: {status}")
    # clean up the SSH key
    ConMgr.remove_ssh_keys(RHUA, [HA_HOSTNAME])

def test_20_delete_unreachable():
    '''
    add a Load-balancer, make it unreachable, and see if it can still be deleted from the RHUA
    '''
    # for RHBZ#1639996
    status = RHUIManagerCLIInstance.add(RHUA, "haproxy", HA_HOSTNAME, unsafe=True)
    nose.tools.ok_(status, msg=f"unexpected installation status: {status}")
    hap_list = RHUIManagerCLIInstance.list(RHUA, "haproxy")
    nose.tools.eq_(hap_list, [HA_HOSTNAME])

    Helpers.break_hostname(RHUA, HA_HOSTNAME)

    # delete it
    status = RHUIManagerCLIInstance.delete(RHUA, "haproxy", [HA_HOSTNAME], force=True)
    nose.tools.ok_(status, msg=f"unexpected deletion status: {status}")
    # check it
    hap_list = RHUIManagerCLIInstance.list(RHUA, "haproxy")
    nose.tools.eq_(hap_list, [])

    Helpers.unbreak_hostname(RHUA)

    # the node remains configured (haproxy)... unconfigure it properly
    # do so by adding and deleting it again
    RHUIManagerCLIInstance.add(RHUA, "haproxy", HA_HOSTNAME, unsafe=True)
    RHUIManagerCLIInstance.delete(RHUA, "haproxy", [HA_HOSTNAME], force=True)

    # clean up the SSH key
    ConMgr.remove_ssh_keys(RHUA, [HA_HOSTNAME])

def test_21_check_cleanup():
    '''
    check if the haproxy service was stopped
    '''
    # for RHBZ#1640002
    nose.tools.ok_(not Helpers.check_service(HAPROXY, "haproxy"),
                   msg="haproxy is still running on " + HA_HOSTNAME)
def teardown():
    '''
    announce the end of the test run
    '''
    print(f"*** Finished running {basename(__file__)}. ***")
