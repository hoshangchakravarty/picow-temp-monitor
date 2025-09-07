# app.py — Renewable Energy Monitoring for Microgrids in Villages
import warnings
warnings.filterwarnings(
    "ignore",
    message="You passed a `<class 'narwhals.stable.v1.DataFrame'>` to `is_pandas_dataframe`",
    module="altair.utils.data",
)

import streamlit as st
import paho.mqtt.client as mqtt
import ssl
import threading
import queue
import pandas as pd
from datetime import datetime
import altair as alt
from streamlit_autorefresh import st_autorefresh

# ---------- Page Setup ----------
st.set_page_config(
    page_title="Renewable Energy Monitoring for Microgrids in Villages",
    page_icon="🌿",
    layout="wide"
)
alt.data_transformers.enable('default', max_rows=None)

# Auto-refresh ~2.5s
st_autorefresh(interval=2500, key="refresh")

# ---------- Sidebar Controls ----------
st.sidebar.header("⚙️ Microgrid Settings")
panel_rating_w = st.sidebar.number_input("Rated Capacity (W)", min_value=10, max_value=5000, value=100, step=10)
input_type = st.sidebar.selectbox("Incoming MQTT Value", ["Percent 0–100", "Watts"], index=0)
smooth_window = st.sidebar.slider("Smoothing Window (samples)", 1, 20, 4)
clear_btn = st.sidebar.button("🧹 Clear Data")
st.sidebar.markdown("---")
st.sidebar.caption("Village microgrid demo • IoT + MQTT + Streamlit")

# ---------- Session State ----------
if 'gen' not in st.session_state:
    st.session_state['gen'] = None
if 'data' not in st.session_state or clear_btn:
    st.session_state['data'] = pd.DataFrame(columns=['Timestamp', 'Generation'])

# ---------- MQTT Client (cached) ----------
@st.cache_resource
def init_mqtt_client():
    q = queue.Queue(maxsize=500)  # cap queue; we’ll drop oldest if full

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            # Primary topic (required)
            client.subscribe(st.secrets.MQTT_TOPIC)  # e.g. "picow/generation"
            # Optional: second topic (e.g. blackout flag); define MQTT_BLACKOUT in secrets if you need it
            if "MQTT_BLACKOUT" in st.secrets:
                client.subscribe(st.secrets.MQTT_BLACKOUT)  # e.g. "picow/blackout"
        else:
            print("MQTT connect failed:", rc)

    def on_message(client, userdata, msg):
        try:
            # Only treat the main topic as numeric data
            if msg.topic == st.secrets.MQTT_TOPIC:
                val = float(msg.payload.decode('utf-8'))
                if q.full():
                    try:
                        q.get_nowait()  # drop oldest
                    except queue.Empty:
                        pass
                q.put_nowait(val)
            else:
                # Non-numeric side topics can be ignored or handled separately
                pass
        except Exception:
            # Avoid log spam on bad payloads
            pass

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

# ---------- Ingest New Samples (non-blocking) ----------
try:
    while True:
        v = q.get_nowait()
        now = datetime.now()

        st.session_state['gen'] = v
        new_row = pd.DataFrame({'Timestamp': [now], 'Generation': [v]})
        if st.session_state['data'].empty:
            st.session_state['data'] = new_row
        else:
            st.session_state['data'] = pd.concat(
                [st.session_state['data'], new_row],
                ignore_index=True
            )
except queue.Empty:
    pass

# ---------- DataFrame (force native pandas to avoid Narwhals warnings) ----------
df = st.session_state['data']
# convert to truly native pandas (Narwhals-safe)
if hasattr(df, "to_native"):
    df = df.to_native()
elif hasattr(df, "to_pandas"):
    df = df.to_pandas()
else:
    df = pd.DataFrame(df)
df = df.copy()

# ---------- Transformations ----------
if not df.empty:
    df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
    df = df.dropna(subset=['Timestamp']).sort_values('Timestamp')

    # Smoothing (moving average)
    if smooth_window > 1 and len(df) >= smooth_window:
        df['Gen_smooth'] = df['Generation'].rolling(window=smooth_window, min_periods=1).mean()
    else:
        df['Gen_smooth'] = df['Generation']

    # Power
    if input_type == "Percent 0–100":
        df['Power_W'] = (df['Gen_smooth'].clip(lower=0) / 100.0) * panel_rating_w
        value_label = "Generation (%)"
    else:
        df['Power_W'] = df['Gen_smooth'].clip(lower=0)
        value_label = "Generation (W)"

    # Energy from true time deltas
    # (limit absurd gaps to keep totals sane)
    dt_sec = df['Timestamp'].diff().dt.total_seconds().fillna(0)
    dt_sec = dt_sec.clip(lower=0, upper=12 * 60)  # cap at 12 minutes
    df['dt_h'] = dt_sec / 3600.0
    df['Wh_increment'] = df['Power_W'] * df['dt_h']
    df['Energy_kWh'] = df['Wh_increment'].cumsum() / 1000.0

