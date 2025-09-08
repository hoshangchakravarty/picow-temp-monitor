# streamlit_app.py
import streamlit as st
import ssl, threading
from datetime import datetime
import paho.mqtt.client as mqtt
from streamlit_autorefresh import st_autorefresh
from streamlit.runtime.scriptrunner import add_script_run_ctx  # 👈 attach context

BROKER     = st.secrets["MQTT_BROKER"]
PORT       = int(st.secrets["MQTT_PORT"])
TOPIC      = st.secrets["MQTT_TOPIC"]
CLIENT_ID  = st.secrets["MQTT_CLIENT_ID"]
USERNAME   = st.secrets["MQTT_USERNAME"]
PASSWORD   = st.secrets["MQTT_PASSWORD"]

st.set_page_config(page_title="PicoW Generation Monitor", page_icon="🔆", layout="centered")
st.title("🔆 PicoW Generation Monitor")

# --- thread-safe state (no st.* inside) ---
_state_lock = threading.Lock()
_latest = {"val": None, "ts": None, "connected": False}

def _set(val=None, ts=None, connected=None):
    with _state_lock:
        if val is not None: _latest["val"] = val
        if ts  is not None: _latest["ts"]  = ts
        if connected is not None: _latest["connected"] = connected

def _get():
    with _state_lock:
        return _latest["val"], _latest["ts"], _latest["connected"]

# --- MQTT callbacks ---
def on_connect(client, userdata, flags, rc):
    _set(connected=(rc == 0))
    if rc == 0:
        client.subscribe(TOPIC)

def on_message(client, userdata, msg):
    try:
        _set(val=float(msg.payload.decode().strip()), ts=datetime.now())
    except Exception:
        pass

# --- background thread with context attached ---
def start_mqtt():
    client = mqtt.Client(client_id=CLIENT_ID, clean_session=True)
    client.username_pw_set(USERNAME, PASSWORD)
    client.tls_set_context(ssl.create_default_context())   # TLS
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT, keepalive=60)
    client.loop_forever()

if "mqtt_thread_started" not in st.session_state:
    t = threading.Thread(target=start_mqtt, daemon=True, name="start_mqtt")
    add_script_run_ctx(t)  # 👈 this silences the ScriptRunContext warning
    t.start()
    st.session_state.mqtt_thread_started = True

# --- UI ---
st_autorefresh(interval=2000, key="refresh")
c1, c2 = st.columns(2)
c1.write("**Broker**: " + BROKER)
c2.write("**Topic**: " + TOPIC)

val, ts, connected = _get()
if val is not None:
    st.metric("Current Generation", f"{val:.2f} %")
    if ts:
        age = (datetime.now() - ts).total_seconds()
        st.caption(f"Last update: {ts.strftime('%H:%M:%S')} (~{int(age)}s ago)")
elif connected:
    st.info("Connected to MQTT. Waiting for first message…")
else:
    st.warning("Connecting to MQTT…")
