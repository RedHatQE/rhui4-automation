""" Functions to interact with the Pulp API """

import shlex

from stitches.expect import Expect

from rhui4_tests_lib.conmgr import ConMgr
from rhui4_tests_lib.util import Util

class PulpAPI():
    """ Pulp API functions """
    @staticmethod
    def delete_orphans(connection, orphan_protection_time=0):
        """ delete all orphaned content """
        admin_password = shlex.quote(Util.get_saved_password(connection))
        rhua_hostname = ConMgr.get_rhua_hostname()
        Expect.expect_retval(connection,
                             f"curl --cacert /etc/pki/rhui/certs/ca.crt -u admin:{admin_password}" +
                             f" -d orphan_protection_time={orphan_protection_time}" +
                             f" -X POST https://{rhua_hostname}/pulp/api/v3/orphans/cleanup/")
