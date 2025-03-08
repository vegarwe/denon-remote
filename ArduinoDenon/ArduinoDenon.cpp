#include <Arduino.h>
#include <ArduinoJson.h>
#include <IRremote.h>
#include <HardwareSerial.h>
#include <MQTT.h> // TODO: Remove?
#include <WiFi.h>

#include "wifi_mqtt.h"
#include "mqtt_ota.h"
#include "config.h"


static HardwareSerial*  debugger    = NULL;
static String           mqttPrefix;


static int              RECV_PIN    = 15;
static IRrecv           irrecv(RECV_PIN);
static uint32_t         tvToggle    = 0;

static byte             SEND_PIN    = 19;
static IRsend           irsend(SEND_PIN);


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
        // Only actually toggle if this is not in response to a status command
        if (recv_status_counter >= curr_status_counter)
        {
            tvToggle = millis();
        }
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


void mqttMessageReceived(MQTTClient *client, char topicBuffer[], char payloadBuffer[], int length)
{
    String topic(topicBuffer);
    if (Update.isRunning() || topic.startsWith(mqttPrefix + "/ota/"))
    {
        if (! topic.startsWith(mqttPrefix + "/ota/")) return;

        if (! Update.isRunning())
        {
            irrecv.disableIRIn();
        }
        return mqtt_ota_handle_payload(topic, payloadBuffer, length);
    }

    String payload(payloadBuffer);

    if (debugger)
    {
        debugger->print("mqttMessageReceived: [");
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
    else if (topic.startsWith(mqttPrefix+ "/irrgang") && payload == "power")
    {
        irsend.sendNEC(0x20DF10EF, 32);

    }
}

static String event;

void setup()
{
    debugger = &Serial;

    if (debugger)
    {
        debugger->begin(2000000);
        delay(100);
        debugger->println("");
#if defined(ARDUINO_NodeMCU_32S)
        debugger->println("NodeMCU-32S starting...");
#elif defined(ARDUINO_FEATHER_ESP32)
        debugger->println("Adafruit ESP32 Feather starting...");
#else
        debugger->println("Starting...");
#endif
        delay(500); // TODO: Remove?
    }

    pinMode(LED_BUILTIN, OUTPUT);

    event.reserve(64);

    // Setup Denon Serial port an status
    status.MU = "unknown";
    status.SI = "unknown";
    status.PW = "unknown";
    status.MV = 0.0f;

#if defined(ARDUINO_NodeMCU_32S)
    denon_serial = &Serial2;
#elif defined(ARDUINO_FEATHER_ESP32)
    denon_serial = &Serial1;
#else
    denon_serial = &Serial1;
#endif
    denon_serial->begin(9600);

    request_status();

    mqttPrefix = String(MQTT_ROOT "/") + WiFi.macAddress();
    wifi_mqtt_setup(debugger, mqttPrefix, mqttMessageReceived);
    mqtt_ota_setup(debugger, mqttPrefix);

    irrecv.enableIRIn();

    mqtt.publish(MQTT_ROOT "/control/up", "starting: " + WiFi.macAddress() + " 0x06");
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


void irrgang_loop()
{
    decode_results results;

    if (tvToggle > 0 && (millis() - tvToggle) > 1500)
    {
        tvToggle = 0;
        irsend.sendNEC(0x20DF10EF, 32);
        mqtt.publish(mqttPrefix + "/control/up", "TV power toggled");
    }

    if (! irrecv.decode(&results)) {
        return;
    }

    String type = "UNKNOWN";
    switch (results.decode_type){
        case NEC:           type = "NEC";           break;
        case SONY:          type = "SONY";          break;
        case RC5:           type = "RC5";           break;
        case RC6:           type = "RC6";           break;
        case DISH:          type = "DISH";          break;
        case SHARP:         type = "SHARP";         break;
        case JVC:           type = "JVC";           break;
        case SANYO:         type = "SANYO";         break;
        case MITSUBISHI:    type = "MISUBISHI";     break;
        case SAMSUNG:       type = "SAMSUNG";       break;
        case LG:            type = "LG";            break;
        case WHYNTER:       type = "WHYNTER";       break;
        case AIWA_RC_T501:  type = "AIWARC_T501";   break;
        case PANASONIC:     type = "PNASONIC";      break;
        case DENON:         type = "DENON";         break;
        default:
        case UNKNOWN:       type = "UNKNOWN";       break;
    }

    String data = String("led: ") + type + String("-0x") + String(results.value, HEX);
    mqtt.publish(mqttPrefix + "/control/up", data);
    Serial.print(mqttPrefix + "/control/up: ");
    Serial.println(data);


    static uint32_t prev_time = 0;
    if (millis() - prev_time > 300)
    {
        if (
                (results.decode_type == UNKNOWN && results.value == 0xf4ba2988) // power button?
                ||
                (results.decode_type == SAMSUNG && results.value == 0xe0e040bf) // power button?
            )
        {
            prev_time = millis();

            if (status.PW == "PWON")
            {
                mqtt.publish(mqttPrefix + "/control/up", status.PW + " PWSTANDBY");
                //mqtt.publish("/raiomremote/cmd", "PWSTANDBY");
                send_cmd("PWSTANDBY");
            }
            else
            {
                mqtt.publish(mqttPrefix + "/control/up", status.PW + " PWON");
                //mqtt.publish("/raiomremote/cmd", "PWON");
                send_cmd("PWON");
            }
        }
        else if (results.decode_type == SAMSUNG && results.value == 0xe0e0e01f) // volume up
        {
            prev_time = millis();
            send_cmd("MVUP");
        }
        else if (results.decode_type == SAMSUNG && results.value == 0xe0e0d02f) // volume up
        {
            prev_time = millis();
            send_cmd("MVDOWN");
        }
        else if (results.decode_type == SAMSUNG && results.value == 0xe0e0807f) // Kilde
        {
            prev_time = millis();
            tvToggle = millis();
        }
    }

    irrecv.resume(); // Receive the next value
}


void loop()
{
    serial_read_loop();
    request_status_loop();

    //digitalWrite(LED_BUILTIN, HIGH);

    wifi_mqtt_loop();
    mqtt_ota_loop(); // Will block once update starts

    irrgang_loop();

    yield();
    //digitalWrite(LED_BUILTIN, LOW);
}

