# Real-Time Temperature Tracking with Raspberry Pi Pico W: An MQTT IoT Cloud Solution

Welcome to the **Real-Time Temperature Monitoring System**! 🚀

This project integrates **IoT devices**, **real-time data streaming**, and **advanced data visualization** to create a sophisticated temperature monitoring solution. Using a **Raspberry Pi Pico W**, MQTT protocol, and a Streamlit web application, this project demonstrates how to capture, process, and display temperature data in real time. 🌡️📈

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Usage](#usage)
- [Code Overview](#code-overview)
  - [Streamlit Web App (`main.py`)](#streamlit-web-app-mainpy)
  - [Raspberry Pi Pico W Code (`pico_publisher.py`)](#raspberry-pi-pico-w-code-pico_publisherpy)
- [Customization](#customization)
- [Security Considerations](#security-considerations)
- [License](#license)
- [Acknowledgments](#acknowledgments)

---

## Features

- **Real-Time Data Acquisition** 📡
  - Utilizes the **MQTT protocol** over secure **SSL/TLS** connections.
  - Raspberry Pi Pico W reads temperature data from its internal sensor and publishes it to an MQTT broker.

- **Concurrency and Multithreading** 🧵
  - Implements a separate **thread** for the MQTT client using Python's `threading` module.
  - Ensures the Streamlit app remains responsive while continuously listening for incoming MQTT messages.

- **Thread-Safe Data Sharing** 🔒
  - Employs a **thread-safe queue** to safely communicate between the MQTT client thread and the main Streamlit thread.
  - Uses **Streamlit's `st.session_state`** to maintain state across script reruns.

- **Advanced Data Visualization** 🎨
  - Leverages **Altair** to create an interactive **live line chart** of the temperature data.
  - Magnifies small temperature variations by dynamically adjusting the Y-axis scale.
  - Adds interactive features like tooltips, zooming, and panning.

- **Secure Communication** 🔐
  - Configures SSL/TLS settings to establish a secure connection with the MQTT broker.
  - Uses TLS v1.2 protocol.

---

## Architecture

![Architecture Diagram](architecture.png) <!-- Placeholder for an architecture diagram -->

The system consists of:

- **Raspberry Pi Pico W**: Collects temperature data and publishes it to the MQTT broker.
- **MQTT Broker**: Facilitates message exchange between the Pico W and the Streamlit app.
- **Streamlit Web App**: Subscribes to the MQTT topic, processes incoming data, and displays it in real time.

---

## Prerequisites

- **Hardware**:
  - Raspberry Pi Pico W
  - USB cable for connection
- **Software**:
  - Python 3.7 or higher
  - Streamlit
  - paho-mqtt
  - Altair
  - pandas
- **MQTT Broker**:
  - An MQTT broker accessible over the internet (e.g., HiveMQ Cloud)
- **MicroPython**:
  - MicroPython firmware installed on the Raspberry Pi Pico W

---

## Installation

### Raspberry Pi Pico W Setup

1. **Install MicroPython**:

   - Download the latest MicroPython UF2 file for Raspberry Pi Pico W from the [official website](https://micropython.org/download/rp2-pico-w/).
   - Connect your Pico W to your computer while holding the BOOTSEL button to enter bootloader mode.
   - Drag and drop the UF2 file onto the Pico W drive that appears.

2. **Install Required Libraries on Pico W**:

   - Ensure you have `picozero` and `umqtt.simple` libraries available.
   - You can use a tool like [Thonny IDE](https://thonny.org/) to upload libraries and code to the Pico W.

3. **Upload the MQTT Publisher Code**:

   - Save the provided `pico_publisher.py` code (see [Raspberry Pi Pico W Code](#raspberry-pi-pico-w-code-pico_publisherpy)) to your Pico W.
   - Update the Wi-Fi credentials and MQTT broker details in the code.

### Streamlit Web App Setup

1. **Clone the Repository**:

   ```bash
   git clone https://github.com/yourusername/temperature-monitoring.git
   cd temperature-monitoring
   ```

2. **Set Up a Virtual Environment** (optional but recommended):

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use 'venv\Scripts\activate'
   ```

3. **Install Dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

---

## Usage

1. **Start the Raspberry Pi Pico W**:

   - Ensure the Pico W is powered on and running the `pico_publisher.py` script.
   - It should connect to your Wi-Fi network and start publishing temperature data.

2. **Run the Streamlit App**:

   ```bash
   streamlit run main.py
   ```

3. **View the App**:

   - Open your web browser and navigate to the URL provided by Streamlit (usually `http://localhost:8501`).

4. **Observe Real-Time Data**:

   - Watch as temperature readings appear in real time.
   - Interact with the live line chart to zoom, pan, and explore data.

---

## Code Overview

### Streamlit Web App (`main.py`)

This is the main application file that contains:

- **Project Description**: Provides an overview of the project with emojis for visual appeal.
- **Imports**: Necessary Python modules and libraries.
- **MQTT Client Initialization**:
  - Uses `st.cache_resource` to ensure the MQTT client is initialized only once.
  - Sets up the MQTT client with SSL/TLS configurations.
- **Session State Initialization**:
  - Stores temperature data and readings using `st.session_state`.
- **Data Handling**:
  - Receives temperature data from the MQTT client.
  - Updates the data frame with new readings.
- **Visualization**:
  - Displays the current temperature.
  - Uses Altair to create an interactive line chart with magnified temperature variations.

### Raspberry Pi Pico W Code (`pico_publisher.py`)

This script runs on the Raspberry Pi Pico W and is responsible for:

- **Connecting to Wi-Fi**:

  ```python
  def connect():
      ssid = "your_SSID"
      password = "your_password"
      wlan = network.WLAN(network.STA_IF)
      wlan.active(True)
      wlan.connect(ssid, password)

      while not wlan.isconnected():
          led.toggle()
          time.sleep(1)
          print("Connecting...")
      print("Connected to WiFi!")
      ip = wlan.ifconfig()[0]
      print("IP Address:", ip)
      return ip
  ```

  - Replace `"your_SSID"` and `"your_password"` with your Wi-Fi network credentials.
  - The function attempts to connect to the Wi-Fi network and returns the IP address upon success.

- **Connecting to the MQTT Broker**:

  ```python
  def connectMQTT():
      context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
      context.verify_mode = ssl.CERT_NONE
      client = MQTTClient(
          client_id=b"your_client_id",
          server="your_mqtt_broker_url",
          port=your_mqtt_port,
          user=b"your_username",
          password=b"your_password",
          keepalive=7200,
          ssl=context
      )
      client.connect()
      return client
  ```

  - Replace `"your_client_id"`, `"your_mqtt_broker_url"`, `your_mqtt_port`, `"your_username"`, and `"your_password"` with your MQTT broker details.
  - Configures SSL/TLS settings for a secure connection.

- **Publishing Temperature Data**:

  ```python
  while True:
      temp = pico_temp_sensor.temp
      print("Internal Temperature:", temp, "Celsius")
      publish('picow/temperature', temp)
      led.toggle()
      utime.sleep(5)
  ```

  - Reads the internal temperature sensor using `pico_temp_sensor.temp`.
  - Publishes the temperature data to the MQTT topic `'picow/temperature'` every 5 seconds.
  - Toggles the onboard LED to indicate activity.

- **Helper Functions**:

  - **`publish(topic, value)`**: Publishes the given value to the specified MQTT topic.

    ```python
    def publish(topic, value):
        client.publish(topic.encode('utf-8'), str(value).encode('utf-8'))
        print("Published:", topic, value)
    ```

  - **LED Indicator**: Uses the onboard LED to indicate connection status and publishing activity.

- **Full Code Listing**:

  ```python
  import machine
  import time
  import network
  import utime
  from umqtt.simple import MQTTClient
  import ssl
  from picozero import pico_temp_sensor

  led = machine.Pin('LED', machine.Pin.OUT)

  def connect():
      ssid = "your_SSID"
      password = "your_password"
      wlan = network.WLAN(network.STA_IF)
      wlan.active(True)
      wlan.connect(ssid, password)

      while not wlan.isconnected():
          led.toggle()
          time.sleep(1)
          print("Connecting...")
      print("Connected to WiFi!")
      ip = wlan.ifconfig()[0]
      print("IP Address:", ip)
      return ip

  def connectMQTT():
      context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
      context.verify_mode = ssl.CERT_NONE
      client = MQTTClient(
          client_id=b"your_client_id",
          server="your_mqtt_broker_url",
          port=your_mqtt_port,
          user=b"your_username",
          password=b"your_password",
          keepalive=7200,
          ssl=context
      )
      client.connect()
      return client

  def publish(topic, value):
      client.publish(topic.encode('utf-8'), str(value).encode('utf-8'))
      print("Published:", topic, value)

  ip = connect()
  client = connectMQTT()

  while True:
      temp = pico_temp_sensor.temp
      print("Internal Temperature:", temp, "Celsius")
      publish('picow/temperature', temp)
      led.toggle()
      utime.sleep(5)
  ```

  - **Note**: Replace the placeholders with your actual Wi-Fi and MQTT broker credentials.

---

## Customization

- **Adjust Refresh Interval in Streamlit App**:
  - Modify the `st_autorefresh(interval=5000, key="refresh")` line in `main.py` to change how often the app refreshes.
- **Change MQTT Settings**:
  - Update MQTT broker details, topic, username, and password in both `main.py` and `pico_publisher.py` as needed.
- **Enhance Visualization**:
  - Customize the Altair chart in `main.py` to change colors, add more interactive features, or display additional data.
- **Modify Publishing Interval on Pico W**:
  - Adjust the `utime.sleep(5)` line in `pico_publisher.py` to change how often the Pico W publishes temperature data.

---

## Security Considerations

- **SSL/TLS Configuration**:
  - The current configuration disables certificate verification for testing purposes.
  - For production, enable certificate verification and use valid certificates.
- **Credentials**:
  - Ensure that Wi-Fi and MQTT usernames and passwords are stored securely.
  - Consider using environment variables or a configuration file that's not checked into version control.
- **Network Security**:
  - Be cautious when exposing your MQTT broker over the internet.
  - Implement appropriate firewall rules and access controls.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- **Streamlit**: For providing an excellent framework for building interactive web apps in Python.
- **paho-mqtt**: For the MQTT client library.
- **Altair**: For the powerful and intuitive data visualization library.
- **Raspberry Pi Foundation**: For the Raspberry Pi Pico W hardware.
- **MicroPython**: For enabling Python on microcontrollers.

---

Feel free to explore, modify, and enhance this project. If you have any questions or need assistance, please don't hesitate to reach out! Happy coding! 😊

---

**Note**: Replace placeholders like `your_SSID`, `your_password`, `your_client_id`, `your_mqtt_broker_url`, `your_mqtt_port`, `your_username`, and `your_password` with your actual credentials. Be sure to keep this sensitive information secure and avoid committing it to public repositories.