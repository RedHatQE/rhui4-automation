""" RHUIManagerCLI functions """

from os.path import join
import re
import time

import nose

from stitches.expect import Expect

from rhui4_tests_lib.helpers import Helpers
from rhui4_tests_lib.util import Util

DEFAULT_ENT_CERT = "/tmp/extra_rhui_files/rhcert.pem"

def _get_repo_status(connection, repo_name):
    '''
    get the status of the given repository
    '''
    _, stdout, _ = connection.exec_command("rhui-manager status")
    lines = stdout.read().decode().splitlines()
    status = None
    for line in lines:
        if line.startswith(repo_name):
            status = Util.uncolorify(line).split()[-1]
            break
    if status:
        return status
    raise RuntimeError("Invalid repository name.")

def _wait_till_repo_synced(connection, repo_id, expected_status="SUCCESS"):
    '''
    wait until the specified repo is synchronized
    '''
    repo_name = RHUIManagerCLI.repo_info(connection, repo_id)["name"]
    repo_status = _get_repo_status(connection, repo_name)
    while repo_status in ["Never", "SCHEDULED", "RUNNING"]:
        time.sleep(10)
        repo_status = _get_repo_status(connection, repo_name)
    nose.tools.assert_equal(repo_status, expected_status)

def _ent_list(stdout):
    '''
    return a list of entitlements based on the given output (produced by cert upload/info)
    '''
    response = stdout.read().decode()
    lines = list(map(str.lstrip, str(response).splitlines()))
    # there should be a header in the output, with status
    try:
        status = Util.uncolorify(lines[2])
    except IndexError:
        raise RuntimeError(f"Unexpected output: {response}") from None
    if status == "Valid":
        # only pay attention to lines containing products
        # (which are non-empty lines below the header, without expriration and file name info)
        entitlements = [line for line in lines[3:] if line and not line.startswith("Expiration")]
        return entitlements
    if status in ("Expired", "No Red Hat entitlements found."):
        # return an empty list
        return []
    # if we're here, there's another problem with the entitlements/output
    raise RuntimeError(f"An error occurred: {response}")

class CustomRepoAlreadyExists(Exception):
    '''
    Raised if a custom repo with this ID already exists
    '''

class CustomRepoGpgKeyNotFound(Exception):
    '''
    Raised if the GPG key path to use with a custom repo is invalid
    '''

