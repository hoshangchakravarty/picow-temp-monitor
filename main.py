# streamlit_app.py
import streamlit as st
import ssl
from datetime import datetime
import paho.mqtt.client as mqtt
from streamlit_autorefresh import st_autorefresh

BROKER     = st.secrets["MQTT_BROKER"]
PORT       = int(st.secrets["MQTT_PORT"])
TOPIC      = st.secrets["MQTT_TOPIC"]
CLIENT_ID  = st.secrets["MQTT_CLIENT_ID"]
USERNAME   = st.secrets["MQTT_USERNAME"]
PASSWORD   = st.secrets["MQTT_PASSWORD"]

st.set_page_config(page_title="PicoW Generation Monitor", page_icon="🔆", layout="centered")
st.title("🔆 PicoW Generation Monitor")

if "latest" not in st.session_state:
    st.session_state.latest = None
if "ts" not in st.session_state:
    st.session_state.ts = None
if "connected" not in st.session_state:
    st.session_state.connected = False
if "mqtt_client" not in st.session_state:
    # Create client once
    client = mqtt.Client(client_id=CLIENT_ID, clean_session=True)
    client.username_pw_set(USERNAME, PASSWORD)
    client.tls_set_context(ssl.create_default_context())

    def on_connect(c, u, f, rc):
        st.session_state.connected = (rc == 0)
        if rc == 0:
            c.subscribe(TOPIC)

    def on_message(c, u, msg):
        try:
            st.session_state.latest = float(msg.payload.decode().strip())
            st.session_state.ts = datetime.now()
        except Exception:
            pass

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT, keepalive=60)
    client.loop_start()  # 👈 background network loop handled by Paho
    st.session_state.mqtt_client = client

# UI refresh
st_autorefresh(interval=2000, key="refresh")
c1, c2 = st.columns(2)
c1.write("**Broker**: " + BROKER)
c2.write("**Topic**: " + TOPIC)

if st.session_state.latest is not None:
    st.metric("Current Generation", f"{st.session_state.latest:.2f} %")
    if st.session_state.ts:
        age = (datetime.now() - st.session_state.ts).total_seconds()
        st.caption(f"Last update: {st.session_state.ts.strftime('%H:%M:%S')} (~{int(age)}s ago)")
elif st.session_state.connected:
    st.info("Connected to MQTT. Waiting for first message…")
else:
    st.warning("Connecting to MQTT…")
