#! /usr/bin/python -tt

""" Create CloudFormation stack """

import os
import socket
import argparse
import time
import logging
import sys
import random
import string
import json
import re

import boto3
import yaml

instance_types = {"arm64": "t4g.large", "x86_64": "m5.large"}

argparser = argparse.ArgumentParser(description='Create CloudFormation stack for RHUI 4')
argparser.add_argument('--rhua', help=argparse.SUPPRESS)
argparser.add_argument('--iso', help=argparse.SUPPRESS)

argparser.add_argument('--name', help='common name for stack members', default='rhui')
argparser.add_argument('--cli6', help='number of RHEL6 clients', type=int, default=0)
argparser.add_argument('--cli7', help='number of RHEL7 clients', type=int, default=0)
argparser.add_argument('--cli7-arch', help='RHEL 7 clients\' architectures (comma-separated list)', default='x86_64', metavar='ARCH')
argparser.add_argument('--cli8', help='number of RHEL8 clients', type=int, default=0)
argparser.add_argument('--cli8-arch', help='RHEL 8 clients\' architectures (comma-separated list)', default='x86_64', metavar='ARCH')
argparser.add_argument('--cli9', help='number of RHEL9 clients', type=int, default=0)
argparser.add_argument('--cli9-arch', help='RHEL 9 clients\' architectures (comma-separated list)', default='x86_64', metavar='ARCH')
argparser.add_argument('--cli10', help='number of RHEL10 clients', type=int, default=0)
argparser.add_argument('--cli10-arch', help='RHEL 10 clients\' architectures (comma-separated list)', default='x86_64', metavar='ARCH')
argparser.add_argument('--cli-all', help='launch one client per RHEL version and available architecture, RHEL 6+ by default; numbers can still be overridden)', action='store_const', const=True, default=False)
argparser.add_argument('--cli-only', help='launch only client machines', action='store_const', const=True, default=False)
argparser.add_argument('--cds', help='number of CDSes instances', type=int, default=1)
argparser.add_argument('--cds-diversity', help='use newer RHEL major versions if using multiple CDS nodes', action='store_const', const=True, default=False)
argparser.add_argument('--dns', help='DNS', action='store_const', const=True, default=False)
argparser.add_argument('--nfs', help='NFS', action='store_const', const=True, default=False)
argparser.add_argument('--haproxy', help='number of HAProxies', type=int, default=1)
argparser.add_argument('--test', help='test machine with RHEL 8', action='store_const', const=True, default=False)
argparser.add_argument('--rhui5launchpad', help='add a launchpad for a future migration to RHUI 5', action='store_const', const=True, default=False)
argparser.add_argument('--rhui5rhua', help='add a RHUA for a future (non-in-place) migration to RHUI 5', action='store_const', const=True, default=False)
argparser.add_argument('--input-conf', default="/etc/rhui_ec2.yaml", help='use supplied yaml config file')
argparser.add_argument('--output-conf', help='output file')
argparser.add_argument('--region', default="eu-west-1", help='use specified region')
argparser.add_argument('--debug', action='store_const', const=True,
                       default=False, help='debug mode')
argparser.add_argument('--dry-run', action='store_const', const=True,
                       default=False, help='only validate the data and print what would be used')
argparser.add_argument('--timeout', type=int,
                       default=10, help='stack creation timeout (in minutes)')

argparser.add_argument('--vpcid', help='VPCid (overrides the configuration for the region)')
argparser.add_argument('--subnetid', help='Subnet id (for VPC) (overrides the configuration for the region)')
argparser.add_argument('--novpc', help='do not use VPC, use EC2 Classic', action='store_const', const=True, default=False)

