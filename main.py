# streamlit_app.py
import streamlit as st
import paho.mqtt.client as mqtt
import ssl
import threading

# === Secrets ===
BROKER = st.secrets["MQTT_BROKER"]
PORT = int(st.secrets["MQTT_PORT"])
TOPIC = st.secrets["MQTT_TOPIC"]
CLIENT_ID = st.secrets["MQTT_CLIENT_ID"]
USERNAME = st.secrets["MQTT_USERNAME"]
PASSWORD = st.secrets["MQTT_PASSWORD"]

# === Shared state ===
latest_value = {"gen": None}

# === MQTT callbacks ===
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        client.subscribe(TOPIC)
    else:
        print("❌ Failed to connect, code:", rc)

def on_message(client, userdata, msg):
    try:
        latest_value["gen"] = float(msg.payload.decode())
    except:
        pass

# === MQTT background thread ===
def mqtt_thread():
    client = mqtt.Client(CLIENT_ID)
    client.username_pw_set(USERNAME, PASSWORD)
    client.tls_set_context(ssl.create_default_context())
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT, keepalive=60)
    client.loop_forever()

threading.Thread(target=mqtt_thread, daemon=True).start()

# === Streamlit UI ===
st.set_page_config(page_title="PicoW Generation Monitor", page_icon="⚡", layout="centered")
st.title("🔆 PicoW Generation Monitor")

placeholder = st.empty()

while True:
    if latest_value["gen"] is not None:
        placeholder.metric("Current Generation", f"{latest_value['gen']} %")
    else:
        placeholder.info("Waiting for data from Pico W...")

    # refresh UI every 2s
    st.sleep(2)
