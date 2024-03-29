#! /usr/bin/python -tt

""" Create CloudFormation stack """

import os
from paramiko import SSHClient
from boto import cloudformation
from boto import regioninfo
from boto import ec2
import argparse
import time
import logging
import subprocess
import sys
import random
import string
import json
import tempfile
import paramiko
import yaml
import re

# pylint: disable=W0621


class SyncSSHClient(SSHClient):
    '''
    Special class for sync'ed commands execution over ssh
    '''
    def run_sync(self, command):
        """ Run sync """
        logging.debug("RUN_SYNC '%s'", command)
        stdin, stdout, stderr = self.exec_command(command)
        status = stdout.channel.recv_exit_status()
        if status:
            logging.debug("RUN_SYNC status: %i", status)
        else:
            logging.debug("RUN_SYNC failed!")
        return stdin, stdout, stderr

    def run_with_pty(self, command):
        """ Run with PTY """
        logging.debug("RUN_WITH_PTY '%s'", command)
        chan = self.get_transport().open_session()
        chan.get_pty()
        chan.exec_command(command)
        status = chan.recv_exit_status()
        logging.debug("RUN_WITH_PTY recv: %s", chan.recv(16384))
        logging.debug("RUN_WITH_PTY status: %i", status)
        chan.close()
        return status

instance_types = {"arm64": "t4g.large", "x86_64": "m5.large"}

argparser = argparse.ArgumentParser(description='Create CloudFormation stack for RHUI 4')
argparser.add_argument('--rhua', help=argparse.SUPPRESS)
argparser.add_argument('--iso', help=argparse.SUPPRESS)

argparser.add_argument('--name', help='common name for stack members', default='rhui')
argparser.add_argument('--cli5', help='number of RHEL5 clients', type=int, default=0)
argparser.add_argument('--cli6', help='number of RHEL6 clients', type=int, default=0)
argparser.add_argument('--cli7', help='number of RHEL7 clients', type=int, default=0)
argparser.add_argument('--cli7-arch', help='RHEL 7 clients\' architectures (comma-separated list)', default='x86_64', metavar='ARCH')
argparser.add_argument('--cli8', help='number of RHEL8 clients', type=int, default=0)
argparser.add_argument('--cli8-arch', help='RHEL 8 clients\' architectures (comma-separated list)', default='x86_64', metavar='ARCH')
argparser.add_argument('--cli9', help='number of RHEL9 clients', type=int, default=0)
argparser.add_argument('--cli9-arch', help='RHEL 9 clients\' architectures (comma-separated list)', default='x86_64', metavar='ARCH')
argparser.add_argument('--cli-all', help='launch one client per RHEL version and available architecture, without RHEL 5 by default; numbers can still be overridden)', action='store_const', const=True, default=False)
argparser.add_argument('--cli-only', help='launch only client machines', action='store_const', const=True, default=False)
argparser.add_argument('--cds', help='number of CDSes instances', type=int, default=1)
argparser.add_argument('--dns', help='DNS', action='store_const', const=True, default=False)
argparser.add_argument('--nfs', help='NFS', action='store_const', const=True, default=False)
argparser.add_argument('--haproxy', help='number of HAProxies', type=int, default=1)
argparser.add_argument('--test', help='test machine with RHEL 8', action='store_const', const=True, default=False)
argparser.add_argument('--input-conf', default="/etc/rhui_ec2.yaml", help='use supplied yaml config file')
argparser.add_argument('--output-conf', help='output file')
argparser.add_argument('--region', default="eu-west-1", help='use specified region')
argparser.add_argument('--debug', action='store_const', const=True,
                       default=False, help='debug mode')
argparser.add_argument('--dry-run', action='store_const', const=True,
                       default=False, help='do not run stack creation, validate only')
argparser.add_argument('--parameters', metavar='<expr>', nargs="*",
                       help="space-separated NAME=VALUE list of parameters")

argparser.add_argument('--timeout', type=int,
                       default=10, help='stack creation timeout')

