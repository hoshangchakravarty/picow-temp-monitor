import streamlit as st
import paho.mqtt.client as mqtt
import ssl
import threading
import queue
import pandas as pd
from datetime import datetime, timedelta
import altair as alt
from streamlit_autorefresh import st_autorefresh

# ====== (Optional) Fallback constants — you can keep these or rely purely on st.secrets ======
MQTT_BROKER = "550400ab5c0a4d15a091aa8699ccccf9.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_TOPIC = "picow/generation"   # 🔶 Pico publishes percent 0–100 here
MQTT_CLIENT_ID = "streamlit_subscriber"
MQTT_USERNAME = "hoshang"
MQTT_PASSWORD = "Micropython1"

# ====== Page & Refresh ======
st.set_page_config(page_title="Renewable Energy Monitoring for Microgrids in Villages", page_icon="🌿", layout="wide")
alt.data_transformers.enable('default', max_rows=None)
st_autorefresh(interval=2500, key="refresh")

# ====== Sidebar (simple; add more later if you want) ======
st.sidebar.header("⚙️ Inputs")
panel_rating_w = st.sidebar.number_input("Rated Capacity (W)", min_value=10, max_value=5000, value=100, step=10)
input_type = st.sidebar.selectbox("Incoming MQTT Value", ["Percent 0–100", "Watts"], index=0)
smooth_window = st.sidebar.slider("Smoothing Window (samples)", 1, 20, 4)
clear_btn = st.sidebar.button("🧹 Clear Data")

# ====== Session State (names parallel to your temperature app) ======
if 'generation' not in st.session_state:
    st.session_state['generation'] = None

if 'generation_data' not in st.session_state or clear_btn:
    st.session_state['generation_data'] = pd.DataFrame(columns=['Timestamp', 'Generation'])

# ====== MQTT: EXACT same structure & logic as your temperature app ======
@st.cache_resource
def init_mqtt_client():
    message_queue = queue.Queue()

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("Connected to MQTT Broker!")
            client.subscribe(st.secrets.MQTT_TOPIC)  # <== uses st.secrets like your temp app
            print(f"Subscribed to topic: {st.secrets.MQTT_TOPIC}")
        else:
            print(f"Failed to connect, return code {rc}")

    def on_message(client, userdata, msg):
        try:
            val = float(msg.payload.decode('utf-8'))
            # Put into queue; do NOT touch session_state here (same as temp app)
            message_queue.put(val)
        except Exception as e:
            print("Bad payload:", e)

    def mqtt_client():
        # v3.1.1 protocol, same as your temp app
        client = mqtt.Client(client_id=st.secrets.MQTT_CLIENT_ID, protocol=mqtt.MQTTv311)

        # Username/password
        client.username_pw_set(st.secrets.MQTT_USERNAME, st.secrets.MQTT_PASSWORD)

        # TLS (accept insecure — testing)
        client.tls_set(
            cert_reqs=ssl.CERT_NONE,
            tls_version=ssl.PROTOCOL_TLSv1_2,
        )
        client.tls_insecure_set(True)

        # Callbacks
        client.on_connect = on_connect
        client.on_message = on_message

        # Connect & block
        client.connect(st.secrets.MQTT_BROKER, st.secrets.MQTT_PORT, keepalive=60)
        client.loop_forever()

    # Spawn thread (daemon), identical to your temp app
    mqtt_thread = threading.Thread(target=mqtt_client, name="MQTTThread")
    mqtt_thread.daemon = True
    mqtt_thread.start()

    return message_queue

# ====== Ensure the same secrets keys exist; if not, map fallbacks ======
# (This lets you run locally without editing the rest of the code.)
if "MQTT_BROKER" not in st.secrets:
    st.secrets["MQTT_BROKER"] = MQTT_BROKER
if "MQTT_PORT" not in st.secrets:
    st.secrets["MQTT_PORT"] = MQTT_PORT
if "MQTT_TOPIC" not in st.secrets:
    st.secrets["MQTT_TOPIC"] = MQTT_TOPIC
if "MQTT_CLIENT_ID" not in st.secrets:
    st.secrets["MQTT_CLIENT_ID"] = MQTT_CLIENT_ID
if "MQTT_USERNAME" not in st.secrets:
    st.secrets["MQTT_USERNAME"] = MQTT_USERNAME
if "MQTT_PASSWORD" not in st.secrets:
    st.secrets["MQTT_PASSWORD"] = MQTT_PASSWORD

# ====== Start MQTT (queue) ======
message_queue = init_mqtt_client()

# ====== UI placeholders ======
st.title("🌿 Renewable Energy Monitoring for Microgrids in Villages")
metric_placeholder = st.empty()
chart_main_placeholder = st.empty()
chart_row_placeholder = st.columns(2)
hist_placeholder = st.empty()

# ====== Drain queue (identical pattern to temp app) ======
try:
    while True:
        v = message_queue.get_nowait()
        st.session_state['generation'] = v
        new_row = pd.DataFrame({'Timestamp': [datetime.now()], 'Generation': [v]})

        if st.session_state['generation_data'].empty:
            st.session_state['generation_data'] = new_row
        else:
            st.session_state['generation_data'] = pd.concat(
                [st.session_state['generation_data'], new_row],
                ignore_index=True
            )
except queue.Empty:
    pass

