"""Functions for the RHUI Configuration"""

from configparser import ConfigParser
import yaml

from stitches.expect import Expect

from rhui4_tests_lib.incontainers import RhuiinContainers

BACKUP_EXT = ".bak"
RHUI_CFG = "/etc/rhui/rhui-tools.conf"
RHUI_CFG_BAK = RHUI_CFG + BACKUP_EXT
ANSWERS = "/root/.rhui/answers.yaml"
ANSWERS_BAK = ANSWERS + BACKUP_EXT

RHUI_ROOT = "/var/lib/rhui/remote_share"
LEGACY_CA_DIR = "/etc/pki/rhui/legacy"

class Config():
    """reading from and writing to RHUI configuration files"""
    @staticmethod
    def get_credentials(connection, site="rh"):
        '''
        get the user name and password for the given site from the RHUA
        '''
        path = "/tmp/extra_rhui_files/credentials.conf"
        creds_cfg = ConfigParser()
        _, stdout, _ = connection.exec_command(f"cat {path}")
        creds_cfg.read_file(stdout)
        if not creds_cfg.has_section(site):
            raise RuntimeError(f"section {site} does not exist in {path}")
        if not creds_cfg.has_option(site, "username"):
            raise RuntimeError(f"username does not exist inside {site} in {path}")
        if not creds_cfg.has_option(site, "password"):
            raise RuntimeError(f"password does not exist inside {site} in {path}")
        credentials = [creds_cfg.get(site, "username"), creds_cfg.get(site, "password")]
        return credentials

    @staticmethod
    def get_from_answers(connection, option, answers_file=ANSWERS):
        """get the value of the given option from the answers file"""
        _, stdout, _ = connection.exec_command(f"cat {answers_file}")
        answers = yaml.safe_load(stdout)
        answer = answers["rhua"][option]
        return answer

    @staticmethod
    def get_from_rhui_tools_conf(connection, section, option):
        """get the value of the given option from the given section in RHUI configuration"""
        # raises standard configparser exceptions on failures
        rhuicfg = ConfigParser()
        _, stdout, _ = connection.exec_command(f"cat {RHUI_CFG}")
        rhuicfg.read_file(stdout)
        return rhuicfg.get(section, option)

    @staticmethod
    def get_registry_url(site, connection=""):
        """get the URL for the given container registry or for the saved one (use "default" then)"""
        if site == "default":
            return Config.get_from_rhui_tools_conf(connection, "container", "registry_url")
        urls = {"rh": "https://registry.redhat.io",
                "quay": "https://quay.io",
                "gitlab": "https://registry.gitlab.com"}
        if site in urls:
            return urls[site]
        return None

    @staticmethod
    def set_registry_credentials(connection, site="rh", data="", backup=True, use_installer=False):
        """put container registry credentials into the RHUI configuration file"""
        # if "site" isn't in credentials.conf, then "data" is supposed to be:
        # [username, password, url], or just [url] if no authentication is to be used for "site";
        # first get the RHUI config file
        rhuicfg = ConfigParser()
        _, stdout, _ = connection.exec_command(f"cat {RHUI_CFG}")
        rhuicfg.read_file(stdout)
        # add the relevant config section if it's not there yet
        if not rhuicfg.has_section("container"):
            rhuicfg.add_section("container")
        # then get the credentials
        try:
            credentials = Config.get_credentials(connection, site)
            url = Config.get_registry_url(site)
            rhuicfg.set("container", "registry_url", url)
            rhuicfg.set("container", "registry_auth", "True")
        except RuntimeError:
            # the site isn't defined in the credentials file -> use the data passed to this method
            if len(data) == 3:
                rhuicfg.set("container", "registry_url", data[2])
                rhuicfg.set("container", "registry_auth", "True")
                credentials = data[:-1]
            elif len(data) == 1:
                rhuicfg.set("container", "registry_url", data[0])
                rhuicfg.set("container", "registry_auth", "False")
                credentials = False
            else:
                raise ValueError("the passed data is invalid") from None
        # if credentials are known, add them into the configuration
        if credentials:
            rhuicfg.set("container", "registry_username", credentials[0])
            rhuicfg.set("container", "registry_password", credentials[1])
        # otherwise, make sure the options don't exists in the configuration
        else:
            rhuicfg.remove_option("container", "registry_username")
            rhuicfg.remove_option("container", "registry_password")
        # back up the original config file (unless prevented)
        if backup:
            Config.backup_rhui_tools_conf(connection)
        # save (rewrite) the configuration file with the newly added credentials
        if use_installer:
            cmd = "rhui-installer --rerun"
            for item in ["url", "auth", "username", "password"]:
                cmd += f" --registry-{item} "
                cmd += rhuicfg.get("container", f"registry_{item}", fallback="\"\"")
            Expect.expect_retval(connection, cmd, timeout=600)
        else:
            stdin, _, _ = connection.exec_command(f"cat > {RHUI_CFG}")
            rhuicfg.write(stdin)

    @staticmethod
    def set_rhui_tools_conf(connection, section, option, value, backup=True):
        """set a configuration option in the RHUI tools configuration file"""
        rhuicfg = ConfigParser()
        _, stdout, _ = connection.exec_command(f"cat {RHUI_CFG}")
        rhuicfg.read_file(stdout)
        rhuicfg.set(section, option, value)
        # back up the original config file (unless prevented)
        if backup:
            Config.backup_rhui_tools_conf(connection)
        # save (rewrite) the configuration file
        stdin, _, _ = connection.exec_command(f"cat > {RHUI_CFG}")
        rhuicfg.write(stdin)

    @staticmethod
    def set_sync_policy(connection, policy_name, policy_type, backup=True):
        """set a sync policy to one of the available types"""
        # validate the input
        valid_names = {"default", "rpm", "source", "debug"}
        if policy_name not in valid_names:
            raise ValueError(f"Unsupported name: '{policy_name}'. Use one of: {valid_names}.")
        valid_types = {"immediate", "on_demand"}
        if policy_type not in valid_types:
            raise ValueError(f"Unsupported type: '{policy_type}'. Use one of: {valid_types}.")
        # set it
        Config.set_rhui_tools_conf(connection,
                                   "rhui",
                                   f"{policy_name}_sync_policy",
                                   policy_type,
                                   backup)

    @staticmethod
    def backup_answers(connection):
        """create a backup copy of the RHUI installer answers file"""
        Expect.expect_retval(connection, f"cp {ANSWERS} {ANSWERS_BAK}")

    @staticmethod
    def backup_rhui_tools_conf(connection):
        """create a backup copy of the RHUI tools configuration file"""
        Expect.expect_retval(connection, f"mv -f {RHUI_CFG} {RHUI_CFG_BAK}")

    @staticmethod
    def edit_rhui_tools_conf(connection, opt, val, backup=True, container=False):
        """set an option in the RHUI tools configuration file to the given value"""
        # the 'container' parameter only makes sense when editing the file on a CDS
        cmd = RhuiinContainers.exec_cmd("cds", "sed -i") if container else "sed -i"
        if backup:
            cmd = f"{cmd}{BACKUP_EXT}"
        cmd = f"{cmd} 's/^{opt}.*/{opt}: {val}/' {RHUI_CFG}"
        Expect.expect_retval(connection, cmd)

    @staticmethod
    def restore_answers(connection):
        """restore the backup copy of the RHUI installer answers file"""
        Expect.expect_retval(connection, f"mv -f {ANSWERS_BAK} {ANSWERS}")

    @staticmethod
    def restore_rhui_tools_conf(connection, container=False):
        """restore the backup copy of the RHUI tools configuration file"""
        cmd = RhuiinContainers.exec_cmd("cds", "mv") if container else "mv"
        Expect.expect_retval(connection, f"{cmd} -f {RHUI_CFG_BAK} {RHUI_CFG}")
