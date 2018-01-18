# OpTest Install Utils

import threading
import SocketServer
import BaseHTTPServer
import SimpleHTTPServer

BASE_PATH = ""
INITRD = ""
KS = ""
DISK = ""
USERNAME = ""
PASSWORD = ""

class InstallUtil():
    def __init__(self, base_path="", initrd="initrd.img", vmlinux="vmlinuz",
                 ks="", disk="", password="passw0rd", username="root"):
        global BASE_PATH
        global INITRD
        global VMLINUX
        global KS
        global DISK
        global USERNAME
        global PASSWORD
        BASE_PATH = base_path
        INITRD = initrd
        VMLINUX = vmlinux
        KS = ks
        DISK = disk
        USERNAME = username
        PASSWORD = password


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
            ps = d.format("passw0rd", DISK, DISK, DISK)
            self.wfile.write(ps)
            return
        elif "repo" in self.path:
            self.path = BASE_PATH + self.path
            self.send_header("Content-type", "text/html")
            self.end_headers()
            f = self.send_head()
            if f:
                try:
                    self.copyfile(f, self.wfile)
                finally:
                    f.close()
        else:
            self.send_response(404)
            return

class ThreadedHTTPServer(SocketServer.ThreadingMixIn, BaseHTTPServer.HTTPServer):
    pass

def start_server():
    HOST, PORT = "0.0.0.0", 0
    server = ThreadedHTTPServer((HOST, PORT), ThreadedHTTPHandler)
    ip, port = server.server_address
    print "# Listening on %s:%s" % (ip,port)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    print "# Server running in thread:",server_thread.name
    return port

def stop_server():
    server.shutdown()
    server.server_close()
    return
