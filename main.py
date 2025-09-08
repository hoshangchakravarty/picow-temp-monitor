# streamlit_app.py
import streamlit as st
import paho.mqtt.client as mqtt
import ssl
import threading
import queue
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
from streamlit.runtime.scriptrunner import add_script_run_ctx  # attach context

# --- MUST be first Streamlit call ---
st.set_page_config(page_title="PicoW Generation (Latest)", page_icon="🔆", layout="centered")

# Auto-refresh ~2s (after page_config)
st_autorefresh(interval=2000, key="refresh")

# ---------- Session state ----------
if "gen" not in st.session_state:
    st.session_state.gen = None
if "gen_ts" not in st.session_state:
    st.session_state.gen_ts = None
if "mqtt_started" not in st.session_state:
    st.session_state.mqtt_started = False

# ---------- MQTT init (one-time) ----------
def start_mqtt_thread():
    """
    Spawns a background MQTT subscriber thread and returns a Queue.
    No st.* calls inside the thread. Thread is attached to Streamlit context.
    """
    q = queue.Queue()

    # Copy secrets so thread never touches st.*
    BROKER    = st.secrets.MQTT_BROKER
    PORT      = int(st.secrets.MQTT_PORT)
    TOPIC     = st.secrets.MQTT_TOPIC        # e.g., "picow/gen"
    CLIENT_ID = st.secrets.MQTT_CLIENT_ID
    USERNAME  = st.secrets.MQTT_USERNAME
    PASSWORD  = st.secrets.MQTT_PASSWORD

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            client.subscribe(TOPIC)

    def on_message(client, userdata, msg):
        try:
            val = float(msg.payload.decode("utf-8").strip())
            q.put((val, datetime.now()))
        except Exception:
            pass

    def mqtt_client():
        client = mqtt.Client(client_id=CLIENT_ID, protocol=mqtt.MQTTv311)
        client.username_pw_set(USERNAME, PASSWORD)

        # TLS (insecure verify for quick testing; matches your Pico W)
        client.tls_set(cert_reqs=ssl.CERT_NONE, tls_version=ssl.PROTOCOL_TLSv1_2)
        client.tls_insecure_set(True)

        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(BROKER, PORT, keepalive=60)
        client.loop_forever()

    t = threading.Thread(target=mqtt_client, name="MQTTThread", daemon=True)
    add_script_run_ctx(t)             # <<< prevents ScriptRunContext warnings
    t.start()
    return q

# create/start exactly once and keep the queue
if "msg_queue" not in st.session_state:
    st.session_state.msg_queue = start_mqtt_thread()
    st.session_state.mqtt_started = True

# ---------- UI ----------
st.title("🔆 PicoW Generation (Latest)")

# Drain any new messages from the queue
try:
    while True:
        val, ts = st.session_state.msg_queue.get_nowait()
        st.session_state.gen = val
        st.session_state.gen_ts = ts
except queue.Empty:
    pass

# Show current generation (percent)
if st.session_state.gen is not None:
    st.metric("Current Generation", f"{st.session_state.gen:.2f} %")
    if st.session_state.gen_ts:
        age = (datetime.now() - st.session_state.gen_ts).total_seconds()
        st.caption(f"Last update: {st.session_state.gen_ts.strftime('%H:%M:%S')} (~{int(age)}s ago)")
else:
    st.info("Waiting for data…")

# Small hint row
c1, c2 = st.columns(2)
with c1:
    st.caption(f"Broker: {st.secrets.MQTT_BROKER}")
with c2:
    st.caption(f"Topic: {st.secrets.MQTT_TOPIC} • TLS: on (insecure verify)")
