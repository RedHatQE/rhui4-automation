"""Functions for RHUI in Containers"""

from configparser import ConfigParser

def _get_container_name(instance_type):
    """get the name of the container for the given node type"""
    containers = {
                  "cds": "rhui4-cds",
                 }
    if instance_type not in containers:
        raise ValueError(f"Unsupported type: '{instance_type}'. " \
                         f"Use one of: {list(containers.keys())}.")
    return containers[instance_type]

class RhuiinContainers():
    """Containerized RHUI functions"""
    @staticmethod
    def is_containerized(connection):
        """return True/False depending on whether the node is containerized or not"""
        container_files = {
                           "cds": "/etc/containers/systemd/rhui_cds.container",
                          }
        good_exit_statuses = [connection.recv_exit_status(f"test -f {container_file}") == 0 \
                              for container_file in container_files.values()]
        return any(good_exit_statuses)

    @staticmethod
    def get_instance_registry(connection):
        """get the hostname of the internal RHUI development registry"""
        path = "/tmp/extra_rhui_files/credentials.conf"
        reg_cfg = ConfigParser()
        _, stdout, _ = connection.exec_command(f"cat {path}")
        reg_cfg.read_file(stdout)
        section = "instance_images"
        option = "registry"
        if not reg_cfg.has_section(section):
            raise RuntimeError(f"section {section} does not exist in {path}")
        if not reg_cfg.has_option(section, option):
            raise RuntimeError(f"the registry is not defined in {path}")
        registry = reg_cfg.get(section, option)
        return registry

    @staticmethod
    def exec_cmd(instance_type, cmd):
        """return the command that will execute the actual command on a containerized RHUI node"""
        name = _get_container_name(instance_type)
        return f"podman exec -it {name} {cmd}"

    @staticmethod
    def copy(source, instance_type, dest):
        """return the command that will copy the file to the container"""
        name = _get_container_name(instance_type)
        return f"podman cp {source} {name}:{dest}"
