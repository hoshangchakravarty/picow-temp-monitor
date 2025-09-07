# -------------------------------------------------------------
# 🌿 Microgrid Monitor (Reliable MQTT + Auto-Reconnect)
# -------------------------------------------------------------
import os, time, ssl, threading, queue
from datetime import datetime, timedelta

import streamlit as st
import pandas as pd
import altair as alt
import paho.mqtt.client as mqtt
from streamlit_autorefresh import st_autorefresh

# ================== CONFIG (fallbacks if st.secrets missing) ==================
BROKER   = getattr(st.secrets, "MQTT_BROKER",   "550400ab5c0a4d15a091aa8699ccccf9.s1.eu.hivemq.cloud")
PORT     = int(getattr(st.secrets, "MQTT_PORT", 8883))
USERNAME = getattr(st.secrets, "MQTT_USERNAME", "hoshang")
PASSWORD = getattr(st.secrets, "MQTT_PASSWORD", "Micropython1")
CLIENTID = getattr(st.secrets, "MQTT_CLIENT_ID","streamlit_subscriber")
TOPIC    = getattr(st.secrets, "MQTT_TOPIC",    "picow/generation")  # 🔶 matches Pico W publisher

# ================== PAGE ==================
st.set_page_config(page_title="Renewable Energy Monitoring for Microgrids in Villages", page_icon="🌿", layout="wide")
alt.data_transformers.enable('default', max_rows=None)
st_autorefresh(interval=2500, key="refresh")

# ================== SIDEBAR ==================
st.sidebar.header("⚙️ Microgrid Settings")
panel_rating_w = st.sidebar.number_input("Rated Capacity (W)", min_value=10, max_value=5000, value=100, step=10)
input_type     = st.sidebar.selectbox("Incoming MQTT Value", ["Percent 0–100", "Watts"], index=0)
smooth_window  = st.sidebar.slider("Smoothing Window (samples)", 1, 20, 4)
max_rows       = st.sidebar.slider("Keep last N samples", 300, 20000, 3000, step=100)
clear_btn      = st.sidebar.button("🧹 Clear Data")
st.sidebar.markdown("---")
st.sidebar.caption("This simulates village-scale microgrid generation using IoT & MQTT.")

# ================== SESSION STATE ==================
if "data" not in st.session_state or clear_btn:
    st.session_state.data = pd.DataFrame(columns=["Timestamp","Generation"])
if "last_msg_ts" not in st.session_state:
    st.session_state.last_msg_ts = None

# ================== MQTT (threaded, cached, auto-reconnect) ==================
@st.cache_resource
def mqtt_bridge():
    """
    Starts one background MQTT client that:
      - auto-reconnects with exponential backoff
      - pushes float readings into a thread-safe Queue
    Returns the Queue.
    """
    q = queue.Queue()
    lock = threading.Lock()
    connected = {"ok": False}
    stop_flag = {"stop": False}

    def _connect(c):
        # TLS (accept insecure for testing)
        c.tls_set(cert_reqs=ssl.CERT_NONE, tls_version=ssl.PROTOCOL_TLSv1_2)
        c.tls_insecure_set(True)
        c.username_pw_set(USERNAME, PASSWORD)
        c.connect(BROKER, PORT, keepalive=60)

    def on_connect(client, userdata, flags, rc, properties=None):
        with lock:
            connected["ok"] = (rc == 0)
        if rc == 0:
            client.subscribe(TOPIC)
        else:
            print("MQTT connect failed rc=", rc)

    def on_disconnect(client, userdata, rc, properties=None):
        with lock:
            connected["ok"] = False
        print("MQTT disconnected rc=", rc)

    def on_message(client, userdata, msg):
        try:
            val = float(msg.payload.decode("utf-8"))
            q.put((datetime.now(), val))
        except Exception as e:
            print("Bad payload:", e)

    def worker():
        backoff = 1
        client = mqtt.Client(client_id=CLIENTID, protocol=mqtt.MQTTv311)
        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = on_message

        while not stop_flag["stop"]:
            try:
                _connect(client)
                client.loop_start()
                # Wait until connected or timeout
                t0 = time.time()
                while not connected["ok"] and time.time() - t0 < 8 and not stop_flag["stop"]:
                    time.sleep(0.2)

                if connected["ok"]:
                    print("✅ MQTT connected & subscribed:", TOPIC)
                    backoff = 1  # reset after success
                    # Stay alive; if disconnected, break to reconnect
                    while not stop_flag["stop"] and connected["ok"]:
                        time.sleep(0.5)
                else:
                    print("⚠️ MQTT connect timeout; retrying...")
                    client.loop_stop()
                    client.disconnect()
            except Exception as e:
                print("MQTT error:", e)
                try:
                    client.loop_stop()
                except:
                    pass
                try:
                    client.disconnect()
                except:
                    pass

            # exponential backoff before retry
            if stop_flag["stop"]:
                break
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)

        # cleanup
        try:
            client.loop_stop()
        except:
            pass
        try:
            client.disconnect()
        except:
            pass

    th = threading.Thread(target=worker, name="MQTT-Bridge", daemon=True)
    th.start()
    return q

