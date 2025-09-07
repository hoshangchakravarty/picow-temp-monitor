import streamlit as st
import paho.mqtt.client as mqtt
import ssl
import threading
import queue
import pandas as pd
from datetime import datetime, timedelta
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
st.sidebar.caption("This simulates village-scale microgrid generation using IoT & MQTT.")

# ---------- Topics ----------
GEN_TOPIC = st.secrets.MQTT_TOPIC                # e.g. "picow/generation"
BLACKOUT_TOPIC = st.secrets.get("MQTT_TOPIC_BLACKOUT", "picow/blackout")

# ---------- Session State ----------
if 'gen' not in st.session_state:
    st.session_state['gen'] = None
if 'data' not in st.session_state or clear_btn:
    st.session_state['data'] = pd.DataFrame(columns=['Timestamp', 'Generation'])
if 'blackout_state' not in st.session_state:
    st.session_state['blackout_state'] = 0  # 0=normal,1=blackout
if 'blackouts' not in st.session_state or clear_btn:
    # log of state changes: Timestamp, State (0/1)
    st.session_state['blackouts'] = pd.DataFrame(columns=['Timestamp', 'State'])

# ---------- MQTT Client ----------
@st.cache_resource
def init_mqtt_client(gen_topic, blackout_topic):
    q = queue.Queue()

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            client.subscribe(gen_topic)
            client.subscribe(blackout_topic)
            print(f"Subscribed: {gen_topic}, {blackout_topic}")
        else:
            print("MQTT connect failed:", rc)

    def on_message(client, userdata, msg):
        try:
            if msg.topic == gen_topic:
                val = float(msg.payload.decode('utf-8'))
                q.put(("gen", val, datetime.now()))
            elif msg.topic == blackout_topic:
                raw = msg.payload.decode('utf-8').strip()
                state = 1 if raw in ("1", "true", "True") else 0
                q.put(("blackout", state, datetime.now()))
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

q = init_mqtt_client(GEN_TOPIC, BLACKOUT_TOPIC)

# ---------- Ingest New Samples ----------
try:
    while True:
        typ, val, ts = q.get_nowait()
        if typ == "gen":
            st.session_state['gen'] = val
            st.session_state['data'] = pd.concat(
                [st.session_state['data'], pd.DataFrame({'Timestamp': [ts], 'Generation': [val]})],
                ignore_index=True
            )
        elif typ == "blackout":
            # Only log state changes
            if val != st.session_state['blackout_state']:
                st.session_state['blackout_state'] = val
                st.session_state['blackouts'] = pd.concat(
                    [st.session_state['blackouts'], pd.DataFrame({'Timestamp': [ts], 'State': [val]})],
                    ignore_index=True
                )
except queue.Empty:
    pass

# ---------- Prep Data ----------
df = st.session_state['data'].copy()
blk = st.session_state['blackouts'].copy()

if not df.empty:
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    if smooth_window > 1 and len(df) >= smooth_window:
        df['Gen_smooth'] = df['Generation'].rolling(window=smooth_window, min_periods=1).mean()
    else:
        df['Gen_smooth'] = df['Generation']

    # Compute Power
    if input_type == "Percent 0–100":
        df['Power_W'] = (df['Gen_smooth'].clip(lower=0) / 100.0) * panel_rating_w
        value_label = "Generation (%)"
    else:
        df['Power_W'] = df['Gen_smooth'].clip(lower=0)
        value_label = "Generation (W)"

    # Energy from real deltas
    df = df.sort_values('Timestamp')
    df['dt_h'] = df['Timestamp'].diff().dt.total_seconds().fillna(0) / 3600.0
    df.loc[df['dt_h'] > 0.2, 'dt_h'] = 0.0
    df['Wh_increment'] = df['Power_W'] * df['dt_h']
    df['Energy_kWh'] = df['Wh_increment'].cumsum() / 1000.0

# ---------- Header ----------
st.title("🌿 Renewable Energy Monitoring for Microgrids in Villages")

# Live blackout banner
if st.session_state['blackout_state'] == 1:
    st.error("🚨 BLACKOUT DETECTED — No light measured at the sensor")

colA, colB, colC, colD, colE = st.columns(5)
if df.empty:
    colA.metric("Current Output", "—")
    colB.metric("Peak Output", "—")
    colC.metric("Cumulative Energy", "—")
    colD.metric("Samples", "0")
    colE.metric("Outage Today", "—")