argparser.add_argument('--ami-6-override', help='RHEL 6 AMI ID to override the mapping', metavar='ID')
argparser.add_argument('--ami-7-override', help='RHEL 7 AMI ID to override the mapping', metavar='ID')
argparser.add_argument('--ami-8-override', help='RHEL 8 AMI ID to override the mapping', metavar='ID')
argparser.add_argument('--ami-9-override', help='RHEL 9 AMI ID to override the mapping', metavar='ID')
argparser.add_argument('--ami-10-override', help='RHEL 10 AMI ID to override the mapping', metavar='ID')
argparser.add_argument('--ami-8-arm64-override', help='RHEL 8 ARM64 AMI ID to override the mapping', metavar='ID')
argparser.add_argument('--ami-9-arm64-override', help='RHEL 9 ARM64 AMI ID to override the mapping', metavar='ID')
argparser.add_argument('--ami-10-arm64-override', help='RHEL 10 ARM64 AMI ID to override the mapping', metavar='ID')
argparser.add_argument('--ansible-ssh-extra-args', help='Extra arguments for SSH connections established by Ansible', metavar='ARGS')
argparser.add_argument('--key-pair-name', help='the name of the key pair in the given AWS region, if your local user name differs and SSH configuraion is undefined in the yaml config file')

args = argparser.parse_args()


fs_type = "rhua"

if args.debug:
    loglevel = logging.DEBUG
else:
    loglevel = logging.INFO

REGION = args.region

logging.basicConfig(level=loglevel, format='%(asctime)s %(levelname)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')

if args.cli_all:
    args.cli7 = args.cli7 or -1
    args.cli8 = args.cli8 or -1
    args.cli9 = args.cli9 or -1
    args.cli10 = args.cli10 or -1

if args.cli_only:
    args.cds = args.haproxy = 0
    fs_type = ''

if (args.vpcid and not args.subnetid) or (args.subnetid and not args.vpcid):
    logging.error("vpcid and subnetid parameters should be set together!")
    sys.exit(1)
if args.novpc:
    instance_types["x86_64"] = "m3.large"

try:
    with open(args.input_conf, 'r') as confd:
        valid_config = yaml.safe_load(confd)

    if "ssh" in valid_config.keys() and REGION in valid_config["ssh"].keys():
        (ssh_key_name, ssh_key) = valid_config["ssh"][REGION]
    else:
        ssh_key = ""
        ssh_key_name = args.key_pair_name or os.getlogin()
    ec2_name = re.search("[a-zA-Z]+", ssh_key_name).group(0)
    if args.key_pair_name:
        ssh_key = "~/.ssh/id_rsa_" + ec2_name
    if not args.novpc:
        (vpcid, subnetid) = (args.vpcid, args.subnetid) if args.vpcid else valid_config["vpc"][REGION]

except Exception as e:
    logging.error("got '%s' error processing: %s", e, args.input_conf)
    logging.error("Please, check your config or and try again")
    sys.exit(1)

json_dict = {}

json_dict['AWSTemplateFormatVersion'] = '2010-09-09'

if args.nfs:
    fs_type = "nfs"

if args.cli7 == -1:
    args.cli7 = len(instance_types)
    args.cli7_arch = ",".join(instance_types.keys())
if args.cli8 == -1:
    args.cli8 = len(instance_types)
    args.cli8_arch = ",".join(instance_types.keys())
if args.cli9 == -1:
    args.cli9 = len(instance_types)
    args.cli9_arch = ",".join(instance_types.keys())
if args.cli10 == -1:
    args.cli10 = len(instance_types)
    args.cli10_arch = ",".join(instance_types.keys())

if args.rhua:
    logging.info("The --rhua parameter is deprecated. " +
                 "RHEL 8 is used on all nodes except for clients that you set up differently.")
if args.iso:
    logging.info("The --iso parameter is deprecated. Use --name instead. " +
                 "Using '%s' as the name to keep compatibility & for your convenience." % args.iso)
    args.name = args.iso
rhui_os = "RHEL8"

json_dict['Description'] = "Client-only stack" if args.cli_only else "RHUI with %s CDS and %s HAProxy nodes" % (args.cds, args.haproxy)
if args.cli6 > 0:
    json_dict['Description'] += ", %s RHEL6 client" % args.cli6 + ("s" if args.cli6 > 1 else "")