# ====== Compute smoothing, power, energy ======
df = st.session_state['generation_data'].copy()
if not df.empty:
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])

    # Smoothing
    if smooth_window > 1 and len(df) >= smooth_window:
        df['Gen_smooth'] = df['Generation'].rolling(window=smooth_window, min_periods=1).mean()
    else:
        df['Gen_smooth'] = df['Generation']

    # Power calculation
    if input_type == "Percent 0–100":
        df['Power_W'] = (df['Gen_smooth'].clip(lower=0) / 100.0) * panel_rating_w
    else:
        df['Power_W'] = df['Gen_smooth'].clip(lower=0)

    # Energy calculation (kWh) via time-delta integration
    df = df.sort_values('Timestamp')
    df['dt_h'] = df['Timestamp'].diff().dt.total_seconds().fillna(0) / 3600.0
    # Ignore long gaps (like app sleeping) to keep energy realistic
    df.loc[df['dt_h'] > 0.20, 'dt_h'] = 0.0
    df['Wh_increment'] = df['Power_W'] * df['dt_h']
    df['Energy_kWh'] = df['Wh_increment'].cumsum() / 1000.0

# ====== Metrics ======
if df.empty:
    metric_placeholder.columns(4)[0].metric("Current Output", "—")
    metric_placeholder.columns(4)[1].metric("Peak Output", "—")
    metric_placeholder.columns(4)[2].metric("Cumulative Energy", "—")
    metric_placeholder.columns(4)[3].metric("Samples", "0")
else:
    colA, colB, colC, colD = metric_placeholder.columns(4)
    last_ts = df['Timestamp'].iloc[-1]
    offline = (datetime.now() - last_ts) > timedelta(seconds=10)

    current_val = df['Generation'].iloc[-1]
    peak_val = df['Generation'].max()
    total_kwh = df['Energy_kWh'].iloc[-1]

    if input_type == "Percent 0–100":
        colA.metric("Current Output", f"{current_val:.2f} %")
        colB.metric("Peak Output", f"{peak_val:.2f} %")
    else:
        colA.metric("Current Output", f"{df['Power_W'].iloc[-1]:.1f} W")
        colB.metric("Peak Output", f"{df['Power_W'].max():.1f} W")

    colC.metric("Cumulative Energy", f"{total_kwh:.4f} kWh")
    colD.metric("Samples", f"{len(df)}")

    if offline:
        st.warning("⚠️ No new data for 10+ seconds (device offline?)")

# ====== Charts (Altair) ======
if not df.empty:
    eco_green  = "#2ca02c"
    eco_blue   = "#1f77b4"
    eco_orange = "#ff7f0e"

    x_time = alt.X('Timestamp:T', title='Time')

    # Main live chart (percent or watts)
    if input_type == "Percent 0–100":
        y_live = alt.Y('Gen_smooth:Q', title='Generation (%)')
        live_chart = alt.Chart(df).mark_line(color=eco_green, point=True).encode(
            x=x_time, y=y_live,
            tooltip=[alt.Tooltip('Timestamp:T'), alt.Tooltip('Gen_smooth:Q', title='Generation (%)', format='.2f')]
        ).properties(title='🌞 Live Generation (%)', height=280)
    else:
        y_live = alt.Y('Power_W:Q', title='Power (W)')
        live_chart = alt.Chart(df).mark_line(color=eco_green, point=True).encode(
            x=x_time, y=y_live,
            tooltip=[alt.Tooltip('Timestamp:T'), alt.Tooltip('Power_W:Q', title='Power (W)', format='.1f')]
        ).properties(title='🌞 Live Power Output (W)', height=280)

    chart_main_placeholder.altair_chart(live_chart.interactive(), use_container_width=True)

    # Row charts
    with chart_row_placeholder[0]:
        power_area = alt.Chart(df).mark_area(color=eco_blue, opacity=0.4).encode(
            x=x_time,
            y=alt.Y('Power_W:Q', title='Power (W)'),
            tooltip=[alt.Tooltip('Timestamp:T'), alt.Tooltip('Power_W:Q', title='Power (W)', format='.1f')]
        ).properties(title='⚡ Instantaneous Power', height=220)
        st.altair_chart(power_area.interactive(), use_container_width=True)

    with chart_row_placeholder[1]:
        energy_area = alt.Chart(df).mark_area(color=eco_orange, opacity=0.4).encode(
            x=x_time,
            y=alt.Y('Energy_kWh:Q', title='Cumulative Energy (kWh)'),
            tooltip=[alt.Tooltip('Timestamp:T'), alt.Tooltip('Energy_kWh:Q', title='Energy (kWh)', format='.5f')]
        ).properties(title='📈 Cumulative Energy Generated', height=220)
        st.altair_chart(energy_area.interactive(), use_container_width=True)

    # Distribution
    hist = alt.Chart(df).mark_bar(color=eco_green, opacity=0.8).encode(
        x=alt.X('Power_W:Q', bin=alt.Bin(maxbins=30), title='Power (W)'),
        y=alt.Y('count():Q', title='Samples'),
        tooltip=[alt.Tooltip('count():Q', title='Samples')]
    ).properties(title='📊 Distribution of Generation', height=220)
    hist_placeholder.altair_chart(hist, use_container_width=True)

    # Download CSV
    csv = df[['Timestamp','Generation','Gen_smooth','Power_W','Energy_kWh']].to_csv(index=False).encode('utf-8')
    st.download_button("⬇️ Download Microgrid Data (CSV)", data=csv, file_name="village_microgrid.csv", mime="text/csv")
else:
    st.info("Waiting for data…")

# ====== Footer ======
st.markdown(
    """
    <div style="opacity:0.8; font-size:0.9rem; text-align:center; margin-top: 0.5rem;">
      🌍 This demo shows how IoT can empower <b>village microgrids</b> to monitor solar generation in real time.<br>
      Built with <b>Raspberry Pi Pico W</b> · Data over <b>MQTT</b> · Visualized in <b>Streamlit</b>.
    </div>
    """,
    unsafe_allow_html=True
)
