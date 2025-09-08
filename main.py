# streamlit_app.py
import streamlit as st
import paho.mqtt.client as mqtt
import ssl
import threading
import queue
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# Auto-refresh ~2.5s (matches Pico W publish cadence)
st_autorefresh(interval=2000, key="refresh")

# ---------- Session state ----------
if "gen" not in st.session_state:
    st.session_state.gen = None
if "gen_ts" not in st.session_state:
    st.session_state.gen_ts = None

# ---------- MQTT init (one-time) ----------
@st.cache_resource
def init_mqtt_client():
    """
    Creates a background MQTT subscriber thread and returns a thread-safe queue.
    The thread NEVER touches st.* APIs—only pushes values into the queue.
    """
    q = queue.Queue()

    # Capture secrets once so the thread doesn't touch st.*
    BROKER    = st.secrets.MQTT_BROKER
    PORT      = int(st.secrets.MQTT_PORT)
    TOPIC     = st.secrets.MQTT_TOPIC       # e.g., "picow/gen"
    CLIENT_ID = st.secrets.MQTT_CLIENT_ID
    USERNAME  = st.secrets.MQTT_USERNAME
    PASSWORD  = st.secrets.MQTT_PASSWORD

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            client.subscribe(TOPIC)
        # No streamlit calls here

    def on_message(client, userdata, msg):
        try:
            val = float(msg.payload.decode("utf-8").strip())
            q.put((val, datetime.now()))
        except Exception:
            pass

    def mqtt_client():
        client = mqtt.Client(client_id=CLIENT_ID, protocol=mqtt.MQTTv311)
        client.username_pw_set(USERNAME, PASSWORD)

        # TLS (insecure verify allowed for quick testing, matches your Pico W)
        client.tls_set(
            cert_reqs=ssl.CERT_NONE,
            tls_version=ssl.PROTOCOL_TLSv1_2,
        )
        client.tls_insecure_set(True)

        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(BROKER, PORT, keepalive=60)
        client.loop_forever()

    t = threading.Thread(target=mqtt_client, name="MQTTThread", daemon=True)
    t.start()
    return q

msg_queue = init_mqtt_client()

# ---------- UI ----------
st.set_page_config(page_title="PicoW Generation (Latest)", page_icon="🔆", layout="centered")
st.title("🔆 PicoW Generation (Latest)")

# Drain any new messages from the queue
try:
    while True:
        val, ts = msg_queue.get_nowait()
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
    st.caption(f"Topic: {st.secrets.MQTT_TOPIC}  •  TLS: on (insecure verify)")
