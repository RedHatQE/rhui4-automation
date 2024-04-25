"""Functions for Yum Commands and Repodata Handling"""

import time

from stitches.expect import Expect
import xmltodict

from rhui4_tests_lib.rhuimanager_cmdline import RHUIManagerCLI

class Yummy():
    """various functions to test yum commands and repodata"""
    @staticmethod
    def repodata_location(connection, repo, datatype):
        """return the path to the repository file (on the RHUA) of the given data type"""
        # data types are : filelists, group, primary, updateinfo etc.
        # export the repo to make sure the symlinks exist
        RHUIManagerCLI.repo_export(connection, repo)
        time.sleep(3)
        base_path = "/var/lib/rhui/remote_share/symlinks/pulp/content"
        relative_path = RHUIManagerCLI.repo_info(connection, repo)["relativepath"]
        repodata_file = f"{base_path}/{relative_path}/repodata/repomd.xml"
        _, stdout, _ = connection.exec_command(f"cat {repodata_file}")
        repodata = xmltodict.parse(stdout.read())
        location_list = [data["location"]["@href"] for data in repodata["repomd"]["data"] \
                         if data["@type"] == datatype]
        if location_list:
            location = location_list[0]
            wanted_file = f"{base_path}/{relative_path}/{location}"
            return wanted_file
        return None

    @staticmethod
    def comps_xml_grouplist(connection, comps_xml, uservisible_only=True):
        """return a sorted list of yum groups in the given comps.xml file"""
        # by default, only groups with <uservisible>true</uservisible> are taken into account,
        # but those "invisible" can be included too, if requested
        _, stdout, _ = connection.exec_command(f"cat {comps_xml}")
        comps = xmltodict.parse(stdout.read())
        # in a multi-group comps.xml file, the groups are in a list,
        # whereas in a single-group file, the group is just a string
        if isinstance(comps["comps"]["group"], list):
            # get a list of name-visibility pairs first
            group_info = [[group["name"][0], group["uservisible"].lower() == "true"] \
                          for group in comps["comps"]["group"]]
            if uservisible_only:
                grouplist = [group[0] for group in group_info if group[1]]
            else:
                grouplist = [group[0] for group in group_info]
            return sorted(grouplist)
        if uservisible_only:
            if comps["comps"]["group"]["uservisible"].lower() == "true":
                return [comps["comps"]["group"]["name"][0]]
            return []
        return [comps["comps"]["group"]["name"][0]]

    @staticmethod
    def comps_xml_langpacks(connection, comps_xml):
        """return a list of name, package tuples for the langpacks from the given comps.xml file"""
        # or None if there are no langpacks
        _, stdout, _ = connection.exec_command(f"cat {comps_xml}")
        comps = xmltodict.parse(stdout.read())
        if "langpacks" in comps["comps"] and comps["comps"]["langpacks"]:
            names_pkgs = [(match["@name"], match["@install"]) \
                          for match in comps["comps"]["langpacks"]["match"]]
            return names_pkgs
        return None

    @staticmethod
    def grouplist(connection):
        """return a sorted list of yum groups available to the client"""
        # first clean metadata, which may contain outdated information
        Expect.expect_retval(connection, "yum clean all")
        # fetch the complete output from the command
        _, stdout, _ = connection.exec_command("yum grouplist")
        all_lines = stdout.read().decode().splitlines()
        # yum groups are on lines that start with three spaces
        grouplist = [line.strip() for line in all_lines if line.startswith("   ")]
        return sorted(grouplist)

    @staticmethod
    def group_packages(connection, group):
        """return a sorted list of packages available to the client in the given yum group"""
        # fetch the complete output from the command
        _, stdout, _ = connection.exec_command(f"yum groupinfo '{group}'")
        all_lines = stdout.read().decode().splitlines()
        # packages are on lines that start with three spaces
        packagelist = [line.strip() for line in all_lines if line.startswith("   ")]
        # in addition, the package names can start with +, -, or = depending on the status
        # (see man yum -> groups)
        # so, let's remove such signs if they're present
        packagelist = [pkg[1:] if pkg[0] in ["+", "-", "="] else pkg for pkg in packagelist]
        return sorted(packagelist)

    @staticmethod
    def repolist(connection, alll=False, enabled=True, disabled=False):
        """return a list of yum repositories, only enabled by default"""
        cmd = "yum -q repolist"
        if alll:
            cmd += " all"
        elif disabled:
            cmd += " disabled"
        elif enabled:
            pass
        else:
            raise ValueError("You cannot turn all options off.")
        _, stdout, _ = connection.exec_command(cmd)
        raw_output = stdout.read().decode().splitlines()
        repos = [line.split()[0] for line in raw_output if not line.startswith("repo ")]
        # on RHEL 7, the repos are in fact like .../7Server/x86_64; strip that
        repos = [repo.split("/")[0] for repo in repos]
        return repos

    @staticmethod
    def install(connection, packages, gpgcheck=True, timeout=20, expect_trouble=False):
        """return a list of yum repositories, only enabled by default"""
        cmd = "yum -y install "
        cmd += " ".join(packages)
        if not gpgcheck:
            cmd += " --nogpgcheck"
        Expect.expect_retval(connection, cmd, 1 if expect_trouble else 0, timeout)

    @staticmethod
    def downgrade(connection, packages, gpgcheck=True, timeout=20, expect_trouble=False):
        """return a list of yum repositories, only enabled by default"""
        cmd = "yum -y downgrade "
        cmd += " ".join(packages)
        if not gpgcheck:
            cmd += " --nogpgcheck"
        Expect.expect_retval(connection, cmd, 1 if expect_trouble else 0, timeout)

    @staticmethod
    def is_up_to_date(connection, packages=None, expect_update=False):
        """check for updates for the given packages (or any updates); no updates: return True"""
        cmd = "yum check-update "
        cmd += " ".join(packages) if packages else ""
        return connection.recv_exit_status(cmd, timeout=60) == (100 if expect_update else 0)

    @staticmethod
    def module_list(connection, package):
        """return information module streams for the package, exactly as presented by dnf"""
        cmd = f"dnf -q module list {package}"
        _, stdout, _ = connection.exec_command(cmd)
        raw_module_list_output = stdout.read().decode()
        return raw_module_list_output
