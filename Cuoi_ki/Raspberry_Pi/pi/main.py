"""Raspberry Pi client: camera streaming, MQTT, and local hardware control."""

import asyncio
import json
import logging
import os
import queue
import threading
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import cv2
import paho.mqtt.client as mqtt
import websockets
from websockets.exceptions import WebSocketException
from pydantic import ValidationError

from pi.hardware import MockHardware, RaspberryPiHardware
from shared.config import PROJECT_ROOT, cfg
from shared.logging_config import configure_logging
from shared.mqtt_topics import QOS, Topics
from shared.schemas import (
    DeviceStatus,
    LEDAck,
    LEDCommand,
    LEDStatus,
    LightSensor,
    WebSocketAuth,
)

configure_logging("pi")
logger = logging.getLogger(__name__)


class SessionExpiredError(RuntimeError):
    pass


def _token() -> str:
    return os.environ.get(
        "PHOTOBOOTH_STATIC_TOKEN",
        str(cfg.get("server", {}).get("static_token", "")),
    )


class MqttBridge:
    def __init__(self, hardware, capture_queue: queue.Queue) -> None:
        settings = cfg.get("mqtt", {})
        self.device_id = settings.get("device_id", "pi01")
        self.hardware = hardware
        self.capture_queue = capture_queue
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
            client_id=f"photobooth-{self.device_id}",
        )
        if settings.get("username"):
            self.client.username_pw_set(settings["username"], settings.get("password"))
        if settings.get("tls_enabled"):
            self.client.tls_set(ca_certs=settings.get("tls_ca_certs"))
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        offline = DeviceStatus(
            device_id=self.device_id,
            status="offline",
            version="2.0",
        )
        self.client.will_set(
            Topics.status(self.device_id),
            offline.model_dump_json(),
            qos=self._qos["status"],
            retain=True,
        )

    @property
    def connected(self) -> bool:
        return self.client.is_connected()

    def start(self) -> None:
        host = self._settings.get("broker_host", "127.0.0.1")
        port = int(self._settings.get("broker_port", 1883))
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        try:
            self.client.connect_async(host, port, keepalive=30)
            self.client.loop_start()
            logger.info("Connecting to MQTT broker %s:%s", host, port)
        except (OSError, ValueError):
            logger.exception("Could not start MQTT connection to %s:%s", host, port)

    def stop(self) -> None:
        if self.client.is_connected():
            online = DeviceStatus(device_id=self.device_id, status="offline")
            info = self.client.publish(
                Topics.status(self.device_id),
                online.model_dump_json(),
                qos=self._qos["status"],
                retain=True,
            )
            info.wait_for_publish(timeout=2)
            self.client.disconnect()
        self.client.loop_stop()

    def publish_button(self, action: str) -> None:
        if not self.connected:
            logger.warning("Cannot publish button event; MQTT is disconnected")
            return
        payload = {
            "device_id": self.device_id,
            "action": action,
            "timestamp": time.time(),
        }
        self.client.publish(
            Topics.button(self.device_id),
            json.dumps(payload),
            qos=self._qos["command"],
        )

    def publish_photo_status(self, command_id: str, success: bool, detail: str) -> None:
        if not self.connected:
            logger.warning("Cannot publish photo status; MQTT is disconnected")
            return
        self.client.publish(
            Topics.photo_status(self.device_id),
            json.dumps(
                {
                    "command_id": command_id,
                    "status": "completed" if success else "failed",
                    "detail": detail,
                    "timestamp": time.time(),
                }
            ),
            qos=self._qos["command"],
        )

    def publish_light(self, lux: float) -> None:
        if not self.connected:
            return
        payload = LightSensor(
            device_id=self.device_id,
            lux=lux,
            timestamp=time.time(),
        )
        self.client.publish(
            Topics.sensor_light(self.device_id),
            payload.model_dump_json(),
            qos=self._qos["telemetry"],
        )

    def publish_heartbeat(self) -> None:
        if not self.connected:
            return
        payload = DeviceStatus(
            device_id=self.device_id,
            status="online",
            version="2.0",
            timestamp=time.time(),
        )
        self.client.publish(
            Topics.status(self.device_id),
            payload.model_dump_json(),
            qos=self._qos["status"],
            retain=True,
        )

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            logger.error("MQTT connection rejected: %s", reason_code)
            return
        client.subscribe(
            [
                (Topics.led_set(self.device_id), self._qos["command"]),
                (Topics.capture(self.device_id), self._qos["command"]),
            ]
        )
        online = DeviceStatus(
            device_id=self.device_id,
            status="online",
            version="2.0",
            timestamp=time.time(),
        )
        client.publish(
            Topics.status(self.device_id),
            online.model_dump_json(),
            qos=self._qos["status"],
            retain=True,
        )
        logger.info("Connected to MQTT broker as %s", self.device_id)

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties) -> None:
        logger.warning("Disconnected from MQTT broker: %s", reason_code)

    def _on_message(self, client, userdata, message) -> None:
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            if message.topic == Topics.led_set(self.device_id):
                command = LEDCommand.model_validate(payload)
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
                if not ack.success:
                    logger.error("LED command failed: %s", ack.error)
            elif message.topic == Topics.capture(self.device_id):
                command_id = str(payload["command_id"])
                session_id = str(payload["session_id"])
                capture_command = {
                    "command_id": command_id,
                    "session_id": session_id,
                    "source": "server",
                }
                photo_id = payload.get("photo_id")
                if photo_id is not None:
                    if not isinstance(photo_id, str):
                        raise ValueError("Capture photo_id must be a string")
                    capture_command["photo_id"] = photo_id
                self.capture_queue.put(capture_command)
            else:
                logger.warning("Ignoring unsupported MQTT topic %s", message.topic)
        except (KeyError, UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError):
            logger.exception("Invalid MQTT command on topic %s", message.topic)