class RHUIManagerCLI():
    '''
    The RHUI manager command-line interface (shell commands to control the RHUA).
    '''
    @staticmethod
    def cert_upload(connection, cert=DEFAULT_ENT_CERT):
        '''
        upload a new or updated Red Hat content certificate and return a list of valid entitlements
        '''
        # get the complete output and split it into (left-stripped) lines
        _, stdout, _ = connection.exec_command(f"rhui-manager cert upload --cert {cert}")
        if cert == DEFAULT_ENT_CERT:
            Helpers.copy_repo_mappings(connection)
        return _ent_list(stdout)

    @staticmethod
    def cert_info(connection):
        '''
        return a list of valid entitlements (if any)
        '''
        _, stdout, _ = connection.exec_command("rhui-manager cert info")
        return _ent_list(stdout)

    @staticmethod
    def repo_unused(connection, by_repo_id=False):
        '''
        return a list of repos that are entitled but not added to RHUI
        '''
        # beware: if using by_repo_id, products will be followed by one or more repo IDs
        # on separate lines that start with two spaces
        cmd = "rhui-manager repo unused"
        if by_repo_id:
            cmd += " --by_repo_id"
        _, stdout, _ = connection.exec_command(cmd)
        response = stdout.read().decode().splitlines()
        # return everything but the first four lines, which contain headers
        return response[4:]

    @staticmethod
    def repo_add(connection, repo):
        '''
        add a repo specified by its product name
        '''
        Expect.ping_pong(connection,
                         "rhui-manager repo add --product_name \"" + repo + "\"",
                         "Successfully added")

    @staticmethod
    def repo_add_by_repo(connection, repo_ids, sync_now=False, expect_trouble=False):
        '''
        add a list of repos specified by their IDs
        '''
        cmd = "rhui-manager repo add_by_repo --repo_ids " + ",".join(repo_ids)
        if sync_now:
            cmd += " --sync_now"
        Expect.expect_retval(connection,
                             cmd,
                             0 if not expect_trouble else 1,
                             timeout=600)
        if sync_now:
            for repo_id in repo_ids:
                _wait_till_repo_synced(connection, repo_id)

    @staticmethod
    def repo_add_by_file(connection, repo_file, sync_now=False, expect_trouble=False):
        '''
        add a list of repos specified in an input file
        '''
        cmd = "rhui-manager repo add_by_file --file " + repo_file
        if sync_now:
            cmd += " --sync_now"
        Expect.expect_retval(connection,
                             cmd,
                             0 if not expect_trouble else 1,
                             timeout=600)
        if sync_now:
            repo_ids = Helpers.get_repos_from_yaml(connection, repo_file)
            for repo_id in repo_ids:
                _wait_till_repo_synced(connection, repo_id)

    @staticmethod
    def repo_list(connection, ids_only=False, redhat_only=False, delimiter=""):
        '''
        show repos; can show IDs only, RH repos only, and accepts a delimiter
        '''
        cmd = "rhui-manager repo list"
        if ids_only:
            cmd += " --ids_only"
        if redhat_only:
            cmd += " --redhat_only"
        if delimiter:
            cmd += " --delimiter " + delimiter
        _, stdout, _ = connection.exec_command(cmd)
        response = stdout.read().decode().strip()
        return response

    @staticmethod
    def repo_sync(connection, repo_id, expected_status="SUCCESS"):
        '''
        sync a repo
        '''
        Expect.ping_pong(connection,
                         "rhui-manager repo sync --repo_id " + repo_id,
                         "successfully scheduled for the next available timeslot")
        _wait_till_repo_synced(connection, repo_id, expected_status=expected_status)

    @staticmethod
    def repo_info(connection, repo_id):
        '''
        return a dictionary containing information about the given repo
        '''
        _, stdout, _ = connection.exec_command(f"rhui-manager repo info --repo_id {repo_id}")
        all_lines = stdout.read().decode().splitlines()
        if all_lines[0] == f"repository {repo_id} was not found":
            raise RuntimeError("Invalid repository ID.")
        return Util.lines_to_dict(all_lines)

    @staticmethod
    def repo_create_custom(connection,
                           repo_id,
                           path="",
                           display_name="",
                           redhat_content=False,
                           protected=False,
                           gpg_public_keys=""):
        '''
        create a custom repo
        '''
        # compose the command
        cmd = f"rhui-manager repo create_custom --repo_id {repo_id}"
        if path:
            cmd += f" --path {path}"
        if display_name:
            cmd += f" --display_name '{display_name}'"
        if redhat_content:
            cmd += " --redhat_content"
        if protected:
            cmd += " --protected"
        if gpg_public_keys:
            cmd += f" --gpg_public_keys {gpg_public_keys}"
        # get a list of invalid GPG key files (will be implicitly empty if that option isn't used)
        key_list = gpg_public_keys.split(",")
        bad_keys = [key for key in key_list if connection.recv_exit_status(f"test -f {key}")]
        # possible output (more or less specific):
        out = {"missing_options": "Usage:",
               "invalid_id": "Only.*valid in a repository ID",
               "repo_exists": f"A repository with ID \"{repo_id}\" already exists",
               "bad_gpg": "The following files are unreadable:\r\n\r\n" + "\r\n".join(bad_keys),
               "success": f"Successfully created repository \"{display_name or repo_id}\""}
        # run the command and see what happens
        Expect.enter(connection, cmd)
        state = Expect.expect_list(connection,
                                   [(re.compile(f".*{out['missing_options']}.*", re.DOTALL), 1),
                                    (re.compile(f".*{out['invalid_id']}.*", re.DOTALL), 2),
                                    (re.compile(f".*{out['repo_exists']}.*", re.DOTALL), 3),
                                    (re.compile(f".*{out['bad_gpg']}.*", re.DOTALL), 4),
                                    (re.compile(f".*{out['success']}.*", re.DOTALL), 5)])
        if state in (1, 2):
            raise ValueError("the given repo ID is unusable")
        if state == 3:
            raise CustomRepoAlreadyExists()
        if state == 4:
            raise CustomRepoGpgKeyNotFound()
        # make sure rhui-manager reported success
        nose.tools.assert_equal(state, 5)

    @staticmethod
    def repo_delete(connection, repo_id):
        '''
        delete the given repo
        '''
        Expect.expect_retval(connection, f"rhui-manager repo delete --repo_id {repo_id}")

    @staticmethod
    def repo_add_errata(connection, repo_id, updateinfo):
        '''
        associate errata metadata with a repo
        '''
        Expect.expect_retval(connection,
                             "rhui-manager repo add_errata " +
                             f"--repo_id {repo_id} --updateinfo '{updateinfo}'",
                             timeout=120)

    @staticmethod
    def repo_add_comps(connection, repo_id, comps):
        '''
        associate comps metadata with a repo
        '''
        Expect.expect_retval(connection,
                             "rhui-manager repo add_comps " +
                             f"--repo_id {repo_id} --comps {comps}",
                             timeout=120)
        # better export the repo in case a previously added comps file for this repo is diferent
        RHUIManagerCLI.repo_export(connection, repo_id)

    @staticmethod
    def repo_export(connection, repo_id):
        '''
        export a repository to the filesystem
        '''
        Expect.expect_retval(connection, f"rhui-manager repo export --repo_id {repo_id}")

    @staticmethod
    def packages_list(connection, repo_id):
        '''
        return a list of packages present in the repo
        '''
        _, stdout, _ = connection.exec_command(f"rhui-manager packages list --repo_id {repo_id}")
        return stdout.read().decode().splitlines()

    @staticmethod
    def packages_remote(connection, repo_id, url):
        '''
        upload packages from a remote URL to a custom repository
        '''
        cmd = f"rhui-manager packages remote --repo_id {repo_id} --url {url}"
        Expect.expect_retval(connection, cmd)

    @staticmethod
    def packages_upload(connection, repo_id, path):
        '''
        upload a package or a directory with packages to the custom repo
        '''
        cmd = f"rhui-manager packages upload --repo_id {repo_id} --packages '{path}'"
        Expect.expect_retval(connection, cmd)

    @staticmethod
    def client_labels(connection):
        '''
        view repo labels in the RHUA; returns a list of the labels
        '''
        _, stdout, _ = connection.exec_command("rhui-manager client labels")
        labels = stdout.read().decode().splitlines()
        return labels

    @staticmethod
    def client_cert(connection, repo_labels, name, days, directory):
        '''
        generate an entitlement certificate
        '''
        Expect.ping_pong(connection,
                         f"rhui-manager client cert --repo_label {','.join(repo_labels)} " +
                         f"--name {name} --days {str(days)} --dir {directory}",
                         "Entitlement certificate created at " + join(directory, name),
                         timeout=60)

    @staticmethod
    def client_rpm(connection, certdata, rpmdata, directory, unprotected_repos=None, proxy=""):
        '''
        generate a client configuration RPM
        The certdata argument must be a list, and two kinds of data are supported:
          * key path and cert path (full paths, starting with "/"), or
          * one or more repo labels and optionally an integer denoting the number of days the cert
            will be valid for; if unspecified, rhui-manager will use 365. In this case,
            a certificate will be generated on the fly.
        The rpmdata argument must be a list with one, two or three strings:
          * package name: the name for the RPM
          * package version: string denoting the version; if unspecified, rhui-manager will use 2.0
          * package release: string denoting the release; if unspecified, rhui-manager will use 1
        '''
        cmd = "rhui-manager client rpm"
        if certdata[0].startswith("/"):
            cmd += f" --private_key {certdata[0]} --entitlement_cert {certdata[1]}"
        else:
            cmd += " --cert"
            if isinstance(certdata[-1], int):
                cmd += f" --days {certdata.pop()}"
            cmd += " --repo_label " + ','.join(certdata)
        cmd += f" --rpm_name {rpmdata[0]}"
        if len(rpmdata) > 1:
            cmd += f" --rpm_version {rpmdata[1]}"
            if len(rpmdata) > 2:
                cmd += f" --rpm_release {rpmdata[2]}"
            else:
                rpmdata.append("1")
        else:
            rpmdata.append("2.0")
            rpmdata.append("1")
        cmd += f" --dir {directory}"
        if unprotected_repos:
            cmd += " --unprotected_repos " + ",".join(unprotected_repos)
        if proxy:
            cmd += " --proxy " + proxy
        Expect.ping_pong(connection,
                         cmd,
                         f"Location: {directory}/{rpmdata[0]}-{rpmdata[1]}/build/RPMS/noarch/" +
                         f"{rpmdata[0]}-{rpmdata[1]}-{rpmdata[2]}.noarch.rpm")

    @staticmethod
    def client_content_source(connection, certdata, rpmdata, directory):
        '''
        generate an alternate source config rpm
        (very similar to client_rpm() -- see the usage described there)
        '''
        cmd = "rhui-manager client content_source"
        if certdata[0].startswith("/"):
            cmd += f" --private_key {certdata[0]} --entitlement_cert {certdata[1]}"
        else:
            cmd += " --cert"
            if isinstance(certdata[-1], int):
                cmd += " --days " + certdata.pop()
            cmd += " --repo_label " + ",".join(certdata)
        cmd += " --rpm_name " + rpmdata[0]
        if len(rpmdata) > 1:
            cmd += " --rpm_version " + rpmdata[1]
        else:
            rpmdata.append("2.0")
        cmd += " --dir " + directory
        Expect.ping_pong(connection,
                         cmd,
                         f"Location: {directory}/{rpmdata[0]}-{rpmdata[1]}/build/RPMS/noarch/" +
                         f"{rpmdata[0]}-{rpmdata[1]}-1.noarch.rpm")

    @staticmethod
    def logout(connection):
        '''
        log out from rhui-manager
        '''
        Expect.enter(connection, "rhui-manager --logout")
