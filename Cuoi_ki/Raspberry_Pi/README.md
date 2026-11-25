# Raspberry Pi module

This is the standalone Raspberry Pi client. Copy the entire `Raspberry_Pi`
folder to the Pi; do not copy only `pi/`, because `shared/` and `config/` are
required at runtime.

## Configure

Edit `config/config.yaml`:

- Set `server.client_host` to the PC/laptop's LAN IP address.
- Set `mqtt.broker_host` to the MQTT broker's LAN IP address.
- The default `camera.mock_hardware: false` uses the real Pi camera/GPIO. Set
  it to `true` only for a software-only demo; startup logs state which source
  is active.
- LED PWM is configured on BCM GPIO18; the physical button defaults to BCM
  GPIO17. With GPIO Zero's default pull-up, wire the button between GPIO17 and
  GND. Set `camera.button_gpio_pin: null` if no physical button is connected.
- To disable the optional BH1750 sensor, set
  `camera.light_sensor_address: null` and `light_control.enabled: false`.
- Set the same `server.static_token` value as the Server module if token
  authentication is enabled there.

For real GPIO hardware, GPIO Zero also needs the `lgpio` pin backend. Install
its build dependencies on Raspberry Pi OS, then install `lgpio` into the active
virtual environment:

```bash
sudo apt update
sudo apt install python3-dev swig liblgpio-dev -y
source .venv/bin/activate
python -m pip install lgpio
```

The `lgpio` backend provides the PWM support required by the configured LED.

The BH1750 backend is only needed if the sensor is enabled. The Pi and PC must
be able to reach each other, and the configured API and MQTT ports must be
reachable through the network/firewall.
The checked-in Pi config uses `10.228.70.213` for both Server and broker;
change those values if the PC's LAN IP changes.

## Install and run

From inside `Raspberry_Pi`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[pi]"
python -m pi.main
```

The client sends camera frames to the Server over WebSocket and communicates
device status, sensor readings, and commands over MQTT. Captures queued while
offline are stored under `data/offline_photos/` and uploaded after reconnecting.
The default stream resolution is 480x360 at JPEG quality 60 for smoother
preview; high-resolution capture remains configured separately.
The Server recognizes hand gestures and sends capture commands over MQTT; no
pose template or pose-scoring model is required.

The stream defaults to 480x360 at 12 FPS. Pi logs include AI processing time
and observed frame interval/FPS, so you can tell whether the target rate is
actually being met. If the observed rate is low, check network and Pi capture
time as well as AI inference time. If AI time is high, reduce
`camera.width`/`camera.height` to `320x240` and `jpeg_quality` to 50; lower
resolution can reduce gesture accuracy, so verify gestures remain reliable.

## Test real hardware over MQTT only

To check the camera, physical LED, and MQTT connection without starting the
full camera-streaming client, set `camera.mock_hardware: false` and run from
the project folder. The BH1750 test is skipped when its address is `null`:

```bash
python tools/mock_pi_hardware.py
```

The test publishes device status, applies received LED commands to the
configured GPIO, and publishes ACK/status messages. If BH1750 is enabled it
also publishes measured light readings; if a button GPIO is configured, button
presses are sent over MQTT. Press `Ctrl+C` to stop; unexpected disconnects are
reported offline through MQTT Last Will.
