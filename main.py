import streamlit as st
import paho.mqtt.client as mqtt
import ssl
import threading
import queue
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import altair as alt
from streamlit_autorefresh import st_autorefresh

# ---------- Page & Theme ----------
st.set_page_config(page_title="Solar Generation Dashboard", page_icon="☀️", layout="wide")
alt.data_transformers.enable('default', max_rows=None)

# Auto-refresh ~2.5s (keeps UI snappy)
st_autorefresh(interval=2500, key="refresh")

# ---------- Sidebar Controls ----------
st.sidebar.header("⚙️ Settings")
panel_rating_w = st.sidebar.number_input("Panel Rating (W at 100%)", min_value=10, max_value=5000, value=100, step=10)
use_percent_input = st.sidebar.selectbox("Incoming MQTT Value", ["Percent 0–100", "Watts"], index=0)
smooth_window = st.sidebar.slider("Smoothing Window (samples)", 1, 20, 4, help="Moving average for charts")
clear_btn = st.sidebar.button("🧹 Clear Data")
st.sidebar.markdown("---")
st.sidebar.caption("Tip: change rating for realistic kWh. Data is computed from actual time deltas.")

# ---------- Session State ----------
if 'gen' not in st.session_state:
    st.session_state['gen'] = None

if 'data' not in st.session_state or clear_btn:
    st.session_state['data'] = pd.DataFrame(columns=['Timestamp', 'Generation'])

# ---------- MQTT (cached once) ----------
@st.cache_resource
def init_mqtt_client():
    q = queue.Queue()

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("Connected to MQTT Broker")
            client.subscribe(st.secrets.MQTT_TOPIC)   # e.g., "picow/generation"
            print(f"Subscribed: {st.secrets.MQTT_TOPIC}")
        else:
            print("MQTT connect failed:", rc)

    def on_message(client, userdata, msg):
        try:
            val = float(msg.payload.decode('utf-8'))
            q.put(val)
        except Exception as e:
            print("Bad payload:", e)

    def worker():
        c = mqtt.Client(client_id=st.secrets.MQTT_CLIENT_ID, protocol=mqtt.MQTTv311)
        c.username_pw_set(st.secrets.MQTT_USERNAME, st.secrets.MQTT_PASSWORD)
        c.tls_set(cert_reqs=ssl.CERT_NONE, tls_version=ssl.PROTOCOL_TLSv1_2)
        c.tls_insecure_set(True)
        c.on_connect = on_connect
        c.on_message = on_message
        c.connect(st.secrets.MQTT_BROKER, st.secrets.MQTT_PORT, keepalive=60)
        c.loop_forever()

    t = threading.Thread(target=worker, name="MQTTThread", daemon=True)
    t.start()
    return q

q = init_mqtt_client()

# ---------- Ingest new samples ----------
try:
    while True:
        v = q.get_nowait()
        st.session_state['gen'] = v
        st.session_state['data'] = pd.concat(
            [st.session_state['data'], pd.DataFrame({'Timestamp': [datetime.now()], 'Generation': [v]})],
            ignore_index=True
        )
except queue.Empty:
    pass

# Make a safe copy for charts/calcs
df = st.session_state['data'].copy()
if not df.empty:
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    # Smooth for nicer visuals (moving average on Generation)
    if smooth_window > 1 and len(df) >= smooth_window:
        df['Gen_smooth'] = df['Generation'].rolling(window=smooth_window, min_periods=1).mean()
    else:
        df['Gen_smooth'] = df['Generation']

    # Compute Power (W)
    if use_percent_input == "Percent 0–100":
        df['Power_W'] = (df['Gen_smooth'].clip(lower=0) / 100.0) * panel_rating_w
        current_label = "Generation (%)"
    else:
        df['Power_W'] = df['Gen_smooth'].clip(lower=0)
        current_label = "Generation (W)"

    # Compute Energy from actual time deltas (Wh then kWh)
    df = df.sort_values('Timestamp')
    df['dt_h'] = df['Timestamp'].diff().dt.total_seconds().fillna(0) / 3600.0
    # Truncate absurd gaps (e.g., first row); optional but keeps totals sane
    df.loc[df['dt_h'] > 0.2, 'dt_h'] = 0.0  # >12 min gap counts as 0
    df['Wh_increment'] = df['Power_W'] * df['dt_h']
    df['Energy_kWh'] = df['Wh_increment'].cumsum() / 1000.0

# ---------- Header & Status ----------
st.title("☀️ Solar Generation — Live Dashboard")

colA, colB, colC, colD = st.columns(4)
if df.empty:
    colA.metric("Current", "—")
    colB.metric("Peak", "—")
    colC.metric("Total Energy", "—")
    colD.metric("Samples", "0")
