''' Methods to manage other RHUI nodes '''

from rhui4_tests_lib.conmgr import ConMgr, SUDO_USER_NAME, SUDO_USER_KEY

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
            force=False, unsafe=False):
        '''
        Add a CDS or HAProxy node.
        If hostname is empty, ConMgr will be used to determine the default one for the node type
        Return True if the command exited with 0, and False otherwise.
        Note to the caller: Trust no one! Check for yourself if the node has really been added.
        '''
        _validate_node_type(node_type)
        if not hostname:
            if node_type == "cds":
                hostname = ConMgr.get_cds_hostnames()[0]
            elif node_type == "haproxy":
                hostname = ConMgr.get_cds_lb_hostname()
        cmd = f"rhui-manager {node_type} add " + \
              f"--hostname {hostname} --ssh_user {ssh_user} --keyfile_path {keyfile_path}"
        if force:
            cmd += " --force"
        if unsafe:
            cmd += " --unsafe"
        return connection.recv_exit_status(cmd, timeout=300) == 0

    @staticmethod
    def reinstall(connection, node_type, hostname):
        '''
        Reinstall a CDS or HAProxy node.
        Return True if the command exited with 0, and False otherwise.
        '''
        _validate_node_type(node_type)
        cmd = f"rhui-manager {node_type} reinstall --hostname {hostname}"
        return connection.recv_exit_status(cmd, timeout=120) == 0

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
                hostnames = ConMgr.get_cds_lb_hostname()
        cmd = f"rhui-manager {node_type} delete --hostnames {','.join(hostnames)}"
        if force:
            cmd += " --force"
        return connection.recv_exit_status(cmd, timeout=180) == 0