argparser.add_argument('--vpcid', help='VPCid (overrides the configuration for the region)')
argparser.add_argument('--subnetid', help='Subnet id (for VPC) (overrides the configuration for the region)')
argparser.add_argument('--novpc', help='do not use VPC, use EC2 Classic', action='store_const', const=True, default=False)

argparser.add_argument('--ami-5-override', help='RHEL 5 AMI ID to override the mapping', metavar='ID')
argparser.add_argument('--ami-6-override', help='RHEL 6 AMI ID to override the mapping', metavar='ID')
argparser.add_argument('--ami-7-override', help='RHEL 7 AMI ID to override the mapping', metavar='ID')
argparser.add_argument('--ami-8-override', help='RHEL 8 AMI ID to override the mapping', metavar='ID')
argparser.add_argument('--ami-9-override', help='RHEL 9 AMI ID to override the mapping', metavar='ID')
argparser.add_argument('--ami-8-arm64-override', help='RHEL 8 ARM64 AMI ID to override the mapping', metavar='ID')
argparser.add_argument('--ami-9-arm64-override', help='RHEL 9 ARM64 AMI ID to override the mapping', metavar='ID')
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

if args.debug:
    logging.getLogger("paramiko").setLevel(logging.DEBUG)
else:
    logging.getLogger("paramiko").setLevel(logging.WARNING)

if args.cli_all:
    args.cli6 = args.cli6 or 1
    args.cli7 = args.cli7 or -1
    args.cli8 = args.cli8 or -1
    args.cli9 = args.cli9 or -1

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
        ssh_key = False
        ssh_key_name = args.key_pair_name or os.getlogin()
    ec2_key = valid_config["ec2"]["ec2-key"]
    ec2_secret_key = valid_config["ec2"]["ec2-secret-key"]
    ec2_name = re.search("[a-zA-Z]+", ssh_key_name).group(0)
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

if args.rhua:
    logging.info("The --rhua parameter is deprecated. " +
                 "RHEL 8 is used on all nodes except for clients that you set up differently.")
if args.iso:
    logging.info("The --iso parameter is deprecated. Use --name instead. " +
                 "Using '%s' as the name to keep compatibility & for your convenience." % args.iso)
    args.name = args.iso
rhui_os = "RHEL8"

json_dict['Description'] = "Client-only stack" if args.cli_only else "RHUI with %s CDS and %s HAProxy nodes" % (args.cds, args.haproxy)
if args.cli5 > 0:
    json_dict['Description'] += ", %s RHEL5 client" % args.cli5 + ("s" if args.cli5 > 1 else "")
if args.cli6 > 0:
    json_dict['Description'] += ", %s RHEL6 client" % args.cli6 + ("s" if args.cli6 > 1 else "")
if args.cli7 > 0:
    json_dict['Description'] += ", %s RHEL7 client" % args.cli7 + ("s" if args.cli7 > 1 else "")
if args.cli8 > 0:
    json_dict['Description'] += ", %s RHEL8 client" % args.cli8 + ("s" if args.cli8 > 1 else "")
if args.cli9 > 0:
    json_dict['Description'] += ", %s RHEL9 client" % args.cli9 + ("s" if args.cli9 > 1 else "")
if args.test:
    json_dict['Description'] += ", TEST machine"
if args.dns:
    json_dict['Description'] += ", DNS"
if args.nfs:
    json_dict['Description'] += ", NFS"


fs_type_f = fs_type

if fs_type_f == "rhua":
    fs_type_f = "nfs"

json_dict['Mappings'] = {u'RHEL5': {args.region: {}},
                         u'RHEL6': {args.region: {}},
                         u'RHEL7': {args.region: {}},
                         u'RHEL8': {args.region: {}},
                         u'RHEL9': {args.region: {}}}

