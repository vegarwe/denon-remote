#ifndef _MQTT_OTA_H
#define _MQTT_OTA_H

#include <stdbool.h>
#include <HardwareSerial.h>
#include <Update.h>


void mqtt_ota_setup(HardwareSerial* dbg = NULL, String topicPrefix = "");
void mqtt_ota_handle_payload(String topic, char * payload, size_t length);
void mqtt_ota_loop();

#endif//_MQTT_OTA_H