if args.cli7 > 0:
    json_dict['Description'] += ", %s RHEL7 client" % args.cli7 + ("s" if args.cli7 > 1 else "")
if args.cli8 > 0:
    json_dict['Description'] += ", %s RHEL8 client" % args.cli8 + ("s" if args.cli8 > 1 else "")
if args.cli9 > 0:
    json_dict['Description'] += ", %s RHEL9 client" % args.cli9 + ("s" if args.cli9 > 1 else "")
if args.cli10 > 0:
    json_dict['Description'] += ", %s RHEL10 client" % args.cli10 + ("s" if args.cli10 > 1 else "")
if args.test:
    json_dict['Description'] += ", TEST machine"
if args.dns:
    json_dict['Description'] += ", DNS"
if args.nfs:
    json_dict['Description'] += ", NFS"
if args.rhui5launchpad:
    json_dict['Description'] += ", RHUI 5 launchpad"
if args.rhui5rhua:
    json_dict['Description'] += ", RHUI 5 RHUA"


fs_type_f = fs_type

if fs_type_f == "rhua":
    fs_type_f = "nfs"

json_dict['Mappings'] = {u'RHEL6': {args.region: {}},
                         u'RHEL7': {args.region: {}},
                         u'RHEL8': {args.region: {}},
                         u'RHEL9': {args.region: {}},
                         u'RHEL10': {args.region: {}}}

try:
    if args.ami_6_override:
        json_dict['Mappings']['RHEL6'][args.region]['AMI'] = args.ami_6_override
    else:
        with open("RHEL6mapping.json") as mjson:
            rhel6mapping = json.load(mjson)
            json_dict['Mappings']['RHEL6'] = rhel6mapping

    if args.ami_7_override:
        json_dict['Mappings']['RHEL7'][args.region]['AMI'] = args.ami_7_override
    else:
        with open("RHEL7mapping.json") as mjson:
            rhel7mapping = json.load(mjson)
            json_dict['Mappings']['RHEL7'] = rhel7mapping

    if args.ami_8_override:
        json_dict['Mappings']['RHEL8'][args.region]['AMI'] = args.ami_8_override
    else:
        with open("RHEL8mapping.json") as mjson:
            rhel8mapping = json.load(mjson)
            json_dict['Mappings']['RHEL8'] = rhel8mapping

    if args.ami_9_override:
        json_dict['Mappings']['RHEL9'][args.region]['AMI'] = args.ami_9_override
    else:
        with open("RHEL9mapping.json") as mjson:
            rhel9mapping = json.load(mjson)
            json_dict['Mappings']['RHEL9'] = rhel9mapping

    if args.ami_10_override:
        json_dict['Mappings']['RHEL10'][args.region]['AMI'] = args.ami_10_override
    else:
        with open("RHEL10mapping.json") as mjson:
            rhel10mapping = json.load(mjson)
            json_dict['Mappings']['RHEL10'] = rhel10mapping

except Exception as e:
    sys.stderr.write("Got '%s' error \n" % e)
    sys.exit(1)

def concat_name(node='', cfgfile=False):
    return '_'.join(filter(None,
                           ['hosts' if cfgfile else ec2_name,
                            fs_type_f,
                            args.name,
                            node])
                    ) + ('.cfg' if cfgfile else '')

json_dict['Parameters'] = \
{u'KeyName': {u'Description': u'Name of an existing EC2 KeyPair to enable SSH access to the instances',
              u'Type': u'String'}}

