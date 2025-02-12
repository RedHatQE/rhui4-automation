'''Tests for Update Handling in the Installer'''

from os.path import basename

import logging
import nose
from stitches.expect import Expect

from rhui4_tests_lib.cfg import Config
from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.yummy import Yummy

logging.basicConfig(level=logging.DEBUG)

TEST_PACKAGE = "tzdata"
ARG_IGNORE_UPDATES = "--ignore-newer-rhel-packages"

CUSTOM_CONFIG = {"section": "rhui", "option": "log_level", "value": "DEBUG"}

RHUA = ConMgr.connect()

def setup():
    """announce the beginning of the test run"""
    print(f"*** Running {basename(__file__)}: ***")

def test_01_downgrade_test_package():
    """downgrade the test package"""
    Yummy.downgrade(RHUA, [TEST_PACKAGE])

def test_02_rerun_installer_ignore_updates():
    """rerun the RHUI installer and make it ignore RHEL updates"""
    Expect.expect_retval(RHUA, f"rhui-installer --rerun {ARG_IGNORE_UPDATES}", timeout=600)

def test_03_check_update():
    """check if there is still an update for the test package"""
    nose.tools.ok_(not Yummy.is_up_to_date(RHUA, [TEST_PACKAGE]))

def test_04_custom_configuration():
    """create a custom configuration"""
    Config.set_rhui_tools_conf(RHUA,
                               CUSTOM_CONFIG["section"],
                               CUSTOM_CONFIG["option"],
                               CUSTOM_CONFIG["value"],
                               use_custom_cfg=True)

def test_05_rerun_installer_apply_updates():
    """rerun the RHUI installer and make it apply RHEL updates"""
    Expect.expect_retval(RHUA, "rhui-installer --rerun", timeout=600)

def test_06_check_update():
    """check if there is no update for the test package"""
    nose.tools.ok_(Yummy.is_up_to_date(RHUA, [TEST_PACKAGE]))

def test_07_check_custom_configuration():
    """check if the custom configuration survived the reinstallation"""
    saved_value = Config.get_from_rhui_tools_conf(RHUA,
                                                  CUSTOM_CONFIG["section"],
                                                  CUSTOM_CONFIG["option"],
                                                  True)
    nose.tools.eq_(saved_value, CUSTOM_CONFIG["value"])

def test_08_cleanup():
    """clean up"""
    Config.remove_custom_rhui_tools_conf(RHUA)

def teardown():
    '''
       announce the end of the test run
    '''
    print(f"*** Finished running {basename(__file__)}. ***")
