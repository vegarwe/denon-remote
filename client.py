import paho.mqtt.client as mqtt


def on_connect(client, userdata, flags, rc):
    print("Connected with result code %s" % rc)

    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe("/raiomremote/#")


def on_message(client, userdata, msg):
    print("Topic %s, payload %s" % (msg.topic, msg.payload))


def main():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    #client.connect("iot.eclipse.org", 1883, 60)
    client.username_pw_set("raiom", "FjaseFlyndreFisk")
    client.connect("kanskje.de", 1883, 60)

    # Blocking call that processes network traffic, dispatches callbacks and
    # handles reconnecting.
    # Other loop*() functions are available that give a threaded interface and a
    # manual interface.
    client.loop_forever()


if __name__ == "__main__":
    main()
