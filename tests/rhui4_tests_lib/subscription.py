""" RHSM integration in RHUI """

import re

from stitches.expect import Expect

from rhui4_tests_lib.helpers import Helpers
from rhui4_tests_lib.cfg import Config

class RHSMRHUI():
    """Subscription management for RHUI"""
    @staticmethod
    def register_system(connection, username="", password="", fail_if_registered=False):
        """register with RHSM"""
        # if username or password isn't specified, it will be obtained using
        # the get_credentials method on the remote host -- only usable with the RHUA
        # if the system is already registered, it will be unregistered first,
        # unless fail_if_registered == True
        if fail_if_registered and Helpers.is_registered(connection):
            raise RuntimeError("The system is already registered.")
        if not username or not password:
            username, password = Config.get_credentials(connection)
        Expect.expect_retval(connection,
                             "subscription-manager register --force --type rhui " +
                             f"--username {username} --password {password}",
                             timeout=60)

    @staticmethod
    def attach_subscription(connection, sub):
        """attach a supported subscription (deprecated by SCA)"""
        # 'sub' can be anything that sub-man can search by,
        # but typically it's the subscription name or the SKU
        # (or a substring with one or more wildcards)
        _, stdout, _ = connection.exec_command("subscription-manager list --available " +
                                               f"--matches '{sub}' --pool-only 2>&1")
        pools = stdout.read().decode().splitlines()
        if not pools:
            raise RuntimeError("There are no available pools.")
        if not all(re.match(r"^[0-9a-f]+$", pool) for pool in pools):
            raise RuntimeError(f"This doesn't look like a list of pools: '{pools}'.")
        pool_opts = " ".join(["--pool " + pool for pool in pools])
        # attach the pool(s)
        Expect.expect_retval(connection, "subscription-manager attach " + pool_opts, timeout=60)

    @staticmethod
    def enable_rhui_repo(connection, base_rhel=True, ansible=False):
        """enable the RHUI 4 repo and by default also the base RHEL repo, disable everything else"""
        cmd = "subscription-manager repos --disable=* --enable=rhui-4-for-rhel-8-x86_64-rpms"
        if ansible:
            cmd += " --enable=ansible-2-for-rhel-8-x86_64-rhui-rpms"
        if base_rhel:
            cmd += " --enable=rhel-8-for-x86_64-appstream-rhui-rpms"
            cmd += " --enable=rhel-8-for-x86_64-baseos-rhui-rpms"
        Expect.expect_retval(connection, cmd, timeout=60)

    @staticmethod
    def unregister_system(connection):
        """unregister from RHSM"""
        Expect.expect_retval(connection, "subscription-manager unregister", timeout=20)

    @staticmethod
    def sca_setup(connection):
        """set the RHUA up for Simple Content Access (SCA) testing"""
        Expect.expect_retval(connection, "cp /tmp/extra_rhui_files/SCA/* /etc/pki/entitlement/")

    @staticmethod
    def sca_cleanup(connection):
        """clean up the (SCA) cert and key"""
        Expect.expect_retval(connection, "rm -f /etc/pki/entitlement/*")
