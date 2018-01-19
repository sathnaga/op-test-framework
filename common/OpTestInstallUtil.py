# OpTest Install Utils

import shutil
import urllib2
import os
import threading
import SocketServer
import BaseHTTPServer
import SimpleHTTPServer
import commands

BASE_PATH = ""
INITRD = ""
KS = ""
DISK = ""
USERNAME = ""
PASSWORD = ""
BOOTPATH = ""
SERVER = ""
REPO = ""
MY_IP = ""


class InstallUtil():
    def __init__(self, base_path="", initrd="initrd.img", vmlinux="vmlinuz",
                 ks="", disk="", password="passw0rd", username="root",
                 boot_path="", repo="", my_ip=""):
        global BASE_PATH
        global INITRD
        global VMLINUX
        global KS
        global DISK
        global USERNAME
        global PASSWORD
        global BOOTPATH
        global REPO
        global MY_IP
        BASE_PATH = base_path
        INITRD = initrd
        VMLINUX = vmlinux
        KS = ks
        DISK = disk
        USERNAME = username
        PASSWORD = password
        BOOTPATH = boot_path
        REPO = repo
        MY_IP = my_ip


class ThreadedHTTPHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
    def do_HEAD(self):
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
            #self.send_header("Content-type", "text/html")
            #self.end_headers()
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
                if "hostos" or "rhel" in BASE_PATH:
                    ps = d.format(REPO, PASSWORD, DISK, DISK, DISK)
                elif "ubuntu" in BASE_PATH:
                    ps = d.format("openpower", "example.com",
                                  PASSWORD, PASSWORD, USERNAME, PASSWORD, PASSWORD,
                                  DISK, 100000, "op-test-ubuntu-root", "")
                else:
                    print "unknown distro"
                self.wfile.write(ps)
                return
            else:
                self.send_response(404)
                return


class ThreadedHTTPServer(SocketServer.ThreadingMixIn, BaseHTTPServer.HTTPServer):
    pass


def start_server():
    HOST, PORT = "0.0.0.0", 0
    global SERVER
    global REPO
    SERVER = ThreadedHTTPServer((HOST, PORT), ThreadedHTTPHandler)
    ip, port = SERVER.server_address
    if not REPO:
        REPO = "http://%s:%s/repo" % (MY_IP, port)
    print "# Listening on %s:%s" % (ip, port)
    server_thread = threading.Thread(target=SERVER.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    print "# Server running in thread:", server_thread.name
    return port


def stop_server():
    SERVER.shutdown()
    SERVER.server_close()
    return


def setup_repo(cdrom):
    """
    Check if given cdrom is url or file
    if url, download in the BASE_PATH and
    mount to repo folder, have a check if mount
    exists already
    """
    repo_path = os.path.join(BASE_PATH, 'repo')
    if os.path.ismount(repo_path):
        # repo mount exits already clear it
        status, output = commands.getstatusoutput("umount %s" % os.path.abspath(repo_path))
        if status != 0:
            print "failed to unmount",os.path.abspath(repo_path)
            return os.path.abspath(repo_path)
    elif os.path.isdir(repo_path):
        # delete it
        shutil.rmtree(repo_path)
    else:
        pass
    if not os.path.isdir(repo_path):
        os.makedirs(os.path.abspath(repo_path))
    if os.path.isfile(cdrom):
        cmd = "mount -t iso9660 -o loop %s %s" % (cdrom, os.path.abspath(repo_path))
        status, output = commands.getstatusoutput(cmd)
        if status != 0:
            print cdrom, os.path.abspath(repo_path)
            print "Failed to mount iso", output
            return
        return os.path.abspath(repo_path)
    cdrom_file = urllib2.urlopen(cdrom)
    if cdrom_file:
        with open(os.path.join(BASE_PATH, "iso"), 'wb') as f:
            f.write(cdrom_file.read())
        cmd = "mount -t iso9660 -o loop %s %s" % (os.path.join(BASE_PATH, "iso"),
                                                  os.path.abspath(repo_path))
        status, output = commands.getstatusoutput(cmd)
        if status != 0:
            print "Failed to mount iso", output
            return
        return os.path.abspath(repo_path)


def extract_install_files(repo_path):
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
        shutil.copyfile(vmlinux_src, vmlinux_dst)
        shutil.copyfile(initrd_src, initrd_dst)
        return
    vmlinux_file = urllib2.urlopen(vmlinux_src)
    if vmlinux_file:
        with open(vmlinux_dst, 'wb') as f:
            f.write(vmlinux_file.read())
    initrd_file = urllib2.urlopen(initrd_src)
    if initrd_file:
        with open(initrd_dst, 'wb') as f:
            f.write(initrd_file.read())
    return
