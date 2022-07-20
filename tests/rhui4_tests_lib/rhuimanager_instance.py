""" RHUIManager CDS functions """

import re
import time

from stitches.expect import Expect, CTRL_C

from rhui4_tests_lib.conmgr import ConMgr, SUDO_USER_NAME, SUDO_USER_KEY
from rhui4_tests_lib.rhuimanager import RHUIManager
from rhui4_tests_lib.instance import Instance

class InstanceAlreadyExistsError(Exception):
    """
    To be raised when trying to add an already tracked Cds or HAProxy
    """

class NoSuchInstance(Exception):
    """
    To be raised e.g. when trying to select a non-existing Cds or HAProxy
    """

class InvalidSshKeyPath(Exception):
    """
    To be raised if rhui-manager wasn't able to locate the provided SSH key path
    """

class RHUIManagerInstance():
    '''
    Represents -= Content Delivery Server (CDS) Management =- RHUI screen
    '''
    prompt_cds = r'rhui \(cds\) => '
    prompt_hap = r'rhui \(loadbalancers\) => '

    @staticmethod
    def add_instance(connection, screen,
                     hostname="", user_name=SUDO_USER_NAME, ssh_key_path=SUDO_USER_KEY,
                     ssl_crt="", ssl_key="",
                     update=False):
        '''
        Register (add) a new CDS or HAProxy instance
        @param hostname instance, or the default value for the screen type as ConMgr knows it
        @param user_name SSH user name for the hostname
        @param ssh_key_path SSH private key for the user at the host
        @param ssl_crt (optional) absolute path to the SSL certificate to deploy (CDS only)
        @param ssl_key (optional) absolute path to the SSL key to deploy (CDS only)
        @param update Bool; update the cds or hap if it is already tracked or raise an exception
        '''
        if not hostname:
            if screen == "cds":
                hostname = ConMgr.get_cds_hostnames()[0]
            elif screen == "loadbalancers":
                hostname = ConMgr.get_cds_lb_hostname()
            else:
                raise ValueError("hostname not given and screen invalid")
        # first check if the RHUA knows the host's SSH key, because if so, rhui-manager
        # won't ask you to confirm the key
        key_check_cmd = "ssh-keygen -F " + hostname
        # check if the host is known
        # in RHEL 8, ssh-keygen considers a hostname known even if the case doesn't match,
        # but rhui-manager doesn't
        known_host = hostname.islower() and connection.recv_exit_status(key_check_cmd) == 0
        # run rhui-manager and add the instance
        RHUIManager.screen(connection, screen)
        Expect.enter(connection, "a")
        Expect.expect(connection, ".*Hostname of the .*instance to register:")
        Expect.enter(connection, hostname)
        state = Expect.expect_list(connection, [ \
            (re.compile(f".*Username with SSH access to {hostname} and sudo privileges:.*",
                        re.DOTALL), 1),
            (re.compile(r".*instance with that hostname exists.*Continue\?\s+\(y/n\): ",
                        re.DOTALL), 2)
                                               ])
        if state == 2:
            # cds or haproxy of the same hostname is already being tracked
            if not update:
                # but we don't wish to update its config: say no, quit rhui-manager, and raise
                # an exception
                Expect.enter(connection, "n")
                RHUIManager.quit(connection)
                raise InstanceAlreadyExistsError(hostname +
                                                 " already tracked but update wasn't required")
            # we wish to update, send 'y' answer
            Expect.enter(connection, "y")
            # the question about user name comes now
            Expect.expect(connection,
                          f"Username with SSH access to {hostname} and sudo privileges:")
        # if the execution reaches here, username question was already asked
        Expect.enter(connection, user_name)
        Expect.expect(connection,
                      f"Absolute path to an SSH private key to log into {hostname} as {user_name}:")
        Expect.enter(connection, ssh_key_path)
        state = Expect.expect_list(connection, [
            (re.compile(".*Cannot find file, please enter a valid path.*", re.DOTALL), 1),
            (re.compile(".*Checking SSH authentication on instance.*", re.DOTALL), 2),
            (re.compile(".*Optional absolute path to user supplied SSL key file:.*", re.DOTALL), 3)
        ])
        if state == 1:
            # don't know how to continue with invalid path: raise an exception
            Expect.enter(connection, CTRL_C)
            Expect.enter(connection, "q")
            raise InvalidSshKeyPath(ssh_key_path)
        if state == 3:
            # the SSL key is only asked for when adding a CDS
            Expect.enter(connection, ssl_key)
            # if the SSL key is specified, rhui-manager also asks for the SSL certificate
            # warning: we don't validate the response,
            # if the key file is invalid, we'll eventually fail
            if ssl_key:
                Expect.expect(connection, "Optional absolute path to user supplied SSL crt file:")
                Expect.enter(connection, ssl_crt)
                Expect.expect(connection, "Checking SSH authentication on instance")
        # all OK
        # if the SSH key is unknown, rhui-manager now asks you to confirm it; say yes
        if not known_host:
            time.sleep(7)
            Expect.enter(connection, "yes")
        # installation and configuration through Ansible happens here, let it take its time
        RHUIManager.quit(connection, "The .*was successfully configured.", 180)


    @staticmethod
    def delete(connection, screen, instances):
        '''
        unregister (delete) one or more CDS or HAProxy instances from the RHUI
        '''
        # first check if the instances are really tracked
        tracked_instances = RHUIManagerInstance.list(connection, screen)
        hostnames = [instance.host_name for instance in tracked_instances]
        bad_instances = [i for i in instances if i not in hostnames]
        if bad_instances:
            raise NoSuchInstance(bad_instances)
        RHUIManager.screen(connection, screen)
        Expect.enter(connection, "d")
        RHUIManager.select_items(connection, instances)
        Expect.enter(connection, "y")
        RHUIManager.quit(connection, "Unregistered", 180)

    @staticmethod
    def delete_all(connection, screen):
        '''
        unregister (delete) all CDS or HAProxy instances from the RHUI
        '''
        RHUIManager.screen(connection, screen)
        Expect.enter(connection, "d")
        Expect.expect(connection, "Enter value .*:")
        Expect.enter(connection, "a")
        Expect.expect(connection, "Enter value .*:")
        Expect.enter(connection, "c")
        Expect.expect(connection, "Are you sure .*:")
        Expect.enter(connection, "y")
        RHUIManager.quit(connection, "Unregistered", 60)

    @staticmethod
    def list(connection, screen):
        '''
        return the list of currently managed CDS or HAProxy instances
        '''
        RHUIManager.screen(connection, screen)
        # eating prompt!!
        lines = RHUIManager.list_lines(connection, r"rhui \(" + screen + r"\) => ")
        ret = Instance.parse(lines)
        Expect.enter(connection, 'q')
        return [cds for _, cds in ret]
