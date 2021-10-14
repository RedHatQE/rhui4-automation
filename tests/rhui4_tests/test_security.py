"""Various Security Tests"""

import csv
import logging
from os.path import basename
import subprocess

import nose

from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.rhuimanager import RHUIManager
from rhui4_tests_lib.rhuimanager_instance import RHUIManagerInstance

logging.basicConfig(level=logging.DEBUG)

HOSTNAMES = {"RHUA": ConMgr.get_rhua_hostname(),
             "CDS": ConMgr.get_cds_hostnames()[0],
             "HAProxy": ConMgr.get_cds_lb_hostname()}
PORTS = { "https": 443 }
PROTOCOL_TEST_CMD = "echo | openssl s_client -%s -connect %s:%s; echo $?"
# these are in fact the s_client options for protocols, just without the dash
PROTOCOLS = {"good": ["tls1_2"],
             "bad": ["tls1", "tls1_1"]}
RESULTS = {"good": "Secure Renegotiation IS supported",
           "bad": "Secure Renegotiation IS NOT supported"}

# connections to the RHUA and the HAProxy nodes
RHUA = ConMgr.connect()
HAPROXY = ConMgr.connect(HOSTNAMES["HAProxy"])

def _check_protocols(hostname, port):
    """helper method to try various protocols on hostname:port"""
    # check allowed protocols
    for protocol in PROTOCOLS["good"]:
        raw_output = subprocess.check_output(PROTOCOL_TEST_CMD % (protocol, hostname, port),
                                             shell=True,
                                             stderr=subprocess.STDOUT)
        output_lines = raw_output.decode().splitlines()
        # check for the line that indicates a good result
        nose.tools.ok_(RESULTS["good"] in output_lines,
                       msg=f"s_client didn't print '{RESULTS['good']}' when using {protocol}" +
                           f"with {hostname}:{port}")
        # also check the exit status (the last line), should be 0 to indicate success
        nose.tools.eq_(int(output_lines[-1]), 0)
    # check disallowed protocols
    for protocol in PROTOCOLS["bad"]:
        raw_output = subprocess.check_output(PROTOCOL_TEST_CMD % (protocol, hostname, port),
                                             shell=True,
                                             stderr=subprocess.STDOUT)
        output_lines = raw_output.decode().splitlines()
        # check for the line that indicates a bad result
        nose.tools.ok_(RESULTS["bad"] in output_lines,
                       msg=f"s_client didn't print '{RESULTS['bad']}' when using {protocol}" +
                           f"with {hostname}:{port}")
        # also check the exit status (the last line), should be 1 to indicate a failure
        nose.tools.eq_(int(output_lines[-1]), 1)

def setup():
    """announce the beginning of the test run"""
    print(f"*** Running {basename(__file__)}: ***")

def test_01_login_add_cds_hap():
    """log in to RHUI, add CDS and HAProxy nodes"""
    RHUIManager.initial_run(RHUA)
    RHUIManagerInstance.add_instance(RHUA, "cds")
    RHUIManagerInstance.add_instance(RHUA, "loadbalancers")

def test_02_https_rhua():
    """check protocols allowed by nginx on the RHUA"""
    # for RHBZ#1637261
    _check_protocols(HOSTNAMES["RHUA"], PORTS["https"])

def test_03_https_cds():
    """check protocols allowed by nginx on the CDS nodes"""
    # for RHBZ#1637261
    _check_protocols(HOSTNAMES["CDS"], PORTS["https"])

def test_04_haproxy_stats():
    """check haproxy stats"""
    # for RHBZ#1718066
    _, stdout, _ = HAPROXY.exec_command("echo 'show stat' | nc -U /var/lib/haproxy/stats")
    stats = list(csv.DictReader(stdout))
    httpsstats = {row["svname"]: row["status"] for row in stats if row["# pxname"] == "https00"}
    # check the stats for the frontend, the CDS nodes, and the backend; https
    nose.tools.eq_(httpsstats["FRONTEND"], "OPEN")
    nose.tools.eq_(httpsstats["BACKEND"], "UP")
    nose.tools.eq_(httpsstats[HOSTNAMES["CDS"]], "UP")

def test_99_cleanup():
    """delete CDS and HAProxy nodes"""
    RHUIManagerInstance.delete_all(RHUA, "loadbalancers")
    RHUIManagerInstance.delete_all(RHUA, "cds")

def teardown():
    """announce the end of the test run"""
    print(f"*** Finished running {basename(__file__)}. ***")