# ---------- UI Header ----------
st.title("🌿 Renewable Energy Monitoring for Microgrids in Villages")

colA, colB, colC, colD = st.columns(4)
if df.empty:
    colA.metric("Current Output", "—")
    colB.metric("Peak Output", "—")
    colC.metric("Cumulative Energy", "—")
    colD.metric("Samples", "0")
else:
    current_val = df['Generation'].iloc[-1]
    peak_val = df['Generation'].max()
    total_kwh = df['Energy_kWh'].iloc[-1]

    if input_type == "Percent 0–100":
        colA.metric("Current Output", f"{current_val:.2f} %")
        colB.metric("Peak Output", f"{peak_val:.2f} %")
        # ⚠️ Blackout logic: current == 0%
        if round(current_val, 2) == 0.0:
            st.error("🛑 Blackout detected: current generation is 0 %")
    else:
        colA.metric("Current Output", f"{df['Power_W'].iloc[-1]:.1f} W")
        colB.metric("Peak Output", f"{df['Power_W'].max():.1f} W")

    colC.metric("Cumulative Energy", f"{total_kwh:.4f} kWh")
    colD.metric("Samples", f"{len(df)}")

# ---------- Charts ----------
if not df.empty:
    eco_green = "#2ca02c"
    eco_blue = "#1f77b4"
    eco_orange = "#ff7f0e"

    x_time = alt.X('Timestamp:T', title='Time')

    # 1) Live Generation
    if input_type == "Percent 0–100":
        y = alt.Y('Gen_smooth:Q', title='Generation (%)')
        gen_chart = alt.Chart(df).mark_line(color=eco_green, point=True).encode(
            x=x_time, y=y,
            tooltip=[alt.Tooltip('Timestamp:T'),
                     alt.Tooltip('Gen_smooth:Q', title='Generation (%)', format='.2f')]
        ).properties(title='🌞 Live Generation (%)', height=280)
    else:
        y = alt.Y('Power_W:Q', title='Power (W)')
        gen_chart = alt.Chart(df).mark_line(color=eco_green, point=True).encode(
            x=x_time, y=y,
            tooltip=[alt.Tooltip('Timestamp:T'),
                     alt.Tooltip('Power_W:Q', title='Power (W)', format='.1f')]
        ).properties(title='🌞 Live Power Output (W)', height=280)

    # 2) Instantaneous Power (area)
    power_area = alt.Chart(df).mark_area(color=eco_blue, opacity=0.4).encode(
        x=x_time,
        y=alt.Y('Power_W:Q', title='Power (W)'),
        tooltip=[alt.Tooltip('Timestamp:T'),
                 alt.Tooltip('Power_W:Q', title='Power (W)', format='.1f')]
    ).properties(title='⚡ Instantaneous Power', height=220)

    # 3) Cumulative Energy (kWh)
    energy_area = alt.Chart(df).mark_area(color=eco_orange, opacity=0.4).encode(
        x=x_time,
        y=alt.Y('Energy_kWh:Q', title='Cumulative Energy (kWh)'),
        tooltip=[alt.Tooltip('Timestamp:T'),
                 alt.Tooltip('Energy_kWh:Q', title='Energy (kWh)', format='.5f')]
    ).properties(title='📈 Cumulative Energy Generated', height=220)

    # 4) Distribution (Power)
    hist = alt.Chart(df).mark_bar(color=eco_green, opacity=0.85).encode(
        x=alt.X('Power_W:Q', bin=alt.Bin(maxbins=30), title='Power (W)'),
        y=alt.Y('count():Q', title='Samples'),
        tooltip=[alt.Tooltip('count():Q', title='Samples')]
    ).properties(title='📊 Distribution of Generation', height=220)

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
    st.download_button("⬇️ Download Microgrid Data (CSV)", data=csv,
                       file_name="village_microgrid.csv", mime="text/csv")

# ---------- Footer ----------
st.markdown(
    """
    <div style="opacity:0.85; font-size:0.9rem; text-align:center; margin-top: 0.5rem;">
      🌍 Monitoring renewable energy for <b>village microgrids</b> in real time.<br>
      Built with <b>Raspberry Pi Pico W</b> · Data over <b>MQTT</b> · Visualized in <b>Streamlit</b>.
    </div>
    """,
    unsafe_allow_html=True
)
