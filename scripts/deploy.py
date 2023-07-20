#!/usr/bin/python
"""RHUI 4 Automation Deployment Made Easy"""

from os import system
from os.path import exists, expanduser, join
import sys

import argparse
from configparser import RawConfigParser

# there can be configuration to complement some options
CFG_FILE = "~/.rhui4-automation.cfg"
R4A_CFG = RawConfigParser()
R4A_CFG.read(expanduser(CFG_FILE))
if R4A_CFG.has_section("main") and R4A_CFG.has_option("main", "basedir"):
    RHUI_DIR = R4A_CFG.get("main", "basedir")
else:
    RHUI_DIR = "~/RHUI"

PRS = argparse.ArgumentParser(description="Run the RHUI 4 Automation playbook to deploy RHUI.",
                              formatter_class=argparse.ArgumentDefaultsHelpFormatter)
PRS.add_argument("inventory",
                 help="inventory file; typically hosts_*.cfg created by create-cf-stack.py",
                 nargs="?")
PRS.add_argument("--iso",
                 help="RHUI ISO file",
                 default=join(RHUI_DIR, "RHUI.iso"),
                 metavar="file")
PRS.add_argument("--rhsm",
                 help="use RHSM instead of a RHUI ISO",
                 action="store_true")
PRS.add_argument("--client-rpm",
                 help="RHUI client RPM (another source of RHUI packages); '_' = load from config",
                 metavar="file")
PRS.add_argument("--upgrade",
                 help="upgrade all packages before running the deployment",
                 action="store_true")
PRS.add_argument("--fips",
                 help="enable FIPS before running the deployment",
                 action="store_true")
PRS.add_argument("--ansible-engine",
                 help="install Ansible Engine first (or else Ansible Core will be installed)",
                 action="store_true")
PRS.add_argument("--proxy",
                 help="configure RHUI to connect to the CDN via a proxy",
                 action="store_true")
PRS.add_argument("--extra-files",
                 help="ZIP file with extra files",
                 default=join(RHUI_DIR, "extra_files.zip"),
                 metavar="file")
PRS.add_argument("--credentials",
                 help="configuration file with credentials",
                 default=join(RHUI_DIR, "credentials.conf"),
                 metavar="file")
PRS.add_argument("--tests",
                 help="RHUI test to run",
                 metavar="test name or category")
PRS.add_argument("--prep",
                 help="prepare RHUI for other testing (upload the cert, add nodes, cache repos)",
                 action="store_true")
PRS.add_argument("--patch",
                 help="patch to apply to rhui4-automation",
                 metavar="file")
PRS.add_argument("--branch",
                 help="clone and install a particular rhui4-automation branch")
PRS.add_argument("--rhel8b",
                 help="RHEL 8 Beta baseurl or compose",
                 metavar="URL/compose")
PRS.add_argument("--rhel9b",
                 help="RHEL 9 Beta baseurl or compose",
                 metavar="URL/compose")
PRS.add_argument("--tags",
                 help="run only tasks tagged this way",
                 metavar="tags")
PRS.add_argument("--skip-tags",
                 help="skip tasks tagged this way",
                 metavar="tags")
PRS.add_argument("--extra-vars",
                 help="supply these variables to Ansible")
PRS.add_argument("--dry-run",
                 help="only construct and print the ansible-playbook command, do not run it",
                 action="store_true")

ARGS = PRS.parse_args()

if not ARGS.inventory:
    PRS.print_help()
    sys.exit(1)

if not exists(ARGS.inventory):
    print(ARGS.inventory + " does not exist.")
    sys.exit(1)

if ARGS.rhsm:
    if not exists(expanduser(ARGS.credentials)):
        print(f"--rhsm was used but {ARGS.credentials} does not exist, exiting.")
        sys.exit(1)
