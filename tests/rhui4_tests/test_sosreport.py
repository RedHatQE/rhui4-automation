""" Test case for sosreport usage in RHUI """

# for RHBZ#1591027 and RHBZ#1578678

import logging
from os.path import basename, join
from shutil import rmtree
from tempfile import mkdtemp

from stitches.expect import Expect

from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.helpers import Helpers
from rhui4_tests_lib.rhuimanager import RHUIManager
from rhui4_tests_lib.rhuimanager_instance import RHUIManagerInstance
from rhui4_tests_lib.sos import Sos

logging.basicConfig(level=logging.DEBUG)

TMPDIR = mkdtemp()
SOSREPORT_LOCATION_RHUA = join(TMPDIR, "sosreport_location_rhua")
SOSREPORT_LOCATION_CDS = join(TMPDIR, "sosreport_location_cds")

CONNECTION_RHUA = RHUA = ConMgr.connect()
CONNECTION_CDS = ConMgr.connect(ConMgr.get_cds_hostnames()[0])

WANTED_FILES_RHUA = ["/root/.rhui/answers.yaml",
                     "/root/.rhui/rhui.log",
                     "/etc/rhui/rhui-tools.conf",
                     "/etc/pulp/settings.py",
                     "/var/log/rhui-subscription-sync.log"]
WANTED_FILES_CDS = ["/etc/nginx/nginx.conf",
                    "/etc/nginx/conf.d/ssl.conf",
                    "/var/log/nginx/access.log",
                    "/var/log/nginx/error.log"]

CMDS_RHUA = ["rhui-manager status",
             "rhui-manager cert info"]
CMDS_CDS = ["ls -lR /var/lib/rhui/remote_share"]
WANTED_FILES_RHUA.extend([Helpers.encode_sos_command(cmd) for cmd in CMDS_RHUA])
WANTED_FILES_CDS.extend([Helpers.encode_sos_command(cmd) for cmd in CMDS_CDS])

def setup():
    '''
        announce the beginning of the test run
    '''
    print(f"*** Running {basename(__file__)}: ***")

def test_00_rhui_init():
    '''
        add a CDS and run rhui-subscription-sync to ensure their log files exist
    '''
    #  use initial_run first to ensure we're logged in to rhui-manager
    RHUIManager.initial_run(CONNECTION_RHUA)
    RHUIManagerInstance.add_instance(CONNECTION_RHUA, "cds")
    # can't use expect_retval as the exit code can be 0 or 1 (sync is configured or unconfigured)
    Expect.ping_pong(CONNECTION_RHUA,
                     "rhui-subscription-sync ; echo ACK",
                     "ACK")

def test_01_rhua_sosreport_run():
    '''
        run sosreport on the RHUA node
    '''
    sosreport_location = Sos.run(CONNECTION_RHUA)
    with open(SOSREPORT_LOCATION_RHUA, "w", encoding="utf-8") as location:
        location.write(sosreport_location)

def test_02_rhua_sosreport_check():
    '''
        check if the sosreport archive from the RHUA node contains the desired files
    '''
    with open(SOSREPORT_LOCATION_RHUA, encoding="utf-8") as location:
        sosreport_location = location.read()
    Sos.check_files_in_archive(CONNECTION_RHUA, WANTED_FILES_RHUA, sosreport_location)

def test_03_cds_sosreport_run():
    '''
        run sosreport on the CDS node
    '''
    sosreport_location = Sos.run(CONNECTION_CDS)
    with open(SOSREPORT_LOCATION_CDS, "w", encoding="utf-8") as location:
        location.write(sosreport_location)

def test_04_cds_sosreport_check():
    '''
        check if the sosreport archive from the CDS node contains the desired files
    '''
    with open(SOSREPORT_LOCATION_CDS, encoding="utf-8") as location:
        sosreport_location = location.read()
    Sos.check_files_in_archive(CONNECTION_CDS, WANTED_FILES_CDS, sosreport_location)

def test_99_cleanup():
    '''
        delete the archives and their checksum files, local caches; remove CDS
    '''
    with open(SOSREPORT_LOCATION_RHUA, encoding="utf-8") as location:
        sosreport_file = location.read()
    Expect.ping_pong(CONNECTION_RHUA,
                     "rm -f " + sosreport_file + "* ; " +
                     "ls " + sosreport_file + "* 2>&1",
                     "No such file or directory")
    with open(SOSREPORT_LOCATION_CDS, encoding="utf-8") as location:
        sosreport_file = location.read()
    Expect.ping_pong(CONNECTION_CDS,
                     "rm -f " + sosreport_file + "* ; " +
                     "ls " + sosreport_file + "* 2>&1",
                     "No such file or directory")
    rmtree(TMPDIR)
    RHUIManagerInstance.delete_all(CONNECTION_RHUA, "cds")

def teardown():
    '''
        announce the end of the test run
    '''
    print(f"*** Finished running {basename(__file__)}. ***")
