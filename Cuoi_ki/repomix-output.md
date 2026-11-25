This file is a merged representation of the entire codebase, combined into a single document by Repomix.

# File Summary

## Purpose
This file contains a packed representation of the entire repository's contents.
It is designed to be easily consumable by AI systems for analysis, code review,
or other automated processes.

## File Format
The content is organized as follows:
1. This summary section
2. Repository information
3. Directory structure
4. Repository files (if enabled)
5. Multiple file entries, each consisting of:
  a. A header with the file path (## File: path/to/file)
  b. The full contents of the file in a code block

## Usage Guidelines
- This file should be treated as read-only. Any changes should be made to the
  original repository files, not this packed version.
- When processing this file, use the file path to distinguish
  between different files in the repository.
- Be aware that this file may contain sensitive information. Handle it with
  the same level of security as you would the original repository.

## Notes
- Some files may have been excluded based on .gitignore rules and Repomix's configuration
- Binary files are not included in this packed representation. Please refer to the Repository Structure section for a complete list of file paths, including binary files
- Files matching patterns in .gitignore are excluded
- Files matching default ignore patterns are excluded
- Files are sorted by Git change count (files with more changes are at the bottom)

# Directory Structure
````
config/
  config.yaml
pi/
  __init__.py
  main.py
server/
  __init__.py
  main.py
shared/
  __init__.py
  config.py
  mqtt_topics.py
  schemas.py
tools/
  mock_pi_mqtt.py
  mock_server.py
.gitignore
pyproject.toml
README.md
````

# Files

## File: config/config.yaml
````yaml
# config/config.yaml
# ==================
# MỌI THÔNG SỐ CẤU HÌNH ĐỀU Ở ĐÂY — không hardcode trong code.
# Khi demo đổi mạng: chỉ sửa file này.

server:
  host: "127.0.0.1"          # ← đổi thành IP của PC khi Pi kết nối thật
  ws_port: 8765
  http_port: 8000
  static_token: "photobooth_demo_2026"   # token tĩnh cho Base

mqtt:
  broker_host: "127.0.0.1"   # ← đổi thành IP PC nếu broker chạy trên PC
  broker_port: 1883
  device_id: "pi01"
  heartbeat_interval_sec: 5
  # LWT (Last Will) — broker tự gửi khi Pi mất kết nối đột ngột
  lwt_payload: '{"device_id": "pi01", "status": "offline"}'

camera:
  width: 640
  height: 480
  jpeg_quality: 70            # 70 đủ cho AI, giảm băng thông
  target_fps: 5               # tăng lên 10 nếu benchmark ổn

light_control:
  lux_low: 150                # dưới ngưỡng này → tăng LED
  lux_high: 300               # trên ngưỡng này → giảm LED
  hysteresis: 30              # vùng "giữ nguyên" để tránh nhấp nháy
  min_cmd_interval_sec: 2.0   # tối đa 1 lệnh LED / 2 giây
  default_brightness: 50      # mức mặc định khi mất kết nối

pose:
  stability_frames: 10        # giữ pose tốt liên tục N frame → auto capture
  score_threshold: 75         # 0–100, cần chỉnh lại sau khi test thực tế
  countdown_sec: 3

storage:
  photo_dir: "data/photos"
  db_path: "data/photobooth.db"
  log_dir: "data/logs"
  telemetry_retention_days: 7
````

## File: pi/__init__.py
````python
"""
pi/__init__.py
"""
````

## File: pi/main.py
````python
"""
pi/main.py
----------
Entry point của ứng dụng Pi.
Chạy: python pi/main.py
"""
# TODO: import và khởi động các module Pi
````

## File: server/__init__.py
````python
"""
server/__init__.py
"""
````

## File: server/main.py
````python
"""
server/main.py
--------------
Entry point của AI Server.
Chạy: python server/main.py
      hoặc: uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload
"""
from fastapi import FastAPI

app = FastAPI(title="AI Smart Photobooth 2.0")

@app.get("/health")
def health():
    return {"status": "ok"}

# TODO: thêm router cho sessions, photos, devices, dashboard
# TODO: khởi động MQTT client, WebSocket server

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=True)
````

## File: shared/__init__.py
````python
"""
shared/__init__.py
Đánh dấu shared/ là Python package để import được.
"""
````

## File: shared/config.py
````python
"""
shared/config.py
----------------
Đọc config.yaml một lần, dùng ở mọi nơi.

Dùng:
    from shared.config import cfg
    host = cfg["server"]["host"]
    fps  = cfg["camera"]["target_fps"]
"""

import yaml
from pathlib import Path

_config = None


