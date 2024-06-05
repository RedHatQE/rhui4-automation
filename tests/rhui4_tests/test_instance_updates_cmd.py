'''Tests for Update Handling in the CLI Instance Management'''

from os.path import basename

import logging
import nose

from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.rhuimanager import RHUIManager
from rhui4_tests_lib.rhuimanager_cmdline_instance import RHUIManagerCLIInstance
from rhui4_tests_lib.yummy import Yummy

logging.basicConfig(level=logging.DEBUG)

TEST_PACKAGE = "tzdata"

CDS_HOSTNAME = ConMgr.get_cds_hostnames()[0]
HA_HOSTNAME = ConMgr.get_cds_lb_hostname()

RHUA = ConMgr.connect()
CDS = ConMgr.connect(CDS_HOSTNAME)
HAPROXY = ConMgr.connect(HA_HOSTNAME)

def setup():
    """announce the beginning of the test run"""
    print(f"*** Running {basename(__file__)}: ***")

def test_01_downgrade_test_package():
    """log in to RHUI, downgrade the test package on the CDS and HAProxy instaces"""
    RHUIManager.initial_run(RHUA)
    for node in CDS, HAPROXY:
        Yummy.downgrade(node, [TEST_PACKAGE])

def test_02_add_cds_no_update():
    """add a CDS and make it ignore RHEL updates"""
    RHUIManagerCLIInstance.add(RHUA, "cds", unsafe=True, no_update=True)

def test_03_check_update():
    """check if there is still an update for the test package"""
    nose.tools.ok_(not Yummy.is_up_to_date(CDS, [TEST_PACKAGE]))

def test_04_reinstall_cds_apply_updates():
    """reinstall the CDS and make it apply RHEL updates"""
    RHUIManagerCLIInstance.reinstall(RHUA, "cds", CDS_HOSTNAME)

def test_05_check_update():
    """check if there is no update for the test package"""
    nose.tools.ok_(Yummy.is_up_to_date(CDS, [TEST_PACKAGE]))

def test_06_delete_cds_downgrade():
    """delete the CDS and downgrade the test package on it"""
    RHUIManagerCLIInstance.delete(RHUA, "cds", [CDS_HOSTNAME], force=True)
    Yummy.downgrade(CDS, [TEST_PACKAGE])

def test_07_add_cds_add_updates():
    """add a CDS and make it apply RHEL updates"""
    RHUIManagerCLIInstance.add(RHUA, "cds", unsafe=True)

def test_08_check_update():
    """check if there is no update for the test package"""
    nose.tools.ok_(Yummy.is_up_to_date(CDS, [TEST_PACKAGE]))

def test_09_delete_cds():
    """delete the CDS"""
    RHUIManagerCLIInstance.delete(RHUA, "cds", [CDS_HOSTNAME], force=True)

def test_10_add_lb_no_update():
    """add a loadbalancer and make it ignore RHEL updates"""
    RHUIManagerCLIInstance.add(RHUA, "haproxy", unsafe=True, no_update=True)

def test_11_check_update():
    """check if there is still an update for the test package"""
    nose.tools.ok_(not Yummy.is_up_to_date(HAPROXY, [TEST_PACKAGE]))

def test_12_reinstall_lb_apply_updates():
    """reinstall the loadbalancer and make it apply RHEL updates"""
    RHUIManagerCLIInstance.reinstall(RHUA, "haproxy", HA_HOSTNAME)

def test_13_check_update():
    """check if there is no update for the test package"""
    nose.tools.ok_(Yummy.is_up_to_date(HAPROXY, [TEST_PACKAGE]))

def test_14_delete_lb_downgrade():
    """delete the loadbalancer and downgrade the test package on it"""
    RHUIManagerCLIInstance.delete(RHUA, "haproxy", [HA_HOSTNAME], force=True)
    Yummy.downgrade(HAPROXY, [TEST_PACKAGE])

def test_15_add_lb_apply_updates():
    """add a loadbalancer and make it apply RHEL updates"""
    RHUIManagerCLIInstance.add(RHUA, "haproxy", unsafe=True)

def test_16_check_update():
    """check if there is no update for the test package"""
    nose.tools.ok_(Yummy.is_up_to_date(HAPROXY, [TEST_PACKAGE]))

def test_17_delete_lb():
    """delete the loadbalancer"""
    RHUIManagerCLIInstance.delete(RHUA, "haproxy", [HA_HOSTNAME], force=True)

def test_18_cleanup():
    """clean up"""
    ConMgr.remove_ssh_keys(RHUA)

def teardown():
    """announce the end of the test run"""
    print(f"*** Finished running {basename(__file__)}. ***")
