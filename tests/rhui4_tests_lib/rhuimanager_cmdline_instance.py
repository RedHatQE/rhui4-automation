''' Methods to manage other RHUI nodes '''

from rhui4_tests_lib.conmgr import ConMgr, SUDO_USER_NAME, SUDO_USER_KEY
from rhui4_tests_lib.incontainers import RhuiinContainers

def _validate_node_type(text):
    '''
    Check if the given text is a valid RHUI node type.
    '''
    ok_types = ["cds", "haproxy"]
    if text not in ok_types:
        raise ValueError(f"Unsupported node type: '{text}'. Use one of: {ok_types}.")

class RHUIManagerCLIInstance():
    '''
    The rhui-manager command-line interface to control CDS and HAProxy nodes.
    '''
    @staticmethod
    def list(connection, node_type):
        '''
        Return a list of CDS or HAProxy nodes (hostnames).
        '''
        _validate_node_type(node_type)
        _, stdout, _ = connection.exec_command(f"rhui-manager {node_type} list")
        lines = stdout.read().decode()
        nodes = [line.split(":")[1].strip() for line in lines.splitlines() if "Hostname:" in line]
        return nodes

    @staticmethod
    def add(connection, node_type,
            hostname="", ssh_user=SUDO_USER_NAME, keyfile_path=SUDO_USER_KEY,
            container=False, container_registry="", container_image="",
            ssl_crt="", ssl_key="",
            haproxy_config_file="",
            force=False, unsafe=False, no_update=False):
        '''
        Add a CDS or HAProxy node. Deploy on the VM itself, or as a container on the VM.
        If hostname is empty, ConMgr will be used to determine the default one for the node type
        Return True if the command exited with 0, and False otherwise.
        Note to the caller: Trust no one! Check for yourself if the node has really been added.
        '''
        _validate_node_type(node_type)
        if node_type == "haproxy" and (ssl_crt or ssl_key):
            raise ValueError("SSL cert and/or key is meaningless when adding an HAproxy node")
        if not hostname:
            if node_type == "cds":
                hostname = ConMgr.get_cds_hostnames()[0]
            elif node_type == "haproxy":
                hostname = ConMgr.get_lb_hostname()
        arg = "add_container" if container else "add"
        cmd = f"rhui-manager {node_type} {arg} " + \
              f"--hostname {hostname} --ssh_user {ssh_user} --keyfile_path {keyfile_path}"
        if container:
            # remove this comment and the line below when the CDS image is published
            container_registry = RhuiinContainers.get_instance_registry(connection)
            if container_registry:
                cmd += f" --container_registry {container_registry}"
            if container_image:
                cmd += f" --container_image {container_image}"
        if ssl_crt:
            cmd += f" --user_supplied_ssl_crt {ssl_crt}"
        if ssl_key:
            cmd += f" --user_supplied_ssl_key {ssl_key}"
        if haproxy_config_file:
            cmd += f" --config {haproxy_config_file}"
        if force:
            cmd += " --force"
        if unsafe:
            cmd += " --unsafe"
        if no_update:
            cmd += " --no_update"
        return connection.recv_exit_status(cmd, timeout=600) == 0

    @staticmethod
    def reinstall(connection, node_type, hostname="", all_nodes=False, no_update=False):
        '''
        Reinstall a CDS or HAProxy node. One hostname or all tracked nodes.
        Return True if the command exited with 0, and False otherwise.
        '''
        _validate_node_type(node_type)
        if all_nodes:
            cmd = f"rhui-manager {node_type} reinstall --all"
        elif hostname:
            cmd = f"rhui-manager {node_type} reinstall --hostname {hostname}"
        else:
            raise ValueError("Either a hostname or '--all' must be used.")
        if no_update:
            cmd += " --no_update"
        return connection.recv_exit_status(cmd, timeout=540) == 0

    @staticmethod
    def delete(connection, node_type, hostnames="", force=False):
        '''
        Reinstall one or more CDS or HAProxy nodes.
        Return True if the command exited with 0, and False otherwise.
        Note to the caller: Trust no one! Check for yourself if the nodes have really been deleted.
        '''
        _validate_node_type(node_type)
        if not hostnames:
            if node_type == "cds":
                hostnames = ConMgr.get_cds_hostnames()
            elif node_type == "haproxy":
                hostnames = [ConMgr.get_lb_hostname()]
        cmd = f"rhui-manager {node_type} delete --hostnames {','.join(hostnames)}"
        if force:
            cmd += " --force"
        return connection.recv_exit_status(cmd, timeout=180) == 0
