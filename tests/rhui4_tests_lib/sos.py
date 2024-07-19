"""Sos in RHUI"""

import re

import nose

class Sos():
    """Sos handling for RHUI"""
    @staticmethod
    def run(connection):
        """run the sosreport command"""
        # now run sosreport with only the relevant plug-ins enabled, return the tarball location
        _, stdout, _ = connection.exec_command("sos report -o nginx,pulpcore,rhui --batch")
        lines = stdout.read().decode().splitlines()
        # return the line below the one which indicates that the following line contains the path
        see_path = False
        for line in lines:
            if see_path:
                return line.strip()
            if line.startswith("Your sosreport"):
                # process the line in the next iteration
                see_path = True
        # the in unlikely event that the output doesn't look as expected, return None
        return None

    @staticmethod
    def check_files_in_archive(connection, filelist, archive):
        """check if the files in the given filelist are collected in the given archive"""
        # make sure the archive exists
        if connection.recv_exit_status("test -f " + archive):
            raise OSError(archive + " does not exist")
        # read the contents of the archive, and check if each file from the filelist is there
        # must strip the path in front of the real root directory; the archive contains files like:
        # sosreport-HOST-DATE-HASH/etc/rhui/rhui-tools.conf
        # while the given filelist contains actual paths like /etc/rhui/rhui-tools.conf
        pattern = "^[^/]+"
        _, stdout, _ = connection.exec_command("tar tf " + archive)
        archive_filelist_raw = stdout.read().decode().splitlines()
        archive_filelist = [re.sub(pattern, "", path) for path in archive_filelist_raw]
        missing_files = [f for f in filelist if f not in archive_filelist]
        nose.tools.ok_(not missing_files,
                       msg=f"Not found in the archive: {missing_files}")

    @staticmethod
    def is_obfuscated(connection, match, path, archive):
        """check if the value of the option in the file (path) in the archive is obfuscated"""
        # make sure the archive exists
        if connection.recv_exit_status("test -f " + archive):
            raise OSError(archive + " does not exist")
        # print the file from the archive
        cmd = f"tar xf {archive} --wildcards 'sosreport-*{path}' -O"
        _, stdout, _ = connection.exec_command(cmd)
        lines = stdout.read().decode().splitlines()
        problems = [line for line in lines if match in line and not line.endswith("********")]
        nose.tools.ok_(not problems, msg=f"Problematic lines: {problems}")