class PiClient:
    def __init__(self) -> None:
        self.settings = cfg.get("server", {})
        self.camera_settings = cfg.get("camera", {})
        self.device_id = cfg.get("mqtt", {}).get("device_id", "pi01")
        self.host = self.settings.get("client_host", "127.0.0.1")
        self.port = int(self.settings.get("http_port", 8000))
        self.base_url = f"http://{self.host}:{self.port}"
        self.ws_url = f"ws://{self.host}:{self.port}{self.settings.get('ws_path', '/ws/frames')}"
        self.capture_queue: queue.Queue = queue.Queue()
        self.manual_capture = threading.Event()
        self._camera_lock = threading.Lock()
        self._processed_command_ids: set[str] = set()
        offline_dir = cfg.get("storage", {}).get("offline_photo_dir", "data/offline_photos")
        self.offline_photo_dir = Path(offline_dir).expanduser()
        if not self.offline_photo_dir.is_absolute():
            self.offline_photo_dir = PROJECT_ROOT / self.offline_photo_dir
        if self.camera_settings.get("mock_hardware", False):
            logger.warning("Mock hardware is enabled; camera frames will be synthetic")
            self.hardware = MockHardware()
        else:
            logger.info(
                "Opening Raspberry Pi camera at index %s",
                self.camera_settings.get("device_index", 0),
            )
            self.hardware = RaspberryPiHardware(self._on_button)
        self.mqtt = MqttBridge(self.hardware, self.capture_queue)
        self.session_id: str | None = None

    def _headers(self, content_type: str | None = None) -> dict[str, str]:
        headers = {}
        token = _token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _request_json(self, path: str, method: str = "GET", payload: dict | None = None):
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=self._headers("application/json" if body is not None else None),
            method=method,
        )
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def _get_or_create_session(self) -> str:
        active_path = f"/api/v1/sessions/active/{quote(self.device_id, safe='')}"
        try:
            session = self._request_json(active_path)
            return str(session["session_id"])
        except HTTPError as exc:
            if exc.code != 404:
                raise
        session = self._request_json(
            "/api/v1/sessions",
            method="POST",
            payload={
                "device_id": self.device_id,
                "pose_template_id": None,
                "effect_id": cfg.get("effects", {}).get("default_effect_id", "original"),
            },
        )
        return str(session["session_id"])

    async def _ensure_session(self) -> str:
        delay = 1
        while True:
            try:
                self.session_id = await asyncio.to_thread(self._get_or_create_session)
                logger.info("Using active session %s", self.session_id)
                return self.session_id
            except (HTTPError, URLError, TimeoutError, OSError, ValueError):
                logger.exception("Could not get a session; retrying in %s seconds", delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)

    async def _publish_telemetry(self) -> None:
        interval = float(cfg.get("mqtt", {}).get("telemetry_interval_sec", 2))
        heartbeat_interval = float(cfg.get("mqtt", {}).get("heartbeat_interval_sec", 5))
        light_sensor_enabled = self.camera_settings.get("light_sensor_address") is not None
        last_heartbeat = 0.0
        while True:
            try:
                if time.monotonic() - last_heartbeat >= heartbeat_interval:
                    self.mqtt.publish_heartbeat()
                    last_heartbeat = time.monotonic()
                if light_sensor_enabled:
                    lux = await asyncio.to_thread(self.hardware.read_lux)
                    self.mqtt.publish_light(lux)
            except (RuntimeError, ValueError):
                logger.exception("Could not read the configured light sensor")
            await asyncio.sleep(interval)

    async def _stream(self, session_id: str) -> None:
        frame_id = 0
        target_fps = max(1, int(self.camera_settings.get("target_fps", 5)))
        frame_interval = 1 / target_fps
        max_size = int(self.settings.get("max_frame_bytes", 10 * 1024 * 1024))
        previous_frame_started = None

        async with websockets.connect(
            self.ws_url, max_size=max_size, ping_interval=20
        ) as websocket:
            await websocket.send(WebSocketAuth(token=_token()).model_dump_json())
            auth_response = json.loads(await websocket.recv())
            if not auth_response.get("authenticated"):
                raise PermissionError("AI server rejected WebSocket authentication")
            logger.info("Connected to AI server WebSocket")
            await self._sync_pending_photos(session_id)
            while True:
                started = time.monotonic()
                frame_interval_ms = (
                    (started - previous_frame_started) * 1000
                    if previous_frame_started is not None
                    else None
                )
                previous_frame_started = started
                frame = await asyncio.to_thread(self._read_frame)
                width = int(self.camera_settings.get("width", 640))
                height = int(self.camera_settings.get("height", 480))
                if frame.shape[1] != width or frame.shape[0] != height:
                    frame = cv2.resize(frame, (width, height))
                quality = int(self.camera_settings.get("jpeg_quality", 70))
                encoded, jpeg = cv2.imencode(
                    ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality]
                )
                if not encoded:
                    raise RuntimeError("Could not encode camera frame as JPEG")
                frame_id += 1
                metadata = {
                    "session_id": session_id,
                    "device_id": self.device_id,
                    "frame_id": frame_id,
                    "timestamp": time.time(),
                }
                await websocket.send(json.dumps(metadata))
                await websocket.send(jpeg.tobytes())
                response = await asyncio.wait_for(websocket.recv(), timeout=30)
                if isinstance(response, bytes):
                    logger.warning("AI server returned an unexpected binary message")
                else:
                    self._handle_frame_result(
                        json.loads(response), session_id, frame_interval_ms
                    )
                await self._process_capture_requests(session_id)
                remaining = frame_interval - (time.monotonic() - started)
                if remaining > 0:
                    await asyncio.sleep(remaining)

    def _handle_frame_result(
        self,
        result: dict,
        session_id: str,
        frame_interval_ms: float | None = None,
    ) -> None:
        if "error" in result:
            if result["error"] == "Session is not active":
                raise SessionExpiredError(session_id)
            logger.warning("AI server rejected frame %s: %s", result.get("frame_id"), result["error"])
            return
        frame_interval_ms = frame_interval_ms or 0.0
        achieved_fps = 1000 / frame_interval_ms if frame_interval_ms > 0 else 0.0
        logger.info(
            "frame=%s gesture=%s confidence=%.2f control=%s effect=%s zoom=%.2fx processing_ms=%.1f frame_interval_ms=%.1f achieved_fps=%.1f",
            result.get("frame_id"),
            result.get("selected_gesture") or "none",
            result.get("selected_gesture_score", 0),
            result.get("control_state", "inactive"),
            result.get("selected_effect_id", "original"),
            result.get("zoom_factor", 1),
            result.get("processing_ms", 0),
            frame_interval_ms,
            achieved_fps,
        )

    async def _process_capture_requests(self, session_id: str) -> None:
        try:
            command = self.capture_queue.get_nowait()
        except queue.Empty:
            return
        if command["session_id"] != session_id:
            logger.warning("Ignoring capture command for a different session")
            return
        if command["command_id"] in self._processed_command_ids:
            logger.warning("Ignoring duplicate capture command %s", command["command_id"])
            return
        self._processed_command_ids.add(command["command_id"])
        try:
            photo_id = str(command.get("photo_id", uuid.uuid4().hex))
            jpeg = None
            frame = await asyncio.to_thread(self._read_photo_frame)
            quality = int(self.camera_settings.get("photo_jpeg_quality", 90))
            encoded, encoded_jpeg = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality]
            )
            if not encoded:
                raise RuntimeError("Could not encode captured photo")
            jpeg = encoded_jpeg
            photo = await asyncio.to_thread(
                self._upload_photo,
                session_id,
                jpeg.tobytes(),
                int(command.get("pose_score", 0)),
                photo_id,
            )
            self.mqtt.publish_photo_status(
                command["command_id"], True, str(photo["photo_id"])
            )
            logger.info("Saved photo %s for session %s", photo["photo_id"], session_id)
        except (HTTPError, URLError, TimeoutError, OSError, RuntimeError, ValueError):
            logger.exception("Photo capture failed for command %s", command["command_id"])
            if jpeg is not None:
                self._save_offline_photo(session_id, photo_id, jpeg.tobytes())
                self.mqtt.publish_photo_status(
                    command["command_id"], False, "saved locally for sync"
                )
            else:
                self.mqtt.publish_photo_status(command["command_id"], False, "capture failed")

    def _read_frame(self):
        with self._camera_lock:
            return self.hardware.read_frame()

    def _read_photo_frame(self):
        with self._camera_lock:
            return self.hardware.capture_photo()

    async def _manual_capture_loop(self) -> None:
        while True:
            triggered = await asyncio.to_thread(self.manual_capture.wait, 0.5)
            if not triggered:
                continue
            self.manual_capture.clear()
            command_id = f"button-{uuid.uuid4().hex}"
            photo_id = uuid.uuid4().hex
            session_id = self.session_id
            try:
                frame = await asyncio.to_thread(self._read_photo_frame)
                quality = int(self.camera_settings.get("photo_jpeg_quality", 90))
                encoded, jpeg = cv2.imencode(
                    ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality]
                )
                if not encoded:
                    raise RuntimeError("Could not encode captured photo")
                if session_id:
                    try:
                        photo = await asyncio.to_thread(
                            self._upload_photo, session_id, jpeg.tobytes(), 0, photo_id
                        )
                        self.mqtt.publish_photo_status(
                            command_id, True, str(photo["photo_id"])
                        )
                        continue
                    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
                        logger.exception("Server upload failed; preserving photo locally")
                self._save_offline_photo(session_id, photo_id, jpeg.tobytes())
                self.mqtt.publish_photo_status(command_id, False, "saved locally for sync")
            except (OSError, RuntimeError, ValueError):
                logger.exception("Manual photo capture failed")

    def _save_offline_photo(self, session_id: str | None, photo_id: str, jpeg: bytes) -> Path:
        folder_name = str(uuid.UUID(session_id)) if session_id else "unassigned"
        directory = self.offline_photo_dir / folder_name
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / f"{photo_id}.jpg"
        destination.write_bytes(jpeg)
        logger.warning("Photo saved offline at %s", destination)
        return destination

    async def _sync_pending_photos(self, session_id: str) -> None:
        self.offline_photo_dir.mkdir(parents=True, exist_ok=True)
        directories = sorted(
            (path for path in self.offline_photo_dir.iterdir() if path.is_dir()),
            key=lambda path: path.name != "unassigned",
        )
        for directory in directories:
            if directory.name == "unassigned":
                target_session = session_id
            else:
                try:
                    target_session = str(uuid.UUID(directory.name))
                except ValueError:
                    logger.error("Ignoring invalid offline session directory %s", directory)
                    continue
            for photo_path in directory.glob("*.jpg"):
                try:
                    jpeg = await asyncio.to_thread(photo_path.read_bytes)
                    await asyncio.to_thread(
                        self._upload_photo, target_session, jpeg, 0, photo_path.stem
                    )
                    await asyncio.to_thread(photo_path.unlink)
                    logger.info("Uploaded offline photo %s", photo_path.name)
                except (HTTPError, URLError, TimeoutError, OSError, ValueError):
                    logger.exception("Could not sync offline photo %s", photo_path)

    def _upload_photo(
        self, session_id: str, jpeg: bytes, pose_score: int, photo_id: str | None = None
    ) -> dict:
        query = urlencode({"session_id": session_id})
        request = Request(
            f"{self.base_url}/api/v1/photos?{query}",
            data=jpeg,
            headers={
                **self._headers("image/jpeg"),
                "X-Pose-Score": str(pose_score),
                **({"X-Photo-ID": photo_id} if photo_id else {}),
            },
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def _on_button(self, action: str) -> None:
        logger.info("Physical button pressed: %s", action)
        self.manual_capture.set()
        if hasattr(self, "mqtt"):
            self.mqtt.publish_button(action)

    async def run(self) -> None:
        self.mqtt.start()
        telemetry_task = asyncio.create_task(self._publish_telemetry())
        manual_task = asyncio.create_task(self._manual_capture_loop())
        delay = 1
        try:
            session_id = await self._ensure_session()
            while True:
                try:
                    await self._stream(session_id)
                    delay = 1
                except SessionExpiredError:
                    logger.info("Session %s ended; creating or restoring a session", session_id)
                    session_id = await self._ensure_session()
                    delay = 1
                except (OSError, TimeoutError, RuntimeError, ValueError, WebSocketException):
                    logger.exception("Camera stream failed; reconnecting in %s seconds", delay)
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 30)
        finally:
            self.manual_capture.set()
            telemetry_task.cancel()
            manual_task.cancel()
            try:
                await telemetry_task
            except asyncio.CancelledError:
                pass
            try:
                await manual_task
            except asyncio.CancelledError:
                pass
            self.mqtt.stop()
            self.hardware.close()
            if self.session_id:
                try:
                    await asyncio.to_thread(
                        self._request_json,
                        f"/api/v1/sessions/{quote(self.session_id, safe='')}/end",
                        "POST",
                    )
                except (HTTPError, URLError, TimeoutError, OSError, ValueError):
                    logger.exception("Could not end session %s", self.session_id)


async def main() -> None:
    await PiClient().run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Raspberry Pi client stopped")