try:
    if args.ami_5_override:
        json_dict['Mappings']['RHEL5'][args.region]['AMI'] = args.ami_5_override
    else:
        with open("RHEL5mapping.json") as mjson:
            rhel5mapping = json.load(mjson)
            json_dict['Mappings']['RHEL5'] = rhel5mapping

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
    json_dict['Resources']["cds%i" % i] = \
        {u'Properties': {u'ImageId': {u'Fn::FindInMap': [rhui_os, {u'Ref': u'AWS::Region'}, u'AMI']},
                               u'InstanceType': instance_types["x86_64"],
                               u'KeyName': {u'Ref': u'KeyName'},
                               u'SecurityGroups': [{u'Ref': u'RHUIsecuritygroup'}],
                               u'Tags': [{u'Key': u'Name', u'Value': concat_name(u'cds%i' % i)},
                                         {u'Key': u'Role', u'Value': u'CDS'},
                                         ]},
               u'Type': u'AWS::EC2::Instance'}

# clients
os_dict = {5: "RHEL5", 6: "RHEL6", 7: "RHEL7", 8: "RHEL8", 9: "RHEL9"}
for i in (5, 6, 7, 8, 9):
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
                # RHEL 5 and 6 can't run on m5
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
                                             {u'Key': u'OS', u'Value': u'%s' % os[:5]}]},
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

region = regioninfo.RegionInfo(name=args.region,
                               endpoint="cloudformation." + args.region + ".amazonaws.com")

if not region:
    logging.error("Unable to connect to region: " + args.region)
    sys.exit(1)

con_cf = cloudformation.connection.CloudFormationConnection(aws_access_key_id=ec2_key,
                                                            aws_secret_access_key=ec2_secret_key,
                                                            region=region)

con_ec2 = ec2.connect_to_region(args.region,
                                aws_access_key_id=ec2_key,
                                aws_secret_access_key=ec2_secret_key)

if not con_cf or not con_ec2:
    logging.error("Create CF/EC2 connections: " + args.region)
    sys.exit(1)

STACK_ID = "STACK-%s-%s-%s" % (ec2_name, args.name, ''.join(random.choice(string.ascii_lowercase) for x in range(10)))
logging.info("Creating stack with ID " + STACK_ID)

parameters = []
try:
    if args.parameters:
        for param in args.parameters:
            parameters.append(tuple(param.split('=')))
except:
    logging.error("Wrong parameters format")
    sys.exit(1)

parameters.append(("KeyName", ssh_key_name))

if args.dry_run:
    sys.exit(0)

con_cf.create_stack(STACK_ID, template_body=json_body,
                    parameters=parameters, timeout_in_minutes=args.timeout)

is_complete = False
result = False
while not is_complete:
    time.sleep(10)
    try:
        for event in con_cf.describe_stack_events(STACK_ID):
            if event.resource_type == "AWS::CloudFormation::Stack" and event.resource_status == "CREATE_COMPLETE":
                logging.info("Stack creation completed")
                is_complete = True
                result = True
                break
            if event.resource_type == "AWS::CloudFormation::Stack" and event.resource_status == "ROLLBACK_COMPLETE":
                logging.info("Stack creation failed")
                is_complete = True
                break
    except:
        # Sometimes 'Rate exceeded' happens
        pass

if not result:
    sys.exit(1)

instances = []
for res in con_cf.describe_stack_resources(STACK_ID):
    # we do care about instances only
    if res.resource_type == 'AWS::EC2::Instance' and res.physical_resource_id:
        logging.debug("Instance " + res.physical_resource_id + " created")
        instances.append(res.physical_resource_id)

