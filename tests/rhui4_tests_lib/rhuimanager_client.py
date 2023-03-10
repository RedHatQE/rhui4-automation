""" RHUIManager Client functions """

import re

from stitches.expect import Expect

from rhui4_tests_lib.rhuimanager import RHUIManager

class ContainerSupportDisabledError(Exception):
    '''
    To be raised if container support is disabled in RHUI configuration.
    '''

class RHUIManagerClient():
    '''
    Represents -= Client Entitlement Management =- RHUI screen
    '''
    @staticmethod
    def generate_ent_cert(connection, repolist, certname, dirname, validity_days=""):
        '''
        generate an entitlement certificate
        '''
        RHUIManager.screen(connection, "client")
        Expect.enter(connection, "e")
        RHUIManager.select(connection, repolist)
        Expect.expect(connection, "Name of the certificate.*contained with it:")
        Expect.enter(connection, certname)
        Expect.expect(connection, "Local directory in which to save the generated certificate.*:")
        Expect.enter(connection, dirname)
        Expect.expect(connection, "Number of days the certificate should be valid.*:")
        Expect.enter(connection, validity_days)
        RHUIManager.proceed_without_check(connection)
        RHUIManager.quit(connection, timeout=60)

    @staticmethod
    def create_conf_rpm(connection, dirname, certpath, certkey, rpmname, rpmversion="",
                        rpmrelease="", unprotected_repos=None):
        '''
        create a client configuration RPM from an entitlement certificate
        '''
        RHUIManager.screen(connection, "client")
        Expect.enter(connection, "c")
        Expect.expect(connection, "Full path to local directory.*:")
        Expect.enter(connection, dirname)
        Expect.expect(connection, "Name of the RPM:")
        Expect.enter(connection, rpmname)
        Expect.expect(connection, "Version of the configuration RPM.*:")
        Expect.enter(connection, rpmversion)
        Expect.expect(connection, "Release of the configuration RPM.*:")
        Expect.enter(connection, rpmrelease)
        Expect.expect(connection, "Full path to the entitlement certificate.*:")
        Expect.enter(connection, certpath)
        Expect.expect(connection,
                      "Full path to the private key for the above entitlement certificate:")
        Expect.enter(connection, certkey)
        if unprotected_repos:
            RHUIManager.select(connection, unprotected_repos)
        if not rpmversion:
            rpmversion = "2.0"
        if not rpmrelease:
            rpmrelease = "1"
        Expect.expect(connection,
                      f"Location: {dirname}/{rpmname}-{rpmversion}/build/RPMS/noarch/" +
                      f"{rpmname}-{rpmversion}-{rpmrelease}.noarch.rpm")
        Expect.enter(connection, "q")

    @staticmethod
    def create_container_conf_rpm(connection, dirname, rpmname, rpmversion="", rpmrelease="",
                                  days=""):
        '''
        create a container client configuration RPM
        '''
        RHUIManager.screen(connection, "client")
        Expect.enter(connection, "d")
        state = Expect.expect_list(connection,
                                   [(re.compile(".*Full path to local directory.*:",
                                                re.DOTALL),
                                     1),
                                    (re.compile(".*Container support is not currently enabled.*",
                                                re.DOTALL),
                                     2)])
        if state == 2:
            Expect.enter(connection, "q")
            raise ContainerSupportDisabledError()

        Expect.enter(connection, dirname)
        Expect.expect(connection, "Name of the RPM:")
        Expect.enter(connection, rpmname)
        Expect.expect(connection, "Version of the configuration RPM.*:")
        Expect.enter(connection, rpmversion)
        Expect.expect(connection, "Release of the configuration RPM.*:")
        Expect.enter(connection, rpmrelease)
        Expect.expect(connection, "Number of days.*:")
        Expect.enter(connection, days)
        if not rpmversion:
            rpmversion = "2.0"
        if not rpmrelease:
            rpmrelease = "1"
        Expect.expect(connection,
                      f"Location: {dirname}/{rpmname}-{rpmversion}/build/RPMS/noarch/" +
                      f"{rpmname}-{rpmversion}-{rpmrelease}.noarch.rpm")
        Expect.enter(connection, "q")
