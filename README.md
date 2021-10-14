RHUI 4 Automation
=================

__Tools to deploy and test Red Hat Update Infrastructure 4 (RHUI 4).__

Overview
--------
RHUI 4 Automation consists of a script that prepares AWS EC2 machines and a set of Ansible playbooks that turn the machines into fully functional RHUI 4 nodes: RHUA, CDSes, HAProxy etc. Optionally, a test machine and a client machine can also be installed and made available for automated testing and/or further manual experimenting.

This is essentially a clone of RHUI 3 Automation. Most of the credit goes to its maintainers.

Contents
--------

* `deploy/`: Ansible playbooks to set up the individual nodes.
* `docs/`: Documentation for test modules. Needs Sphinx to build.
* `scripts/`: Scripts to simplify the deployment even more by creating a cloudformation stack with the individual RHUI 4 nodes and a hosts configuration file to use by Ansible.
* `tests/`: Test suite (test cases and libraries) to verify the functionality of an installed RHUI 4 environment or check for potential regressions in new RHUI 4 versions.
* `hosts.cfg`: A template for the hosts configuration.
* `RHEL*mapping.json`: IDs of the latest AMIs. The deployment script uses this data.

Usage
-----

See the [deployment readme file](deploy/README.md) for details.

Data Files
----------

In addition to `hosts.cfg` and the JSON files, the following data file exists:

* `tests/rhui4_tests/tested_repos.yaml`: Names of repositories to test. These repositories must be part of the entitlement certificate which is uploaded to RHUA. For more information about the certificate, see the [requirements section in the tests readme file](tests/README.md#requirements).