instances_detail = []
for i in con_ec2.get_all_instances():
    for ii in  i.instances:
        if ii.id in instances:
            try:
                public_hostname = ii.tags["PublicHostname"]
            except KeyError:
                public_hostname = ii.public_dns_name
            # sometimes an instance doesn't get its public hostname immediately (it's empty)
            # if that's the case, keep asking AWS (using the CLI)
            get_pub_hostname_cmd = "aws ec2 describe-instances --region %s --instance-ids %s --query 'Reservations[].Instances[].PublicDnsName'" % (REGION, ii.id)
            while not public_hostname:
                logging.info('the public hostname of %s is not yet known, will try to fetch it after a while' % ii.id)
                time.sleep(20)
                cmd_out = subprocess.check_output(get_pub_hostname_cmd, shell=True).decode()
                response_list = json.loads(cmd_out)
                if response_list:
                    public_hostname = response_list[0]
            try:
                private_hostname = ii.tags["PrivateHostname"]
            except KeyError:
                private_hostname = ii.private_dns_name
            try:
                role = ii.tags["Role"]
            except KeyError:
                role = None

            if ii.ip_address:
                public_ip = ii.ip_address
            else:
                public_ip = ii.private_ip_address
            private_ip = ii.private_ip_address

            details_dict = {"id": ii.id,
                            "public_hostname": public_hostname,
                            "private_hostname": private_hostname,
                            "role": role,
                            "public_ip": public_ip,
                            "private_ip": private_ip}

            for tag_key in ii.tags.keys():
                if tag_key not in ["PublicHostname", "PrivateHostname", "Role"]:
                    details_dict[tag_key] = ii.tags[tag_key]

            instances_detail.append(details_dict)

logging.debug(instances_detail)
result = []
ids = []
for instance in instances_detail:
    iid = str(instance['id'])
    if instance["public_ip"]:
        ip = instance["public_ip"]
        result_item = dict(role=str(instance['role']),
                           hostname=str(instance['public_hostname']),
                           ip=str(ip),
                           instance_id=iid)
        logging.info("Instance with public ip created: %s", result_item)
    else:
        ip = instance["private_ip"]
        result_item = dict(role=str(instance['role']),
                           hostname=str(instance['private_hostname']),
                           ip=str(ip),
                           instance_id=iid)
        logging.info("Instance with private ip created: %s", result_item)
    result.append(result_item)
    ids.append(iid)


for instance in instances_detail:
    if instance["private_hostname"]:
        hostname = instance["private_hostname"]
    else:
        hostname = instance["public_hostname"]
    instance['hostname'] = hostname


# output file

if args.output_conf:
    outfile = args.output_conf
else:
    outfile = concat_name(cfgfile=True)

