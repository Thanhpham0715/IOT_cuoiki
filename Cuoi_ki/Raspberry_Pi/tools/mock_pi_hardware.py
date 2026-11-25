"""MQTT test client that uses real Raspberry Pi hardware."""

import json
import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import paho.mqtt.client as mqtt
from pydantic import ValidationError

from pi.hardware import RaspberryPiHardware
from shared.config import cfg
from shared.logging_config import configure_logging
from shared.mqtt_topics import QOS, Topics
from shared.schemas import (
    ButtonEvent,
    DeviceStatus,
    LEDAck,
    LEDCommand,
    LEDStatus,
    LightSensor,
)

logger = logging.getLogger(__name__)


class HardwareMqttMock:
    def __init__(self) -> None:
        settings = cfg.get("mqtt", {})
        self.device_id = str(settings.get("device_id", "pi01"))
        self._settings = settings
        self._qos = {
            "telemetry": int(settings.get("qos_telemetry", QOS["telemetry"])),
            "command": int(settings.get("qos_command", QOS["command"])),
            "status": int(settings.get("qos_status", QOS["status"])),
        }
        if any(value not in {0, 1, 2} for value in self._qos.values()):
            raise ValueError("MQTT QoS values must be 0, 1, or 2")

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"photobooth-hardware-test-{self.device_id}",
        )
        if settings.get("username"):
            self.client.username_pw_set(settings["username"], settings.get("password"))
        if settings.get("tls_enabled"):
            self.client.tls_set(ca_certs=settings.get("tls_ca_certs"))

        offline = DeviceStatus(
            device_id=self.device_id,
            status="offline",
            version="hardware-test",
        )
        self.client.will_set(
            Topics.status(self.device_id),
            offline.model_dump_json(),
            qos=self._qos["status"],
            retain=True,
        )
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.hardware = RaspberryPiHardware(button_callback=self._publish_button)

    def run(self) -> None:
        loop_started = False
        try:
            frame = self.hardware.read_frame()
            logger.info("Camera ready: %sx%s", frame.shape[1], frame.shape[0])

            host = self._settings.get("broker_host", "127.0.0.1")
            port = int(self._settings.get("broker_port", 1883))
            interval = max(0.1, float(self._settings.get("telemetry_interval_sec", 2)))
            heartbeat_interval = max(
                0.1, float(self._settings.get("heartbeat_interval_sec", 5))
            )
            light_sensor_enabled = (
                cfg.get("camera", {}).get("light_sensor_address") is not None
            )
            if not light_sensor_enabled:
                logger.info("BH1750 sensor is disabled")

            self.client.reconnect_delay_set(min_delay=1, max_delay=30)
            self.client.connect_async(host, port, keepalive=30)
            self.client.loop_start()
            loop_started = True
            logger.info("Connecting to MQTT broker %s:%s", host, port)

            last_heartbeat = 0.0
            while True:
                now = time.monotonic()
                if self.client.is_connected():
                    if now - last_heartbeat >= heartbeat_interval:
                        self._publish_status("online")
                        last_heartbeat = now
                    if light_sensor_enabled:
                        try:
                            self._publish_light(self.hardware.read_lux())
                        except (RuntimeError, ValueError):
                            logger.exception("Could not read the configured light sensor")
                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("Stopping hardware MQTT test")
        finally:
            if loop_started:
                self.stop()
            else:
                self.hardware.close()

    def stop(self) -> None:
        if self.client.is_connected():
            info = self._publish_status("offline")
            if info.rc == mqtt.MQTT_ERR_SUCCESS:
                info.wait_for_publish(timeout=2)
            self.client.disconnect()
        self.client.loop_stop()
        self.hardware.close()

    def _on_connect(
        self, client, _userdata, _flags, reason_code, _properties
    ) -> None:
        if reason_code.is_failure:
            logger.error("MQTT connection rejected: %s", reason_code)
            return
        client.subscribe(
            Topics.led_set(self.device_id),
            qos=self._qos["command"],
        )
        self._publish_status("online")
        logger.info("Connected to MQTT broker as %s", self.device_id)

    def _on_disconnect(
        self, _client, _userdata, _disconnect_flags, reason_code, _properties
    ) -> None:
        logger.warning("Disconnected from MQTT broker: %s", reason_code)

    def _on_message(self, client, _userdata, message) -> None:
        try:
            command = LEDCommand.model_validate(
                json.loads(message.payload.decode("utf-8"))
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError):
            logger.exception("Invalid LED command on topic %s", message.topic)
            return

        try:
            applied = self.hardware.set_led(command.brightness)
            ack = LEDAck(command_id=command.command_id, applied=applied)
        except (RuntimeError, OSError, ValueError) as exc:
            ack = LEDAck(
                command_id=command.command_id,
                applied=0,
                success=False,
                error=str(exc),
            )

        client.publish(
            Topics.device_ack(self.device_id),
            ack.model_dump_json(),
            qos=self._qos["command"],
        )
        if ack.success:
            client.publish(
                Topics.led_status(self.device_id),
                LEDStatus(
                    device_id=self.device_id,
                    brightness=ack.applied,
                    timestamp=time.time(),
                ).model_dump_json(),
                qos=self._qos["telemetry"],
                retain=True,
            )
            logger.info("Applied LED brightness %s%%", ack.applied)
        else:
            logger.error("Could not apply LED command: %s", ack.error)

    def _publish_button(self, action: str) -> None:
        if not self.client.is_connected():
            logger.warning("Cannot publish button event; MQTT is disconnected")
            return
        event = ButtonEvent(
            device_id=self.device_id,
            action=action,
            timestamp=time.time(),
        )
        self.client.publish(
            Topics.button(self.device_id),
            event.model_dump_json(),
            qos=self._qos["command"],
        )

    def _publish_light(self, lux: float) -> None:
        sensor = LightSensor(
            device_id=self.device_id,
            lux=lux,
            timestamp=time.time(),
        )
        self.client.publish(
            Topics.sensor_light(self.device_id),
            sensor.model_dump_json(),
            qos=self._qos["telemetry"],
        )
        logger.info("BH1750 light level: %.1f lux", lux)

    def _publish_status(self, status: str):
        payload = DeviceStatus(
            device_id=self.device_id,
            status=status,
            version="hardware-test",
            timestamp=time.time(),
        )
        return self.client.publish(
            Topics.status(self.device_id),
            payload.model_dump_json(),
            qos=self._qos["status"],
            retain=True,
        )


def main() -> None:
    configure_logging("pi-hardware-test")
    if cfg.get("camera", {}).get("mock_hardware", False):
        raise RuntimeError(
            "Set camera.mock_hardware to false before running on real hardware"
        )
    HardwareMqttMock().run()


if __name__ == "__main__":
    main()
