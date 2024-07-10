"""CDS-HAProxy Interoperability Tests"""

from os.path import basename

import logging
import nose
from stitches.expect import Expect

from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.helpers import Helpers
from rhui4_tests_lib.rhuimanager_cmdline_instance import RHUIManagerCLIInstance
from rhui4_tests_lib.rhuimanager import RHUIManager
from rhui4_tests_lib.rhuimanager_instance import RHUIManagerInstance

logging.basicConfig(level=logging.DEBUG)

# check if (at least) two CDS nodes are actually available
CDS_HOSTNAMES = ConMgr.get_cds_hostnames()
CDS2_EXISTS = len(CDS_HOSTNAMES) > 1

HA_HOSTNAME = ConMgr.get_cds_lb_hostname()

RHUA = ConMgr.connect()
CDS = ConMgr.connect(CDS_HOSTNAMES[0])
HAPROXY = ConMgr.connect(HA_HOSTNAME)

def setup():
    """announce the beginning of the test run"""
    print(f"*** Running {basename(__file__)}: ***")

def test_01_login_add_hap():
    """log in to RHUI, add an HAProxy Load-balancer, check the restart script"""
    RHUIManager.initial_run(RHUA)
    RHUIManagerInstance.add_instance(RHUA, "loadbalancers")
    # also check the restart script there
    Helpers.restart_rhui_services(HAPROXY)

def test_02_add_first_cds():
    """[TUI] add the first CDS, check the restart script"""
    RHUIManagerInstance.add_instance(RHUA, "cds", CDS_HOSTNAMES[0])
    # also check the restart script there
    Helpers.restart_rhui_services(CDS)

def test_03_check_haproxy_cfg():
    """check if the first CDS was added to the HAProxy configuration file"""
    nose.tools.ok_(Helpers.cds_in_haproxy_cfg(HAPROXY, CDS_HOSTNAMES[0]))

def test_04_add_second_cds():
    """[TUI] add the second CDS"""
    if not CDS2_EXISTS:
        raise nose.exc.SkipTest("The second CDS does not exist")
    RHUIManagerInstance.add_instance(RHUA, "cds", CDS_HOSTNAMES[1])

def test_05_check_haproxy_cfg():
    """check if the second CDS was added to the HAProxy configuration file"""
    if not CDS2_EXISTS:
        raise nose.exc.SkipTest("The second CDS does not exist")
    nose.tools.ok_(Helpers.cds_in_haproxy_cfg(HAPROXY, CDS_HOSTNAMES[1]))
    # also check if the first one is still there
    nose.tools.ok_(Helpers.cds_in_haproxy_cfg(HAPROXY, CDS_HOSTNAMES[0]))

def test_06_delete_second_cds():
    """[TUI] delete the second CDS"""
    if not CDS2_EXISTS:
        raise nose.exc.SkipTest("The second CDS does not exist")
    RHUIManagerInstance.delete(RHUA, "cds", [CDS_HOSTNAMES[1]])

def test_07_check_haproxy_cfg():
    """check if the second CDS (and only it) was deleted from the HAProxy configuration file"""
    if not CDS2_EXISTS:
        raise nose.exc.SkipTest("The second CDS does not exist")
    nose.tools.ok_(not Helpers.cds_in_haproxy_cfg(HAPROXY, CDS_HOSTNAMES[1]))
    nose.tools.ok_(Helpers.cds_in_haproxy_cfg(HAPROXY, CDS_HOSTNAMES[0]))

def test_08_delete_first_cds():
    """[TUI] delete the first CDS"""
    RHUIManagerInstance.delete(RHUA, "cds", [CDS_HOSTNAMES[0]])

def test_09_check_haproxy_cfg():
    """check if the first CDS was deleted from the HAProxy configuration file"""
    nose.tools.ok_(not Helpers.cds_in_haproxy_cfg(HAPROXY, CDS_HOSTNAMES[0]))

def test_10_add_first_cds():
    """[CLI] add the first CDS"""
    RHUIManagerCLIInstance.add(RHUA, "cds", CDS_HOSTNAMES[0], unsafe=True)

def test_11_check_haproxy_cfg():
    """check if the first CDS was added to the HAProxy configuration file"""
    nose.tools.ok_(Helpers.cds_in_haproxy_cfg(HAPROXY, CDS_HOSTNAMES[0]))

def test_12_add_second_cds():
    """[CLI] add the second CDS"""
    if not CDS2_EXISTS:
        raise nose.exc.SkipTest("The second CDS does not exist")
    RHUIManagerCLIInstance.add(RHUA, "cds", CDS_HOSTNAMES[1], unsafe=True)

def test_13_check_haproxy_cfg():
    """check if the second CDS was added to the HAProxy configuration file"""
    if not CDS2_EXISTS:
        raise nose.exc.SkipTest("The second CDS does not exist")
    nose.tools.ok_(Helpers.cds_in_haproxy_cfg(HAPROXY, CDS_HOSTNAMES[1]))
    # also check if the first one is still there
    nose.tools.ok_(Helpers.cds_in_haproxy_cfg(HAPROXY, CDS_HOSTNAMES[0]))

def test_14_delete_second_cds():
    """[CLI] delete the second CDS"""
    if not CDS2_EXISTS:
        raise nose.exc.SkipTest("The second CDS does not exist")
    RHUIManagerCLIInstance.delete(RHUA, "cds", [CDS_HOSTNAMES[1]])

def test_15_check_haproxy_cfg():
    """check if the second CDS (and only it) was deleted from the HAProxy configuration file"""
    if not CDS2_EXISTS:
        raise nose.exc.SkipTest("The second CDS does not exist")
    nose.tools.ok_(not Helpers.cds_in_haproxy_cfg(HAPROXY, CDS_HOSTNAMES[1]))
    nose.tools.ok_(Helpers.cds_in_haproxy_cfg(HAPROXY, CDS_HOSTNAMES[0]))

def test_16_delete_first_cds():
    """[CLI] delete the first CDS"""
    RHUIManagerCLIInstance.delete(RHUA, "cds", [CDS_HOSTNAMES[0]], True)

def test_17_check_haproxy_cfg():
    """check if the first CDS was deleted from the HAProxy configuration file"""
    nose.tools.ok_(not Helpers.cds_in_haproxy_cfg(HAPROXY, CDS_HOSTNAMES[0]))

def test_99_cleanup():
    """delete the HAProxy Load-balancer, check the restart script (works on RHUA, gone elsewhere)"""
    RHUIManagerInstance.delete(RHUA, "loadbalancers", [HA_HOSTNAME])
    # also clean up the SSH keys (if left behind)
    ConMgr.remove_ssh_keys(RHUA)
    # also check the restart script on the RHUA
    Helpers.restart_rhui_services(RHUA)
    # check if deprecated services are gone
    Expect.expect_retval(RHUA, "test -f /lib/systemd/system/pulpcore-resource-manager.service", 1)
    # and finally check if the restart script is gone from the other nodes
    Expect.expect_retval(CDS, "which rhui-services-restart", 1)
    Expect.expect_retval(HAPROXY, "which rhui-services-restart", 1)

def teardown():
    """announce the end of the test run"""
    print(f"*** Finished running {basename(__file__)}. ***")
