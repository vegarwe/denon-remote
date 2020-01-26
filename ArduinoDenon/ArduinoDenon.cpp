#include <ArduinoJson.h>
#include <HardwareSerial.h>
#include <MQTT.h>
#include <WiFi.h>

#include "config.h"


#define WIFI_CONNECTION_TIMEOUT 30000;


// WiFi client and MQTT client
static WiFiClient client;
static MQTTClient mqtt(384);

// Object used for debug output
static HardwareSerial* debugger = NULL;
static HardwareSerial* denon_serial = NULL;

static unsigned int curr_status_counter = 0;
static unsigned int recv_status_counter = 0;


struct denon_status
{
    String MU;
    String SI;
    String PW;
    float  MV;
};

static struct denon_status status;


void send_cmd(const char* cmd)
{
    denon_serial->print(cmd);
    denon_serial->print("\r");
}


void handle_event(String& event)
{
    if (event.endsWith("\r"))
    {
        event.remove(event.length() - 1, 1);
    }

    // ('MUOFF\r', 'SITV\r', 'PWON\r', 'MUOFF\r', 'Z2MUOFF\r', 'MV35\r', 'MVMAX 98\r', 'PWSTANDBY\r', 'ZMOFF\r', 'MSDTS NEO:6 C\r')
    if (event.startsWith("MU"))
    {
        status.MU = event;
    }
    else if (event.startsWith("SI"))
    {
        status.SI = event;
    }
    else if (event.startsWith("PW"))
    {
        status.PW = event;
    }
    else if (event.startsWith("MVMAX"))
    {
        // Ignore
        return;
    }
    else if (event.startsWith("MV"))
    {
        event = event.substring(2);
        status.MV = event.toFloat();
        if (event.length() == 3)
        {
            status.MV = status.MV / 10.F;
        }
        status.MV += 1.0F; // Is of by one for some reason
    }
    else
    {
        if (debugger) debugger->print("Unhandled event: '");
        if (debugger) debugger->print(event);
        if (debugger) debugger->println("'");
        return;
    }

    StaticJsonDocument<255> json;
    //json["id"] = WiFi.macAddress();
    //json["IP"] = WiFi.localIP().toString();
    //json["up"] = millis();
    json["MU"] = status.MU;
    json["SI"] = status.SI;
    json["PW"] = status.PW;
    json["MV"] = status.MV;

    if (debugger)
    {
        debugger->print("status: ");
        serializeJsonPretty(json, *debugger);
        debugger->println("");
    }

    if (status.MV != 0.0F)
    {
        String msg;
        serializeJson(json, msg);
        mqtt.publish("/raiomremote/events/status", msg.c_str());
    }

    if (recv_status_counter < curr_status_counter)
    {
        // TODO: Only increment if response to status command
        recv_status_counter++;
    }
}


void request_status()
{
    curr_status_counter = 0;
    recv_status_counter = 0;
}


void send_request_cmd(char* cmd)
{
    send_cmd(cmd);
    if (debugger) debugger->println("Sending MU?");
    curr_status_counter++;
}


void request_status_loop()
{
    // TODO: Implement as list of commands to send?
    //char status_cmds[][] = {
    //        "MU?",
    //        "SI?",
    //        "PW?",
    //        "MV?"};

    if (recv_status_counter < curr_status_counter)
    {
        return;
    }

    switch (curr_status_counter)
    {
        case 0: send_request_cmd("MU?"); break;
        case 1: send_request_cmd("SI?"); break;
        case 2: send_request_cmd("PW?"); break;
        case 3: send_request_cmd("MV?"); break;
        default: break;
    }
}


void serial_read_loop()
{
    if (! denon_serial->available())
    {
        return;
    }

    digitalWrite(LED_BUILTIN, HIGH);
    String event;
    event.reserve(64);
    while (denon_serial->available())
    {
        char newByte = denon_serial->read();
        event += newByte;

        if (newByte == '\r')
        {
            handle_event(event);
            event = "";
        }
    }

    digitalWrite(LED_BUILTIN, LOW);
}


