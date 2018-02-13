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
# OpTest Install Utils
#

import shutil
import urllib2
import os
import threading
import SocketServer
import BaseHTTPServer
import SimpleHTTPServer
import commands
import time
from Exceptions import CommandFailed
import OpTestConfiguration


BASE_PATH = ""
INITRD = ""
VMLINUX = ""
KS = ""
DISK = ""
USERNAME = ""
PASSWORD = ""
REPO = ""
BOOTPATH = ""
conf = OpTestConfiguration.conf


class InstallUtil():
    def __init__(self, base_path="", initrd="", vmlinux="",
                 ks="", boot_path="", repo=""):
        global BASE_PATH
        global INITRD
        global VMLINUX
        global KS
        global DISK
        global USERNAME
        global PASSWORD
        global BOOTPATH
        global REPO
        self.conf = conf
        self.host = conf.host()
        self.system = conf.system()
        self.system.host_console_unique_prompt()
        self.console = self.system.sys_get_ipmi_console()
        self.server = ""
        self.repo = conf.args.os_repo
        REPO = self.repo
        DISK = self.host.get_scratch_disk()
        USERNAME = self.host.username()
        PASSWORD = self.host.password()
        BOOTPATH = boot_path
        BASE_PATH = base_path
        INITRD = initrd
        VMLINUX = vmlinux
        KS = ks

    def wait_for_network(self):
        retry = 30
        while retry > 0:
            try:
                output = self.console.run_command("ifconfig -a")
                return True
            except CommandFailed as cf:
                if cf.exitcode is 1:
                    time.sleep(1)
                    retry = retry - 1
                    pass
                else:
                    raise cf

    def assign_ip_petitboot(self):
        """
        Assign host ip in petitboot
        """
        self.console.run_command("stty cols 300")
        self.console.run_command("stty rows 30")
        # Lets reduce timeout in petitboot
        self.console.run_command("nvram --update-config petitboot,timeout=10")
        cmd = "ip addr|grep -B1 -i %s|grep BROADCAST|awk -F':' '{print $2}'" % self.conf.args.host_mac
        iface = self.console.run_command(cmd)[0].strip()
        cmd = "ifconfig %s %s netmask %s" % (iface, self.host.ip, self.conf.args.host_submask)
        self.console.run_command(cmd)
        cmd = "route add default gateway %s" % self.conf.args.host_gateway
        self.console.run_command_ignore_fail(cmd)
        cmd = "echo 'nameserver %s' > /etc/resolv.conf" % self.conf.args.host_dns
        self.console.run_command(cmd)

    def get_server_ip(self):
        """
        """
        my_ip = ""
        self.wait_for_network()
        # Check if ip is assigned in petitboot
        try:
            self.console.run_command("ping %s -c 1" % self.conf.args.host_gateway)
        except CommandFailed as cf:
            self.assign_ip_petitboot()
        try:
            my_ip = self.system.get_my_ip_from_host_perspective()
        finally:
            self.console.run_command("ping %s -c 1" % my_ip)
            return my_ip

    def start_server(self, server_ip):
        """
        Start local http server
        """
        HOST, PORT = "0.0.0.0", 0
        global REPO
        self.server = ThreadedHTTPServer((HOST, PORT), ThreadedHTTPHandler)
        ip, port = self.server.server_address
        if not REPO:
            REPO = "http://%s:%s/repo" % (server_ip, port)
        print "# Listening on %s:%s" % (ip, port)
        server_thread = threading.Thread(target=self.server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        print "# Server running in thread:", server_thread.name
        return port

    def stop_server(self):
        """
        Stops local http server
        """
        self.server.shutdown()
        self.server.server_close()
        return

    def setup_repo(self, cdrom):
        """
        Sets up repo from given cdrom.
        Check if given cdrom is url or file
        if url, download in the BASE_PATH and
        mount to repo folder

        :params cdrom: OS cdrom path local or remote
        """
        repo_path = os.path.join(BASE_PATH, 'repo')
        abs_repo_path = os.path.abspath(repo_path)
        # Clear already mount repo
        if os.path.ismount(repo_path):
            status, output = commands.getstatusoutput("umount %s" % abs_repo_path)
            if status != 0:
                print "failed to unmount", abs_repo_path
                return ""
        elif os.path.isdir(repo_path):
            shutil.rmtree(repo_path)
        else:
            pass
        if not os.path.isdir(repo_path):
            os.makedirs(abs_repo_path)

        if os.path.isfile(cdrom):
            cdrom_path = cdrom
        else:
            cdrom_url = urllib2.urlopen(cdrom)
            if not cdrom_url:
                print "Unknown cdrom path %s" % cdrom
                return ""
            with open(os.path.join(BASE_PATH, "iso"), 'wb') as f:
                f.write(cdrom_url.read())
            cdrom_path = os.path.join(BASE_PATH, "iso")
        cmd = "mount -t iso9660 -o loop %s %s" % (cdrom_path, abs_repo_path)
        status, output = commands.getstatusoutput(cmd)
        if status != 0:
            print "Failed to mount iso %s on %s\n %s", (cdrom, abs_repo_path,
                                                        output)
            return ""
        return abs_repo_path

    def extract_install_files(self, repo_path):
        """
        extract the install file from given repo path

        :params repo_path: os repo path either local or remote
        """
        vmlinux_src = os.path.join(repo_path, BOOTPATH, VMLINUX)
        initrd_src = os.path.join(repo_path, BOOTPATH, INITRD)
        vmlinux_dst = os.path.join(BASE_PATH, VMLINUX)
        initrd_dst = os.path.join(BASE_PATH, INITRD)
        # let us make sure, no old vmlinux, initrd
        if os.path.isfile(vmlinux_dst):
            os.remove(vmlinux_dst)
        if os.path.isfile(initrd_dst):
            os.remove(initrd_dst)

        if os.path.isdir(repo_path):
            try:
                shutil.copyfile(vmlinux_src, vmlinux_dst)
                shutil.copyfile(initrd_src, initrd_dst)
            except Exception:
                return False
        else:
            vmlinux_file = urllib2.urlopen(vmlinux_src)
            initrd_file = urllib2.urlopen(initrd_src)
            if not (vmlinux_file and initrd_file):
                print "Unknown repo path %s, %s" % (vmlinux_src, initrd_src)
                return False
            try:
                with open(vmlinux_dst, 'wb') as f:
                    f.write(vmlinux_file.read())
                with open(initrd_dst, 'wb') as f:
                    f.write(initrd_file.read())
            except Exception:
                return False
        return True

    def set_bootable_disk(self, disk):
        """
        Sets the given disk as default bootable entry in petitboot
        """
        self.system.sys_set_bootdev_no_override()
        self.system.host_console_unique_prompt()
        self.console.run_command("stty cols 300")
        self.console.run_command("stty rows 30")
        # FIXME: wait till the device(disk) discovery in petitboot
        time.sleep(60)
        cmd = 'blkid %s-*' % disk
        output = self.console.run_command(cmd)
        uuid = output[0].split(':')[1].split('=')[1].replace("\"", "")
        cmd = 'nvram --update-config "auto-boot?=true"'
        output = self.console.run_command(cmd)
        cmd = 'nvram --update-config petitboot,bootdevs=uuid:%s' % uuid
        output = self.console.run_command(cmd)
        cmd = 'nvram --print-config'
        output = self.console.run_command(cmd)
        return


class ThreadedHTTPHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
    def do_HEAD(self):
        # FIXME: Local repo unable to handle http request while installation
        # Avoid using cdrom if your kickstart file needs repo, if installation
        # just needs vmlinx and initrd from cdrom, cdrom still can be used.
        if "repo" in self.path:
            self.path = BASE_PATH + self.path
            f = self.send_head()
            if f:
                f.close()
        else:
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()

    def do_GET(self):
        if "repo" in self.path:
            self.path = BASE_PATH + self.path
            f = self.send_head()
            if f:
                try:
                    self.copyfile(f, self.wfile)
                finally:
                    f.close()
        else:
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            print "# Webserver was asked for: ", self.path
            if self.path == "/%s" % VMLINUX:
                f = open("%s/%s" % (BASE_PATH, VMLINUX), "r")
                d = f.read()
                self.wfile.write(d)
                f.close()
                return
            elif self.path == "/%s" % INITRD:
                f = open("%s/%s" % (BASE_PATH, INITRD), "r")
                d = f.read()
                self.wfile.write(d)
                f.close()
                return
            elif self.path == "/%s" % KS:
                f = open("%s/%s" % (BASE_PATH, KS), "r")
                d = f.read()
                if "hostos" in BASE_PATH:
                    ps = d.format(REPO, PASSWORD, DISK, DISK, DISK)
                elif "rhel" in BASE_PATH:
                    ps = d.format(REPO, PASSWORD, DISK, DISK, DISK)
                elif "ubuntu" in BASE_PATH:
                    ps = d.format("openpower", "example.com",
                                  PASSWORD, PASSWORD, DISK)
                else:
                    print "unknown distro"
                self.wfile.write(ps)
                return
            else:
                self.send_response(404)
                return


class ThreadedHTTPServer(SocketServer.ThreadingMixIn, BaseHTTPServer.HTTPServer):
    pass