msg_q = mqtt_bridge()

# ================== INGEST (non-blocking) ==================
# Drain at most K messages per rerun to avoid long blocking loops
K = 500
drained = 0
while drained < K:
    try:
        ts, v = msg_q.get_nowait()
    except queue.Empty:
        break
    st.session_state.last_msg_ts = ts
    st.session_state.data = pd.concat(
        [st.session_state.data, pd.DataFrame({"Timestamp":[ts], "Generation":[v]})],
        ignore_index=True
    )
    drained += 1

# Trim to last N rows to keep memory predictable
if not st.session_state.data.empty and len(st.session_state.data) > max_rows:
    st.session_state.data = st.session_state.data.iloc[-max_rows:].reset_index(drop=True)

# ================== ANALYTICS ==================
df = st.session_state.data.copy()
if not df.empty:
    df["Timestamp"] = pd.to_datetime(df["Timestamp"])
    if smooth_window > 1 and len(df) >= smooth_window:
        df["Gen_smooth"] = df["Generation"].rolling(window=smooth_window, min_periods=1).mean()
    else:
        df["Gen_smooth"] = df["Generation"]

    if input_type == "Percent 0–100":
        df["Power_W"] = (df["Gen_smooth"].clip(lower=0) / 100.0) * panel_rating_w
        value_label = "Generation (%)"
    else:
        df["Power_W"] = df["Gen_smooth"].clip(lower=0)
        value_label = "Generation (W)"

    df = df.sort_values("Timestamp")
    df["dt_h"] = df["Timestamp"].diff().dt.total_seconds().fillna(0) / 3600.0
    # Ignore long gaps when app was sleeping; keeps energy realistic
    df.loc[df["dt_h"] > 0.20, "dt_h"] = 0.0
    df["Wh_increment"] = df["Power_W"] * df["dt_h"]
    df["Energy_kWh"] = df["Wh_increment"].cumsum() / 1000.0

# ================== HEADER ==================
st.title("🌿 Renewable Energy Monitoring for Microgrids in Villages")

colA, colB, colC, colD = st.columns(4)
if df.empty:
    colA.metric("Current Output", "—")
    colB.metric("Peak Output", "—")
    colC.metric("Cumulative Energy", "—")
    colD.metric("Samples", "0")
