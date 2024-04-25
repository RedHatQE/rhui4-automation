"""Tests for changing the number of Pulp Workers"""

from os.path import basename

import logging
import nose
from stitches.expect import Expect

from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.helpers import Helpers, ANSWERS_BAK

logging.basicConfig(level=logging.DEBUG)

RHUA_HOSTNAME = ConMgr.get_rhua_hostname()

RHUA = ConMgr.connect()

CUSTOM_WORKER_COUNT = 2
UNIT_NAME = "pulpcore-worker"

def _change_worker_count(count, expect_failure=False):
    """helper method to change the number of Pulp workers"""
    cmd = f"rhui-installer --rerun --pulp-workers {count}"
    Expect.expect_retval(RHUA, cmd, 2 if expect_failure else 0, 600)

def _get_current_pulp_worker_count():
    """get the number of Pulp workers"""
    cmd = f"systemctl list-units --no-legend --all '{UNIT_NAME}@*'"
    _, stdout, _ = RHUA.exec_command(cmd)
    raw_lines = stdout.read().decode().splitlines()
    return len(raw_lines)

def setup():
    """announce the beginning of the test run"""
    print(f"*** Running {basename(__file__)}: ***")

def test_01_prep():
    """back up the answers file"""
    Helpers.backup_answers(RHUA)

def test_02_change_pulp_worker_count():
    """change the number of Pulp workers"""
    _change_worker_count(CUSTOM_WORKER_COUNT)

def test_03_check_pulp_worker_count():
    """check if the number of Pulp workers has changed"""
    current_count = _get_current_pulp_worker_count()
    nose.tools.eq_(current_count, CUSTOM_WORKER_COUNT)

def test_04_check_rhui_manager_status():
    """run rhui-manager status and check if workers are ok and their count matches"""
    cmd = "rhui-manager --noninteractive status"
    _, stdout, _ = RHUA.exec_command(cmd)
    output = stdout.read().decode().splitlines()
    worker_lines = [line for line in output if line.startswith(UNIT_NAME)]
    nose.tools.eq_(len(worker_lines), CUSTOM_WORKER_COUNT)
    exit_code = output[-1]
    # also, if all the services are OK, the last line in the output will be 0
    nose.tools.eq_(exit_code, str(0))

def test_05_revert_pulp_worker_count():
    """revert the number of Pulp workers"""
    orig_count = Helpers.get_from_answers(RHUA, "pulp_workers", ANSWERS_BAK)
    _change_worker_count(orig_count)

def test_06_check_pulp_worker_count():
    """check if the number of Pulp workers has been reverted"""
    current_count = _get_current_pulp_worker_count()
    orig_count = Helpers.get_from_answers(RHUA, "pulp_workers", ANSWERS_BAK)
    nose.tools.eq_(current_count, orig_count)

def test_07_wrong_count_parameter():
    """check if the installer refuses incorrect Pulp worker count values"""
    for bad_count in [0, -1, "foo", ""]:
        _change_worker_count(bad_count, True)

def test_99_cleanup():
    """clean up: remove the answers file backup"""
    Helpers.restore_answers(RHUA)

def teardown():
    """announce the end of the test run"""
    print(f"*** Finished running {basename(__file__)}. ***")
