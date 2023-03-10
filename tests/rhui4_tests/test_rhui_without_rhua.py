"""Tests for RHUI without the RHUA"""

from os.path import basename

import logging
import nose
import requests
from stitches.expect import Expect
import urllib3

from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.rhuimanager import RHUIManager
from rhui4_tests_lib.rhuimanager_client import RHUIManagerClient, \
                                               ContainerSupportDisabledError as CliError
from rhui4_tests_lib.rhuimanager_instance import RHUIManagerInstance
from rhui4_tests_lib.rhuimanager_repo import RHUIManagerRepo, \
                                             ContainerSupportDisabledError as RepoError

logging.basicConfig(level=logging.DEBUG)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

RHUA = ConMgr.connect()
CDS_HOSTNAME = ConMgr.get_cds_hostnames()[0]
CDS = ConMgr.connect(CDS_HOSTNAME)
TEST_PATHS = ["/pulp/container/", "/v2", "/extensions/v2/"]

def _toggle_container_support(switch):
    """helper method to enable or disable container support"""
    if not isinstance(switch, bool):
        raise ValueError("Expected a boolean value.")
    cmd = f"rhui-installer --rerun --container-support-enabled {switch}"
    Expect.expect_retval(RHUA, cmd, timeout=600)

def setup():
    """announce the beginning of the test run"""
    print(f"*** Running {basename(__file__)}: ***")

def test_01_init():
    """log in to RHUI"""
    RHUIManager.initial_run(RHUA)

def test_02_disable_containers():
    """disable support for containers"""
    _toggle_container_support(False)

def test_03_add_cds():
    """add a CDS"""
    RHUIManagerInstance.add_instance(RHUA, "cds")

def test_04_try_adding_a_container():
    """try adding a container, should not be possible"""
    nose.tools.assert_raises(RepoError,
                             RHUIManagerRepo.add_container,
                             RHUA,
                             "foo")

def test_05_try_creating_container_conf():
    """try creating a container configuration RPM, should not be possible"""
    nose.tools.assert_raises(CliError,
                             RHUIManagerClient.create_container_conf_rpm,
                             RHUA,
                             "/tmp",
                             "foo")

def test_06_check_cds_nginx_conf():
    """check the nginx configuration file for container configuration"""
    _, stdout, _ = CDS.exec_command("cat /etc/nginx/conf.d/ssl.conf")
    fetched_cfg = stdout.read().decode()
    for path in TEST_PATHS:
        nose.tools.ok_(path not in fetched_cfg)

def test_07_check_container_urls():
    """check container related URLs, should not be available/found"""
    for path in TEST_PATHS:
        response = requests.head(f"https://{CDS_HOSTNAME}{path}", verify=False)
        nose.tools.eq_(response.status_code, 404)

def test_99_cleanup():
    """re-enable container support, uninstall the CDS"""
    _toggle_container_support(True)
    RHUIManagerInstance.delete_all(RHUA, "cds")

def teardown():
    """announce the end of the test run"""
    print(f"*** Finished running {basename(__file__)}. ***")
