import os
import json
import asyncio
import aiomqtt
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
# done Get ServiceWorker to work with basic auth
# done Status on reload
# done Fix password (leaked to GitHub)
# done webworker


SCRIPT_PATH = os.path.dirname(os.path.abspath(__file__))


class Denon():
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
        self.client.username_pw_set(self.mqtt_user, self.mqtt_pass)
        self.client.loop_start()
        await self.client.connect(self.mqtt_host, self.mqtt_port, 60)
        await self.connected.wait()

    async def stop(self):
        await self.client.loop_stop()
        self.client.disconnect()

    def _on_connect(self, client, userdata, flags, rc):
        print("Connected with result code %s" % rc)

        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        client.subscribe("/raiomremote/events/#")

        self.connected.set()

    def _on_message(self, client, userdata, msg):
        print("Topic %s, payload %s" % (msg.topic, msg.payload))

        self.status = json.loads(msg.payload.decode('utf-8'))

        for ws_client in WSHandler.participants:
            ws_client.write_message(self.status)


class WSHandler(tornado.websocket.WebSocketHandler):
    participants = set()

    def check_origin(self, origin):
        return True

    def open(self, *args, **kwargs):
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
    config = {}

    def __check_auth(self):
        if 'auth_data' not in self.config:
            return True

        auth_cookie = self.get_secure_cookie("auth_data").decode()
        return auth_cookie == self.config['auth_data']

    def put(self, path):
        if not self.__check_auth():
            return self.send_error(401)
        if not self.denon:
            return self.send_error(412)

        if path == 'api/cmd':
            cmd = json.loads(self.request.body.decode('utf-8'))
            self.denon.cmd(cmd['cmd'])
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
        elif path in ['login', 'login.html']:
            if not self.__check_auth():
                self.set_status(200)
                self.set_header("Content-type", "text/html")
                self.write(open(os.path.join(SCRIPT_PATH, 'login.html')).read())
                return
            if 'auth_data' in self.config:
                self.set_secure_cookie("auth_data", self.config['auth_data'], secure=True, expires_days=900)
            self.redirect('index.html')
        else:
            self.send_error(404)

    def post(self, path):
        if path in ['login', 'login.html']:
            auth_data = self.get_body_argument("password", default=None, strip=False)
            if auth_data == self.config['auth_data']:
                self.set_secure_cookie("auth_data", self.config['auth_data'], secure=True, expires_days=900)
                self.redirect('index.html')
            else:
                self.set_status(200)
                self.set_header("Content-type", "text/html")
                self.write(open(os.path.join(SCRIPT_PATH, 'login.html')).read())
        else:
            self.send_error(404)

def main():
    application = tornado.web.Application([
        (r'/ws', WSHandler),
        (r"/static/(.*)", tornado.web.StaticFileHandler, dict(path=SCRIPT_PATH)),
        (r'/(.*)', MainHandler),
    ], cookie_secret="d0870884-495c-4758-8c86-24383dc0ee69")

    tornado.platform.asyncio.AsyncIOMainLoop().install()
    loop = asyncio.get_event_loop()

    config = json.load(open(os.path.join(SCRIPT_PATH, 'server.json')))
    denon = Denon(config['mqtt_host'], config['mqtt_user'], config['mqtt_pass'])

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
    loop.stop()


if __name__ == '__main__':
    main()
