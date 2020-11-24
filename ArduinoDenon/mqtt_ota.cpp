#include "mqtt_ota.h"

#include <string.h>

#include "wifi_mqtt.h"


static HardwareSerial*  debugger = NULL;
static String           mqttPrefix;


void mqtt_ota_setup(HardwareSerial* dbg, String topicPrefix)
{
    mqttPrefix = topicPrefix;
    debugger = dbg;
}


void mqtt_ota_loop()
{
    if (Update.isRunning())
    {
        while (true) wifi_mqtt_loop();
    }
}


void mqtt_ota_handle_payload(String topic, char * payload, size_t length)
{
    if (     topic.endsWith("/ota/down/finished"))
    {
        // TODO: If not running, abort abort abort!
        if (strnlen(payload, length) > 0)
        {
            if (debugger) debugger->printf("Will test MD5 cheksum: %s\n", payload);
            Update.setMD5(payload);
        }

        if (Update.end(true))
        {
            if (debugger) debugger->printf("Restarting after %s OTA\n", (Update.hasError() ? "failed" : "successful"));
            ESP.restart();
        }
        else
        {
            if (debugger) Update.printError(*debugger);
        }
    }
    else if (topic.endsWith("/ota/down/abort"))
    {
        Update.abort();
        ESP.restart();
    }
    else if (topic.endsWith("/ota/down/start"))
    {
        size_t size = String(payload).toInt();

        // TODO: Start a timer!!!

        if (debugger) debugger->printf("ota start: %d\n", size);

        if (Update.begin(size > 0 ? size : UPDATE_SIZE_UNKNOWN))
        {
            mqtt.publish(mqttPrefix + "/ota/up/ready", "20");
        }
        else
        {
            if (debugger) Update.printError(*debugger);
        }
    }
    else if (topic.endsWith("/ota/down/data") && Update.isRunning())
    {
        static uint32_t pkt_count = 1;
        if ((pkt_count % 20) == 0)
        {
            mqtt.publish(mqttPrefix + "/ota/up/progress", "20");

            if (debugger) debugger->printf("Handle payload %d data %d\n", pkt_count, length);
        }

        if (Update.write((uint8_t*)payload, length) != length)
        {
            if (debugger) Update.printError(*debugger);
        }

        pkt_count++;
    }
    else
    {
        if (debugger) debugger->printf("Unknown topic: %s, or update not running\n", topic.c_str());
    }
}

