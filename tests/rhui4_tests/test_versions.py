"""Software Version Tests"""

from os.path import basename

import nose

from rhui4_tests_lib.cfg import Config
from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.yummy import Yummy

RHUA = ConMgr.connect()
CDS = ConMgr.connect(ConMgr.get_cds_hostnames()[0])

PSQL_DATA = {"old_version": 12,
             "version_tolerance": 1}

def _installed_major_version(connection, package):
    """get the installed version of the package"""
    _, stdout, _ = connection.exec_command("rpm -q --qf '%{VERSION}' " + package)
    # split by the last dot
    major_dot_version = stdout.read().decode().rsplit(".", 1)
    # return only the part in front of the last dot
    major_version = major_dot_version[0]
    return None if major_version == f"package {package} is not installed\n" else major_version

def _latest_available_module_stream(connection, package):
    """get the latest available module stream for the package"""
    module_list_lines = Yummy.module_list(connection, package).splitlines()
    # parse the lines: only get those that contain information about the package
    lines_with_stream_info = [line for line in module_list_lines if line.startswith(package)]
    if not lines_with_stream_info:
        return None
    # parse the "table": only get the column with versions
    streams = [line.split()[1] for line in lines_with_stream_info]
    # return the last row (ie. version)
    return streams[-1]

def _check_package(connection, package, tolerance=0):
    """check if the latest module stream is installed for the package, possibly within limits"""
    installed = _installed_major_version(connection, package)
    if not installed:
        raise ValueError(f"{package} is not installed")
    available = _latest_available_module_stream(connection, package)
    if not available:
        raise ValueError(f"{package} stream is not available")
    if tolerance:
        diff = float(available) - float(installed)
        if diff < 0:
            raise ValueError("the installed version is newer than the latest available version")
        nose.tools.ok_(diff <= tolerance,
                       msg=f"the difference ({diff}) is not within the tolerance ({tolerance})")
    else:
        nose.tools.eq_(installed, available)

def setup():
    """announce the beginning of the test run"""
    print(f"*** Running {basename(__file__)}: ***")

def test_01_postgresql():
    """check the postgresql module stream"""
    package = "postgresql"
    answers_option = f"{package}_version"
    # Was this RHUI installed with the old/original version? If so, skip this test.
    installed_package_version = int(Config.get_from_answers(RHUA, answers_option))
    if installed_package_version == PSQL_DATA["old_version"]:
        raise nose.exc.SkipTest(f"This RHUI was installed with the old {package} version.")
    _check_package(RHUA, package, PSQL_DATA["version_tolerance"])

def test_02_nginx():
    """check the nginx module stream, RHUA and CDS"""
    package = "nginx"
    for conn in [RHUA, CDS]:
        _check_package(conn, package)

def teardown():
    """announce the end of the test run"""
    print(f"*** Finished running {basename(__file__)}. ***")