elif ARGS.client_rpm:
    if ARGS.client_rpm == "_":
        base_client_rpm_file_name = R4A_CFG.get("main", "client_rpm", fallback=None)
        if not base_client_rpm_file_name:
            print("No client RPM is configured, exiting.")
            sys.exit(1)
        ARGS.client_rpm = join(RHUI_DIR, base_client_rpm_file_name)
    if not exists(expanduser(ARGS.client_rpm)):
        print(f"{ARGS.client_rpm} is not a file, exiting.")
        sys.exit(1)
elif ARGS.iso:
    if not exists(expanduser(ARGS.iso)):
        print(f"{ARGS.iso} is not a file, exiting.")
        sys.exit(1)
else:
    print("No way to install RHUI packages was specified.")
    sys.exit(1)

# start building the command
CMD = f"ansible-playbook -i {ARGS.inventory} deploy/site.yml --extra-vars '"

# start building the extra variables
if ARGS.client_rpm:
    EVARS = f"client_rpm={ARGS.client_rpm}"
elif ARGS.rhsm:
    EVARS = ""
elif ARGS.iso:
    EVARS = f"rhui_iso={ARGS.iso}"

if ARGS.upgrade:
    EVARS += " upgrade_all_pkg=True"

if ARGS.fips:
    EVARS += " fips=True"

if ARGS.ansible_engine:
    EVARS += " ansible_engine=True"

if ARGS.proxy:
    EVARS += " proxy=True"

if exists(expanduser(ARGS.extra_files)):
    EVARS += " extra_files=" + ARGS.extra_files
else:
    print(ARGS.extra_files + " does not exist, ignoring")

if exists(expanduser(ARGS.credentials)):
    EVARS += " credentials=" + ARGS.credentials
else:
    print(ARGS.credentials + " does not exist, ignoring")

# provided that the RHEL X Beta string is NOT a URL,
# see if the configuration contains templates for RHEL Beta baseurls;
# if so, expand them
# if not, use the arguments verbatim
if ARGS.rhel8b:
    if ":/" not in ARGS.rhel8b and R4A_CFG.has_option("beta", "rhel8_template"):
        try:
            ARGS.rhel8b = R4A_CFG.get("beta", "rhel8_template") % ARGS.rhel8b
        except TypeError:
            print(f"The RHEL 8 Beta URL template is written incorrectly in {CFG_FILE}. " +
                  "It must contain '%s' in one place.")
            sys.exit(1)
    EVARS += " rhel8_beta_baseurl=" + ARGS.rhel8b

if ARGS.rhel9b:
    if ":/" not in ARGS.rhel9b and R4A_CFG.has_option("beta", "rhel9_template"):
        try:
            ARGS.rhel9b = R4A_CFG.get("beta", "rhel9_template") % ARGS.rhel9b
        except TypeError:
            print(f"The RHEL 9 Beta URL template is written incorrectly in {CFG_FILE}. " +
                  "It must contain '%s' in one place.")
            sys.exit(1)
    EVARS += " rhel9_beta_baseurl=" + ARGS.rhel9b

if ARGS.tests:
    EVARS += " tests=" + ARGS.tests

if ARGS.prep:
    EVARS += " prep=True"

if ARGS.patch:
    if exists(expanduser(ARGS.patch)):
        EVARS += " patch=" + ARGS.patch
    else:
        print(f"--patch was specified but {ARGS.patch} does not exist, exiting.")
        sys.exit(1)

if ARGS.branch:
    EVARS += " branch=" + ARGS.branch

if ARGS.extra_vars:
    EVARS += " " + ARGS.extra_vars

# join the command and the extra variables
CMD += EVARS.lstrip() + "'"

# use/skip specific tags if requested
if ARGS.tags:
    CMD += " --tags " + ARGS.tags

if ARGS.skip_tags:
    CMD += " --skip-tags " + ARGS.skip_tags

# the command is now built; print it and then run it (unless in the dry-run mode)
if ARGS.dry_run:
    print("DRY RUN: would have run: " + CMD)
else:
    print("Running: " + CMD)
    system(CMD)
