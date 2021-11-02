#! /usr/bin/python -tt
"""Regenerate a list of AMI IDs based on the given AMI description."""

import sys
import subprocess
import json
import argparse

if subprocess.call("which aws &> /dev/null", shell=True):
    sys.stderr.write("The aws client is not available. Please install package awscli.\n")
    sys.exit(1)

if subprocess.call("aws configure get aws_access_key_id &> /dev/null", shell=True):
    sys.stderr.write("The aws client is not configured. Please run `aws configure'.\n")
    sys.exit(1)

argparser = argparse.ArgumentParser(description='Get a list of AMIs')
argparser.add_argument('rhel',
                       help='Description of the AMI \
                       (e.g. RHEL-7.5_HVM_GA-20180322-x86_64-1-Hourly2-GP2)',
                       metavar='AMI',
                       nargs='?')

args = argparser.parse_args()

if not args.rhel:
    argparser.print_help()
    sys.exit(1)

if args.rhel.startswith("RHEL-9"):
    MAPPING = "RHEL9mapping.json"
elif args.rhel.startswith("RHEL-8"):
    MAPPING = "RHEL8mapping.json"
elif args.rhel.startswith("RHEL-7"):
    MAPPING = "RHEL7mapping.json"
elif args.rhel.startswith("RHEL-6"):
    MAPPING = "RHEL6mapping.json"
elif args.rhel.startswith("RHEL-5"):
    MAPPING = "RHEL5mapping.json"
else:
    sys.stderr.write("Wrong parameters")
    sys.exit(1)

ami_properties = args.rhel.split("-")
if ami_properties[3] != "x86_64":
    MAPPING = MAPPING.replace(".", f"_{ami_properties[3]}.")

CMD = "aws ec2 describe-regions " \
      "--all-regions " \
      "--query 'Regions[].{Name:RegionName}' " \
      "--output text"
cmd_out = subprocess.check_output(CMD, shell=True)
regions = cmd_out.decode().splitlines()

CMD = "aws ec2 describe-images " \
      "--filters Name=name,Values=*{0}* " \
      "--query Images[*].ImageId --region {1}"

out_dict = {}

for i in regions:
    print(CMD.format(args.rhel, i))
    ami = subprocess.Popen(CMD.format(args.rhel, i).split(), stdout=subprocess.PIPE)
    out, err = ami.communicate()
    js = json.loads(out)
    try:
        AMI_ID = js[0]
    except IndexError as err:
        sys.stderr.write(f"Got '{err}' error \n")
        sys.stderr.write(f"Missing AMI ID for '{i}' region \n \n")
        AMI_ID = ""
    out_dict[i] = {}
    out_dict[i]["AMI"] = AMI_ID

with open(MAPPING, "w", encoding="utf-8") as f:
    json.dump(out_dict, f, indent=4, sort_keys=True)
