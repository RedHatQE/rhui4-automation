""" Functions to interact with the Pulp API """

import shlex

import json
from stitches.expect import Expect

from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.util import Util

def _get_api_base_cmd(connection):
    """get the base command to access the API; you append the required Pulp href to it"""
    admin_password = shlex.quote(Util.get_saved_password(connection))
    rhua_hostname = ConMgr.get_rhua_hostname()
    cacert = "/etc/pki/rhui/certs/ca.crt"
    return f"curl --cacert {cacert} -u admin:{admin_password} https://{rhua_hostname}"

class PulpAPI():
    """ Pulp API functions """
    @staticmethod
    def delete_orphans(connection, orphan_protection_time=0):
        """ delete all orphaned content """
        cleanup_href = "/pulp/api/v3/orphans/cleanup/"
        cmd = _get_api_base_cmd(connection) + cleanup_href + \
              f" -d orphan_protection_time={orphan_protection_time} -X POST"
        Expect.expect_retval(connection, cmd)

    @staticmethod
    def list_repos(connection):
        """ return information about repos """
        repos_href = "/pulp/api/v3/repositories/rpm/rpm/"
        cmd = _get_api_base_cmd(connection) + repos_href
        _, stdout, _ = connection.exec_command(cmd)
        data = json.load(stdout)
        return data["results"]

    @staticmethod
    def list_repo_versions(connection, repo):
        """ return information about the versions of the given repo """
        repos = PulpAPI.list_repos(connection)
        try:
            versions_href = [r["versions_href"] for r in repos if r["name"] == repo][0]
        except IndexError as exc:
            raise RuntimeError(f"{repo} does not exist") from exc
        cmd = _get_api_base_cmd(connection) + versions_href
        _, stdout, _ = connection.exec_command(cmd)
        data = json.load(stdout)
        return data["results"]
