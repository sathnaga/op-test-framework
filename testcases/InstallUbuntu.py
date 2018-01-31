#!/usr/bin/python2
# OpenPOWER Automated Test Project
#
# Contributors Listed Below - COPYRIGHT 2015,2017
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

# Let's boot some Installers!

import unittest
import time
import pexpect
import subprocess

import OpTestConfiguration
from common.OpTestUtil import OpTestUtil
from common.OpTestSystem import OpSystemState
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
        my_ip = self.system.get_my_ip_from_host_perspective()
        print "# FOUND MY IP: %s" % my_ip


class InstallUbuntu(unittest.TestCase):
    def setUp(self):
        conf = OpTestConfiguration.conf
        self.conf = conf
        self.host = conf.host()
        self.ipmi = conf.ipmi()
        self.system = conf.system()
        self.bmc = conf.bmc()
        self.util = OpTestUtil()
        self.bmc_type = conf.args.bmc_type

    def select_petitboot_item(self, item):
        self.system.goto_state(OpSystemState.PETITBOOT)
        rawc = self.c.get_console()
        r = None
        while r != 0:
            time.sleep(0.2)
            r = rawc.expect(['\*.*\s+' + item, '\*.*\s+', pexpect.TIMEOUT],
                            timeout=1)
            if r == 0:
                break
            rawc.send("\x1b[A")
            rawc.expect('')
            rawc.sendcontrol('l')

    def runTest(self):
        self.system.goto_state(OpSystemState.PETITBOOT_SHELL)
        self.c = self.system.sys_get_ipmi_console()
        self.system.host_console_unique_prompt()

        # Set the install paths
        base_path = "osimages/ubuntu"
        boot_path = "ubuntu-installer/ppc64el"
        vmlinux = "vmlinux"
        initrd = "initrd.gz"
        ks = "preseed.cfg"

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
        my_ip = self.system.get_my_ip_from_host_perspective()
        if not my_ip:
            self.fail("unable to get the ip from host")
        self.system.host_console_unique_prompt()
        self.c.run_command("ping %s -c 1" % my_ip)

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

        if not self.conf.args.os_repo:
            repo = 'http://%s:%s/repo' % (my_ip, port)

        kernel_args = (' auto console=ttyS0 '
                       'interface=auto '
                       'netcfg/disable_autoconfig=true '
                       'netcfg/get_nameservers=%s '
                       'netcfg/get_ipaddress=%s '
                       'netcfg/get_netmask=%s '
                       'netcfg/get_gateway=%s '
                       'debian-installer/locale=en_US '
                       'console-setup/ask_detect=false '
                       'console-setup/layoutcode=us '
                       'netcfg/get_hostname=ubuntu '
                       'netcfg/get_domain=example.com '
                       'netcfg/link_wait_timeout=60 '
                       'partman-auto/disk=%s '
                       'locale=en_US '
                       'url=http://%s:%s/preseed.cfg' % (self.conf.args.host_dns,
                                                         self.host.ip,
                                                         self.conf.args.host_submask,
                                                         self.conf.args.host_gateway,
                                                         self.host.get_scratch_disk(),
                                                         my_ip, port))

        if "qemu" in self.bmc_type:
            kernel_args = kernel_args + ' netcfg/choose_interface=auto '
            # For Qemu, we boot from CDROM, so let's use petitboot!
            self.select_petitboot_item('Install Ubuntu Server')
            rawc = self.c.get_console()
            rawc.send('e')
            # In future, we should implement a method like this:
            #  self.petitboot_select_field('Boot arguments:')
            # But, in the meantime:
            rawc.send('\t\t\t\t')  # FIXME :)
            rawc.send('\b\b\b\b')  # remove ' ---'
            rawc.send('\b\b\b\b\b')  # remove 'quiet'
            rawc.send(kernel_args)
            rawc.send('\t')
            rawc.sendline('')
            rawc.sendline('')
        else:
            if not self.conf.args.host_mac:
                arp = subprocess.check_output(['arp', self.host.hostname()]).split('\n')[1]
                arp = arp.split()
                host_mac_addr = arp[2]
                print "# Found host mac addr %s", host_mac_addr
            else:
                host_mac_addr = self.conf.args.host_mac
            kernel_args = kernel_args + ' netcfg/choose_interface=%s BOOTIF=01-%s' % (host_mac_addr, '-'.join(host_mac_addr.split(':')))
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

        # Do things
        rawc = self.c.get_console()
        rawc.expect('Sent SIGKILL to all processes', timeout=60)
        rawc.expect('Loading additional components', timeout=300)
        rawc.expect('Setting up the clock', timeout=300)
        rawc.expect('Detecting hardware', timeout=300)
        rawc.expect('Partitions formatting', timeout=300)
        rawc.expect('Installing the base system', timeout=300)
        r = None
        while r != 0:
            r = rawc.expect(['Finishing the installation',
                             'Select and install software',
                             'Preparing', 'Configuring',
                             'Cleaning up'
                             'Retrieving', 'Installing',
                             'boot loader',
                             'Running'], timeout=600)
        rawc.expect('Requesting system reboot', timeout=300)
        self.system.set_state(OpSystemState.IPLing)
        self.system.goto_state(OpSystemState.PETITBOOT_SHELL)
        OpTestInstallUtil.stop_server()
        OpTestInstallUtil.set_bootable_disk(self.host.get_scratch_disk())
        self.system.goto_state(OpSystemState.OS)
        con = self.system.sys_get_ipmi_console()
        self.system.host_console_login()
        self.system.host_console_unique_prompt()
        con.run_command("uname -a")
        con.run_command("cat /etc/os-release")
        # Run additional host commands if any from user
        if self.conf.args.host_cmd:
            con.run_command(self.conf.args.host_cmd)
