This file is a merged representation of a subset of the codebase, containing files not matching ignore patterns, combined into a single document by Repomix.

# File Summary

## Purpose
This file contains a packed representation of a subset of the repository's contents that is considered the most important context.
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
- Files matching these patterns are excluded: **/repomix-output*.md, photo_effects_pack/**
- Files matching patterns in .gitignore are excluded
- Files matching default ignore patterns are excluded
- Files are sorted by Git change count (files with more changes are at the bottom)

# Directory Structure
````
AI/
  api/
    gesture_recognizer.task
    README.md
    requirements.txt
    server.py
  models/
    face_landmarker.task
    gesture_recognizer.task
  photos/
    photo_20261117_194249_658943.jpg
    photo_20261117_194323_710750.jpg
    photo_20261117_194347_792793.jpg
  prediction_api/
    app.py
    README.md
    requirements.txt
  gesture_photobooth_demo_2.py
  gesture_photobooth_demo.py
  requirements.txt
  yolo11n-pose.pt
Cuoi_ki/
  Raspberry_Pi/
    config/
      config.yaml
    pi/
      __init__.py
      hardware.py
      main.py
    shared/
      __init__.py
      config.py
      logging_config.py
      mqtt_topics.py
      schemas.py
    tools/
      mock_pi_hardware.py
    .gitignore
    pyproject.toml
    README.md
  Server_Module/
    assets/
      photo_effects/
        face_overlays/
          cat_ears/
            metadata.json
            overlay.png
          crown/
            metadata.json
            overlay.png
          glasses/
            metadata.json
            overlay.png
          halo/
            metadata.json
            overlay.png
          .gitkeep
        filters/
          .gitkeep
        frames/
          classic_strip_4.png
          grid_2x2_retro.png
          pastel_pink_strip_4.png
        manifest.json
        README.md
    config/
      config.yaml
    photobooth_server.egg-info/
      dependency_links.txt
      PKG-INFO
      requires.txt
      SOURCES.txt
      top_level.txt
    server/
      static/
        admin.html
      __init__.py
      ai.py
      face_overlays.py
      gesture_control.py
      image_processing.py
      iot.py
      main.py
      photo_layout.py
      pose_matching.py
      storage.py
    shared/
      __init__.py
      config.py
      logging_config.py
      mqtt_topics.py
      schemas.py
    templates/
      poses/
        README.md
    tests/
      test_face_overlays.py
      test_gesture_control.py
      test_image_processing.py
      test_photo_layout.py
      test_pose_matching.py
      test_schemas.py
      test_storage.py
    tools/
      mock_pi_mqtt.py
      mock_server.py
    .gitignore
    pyproject.toml
    README.md
  .gitignore
  Raspberry_Pi.zip
  README.md
.gitignore
````

# Files

## File: AI/api/README.md
````markdown
# API nhận diện cử chỉ

Chép toàn bộ thư mục này sang laptop có IP `10.190.22.213`. Thư mục đã có
file model `gesture_recognizer.task`.

Mở terminal trong thư mục đã chép. Ví dụ dùng Python 3.11 trên Linux hoặc macOS:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python server.py
```

Trên Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe server.py
```

Giữ terminal chạy và cho phép Raspberry Pi truy cập cổng TCP 8080 qua tường
lửa laptop. Dùng mạng LAN tin cậy vì API nhận ảnh camera qua HTTP. Từ Pi,
kiểm tra kết nối:

```bash
curl --max-time 3 http://10.190.22.213:8080/health
```

Kết quả mong đợi là `{"status":"ok"}`. Sau đó chạy booth và nhận quyền trên
trang khách hoặc kiosk để Pi bắt đầu gửi ảnh. Mỗi request `/recognize` và kết
quả dự đoán (nhãn, confidence, số tay, thời gian xử lý) sẽ được in ở terminal
đang chạy server; ảnh và tọa độ landmark không được ghi vào log.
````

## File: AI/api/requirements.txt
````
Flask>=3.1,<4
waitress>=3,<4
mediapipe>=0.10.18,<0.11
opencv-python>=4.8,<5
````

## File: AI/api/server.py
````python
"""Run MediaPipe gesture inference on a machine on the booth's LAN."""
from pathlib import Path
from threading import Lock
import time

import cv2
from flask import Flask, request
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import numpy as np
from waitress import serve


def create_app():
    app = Flask(__name__)
    app.logger.setLevel('INFO')
    app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024
    model = Path(__file__).with_name('gesture_recognizer.task')
    recognizer = vision.GestureRecognizer.create_from_options(
        vision.GestureRecognizerOptions(
            base_options=python.BaseOptions(model_asset_path=str(model)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
        )
    )
    lock = Lock()
    timestamp = 0

    @app.get('/health')
    def health():
        return {'status': 'ok'}

    @app.post('/recognize')
    def recognize():
        nonlocal timestamp
        started = time.perf_counter()
        app.logger.info(
            'recognize_request client=%s content_length=%s',
            request.remote_addr,
            request.content_length,
        )
        body = request.get_data()
        if not body:
            app.logger.warning('recognize_rejected client=%s reason=empty_body', request.remote_addr)
            return {'error': 'Expected a JPEG image'}, 400
        frame = cv2.imdecode(np.frombuffer(body, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            app.logger.warning('recognize_rejected client=%s reason=invalid_image', request.remote_addr)
            return {'error': 'Expected a JPEG image'}, 400
        image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
        )
        with lock:
            timestamp = max(timestamp + 1, time.monotonic_ns() // 1_000_000)
            result = recognizer.recognize_for_video(image, timestamp)
        hands = []
        for index, landmarks in enumerate(result.hand_landmarks):
            categories = result.gestures[index]
            category = categories[0] if categories else None
            world = result.hand_world_landmarks[index] if result.hand_world_landmarks else []
            hands.append({
                'pts': [[p.x, p.y] for p in landmarks],
                'world': [[p.x, p.y, p.z] for p in world] or None,
                'label': category.category_name if category else None,
                'score': category.score if category else 0,
            })
        prediction_summary = [
            {'label': hand['label'], 'score': round(float(hand['score']), 4)}
            for hand in hands
        ]
        app.logger.info(
            'recognize_result client=%s hands=%d predictions=%s duration_ms=%.1f',
            request.remote_addr,
            len(hands),
            prediction_summary,
            (time.perf_counter() - started) * 1000,
        )
        return {'hands': hands}

    return app


if __name__ == '__main__':
    app = create_app()
    print('Gesture API: port 8080 (/health, /recognize)', flush=True)
    serve(app, host='0.0.0.0', port=8080)
````

## File: AI/prediction_api/app.py
````python
"""HTTP API for MediaPipe gesture prediction."""

from contextlib import asynccontextmanager
import os
from pathlib import Path
from threading import Lock
from typing import Optional

import cv2
import mediapipe as mp
import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision


ROOT_DIR = Path(__file__).resolve().parent.parent
MODEL_PATH = Path(
    os.environ.get(
        "GESTURE_MODEL_PATH",
        str(ROOT_DIR / "models" / "gesture_recognizer.task"),
    )
).expanduser()
MAX_IMAGE_BYTES = 10 * 1024 * 1024

_recognizer: Optional[vision.GestureRecognizer] = None
_recognizer_lock = Lock()


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _recognizer

    if not MODEL_PATH.is_file():
        raise RuntimeError(
            "Gesture model not found at "
            f"{MODEL_PATH}. Set GESTURE_MODEL_PATH to the model file."
        )

    options = vision.GestureRecognizerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(MODEL_PATH)),
        running_mode=vision.RunningMode.IMAGE,
        num_hands=4,
    )
    _recognizer = vision.GestureRecognizer.create_from_options(options)
    try:
        yield
    finally:
        _recognizer.close()
        _recognizer = None


app = FastAPI(
    title="Gesture Prediction API",
    description="Predict hand gestures from an uploaded JPEG or PNG image.",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": _recognizer is not None}


def _predict(image_bytes: bytes) -> dict:
    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    image_bgr = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise HTTPException(
            status_code=400,
            detail="Could not decode image. Send a valid JPEG or PNG image.",
        )

    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_rgb)

    if _recognizer is None:
        raise HTTPException(status_code=503, detail="Gesture model is not loaded.")

    with _recognizer_lock:
        result = _recognizer.recognize(mp_image)

    predictions = []
    for index, _ in enumerate(result.hand_landmarks):
        categories = result.gestures[index] if index < len(result.gestures) else []
        handedness = (
            result.handedness[index][0].category_name
            if index < len(result.handedness) and result.handedness[index]
            else None
        )
        predictions.append(
            {
                "hand_index": index,
                "gesture": categories[0].category_name if categories else None,
                "score": float(categories[0].score) if categories else None,
                "handedness": handedness,
            }
        )

    return {"hand_count": len(predictions), "predictions": predictions}


@app.post("/predict")
async def predict(request: Request):
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(
            status_code=415,
            detail="Content-Type must be image/jpeg or image/png.",
        )

    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > MAX_IMAGE_BYTES:
                raise HTTPException(status_code=413, detail="Image exceeds the 10 MB limit.")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid Content-Length header.") from exc

    image = bytearray()
    async for chunk in request.stream():
        image.extend(chunk)
        if len(image) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="Image exceeds the 10 MB limit.")

    image_bytes = bytes(image)
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Image body is empty.")

    return await run_in_threadpool(_predict, image_bytes)
````

## File: AI/prediction_api/README.md
````markdown
# Gesture Prediction API

This folder runs the MediaPipe gesture model as an HTTP service. Run it on the
computer that has the model; the Raspberry Pi sends images to that computer.

## 1. Run the server on the PC

Open PowerShell on the PC that contains this project, then run:

```powershell
cd D:\AI_ALL\IOT\AI\prediction_api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

Keep this terminal open while using the API. By default, it uses
`..\models\gesture_recognizer.task` from this project. To use a different
model, set `GESTURE_MODEL_PATH` to its full path before starting Uvicorn.

Find the PC's LAN IPv4 address by running `ipconfig` and looking for the
active adapter's IPv4 address (for example, `192.168.1.100`). On the PC, open
`http://127.0.0.1:8000/health`; the response should contain
`"model_loaded": true`.

The PC and Raspberry Pi must be on a network that can reach each other. Allow
inbound TCP port 8000 in the PC firewall if the Pi cannot connect.

## 2. Call the API from Raspberry Pi

The Pi only needs to send an image; it does not need the AI model or the API
dependencies. On Raspberry Pi OS, install the HTTP client:

```bash
sudo apt update
sudo apt install -y python3-requests
```

For a Raspberry Pi camera, capture an image and send it to the PC (replace the
IP address with the PC's LAN IPv4 address):

```python
import subprocess
import requests

server_url = "http://192.168.1.100:8000"
image_path = "/tmp/hand.jpg"

subprocess.run(
    ["rpicam-still", "--nopreview", "--timeout", "1000", "--output", image_path],
    check=True,
)

with open(image_path, "rb") as image_file:
    response = requests.post(
        f"{server_url}/predict",
        data=image_file,
        headers={"Content-Type": "image/jpeg"},
        timeout=30,
    )
response.raise_for_status()
prediction = response.json()
print(prediction)
```

You can also skip the camera capture and set `image_path` to an existing
JPEG/PNG file. The API accepts images up to 10 MB. Example response:

```json
{
  "hand_count": 1,
  "predictions": [
    {
      "hand_index": 0,
      "gesture": "Open_Palm",
      "score": 0.98,
      "handedness": "Right"
    }
  ]
}
```

If no hand is detected, `hand_count` is `0` and `predictions` is an empty
array. Keep the service on a trusted network; this example API has no
authentication.
````

## File: AI/prediction_api/requirements.txt
````
fastapi
uvicorn[standard]
numpy
opencv-python-headless
mediapipe
````

## File: AI/gesture_photobooth_demo_2.py
````python
#!/usr/bin/env python3
"""
Gesture Photobooth - DEMO chay tren PC (webcam laptop)
=====================================================
Muc dich: xem truoc toan bo luong AI + Photobooth truoc khi tach thanh
Raspberry Pi (chi stream camera) <-> PC Server (AI + Engine).

Chuc nang:
  - MediaPipe Gesture Recognizer: Open_Palm / Thumb_Up / Victory / Pointing_Up / Closed_Fist
  - Pinch-zoom (ngon giua/ap ut/ut co lai, ngon cai va tro tao pinch)
               anh xa tuyet doi (log) + One Euro Filter + hysteresis
  - YOLO11n-pose + ByteTrack: nhan nguoi, giu ID, chon 1 controller (tuy chon)
  - State machine: IDLE -> READY -> COUNTDOWN -> CAPTURING -> RESULT
  - Debounce: confidence, giu N frame, cooldown, release-to-rearm
  - Filter OpenCV don gian, luu anh vao thu muc photos/

Cu chi:
  Open_Palm   (IDLE)      : bat dau, khoa nguoi dieu khien
  Thumb_Up    (READY)     : chup (dem 3-2-1)
  Victory     (READY)     : filter tiep theo
  Pointing_Up (READY)     : filter truoc do
  Closed_Fist (COUNTDOWN) : huy dem nguoc
  Pinch-zoom  (READY)     : cuon ngon giua/ap ut/ut, mo/khep ngon cai - ngon tro
                            de zoom 1.0x -> 2.5x

Phim: q = thoat, r = reset controller
"""
import argparse
import math
import os
import sys
import time
import urllib.request
from datetime import datetime

import cv2
import numpy as np

# --------------------------------------------------------------------------
# Cau hinh
# --------------------------------------------------------------------------
MODEL_URLS = [
    "https://storage.googleapis.com/mediapipe-tasks/gesture_recognizer/gesture_recognizer.task",
    "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task",
]
MODEL_PATH = os.path.join("models", "gesture_recognizer.task")
PHOTO_DIR = "photos"

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12), (9, 13), (13, 14), (14, 15),
    (15, 16), (13, 17), (17, 18), (18, 19), (19, 20), (0, 17),
]

ZOOM_ENTER_FRAMES = 3   # so frame giu tu the zoom truoc khi bat dau
ZOOM_GRACE_FRAMES = 3   # so frame cho phep rot tu the ma khong tha zoom

IDLE, READY, COUNTDOWN, CAPTURING, RESULT = "IDLE", "READY", "COUNTDOWN", "CAPTURING", "RESULT"


# --------------------------------------------------------------------------
# Tien ich
# --------------------------------------------------------------------------
def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def put(img, text, org, scale=0.6, color=(255, 255, 255), thick=1):
    """Ve chu co vien den (cv2.putText khong ho tro tieng Viet co dau)."""
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thick + 2, cv2.LINE_AA)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)


def ensure_model():
    if os.path.exists(MODEL_PATH):
        return MODEL_PATH
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    for url in MODEL_URLS:
        try:
            print(f"[INFO] Dang tai model: {url}")
            urllib.request.urlretrieve(url, MODEL_PATH)
            print(f"[INFO] Da luu: {MODEL_PATH}")
            return MODEL_PATH
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] Tai that bai ({e}), thu URL tiep theo...")
    sys.exit("Khong tai duoc model. Hay tai thu cong gesture_recognizer.task vao thu muc models/")


# --------------------------------------------------------------------------
# Filter + Zoom (Photobooth Engine)
# --------------------------------------------------------------------------
def f_none(img):
    return img


def f_gray(img):
    return cv2.cvtColor(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)


def f_sepia(img):
    k = np.array([[0.272, 0.534, 0.131],
                  [0.349, 0.686, 0.168],
                  [0.393, 0.769, 0.189]], dtype=np.float32)  # thu tu BGR
    return cv2.transform(img, k)


def f_negative(img):
    return 255 - img


def f_cartoon(img):
    gray = cv2.medianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), 7)
    edges = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 9, 7)
    color = cv2.bilateralFilter(img, 9, 75, 75)
    return cv2.bitwise_and(color, cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR))


def f_warm(img):
    out = img.astype(np.int16)
    out[:, :, 2] += 35   # R
    out[:, :, 0] -= 20   # B
    return np.clip(out, 0, 255).astype(np.uint8)


def f_pixel(img):
    h, w = img.shape[:2]
    small = cv2.resize(img, (max(w // 24, 1), max(h // 24, 1)), interpolation=cv2.INTER_LINEAR)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)


FILTERS = [("Original", f_none), ("Gray", f_gray), ("Sepia", f_sepia), ("Warm", f_warm),
           ("Negative", f_negative), ("Cartoon", f_cartoon), ("Pixel", f_pixel)]


def apply_zoom(img, z):
    if z <= 1.001:
        return img
    h, w = img.shape[:2]
    nw, nh = int(w / z), int(h / z)
    x0, y0 = (w - nw) // 2, (h - nh) // 2
    return cv2.resize(img[y0:y0 + nh, x0:x0 + nw], (w, h), interpolation=cv2.INTER_LINEAR)


# --------------------------------------------------------------------------
# Gesture logic
# --------------------------------------------------------------------------
class GestureDebouncer:
    """Confidence + giu N frame + cooldown + release-to-rearm.
    Giu 1 cu chi lien tuc chi phat ra DUNG 1 su kien."""

    def __init__(self, hold_frames=6, min_score=0.6, cooldown=0.8, lost_frames=5):
        self.hold_frames, self.min_score = hold_frames, min_score
        self.cooldown, self.lost_frames = cooldown, lost_frames
        self.cand, self.count, self.missing = None, 0, 0
        self.armed, self.last_fire = True, 0.0

    def update(self, label, score, now):
        valid = label not in (None, "None") and score >= self.min_score
        if not valid:
            self.missing += 1
            if self.missing >= self.lost_frames:   # tha tay ra -> cho phep ban lai
                self.cand, self.count, self.armed = None, 0, True
            return None
        self.missing = 0
        if label != self.cand:
            self.cand, self.count, self.armed = label, 1, True
            return None
        self.count += 1
        if self.armed and self.count >= self.hold_frames and now - self.last_fire >= self.cooldown:
            self.armed, self.last_fire = False, now
            return label
        return None

    def reset(self):
        self.cand, self.count, self.missing, self.armed = None, 0, 0, True


def pinch_ratio(pts, world=None):
    """Khoang cach ngon cai(4) - ngon tro(8) / co ban tay (0 -> 9).
    Uu tien toa do 3D 'world' (met) cua MediaPipe: khong bi sai lech khi
    xoay/nghieng tay hoac tay xa-gan camera. Fallback ve 2D."""
    if world is not None:
        d = lambda i, j: math.dist(world[i], world[j])
        return d(4, 8) / max(d(0, 9), 1e-6)
    return dist(pts[4], pts[8]) / max(dist(pts[0], pts[9]), 1e-6)


def zoom_pose_info(pts, engaged=False):
    """Tu the zoom = 3 ngon cuoi co lai + ngon cai & ngon tro DUOI RA (mo hoac cham nhau).
    Bat buoc ngon tro phai duoi ra de khong nham voi Thumb_Up / Closed_Fist.
    engaged=True -> nguong long hon (hysteresis) de khong bi rot tu the khi dang zoom."""
    wrist = pts[0]
    size = max(dist(pts[0], pts[9]), 1e-6)
    folded = all(dist(pts[tip], wrist) < dist(pts[pip], wrist)
                 for tip, pip in ((12, 10), (16, 14), (20, 18)))
    thumb_out = dist(pts[4], pts[9]) / size > (0.50 if engaged else 0.65)
    index_out = dist(pts[8], wrist) > (0.95 if engaged else 1.05) * dist(pts[5], wrist)
    return folded and thumb_out and index_out, folded, thumb_out, index_out


class OneEuro:
    """One Euro Filter: dung yen -> muot het rung, chuyen dong nhanh -> gan nhu khong tre."""

    def __init__(self, min_cutoff=1.0, beta=5.0, d_cutoff=1.0):
        self.min_cutoff, self.beta, self.d_cutoff = min_cutoff, beta, d_cutoff
        self.x, self.dx = None, 0.0

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x, dt):
        if self.x is None:
            self.x, self.dx = x, 0.0
            return x
        dt = max(dt, 1e-3)
        self.dx += self._alpha(self.d_cutoff, dt) * ((x - self.x) / dt - self.dx)
        cutoff = self.min_cutoff + self.beta * abs(self.dx)
        self.x += self._alpha(cutoff, dt) * (x - self.x)
        return self.x

    def reset(self):
        self.x, self.dx = None, 0.0


class ZoomController:
    """Anh xa TUYET DOI: do mo ngon cai - ngon tro  ->  muc zoom.
      khep sat (pinch)  = zmin (1.0x, thu nho)
      mo rong het co    = zmax (2.5x, phong to)
    - Zoom theo thang log => cung do dich ngon tay cho cam giac zoom deu.
    - OneEuro loc rung, gioi han toc do (max_speed) de vao tu the khong bi giat.
    - Khoang ratio [lo, hi] tu mo rong theo tay nguoi dung (calibration tu dong)."""

    def __init__(self, zmin=1.0, zmax=2.5, r_lo=0.18, r_hi=1.05,
                 max_speed=5.0, edge=0.04):
        self.zmin, self.zmax = zmin, zmax
        self.lo, self.hi = r_lo, r_hi
        self.max_speed, self.edge = max_speed, edge
        self.filter = OneEuro()
        self.zoom = self.target = zmin

    def update(self, ratio, dt):
        dt = min(max(dt, 1e-3), 0.1)
        f = self.filter(ratio, dt)
        self.lo = max(0.08, min(self.lo, f))      # chi mo rong, khong thu hep
        self.hi = min(1.60, max(self.hi, f))
        t = (f - self.lo) / max(self.hi - self.lo, 1e-6)
        t = min(max((t - self.edge) / (1.0 - 2.0 * self.edge), 0.0), 1.0)  # cham dau/cuoi la dat min/max
        self.target = self.zmin * (self.zmax / self.zmin) ** t
        cur, tgt = math.log(self.zoom), math.log(self.target)
        step = self.max_speed * dt
        cur += max(-step, min(step, tgt - cur))
        self.zoom = math.exp(cur)

    def release(self):
        self.filter.reset()


# --------------------------------------------------------------------------
# Person detection + controller selection
# --------------------------------------------------------------------------
class PersonDetector:
    def __init__(self, model_name, imgsz=640, device=None):
        from ultralytics import YOLO  # import tre de demo chay duoc ca khi khong cai ultralytics
        self.model = YOLO(model_name)
        self.imgsz, self.device = imgsz, device

    def detect(self, frame):
        kw = dict(persist=True, classes=[0], imgsz=self.imgsz, conf=0.4, verbose=False,
                  tracker="bytetrack.yaml")
        if self.device:
            kw["device"] = self.device
        res = self.model.track(frame, **kw)[0]
        persons = []
        if res.boxes is None or len(res.boxes) == 0:
            return persons
        xyxy = res.boxes.xyxy.cpu().numpy()
        ids = res.boxes.id.int().cpu().tolist() if res.boxes.id is not None else [None] * len(xyxy)
        kxy = res.keypoints.xy.cpu().numpy() if res.keypoints is not None else None
        kc = (res.keypoints.conf.cpu().numpy()
              if res.keypoints is not None and res.keypoints.conf is not None else None)
        for i, (box, pid) in enumerate(zip(xyxy, ids)):
            wrists = []
            if kxy is not None and len(kxy) > i:
                for k in (9, 10):  # co tay trai / phai (COCO)
                    x, y = kxy[i][k]
                    c = float(kc[i][k]) if kc is not None else 1.0
                    wrists.append((float(x), float(y), c))
            persons.append(dict(id=int(pid) if pid is not None else None,
                                box=tuple(float(v) for v in box), wrists=wrists))
        return persons


def assign_owner(wrist_xy, persons):
    """Ban tay thuoc nguoi nao: co tay nam trong bbox (mo rong) va gan keypoint co tay nhat."""
    best, best_d = None, 1e12
    for p in persons:
        x1, y1, x2, y2 = p["box"]
        m = 0.15 * (x2 - x1)
        if not (x1 - m <= wrist_xy[0] <= x2 + m and y1 - m <= wrist_xy[1] <= y2 + m):
            continue
        ds = [dist(wrist_xy, (x, y)) for x, y, c in p["wrists"] if c > 0.3]
        d = min(ds) if ds else dist(wrist_xy, ((x1 + x2) / 2, (y1 + y2) / 2)) * 2
        if d < best_d:
            best, best_d = p["id"], d
    return best


class ControllerManager:
    def __init__(self, release_after=2.0):
        self.id, self.last_seen, self.release_after = None, 0.0, release_after

    def update(self, present_ids, now):
        if self.id is None:
            return
        if self.id in present_ids:
            self.last_seen = now
        elif now - self.last_seen > self.release_after:
            self.id = None

    def lock(self, pid, now):
        self.id, self.last_seen = pid, now


# --------------------------------------------------------------------------
# Photobooth state machine
# --------------------------------------------------------------------------
class Photobooth:
    def __init__(self, countdown_s=3, result_s=4):
        self.state, self.filter_idx = IDLE, 0
        self.countdown_s, self.result_s = countdown_s, result_s
        self.countdown_end, self.result_until = 0.0, 0.0
        self.result_img, self.result_path = None, ""

    def to_idle(self):
        self.state = IDLE

    def on_gesture(self, g, now):
        """AI chi bao cu chi; Booth moi la noi xac thuc va doi trang thai."""
        if self.state == IDLE and g == "Open_Palm":
            self.state = READY
        elif self.state == READY:
            if g == "Thumb_Up":
                self.state, self.countdown_end = COUNTDOWN, now + self.countdown_s
            elif g == "Victory":
                self.filter_idx = (self.filter_idx + 1) % len(FILTERS)
            elif g == "Pointing_Up":
                self.filter_idx = (self.filter_idx - 1) % len(FILTERS)
        elif self.state == COUNTDOWN and g == "Closed_Fist":
            self.state = READY  # chi huy duoc khi dang COUNTDOWN
        elif self.state == RESULT:
            if g == "Thumb_Up":
                self.state, self.countdown_end = COUNTDOWN, now + self.countdown_s
            elif g == "Closed_Fist":
                self.state = READY

    def tick(self, now, clean_frame):
        if self.state == COUNTDOWN and now >= self.countdown_end:
            self.state = CAPTURING
            os.makedirs(PHOTO_DIR, exist_ok=True)
            self.result_path = os.path.join(
                PHOTO_DIR, f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg")
            if not cv2.imwrite(self.result_path, clean_frame):
                raise OSError(f"Could not save captured photo to {self.result_path}")
            self.result_img = clean_frame.copy()
            self.result_until = now + self.result_s
            self.state = RESULT
            print(f"[CAPTURE] Da luu {self.result_path}")
        elif self.state == RESULT and now >= self.result_until:
            self.state = READY

    def render(self, view, zoom, now, zoom_active=False, zoom_target=1.0):
        out = (self.result_img if self.state == RESULT and self.result_img is not None else view).copy()
        h, w = out.shape[:2]
        put(out, f"State: {self.state}", (12, 28), 0.7, (0, 255, 255), 2)
        put(out, f"Filter: {FILTERS[self.filter_idx][0]}   Zoom: {zoom:.2f}x", (12, 58), 0.6)
        if self.state == IDLE:
            put(out, "Show OPEN PALM to start", (w // 2 - 170, h // 2), 0.9, (0, 255, 0), 2)
            put(out, "Hold one open palm to select the controller", (12, h - 20), 0.55)
        elif self.state == COUNTDOWN:
            n = max(1, math.ceil(self.countdown_end - now))
            put(out, str(n), (w // 2 - 40, h // 2 + 40), 4.0, (0, 0, 255), 8)
            put(out, "FIST = cancel", (w // 2 - 80, h - 30), 0.8, (255, 255, 255), 2)
        elif self.state == READY:
            put(out, "Thumb Up: capture | Victory: next filter | Pointing Up: previous filter",
                (12, h - 42), 0.5)
            put(out, "Zoom: curl middle/ring/pinky; open thumb-index = zoom in, pinch = zoom out",
                (12, h - 20), 0.5)
            bx, by0, by1 = w - 40, 90, h - 90          # thanh zoom ben phai
            cv2.rectangle(out, (bx, by0), (bx + 14, by1), (0, 0, 0), -1)
            cv2.rectangle(out, (bx, by0), (bx + 14, by1), (255, 255, 255), 1)

            def zy(z):
                f = math.log(max(z, 1.0)) / math.log(2.5)
                return int(by1 - min(max(f, 0.0), 1.0) * (by1 - by0))
            cv2.rectangle(out, (bx + 1, zy(zoom)), (bx + 13, by1 - 1),
                          (0, 255, 0) if zoom_active else (160, 160, 160), -1)
            if zoom_active:
                cv2.line(out, (bx - 8, zy(zoom_target)), (bx + 22, zy(zoom_target)), (0, 200, 255), 2)
        elif self.state == RESULT:
            put(out, f"Saved: {self.result_path}", (12, h - 20), 0.6, (0, 255, 0), 2)
            put(out, "Thumb Up: retake | Closed Fist: back to READY", (12, h - 44), 0.5)
        return out


# --------------------------------------------------------------------------
# Debug drawing
# --------------------------------------------------------------------------
def draw_debug(frame, persons, hands, ctrl_id, chosen, info_lines):
    dbg = frame.copy()
    for p in persons:
        x1, y1, x2, y2 = map(int, p["box"])
        is_ctrl = ctrl_id is not None and ctrl_id == p["id"]
        cv2.rectangle(dbg, (x1, y1), (x2, y2), (0, 255, 0) if is_ctrl else (140, 140, 140), 2)
        pid_label = p["id"] if p["id"] is not None else "?"
        put(dbg, f"ID {pid_label}" + (" [CONTROLLER]" if is_ctrl else ""),
            (x1, max(y1 - 8, 16)), 0.55,
            (0, 255, 0) if is_ctrl else (200, 200, 200))
    for hnd in hands:
        pts = [(int(x), int(y)) for x, y in hnd["pts"]]
        color = (0, 200, 255) if hnd is chosen else (255, 120, 0)
        for a, b in HAND_CONNECTIONS:
            cv2.line(dbg, pts[a], pts[b], color, 2)
        for pt in pts:
            cv2.circle(dbg, pt, 3, (255, 255, 255), -1)
        cv2.line(dbg, pts[4], pts[8], (0, 0, 255), 2)  # doan do khoang cach pinch
        put(dbg, f"{hnd['label']} {hnd['score']:.2f} ({hnd['side']}) owner={hnd['owner']}",
            (pts[0][0] - 40, pts[0][1] + 25), 0.5, color)
    for i, line in enumerate(info_lines):
        put(dbg, line, (10, 24 + 22 * i), 0.55)
    return dbg


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def parse_args():
    ap = argparse.ArgumentParser(description="Gesture Photobooth demo (webcam PC)")
    ap.add_argument("--camera", type=int, default=0, help="chi so camera (mac dinh 0)")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--no-yolo", action="store_true", help="tat nhan nguoi, chi dung MediaPipe")
    ap.add_argument("--yolo-model", default="yolo11n-pose.pt")
    ap.add_argument("--yolo-every", type=int, default=2, help="chay YOLO moi N frame")
    ap.add_argument("--device", default=None, help="vd: cpu, cuda:0, mps")
    ap.add_argument("--hold-frames", type=int, default=6, help="so frame giu cu chi de xac nhan")
    ap.add_argument("--min-score", type=float, default=0.6)
    return ap.parse_args()


def main():
    args = parse_args()

    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    options = vision.GestureRecognizerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=ensure_model()),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=4,
        min_hand_detection_confidence=0.5,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    recognizer = vision.GestureRecognizer.create_from_options(options)

    detector = None
    if not args.no_yolo:
        try:
            detector = PersonDetector(args.yolo_model, device=args.device)
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] Khong khoi tao duoc YOLO ({e}). Chay che do --no-yolo.")

    cap = cv2.VideoCapture(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    if not cap.isOpened():
        sys.exit(f"Khong mo duoc camera {args.camera}")

    booth = Photobooth()
    deb = GestureDebouncer(hold_frames=args.hold_frames, min_score=args.min_score)
    zoom = ZoomController()
    ctrl = ControllerManager()

    persons, frame_idx, last_ts = [], 0, 0
    zoom_count, zoom_miss, zoom_engaged = 0, 0, False
    fps, t_prev = 0.0, time.monotonic()
    last_fired = ""
    selection_owner = None

    while True:
        ok, frame = cap.read()
        if not ok:
            print("[ERROR] Doc camera that bai")
            break
        frame = cv2.flip(frame, 1)  # che do guong
        now = time.monotonic()
        h, w = frame.shape[:2]

        # ---- 1. Person detection + tracking ----
        if detector is not None and frame_idx % max(args.yolo_every, 1) == 0:
            persons = detector.detect(frame)

        # ---- 2. Hand + gesture ----
        ts = max(int(now * 1000), last_ts + 1)
        last_ts = ts
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        res = recognizer.recognize_for_video(mp_img, ts)

        hands = []
        for i, lms in enumerate(res.hand_landmarks):
            pts = [(lm.x * w, lm.y * h) for lm in lms]
            if res.gestures and i < len(res.gestures) and res.gestures[i]:
                g = res.gestures[i][0]
                label, score = g.category_name, float(g.score)
            else:
                label, score = "None", 0.0
            side = res.handedness[i][0].category_name if res.handedness else "?"
            owner = assign_owner(pts[0], persons) if detector is not None else "solo"
            world = None
            wl = getattr(res, "hand_world_landmarks", None)
            if wl and i < len(wl) and wl[i]:
                world = [(lm.x, lm.y, lm.z) for lm in wl[i]]
            hands.append(dict(pts=pts, world=world, label=label, score=score, side=side, owner=owner))

        # ---- 3. Chon controller ----
        if detector is not None:
            present = {p["id"] for p in persons}
        else:
            present = {"solo"} if hands else set()

        ctrl.update(present, now)
        if ctrl.id is None and booth.state != IDLE:
            booth.to_idle()  # controller roi di -> giai phong quyen

        if ctrl.id is None:
            candidates = [hd for hd in hands
                          if hd["label"] == "Open_Palm" and hd["score"] >= 0.7
                          and hd["owner"] is not None]
            chosen = max(candidates, key=lambda hd: hd["score"]) if candidates else None
            owner = chosen["owner"] if chosen is not None else None
            if owner != selection_owner:
                deb.reset()
                selection_owner = owner
        else:
            mine = [hd for hd in hands if hd["owner"] == ctrl.id]
            chosen = max(mine, key=lambda hd: hd["score"]) if mine else None
            selection_owner = None

        # ---- 4. Gesture -> action ----
        fired, zoom_active, ratio = None, False, 0.0
        pose_dbg = (False, False, False)
        if chosen is not None:
            in_pose, folded, thumb_out, index_out = zoom_pose_info(chosen["pts"], zoom_engaged)
            ratio = pinch_ratio(chosen["pts"], chosen.get("world"))
            pose_dbg = (folded, thumb_out, index_out)
            if in_pose:
                zoom_miss = 0
                if booth.state == READY:
                    zoom_count += 1
                    if zoom_count >= ZOOM_ENTER_FRAMES:
                        zoom_active = zoom_engaged = True
                        zoom.update(ratio, now - t_prev)
                else:
                    zoom_count, zoom_engaged = 0, False
                    zoom.release()
                deb.update(None, 0.0, now)
            else:
                zoom_miss += 1
                if zoom_miss > ZOOM_GRACE_FRAMES:   # mat tu the that su -> tha zoom
                    zoom_count, zoom_engaged = 0, False
                    zoom.release()
                    fired = deb.update(chosen["label"], chosen["score"], now)
                else:                               # rot 1-2 frame: giu nguyen zoom
                    deb.update(None, 0.0, now)
        else:
            zoom_miss += 1
            if zoom_miss > ZOOM_GRACE_FRAMES:
                zoom_count, zoom_engaged = 0, False
                zoom.release()
            deb.update(None, 0.0, now)

        if fired:
            last_fired = f"{fired} @ {datetime.now().strftime('%H:%M:%S')}"
            print(f"[GESTURE] {fired} (state={booth.state})")
            if (booth.state == IDLE and fired == "Open_Palm" and chosen is not None
                    and chosen["owner"] is not None):
                ctrl.lock(chosen["owner"], now)
                selection_owner = None
                print(f"[CONTROLLER] Khoa nguoi dieu khien: {ctrl.id}")
            booth.on_gesture(fired, now)

        # ---- 5. Photobooth engine: zoom -> filter -> capture ----
        view = FILTERS[booth.filter_idx][1](apply_zoom(frame, zoom.zoom))
        booth.tick(now, view)
        preview = booth.render(view, zoom.zoom, now, zoom_active, zoom.target)

        # ---- 6. Hien thi ----
        fps = 0.9 * fps + 0.1 / max(now - t_prev, 1e-6)
        t_prev = now
        info = [
            f"FPS: {fps:4.1f}   persons: {len(persons) if detector else 'off'}   hands: {len(hands)}",
            f"Controller: {ctrl.id}   Last event: {last_fired}",
            f"Pinch ratio: {ratio:.2f}   folded={pose_dbg[0]} thumb_out={pose_dbg[1]} "
            f"index_out={pose_dbg[2]}   "
            f"zoom_mode={zoom_active}",
        ]
        cv2.imshow("Photobooth Preview", preview)
        cv2.imshow("AI Debug", draw_debug(frame, persons, hands, ctrl.id, chosen, info))

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord("r"):
            ctrl.id = None
            booth.to_idle()
        frame_idx += 1

    cap.release()
    recognizer.close()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
````

## File: AI/gesture_photobooth_demo.py
````python
#!/usr/bin/env python3
"""
Gesture Photobooth - DEMO chay tren PC (webcam laptop)
=====================================================
Muc dich: xem truoc toan bo luong AI + Photobooth truoc khi tach thanh
Raspberry Pi (chi stream camera) <-> PC Server (AI + Engine).

Chuc nang:
  - MediaPipe Gesture Recognizer: Open_Palm / Thumb_Up / Victory / Pointing_Up / Closed_Fist
  - Pinch-zoom (ngon giua/ap ut/ut co lai, ngon cai va tro tao pinch)
               tu tinh khoang cach ngon cai - ngon tro, EMA + dead-zone
  - YOLO11n-pose + ByteTrack: nhan nguoi, giu ID, chon 1 controller (tuy chon)
  - State machine: IDLE -> READY -> COUNTDOWN -> CAPTURING -> RESULT
  - Debounce: confidence, giu N frame, cooldown, release-to-rearm
  - Filter OpenCV don gian, luu anh vao thu muc photos/

Cu chi:
  Open_Palm   (IDLE)      : bat dau, khoa nguoi dieu khien
  Thumb_Up    (READY)     : chup (dem 3-2-1)
  Victory     (READY)     : filter tiep theo
  Pointing_Up (READY)     : filter truoc do
  Closed_Fist (COUNTDOWN) : huy dem nguoc
  Pinch-zoom  (READY)     : cuon ngon giua/ap ut/ut, mo/khep ngon cai - ngon tro
                            de zoom 1.0x -> 2.5x

Phim: q = thoat, r = reset controller
"""
import argparse
import math
import os
import sys
import time
import urllib.request
from datetime import datetime

import cv2
import numpy as np

# --------------------------------------------------------------------------
# Cau hinh
# --------------------------------------------------------------------------
MODEL_URLS = [
    "https://storage.googleapis.com/mediapipe-tasks/gesture_recognizer/gesture_recognizer.task",
    "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task",
]
MODEL_PATH = os.path.join("models", "gesture_recognizer.task")
PHOTO_DIR = "photos"

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12), (9, 13), (13, 14), (14, 15),
    (15, 16), (13, 17), (17, 18), (18, 19), (19, 20), (0, 17),
]

IDLE, READY, COUNTDOWN, CAPTURING, RESULT = "IDLE", "READY", "COUNTDOWN", "CAPTURING", "RESULT"


# --------------------------------------------------------------------------
# Tien ich
# --------------------------------------------------------------------------
def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def put(img, text, org, scale=0.6, color=(255, 255, 255), thick=1):
    """Ve chu co vien den (cv2.putText khong ho tro tieng Viet co dau)."""
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thick + 2, cv2.LINE_AA)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)


def ensure_model():
    if os.path.exists(MODEL_PATH):
        return MODEL_PATH
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    for url in MODEL_URLS:
        try:
            print(f"[INFO] Dang tai model: {url}")
            urllib.request.urlretrieve(url, MODEL_PATH)
            print(f"[INFO] Da luu: {MODEL_PATH}")
            return MODEL_PATH
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] Tai that bai ({e}), thu URL tiep theo...")
    sys.exit("Khong tai duoc model. Hay tai thu cong gesture_recognizer.task vao thu muc models/")


# --------------------------------------------------------------------------
# Filter + Zoom (Photobooth Engine)
# --------------------------------------------------------------------------
def f_none(img):
    return img


def f_gray(img):
    return cv2.cvtColor(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)


def f_sepia(img):
    k = np.array([[0.272, 0.534, 0.131],
                  [0.349, 0.686, 0.168],
                  [0.393, 0.769, 0.189]], dtype=np.float32)  # thu tu BGR
    return cv2.transform(img, k)


def f_negative(img):
    return 255 - img


def f_cartoon(img):
    gray = cv2.medianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), 7)
    edges = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 9, 7)
    color = cv2.bilateralFilter(img, 9, 75, 75)
    return cv2.bitwise_and(color, cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR))


def f_warm(img):
    out = img.astype(np.int16)
    out[:, :, 2] += 35   # R
    out[:, :, 0] -= 20   # B
    return np.clip(out, 0, 255).astype(np.uint8)


def f_pixel(img):
    h, w = img.shape[:2]
    small = cv2.resize(img, (max(w // 24, 1), max(h // 24, 1)), interpolation=cv2.INTER_LINEAR)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)


FILTERS = [("Original", f_none), ("Gray", f_gray), ("Sepia", f_sepia), ("Warm", f_warm),
           ("Negative", f_negative), ("Cartoon", f_cartoon), ("Pixel", f_pixel)]


def apply_zoom(img, z):
    if z <= 1.001:
        return img
    h, w = img.shape[:2]
    nw, nh = int(w / z), int(h / z)
    x0, y0 = (w - nw) // 2, (h - nh) // 2
    return cv2.resize(img[y0:y0 + nh, x0:x0 + nw], (w, h), interpolation=cv2.INTER_LINEAR)


# --------------------------------------------------------------------------
# Gesture logic
# --------------------------------------------------------------------------
class GestureDebouncer:
    """Confidence + giu N frame + cooldown + release-to-rearm.
    Giu 1 cu chi lien tuc chi phat ra DUNG 1 su kien."""

    def __init__(self, hold_frames=6, min_score=0.6, cooldown=0.8, lost_frames=5):
        self.hold_frames, self.min_score = hold_frames, min_score
        self.cooldown, self.lost_frames = cooldown, lost_frames
        self.cand, self.count, self.missing = None, 0, 0
        self.armed, self.last_fire = True, 0.0

    def update(self, label, score, now):
        valid = label not in (None, "None") and score >= self.min_score
        if not valid:
            self.missing += 1
            if self.missing >= self.lost_frames:   # tha tay ra -> cho phep ban lai
                self.cand, self.count, self.armed = None, 0, True
            return None
        self.missing = 0
        if label != self.cand:
            self.cand, self.count, self.armed = label, 1, True
            return None
        self.count += 1
        if self.armed and self.count >= self.hold_frames and now - self.last_fire >= self.cooldown:
            self.armed, self.last_fire = False, now
            return label
        return None

    def reset(self):
        self.cand, self.count, self.missing, self.armed = None, 0, 0, True


def pinch_ratio(pts):
    """Khoang cach ngon cai(4) - ngon tro(8), chuan hoa theo co tay (0 -> 9)."""
    return dist(pts[4], pts[8]) / max(dist(pts[0], pts[9]), 1e-6)


def zoom_pose_info(pts):
    """Tu the zoom: ba ngon cuoi co lai, ngon cai va ngon tro tao pinch."""
    wrist = pts[0]
    size = max(dist(pts[0], pts[9]), 1e-6)
    folded = all(dist(pts[tip], wrist) < dist(pts[pip], wrist)
                 for tip, pip in ((12, 10), (16, 14), (20, 18)))
    thumb_out = dist(pts[4], pts[9]) / size > 0.8
    index_out = dist(pts[8], wrist) > 0.85 * dist(pts[6], wrist)
    return folded and thumb_out, folded, thumb_out, index_out


class ZoomController:
    def __init__(self, zmin=1.0, zmax=2.5, input_smoothing_s=0.10,
                 response_s=0.08, deadzone=0.015, r_min=0.25, r_max=1.4):
        self.zmin, self.zmax = zmin, zmax
        self.input_smoothing_s, self.response_s = input_smoothing_s, response_s
        self.deadzone = deadzone
        self.r_min, self.r_max = r_min, r_max
        self.zoom, self.ema = 1.0, None
        self.anchor_ratio, self.anchor_zoom = None, None

    def update(self, ratio, dt):
        dt = min(max(dt, 0.0), 0.1)
        if self.ema is None:
            self.ema = ratio
            self.anchor_ratio, self.anchor_zoom = ratio, self.zoom
        elif dt > 0:
            alpha = 1.0 - math.exp(-dt / self.input_smoothing_s)
            self.ema += alpha * (ratio - self.ema)
        sensitivity = (self.zmax - self.zmin) / max(self.r_max - self.r_min, 1e-6)
        target = self.anchor_zoom + (self.ema - self.anchor_ratio) * sensitivity
        target = min(max(target, self.zmin), self.zmax)
        if abs(target - self.zoom) > self.deadzone and dt > 0:
            response = 1.0 - math.exp(-dt / self.response_s)
            self.zoom += response * (target - self.zoom)

    def release(self):
        self.ema, self.anchor_ratio, self.anchor_zoom = None, None, None


# --------------------------------------------------------------------------
# Person detection + controller selection
# --------------------------------------------------------------------------
class PersonDetector:
    def __init__(self, model_name, imgsz=640, device=None):
        from ultralytics import YOLO  # import tre de demo chay duoc ca khi khong cai ultralytics
        self.model = YOLO(model_name)
        self.imgsz, self.device = imgsz, device

    def detect(self, frame):
        kw = dict(persist=True, classes=[0], imgsz=self.imgsz, conf=0.4, verbose=False,
                  tracker="bytetrack.yaml")
        if self.device:
            kw["device"] = self.device
        res = self.model.track(frame, **kw)[0]
        persons = []
        if res.boxes is None or len(res.boxes) == 0:
            return persons
        xyxy = res.boxes.xyxy.cpu().numpy()
        ids = res.boxes.id.int().cpu().tolist() if res.boxes.id is not None else [None] * len(xyxy)
        kxy = res.keypoints.xy.cpu().numpy() if res.keypoints is not None else None
        kc = (res.keypoints.conf.cpu().numpy()
              if res.keypoints is not None and res.keypoints.conf is not None else None)
        for i, (box, pid) in enumerate(zip(xyxy, ids)):
            wrists = []
            if kxy is not None and len(kxy) > i:
                for k in (9, 10):  # co tay trai / phai (COCO)
                    x, y = kxy[i][k]
                    c = float(kc[i][k]) if kc is not None else 1.0
                    wrists.append((float(x), float(y), c))
            persons.append(dict(id=int(pid) if pid is not None else None,
                                box=tuple(float(v) for v in box), wrists=wrists))
        return persons


def assign_owner(wrist_xy, persons):
    """Ban tay thuoc nguoi nao: co tay nam trong bbox (mo rong) va gan keypoint co tay nhat."""
    best, best_d = None, 1e12
    for p in persons:
        x1, y1, x2, y2 = p["box"]
        m = 0.15 * (x2 - x1)
        if not (x1 - m <= wrist_xy[0] <= x2 + m and y1 - m <= wrist_xy[1] <= y2 + m):
            continue
        ds = [dist(wrist_xy, (x, y)) for x, y, c in p["wrists"] if c > 0.3]
        d = min(ds) if ds else dist(wrist_xy, ((x1 + x2) / 2, (y1 + y2) / 2)) * 2
        if d < best_d:
            best, best_d = p["id"], d
    return best


class ControllerManager:
    def __init__(self, release_after=2.0):
        self.id, self.last_seen, self.release_after = None, 0.0, release_after

    def update(self, present_ids, now):
        if self.id is None:
            return
        if self.id in present_ids:
            self.last_seen = now
        elif now - self.last_seen > self.release_after:
            self.id = None

    def lock(self, pid, now):
        self.id, self.last_seen = pid, now


# --------------------------------------------------------------------------
# Photobooth state machine
# --------------------------------------------------------------------------
class Photobooth:
    def __init__(self, countdown_s=3, result_s=4):
        self.state, self.filter_idx = IDLE, 0
        self.countdown_s, self.result_s = countdown_s, result_s
        self.countdown_end, self.result_until = 0.0, 0.0
        self.result_img, self.result_path = None, ""

    def to_idle(self):
        self.state = IDLE

    def on_gesture(self, g, now):
        """AI chi bao cu chi; Booth moi la noi xac thuc va doi trang thai."""
        if self.state == IDLE and g == "Open_Palm":
            self.state = READY
        elif self.state == READY:
            if g == "Thumb_Up":
                self.state, self.countdown_end = COUNTDOWN, now + self.countdown_s
            elif g == "Victory":
                self.filter_idx = (self.filter_idx + 1) % len(FILTERS)
            elif g == "Pointing_Up":
                self.filter_idx = (self.filter_idx - 1) % len(FILTERS)
        elif self.state == COUNTDOWN and g == "Closed_Fist":
            self.state = READY  # chi huy duoc khi dang COUNTDOWN
        elif self.state == RESULT:
            if g == "Thumb_Up":
                self.state, self.countdown_end = COUNTDOWN, now + self.countdown_s
            elif g == "Closed_Fist":
                self.state = READY

    def tick(self, now, clean_frame):
        if self.state == COUNTDOWN and now >= self.countdown_end:
            self.state = CAPTURING
            os.makedirs(PHOTO_DIR, exist_ok=True)
            self.result_path = os.path.join(
                PHOTO_DIR, f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg")
            if not cv2.imwrite(self.result_path, clean_frame):
                raise OSError(f"Could not save captured photo to {self.result_path}")
            self.result_img = clean_frame.copy()
            self.result_until = now + self.result_s
            self.state = RESULT
            print(f"[CAPTURE] Da luu {self.result_path}")
        elif self.state == RESULT and now >= self.result_until:
            self.state = READY

    def render(self, view, zoom, now):
        out = (self.result_img if self.state == RESULT and self.result_img is not None else view).copy()
        h, w = out.shape[:2]
        put(out, f"State: {self.state}", (12, 28), 0.7, (0, 255, 255), 2)
        put(out, f"Filter: {FILTERS[self.filter_idx][0]}   Zoom: {zoom:.2f}x", (12, 58), 0.6)
        if self.state == IDLE:
            put(out, "Show OPEN PALM to start", (w // 2 - 170, h // 2), 0.9, (0, 255, 0), 2)
            put(out, "Hold one open palm to select the controller", (12, h - 20), 0.55)
        elif self.state == COUNTDOWN:
            n = max(1, math.ceil(self.countdown_end - now))
            put(out, str(n), (w // 2 - 40, h // 2 + 40), 4.0, (0, 0, 255), 8)
            put(out, "FIST = cancel", (w // 2 - 80, h - 30), 0.8, (255, 255, 255), 2)
        elif self.state == READY:
            put(out, "Thumb Up: capture | Victory: next filter | Pointing Up: previous filter",
                (12, h - 42), 0.5)
            put(out, "Zoom: curl middle/ring/pinky; pinch thumb and index finger",
                (12, h - 20), 0.5)
        elif self.state == RESULT:
            put(out, f"Saved: {self.result_path}", (12, h - 20), 0.6, (0, 255, 0), 2)
            put(out, "Thumb Up: retake | Closed Fist: back to READY", (12, h - 44), 0.5)
        return out


# --------------------------------------------------------------------------
# Debug drawing
# --------------------------------------------------------------------------
def draw_debug(frame, persons, hands, ctrl_id, chosen, info_lines):
    dbg = frame.copy()
    for p in persons:
        x1, y1, x2, y2 = map(int, p["box"])
        is_ctrl = ctrl_id is not None and ctrl_id == p["id"]
        cv2.rectangle(dbg, (x1, y1), (x2, y2), (0, 255, 0) if is_ctrl else (140, 140, 140), 2)
        pid_label = p["id"] if p["id"] is not None else "?"
        put(dbg, f"ID {pid_label}" + (" [CONTROLLER]" if is_ctrl else ""),
            (x1, max(y1 - 8, 16)), 0.55,
            (0, 255, 0) if is_ctrl else (200, 200, 200))
    for hnd in hands:
        pts = [(int(x), int(y)) for x, y in hnd["pts"]]
        color = (0, 200, 255) if hnd is chosen else (255, 120, 0)
        for a, b in HAND_CONNECTIONS:
            cv2.line(dbg, pts[a], pts[b], color, 2)
        for pt in pts:
            cv2.circle(dbg, pt, 3, (255, 255, 255), -1)
        cv2.line(dbg, pts[4], pts[8], (0, 0, 255), 2)  # doan do khoang cach pinch
        put(dbg, f"{hnd['label']} {hnd['score']:.2f} ({hnd['side']}) owner={hnd['owner']}",
            (pts[0][0] - 40, pts[0][1] + 25), 0.5, color)
    for i, line in enumerate(info_lines):
        put(dbg, line, (10, 24 + 22 * i), 0.55)
    return dbg


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def parse_args():
    ap = argparse.ArgumentParser(description="Gesture Photobooth demo (webcam PC)")
    ap.add_argument("--camera", type=int, default=0, help="chi so camera (mac dinh 0)")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--no-yolo", action="store_true", help="tat nhan nguoi, chi dung MediaPipe")
    ap.add_argument("--yolo-model", default="yolo11n-pose.pt")
    ap.add_argument("--yolo-every", type=int, default=2, help="chay YOLO moi N frame")
    ap.add_argument("--device", default=None, help="vd: cpu, cuda:0, mps")
    ap.add_argument("--hold-frames", type=int, default=6, help="so frame giu cu chi de xac nhan")
    ap.add_argument("--min-score", type=float, default=0.6)
    return ap.parse_args()


def main():
    args = parse_args()

    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    options = vision.GestureRecognizerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=ensure_model()),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=4,
        min_hand_detection_confidence=0.5,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    recognizer = vision.GestureRecognizer.create_from_options(options)

    detector = None
    if not args.no_yolo:
        try:
            detector = PersonDetector(args.yolo_model, device=args.device)
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] Khong khoi tao duoc YOLO ({e}). Chay che do --no-yolo.")

    cap = cv2.VideoCapture(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    if not cap.isOpened():
        sys.exit(f"Khong mo duoc camera {args.camera}")

    booth = Photobooth()
    deb = GestureDebouncer(hold_frames=args.hold_frames, min_score=args.min_score)
    zoom = ZoomController()
    ctrl = ControllerManager()

    persons, frame_idx, last_ts = [], 0, 0
    zoom_count, fps, t_prev = 0, 0.0, time.monotonic()
    last_fired = ""
    selection_owner = None

    while True:
        ok, frame = cap.read()
        if not ok:
            print("[ERROR] Doc camera that bai")
            break
        frame = cv2.flip(frame, 1)  # che do guong
        now = time.monotonic()
        h, w = frame.shape[:2]

        # ---- 1. Person detection + tracking ----
        if detector is not None and frame_idx % max(args.yolo_every, 1) == 0:
            persons = detector.detect(frame)

        # ---- 2. Hand + gesture ----
        ts = max(int(now * 1000), last_ts + 1)
        last_ts = ts
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        res = recognizer.recognize_for_video(mp_img, ts)

        hands = []
        for i, lms in enumerate(res.hand_landmarks):
            pts = [(lm.x * w, lm.y * h) for lm in lms]
            if res.gestures and i < len(res.gestures) and res.gestures[i]:
                g = res.gestures[i][0]
                label, score = g.category_name, float(g.score)
            else:
                label, score = "None", 0.0
            side = res.handedness[i][0].category_name if res.handedness else "?"
            owner = assign_owner(pts[0], persons) if detector is not None else "solo"
            hands.append(dict(pts=pts, label=label, score=score, side=side, owner=owner))

        # ---- 3. Chon controller ----
        if detector is not None:
            present = {p["id"] for p in persons}
        else:
            present = {"solo"} if hands else set()

        ctrl.update(present, now)
        if ctrl.id is None and booth.state != IDLE:
            booth.to_idle()  # controller roi di -> giai phong quyen

        if ctrl.id is None:
            candidates = [hd for hd in hands
                          if hd["label"] == "Open_Palm" and hd["score"] >= 0.7
                          and hd["owner"] is not None]
            chosen = max(candidates, key=lambda hd: hd["score"]) if candidates else None
            owner = chosen["owner"] if chosen is not None else None
            if owner != selection_owner:
                deb.reset()
                selection_owner = owner
        else:
            mine = [hd for hd in hands if hd["owner"] == ctrl.id]
            chosen = max(mine, key=lambda hd: hd["score"]) if mine else None
            selection_owner = None

        # ---- 4. Gesture -> action ----
        fired, zoom_active, ratio = None, False, 0.0
        pose_dbg = (False, False, False)
        if chosen is not None:
            in_pose, folded, thumb_out, index_out = zoom_pose_info(chosen["pts"])
            ratio = pinch_ratio(chosen["pts"])
            pose_dbg = (folded, thumb_out, index_out)
            if in_pose:
                if booth.state == READY:
                    zoom_count += 1
                    zoom_active = zoom_count >= 4
                    if zoom_active:
                        zoom.update(ratio, now - t_prev)
                else:
                    zoom_count = 0
                    zoom.release()
                deb.update(None, 0.0, now)
            else:
                zoom_count = 0
                zoom.release()
                fired = deb.update(chosen["label"], chosen["score"], now)
        else:
            zoom_count = 0
            zoom.release()
            deb.update(None, 0.0, now)

        if fired:
            last_fired = f"{fired} @ {datetime.now().strftime('%H:%M:%S')}"
            print(f"[GESTURE] {fired} (state={booth.state})")
            if (booth.state == IDLE and fired == "Open_Palm" and chosen is not None
                    and chosen["owner"] is not None):
                ctrl.lock(chosen["owner"], now)
                selection_owner = None
                print(f"[CONTROLLER] Khoa nguoi dieu khien: {ctrl.id}")
            booth.on_gesture(fired, now)

        # ---- 5. Photobooth engine: zoom -> filter -> capture ----
        view = FILTERS[booth.filter_idx][1](apply_zoom(frame, zoom.zoom))
        booth.tick(now, view)
        preview = booth.render(view, zoom.zoom, now)

        # ---- 6. Hien thi ----
        fps = 0.9 * fps + 0.1 / max(now - t_prev, 1e-6)
        t_prev = now
        info = [
            f"FPS: {fps:4.1f}   persons: {len(persons) if detector else 'off'}   hands: {len(hands)}",
            f"Controller: {ctrl.id}   Last event: {last_fired}",
            f"Pinch ratio: {ratio:.2f}   folded={pose_dbg[0]} thumb_out={pose_dbg[1]} "
            f"index_out={pose_dbg[2]}   "
            f"zoom_mode={zoom_active}",
        ]
        cv2.imshow("Photobooth Preview", preview)
        cv2.imshow("AI Debug", draw_debug(frame, persons, hands, ctrl.id, chosen, info))

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord("r"):
            ctrl.id = None
            booth.to_idle()
        frame_idx += 1

    cap.release()
    recognizer.close()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
````

## File: AI/requirements.txt
````
numpy
opencv-python
mediapipe
# Chi can neu muon nhan nguoi + chon controller (bo qua neu chay --no-yolo)
ultralytics
````

## File: Cuoi_ki/Raspberry_Pi/config/config.yaml
````yaml
# config/config.yaml
# ==================
# MỌI THÔNG SỐ CẤU HÌNH ĐỀU Ở ĐÂY — không hardcode trong code.
# Khi demo đổi mạng: chỉ sửa file này.

server:
  host: "0.0.0.0"
  client_host: "10.228.70.213"
  http_port: 8000
  ws_path: "/ws/frames"
  max_frame_bytes: 10485760
  static_token: ""            # Set PHOTOBOOTH_STATIC_TOKEN for non-local networks

mqtt:
  broker_host: "10.228.70.213"
  broker_port: 1883
  device_id: "pi01"
  username: ""
  password: ""
  tls_enabled: false
  tls_ca_certs: null
  heartbeat_interval_sec: 5
  telemetry_interval_sec: 2
  qos_telemetry: 0
  qos_command: 1
  qos_status: 1

camera:
  width: 480
  height: 360
  jpeg_quality: 60
  target_fps: 12
  device_index: 0
  photo_width: 1920
  photo_height: 1080
  photo_jpeg_quality: 90
  mock_hardware: false
  led_gpio_pin: 18
  button_gpio_pin: 17  # Wire the button between BCM GPIO17 and GND
  light_sensor_address: null

light_control:
  enabled: false
  lux_low: 150
  lux_high: 300
  hysteresis: 30
  min_cmd_interval_sec: 2.0
  default_brightness: 50

effects:
  default_effect_id: "original"

storage:
  photo_dir: "data/photos"
  offline_photo_dir: "data/offline_photos"
  db_path: "data/photobooth.db"
  log_dir: "data/logs"
  telemetry_retention_days: 7
````

## File: Cuoi_ki/Raspberry_Pi/pi/__init__.py
````python
"""
pi/__init__.py
"""
````

## File: Cuoi_ki/Raspberry_Pi/pi/hardware.py
````python
"""Hardware abstraction for mock development and Raspberry Pi deployment."""

import logging
import random
import time
from collections.abc import Callable

import cv2
import numpy as np

from shared.config import cfg

logger = logging.getLogger(__name__)


class MockHardware:
    def __init__(self) -> None:
        camera = cfg.get("camera", {})
        self.width = int(camera.get("width", 640))
        self.height = int(camera.get("height", 480))
        self._started_at = time.monotonic()
        self._lux = 220.0
        self.brightness = int(cfg.get("light_control", {}).get("default_brightness", 50))

    def read_frame(self) -> np.ndarray:
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        elapsed = int(time.monotonic() - self._started_at)
        cv2.putText(
            frame,
            "MOCK CAMERA",
            (30, self.height // 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.1,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            time.strftime("%H:%M:%S"),
            (30, self.height // 2 + 45),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (180, 180, 180),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            f"frame {elapsed}",
            (30, self.height // 2 + 85),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (180, 180, 180),
            2,
            cv2.LINE_AA,
        )
        return frame

    def read_lux(self) -> float:
        self._lux = min(500, max(50, self._lux + random.uniform(-8, 8)))
        return round(self._lux, 1)

    def capture_photo(self) -> np.ndarray:
        return self.read_frame()

    def set_led(self, brightness: int) -> int:
        self.brightness = min(100, max(0, brightness))
        return self.brightness

    def close(self) -> None:
        return None


class RaspberryPiHardware:
    def __init__(self, button_callback: Callable[[str], None] | None = None) -> None:
        camera = cfg.get("camera", {})
        self._camera = cv2.VideoCapture(int(camera.get("device_index", 0)))
        if not self._camera.isOpened():
            self._camera.release()
            raise RuntimeError(
                f"Could not open camera index {camera.get('device_index', 0)}"
            )
        self._camera.set(cv2.CAP_PROP_FRAME_WIDTH, int(camera.get("width", 640)))
        self._camera.set(cv2.CAP_PROP_FRAME_HEIGHT, int(camera.get("height", 480)))
        self._led = None
        self._bus = None
        self._button = None
        led_pin = camera.get("led_gpio_pin")
        if led_pin is not None:
            try:
                from gpiozero import PWMLED
            except ImportError as exc:
                self.close()
                raise RuntimeError("Install gpiozero to control the LED on Raspberry Pi") from exc
            self._led = PWMLED(int(led_pin))
            logger.info("PWM LED configured on BCM GPIO%s", led_pin)
        button_pin = camera.get("button_gpio_pin")
        if button_pin is not None and button_callback is not None:
            try:
                from gpiozero import Button
            except ImportError as exc:
                self.close()
                raise RuntimeError("Install gpiozero to use the physical button") from exc
            self._button = Button(int(button_pin), bounce_time=0.1)
            self._button.when_pressed = lambda: button_callback("manual_capture")
            logger.info("Physical button configured on BCM GPIO%s", button_pin)

    def read_frame(self) -> np.ndarray:
        success, frame = self._camera.read()
        if not success or frame is None:
            raise RuntimeError("Camera did not return a frame")
        return frame

    def capture_photo(self) -> np.ndarray:
        camera = cfg.get("camera", {})
        stream_width = int(camera.get("width", 640))
        stream_height = int(camera.get("height", 480))
        photo_width = int(camera.get("photo_width", 1920))
        photo_height = int(camera.get("photo_height", 1080))
        self._camera.set(cv2.CAP_PROP_FRAME_WIDTH, photo_width)
        self._camera.set(cv2.CAP_PROP_FRAME_HEIGHT, photo_height)
        try:
            return self.read_frame()
        finally:
            self._camera.set(cv2.CAP_PROP_FRAME_WIDTH, stream_width)
            self._camera.set(cv2.CAP_PROP_FRAME_HEIGHT, stream_height)

    def read_lux(self) -> float:
        camera = cfg.get("camera", {})
        address = camera.get("light_sensor_address")
        if address is None:
            raise RuntimeError("BH1750 light sensor address is not configured")
        if self._bus is None:
            try:
                from smbus2 import SMBus
            except ImportError as exc:
                raise RuntimeError("Install smbus2 to read the BH1750 light sensor") from exc
            try:
                self._bus = SMBus(1)
            except OSError as exc:
                raise RuntimeError("Could not open the I2C bus") from exc
        sensor_address = int(address)
        try:
            self._bus.write_byte(sensor_address, 0x10)
            time.sleep(0.18)
            reading = self._bus.read_i2c_block_data(sensor_address, 0x00, 2)
        except (OSError, IndexError) as exc:
            raise RuntimeError("Could not read the BH1750 light sensor") from exc
        return round(((reading[0] << 8) | reading[1]) / 1.2, 1)

    def set_led(self, brightness: int) -> int:
        if self._led is None:
            raise RuntimeError("LED GPIO is disabled; configure camera.led_gpio_pin")
        applied = min(100, max(0, brightness))
        self._led.value = applied / 100
        return applied

    def close(self) -> None:
        if self._camera is not None:
            self._camera.release()
        if self._led is not None:
            self._led.close()
        if self._button is not None:
            self._button.close()
        if self._bus is not None:
            self._bus.close()
````

## File: Cuoi_ki/Raspberry_Pi/pi/main.py
````python
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
````

## File: Cuoi_ki/Raspberry_Pi/shared/__init__.py
````python
"""
shared/__init__.py
Đánh dấu shared/ là Python package để import được.
"""
````

## File: Cuoi_ki/Raspberry_Pi/shared/config.py
````python
"""
shared/config.py
----------------
Đọc config.yaml một lần, dùng ở mọi nơi.

Dùng:
    from shared.config import cfg
    host = cfg["server"]["client_host"]
"""

import os
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_config() -> dict:
    """Load YAML configuration, with an optional PHOTOBOOTH_CONFIG override."""
    config_path = Path(
        os.environ.get(
            "PHOTOBOOTH_CONFIG",
            str(PROJECT_ROOT / "config" / "config.yaml"),
        )
    ).expanduser()
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path

    with config_path.open(encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)
    if not isinstance(config, dict):
        raise ValueError(f"Configuration must be a YAML mapping: {config_path}")

    text_overrides = {
        "PHOTOBOOTH_SERVER_HOST": ("server", "host"),
        "PHOTOBOOTH_CLIENT_HOST": ("server", "client_host"),
        "PHOTOBOOTH_MQTT_HOST": ("mqtt", "broker_host"),
        "PHOTOBOOTH_DEVICE_ID": ("mqtt", "device_id"),
        "PHOTOBOOTH_STATIC_TOKEN": ("server", "static_token"),
        "PHOTOBOOTH_MQTT_USERNAME": ("mqtt", "username"),
        "PHOTOBOOTH_MQTT_PASSWORD": ("mqtt", "password"),
        "PHOTOBOOTH_MQTT_CA_CERT": ("mqtt", "tls_ca_certs"),
    }
    for variable, (section, key) in text_overrides.items():
        if variable in os.environ:
            config.setdefault(section, {})[key] = os.environ[variable]

    mock_hardware = os.environ.get("PHOTOBOOTH_MOCK_HARDWARE")
    if mock_hardware is not None:
        normalized = mock_hardware.strip().lower()
        if normalized not in {"true", "false", "1", "0"}:
            raise ValueError("PHOTOBOOTH_MOCK_HARDWARE must be true/false or 1/0")
        config.setdefault("camera", {})["mock_hardware"] = normalized in {"true", "1"}
    mqtt_tls = os.environ.get("PHOTOBOOTH_MQTT_TLS")
    if mqtt_tls is not None:
        normalized = mqtt_tls.strip().lower()
        if normalized not in {"true", "false", "1", "0"}:
            raise ValueError("PHOTOBOOTH_MQTT_TLS must be true/false or 1/0")
        config.setdefault("mqtt", {})["tls_enabled"] = normalized in {"true", "1"}
    return config


cfg = load_config()
````

## File: Cuoi_ki/Raspberry_Pi/shared/logging_config.py
````python
"""Configure rotating per-module logs with a consistent structured context."""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from shared.config import PROJECT_ROOT, cfg


class LogContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.session_id = getattr(record, "session_id", "-")
        record.action = getattr(record, "action", record.getMessage())
        record.payload = getattr(record, "payload", "-")
        return True


def configure_logging(module_name: str) -> None:
    log_dir = Path(cfg.get("storage", {}).get("log_dir", "data/logs")).expanduser()
    if not log_dir.is_absolute():
        log_dir = PROJECT_ROOT / log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s module=%(name)s "
        "session_id=%(session_id)s action=%(action)s payload=%(payload)s"
    )
    context_filter = LogContextFilter()
    handlers = [
        logging.StreamHandler(),
        RotatingFileHandler(
            log_dir / f"{module_name}.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        ),
    ]
    for handler in handlers:
        handler.setFormatter(formatter)
        handler.addFilter(context_filter)
    log_level = logging.getLevelName(os.environ.get("LOG_LEVEL", "INFO").upper())
    logging.basicConfig(
        level=log_level,
        handlers=handlers,
    )
````

## File: Cuoi_ki/Raspberry_Pi/shared/mqtt_topics.py
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

    @staticmethod
    def capture(device_id: str) -> str:
        """Server yêu cầu Pi chụp ảnh độ phân giải cao."""
        return f"photobooth/{device_id}/camera/capture"

    @staticmethod
    def photo_status(device_id: str) -> str:
        """Pi thông báo kết quả chụp ảnh."""
        return f"photobooth/{device_id}/camera/status"


# QoS mặc định theo loại dữ liệu
QOS = {
    "telemetry": 0,     # lux, LED status — mất 1 bản không sao
    "command": 1,       # led/set, capture — cần đảm bảo đến nơi
    "status": 1,        # online/offline — quan trọng
}
````

## File: Cuoi_ki/Raspberry_Pi/shared/schemas.py
````python
"""Validated JSON contracts used by the Raspberry Pi client and AI server."""

from typing import Literal

from pydantic import BaseModel, Field


class FrameMeta(BaseModel):
    session_id: str = Field(min_length=1)
    device_id: str | None = None
    frame_id: int = Field(ge=0)
    timestamp: float = Field(gt=0)


class WebSocketAuth(BaseModel):
    type: Literal["auth"] = "auth"
    token: str = ""


class KeyPoint(BaseModel):
    name: str
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    visibility: float = Field(ge=0, le=1)


class FeedbackItem(BaseModel):
    body_part: str
    message: str


class GesturePrediction(BaseModel):
    hand_index: int = Field(ge=0)
    gesture: str | None = None
    score: float | None = Field(default=None, ge=0, le=1)
    handedness: str | None = None
    landmarks: list[tuple[float, float]] = Field(default_factory=list)
    world_landmarks: list[tuple[float, float, float]] = Field(default_factory=list)


class GestureFrameResult(BaseModel):
    session_id: str
    frame_id: int = Field(ge=0)
    hand_count: int = Field(default=0, ge=0)
    gestures: list[GesturePrediction] = Field(default_factory=list)
    control_active: bool = False
    control_state: Literal["inactive", "ready", "countdown", "capturing"] = "inactive"
    selected_effect_id: str = "original"
    zoom_factor: float = Field(default=1, ge=1, le=2.5)
    countdown_remaining: int = Field(default=0, ge=0)
    selected_gesture: str | None = None
    selected_gesture_score: float = Field(default=0, ge=0, le=1)
    zoom_active: bool = False
    last_action: str | None = None
    processing_ms: float = Field(default=0, ge=0)


class PoseResult(BaseModel):
    session_id: str
    frame_id: int = Field(ge=0)
    pose_score: int = Field(default=0, ge=0, le=100)
    status: Literal["ok", "adjusting", "no_person", "ai_unavailable"]
    keypoints: list[KeyPoint] = Field(default_factory=list)
    feedback: list[FeedbackItem] = Field(default_factory=list)
    ready_to_capture: bool = False
    hand_count: int = Field(default=0, ge=0)
    gestures: list[GesturePrediction] = Field(default_factory=list)
    processing_ms: float = Field(default=0, ge=0)


class DeviceStatus(BaseModel):
    device_id: str = Field(min_length=1)
    status: Literal["online", "offline"]
    version: str | None = None
    timestamp: float | None = None


class LightSensor(BaseModel):
    device_id: str = Field(min_length=1)
    lux: float = Field(ge=0)
    timestamp: float = Field(gt=0)


class LEDCommand(BaseModel):
    command_id: str = Field(min_length=1)
    brightness: int = Field(ge=0, le=100)


class LEDRequest(BaseModel):
    brightness: int = Field(ge=0, le=100)


class LEDAck(BaseModel):
    command_id: str = Field(min_length=1)
    applied: int = Field(ge=0, le=100)
    success: bool = True
    error: str | None = None


class LEDStatus(BaseModel):
    device_id: str = Field(min_length=1)
    brightness: int = Field(ge=0, le=100)
    timestamp: float = Field(gt=0)


class ButtonEvent(BaseModel):
    device_id: str = Field(min_length=1)
    action: Literal["start_session", "manual_capture", "cancel_countdown"]
    timestamp: float = Field(gt=0)


class SessionCreate(BaseModel):
    device_id: str = Field(min_length=1)
    pose_template_id: str | None = None
    effect_id: str = "original"


class SessionInfo(BaseModel):
    session_id: str
    device_id: str
    status: Literal["active", "completed"]
    pose_template_id: str | None = None
    effect_id: str = "original"
    zoom_factor: float = Field(default=1, ge=1, le=2.5)
    created_at: float
    ended_at: float | None = None


class PhotoMeta(BaseModel):
    photo_id: str
    session_id: str
    pose_template_id: str | None = None
    effect_id: str = "original"
    zoom_factor: float = Field(default=1, ge=1, le=2.5)
    timestamp: float
    file_path: str
    pose_score: int = Field(default=0, ge=0, le=100)


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    uptime_sec: float = Field(ge=0)
    connected_devices: int = Field(ge=0)
    ai_available: bool
    mqtt_connected: bool
````

## File: Cuoi_ki/Raspberry_Pi/tools/mock_pi_hardware.py
````python
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
````

## File: Cuoi_ki/Raspberry_Pi/.gitignore
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
data/offline_photos/
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

## File: Cuoi_ki/Raspberry_Pi/pyproject.toml
````toml
[project]
name = "photobooth-pi"
version = "0.2.0"
requires-python = ">=3.10"
dependencies = [
    "numpy>=1.26,<2",
    "pydantic>=2.6,<3",
    "PyYAML>=6,<7",
]

[project.optional-dependencies]
pi = [
    "opencv-python>=4.8,<5",
    "paho-mqtt>=2.1,<3",
    "websockets>=12,<16",
    "gpiozero>=2,<3",
    "smbus2>=0.4,<1",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["shared*", "pi*"]
````

## File: Cuoi_ki/Raspberry_Pi/README.md
````markdown
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
````

## File: Cuoi_ki/Server_Module/assets/photo_effects/face_overlays/cat_ears/metadata.json
````json
{
  "id": "cat_ears",
  "name": "Tai mèo dễ thương",
  "anchor": "forehead",
  "width_ratio": 1.35,
  "pivot": [
    0.5,
    0.85
  ],
  "offset": [
    0.0,
    -0.05
  ],
  "angle_offset": 0.0
}
````

## File: Cuoi_ki/Server_Module/assets/photo_effects/face_overlays/crown/metadata.json
````json
{
  "id": "crown",
  "name": "Vương miện vàng",
  "anchor": "forehead",
  "width_ratio": 1.12,
  "pivot": [
    0.5,
    0.88
  ],
  "offset": [
    0.0,
    -0.06
  ],
  "angle_offset": 0.0
}
````

## File: Cuoi_ki/Server_Module/assets/photo_effects/face_overlays/glasses/metadata.json
````json
{
  "id": "glasses",
  "name": "Kính râm Aviator",
  "anchor": "eyes",
  "width_ratio": 1.48,
  "pivot": [
    0.5,
    0.42
  ],
  "offset": [
    0.0,
    0.02
  ],
  "angle_offset": 0.0
}
````

## File: Cuoi_ki/Server_Module/assets/photo_effects/face_overlays/halo/metadata.json
````json
{
  "id": "halo",
  "name": "Vòng hào quang",
  "anchor": "forehead",
  "width_ratio": 1.15,
  "pivot": [
    0.5,
    0.5
  ],
  "offset": [
    0.0,
    -0.52
  ],
  "angle_offset": 0.0
}
````

## File: Cuoi_ki/Server_Module/assets/photo_effects/face_overlays/.gitkeep
````

````

## File: Cuoi_ki/Server_Module/assets/photo_effects/filters/.gitkeep
````

````

## File: Cuoi_ki/Server_Module/assets/photo_effects/manifest.json
````json
{
  "version": "1.0.0",
  "filters": [
    {
      "id": "original",
      "name": "Tự nhiên",
      "type": "builtin"
    },
    {
      "id": "gray",
      "name": "Đen trắng",
      "type": "builtin"
    },
    {
      "id": "sepia",
      "name": "Hoài cổ",
      "type": "builtin"
    },
    {
      "id": "warm",
      "name": "Tông ấm",
      "type": "builtin"
    },
    {
      "id": "negative",
      "name": "Âm bản",
      "type": "builtin"
    },
    {
      "id": "cartoon",
      "name": "Hoạt hình",
      "type": "builtin"
    },
    {
      "id": "pixel",
      "name": "Pixel 8-bit",
      "type": "builtin"
    }
  ],
  "face_overlays": [
    {
      "id": "glasses",
      "name": "Kính râm Aviator",
      "overlay": "face_overlays/glasses/overlay.png",
      "metadata": "face_overlays/glasses/metadata.json"
    },
    {
      "id": "crown",
      "name": "Vương miện vàng",
      "overlay": "face_overlays/crown/overlay.png",
      "metadata": "face_overlays/crown/metadata.json"
    },
    {
      "id": "cat_ears",
      "name": "Tai mèo dễ thương",
      "overlay": "face_overlays/cat_ears/overlay.png",
      "metadata": "face_overlays/cat_ears/metadata.json"
    },
    {
      "id": "halo",
      "name": "Vòng hào quang",
      "overlay": "face_overlays/halo/overlay.png",
      "metadata": "face_overlays/halo/metadata.json"
    }
  ],
  "frames": [
    {
      "id": "classic_strip_4",
      "name": "Dải dọc Cổ điển (1x4)",
      "file": "frames/classic_strip_4.png",
      "canvas_size": [
        600,
        1800
      ],
      "slots": [
        [
          40,
          45,
          520,
          350
        ],
        [
          40,
          425,
          520,
          350
        ],
        [
          40,
          805,
          520,
          350
        ],
        [
          40,
          1185,
          520,
          350
        ]
      ],
      "qr_slot": [
        430,
        1585,
        130,
        130
      ]
    },
    {
      "id": "pastel_pink_strip_4",
      "name": "Dải dọc Hồng Pastel (1x4)",
      "file": "frames/pastel_pink_strip_4.png",
      "canvas_size": [
        600,
        1800
      ],
      "slots": [
        [
          40,
          45,
          520,
          350
        ],
        [
          40,
          425,
          520,
          350
        ],
        [
          40,
          805,
          520,
          350
        ],
        [
          40,
          1185,
          520,
          350
        ]
      ],
      "qr_slot": [
        430,
        1585,
        130,
        130
      ]
    },
    {
      "id": "grid_2x2_retro",
      "name": "Khung lưới Studio (2x2)",
      "file": "frames/grid_2x2_retro.png",
      "canvas_size": [
        1200,
        1600
      ],
      "slots": [
        [
          60,
          70,
          520,
          620
        ],
        [
          620,
          70,
          520,
          620
        ],
        [
          60,
          730,
          520,
          620
        ],
        [
          620,
          730,
          520,
          620
        ]
      ],
      "qr_slot": [
        1005,
        1395,
        135,
        135
      ]
    }
  ]
}
````

## File: Cuoi_ki/Server_Module/assets/photo_effects/README.md
````markdown
# Photo effect assets

For a captured photo set, the Server applies each slot's selected color filter
and face overlay to a rendered copy of the high-resolution original. The raw
originals remain unchanged and the live camera preview is not modified. Overlay
and frame assets are loaded when the Server starts, so restart it after adding
or changing them.

## Folders

- `filters/`: reserved for custom color-filter assets such as `.cube` LUT files.
  The existing built-in filters are currently implemented in
  `server/image_processing.py`.
- `face_overlays/<overlay_id>/`: one folder per face sticker. Put a transparent
  RGBA PNG named `overlay.png` and a `metadata.json` in each folder.
- `frames/`: PNG photo-frame templates. The root `manifest.json` lists each
  template's canvas dimensions, four photo-slot rectangles, and reserved QR
  rectangle. Admin lets users choose a template, place four selected originals
  into its slots, and preview the transparent frame composited over them.

The supplied `manifest.json` also lists the built-in color filters and face
overlays. Filter entries reference filters already implemented by the Server;
they are not external LUT files.

Example:

```text
photo_effects/
├── filters/
└── face_overlays/
    ├── glasses/
    │   ├── overlay.png
    │   └── metadata.json
    └── crown/
        ├── overlay.png
        └── metadata.json
```

Example `metadata.json` for a crown:

```json
{
  "id": "crown",
  "name": "Crown",
  "anchor": "forehead",
  "width_ratio": 1.15,
  "pivot": [0.5, 0.85],
  "offset": [0.0, -0.08],
  "angle_offset": 0.0
}
```

Use `"anchor": "eyes"` for glasses and `"anchor": "forehead"` for crowns or
hats. `pivot` is normalized to the PNG dimensions; `offset` is relative to the
face reference width. The Server validates the PNG and metadata at startup.

Admin supports per-slot built-in color effects and optional face overlays. It
center-crops each original to fit a slot, detects faces on the cropped image,
applies the selected color effect, and composites the sticker afterward. The
frame is layered above the processed photos. QR placement is reserved in the
manifest but QR generation and final export are not part of this milestone.

Face overlays require a MediaPipe Face Landmarker task model at
`AI/models/face_landmarker.task`. Its path, number of faces, and confidence
thresholds are configured in `Server_Module/config/config.yaml`.
````

## File: Cuoi_ki/Server_Module/config/config.yaml
````yaml
# config/config.yaml
# ==================
# MỌI THÔNG SỐ CẤU HÌNH ĐỀU Ở ĐÂY — không hardcode trong code.
# Khi demo đổi mạng: chỉ sửa file này.

server:
  host: "0.0.0.0"
  client_host: "127.0.0.1"    # Set to the laptop's LAN IPv4 address on the Pi
  http_port: 8000
  ws_path: "/ws/frames"
  max_frame_bytes: 10485760
  static_token: ""            # Set PHOTOBOOTH_STATIC_TOKEN for non-local networks

mqtt:
  broker_host: "127.0.0.1"
  broker_port: 1883
  device_id: "pi01"
  username: ""
  password: ""
  tls_enabled: false
  tls_ca_certs: null
  heartbeat_interval_sec: 5
  telemetry_interval_sec: 2
  qos_telemetry: 0
  qos_command: 1
  qos_status: 1

light_control:
  enabled: false
  lux_low: 150
  lux_high: 300
  hysteresis: 30
  min_cmd_interval_sec: 2.0
  default_brightness: 50

gesture:
  model_path: "../../AI/models/gesture_recognizer.task"
  num_hands: 1
  min_score: 0.6
  activation_min_score: 0.5
  hold_frames: 4
  cooldown_sec: 0.8
  release_frames: 5
  countdown_sec: 3
  min_hand_presence_confidence: 0.4
  min_tracking_confidence: 0.4

face_effects:
  model_path: "../../AI/models/face_landmarker.task"
  asset_dir: "assets/photo_effects/face_overlays"
  num_faces: 5
  min_face_detection_confidence: 0.5
  min_face_presence_confidence: 0.5
  min_tracking_confidence: 0.5

capture_sequence:
  photo_count: 8
  countdown_sec: 10
  shot_timeout_sec: 60
  retake_decision_timeout_sec: 30

effects:
  default_effect_id: "original"

storage:
  photo_dir: "data/photos"
  offline_photo_dir: "data/offline_photos"
  db_path: "data/photobooth.db"
  log_dir: "data/logs"
  telemetry_retention_days: 7
````

## File: Cuoi_ki/Server_Module/photobooth_server.egg-info/dependency_links.txt
````

````

## File: Cuoi_ki/Server_Module/photobooth_server.egg-info/PKG-INFO
````
Metadata-Version: 2.4
Name: photobooth-server
Version: 0.2.0
Requires-Python: >=3.10
Requires-Dist: numpy<2,>=1.26
Requires-Dist: pydantic<3,>=2.6
Requires-Dist: PyYAML<7,>=6
Provides-Extra: server
Requires-Dist: fastapi<1,>=0.110; extra == "server"
Requires-Dist: uvicorn[standard]<1,>=0.27; extra == "server"
Requires-Dist: paho-mqtt<3,>=2.1; extra == "server"
Requires-Dist: opencv-python-headless<5,>=4.8; extra == "server"
Requires-Dist: mediapipe<0.11,>=0.10.18; extra == "server"
Requires-Dist: ultralytics<9,>=8.3; extra == "server"
````

## File: Cuoi_ki/Server_Module/photobooth_server.egg-info/requires.txt
````
numpy<2,>=1.26
pydantic<3,>=2.6
PyYAML<7,>=6

[server]
fastapi<1,>=0.110
uvicorn[standard]<1,>=0.27
paho-mqtt<3,>=2.1
opencv-python-headless<5,>=4.8
mediapipe<0.11,>=0.10.18
ultralytics<9,>=8.3
````

## File: Cuoi_ki/Server_Module/photobooth_server.egg-info/SOURCES.txt
````
README.md
pyproject.toml
photobooth_server.egg-info/PKG-INFO
photobooth_server.egg-info/SOURCES.txt
photobooth_server.egg-info/dependency_links.txt
photobooth_server.egg-info/requires.txt
photobooth_server.egg-info/top_level.txt
server/__init__.py
server/ai.py
server/image_processing.py
server/iot.py
server/main.py
server/pose_matching.py
server/storage.py
shared/__init__.py
shared/config.py
shared/logging_config.py
shared/mqtt_topics.py
shared/schemas.py
tests/test_image_processing.py
tests/test_pose_matching.py
tests/test_schemas.py
tests/test_storage.py
````

## File: Cuoi_ki/Server_Module/photobooth_server.egg-info/top_level.txt
````
server
shared
````

## File: Cuoi_ki/Server_Module/server/static/admin.html
````html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Photobooth Admin</title>
  <style>
    :root {
      color-scheme: dark;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #0b1020;
      color: #eef2ff;
      font-synthesis: none;
    }
    * { box-sizing: border-box; }
    body { margin: 0; min-width: 320px; background: radial-gradient(ellipse at 12% 0%, #172554 0, #0b1020 48%); }
    button, input, select { font: inherit; }
    button { cursor: pointer; }
    .shell { max-width: 1280px; margin: 0 auto; padding: 28px 24px 48px; }
    header { display: flex; justify-content: space-between; align-items: center; gap: 18px; margin-bottom: 26px; }
    .brand { display: flex; align-items: center; gap: 13px; }
    .brand-mark { display: grid; place-items: center; width: 42px; height: 42px; border-radius: 13px; background: linear-gradient(135deg, #5eead4, #38bdf8); color: #082f49; font-weight: 900; }
    h1 { margin: 0; font-size: 21px; letter-spacing: -.03em; }
    .subtitle { margin-top: 4px; color: #91a0bd; font-size: 13px; }
    a { color: #67e8f9; text-decoration: none; }
    a:hover { text-decoration: underline; }
    .toolbar, .card { border: 1px solid #25304a; background: rgba(15, 23, 42, .84); border-radius: 17px; box-shadow: 0 16px 40px rgba(0, 0, 0, .16); }
    .toolbar { padding: 16px; display: grid; grid-template-columns: minmax(140px, .7fr) minmax(200px, 1fr) auto auto; gap: 12px; align-items: end; margin-bottom: 18px; }
    label { display: block; color: #9aa8c3; font-size: 12px; margin-bottom: 7px; }
    input[type="text"], input[type="password"] { width: 100%; color: #e2e8f0; border: 1px solid #34415d; background: #0b1326; border-radius: 10px; padding: 10px 12px; outline: none; }
    select { width: 100%; color: #e2e8f0; border: 1px solid #34415d; background: #0b1326; border-radius: 10px; padding: 10px 12px; outline: none; }
    input:focus { border-color: #22d3ee; box-shadow: 0 0 0 3px rgba(34, 211, 238, .12); }
    button { border: 0; border-radius: 10px; padding: 10px 15px; color: #071321; font-weight: 750; background: #67e8f9; transition: .15s ease; }
    button:hover:not(:disabled) { background: #a5f3fc; transform: translateY(-1px); }
    button.secondary { color: #dce8f8; background: #293650; }
    button.secondary:hover:not(:disabled) { background: #394968; }
    button:disabled { cursor: not-allowed; opacity: .45; }
    .connection { display: flex; align-items: center; justify-content: flex-end; gap: 8px; min-width: 115px; padding-bottom: 10px; color: #a9b5cb; font-size: 13px; }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: #64748b; box-shadow: 0 0 0 4px rgba(100, 116, 139, .12); }
    .dot.good { background: #34d399; box-shadow: 0 0 0 4px rgba(52, 211, 153, .12); }
    .dot.bad { background: #fb7185; box-shadow: 0 0 0 4px rgba(251, 113, 133, .12); }
    .metrics { display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; margin-bottom: 18px; }
    .metric { padding: 17px 18px; }
    .metric-title { color: #91a0bd; font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }
    .metric-value { margin-top: 9px; font-size: 18px; font-weight: 750; }
    .metric-note { margin-top: 4px; color: #7787a7; font-size: 12px; }
    .main-grid { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(300px, .8fr); gap: 18px; align-items: start; }
    .card { padding: 21px; }
    .card h2 { margin: 0; font-size: 16px; letter-spacing: -.02em; }
    .card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; }
    .muted { color: #91a0bd; font-size: 13px; }
    .status-pill { white-space: nowrap; padding: 6px 10px; border: 1px solid #35435e; border-radius: 999px; color: #b7c3d9; font-size: 12px; }
    .status-pill.good { border-color: #146c56; color: #6ee7b7; background: rgba(16, 185, 129, .08); }
    .status-pill.warn { border-color: #815d22; color: #fcd34d; background: rgba(245, 158, 11, .08); }
    .status-pill.bad { border-color: #87354c; color: #fda4af; background: rgba(244, 63, 94, .08); }
    .score-row { display: flex; align-items: end; justify-content: space-between; gap: 12px; margin: 28px 0 10px; }
    .score { font-size: 48px; font-weight: 800; line-height: 1; letter-spacing: -.06em; }
    .score small { color: #8190ac; font-size: 18px; font-weight: 600; letter-spacing: 0; }
    .ready { color: #94a3b8; font-size: 13px; }
    .progress { height: 9px; overflow: hidden; border-radius: 10px; background: #26324a; }
    .progress > span { display: block; width: 0; height: 100%; border-radius: inherit; background: linear-gradient(90deg, #22d3ee, #34d399); transition: width .25s ease; }
    .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 17px; }
    .stat { border-radius: 11px; padding: 12px; background: #111b30; }
    .stat strong { display: block; font-size: 17px; }
    .stat span { display: block; margin-top: 4px; color: #8493af; font-size: 11px; }
    .section-label { margin: 23px 0 9px; color: #91a0bd; font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }
    .feedback, .keypoints, .gestures { display: grid; gap: 7px; }
    .feedback-item { padding: 10px 12px; border-radius: 9px; background: #111b30; color: #cbd5e1; font-size: 13px; }
    .feedback-item strong { color: #67e8f9; margin-right: 7px; }
    .empty { color: #7f8da7; font-size: 13px; }
    details { margin-top: 15px; }
    summary { cursor: pointer; color: #9fb0ca; font-size: 13px; }
    .keypoints { grid-template-columns: repeat(2, minmax(0, 1fr)); margin-top: 10px; }
    .point { display: flex; justify-content: space-between; gap: 8px; padding: 8px 10px; border-radius: 8px; background: #111b30; color: #aebbd0; font-size: 11px; }
    .point span:last-child { color: #67e8f9; font-variant-numeric: tabular-nums; }
    .control { margin-top: 20px; padding-top: 18px; border-top: 1px solid #26324a; }
    .control:first-of-type { margin-top: 18px; }
    .control-title { margin-bottom: 12px; font-size: 14px; font-weight: 700; }
    .slider-row { display: grid; grid-template-columns: 1fr 54px; gap: 12px; align-items: center; }
    input[type="range"] { width: 100%; accent-color: #22d3ee; }
    output { color: #67e8f9; font-weight: 750; text-align: right; }
    .button-row { display: flex; flex-wrap: wrap; gap: 9px; margin-top: 12px; }
    .action-message { min-height: 20px; margin-top: 10px; color: #9aa8c3; font-size: 12px; overflow-wrap: anywhere; }
    .sequence-progress { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 7px; margin-top: 12px; }
    .sequence-shot { padding: 9px; border: 1px solid #293650; border-radius: 9px; background: #111b30; color: #8493af; font-size: 12px; text-align: center; }
    .sequence-shot.good { border-color: #146c56; color: #6ee7b7; }
    .sequence-shot.warn { border-color: #815d22; color: #fcd34d; }
    .sequence-shot.bad { border-color: #87354c; color: #fda4af; }
    .notice { margin-top: 15px; border-radius: 10px; padding: 11px 12px; color: #fcd34d; background: rgba(245, 158, 11, .08); border: 1px solid rgba(245, 158, 11, .18); font-size: 12px; line-height: 1.5; }
    .camera-card, .history-card, .guide-card { margin-bottom: 18px; }
    .gallery-card { margin: 18px 0; }
    .review-actions { margin-top: 15px; padding: 14px; border: 1px solid #35435e; border-radius: 11px; background: #111b30; }
    .review-message { color: #cbd5e1; font-size: 13px; line-height: 1.5; }
    .photo-layout { margin-top: 18px; padding: 16px; border: 1px solid #35435e; border-radius: 12px; background: #111b30; }
    .layout-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 14px; }
    .layout-frame-row { display: grid; grid-template-columns: minmax(200px, 1fr) minmax(120px, 190px); gap: 14px; align-items: center; margin-top: 14px; }
    .layout-frame-preview { display: block; width: 100%; max-height: 220px; object-fit: contain; border: 1px solid #293650; border-radius: 9px; background: #050914; }
    .layout-slots { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 14px; }
    .layout-slot { min-width: 0; padding: 12px; border: 1px solid #293650; border-radius: 10px; background: #0b1326; }
    .layout-slot h3 { margin: 0 0 10px; color: #67e8f9; font-size: 13px; }
    .layout-slot label { margin-top: 9px; }
    .layout-preview { display: block; max-width: min(100%, 520px); max-height: 720px; margin: 16px auto 0; border: 1px solid #35435e; border-radius: 10px; background: #050914; }
    .photo-gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 12px; margin-top: 15px; }
    .photo-card { min-width: 0; overflow: hidden; border: 1px solid #293650; border-radius: 11px; background: #0b1326; }
    .photo-card img { display: block; width: 100%; aspect-ratio: 4 / 3; object-fit: contain; background: #050914; }
    .photo-card-info { padding: 10px; color: #aebbd0; font-size: 11px; line-height: 1.5; overflow-wrap: anywhere; }
    .photo-card-info strong { display: block; color: #67e8f9; font-size: 12px; }
    .raw-download { margin-top: 8px; padding: 6px 9px; font-size: 11px; }
    .camera-view { position: relative; display: grid; place-items: center; margin-top: 15px; width: 100%; aspect-ratio: 4 / 3; overflow: hidden; border: 1px solid #293650; border-radius: 12px; background: #050914; }
    .camera-view img { display: block; width: 100%; height: 100%; object-fit: contain; }
    .camera-view canvas { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
    .camera-placeholder { position: absolute; color: #71809c; font-size: 14px; }
    .live-badge { position: absolute; top: 12px; left: 12px; display: flex; align-items: center; gap: 7px; padding: 6px 9px; border-radius: 7px; background: rgba(5, 9, 20, .78); color: #dbeafe; font-size: 11px; font-weight: 750; letter-spacing: .08em; }
    .live-badge::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: #fb7185; }
    .live-badge.active::before { background: #34d399; box-shadow: 0 0 8px #34d399; }
    .video-caption { position: absolute; right: 12px; bottom: 12px; max-width: calc(100% - 24px); padding: 8px 11px; border: 1px solid rgba(103, 232, 249, .24); border-radius: 9px; background: rgba(5, 9, 20, .82); color: #e2e8f0; font-size: 12px; font-weight: 700; text-align: right; }
    .table-wrap { overflow-x: auto; margin-top: 14px; }
    table { width: 100%; border-collapse: collapse; text-align: left; font-size: 12px; }
    th { padding: 9px 10px; color: #8493af; font-weight: 600; border-bottom: 1px solid #293650; }
    td { padding: 10px; color: #cbd5e1; border-bottom: 1px solid rgba(41, 54, 80, .62); white-space: nowrap; }
    .guide-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 15px; }
    .guide-item { padding: 13px; border-radius: 10px; background: #111b30; color: #bdc9dc; font-size: 12px; line-height: 1.55; }
    .guide-item strong { display: block; margin-bottom: 5px; color: #67e8f9; font-size: 13px; }
    footer { margin-top: 20px; color: #65738d; font-size: 11px; text-align: center; }
    @media (max-width: 820px) { .metrics { grid-template-columns: repeat(3, 1fr); } .main-grid { grid-template-columns: 1fr; } }
    @media (max-width: 620px) { .shell { padding: 18px 13px 32px; } header { align-items: flex-start; } .toolbar { grid-template-columns: 1fr 1fr; } .connection { justify-content: flex-start; } .metrics { grid-template-columns: repeat(2, 1fr); gap: 9px; } .metric { padding: 14px; } .metric-value { font-size: 16px; } .card { padding: 17px; } .guide-grid { grid-template-columns: 1fr; } }
    @media (max-width: 420px) { .sequence-progress { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
    @media (max-width: 620px) { .layout-slots { grid-template-columns: 1fr; } .layout-frame-row { grid-template-columns: 1fr; } .layout-frame-preview { max-height: 180px; } }
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <div class="brand">
        <div class="brand-mark">PB</div>
        <div>
          <h1>Photobooth Admin</h1>
          <div class="subtitle">Giám sát AI và điều khiển Raspberry Pi</div>
        </div>
      </div>
      <a href="/docs" target="_blank" rel="noreferrer">API docs ↗</a>
    </header>

    <section class="toolbar">
      <div>
        <label for="deviceId">Device ID</label>
        <input id="deviceId" type="text" value="pi01" autocomplete="off">
      </div>
      <div>
        <label for="token">API token (nếu đã cấu hình)</label>
        <input id="token" type="password" placeholder="Để trống nếu không dùng token" autocomplete="off">
      </div>
      <button id="connectButton">Kết nối</button>
      <div class="connection"><span id="connectionDot" class="dot"></span><span id="connectionText">Chưa kết nối</span></div>
    </section>

    <section class="metrics">
      <article class="card metric">
        <div class="metric-title">Server</div>
        <div id="serverStatus" class="metric-value">—</div>
        <div id="serverUptime" class="metric-note">Đang chờ dữ liệu</div>
      </article>
      <article class="card metric">
        <div class="metric-title">AI model</div>
        <div id="aiStatus" class="metric-value">—</div>
        <div class="metric-note">Trạng thái bộ phân tích</div>
      </article>
      <article class="card metric">
        <div class="metric-title">MQTT broker</div>
        <div id="mqttStatus" class="metric-value">—</div>
        <div class="metric-note">Kết nối của Server tới broker</div>
      </article>
      <article class="card metric">
        <div class="metric-title">Thiết bị online</div>
        <div id="deviceCount" class="metric-value">—</div>
        <div id="deviceNote" class="metric-note">Trạng thái MQTT</div>
      </article>
      <article class="card metric">
        <div class="metric-title">FPS nhận diện</div>
        <div id="fpsValue" class="metric-value">—</div>
        <div id="fpsNote" class="metric-note">Frame Server xử lý mỗi giây</div>
      </article>
    </section>

    <section class="card camera-card">
      <div class="card-head">
        <div>
          <h2>Camera Pi</h2>
          <div class="muted" style="margin-top:6px">Frame mới nhất nhận từ Pi</div>
        </div>
        <span id="cameraBadge" class="live-badge">WAITING</span>
      </div>
      <div class="camera-view">
        <img id="cameraImage" alt="Khung hình camera Raspberry Pi" hidden>
        <canvas id="poseOverlay" aria-hidden="true"></canvas>
        <div id="cameraPlaceholder" class="camera-placeholder">Đang chờ frame từ Pi…</div>
        <div id="videoCaption" class="video-caption">Đang chờ kết quả nhận diện…</div>
      </div>
    </section>

    <main class="main-grid">
      <section class="card">
        <div class="card-head">
          <div>
            <h2>Kết quả nhận diện trực tiếp</h2>
            <div id="frameInfo" class="muted" style="margin-top:6px">Chưa nhận frame</div>
          </div>
          <span id="poseStatus" class="status-pill">Đang chờ Pi</span>
        </div>

        <div class="score-row">
          <div><div id="poseScore" class="score">—<small>%</small></div><div class="muted" style="margin-top:6px">Độ tin cậy gesture</div></div>
          <div id="readyState" class="ready">Chưa sẵn sàng chụp</div>
        </div>
        <div class="progress"><span id="scoreBar"></span></div>

        <div class="stats">
          <div class="stat"><strong id="keypointCount">—</strong><span>Gesture được chọn</span></div>
          <div class="stat"><strong id="handCount">—</strong><span>Bàn tay</span></div>
          <div class="stat"><strong id="processingTime">—</strong><span>Thời gian AI (ms)</span></div>
        </div>

        <div class="section-label">Trạng thái điều khiển</div>
        <div id="feedback" class="feedback"><div class="empty">Chưa có kết quả.</div></div>
        <div class="section-label">Gesture</div>
        <div id="gestures" class="gestures"><div class="empty">Chưa có dữ liệu.</div></div>
        <details>
          <summary id="keypointSummary">Chi tiết landmarks bàn tay</summary>
          <div id="keypoints" class="keypoints"></div>
        </details>
        <div id="templateNotice" class="notice" hidden></div>
      </section>

      <aside class="card">
        <div class="card-head">
          <div>
            <h2>Điều khiển thiết bị</h2>
            <div id="sessionInfo" class="muted" style="margin-top:6px">Chưa có session hoạt động</div>
          </div>
          <span id="sessionStatus" class="status-pill">—</span>
        </div>

        <div class="control">
          <div class="control-title">Độ sáng LED</div>
          <div class="slider-row">
            <input id="brightness" type="range" min="0" max="100" step="1" value="50">
            <output id="brightnessValue">50%</output>
          </div>
          <div class="button-row"><button id="ledButton">Gửi lệnh LED</button></div>
          <div id="ledMessage" class="action-message" aria-live="polite"></div>
        </div>

        <div class="control">
          <div class="control-title">Chụp ảnh</div>
          <div class="muted">Gửi lệnh chụp tới Pi trong session hiện tại.</div>
          <div class="button-row"><button id="captureButton" class="secondary" disabled>Yêu cầu chụp</button></div>
          <div id="captureMessage" class="action-message" aria-live="polite"></div>
        </div>

        <div class="control">
          <div class="card-head">
            <div>
              <div id="sequenceTitle" class="control-title">Chụp liên hoàn 8 ảnh</div>
              <div id="sequenceDescription" class="muted">Server đếm ngược 10 giây trước mỗi ảnh và lưu ảnh gốc riêng.</div>
            </div>
            <span id="sequenceStatus" class="status-pill">Chưa chạy</span>
          </div>
          <div class="button-row">
            <button id="sequenceStartButton" disabled>Bắt đầu chụp bộ ảnh</button>
            <button id="sequenceCancelButton" class="secondary" disabled>Hủy bộ chụp</button>
          </div>
          <div id="sequenceMessage" class="action-message" aria-live="polite"></div>
          <div id="sequenceProgress" class="sequence-progress" aria-label="Tiến độ chụp"></div>
        </div>

        <div class="control">
          <div class="control-title">Sticker khuôn mặt</div>
          <label for="faceOverlaySelect">Overlay cho ảnh chụp</label>
          <select id="faceOverlaySelect" disabled>
            <option value="">Không dùng overlay</option>
          </select>
          <div id="faceOverlayMessage" class="action-message" aria-live="polite"></div>
        </div>
      </aside>
    </main>

    <section class="card gallery-card">
      <div class="card-head">
        <div>
          <h2 id="galleryTitle">Ảnh chụp trong session</h2>
          <div id="galleryStatus" class="muted" style="margin-top:6px">Chưa có ảnh trong session.</div>
        </div>
      </div>
      <div id="reviewActions" class="review-actions" hidden>
        <div id="reviewMessage" class="review-message"></div>
        <div id="reviewButtons" class="button-row">
          <button id="retakeButton" class="secondary">Chụp lại cả bộ (tối đa 1 lần)</button>
          <button id="continueReviewButton">Chốt bộ ảnh và tiếp tục</button>
        </div>
      </div>
      <div id="photoLayoutSection" class="photo-layout" hidden>
        <div class="layout-header">
          <div>
            <h2>Chọn khung, ảnh và hiệu ứng</h2>
            <div class="muted" style="margin-top:6px">Chọn khung 4 ô, xếp 4 ảnh theo thứ tự, rồi tùy chỉnh riêng filter và sticker cho từng ô.</div>
          </div>
        </div>
        <div class="layout-frame-row">
          <div>
            <label for="layoutFrameSelect">Mẫu khung</label>
            <select id="layoutFrameSelect"></select>
            <div id="layoutMessage" class="action-message" aria-live="polite"></div>
          </div>
          <img id="layoutFramePreview" class="layout-frame-preview" alt="Mẫu khung đang chọn">
        </div>
        <div id="photoLayoutSlots" class="layout-slots"></div>
        <div class="button-row">
          <button id="savePhotoLayoutButton">Lưu lựa chọn và tạo xem trước</button>
        </div>
        <img id="photoLayoutPreview" class="layout-preview" alt="Ảnh ghép xem trước" hidden>
      </div>
      <div id="photoGallery" class="photo-gallery"></div>
    </section>

    <section class="card history-card">
      <div class="card-head">
        <div>
          <h2>Lịch sử nhận diện gần đây</h2>
          <div class="muted" style="margin-top:6px">Hiển thị 12 kết quả mới nhất; Server giữ tối đa 50 kết quả trong bộ nhớ đến khi khởi động lại</div>
        </div>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Thời gian</th><th>Frame</th><th>Trạng thái</th><th>Confidence</th><th>Gesture</th><th>Filter / zoom</th><th>Hành động</th></tr></thead>
          <tbody id="historyRows"><tr><td colspan="7" class="empty">Chưa có kết quả.</td></tr></tbody>
        </table>
      </div>
    </section>

    <section class="card guide-card">
      <h2>Hướng dẫn sử dụng</h2>
      <div class="guide-grid">
        <div class="guide-item"><strong>1 · Bật hệ thống</strong>Khởi động Server, MQTT broker và chạy <code>python -m pi.main</code> trên Pi. Nhập Device ID, thường là <code>pi01</code>, rồi bấm Kết nối.</div>
        <div class="guide-item"><strong>2 · Bật điều khiển tay</strong>Đưa một bàn tay rõ vào khung hình và giữ lòng bàn tay mở vài nhịp đến khi trạng thái chuyển sang “Sẵn sàng”.</div>
        <div class="guide-item"><strong>3 · Điều khiển bằng gesture</strong>👍 giữ ngón cái để chụp sau đếm ngược; ✌ chuyển filter kế; ☝ chuyển filter trước; nắm tay hủy đếm ngược. Pinch bằng ngón cái–trỏ để zoom.</div>
      </div>
      <div class="notice">Giữ mỗi gesture khoảng 4 frame; confidence cần đạt 60%. Sau lệnh, thả tay ra rồi mới lặp lại. Nút web “Yêu cầu chụp” và nút vật lý (nếu đã nối) vẫn có thể chụp thủ công.</div>
    </section>
    <footer>Dữ liệu được làm mới định kỳ từ Server · Không cần cài thêm frontend package</footer>
  </div>

  <script>
    const $ = (id) => document.getElementById(id);
    const stateLabels = {
      inactive: ["Chưa bật điều khiển", ""],
      ready: ["Sẵn sàng", "good"],
      countdown: ["Đang đếm ngược", "warn"],
      capturing: ["Đang chụp", "warn"],
    };
    const gestureNames = {
      Open_Palm: "Bàn tay mở",
      Thumb_Up: "Giơ ngón cái",
      Victory: "Chữ V",
      Pointing_Up: "Giơ ngón trỏ",
      Closed_Fist: "Nắm tay",
      None: "Chưa xác định",
    };
    const handConnections = [
      [0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8],
      [5, 9], [9, 10], [10, 11], [11, 12], [9, 13], [13, 14], [14, 15],
      [15, 16], [13, 17], [17, 18], [18, 19], [19, 20], [0, 17],
    ];
    let token = "";
    let deviceId = "pi01";
    let pollTimer = null;
    let refreshing = false;
    let currentSession = null;
    let currentReview = null;
    let currentFrameUrl = null;
    let currentFrameKey = null;
    let lastRenderedResultKey = null;
    let latestGestureResult = null;
    let recentFrameTimes = [];
    let faceOverlayCatalogKey = "";
    let faceOverlayUpdating = false;
    let gallerySessionId = null;
    let lastGalleryRefresh = 0;
    let galleryRefreshing = false;
    let sequenceRequesting = false;
    let reviewRequesting = false;
    let latestAdminData = null;
    let photoLayoutEditorKey = "";
    let photoLayoutRequesting = false;
    let framePreviewObjectUrl = null;
    let photoLayoutPreviewObjectUrl = null;
    const photoObjectUrls = new Map();

    function setConnection(text, state) {
      $("connectionText").textContent = text;
      $("connectionDot").className = `dot ${state || ""}`;
    }

    function setPill(element, text, state) {
      element.textContent = text;
      element.className = `status-pill ${state || ""}`;
    }

    function addText(parent, className, text) {
      const item = document.createElement("div");
      item.className = className;
      item.textContent = text;
      parent.appendChild(item);
      return item;
    }

    async function api(path, options = {}) {
      const headers = new Headers(options.headers || {});
      if (token) headers.set("Authorization", `Bearer ${token}`);
      if (options.body) headers.set("Content-Type", "application/json");
      const response = await fetch(path, { ...options, headers, cache: "no-store" });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
      return body;
    }

    async function updateCameraFrame(result) {
      const frameKey = result ? `${result.session_id}:${result.frame_id}` : null;
      if (frameKey && frameKey === currentFrameKey) return;
      const headers = {};
      if (token) headers.Authorization = `Bearer ${token}`;
      const query = new URLSearchParams({ t: String(Date.now()) });
      if (result) query.set("frame_id", String(result.frame_id));
      const path = `/api/v1/admin/frame/${encodeURIComponent(deviceId)}?${query}`;
      const response = await fetch(path, { headers, cache: "no-store" });
      if (response.status === 404) {
        currentFrameKey = null;
        $("cameraImage").hidden = true;
        $("cameraPlaceholder").hidden = false;
        $("cameraPlaceholder").textContent = "Đang chờ frame từ Pi…";
        $("cameraBadge").classList.remove("active");
        $("cameraBadge").textContent = "WAITING";
        drawHandOverlay(null);
        return;
      }
      if (!response.ok) throw new Error(`Không tải được frame camera: HTTP ${response.status}`);
      const nextUrl = URL.createObjectURL(await response.blob());
      const previousUrl = currentFrameUrl;
      currentFrameUrl = nextUrl;
      currentFrameKey = frameKey;
      const image = $("cameraImage");
      image.onload = () => {
        if (previousUrl) URL.revokeObjectURL(previousUrl);
        drawHandOverlay(latestGestureResult);
      };
      image.src = nextUrl;
      image.hidden = false;
      $("cameraPlaceholder").hidden = true;
      $("cameraBadge").classList.add("active");
      $("cameraBadge").textContent = "LIVE";
    }

    function drawHandOverlay(result) {
      const canvas = $("poseOverlay");
      const image = $("cameraImage");
      const bounds = canvas.parentElement.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.round(bounds.width * ratio));
      canvas.height = Math.max(1, Math.round(bounds.height * ratio));
      const context = canvas.getContext("2d");
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, bounds.width, bounds.height);
      if (!result || !image.naturalWidth) return;

      const scale = Math.min(
        bounds.width / image.naturalWidth,
        bounds.height / image.naturalHeight,
      );
      const offsetX = (bounds.width - image.naturalWidth * scale) / 2;
      const offsetY = (bounds.height - image.naturalHeight * scale) / 2;
      const hands = result.gestures || [];
      const color = result.control_active ? "#34d399" : "#22d3ee";
      context.lineWidth = 2.5;
      context.lineCap = "round";
      context.strokeStyle = color;
      context.shadowColor = color;
      context.shadowBlur = 7;
      for (const hand of hands) {
        const points = hand.landmarks || [];
        for (const [startIndex, endIndex] of handConnections) {
          const start = points[startIndex];
          const end = points[endIndex];
          if (!start || !end) continue;
          context.beginPath();
          context.moveTo(
            offsetX + start[0] * image.naturalWidth * scale,
            offsetY + start[1] * image.naturalHeight * scale,
          );
          context.lineTo(
            offsetX + end[0] * image.naturalWidth * scale,
            offsetY + end[1] * image.naturalHeight * scale,
          );
          context.stroke();
        }
        context.shadowBlur = 5;
        for (const point of points) {
          context.beginPath();
          context.arc(
            offsetX + point[0] * image.naturalWidth * scale,
            offsetY + point[1] * image.naturalHeight * scale,
            3,
            0,
            Math.PI * 2,
          );
          context.fillStyle = color;
          context.fill();
        }
      }
    }

    function renderHistory(history) {
      const rows = $("historyRows");
      rows.replaceChildren();
      const items = (history || []).slice(-12).reverse();
      if (!items.length) {
        const row = document.createElement("tr");
        const cell = document.createElement("td");
        cell.colSpan = 7;
        cell.className = "empty";
        cell.textContent = "Chưa có kết quả.";
        row.appendChild(cell);
        rows.appendChild(row);
        return;
      }
      for (const snapshot of items) {
        const result = snapshot.result || {};
        const row = document.createElement("tr");
        const values = [
          new Date(snapshot.received_at * 1000).toLocaleTimeString(),
          `#${result.frame_id ?? "—"}`,
          stateLabels[result.control_state]?.[0] || result.control_state || "—",
          `${Math.round((result.selected_gesture_score || 0) * 100)}%`,
          (result.gestures || []).map((item) => gestureNames[item.gesture] || item.gesture || "Không rõ").join(", ") || "—",
          `${result.selected_effect_id || "original"} · ${Number(result.zoom_factor || 1).toFixed(2)}×`,
          result.last_action || "—",
        ];
        for (const value of values) {
          const cell = document.createElement("td");
          cell.textContent = value;
          row.appendChild(cell);
        }
        rows.appendChild(row);
      }
    }

    function renderFaceOverlays(data, session) {
      const overlays = Array.isArray(data.face_overlays) ? data.face_overlays : [];
      const signature = JSON.stringify(overlays);
      const select = $("faceOverlaySelect");
      if (signature !== faceOverlayCatalogKey) {
        faceOverlayCatalogKey = signature;
        select.replaceChildren(new Option("Không dùng overlay", ""));
        for (const overlay of overlays) {
          select.add(new Option(overlay.name, overlay.overlay_id));
        }
      }

      const modelAvailable = Boolean(data.face_overlay_model_available);
      select.disabled = faceOverlayUpdating || !session || !modelAvailable || !overlays.length;
      if (!faceOverlayUpdating) {
        select.value = session?.face_overlay_id || "";
      }
      if (!modelAvailable) {
        $("faceOverlayMessage").textContent =
          data.face_overlay_model_error || "Face Landmarker chưa sẵn sàng.";
      } else if (!overlays.length) {
        $("faceOverlayMessage").textContent =
          "Chưa có sticker. Thêm PNG RGBA và metadata vào assets/photo_effects/face_overlays rồi khởi động lại Server.";
      } else if (!session) {
        $("faceOverlayMessage").textContent = "Cần có session hoạt động để chọn sticker.";
      } else {
        $("faceOverlayMessage").textContent =
          "Sticker chỉ ghép vào ảnh chụp, không vẽ lên live preview.";
      }
    }

    function clearGallery() {
      for (const objectUrl of photoObjectUrls.values()) URL.revokeObjectURL(objectUrl);
      photoObjectUrls.clear();
      $("photoGallery").replaceChildren();
    }

    async function refreshGallery() {
      if (galleryRefreshing) return;
      const sessionId = currentSession?.session_id || null;
      if (sessionId !== gallerySessionId) {
        clearGallery();
        gallerySessionId = sessionId;
        lastGalleryRefresh = 0;
      }
      if (!sessionId) {
        $("galleryStatus").textContent = "Chưa có session hoạt động.";
        return;
      }
      if (Date.now() - lastGalleryRefresh < 1000) return;

      galleryRefreshing = true;
      lastGalleryRefresh = Date.now();
      try {
        const photos = await api(
          `/api/v1/photos?session_id=${encodeURIComponent(sessionId)}`,
        );
        const reviewBatchId = currentReview?.batch_id;
        const reviewPhotos = reviewBatchId
          ? photos.filter((photo) => photo.capture_batch_id === reviewBatchId)
          : photos;
        const recentPhotos = reviewBatchId
          ? reviewPhotos.sort((first, second) =>
              (first.sequence_number || 0) - (second.sequence_number || 0),
            )
          : reviewPhotos.slice(0, 8);
        renderPhotoLayoutEditor(latestAdminData, recentPhotos);
        for (const photo of recentPhotos) {
          if (photoObjectUrls.has(photo.photo_id)) continue;
          const headers = {};
          if (token) headers.Authorization = `Bearer ${token}`;
          const response = await fetch(
            `/api/v1/photos/${encodeURIComponent(photo.photo_id)}`,
            { headers, cache: "no-store" },
          );
          if (!response.ok) {
            throw new Error(`Không tải được ảnh ${photo.photo_id}: HTTP ${response.status}`);
          }
          photoObjectUrls.set(photo.photo_id, URL.createObjectURL(await response.blob()));
        }

        const visibleIds = new Set(recentPhotos.map((photo) => photo.photo_id));
        for (const [photoId, objectUrl] of photoObjectUrls) {
          if (!visibleIds.has(photoId)) {
            URL.revokeObjectURL(objectUrl);
            photoObjectUrls.delete(photoId);
          }
        }
        const gallery = $("photoGallery");
        gallery.replaceChildren();
        if (!recentPhotos.length) {
          $("galleryStatus").textContent = "Chưa có ảnh trong session. Chụp từ Admin, gesture hoặc nút Pi.";
          addText(gallery, "empty", "Ảnh chụp mới sẽ xuất hiện ở đây.");
          return;
        }

        $("galleryStatus").textContent = reviewBatchId
          ? `${recentPhotos.length} ảnh của bộ đang được xem trước`
          : `${recentPhotos.length} ảnh gần nhất · tự làm mới mỗi giây`;
        for (const photo of recentPhotos) {
          const card = document.createElement("article");
          card.className = "photo-card";
          const link = document.createElement("a");
          link.href = photoObjectUrls.get(photo.photo_id);
          link.target = "_blank";
          link.rel = "noreferrer";
          const image = document.createElement("img");
          image.src = photoObjectUrls.get(photo.photo_id);
          image.alt = `Ảnh chụp ${photo.photo_id}`;
          link.appendChild(image);

          const info = document.createElement("div");
          info.className = "photo-card-info";
          const title = document.createElement("strong");
          title.textContent = new Date(photo.timestamp * 1000).toLocaleString();
          const effect = document.createElement("div");
          effect.textContent = photo.is_raw
            ? `Ảnh gốc · lượt ${photo.sequence_number || "—"}`
            : `${photo.effect_id || "original"} · ${Number(photo.zoom_factor || 1).toFixed(2)}×`;
          const overlay = document.createElement("div");
          overlay.textContent = photo.face_overlay_applied
            ? `${photo.face_overlay_id} · ${photo.face_count} khuôn mặt`
            : photo.face_overlay_id
              ? `${photo.face_overlay_id} · không tìm thấy khuôn mặt`
              : "Không dùng overlay";
          info.append(title, effect, overlay);
          if (photo.raw_available) {
            const download = document.createElement("button");
            download.className = "secondary raw-download";
            download.textContent = "Tải ảnh gốc";
            download.addEventListener("click", async () => {
              const headers = {};
              if (token) headers.Authorization = `Bearer ${token}`;
              try {
                const response = await fetch(
                  `/api/v1/photos/${encodeURIComponent(photo.photo_id)}/raw`,
                  { headers, cache: "no-store" },
                );
                if (!response.ok) {
                  throw new Error(`HTTP ${response.status}`);
                }
                const url = URL.createObjectURL(await response.blob());
                const link = document.createElement("a");
                link.href = url;
                const disposition = response.headers.get("content-disposition") || "";
                const filename = /filename="([^"]+)"/i.exec(disposition)?.[1];
                link.download = filename || `raw_${photo.photo_id}`;
                link.click();
                setTimeout(() => URL.revokeObjectURL(url), 1000);
              } catch (error) {
                $("galleryStatus").textContent = `Không tải được ảnh gốc: ${error.message}`;
              }
            });
            info.appendChild(download);
          }
          card.append(link, info);
          gallery.appendChild(card);
        }
      } catch (error) {
        $("galleryStatus").textContent = `Lỗi tải thư viện ảnh: ${error.message}`;
      } finally {
        galleryRefreshing = false;
      }
    }

    function renderCaptureSequence(batch, session, mqttConnected, review) {
      const active = batch && ["countdown", "capturing"].includes(batch.status);
      $("sequenceStartButton").disabled =
        !session || !mqttConnected || active || Boolean(review) || sequenceRequesting;
      $("sequenceCancelButton").disabled = !active || sequenceRequesting;
      $("captureButton").disabled = !session || active || Boolean(review);

      const statusLabels = {
        countdown: ["Đang đếm ngược", "warn"],
        capturing: ["Đang chụp", "warn"],
        completed: ["Hoàn thành", "good"],
        failed: ["Thất bại", "bad"],
        cancelled: ["Đã hủy", ""],
        interrupted: ["Bị gián đoạn", "bad"],
      };
      const [statusText, statusClass] = statusLabels[batch?.status] || ["Chưa chạy", ""];
      setPill($("sequenceStatus"), statusText, statusClass);

      const progress = $("sequenceProgress");
      progress.replaceChildren();
      if (!batch) {
        $("sequenceMessage").textContent = session
          ? "Chưa có bộ ảnh nào trong session này."
          : "Bắt đầu session trên Pi để chụp bộ ảnh.";
        return;
      }

      const shots = new Map((batch.shots || []).map((shot) => [shot.shot_number, shot]));
      const completed = (batch.shots || []).filter((shot) => shot.status === "completed").length;
      for (let number = 1; number <= batch.target_count; number += 1) {
        const shot = shots.get(number);
        const tile = document.createElement("div");
        const isCurrent = number === batch.current_shot && active;
        const tileClass = shot?.status === "completed"
          ? "good"
          : shot?.status === "failed"
            ? "bad"
            : isCurrent
              ? "warn"
              : "";
        tile.className = `sequence-shot ${tileClass}`;
        const detail = shot?.status === "completed"
          ? "Đã lưu"
          : shot?.status === "failed"
            ? "Lỗi"
            : isCurrent && batch.status === "countdown"
              ? "Đếm ngược"
              : isCurrent && batch.status === "capturing"
                ? "Đang chụp"
                : "Chờ";
        tile.textContent = `Ảnh ${String(number).padStart(2, "0")} · ${detail}`;
        progress.appendChild(tile);
      }

      let detail = `${completed}/${batch.target_count} ảnh gốc đã lưu`;
      if (batch.status === "countdown" && batch.next_shot_at) {
        const remaining = Math.max(0, Math.ceil(Number(batch.next_shot_at) - Date.now() / 1000));
        detail += ` · ảnh ${batch.current_shot} sau ${remaining} giây`;
      } else if (batch.status === "capturing") {
        detail += ` · đang chờ ảnh ${batch.current_shot} từ Pi`;
      }
      if (batch.last_error) detail += ` · ${batch.last_error}`;
      $("sequenceMessage").textContent = detail;
    }

    function renderCaptureReview(review, session) {
      currentReview = review || null;
      $("galleryTitle").textContent = review
        ? ["accepted", "timed_out"].includes(review.status)
          ? "Bộ ảnh đã chốt"
          : "Xem trước bộ ảnh"
        : "Ảnh chụp trong session";
      $("reviewActions").hidden = !review || !session;
      if (!review || !session) return;

      const pending = review.status === "pending";
      const retakeInProgress = review.status === "retake_started";
      $("reviewButtons").hidden = !pending;
      $("retakeButton").disabled =
        !pending || review.retake_used || reviewRequesting;
      $("continueReviewButton").disabled = !pending || reviewRequesting;

      if (pending) {
        const remaining = Math.max(
          0,
          Math.ceil(Number(review.decision_deadline) - Date.now() / 1000),
        );
        const retakeText = review.retake_used
          ? "Bạn đã sử dụng lượt chụp lại."
          : "Bạn còn tối đa một lượt chụp lại.";
        $("reviewMessage").textContent =
          `${retakeText} Tự động chốt bộ ảnh sau ${remaining} giây nếu không chọn.`;
      } else if (retakeInProgress) {
        $("reviewMessage").textContent =
          "Đang chụp lại bộ ảnh. Sau khi hoàn tất, bạn sẽ có thời gian xem trước và chốt bộ ảnh.";
      } else if (review.status === "timed_out") {
        $("reviewMessage").textContent =
          "Đã hết thời gian và tự động chốt bộ ảnh. Hãy chọn 4 ảnh, khung và hiệu ứng bên dưới.";
      } else {
        $("reviewMessage").textContent =
          "Đã chốt bộ ảnh. Hãy chọn 4 ảnh, khung và hiệu ứng bên dưới.";
      }
    }

    function renderFps(history) {
      if (history) {
        recentFrameTimes = history
          .map((snapshot) => Number(snapshot.received_at))
          .filter(Number.isFinite);
      }

      const latest = recentFrameTimes[recentFrameTimes.length - 1];
      if (latest == null) {
        $("fpsValue").textContent = "—";
        $("fpsNote").textContent = "Chờ nhận frame từ Pi";
        return;
      }

      const age = Date.now() / 1000 - latest;
      if (age > 2) {
        $("fpsValue").textContent = "0.0";
        $("fpsNote").textContent = "Không nhận frame mới";
        return;
      }

      const samples = recentFrameTimes.filter((timestamp) => timestamp >= latest - 1.5);
      if (samples.length < 2) {
        $("fpsValue").textContent = "—";
        $("fpsNote").textContent = "Đang đo tốc độ xử lý";
        return;
      }

      const elapsed = samples[samples.length - 1] - samples[0];
      const fps = elapsed > 0 ? (samples.length - 1) / elapsed : 0;
      $("fpsValue").textContent = fps.toFixed(1);
      $("fpsNote").textContent = "Frame Server xử lý mỗi giây";
    }

    function renderPhotoLayoutEditor(data, photos) {
      const section = $("photoLayoutSection");
      const review = data?.capture_review;
      const session = data?.active_session;
      const ready = Boolean(
        session && review && ["accepted", "timed_out"].includes(review.status),
      );
      section.hidden = !ready;
      if (!ready) {
        photoLayoutEditorKey = "";
        return;
      }

      const rawPhotos = photos
        .filter((photo) => photo.is_raw && photo.capture_batch_id === review.batch_id)
        .sort((first, second) => first.sequence_number - second.sequence_number);
      if (rawPhotos.length < 4) {
        $("layoutMessage").textContent = "Cần ít nhất 4 ảnh gốc trong bộ đã chốt để chọn khung.";
        $("savePhotoLayoutButton").disabled = true;
        return;
      }

      const editorKey = `${session.session_id}:${review.batch_id}`;
      if (editorKey === photoLayoutEditorKey) return;
      photoLayoutEditorKey = editorKey;
      $("savePhotoLayoutButton").disabled = false;
      $("layoutMessage").textContent = "Ảnh sẽ được crop vừa từng ô; bản gốc vẫn được giữ nguyên.";

      const templates = data.frame_templates || [];
      const frameSelect = $("layoutFrameSelect");
      frameSelect.replaceChildren();
      for (const template of templates) {
        frameSelect.add(new Option(template.name, template.frame_id));
      }
      const saved = data.photo_layout?.batch_id === review.batch_id
        ? data.photo_layout
        : null;
      const selectedFrame = templates.find(
        (template) => template.frame_id === saved?.frame_id,
      ) || templates[0];
      if (!selectedFrame) {
        $("layoutMessage").textContent = "Server chưa tải được mẫu khung nào.";
        $("savePhotoLayoutButton").disabled = true;
        return;
      }
      frameSelect.value = selectedFrame.frame_id;
      frameSelect.onchange = () => loadFrameTemplatePreview(frameSelect.value);
      loadFrameTemplatePreview(selectedFrame.frame_id);

      const slotContainer = $("photoLayoutSlots");
      slotContainer.replaceChildren();
      const effects = data.effects || [];
      const overlays = data.face_overlays || [];
      const firstFour = rawPhotos.slice(0, 4);
      for (let index = 0; index < 4; index += 1) {
        const savedSlot = saved?.slots?.[index];
        const card = document.createElement("article");
        card.className = "layout-slot";
        const heading = document.createElement("h3");
        heading.textContent = `Ô ${index + 1}`;

        const photoSelect = document.createElement("select");
        photoSelect.className = "layout-photo";
        photoSelect.setAttribute("aria-label", `Ảnh ở ô ${index + 1}`);
        for (const photo of rawPhotos) {
          photoSelect.add(
            new Option(
              `Ảnh ${String(photo.sequence_number).padStart(2, "0")}`,
              photo.photo_id,
            ),
          );
        }
        photoSelect.value = rawPhotos.some(
          (photo) => photo.photo_id === savedSlot?.photo_id,
        ) ? savedSlot.photo_id : firstFour[index].photo_id;

        const effectLabel = document.createElement("label");
        effectLabel.textContent = "Filter màu";
        const effectSelect = document.createElement("select");
        effectSelect.className = "layout-effect";
        effectSelect.setAttribute("aria-label", `Filter màu ô ${index + 1}`);
        for (const effect of effects) {
          effectSelect.add(new Option(effect.name, effect.effect_id));
        }
        effectSelect.value = effects.some(
          (effect) => effect.effect_id === savedSlot?.effect_id,
        ) ? savedSlot.effect_id : "original";

        const overlayLabel = document.createElement("label");
        overlayLabel.textContent = "Sticker khuôn mặt";
        const overlaySelect = document.createElement("select");
        overlaySelect.className = "layout-overlay";
        overlaySelect.setAttribute("aria-label", `Sticker khuôn mặt ô ${index + 1}`);
        overlaySelect.add(new Option("Không dùng sticker", ""));
        for (const overlay of overlays) {
          overlaySelect.add(new Option(overlay.name, overlay.overlay_id));
        }
        overlaySelect.value = overlays.some(
          (overlay) => overlay.overlay_id === savedSlot?.face_overlay_id,
        ) ? savedSlot.face_overlay_id : "";
        overlaySelect.disabled =
          !data.face_overlay_model_available || overlays.length === 0;

        const photoLabel = document.createElement("label");
        photoLabel.textContent = "Ảnh trong ô";
        card.append(
          heading,
          photoLabel,
          photoSelect,
          effectLabel,
          effectSelect,
          overlayLabel,
          overlaySelect,
        );
        slotContainer.appendChild(card);
      }
      $("photoLayoutPreview").hidden = true;
      if (saved) {
        $("layoutMessage").textContent = "Đã lưu bố cục trước đó; đang tải ảnh xem trước.";
        refreshPhotoLayoutPreview(session.session_id);
      }
    }

    async function loadFrameTemplatePreview(frameId) {
      if (!frameId) return;
      try {
        const headers = {};
        if (token) headers.Authorization = `Bearer ${token}`;
        const response = await fetch(
          `/api/v1/photo-frames/${encodeURIComponent(frameId)}`,
          { headers, cache: "no-store" },
        );
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const nextUrl = URL.createObjectURL(await response.blob());
        if (framePreviewObjectUrl) URL.revokeObjectURL(framePreviewObjectUrl);
        framePreviewObjectUrl = nextUrl;
        $("layoutFramePreview").src = nextUrl;
      } catch (error) {
        $("layoutMessage").textContent = `Không tải được mẫu khung: ${error.message}`;
      }
    }

    async function refreshPhotoLayoutPreview(sessionId) {
      try {
        const headers = {};
        if (token) headers.Authorization = `Bearer ${token}`;
        const response = await fetch(
          `/api/v1/sessions/${encodeURIComponent(sessionId)}/photo-layout/preview`,
          { headers, cache: "no-store" },
        );
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(body.detail || `HTTP ${response.status}`);
        }
        const nextUrl = URL.createObjectURL(await response.blob());
        if (photoLayoutPreviewObjectUrl) {
          URL.revokeObjectURL(photoLayoutPreviewObjectUrl);
        }
        photoLayoutPreviewObjectUrl = nextUrl;
        $("photoLayoutPreview").src = nextUrl;
        $("photoLayoutPreview").hidden = false;
        return true;
      } catch (error) {
        $("layoutMessage").textContent = `Không tạo được ảnh xem trước: ${error.message}`;
        return false;
      }
    }

    function render(data) {
      latestAdminData = data;
      const health = data.health || {};
      $("serverStatus").textContent = health.status === "ok" ? "Hoạt động" : "Cần kiểm tra";
      $("serverUptime").textContent = `Uptime ${Math.floor(health.uptime_sec || 0)} giây`;
      $("aiStatus").textContent = health.ai_available ? "Sẵn sàng" : "Không khả dụng";
      $("mqttStatus").textContent = health.mqtt_connected ? "Đã kết nối" : "Mất kết nối";
      $("deviceCount").textContent = String(health.connected_devices ?? 0);
      renderFps(data.result_history || []);

      const session = data.active_session;
      currentSession = session;
      renderFaceOverlays(data, session);
      renderCaptureReview(data.capture_review, session);
      const sequenceConfig = data.capture_sequence_config || {};
      $("sequenceTitle").textContent =
        `Chụp liên hoàn ${sequenceConfig.photo_count || 8} ảnh`;
      $("sequenceDescription").textContent =
        `Server đếm ngược ${sequenceConfig.countdown_sec || 10} giây trước mỗi ảnh và lưu ảnh gốc riêng.`;
      $("sessionInfo").textContent = session
        ? `Session ${session.session_id.slice(0, 8)} · ${session.effect_id || "original"} · ${Number(session.zoom_factor || 1).toFixed(2)}×`
        : "Chưa có session hoạt động";
      setPill($("sessionStatus"), session ? "ACTIVE" : "NO SESSION", session ? "good" : "");
      renderCaptureSequence(
        data.capture_sequence,
        session,
        Boolean(health.mqtt_connected),
        data.capture_review,
      );

      const snapshot = data.latest_result;
      const result = snapshot && snapshot.result;
      latestGestureResult = result;
      const resultKey = result ? `${result.session_id}:${result.frame_id}` : null;
      const newResult = resultKey !== lastRenderedResultKey;
      if (newResult) {
        renderHistory(data.result_history);
        lastRenderedResultKey = resultKey;
      }

      $("deviceNote").textContent = snapshot
        ? `Frame mới lúc ${new Date(snapshot.received_at * 1000).toLocaleTimeString()}`
        : "Chưa nhận frame từ thiết bị";
      if (!result) {
        if (!newResult) return;
        $("frameInfo").textContent = "Chưa nhận frame";
        setPill($("poseStatus"), "Đang chờ Pi", "");
        $("poseScore").innerHTML = "—<small>%</small>";
        $("scoreBar").style.width = "0%";
        $("readyState").textContent = "Đang chờ kết quả gesture";
        $("keypointCount").textContent = "—";
        $("handCount").textContent = "—";
        $("processingTime").textContent = "—";
        $("feedback").replaceChildren(addText(document.createElement("div"), "empty", "Giơ bàn tay mở để bật điều khiển."));
        $("gestures").replaceChildren(addText(document.createElement("div"), "empty", "Chưa có dữ liệu."));
        $("keypoints").replaceChildren();
        $("videoCaption").textContent = "Đang chờ kết quả nhận diện…";
        drawHandOverlay(null);
        return;
      }
      if (!newResult) return;

      $("frameInfo").textContent = `Session ${result.session_id.slice(0, 8)} · Frame #${result.frame_id}`;
      const [statusText, statusClass] = stateLabels[result.control_state] || [result.control_state, ""];
      setPill($("poseStatus"), statusText, statusClass);
      const score = Math.max(0, Math.min(100, Math.round((Number(result.selected_gesture_score) || 0) * 100)));
      const effectName = (data.effects || []).find((item) => item.effect_id === result.selected_effect_id)?.name || result.selected_effect_id;
      $("videoCaption").textContent = [
        statusText,
        result.selected_gesture ? `${gestureNames[result.selected_gesture] || result.selected_gesture} ${score}%` : "",
        result.control_state === "countdown" ? `Chụp sau ${result.countdown_remaining}` : "",
        `Filter: ${effectName}`,
        `Zoom ${Number(result.zoom_factor || 1).toFixed(2)}×`,
      ].filter(Boolean).join(" · ");
      $("cameraImage").style.transform = `scale(${Number(result.zoom_factor || 1)})`;
      $("poseOverlay").style.transform = `scale(${Number(result.zoom_factor || 1)})`;
      $("poseScore").innerHTML = `${score}<small>%</small>`;
      $("scoreBar").style.width = `${score}%`;
      $("readyState").textContent = result.last_action || "Đang theo dõi cử chỉ";
      $("readyState").style.color = result.control_active ? "#6ee7b7" : "#94a3b8";
      $("keypointCount").textContent = result.selected_gesture
        ? (gestureNames[result.selected_gesture] || result.selected_gesture)
        : "—";
      $("handCount").textContent = String(result.hand_count || 0);
      $("processingTime").textContent = Number(result.processing_ms || 0).toFixed(1);

      const feedback = $("feedback");
      feedback.replaceChildren();
      addText(feedback, "feedback-item", result.last_action || "Đang chờ cử chỉ");
      if (result.control_state === "countdown")
        addText(feedback, "feedback-item", `Chụp sau ${result.countdown_remaining} giây · nắm tay để hủy`);

      const gestures = $("gestures");
      gestures.replaceChildren();
      if (result.gestures?.length) {
        for (const item of result.gestures) {
          const name = gestureNames[item.gesture] || item.gesture || "Không xác định";
          const confidence = item.score == null ? "" : ` · ${(item.score * 100).toFixed(0)}%`;
          addText(gestures, "feedback-item", `${item.handedness || "Tay"}: ${name}${confidence}`);
        }
      } else {
        addText(gestures, "empty", "Chưa nhận diện gesture.");
      }

      const keypoints = $("keypoints");
      keypoints.replaceChildren();
      const selectedHand = (result.gestures || []).find(
        (item) => item.gesture === result.selected_gesture,
      );
      $("keypointSummary").textContent = `Chi tiết landmarks bàn tay (${selectedHand?.landmarks?.length || 0})`;
      for (const [index, point] of (selectedHand?.landmarks || []).entries()) {
        const row = document.createElement("div");
        row.className = "point";
        const name = document.createElement("span");
        name.textContent = `Landmark ${index}`;
        const coords = document.createElement("span");
        coords.textContent = `x ${Number(point[0]).toFixed(2)}, y ${Number(point[1]).toFixed(2)}`;
        row.append(name, coords);
        keypoints.appendChild(row);
      }

      const notice = $("templateNotice");
      notice.hidden = false;
      notice.textContent = "Open_Palm bật điều khiển · Thumb_Up chụp · Victory filter kế · Pointing_Up filter trước · Closed_Fist hủy đếm ngược · Pinch để zoom.";
    }

    async function refresh() {
      if (refreshing) return;
      refreshing = true;
      try {
        const query = new URLSearchParams({ device_id: deviceId });
        const data = await api(`/api/v1/admin/state?${query}`);
        render(data);
        await updateCameraFrame(data.latest_result?.result || null);
        await refreshGallery();
        setConnection("Đang cập nhật", "good");
      } catch (error) {
        renderFps();
        setConnection(error.message, "bad");
      } finally {
        refreshing = false;
      }
    }

    $("connectButton").addEventListener("click", async () => {
      token = $("token").value.trim();
      deviceId = $("deviceId").value.trim() || "pi01";
      if (pollTimer) clearInterval(pollTimer);
      await refresh();
      pollTimer = setInterval(refresh, 200);
    });

    $("brightness").addEventListener("input", (event) => {
      $("brightnessValue").textContent = `${event.target.value}%`;
    });

    $("ledButton").addEventListener("click", async () => {
      try {
        const result = await api(`/api/v1/devices/${encodeURIComponent(deviceId)}/led`, {
          method: "POST",
          body: JSON.stringify({ brightness: Number($("brightness").value) }),
        });
        $("ledMessage").textContent = `Lệnh đã gửi · ${result.command_id}`;
      } catch (error) {
        $("ledMessage").textContent = `Không gửi được lệnh: ${error.message}`;
      }
    });

    $("captureButton").addEventListener("click", async () => {
      if (!currentSession || $("captureButton").disabled) return;
      try {
        const result = await api(`/api/v1/sessions/${encodeURIComponent(currentSession.session_id)}/capture`, {
          method: "POST",
        });
        $("captureMessage").textContent = `Lệnh chụp đã gửi · ${result.command_id}`;
      } catch (error) {
        $("captureMessage").textContent = `Không gửi được lệnh: ${error.message}`;
      }
    });

    $("sequenceStartButton").addEventListener("click", async () => {
      if (!currentSession || sequenceRequesting) return;
      sequenceRequesting = true;
      $("sequenceStartButton").disabled = true;
      try {
        await api(
          `/api/v1/sessions/${encodeURIComponent(currentSession.session_id)}/capture-sequence`,
          { method: "POST" },
        );
        $("sequenceMessage").textContent = "Đã bắt đầu chụp bộ ảnh.";
      } catch (error) {
        $("sequenceMessage").textContent = `Không bắt đầu được: ${error.message}`;
      } finally {
        sequenceRequesting = false;
        await refresh();
      }
    });

    $("sequenceCancelButton").addEventListener("click", async () => {
      if (!currentSession || sequenceRequesting) return;
      sequenceRequesting = true;
      $("sequenceCancelButton").disabled = true;
      try {
        await api(
          `/api/v1/sessions/${encodeURIComponent(currentSession.session_id)}/capture-sequence/cancel`,
          { method: "POST" },
        );
        $("sequenceMessage").textContent = "Đã yêu cầu hủy bộ chụp.";
      } catch (error) {
        $("sequenceMessage").textContent = `Không hủy được: ${error.message}`;
      } finally {
        sequenceRequesting = false;
        await refresh();
      }
    });

    $("retakeButton").addEventListener("click", async () => {
      if (!currentSession || !currentReview || reviewRequesting) return;
      reviewRequesting = true;
      $("retakeButton").disabled = true;
      try {
        await api(
          `/api/v1/sessions/${encodeURIComponent(currentSession.session_id)}/capture-sequence/retake`,
          { method: "POST" },
        );
        $("reviewMessage").textContent = "Đã bắt đầu lượt chụp lại.";
      } catch (error) {
        $("reviewMessage").textContent = `Không bắt đầu được: ${error.message}`;
      } finally {
        reviewRequesting = false;
        await refresh();
      }
    });

    $("continueReviewButton").addEventListener("click", async () => {
      if (!currentSession || !currentReview || reviewRequesting) return;
      reviewRequesting = true;
      $("continueReviewButton").disabled = true;
      try {
        await api(
          `/api/v1/sessions/${encodeURIComponent(currentSession.session_id)}/capture-review/continue`,
          { method: "POST" },
        );
      } catch (error) {
        $("reviewMessage").textContent = `Không chốt được bộ ảnh: ${error.message}`;
      } finally {
        reviewRequesting = false;
        await refresh();
      }
    });

    $("savePhotoLayoutButton").addEventListener("click", async () => {
      if (!currentSession || !currentReview || photoLayoutRequesting) return;
      const slots = [...$("photoLayoutSlots").querySelectorAll(".layout-slot")];
      const payload = {
        frame_id: $("layoutFrameSelect").value,
        slots: slots.map((slot) => ({
          photo_id: slot.querySelector(".layout-photo").value,
          effect_id: slot.querySelector(".layout-effect").value,
          face_overlay_id: slot.querySelector(".layout-overlay").value || null,
        })),
      };
      if (new Set(payload.slots.map((slot) => slot.photo_id)).size !== 4) {
        $("layoutMessage").textContent = "Hãy chọn 4 ảnh khác nhau cho 4 ô.";
        return;
      }

      photoLayoutRequesting = true;
      $("savePhotoLayoutButton").disabled = true;
      $("layoutMessage").textContent = "Đang lưu lựa chọn và ghép ảnh xem trước…";
      try {
        await api(
          `/api/v1/sessions/${encodeURIComponent(currentSession.session_id)}/photo-layout`,
          { method: "PUT", body: JSON.stringify(payload) },
        );
        const previewed = await refreshPhotoLayoutPreview(currentSession.session_id);
        if (previewed) {
          $("layoutMessage").textContent =
            "Đã tạo ảnh xem trước. Ảnh gốc vẫn được giữ nguyên; chưa có file xuất hoặc QR.";
        }
      } catch (error) {
        $("layoutMessage").textContent = `Không lưu được bố cục: ${error.message}`;
      } finally {
        photoLayoutRequesting = false;
        $("savePhotoLayoutButton").disabled = false;
      }
    });

    $("faceOverlaySelect").addEventListener("change", async (event) => {
      if (!currentSession || faceOverlayUpdating) return;
      const sessionId = currentSession.session_id;
      const previousOverlayId = currentSession.face_overlay_id || "";
      faceOverlayUpdating = true;
      $("faceOverlaySelect").disabled = true;
      try {
        const updated = await api(
          `/api/v1/sessions/${encodeURIComponent(sessionId)}/face-overlay`,
          {
            method: "PUT",
            body: JSON.stringify({ overlay_id: event.target.value || null }),
          },
        );
        currentSession = updated;
        $("faceOverlayMessage").textContent = updated.face_overlay_id
          ? `Đã chọn overlay: ${updated.face_overlay_id}`
          : "Đã tắt overlay.";
      } catch (error) {
        $("faceOverlaySelect").value = previousOverlayId;
        $("faceOverlayMessage").textContent = `Không đổi được overlay: ${error.message}`;
      } finally {
        faceOverlayUpdating = false;
        await refresh();
      }
    });

    window.addEventListener("resize", () => drawHandOverlay(latestGestureResult));
  </script>
</body>
</html>
````

## File: Cuoi_ki/Server_Module/server/__init__.py
````python
"""
server/__init__.py
"""
````

## File: Cuoi_ki/Server_Module/server/ai.py
````python
"""MediaPipe hand-gesture inference for photobooth controls."""

import logging
import threading
import time
from pathlib import Path

import cv2
import numpy as np

from shared.config import PROJECT_ROOT, cfg
from shared.schemas import GesturePrediction

logger = logging.getLogger(__name__)


def _configured_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


class FrameAnalyzer:
    """Runs MediaPipe Gesture Recognizer and returns hand landmarks."""

    def __init__(self) -> None:
        settings = cfg.get("gesture", {})
        model_path = settings.get("model_path")
        self._lock = threading.Lock()
        self._recognizer = None
        self._media_pipe = None
        self._last_timestamp_ms = 0
        if not model_path:
            logger.warning("Gesture recognition model path is not configured")
            return

        path = _configured_path(str(model_path))
        if not path.is_file():
            logger.warning("Gesture recognition model not found: %s", path)
            return
        try:
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision

            options = vision.GestureRecognizerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=str(path)),
                running_mode=vision.RunningMode.VIDEO,
                num_hands=int(settings.get("num_hands", 2)),
                min_hand_presence_confidence=float(
                    settings.get("min_hand_presence_confidence", 0.4)
                ),
                min_tracking_confidence=float(
                    settings.get("min_tracking_confidence", 0.4)
                ),
            )
            self._recognizer = vision.GestureRecognizer.create_from_options(options)
            self._media_pipe = mp
            logger.info("Loaded gesture recognition model from %s", path)
        except (ImportError, OSError, RuntimeError, ValueError):
            logger.exception("Could not load gesture recognition model at %s", path)

    @property
    def available(self) -> bool:
        return self._recognizer is not None

    def close(self) -> None:
        with self._lock:
            if self._recognizer is not None:
                self._recognizer.close()
                self._recognizer = None

    def analyze(self, image_bytes: bytes) -> dict:
        started = time.perf_counter()
        image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Frame is not a valid JPEG or PNG image")
        if self._recognizer is None or self._media_pipe is None:
            return {
                "hand_count": 0,
                "gestures": [],
                "processing_ms": (time.perf_counter() - started) * 1000,
            }

        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        mp_image = self._media_pipe.Image(
            image_format=self._media_pipe.ImageFormat.SRGB,
            data=image_rgb,
        )
        with self._lock:
            timestamp_ms = max(
                self._last_timestamp_ms + 1,
                time.monotonic_ns() // 1_000_000,
            )
            self._last_timestamp_ms = timestamp_ms
            result = self._recognizer.recognize_for_video(mp_image, timestamp_ms)

        predictions = []
        for index, landmarks in enumerate(result.hand_landmarks):
            categories = result.gestures[index] if index < len(result.gestures) else []
            category = categories[0] if categories else None
            handedness = (
                result.handedness[index][0].category_name
                if index < len(result.handedness) and result.handedness[index]
                else None
            )
            world_points = (
                result.hand_world_landmarks[index]
                if index < len(result.hand_world_landmarks)
                else []
            )
            predictions.append(
                GesturePrediction(
                    hand_index=index,
                    gesture=category.category_name if category else None,
                    score=float(category.score) if category else None,
                    handedness=handedness,
                    landmarks=[(float(point.x), float(point.y)) for point in landmarks],
                    world_landmarks=[
                        (float(point.x), float(point.y), float(point.z))
                        for point in world_points
                    ],
                )
            )

        return {
            "hand_count": len(predictions),
            "gestures": predictions,
            "processing_ms": (time.perf_counter() - started) * 1000,
        }
````

## File: Cuoi_ki/Server_Module/server/face_overlays.py
````python
"""Face Landmarker inference and metadata-driven photo overlay placement."""

import json
import logging
import math
import re
import threading
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from shared.config import PROJECT_ROOT, cfg

logger = logging.getLogger(__name__)

_REQUIRED_LANDMARKS = (10, 33, 133, 234, 263, 362, 454)
_VALID_OVERLAY_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class FaceLandmarkerUnavailable(RuntimeError):
    """Raised when an overlay is selected but its model is unavailable."""


@dataclass(frozen=True)
class OverlayAsset:
    overlay_id: str
    name: str
    anchor: str
    width_ratio: float
    pivot: tuple[float, float]
    offset: tuple[float, float]
    angle_offset: float
    image: np.ndarray


@dataclass(frozen=True)
class PreparedOverlay:
    image: np.ndarray
    x: int
    y: int


def _configured_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def _pair(value: object, field: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{field} must contain exactly two numbers")
    return (_number(value[0], field), _number(value[1], field))


def load_overlays(asset_dir: Path) -> dict[str, OverlayAsset]:
    if not asset_dir.exists():
        return {}
    if not asset_dir.is_dir():
        raise ValueError(f"Face overlay asset path is not a directory: {asset_dir}")

    overlays: dict[str, OverlayAsset] = {}
    for folder in sorted(asset_dir.iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        metadata_path = folder / "metadata.json"
        image_path = folder / "overlay.png"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ValueError(f"Could not read face overlay metadata: {metadata_path}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in face overlay metadata: {metadata_path}") from exc
        if not isinstance(metadata, dict):
            raise ValueError(f"Face overlay metadata must be an object: {metadata_path}")

        overlay_id = metadata.get("id")
        if (
            not isinstance(overlay_id, str)
            or not _VALID_OVERLAY_ID.fullmatch(overlay_id)
            or overlay_id != folder.name
        ):
            raise ValueError(
                f"Overlay id in {metadata_path} must match its folder name"
            )
        anchor = metadata.get("anchor")
        if not isinstance(anchor, str) or anchor not in {"eyes", "forehead"}:
            raise ValueError(f"Unsupported face overlay anchor in {metadata_path}")
        width_ratio = _number(metadata.get("width_ratio"), "width_ratio")
        if not 0 < width_ratio <= 5:
            raise ValueError("width_ratio must be greater than 0 and at most 5")
        pivot = _pair(metadata.get("pivot"), "pivot")
        if any(value < 0 or value > 1 for value in pivot):
            raise ValueError("pivot values must be between 0 and 1")
        offset = _pair(metadata.get("offset", [0.0, 0.0]), "offset")
        angle_offset = _number(metadata.get("angle_offset", 0.0), "angle_offset")
        if not -180 <= angle_offset <= 180:
            raise ValueError("angle_offset must be between -180 and 180 degrees")

        overlay_image = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
        if (
            overlay_image is None
            or overlay_image.ndim != 3
            or overlay_image.shape[2] != 4
            or overlay_image.shape[0] < 1
            or overlay_image.shape[1] < 1
        ):
            raise ValueError(
                f"Overlay image must be a readable transparent RGBA PNG: {image_path}"
            )
        name = metadata.get("name", overlay_id)
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"name must be a non-empty string in {metadata_path}")
        overlays[overlay_id] = OverlayAsset(
            overlay_id=overlay_id,
            name=name.strip(),
            anchor=anchor,
            width_ratio=width_ratio,
            pivot=pivot,
            offset=offset,
            angle_offset=angle_offset,
            image=overlay_image,
        )
    return overlays


def face_geometry(
    landmarks: list[tuple[float, float]],
    image_width: int,
    image_height: int,
    anchor: str,
) -> tuple[tuple[float, float], float, float] | None:
    """Return anchor pixel coordinates, reference width, and eye-line angle."""
    if len(landmarks) <= max(_REQUIRED_LANDMARKS):
        return None

    points = [
        (float(x) * image_width, float(y) * image_height)
        for x, y in landmarks
    ]
    if not all(math.isfinite(coord) for point in points for coord in point):
        return None

    left_eye = (
        (points[33][0] + points[133][0]) / 2,
        (points[33][1] + points[133][1]) / 2,
    )
    right_eye = (
        (points[362][0] + points[263][0]) / 2,
        (points[362][1] + points[263][1]) / 2,
    )
    if left_eye[0] > right_eye[0]:
        left_eye, right_eye = right_eye, left_eye
    angle = math.degrees(
        math.atan2(right_eye[1] - left_eye[1], right_eye[0] - left_eye[0])
    )

    if anchor == "eyes":
        anchor_xy = (
            (left_eye[0] + right_eye[0]) / 2,
            (left_eye[1] + right_eye[1]) / 2,
        )
        reference_width = math.dist(points[33], points[263])
    elif anchor == "forehead":
        anchor_xy = points[10]
        reference_width = math.dist(points[234], points[454])
    else:
        raise ValueError(f"Unsupported face overlay anchor: {anchor}")

    if reference_width < 1:
        return None
    return anchor_xy, reference_width, angle


def rotate_overlay_with_pivot(
    image: np.ndarray, pivot: tuple[float, float], angle_degrees: float
) -> tuple[np.ndarray, tuple[float, float]]:
    """Rotate without clipping and return the pivot transformed by that same matrix."""
    height, width = image.shape[:2]
    center_x, center_y = width / 2.0, height / 2.0
    matrix = cv2.getRotationMatrix2D((center_x, center_y), -angle_degrees, 1.0)
    cosine = abs(matrix[0, 0])
    sine = abs(matrix[0, 1])
    rotated_width = max(1, int(math.ceil(height * sine + width * cosine)))
    rotated_height = max(1, int(math.ceil(height * cosine + width * sine)))
    matrix[0, 2] += rotated_width / 2.0 - center_x
    matrix[1, 2] += rotated_height / 2.0 - center_y
    rotated = cv2.warpAffine(
        image,
        matrix,
        (rotated_width, rotated_height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )
    pivot_x, pivot_y = pivot
    transformed_pivot = (
        matrix[0, 0] * pivot_x + matrix[0, 1] * pivot_y + matrix[0, 2],
        matrix[1, 0] * pivot_x + matrix[1, 1] * pivot_y + matrix[1, 2],
    )
    return rotated, transformed_pivot


def blend_overlay(frame: np.ndarray, overlay: np.ndarray, x: int, y: int) -> bool:
    """Alpha-composite an RGBA overlay, clipping it safely to the frame bounds."""
    frame_height, frame_width = frame.shape[:2]
    overlay_height, overlay_width = overlay.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(frame_width, x + overlay_width), min(frame_height, y + overlay_height)
    if x0 >= x1 or y0 >= y1:
        return False

    overlay_x0, overlay_y0 = x0 - x, y0 - y
    overlay_x1 = overlay_x0 + (x1 - x0)
    overlay_y1 = overlay_y0 + (y1 - y0)
    overlay_crop = overlay[overlay_y0:overlay_y1, overlay_x0:overlay_x1]
    if not np.any(overlay_crop[:, :, 3]):
        return False
    alpha = overlay_crop[:, :, 3:4].astype(np.float32) / 255.0
    frame_crop = frame[y0:y1, x0:x1]
    blended = (
        overlay_crop[:, :, :3].astype(np.float32) * alpha
        + frame_crop.astype(np.float32) * (1.0 - alpha)
    )
    frame_crop[:] = np.clip(blended, 0, 255).astype(frame.dtype)
    return True


class FaceOverlayProcessor:
    def __init__(self, config: dict | None = None) -> None:
        settings = (config or cfg).get("face_effects", {})
        self.asset_dir = _configured_path(
            str(settings.get("asset_dir", "assets/photo_effects/face_overlays"))
        )
        model_value = settings.get("model_path")
        self.model_path = _configured_path(str(model_value)) if model_value else None
        self.overlays = load_overlays(self.asset_dir)
        self._lock = threading.Lock()
        self._landmarker = None
        self._media_pipe = None
        self.unavailable_reason: str | None = None

        if self.model_path is None:
            self.unavailable_reason = "Face Landmarker model path is not configured"
        elif not self.model_path.is_file():
            self.unavailable_reason = f"Face Landmarker model not found: {self.model_path}"
        else:
            try:
                import mediapipe as mp
            except (ImportError, OSError) as exc:
                self.unavailable_reason = f"Could not load MediaPipe: {exc}"
            else:
                settings_num_faces = int(settings.get("num_faces", 5))
                if settings_num_faces < 1:
                    raise ValueError("face_effects.num_faces must be at least 1")
                options = mp.tasks.vision.FaceLandmarkerOptions(
                    base_options=mp.tasks.BaseOptions(
                        model_asset_path=str(self.model_path)
                    ),
                    running_mode=mp.tasks.vision.RunningMode.IMAGE,
                    num_faces=settings_num_faces,
                    min_face_detection_confidence=float(
                        settings.get("min_face_detection_confidence", 0.5)
                    ),
                    min_face_presence_confidence=float(
                        settings.get("min_face_presence_confidence", 0.5)
                    ),
                    min_tracking_confidence=float(
                        settings.get("min_tracking_confidence", 0.5)
                    ),
                )
                self._landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(
                    options
                )
                self._media_pipe = mp
                logger.info("Loaded Face Landmarker model from %s", self.model_path)

        if self.unavailable_reason:
            logger.warning("%s", self.unavailable_reason)
        if not self.overlays:
            logger.info("No face overlay assets found in %s", self.asset_dir)

    @property
    def available(self) -> bool:
        return self._landmarker is not None

    def catalog(self) -> list[dict[str, str]]:
        return [
            {
                "overlay_id": overlay.overlay_id,
                "name": overlay.name,
                "anchor": overlay.anchor,
            }
            for overlay in self.overlays.values()
        ]

    def prepare(
        self, image: np.ndarray, overlay_id: str | None
    ) -> tuple[list[PreparedOverlay], int]:
        if overlay_id is None:
            return [], 0
        overlay = self.overlays.get(overlay_id)
        if overlay is None:
            raise ValueError(f"Unknown face overlay: {overlay_id}")
        landmarker = self._landmarker
        media_pipe = self._media_pipe
        if landmarker is None or media_pipe is None:
            raise FaceLandmarkerUnavailable(
                self.unavailable_reason or "Face Landmarker is unavailable"
            )
        if image.ndim != 3 or image.shape[2] != 3:
            raise ValueError("Face overlay input must be a BGR color image")

        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        mp_image = media_pipe.Image(
            image_format=media_pipe.ImageFormat.SRGB,
            data=np.ascontiguousarray(rgb_image),
        )
        with self._lock:
            result = landmarker.detect(mp_image)

        image_height, image_width = image.shape[:2]
        prepared: list[PreparedOverlay] = []
        detected_count = len(result.face_landmarks)
        for face_landmarks in result.face_landmarks:
            points = [(point.x, point.y) for point in face_landmarks]
            geometry = face_geometry(
                points, image_width, image_height, overlay.anchor
            )
            if geometry is None:
                continue
            anchor_xy, reference_width, face_angle = geometry
            overlay_width = max(1, round(reference_width * overlay.width_ratio))
            source_height, source_width = overlay.image.shape[:2]
            overlay_height = max(
                1, round(source_height * overlay_width / source_width)
            )
            interpolation = (
                cv2.INTER_AREA if overlay_width < source_width else cv2.INTER_LINEAR
            )
            scaled = cv2.resize(
                overlay.image,
                (overlay_width, overlay_height),
                interpolation=interpolation,
            )
            pivot_xy = (
                overlay.pivot[0] * overlay_width,
                overlay.pivot[1] * overlay_height,
            )
            rotated, rotated_pivot = rotate_overlay_with_pivot(
                scaled, pivot_xy, face_angle + overlay.angle_offset
            )

            offset_x, offset_y = overlay.offset
            angle_radians = math.radians(face_angle)
            dx = (
                offset_x * math.cos(angle_radians)
                - offset_y * math.sin(angle_radians)
            ) * reference_width
            dy = (
                offset_x * math.sin(angle_radians)
                + offset_y * math.cos(angle_radians)
            ) * reference_width
            paste_x = round(anchor_xy[0] + dx - rotated_pivot[0])
            paste_y = round(anchor_xy[1] + dy - rotated_pivot[1])
            prepared.append(PreparedOverlay(rotated, paste_x, paste_y))
        return prepared, detected_count

    @staticmethod
    def composite(image: np.ndarray, prepared: list[PreparedOverlay]) -> int:
        return sum(
            blend_overlay(image, item.image, item.x, item.y)
            for item in prepared
        )

    def close(self) -> None:
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None
````

## File: Cuoi_ki/Server_Module/server/gesture_control.py
````python
"""Debounced hand-gesture controls for a single photobooth session."""

import math
import time


class GestureDebouncer:
    def __init__(
        self,
        hold_frames: int = 4,
        min_score: float = 0.6,
        cooldown_sec: float = 0.8,
        release_frames: int = 5,
    ) -> None:
        self.hold_frames = hold_frames
        self.min_score = min_score
        self.cooldown_sec = cooldown_sec
        self.release_frames = release_frames
        self.reset()

    def reset(self) -> None:
        self.candidate: str | None = None
        self.count = 0
        self.missing = 0
        self.armed = True
        self.last_fired_at = 0.0

    def update(
        self,
        label: str | None,
        score: float,
        now: float,
        min_score: float | None = None,
    ) -> str | None:
        threshold = self.min_score if min_score is None else min_score
        if not label or score < threshold:
            self.missing += 1
            if self.missing >= self.release_frames:
                self.candidate = None
                self.count = 0
                self.armed = True
            return None

        self.missing = 0
        if label != self.candidate:
            self.candidate = label
            self.count = 1
            self.armed = True
            return None

        self.count += 1
        if (
            self.armed
            and self.count >= self.hold_frames
            and now - self.last_fired_at >= self.cooldown_sec
        ):
            self.armed = False
            self.last_fired_at = now
            return label
        return None


class OneEuro:
    def __init__(self, min_cutoff: float = 1.0, beta: float = 5.0) -> None:
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.value: float | None = None
        self.derivative = 0.0

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def update(self, value: float, dt: float) -> float:
        dt = max(dt, 1e-3)
        if self.value is None:
            self.value = value
            return value
        derivative = (value - self.value) / dt
        alpha = self._alpha(1.0, dt)
        self.derivative += alpha * (derivative - self.derivative)
        cutoff = self.min_cutoff + self.beta * abs(self.derivative)
        self.value += self._alpha(cutoff, dt) * (value - self.value)
        return self.value

    def reset(self) -> None:
        self.value = None
        self.derivative = 0.0


class ZoomController:
    def __init__(self) -> None:
        self.filter = OneEuro()
        self.zoom = 1.0
        self.low = 0.18
        self.high = 1.05

    def update(self, ratio: float, dt: float) -> float:
        dt = min(max(dt, 1e-3), 0.1)
        value = self.filter.update(ratio, dt)
        self.low = max(0.08, min(self.low, value))
        self.high = min(1.6, max(self.high, value))
        amount = (value - self.low) / max(self.high - self.low, 1e-6)
        amount = min(max((amount - 0.04) / 0.92, 0), 1)
        target = math.exp(amount * math.log(2.5))
        current_log = math.log(self.zoom)
        target_log = math.log(target)
        max_step = 5.0 * dt
        self.zoom = math.exp(
            current_log + max(-max_step, min(max_step, target_log - current_log))
        )
        return self.zoom


def _distance(first: tuple[float, ...], second: tuple[float, ...]) -> float:
    return math.dist(first, second)


def _zoom_pose(landmarks: list[tuple[float, float]], engaged: bool) -> bool:
    if len(landmarks) < 21:
        return False
    wrist = landmarks[0]
    size = max(_distance(landmarks[0], landmarks[9]), 1e-6)
    folded = all(
        _distance(landmarks[tip], wrist) < _distance(landmarks[pip], wrist)
        for tip, pip in ((12, 10), (16, 14), (20, 18))
    )
    thumb_out = _distance(landmarks[4], landmarks[9]) / size > (
        0.50 if engaged else 0.65
    )
    index_out = _distance(landmarks[8], wrist) > (
        0.95 if engaged else 1.05
    ) * _distance(landmarks[5], wrist)
    return folded and thumb_out and index_out


def _pinch_ratio(
    landmarks: list[tuple[float, float]],
    world_landmarks: list[tuple[float, float, float]],
) -> float:
    if len(world_landmarks) >= 10:
        distance = lambda first, second: math.dist(
            world_landmarks[first], world_landmarks[second]
        )
    else:
        distance = lambda first, second: _distance(
            landmarks[first], landmarks[second]
        )
    return distance(4, 8) / max(distance(0, 9), 1e-6)


class GestureControl:
    """Tracks activation, countdown, filter selection, and pinch zoom."""

    def __init__(
        self,
        hold_frames: int = 4,
        min_score: float = 0.6,
        cooldown_sec: float = 0.8,
        release_frames: int = 5,
        countdown_sec: int = 3,
        activation_min_score: float = 0.5,
    ) -> None:
        self.debouncer = GestureDebouncer(
            hold_frames, min_score, cooldown_sec, release_frames
        )
        self.activation_min_score = activation_min_score
        self.countdown_sec = countdown_sec
        self.zoom_controller = ZoomController()
        self.session_id: str | None = None
        self.active = False
        self.state = "inactive"
        self.effect_id = "original"
        self.countdown_deadline = 0.0
        self.pending_command_id: str | None = None
        self.zoom_pose_count = 0
        self.zoom_missing_count = 0
        self.previous_time: float | None = None
        self.last_action = "Giơ bàn tay mở để bật điều khiển"
        self.last_event: str | None = None

    def _reset_for_session(self, session_id: str, effect_id: str) -> None:
        self.debouncer.reset()
        self.zoom_controller = ZoomController()
        self.session_id = session_id
        self.active = False
        self.state = "inactive"
        self.effect_id = effect_id
        self.countdown_deadline = 0.0
        self.pending_command_id = None
        self.zoom_pose_count = 0
        self.zoom_missing_count = 0
        self.last_action = "Giơ bàn tay mở để bật điều khiển"
        self.last_event = None

    def process(
        self,
        session_id: str,
        gestures: list[dict],
        effect_id: str,
        effect_ids: list[str],
        now: float | None = None,
    ) -> dict:
        now = time.monotonic() if now is None else now
        if session_id != self.session_id:
            self._reset_for_session(session_id, effect_id)
        self.effect_id = effect_id
        self.previous_time, previous_time = now, self.previous_time
        dt = now - previous_time if previous_time is not None else 0.125
        chosen = max(
            gestures,
            key=lambda item: float(item.get("score") or 0),
            default=None,
        )
        label = chosen.get("gesture") if chosen else None
        score = float(chosen.get("score") or 0) if chosen else 0.0
        landmarks = chosen.get("landmarks") or [] if chosen else []
        world_landmarks = chosen.get("world_landmarks") or [] if chosen else []

        zoom_active = False
        if (
            self.active
            and self.state == "ready"
            and _zoom_pose(landmarks, self.zoom_pose_count >= 3)
        ):
            self.zoom_missing_count = 0
            self.zoom_pose_count += 1
            self.debouncer.update(None, 0, now)
            if self.zoom_pose_count >= 3:
                self.zoom_controller.update(
                    _pinch_ratio(landmarks, world_landmarks), dt
                )
                zoom_active = True
        else:
            self.zoom_missing_count += 1
            if self.zoom_missing_count > 3:
                self.zoom_pose_count = 0
                self.zoom_controller.filter.reset()

        event = None
        if not zoom_active and not (
            self.zoom_pose_count and self.zoom_missing_count <= 3
        ):
            event = self.debouncer.update(
                label,
                score,
                now,
                min_score=(
                    self.activation_min_score
                    if not self.active and label == "Open_Palm"
                    else None
                ),
            )

        capture_requested = False
        effect_changed = False
        if event:
            self.last_event = event
            if not self.active and event == "Open_Palm":
                self.active = True
                self.state = "ready"
                self.last_action = "Đã bật điều khiển cử chỉ"
            elif self.active and self.state == "ready":
                if event == "Thumb_Up":
                    self.state = "countdown"
                    self.countdown_deadline = now + self.countdown_sec
                    self.last_action = "Bắt đầu đếm ngược chụp"
                elif event in {"Victory", "Pointing_Up"} and effect_ids:
                    try:
                        index = effect_ids.index(self.effect_id)
                    except ValueError:
                        index = 0
                    offset = 1 if event == "Victory" else -1
                    self.effect_id = effect_ids[(index + offset) % len(effect_ids)]
                    effect_changed = True
                    self.last_action = f"Đã đổi filter: {self.effect_id}"
            elif self.active and self.state == "countdown" and event == "Closed_Fist":
                self.state = "ready"
                self.countdown_deadline = 0.0
                self.last_action = "Đã hủy chụp"

        if self.state == "countdown" and now >= self.countdown_deadline:
            self.state = "capturing"
            capture_requested = True
            self.last_action = "Đang gửi lệnh chụp tới Raspberry Pi"

        remaining = (
            max(0, math.ceil(self.countdown_deadline - now))
            if self.state == "countdown"
            else 0
        )
        return {
            "control_active": self.active,
            "control_state": self.state,
            "selected_effect_id": self.effect_id,
            "zoom_factor": round(self.zoom_controller.zoom, 3),
            "countdown_remaining": remaining,
            "last_action": self.last_action,
            "selected_gesture": label,
            "selected_gesture_score": round(score, 3),
            "zoom_active": zoom_active,
            "capture_requested": capture_requested,
            "effect_changed": effect_changed,
        }

    def capture_queued(self, command_id: str) -> None:
        self.pending_command_id = command_id
        self.last_action = f"Đã gửi lệnh chụp ({command_id[:8]})"

    def capture_failed(self, error: str) -> None:
        self.pending_command_id = None
        self.state = "ready"
        self.last_action = f"Không gửi được lệnh chụp: {error}"

    def capture_finished(self, success: bool, detail: str = "") -> None:
        self.pending_command_id = None
        self.state = "ready"
        self.last_action = (
            f"Chụp xong: {detail}" if success else f"Chụp lỗi: {detail}"
        )

    def snapshot(self) -> dict:
        return {
            "control_active": self.active,
            "control_state": self.state,
            "selected_effect_id": self.effect_id,
            "zoom_factor": round(self.zoom_controller.zoom, 3),
            "countdown_remaining": 0,
            "last_action": self.last_action,
            "last_event": self.last_event,
            "pending_command_id": self.pending_command_id,
        }
````

## File: Cuoi_ki/Server_Module/server/image_processing.py
````python
"""Allowlisted server-side photo effects adapted from the AI demo pipeline."""

import cv2
import numpy as np


EFFECTS = {
    "original": "Original",
    "gray": "Grayscale",
    "sepia": "Sepia",
    "warm": "Warm",
    "negative": "Negative",
    "cartoon": "Cartoon",
    "pixel": "Pixel",
}


def list_effects() -> list[dict[str, str]]:
    return [{"effect_id": effect_id, "name": name} for effect_id, name in EFFECTS.items()]


def process_image(
    image_bytes: bytes, effect_id: str, zoom_factor: float = 1.0
) -> bytes:
    image = decode_image(image_bytes)
    image = apply_zoom(image, zoom_factor)
    image = apply_effect(image, effect_id)
    return encode_image(image)


def decode_image(image_bytes: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Image data is invalid")
    return image


def apply_zoom(image: np.ndarray, zoom_factor: float = 1.0) -> np.ndarray:
    if not 1 <= zoom_factor <= 2.5:
        raise ValueError("Zoom factor must be between 1.0 and 2.5")
    if zoom_factor <= 1.001:
        return image

    height, width = image.shape[:2]
    crop_width = max(1, int(width / zoom_factor))
    crop_height = max(1, int(height / zoom_factor))
    left = (width - crop_width) // 2
    top = (height - crop_height) // 2
    return cv2.resize(
        image[top : top + crop_height, left : left + crop_width],
        (width, height),
        interpolation=cv2.INTER_LINEAR,
    )


def apply_effect(image: np.ndarray, effect_id: str) -> np.ndarray:
    if effect_id not in EFFECTS:
        raise ValueError(f"Unknown image effect: {effect_id}")
    if effect_id == "gray":
        image = cv2.cvtColor(
            cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR
        )
    elif effect_id == "sepia":
        matrix = np.array(
            [
                [0.272, 0.534, 0.131],
                [0.349, 0.686, 0.168],
                [0.393, 0.769, 0.189],
            ],
            dtype=np.float32,
        )
        image = cv2.transform(image, matrix)
    elif effect_id == "warm":
        adjusted = image.astype(np.int16)
        adjusted[:, :, 2] += 35
        adjusted[:, :, 0] -= 20
        image = np.clip(adjusted, 0, 255).astype(np.uint8)
    elif effect_id == "negative":
        image = 255 - image
    elif effect_id == "cartoon":
        gray = cv2.medianBlur(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), 7)
        edges = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_MEAN_C,
            cv2.THRESH_BINARY,
            9,
            7,
        )
        color = cv2.bilateralFilter(image, 9, 75, 75)
        image = cv2.bitwise_and(color, cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR))
    elif effect_id == "pixel":
        height, width = image.shape[:2]
        small = cv2.resize(
            image,
            (max(width // 24, 1), max(height // 24, 1)),
            interpolation=cv2.INTER_LINEAR,
        )
        image = cv2.resize(small, (width, height), interpolation=cv2.INTER_NEAREST)

    return image


def encode_image(image: np.ndarray) -> bytes:
    encoded, output = cv2.imencode(".jpg", image)
    if not encoded:
        raise ValueError("Could not encode processed photo")
    return output.tobytes()
````

## File: Cuoi_ki/Server_Module/server/iot.py
````python
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
````

## File: Cuoi_ki/Server_Module/server/main.py
````python
"""Central FastAPI service for sessions, camera frames, gallery, and IoT."""

import asyncio
import hmac
import logging
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from pydantic import ValidationError

from shared.config import PROJECT_ROOT, cfg
from shared.logging_config import configure_logging
from shared.schemas import (
    FaceOverlaySelection,
    FrameMeta,
    GestureFrameResult,
    HealthResponse,
    LEDRequest,
    PhotoLayoutSelection,
    PhotoMeta,
    SessionCreate,
    SessionInfo,
    WebSocketAuth,
)
from server.ai import FrameAnalyzer
from server.face_overlays import FaceLandmarkerUnavailable, FaceOverlayProcessor
from server.gesture_control import GestureControl
from server.image_processing import (
    EFFECTS,
    apply_effect,
    apply_zoom,
    decode_image,
    encode_image,
    list_effects,
)
from server.iot import IoTManager
from server.photo_layout import (
    FrameTemplate,
    crop_to_slot,
    load_frame_templates,
    render_frame,
)
from server.storage import Storage

configure_logging("server")
logger = logging.getLogger(__name__)
MAX_IMAGE_BYTES = int(cfg.get("server", {}).get("max_frame_bytes", 10 * 1024 * 1024))
WS_PATH = str(cfg.get("server", {}).get("ws_path", "/ws/frames"))
STARTED_AT = time.monotonic()
ADMIN_HISTORY_LIMIT = 50
ADMIN_FRAME_HISTORY_LIMIT = 10
ADMIN_PAGE = Path(__file__).parent / "static" / "admin.html"
PHOTO_EFFECTS_DIR = PROJECT_ROOT / "assets" / "photo_effects"


def _process_uploaded_photo(
    image_bytes: bytes,
    effect_id: str,
    zoom_factor: float,
    face_overlay_id: str | None,
    face_overlays: FaceOverlayProcessor,
) -> tuple[bytes, int, bool]:
    image = apply_zoom(decode_image(image_bytes), zoom_factor)
    prepared, face_count = face_overlays.prepare(image, face_overlay_id)
    image = apply_effect(image, effect_id)
    applied_count = face_overlays.composite(image, prepared)
    return encode_image(image), face_count, applied_count > 0


def _render_saved_photo_layout(
    storage: Storage,
    layout: dict,
    frame_templates: dict[str, FrameTemplate],
    face_overlays: FaceOverlayProcessor,
) -> bytes:
    template = frame_templates.get(layout["frame_id"])
    if template is None:
        raise ValueError(f"Unknown photo frame: {layout['frame_id']}")

    slot_images = []
    for (_, _, width, height), slot in zip(template.slots, layout["slots"]):
        photo = storage.get_photo(slot["photo_id"])
        if (
            photo is None
            or photo["capture_batch_id"] != layout["batch_id"]
            or not photo["is_raw"]
            or not photo.get("raw_file_path")
        ):
            raise ValueError("A selected original photo is no longer available")
        raw_path = (
            storage.photo_dir / photo["raw_file_path"]
        ).resolve()
        if storage.photo_dir.resolve() not in raw_path.parents:
            raise ValueError("Selected original photo path is invalid")
        if not raw_path.is_file():
            raise ValueError(f"Selected original photo is missing: {photo['photo_id']}")

        image = crop_to_slot(
            decode_image(raw_path.read_bytes()), width, height
        )
        prepared, _ = face_overlays.prepare(image, slot["face_overlay_id"])
        image = apply_effect(image, slot["effect_id"])
        face_overlays.composite(image, prepared)
        slot_images.append(image)

    return encode_image(render_frame(template, slot_images))


async def _run_capture_sequence(app: FastAPI, batch_id: str) -> None:
    storage: Storage = app.state.storage
    iot: IoTManager = app.state.iot
    batch = storage.get_capture_batch(batch_id)
    if batch is None:
        raise ValueError(f"Capture batch not found: {batch_id}")

    session_id = batch["session_id"]
    device_id = batch["device_id"]
    try:
        shot_timeout_sec = int(
            cfg.get("capture_sequence", {}).get("shot_timeout_sec", 60)
        )
        if not 1 <= shot_timeout_sec <= 300:
            raise ValueError("shot_timeout_sec must be between 1 and 300")
        review_timeout_sec = int(
            cfg.get("capture_sequence", {}).get(
                "retake_decision_timeout_sec", 30
            )
        )
        if not 30 <= review_timeout_sec <= 60:
            raise ValueError(
                "retake_decision_timeout_sec must be between 30 and 60"
            )
        for shot_number in range(1, batch["target_count"] + 1):
            batch = storage.get_capture_batch(batch_id)
            if batch is None or batch["status"] == "cancelled":
                return
            session = storage.get_session(session_id)
            if session is None or session["status"] != "active":
                raise RuntimeError("Session ended during capture sequence")

            next_shot_at = time.time() + batch["countdown_sec"]
            storage.update_capture_batch(
                batch_id, "countdown", shot_number, next_shot_at
            )
            while time.time() < next_shot_at:
                await asyncio.sleep(min(0.25, next_shot_at - time.time()))
                batch = storage.get_capture_batch(batch_id)
                if batch is None or batch["status"] == "cancelled":
                    return

            photo_id = str(uuid.uuid4())
            command_id = uuid.uuid4().hex
            storage.create_capture_shot(
                batch_id, shot_number, photo_id, command_id
            )
            updated_batch = storage.update_capture_batch(
                batch_id, "capturing", shot_number
            )
            if updated_batch is None or updated_batch["status"] != "capturing":
                storage.update_capture_shot(
                    photo_id, "failed", "Capture sequence cancelled"
                )
                return
            try:
                iot.publish_capture(
                    device_id, session_id, photo_id=photo_id, command_id=command_id
                )
            except RuntimeError as exc:
                storage.update_capture_shot(photo_id, "failed", str(exc))
                raise

            deadline = time.monotonic() + shot_timeout_sec
            while time.monotonic() < deadline:
                batch = storage.get_capture_batch(batch_id)
                if batch is None or batch["status"] == "cancelled":
                    storage.update_capture_shot(
                        photo_id, "failed", "Capture sequence cancelled"
                    )
                    return
                session = storage.get_session(session_id)
                if session is None or session["status"] != "active":
                    raise RuntimeError("Session ended while waiting for captured photo")

                camera_status = iot.get_camera_status(device_id, command_id)
                if camera_status and camera_status.get("command_id") == command_id:
                    if camera_status.get("status") == "failed":
                        detail = str(camera_status.get("detail", "Pi capture failed"))
                        storage.update_capture_shot(photo_id, "failed", detail)
                        raise RuntimeError(detail)
                    if (
                        camera_status.get("status") == "completed"
                        and storage.get_photo(photo_id) is not None
                    ):
                        break
                await asyncio.sleep(0.2)
            else:
                storage.update_capture_shot(
                    photo_id,
                    "failed",
                    f"Pi did not complete shot {shot_number} within {shot_timeout_sec}s",
                )
                raise TimeoutError(
                    f"Pi did not complete shot {shot_number} within {shot_timeout_sec}s"
                )

        batch = storage.get_capture_batch(batch_id)
        if batch and batch["status"] != "cancelled":
            storage.complete_capture_batch(batch_id, review_timeout_sec)
    except asyncio.CancelledError:
        storage.cancel_capture_batch(batch_id)
        batch = storage.get_capture_batch(batch_id)
        if batch and batch["attempt_number"] == 2:
            storage.restore_capture_review_after_retake(
                batch_id,
                int(
                    cfg.get("capture_sequence", {}).get(
                        "retake_decision_timeout_sec", 30
                    )
                ),
            )
        raise
    except (RuntimeError, TimeoutError, ValueError) as exc:
        logger.exception("Capture sequence %s failed", batch_id)
        batch = storage.get_capture_batch(batch_id)
        if batch and batch["status"] in {"countdown", "capturing"}:
            storage.update_capture_batch(
                batch_id,
                "failed",
                batch["current_shot"],
                last_error=str(exc),
            )
            if batch["attempt_number"] == 2:
                storage.restore_capture_review_after_retake(
                    batch_id,
                    int(
                        cfg.get("capture_sequence", {}).get(
                            "retake_decision_timeout_sec", 30
                        )
                    ),
                )


def _capture_task_finished(app: FastAPI, batch_id: str, task: asyncio.Task) -> None:
    app.state.capture_tasks.pop(batch_id, None)
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        logger.error(
            "Capture sequence task %s stopped unexpectedly",
            batch_id,
            exc_info=(type(error), error, error.__traceback__),
        )


def _api_token() -> str:
    return os.environ.get(
        "PHOTOBOOTH_STATIC_TOKEN",
        str(cfg.get("server", {}).get("static_token", "")),
    )


def _authorized(token: str | None) -> bool:
    expected = _api_token()
    return not expected or (token is not None and hmac.compare_digest(token, expected))


def _require_auth(authorization: str | None) -> None:
    expected = _api_token()
    if expected and not _authorized(
        authorization.removeprefix("Bearer ").strip() if authorization else None
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token")


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage = Storage()
    storage.interrupt_active_capture_batches()
    analyzer = FrameAnalyzer()
    face_overlays = FaceOverlayProcessor()
    frame_templates = load_frame_templates(PHOTO_EFFECTS_DIR)
    iot = IoTManager(storage)
    app.state.storage = storage
    app.state.analyzer = analyzer
    app.state.face_overlays = face_overlays
    app.state.frame_templates = frame_templates
    app.state.iot = iot
    app.state.admin_state_lock = threading.Lock()
    app.state.frame_history = {}
    app.state.latest_results = {}
    app.state.result_history = {}
    app.state.gesture_controls = {}
    app.state.controls_persisted_at = {}
    app.state.capture_tasks = {}
    iot.start()
    if not _api_token():
        logger.warning("PHOTOBOOTH_STATIC_TOKEN is empty; API endpoints are unauthenticated")
    try:
        yield
    finally:
        capture_tasks = list(app.state.capture_tasks.values())
        for task in capture_tasks:
            task.cancel()
        if capture_tasks:
            await asyncio.gather(*capture_tasks, return_exceptions=True)
        iot.stop()
        analyzer.close()
        face_overlays.close()
        storage.close()


app = FastAPI(title="AI Smart Photobooth Server", lifespan=lifespan)


@app.get("/admin", include_in_schema=False)
def admin_page():
    return FileResponse(ADMIN_PAGE, media_type="text/html")


@app.get("/health", response_model=HealthResponse)
def health(request: Request):
    analyzer: FrameAnalyzer = request.app.state.analyzer
    iot: IoTManager = request.app.state.iot
    return HealthResponse(
        status="ok" if analyzer.available and iot.connected else "degraded",
        uptime_sec=max(0, time.monotonic() - STARTED_AT),
        connected_devices=request.app.state.storage.connected_devices(),
        ai_available=analyzer.available,
        mqtt_connected=iot.connected,
    )


@app.get("/api/v1/admin/state")
def admin_state(
    request: Request,
    device_id: str | None = None,
    authorization: str | None = Header(default=None),
):
    _require_auth(authorization)
    selected_device = device_id or str(cfg.get("mqtt", {}).get("device_id", "pi01"))
    sessions = request.app.state.storage.list_active_sessions(selected_device)
    with request.app.state.admin_state_lock:
        latest_result = request.app.state.latest_results.get(selected_device)
        history = list(request.app.state.result_history.get(selected_device, [])[-12:])
    active_session = sessions[0] if sessions else None
    sequence_settings = cfg.get("capture_sequence", {})
    capture_review = (
        request.app.state.storage.get_capture_review(active_session["session_id"])
        if active_session
        else None
    )
    capture_sequence = (
        request.app.state.storage.get_latest_capture_batch(
            active_session["session_id"]
        )
        if active_session
        else None
    )
    return {
        "device_id": selected_device,
        "health": health(request).model_dump(mode="json"),
        "active_session": active_session,
        "capture_sequence": capture_sequence,
        "capture_review": capture_review,
        "photo_layout": (
            request.app.state.storage.get_photo_layout(active_session["session_id"])
            if active_session
            else None
        ),
        "frame_templates": [
            template.public_dict()
            for template in request.app.state.frame_templates.values()
        ],
        "capture_sequence_config": {
            "photo_count": int(sequence_settings.get("photo_count", 8)),
            "countdown_sec": int(sequence_settings.get("countdown_sec", 10)),
            "retake_decision_timeout_sec": int(
                sequence_settings.get("retake_decision_timeout_sec", 30)
            ),
        },
        "latest_result": latest_result,
        "result_history": history,
        "effects": list_effects(),
        "face_overlays": request.app.state.face_overlays.catalog(),
        "face_overlay_model_available": request.app.state.face_overlays.available,
        "face_overlay_model_error": request.app.state.face_overlays.unavailable_reason,
    }


@app.get("/api/v1/photo-frames/{frame_id}")
def get_photo_frame(
    frame_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
):
    _require_auth(authorization)
    template = request.app.state.frame_templates.get(frame_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Photo frame not found")
    return FileResponse(
        template.image_path,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.put("/api/v1/sessions/{session_id}/photo-layout")
def save_photo_layout(
    session_id: str,
    payload: PhotoLayoutSelection,
    request: Request,
    authorization: str | None = Header(default=None),
):
    _require_auth(authorization)
    storage: Storage = request.app.state.storage
    session = storage.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["status"] != "active":
        raise HTTPException(status_code=409, detail="Session is not active")
    if payload.frame_id not in request.app.state.frame_templates:
        raise HTTPException(status_code=422, detail="Unsupported photo frame")
    review = storage.get_capture_review(session_id)
    if review is None or review["status"] not in {"accepted", "timed_out"}:
        raise HTTPException(status_code=409, detail="Complete the capture review first")

    photo_ids = [slot.photo_id for slot in payload.slots]
    if len(set(photo_ids)) != len(photo_ids):
        raise HTTPException(status_code=422, detail="Choose four different photos")
    face_overlays: FaceOverlayProcessor = request.app.state.face_overlays
    normalized_slots = []
    for slot in payload.slots:
        if slot.effect_id not in EFFECTS:
            raise HTTPException(status_code=422, detail="Unsupported image effect")
        if slot.face_overlay_id is not None:
            if slot.face_overlay_id not in face_overlays.overlays:
                raise HTTPException(status_code=422, detail="Unsupported face overlay")
            if not face_overlays.available:
                raise HTTPException(
                    status_code=503,
                    detail=face_overlays.unavailable_reason
                    or "Face Landmarker is unavailable",
                )
        normalized_slots.append(slot.model_dump())
    try:
        return storage.save_photo_layout(
            session_id,
            review["batch_id"],
            payload.frame_id,
            normalized_slots,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/v1/sessions/{session_id}/photo-layout/preview")
async def preview_photo_layout(
    session_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
):
    _require_auth(authorization)
    storage: Storage = request.app.state.storage
    session = storage.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    layout = storage.get_photo_layout(session_id)
    if layout is None:
        raise HTTPException(status_code=409, detail="Save a photo layout first")
    try:
        image = await asyncio.to_thread(
            _render_saved_photo_layout,
            storage,
            layout,
            request.app.state.frame_templates,
            request.app.state.face_overlays,
        )
    except FaceLandmarkerUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(
        content=image,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/v1/admin/frame/{device_id}")
def admin_frame(
    device_id: str,
    request: Request,
    frame_id: int | None = Query(default=None, ge=0),
    authorization: str | None = Header(default=None),
):
    _require_auth(authorization)
    with request.app.state.admin_state_lock:
        frames = request.app.state.frame_history.get(device_id, [])
        if frame_id is None:
            frame = frames[-1][1] if frames else None
        else:
            frame = next(
                (image for stored_id, image in reversed(frames) if stored_id == frame_id),
                None,
            )
    if frame is None:
        raise HTTPException(status_code=404, detail="No camera frame is available yet")
    return Response(
        content=frame,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/v1/sessions", response_model=SessionInfo, status_code=201)
def create_session(
    payload: SessionCreate,
    request: Request,
    authorization: str | None = Header(default=None),
):
    _require_auth(authorization)
    if payload.effect_id not in EFFECTS:
        raise HTTPException(status_code=422, detail="Unsupported image effect")
    face_overlays: FaceOverlayProcessor = request.app.state.face_overlays
    if payload.face_overlay_id is not None:
        if payload.face_overlay_id not in face_overlays.overlays:
            raise HTTPException(status_code=422, detail="Unsupported face overlay")
        if not face_overlays.available:
            raise HTTPException(
                status_code=503,
                detail=face_overlays.unavailable_reason or "Face Landmarker is unavailable",
            )
    try:
        return request.app.state.storage.create_session(
            payload.device_id,
            payload.pose_template_id,
            payload.effect_id,
            payload.face_overlay_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/v1/effects")
def list_image_effects(
    authorization: str | None = Header(default=None),
):
    _require_auth(authorization)
    return list_effects()


@app.get("/api/v1/sessions/active/{device_id}", response_model=SessionInfo)
def active_session(
    device_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
):
    _require_auth(authorization)
    storage: Storage = request.app.state.storage
    sessions = storage.list_active_sessions(device_id)
    if not sessions:
        raise HTTPException(status_code=404, detail="No active session for this device")
    return sessions[0]


@app.get("/api/v1/sessions/{session_id}", response_model=SessionInfo)
def get_session(
    session_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
):
    _require_auth(authorization)
    session = request.app.state.storage.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.put("/api/v1/sessions/{session_id}/face-overlay", response_model=SessionInfo)
def update_session_face_overlay(
    session_id: str,
    payload: FaceOverlaySelection,
    request: Request,
    authorization: str | None = Header(default=None),
):
    _require_auth(authorization)
    storage: Storage = request.app.state.storage
    session = storage.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["status"] != "active":
        raise HTTPException(status_code=409, detail="Session is not active")

    face_overlays: FaceOverlayProcessor = request.app.state.face_overlays
    if payload.overlay_id is not None:
        if payload.overlay_id not in face_overlays.overlays:
            raise HTTPException(status_code=422, detail="Unsupported face overlay")
        if not face_overlays.available:
            raise HTTPException(
                status_code=503,
                detail=face_overlays.unavailable_reason or "Face Landmarker is unavailable",
            )

    updated = storage.update_session_face_overlay(session_id, payload.overlay_id)
    if updated is None:
        raise HTTPException(status_code=409, detail="Session is not active")
    return updated


@app.post("/api/v1/sessions/{session_id}/end", response_model=SessionInfo)
def end_session(
    session_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
):
    _require_auth(authorization)
    session = request.app.state.storage.end_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.post("/api/v1/sessions/{session_id}/capture")
def request_capture(
    session_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
):
    _require_auth(authorization)
    session = request.app.state.storage.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["status"] != "active":
        raise HTTPException(status_code=409, detail="Session is not active")
    controls = request.app.state.gesture_controls.get(session["device_id"])
    if controls and controls.session_id == session_id:
        request.app.state.storage.update_session_controls(
            session_id, controls.effect_id, controls.zoom_controller.zoom
        )
    try:
        command_id = request.app.state.iot.publish_capture(session["device_id"], session_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"command_id": command_id, "status": "queued"}


def _create_capture_sequence(
    request: Request, session_id: str, is_retake: bool = False
) -> dict:
    storage: Storage = request.app.state.storage
    session = storage.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["status"] != "active":
        raise HTTPException(status_code=409, detail="Session is not active")
    if not request.app.state.iot.connected:
        raise HTTPException(status_code=503, detail="MQTT broker is not connected")

    settings = cfg.get("capture_sequence", {})
    try:
        photo_count = int(settings.get("photo_count", 8))
        countdown_sec = int(settings.get("countdown_sec", 10))
        shot_timeout_sec = int(settings.get("shot_timeout_sec", 60))
        review_timeout_sec = int(
            settings.get("retake_decision_timeout_sec", 30)
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=500, detail="Invalid capture sequence configuration"
        ) from exc
    if (
        not 4 <= photo_count <= 8
        or not 1 <= countdown_sec <= 30
        or not 1 <= shot_timeout_sec <= 300
        or not 30 <= review_timeout_sec <= 60
    ):
        raise HTTPException(
            status_code=500, detail="Invalid capture sequence configuration"
        )
    try:
        batch = storage.create_capture_batch(
            session_id, photo_count, countdown_sec, is_retake=is_retake
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    task = asyncio.create_task(_run_capture_sequence(request.app, batch["batch_id"]))
    request.app.state.capture_tasks[batch["batch_id"]] = task
    task.add_done_callback(
        lambda finished, app=request.app, batch_id=batch["batch_id"]:
        _capture_task_finished(app, batch_id, finished)
    )
    return batch


@app.post("/api/v1/sessions/{session_id}/capture-sequence")
async def start_capture_sequence(
    session_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
):
    _require_auth(authorization)
    return _create_capture_sequence(request, session_id)


@app.post("/api/v1/sessions/{session_id}/capture-sequence/retake")
async def retake_capture_sequence(
    session_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
):
    _require_auth(authorization)
    return _create_capture_sequence(request, session_id, is_retake=True)


@app.post("/api/v1/sessions/{session_id}/capture-sequence/cancel")
async def cancel_capture_sequence(
    session_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
):
    _require_auth(authorization)
    storage: Storage = request.app.state.storage
    batch = storage.get_active_capture_batch(session_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="No active capture sequence")
    cancelled = storage.cancel_capture_batch(batch["batch_id"])
    if batch["attempt_number"] == 2:
        timeout_sec = int(
            cfg.get("capture_sequence", {}).get(
                "retake_decision_timeout_sec", 30
            )
        )
        storage.restore_capture_review_after_retake(batch["batch_id"], timeout_sec)
    return cancelled


@app.post("/api/v1/sessions/{session_id}/capture-review/continue")
def continue_capture_review(
    session_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
):
    _require_auth(authorization)
    session = request.app.state.storage.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["status"] != "active":
        raise HTTPException(status_code=409, detail="Session is not active")
    review = request.app.state.storage.decide_capture_review(session_id)
    if review is None:
        raise HTTPException(status_code=404, detail="No capture review is pending")
    if review["status"] == "retake_started":
        raise HTTPException(status_code=409, detail="Retake is still in progress")
    return review


@app.post("/api/v1/devices/{device_id}/led")
def set_led(
    device_id: str,
    payload: LEDRequest,
    request: Request,
    authorization: str | None = Header(default=None),
):
    _require_auth(authorization)
    try:
        command_id = request.app.state.iot.publish_led(device_id, payload.brightness)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"command_id": command_id, "status": "queued"}


@app.get("/api/v1/telemetry")
def telemetry(
    request: Request,
    device_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    authorization: str | None = Header(default=None),
):
    _require_auth(authorization)
    return request.app.state.storage.list_telemetry(device_id, limit)


@app.get("/api/v1/photos", response_model=list[PhotoMeta])
def list_photos(
    request: Request,
    session_id: str | None = None,
    authorization: str | None = Header(default=None),
):
    _require_auth(authorization)
    return request.app.state.storage.list_photos(session_id)


@app.post("/api/v1/photos", response_model=PhotoMeta, status_code=201)
async def upload_photo(
    request: Request,
    session_id: str,
    pose_score: int = Header(default=0, ge=0, le=100, alias="X-Pose-Score"),
    photo_id: str | None = Header(default=None, alias="X-Photo-ID"),
    authorization: str | None = Header(default=None),
):
    _require_auth(authorization)
    session = request.app.state.storage.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if content_type not in {"image/jpeg", "image/png"}:
        raise HTTPException(status_code=415, detail="Send a JPEG or PNG image")
    image = bytearray()
    async for chunk in request.stream():
        image.extend(chunk)
        if len(image) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="Image exceeds the configured size limit")
    if not image:
        raise HTTPException(status_code=400, detail="Image body is empty")
    capture_shot = (
        request.app.state.storage.get_capture_shot_by_photo_id(photo_id)
        if photo_id
        else None
    )
    if capture_shot:
        if capture_shot["batch_id"] is None:
            raise HTTPException(status_code=409, detail="Capture sequence metadata is invalid")
        try:
            raw_photo = request.app.state.storage.save_raw_photo(
                session_id,
                bytes(image),
                photo_id,
                capture_shot["batch_id"],
                int(capture_shot["shot_number"]),
                pose_score,
                "png" if content_type == "image/png" else "jpg",
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except OSError as exc:
            logger.exception(
                "Could not save raw photo %s for session %s", photo_id, session_id
            )
            raise HTTPException(status_code=500, detail="Could not save raw photo") from exc
        return raw_photo
    try:
        effect_id = session["effect_id"]
        zoom_factor = float(session.get("zoom_factor", 1.0))
        face_overlay_id = session.get("face_overlay_id")
        processed_image, face_count, face_overlay_applied = await asyncio.to_thread(
            _process_uploaded_photo,
            bytes(image),
            effect_id,
            zoom_factor,
            face_overlay_id,
            request.app.state.face_overlays,
        )
    except FaceLandmarkerUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        return request.app.state.storage.save_photo(
            session_id,
            processed_image,
            pose_score,
            photo_id,
            effect_id,
            zoom_factor,
            face_overlay_id,
            face_count,
            face_overlay_applied,
            bytes(image),
            "png" if content_type == "image/png" else "jpg",
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OSError as exc:
        logger.exception("Could not save uploaded photo for session %s", session_id)
        raise HTTPException(status_code=500, detail="Could not save photo") from exc


@app.get("/api/v1/photos/{photo_id}")
def get_photo(
    photo_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
):
    _require_auth(authorization)
    photo = request.app.state.storage.get_photo(photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    path = request.app.state.storage.photo_dir / photo["file_path"]
    if not path.is_file():
        logger.error("Photo metadata exists but file is missing: %s", path)
        raise HTTPException(status_code=404, detail="Photo file is missing")
    return FileResponse(path, media_type="image/jpeg", filename=f"{photo_id}.jpg")


@app.get("/api/v1/photos/{photo_id}/raw")
def get_raw_photo(
    photo_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
):
    _require_auth(authorization)
    photo = request.app.state.storage.get_photo(photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    raw_file_path = photo.get("raw_file_path")
    if not raw_file_path:
        raise HTTPException(status_code=404, detail="Raw original is not available")
    path = (request.app.state.storage.photo_dir / raw_file_path).resolve()
    if request.app.state.storage.photo_dir.resolve() not in path.parents:
        logger.error("Raw photo path escapes storage directory: %s", path)
        raise HTTPException(status_code=500, detail="Invalid raw photo path")
    if not path.is_file():
        logger.error("Raw photo metadata exists but file is missing: %s", path)
        raise HTTPException(status_code=404, detail="Raw photo file is missing")
    return FileResponse(path, media_type="application/octet-stream", filename=path.name)


@app.websocket(WS_PATH)
async def stream_frames(websocket: WebSocket):
    await websocket.accept()
    try:
        auth_message = WebSocketAuth.model_validate(await websocket.receive_json())
    except (ValidationError, ValueError):
        await websocket.close(code=1008, reason="Invalid authentication message")
        return
    if not _authorized(auth_message.token):
        await websocket.send_json({"type": "auth", "authenticated": False})
        await websocket.close(code=1008, reason="Invalid or missing token")
        return
    await websocket.send_json({"type": "auth", "authenticated": True})
    try:
        while True:
            try:
                metadata = await websocket.receive_json()
                frame_meta = FrameMeta.model_validate(metadata)
                image = await websocket.receive_bytes()
                if len(image) > MAX_IMAGE_BYTES:
                    await websocket.send_json({"error": "Frame exceeds configured size limit"})
                    continue
                session = websocket.app.state.storage.get_session(frame_meta.session_id)
                if session is None or session["status"] != "active":
                    await websocket.send_json({"error": "Session is not active"})
                    continue
                if frame_meta.device_id and frame_meta.device_id != session["device_id"]:
                    await websocket.send_json({"error": "Frame device does not own this session"})
                    continue
                analysis = await asyncio.to_thread(
                    websocket.app.state.analyzer.analyze, image
                )
                device_id = session["device_id"]
                controls = websocket.app.state.gesture_controls.setdefault(
                    device_id,
                    GestureControl(
                        hold_frames=int(cfg.get("gesture", {}).get("hold_frames", 4)),
                        min_score=float(cfg.get("gesture", {}).get("min_score", 0.6)),
                        activation_min_score=float(
                            cfg.get("gesture", {}).get("activation_min_score", 0.5)
                        ),
                        cooldown_sec=float(
                            cfg.get("gesture", {}).get("cooldown_sec", 0.8)
                        ),
                        release_frames=int(
                            cfg.get("gesture", {}).get("release_frames", 5)
                        ),
                        countdown_sec=int(
                            cfg.get("gesture", {}).get("countdown_sec", 3)
                        ),
                    ),
                )
                camera_status = websocket.app.state.iot.get_camera_status(device_id)
                if (
                    controls.state == "capturing"
                    and controls.pending_command_id
                    and camera_status
                    and camera_status.get("command_id") == controls.pending_command_id
                ):
                    controls.capture_finished(
                        camera_status.get("status") == "completed",
                        str(camera_status.get("detail", "")),
                    )

                control_now = time.monotonic()
                control = controls.process(
                    frame_meta.session_id,
                    [gesture.model_dump(mode="json") for gesture in analysis["gestures"]],
                    session.get("effect_id", "original"),
                    list(EFFECTS),
                    now=control_now,
                )
                persisted_session, persisted_at = (
                    websocket.app.state.controls_persisted_at.get(device_id, (None, 0.0))
                )
                persist_controls = (
                    control["effect_changed"]
                    or control["capture_requested"]
                    or persisted_session != frame_meta.session_id
                    or control_now - persisted_at >= 1.0
                )
                if persist_controls:
                    updated_session = websocket.app.state.storage.update_session_controls(
                        frame_meta.session_id,
                        control["selected_effect_id"],
                        control["zoom_factor"],
                    )
                    if updated_session is None:
                        raise ValueError("Session ended while applying gesture controls")
                    session = updated_session
                if control["capture_requested"]:
                    try:
                        command_id = websocket.app.state.iot.publish_capture(
                            device_id, frame_meta.session_id
                        )
                    except RuntimeError as exc:
                        controls.capture_failed(str(exc))
                    else:
                        controls.capture_queued(command_id)
                if persist_controls:
                    websocket.app.state.controls_persisted_at[device_id] = (
                        frame_meta.session_id,
                        control_now,
                    )

                result = GestureFrameResult(
                    session_id=frame_meta.session_id,
                    frame_id=frame_meta.frame_id,
                    hand_count=analysis["hand_count"],
                    gestures=analysis["gestures"],
                    control_active=controls.active,
                    control_state=controls.state,
                    selected_effect_id=controls.effect_id,
                    zoom_factor=controls.zoom_controller.zoom,
                    countdown_remaining=control["countdown_remaining"],
                    selected_gesture=control["selected_gesture"],
                    selected_gesture_score=control["selected_gesture_score"],
                    zoom_active=control["zoom_active"],
                    last_action=controls.last_action,
                    processing_ms=analysis["processing_ms"],
                )
                result_payload = result.model_dump(mode="json")
                snapshot = {
                    "received_at": time.time(),
                    "result": result_payload,
                }
                with websocket.app.state.admin_state_lock:
                    frames = websocket.app.state.frame_history.setdefault(device_id, [])
                    frames.append((frame_meta.frame_id, image))
                    del frames[:-ADMIN_FRAME_HISTORY_LIMIT]
                    websocket.app.state.latest_results[device_id] = snapshot
                    history = websocket.app.state.result_history.setdefault(device_id, [])
                    history.append(snapshot)
                    del history[:-ADMIN_HISTORY_LIMIT]
                await websocket.send_json(result_payload)
            except (ValidationError, ValueError) as exc:
                await websocket.send_json({"error": str(exc)})
    except WebSocketDisconnect:
        logger.info("Camera WebSocket disconnected")


if __name__ == "__main__":
    import uvicorn

    server_settings = cfg.get("server", {})
    uvicorn.run(
        "server.main:app",
        host=server_settings.get("host", "0.0.0.0"),
        port=int(server_settings.get("http_port", 8000)),
        reload=False,
    )
````

## File: Cuoi_ki/Server_Module/server/photo_layout.py
````python
"""Frame catalog loading and four-slot photo layout rendering."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

_VALID_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


@dataclass(frozen=True)
class FrameTemplate:
    frame_id: str
    name: str
    image_path: Path
    width: int
    height: int
    slots: tuple[tuple[int, int, int, int], ...]

    def public_dict(self) -> dict:
        return {
            "frame_id": self.frame_id,
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "slots": [list(slot) for slot in self.slots],
        }


def load_frame_templates(asset_dir: Path) -> dict[str, FrameTemplate]:
    manifest_path = asset_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Could not read photo-effect manifest: {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid photo-effect manifest: {manifest_path}") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("frames"), list):
        raise ValueError("Photo-effect manifest must contain a frames list")

    templates: dict[str, FrameTemplate] = {}
    for entry in manifest["frames"]:
        if not isinstance(entry, dict):
            raise ValueError("Each frame manifest entry must be an object")
        frame_id = entry.get("id")
        name = entry.get("name")
        relative_file = entry.get("file")
        size = entry.get("canvas_size")
        raw_slots = entry.get("slots")
        if (
            not isinstance(frame_id, str)
            or not _VALID_ID.fullmatch(frame_id)
            or frame_id in templates
        ):
            raise ValueError("Frame ids must be unique lowercase identifiers")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Frame {frame_id} must have a non-empty name")
        if not isinstance(relative_file, str):
            raise ValueError(f"Frame {frame_id} must define an image file")
        image_path = (asset_dir / relative_file).resolve()
        if asset_dir.resolve() not in image_path.parents:
            raise ValueError(f"Frame image path escapes the asset directory: {relative_file}")
        if (
            not isinstance(size, list)
            or len(size) != 2
            or any(type(value) is not int or value < 1 for value in size)
        ):
            raise ValueError(f"Frame {frame_id} has invalid canvas_size")
        if not isinstance(raw_slots, list) or len(raw_slots) != 4:
            raise ValueError(f"Frame {frame_id} must define exactly four photo slots")

        slots: list[tuple[int, int, int, int]] = []
        for raw_slot in raw_slots:
            if (
                not isinstance(raw_slot, list)
                or len(raw_slot) != 4
                or any(type(value) is not int for value in raw_slot)
            ):
                raise ValueError(f"Frame {frame_id} contains an invalid photo slot")
            x, y, width, height = raw_slot
            if (
                x < 0
                or y < 0
                or width < 1
                or height < 1
                or x + width > size[0]
                or y + height > size[1]
            ):
                raise ValueError(f"Frame {frame_id} photo slot is outside its canvas")
            slots.append((x, y, width, height))

        frame_image = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
        if (
            frame_image is None
            or frame_image.ndim != 3
            or frame_image.shape[2] != 4
            or (frame_image.shape[1], frame_image.shape[0]) != tuple(size)
        ):
            raise ValueError(
                f"Frame {frame_id} must be a readable RGBA PNG matching canvas_size"
            )
        templates[frame_id] = FrameTemplate(
            frame_id=frame_id,
            name=name.strip(),
            image_path=image_path,
            width=size[0],
            height=size[1],
            slots=tuple(slots),
        )
    if not templates:
        raise ValueError("Photo-effect manifest does not contain any frames")
    return templates


def crop_to_slot(image: np.ndarray, width: int, height: int) -> np.ndarray:
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("Photo layout input must be a BGR color image")
    if width < 1 or height < 1:
        raise ValueError("Photo slot dimensions must be positive")

    source_height, source_width = image.shape[:2]
    target_ratio = width / height
    source_ratio = source_width / source_height
    if source_ratio > target_ratio:
        crop_width = max(1, round(source_height * target_ratio))
        left = (source_width - crop_width) // 2
        cropped = image[:, left : left + crop_width]
    else:
        crop_height = max(1, round(source_width / target_ratio))
        top = (source_height - crop_height) // 2
        cropped = image[top : top + crop_height, :]
    interpolation = cv2.INTER_AREA if cropped.shape[1] > width else cv2.INTER_CUBIC
    return cv2.resize(cropped, (width, height), interpolation=interpolation)


def render_frame(
    template: FrameTemplate, slot_images: list[np.ndarray]
) -> np.ndarray:
    if len(slot_images) != len(template.slots):
        raise ValueError("The selected frame requires exactly four photos")

    canvas = np.full((template.height, template.width, 3), 255, dtype=np.uint8)
    for image, (x, y, width, height) in zip(slot_images, template.slots):
        canvas[y : y + height, x : x + width] = crop_to_slot(image, width, height)

    frame = cv2.imread(str(template.image_path), cv2.IMREAD_UNCHANGED)
    if frame is None:
        raise ValueError(f"Could not read frame template: {template.image_path}")
    alpha = frame[:, :, 3:4].astype(np.float32) / 255.0
    composed = (
        frame[:, :, :3].astype(np.float32) * alpha
        + canvas.astype(np.float32) * (1.0 - alpha)
    )
    return np.clip(composed, 0, 255).astype(np.uint8)
````

## File: Cuoi_ki/Server_Module/server/pose_matching.py
````python
"""Load reference poses and compare them with normalized server keypoints."""

import json
import logging
import math

from pydantic import BaseModel, Field, ValidationError

from shared.config import PROJECT_ROOT
from shared.schemas import FeedbackItem, KeyPoint

logger = logging.getLogger(__name__)


class PoseTemplate(BaseModel):
    template_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    tolerance: float = Field(default=0.35, gt=0)
    keypoints: dict[str, tuple[float, float]] = Field(min_length=3)


class PoseMatcher:
    def __init__(self) -> None:
        self.directory = PROJECT_ROOT / "templates" / "poses"
        self.templates = self._load_templates()

    def _load_templates(self) -> dict[str, PoseTemplate]:
        templates = {}
        self.directory.mkdir(parents=True, exist_ok=True)
        for path in sorted(self.directory.glob("*.json")):
            try:
                template = PoseTemplate.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValidationError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"Invalid pose template {path}: {exc}") from exc
            if template.template_id in templates:
                raise ValueError(f"Duplicate pose template ID: {template.template_id}")
            templates[template.template_id] = template
        logger.info("Loaded %s pose templates from %s", len(templates), self.directory)
        return templates

    def list_templates(self) -> list[dict[str, str]]:
        return [
            {"template_id": item.template_id, "name": item.name}
            for item in self.templates.values()
        ]

    def has_template(self, template_id: str) -> bool:
        return template_id in self.templates

    def match(
        self, template_id: str, keypoints: list[KeyPoint]
    ) -> tuple[int, list[FeedbackItem]]:
        template = self.templates[template_id]
        observed = {point.name: point for point in keypoints}
        common_names = template.keypoints.keys() & observed.keys()
        if len(common_names) < 3:
            return 0, [
                FeedbackItem(
                    body_part="body",
                    message="Keep more of your body visible to the camera",
                )
            ]

        center, scale = self._body_reference(observed)
        errors = []
        for name in common_names:
            point = observed[name]
            expected_x, expected_y = template.keypoints[name]
            actual_x = (point.x - center[0]) / scale
            actual_y = (point.y - center[1]) / scale
            distance = ((actual_x - expected_x) ** 2 + (actual_y - expected_y) ** 2) ** 0.5
            errors.append((name, distance, point.visibility))

        total_visibility = sum(visibility for _, _, visibility in errors)
        mean_error = (
            sum(distance * visibility for _, distance, visibility in errors)
            / max(total_visibility, 1e-6)
        )
        score = round(max(0, min(100, 100 * (1 - mean_error / template.tolerance))))
        if score >= 90:
            return score, []
        feedback = [
            FeedbackItem(
                body_part=name.replace("_", " "),
                message=f"Move your {name.replace('_', ' ')} closer to the reference pose",
            )
            for name, distance, _ in sorted(errors, key=lambda item: item[1], reverse=True)[:2]
        ]
        return score, feedback

    @staticmethod
    def _body_reference(
        keypoints: dict[str, KeyPoint],
    ) -> tuple[tuple[float, float], float]:
        shoulders = [keypoints[name] for name in ("left_shoulder", "right_shoulder") if name in keypoints]
        hips = [keypoints[name] for name in ("left_hip", "right_hip") if name in keypoints]
        anchors = shoulders or hips
        if len(anchors) == 2:
            center = (
                (anchors[0].x + anchors[1].x) / 2,
                (anchors[0].y + anchors[1].y) / 2,
            )
            scale = math.dist(
                (anchors[0].x, anchors[0].y),
                (anchors[1].x, anchors[1].y),
            )
            if scale > 1e-6:
                return center, scale
        points = list(keypoints.values())
        center = (
            (min(point.x for point in points) + max(point.x for point in points)) / 2,
            (min(point.y for point in points) + max(point.y for point in points)) / 2,
        )
        scale = max(
            max(point.x for point in points) - min(point.x for point in points),
            max(point.y for point in points) - min(point.y for point in points),
        )
        return center, max(scale, 1e-6)
````

## File: Cuoi_ki/Server_Module/server/storage.py
````python
"""SQLite persistence for sessions, captured photos, and device telemetry."""

import json
import sqlite3
import threading
import time
import uuid
import logging
from pathlib import Path

from shared.config import PROJECT_ROOT, cfg

logger = logging.getLogger(__name__)


def _configured_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


class Storage:
    def __init__(self, config: dict | None = None) -> None:
        settings = (config or cfg).get("storage", {})
        self.photo_dir = _configured_path(settings.get("photo_dir", "data/photos"))
        database_path = _configured_path(settings.get("db_path", "data/photobooth.db"))
        self.photo_dir.mkdir(parents=True, exist_ok=True)
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._initialize()

    def _initialize(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    pose_template_id TEXT,
                    effect_id TEXT NOT NULL DEFAULT 'original',
                    face_overlay_id TEXT,
                    zoom_factor REAL NOT NULL DEFAULT 1.0,
                    status TEXT NOT NULL CHECK (status IN ('active', 'completed')),
                    created_at REAL NOT NULL,
                    ended_at REAL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_session_per_device
                    ON sessions(device_id) WHERE status = 'active';
                CREATE TABLE IF NOT EXISTS photos (
                    photo_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(session_id),
                    timestamp REAL NOT NULL,
                    file_path TEXT NOT NULL UNIQUE,
                    raw_file_path TEXT,
                    capture_batch_id TEXT,
                    sequence_number INTEGER,
                    is_raw INTEGER NOT NULL DEFAULT 0,
                    pose_score INTEGER NOT NULL DEFAULT 0,
                    effect_id TEXT NOT NULL DEFAULT 'original',
                    face_overlay_id TEXT,
                    face_count INTEGER NOT NULL DEFAULT 0,
                    face_overlay_applied INTEGER NOT NULL DEFAULT 0,
                    zoom_factor REAL NOT NULL DEFAULT 1.0
                );
                CREATE TABLE IF NOT EXISTS telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    value REAL NOT NULL,
                    timestamp REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS devices (
                    device_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    version TEXT,
                    updated_at REAL NOT NULL,
                    led_brightness INTEGER
                );
                CREATE TABLE IF NOT EXISTS capture_batches (
                    batch_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(session_id),
                    device_id TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN ('countdown', 'capturing', 'completed',
                                   'failed', 'cancelled', 'interrupted')
                    ),
                    target_count INTEGER NOT NULL,
                    countdown_sec INTEGER NOT NULL,
                    current_shot INTEGER NOT NULL DEFAULT 0,
                    next_shot_at REAL,
                    last_error TEXT,
                    started_at REAL NOT NULL,
                    completed_at REAL,
                    attempt_number INTEGER NOT NULL DEFAULT 1
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_capture_batch_per_session
                    ON capture_batches(session_id)
                    WHERE status IN ('countdown', 'capturing');
                CREATE TABLE IF NOT EXISTS capture_shots (
                    batch_id TEXT NOT NULL REFERENCES capture_batches(batch_id),
                    shot_number INTEGER NOT NULL,
                    photo_id TEXT NOT NULL UNIQUE,
                    command_id TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL CHECK (status IN ('queued', 'completed', 'failed')),
                    error TEXT,
                    created_at REAL NOT NULL,
                    completed_at REAL,
                    PRIMARY KEY (batch_id, shot_number)
                );
                CREATE TABLE IF NOT EXISTS capture_reviews (
                    session_id TEXT PRIMARY KEY REFERENCES sessions(session_id),
                    batch_id TEXT NOT NULL REFERENCES capture_batches(batch_id),
                    status TEXT NOT NULL CHECK (
                        status IN ('pending', 'retake_started', 'accepted', 'timed_out')
                    ),
                    retake_used INTEGER NOT NULL DEFAULT 0,
                    decision_deadline REAL,
                    decided_at REAL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS photo_layouts (
                    session_id TEXT PRIMARY KEY REFERENCES sessions(session_id),
                    batch_id TEXT NOT NULL REFERENCES capture_batches(batch_id),
                    frame_id TEXT NOT NULL,
                    slots_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )
            capture_batch_columns = {
                row["name"]
                for row in self._connection.execute(
                    "PRAGMA table_info(capture_batches)"
                ).fetchall()
            }
            if "attempt_number" not in capture_batch_columns:
                self._connection.execute(
                    "ALTER TABLE capture_batches ADD COLUMN attempt_number INTEGER NOT NULL DEFAULT 1"
                )
            session_columns = {
                row["name"]
                for row in self._connection.execute("PRAGMA table_info(sessions)").fetchall()
            }
            if "effect_id" not in session_columns:
                self._connection.execute(
                    "ALTER TABLE sessions ADD COLUMN effect_id TEXT NOT NULL DEFAULT 'original'"
                )
            if "face_overlay_id" not in session_columns:
                self._connection.execute(
                    "ALTER TABLE sessions ADD COLUMN face_overlay_id TEXT"
                )
            if "zoom_factor" not in session_columns:
                self._connection.execute(
                    "ALTER TABLE sessions ADD COLUMN zoom_factor REAL NOT NULL DEFAULT 1.0"
                )
            photo_columns = {
                row["name"]
                for row in self._connection.execute("PRAGMA table_info(photos)").fetchall()
            }
            if "effect_id" not in photo_columns:
                self._connection.execute(
                    "ALTER TABLE photos ADD COLUMN effect_id TEXT NOT NULL DEFAULT 'original'"
                )
            if "face_overlay_id" not in photo_columns:
                self._connection.execute(
                    "ALTER TABLE photos ADD COLUMN face_overlay_id TEXT"
                )
            if "face_count" not in photo_columns:
                self._connection.execute(
                    "ALTER TABLE photos ADD COLUMN face_count INTEGER NOT NULL DEFAULT 0"
                )
            if "face_overlay_applied" not in photo_columns:
                self._connection.execute(
                    "ALTER TABLE photos ADD COLUMN face_overlay_applied INTEGER NOT NULL DEFAULT 0"
                )
            if "zoom_factor" not in photo_columns:
                self._connection.execute(
                    "ALTER TABLE photos ADD COLUMN zoom_factor REAL NOT NULL DEFAULT 1.0"
                )
            for column, definition in (
                ("raw_file_path", "TEXT"),
                ("capture_batch_id", "TEXT"),
                ("sequence_number", "INTEGER"),
                ("is_raw", "INTEGER NOT NULL DEFAULT 0"),
            ):
                if column not in photo_columns:
                    self._connection.execute(
                        f"ALTER TABLE photos ADD COLUMN {column} {definition}"
                    )
            retention_days = int(cfg.get("storage", {}).get("telemetry_retention_days", 7))
            if retention_days < 0:
                raise ValueError("telemetry_retention_days cannot be negative")
            cutoff = time.time() - retention_days * 86400
            self._connection.execute(
                "DELETE FROM telemetry WHERE timestamp < ?",
                (cutoff,),
            )

    def create_session(
        self,
        device_id: str,
        pose_template_id: str | None,
        effect_id: str = "original",
        face_overlay_id: str | None = None,
    ) -> dict:
        session_id = str(uuid.uuid4())
        created_at = time.time()
        try:
            with self._lock, self._connection:
                self._connection.execute(
                    """INSERT INTO sessions
                       (session_id, device_id, pose_template_id, effect_id,
                        face_overlay_id, status, created_at)
                       VALUES (?, ?, ?, ?, ?, 'active', ?)""",
                    (
                        session_id,
                        device_id,
                        pose_template_id,
                        effect_id,
                        face_overlay_id,
                        created_at,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Device {device_id} already has an active session") from exc
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_active_sessions(self, device_id: str) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                """SELECT * FROM sessions
                   WHERE device_id = ? AND status = 'active'
                   ORDER BY created_at DESC""",
                (device_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def end_session(self, session_id: str) -> dict | None:
        with self._lock, self._connection:
            now = time.time()
            self._connection.execute(
                """UPDATE sessions SET status = 'completed', ended_at = ?
                   WHERE session_id = ? AND status = 'active'""",
                (now, session_id),
            )
            self._connection.execute(
                """UPDATE capture_reviews SET status = 'timed_out',
                       decision_deadline = NULL, decided_at = ?, updated_at = ?
                   WHERE session_id = ?
                     AND status IN ('pending', 'retake_started')""",
                (now, now, session_id),
            )
        return self.get_session(session_id)

    def update_session_controls(
        self, session_id: str, effect_id: str, zoom_factor: float
    ) -> dict | None:
        if not 1 <= zoom_factor <= 2.5:
            raise ValueError("zoom_factor must be between 1.0 and 2.5")
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """UPDATE sessions SET effect_id = ?, zoom_factor = ?
                   WHERE session_id = ? AND status = 'active'""",
                (effect_id, zoom_factor, session_id),
            )
            if cursor.rowcount == 0:
                return None
        return self.get_session(session_id)

    def update_session_face_overlay(
        self, session_id: str, face_overlay_id: str | None
    ) -> dict | None:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """UPDATE sessions SET face_overlay_id = ?
                   WHERE session_id = ? AND status = 'active'""",
                (face_overlay_id, session_id),
            )
            if cursor.rowcount == 0:
                return None
        return self.get_session(session_id)

    def create_capture_batch(
        self,
        session_id: str,
        target_count: int,
        countdown_sec: int,
        is_retake: bool = False,
    ) -> dict:
        if not 1 <= target_count <= 8:
            raise ValueError("target_count must be between 1 and 8")
        if not 1 <= countdown_sec <= 30:
            raise ValueError("countdown_sec must be between 1 and 30")
        if is_retake:
            self.get_capture_review(session_id)
        batch_id = str(uuid.uuid4())
        started_at = time.time()
        with self._lock, self._connection:
            session = self._connection.execute(
                """SELECT device_id FROM sessions
                   WHERE session_id = ? AND status = 'active'""",
                (session_id,),
            ).fetchone()
            if session is None:
                raise ValueError("Session is not active")
            attempt_number = 1
            review = self._connection.execute(
                "SELECT * FROM capture_reviews WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if is_retake:
                if (
                    review is None
                    or review["status"] != "pending"
                    or review["retake_used"]
                ):
                    raise ValueError("No unused retake is available")
                if (
                    review["decision_deadline"] is not None
                    and review["decision_deadline"] <= started_at
                ):
                    raise ValueError("Retake decision has timed out")
                attempt_number = 2
                self._connection.execute(
                    """UPDATE capture_reviews SET status = 'retake_started',
                           retake_used = 1, decision_deadline = NULL,
                           decided_at = NULL, updated_at = ?
                       WHERE session_id = ? AND status = 'pending'
                         AND retake_used = 0""",
                    (started_at, session_id),
                )
            elif review is not None:
                raise ValueError("The initial capture set has already completed")
            try:
                self._connection.execute(
                    """INSERT INTO capture_batches
                       (batch_id, session_id, device_id, status, target_count,
                        countdown_sec, started_at, attempt_number)
                       VALUES (?, ?, ?, 'countdown', ?, ?, ?, ?)""",
                    (
                        batch_id,
                        session_id,
                        session["device_id"],
                        target_count,
                        countdown_sec,
                        started_at,
                        attempt_number,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("A capture sequence is already active") from exc
        batch = self.get_capture_batch(batch_id)
        if batch is None:
            raise RuntimeError(f"Capture batch metadata missing after creating {batch_id}")
        return batch

    def get_capture_batch(self, batch_id: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM capture_batches WHERE batch_id = ?", (batch_id,)
            ).fetchone()
            if row is None:
                return None
            batch = dict(row)
            shots = self._connection.execute(
                """SELECT shot_number, photo_id, command_id, status, error,
                          created_at, completed_at
                   FROM capture_shots WHERE batch_id = ? ORDER BY shot_number""",
                (batch_id,),
            ).fetchall()
        batch["shots"] = [dict(shot) for shot in shots]
        return batch

    def get_latest_capture_batch(self, session_id: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                """SELECT batch_id FROM capture_batches
                   WHERE session_id = ? ORDER BY started_at DESC LIMIT 1""",
                (session_id,),
            ).fetchone()
        return self.get_capture_batch(row["batch_id"]) if row else None

    def get_active_capture_batch(self, session_id: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                """SELECT batch_id FROM capture_batches
                   WHERE session_id = ? AND status IN ('countdown', 'capturing')
                   ORDER BY started_at DESC LIMIT 1""",
                (session_id,),
            ).fetchone()
        return self.get_capture_batch(row["batch_id"]) if row else None

    def get_capture_review(self, session_id: str) -> dict | None:
        now = time.time()
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM capture_reviews WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if (
                row is not None
                and row["status"] == "pending"
                and row["decision_deadline"] is not None
                and row["decision_deadline"] <= now
            ):
                with self._connection:
                    self._connection.execute(
                        """UPDATE capture_reviews SET status = 'timed_out',
                               decision_deadline = NULL, decided_at = ?, updated_at = ?
                           WHERE session_id = ? AND status = 'pending'
                             AND decision_deadline <= ?""",
                        (now, now, session_id, now),
                    )
                row = self._connection.execute(
                    "SELECT * FROM capture_reviews WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
        if row is None:
            return None
        review = dict(row)
        review["retake_used"] = bool(review["retake_used"])
        return review

    def decide_capture_review(self, session_id: str) -> dict | None:
        now = time.time()
        with self._lock, self._connection:
            self._connection.execute(
                """UPDATE capture_reviews SET status = 'accepted',
                       decision_deadline = NULL, decided_at = ?, updated_at = ?
                   WHERE session_id = ? AND status = 'pending'
                     AND decision_deadline > ?""",
                (now, now, session_id, now),
            )
        return self.get_capture_review(session_id)

    def get_photo_layout(self, session_id: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM photo_layouts WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        layout = dict(row)
        layout["slots"] = json.loads(layout.pop("slots_json"))
        return layout

    def save_photo_layout(
        self,
        session_id: str,
        batch_id: str,
        frame_id: str,
        slots: list[dict],
    ) -> dict:
        if len(slots) != 4:
            raise ValueError("A photo layout must contain exactly four slots")
        photo_ids = [slot["photo_id"] for slot in slots]
        if len(set(photo_ids)) != 4:
            raise ValueError("Each photo can be selected only once")

        now = time.time()
        with self._lock, self._connection:
            review = self._connection.execute(
                """SELECT batch_id, status FROM capture_reviews
                   WHERE session_id = ?""",
                (session_id,),
            ).fetchone()
            if (
                review is None
                or review["status"] not in {"accepted", "timed_out"}
                or review["batch_id"] != batch_id
            ):
                raise ValueError("The capture review must be completed first")

            batch = self._connection.execute(
                """SELECT status FROM capture_batches
                   WHERE batch_id = ? AND session_id = ?""",
                (batch_id, session_id),
            ).fetchone()
            if batch is None or batch["status"] != "completed":
                raise ValueError("The selected capture batch is not complete")

            placeholders = ",".join("?" for _ in photo_ids)
            photos = self._connection.execute(
                f"""SELECT photo_id FROM photos
                    WHERE session_id = ? AND capture_batch_id = ?
                      AND is_raw = 1 AND photo_id IN ({placeholders})""",
                (session_id, batch_id, *photo_ids),
            ).fetchall()
            if len(photos) != 4:
                raise ValueError("All four selected photos must belong to this set")

            self._connection.execute(
                """INSERT INTO photo_layouts
                   (session_id, batch_id, frame_id, slots_json, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(session_id) DO UPDATE SET
                       batch_id = excluded.batch_id,
                       frame_id = excluded.frame_id,
                       slots_json = excluded.slots_json,
                       updated_at = excluded.updated_at""",
                (
                    session_id,
                    batch_id,
                    frame_id,
                    json.dumps(slots, separators=(",", ":")),
                    now,
                ),
            )
        layout = self.get_photo_layout(session_id)
        if layout is None:
            raise RuntimeError(f"Photo layout missing after saving for {session_id}")
        return layout

    def restore_capture_review_after_retake(
        self, batch_id: str, timeout_sec: int
    ) -> dict | None:
        if not 30 <= timeout_sec <= 60:
            raise ValueError("retake decision timeout must be between 30 and 60 seconds")
        now = time.time()
        with self._lock, self._connection:
            batch = self._connection.execute(
                """SELECT session_id, attempt_number FROM capture_batches
                   WHERE batch_id = ?""",
                (batch_id,),
            ).fetchone()
            if batch is None or batch["attempt_number"] != 2:
                return None
            session = self._connection.execute(
                "SELECT status FROM sessions WHERE session_id = ?",
                (batch["session_id"],),
            ).fetchone()
            active = session is not None and session["status"] == "active"
            deadline = now + timeout_sec if active else None
            self._connection.execute(
                """UPDATE capture_reviews SET status = ?, decision_deadline = ?,
                       decided_at = ?, updated_at = ?
                   WHERE session_id = ? AND status = 'retake_started'""",
                (
                    "pending" if active else "timed_out",
                    deadline,
                    None if active else now,
                    now,
                    batch["session_id"],
                ),
            )
        return self.get_capture_review(batch["session_id"])

    def complete_capture_batch(
        self, batch_id: str, review_timeout_sec: int
    ) -> dict | None:
        if not 30 <= review_timeout_sec <= 60:
            raise ValueError("retake decision timeout must be between 30 and 60 seconds")
        now = time.time()
        deadline = now + review_timeout_sec
        with self._lock, self._connection:
            batch = self._connection.execute(
                """SELECT session_id, attempt_number, target_count FROM capture_batches
                   WHERE batch_id = ? AND status IN ('countdown', 'capturing')""",
                (batch_id,),
            ).fetchone()
            if batch is None:
                return self.get_capture_batch(batch_id)
            saved_shots = self._connection.execute(
                """SELECT COUNT(*) AS count FROM capture_shots cs
                   JOIN photos p ON p.photo_id = cs.photo_id
                   WHERE cs.batch_id = ? AND cs.status = 'completed'
                     AND p.is_raw = 1""",
                (batch_id,),
            ).fetchone()["count"]
            if saved_shots != batch["target_count"]:
                raise ValueError(
                    "Capture sequence cannot complete before all raw photos are saved"
                )

            self._connection.execute(
                """UPDATE capture_batches SET status = 'completed',
                       next_shot_at = NULL, last_error = NULL, completed_at = ?
                   WHERE batch_id = ? AND status IN ('countdown', 'capturing')""",
                (now, batch_id),
            )
            if batch["attempt_number"] == 1:
                self._connection.execute(
                    """INSERT INTO capture_reviews
                       (session_id, batch_id, status, retake_used,
                        decision_deadline, updated_at)
                       VALUES (?, ?, 'pending', 0, ?, ?)""",
                    (batch["session_id"], batch_id, deadline, now),
                )
            else:
                cursor = self._connection.execute(
                    """UPDATE capture_reviews SET batch_id = ?, status = 'pending',
                           decision_deadline = ?, decided_at = NULL, updated_at = ?
                       WHERE session_id = ? AND status = 'retake_started'
                         AND retake_used = 1""",
                    (batch_id, deadline, now, batch["session_id"]),
                )
                if cursor.rowcount == 0:
                    raise ValueError("Retake review state is missing")
        return self.get_capture_batch(batch_id)

    def create_capture_shot(
        self, batch_id: str, shot_number: int, photo_id: str, command_id: str
    ) -> None:
        photo_id = str(uuid.UUID(photo_id))
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO capture_shots
                   (batch_id, shot_number, photo_id, command_id, status, created_at)
                   VALUES (?, ?, ?, ?, 'queued', ?)""",
                (batch_id, shot_number, photo_id, command_id, time.time()),
            )

    def get_capture_shot_by_photo_id(self, photo_id: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM capture_shots WHERE photo_id = ?", (photo_id,)
            ).fetchone()
        return dict(row) if row else None

    def update_capture_shot(
        self, photo_id: str, status: str, error: str | None = None
    ) -> None:
        if status not in {"queued", "completed", "failed"}:
            raise ValueError(f"Unsupported capture shot status: {status}")
        completed_at = time.time() if status in {"completed", "failed"} else None
        with self._lock, self._connection:
            self._connection.execute(
                """UPDATE capture_shots SET status = ?, error = ?, completed_at = ?
                   WHERE photo_id = ?""",
                (status, error, completed_at, photo_id),
            )

    def update_capture_batch(
        self,
        batch_id: str,
        status: str,
        current_shot: int,
        next_shot_at: float | None = None,
        last_error: str | None = None,
    ) -> dict | None:
        allowed_statuses = {
            "countdown",
            "capturing",
            "failed",
            "cancelled",
            "interrupted",
        }
        if status not in allowed_statuses:
            raise ValueError(f"Unsupported capture batch status: {status}")
        completed_at = (
            time.time()
            if status in {"failed", "cancelled", "interrupted"}
            else None
        )
        with self._lock, self._connection:
            self._connection.execute(
                """UPDATE capture_batches SET status = ?, current_shot = ?,
                       next_shot_at = ?, last_error = ?, completed_at = ?
                   WHERE batch_id = ?
                     AND status IN ('countdown', 'capturing')""",
                (
                    status,
                    current_shot,
                    next_shot_at,
                    last_error,
                    completed_at,
                    batch_id,
                ),
            )
        return self.get_capture_batch(batch_id)

    def cancel_capture_batch(self, batch_id: str) -> dict | None:
        with self._lock, self._connection:
            self._connection.execute(
                """UPDATE capture_batches SET status = 'cancelled',
                       next_shot_at = NULL, last_error = 'Cancelled by operator',
                       completed_at = ?
                   WHERE batch_id = ? AND status IN ('countdown', 'capturing')""",
                (time.time(), batch_id),
            )
        return self.get_capture_batch(batch_id)

    def interrupt_active_capture_batches(self) -> None:
        with self._lock, self._connection:
            now = time.time()
            review_timeout_sec = int(
                cfg.get("capture_sequence", {}).get(
                    "retake_decision_timeout_sec", 30
                )
            )
            self._connection.execute(
                """UPDATE capture_batches SET status = 'interrupted',
                       next_shot_at = NULL,
                       last_error = 'Server restarted before sequence completed',
                       completed_at = ?
                   WHERE status IN ('countdown', 'capturing')""",
                (now,),
            )
            self._connection.execute(
                """UPDATE capture_reviews SET status = 'pending',
                       decision_deadline = ?, decided_at = NULL, updated_at = ?
                   WHERE status = 'retake_started'""",
                (now + review_timeout_sec, now),
            )
            self._connection.execute(
                """UPDATE capture_shots SET status = 'failed',
                       error = 'Server restarted before photo upload completed',
                       completed_at = ?
                   WHERE status = 'queued'
                     AND batch_id IN (
                         SELECT batch_id FROM capture_batches WHERE status = 'interrupted'
                     )""",
                (now,),
            )

    def save_photo(
        self,
        session_id: str,
        image: bytes,
        pose_score: int = 0,
        photo_id: str | None = None,
        effect_id: str = "original",
        zoom_factor: float = 1.0,
        face_overlay_id: str | None = None,
        face_count: int = 0,
        face_overlay_applied: bool = False,
        raw_image: bytes | None = None,
        raw_extension: str = "jpg",
    ) -> dict:
        if not 1 <= zoom_factor <= 2.5:
            raise ValueError("zoom_factor must be between 1.0 and 2.5")
        if face_count < 0:
            raise ValueError("face_count cannot be negative")
        photo_id = str(uuid.UUID(photo_id)) if photo_id else str(uuid.uuid4())
        if raw_extension not in {"jpg", "png"}:
            raise ValueError("raw_extension must be jpg or png")
        timestamp = time.time()
        filename = f"{photo_id}.jpg"
        destination = self.photo_dir / filename
        raw_relative_path = None
        raw_destination = None
        if raw_image is not None:
            session_folder = str(uuid.UUID(session_id))
            raw_relative_path = str(
                Path("raw") / session_folder / f"{photo_id}.{raw_extension}"
            )
            raw_destination = self.photo_dir / raw_relative_path
        with self._lock:
            existing = self._connection.execute(
                "SELECT session_id FROM photos WHERE photo_id = ?", (photo_id,)
            ).fetchone()
            if existing:
                if existing["session_id"] != session_id:
                    raise ValueError("Photo ID is already associated with another session")
                return self.get_photo(photo_id)

            try:
                destination.write_bytes(image)
                if raw_destination is not None and raw_image is not None:
                    raw_destination.parent.mkdir(parents=True, exist_ok=True)
                    raw_destination.write_bytes(raw_image)
                with self._connection:
                    self._connection.execute(
                        """INSERT INTO photos
                           (photo_id, session_id, timestamp, file_path, raw_file_path,
                            pose_score,
                            effect_id, zoom_factor, face_overlay_id, face_count,
                            face_overlay_applied)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            photo_id,
                            session_id,
                            timestamp,
                            filename,
                            raw_relative_path,
                            pose_score,
                            effect_id,
                            zoom_factor,
                            face_overlay_id,
                            face_count,
                            int(face_overlay_applied),
                        ),
                    )
            except (OSError, sqlite3.Error):
                for path in (destination, raw_destination):
                    if path is not None:
                        try:
                            path.unlink(missing_ok=True)
                        except OSError:
                            logger.exception("Could not remove incomplete photo file %s", path)
                raise
        session = self.get_session(session_id)
        return {
            "photo_id": photo_id,
            "session_id": session_id,
            "pose_template_id": session["pose_template_id"] if session else None,
            "effect_id": effect_id,
            "face_overlay_id": face_overlay_id,
            "face_count": face_count,
            "face_overlay_applied": face_overlay_applied,
            "zoom_factor": zoom_factor,
            "timestamp": timestamp,
            "file_path": filename,
            "raw_file_path": raw_relative_path,
            "raw_available": raw_relative_path is not None,
            "is_raw": False,
            "capture_batch_id": None,
            "sequence_number": None,
            "pose_score": pose_score,
        }

    def save_raw_photo(
        self,
        session_id: str,
        image: bytes,
        photo_id: str,
        batch_id: str,
        sequence_number: int,
        pose_score: int = 0,
        extension: str = "jpg",
    ) -> dict:
        if not 1 <= sequence_number <= 8:
            raise ValueError("sequence_number must be between 1 and 8")
        if extension not in {"jpg", "png"}:
            raise ValueError("Raw photo extension must be jpg or png")
        photo_id = str(uuid.UUID(photo_id))
        session_id = str(uuid.UUID(session_id))
        batch_id = str(uuid.UUID(batch_id))
        relative_path = str(
            Path("raw")
            / session_id
            / batch_id
            / f"raw_{sequence_number:02}.{extension}"
        )
        destination = self.photo_dir / relative_path
        timestamp = time.time()
        with self._lock:
            shot = self._connection.execute(
                """SELECT cs.photo_id, cb.session_id FROM capture_shots cs
                   JOIN capture_batches cb USING (batch_id)
                   WHERE cs.batch_id = ? AND cs.shot_number = ? AND cs.photo_id = ?""",
                (batch_id, sequence_number, photo_id),
            ).fetchone()
            if shot is None or shot["session_id"] != session_id:
                raise ValueError("Raw photo does not match a capture sequence shot")
            existing = self._connection.execute(
                "SELECT session_id FROM photos WHERE photo_id = ?", (photo_id,)
            ).fetchone()
            if existing:
                if existing["session_id"] != session_id:
                    raise ValueError("Photo ID is already associated with another session")
                return self.get_photo(photo_id)

            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(image)
                with self._connection:
                    self._connection.execute(
                        """INSERT INTO photos
                           (photo_id, session_id, timestamp, file_path, raw_file_path,
                            capture_batch_id, sequence_number, is_raw, pose_score,
                            effect_id, zoom_factor)
                           VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, 'original', 1.0)""",
                        (
                            photo_id,
                            session_id,
                            timestamp,
                            relative_path,
                            relative_path,
                            batch_id,
                            sequence_number,
                            pose_score,
                        ),
                    )
                    self._connection.execute(
                        """UPDATE capture_shots SET status = 'completed', error = NULL,
                               completed_at = ?
                           WHERE batch_id = ? AND shot_number = ? AND photo_id = ?""",
                        (timestamp, batch_id, sequence_number, photo_id),
                    )
            except (OSError, sqlite3.Error):
                try:
                    destination.unlink(missing_ok=True)
                except OSError:
                    logger.exception("Could not remove incomplete raw photo %s", destination)
                raise
        photo = self.get_photo(photo_id)
        if photo is None:
            raise RuntimeError(f"Raw photo metadata missing after saving {photo_id}")
        return photo

    def get_photo(self, photo_id: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                """SELECT p.*, s.pose_template_id FROM photos p
                   JOIN sessions s USING (session_id) WHERE p.photo_id = ?""",
                (photo_id,),
            ).fetchone()
        return self._photo_dict(row) if row else None

    def list_photos(self, session_id: str | None = None) -> list[dict]:
        query = """SELECT p.*, s.pose_template_id FROM photos p
                   JOIN sessions s USING (session_id)"""
        parameters: tuple = ()
        if session_id:
            query += " WHERE p.session_id = ?"
            parameters = (session_id,)
        query += " ORDER BY p.timestamp DESC"
        with self._lock:
            rows = self._connection.execute(query, parameters).fetchall()
        return [self._photo_dict(row) for row in rows]

    @staticmethod
    def _photo_dict(row: sqlite3.Row) -> dict:
        photo = dict(row)
        photo["raw_available"] = photo.get("raw_file_path") is not None
        photo["is_raw"] = bool(photo.get("is_raw", False))
        photo["face_overlay_applied"] = bool(
            photo.get("face_overlay_applied", False)
        )
        return photo

    def record_telemetry(self, device_id: str, metric: str, value: float, timestamp: float) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO telemetry (device_id, metric, value, timestamp) VALUES (?, ?, ?, ?)",
                (device_id, metric, value, timestamp),
            )

    def list_telemetry(self, device_id: str | None = None, limit: int = 100) -> list[dict]:
        query = "SELECT device_id, metric, value, timestamp FROM telemetry"
        parameters: tuple = ()
        if device_id:
            query += " WHERE device_id = ?"
            parameters = (device_id,)
        query += " ORDER BY timestamp DESC LIMIT ?"
        parameters += (limit,)
        with self._lock:
            rows = self._connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def update_device(self, device_id: str, status: str, version: str | None = None) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO devices (device_id, status, version, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(device_id) DO UPDATE SET status = excluded.status,
                       version = excluded.version, updated_at = excluded.updated_at""",
                (device_id, status, version, time.time()),
            )

    def update_led(self, device_id: str, brightness: int) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO devices (device_id, status, updated_at, led_brightness)
                   VALUES (?, 'unknown', ?, ?)
                   ON CONFLICT(device_id) DO UPDATE SET
                       led_brightness = excluded.led_brightness""",
                (device_id, time.time(), brightness),
            )

    def connected_devices(self) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT COUNT(*) AS count FROM devices WHERE status = 'online'"
            ).fetchone()
        return int(row["count"])

    def close(self) -> None:
        with self._lock:
            self._connection.close()
````

## File: Cuoi_ki/Server_Module/shared/__init__.py
````python
"""
shared/__init__.py
Đánh dấu shared/ là Python package để import được.
"""
````

## File: Cuoi_ki/Server_Module/shared/config.py
````python
"""
shared/config.py
----------------
Đọc config.yaml một lần, dùng ở mọi nơi.

Dùng:
    from shared.config import cfg
    host = cfg["server"]["host"]
"""

import os
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_config() -> dict:
    """Load YAML configuration, with an optional PHOTOBOOTH_CONFIG override."""
    config_path = Path(
        os.environ.get(
            "PHOTOBOOTH_CONFIG",
            str(PROJECT_ROOT / "config" / "config.yaml"),
        )
    ).expanduser()
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path

    with config_path.open(encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)
    if not isinstance(config, dict):
        raise ValueError(f"Configuration must be a YAML mapping: {config_path}")

    text_overrides = {
        "PHOTOBOOTH_SERVER_HOST": ("server", "host"),
        "PHOTOBOOTH_CLIENT_HOST": ("server", "client_host"),
        "PHOTOBOOTH_MQTT_HOST": ("mqtt", "broker_host"),
        "PHOTOBOOTH_DEVICE_ID": ("mqtt", "device_id"),
        "PHOTOBOOTH_STATIC_TOKEN": ("server", "static_token"),
        "PHOTOBOOTH_GESTURE_MODEL": ("gesture", "model_path"),
        "PHOTOBOOTH_MQTT_USERNAME": ("mqtt", "username"),
        "PHOTOBOOTH_MQTT_PASSWORD": ("mqtt", "password"),
        "PHOTOBOOTH_MQTT_CA_CERT": ("mqtt", "tls_ca_certs"),
    }
    for variable, (section, key) in text_overrides.items():
        if variable in os.environ:
            config.setdefault(section, {})[key] = os.environ[variable]

    mqtt_tls = os.environ.get("PHOTOBOOTH_MQTT_TLS")
    if mqtt_tls is not None:
        normalized = mqtt_tls.strip().lower()
        if normalized not in {"true", "false", "1", "0"}:
            raise ValueError("PHOTOBOOTH_MQTT_TLS must be true/false or 1/0")
        config.setdefault("mqtt", {})["tls_enabled"] = normalized in {"true", "1"}
    return config


cfg = load_config()
````

## File: Cuoi_ki/Server_Module/shared/logging_config.py
````python
"""Configure rotating per-module logs with a consistent structured context."""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from shared.config import PROJECT_ROOT, cfg


class LogContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.session_id = getattr(record, "session_id", "-")
        record.action = getattr(record, "action", record.getMessage())
        record.payload = getattr(record, "payload", "-")
        return True


def configure_logging(module_name: str) -> None:
    log_dir = Path(cfg.get("storage", {}).get("log_dir", "data/logs")).expanduser()
    if not log_dir.is_absolute():
        log_dir = PROJECT_ROOT / log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s module=%(name)s "
        "session_id=%(session_id)s action=%(action)s payload=%(payload)s"
    )
    context_filter = LogContextFilter()
    handlers = [
        logging.StreamHandler(),
        RotatingFileHandler(
            log_dir / f"{module_name}.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        ),
    ]
    for handler in handlers:
        handler.setFormatter(formatter)
        handler.addFilter(context_filter)
    log_level = logging.getLevelName(os.environ.get("LOG_LEVEL", "INFO").upper())
    logging.basicConfig(
        level=log_level,
        handlers=handlers,
    )
````

## File: Cuoi_ki/Server_Module/shared/mqtt_topics.py
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

    @staticmethod
    def capture(device_id: str) -> str:
        """Server yêu cầu Pi chụp ảnh độ phân giải cao."""
        return f"photobooth/{device_id}/camera/capture"

    @staticmethod
    def photo_status(device_id: str) -> str:
        """Pi thông báo kết quả chụp ảnh."""
        return f"photobooth/{device_id}/camera/status"


# QoS mặc định theo loại dữ liệu
QOS = {
    "telemetry": 0,     # lux, LED status — mất 1 bản không sao
    "command": 1,       # led/set, capture — cần đảm bảo đến nơi
    "status": 1,        # online/offline — quan trọng
}
````

## File: Cuoi_ki/Server_Module/shared/schemas.py
````python
"""Validated JSON contracts used by the Raspberry Pi client and AI server."""

from typing import Literal

from pydantic import BaseModel, Field


class FrameMeta(BaseModel):
    session_id: str = Field(min_length=1)
    device_id: str | None = None
    frame_id: int = Field(ge=0)
    timestamp: float = Field(gt=0)


class WebSocketAuth(BaseModel):
    type: Literal["auth"] = "auth"
    token: str = ""


class KeyPoint(BaseModel):
    name: str
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    visibility: float = Field(ge=0, le=1)


class FeedbackItem(BaseModel):
    body_part: str
    message: str


class GesturePrediction(BaseModel):
    hand_index: int = Field(ge=0)
    gesture: str | None = None
    score: float | None = Field(default=None, ge=0, le=1)
    handedness: str | None = None
    landmarks: list[tuple[float, float]] = Field(default_factory=list)
    world_landmarks: list[tuple[float, float, float]] = Field(default_factory=list)


class GestureFrameResult(BaseModel):
    session_id: str
    frame_id: int = Field(ge=0)
    hand_count: int = Field(default=0, ge=0)
    gestures: list[GesturePrediction] = Field(default_factory=list)
    control_active: bool = False
    control_state: Literal["inactive", "ready", "countdown", "capturing"] = "inactive"
    selected_effect_id: str = "original"
    zoom_factor: float = Field(default=1, ge=1, le=2.5)
    countdown_remaining: int = Field(default=0, ge=0)
    selected_gesture: str | None = None
    selected_gesture_score: float = Field(default=0, ge=0, le=1)
    zoom_active: bool = False
    last_action: str | None = None
    processing_ms: float = Field(default=0, ge=0)


class PoseResult(BaseModel):
    session_id: str
    frame_id: int = Field(ge=0)
    pose_score: int = Field(default=0, ge=0, le=100)
    status: Literal["ok", "adjusting", "no_person", "ai_unavailable"]
    keypoints: list[KeyPoint] = Field(default_factory=list)
    feedback: list[FeedbackItem] = Field(default_factory=list)
    ready_to_capture: bool = False
    hand_count: int = Field(default=0, ge=0)
    gestures: list[GesturePrediction] = Field(default_factory=list)
    processing_ms: float = Field(default=0, ge=0)


class DeviceStatus(BaseModel):
    device_id: str = Field(min_length=1)
    status: Literal["online", "offline"]
    version: str | None = None
    timestamp: float | None = None


class LightSensor(BaseModel):
    device_id: str = Field(min_length=1)
    lux: float = Field(ge=0)
    timestamp: float = Field(gt=0)


class LEDCommand(BaseModel):
    command_id: str = Field(min_length=1)
    brightness: int = Field(ge=0, le=100)


class LEDRequest(BaseModel):
    brightness: int = Field(ge=0, le=100)


class LEDAck(BaseModel):
    command_id: str = Field(min_length=1)
    applied: int = Field(ge=0, le=100)
    success: bool = True
    error: str | None = None


class LEDStatus(BaseModel):
    device_id: str = Field(min_length=1)
    brightness: int = Field(ge=0, le=100)
    timestamp: float = Field(gt=0)


class ButtonEvent(BaseModel):
    device_id: str = Field(min_length=1)
    action: Literal["start_session", "manual_capture", "cancel_countdown"]
    timestamp: float = Field(gt=0)


class SessionCreate(BaseModel):
    device_id: str = Field(min_length=1)
    pose_template_id: str | None = None
    effect_id: str = "original"
    face_overlay_id: str | None = None


class FaceOverlaySelection(BaseModel):
    overlay_id: str | None = None


class PhotoLayoutSlot(BaseModel):
    photo_id: str = Field(min_length=1)
    effect_id: str = "original"
    face_overlay_id: str | None = None


class PhotoLayoutSelection(BaseModel):
    frame_id: str = Field(min_length=1)
    slots: list[PhotoLayoutSlot] = Field(min_length=4, max_length=4)


class SessionInfo(BaseModel):
    session_id: str
    device_id: str
    status: Literal["active", "completed"]
    pose_template_id: str | None = None
    effect_id: str = "original"
    face_overlay_id: str | None = None
    zoom_factor: float = Field(default=1, ge=1, le=2.5)
    created_at: float
    ended_at: float | None = None


class PhotoMeta(BaseModel):
    photo_id: str
    session_id: str
    capture_batch_id: str | None = None
    sequence_number: int | None = Field(default=None, ge=1, le=8)
    is_raw: bool = False
    raw_available: bool = False
    pose_template_id: str | None = None
    effect_id: str = "original"
    face_overlay_id: str | None = None
    face_count: int = Field(default=0, ge=0)
    face_overlay_applied: bool = False
    zoom_factor: float = Field(default=1, ge=1, le=2.5)
    timestamp: float
    file_path: str
    pose_score: int = Field(default=0, ge=0, le=100)


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    uptime_sec: float = Field(ge=0)
    connected_devices: int = Field(ge=0)
    ai_available: bool
    mqtt_connected: bool
````

## File: Cuoi_ki/Server_Module/templates/poses/README.md
````markdown
# Pose template format

Put one UTF-8 JSON file per reference pose in this folder. The `template_id`
must be unique. Keypoint coordinates use body-relative units: the midpoint of
the shoulders is `(0, 0)` and shoulder width is `1`. If shoulders are absent,
the matcher falls back to hip width, then the visible body bounding box.

```json
{
  "template_id": "arms-out",
  "name": "Arms out",
  "tolerance": 0.35,
  "keypoints": {
    "left_shoulder": [-0.5, 0.0],
    "right_shoulder": [0.5, 0.0],
    "left_elbow": [-1.0, 0.0],
    "right_elbow": [1.0, 0.0]
  }
}
```

The server validates templates at startup and exposes them through
`GET /api/v1/poses`. Sessions can select a template with `pose_template_id`.
````

## File: Cuoi_ki/Server_Module/tests/test_face_overlays.py
````python
import json
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from server.face_overlays import (
    FaceLandmarkerUnavailable,
    FaceOverlayProcessor,
    blend_overlay,
    face_geometry,
    load_overlays,
    rotate_overlay_with_pivot,
)


class FaceOverlayTests(unittest.TestCase):
    def test_face_geometry_uses_eye_line_and_anchor_specific_reference_width(self):
        landmarks = [(0.5, 0.5)] * 478
        landmarks[10] = (0.5, 0.25)
        landmarks[33] = (0.3, 0.4)
        landmarks[133] = (0.4, 0.4)
        landmarks[362] = (0.6, 0.4)
        landmarks[263] = (0.7, 0.4)
        landmarks[234] = (0.2, 0.5)
        landmarks[454] = (0.8, 0.5)

        eyes = face_geometry(landmarks, 200, 100, "eyes")
        self.assertIsNotNone(eyes)
        self.assertAlmostEqual(eyes[0][0], 100.0)
        self.assertAlmostEqual(eyes[0][1], 40.0)
        self.assertAlmostEqual(eyes[1], 80.0)
        self.assertAlmostEqual(eyes[2], 0.0)

        forehead = face_geometry(landmarks, 200, 100, "forehead")
        self.assertIsNotNone(forehead)
        self.assertAlmostEqual(forehead[0][0], 100.0)
        self.assertAlmostEqual(forehead[0][1], 25.0)
        self.assertAlmostEqual(forehead[1], 120.0)
        self.assertAlmostEqual(forehead[2], 0.0)

    def test_rotated_overlay_returns_pivot_in_rotated_coordinates(self):
        overlay = np.zeros((10, 20, 4), dtype=np.uint8)
        rotated, pivot = rotate_overlay_with_pivot(overlay, (10.0, 5.0), 0.0)

        self.assertEqual(rotated.shape[:2], (10, 20))
        self.assertEqual(pivot, (10.0, 5.0))

    def test_alpha_blending_clips_overlay_at_frame_edges(self):
        frame = np.zeros((2, 2, 3), dtype=np.uint8)
        overlay = np.zeros((2, 2, 4), dtype=np.uint8)
        overlay[:, :, 0] = 255
        overlay[:, :, 3] = 255

        self.assertTrue(blend_overlay(frame, overlay, -1, -1))
        self.assertEqual(frame[0, 0].tolist(), [255, 0, 0])
        self.assertEqual(int(frame[1, 1].sum()), 0)
        self.assertFalse(blend_overlay(frame, overlay, 3, 3))

    def test_overlay_metadata_requires_rgba_png_and_missing_model_is_explicit(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            asset_dir = Path(temporary_directory)
            overlay_dir = asset_dir / "crown"
            overlay_dir.mkdir()
            (overlay_dir / "metadata.json").write_text(
                json.dumps(
                    {
                        "id": "crown",
                        "name": "Crown",
                        "anchor": "forehead",
                        "width_ratio": 1.15,
                        "pivot": [0.5, 0.85],
                        "offset": [0.0, -0.08],
                        "angle_offset": 0.0,
                    }
                ),
                encoding="utf-8",
            )
            cv2.imwrite(
                str(overlay_dir / "overlay.png"),
                np.zeros((8, 8, 4), dtype=np.uint8),
            )

            self.assertEqual(list(load_overlays(asset_dir)), ["crown"])
            processor = FaceOverlayProcessor(
                {
                    "face_effects": {
                        "asset_dir": str(asset_dir),
                        "model_path": str(asset_dir / "missing.task"),
                    }
                }
            )
            self.assertFalse(processor.available)
            with self.assertRaises(FaceLandmarkerUnavailable):
                processor.prepare(np.zeros((10, 10, 3), dtype=np.uint8), "crown")


if __name__ == "__main__":
    unittest.main()
````

## File: Cuoi_ki/Server_Module/tests/test_gesture_control.py
````python
import unittest

from server.gesture_control import GestureControl, GestureDebouncer, ZoomController


class GestureDebouncerTests(unittest.TestCase):
    def test_requires_hold_and_release_before_same_gesture_repeats(self):
        debounce = GestureDebouncer(hold_frames=3, min_score=0.6)
        first_event = None
        for frame in range(3):
            first_event = debounce.update("Victory", 0.9, 10 + frame * 0.1)
        self.assertEqual(first_event, "Victory")

        self.assertIsNone(debounce.update("Victory", 0.9, 11))
        for frame in range(5):
            debounce.update(None, 0, 12 + frame * 0.1)
        second_event = None
        for frame in range(3):
            second_event = debounce.update("Victory", 0.9, 13 + frame * 0.1)
        self.assertEqual(second_event, "Victory")

    def test_rejects_low_confidence_gesture(self):
        debounce = GestureDebouncer(hold_frames=2, min_score=0.6)
        debounce.update("Open_Palm", 0.5, 10)
        self.assertIsNone(debounce.update("Open_Palm", 0.5, 10.1))

    def test_one_missing_frame_does_not_reset_hold_count(self):
        debounce = GestureDebouncer(hold_frames=3, min_score=0.6)
        debounce.update("Open_Palm", 0.9, 10)
        debounce.update("Open_Palm", 0.9, 10.1)

        self.assertIsNone(debounce.update(None, 0, 10.2))
        self.assertEqual(debounce.count, 2)
        self.assertEqual(debounce.update("Open_Palm", 0.9, 10.3), "Open_Palm")


class GestureControlTests(unittest.TestCase):
    def setUp(self):
        self.control = GestureControl(hold_frames=2, countdown_sec=3)
        self.now = 10.0
        self.effects = ["original", "gray", "sepia"]

    def send(self, gesture):
        self.now += 0.2
        hands = (
            [{"gesture": gesture, "score": 0.9, "landmarks": []}]
            if gesture
            else []
        )
        return self.control.process(
            "session-1", hands, self.control.effect_id, self.effects, self.now
        )

    def release(self):
        for _ in range(5):
            self.send(None)

    def activate(self):
        self.send("Open_Palm")
        result = self.send("Open_Palm")
        self.assertTrue(result["control_active"])
        self.release()

    def test_open_palm_activates_and_victory_cycles_filter(self):
        self.activate()
        self.send("Victory")
        result = self.send("Victory")
        self.assertTrue(result["effect_changed"])
        self.assertEqual(result["selected_effect_id"], "gray")

    def test_open_palm_uses_lower_activation_threshold(self):
        control = GestureControl(
            hold_frames=2, min_score=0.6, activation_min_score=0.5
        )
        result = None
        for timestamp in (10.0, 10.2):
            result = control.process(
                "session-1",
                [{"gesture": "Open_Palm", "score": 0.55}],
                "original",
                self.effects,
                now=timestamp,
            )

        self.assertTrue(result["control_active"])

    def test_thumb_up_countdown_can_be_cancelled_by_closed_fist(self):
        self.activate()
        self.send("Thumb_Up")
        result = self.send("Thumb_Up")
        self.assertEqual(result["control_state"], "countdown")
        self.release()
        self.send("Closed_Fist")
        result = self.send("Closed_Fist")
        self.assertEqual(result["control_state"], "ready")
        self.assertEqual(result["countdown_remaining"], 0)

    def test_countdown_requests_capture_once(self):
        self.activate()
        self.send("Thumb_Up")
        self.send("Thumb_Up")
        result = self.control.process(
            "session-1", [], self.control.effect_id, self.effects, self.now + 3.1
        )
        self.assertTrue(result["capture_requested"])
        self.assertEqual(result["control_state"], "capturing")
        self.assertFalse(
            self.control.process(
                "session-1", [], self.control.effect_id, self.effects, self.now + 3.2
            )["capture_requested"]
        )

    def test_zoom_remains_in_supported_range(self):
        zoom = ZoomController()
        self.assertGreater(zoom.update(0.9, 0.03), 1.0)
        self.assertGreaterEqual(zoom.zoom, 1.0)
        self.assertLessEqual(zoom.zoom, 2.5)


if __name__ == "__main__":
    unittest.main()
````

## File: Cuoi_ki/Server_Module/tests/test_image_processing.py
````python
import unittest

import cv2
import numpy as np

from server.image_processing import EFFECTS, process_image


class ImageProcessingTests(unittest.TestCase):
    def test_effect_catalog_is_allowlisted_and_transforms_jpeg(self):
        image = np.full((16, 16, 3), 100, dtype=np.uint8)
        encoded, jpeg = cv2.imencode(".jpg", image)
        self.assertTrue(encoded)

        processed = process_image(jpeg.tobytes(), "negative")
        decoded = cv2.imdecode(np.frombuffer(processed, dtype=np.uint8), cv2.IMREAD_COLOR)

        self.assertIn("negative", EFFECTS)
        self.assertGreater(float(decoded.mean()), 100)

    def test_unknown_effect_is_rejected(self):
        with self.assertRaises(ValueError):
            process_image(b"not an image", "unknown")

    def test_zoom_is_applied_and_out_of_range_zoom_is_rejected(self):
        image = np.zeros((32, 32, 3), dtype=np.uint8)
        image[8:24, 8:24] = 200
        encoded, jpeg = cv2.imencode(".jpg", image)
        self.assertTrue(encoded)

        zoomed = process_image(jpeg.tobytes(), "original", zoom_factor=2)
        decoded = cv2.imdecode(np.frombuffer(zoomed, dtype=np.uint8), cv2.IMREAD_COLOR)

        self.assertGreater(float(decoded[16, 16].mean()), float(decoded[2, 2].mean()))
        with self.assertRaises(ValueError):
            process_image(jpeg.tobytes(), "original", zoom_factor=3)


if __name__ == "__main__":
    unittest.main()
````

## File: Cuoi_ki/Server_Module/tests/test_photo_layout.py
````python
import unittest
from pathlib import Path

import numpy as np

from server.photo_layout import crop_to_slot, load_frame_templates, render_frame


class PhotoLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.asset_dir = Path(__file__).parent.parent / "assets" / "photo_effects"
        cls.frames = load_frame_templates(cls.asset_dir)

    def test_asset_manifest_loads_all_four_slot_frames(self):
        self.assertEqual(
            set(self.frames),
            {"classic_strip_4", "pastel_pink_strip_4", "grid_2x2_retro"},
        )
        self.assertTrue(all(len(frame.slots) == 4 for frame in self.frames.values()))

    def test_crop_and_frame_render_preserve_photo_slot_dimensions(self):
        source = np.full((80, 120, 3), (15, 80, 220), dtype=np.uint8)
        fitted = crop_to_slot(source, 40, 60)
        self.assertEqual(fitted.shape, (60, 40, 3))

        template = self.frames["classic_strip_4"]
        colors = [
            np.full((20, 20, 3), color, dtype=np.uint8)
            for color in (
                (10, 20, 30),
                (40, 50, 60),
                (70, 80, 90),
                (100, 110, 120),
            )
        ]
        result = render_frame(template, colors)

        self.assertEqual(result.shape, (1800, 600, 3))
        for color, (x, y, width, height) in zip(colors, template.slots):
            center = result[y + height // 2, x + width // 2]
            np.testing.assert_array_equal(center, color[0, 0])


if __name__ == "__main__":
    unittest.main()
````

## File: Cuoi_ki/Server_Module/tests/test_pose_matching.py
````python
import unittest

from server.pose_matching import PoseMatcher, PoseTemplate
from shared.schemas import KeyPoint


class PoseMatcherTests(unittest.TestCase):
    def test_matching_pose_scores_aligned_body_relative_keypoints(self):
        matcher = PoseMatcher()
        matcher.templates = {
            "arms-out": PoseTemplate(
                template_id="arms-out",
                name="Arms out",
                keypoints={
                    "left_shoulder": (-0.5, 0.0),
                    "right_shoulder": (0.5, 0.0),
                    "left_elbow": (-1.0, 0.0),
                    "right_elbow": (1.0, 0.0),
                },
            )
        }
        keypoints = [
            KeyPoint(name="left_shoulder", x=0.4, y=0.3, visibility=0.95),
            KeyPoint(name="right_shoulder", x=0.6, y=0.3, visibility=0.95),
            KeyPoint(name="left_elbow", x=0.3, y=0.3, visibility=0.9),
            KeyPoint(name="right_elbow", x=0.7, y=0.3, visibility=0.9),
        ]

        score, feedback = matcher.match("arms-out", keypoints)

        self.assertEqual(score, 100)
        self.assertEqual(feedback, [])


if __name__ == "__main__":
    unittest.main()
````

## File: Cuoi_ki/Server_Module/tests/test_schemas.py
````python
import unittest

from pydantic import ValidationError

from shared.schemas import (
    FrameMeta,
    LEDCommand,
    LEDRequest,
    PhotoLayoutSelection,
)


class ContractTests(unittest.TestCase):
    def test_frame_metadata_requires_positive_timestamp(self):
        with self.assertRaises(ValidationError):
            FrameMeta(session_id="session", frame_id=1, timestamp=0)

    def test_led_request_limits_brightness_and_command_owns_id(self):
        request = LEDRequest(brightness=70)
        command = LEDCommand(command_id="cmd-1", brightness=request.brightness)
        self.assertEqual(command.brightness, 70)
        with self.assertRaises(ValidationError):
            LEDRequest(brightness=101)

    def test_photo_layout_requires_four_slots(self):
        PhotoLayoutSelection(
            frame_id="classic_strip_4",
            slots=[{"photo_id": str(index)} for index in range(4)],
        )
        with self.assertRaises(ValidationError):
            PhotoLayoutSelection(
                frame_id="classic_strip_4",
                slots=[{"photo_id": "only-one"}],
            )


if __name__ == "__main__":
    unittest.main()
````

## File: Cuoi_ki/Server_Module/tests/test_storage.py
````python
import tempfile
import time
import unittest
import uuid
from pathlib import Path

from server.storage import Storage


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.storage = Storage(
            {
                "storage": {
                    "photo_dir": str(root / "photos"),
                    "db_path": str(root / "photobooth.db"),
                }
            }
        )

    def tearDown(self):
        self.storage.close()
        self.temporary_directory.cleanup()

    def _complete_single_shot_batch(self, session_id, is_retake=False):
        batch = self.storage.create_capture_batch(
            session_id, 1, 10, is_retake=is_retake
        )
        photo_id = str(uuid.uuid4())
        self.storage.create_capture_shot(
            batch["batch_id"], 1, photo_id, uuid.uuid4().hex
        )
        self.storage.save_raw_photo(
            session_id, b"raw photo", photo_id, batch["batch_id"], 1
        )
        return self.storage.complete_capture_batch(batch["batch_id"], 30)

    def _complete_four_shot_batch(self, session_id, accept_review=True):
        batch = self.storage.create_capture_batch(session_id, 4, 1)
        photo_ids = []
        for number in range(1, 5):
            photo_id = str(uuid.uuid4())
            photo_ids.append(photo_id)
            self.storage.create_capture_shot(
                batch["batch_id"], number, photo_id, uuid.uuid4().hex
            )
            self.storage.save_raw_photo(
                session_id, b"raw photo", photo_id, batch["batch_id"], number
            )
        self.storage.complete_capture_batch(batch["batch_id"], 30)
        if accept_review:
            self.storage.decide_capture_review(session_id)
        return batch, photo_ids

    def test_only_one_active_session_per_device(self):
        first = self.storage.create_session("pi01", None)
        with self.assertRaises(ValueError):
            self.storage.create_session("pi01", None)

        self.storage.end_session(first["session_id"])
        second = self.storage.create_session("pi01", None)
        self.assertNotEqual(first["session_id"], second["session_id"])

    def test_session_effect_and_zoom_controls_are_persisted_per_photo(self):
        session = self.storage.create_session("pi01", None)
        updated = self.storage.update_session_controls(
            session["session_id"], "sepia", 1.8
        )

        self.assertEqual(updated["effect_id"], "sepia")
        self.assertEqual(updated["zoom_factor"], 1.8)

        photo = self.storage.save_photo(
            session["session_id"],
            b"jpeg bytes",
            effect_id="sepia",
            zoom_factor=1.8,
        )
        self.assertEqual(photo["effect_id"], "sepia")
        self.assertEqual(photo["zoom_factor"], 1.8)
        self.assertEqual(self.storage.get_photo(photo["photo_id"])["effect_id"], "sepia")

    def test_photo_upload_is_idempotent_and_bound_to_its_session(self):
        first_session = self.storage.create_session("pi01", None)
        photo = self.storage.save_photo(
            first_session["session_id"],
            b"jpeg bytes",
            pose_score=82,
            photo_id="a" * 32,
        )
        duplicate = self.storage.save_photo(
            first_session["session_id"],
            b"jpeg bytes",
            pose_score=82,
            photo_id="a" * 32,
        )
        self.assertEqual(photo["photo_id"], duplicate["photo_id"])
        self.assertTrue((self.storage.photo_dir / photo["file_path"]).is_file())

        self.storage.end_session(first_session["session_id"])
        second_session = self.storage.create_session("pi01", None)
        with self.assertRaises(ValueError):
            self.storage.save_photo(
                second_session["session_id"],
                b"jpeg bytes",
                photo_id="a" * 32,
            )

    def test_face_overlay_selection_and_photo_result_are_persisted(self):
        session = self.storage.create_session("pi01", None, face_overlay_id="crown")
        updated = self.storage.update_session_face_overlay(
            session["session_id"], "glasses"
        )
        self.assertEqual(updated["face_overlay_id"], "glasses")

        photo = self.storage.save_photo(
            session["session_id"],
            b"jpeg bytes",
            face_overlay_id="glasses",
            face_count=2,
            face_overlay_applied=True,
        )
        stored_photo = self.storage.get_photo(photo["photo_id"])
        self.assertEqual(stored_photo["face_overlay_id"], "glasses")
        self.assertEqual(stored_photo["face_count"], 2)
        self.assertEqual(stored_photo["face_overlay_applied"], 1)

    def test_capture_sequence_saves_correlated_raw_photo(self):
        session = self.storage.create_session("pi01", None)
        batch = self.storage.create_capture_batch(session["session_id"], 2, 10)
        photo_id = "b" * 32
        self.storage.create_capture_shot(batch["batch_id"], 1, photo_id, "command-1")

        with self.assertRaises(ValueError):
            other_session = self.storage.create_session("pi02", None)
            self.storage.save_raw_photo(
                other_session["session_id"],
                b"wrong session",
                photo_id,
                batch["batch_id"],
                1,
            )

        raw_bytes = b"original jpeg bytes"
        photo = self.storage.save_raw_photo(
            session["session_id"],
            raw_bytes,
            photo_id,
            batch["batch_id"],
            1,
        )
        self.assertTrue(photo["is_raw"])
        self.assertEqual(photo["capture_batch_id"], batch["batch_id"])
        self.assertEqual(photo["sequence_number"], 1)
        self.assertEqual((self.storage.photo_dir / photo["file_path"]).read_bytes(), raw_bytes)
        saved_batch = self.storage.get_capture_batch(batch["batch_id"])
        self.assertEqual(saved_batch["shots"][0]["status"], "completed")

    def test_capture_batch_terminal_state_cannot_be_overwritten(self):
        session = self.storage.create_session("pi01", None)
        batch = self.storage.create_capture_batch(session["session_id"], 1, 10)
        self.storage.cancel_capture_batch(batch["batch_id"])

        updated = self.storage.update_capture_batch(
            batch["batch_id"], "failed", current_shot=1
        )

        self.assertEqual(updated["status"], "cancelled")

    def test_capture_batch_cannot_complete_before_all_originals_are_saved(self):
        session = self.storage.create_session("pi01", None)
        batch = self.storage.create_capture_batch(session["session_id"], 1, 10)

        with self.assertRaises(ValueError):
            self.storage.complete_capture_batch(batch["batch_id"], 30)

        self.assertEqual(
            self.storage.get_capture_batch(batch["batch_id"])["status"],
            "countdown",
        )
        self.assertIsNone(self.storage.get_capture_review(session["session_id"]))

    def test_capture_review_allows_only_one_retake_and_can_be_accepted(self):
        session = self.storage.create_session("pi01", None)
        initial = self._complete_single_shot_batch(session["session_id"])

        review = self.storage.get_capture_review(session["session_id"])
        self.assertEqual(review["status"], "pending")
        retake = self.storage.create_capture_batch(
            session["session_id"], 1, 10, is_retake=True
        )
        self.assertEqual(retake["attempt_number"], 2)
        self.assertEqual(
            self.storage.get_capture_review(session["session_id"])["status"],
            "retake_started",
        )

        self.storage.cancel_capture_batch(retake["batch_id"])
        restored = self.storage.restore_capture_review_after_retake(
            retake["batch_id"], 30
        )
        self.assertEqual(restored["status"], "pending")
        self.assertTrue(restored["retake_used"])
        self.assertEqual(restored["batch_id"], initial["batch_id"])
        with self.assertRaises(ValueError):
            self.storage.create_capture_batch(
                session["session_id"], 1, 10, is_retake=True
            )

        accepted = self.storage.decide_capture_review(session["session_id"])
        self.assertEqual(accepted["status"], "accepted")

    def test_completed_retake_replaces_the_preview_batch(self):
        session = self.storage.create_session("pi01", None)
        initial = self._complete_single_shot_batch(session["session_id"])

        retake = self._complete_single_shot_batch(
            session["session_id"], is_retake=True
        )

        review = self.storage.get_capture_review(session["session_id"])
        self.assertEqual(review["status"], "pending")
        self.assertTrue(review["retake_used"])
        self.assertEqual(review["batch_id"], retake["batch_id"])
        self.assertNotEqual(review["batch_id"], initial["batch_id"])

    def test_capture_review_timeout_automatically_keeps_current_set(self):
        session = self.storage.create_session("pi01", None)
        self._complete_single_shot_batch(session["session_id"])
        with self.storage._lock, self.storage._connection:
            self.storage._connection.execute(
                """UPDATE capture_reviews SET decision_deadline = ?
                   WHERE session_id = ?""",
                (time.time() - 1, session["session_id"]),
            )

        review = self.storage.get_capture_review(session["session_id"])

        self.assertEqual(review["status"], "timed_out")
        self.assertIsNone(review["decision_deadline"])

    def test_photo_layout_persists_frame_and_per_slot_effects(self):
        session = self.storage.create_session("pi01", None)
        batch, photo_ids = self._complete_four_shot_batch(session["session_id"])
        slots = [
            {
                "photo_id": photo_id,
                "effect_id": effect_id,
                "face_overlay_id": overlay_id,
            }
            for photo_id, effect_id, overlay_id in zip(
                photo_ids,
                ["gray", "sepia", "warm", "original"],
                [None, "crown", None, "glasses"],
            )
        ]

        saved = self.storage.save_photo_layout(
            session["session_id"], batch["batch_id"], "classic_strip_4", slots
        )

        self.assertEqual(saved["frame_id"], "classic_strip_4")
        self.assertEqual(saved["batch_id"], batch["batch_id"])
        self.assertEqual(saved["slots"], slots)

    def test_photo_layout_requires_completed_review_and_four_distinct_photos(self):
        session = self.storage.create_session("pi01", None)
        batch, photo_ids = self._complete_four_shot_batch(
            session["session_id"], accept_review=False
        )
        slots = [
            {
                "photo_id": photo_id,
                "effect_id": "original",
                "face_overlay_id": None,
            }
            for photo_id in photo_ids
        ]

        with self.assertRaises(ValueError):
            self.storage.save_photo_layout(
                session["session_id"], batch["batch_id"], "classic_strip_4", slots
            )

        self.storage.decide_capture_review(session["session_id"])
        slots[1] = {**slots[1], "photo_id": slots[0]["photo_id"]}
        with self.assertRaises(ValueError):
            self.storage.save_photo_layout(
                session["session_id"], batch["batch_id"], "classic_strip_4", slots
            )

        slots[1] = {**slots[1], "photo_id": photo_ids[1]}
        other_session = self.storage.create_session("pi02", None)
        with self.assertRaises(ValueError):
            self.storage.save_photo_layout(
                other_session["session_id"],
                batch["batch_id"],
                "classic_strip_4",
                slots,
            )


if __name__ == "__main__":
    unittest.main()
````

## File: Cuoi_ki/Server_Module/tools/mock_pi_mqtt.py
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

## File: Cuoi_ki/Server_Module/tools/mock_server.py
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

## File: Cuoi_ki/Server_Module/.gitignore
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
data/offline_photos/
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

## File: Cuoi_ki/Server_Module/pyproject.toml
````toml
# AI Smart Photobooth 2.0
# =======================
# Chạy trên: Raspberry Pi 4 (client IoT) + PC (AI Server)
# Phát triển: SSH vào PC, code chung cây thư mục này.

[project]
name = "photobooth-server"
version = "0.2.0"
requires-python = ">=3.10"
dependencies = [
    "numpy>=1.26,<2",
    "pydantic>=2.6,<3",
    "PyYAML>=6,<7",
]

[project.optional-dependencies]
server = [
    "fastapi>=0.110,<1",
    "uvicorn[standard]>=0.27,<1",
    "paho-mqtt>=2.1,<3",
    "opencv-python-headless>=4.8,<5",
    "mediapipe>=0.10.18,<0.11",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["shared*", "server*"]

[tool.setuptools.package-data]
server = ["static/*.html"]
````

## File: Cuoi_ki/Server_Module/README.md
````markdown
# Server module

This standalone project runs on the PC/laptop. It provides the API, AI
processing, photo/session storage, and MQTT control for the Raspberry Pi.

## Configure

Edit `config/config.yaml`:

- Keep `server.host` as `0.0.0.0` so the Pi can connect over the LAN.
- Set `mqtt.broker_host` to the MQTT broker address. Use `127.0.0.1` if the
  broker runs on this PC.
- Set `server.static_token` if authentication is needed; configure the same
  token in the Pi module.
- MediaPipe Gesture Recognizer defaults to
  `../../AI/models/gesture_recognizer.task`, assuming the `AI` folder is next
  to the original `Cuoi_ki` folder. Change `gesture.model_path` if needed.
- MediaPipe Face Landmarker defaults to
  `../../AI/models/face_landmarker.task`. Face overlays are loaded from
  `assets/photo_effects/face_overlays/<overlay_id>/`; each overlay needs an
  RGBA `overlay.png` and `metadata.json`. See
  `assets/photo_effects/README.md` for the metadata format. Restart the Server
  after adding or changing overlay assets.

## Install and run

From inside `Server_Module`:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[server]"
python -m server.main
```

Start the MQTT broker before the Server. The API health check is
`http://127.0.0.1:8000/health`; interactive API documentation is available at
`http://127.0.0.1:8000/docs`. The admin dashboard is available at
`http://127.0.0.1:8000/admin`.

The dashboard displays live hand gestures and Server/MQTT state, overlays hand
landmarks, and can send LED and capture commands to the active Pi session. It
also lets you choose a face overlay for captured photos and view the processed
photo gallery, run a multi-photo capture sequence, and download raw originals.
Face stickers are applied to captured photos only; the live camera preview
remains unchanged.
Gesture controls follow the AI demo: Open_Palm enables control, Thumb_Up starts
a capture countdown, Victory/Pointing_Up cycle image effects, Closed_Fist
cancels a countdown, and the pinch hand pose controls 1.0x-2.5x zoom. Gestures
must meet the configured confidence and hold-frame thresholds. Open_Palm has a
separate activation threshold to account for its lower model confidence. The Pi
stream is configured in `Raspberry_Pi/config/config.yaml` (480x360 at 12 FPS by
default); Pi logs report both AI inference time and observed frame interval/FPS.
The latest 50 recognition results are held in memory until the Server restarts.
Still captures keep their configured high resolution.
If a static token is configured, enter it on the dashboard before connecting.

## Capture an eight-photo set

Start a Pi session and connect to the Admin dashboard. Select **Bắt đầu chụp bộ
ảnh** to capture the configured number of photos sequentially. The default is
eight photos with a 10-second countdown before each shot; the dashboard shows
the countdown, received shots, and errors, and can cancel an active sequence.
The Pi must be connected to the MQTT broker and able to upload images to the
Server.

The sequence does not render filters or overlays. Each received source image is
stored as a clean original at
`data/photos/raw/<session_id>/<batch_id>/raw_01.jpg` through `raw_08.jpg`.
The original is available through the authenticated
`GET /api/v1/photos/{photo_id}/raw` endpoint. Photo and sequence metadata can
be inspected with `GET /api/v1/photos?session_id=<session_id>` and the
`capture_sequence` field in `GET /api/v1/admin/state`.

The values can be changed in `config/config.yaml` under `capture_sequence`:

```yaml
capture_sequence:
  photo_count: 8
  countdown_sec: 10
  shot_timeout_sec: 60
  retake_decision_timeout_sec: 30
```

`photo_count` is limited to 4-8 so every supplied four-slot frame can be filled,
`countdown_sec` to 1-30 seconds, and
`shot_timeout_sec` to 1-300 seconds. A sequence is marked failed if a shot
cannot be confirmed before its timeout. After the first successful set, Admin
shows its eight-photo preview and offers one full-set retake. If there is no
decision within `retake_decision_timeout_sec` (30-60 seconds), the current set
is kept automatically. Retake images are stored as a separate batch; they do
not overwrite the first originals. Choosing **Chốt bộ ảnh và tiếp tục** ends
this review stage; selecting photos and composing a frame are subsequent
steps in the same post-capture flow.

The review controls call `POST /api/v1/sessions/{session_id}/capture-sequence/retake`
and `POST /api/v1/sessions/{session_id}/capture-review/continue`. Admin state
includes the review status and decision deadline.

## Choose photos, frame, and per-slot effects

After choosing **Chốt bộ ảnh và tiếp tục** (or when the review timer expires),
the Admin page opens the layout editor for the current capture batch. Select
one of the three supplied four-slot frames, then choose four different photos
and their order. Each slot has its own built-in color filter and optional face
sticker. The Server center-crops each selected original to its frame slot,
applies that slot's filter, places the sticker afterward, and composites the
transparent frame on top. The selected settings persist in SQLite and can be
changed until the session ends.

Use **Lưu lựa chọn và tạo xem trước** to render and inspect the combined image.
The source originals remain untouched. Frame options are available from
`GET /api/v1/admin/state`; save settings with
`PUT /api/v1/sessions/{session_id}/photo-layout` and fetch the rendered preview
from `GET /api/v1/sessions/{session_id}/photo-layout/preview`. This milestone
does not yet write a final deliverable, print the photo, upload to cloud, or
generate a QR code.

The provided photo-effect pack is installed under `assets/photo_effects/`:
three frame PNGs, four RGBA face overlays with placement metadata, and the
`manifest.json` describing frame slot coordinates. Overlays and frames are
loaded at Server startup; restart the Server after changing these assets.

Runtime database, photos, and logs are stored in this project's `data/`
directory. Run the tests from this folder with:

```bash
python -m unittest discover -s tests
```
````

## File: Cuoi_ki/.gitignore
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
data/offline_photos/
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

## File: Cuoi_ki/README.md
````markdown
# Photobooth modules

The code is split into two standalone projects:

- [Raspberry_Pi](./Raspberry_Pi/README.md): copy this folder to the Raspberry Pi.
- [Server_Module](./Server_Module/README.md): run this folder on the PC/laptop.

Each project contains its own configuration, dependencies, and `shared/`
protocol package, so it can be installed and run independently. Keep the two
copies of `shared/` in sync when changing message schemas or MQTT topics.

The original project documents remain at this folder's root.
````

## File: .gitignore
````
# Python cache
__pycache__/
*.py[cod]
*.pyo

# Python virtual environments
venv/
.venv/
env/

# Environment variables and secrets
.env
.env.*
!.env.example

# Node.js
node_modules/
dist/
build/

# IDE
.idea/
.vscode/

# Logs and temporary files
*.log
*.tmp
temp/
tmp/

# OS
.DS_Store
Thumbs.db

# Jupyter
.ipynb_checkpoints/

# Python testing and cache
.pytest_cache/
.mypy_cache/
.ruff_cache/
````