json_dict['Resources'] = \
{u'RHUIsecuritygroup': {u'Properties': {u'GroupDescription': u'RHUI security group',
                                        u'SecurityGroupIngress': [{u'CidrIp': u'0.0.0.0/0',
                                                                   u'FromPort': u'22',
                                                                   u'IpProtocol': u'tcp',
                                                                   u'ToPort': u'22'},
                                                                   {u'CidrIp': u'0.0.0.0/0',
                                                                   u'FromPort': u'443',
                                                                   u'IpProtocol': u'tcp',
                                                                   u'ToPort': u'443'},
                                                                   {u'CidrIp': u'0.0.0.0/0',
                                                                   u'FromPort': u'2049',
                                                                   u'IpProtocol': u'tcp',
                                                                   u'ToPort': u'2049'},
                                                                   {u'CidrIp': u'0.0.0.0/0',
                                                                   u'FromPort': u'80',
                                                                   u'IpProtocol': u'tcp',
                                                                   u'ToPort': u'80'},
                                                                   {u'CidrIp': u'0.0.0.0/0',
                                                                   u'FromPort': u'3128',
                                                                   u'IpProtocol': u'tcp',
                                                                   u'ToPort': u'3128'},
                                                                  {u'CidrIp': u'0.0.0.0/0',
                                                                   u'FromPort': u'53',
                                                                   u'IpProtocol': u'tcp',
                                                                   u'ToPort': u'53'},
                                                                  {u'CidrIp': u'0.0.0.0/0',
                                                                   u'FromPort': u'53',
                                                                   u'IpProtocol': u'udp',
                                                                   u'ToPort': u'53'}]},
                        u'Type': u'AWS::EC2::SecurityGroup'}}

# nfs == rhua
# add a 100 GB volume for RHUI repos if using NFS
if (fs_type == "rhua"):
    json_dict['Resources']["rhua"] = \
     {u'Properties': {u'ImageId': {u'Fn::FindInMap': [rhui_os, {u'Ref': u'AWS::Region'}, u'AMI']},
                               u'InstanceType': instance_types["x86_64"],
                               u'KeyName': {u'Ref': u'KeyName'},
                               u'SecurityGroups': [{u'Ref': u'RHUIsecuritygroup'}],
                                 u'BlockDeviceMappings' : [
                                            {
                                              "DeviceName" : "/dev/sdb",
                                              "Ebs" : {"VolumeSize" : "100"}
                                            }
                                 ],
                               u'Tags': [{u'Key': u'Name', u'Value': concat_name(u'rhua')},
                                         {u'Key': u'Role', u'Value': u'RHUA'},
                                         ]},
               u'Type': u'AWS::EC2::Instance'}

elif fs_type:
    json_dict['Resources']["rhua"] = \
     {u'Properties': {u'ImageId': {u'Fn::FindInMap': [rhui_os, {u'Ref': u'AWS::Region'}, u'AMI']},
                               u'InstanceType': instance_types["x86_64"],
                               u'KeyName': {u'Ref': u'KeyName'},
                               u'SecurityGroups': [{u'Ref': u'RHUIsecuritygroup'}],
                               u'Tags': [{u'Key': u'Name', u'Value': concat_name(u'rhua')},
                                         {u'Key': u'Role', u'Value': u'RHUA'},
                                         ]},
               u'Type': u'AWS::EC2::Instance'}


# cdses
for i in range(1, args.cds + 1):
    # use RHEL 8 and 9 alternately
    if args.cds_diversity:
        cds_os = "RHEL8" if i % 2 else "RHEL9"
    else:
        cds_os = "RHEL8"
    json_dict['Resources']["cds%i" % i] = \
        {u'Properties': {u'ImageId': {u'Fn::FindInMap': [cds_os, {u'Ref': u'AWS::Region'}, u'AMI']},
                               u'InstanceType': instance_types["x86_64"],
                               u'KeyName': {u'Ref': u'KeyName'},
                               u'SecurityGroups': [{u'Ref': u'RHUIsecuritygroup'}],
                               u'Tags': [{u'Key': u'Name', u'Value': concat_name(u'cds%i' % i)},
                                         {u'Key': u'Role', u'Value': u'CDS'},
                                         ]},
               u'Type': u'AWS::EC2::Instance'}

