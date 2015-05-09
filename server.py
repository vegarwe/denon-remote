import os
import re
import sys
import json
import time
import serial
import threading
import BaseHTTPServer
from mimetypes import types_map

HOST_NAME = ''
PORT_NUMBER = 8080
script_path = os.path.dirname(os.path.realpath(sys.argv[0]))

#default_handler = SimpleHTTPServer.SimpleHTTPRequestHandler

class Denon(object):
    MV = re.compile('MV([0-9]{1,2})([0-9]*)')

    def __init__(self, port='/dev/ttyAMA0', baudrate=9600):
        self.s = serial.Serial(port, timeout=.1, baudrate=baudrate)
        self.status = {}

    def cmd(self, cmd):
        print "cmd %r" % cmd
        self.s.write('%s\r' % cmd)

    def request_status(self):
        self.cmd("MU?")
        self.cmd("SI?")
        self.cmd("PW?")
        self.cmd("MV?")
        return self.status

    def close(self):
        self.s.close()

    def start(self):
        self.t1_stop = threading.Event()
        self.t1 = threading.Thread(target=self.run)
        self.t1.start()
        time.sleep(.01) # Allow read thread to start

    def stop(self):
        self.t1_stop.set()
        self.t1.join()

    def run(self):
        for event in self._get_event():
            print 'event %r' % (event)
            self._parse_event(event)

    def _get_event(self):
        data = ''
        while not self.t1_stop.is_set():
            tmp = self.s.read(1) # Wait for read timeout
            if tmp == '':
                continue
            data += tmp + self.s.read(self.s.inWaiting()) # Read all buffered

            #print 'read buffer %r' % data
            while True:
                i = data.find('\r')
                if i < 0: break
                yield data[:i]
                data = data[i+1:]

    def _parse_event(self, event):
        if event.startswith("MU"):
            self.status['MU'] = event.rstrip('\r')
        if event.startswith("SI"):
            self.status['SI'] = event.rstrip('\r')
        if event.startswith("PW"):
            self.status['PW'] = event.rstrip('\r')
        if event.startswith("MV"):
            m = Denon.MV.search(event)
            if m:
                volume = 1 + int(m.group(1)) # Is of by one for some reason
                if m.group(2) != '':
                    volume += int(m.group(2)) / 10.
                self.status['MV'] = volume

denon = None

class MyHandler(BaseHTTPServer.BaseHTTPRequestHandler):

    def do_PUT(self):
        if self.path.startswith('/api/'):
            return self.put_api()
        self.send_error(404)

    def do_GET(self):

        if self.path.startswith('/api/'):
            return self.get_api()

        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(INDEX_HTML)
        else:
            fname,ext = os.path.splitext(self.path)
            if ext in (".html", ".css"):
                try:
                    full_file_name = os.path.join(script_path, self.path.lstrip('/'))
                    with open(full_file_name) as f:
                        self.send_response(200)
                        self.send_header('Content-type', types_map[ext])
                        self.end_headers()
                        self.wfile.write(f.read())
                except IOError:
                    print 'file not found %r' % full_file_name
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

INDEX_HTML = """
<!DOCTYPE html>
<html ng-app="denonRemoteApp">
    <head>
        <title>Title goes here.</title>
        <script src="https://ajax.googleapis.com/ajax/libs/angularjs/1.3.14/angular.min.js"></script>
        <style>
            .input li {
                list-style: none;
            }
            .input li {
                width:  200px;
            }
            .input button {
                padding: 10px;
                margin:   5px;
            }
            .full button {
                width:  90%;
            }
            .split button {
                width:  41%;
            }
        </style>
    </head>
    <body ng-controller="DenonCtrl">
        <ul class='input'>
            <li class='split'>
                <button ng-click='post_cmd("PWON")'         class='button'> ON </button>
                <button ng-click='post_cmd("PWSTANDBY")'    class='button'> STANDBY </button>
            </li>
            <li class='split'>
                <button ng-click='post_cmd("MUON")'         class='button'> mute </button>
                <button ng-click='post_cmd("MUOFF")'        class='button'> unmute </button>
            </li>
            <li class='full'><button ng-click='post_cmd("SIDVD")'        class='button'> Chromecast (DVD) </button></li>
            <li class='full'><button ng-click='post_cmd("SITV")'         class='button'> TV </button></li>
            <li class='full'><button ng-click='post_cmd("SIVCR")'        class='button'> Jack plug (VCR/iPod) </button></li>
            <li class='full'><button ng-click='post_cmd("SIHDP")'        class='button'> HDMI plug (HDP) </button></li>
            <li class='full'><button ng-click='post_cmd("SITUNER")'      class='button'> Radio (TUNER) </button></li>
            <li class='full'><button ng-click='post_cmd("SISAT/CBL")'    class='button'> RasbPi (SAT/CBL) </button></li>
        </ul>

        Status
        <ul>
            <li>MU: {{ denon_status.MU }}</li>
            <li>SI: {{ denon_status.SI }}</li>
            <li>MV: {{ denon_status.MV }}</li>
            <li>PW: {{ denon_status.PW }}</li>
        </ul>
    </body>

    <script type="text/javascript">
        var denonRemoteApp = angular.module('denonRemoteApp', []);

        denonRemoteApp.controller('DenonCtrl', function ($scope, $http, $interval) {
            $scope.get_status = function () {
                console.log("get_status");
                $http.get("http://192.168.1.13:8080/api/status")
                   .success(function(data, status, headers, config) {
                       $scope.denon_status = data;
                   }).error(function(data, status, headers, config) {
                       $scope.errorMsg = "Failed to get status";
                   });
            }

            $scope.post_cmd = function (cmd) {
                console.log("post_cmd " + cmd);
                $http.put("http://192.168.1.13:8080/api/cmd", cmd)
                      .success(function(data, status, headers, config) {
                             //$scope.denon_status = data;
                    }).error(function(data, status, headers, config) {
                           $scope.errorMsg = "Failed to mute";
                    });

            }

            $scope.get_status();
            var timer=$interval(function() {
                console.log("timer");
                $scope.get_status();
            }, 2000);

        });
    </script>

</html>
"""

if __name__ == '__main__':
    denon = Denon()
    if len(sys.argv) == 2:
        denon.cmd(sys.argv[1])
        print '%s: %r' % (sys.argv[1], denon.s.read(512))
        raise SystemExit(0)

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