else:
    last_ts = df["Timestamp"].iloc[-1]
    offline = (datetime.now() - last_ts) > timedelta(seconds=10)

    current_val = df["Generation"].iloc[-1]
    peak_val    = df["Generation"].max()
    total_kwh   = df["Energy_kWh"].iloc[-1]

    if input_type == "Percent 0–100":
        colA.metric("Current Output", f"{current_val:.2f} %")
        colB.metric("Peak Output",   f"{peak_val:.2f} %")
    else:
        colA.metric("Current Output", f"{df['Power_W'].iloc[-1]:.1f} W")
        colB.metric("Peak Output",   f"{df['Power_W'].max():.1f} W")

    colC.metric("Cumulative Energy", f"{total_kwh:.4f} kWh")
    colD.metric("Samples", f"{len(df)}")

    if offline:
        st.warning("⚠️ No new data for 10+ seconds (device offline?)")

# ================== CHARTS ==================
if not df.empty:
    eco_green  = "#2ca02c"
    eco_blue   = "#1f77b4"
    eco_orange = "#ff7f0e"
    x_time = alt.X("Timestamp:T", title="Time")

    if input_type == "Percent 0–100":
        y = alt.Y("Gen_smooth:Q", title="Generation (%)")
        gen_chart = alt.Chart(df).mark_line(color=eco_green, point=True).encode(
            x=x_time, y=y, tooltip=[alt.Tooltip("Timestamp:T"),
                                    alt.Tooltip("Gen_smooth:Q", title="Generation (%)", format=".2f")]
        ).properties(title="🌞 Live Generation (%)", height=280)
    else:
        y = alt.Y("Power_W:Q", title="Power (W)")
        gen_chart = alt.Chart(df).mark_line(color=eco_green, point=True).encode(
            x=x_time, y=y, tooltip=[alt.Tooltip("Timestamp:T"),
                                    alt.Tooltip("Power_W:Q", title="Power (W)", format=".1f")]
        ).properties(title="🌞 Live Power Output (W)", height=280)

    power_area = alt.Chart(df).mark_area(color=eco_blue, opacity=0.4).encode(
        x=x_time, y=alt.Y("Power_W:Q", title="Power (W)"),
        tooltip=[alt.Tooltip("Timestamp:T"), alt.Tooltip("Power_W:Q", title="Power (W)", format=".1f")]
    ).properties(title="⚡ Instantaneous Power", height=220)

    energy_area = alt.Chart(df).mark_area(color=eco_orange, opacity=0.4).encode(
        x=x_time, y=alt.Y("Energy_kWh:Q", title="Cumulative Energy (kWh)"),
        tooltip=[alt.Tooltip("Timestamp:T"), alt.Tooltip("Energy_kWh:Q", title="Energy (kWh)", format=".5f")]
    ).properties(title="📈 Cumulative Energy Generated", height=220)

    hist = alt.Chart(df).mark_bar(color=eco_green, opacity=0.8).encode(
        x=alt.X("Power_W:Q", bin=alt.Bin(maxbins=30), title="Power (W)"),
        y=alt.Y("count():Q", title="Samples"),
        tooltip=[alt.Tooltip("count():Q", title="Samples")]
    ).properties(title="📊 Distribution of Generation", height=220)

    st.altair_chart(gen_chart.interactive(), use_container_width=True)
    c1, c2 = st.columns(2)
    with c1:
        st.altair_chart(power_area.interactive(), use_container_width=True)
    with c2:
        st.altair_chart(energy_area.interactive(), use_container_width=True)
    st.altair_chart(hist, use_container_width=True)

    # Download
    csv = df[["Timestamp","Generation","Gen_smooth","Power_W","Energy_kWh"]].to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download Microgrid Data (CSV)", data=csv, file_name="village_microgrid.csv", mime="text/csv")

# ================== FOOTER ==================
st.markdown(
    """
    <div style="opacity:0.8; font-size:0.9rem; text-align:center; margin-top:0.5rem;">
      🌍 This demo shows how IoT can empower <b>village microgrids</b> to monitor solar generation in real time.<br>
      Built with <b>Raspberry Pi Pico W</b> · Data over <b>MQTT</b> · Visualized in <b>Streamlit</b>.
    </div>
    """,
    unsafe_allow_html=True
)
