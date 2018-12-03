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
import paho.mqtt.client as mqtt


class Denon(object):
    MV = re.compile('MV([0-9]{1,2})([0-9]*)')

    def __init__(self, port='/dev/ttyAMA0', baudrate=9600):
        self.s = serial.Serial(port, timeout=.1, baudrate=baudrate)
        self.status = {}
        self.mqtt_client = None
        self._lock = threading.Lock()

    def cmd(self, cmd):
        #print "cmd   %r" % cmd
        with self._lock:
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
        self.t1 = threading.Thread(target=self._run)
        self.t1.start()
        time.sleep(.01) # Allow read thread to start

    def stop(self):
        self.t1_stop.set()
        self.t1.join()

    def _run(self):
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

        if self.mqtt_client:
            self.mqtt_client.send_status(self.status)


class MQTTDenon(object):
    def __init__(self, hostname, username, password):
        self.mqtt_host  = hostname
        self.mqtt_port  = 1883
        self.mqtt_user  = username
        self.mqtt_pass  = password
        self.status     = {}
        self.client     = mqtt.Client()
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def cmd(self, cmd):
        print("cmd   %r" % cmd)
        self.client.publish("/raiomremote/cmd", cmd)

    def request_status(self):
        print("request_status")
        self.client.publish("/raiomremote/request_status", "")
        return self.status

    def start(self):
        print("start")
        self.client.username_pw_set(self.mqtt_user, self.mqtt_pass)
        self.client.connect(self.mqtt_host, self.mqtt_port, 60)
        self.client.loop_start()

    def stop(self):
        print("stop")
        self.client.loop_stop()
        self.client.disconnect()

    def close(self):
        print("close")

    def _on_connect(self, client, userdata, flags, rc):
        print("Connected with result code %s" % rc)

        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        client.subscribe("/raiomremote/events/#")


    def _on_message(self, client, userdata, msg):
        print("Topic %s, payload %s" % (msg.topic, msg.payload))

        try:
            self.status = json.loads(msg.payload.decode('utf-8'))

            for ws_client in WSHandler.participants:
                d = ws_client.write_message(self.status)
        except Exception as e:
            print('Exception %r %s' % (e, e))

class MQTTClient(object):
    def __init__(self, denon, hostname, username, password):
        self.denon      = denon
        self.mqtt_host  = hostname
        self.mqtt_port  = 1883
        self.mqtt_user  = username
        self.mqtt_pass  = password
        self.status     = {}
        self.client     = mqtt.Client()
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

        # TODO: Fix event handler callback instead...
        denon.mqtt_client = self

    def start(self):
        self.client.username_pw_set(self.mqtt_user, self.mqtt_pass)
        self.client.connect(self.mqtt_host, self.mqtt_port, 60)
        self.client.loop_start()

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()

    def send_status(self, status):
        self.client.publish("/raiomremote/events/status", json.dumps(status))

    def _on_connect(self, client, userdata, flags, rc):
        print("Connected with result code %s" % rc)

        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        client.subscribe("/raiomremote/cmd/#")


    def _on_message(self, client, userdata, msg):
        #print("Topic %s, payload %s" % (msg.topic, msg.payload))
        cmds = ("MU?",
                "SI?",
                "PW?",
                "MV?",

                "PWON",
                "PWSTANDBY",
                "MVUP",
                "MVDOWN",
                "MUON",
                "MUOFF",
                "SIDVD",
                "SITV",
                "SIVCR",
                "SIHDP",
                "SITUNER",
                "SISAT/CBL")

        approved_command = False
        for cmd in cmds:
            if msg.payload.startswith(cmd):
                approved_command = True
                break

        if approved_command:
            self.denon.cmd(msg.payload)


class WSHandler(tornado.websocket.WebSocketHandler):
    participants = set()

    def check_origin(self, origin):
        return True

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
        print('path %s' % path)
        if not self.denon:
            self.send_error(412)
            return

        if path == 'api/cmd':
            d = json.loads(self.request.body.decode('utf-8'))
            self.denon.cmd(d['cmd'])
            self.set_status(200)
            self.write(self.denon.status)
        elif path == 'api/request_status':
            self.denon.request_status()
            self.set_status(200)
            self.write('OK')
        else:
            self.send_error(405)

    def get(self, path):
        if path == 'api/status':
            self.set_status(200)
            self.write(self.denon.status)
        elif path == '' or path == 'index.html':
            self.set_status(200)
            self.set_header("Content-type", "text/html")
            self.write(open('index.html').read())
        elif path in ['sw.js']:
            self.set_status(200)
            self.set_header("Content-type", "text/javascript")
            self.write(open(path).read())
        else:
            self.send_error(404)


script_path = os.path.dirname(os.path.realpath(__file__))

application = tornado.web.Application([
    (r'/ws', WSHandler),
    (r"/static/(.*)", tornado.web.StaticFileHandler, dict(path=script_path)),
    (r'/(.*)', MainHandler),
])

def main():
    config = json.load(open('server.json'))
    if 'serial' in config:
        denon = Denon(config['serial'])
        mqtt_client = MQTTClient(denon, config['mqtt_host'], config['mqtt_user'], config['mqtt_pass'])
        mqtt_client.start()
    else:
        denon = MQTTDenon(config['mqtt_host'], config['mqtt_user'], config['mqtt_pass'])

    denon.start()
    denon.request_status()
    MainHandler.denon = denon

    http_server = tornado.httpserver.HTTPServer(application)
    if 'http_addr' in config:
        http_server.listen(config['http_port'], address=config['http_addr'])
    else:
        http_server.listen(config['http_port'])

    try:
        tornado.ioloop.IOLoop.instance().start()
    except KeyboardInterrupt:
        pass

    tornado.ioloop.IOLoop.instance().stop()
    denon.stop()
    denon.close()
    if 'serial' in config:
        mqtt_client.stop()

if __name__ == '__main__':
    main()