def _load():
    global _config
    if _config is None:
        path = Path(__file__).parent.parent / "config" / "config.yaml"
        with open(path, encoding="utf-8") as f:
            _config = yaml.safe_load(f)
    return _config


# Import thẳng: from shared.config import cfg
cfg = _load()
````

## File: shared/mqtt_topics.py
````python
"""
shared/mqtt_topics.py
---------------------
Tên topic MQTT dùng chung.
Mọi người import từ đây, không gõ tay chuỗi topic ở nhiều chỗ.

Dùng:
    from shared.mqtt_topics import Topics
    client.subscribe(Topics.led_set("pi01"))   # → "photobooth/pi01/led/set"
"""


class Topics:
    """Factory tạo topic theo device_id."""

    @staticmethod
    def status(device_id: str) -> str:
        """Pi publish online/offline (retained + LWT)."""
        return f"photobooth/{device_id}/status"

    @staticmethod
    def sensor_light(device_id: str) -> str:
        """Pi publish lux."""
        return f"photobooth/{device_id}/sensor/light"

    @staticmethod
    def led_set(device_id: str) -> str:
        """Server publish lệnh LED."""
        return f"photobooth/{device_id}/led/set"

    @staticmethod
    def led_status(device_id: str) -> str:
        """Pi publish trạng thái LED hiện tại."""
        return f"photobooth/{device_id}/led/status"

    @staticmethod
    def device_ack(device_id: str) -> str:
        """Pi publish ACK sau khi thực thi lệnh."""
        return f"photobooth/{device_id}/device/ack"

    @staticmethod
    def button(device_id: str) -> str:
        """Pi publish sự kiện nút nhấn."""
        return f"photobooth/{device_id}/button"


# QoS mặc định theo loại dữ liệu
QOS = {
    "telemetry": 0,     # lux, LED status — mất 1 bản không sao
    "command": 1,       # led/set, capture — cần đảm bảo đến nơi
    "status": 1,        # online/offline — quan trọng
}
````

## File: shared/schemas.py
````python
"""
shared/schemas.py
-----------------
"Hợp đồng" JSON giữa Pi và Server.

TẠI SAO CẦN FILE NÀY?
  Pi gửi lệnh chụp → Server nhận.
  Nếu Pi gửi   {"brightness": 70}
  mà Server đợi {"led_level": 70}
  → code lỗi, debug mất nửa ngày.

  File này chốt: trường nào, kiểu gì, bắt buộc hay không.
  Mọi người import từ đây, không tự định nghĩa riêng.

CÁCH DÙNG:
  from shared.schemas import LEDCommand, PoseResult
  cmd = LEDCommand(command_id="cmd_001", brightness=70)
  print(cmd.model_dump_json())   # → {"command_id":"cmd_001","brightness":70}
"""

from pydantic import BaseModel, Field
from typing import List, Optional


# ═══════════════════════════════════════════════════════════════
#  WEBSOCKET  Pi ←→ Server
# ═══════════════════════════════════════════════════════════════

class FrameMeta(BaseModel):
    """Pi gửi kèm mỗi frame ảnh (gửi JSON trước, rồi gửi JPEG binary sau)."""
    session_id: str
    frame_id: int
    timestamp: float            # time.time() trên Pi


class KeyPoint(BaseModel):
    """Một điểm khớp trên cơ thể người."""
    name: str                   # "left_shoulder", "right_wrist", ...
    x: float                    # 0.0 → 1.0  (chuẩn hóa theo chiều rộng frame)
    y: float                    # 0.0 → 1.0  (chuẩn hóa theo chiều cao frame)
    visibility: float           # 0.0 → 1.0  (độ chắc chắn của MediaPipe)


class FeedbackItem(BaseModel):
    """Một câu hướng dẫn cho người dùng."""
    body_part: str              # "right_arm", "head", "shoulders", ...
    message: str                # "Giơ tay phải lên cao hơn"


class PoseResult(BaseModel):
    """Server gửi về Pi sau mỗi frame xử lý xong."""
    session_id: str
    frame_id: int
    pose_score: int             # 0–100, do rule-based tính
    status: str                 # "ok" | "adjusting" | "no_person"
    keypoints: List[KeyPoint] = []
    feedback: List[FeedbackItem] = []
    ready_to_capture: bool = False


class CaptureCommand(BaseModel):
    """Server yêu cầu Pi chụp ảnh (gửi khi pose ổn định đủ N frame)."""
    command_id: str             # "cap_<8 ký tự ngẫu nhiên>"  — tránh chụp trùng
    countdown_sec: int = 3


# ═══════════════════════════════════════════════════════════════
#  MQTT  Pi ←→ Server
# ═══════════════════════════════════════════════════════════════

