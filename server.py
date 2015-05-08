import os
import json
import time
import serial
import threading
import BaseHTTPServer
from mimetypes import types_map

HOST_NAME = ''
PORT_NUMBER = 8080

#default_handler = SimpleHTTPServer.SimpleHTTPRequestHandler

class Denon(object):
    def __init__(self, port='/dev/ttyAMA0', baudrate=9600):
        self.s = serial.Serial(port, timeout=.3, baudrate=baudrate)
        self.status = {}

    def cmd(self, cmd):
        print "self.s.write %r" % cmd
        self.s.write('%s\r' % cmd)

    def request_status(self):
        self.cmd("MU?")
        self.cmd("SI?")
        return self.status

    def close(self):
        self.s.close()

    def start(self):
        self.t1_stop = threading.Event()
        self.t1 = threading.Thread(target=self._read)
        self.t1.start()

    def stop(self):
        self.t1_stop.set()
        self.t1.join()

    def _read(self):
        while not self.t1_stop.is_set():
            #self.t1_stop.wait(1)
            data = ''
            while not data.endswith('\r'):
                tmp = self.s.read(512) # wait for timeout
                data += tmp
                if tmp == '': break
            print '_read %r' % data
            for i in data.split('\r'):
                self._parse_return(i)
        return data

    def _parse_return(self, data):
        if data.startswith("MU"):
            self.status['MU'] = data.rstrip('\r')
        if data.startswith("SI"):
            self.status['SI'] = data.rstrip('\r')
        print '_parse_return %r %s' % (data, self.status)

denon = Denon()

class MyHandler(BaseHTTPServer.BaseHTTPRequestHandler):

    def do_PUT(self):
        if self.path.startswith('/api/'):
            return self.put_api()
        self.send_error(404)

    def do_GET(self):

        if self.path.startswith('/api/'):
            return self.get_api()

        if self.path == '/':
            self.path = '/index.html'

        fname,ext = os.path.splitext(self.path)
        if ext in (".html", ".css"):
            try:
                with open(os.path.join('WEBROOT', self.path.lstrip('/'))) as f:
                    self.send_response(200)
                    self.send_header('Content-type', types_map[ext])
                    self.end_headers()
                    self.wfile.write(f.read())
            except IOError:
                self.send_error(404)
        else:
            self.send_error(404)

    def put_api(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()

        if self.path == '/api/cmd':
            length = int(self.headers['Content-Length'])
            content = self.rfile.read(length)
            print 'content: %r' % content
            denon.cmd(content)
            json.dump(denon.status, self.wfile)
        else:
            self.send_error(404)
            return

    def get_api(self):
        if self.path == '/api/status':
            return self.get_status()
        else:
            self.send_error(404)

    def get_status(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()

        json.dump(denon.status, self.wfile)

if __name__ == '__main__':
    denon.start()
    denon.request_status() # TODO: Exit if failing

    httpd = BaseHTTPServer.HTTPServer((HOST_NAME, PORT_NUMBER), MyHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()

    denon.stop()
    denon.close()
