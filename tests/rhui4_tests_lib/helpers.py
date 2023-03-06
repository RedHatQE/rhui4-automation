"""Helper Functions for RHUI Test Cases"""

from os.path import basename, join
import time

from configparser import ConfigParser
import yaml

from stitches.expect import Expect, ExpectFailed
import nose

RHUI_CFG = "/etc/rhui/rhui-tools.conf"

class Helpers():
    """actions that may be repeated in specific test cases and do not belong in general utils"""
    @staticmethod
    def break_hostname(connection, hostname):
        """override DNS by setting a fake IP address in /etc/hosts and stopping bind"""
        tweak_hosts_cmd = fr"sed -i.bak 's/^[^ ]*\(.*i{hostname}\)$/256.0.0.0\1/' /etc/hosts"
        Expect.expect_retval(connection, tweak_hosts_cmd)
        Expect.expect_retval(connection, "service named stop")

    @staticmethod
    def unbreak_hostname(connection):
        """undo the changes made by break_hostname"""
        Expect.expect_retval(connection, "mv -f /etc/hosts.bak /etc/hosts")
        Expect.expect_retval(connection, "service named start")

    @staticmethod
    def cds_in_haproxy_cfg(connection, cds):
        """check if the CDS is present in the HAProxy configuration"""
        _, stdout, _ = connection.exec_command("cat /etc/haproxy/haproxy.cfg")
        cfg = stdout.read().decode()
        return f"server {cds} {cds}:443 check" in cfg

    @staticmethod
    def check_service(connection, service):
        """check if the given service is running"""
        return connection.recv_exit_status(f"systemctl is-active {service}") == 0

    @staticmethod
    def check_mountpoint(connection, mountpoint):
        """check if something is mounted in the given directory"""
        return connection.recv_exit_status(f"mountpoint {mountpoint}") == 0

    @staticmethod
    def encode_sos_command(command, plugin="rhui"):
        """replace special characters with safe ones and compose the path in the archive"""
        # spaces become underscores
        # slashes become dots
        command = command.replace(" ", "_")
        command = command.replace("/", ".")
        # the actual file is in the /commands directory in the archive
        return join("/sos_commands", plugin, command)

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
    def get_registry_url(site, connection=""):
        """get the URL for the given container registry or for the saved one (use "default" then)"""
        if site == "default":
            rhuicfg = ConfigParser()
            _, stdout, _ = connection.exec_command(f"cat {RHUI_CFG}")
            rhuicfg.read_file(stdout)
            if not rhuicfg.has_option("container", "registry_url"):
                return None
            return rhuicfg.get("container", "registry_url")
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
            credentials = Helpers.get_credentials(connection, site)
            url = Helpers.get_registry_url(site)
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
            Helpers.backup_rhui_tools_conf(connection)
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
    def backup_rhui_tools_conf(connection):
        """create a backup copy of the RHUI tools configuration file"""
        Expect.expect_retval(connection, f"mv -f {RHUI_CFG} {RHUI_CFG}.bak")

    @staticmethod
    def edit_rhui_tools_conf(connection, opt, val, backup=True):
        """set an option in the RHUI tools configuration file to the given value"""
        cmd = "sed -i"
        if backup:
            cmd = f"{cmd}.bak"
        cmd = f"{cmd} 's/^{opt}.*/{opt}: {val}/' {RHUI_CFG}"
        Expect.expect_retval(connection, cmd)

    @staticmethod
    def restore_rhui_tools_conf(connection):
        """restore the backup copy of the RHUI tools configuration file"""
        Expect.expect_retval(connection, f"mv -f {RHUI_CFG}.bak {RHUI_CFG}")

    @staticmethod
    def is_registered(connection):
        """return True if the remote host is registered with RHSM, or False otherwise"""
        return connection.recv_exit_status("subscription-manager identity") == 0

    @staticmethod
    def restart_rhui_services(connection, node_type="rhua"):
        """restart RHUI services on the remote host (according to the specified type)"""
        services = {
                    "rhua":    [
                                "nginx",
                                "pulpcore-api",
                                "pulpcore-content",
                                "pulpcore-worker@*"
                               ],
                    "cds":     [
                                "nginx",
                                "gunicorn-auth",
                                "gunicorn-content_manager",
                                "gunicorn-mirror"
                               ],
                    "haproxy": [
                                "haproxy"
                               ]
                   }
        if node_type not in services:
            raise ValueError(f"{node_type} is not a known node type") from None
        get_pids_cmd = "systemctl -p MainPID show %s | awk -F = '/PID/ { print $2 }'"
        # fetch the current PIDs
        _, stdout, _ = connection.exec_command(get_pids_cmd % " ".join(services[node_type]))
        oldpids = list(map(int, stdout.read().decode().splitlines()))
        # actually run the restart script, should exit with 0
        Expect.expect_retval(connection, "rhui-services-restart", timeout=20)
        # fetch PIDs again
        _, stdout, _ = connection.exec_command(get_pids_cmd % " ".join(services[node_type]))
        newpids = list(map(int, stdout.read().decode().splitlines()))
        # 0 in the output means the service is down (or doesn't exist)
        nose.tools.ok_(0 not in oldpids, msg="an inactive (or unknown) service was detected")
        # the number of PIDs should remain the same
        nose.tools.eq_(len(oldpids), len(newpids))
        # none of the new PIDs should be among the old PIDs; that would mean the service
        # wasn't restarted
        for pid in newpids:
            nose.tools.ok_(pid not in oldpids, msg=f"{pid} remained running")

    @staticmethod
    def add_legacy_ca(connection, local_ca_file):
        """configure a CDS to accept a legacy CA"""
        # this method takes the path to the local CA file and configures that CA on a CDS
        ca_dir = "/etc/pki/rhui/legacy"
        ca_file = join(ca_dir, basename(local_ca_file))
        Expect.expect_retval(connection, f"mkdir -p {ca_dir}")
        connection.sftp.put(local_ca_file, ca_file)
        Helpers.edit_rhui_tools_conf(connection, "log_level", "DEBUG")
        Expect.expect_retval(connection, "rhui-services-restart")

    @staticmethod
    def del_legacy_ca(connection, ca_file_name):
        """unconfigure a legacy CA"""
        # this method takes just the base file name (something.crt) in the legacy CA dir on a CDS
        # and unconfigures that CA
        ca_dir = "/etc/pki/rhui/legacy"
        ca_file = join(ca_dir, ca_file_name)
        Expect.expect_retval(connection, f"rm {ca_file}")
        Expect.expect_retval(connection, f"rmdir {ca_dir} || :")
        Helpers.restore_rhui_tools_conf(connection)
        Expect.expect_retval(connection, "logrotate -f /etc/logrotate.d/nginx")
        Expect.expect_retval(connection, "rhui-services-restart")

    @staticmethod
    def get_repos_from_yaml(connection, yaml_file):
        """load the specified YAML file with repo_ids and return them as a list"""
        _, stdout, _ = connection.exec_command(f"cat {yaml_file}")
        import_repo_data = yaml.safe_load(stdout)
        repo_ids = import_repo_data["repo_ids"]
        return repo_ids

    @staticmethod
    def copy_repo_mappings(connection, best_effort=True):
        """copy the repo cache from extra files to the cache dir to speed up repo management"""
        # with best_effort set to True, this method won't fail is the mapping file can't be copied
        # if this method is called right after the cert upload is executed, the cert may not
        # be available yet; let's sleep
        time.sleep(7)
        _, stdout, _ = connection.exec_command("ls /etc/pki/rhui/redhat/")
        cert_files = stdout.read().decode().splitlines()
        if not cert_files:
            raise RuntimeError("No uploaded certificate was found.")
        if len(cert_files) > 1:
            raise RuntimeError("More than one uploaded certificate was found.")
        mapping_file = f"/var/cache/rhui/{cert_files[0]}.mappings"
        try:
            Expect.expect_retval(connection,
                                 f"cp /tmp/extra_rhui_files/rhcert.mappings {mapping_file}")
        except ExpectFailed:
            if best_effort:
                pass
            else:
                raise RuntimeError("Could not copy the mappings.") from None
