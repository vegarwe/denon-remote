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
        print "cmd   %r" % cmd
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
            denon.cmd(content)
            json.dump(denon.status, self.wfile)
        elif self.path == '/api/request_status':
            denon.request_status()
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

# TODO: Show errorMsg
INDEX_HTML = """
<!DOCTYPE html>
<html ng-app="denonRemoteApp">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="http://maxcdn.bootstrapcdn.com/bootstrap/3.3.4/css/bootstrap.min.css">
  <style>
      .col-md-4.split button {
          width:  151px;
          padding: 12px;
          margin:   2px;
      }
      .col-md-4 button {
          width:  310px;
          padding: 12px;
          margin:   2px;
      }
  </style>
  <script src="https://ajax.googleapis.com/ajax/libs/angularjs/1.3.14/angular.min.js"></script>
</head>
<body ng-controller="DenonCtrl">

<div class="container">

    <!--
    <div class="jumbotron">
      <h1>W3Schools Demo</h1> 
      <p>Resize this responsive page!</p> 
    </div>
    -->
    
    Input
    <div class="row">
        <div class="col-md-4 split">
            <button ng-click='post_cmd("PWON")'     > ON </button>
            <button ng-click='post_cmd("PWSTANDBY")'> STANDBY </button>
        </div>
        <div class="col-md-4 split">
            <button ng-click='put_cmd("MVUP")'                        > Up </button>
            <button ng-click='put_cmd("MUON")'                        > mute </button>
        </div>
        <div class="col-md-4 split">
            <button ng-click='put_cmd("MVDOWN")'                      > Down </button>
            <button ng-click='put_cmd("MUOFF")'                       > unmute </button>
        </div>
        <div class="col-md-4"><button ng-click='post_cmd("SIDVD")'    > Chromecast (DVD) </button></div>
        <div class="col-md-4"><button ng-click='post_cmd("SITV")'     > TV </button></div>
        <div class="col-md-4"><button ng-click='post_cmd("SIVCR")'    > Jack plug (VCR/iPod) </button></div>
        <div class="col-md-4"><button ng-click='post_cmd("SIHDP")'    > HDMI plug (HDP) </button></div>
        <div class="col-md-4"><button ng-click='post_cmd("SITUNER")'  > Radio (TUNER) </button></div>
        <div class="col-md-4"><button ng-click='post_cmd("SISAT/CBL")'> RasbPi (SAT/CBL) </button></div>
    </div>

    Status
    <ul>
        <li>MU: {{ denon_status.MU }}</li>
        <li>SI: {{ denon_status.SI }}</li>
        <li>MV: {{ denon_status.MV }}</li>
        <li>PW: {{ denon_status.PW }}</li>
    </ul>

</div> <!-- end container -->

</body>

<script type="text/javascript">
    var denonRemoteApp = angular.module('denonRemoteApp', []);
    
    denonRemoteApp.controller('DenonCtrl', function ($scope, $http, $interval) {

        $scope.get_status = function () {
            $http.get("http://192.168.1.13:8080/api/status")
               .success(function(data, status, headers, config) {
                   $scope.denon_status = data;
               }).error(function(data, status, headers, config) {
                   $scope.errorMsg = "Failed to get status";
                   console.log($scope.errorMsg);
               });
        }
    
        $scope.put_cmd = function (cmd) {
            $http.put("http://192.168.1.13:8080/api/cmd", cmd)
                  .success(function(data, status, headers, config) {
                         //$scope.denon_status = data;
                }).error(function(data, status, headers, config) {
                    $scope.errorMsg = "Failed to mute";
                    console.log($scope.errorMsg);
                });
    
        }
    
        $scope.request_status = function () {
            console.log("request_status");
            $http.put("http://192.168.1.13:8080/api/request_status")
                  .success(function(data, status, headers, config) {
                }).error(function(data, status, headers, config) {
                    $scope.errorMsg = "Failed to mute";
                    console.log($scope.errorMsg);
                });
    
        }
    
        $scope.request_status();
        var timer=$interval(function() {
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
