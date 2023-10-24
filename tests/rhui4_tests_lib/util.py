""" Utility functions """

from configparser import ConfigParser
import os
import re
import tempfile
import urllib3

import certifi
from stitches.expect import Expect

from rhui4_tests_lib.conmgr import ConMgr

class Util():
    '''
    Utility functions for instances
    '''
    @staticmethod
    def uncolorify(instr):
        """ Remove colorification """
        res = instr.replace("\x1b", "")
        res = res.replace("[91m", "")
        res = res.replace("[92m", "")
        res = res.replace("[93m", "")
        res = res.replace("[95m", "")
        res = res.replace("[96m", "")
        res = res.replace("[97m", "")
        res = res.replace("[0m", "")
        return res

    @staticmethod
    def remove_amazon_rhui_conf_rpm(connection):
        '''
        Remove Amazon RHUI config rpm (owning /usr/sbin/choose_repo.py) from instance
        downlad the rpm first, though, so the configuration can be restored if needed
        (but don't fail if the download is unsuccessful, just try your luck)
        note that more than one rpm can actually own the file, typically on beta AMIs
        the rpm(s) is/are saved in /root
        '''
        Expect.expect_retval(connection,
                             "file=/usr/sbin/choose_repo.py; " +
                             "if [ -f $file ]; then" +
                             "  package=`rpm -qf --queryformat '%{NAME} ' $file`;" +
                             "  yumdownloader $package;" +
                             "  rpm -e $package;" +
                             "fi",
                             timeout=60)

    @staticmethod
    def disable_beta_repos(connection):
        '''
        Disable RHEL Beta repos that might have been created during the deployment
        if testing RHUI on/with an unreleased compose.
        '''
        Expect.expect_retval(connection,
                             "if [ -f /etc/yum.repos.d/rhel*_beta.repo ]; then" +
                             "  yum-config-manager --disable 'rhel*_beta*';" +
                             "fi")

    @staticmethod
    def remove_rpm(connection, rpmlist, pedantic=False):
        '''
        Remove RPMs from a remote host.
        If "pedantic", fail if the rpmlist contains one or more packages that are not installed.
        Otherwise, ignore such packages, remove whatever *is* installed (if anything).
        '''
        installed = [rpm for rpm in rpmlist if connection.recv_exit_status("rpm -q " + rpm) == 0]
        if installed:
            Expect.expect_retval(connection, "rpm -e " + " ".join(installed), timeout=60)
        if pedantic and installed != rpmlist:
            raise OSError(f"{set(rpmlist) - set(installed)}: not installed, could not remove")

    @staticmethod
    def install_pkg_from_rhua(rhua_connection, target_connection, pkgpath, allow_update=False):
        '''
        Transfer a package from the RHUA to the target node and install it there.
        '''
        # the package can be an RPM file to install/update using rpm -- typically a RHUI client
        # configuration RPM,
        # or it can be a gzipped tarball -- any content
        supported_extensions = {"RPM": ".rpm", "tar": ".tar.gz"}
        target_file_name = "/tmp/" + os.path.basename(pkgpath)
        if pkgpath.endswith(supported_extensions["RPM"]):
            option = "U" if allow_update else "i"
            cmd = f"rpm -{option} {target_file_name}"
        elif pkgpath.endswith(supported_extensions["tar"]):
            cmd = "tar xf" + target_file_name
        else:
            raise ValueError(f"{pkgpath} has an unsupported file extension. " +
                             f"Supported extensions are: {list(supported_extensions.values())}")

        local_file = tempfile.NamedTemporaryFile(delete=False)
        local_file.close()

        rhua_connection.sftp.get(pkgpath, local_file.name)
        target_connection.sftp.put(local_file.name, target_file_name)

        Expect.expect_retval(target_connection, cmd)

        os.unlink(local_file.name)
        Expect.expect_retval(target_connection, "rm -f " + target_file_name)

    @staticmethod
    def get_saved_password(connection, creds_file="/etc/rhui/rhui-subscription-sync.conf"):
        '''
        Read rhui-manager password from the rhui-subscription-sync configuration file
        '''
        creds_cfg = ConfigParser()
        _, stdout, _ = connection.exec_command("cat " + creds_file)
        creds_cfg.read_file(stdout)
        return creds_cfg.get("auth", "password") if creds_cfg.has_section("auth") else None

    @staticmethod
    def get_rhel_version(connection):
        '''
        get RHEL X.Y version (dict with two integers representing the major and minor version)
        '''
        _, stdout, _ = connection.exec_command(r"egrep -o '[0-9]+\.[0-9]+' /etc/redhat-release")
        version = stdout.read().decode().strip().split(".")
        try:
            version_dict = {"major": int(version[0]), "minor": int(version[1])}
            return version_dict
        except ValueError:
            return None

    @staticmethod
    def get_arch(connection):
        '''
        get machine architecture; note that ARM64 is presented as aarch64.
        '''
        _, stdout, _ = connection.exec_command("arch")
        arch = stdout.read().decode().strip()
        return arch

    @staticmethod
    def format_repo(name, version="", kind=""):
        '''
        helper method to put together a repo name, version, and kind
        the way RHUI repos are called in rhui-manager
        '''
        repo = name
        if version:
            repo += f" ({version})"
        if kind:
            repo += f" ({kind})"
        return repo

    @staticmethod
    def get_rpms_in_dir(connection, directory):
        '''
        return a list of RPM files in the directory
        '''
        _, stdout, _ = connection.exec_command(f"cd {directory} && ls -w1 *.rpm")
        rpms = stdout.read().decode().splitlines()
        return rpms

    @staticmethod
    def get_rpm_links(url):
        '''
        return a list of RPM files linked from an HTML page (e.g. a directory listing)
        '''
        poolmgr = urllib3.PoolManager(cert_reqs="CERT_REQUIRED", ca_certs=certifi.where())
        try:
            request = poolmgr.request("GET", url)
        except (urllib3.exceptions.SSLError, urllib3.exceptions.MaxRetryError):
            # if the URL can't be reached, consider it an empty page
            return []
        content = request.data.decode()
        rpmlinks = re.findall(r"<a href=\"[^\"]*\.rpm", content)
        rpms = [rpmlink.replace("<a href=\"", "") for rpmlink in rpmlinks]
        return rpms

    @staticmethod
    def check_package_url(connection, package, path=""):
        '''
        verify that the package is available from the RHUI (and not from an unwanted repo)
        '''
        # The name of the test package may contain characters which must be escaped in REs.
        # In modern pulp-rpm versions, packages are in .../Packages/<first letter (lowercase)>/,
        # and the URL can be .../os/...NVR or .../os//...NVR, so let's tolerate anything between
        # the path and the package name. The path is optional, though; if you don't know it or
        # don't care about it, call this method with the mandatory arguments only.
        package_escaped = re.escape(package)
        Expect.ping_pong(connection,
                         "yumdownloader --url " + package_escaped,
                         f"https://{ConMgr.get_cds_lb_hostname()}" +
                         f"/pulp/content/{path}.*{package_escaped}")

    @staticmethod
    def cert_expired(connection, cert, seconds=0):
        '''
        check if the certificate has already expired or will expire, return true if so
        '''
        file_exists = connection.recv_exit_status("test -f " + cert) == 0
        if not file_exists:
            raise OSError(cert + " does not exist")
        cmd = f"openssl x509 -noout -in {cert} -checkend {seconds}"
        return connection.recv_exit_status(cmd) == 1

    @staticmethod
    def fetch(connection, source, dest):
        '''
        fetch a file from the remote host
        '''
        connection.sftp.get(source, dest)

    @staticmethod
    def safe_pulp_repo_name(name):
        '''
        replace prohibited characters in repo names with safe ones (as per rhui-manager)
        '''
        return name.replace("/", "_").replace(".", "_")

    @staticmethod
    def mktemp_remote(connection, extension=""):
        '''
        create a temporary file on the remote host and return its path
        '''
        _, stdout, _ = connection.exec_command("mktemp /tmp/XXXX" + extension)
        path = stdout.read().decode().strip()
        return path

    @staticmethod
    def get_file_type(connection, path):
        '''
        What kind of file is it? A regular file, a directory, symlink, ... or None.
        '''
        _, stdout, _ = connection.exec_command(f"stat -c %F '{path}'")
        ftype = stdout.read().decode().strip()
        return ftype or None

    @staticmethod
    def lines_to_dict(lines):
        '''
        takes one or more lines with a colon and returns a dict with keys: values,
        where keys are sanitized first (spaces removed, letters in lowercase),
        and values are left-stripped
        '''
        info_pair_list = [line.split(":", 1) for line in lines]
        info_dict = {i[0].replace(" ", "").lower(): i[1].lstrip() for i in info_pair_list}
        return info_dict

    @staticmethod
    def is_logged_in(connection):
        '''
        returns true if login credentials exist, or false otherwise
        '''
        cmd = "test -f /root/.rhui/http-localhost:24817/cookies.txt"
        return connection.recv_exit_status(cmd) == 0

    @staticmethod
    def fips_enabled(connection):
        '''
        returns true if FIPS is enabled on the remote host, or false otherwise
        '''
        _, stdout, _ = connection.exec_command("cat /proc/sys/crypto/fips_enabled")
        status = int(stdout.read().decode().strip())
        return status == 1
