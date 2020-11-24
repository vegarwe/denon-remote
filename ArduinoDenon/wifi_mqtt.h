#ifndef _WIFI_MQTT_H
#define _WIFI_MQTT_H

#include <HardwareSerial.h>
#include <MQTTClient.h>

extern MQTTClient mqtt;
void wifi_mqtt_setup(HardwareSerial* dbg, String topicPrefix, MQTTClientCallbackAdvanced messageCb);
bool wifi_mqtt_loop();

#endif//_WIFI_MQTT_H