# clients
os_dict = {6: "RHEL6", 7: "RHEL7", 8: "RHEL8", 9: "RHEL9", 10: "RHEL10"}
for i in (6, 7, 8, 9, 10):
    num_cli_ver = args.__getattribute__("cli%i" % i)
    if num_cli_ver:
        os = os_dict[i]
        for j in range(1, num_cli_ver + 1):
            try:
                cli_arch = args.__getattribute__("cli%i_arch" % i).split(",")[j-1]
                if not cli_arch:
                    cli_arch = "x86_64"
            except (AttributeError, IndexError):
                cli_arch = "x86_64"
            try:
                # RHEL 6 can't run on m5
                instance_type = instance_types[cli_arch] if i >= 7 else 'm3.large' if args.novpc else 'i3.large'
            except KeyError:
                logging.error("Unknown architecture: %s" % cli_arch)
                sys.exit(1)
            if cli_arch == "x86_64":
                image_id = {u'Fn::FindInMap': [os, {u'Ref': u'AWS::Region'}, u'AMI']}
            else:
                if args.novpc:
                    logging.error("EC2 Classic can only be used with x86_64 instances.")
                    logging.error("Stack creation would fail. Quitting.")
                    sys.exit(1)
                if i == 8 and args.ami_8_arm64_override:
                    image_id = args.ami_8_arm64_override
                elif i == 9 and args.ami_9_arm64_override:
                    image_id = args.ami_9_arm64_override
                elif i == 10 and args.ami_10_arm64_override:
                    image_id = args.ami_10_arm64_override
                else:
                    with open("RHEL%smapping_%s.json" % (i, cli_arch)) as mjson:
                       image_ids =  json.load(mjson)
                       image_id = image_ids[args.region]["AMI"]
            json_dict['Resources']["cli%inr%i" % (i, j)] = \
                {u'Properties': {u'ImageId': image_id,
                                   u'InstanceType': instance_type,
                                   u'KeyName': {u'Ref': u'KeyName'},
                                   u'SecurityGroups': [{u'Ref': u'RHUIsecuritygroup'}],
                                   u'Tags': [{u'Key': u'Name', u'Value': concat_name(u'cli%i_%i' % (i, j))},
                                             {u'Key': u'Role', u'Value': u'CLI'},
                                             {u'Key': u'OS', u'Value': u'%s' % os}]},
                   u'Type': u'AWS::EC2::Instance'}
                   
# nfs
if (fs_type == "nfs"):
    json_dict['Resources']["nfs"] = \
     {u'Properties': {u'ImageId': {u'Fn::FindInMap': [rhui_os, {u'Ref': u'AWS::Region'}, u'AMI']},
                               u'InstanceType': instance_types["x86_64"],
                               u'KeyName': {u'Ref': u'KeyName'},
                               u'SecurityGroups': [{u'Ref': u'RHUIsecuritygroup'}],
                                 u'BlockDeviceMappings' : [
                                            {
                                              "DeviceName" : "/dev/sdb",
                                              "Ebs" : {"VolumeSize" : "100"}
                                            },
                                 ],
                               u'Tags': [{u'Key': u'Name', u'Value': concat_name(u'nfs')},
                                         {u'Key': u'Role', u'Value': u'NFS'},
                                         ]},
               u'Type': u'AWS::EC2::Instance'}

# dns
if args.dns:
    json_dict['Resources']["dns"] = \
     {u'Properties': {u'ImageId': {u'Fn::FindInMap': [rhui_os, {u'Ref': u'AWS::Region'}, u'AMI']},
                               u'InstanceType': instance_types["x86_64"],
                               u'KeyName': {u'Ref': u'KeyName'},
                               u'SecurityGroups': [{u'Ref': u'RHUIsecuritygroup'}],
                               u'Tags': [{u'Key': u'Name', u'Value': concat_name(u'dns')},
                                         {u'Key': u'Role', u'Value': u'DNS'},
                                         ]},
               u'Type': u'AWS::EC2::Instance'}