try:
    with open(outfile, 'w') as f:
        f.write('[RHUA]\n')
        for instance in instances_detail:
            if instance["role"] == "RHUA":
                f.write(str(instance['public_hostname']))
                if ssh_key:
                    f.write(' ansible_ssh_private_key_file=%s' % ssh_key)
                if args.ansible_ssh_extra_args:
                    f.write(' ansible_ssh_extra_args="%s"' % args.ansible_ssh_extra_args)
                f.write('\n')
        # rhua as nfs
        if fs_type == "rhua":
            f.write('\n[NFS]\n')
            for instance in instances_detail:
                if instance["role"] == "RHUA":
                    f.write(str(instance['public_hostname']))
                    if ssh_key:
                        f.write(' ansible_ssh_private_key_file=%s' % ssh_key)
                    if args.ansible_ssh_extra_args:
                        f.write(' ansible_ssh_extra_args="%s"' % args.ansible_ssh_extra_args)
                    f.write('\n')
        # nfs
        elif fs_type == "nfs":
            f.write('\n[NFS]\n')
            for instance in instances_detail:
                if instance["role"] == "NFS":
                    f.write(str(instance['public_hostname']))
                    if ssh_key:
                        f.write(' ansible_ssh_private_key_file=%s' % ssh_key)
                    if args.ansible_ssh_extra_args:
                        f.write(' ansible_ssh_extra_args="%s"' % args.ansible_ssh_extra_args)
                    f.write('\n')
        # cdses
        f.write('\n[CDS]\n')
        for instance in instances_detail:
            if instance["role"] == "CDS":
                f.write(str(instance['public_hostname']))
                if ssh_key:
                    f.write(' ansible_ssh_private_key_file=%s' % ssh_key)
                if args.ansible_ssh_extra_args:
                    f.write(' ansible_ssh_extra_args="%s"' % args.ansible_ssh_extra_args)
                f.write('\n')
        # dns
        f.write('\n[DNS]\n')
        if args.dns:
            for instance in instances_detail:
                if instance["role"] == "DNS":
                    f.write(str(instance['public_hostname']))
                    if ssh_key:
                        f.write(' ansible_ssh_private_key_file=%s' % ssh_key)
                    if args.ansible_ssh_extra_args:
                        f.write(' ansible_ssh_extra_args="%s"' % args.ansible_ssh_extra_args)
                    f.write('\n')
        else:
            for instance in instances_detail:
                if instance["role"] == "RHUA":
                    f.write(str(instance['public_hostname']))
                    if ssh_key:
                        f.write(' ansible_ssh_private_key_file=%s' % ssh_key)
                    if args.ansible_ssh_extra_args:
                        f.write(' ansible_ssh_extra_args="%s"' % args.ansible_ssh_extra_args)
                    f.write('\n')
        # cli
        if args.cli5 or args.cli6 or args.cli7 or args.cli8 or args.cli9:
            f.write('\n[CLI]\n')
            for instance in instances_detail:
                if instance["role"] == "CLI":
                    # RHEL 5 and 6 can't be set up using modern ansible versions
                    # write the data anyway so the user can see it, but comment it out
                    if instance["OS"] in ["RHEL5", "RHEL6"]:
                        f.write('#')
                    f.write(str(instance['public_hostname']))
                    # only RHEL >= 6 has ec2-user, RHEL 5 has just root
                    if instance["OS"] == "RHEL5":
                        f.write(' ansible_ssh_user=root ')
                    if ssh_key:
                        f.write(' ansible_ssh_private_key_file=%s' % ssh_key)
                    if args.ansible_ssh_extra_args:
                        f.write(' ansible_ssh_extra_args="%s"' % args.ansible_ssh_extra_args)
                    f.write('\n')
        # test
        if args.test:
            f.write('\n[TEST]\n')
            for instance in instances_detail:
                if instance["role"] == "TEST":
                    f.write(str(instance['public_hostname']))
                    if ssh_key:
                        f.write(' ansible_ssh_private_key_file=%s' % ssh_key)
                    if args.ansible_ssh_extra_args:
                        f.write(' ansible_ssh_extra_args="%s"' % args.ansible_ssh_extra_args)
                    f.write('\n')
        # haproxy
        f.write('\n[HAPROXY]\n')
        for instance in instances_detail:
            if instance["role"] == "HAProxy":
                f.write(str(instance['public_hostname']))
                if ssh_key:
                    f.write(' ansible_ssh_private_key_file=%s' % ssh_key)
                if args.ansible_ssh_extra_args:
                    f.write(' ansible_ssh_extra_args="%s"' % args.ansible_ssh_extra_args)
                f.write('\n')


except Exception as e:
    logging.error("got '%s' error processing: %s", e, args.output_conf)
    sys.exit(1)


# --- close the channels
for instance in instances_detail:
    logging.debug('closing instance %s channel', instance['hostname'])
    try:
        instance['client'].close()
    except Exception as e:
        logging.warning('closing %s client channel: %s', instance['hostname'], e)
    finally:
        logging.debug('client %s channel closed', instance['hostname'])
    logging.debug('closing client %s sftp channel', instance['hostname'])
    try:
        instance['sftp'].close()
    except Exception as e:
        logging.warning('closing %s sftp channel: %s', instance['hostname'], e)
    finally:
        logging.debug('client %s sftp channel closed', instance['hostname'])

# --- dump the result
print('# --- instances created ---')
yaml.dump(result, sys.stdout)
print('# instance IDs: ---')
print(' '.join(ids))
print('# --- stack data saved in %s ---' % outfile)
# check if the file really contains all the hostnames; they should be there, but just in case...
# (basically, if a line starts with the space character, it's a problem; report the line number)
outfile_ok = True
with open(outfile) as outfile_fd:
    saved_lines = outfile_fd.readlines()
    for index, text in enumerate(saved_lines):
        if text.startswith(' '):
            print('Missing hostname on line %s!' % (index + 1))
            outfile_ok = False
    if not outfile_ok:
        print('Fix the file manually, or delete the stack and try again.')
        sys.exit(2)