else:
    # Online status
    last_ts = df['Timestamp'].iloc[-1]
    offline = (datetime.now() - last_ts) > timedelta(seconds=10)

    current_val = df['Generation'].iloc[-1]
    peak_val = df['Generation'].max()
    total_kwh = df['Energy_kWh'].iloc[-1]

    # KPIs
    if use_percent_input == "Percent 0–100":
        colA.metric("Current Generation", f"{current_val:.2f} %")
        colB.metric("Peak Generation", f"{peak_val:.2f} %")
    else:
        colA.metric("Current Generation", f"{df['Power_W'].iloc[-1]:.1f} W")
        colB.metric("Peak Generation", f"{df['Power_W'].max():.1f} W")
    colC.metric("Total Energy", f"{total_kwh:.4f} kWh")
    colD.metric("Samples", f"{len(df)}")

    if offline:
        st.warning("No new data for 10+ seconds (device offline?)")

# ---------- Charts ----------
if not df.empty:
    # Common X
    x_time = alt.X('Timestamp:T', title='Time')

    # 1) Generation % line (or Watts if selected)
    if use_percent_input == "Percent 0–100":
        y_gen = alt.Y('Gen_smooth:Q', title='Generation (%)')
        gen_chart = alt.Chart(df).mark_line(point=True).encode(x=x_time, y=y_gen,
                    tooltip=[alt.Tooltip('Timestamp:T'),
                             alt.Tooltip('Gen_smooth:Q', title='Generation (%)', format='.2f')]) \
                    .properties(title='Live Generation (%)', height=280)
    else:
        y_gen = alt.Y('Power_W:Q', title='Power (W)')
        gen_chart = alt.Chart(df).mark_line(point=True).encode(x=x_time, y=y_gen,
                    tooltip=[alt.Tooltip('Timestamp:T'),
                             alt.Tooltip('Power_W:Q', title='Power (W)', format='.1f')]) \
                    .properties(title='Live Power (W)', height=280)

    # 2) Instant Power area
    power_area = alt.Chart(df).mark_area(opacity=0.35).encode(
        x=x_time,
        y=alt.Y('Power_W:Q', title='Power (W)'),
        tooltip=[alt.Tooltip('Timestamp:T'),
                 alt.Tooltip('Power_W:Q', title='Power (W)', format='.1f')]
    ).properties(title='Instantaneous Power', height=220)

    # 3) Cumulative Energy (kWh) step/area
    energy_area = alt.Chart(df).mark_area(opacity=0.35).encode(
        x=x_time,
        y=alt.Y('Energy_kWh:Q', title='Cumulative Energy (kWh)'),
        tooltip=[alt.Tooltip('Timestamp:T'),
                 alt.Tooltip('Energy_kWh:Q', title='Energy (kWh)', format='.5f')]
    ).properties(title='Cumulative Energy', height=220)

    # 4) Distribution of Generation (% or W)
    if use_percent_input == "Percent 0–100":
        hist = alt.Chart(df).mark_bar().encode(
            x=alt.X('Gen_smooth:Q', bin=alt.Bin(maxbins=30), title='Generation (%)'),
            y=alt.Y('count():Q', title='Samples'),
            tooltip=[alt.Tooltip('count():Q', title='Samples')]
        ).properties(title='Generation Distribution', height=220)
    else:
        hist = alt.Chart(df).mark_bar().encode(
            x=alt.X('Power_W:Q', bin=alt.Bin(maxbins=30), title='Power (W)'),
            y=alt.Y('count():Q', title='Samples'),
            tooltip=[alt.Tooltip('count():Q', title='Samples')]
        ).properties(title='Power Distribution', height=220)

    # Layout
    st.altair_chart(gen_chart.interactive(), use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        st.altair_chart(power_area.interactive(), use_container_width=True)
    with c2:
        st.altair_chart(energy_area.interactive(), use_container_width=True)

    st.altair_chart(hist, use_container_width=True)

    # Download CSV
    csv = df[['Timestamp', 'Generation', 'Gen_smooth', 'Power_W', 'Energy_kWh']].to_csv(index=False).encode('utf-8')
    st.download_button("⬇️ Download Data (CSV)", data=csv, file_name="solar_generation.csv", mime="text/csv")

# ---------- Footer ----------
st.markdown(
    """
    <div style="opacity:0.7; font-size:0.9rem; text-align:center; margin-top: 0.5rem;">
      Data source: Raspberry Pi Pico W via MQTT · Charts: Altair · Calculations: real-time based on actual time deltas
    </div>
    """,
    unsafe_allow_html=True
)