# test
if args.test:
    os = "RHEL8"
    json_dict['Resources']["test"] = \
     {u'Properties': {u'ImageId': {u'Fn::FindInMap': [os, {u'Ref': u'AWS::Region'}, u'AMI']},
                               u'InstanceType': instance_types["x86_64"],
                               u'KeyName': {u'Ref': u'KeyName'},
                               u'SecurityGroups': [{u'Ref': u'RHUIsecuritygroup'}],
                               u'Tags': [{u'Key': u'Name', u'Value': concat_name(u'test')},
                                         {u'Key': u'Role', u'Value': u'TEST'},
                                         ]},
               u'Type': u'AWS::EC2::Instance'}

# HAProxy
for i in range(1, args.haproxy + 1):
    json_dict['Resources']["haproxy%i" % i] = \
        {u'Properties': {u'ImageId': {u'Fn::FindInMap': [rhui_os, {u'Ref': u'AWS::Region'}, u'AMI']},
                               u'InstanceType': instance_types["x86_64"],
                               u'KeyName': {u'Ref': u'KeyName'},
                               u'SecurityGroups': [{u'Ref': u'RHUIsecuritygroup'}],
                               u'Tags': [{u'Key': u'Name', u'Value': concat_name(u'haproxy%i' % i)},
                                         {u'Key': u'Role', u'Value': u'HAProxy'},
                                         ]},
                   u'Type': u'AWS::EC2::Instance'}
# RHUI 5 launchpad
if args.rhui5launchpad:
    os = "RHEL9"
    json_dict['Resources']["launchpad"] = \
     {u'Properties': {u'ImageId': {u'Fn::FindInMap': [os, {u'Ref': u'AWS::Region'}, u'AMI']},
                               u'InstanceType': instance_types["x86_64"],
                               u'KeyName': {u'Ref': u'KeyName'},
                               u'SecurityGroups': [{u'Ref': u'RHUIsecuritygroup'}],
                               u'Tags': [{u'Key': u'Name', u'Value': concat_name(u'launchpad')},
                                         {u'Key': u'Role', u'Value': u'LAUNCHPAD'},
                                         ]},
               u'Type': u'AWS::EC2::Instance'}

# RHUI 5 RHUA
if args.rhui5rhua:
    os = "RHEL9"
    json_dict['Resources']["anotherrhua"] = \
     {u'Properties': {u'ImageId': {u'Fn::FindInMap': [os, {u'Ref': u'AWS::Region'}, u'AMI']},
                               u'InstanceType': instance_types["x86_64"],
                               u'KeyName': {u'Ref': u'KeyName'},
                               u'SecurityGroups': [{u'Ref': u'RHUIsecuritygroup'}],
                               u'Tags': [{u'Key': u'Name', u'Value': concat_name(u'anotherrhua')},
                                         {u'Key': u'Role', u'Value': u'ANOTHERRHUA'},
                                         ]},
               u'Type': u'AWS::EC2::Instance'}


if not args.novpc:
    # Setting VpcId and SubnetId
    json_dict['Outputs'] = {}
    for key in list(json_dict['Resources']):
        # We'll be changing dictionary so retyping to a list is required to ensure compatibility with Python 3.7+.
        if json_dict['Resources'][key]['Type'] == 'AWS::EC2::SecurityGroup':
            json_dict['Resources'][key]['Properties']['VpcId'] = vpcid
        elif json_dict['Resources'][key]['Type'] == 'AWS::EC2::Instance':
            json_dict['Resources'][key]['Properties']['SubnetId'] = subnetid
            json_dict['Resources'][key]['Properties']['SecurityGroupIds'] = json_dict['Resources'][key]['Properties'].pop('SecurityGroups')
            json_dict['Resources']["%sEIP" % key] = \
            {
                "Type" : "AWS::EC2::EIP",
                "Properties" : {"Domain" : "vpc",
                                "InstanceId" : {"Ref" : key}
                               }
            }


