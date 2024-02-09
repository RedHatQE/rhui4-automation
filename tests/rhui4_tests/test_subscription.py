""" Test case for the RHUI SKU and the RHUI 4 repo """

import logging
from os.path import basename

import nose
from stitches.expect import Expect
import yaml

from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.rhuimanager import RHUIManager
from rhui4_tests_lib.rhuimanager_entitlement import RHUIManagerEntitlements
from rhui4_tests_lib.subscription import RHSMRHUI

logging.basicConfig(level=logging.DEBUG)

RHUA = ConMgr.connect()

class TestSubscription():
    """class for tests for subscription registration in RHUI"""

    def __init__(self):
        with open("/etc/rhui4_tests/tested_repos.yaml", encoding="utf-8") as configfile:
            doc = yaml.safe_load(configfile)
            self.subscriptions = doc["subscriptions"]

    @staticmethod
    def setup_class():
        """announce the beginning of the test run"""
        print(f"*** Running {basename(__file__)}: ***")

    @staticmethod
    def test_00_initial_run():
        """log in to RHUI"""
        RHUIManager.initial_run(RHUA)

    @staticmethod
    def test_01_register_system():
        """register with RHSM"""
        RHSMRHUI.register_system(RHUA)

    def test_02_attach_rhui_sub(self):
        """attach the RHUI subscription"""
        RHSMRHUI.attach_subscription(RHUA, self.subscriptions["RHUI"])

    def test_03_attach_atomic_sub(self):
        """attach the Atomic subscription"""
        RHSMRHUI.attach_subscription(RHUA, self.subscriptions["Atomic"])

    @staticmethod
    def test_04_check_entitlements():
        """check entitlements"""
        Expect.expect_retval(RHUA, "rhui-subscription-sync")
        nose.tools.ok_(RHUIManagerEntitlements.list_rh_entitlements(RHUA))

    @staticmethod
    def test_05_unregister_system():
        """unregister from RHSM"""
        RHSMRHUI.unregister_system(RHUA)
        RHUIManager.remove_rh_certs(RHUA)

    @staticmethod
    def test_06_sca_setup():
        """set up SCA"""
        RHSMRHUI.sca_setup(RHUA)

    @staticmethod
    def test_07_check_entitlements():
        """check entitlements"""
        Expect.expect_retval(RHUA, "rhui-subscription-sync", timeout=30)
        nose.tools.ok_(RHUIManagerEntitlements.list_rh_entitlements(RHUA))

    @staticmethod
    def test_08_sca_cleanup():
        """clean up the SCA cert and key"""
        RHSMRHUI.sca_cleanup(RHUA)
        RHUIManager.remove_rh_certs(RHUA)

    @staticmethod
    def teardown_class():
        """announce the end of the test run"""
        print(f"*** Finished running {basename(__file__)}. ***")
