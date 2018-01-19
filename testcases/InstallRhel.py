#!/usr/bin/python2
# OpenPOWER Automated Test Project
#
# Contributors Listed Below - COPYRIGHT 2018
# [+] International Business Machines Corp.
#
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied. See the License for the specific language governing
# permissions and limitations under the License.
#


import unittest
import time
#import pexpect
#import socket
import subprocess

import OpTestConfiguration
from common.OpTestUtil import OpTestUtil
from common.OpTestSystem import OpSystemState
from common.OpTestError import OpTestError
from common.Exceptions import CommandFailed
from common import OpTestInstallUtil


class MyIPfromHost(unittest.TestCase):
    def setUp(self):
        conf = OpTestConfiguration.conf
        self.host = conf.host()
        self.ipmi = conf.ipmi()
        self.system = conf.system()
        self.bmc = conf.bmc()
        self.util = OpTestUtil()

    def runTest(self):
        self.system.goto_state(OpSystemState.PETITBOOT_SHELL)
        self.c = self.system.sys_get_ipmi_console()
        self.system.host_console_unique_prompt()
        #my_ip = self.system.get_my_ip_from_host_perspective()
        my_ip = "9.40.192.92"
        print "# FOUND MY IP: %s" % my_ip


class InstallRhel(unittest.TestCase):
    def setUp(self):
        self.conf = OpTestConfiguration.conf
        self.host = self.conf.host()
        self.ipmi = self.conf.ipmi()
        self.system = self.conf.system()
        self.bmc = self.conf.bmc()
        self.util = OpTestUtil()
        self.bmc_type = self.conf.args.bmc_type

    def runTest(self):
        self.system.goto_state(OpSystemState.PETITBOOT_SHELL)
        self.c = self.system.sys_get_ipmi_console()
        self.system.host_console_unique_prompt()
        my_ip = "9.40.192.92"
        retry = 30
        while retry > 0:
            try:
                self.c.run_command("ifconfig -a")
                break
            except CommandFailed as cf:
                if cf.exitcode is 1:
                    time.sleep(1)
                    retry = retry - 1
                    pass
                else:
                    raise cf
        retry = 30
        while retry > 0:
            try:
                #my_ip = self.system.get_my_ip_from_host_perspective()
                self.c.run_command("ping %s -c 1" % my_ip)
                break
            except CommandFailed as cf:
                if cf.exitcode is 1:
                    time.sleep(1)
                    retry = retry - 1
                    pass
                else:
                    raise cf

        base_path = "osimages/rhel"
        boot_path = "ppc/ppc64"
        vmlinux = "vmlinuz"
        initrd = "initrd.img"
        ks = "rhel.ks"

        OpTestInstallUtil.InstallUtil(base_path=base_path,
                                      vmlinux=vmlinux,
                                      initrd=initrd, ks=ks,
                                      disk=self.host.get_scratch_disk(),
                                      boot_path=boot_path,
                                      my_ip=my_ip,
                                      repo=self.conf.args.os_repo)

        if self.conf.args.os_cdrom and not self.conf.args.os_repo:
            repo = OpTestInstallUtil.setup_repo(self.conf.args.os_cdrom)
        if self.conf.args.os_repo:
            repo = self.conf.args.os_repo

        OpTestInstallUtil.extract_install_files(repo)

        # start our web server
        port = OpTestInstallUtil.start_server()

        if "qemu" not in self.bmc_type:
            if not self.conf.args.host_mac:
                # we need to go and grab things from the network to netboot
                arp = subprocess.check_output(['arp', self.host.hostname()]).split('\n')[1]
                arp = arp.split()
                host_mac_addr = arp[2]
                print "# Found host mac addr %s", host_mac_addr
            else:
                host_mac_addr = self.conf.args.host_mac
            ks_url = 'http://%s:%s/%s' % (my_ip, port, ks)
            kernel_args = "ifname=net0:%s ip=%s::%s:%s:%s:net0:none nameserver=%s inst.ks=%s" % (host_mac_addr,
                                                                                                 self.host.ip,
                                                                                                 self.conf.args.host_gateway,
                                                                                                 self.conf.args.host_submask,
                                                                                                 self.host.hostname(),
                                                                                                 self.conf.args.host_dns,
                                                                                                 ks_url)
            self.system.goto_state(OpSystemState.PETITBOOT_SHELL)
            cmd = "[ -f %s ]&& rm -f %s;[ -f %s ] && rm -f %s;true" % (vmlinux,
                                                                       vmlinux,
                                                                       initrd,
                                                                       initrd)
            self.c.run_command(cmd)
            self.c.run_command("wget http://%s:%s/%s" % (my_ip, port, vmlinux))
            self.c.run_command("wget http://%s:%s/%s" % (my_ip, port, initrd))
            self.c.run_command("kexec -i %s -c \"%s\" %s -l" % (initrd,
                                                                kernel_args,
                                                                vmlinux))
            self.c.get_console().send("kexec -e\n")
        else:
            pass
        # Do things
        rawc = self.c.get_console()
        rawc.expect('Sent SIGKILL to all processes', timeout=60)
        r = None
        while r != 0:
            r = rawc.expect(['Running post-installation scripts',
                             'Starting installer',
                             'Setting up the installation environment',
                             'Starting package installation process',
                             'Performing post-installation setup tasks',
                             'Configuring installed system'], timeout=600)
        rawc.expect('reboot: Restarting system', timeout=300)
        self.system.set_state(OpSystemState.IPLing)
        self.system.goto_state(OpSystemState.PETITBOOT_SHELL)
        OpTestInstallUtil.stop_server()