json_dict['Outputs'] = {}

json_body = json.dumps(json_dict, indent=4)

STACK_ID = "STACK-%s-%s-%s" % (ec2_name, args.name, ''.join(random.choice(string.ascii_lowercase) for x in range(10)))
logging.info("Creating stack with ID " + STACK_ID)

parameters = [{"ParameterKey": "KeyName", "ParameterValue": ssh_key_name}]

if args.dry_run:
    print("Dry run.")
    print("This would be the template:")
    print(json_body)
    print("This would be the parameters:")
    print(parameters)
    sys.exit(0)

cf_client = boto3.client("cloudformation", region_name=args.region)
cf_client.create_stack(StackName=STACK_ID,
                       TemplateBody=json_body,
                       Parameters=parameters,
                       TimeoutInMinutes=args.timeout)

is_complete = False
success = False
while not is_complete:
    time.sleep(10)
    response = cf_client.describe_stacks(StackName=STACK_ID)
    status = response["Stacks"][0]["StackStatus"]
    if status == "CREATE_IN_PROGRESS":
        continue
    if status == "CREATE_COMPLETE":
        logging.info("Stack creation completed")
        is_complete = True
        success = True
    elif status in ("ROLLBACK_IN_PROGRESS", "ROLLBACK_COMPLETE"):
        logging.info("Stack creation failed: %s", status)
        is_complete = True
    else:
        logging.error("Unexpected stack status: %s", status)
        break

if not success:
    print("Review the stack in the CloudFormation console and diagnose the reason.")
    print("Be sure to delete the stack. Even stacks that were rolled back still consume resources!")
    sys.exit(1)

# obtain information about the stack
resources = cf_client.describe_stack_resources(StackName=STACK_ID)
# create a dict with items such as haproxy1EIP: 50:60:70:80
ip_addresses = {resource["LogicalResourceId"]: resource["PhysicalResourceId"] \
                for resource in resources['StackResources'] \
                if resource["ResourceType"] == "AWS::EC2::EIP"}
# create another, more useful dict with roles: hostnames
hostnames = {lri.replace("EIP", ""): socket.getfqdn(ip) \
             for lri, ip in ip_addresses.items()}
# also create a list of instance IDs to print in the end
instance_ids = [resource["PhysicalResourceId"] \
                for resource in resources['StackResources'] \
                if resource["ResourceType"] == "AWS::EC2::Instance"]

# output file
if args.output_conf:
    outfile = args.output_conf
else:
    outfile = concat_name(cfgfile=True)

