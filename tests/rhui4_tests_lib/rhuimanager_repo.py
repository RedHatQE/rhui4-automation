""" RHUIManager Repo functions """

from os.path import basename
import re
import time

from stitches.expect import CTRL_C, Expect

from rhui4_tests_lib.helpers import Helpers
from rhui4_tests_lib.rhuimanager import RHUIManager
from rhui4_tests_lib.util import Util


class AlreadyExistsError(Exception):
    '''
    To be raised if a custom repo already exists with this name.
    '''

class RHUIManagerRepo():
    '''
    Represents -= Repository Management =- RHUI screen
    '''
    @staticmethod
    def add_custom_repo(connection,
                        reponame,
                        displayname="",
                        path="",
                        entitlement="y",
                        entitlement_path="",
                        redhat_gpg="y",
                        custom_gpg=None):
        '''
        create a new custom repository
        '''
        RHUIManager.screen(connection, "repo")
        Expect.enter(connection, "c")
        Expect.expect(connection, "Unique ID for the custom repository.*:")
        Expect.enter(connection, reponame)
        checklist = ["ID: " + reponame]
        state = Expect.expect_list(connection,
                                   [(re.compile(".*Display name for the custom repository.*:",
                                                re.DOTALL),
                                     1),
                                    (re.compile(".*repository.*already exists.*Unique ID.*:",
                                                re.DOTALL),
                                     2)])
        if state == 1:
            Expect.enter(connection, displayname)
            if displayname != "":
                checklist.append("Name: " + displayname)
            else:
                checklist.append("Name: " + reponame)
            Expect.expect(connection, "Unique path at which the repository will be served.*:")
            Expect.enter(connection, path)
            if path != "":
                path_real = path
            else:
                path_real = reponame
            checklist.append("Path: " + path_real)
            Expect.expect(connection,
                          "Should the repository require an entitlement certificate " +
                          r"to access\? \(y/n\)")
            Expect.enter(connection, entitlement)
            if entitlement == "y":
                Expect.expect(connection,
                              "Path that should be used when granting an entitlement " +
                              "for this repository.*:")
                Expect.enter(connection, entitlement_path)
                if entitlement_path != "":
                    checklist.append("Entitlement: " + entitlement_path)
                else:
                    educated_guess, replace_count = re.subn("(i386|x86_64)", "$basearch", path_real)
                    if replace_count > 1:
                        # bug 815975
                        educated_guess = path_real
                    checklist.append("Entitlement: " + educated_guess)
            Expect.expect(connection, r"packages are signed by a GPG key\? \(y/n\)")
            if redhat_gpg == "y" or custom_gpg:
                Expect.enter(connection, "y")
                checklist.append("GPG Check Yes")
                Expect.expect(connection,
                              "Will the repository be used to host any " +
                              r"Red Hat GPG signed content\? \(y/n\)")
                Expect.enter(connection, redhat_gpg)
                if redhat_gpg == "y":
                    checklist.append("Red Hat GPG Key: Yes")
                else:
                    checklist.append("Red Hat GPG Key: No")
                Expect.expect(connection,
                              "Will the repository be used to host any " +
                              r"custom GPG signed content\? \(y/n\)")
                if custom_gpg:
                    Expect.enter(connection, "y")
                    Expect.expect(connection,
                                  "Enter the absolute path to the public key of the GPG keypair:")
                    Expect.enter(connection, custom_gpg)
                    Expect.expect(connection,
                                  r"Would you like to enter another public key\? \(y/n\)")
                    Expect.enter(connection, "n")
                    checklist.append("Custom GPG Keys: '" + custom_gpg + "'")
                else:
                    Expect.enter(connection, "n")
                    checklist.append("Custom GPG Keys: (None)")
            else:
                Expect.enter(connection, "n")
                checklist.append("GPG Check No")
                checklist.append("Red Hat GPG Key: No")

            RHUIManager.proceed_with_check(connection,
                                           "The following repository will be created:",
                                           checklist)
            RHUIManager.quit(connection, "Successfully created repository *")
        else:
            Expect.enter(connection, CTRL_C)
            RHUIManager.quit(connection)
            raise AlreadyExistsError()

    @staticmethod
    def add_rh_repo_all(connection):
        '''
        add a new Red Hat content repository (All in Certificate)
        '''
        RHUIManager.screen(connection, "repo")
        Expect.enter(connection, "a")
        Expect.expect(connection, "Import Repositories:.*to abort:", 660)
        Expect.enter(connection, "1")
        RHUIManager.proceed_without_check(connection)
        RHUIManager.quit(connection, "", 180)

    @staticmethod
    def add_rh_repo_by_product(connection, productlist):
        '''
        add a new Red Hat content repository (By Product)
        '''
        RHUIManager.screen(connection, "repo")
        Expect.enter(connection, "a")
        Expect.expect(connection, "Import Repositories:.*to abort:", 660)
        Expect.enter(connection, "2")
        RHUIManager.select(connection, productlist)
        RHUIManager.proceed_with_check(connection,
                                       "The following products will be deployed:",
                                       productlist)
        RHUIManager.quit(connection)

    @staticmethod
    def add_rh_repo_by_repo(connection, repolist):
        '''
        add a new Red Hat content repository (By Repository)
        '''
        RHUIManager.screen(connection, "repo")
        Expect.enter(connection, "a")
        Expect.expect(connection, "Import Repositories:.*to abort:", 660)
        Expect.enter(connection, "3")
        RHUIManager.select(connection, repolist)
        repolist_mod = list(repolist)
        for repo in repolist:
            # strip " (kind)"
            repo_stripped = re.sub(r" \([a-zA-Z]*\)$", "", repo)
            # strip " (version)" if present (if "(RPMs)" isn't there instead)
            repo_stripped = re.sub(r" \((?!RPMs)[a-zA-Z0-9_-]*\)$", "", repo_stripped)
            repolist_mod.append(repo_stripped)
        RHUIManager.proceed_with_check(connection,
                                       "The following product repositories will be deployed:",
                                       repolist_mod)
        RHUIManager.quit(connection)

    @staticmethod
    def add_container(connection, containername, containerid="", displayname="", credentials=""):
        '''
        add a new Red Hat container
        '''
        default_registry = Helpers.get_registry_url("default", connection)
        # if the credentials parameter is supplied, it's supposed to be a list containing:
        #   0 - registry hostname if not using the default one
        #   1 - username (if required; the default registry requires the RH (CCSP) login)
        #   2 - password (if required)
        # do NOT supply them if they're in rhui-tools.conf and you want to use the default registry;
        # this method will fail otherwise, because it will expect rhui-manager to ask for them
        RHUIManager.screen(connection, "repo")
        Expect.enter(connection, "ac")
        Expect.expect(connection, "Specify URL of registry .*:")
        if credentials and credentials[0]:
            registry = credentials[0]
            Expect.enter(connection, registry)
        else:
            registry = default_registry
            Expect.enter(connection, "")
        Expect.expect(connection, "Name of the container in the registry:")
        Expect.enter(connection, containername)
        Expect.expect(connection, "Unique ID for the container .*]", 60)
        Expect.enter(connection, containerid)
        Expect.expect(connection, "Display name for the container.*]:")
        Expect.enter(connection, displayname)
        # login & password provided, or a non-default registry specified
        if credentials or registry != default_registry:
            Expect.expect(connection, "Registry username:")
            if len(credentials) > 2:
                Expect.enter(connection, credentials[1])
                Expect.expect(connection, "Registry password:")
                Expect.enter(connection, credentials[2])
            else:
                Expect.enter(connection, "")
        if not containerid:
            containerid = Util.safe_pulp_repo_name(containername)
        if not displayname:
            displayname = Util.safe_pulp_repo_name(containername)
        RHUIManager.proceed_with_check(connection,
                                       "The following container will be added:",
                                       ["Registry URL: " + registry,
                                        "Container Id: " + containerid,
                                        "Display Name: " + displayname,
                                        "Upstream Container Name: " + containername])
        RHUIManager.quit(connection)

    @staticmethod
    def list(connection):
        '''
        list repositories
        '''
        RHUIManager.screen(connection, "repo")
        Expect.enter(connection, "l")
        # eating prompt!!
        pattern = re.compile(r'l\r\n(.*)\r\n-+\r\nrhui\s* \(repo\)\s* =>',
                             re.DOTALL)
        ret = Expect.match(connection, pattern, grouplist=[1])[0]
        reslist = map(str.strip, str(ret).splitlines())
        repolist = []
        for line in reslist:
            if line in ["",
                        "Custom Repositories",
                        "Red Hat Repositories",
                        "Container",
                        "Yum",
                        "No repositories are currently managed by the RHUI"]:
                continue
            repolist.append(line)
        Expect.enter(connection, 'q')
        return repolist

    @staticmethod
    def get_repo_version(connection, reponame):
        '''
        get repo version
        '''
        repolist = RHUIManagerRepo.list(connection)
        # delete escape back slash from the reponame
        reponame = reponame.replace("\\", "")
        # get full repo name with its version from the list of all repos
        full_reponame = next((s for s in repolist if reponame in s), None)
        #return full_reponame
        # get its version
        repo_version = re.sub(r'^.*\((.*?)\)[^\(]*$', r'\g<1>', full_reponame)

        return repo_version

    @staticmethod
    def delete_repo(connection, repolist):
        '''
        delete a repository from the RHUI
        '''
        RHUIManager.screen(connection, "repo")
        Expect.enter(connection, "d")
        RHUIManager.select(connection, repolist)
        RHUIManager.proceed_without_check(connection)
        RHUIManager.quit(connection)

    @staticmethod
    def delete_all_repos(connection):
        '''
        delete all repositories from the RHUI
        '''
        RHUIManager.screen(connection, "repo")
        Expect.enter(connection, "d")
        status = Expect.expect_list(connection,
                                    [(re.compile(".*No repositories.*", re.DOTALL), 1),
                                     (re.compile(".*Enter value.*", re.DOTALL), 2)],
                                    360)
        if status == 1:
            RHUIManager.quit(connection)
            return
        Expect.enter(connection, "a")
        Expect.expect(connection, "Enter value .*:")
        Expect.enter(connection, "c")
        RHUIManager.proceed_without_check(connection)
        # Wait until all repos are deleted
        RHUIManager.quit(connection, "", 360)
        while RHUIManagerRepo.list(connection):
            time.sleep(10)

    @staticmethod
    def upload_content(connection, repolist, path):
        '''
        upload content to a custom repository
        '''
        # Check whether "path" is a file or a directory.
        # If it is a directory, get a list of *.rpm files in it.
        path_type = Util.get_file_type(connection, path)
        if path_type == "regular file":
            content = [basename(path)]
        elif path_type == "directory":
            content = Util.get_rpms_in_dir(connection, path)
        else:
            # This should not happen. Getting here means that "path" is neither a file
            # nor a directory.
            # Anyway, going on with no content,
            # leaving it up to proceed_with_check() to handle this situation.
            content = []
        # Continue in rhui-manager.
        RHUIManager.screen(connection, "repo")
        Expect.enter(connection, "u")
        RHUIManager.select(connection, repolist)
        Expect.expect(connection, "will be uploaded:")
        Expect.enter(connection, path)
        RHUIManager.proceed_with_check(connection, "The following RPMs will be uploaded:", content)
        RHUIManager.quit(connection, timeout=60)

    @staticmethod
    def upload_remote_content(connection, repolist, url):
        '''
        upload content from a remote web site to a custom repository
        '''
        # Check whether "url" is an RPM file or a directory.
        # If it is a directory, get a list of *.rpm links in it.
        rpms = [basename(url)] if url.endswith(".rpm") else Util.get_rpm_links(url)
        # Continue in rhui-manager.
        RHUIManager.screen(connection, "repo")
        Expect.enter(connection, "ur")
        RHUIManager.select(connection, repolist)
        Expect.expect(connection, "will be uploaded:")
        Expect.enter(connection, url)
        if rpms:
            RHUIManager.proceed_with_check(connection, "The following RPMs will be uploaded:", rpms)
        RHUIManager.quit(connection, timeout=60)

    @staticmethod
    def check_for_package(connection, reponame, package):
        '''
        list packages in a repository
        '''
        RHUIManager.screen(connection, "repo")
        Expect.enter(connection, "p")

        RHUIManager.select_one(connection, reponame)
        Expect.expect(connection, r"\(blank line for no filter\):")
        Expect.enter(connection, package)

        pattern = re.compile(r'.*only\.\r\n(.*)\r\n-+\r\nrhui\s* \(repo\)\s* =>',
                             re.DOTALL)
        ret = Expect.match(connection, pattern, grouplist=[1])[0]
        reslist = map(str.strip, str(ret).splitlines())
        packagelist = []
        for line in reslist:
            if line == '':
                continue
            if line == 'Packages:':
                continue
            if line == 'No packages found that match the given filter.':
                continue
            if line == 'No packages in the repository.':
                continue
            packagelist.append(line)
        Expect.enter(connection, 'q')
        return packagelist

    @staticmethod
    def check_detailed_information(connection, repo):
        '''
        get repository properties
        '''
        RHUIManager.screen(connection, "repo")
        Expect.enter(connection, "i")
        RHUIManager.select(connection, [repo])
        pattern = re.compile(r".*(Name:.*)\r\n\r\n-+\r\nrhui\s* \(repo\)\s* =>", re.DOTALL)
        all_lines = Expect.match(connection, pattern)[0].splitlines()
        Expect.enter(connection, "q")
        return Util.lines_to_dict(all_lines)