else:
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

    # Outage duration today (sum of blackout intervals overlapping today)
    def outage_duration_today(blk_df: pd.DataFrame) -> timedelta:
        if blk_df.empty:
            return timedelta(0)
        # Build intervals from state changes
        rows = blk_df.sort_values('Timestamp').to_records(index=False)
        intervals = []
        active_start = None
        for ts, state in rows:
            if state == 1 and active_start is None:
                active_start = ts
            elif state == 0 and active_start is not None:
                intervals.append((active_start, ts))
                active_start = None
        # If blackout still active, close at now
        if active_start is not None:
            intervals.append((active_start, datetime.now()))
        # Sum only overlaps with today's window
        start_of_day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = datetime.now()
        total = timedelta(0)
        for a, b in intervals:
            s = max(a, start_of_day)
            e = min(b, end_of_day)
            if e > s:
                total += (e - s)
        return total

    outage_td = outage_duration_today(blk)
    colC.metric("Cumulative Energy", f"{total_kwh:.4f} kWh")
    colD.metric("Samples", f"{len(df)}")
    colE.metric("Outage Today", f"{outage_td}", help="Total blackout time accumulated since midnight")

    if offline:
        st.warning("⚠️ No new data for 10+ seconds (device offline?)")

# ---------- Charts ----------
if not df.empty:
    eco_green = "#2ca02c"; eco_blue = "#1f77b4"; eco_orange = "#ff7f0e"; alert_red = "#d62728"
    x_time = alt.X('Timestamp:T', title='Time')

    # Build blackout vertical rules (one per event)
    blackout_rules = None
    if not blk.empty:
        blk = blk.copy()
        blk['Timestamp'] = pd.to_datetime(blk['Timestamp'])
        blackout_rules = alt.Chart(blk).mark_rule(color=alert_red, strokeDash=[6,4]).encode(
            x='Timestamp:T',
            tooltip=[alt.Tooltip('Timestamp:T', title='Event'), alt.Tooltip('State:N')]
        )

    # 1) Live Generation / Power
    if input_type == "Percent 0–100":
        base = alt.Chart(df).mark_line(color=eco_green, point=True).encode(
            x=x_time,
            y=alt.Y('Gen_smooth:Q', title='Generation (%)'),
            tooltip=[alt.Tooltip('Timestamp:T'),
                     alt.Tooltip('Gen_smooth:Q', title='Generation (%)', format='.2f')]
        ).properties(title='🌞 Live Generation (%)', height=280)
    else:
        base = alt.Chart(df).mark_line(color=eco_green, point=True).encode(
            x=x_time,
            y=alt.Y('Power_W:Q', title='Power (W)'),
            tooltip=[alt.Tooltip('Timestamp:T'),
                     alt.Tooltip('Power_W:Q', title='Power (W)', format='.1f')]
        ).properties(title='🌞 Live Power Output (W)', height=280)

    gen_chart = base if blackout_rules is None else (base + blackout_rules)
    st.altair_chart(gen_chart.interactive(), use_container_width=True)

    # 2) Instantaneous Power
    base_power = alt.Chart(df).mark_area(color=eco_blue, opacity=0.4).encode(
        x=x_time,
        y=alt.Y('Power_W:Q', title='Power (W)'),
        tooltip=[alt.Tooltip('Timestamp:T'),
                 alt.Tooltip('Power_W:Q', title='Power (W)', format='.1f')]
    ).properties(title='⚡ Instantaneous Power', height=220)
    power_area = base_power if blackout_rules is None else (base_power + blackout_rules)
    c1, c2 = st.columns(2)
    with c1:
        st.altair_chart(power_area.interactive(), use_container_width=True)

    # 3) Cumulative Energy
    base_energy = alt.Chart(df).mark_area(color=eco_orange, opacity=0.4).encode(
        x=x_time,
        y=alt.Y('Energy_kWh:Q', title='Cumulative Energy (kWh)'),
        tooltip=[alt.Tooltip('Timestamp:T'),
                 alt.Tooltip('Energy_kWh:Q', title='Energy (kWh)', format='.5f')]
    ).properties(title='📈 Cumulative Energy Generated', height=220)
    energy_area = base_energy if blackout_rules is None else (base_energy + blackout_rules)
    with c2:
        st.altair_chart(energy_area.interactive(), use_container_width=True)

    # 4) Distribution
    hist = alt.Chart(df).mark_bar(color=eco_green, opacity=0.8).encode(
        x=alt.X('Power_W:Q', bin=alt.Bin(maxbins=30), title='Power (W)'),
        y=alt.Y('count():Q', title='Samples'),
        tooltip=[alt.Tooltip('count():Q', title='Samples')]
    ).properties(title='📊 Distribution of Generation', height=220)
    st.altair_chart(hist, use_container_width=True)

    # Download CSV
    csv = df[['Timestamp', 'Generation', 'Gen_smooth', 'Power_W', 'Energy_kWh']].to_csv(index=False).encode('utf-8')
    st.download_button("⬇️ Download Microgrid Data (CSV)", data=csv, file_name="village_microgrid.csv", mime="text/csv")

# ---------- Footer ----------
st.markdown(
    """
    <div style="opacity:0.8; font-size:0.9rem; text-align:center; margin-top: 0.5rem;">
      🌍 This demo shows how IoT can empower <b>village microgrids</b> to monitor solar generation in real time.<br>
      Built with <b>Raspberry Pi Pico W</b> · Data over <b>MQTT</b> · Visualized in <b>Streamlit</b>.
    </div>
    """,
    unsafe_allow_html=True
)
