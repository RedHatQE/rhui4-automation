Requirements
---------------
* [Ansible](https://docs.ansible.com/ansible/latest/installation_guide/installation_distros.html#installing-ansible-on-fedora-linux) version 2.8 and later but not later than 2.16 because later versions can no longer manage RHEL 8 systems. Using e.g. Fedora 41 is encouraged.
* Have enough machines running RHEL 8 ready - check the rest of Read Me for details on various RHUI setups.
* Have the latest RHUI 4 ISO or Red Hat CCSP credentials.

Usage
--------

* Run the [stack creation script](../scripts/README.md) to launch VMs and get an inventory file with information about the VMs.
* Run the [deployment script](../scripts/deploy.py) to deploy RHUI on the VMs.

Note that if you use `--rhel8b`, all RHEL 8 systems will get rebooted after the update
to the given compose. Ditto for `--rhel9b`.
This will allow a new kernel to boot, apps to load with a new glibc, etc.

If you want to use Red Hat CCSP credentials instead of the ISO, the credentials file must look
like this:

```
[rh]
username=YOUR_RH_USERNAME
password=YOUR_RH_PASSWORD
````

The deployment script can also read templates for RHEL 8 or 9 Beta URLs
from `~/.rhui4-automation.cfg`; the expected format is as follows:

```
[beta]
rhel8_template=http://host/path/%s/path/
rhel9_template=http://host/path/%s/path/
```

Managed roles
-------------
- DNS
- RHUA
- CDSes
- HAProxy (load balancer)
- NFS server
- Clients (optional)
- [Tests](../tests/README.md) (optional)

Supported configurations
------------------------
The rule of thumb is multiple roles can be applied to a single node.
This allows various deployment configurations, just to outline the minimal one:
- Rhua+Dns+Nfs, n\*Cds, m\*HAProxy

Please, bare in mind that role application sets node `hostname` such as hap01.example.com, nfs.example.com overriding any hostname previously set (by other role application).
Although all the role hostnames are properly resolvable (through /etc/hosts and optionaly the name server), the last applied hostname will stick to the node.

Configuration Samples
---------------------
Edit your copy of the `hosts.cfg` to meet your preferences:
* example:
```ini
# Rhua+Dns+Nfs, 2*Cds, 2*HAProxy
[DNS]
ec2-10.0.0.2.eu-west-1.compute.amazonaws.com

[NFS]
ec2-10.0.0.2.eu-west-1.compute.amazonaws.com

[RHUA]
ec2-10.0.0.2.eu-west-1.compute.amazonaws.com

[CDS]
ec2-10.0.0.3.eu-west-1.compute.amazonaws.com
ec2-10.0.0.4.eu-west-1.compute.amazonaws.com

[HAPROXY]
ec2-10.0.0.5.eu-west-1.compute.amazonaws.com

[CLI]
ec2-10.0.0.6.eu-west-1.compute.amazonaws.com

#[TEST]
#ec2-10.0.0.8.eu-west-1.compute.amazonaws.com
```

Check the [hosts.cfg](../hosts.cfg) file for more combinations.


Configuration Limitations
-------------------------
Even though one can apply multiple roles to a single node, some combinations are restricted or make no sense:
- singleton roles --- only one instance per site: Rhua, Nfs, Dns, Proxy, Test
- mutually exclusive roles --- can't be applied to the same node: Rhua, Cds, HAProxy, Proxy (all listen on port 443)
- optional roles --- may be absent in one's site: Dns, HAProxy, Proxy, Cli, Test
- multi-roles --- usually multiple instances per site: CDS, HAProxy, Cli

Network Ports:
---------------------------------------

* RHUA to cdn.redhat.com 443/TCP
* RHUA to CDSes 22/TCP for initial SSH configuration
* RHUA to HAProxy 22/TCP for initial SSH configuration
* clients to HAProxy 443/TCP
* HAProxy to CDSes 443/TCP
* NFS port 2049/TCP on the NFS server
