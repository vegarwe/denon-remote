#ifndef _WIFI_MQTT_H
#define _WIFI_MQTT_H

#include <MQTTClient.h>

void wifi_mqtt_setup(HardwareSerial* dbg = NULL, MQTTClientCallbackSimple messageCb = NULL);
void wifi_mqtt_loop();
void wifi_mqtt_publish(String topic, String payload);

#endif//_WIFI_MQTT_H

