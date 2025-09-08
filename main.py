# streamlit_app.py
import streamlit as st
import ssl
import threading
import time
from datetime import datetime
import paho.mqtt.client as mqtt
from streamlit_autorefresh import st_autorefresh

# === Secrets (from .streamlit/secrets.toml) ===
BROKER     = st.secrets["MQTT_BROKER"]
PORT       = int(st.secrets["MQTT_PORT"])
TOPIC      = st.secrets["MQTT_TOPIC"]        # "picow/gen"
CLIENT_ID  = st.secrets["MQTT_CLIENT_ID"]
USERNAME   = st.secrets["MQTT_USERNAME"]
PASSWORD   = st.secrets["MQTT_PASSWORD"]

# === Page ===
st.set_page_config(page_title="PicoW Generation Monitor", page_icon="🔆", layout="centered")
st.title("🔆 PicoW Generation Monitor")

# === Shared state in session ===
if "latest_value" not in st.session_state:
    st.session_state.latest_value = None
if "last_ts" not in st.session_state:
    st.session_state.last_ts = None
if "mqtt_ok" not in st.session_state:
    st.session_state.mqtt_ok = False
if "mqtt_thread_started" not in st.session_state:
    st.session_state.mqtt_thread_started = False

# === MQTT callbacks ===
def on_connect(client, userdata, flags, rc):
    st.session_state.mqtt_ok = (rc == 0)
    if rc == 0:
        client.subscribe(TOPIC)
    else:
        print("❌ MQTT connect failed:", rc)

def on_message(client, userdata, msg):
    try:
        val = float(msg.payload.decode().strip())
        st.session_state.latest_value = val
        st.session_state.last_ts = datetime.now()
    except Exception as e:
        print("Decode error:", e)

# === MQTT background thread (single start) ===
def start_mqtt():
    client = mqtt.Client(client_id=CLIENT_ID, clean_session=True)
    client.username_pw_set(USERNAME, PASSWORD)
    client.tls_set_context(ssl.create_default_context())   # TLS for HiveMQ Cloud
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT, keepalive=60)
    client.loop_forever()

if not st.session_state.mqtt_thread_started:
    threading.Thread(target=start_mqtt, daemon=True).start()
    st.session_state.mqtt_thread_started = True

# === Light status row ===
col1, col2 = st.columns(2)
with col1:
    st.write("**Broker**:", BROKER)
with col2:
    st.write("**Topic**:", TOPIC)

# === Auto-refresh (2s) ===
st_autorefresh(interval=2000, key="refresh")

# === UI ===
if st.session_state.latest_value is not None:
    st.metric("Current Generation", f"{st.session_state.latest_value:.2f} %")
    age = (datetime.now() - st.session_state.last_ts).total_seconds() if st.session_state.last_ts else None
    st.caption(f"Last update: {st.session_state.last_ts.strftime('%H:%M:%S')} (age ~{int(age)}s)" if age is not None else "Last update: just now")
else:
    if st.session_state.mqtt_ok:
        st.info("Connected. Waiting for first message…")
    else:
        st.warning("Connecting to MQTT… If this persists, check credentials/TLS and broker reachability.")

# Optional small note
st.caption("Tip: Your Pico W publishes every ~2s. This page refreshes every 2s to show the latest value.")
