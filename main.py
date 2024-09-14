import streamlit as st
import paho.mqtt.client as mqtt
import ssl
import threading
import queue
import pandas as pd
from datetime import datetime
import altair as alt  # Import Altair for advanced charting
from streamlit_autorefresh import st_autorefresh


# Auto-refresh the app every 5 seconds
st_autorefresh(interval=2500, key="refresh")

# Initialize session_state variables
if 'temperature' not in st.session_state:
    st.session_state['temperature'] = None

if 'temperature_data' not in st.session_state:
    # Initialize with empty DataFrame
    st.session_state['temperature_data'] = pd.DataFrame(columns=['Timestamp', 'Temperature'])

# Use st.cache_resource to initialize the MQTT client and message queue only once
@st.cache_resource
def init_mqtt_client():
    message_queue = queue.Queue()

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("Connected to MQTT Broker!")
            client.subscribe(st.secrets.MQTT_TOPIC)
            print(f"Subscribed to topic: {st.secrets.MQTT_TOPIC}")
        else:
            print(f"Failed to connect, return code {rc}")

    def on_message(client, userdata, msg):
        temperature = float(msg.payload.decode('utf-8'))
        print(f"Received temperature: {temperature}°C from topic: {msg.topic}")
        # Put the temperature into the queue without accessing st.session_state
        message_queue.put(temperature)

    def mqtt_client():
        # Create an MQTT client instance with MQTT v3.1.1 protocol
        client = mqtt.Client(client_id=st.secrets.MQTT_CLIENT_ID, protocol=mqtt.MQTTv311)

        # Set username and password
        client.username_pw_set(st.secrets.MQTT_USERNAME, st.secrets.MQTT_PASSWORD)

        # Configure TLS/SSL settings
        client.tls_set(
            cert_reqs=ssl.CERT_NONE,  # Disable certificate verification
            tls_version=ssl.PROTOCOL_TLSv1_2,  # Use TLS v1.2
        )
        client.tls_insecure_set(True)  # Allow insecure server connections

        # Assign event callbacks
        client.on_connect = on_connect
        client.on_message = on_message

        # Connect to the broker
        client.connect(st.secrets.MQTT_BROKER, st.secrets.MQTT_PORT, keepalive=60)

        # Start the network loop
        client.loop_forever()

    # Start MQTT client in a separate thread
    mqtt_thread = threading.Thread(target=mqtt_client, name="MQTTThread")
    mqtt_thread.daemon = True
    mqtt_thread.start()

    return message_queue

# Initialize the MQTT client and get the message queue
message_queue = init_mqtt_client()

# Streamlit app layout
st.title("Real-time Temperature Data from Raspberry Pi Pico W 📡")

# Placeholder for temperature display
temperature_placeholder = st.empty()

# Placeholder for the line chart
chart_placeholder = st.empty()

# Update temperature from the queue
try:
    while True:
        temperature = message_queue.get_nowait()
        st.session_state['temperature'] = temperature

        # Append the new temperature to the DataFrame
        new_data = pd.DataFrame({
            'Timestamp': [datetime.now()],
            'Temperature': [temperature]
        })

        if st.session_state['temperature_data'].empty:
            # Assign directly if the DataFrame is empty
            st.session_state['temperature_data'] = new_data
        else:
            # Concatenate if the DataFrame is not empty
            st.session_state['temperature_data'] = pd.concat(
                [st.session_state['temperature_data'], new_data],
                ignore_index=True
            )
except queue.Empty:
    pass

# Display the current temperature
if st.session_state['temperature'] is not None:
    temperature_placeholder.markdown(f"### Current Temperature: {st.session_state['temperature']}°C 🌡️")
else:
    temperature_placeholder.markdown("Waiting for data...")

# Display the live line chart with magnified Y-axis
if not st.session_state['temperature_data'].empty:
    # Ensure Timestamp is datetime
    st.session_state['temperature_data']['Timestamp'] = pd.to_datetime(
        st.session_state['temperature_data']['Timestamp']
    )

    # Set the index to the Timestamp for better plotting (optional)
    temp_data = st.session_state['temperature_data']

    # Calculate min and max temperature for Y-axis range
    min_temp = temp_data['Temperature'].min()
    max_temp = temp_data['Temperature'].max()
    temp_range = max_temp - min_temp

    # Add padding to the Y-axis range
    padding = temp_range * 0.2 if temp_range != 0 else 1  # Avoid zero padding
    y_min = min_temp - padding
    y_max = max_temp + padding

    # Create Altair line chart
    line_chart = alt.Chart(temp_data).mark_line(point=True).encode(
        x=alt.X('Timestamp:T', title='Time'),
        y=alt.Y('Temperature:Q', title='Temperature (°C)', scale=alt.Scale(domain=[y_min, y_max])),
        tooltip=['Timestamp:T', 'Temperature:Q']
    ).properties(
        width=700,
        height=400,
        title='Live Temperature Readings'
    ).interactive()  # Enable zoom and pan

    # Display the chart
    chart_placeholder.altair_chart(line_chart, use_container_width=True)
else:
    chart_placeholder.markdown("Waiting for data to plot...")

st.markdown("""
This project showcases the integration of **IoT devices**, **real-time data streaming**, and **advanced data visualization** to create a sophisticated temperature monitoring solution. Below, you'll find live temperature readings from a Raspberry Pi Pico W, beautifully plotted for your analysis. 📈

### 🌟 **Key Features**

- **Real-time Data Acquisition** 📡
  - Utilizes the **MQTT protocol** over secure **SSL/TLS** connections to receive temperature data from the Raspberry Pi Pico W in real time.
  - The Raspberry Pi Pico W reads temperature data from its internal sensor and publishes it to an MQTT broker at regular intervals.

- **Concurrency and Multithreading** 🧵
  - Implements a separate **thread** for the MQTT client using Python's `threading` module.
  - Ensures the Streamlit app remains responsive while continuously listening for incoming MQTT messages.

- **Thread-safe Data Sharing** 🔒
  - Employs a **thread-safe queue** to safely communicate between the MQTT client thread and the main Streamlit thread.
  - Uses **Streamlit's `st.session_state`** to maintain state across script reruns without causing race conditions.

- **Advanced Data Visualization** 🎨
  - Leverages **Altair** to create an interactive **live line chart** of the temperature data.
  - Magnifies small temperature variations by dynamically adjusting the Y-axis scale based on the data range.
  - Adds interactive features like tooltips, zooming, and panning for enhanced data analysis.

- **Secure Communication** 🔐
  - Configures SSL/TLS settings to establish a secure connection with the MQTT broker.
  - Uses TLS v1.2 protocol and handles certificates appropriately for testing purposes.

---

""")