void wifi_loop()
{
    if (WiFi.status() == WL_CONNECTED)
    {
        return;
    }

    // Connect to WiFi access point.
    Serial.print("Connecting to WiFi network: ");
    Serial.println(WIFI_SSID);

    // Make one first attempt at connect, this seems to considerably speed up the first connection
    WiFi.disconnect();
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    delay(1000);

    // Loop (forever...), waiting for the WiFi connection to complete
    long vTimeout = millis() + WIFI_CONNECTION_TIMEOUT;
    while (WiFi.status() != WL_CONNECTED) {
        delay(100);
        if (debugger) debugger->print(".");

        // If we timed out, disconnect and try again
        if (vTimeout < millis())
        {
            if (debugger)
            {
                debugger->print("Timout during connect. WiFi status is: ");
                debugger->println(WiFi.status());
            }
            WiFi.disconnect();
            WiFi.begin(WIFI_SSID, WIFI_PASS);
            vTimeout = millis() + WIFI_CONNECTION_TIMEOUT;
        }
        yield();
    }

    Serial.println("");
    Serial.println("WiFi connected");

    if (debugger) {
        debugger->print("IP address: ");
        debugger->println(WiFi.localIP());
    }
}


void mqtt_setup()
{
    Serial.print("Connecting MQTT to ");
    Serial.println(MQTT_HOST);

    String mqttClientID(WiFi.macAddress());

    // Wait for the MQTT connection to complete
    while (!mqtt.connected()) {
        if (! mqtt.connect(mqttClientID.c_str(), MQTT_USER, MQTT_PASS))
        {
            if (debugger) debugger->println("MQTT connect failed, trying again in 5 seconds");

            // Wait 2 seconds before retrying
            mqtt.disconnect();
            delay(1000);
            continue;
        }

        // Allow some resources for the WiFi connection
        yield();

        mqtt.subscribe("/raiomremote/cmd/#");
        mqtt.subscribe("/raiomremote/api/#");
    }

    Serial.println("Successfully connected to MQTT!");
}


void mqtt_on_message(String &topic, String &payload)
{

    if (debugger) {
        debugger->print("mqtt_on_message: ");
        debugger->print("[");
        debugger->print(topic);
        debugger->print("] ");
        debugger->println(payload);
    }

    if (topic == "/raiomremote/cmd")
    {
        if (payload == "MU?"        ||
                payload == "SI?"        ||
                payload == "PW?"        ||
                payload == "MV?"        ||

                payload == "PWON"       ||
                payload == "PWSTANDBY"  ||
                payload == "MVUP"       ||
                payload == "MVDOWN"     ||
                payload == "MUON"       ||
                payload == "MUOFF"      ||
                payload == "SIDVD"      ||
                payload == "SITV"       ||
                payload == "SIVCR"      ||
                payload == "SIHDP"      ||
                payload == "SITUNER"    ||
                payload == "SISAT/CBL")
        {
            send_cmd(payload.c_str());
        }
    }
    else if (topic == "/raiomremote/api")
    {
        if (payload == "request_status")
        {
            if (debugger) debugger->println("request_status");
            request_status();
        }
    }
}


void setup()
{
    Serial.begin(115200);
    debugger = &Serial;

    if (debugger) {
        delay(2000);
        debugger->println("");
#if defined(ARDUINO_NodeMCU_32S)
        debugger->println("NodeMCU-32S starting...");
#elif defined(ARDUINO_FEATHER_ESP32)
        debugger->println("Adafruit ESP32 Feather starting...");
#else
        debugger->println("Starting...");
#endif
    }

    pinMode(LED_BUILTIN, OUTPUT);

    // Setup Denon Serial port an status
    status.MU = "unknown";
    status.SI = "unknown";
    status.PW = "unknown";
    status.MV = 0.0f;

#if defined(ARDUINO_NodeMCU_32S)
    denon_serial = &Serial1;
#elif defined(ARDUINO_FEATHER_ESP32)
    denon_serial = &Serial2;
#else
    denon_serial = &Serial2;
#endif
    denon_serial->begin(9600);

    request_status();

    // Setup Wifi
    WiFi.enableAP(false);
    WiFi.mode(WIFI_STA);
    wifi_loop();

    // Setup MQTT
    mqtt.begin(MQTT_HOST, client);
    mqtt.onMessage(mqtt_on_message);
    mqtt_setup();
}


void loop()
{
    serial_read_loop();
    request_status_loop();

    wifi_loop();
    mqtt.loop();
    delay(10); // <- fixes some issues with WiFi stability

    // Reconnect to WiFi and MQTT as needed
    if (!mqtt.connected()) {
        mqtt_setup();
    }
}

