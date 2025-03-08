import aiomqtt
import asyncio
import json
import os
import ssl

import tornado.httpserver
import tornado.web
import tornado.websocket

from tornado.ioloop import IOLoop

# TODO Update PRECACHE in python based on git hash or MD5?


SCRIPT_PATH = os.path.dirname(os.path.abspath(__file__))


class Denon():
    def __init__(self, config):
        self.config = config
        self.status = {}

        loop = asyncio.get_event_loop()
        self.client = None

    async def cmd(self, cmd):
        if not self.client:
            return

        print("cmd   %r" % cmd)

        if cmd == "ToggleTV":
            await self.client.publish("denon/24:62:AB:D2:80:6C/irrgang", "power")
        else:
            await self.client.publish("/raiomremote/cmd", cmd)

    async def request_status(self):
        if not self.client:
            return

        print("request_status")
        await self.client.publish("/raiomremote/api", "request_status")
        return self.status

    async def run(self):
        client_params = {
                'hostname': self.config['mqtt_host'],
                'port':     self.config['mqtt_port']
        }

        if 'mqtt_user' in self.config:
            client_params['username'] = self.config['mqtt_user']
            client_params['password'] = self.config['mqtt_pass']
        if 'mqtt_cert' in self.config:
            #tls_context = ssl.create_default_context()
            client_params['tls_params'] = aiomqtt.TLSParameters(
                    ca_certs    = self.config['mqtt_ca'],
                    certfile    = self.config['mqtt_cert'],
                    keyfile     = self.config['mqtt_key'],
                    cert_reqs   = ssl.CERT_REQUIRED)
        elif 'mqtt_ca' in self.config:
            client_params['tls_params'] = aiomqtt.TLSParameters(
                   #tls_version = ssl.PROTOCOL_TLS,
                   #cert_reqs   = ssl.CERT_REQUIRED,
                   #cert_reqs   = ssl.CERT_OPTIONAL,
                    cert_reqs   = ssl.CERT_NONE,
                    ca_certs    = self.config['mqtt_ca']
                    )

        print(client_params)
        async with aiomqtt.Client(**client_params) as client:
            print('connected?')
            self.client = client
            await client.subscribe("/raiomremote/events/#")
            await self.request_status()
            async for msg in client.messages:
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

        auth_cookie = self.get_secure_cookie("auth_data")
        if not auth_cookie:
            return False

        return auth_cookie.decode() == self.config['auth_data']

    def put(self, path):
        if not self.__check_auth():
            return self.send_error(401)
        if not self.denon:
            return self.send_error(412)

        if path == 'api/cmd':
            cmd = json.loads(self.request.body.decode('utf-8'))
            IOLoop.current().spawn_callback(self.denon.cmd, cmd['cmd'])
            self.set_status(200)
            self.write(self.denon.status)
        elif path == 'api/request_status':
            IOLoop.current().run_sync(self.denon.request_status)
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
    config = json.load(open(os.path.join(SCRIPT_PATH, 'server.json')))

    # Webserver
    application = tornado.web.Application([
        (r'/ws', WSHandler),
        (r"/static/(.*)", tornado.web.StaticFileHandler, dict(path=SCRIPT_PATH)),
        (r'/(.*)', MainHandler),
    ], cookie_secret="d0870884-495c-4758-8c86-24383dc0ee69")

    http_server = tornado.httpserver.HTTPServer(application)
    if 'http_addr' in config:
        http_server.listen(config['http_port'], address=config['http_addr'])
    else:
        http_server.listen(config['http_port'])
    print('http_port', config['http_port'])

    # MQTT client
    denon = Denon(config)

    MainHandler.denon = denon
    MainHandler.config = config

    # Runtime loop
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(denon.run())
    except KeyboardInterrupt:
        pass

    print("Stopping")
    loop.stop()


if __name__ == '__main__':
    main()
