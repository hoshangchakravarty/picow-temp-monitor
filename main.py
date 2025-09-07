import streamlit as st
import paho.mqtt.client as mqtt
import ssl
import threading
import queue
import pandas as pd
from datetime import datetime
import altair as alt
from streamlit_autorefresh import st_autorefresh

# Optional: avoid Altair data limits & weird dataset reuse issues
alt.data_transformers.enable('default', max_rows=None)

# Auto-refresh ~2.5s
st_autorefresh(interval=2500, key="refresh")

# ---- Session state ----
if 'generation' not in st.session_state:
    st.session_state['generation'] = None

if 'generation_data' not in st.session_state:
    st.session_state['generation_data'] = pd.DataFrame(columns=['Timestamp', 'Generation'])

# ---- MQTT setup (cached) ----
@st.cache_resource
def init_mqtt_client():
    message_queue = queue.Queue()

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("Connected to MQTT Broker!")
            client.subscribe(st.secrets.MQTT_TOPIC)   # e.g., "picow/generation"
            print(f"Subscribed to topic: {st.secrets.MQTT_TOPIC}")
        else:
            print(f"Failed to connect, return code {rc}")

    def on_message(client, userdata, msg):
        try:
            value = float(msg.payload.decode('utf-8'))
            message_queue.put(value)
        except Exception as e:
            print("Bad payload:", e)

    def mqtt_client():
        c = mqtt.Client(client_id=st.secrets.MQTT_CLIENT_ID, protocol=mqtt.MQTTv311)
        c.username_pw_set(st.secrets.MQTT_USERNAME, st.secrets.MQTT_PASSWORD)
        c.tls_set(cert_reqs=ssl.CERT_NONE, tls_version=ssl.PROTOCOL_TLSv1_2)
        c.tls_insecure_set(True)
        c.on_connect = on_connect
        c.on_message = on_message
        c.connect(st.secrets.MQTT_BROKER, st.secrets.MQTT_PORT, keepalive=60)
        c.loop_forever()

    t = threading.Thread(target=mqtt_client, name="MQTTThread", daemon=True)
    t.start()
    return message_queue

message_queue = init_mqtt_client()

# ---- UI ----
st.title("Real-time Solar Generation ⚡️☀️")

current_placeholder = st.empty()
chart_placeholder = st.empty()

# Drain the queue without blocking
try:
    while True:
        gen = message_queue.get_nowait()
        st.session_state['generation'] = gen

        new_row = pd.DataFrame({
            'Timestamp': [datetime.now()],
            'Generation': [gen]  # expect % or W depending on your publisher
        })
        st.session_state['generation_data'] = pd.concat(
            [st.session_state['generation_data'], new_row],
            ignore_index=True
        )
except queue.Empty:
    pass

# Current value
if st.session_state['generation'] is not None:
    # If your Pico sends % brightness: append " %"
    current_placeholder.markdown(
        f"### Current Generation: {st.session_state['generation']} %"
    )
else:
    current_placeholder.markdown("Waiting for data...")

# Chart
df = st.session_state['generation_data']
if not df.empty:
    # Ensure dtype and pass a fresh copy to Altair to avoid "Unrecognized data set"
    df = df.copy()
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])

    # Y-range padding
    y_min = df['Generation'].min()
    y_max = df['Generation'].max()
    pad = (y_max - y_min) * 0.2 if y_max != y_min else 1
    y_domain = [y_min - pad, y_max + pad]

    chart = (
        alt.Chart(df)
        .mark_line(point=True)
        .encode(
            x=alt.X('Timestamp:T', title='Time'),
            y=alt.Y('Generation:Q', title='Generation (%)', scale=alt.Scale(domain=y_domain)),
            tooltip=[alt.Tooltip('Timestamp:T'), alt.Tooltip('Generation:Q', title='Generation')]
        )
        .properties(title='Live Generation Readings', width=700, height=400)
        .interactive()
    )

    chart_placeholder.altair_chart(chart, use_container_width=True)
else:
    chart_placeholder.markdown("Waiting for data to plot...")

st.markdown("""
This project showcases the integration of **IoT devices**, **real-time data streaming**, and **advanced data visualization** to create a sophisticated solar energy generation monitoring solution. Below, you'll find live generation data from a Raspberry Pi Pico W, beautifully plotted for your analysis. ☀️⚡
""")
