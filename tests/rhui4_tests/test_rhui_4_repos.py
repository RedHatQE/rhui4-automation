'''Tests for RHUI 4 repos and EUS listings'''

from os.path import basename
import re

from heapq import merge
import logging
import nose
from stitches.expect import Expect
import requests

from rhui4_tests_lib.conmgr import ConMgr

logging.basicConfig(level=logging.DEBUG)

RHUA = ConMgr.connect()

DOC = "https://access.redhat.com/documentation/en-us/red_hat_update_infrastructure/4/html/" \
      "release_notes/index"
VERSION_STRING = r"4\.[0-9]+ Release Notes"

MAX_RHEL_6_EUS = 7
MAX_RHEL_7_EUS = 7
MAX_RHEL_8_EUS = 8
MAX_RHEL_9_EUS = 6
MAX_RHEL_10_EUS = 0

def _check_rpms():
    '''
        helper method to check if the RHUI repository contains enough RPMs
        and if "rhui-tools" is included (the main package and -libs, all released versions)
    '''
    cmd = "wget -q -O - " + \
          "--certificate /tmp/extra_rhui_files/rhcert.pem " + \
          "--ca-certificate /etc/rhsm/ca/redhat-uep.pem " + \
          "https://cdn.redhat.com/" + \
          "content/dist/layered/rhel8/x86_64/rhui/4/os/"

    rpm_link_pattern = r'href="[^"]+\.rpm'
    min_count = 78
    # first fetch repodata
    _, stdout, _ = RHUA.exec_command(cmd + "repodata/repomd.xml")
    repomd_xml = stdout.read().decode()
    primary_xml_gz_path = re.findall("[0-9a-f]+-primary.xml.gz", repomd_xml)[0]
    # now fetch package info, uncompressed & filtered on the RHUA, paths on separate lines
    # (not fetching the compressed or uncompressed data as it's not decode()able)
    _, stdout, _ = RHUA.exec_command(cmd + "repodata/" + primary_xml_gz_path +
                                     f" | zegrep -o '{rpm_link_pattern}'" +
                                     " | sed 's/href=\"//'")
    rpm_paths = stdout.read().decode().splitlines()
    # get just package file names
    rpms = [basename(rpm) for rpm in rpm_paths]
    # check the number of RPMs
    rpms_count = len(rpms)
    error_msg = f"Not enough RPMs. Expected at least {min_count}, found "
    if rpms_count == 0:
        error_msg += "none."
    else:
        error_msg += f"the following {rpms_count}: {rpms}."
    nose.tools.ok_(rpms_count >= min_count, msg=error_msg)
    rhui_tools_rpms = [rpm for rpm in rpms if rpm.startswith("rhui-tools")]
    nose.tools.ok_(rhui_tools_rpms, msg="rhui-tools*: no such link")

    rhui_tools_rpms.sort()
    latest_rhui_rpm_in_repo = rhui_tools_rpms[-1]
    # can the latest version actually be fetched?
    Expect.expect_retval(RHUA,
                         cmd.replace("-q -O -", "-O /dev/null") +
                         "Packages/r/" +
                         latest_rhui_rpm_in_repo)

    latest_rpm_version = latest_rhui_rpm_in_repo.rsplit('-', 2)[1]
    latest_rpm_xy_list = latest_rpm_version.split(".")[:2]
    return float(".".join(latest_rpm_xy_list))

def _check_latest_documented_version(expected_version):
    '''
        helper method to check if the latest released and documented versions match
        the version is expected to be a floating point number representing major.minor
    '''
    documented_titles = re.findall(VERSION_STRING, requests.get(DOC, timeout=30).text)
    documented_versions = [float(title.split()[0]) for title in documented_titles]
    documented_versions.sort()
    latest_documented_version = documented_versions[-1]
    nose.tools.eq_(expected_version, latest_documented_version)

def _check_listing(major, min_eus, max_eus, step=1, exceptions=None):
    '''
        helper method to check if the listings file for the given EUS version is complete
        major: RHEL X version to check
        min_eus: expected min RHEL (X.)Y version
        max_eus: expected max RHEL (X.)Y version
        step: increments
        exceptions: a list of minor versions outside the increments
        for lists of X.Y versions in EUS, see:
        https://access.redhat.com/support/policy/updates/errata/#Extended_Update_Support
    '''
    subpath = f"rhel/rhui/server/{major}" if major < 8 else f"rhel{major}/rhui"
    cmd = "wget -q -O - " + \
          "--certificate /tmp/extra_rhui_files/rhcert.pem " + \
          "--ca-certificate /etc/rhsm/ca/redhat-uep.pem " + \
          f"https://cdn.redhat.com/content/eus/{subpath}/listing"
    listings_expected = [f"{major}.{minor}" for minor in range(min_eus, max_eus + 1, step)]
    if exceptions:
        listings_expected = list(merge(listings_expected,
                                       [f"{major}.{minor}" for minor in exceptions]))
    _, stdout, _ = RHUA.exec_command(cmd)
    listings_actual = stdout.read().decode().splitlines()
    nose.tools.eq_(listings_expected, listings_actual)

def setup():
    '''
       announce the beginning of the test run
    '''
    print(f"*** Running {basename(__file__)}: ***")

def test_01_rhui_4_for_rhel_8_check():
    '''
        check if the RHUI 4 packages for RHEL 8 are available and the latest version is documented
    '''
    rhui_version = _check_rpms()
    _check_latest_documented_version(rhui_version)

def test_02_eus_6_repos_check():
    '''
        check if all supported RHEL 6 EUS versions are available
    '''
    # RHEL 6.1-6.7
    _check_listing(6, 1, MAX_RHEL_6_EUS)

def test_03_eus_7_repos_check():
    '''
        check if all supported RHEL 7 EUS versions are available
    '''
    # RHEL 7.1-7.7
    _check_listing(7, 1, MAX_RHEL_7_EUS)

def test_04_eus_8_repos_check():
    '''
        check if all supported RHEL 8 EUS versions are available
    '''
    # RHEL 8.1 and then 8.even numbers
    _check_listing(8, 2, MAX_RHEL_8_EUS, 2, [1])

def test_05_eus_9_repos_check():
    '''
        check if all supported RHEL 9 EUS versions are available
    '''
    # RHEL 9.even numbers
    _check_listing(9, 0, MAX_RHEL_9_EUS, 2)

def test_06_eus_10_repos_check():
    '''
        check if all supported RHEL 10 EUS versions are available
    '''
    # Only one version now
    _check_listing(10, 0, MAX_RHEL_10_EUS)

def teardown():
    '''
       announce the end of the test run
    '''
    print(f"*** Finished running {basename(__file__)}. ***")
