import os
import re
import json
import base64
import asyncio
import aiomqtt
import serial_asyncio
import tornado.ioloop
import tornado.httpserver
import tornado.web
import tornado.websocket
import tornado.platform.asyncio

# TODO Update PRECACHE in python based on git hash or MD5?
# done Fix cookie
# done Reconnect websocket (on click, maybe also on timeout)
# done Show websocket status on page
# done python3, asyncio
# done Get ServiceWorker to work with basic auth (and Update PRECACHE in python based on git hash or MD5?)
# done Status on reload
# done Fix password (leaked to GitHub)
# done webworker


SCRIPT_PATH = os.path.dirname(os.path.abspath(__file__))

class Denon(asyncio.Protocol):
    connected = None
    instance = None
    MV = re.compile('MV([0-9]{1,2})([0-9]*)')

    def __init__(self):
        self.status = {}
        self.mqtt_client = None
        self.transport = None
        self.data = bytes()

    def connection_made(self, transport):
        Denon.instance = self # TODO: UUuuuuuuuugly. Please figure out a fix
        self.transport = transport
        self.connected.set()

    def connection_lost(self, exc):
        print('Writer closed')
        self.instance = None

    def cmd(self, cmd):
        #print("cmd   %r" % cmd)
        self.transport.write(bytes(cmd + '\r', 'utf-8'))

    async def request_status(self):
        print('request_status')
        self.cmd("MU?")
        await asyncio.sleep(0.001)
        self.cmd("SI?")
        await asyncio.sleep(0.001)
        self.cmd("PW?")
        await asyncio.sleep(0.001)
        self.cmd("MV?")
        await asyncio.sleep(0.001)
        return self.status

    def close(self):
        print('close')
        self.transport.close()

    async def start(self):
        print('start')

    async def stop(self):
        print('stop')

    def data_received(self, data):
        self.data += data

        if b'\r' in self.data:
            lines = self.data.split(b'\r')
            self.data = lines[-1] # Keep partial command
            for line in lines[:-1]:
                self._parse_event(line.decode('utf-8'))

    def _parse_event(self, event):
        #print('event', event)
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
        if event.startswith("MVMAX"):
            return # Ignore event

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

        loop = asyncio.get_event_loop()
        self.client     = aiomqtt.Client(loop)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.connected  = asyncio.Event(loop=loop)

    def cmd(self, cmd):
        print("cmd   %r" % cmd)
        self.client.publish("/raiomremote/cmd", cmd)

    async def request_status(self):
        print("request_status")
        self.client.publish("/raiomremote/api", "request_status")
        return self.status

    async def start(self):
        print("start")
        self.client.username_pw_set(self.mqtt_user, self.mqtt_pass)
        self.client.loop_start()
        await self.client.connect(self.mqtt_host, self.mqtt_port, 60)
        await self.connected.wait()

    async def stop(self):
        print("stop")
        await self.client.loop_stop()
        self.client.disconnect()

    def close(self):
        print("close")

    def _on_connect(self, client, userdata, flags, rc):
        print("Connected with result code %s" % rc)

        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        client.subscribe("/raiomremote/events/#")

        self.connected.set()

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

        loop = asyncio.get_event_loop()
        self.client     = aiomqtt.Client(loop)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.connected  = asyncio.Event(loop=loop)

        # TODO: Fix event handler callback instead...
        denon.mqtt_client = self

    async def start(self):
        self.client.username_pw_set(self.mqtt_user, self.mqtt_pass)
        self.client.loop_start()
        await self.client.connect(self.mqtt_host, self.mqtt_port, 60)
        await self.connected.wait()

    async def stop(self):
        print("stop")
        await self.client.loop_stop()
        self.client.disconnect()

    def send_status(self, status):
        self.client.publish("/raiomremote/events/status", json.dumps(status))

    def _on_connect(self, client, userdata, flags, rc):
        print("Connected with result code %s" % rc)

        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        client.subscribe("/raiomremote/cmd/#")
        client.subscribe("/raiomremote/api/#")

        self.connected.set()

    def _handle_cmd(self, cmd):
        cmds = (b"MU?",
                b"SI?",
                b"PW?",
                b"MV?",

                b"PWON",
                b"PWSTANDBY",
                b"MVUP",
                b"MVDOWN",
                b"MUON",
                b"MUOFF",
                b"SIDVD",
                b"SITV",
                b"SIVCR",
                b"SIHDP",
                b"SITUNER",
                b"SISAT/CBL")

        approved_command = False
        for i in cmds:
            if cmd.startswith(i):
                approved_command = True
                break

        if approved_command:
            self.denon.cmd(cmd.decode('utf-8'))

    def _handle_api(self, cmd):
        #print('_handle_api', cmd)
        if cmd == 'request_status':
            self.denon.request_status()

    def _on_message(self, client, userdata, msg):
        #print("Topic %s, payload %s" % (msg.topic, msg.payload))

        if   msg.topic == '/raiomremote/api':
            return self._handle_api(msg.payload)
        elif msg.topic == '/raiomremote/cmd':
            return self._handle_cmd(msg.payload)


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
    config = None

    def __check_auth(self):
        if 'auth_data' not in self.config:
            return True

        auth_cookie = self.get_cookie("auth_data")
        if auth_cookie == self.config['auth_data']:
            return True

        auth_header = self.request.headers.get("Authorization", "")
        auth_decoded = base64.b64decode(auth_header[6:]).decode('ascii')
        if not auth_decoded == self.config['auth_data']:
            self.set_status(401)
            self.set_header('WWW-Authenticate', 'Basic realm=\"research\"')
            self.set_header("Content-type", "text/plain")
            self.write('401: No can do')
            tornado.web.Finish()
            return False

        return True

    def put(self, path):
        if not self.__check_auth():
            return
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
            self.set_header("Content-type", "application/json")
            self.write(json.dumps(self.denon.status))
        elif path in ['', 'index.html']:
            self.set_status(200)
            self.set_header("Content-type", "text/html")
            self.write(open(os.path.join(SCRIPT_PATH, 'index.html')).read())
        elif path in ['sw.js']:
            self.set_status(200)
            self.set_header("Content-type", "text/javascript")
            self.write(open(os.path.join(SCRIPT_PATH, path)).read())
        elif path in ['login']:
            if not self.__check_auth():
                return
            if 'auth_data' in self.config:
                self.set_cookie("auth_data", self.config['auth_data'], expires_days=300)
            self.redirect('index.html')
        else:
            self.send_error(404)


