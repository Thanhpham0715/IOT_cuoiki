"""MQTT bridge for device telemetry, status, and hardware commands."""

import json
import logging
import threading
import time
import uuid
from collections import deque

import paho.mqtt.client as mqtt
from pydantic import ValidationError

from shared.config import cfg
from shared.mqtt_topics import QOS, Topics
from shared.schemas import (
    ButtonEvent,
    DeviceStatus,
    LEDAck,
    LEDCommand,
    LEDStatus,
    LightSensor,
)
from server.storage import Storage

logger = logging.getLogger(__name__)


class IoTManager:
    def __init__(self, storage: Storage) -> None:
        settings = cfg.get("mqtt", {})
        self.device_id = settings.get("device_id", "pi01")
        self._settings = settings
        self._storage = storage
        self._qos = {
            "telemetry": int(settings.get("qos_telemetry", QOS["telemetry"])),
            "command": int(settings.get("qos_command", QOS["command"])),
            "status": int(settings.get("qos_status", QOS["status"])),
        }
        if any(value not in {0, 1, 2} for value in self._qos.values()):
            raise ValueError("MQTT QoS values must be 0, 1, or 2")
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"photobooth-server-{uuid.uuid4().hex[:8]}",
        )
        if settings.get("username"):
            self._client.username_pw_set(settings["username"], settings.get("password"))
        if settings.get("tls_enabled"):
            self._client.tls_set(ca_certs=settings.get("tls_ca_certs"))
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._connected = threading.Event()
        self._recent_lux: deque[float] = deque(maxlen=5)
        self._last_led_command_at = 0.0
        self._led_brightness = int(cfg.get("light_control", {}).get("default_brightness", 50))
        self._light_control_lock = threading.Lock()
        self._camera_status_lock = threading.Lock()
        self._camera_status: dict[str, dict] = {}
        self._camera_status_by_command: dict[tuple[str, str], dict] = {}

    @property
    def connected(self) -> bool:
        return self._connected.is_set() and self._client.is_connected()

    def start(self) -> None:
        host = self._settings.get("broker_host", "127.0.0.1")
        port = int(self._settings.get("broker_port", 1883))
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        try:
            self._client.connect_async(host, port, keepalive=30)
            self._client.loop_start()
            logger.info("Connecting to MQTT broker %s:%s", host, port)
        except (OSError, ValueError):
            logger.exception("Could not start MQTT connection to %s:%s", host, port)

    def stop(self) -> None:
        if self._client.is_connected():
            self._client.disconnect()
        self._client.loop_stop()

    def publish_led(self, device_id: str, brightness: int) -> str:
        if not self.connected:
            raise RuntimeError("MQTT broker is not connected")
        command = LEDCommand(command_id=uuid.uuid4().hex, brightness=brightness)
        info = self._client.publish(
            Topics.led_set(device_id),
            command.model_dump_json(),
            qos=self._qos["command"],
        )
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"MQTT publish failed with result code {info.rc}")
        self._last_led_command_at = time.monotonic()
        return command.command_id

    def publish_capture(
        self,
        device_id: str,
        session_id: str,
        photo_id: str | None = None,
        command_id: str | None = None,
    ) -> str:
        if not self.connected:
            raise RuntimeError("MQTT broker is not connected")
        command_id = command_id or uuid.uuid4().hex
        payload = {"command_id": command_id, "session_id": session_id}
        if photo_id is not None:
            payload["photo_id"] = photo_id
        info = self._client.publish(
            Topics.capture(device_id),
            json.dumps(payload),
            qos=self._qos["command"],
        )
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"MQTT publish failed with result code {info.rc}")
        return command_id

    def get_camera_status(
        self, device_id: str, command_id: str | None = None
    ) -> dict | None:
        with self._camera_status_lock:
            status = (
                self._camera_status_by_command.get((device_id, command_id))
                if command_id is not None
                else self._camera_status.get(device_id)
            )
            return dict(status) if status else None

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            self._connected.clear()
            logger.error("MQTT connection rejected: %s", reason_code)
            return
        self._connected.set()
        client.subscribe(
            [
                (f"photobooth/+/status", self._qos["status"]),
                (f"photobooth/+/sensor/light", self._qos["telemetry"]),
                (f"photobooth/+/led/status", self._qos["telemetry"]),
                (f"photobooth/+/device/ack", self._qos["command"]),
                (f"photobooth/+/button", self._qos["command"]),
                (f"photobooth/+/camera/status", self._qos["command"]),
            ]
        )
        logger.info("Connected to MQTT broker")

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties) -> None:
        self._connected.clear()
        logger.warning("Disconnected from MQTT broker: %s", reason_code)

    def _on_message(self, client, userdata, message) -> None:
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            parts = message.topic.split("/")
            device_id = parts[1]
            if len(parts) == 3 and parts[2] == "status":
                status = DeviceStatus.model_validate(payload)
                if status.device_id != device_id:
                    raise ValueError("Device ID does not match MQTT topic")
                self._storage.update_device(status.device_id, status.status, status.version)
            elif len(parts) == 4 and parts[2:] == ["sensor", "light"]:
                sensor = LightSensor.model_validate(payload)
                if sensor.device_id != device_id:
                    raise ValueError("Device ID does not match MQTT topic")
                self._storage.record_telemetry(
                    sensor.device_id, "lux", sensor.lux, sensor.timestamp
                )
                self._recent_lux.append(sensor.lux)
                self._adjust_light(device_id, sum(self._recent_lux) / len(self._recent_lux))
            elif len(parts) == 4 and parts[2:] == ["device", "ack"]:
                ack = LEDAck.model_validate(payload)
                self._led_brightness = ack.applied
                self._storage.update_led(device_id, ack.applied)
                if ack.success:
                    logger.info(
                        "Device %s applied LED brightness %s%%",
                        device_id,
                        ack.applied,
                    )
                else:
                    logger.error("Device %s rejected LED command: %s", device_id, ack.error)
            elif len(parts) == 4 and parts[2:] == ["led", "status"]:
                status = LEDStatus.model_validate(payload)
                if status.device_id != device_id:
                    raise ValueError("Device ID does not match MQTT topic")
                self._led_brightness = status.brightness
                self._storage.update_led(device_id, status.brightness)
            elif len(parts) == 3 and parts[2] == "button":
                event = ButtonEvent.model_validate(payload)
                if event.device_id != device_id:
                    raise ValueError("Device ID does not match MQTT topic")
                logger.info("Button event from %s: %s", event.device_id, event.action)
            elif len(parts) == 4 and parts[2:] == ["camera", "status"]:
                command_id = payload.get("command_id")
                status = payload.get("status")
                if not isinstance(command_id, str) or status not in {"completed", "failed"}:
                    raise ValueError("Invalid camera command result")
                with self._camera_status_lock:
                    self._camera_status[device_id] = dict(payload)
                    self._camera_status_by_command[(device_id, command_id)] = dict(payload)
                    while len(self._camera_status_by_command) > 256:
                        oldest_command = next(iter(self._camera_status_by_command))
                        del self._camera_status_by_command[oldest_command]
                logger.info("Camera command result from %s: %s", device_id, payload)
            else:
                logger.warning("Ignoring unsupported MQTT topic %s", message.topic)
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError):
            logger.exception("Invalid MQTT payload on topic %s", message.topic)

    def _adjust_light(self, device_id: str, lux: float) -> None:
        settings = cfg.get("light_control", {})
        if not settings.get("enabled", False):
            return
        with self._light_control_lock:
            min_interval = float(settings.get("min_cmd_interval_sec", 2))
            if time.monotonic() - self._last_led_command_at < min_interval:
                return
            hysteresis = float(settings.get("hysteresis", 0))
            low = float(settings.get("lux_low", 150)) - hysteresis
            high = float(settings.get("lux_high", 300)) + hysteresis
            if lux < low:
                brightness = min(100, self._led_brightness + 10)
            elif lux > high:
                brightness = max(0, self._led_brightness - 10)
            else:
                return
            try:
                self.publish_led(device_id, brightness)
            except RuntimeError:
                logger.warning("Cannot adjust LED while MQTT is disconnected")
