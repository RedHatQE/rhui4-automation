""" Functions to interact with the Pulp API """

from stitches.expect import Expect

from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.util import Util

class PulpAPI():
    """ Pulp API functions """
    @staticmethod
    def delete_orphans(connection):
        """ delete all orphaned content """
        admin_password = Util.get_saved_password(connection)
        rhua_hostname = ConMgr.get_rhua_hostname()
        Expect.expect_retval(connection,
                             f"curl --cacert /etc/pki/rhui/certs/ca.crt -u admin:{admin_password}" +
                             f" -X POST https://{rhua_hostname}/pulp/api/v3/orphans/cleanup/")