class DeviceStatus(BaseModel):
    """Pi publish khi kết nối / mất kết nối.
    LWT dùng: status="offline", retain=True."""
    device_id: str
    status: str                 # "online" | "offline"
    version: Optional[str] = None


class LightSensor(BaseModel):
    """Pi publish lux mỗi 1–2 giây."""
    device_id: str
    lux: float
    timestamp: float


class LEDCommand(BaseModel):
    """Server gửi lệnh đặt mức LED cho Pi."""
    command_id: str             # "cmd_<8 ký tự>" — Pi dùng để gửi ACK khớp lại
    brightness: int             # 0–100 (PWM %)


class LEDAck(BaseModel):
    """Pi gửi lại xác nhận đã thực thi lệnh LED."""
    command_id: str             # phải khớp với LEDCommand.command_id
    applied: int                # mức Pi thực sự đặt (có thể khác do giới hạn phần cứng)


class ButtonEvent(BaseModel):
    """Pi publish khi người dùng nhấn nút vật lý."""
    device_id: str
    action: str                 # "start_session" | "manual_capture" | "cancel_countdown"
    timestamp: float


# ═══════════════════════════════════════════════════════════════
#  REST API  (Base: chỉ dùng khi cần gallery và health check)
# ═══════════════════════════════════════════════════════════════

class PhotoMeta(BaseModel):
    """Metadata một ảnh đã chụp, lưu trong SQLite."""
    photo_id: str
    session_id: str
    pose_template_id: str
    timestamp: float
    file_path: str              # đường dẫn tương đối từ data/photos/
    pose_score: int


class HealthResponse(BaseModel):
    """GET /health"""
    status: str = "ok"
    uptime_sec: float
    connected_devices: int
````

## File: tools/mock_pi_mqtt.py
````python
"""
tools/mock_pi_mqtt.py
---------------------
Giả lập Pi publish MQTT — để test dashboard và server mà không cần Pi thật.

Chạy: python tools/mock_pi_mqtt.py
"""
import json
import random
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import paho.mqtt.client as mqtt
from shared.config import cfg
from shared.mqtt_topics import Topics
from shared.schemas import LightSensor, DeviceStatus, LEDAck

DEVICE_ID = cfg["mqtt"]["device_id"]
BROKER    = cfg["mqtt"]["broker_host"]
PORT      = cfg["mqtt"]["broker_port"]
INTERVAL  = cfg["mqtt"]["heartbeat_interval_sec"]


def on_message(client, userdata, msg):
    """Nhận lệnh LED từ server và gửi ACK giả."""
    try:
        payload = json.loads(msg.payload.decode())
        cmd_id  = payload.get("command_id", "unknown")
        brightness = payload.get("brightness", 50)
        print(f"[mock_pi] Nhận lệnh LED: brightness={brightness} (cmd={cmd_id})")

        ack = LEDAck(command_id=cmd_id, applied=brightness)
        client.publish(Topics.device_ack(DEVICE_ID), ack.model_dump_json(), qos=1)
        print(f"[mock_pi] Gửi ACK: {ack.model_dump_json()}")
    except Exception as e:
        print(f"[mock_pi] Lỗi xử lý lệnh LED: {e}")


def main():
    client = mqtt.Client(client_id=f"mock_pi_{DEVICE_ID}")

    # LWT: broker tự gửi "offline" nếu mock_pi mất kết nối đột ngột
    lwt_payload = DeviceStatus(device_id=DEVICE_ID, status="offline").model_dump_json()
    client.will_set(Topics.status(DEVICE_ID), lwt_payload, qos=1, retain=True)

    client.on_message = on_message
    client.connect(BROKER, PORT)
    client.subscribe(Topics.led_set(DEVICE_ID), qos=1)

    # Publish online
    online = DeviceStatus(device_id=DEVICE_ID, status="online", version="mock-0.1")
    client.publish(Topics.status(DEVICE_ID), online.model_dump_json(), qos=1, retain=True)
    print(f"[mock_pi] Đã kết nối broker {BROKER}:{PORT}, device_id={DEVICE_ID}")
    print("[mock_pi] Đang publish lux mỗi 2 giây. Ctrl+C để dừng.")

    client.loop_start()

    lux = 200.0
    try:
        while True:
            # Lux dao động ngẫu nhiên (mô phỏng cảm biến)
            lux += random.uniform(-10, 10)
            lux = max(50, min(500, lux))

            sensor = LightSensor(device_id=DEVICE_ID, lux=round(lux, 1), timestamp=time.time())
            client.publish(Topics.sensor_light(DEVICE_ID), sensor.model_dump_json(), qos=0)
            print(f"[mock_pi] lux={lux:.1f}")

            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        print("\n[mock_pi] Dừng.")
        # Không gọi disconnect() → broker sẽ gửi LWT "offline"
        client.loop_stop()