try:
    with open(outfile, 'w') as f:
        f.write('[RHUA]\n')
        for role, hostname in hostnames.items():
            if role == "rhua":
                f.write(hostname)
                if ssh_key:
                    f.write(' ansible_ssh_private_key_file=%s' % ssh_key)
                if args.ansible_ssh_extra_args:
                    f.write(' ansible_ssh_extra_args="%s"' % args.ansible_ssh_extra_args)
                f.write('\n')
        # rhua as nfs
        if fs_type == "rhua":
            f.write('\n[NFS]\n')
            for role, hostname in hostnames.items():
                if role == "rhua":
                    f.write(hostname)
                    if ssh_key:
                        f.write(' ansible_ssh_private_key_file=%s' % ssh_key)
                    if args.ansible_ssh_extra_args:
                        f.write(' ansible_ssh_extra_args="%s"' % args.ansible_ssh_extra_args)
                    f.write('\n')
        # nfs
        elif fs_type == "nfs":
            f.write('\n[NFS]\n')
            for role, hostname in hostnames.items():
                if role == "nfs":
                    f.write(hostname)
                    if ssh_key:
                        f.write(' ansible_ssh_private_key_file=%s' % ssh_key)
                    if args.ansible_ssh_extra_args:
                        f.write(' ansible_ssh_extra_args="%s"' % args.ansible_ssh_extra_args)
                    f.write('\n')
        # cdses
        f.write('\n[CDS]\n')
        for role, hostname in hostnames.items():
            if role.startswith("cds"):
                f.write(hostname)
                if ssh_key:
                    f.write(' ansible_ssh_private_key_file=%s' % ssh_key)
                if args.ansible_ssh_extra_args:
                    f.write(' ansible_ssh_extra_args="%s"' % args.ansible_ssh_extra_args)
                f.write('\n')
        # dns
        f.write('\n[DNS]\n')
        if args.dns:
            for role, hostname in hostnames.items():
                if role == "dns":
                    f.write(hostname)
                    if ssh_key:
                        f.write(' ansible_ssh_private_key_file=%s' % ssh_key)
                    if args.ansible_ssh_extra_args:
                        f.write(' ansible_ssh_extra_args="%s"' % args.ansible_ssh_extra_args)
                    f.write('\n')
        else:
            for role, hostname in hostnames.items():
                if role == "rhua":
                    f.write(hostname)
                    if ssh_key:
                        f.write(' ansible_ssh_private_key_file=%s' % ssh_key)
                    if args.ansible_ssh_extra_args:
                        f.write(' ansible_ssh_extra_args="%s"' % args.ansible_ssh_extra_args)
                    f.write('\n')
        # cli
        if args.cli6 or args.cli7 or args.cli8 or args.cli9 or args.cli10:
            f.write('\n[CLI]\n')
            for role, hostname in hostnames.items():
                if role.startswith("cli"):
                    f.write(hostname)
                    if ssh_key:
                        f.write(' ansible_ssh_private_key_file=%s' % ssh_key)
                    if args.ansible_ssh_extra_args:
                        f.write(' ansible_ssh_extra_args="%s"' % args.ansible_ssh_extra_args)
                    f.write('\n')
        # test
        if args.test:
            f.write('\n[TEST]\n')
            for role, hostname in hostnames.items():
                if role == "test":
                    f.write(hostname)
                    if ssh_key:
                        f.write(' ansible_ssh_private_key_file=%s' % ssh_key)
                    if args.ansible_ssh_extra_args:
                        f.write(' ansible_ssh_extra_args="%s"' % args.ansible_ssh_extra_args)
                    f.write('\n')
        # haproxy
        f.write('\n[HAPROXY]\n')
        for role, hostname in hostnames.items():
            if role.startswith("haproxy"):
                f.write(hostname)
                if ssh_key:
                    f.write(' ansible_ssh_private_key_file=%s' % ssh_key)
                if args.ansible_ssh_extra_args:
                    f.write(' ansible_ssh_extra_args="%s"' % args.ansible_ssh_extra_args)
                f.write('\n')
        # RHUI 5 launchpad
        if args.rhui5launchpad:
            f.write('\n[LAUNCHPAD]\n')
            for role, hostname in hostnames.items():
                if role == "launchpad":
                    f.write(hostname)
                    if ssh_key:
                        f.write(' ansible_ssh_private_key_file=%s' % ssh_key)
                    if args.ansible_ssh_extra_args:
                        f.write(' ansible_ssh_extra_args="%s"' % args.ansible_ssh_extra_args)
                    f.write('\n')

        # RHUI 5 RHUA
        if args.rhui5rhua:
            f.write('\n[ANOTHERRHUA]\n')
            for role, hostname in hostnames.items():
                if role == "anotherrhua":
                    f.write(hostname)
                    if ssh_key:
                        f.write(' ansible_ssh_private_key_file=%s' % ssh_key)
                    if args.ansible_ssh_extra_args:
                        f.write(' ansible_ssh_extra_args="%s"' % args.ansible_ssh_extra_args)
                    f.write('\n')


except Exception as e:
    logging.error("got '%s' error processing: %s", e, args.output_conf)
    sys.exit(1)

print("Instance IDs:")
print(" ".join(instance_ids))
print(f"Inventory file contents ({outfile}):")
with open(outfile, encoding="utf-8") as outfile_fd:
    print(outfile_fd.read())
