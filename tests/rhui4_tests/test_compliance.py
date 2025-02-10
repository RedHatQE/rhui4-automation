"""Various Compliance Tests"""

from os.path import basename
import re

from stitches.expect import Expect

from rhui4_tests_lib.conmgr import ConMgr

RHUA = ConMgr.connect()

def _check_rhui_rpms(connection, query, present=True):
    """helper method to check the contents of RHUI packages"""
    cmd = "rpm -ql rhui-installer rhui-tools rhui-tools-libs | " \
          "xargs grep --directories skip --binary-files without-match -i " \
          f"{re.escape(query)}"
    Expect.expect_retval(connection, cmd, 0 if present else 123)

def setup():
    """announce the beginning of the test run"""
    print(f"*** Running {basename(__file__)}: ***")

def test_01_ec2():
    """check if the string EC2 is not used in the RHUI source code"""
    _check_rhui_rpms(RHUA, "ec2", False)

def test_02_deprecation_warnings():
    """check for deprecation warnings from the installer playbook"""
    Expect.expect_retval(RHUA,
                         "grep -i 'DEPRECATION WARNING' "
                         "/var/log/rhui-installer/install_logger.log.*",
                         1)

def teardown():
    """announce the end of the test run"""
    print(f"*** Finished running {basename(__file__)}. ***")