def main():
    application = tornado.web.Application([
        (r'/ws', WSHandler),
        (r"/static/(.*)", tornado.web.StaticFileHandler, dict(path=SCRIPT_PATH)),
        (r'/(.*)', MainHandler),
    ])

    tornado.platform.asyncio.AsyncIOMainLoop().install()
    loop = asyncio.get_event_loop()

    config = json.load(open(os.path.join(SCRIPT_PATH, 'server.json')))
    if 'serial' in config:
        # TODO: Ugly fugly, please fix
        Denon.connected  = asyncio.Event(loop=loop)
        asyncio.ensure_future(serial_asyncio.create_serial_connection(loop, Denon, config['serial'], baudrate=9600))
        loop.run_until_complete(Denon.connected.wait())
        denon = Denon.instance

        mqtt_client = MQTTClient(denon, config['mqtt_host'], config['mqtt_user'], config['mqtt_pass'])
        loop.run_until_complete(mqtt_client.start())
    else:
        denon = MQTTDenon(config['mqtt_host'], config['mqtt_user'], config['mqtt_pass'])

    MainHandler.denon = denon
    MainHandler.config = config

    loop.run_until_complete(denon.start())
    loop.run_until_complete(denon.request_status())

    http_server = tornado.httpserver.HTTPServer(application)
    if 'http_addr' in config:
        http_server.listen(config['http_port'], address=config['http_addr'])
    else:
        http_server.listen(config['http_port'])

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass

    print("Stopping")
    loop.run_until_complete(denon.stop())
    denon.close()
    if 'serial' in config:
        loop.run_until_complete(mqtt_client.stop())
    loop.stop()


if __name__ == '__main__':
    main()