if __name__ == "__main__":
    main()
````

## File: tools/mock_server.py
````python
"""
tools/mock_server.py
--------------------
Server giả để Pi phát triển và test độc lập — KHÔNG cần AI thật.

Nhận frame từ Pi → trả PoseResult ngẫu nhiên mỗi vòng.
Chạy: python tools/mock_server.py
"""
import asyncio
import json
import random
import time
import websockets

# Thêm root vào path để import shared
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.schemas import PoseResult, FeedbackItem

PORT = 8765


async def handler(websocket):
    print(f"[mock_server] Pi kết nối: {websocket.remote_address}")
    frame_id = 0

    async for message in websocket:
        frame_id += 1

        # Bỏ qua binary frame (JPEG), chỉ parse JSON meta
        if isinstance(message, str):
            meta = json.loads(message)
            session_id = meta.get("session_id", "mock_session")
        else:
            session_id = "mock_session"
            # Nhận được ảnh — trong thực tế server sẽ gửi vào AI
            # print(f"[mock_server] Nhận frame {frame_id}, {len(message)} bytes")
            continue

        # Giả lập AI response — cứ 15 frame thì "sẵn sàng chụp"
        score = random.randint(55, 95)
        ready = (frame_id % 15 == 0)

        result = PoseResult(
            session_id=session_id,
            frame_id=frame_id,
            pose_score=score,
            status="ok" if score >= 75 else "adjusting",
            feedback=([] if score >= 75 else [
                FeedbackItem(body_part="right_arm", message="Giơ tay phải lên cao hơn")
            ]),
            ready_to_capture=ready,
        )

        await websocket.send(result.model_dump_json())
        if ready:
            print(f"[mock_server] Frame {frame_id}: READY TO CAPTURE (score={score})")


async def main():
    print(f"[mock_server] Đang chạy tại ws://0.0.0.0:{PORT}")
    print("[mock_server] Ctrl+C để dừng")
    async with websockets.serve(handler, "0.0.0.0", PORT):
        await asyncio.Future()  # chạy mãi


if __name__ == "__main__":
    asyncio.run(main())
````

## File: .gitignore
````
# .gitignore
__pycache__/
*.pyc
*.pyo
.venv/
venv/
.env

# Dữ liệu runtime — không commit
data/photos/
data/logs/
data/*.db
data/*.db-shm
data/*.db-wal

# File tạm từ công cụ đọc docx
read_docx.py
docx_content.txt

# IDE
.vscode/
.idea/
*.swp
````

## File: pyproject.toml
````toml
# AI Smart Photobooth 2.0
# =======================
# Chạy trên: Raspberry Pi 4 (client IoT) + PC (AI Server)
# Phát triển: SSH vào PC, code chung cây thư mục này.

[project]
name = "photobooth"
version = "0.1.0"
requires-python = ">=3.10"

[tool.setuptools.packages.find]
where = ["."]
include = ["shared*", "pi*", "server*"]
````

## File: README.md
````markdown
# AI Smart Photobooth 2.0

## Cấu trúc thư mục

```
photobooth/
├── shared/          # Schema, config, hằng số — dùng chung Pi lẫn Server
├── pi/              # Code chạy trên Raspberry Pi
├── server/          # Code chạy trên PC (FastAPI + AI + IoT manager)
├── templates/poses/ # File JSON pose mẫu (3 pose ban đầu)
├── tools/           # Script tiện ích (tạo template, mock server, ...)
├── config/          # config.yaml — mọi thông số cấu hình ở đây
├── data/            # Ảnh, database, log (không commit lên Git)
├── tests/           # Smoke test và integration test
└── docs/            # Tài liệu
```

## Khởi động nhanh (trên PC / server SSH)

```bash
# 1. Cài thư viện
pip install -e .
pip install fastapi uvicorn websockets paho-mqtt mediapipe opencv-python pydantic pyyaml aiosqlite

# 2. Sửa IP trong config/config.yaml nếu cần

# 3. Chạy server
python server/main.py

# 4. (Trên Pi) Chạy Pi client
python pi/main.py
```

## Quy tắc chung

- **Mọi thông số cấu hình** → `config/config.yaml`, không hardcode trong code.
- **Mọi format JSON** → `shared/schemas.py`, không tự định nghĩa riêng.
- **Mọi tên topic MQTT** → `shared/mqtt_topics.py`.
- `data/` không commit lên Git (đã có trong .gitignore).
````
