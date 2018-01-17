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
import pexpect
import socket
import threading
import SocketServer
import BaseHTTPServer
import subprocess

import OpTestConfiguration
from common.OpTestUtil import OpTestUtil
from common.OpTestSystem import OpSystemState
from common.OpTestError import OpTestError
from common.Exceptions import CommandFailed

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

class InstallHostOS(unittest.TestCase):
    def setUp(self):
        conf = OpTestConfiguration.conf
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
        time.sleep(100)
        self.c = self.system.sys_get_ipmi_console()
        self.system.host_console_unique_prompt()

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
                my_ip = "9.40.192.92"
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

        scratch_disk_size = self.host.get_scratch_disk_size(self.c)

        # start our web server
        HOST, PORT = "0.0.0.0", 0
        server = ThreadedHTTPServer((HOST, PORT), ThreadedHTTPHandler)
        ip, port = server.server_address
        print "# Listening on %s:%s" % (ip,port)
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        print "# Server running in thread:",server_thread.name

        my_ip = "9.40.192.92"
        #my_ip = self.system.get_my_ip_from_host_perspective()

        if not "qemu" in self.bmc_type:
            # we need to go and grab things from the network to netboot
            arp = subprocess.check_output(['arp', self.host.hostname()]).split('\n')[1]
            arp = arp.split()
            host_mac_addr = arp[2]
            print "# Found host mac addr %s", host_mac_addr
            ks_url = 'http://%s:%s/hostos.ks' % (my_ip, port)
            kernel_args = "ifname=net0:%s ip=%s::9.40.192.1:255.255.255.0:%s:net0:none nameserver=9.0.9.1 inst.ks=%s" % (host_mac_addr,
                                                                                                                         self.host.ip,
                                                                                                                         self.host.hostname(),
                                                                                                                         ks_url)
            self.system.goto_state(OpSystemState.PETITBOOT_SHELL)
            self.c.run_command("[ -f vmlinuz ]&& rm -f vmlinuz;[ -f initrd.img ] && rm -f initrd.img;echo 'true'")
            self.c.run_command("wget http://%s:%s/hostos/vmlinuz" % (my_ip, port))
            self.c.run_command("wget http://%s:%s/hostos/initrd.img" % (my_ip, port))
            self.c.run_command("kexec -i initrd.img -c \"%s\" vmlinuz -l" % kernel_args)
            self.c.get_console().send("kexec -e\n")
        else:
            pass

        # Do things
        rawc = self.c.get_console()
        rawc.expect('opal: OPAL detected',timeout=60)
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
        #server.shutdown()
        server.server_close()

class ThreadedHTTPHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        conf = OpTestConfiguration.conf
        host = conf.host()
        print "# Webserver was asked for: ", self.path
        if self.path == "/hostos/vmlinuz":
            f = open("osimages/hostos/vmlinuz", "r")
            d = f.read()
            self.wfile.write(d)
            f.close()
            return
        elif self.path == "/hostos/initrd.img":
            f = open("osimages/hostos/initrd.img", "r")
            d = f.read()
            self.wfile.write(d)
            f.close()
            return
        elif self.path == "/hostos.ks":
            host_username = host.username()
            host_password = host.password()
            f = open("osimages/hostos/hostos.ks", "r")
            d = f.read()
            ps = d.format(host_password, host.get_scratch_disk(),
                          host.get_scratch_disk(),
                          host.get_scratch_disk())
            self.wfile.write(ps)
            return
        else:
            self.send_response(404)
            return

class ThreadedHTTPServer(SocketServer.ThreadingMixIn, BaseHTTPServer.HTTPServer):
    pass
