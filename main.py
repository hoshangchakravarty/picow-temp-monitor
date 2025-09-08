# streamlit_app.py
import streamlit as st
import ssl
from datetime import datetime
import paho.mqtt.client as mqtt
from streamlit_autorefresh import st_autorefresh
from queue import Queue, Empty

# ===== Secrets (.streamlit/secrets.toml) =====
BROKER     = st.secrets["MQTT_BROKER"]
PORT       = int(st.secrets["MQTT_PORT"])     # 8883 for HiveMQ Cloud (TLS)
TOPIC      = st.secrets["MQTT_TOPIC"]         # "picow/gen"
CLIENT_ID  = st.secrets["MQTT_CLIENT_ID"]
USERNAME   = st.secrets["MQTT_USERNAME"]
PASSWORD   = st.secrets["MQTT_PASSWORD"]

# ===== Page =====
st.set_page_config(page_title="PicoW Generation Monitor", page_icon="🔆", layout="centered")
st.title("🔆 PicoW Generation Monitor")

# ===== One-time init =====
if "connected" not in st.session_state:
    st.session_state.connected = False
if "latest_val" not in st.session_state:
    st.session_state.latest_val = None
if "latest_ts" not in st.session_state:
    st.session_state.latest_ts = None
if "q" not in st.session_state:
    st.session_state.q = Queue()
if "mqtt_started" not in st.session_state:
    # Create client once
    client = mqtt.Client(client_id=CLIENT_ID, clean_session=True)
    client.username_pw_set(USERNAME, PASSWORD)

    # TLS for HiveMQ Cloud
    ctx = ssl.create_default_context()
    client.tls_set_context(ctx)

    # ---- MQTT callbacks (NO Streamlit calls inside) ----
    def on_connect(c, u, f, rc):
        # push status into queue; main thread will update UI state
        st.session_state.q.put(("connected", (rc == 0)))
        if rc == 0:
            c.subscribe(TOPIC)

    def on_message(c, u, msg):
        try:
            val = float(msg.payload.decode().strip())
            st.session_state.q.put(("value", (val, datetime.now())))
        except Exception:
            pass

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT, keepalive=60)
    client.loop_start()  # background network loop managed by Paho
    st.session_state.mqtt_started = True

# ===== Drain queue (main thread only) =====
def drain_queue():
    updated = False
    while True:
        try:
            kind, payload = st.session_state.q.get_nowait()
        except Empty:
            break
        if kind == "connected":
            st.session_state.connected = payload
            updated = True
        elif kind == "value":
            val, ts = payload
            st.session_state.latest_val = val
            st.session_state.latest_ts = ts
            updated = True
    return updated

drain_queue()

# ===== Header info =====
c1, c2 = st.columns(2)
c1.write("**Broker**: " + BROKER)
c2.write("**Topic**: " + TOPIC)

# ===== Auto-refresh every 2s =====
st_autorefresh(interval=2000, key="refresh")

# ===== UI =====
val = st.session_state.latest_val
ts  = st.session_state.latest_ts
if val is not None:
    st.metric("Current Generation", f"{val:.2f} %")
    if ts:
        age = (datetime.now() - ts).total_seconds()
        st.caption(f"Last update: {ts.strftime('%H:%M:%S')} (~{int(age)}s ago)")
elif st.session_state.connected:
    st.info("Connected to MQTT. Waiting for first message…")
else:
    st.warning("Connecting to MQTT…")

st.caption("This page refreshes every 2s. Pico W publishes every ~2s.")
