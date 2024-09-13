import machine
import time
import network
import utime
import socket
from umqtt.simple import MQTTClient
import ssl

from picozero import pico_temp_sensor, pico_led

led = machine.Pin('LED', machine.Pin.OUT)

def connect():
    ssid = "xxx"
    password = "xxx"
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid,password)

    while not wlan.isconnected():
        led.value(True)
        time.sleep(0.5)
        led.value(False)
        time.sleep(1)
        print("Connecting...")
        
        led.value(True)
        print("Connected to WiFi!")
        ip = wlan.ifconfig()[0]
        print("IP Address: ", ip)
        return ip
        
    if wlan.isconnected():
        print("Already Connected!")
        ip = wlan.ifconfig()[0]
        print("IP Address: ", ip)
        return ip


def connectMQTT():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.verify_mode = ssl.CERT_NONE
    client = MQTTClient(client_id=b"xxx",
    port=xxx,
    user=b"xxx",
    password=b"xxx",
    keepalive=7200,
    ssl=context
    )

    client.connect()
    return client

def publish(topic, value):
    print(topic)
    print(value)
    client.publish(topic.encode('utf-8'), str(value).encode('utf-8'))
    print("Publish Done")
    

ip = connect()
client = connectMQTT()

while True:
    temp = pico_temp_sensor.temp
    print("Internal Temperature:", temp, "Celcius")
    publish('picow/temperature', temp)
    led.value(True)
    time.sleep(0.5)
    led.value(False)
    utime.sleep(5)