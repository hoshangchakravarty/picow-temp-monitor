# streamlit_app.py
import streamlit as st
import ssl
import threading
from datetime import datetime
import paho.mqtt.client as mqtt
from streamlit_autorefresh import st_autorefresh

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

# ===== Thread-safe shared state (no Streamlit calls here) =====
_state_lock = threading.Lock()
_latest_value = {"val": None, "ts": None, "connected": False}

def _set_state(val=None, ts=None, connected=None):
    with _state_lock:
        if val is not None:
            _latest_value["val"] = val
        if ts is not None:
            _latest_value["ts"] = ts
        if connected is not None:
            _latest_value["connected"] = connected

def _get_state():
    with _state_lock:
        return _latest_value["val"], _latest_value["ts"], _latest_value["connected"]

# ===== MQTT callbacks (NO Streamlit APIs here) =====
def on_connect(client, userdata, flags, rc):
    _set_state(connected=(rc == 0))
    if rc == 0:
        client.subscribe(TOPIC)

def on_message(client, userdata, msg):
    try:
        val = float(msg.payload.decode().strip())
        _set_state(val=val, ts=datetime.now())
    except Exception:
        pass

# ===== MQTT loop in a background thread =====
def start_mqtt():
    client = mqtt.Client(client_id=CLIENT_ID, clean_session=True)
    client.username_pw_set(USERNAME, PASSWORD)
    client.tls_set_context(ssl.create_default_context())   # TLS for HiveMQ Cloud
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT, keepalive=60)
    client.loop_forever()

# Start the thread only once per session
if "mqtt_thread_started" not in st.session_state:
    threading.Thread(target=start_mqtt, daemon=True).start()
    st.session_state.mqtt_thread_started = True

# ===== Header info =====
col1, col2 = st.columns(2)
with col1: st.write("**Broker**:", BROKER)
with col2: st.write("**Topic**:", TOPIC)

# Auto-refresh every 2s (no infinite loop)
st_autorefresh(interval=2000, key="refresh")

# ===== UI render from thread-safe state =====
val, ts, connected = _get_state()

if val is not None:
    st.metric("Current Generation", f"{val:.2f} %")
    if ts:
        age = (datetime.now() - ts).total_seconds()
        st.caption(f"Last update: {ts.strftime('%H:%M:%S')} (~{int(age)}s ago)")
elif connected:
    st.info("Connected to MQTT. Waiting for first message…")
else:
    st.warning("Connecting to MQTT… If this persists, verify TLS creds and broker reachability.")

st.caption("Page refreshes every 2s. Pico W publishes every ~2s.")
