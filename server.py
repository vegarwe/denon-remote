import json
import os
import re
import serial
import sys
import time
import threading
import tornado.ioloop
import tornado.httpserver
import tornado.web
import tornado.websocket

class Denon(object):
    MV = re.compile('MV([0-9]{1,2})([0-9]*)')

    def __init__(self, port='/dev/ttyAMA0', baudrate=9600):
        self.s = serial.Serial(port, timeout=.1, baudrate=baudrate)
        self.status = {}

    def cmd(self, cmd):
        #print "cmd   %r" % cmd
        self.s.write('%s\r' % cmd)

    def request_status(self):
        self.cmd("MU?")
        time.sleep(.001)
        self.cmd("SI?")
        time.sleep(.001)
        self.cmd("PW?")
        time.sleep(.001)
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
            #print 'event %r' % (event)
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

        for client in WSHandler.participants:
            #print "client", client
            client.write_message(self.status)

class WSHandler(tornado.websocket.WebSocketHandler):
    participants = set()

    def open(self):
        #print 'connection opened'
        self.participants.add(self)

    def on_message(self, message):
        pass
        #print 'message received %s' % message

    def on_close(self):
        #print 'connection closed'
        self.participants.remove(self)

class MainHandler(tornado.web.RequestHandler):
    denon = None

    def put(self, path):
        if not denon:
            self.send_error(412)
            return

        if path == 'api/cmd':
            d = json.loads(self.request.body)
            denon.cmd(d['cmd'])
            self.set_status(200)
            self.write(denon.status)
        elif path == 'api/request_status':
            denon.request_status()
            self.set_status(200)
            self.write('OK')
        else:
            self.send_error(405)

    def get(self, path):
        if path == 'api/status':
            self.set_status(200)
            self.write(denon.status)
        elif path == '' or path == 'index.html':
            self.set_status(200)
            self.set_header("Content-type", "text/html")
            self.write(INDEX_HTML)
        else:
            self.send_error(404)


# TODO: Show errorMsg
INDEX_HTML = """
<!DOCTYPE html>
<html ng-app="denonRemoteApp">
<head>
    <title>Raiom remote</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="shortcut icon" href="static/favicon.ico">
    <link rel="stylesheet" href="http://maxcdn.bootstrapcdn.com/bootstrap/3.3.4/css/bootstrap.min.css">
    <style>
        button {
            width:         151px;
            height:         40px;
            margin:          5px;
            margin-bottom:   8px !important;
        }

        table {
            margin-left:    10px;
            font-size:      20px;
        }
        td {
            padding-left:         10px;
        }

    </style>
    <script src="https://ajax.googleapis.com/ajax/libs/angularjs/1.3.14/angular.min.js"></script>
</head>
<body ng-controller="DenonCtrl">

<div class="container">

    Input
    <div>
        <button class="btn" ng-click='put_cmd("PWON")'     > ON </button>
        <button class="btn" ng-click='put_cmd("PWSTANDBY")'> STANDBY </button>
        <button class="btn" ng-click='put_cmd("MVUP")'     > Up </button>
        <button class="btn" ng-click='put_cmd("MVDOWN")'   > Down </button>
        <button class="btn" ng-click='put_cmd("MUON")'     > Mute </button>
        <button class="btn" ng-click='put_cmd("MUOFF")'    > Unmute </button>
        <button class="btn" ng-click='put_cmd("SIDVD")'    > Chromecast (DVD) </button>
        <button class="btn" ng-click='put_cmd("SITV")'     > TV </button>
        <button class="btn" ng-click='put_cmd("SIVCR")'    > Jack plug (VCR/iPod) </button>
        <button class="btn" ng-click='put_cmd("SIHDP")'    > HDMI plug (HDP) </button>
        <button class="btn" ng-click='put_cmd("SITUNER")'  > Radio (TUNER) </button>
        <button class="btn" ng-click='put_cmd("SISAT/CBL")'> RasbPi (SAT/CBL) </button>

        <table class='status'>
            <tr><th>MU:</th><td>{{ denon_status.MU }}</td></tr>
            <tr><th>SI:</th><td>{{ denon_status.SI }}</td></tr>
            <tr><th>MV:</th><td>{{ denon_status.MV }}</td></tr>
            <tr><th>PW:</th><td>{{ denon_status.PW }}</td></tr>
        </table>
    </div>

</div> <!-- end container -->

</body>

<script type="text/javascript">
    var denonRemoteApp = angular.module('denonRemoteApp', []);

    denonRemoteApp.controller('DenonCtrl', function ($scope, $http, $interval, $location) {

        $scope.get_status = function () {
            $http.get("/api/status")
                .success(function(data, status, headers, config) {
                    $scope.denon_status = data;
                }).error(function(data, status, headers, config) {
                    $scope.errorMsg = "Failed to get status";
                    console.log($scope.errorMsg);
                });
        }

        $scope.put_cmd = function (cmd) {
            $http.put("/api/cmd", {'cmd': cmd})
                .success(function(data, status, headers, config) {
                    //$scope.denon_status = data;
                }).error(function(data, status, headers, config) {
                    $scope.errorMsg = "Failed to mute";
                    console.log($scope.errorMsg);
                });

        }

        $scope.request_status = function () {
            console.log("request_status");
            $http.put("/api/request_status")
                .success(function(data, status, headers, config) {
                    //
                }).error(function(data, status, headers, config) {
                    $scope.errorMsg = "Failed to mute";
                    console.log($scope.errorMsg);
                });

        }

        connect = function() {
            $scope.ws = new WebSocket("ws://" + $location.host() + ":" + $location.port() + "/ws");

            $scope.ws.onmessage = function(evt) {
                $scope.denon_status = JSON.parse(evt.data);
                $scope.$apply();
            };

            $scope.ws.onclose = function(evt) {
                console.log("onclose");
            };

            $scope.ws.onopen = function(evt) {
                console.log("onopen");
            };
        }
        $scope.get_status();

        connect();

    });
</script>

</html>
"""

script_path = os.path.dirname(os.path.realpath(sys.argv[0]))

application = tornado.web.Application([
    (r'/ws', WSHandler),
    (r"/static/(.*)", tornado.web.StaticFileHandler, dict(path=script_path)),
    (r'/(.*)', MainHandler),
])

if __name__ == '__main__':
    denon = Denon()
    if len(sys.argv) == 2:
        denon.cmd(sys.argv[1])
        #print '%s: %r' % (sys.argv[1], denon.s.read(512))
        raise SystemExit(0)

    denon.start()
    denon.request_status() # TODO: Exit if failing
    MainHandler.denon = denon

    http_server = tornado.httpserver.HTTPServer(application)
    http_server.listen(80)
    try:
        tornado.ioloop.IOLoop.instance().start()
    except KeyboardInterrupt:
        pass

    tornado.ioloop.IOLoop.instance().stop() # TODO: Do we need to stop?
    denon.stop()
    denon.close()
