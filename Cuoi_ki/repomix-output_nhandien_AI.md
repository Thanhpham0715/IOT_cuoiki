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
- Files matching these patterns are excluded: assets/**, *.xml
- Files matching patterns in .gitignore are excluded
- Files matching default ignore patterns are excluded
- Files are sorted by Git change count (files with more changes are at the bottom)

# Directory Structure
````
cu_chi/
  gesture_photobooth_demo_2.py
deploy/
  photobooth.service
photobooth/
  __init__.py
  engine.py
  gestures.py
  hardware.py
  imaging.py
  storage.py
scripts/
  install.sh
static/
  app.js
  kiosk.css
  kiosk.js
  style.css
templates/
  download.html
  index.html
  kiosk.html
tests/
  browser_server.py
  browser_smoke.py
  test_gestures.py
  test_system.py
.gitignore
bash.txt
manage.py
README.md
requirements-dev.txt
requirements-gestures.txt
requirements-pi.txt
requirements.txt
````

# Files

## File: cu_chi/gesture_photobooth_demo_2.py
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

## File: deploy/photobooth.service
````
[Unit]
Description=Pi Studio Photobooth
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/cuoiky
ExecStart=/home/pi/cuoiky/.venv-gestures/bin/python /home/pi/cuoiky/manage.py run --hardware
Restart=on-failure
RestartSec=5
KillSignal=SIGINT
TimeoutStopSec=15
UMask=0077
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
````

## File: photobooth/__init__.py
````python
import json
import os
import secrets
import time
from functools import wraps
from pathlib import Path
from flask import Flask, abort, jsonify, render_template, request, session, send_from_directory
from werkzeug.security import check_password_hash
from .engine import Booth
from .storage import Store

ROOT=Path(__file__).resolve().parent.parent


def create_app(data_dir=None, demo=False, hardware=False, camera=0, start_worker=True, skip_sensor=False, led_pin=18):
    app=Flask(__name__,template_folder=str(ROOT/'templates'),static_folder=str(ROOT/'static'))
    root=Path(data_dir or os.environ.get('BOOTH_DATA',ROOT/'instance'))
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    credentials=root/'credentials.json'
    if not credentials.exists():
        raise RuntimeError('Chưa tạo tài khoản admin. Chạy: python manage.py init')
    auth=json.loads(credentials.read_text())
    app.config.update(SECRET_KEY=auth['secret'],SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',MAX_CONTENT_LENGTH=16384)
    store=Store(root)
    booth=Booth(store,ROOT/'assets',demo,hardware,camera,skip_sensor,led_pin)
    app.extensions['booth']=booth
    app.extensions['store']=store
    attempts={}

    def admin_required(fn):
        @wraps(fn)
        def wrapper(*a,**kw):
            if not session.get('admin'): abort(403)
            return fn(*a,**kw)
        return wrapper

    @app.before_request
    def security():
        session.permanent=False
        if 'visitor' not in session: session['visitor']=secrets.token_hex(24)
        if 'csrf' not in session: session['csrf']=secrets.token_hex(24)
        if request.method in ('POST','PUT','DELETE'):
            token=request.headers.get('X-CSRF-Token','')
            if not secrets.compare_digest(token,session['csrf']): abort(403)

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Referrer-Policy']='same-origin'
        response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        if request.path.startswith(('/api','/media','/download')): response.headers['Cache-Control']='no-store'
        return response

    @app.errorhandler(ValueError)
    def invalid(exc): return jsonify(error=str(exc)),409

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(413)
    def http_error(exc): return jsonify(error={400:'Yêu cầu không hợp lệ',403:'Không có quyền hoặc phiên đã hết hạn. Hãy tải lại trang.',404:'Không tìm thấy',413:'Dữ liệu quá lớn'}.get(exc.code,'Lỗi')),exc.code

    def body():
        data=request.get_json()
        if not isinstance(data,dict): abort(400)
        return data

    def frames():
        return [p.name for p in sorted((ROOT/'assets/frames').glob('*.png'))]

    @app.get('/')
    @app.get('/admin')
    def index(): return render_template('index.html',csrf=session['csrf'],admin_page=request.path=='/admin')

    @app.get('/kiosk')
    def kiosk(): return render_template('kiosk.html',csrf=session['csrf'])

    @app.get('/download/<sid>')
    def download(sid):
        sess=store.get_session(sid)
        if not sess: abort(404)
        return render_template('download.html',sess=sess,sid=sid)

    @app.get('/download/<sid>/<path:filename>')
    def download_file(sid,filename):
        sess=store.get_session(sid)
        if not sess or filename not in sess['files']: abort(404)
        return send_from_directory(store.photos,filename,as_attachment=request.args.get('view')!='1')

    @app.get('/api/qr/<sid>.png')
    def qr_code(sid):
        sess=store.get_session(sid)
        if not sess: abort(404)
        import io, qrcode
        download_url=request.host_url.rstrip('/')+f'/download/{sid}'
        qr=qrcode.QRCode(version=1,box_size=8,border=2)
        qr.add_data(download_url)
        qr.make(fit=True)
        img=qr.make_image(fill_color='#253b32',back_color='#fffefa')
        buf=io.BytesIO()
        img.save(buf,format='PNG')
        buf.seek(0)
        return app.response_class(buf.getvalue(),mimetype='image/png')

    @app.get('/api/status')
    def status():
        data=booth.status(session['visitor'],session.get('admin',False))
        cfg=store.settings()
        data.update(admin=bool(session.get('admin')),filters=[o for o in booth.camera.options() if o['id'] in cfg['enabled_filters']],frames=frames())
        if session.get('admin'):
            data['settings']=cfg
            data['all_filters']=booth.camera.options()
        return jsonify(data)

    @app.post('/api/login')
    def login():
        ip=request.remote_addr
        now=time.monotonic()
        record=attempts.setdefault(ip,[])
        record[:]=[t for t in record if now-t<300]
        if len(record)>=5: return jsonify(error='Thử lại sau 5 phút'),429
        password=body().get('password','')
        if not isinstance(password,str) or not check_password_hash(auth['password_hash'],password):
            record.append(now)
            return jsonify(error='Sai mật khẩu'),403
        attempts.pop(ip,None)
        session['admin']=True
        store.log('Admin đăng nhập')
        return jsonify(ok=True)

    @app.post('/api/logout')
    def logout():
        session.pop('admin',None)
        return jsonify(ok=True)

    @app.post('/api/control')
    @admin_required
    def control():
        action=body().get('action')
        if action=='start': booth.start()
        elif action=='stop': booth.stop()
        else: abort(400)
        return jsonify(ok=True)

    @app.post('/api/simulate')
    @admin_required
    def simulate():
        if booth.skip_sensor: raise ValueError('Đang bỏ qua cảm biến')
        if booth.hardware.enabled: raise ValueError('Đang sử dụng cảm biến thật')
        value=body().get('near')
        if type(value) is not bool: abort(400)
        booth.hardware.simulated_distance=.6 if value else 2.5
        return jsonify(ok=True)

    @app.post('/api/claim')
    def claim():
        booth.claim(session['visitor'])
        return jsonify(ok=True)

    @app.post('/api/release')
    def release():
        with booth.lock:
            booth._owner(session['visitor'])
            if booth.state=='capturing': raise ValueError('Đang chụp, vui lòng chờ')
            booth.owner=None
            booth.gestures.reset()
            booth.camera.zoom=1.0
        return jsonify(ok=True)

    @app.post('/api/select')
    def select():
        data=body()
        # Omitted fields preserve the current choice; old single-filter clients still work.
        with booth.lock:
            effects=data.get('filters',data.get('filter',booth.effects))
            if isinstance(effects,str): effects=[] if effects=='none' else [effects]
            frame=data.get('frame',booth.frame)
            enabled=store.settings()['enabled_filters']
            if (not isinstance(effects,list) or len(effects)>len(enabled)
                or not all(isinstance(e,str) and e!='none' and e in enabled for e in effects)
                or len(set(effects))!=len(effects)
                or ('mono' in effects and 'sepia' in effects)
                or not isinstance(frame,str) or frame not in ['none']+frames()): abort(400)
            booth.select(session['visitor'],effects,frame)
        return jsonify(ok=True)

    @app.post('/api/capture')
    def capture(): return jsonify(id=booth.capture(session['visitor']))

    @app.get('/api/preview.jpg')
    def preview():
        with booth.lock:
            if not session.get('admin') and (booth.owner!=session['visitor'] or (booth.lease<time.monotonic() and booth.state!='capturing')): abort(403)
            if not booth.camera.jpeg: return '',204
            return app.response_class(booth.camera.jpeg,mimetype='image/jpeg')

    @app.get('/assets/frames/<path:name>')
    def frame_asset(name):
        if name not in frames(): abort(404)
        return send_from_directory(ROOT/'assets/frames',name)

    @app.get('/api/sessions')
    def sessions(): return jsonify(store.sessions(None if session.get('admin') else session['visitor']))

    @app.get('/media/<name>')
    def media(name):
        allowed=store.sessions(None if session.get('admin') else session['visitor'])
        allowed_files=[f for s in allowed for f in s['files']]
        sid=request.args.get('sid')
        if sid:
            sess=store.get_session(sid)
            if sess and name in sess['files']: allowed_files.append(name)
        if name not in allowed_files: abort(404)
        return send_from_directory(store.photos,name,as_attachment=request.args.get('download')=='1')

    @app.delete('/api/sessions/<sid>')
    @admin_required
    def delete(sid):
        with booth.lock:
            if booth.state=='capturing' and booth.sid==sid: raise ValueError('Không thể xóa phiên đang chụp')
            if not store.delete(sid): abort(404)
            store.log('Admin xóa phiên '+sid[:8])
        return jsonify(ok=True)

    @app.get('/api/events')
    @admin_required
    def events(): return jsonify(store.events())

    @app.post('/api/settings')
    @admin_required
    def settings():
        data=body()
        ranges={'distance_m':(.2,3.5),'absence_seconds':(5,300),'photo_count':(1,8),'countdown':(1,10),'retention_days':(1,90)}
        if set(data)!=set(ranges)|{'enabled_filters','default_filter'}: abort(400)
        for k,(lo,hi) in ranges.items():
            v=data[k]
            if type(v) not in (int,float) or not lo<=v<=hi or (k!='distance_m' and type(v) is not int): abort(400)
        enabled=data['enabled_filters']
        known={o['id'] for o in booth.camera.options()}
        if not isinstance(enabled,list) or not all(isinstance(e,str) and e in known for e in enabled) or 'none' not in enabled or data['default_filter'] not in enabled: abort(400)
        with booth.lock:
            if booth.state=='capturing': raise ValueError('Hãy đợi phiên chụp kết thúc trước khi đổi cấu hình')
            store.configure(data)
            booth.effects=[effect for effect in booth.effects if effect in enabled]
        store.log('Admin cập nhật cấu hình')
        return jsonify(ok=True)

    if start_worker: booth.run()
    return app
````

## File: photobooth/engine.py
````python
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
import cv2
from .hardware import Hardware
from .imaging import Imaging
from .gestures import GestureInput


class Booth:
    def __init__(self, store, assets, demo=False, hardware=False, camera=0, skip_sensor=False, led_pin=18):
        self.store=store
        self.store.recover()
        self.camera=Imaging(assets,demo,camera)
        self.gestures=GestureInput(assets/'models/gesture_recognizer.task',enabled=not demo)
        self.hardware=Hardware(hardware,skip_sensor,led_pin)
        self.skip_sensor=skip_sensor
        self.demo=demo
        self.lock=threading.RLock()
        self.shutdown=threading.Event()
        self.state='stopped'
        self.owner=None
        self.lease=0
        self.effects=[]
        self.frame='none'
        self.sid=None
        self.frames=[]
        self.files=[]
        self.last_completed_sid=None
        self.countdown=0
        self.next_shot=0
        self.last_seen=0
        self.near_count=0
        self.distance=None
        self.last_cleanup=0
        self.thread=None
        if self.hardware.button:
            self.hardware.button.when_pressed=self.toggle

    def run(self):
        self.thread=threading.Thread(target=self._loop,daemon=True,name='booth-worker')
        self.thread.start()

    def toggle(self):
        self.start() if self.state=='stopped' else self.stop()

    def start(self):
        with self.lock:
            if self.state!='stopped': return
            if self.hardware.error: raise ValueError(self.hardware.error)
            self.state='ready' if self.skip_sensor else 'waiting'
            self.hardware.light(self.skip_sensor)
            self.last_seen=0
            self.near_count=0
            self.store.log('Admin/nút vật lý: Start')

    def stop(self):
        with self.lock:
            if self.state=='capturing': self._finish('interrupted')
            self.state='stopped'
            self.owner=None
            self.countdown=0
            self.hardware.light(False)
            self.camera.close()
            self.gestures.reset()
            self.store.log('Admin/nút vật lý: Stop')

    def claim(self, owner):
        with self.lock:
            if self.state not in ('ready','capturing'): raise ValueError('Booth chưa sẵn sàng')
            now=time.monotonic()
            if self.owner and self.owner!=owner and (self.state=='capturing' or self.lease>now):
                raise ValueError('Một người dùng khác đang điều khiển booth')
            if self.owner!=owner:
                default=self.store.settings()['default_filter']
                self.effects=[] if default=='none' else [default]
                self.frame='none'
            if self.owner!=owner:
                self.gestures.reset()
                self.camera.zoom=1.0
            self.owner=owner
            self.lease=now+120

    def select(self, owner, effect, frame):
        with self.lock:
            self._owner(owner)
            if self.state!='ready': raise ValueError('Không thể đổi hiệu ứng khi đang chụp')
            self.effects=list(effect) if isinstance(effect,list) else ([] if effect=='none' else [effect])
            self.frame=frame

    def _owner(self, owner):
        if self.owner!=owner or (self.lease<time.monotonic() and self.state!='capturing'):
            raise ValueError('Hãy nhận quyền điều khiển trước')
        self.lease=time.monotonic()+120

    def capture(self, owner):
        with self.lock:
            self._owner(owner)
            if self.state!='ready': raise ValueError('Booth chưa sẵn sàng hoặc đang chụp')
            if self.camera.frame is None or time.monotonic()-self.camera.updated>2:
                raise ValueError('Chưa có hình camera mới')
            if shutil.disk_usage(self.store.root).free<100*1024*1024:
                raise ValueError('Bộ nhớ còn dưới 100 MB. Liên hệ admin để dọn ảnh.')
            self.sid=uuid.uuid4().hex
            self.frames=[]
            self.files=[]
            self.capture_config=self.store.settings()
            self.store.create(self.sid,owner)
            self.state='capturing'
            self.countdown=self.capture_config['countdown']
            self.next_shot=time.monotonic()+self.countdown
            self.store.log('Bắt đầu phiên '+self.sid[:8])
            return self.sid

    def _write(self, name, image):
        path=self.store.photos/name
        if not cv2.imwrite(str(path),image):
            raise RuntimeError('Không lưu được ảnh: '+name)
        self.files.append(name)
        self.store.finish(self.sid,'capturing',self.files)

    def _finish(self, status):
        self.store.finish(self.sid,status,self.files)
        self.store.log('Phiên '+self.sid[:8]+': '+status)
        self.state='ready'
        self.countdown=0
        self.lease=time.monotonic()+120

    def tick(self, now=None):
        with self.lock:
            now=time.monotonic() if now is None else now
            cfg=self.store.settings()
            if self.state=='stopped': return
            self.distance=self.hardware.distance()
            near=self.skip_sensor or (self.distance is not None and 0<self.distance<cfg['distance_m'])
            self.near_count=self.near_count+1 if near else 0
            if self.near_count>=3:
                self.last_seen=now
                if self.state=='waiting':
                    self.state='ready'
                    self.hardware.light(True)
                    self.store.log('Có vật thể gần: bật LED và camera')
            if not self.skip_sensor and self.state=='ready' and now-self.last_seen>cfg['absence_seconds']:
                self.state='waiting'
                self.owner=None
                self.gestures.reset()
                self.hardware.light(False)
                self.camera.close()
            if self.state not in ('ready','capturing'): return
            if not self.camera.read(self.effects,self.frame):
                if self.state=='capturing': self._finish('failed')
                return
            self._gestures()
            if self.state=='capturing':
                self.countdown=max(0,int(self.next_shot-now+.999))
                if now>=self.next_shot:
                    self.frames.append(self.camera.frame.copy())
                    self._write(f'{self.sid}_{len(self.frames)}.jpg',self.camera.with_frame(self.frames[-1],self.frame))
                    if len(self.frames)>=self.capture_config['photo_count']:
                        self._write(f'{self.sid}_strip.jpg',self.camera.collage(self.frames,self.frame))
                        self.last_completed_sid=self.sid
                        self._finish('complete')
                    else:
                        self.next_shot=now+self.capture_config['countdown']

    def _gestures(self):
        # A web owner is required so captured images retain their private owner.
        if not self.owner or (self.lease<time.monotonic() and self.state!='capturing'):
            self.gestures.reset()
            self.camera.zoom=1.0
            return
        event,zoom=self.gestures.process(self.camera.raw,self.camera.faces,self.state=='ready')
        if zoom is not None:
            self.camera.zoom=zoom
        if not event:
            return
        message='Cử chỉ không có lệnh trong trạng thái hiện tại'
        if event=='Open_Palm' and self.state=='ready':
            self.gestures.active=True
            message='Đã bật điều khiển cử chỉ'
        if not self.gestures.active:
            self._gesture_log(event,'Chưa kích hoạt: hãy giơ bàn tay mở trước')
            return
        if event=='Thumb_Up' and self.state=='ready':
            try:
                self.capture(self.owner)
                message='Đã bắt đầu đếm ngược chụp'
            except ValueError as exc:
                message=str(exc)
        elif event=='Closed_Fist' and self.state=='capturing':
            self._finish('interrupted')
            message='Đã hủy phần còn lại của phiên chụp'
        elif event in ('Victory','Pointing_Up') and self.state=='ready':
            options=[o['id'] for o in self.camera.options()
                     if o['id'] in self.store.settings()['enabled_filters']]
            current=self.effects[0] if self.effects else 'none'
            index=options.index(current) if current in options else 0
            effect=options[(index+(1 if event=='Victory' else -1))%len(options)]
            self.effects=[] if effect=='none' else [effect]
            message='Đã đổi hiệu ứng: '+effect
        self._gesture_log(event,message)

    def _gesture_log(self, event, message):
        record=dict(time=datetime.now().astimezone().isoformat(timespec='seconds'),
                    label=event,message=message)
        self.gestures.events.append(record)
        self.gestures.events[:]=self.gestures.events[-8:]
        print(f"[GESTURE] {record['time']} {event}: {message}",flush=True)

    def _loop(self):
        while not self.shutdown.is_set():
            begin=time.monotonic()
            try:
                self.tick()
                if begin-self.last_cleanup>3600:
                    self.cleanup()
                    self.last_cleanup=begin
            except Exception as exc:
                with self.lock:
                    self.camera.error=str(exc)
                    if self.state=='capturing': self._finish('failed')
                self.store.log('Lỗi worker: '+str(exc))
            self.shutdown.wait(max(.01,.125-(time.monotonic()-begin)))

    def cleanup(self):
        with self.lock:
            cutoff=datetime.now(timezone.utc)-timedelta(days=self.store.settings()['retention_days'])
            for item in self.store.sessions():
                if item['status']!='capturing' and datetime.fromisoformat(item['created'])<cutoff:
                    self.store.delete(item['id'])

    def status(self, owner=None, admin=False):
        with self.lock:
            if self.owner==owner: self.lease=time.monotonic()+120
            return dict(state=self.state, led=self.hardware.led_on, distance_m=round(self.distance,2) if self.distance is not None else None,
                camera_ready=self.camera.frame is not None, error=self.camera.error or self.hardware.error,
                gesture_enabled=self.gestures.enabled, gesture_active=self.gestures.active,
                gesture_error=self.gestures.error, gesture_last=self.gestures.last_event, zoom=self.camera.zoom,
                gesture_diagnostic=dict(self.gestures.diagnostic) if admin or self.owner==owner else {},
                gesture_events=list(self.gestures.events) if admin or self.owner==owner else [],
                demo=self.demo, hardware=self.hardware.enabled, skip_sensor=self.skip_sensor, owned=self.owner==owner,
                busy=bool(self.owner and self.owner!=owner and (self.lease>time.monotonic() or self.state=='capturing')),
                filter=self.effects[0] if self.effects else 'none', selected_filters=list(self.effects), frame=self.frame, countdown=self.countdown, taken=len(self.frames) if self.state=='capturing' else 0,
                total=self.store.settings()['photo_count'], last_sid=self.last_completed_sid, free_mb=shutil.disk_usage(self.store.root).free//(1024*1024) if admin else None)

    def close(self):
        self.shutdown.set()
        if self.thread: self.thread.join(timeout=5)
        self.stop()
        self.gestures.close()
        self.hardware.close()
````

## File: photobooth/gestures.py
````python
"""MediaPipe gestures and center-face ownership; no person detector or YOLO."""
import math
import time
from pathlib import Path
import cv2


def dist(a, b):
    return math.hypot(a[0]-b[0], a[1]-b[1])


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



def choose_hand(hands, faces, width):
    """Accept only hands closest to the center face, within its reach.

    Face geometry is an ownership heuristic, not skeletal person tracking.
    Reject ambiguous assignments rather than letting two people control at once.
    """
    if not faces:
        return None
    center=min(range(len(faces)), key=lambda i: abs(faces[i][0]+faces[i][2]/2-width/2))
    candidates=[]
    for hand in hands:
        wrist=hand['pts'][0]
        distances=[]
        for x,y,w,h in faces:
            # Hands can extend sideways and down from the face.
            d=math.hypot((wrist[0]-x-w/2)/w, (wrist[1]-y-h)/h)
            distances.append(d)
        order=sorted(range(len(faces)),key=lambda i: distances[i])
        if order[0]!=center or distances[center]>2.8:
            continue
        if len(order)>1 and distances[order[1]]-distances[center]<.35:
            continue
        candidates.append(hand)
    return max(candidates,key=lambda hand: hand['score']) if candidates else None


class GestureInput:
    def __init__(self, model_path, enabled=True):
        self.model_path=Path(model_path)
        self.enabled=enabled
        self.recognizer=None
        self.error=None
        self.attempted=False
        self.debounce=GestureDebouncer(hold_frames=4)
        self.zoom=ZoomController()
        self.active=False
        self.zoom_count=0
        self.zoom_missing=0
        self.timestamp=0
        self.previous=0
        self.last_event=None
        self.diagnostic={}
        self.events=[]

    def reset(self):
        self.last_event=None
        self.diagnostic={}
        self.events=[]
        self.active=False
        self.debounce.reset()
        self.zoom=ZoomController()
        self.zoom_count=self.zoom_missing=0
        self.previous=0

    def process(self, frame, faces, ready):
        if not self.enabled:
            return None, None
        if not self.attempted:
            self.attempted=True
            try:
                import mediapipe as mp
                from mediapipe.tasks import python
                from mediapipe.tasks.python import vision
                self.mp=mp
                self.recognizer=vision.GestureRecognizer.create_from_options(
                    vision.GestureRecognizerOptions(
                        base_options=python.BaseOptions(model_asset_path=str(self.model_path)),
                        running_mode=vision.RunningMode.VIDEO, num_hands=6))
            except Exception as exc:
                self.error=f'Cử chỉ chưa sẵn sàng: {exc}'
        if self.recognizer is None:
            return None, None
        now=time.monotonic()
        dt=now-self.previous if self.previous else .125
        self.previous=now
        self.timestamp=max(self.timestamp+1,int(now*1000))
        try:
            image=self.mp.Image(image_format=self.mp.ImageFormat.SRGB,
                data=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
            result=self.recognizer.recognize_for_video(image,self.timestamp)
        except Exception as exc:
            self.error=f'Lỗi nhận cử chỉ: {exc}'
            self.reset()
            return None, None
        self.error=None
        h,w=frame.shape[:2]
        hands=[]
        for i, landmarks in enumerate(result.hand_landmarks):
            category=result.gestures[i][0] if result.gestures[i] else None
            world=result.hand_world_landmarks[i] if result.hand_world_landmarks else None
            hands.append(dict(pts=[(p.x*w,p.y*h) for p in landmarks],
                world=[(p.x,p.y,p.z) for p in world] if world else None,
                label=category.category_name if category else None,
                score=category.score if category else 0))
        chosen=choose_hand(hands,faces,w)
        message=('Chưa thấy khuôn mặt' if not faces else
                 'Chưa thấy bàn tay' if not hands else
                 'Tay chưa thuộc người ở giữa hoặc vị trí còn mơ hồ' if chosen is None else
                 'Đang theo dõi tay của người ở giữa')
        self.diagnostic=dict(label=chosen['label'] if chosen else None,
            score=round(float(chosen['score']),3) if chosen else 0,
            hands=len(hands),faces=len(faces),message=message,zooming=False)
        if chosen is not None and self.active and ready and zoom_pose_info(chosen['pts'],self.zoom_count>=3)[0]:
            self.diagnostic["zooming"]=True
            self.zoom_count+=1
            self.zoom_missing=0
            self.debounce.update(None,0,now)
            if self.zoom_count>=3:
                self.zoom.update(pinch_ratio(chosen['pts'],chosen['world']),dt)
                return None,self.zoom.zoom
            return None,None
        self.zoom_missing+=1
        if self.zoom_missing<=3 and self.zoom_count:
            self.debounce.update(None,0,now)
            return None,None
        self.zoom_count=0
        self.zoom.release()
        event=self.debounce.update(chosen['label'] if chosen else None,
            chosen['score'] if chosen else 0,now)
        if event:
            self.last_event=event
        return event,None

    def close(self):
        if self.recognizer:
            self.recognizer.close()
            self.recognizer=None
        self.attempted=False
        self.reset()
````

## File: photobooth/hardware.py
````python
import logging


class Hardware:
    def __init__(self, enabled=False, skip_sensor=False, led_pin=18):
        self.enabled=enabled
        self.skip_sensor=skip_sensor
        self.sensor=self.button=self.led=None
        self.error=None
        self.simulated_distance=2.0
        self.led_on=False
        if enabled:
            stage='khởi tạo thư viện GPIO'
            try:
                from gpiozero import LED, Button, DistanceSensor
                stage=f'LED GPIO{led_pin}'
                self.led=LED(led_pin)
                stage='nút nhấn GPIO17'
                self.button=Button(17,pull_up=True,bounce_time=.15)
                if not skip_sensor:
                    stage='HC-SR04 GPIO23/24'
                    self.sensor=DistanceSensor(echo=24,trigger=23,max_distance=4,queue_len=5,partial=True)
            except Exception as exc:
                self.error=f'GPIO chưa sẵn sàng tại {stage}: {type(exc).__name__}: {exc}'
                logging.getLogger(__name__).exception(self.error)
                self.close()

    def distance(self):
        if self.skip_sensor:
            return None
        if self.enabled:
            return self.sensor.distance*4 if self.sensor else None
        return self.simulated_distance

    def light(self, value):
        self.led_on=bool(value) and not bool(self.error)
        if self.led:
            self.led.value=int(self.led_on)

    def close(self):
        for device in (self.led,self.button,self.sensor):
            if device:
                device.close()
        self.led=self.button=self.sensor=None
        self.led_on=False
````

## File: photobooth/imaging.py
````python
import json
import math
import time
from pathlib import Path
import cv2
import numpy as np
from PIL import Image


class Imaging:
    def __init__(self, assets, demo=False, camera=0):
        self.assets, self.demo, self.index = Path(assets), demo, camera
        self.cap = None
        self.error = None
        self.jpeg = None
        self.frame = None
        self.updated = 0
        self.raw = None
        self.zoom = 1.0
        self.faces = []
        self.face_angles = []
        self.overlay = {}
        self.frame_cache = {}
        self.filters = json.loads((self.assets / 'filters/filters.json').read_text())
        for key, item in self.filters.items():
            self.overlay[key] = np.array(Image.open(self.assets / 'filters' / item['file']).convert('RGBA'))[:, :, [2, 1, 0, 3]]
        
        # Mô hình nhận diện khuôn mặt OpenCV
        cascade = self.assets / 'models/haarcascade_frontalface_default.xml'
        if not cascade.exists() and hasattr(cv2, 'data'):
            cascade = Path(cv2.data.haarcascades) / cascade.name
        self.detector = cv2.CascadeClassifier(str(cascade))
        if self.detector.empty():
            raise RuntimeError('Không tìm được mô hình khuôn mặt OpenCV')
            
        # Mô hình nhận diện mắt để tính góc nghiêng mặt (Rotation without Cropping)
        eye_cascade = self.assets / 'models/haarcascade_eye.xml'
        if not eye_cascade.exists() and hasattr(cv2, 'data'):
            eye_cascade = Path(cv2.data.haarcascades) / eye_cascade.name
        self.eye_detector = cv2.CascadeClassifier(str(eye_cascade)) if eye_cascade.exists() else None
        if self.eye_detector and self.eye_detector.empty():
            self.eye_detector = None
            
        self.counter = 0
        self.last_attempt = 0

    def options(self):
        return [dict(id='none', label='Tự nhiên')] + [dict(id=k, label=v['label']) for k,v in self.filters.items()] + [dict(id='mono',label='Đen trắng'), dict(id='sepia',label='Hoài cổ')]

    @staticmethod
    def rotate_without_cropping(image, angle):
        """
        Thuật toán xoay ảnh bảo toàn kích thước (Rotation without Cropping):
        Xoay ảnh RGBA góc `angle` (độ) quanh tâm mà không bị xén góc.
        Tự động tính toán khung bao mới (bounding box) mở rộng để giữ trọn vẹn sticker.
        """
        if abs(angle) < 0.5:
            return image
        h, w = image.shape[:2]
        cx, cy = w / 2.0, h / 2.0
        M = cv2.getRotationMatrix2D((cx, cy), -angle, 1.0)
        cos = np.abs(M[0, 0])
        sin = np.abs(M[0, 1])
        new_w = max(1, int(np.ceil(h * sin + w * cos)))
        new_h = max(1, int(np.ceil(h * cos + w * sin)))
        M[0, 2] += (new_w / 2.0) - cx
        M[1, 2] += (new_h / 2.0) - cy
        return cv2.warpAffine(
            image, M, (new_w, new_h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0, 0)
        )

    @staticmethod
    def blend(frame, overlay, x, y, width=None):
        """
        Kỹ thuật trộn ảnh kênh Alpha tối ưu hóa (Optimized Alpha Blending).
        """
        if width is not None and width != overlay.shape[1]:
            height = max(1, round(overlay.shape[0] * width / overlay.shape[1]))
            overlay = cv2.resize(overlay, (max(1, width), height))
        height, width = overlay.shape[:2]
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(frame.shape[1], x + width), min(frame.shape[0], y + height)
        if x1 <= x0 or y1 <= y0:
            return
        crop = overlay[y0-y:y1-y, x0-x:x1-x]
        a = crop[:, :, 3:4].astype(np.float32) / 255.0
        frame[y0:y1, x0:x1] = (crop[:, :, :3] * a + frame[y0:y1, x0:x1] * (1.0 - a)).astype(np.uint8)

    def _detect_eyes_and_angles(self, frame):
        """
        Xác định góc nghiêng (Roll Angle) cho từng khuôn mặt dựa trên trục 2 mắt.
        """
        if not self.faces or not self.eye_detector:
            self.face_angles = [0.0] * len(self.faces)
            return
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        new_angles = []
        for i, (x, y, w, h) in enumerate(self.faces):
            prev_angle = self.face_angles[i] if i < len(self.face_angles) else 0.0
            angle = prev_angle
            roi_h = int(h * 0.55)
            roi_gray = gray[y:y+roi_h, x:x+w]
            eyes = self.eye_detector.detectMultiScale(
                roi_gray, scaleFactor=1.1, minNeighbors=3,
                minSize=(max(10, int(w * 0.1)), max(10, int(h * 0.1))),
                maxSize=(int(w * 0.45), int(h * 0.45))
            )
            if len(eyes) >= 2:
                eyes = sorted(eyes, key=lambda e: e[0])
                e1, e2 = eyes[0], eyes[-1]
                p1 = (e1[0] + e1[2] / 2.0, e1[1] + e1[3] / 2.0)
                p2 = (e2[0] + e2[2] / 2.0, e2[1] + e2[3] / 2.0)
                dx = p2[0] - p1[0]
                dy = p2[1] - p1[1]
                if dx > w * 0.2:
                    measured = math.degrees(math.atan2(dy, dx))
                    if abs(measured) > 45:
                        measured = 45.0 if measured > 0 else -45.0
                    # Bộ lọc làm mượt chống rung giật góc nghiêng
                    angle = 0.65 * prev_angle + 0.35 * measured
            new_angles.append(round(angle, 1))
        self.face_angles = new_angles

    def read(self, effects, frame_id='none'):
        if isinstance(effects, str):
            effects = [] if effects == 'none' else [effects]
        if self.demo:
            frame = np.full((480, 640, 3), (47, 32, 22), dtype=np.uint8)
            cv2.circle(frame, (320, 240), 100, (151, 197, 226), -1)
            cv2.circle(frame, (287, 220), 10, (35, 35, 35), -1)
            cv2.circle(frame, (353, 220), 10, (35, 35, 35), -1)
            cv2.ellipse(frame, (320, 260), (40, 23), 0, 0, 180, (35, 35, 35), 4)
            cv2.putText(frame, 'DEMO - NOT LIVE CAMERA', (20, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (235, 235, 235), 1)
            self.faces = [(220, 140, 200, 200)]
            self.face_angles = [0.0]
        else:
            if self.cap is None:
                if time.monotonic() - self.last_attempt < 2:
                    return False
                self.last_attempt = time.monotonic()
                self.cap = cv2.VideoCapture(self.index)
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            ok, frame = self.cap.read()
            if not ok:
                self.close()
                self.error = 'Không đọc được webcam. Kiểm tra USB và chỉ số camera.'
                return False
            frame = cv2.flip(frame, 1)
            if self.counter % 3 == 0:
                small = cv2.resize(frame, (320, 240))
                found = self.detector.detectMultiScale(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), 1.15, 5, minSize=(35, 35))
                sx, sy = frame.shape[1] / 320.0, frame.shape[0] / 240.0
                self.faces = [(int(x * sx), int(y * sy), int(w * sx), int(h * sy)) for x, y, w, h in found]
                self._detect_eyes_and_angles(frame)
        self.raw = frame.copy()
        self.counter += 1
        
        if 'mono' in effects:
            frame = cv2.cvtColor(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
        elif 'sepia' in effects:
            frame = np.clip(cv2.transform(frame.astype(np.float32), np.array([[.131, .534, .272], [.168, .686, .349], [.189, .769, .393]], dtype=np.float32)), 0, 255).astype(np.uint8)
            
        for filter_id in effects:
            if filter_id not in self.overlay:
                continue
            config = self.filters[filter_id]
            overlay_base = self.overlay[filter_id]
            for i, (x, y, w, h) in enumerate(self.faces):
                angle = self.face_angles[i] if i < len(self.face_angles) else 0.0
                target_w = max(1, round(w * config['width']))
                target_h = max(1, round(overlay_base.shape[0] * target_w / overlay_base.shape[1]))
                scaled = cv2.resize(overlay_base, (target_w, target_h))
                
                # Áp dụng thuật toán xoay ảnh không bị cắt góc
                if abs(angle) >= 1.0:
                    rotated = self.rotate_without_cropping(scaled, angle)
                else:
                    rotated = scaled
                    
                # Tính vị trí tâm dán sticker theo góc nghiêng của đầu
                cx0 = x + w / 2.0
                cy0 = y + h * 0.5
                dy0 = h * (config['anchor_y'] - 0.5)
                rad = math.radians(angle)
                cx = cx0 - dy0 * math.sin(rad)
                cy = cy0 + dy0 * math.cos(rad)
                
                rx = round(cx - rotated.shape[1] / 2.0)
                ry = round(cy - rotated.shape[0] / 2.0)
                self.blend(frame, rotated, rx, ry)
                
        if self.zoom > 1.001:
            h, w = frame.shape[:2]
            nw, nh = max(1, int(w / self.zoom)), max(1, int(h / self.zoom))
            x, y = (w - nw) // 2, (h - nh) // 2
            frame = cv2.resize(frame[y:y+nh, x:x+nw], (w, h))
            
        ok, encoded = cv2.imencode('.jpg', self.with_frame(frame, frame_id), [cv2.IMWRITE_JPEG_QUALITY, 78])
        if ok:
            self.frame, self.jpeg, self.updated, self.error = frame, encoded.tobytes(), time.monotonic(), None
        return ok

    def close(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.frame, self.jpeg = None, None
        self.faces = []
        self.face_angles = []
        self.raw = None
        self.zoom = 1.0

    def collage(self, frames, frame_id):
        w, h = 360, 270
        canvas = np.full((h * len(frames) + 32 * (len(frames) + 1), w + 64, 3), 245, dtype=np.uint8)
        for i, im in enumerate(frames):
            canvas[32 + i * (h + 32) : 32 + i * (h + 32) + h, 32 : 32 + w] = cv2.resize(im, (w, h))
        return self.with_frame(canvas, frame_id)

    def with_frame(self, image, frame_id):
        if frame_id == 'none':
            return image
        key = (frame_id, image.shape[1], image.shape[0])
        if key not in self.frame_cache:
            path = self.assets / 'frames' / frame_id
            with Image.open(path) as source:
                overlay = np.array(source.convert('RGBA'))[:, :, [2, 1, 0, 3]]
            overlay = cv2.resize(overlay, (image.shape[1], image.shape[0]))
            # Tìm vùng mở trong suốt bao quanh tâm
            mask = (overlay[:, :, 3] < 32).astype(np.uint8)
            _, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
            label = labels[image.shape[0] // 2, image.shape[1] // 2]
            if not label:
                raise ValueError('Khung phải có vùng giữa trong suốt: ' + frame_id)
            x, y, w, h, _ = stats[label]
            if len(self.frame_cache) >= 16:
                self.frame_cache.clear()
            self.frame_cache[key] = (overlay, (int(x), int(y), int(w), int(h)))
        overlay, (x, y, w, h) = self.frame_cache[key]
        result = np.full_like(image, 245)
        scale = min(w / image.shape[1], h / image.shape[0])
        iw, ih = max(1, round(image.shape[1] * scale)), max(1, round(image.shape[0] * scale))
        ox, oy = x + (w - iw) // 2, y + (h - ih) // 2
        result[oy:oy+ih, ox:ox+iw] = cv2.resize(image, (iw, ih))
        self.blend(result, overlay, 0, 0, result.shape[1])
        return result
````

## File: photobooth/storage.py
````python
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

DEFAULTS = dict(distance_m=1.0, absence_seconds=30, photo_count=4, countdown=3,
                retention_days=7, enabled_filters=['none', 'glasses', 'hat', 'mono', 'sepia'],
                default_filter='none')


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.photos = self.root / 'photos'
        self.photos.mkdir(exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.root / 'booth.db', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, owner TEXT NOT NULL,
          created TEXT NOT NULL, status TEXT NOT NULL, files TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, created TEXT, message TEXT);
        ''')
        self.db.commit()

    def settings(self):
        with self.lock:
            result = DEFAULTS.copy()
            for row in self.db.execute('SELECT * FROM settings'):
                result[row['key']] = json.loads(row['value'])
            return result

    def configure(self, values):
        with self.lock:
            for key, value in values.items():
                self.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, json.dumps(value)))
            self.db.commit()

    def log(self, message):
        with self.lock:
            self.db.execute('INSERT INTO events(created,message) VALUES (?,?)', (self.now(), message))
            self.db.execute('DELETE FROM events WHERE id NOT IN (SELECT id FROM events ORDER BY id DESC LIMIT 500)')
            self.db.commit()

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat()

    def create(self, sid, owner):
        with self.lock:
            self.db.execute('INSERT INTO sessions VALUES (?,?,?,?,?)', (sid, owner, self.now(), 'capturing', '[]'))
            self.db.commit()

    def finish(self, sid, status, files):
        with self.lock:
            self.db.execute('UPDATE sessions SET status=?, files=? WHERE id=?', (status, json.dumps(files), sid))
            self.db.commit()

    def sessions(self, owner=None):
        with self.lock:
            query = 'SELECT * FROM sessions'
            rows = self.db.execute(query + (' WHERE owner=?' if owner else '') + ' ORDER BY created DESC', (owner,) if owner else ()).fetchall()
            return [dict(id=r['id'], created=r['created'], status=r['status'], files=json.loads(r['files'])) for r in rows]

    def get_session(self, sid):
        with self.lock:
            row = self.db.execute('SELECT * FROM sessions WHERE id=?', (sid,)).fetchone()
            if not row:
                return None
            return dict(id=row['id'], owner=row['owner'], created=row['created'], status=row['status'], files=json.loads(row['files']))

    def delete(self, sid):
        with self.lock:
            row = self.db.execute('SELECT files FROM sessions WHERE id=?', (sid,)).fetchone()
            if not row:
                return False
            for name in json.loads(row['files']):
                (self.photos / Path(name).name).unlink(missing_ok=True)
            self.db.execute('DELETE FROM sessions WHERE id=?', (sid,))
            self.db.commit()
            return True

    def recover(self):
        with self.lock:
            self.db.execute("UPDATE sessions SET status='interrupted' WHERE status='capturing'")
            self.db.commit()

    def events(self):
        with self.lock:
            return [dict(r) for r in self.db.execute('SELECT created,message FROM events ORDER BY id DESC LIMIT 100')]
````

## File: scripts/install.sh
````bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install 'Flask>=3.1,<4' 'waitress>=3,<4'
.venv/bin/python - <<'PY'
import cv2, numpy, PIL
print('OpenCV:', cv2.__version__)
PY
printf '\nTiếp theo: .venv/bin/python manage.py init\n'
````

## File: static/app.js
````javascript
'use strict';
const $=id=>document.getElementById(id);
const isAdmin=document.querySelector('meta[name=page]').content==='admin';
const csrf=document.querySelector('meta[name=csrf-token]').content;
const states={stopped:'Đã dừng',waiting:'Đang chờ người',ready:'Sẵn sàng',capturing:'Đang chụp'};
let status=null, previousState='', settingsLoaded=false, optionsKey='', sessionKey='', previewUrl=null, noticeTimer;
let gestureLogKey='', prevCountdown=-1, prevTaken=0, audioCtx=null;

function getAudioContext(){
 if(!audioCtx){
  const AC=window.AudioContext||window.webkitAudioContext;
  if(AC)audioCtx=new AC();
 }
 if(audioCtx&&audioCtx.state==='suspended')audioCtx.resume();
 return audioCtx;
}
function playBeep(freq=880,duration=0.12,type='sine'){
 try{
  const ctx=getAudioContext();if(!ctx)return;
  const osc=ctx.createOscillator(),gain=ctx.createGain();
  osc.type=type;osc.frequency.setValueAtTime(freq,ctx.currentTime);
  gain.gain.setValueAtTime(0.18,ctx.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001,ctx.currentTime+duration);
  osc.connect(gain);gain.connect(ctx.destination);
  osc.start();osc.stop(ctx.currentTime+duration);
 }catch(e){}
}
function playShutterSound(){
 try{
  [520,680,850].forEach((freq,idx)=>{setTimeout(()=>playBeep(freq,0.08,'triangle'),idx*25);});
 }catch(e){}
}
function triggerFlash(){
 const flash=$('flashOverlay');if(!flash)return;
 flash.classList.add('flash');setTimeout(()=>flash.classList.remove('flash'),120);
}
const gestureNames={Open_Palm:'Bàn tay mở',Thumb_Up:'Giơ ngón cái',Victory:'Chữ V',Pointing_Up:'Trỏ lên',Closed_Fist:'Nắm tay',None:'Chưa xác định'};
let selectionPending=0, selectionVersion=0, selectionQueue=Promise.resolve();
function notice(text){$('notice').textContent=text;clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>{$('notice').textContent='';},8000);}
async function api(path,method='GET',data){
 const response=await fetch(path,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:data===undefined?undefined:JSON.stringify(data)});
 const result=await response.json(); if(!response.ok)throw new Error(result.error||'Yêu cầu thất bại');return result;
}
function bind(id,fn){if($(id))$(id).addEventListener('click',async()=>{try{await fn();await refresh();}catch(e){notice(e.message);}});}
function fillSelect(node,items,value){node.replaceChildren(...items.map(i=>{const o=document.createElement('option');o.value=i.id;o.textContent=i.label;return o;}));if(items.some(i=>i.id===value))node.value=value;}
function setupSettings(s){
 if(settingsLoaded)return;
 const form=$('settingsForm');for(const [k,v]of Object.entries(s.settings)){if(form.elements[k])form.elements[k].value=v;}
 const all=s.all_filters;
 fillSelect(form.elements.default_filter,all,s.settings.default_filter);
 $('enabledFilters').replaceChildren(...all.map(i=>{const label=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.value=i.id;input.checked=s.settings.enabled_filters.includes(i.id);input.disabled=i.id==='none';label.append(input,document.createTextNode(i.label));return label;}));settingsLoaded=true;
}
async function refresh(){
 const requestedVersion=selectionVersion;
 try{
 const s=await api('/api/status');status=s;
 $('connection').textContent='● Đã kết nối';$('mode').textContent=s.skip_sensor?(s.demo?'DEMO / BỎ QUA HC-SR04':'BỎ QUA HC-SR04'):s.demo?'CAMERA MÔ PHỎNG':s.hardware?'GPIO + CAMERA THẬT':'CAMERA THẬT / GPIO MÔ PHỎNG';
 if(isAdmin){
 $('loginPanel').hidden=s.admin;$('adminPanel').hidden=!s.admin;
 if(s.admin){$('deviceError').hidden=!s.error;$('deviceError').textContent=s.error||'';$('start').disabled=s.state!=='stopped';$('stop').disabled=s.state==='stopped';$('adminState').textContent=states[s.state];$('distance').textContent=s.distance_m===null?'—':`${s.distance_m.toFixed(2)} m`;$('led').textContent=s.led?'● Đang sáng':'○ Đang tắt';$('disk').textContent=`${s.free_mb} MB`;$('simulation').hidden=s.hardware||s.skip_sensor;setupSettings(s);}
 }else{
 $('gestureHelp').hidden=!s.gesture_enabled;
 $('gestureHelp').textContent=s.gesture_error||(!s.owned?'Nhận quyền trên web, đứng giữa khung hình rồi giơ bàn tay mở để bật cử chỉ.':s.gesture_active?`Cử chỉ đang bật · Zoom ${s.zoom.toFixed(2)}×. 👍 Chụp · ✌ Hiệu ứng tiếp · ☝ Hiệu ứng trước · Nắm tay: hủy chụp. Co ba ngón cuối và mở/khép cái–trỏ để zoom.`:'Đứng giữa khung hình, giữ bàn tay mở để kích hoạt cử chỉ.');
 $('state').textContent=states[s.state];$('cameraLabel').textContent=s.demo?'DEMO':'CAM 01';
 const active=s.owned&&s.camera_ready&&['ready','capturing'].includes(s.state);
 $('preview').hidden=!active;$('placeholder').hidden=active;
 $('gesturePanel').hidden=!active||!s.gesture_enabled;
 const g=s.gesture_diagnostic||{};
 const label=gestureNames[g.label]||g.label||'Chưa xác định';
 $('gestureCurrent').textContent=s.gesture_error||(!g.message?'Đang chờ nhận diện cử chỉ…':`${g.message} · Mặt: ${g.faces} · Tay: ${g.hands} · ${g.zooming?'Đang zoom':label+' ('+Math.round((g.score||0)*100)+'%)'}`);
 const events=s.gesture_events||[];
 const logKey=JSON.stringify(events);
 if(logKey!==gestureLogKey){
  $('gestureLog').replaceChildren(...events.slice().reverse().map(event=>{
   const li=document.createElement('li');
   li.textContent=`${new Date(event.time).toLocaleTimeString('vi-VN')} · ${gestureNames[event.label]||event.label}: ${event.message}`;
   return li;
  }));
  gestureLogKey=logKey;
 }
 $('placeholderTitle').textContent=s.error?'Thiết bị cần kiểm tra':s.state==='stopped'?'Booth đang nghỉ':s.state==='waiting'?'Đến gần để bắt đầu':s.busy?'Vui lòng chờ lượt':'Booth đã sẵn sàng';
 $('placeholderText').textContent=s.error|| (s.state==='stopped'?'Admin cần nhấn Start để bật booth.':s.state==='waiting'?'Đứng trước cảm biến trong phạm vi được cài đặt.':s.busy?'Một người dùng khác đang sử dụng booth.':'Nhấn “Bắt đầu sử dụng” để xem camera và chọn hiệu ứng.');
 $('claim').disabled=s.state!=='ready'||s.busy||s.owned;$('claim').textContent=s.owned?'Bạn đang điều khiển':'Bắt đầu sử dụng';
 for(const id of ['filter','frame','capture','release'])$(id).disabled=!s.owned||s.state!=='ready';
 $('capture').disabled||=!s.camera_ready||selectionPending>0;
 $('countdown').hidden=s.state!=='capturing'||!s.owned;$('countdown').textContent=s.countdown||'📸';
 $('progress').hidden=s.state!=='capturing'||!s.owned;$('progress').textContent=`Đã chụp ${s.taken} / ${s.total}`;
 if(s.state==='capturing'&&s.owned){
  if(s.countdown!==prevCountdown&&s.countdown>0)playBeep(880,0.12);
  if(s.taken>prevTaken){playShutterSound();triggerFlash();}
  prevCountdown=s.countdown;prevTaken=s.taken;
 }else{prevCountdown=-1;prevTaken=0;}
 const key=JSON.stringify([s.filters,s.frames]);
 if(key!==optionsKey){
  $('effectChoices').replaceChildren(...s.filters.filter(f=>f.id!=='none').map(f=>{
   const label=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.value=f.id;input.name='effect';label.append(input,document.createTextNode(f.label));return label;
  }));
  fillSelect($('frame'),[{id:'none',label:'Không khung'},...s.frames.map(f=>({id:f,label:f.replace('.png','').replaceAll('_',' ')}))],s.frame);optionsKey=key;
 }
 if(s.owned&&selectionPending===0&&requestedVersion===selectionVersion){
  for(const input of $('effectChoices').querySelectorAll('input'))input.checked=(s.selected_filters||[]).includes(input.value);
  if(document.activeElement!==$('frame'))$('frame').value=s.frame;
 }
 const frame=$('frame').value;$('frameSample').hidden=frame==='none';if(frame!=='none')$('frameSample').src='/assets/frames/'+encodeURIComponent(frame);
 }
 if(s.state!==previousState){previousState=s.state;await loadSessions();}
 }catch(e){$('connection').textContent='○ Mất kết nối';if(!isAdmin){for(const id of ['claim','capture','filter','frame','release'])$(id).disabled=true;$('preview').hidden=true;$('placeholder').hidden=false;$('placeholderTitle').textContent='Mất kết nối với Pi';$('placeholderText').textContent='Kiểm tra Wi-Fi. Trang sẽ tự kết nối lại.';}if($('gesturePanel'))$('gesturePanel').hidden=true;status=null;}
}
async function loadSessions(force=false){
 if(isAdmin&&!status?.admin)return;
 const items=await api('/api/sessions');const key=JSON.stringify(items);if(key===sessionKey&&!force)return;sessionKey=key;
 const container=$(isAdmin?'adminSessions':'sessions');container.replaceChildren();
 if(!items.length){const p=document.createElement('p');p.className='muted';p.textContent='Chưa có ảnh. Các phiên chụp sẽ xuất hiện tại đây.';container.append(p);return;}
 for(const item of items){
 const section=document.createElement('section');section.className='session';
 const title=document.createElement('div');title.className='session-title';
 const text=document.createElement('span');text.textContent=`${new Date(item.created).toLocaleString('vi-VN')} · ${{complete:'Hoàn tất',capturing:'Đang chụp',failed:'Có lỗi',interrupted:'Đã dừng giữa chừng'}[item.status]||item.status}`;title.append(text);
 if(isAdmin){const del=document.createElement('button');del.className='ghost';del.textContent='Xóa phiên';del.disabled=item.status==='capturing';del.onclick=async()=>{if(!confirm('Xóa vĩnh viễn ảnh của phiên này?'))return;try{await api('/api/sessions/'+item.id,'DELETE');await loadSessions(true);}catch(e){notice(e.message);}};title.append(del);}
 section.append(title);const photos=document.createElement('div');photos.className='photos';
 for(const file of item.files){const figure=document.createElement('figure');figure.className='photo';const image=document.createElement('img');image.src='/media/'+encodeURIComponent(file);image.alt=file.endsWith('_strip.jpg')?'Ảnh ghép của phiên':'Ảnh trong phiên';image.loading='lazy';const link=document.createElement('a');link.href=image.src+'?download=1';link.textContent=file.endsWith('_strip.jpg')?'↓ Tải ảnh ghép':'↓ Tải ảnh';link.download=file;figure.append(image,link);photos.append(figure);}section.append(photos);container.append(section);
 }
}
async function previewLoop(){
 if(!isAdmin&&status?.owned&&status.camera_ready){
 try{const r=await fetch('/api/preview.jpg',{cache:'no-store'});if(r.ok&&r.status!==204){const next=URL.createObjectURL(await r.blob());$('preview').src=next;if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=next;}}catch(e){/* status polling handles reconnect */}
 }setTimeout(previewLoop,160);
}
bind('claim',()=>{getAudioContext();return api('/api/claim','POST',{});});bind('release',()=>api('/api/release','POST',{}));bind('capture',async()=>{getAudioContext();$('capture').disabled=true;await selectionQueue;await api('/api/capture','POST',{});});
function saveSelection(){
 const data={filters:[...$('effectChoices').querySelectorAll('input:checked')].map(input=>input.value),frame:$('frame').value};
 selectionPending++;selectionVersion++;$('capture').disabled=true;
 $('frameSample').hidden=data.frame==='none';
 if(data.frame!=='none')$('frameSample').src='/assets/frames/'+encodeURIComponent(data.frame);
 selectionQueue=selectionQueue.then(async()=>{
  try{await api('/api/select','POST',data);}catch(e){notice(e.message);}
  finally{selectionPending--;}
 });
 selectionQueue.then(()=>refresh());
}
if($('effectChoices'))$('effectChoices').onchange=e=>{
 const input=e.target;
 if(input.checked&&['mono','sepia'].includes(input.value)){
  for(const other of $('effectChoices').querySelectorAll('input'))if(other!==input&&['mono','sepia'].includes(other.value))other.checked=false;
 }
 saveSelection();
};
if($('frame'))$('frame').onchange=saveSelection;
if($('clearEffects'))$('clearEffects').onclick=()=>{for(const input of $('effectChoices').querySelectorAll('input'))input.checked=false;saveSelection();};
bind('start',()=>api('/api/control','POST',{action:'start'}));bind('stop',()=>api('/api/control','POST',{action:'stop'}));bind('near',()=>api('/api/simulate','POST',{near:true}));bind('far',()=>api('/api/simulate','POST',{near:false}));bind('logout',async()=>{await api('/api/logout','POST',{});settingsLoaded=false;});bind('refreshSessions',()=>loadSessions(true));
if($('loginForm'))$('loginForm').onsubmit=async e=>{e.preventDefault();try{await api('/api/login','POST',{password:$('password').value});$('password').value='';await refresh();await loadSessions(true);await loadEvents();}catch(err){notice(err.message);}};
if($('settingsForm'))$('settingsForm').onsubmit=async e=>{e.preventDefault();const form=e.target;const data={};for(const k of ['distance_m','absence_seconds','photo_count','countdown','retention_days'])data[k]=Number(form.elements[k].value);data.enabled_filters=[...$('enabledFilters').querySelectorAll('input:checked')].map(i=>i.value);data.default_filter=form.elements.default_filter.value;try{await api('/api/settings','POST',data);notice('Đã lưu cấu hình');}catch(err){notice(err.message);}};
async function loadEvents(){if(!isAdmin||!status?.admin)return;try{const events=await api('/api/events');$('events').replaceChildren(...events.map(e=>{const li=document.createElement('li'),time=document.createElement('time');time.textContent=new Date(e.created).toLocaleString('vi-VN');li.append(time,document.createTextNode(e.message));return li;}));}catch(e){notice(e.message);}}
async function poll(){await refresh();setTimeout(poll,800);}async function slowPoll(){try{await loadSessions();await loadEvents();}catch(e){/* retry next poll */}setTimeout(slowPoll,5000);}poll();previewLoop();slowPoll();
````

## File: static/kiosk.css
````css
/* ==========================================================================
   Pi Studio — Fullscreen Kiosk Mode Style Sheet
   ========================================================================== */

:root {
  --kiosk-bg: #111a16;
  --kiosk-panel: #182620;
  --kiosk-card: #20332b;
  --kiosk-ink: #f4f6f0;
  --kiosk-muted: #95a39a;
  --kiosk-accent: #dafa7b;
  --kiosk-green: #488062;
  --kiosk-danger: #cf5c4a;
  --kiosk-line: #2d453a;
}

* {
  box-sizing: border-box;
  user-select: none;
}

body.kiosk-body {
  margin: 0;
  background: var(--kiosk-bg);
  color: var(--kiosk-ink);
  font: 16px/1.5 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* ==========================================================================
   Kiosk Header & Status
   ========================================================================== */

.kiosk-header {
  height: 60px;
  padding: 0 32px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--kiosk-line);
  background: rgba(17, 26, 22, 0.95);
  z-index: 100;
}

.kiosk-brand {
  font-size: 20px;
  font-weight: 850;
  letter-spacing: 2px;
  color: var(--kiosk-ink);
  text-decoration: none;
  display: flex;
  align-items: center;
  gap: 10px;
}

.kiosk-brand span {
  font-size: 11px;
  color: var(--kiosk-muted);
  letter-spacing: 1px;
}

.kiosk-status-badge {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 13px;
  font-family: monospace;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 20px;
  background: var(--kiosk-card);
  border: 1px solid var(--kiosk-line);
}

.dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--kiosk-accent);
  box-shadow: 0 0 8px var(--kiosk-accent);
}

.dot.offline {
  background: var(--kiosk-danger);
  box-shadow: 0 0 8px var(--kiosk-danger);
}

/* ==========================================================================
   Kiosk Main Stage
   ========================================================================== */

.kiosk-stage {
  flex: 1;
  position: relative;
  display: flex;
  overflow: hidden;
}

.kiosk-view {
  position: absolute;
  inset: 0;
  display: flex;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.3s ease;
}

.kiosk-view.active {
  opacity: 1;
  pointer-events: auto;
}

/* ==========================================================================
   View 1: Welcome & Attract Mode
   ========================================================================== */

.view-welcome {
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
  padding: 40px;
  background: radial-gradient(circle at center, #1e332a 0%, #111a16 70%);
}

.welcome-logo {
  font-size: 80px;
  color: var(--kiosk-accent);
  margin-bottom: 10px;
  animation: pulse 2.5s infinite;
}

@keyframes pulse {
  0%, 100% { transform: scale(1); filter: drop-shadow(0 0 10px rgba(218, 250, 123, 0.4)); }
  50% { transform: scale(1.08); filter: drop-shadow(0 0 25px rgba(218, 250, 123, 0.8)); }
}

.welcome-title {
  font-size: 52px;
  font-weight: 850;
  letter-spacing: -1px;
  margin: 0 0 12px;
}

.welcome-desc {
  font-size: 20px;
  color: var(--kiosk-muted);
  max-width: 600px;
  margin: 0 0 36px;
}

.welcome-gestures-guide {
  display: flex;
  gap: 20px;
  margin-bottom: 40px;
  flex-wrap: wrap;
  justify-content: center;
}

.gesture-guide-item {
  background: var(--kiosk-card);
  border: 1px solid var(--kiosk-line);
  padding: 16px 20px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.gesture-icon {
  font-size: 32px;
}

.gesture-text strong {
  display: block;
  font-size: 14px;
}

.gesture-text small {
  color: var(--kiosk-muted);
  font-size: 11px;
}

.btn-big-start {
  background: var(--kiosk-accent);
  color: var(--kiosk-bg);
  border: 0;
  border-radius: 20px;
  padding: 20px 48px;
  font-size: 22px;
  font-weight: 800;
  cursor: pointer;
  box-shadow: 0 8px 30px rgba(218, 250, 123, 0.25);
  transition: transform 0.15s, filter 0.15s;
}

.btn-big-start:hover {
  filter: brightness(1.1);
  transform: scale(1.03);
}

.btn-big-start:active {
  transform: scale(0.97);
}

/* ==========================================================================
   View 2: Active Camera & Studio
   ========================================================================== */

.view-studio {
  display: grid;
  grid-template-columns: 1fr 340px;
  gap: 24px;
  padding: 24px 32px;
  width: 100%;
  height: 100%;
}

.studio-main {
  display: flex;
  flex-direction: column;
  position: relative;
  min-height: 0;
}

.kiosk-viewfinder {
  flex: 1;
  position: relative;
  background: #000;
  border-radius: 20px;
  overflow: hidden;
  border: 2px solid var(--kiosk-line);
  box-shadow: 0 10px 40px rgba(0,0,0,0.4);
  display: flex;
  align-items: center;
  justify-content: center;
}

.kiosk-viewfinder img#kioskPreview {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.kiosk-countdown {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  font-size: 140px;
  font-weight: 900;
  color: #fff;
  text-shadow: 0 4px 40px rgba(0,0,0,0.85);
  background: rgba(0,0,0,0.25);
  z-index: 10;
}

.kiosk-countdown[hidden] {
  display: none;
}

.kiosk-progress {
  position: absolute;
  bottom: 20px;
  left: 20px;
  background: rgba(17, 26, 22, 0.85);
  border: 1px solid var(--kiosk-line);
  padding: 8px 18px;
  border-radius: 30px;
  font-size: 14px;
  font-weight: 700;
  color: var(--kiosk-accent);
  z-index: 10;
}

#kioskFlash {
  position: absolute;
  inset: 0;
  background: #fff;
  opacity: 0;
  pointer-events: none;
  z-index: 20;
  transition: opacity 0.12s ease-out;
}

#kioskFlash.flash {
  opacity: 0.98;
  transition: none;
}

.kiosk-sidebar {
  display: flex;
  flex-direction: column;
  gap: 16px;
  justify-content: space-between;
}

.kiosk-sidebar-panel {
  background: var(--kiosk-panel);
  border: 1px solid var(--kiosk-line);
  border-radius: 20px;
  padding: 20px;
}

.kiosk-sidebar-panel h3 {
  margin: 0 0 12px;
  font-size: 16px;
  color: var(--kiosk-accent);
  letter-spacing: 1px;
}

.filter-pills {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.filter-pill {
  background: var(--kiosk-card);
  border: 1px solid var(--kiosk-line);
  color: var(--kiosk-ink);
  padding: 12px 10px;
  border-radius: 12px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  text-align: center;
  transition: all 0.15s;
}

.filter-pill.active {
  background: var(--kiosk-accent);
  color: var(--kiosk-bg);
  border-color: var(--kiosk-accent);
  box-shadow: 0 0 12px rgba(218, 250, 123, 0.3);
}

.btn-kiosk-snap {
  background: var(--kiosk-accent);
  color: var(--kiosk-bg);
  border: 0;
  border-radius: 16px;
  padding: 20px;
  font-size: 18px;
  font-weight: 800;
  width: 100%;
  cursor: pointer;
  box-shadow: 0 6px 20px rgba(218, 250, 123, 0.2);
  transition: transform 0.1s, filter 0.15s;
}

.btn-kiosk-snap:hover {
  filter: brightness(1.1);
}

.btn-kiosk-snap:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.kiosk-gesture-banner {
  background: var(--kiosk-card);
  border: 1px solid var(--kiosk-line);
  border-radius: 12px;
  padding: 12px;
  font-size: 13px;
  text-align: center;
  color: var(--kiosk-muted);
}

/* ==========================================================================
   View 3: Results & QR Code Screen
   ========================================================================== */

.view-result {
  display: grid;
  grid-template-columns: 1fr 1.2fr;
  gap: 40px;
  padding: 32px 60px;
  width: 100%;
  height: 100%;
  align-items: center;
  justify-content: center;
  background: radial-gradient(circle at center, #1e332a 0%, #111a16 80%);
}

.result-photo-column {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
}

.result-photo-frame {
  max-height: 80vh;
  border-radius: 16px;
  box-shadow: 0 12px 40px rgba(0,0,0,0.6);
  border: 3px solid rgba(255,255,255,0.1);
  overflow: hidden;
}

.result-photo-frame img {
  max-height: 80vh;
  width: auto;
  display: block;
  object-fit: contain;
}

.result-qr-column {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  background: var(--kiosk-panel);
  border: 1px solid var(--kiosk-line);
  border-radius: 28px;
  padding: 36px 40px;
  box-shadow: 0 10px 30px rgba(0,0,0,0.3);
}

.result-qr-column h2 {
  font-size: 30px;
  margin: 0 0 8px;
  color: var(--kiosk-accent);
}

.result-qr-column p {
  color: var(--kiosk-muted);
  font-size: 15px;
  margin: 0 0 24px;
  max-width: 360px;
}

.qr-box {
  background: #fff;
  padding: 16px;
  border-radius: 20px;
  box-shadow: 0 8px 30px rgba(0,0,0,0.4);
  margin-bottom: 24px;
}

.qr-box img {
  width: 240px;
  height: 240px;
  display: block;
}

.auto-reset-timer {
  font-size: 13px;
  color: var(--kiosk-muted);
  margin-bottom: 16px;
}

.btn-next-customer {
  background: var(--kiosk-card);
  border: 1px solid var(--kiosk-line);
  color: var(--kiosk-ink);
  padding: 14px 32px;
  border-radius: 14px;
  font-size: 15px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-next-customer:hover {
  background: var(--kiosk-green);
  border-color: var(--kiosk-green);
}
````

## File: static/kiosk.js
````javascript
'use strict';

const $ = id => document.getElementById(id);
const csrf = document.querySelector('meta[name=csrf-token]').content;

let status = null;
let currentView = 'welcome';
let activeFilters = [];
let prevCountdown = -1;
let prevTaken = 0;
let previewUrl = null;
let previewTimer = null;
let resultTimer = null;
let resultSecondsLeft = 45;
let lastHandledSid = null;
let audioCtx = null;

// Clock
setInterval(() => {
  const now = new Date();
  $('kioskClock').textContent = now.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
}, 1000);

// Audio
function getAudioContext() {
  if (!audioCtx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (AC) audioCtx = new AC();
  }
  if (audioCtx && audioCtx.state === 'suspended') audioCtx.resume();
  return audioCtx;
}

function playBeep(freq = 880, duration = 0.12, type = 'sine') {
  try {
    const ctx = getAudioContext();
    if (!ctx) return;
    const osc = ctx.createOscillator(), gain = ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, ctx.currentTime);
    gain.gain.setValueAtTime(0.2, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + duration);
  } catch (e) {}
}

function playShutterSound() {
  try {
    [520, 680, 850].forEach((freq, idx) => {
      setTimeout(() => playBeep(freq, 0.08, 'triangle'), idx * 25);
    });
  } catch (e) {}
}

function triggerFlash() {
  const flash = $('kioskFlash');
  if (!flash) return;
  flash.classList.add('flash');
  setTimeout(() => flash.classList.remove('flash'), 120);
}

// API
async function api(path, method = 'GET', data) {
  const response = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
    body: data === undefined ? undefined : JSON.stringify(data)
  });
  const res = await response.json();
  if (!response.ok) throw new Error(res.error || 'Yêu cầu thất bại');
  return res;
}

function switchView(viewName) {
  currentView = viewName;
  $('viewWelcome').classList.toggle('active', viewName === 'welcome');
  $('viewStudio').classList.toggle('active', viewName === 'studio');
  $('viewResult').classList.toggle('active', viewName === 'result');
}

// Preview loop
async function previewLoop() {
  if (currentView === 'studio' && status?.owned && status.camera_ready) {
    try {
      const r = await fetch('/api/preview.jpg', { cache: 'no-store' });
      if (r.ok && r.status !== 204) {
        const next = URL.createObjectURL(await r.blob());
        $('kioskPreview').src = next;
        if (previewUrl) URL.revokeObjectURL(previewUrl);
        previewUrl = next;
      }
    } catch (e) {}
  }
  setTimeout(previewLoop, 140);
}

// Show Result Screen with QR Code
function showResultScreen(sid) {
  clearInterval(resultTimer);
  lastHandledSid = sid;
  switchView('result');
  $('kioskResultImg').src = `/download/${sid}/${sid}_strip.jpg?view=1`;
  $('kioskQrCode').src = `/api/qr/${sid}.png`;
  
  resultSecondsLeft = 45;
  $('kioskAutoResetTimer').textContent = `Tự động đón người tiếp theo sau ${resultSecondsLeft}s`;
  resultTimer = setInterval(() => {
    resultSecondsLeft--;
    if (resultSecondsLeft <= 0) {
      clearInterval(resultTimer);
      resetToWelcome();
    } else {
      $('kioskAutoResetTimer').textContent = `Tự động đón người tiếp theo sau ${resultSecondsLeft}s`;
    }
  }, 1000);
}

async function resetToWelcome() {
  clearInterval(resultTimer);
  try {
    await api('/api/release', 'POST', {});
  } catch (e) {}
  switchView('welcome');
}

// Main refresh / status poll
async function refresh() {
  try {
    const s = await api('/api/status');
    status = s;
    $('kioskDot').className = 'dot';
    $('kioskStatusText').textContent = s.state === 'stopped' ? 'Booth đang tắt' :
                                      s.state === 'waiting' ? 'Đang chờ người' :
                                      s.state === 'capturing' ? 'Đang chụp ảnh' : 'Sẵn sàng';

    // Auto-claim if customer approaches or opens palm in welcome view
    if (currentView === 'welcome' && s.state === 'ready' && !s.busy && !s.owned) {
      if (s.distance_m !== null && s.distance_m < 1.2) {
        // Someone stepped up close to the booth!
        await claimBooth();
      }
    }

    // State transition handling
    if (s.owned) {
      // If a capture was completed and we haven't displayed it yet
      if (s.last_sid && s.last_sid !== lastHandledSid && s.state === 'ready') {
        showResultScreen(s.last_sid);
        return;
      }

      if (currentView !== 'result') {
        switchView('studio');
      }

      // Countdown and capture progress
      $('kioskCountdown').hidden = s.state !== 'capturing';
      $('kioskCountdown').textContent = s.countdown || '📸';
      $('kioskProgress').textContent = `Đã chụp ${s.taken} / ${s.total}`;
      $('btnKioskSnap').disabled = s.state !== 'ready';

      if (s.state === 'capturing') {
        if (s.countdown !== prevCountdown && s.countdown > 0) playBeep(880, 0.12);
        if (s.taken > prevTaken) {
          playShutterSound();
          triggerFlash();
        }
        prevCountdown = s.countdown;
        prevTaken = s.taken;
      } else {
        prevCountdown = -1;
        prevTaken = 0;
      }

      // Gesture status display
      const g = s.gesture_diagnostic || {};
      const gestureNames = { Open_Palm: 'Bàn tay mở', Thumb_Up: 'Giơ ngón cái', Victory: 'Chữ V', Pointing_Up: 'Trỏ lên', Closed_Fist: 'Nắm tay' };
      const gLabel = gestureNames[g.label] || g.label || '';
      $('kioskGestureBanner').textContent = s.gesture_active ?
        `Cử chỉ đang bật · ${g.message || 'Sẵn sàng'} · ${gLabel} (${Math.round((g.score || 0)*100)}%)` :
        `Giơ bàn tay mở 🖐 để bật điều khiển không chạm`;

      // Sync active filters on pills
      activeFilters = s.selected_filters || [];
      document.querySelectorAll('#kioskFilterPills .filter-pill').forEach(pill => {
        const fid = pill.dataset.filter;
        if (fid === 'none') {
          pill.classList.toggle('active', activeFilters.length === 0);
        } else {
          pill.classList.toggle('active', activeFilters.includes(fid));
        }
      });
    } else {
      if (currentView === 'studio') {
        switchView('welcome');
      }
    }
  } catch (e) {
    $('kioskDot').className = 'dot offline';
    $('kioskStatusText').textContent = 'Mất kết nối';
  }
}

async function claimBooth() {
  getAudioContext();
  try {
    await api('/api/claim', 'POST', {});
    switchView('studio');
  } catch (e) {
    console.error(e);
  }
}

// Event Bindings
$('btnKioskStart').onclick = () => claimBooth();
$('btnKioskLeave').onclick = () => resetToWelcome();
$('btnNextCustomer').onclick = () => resetToWelcome();

$('btnKioskSnap').onclick = async () => {
  getAudioContext();
  try {
    await api('/api/capture', 'POST', {});
  } catch (e) {
    alert(e.message);
  }
};

// Filter pill clicks
document.querySelectorAll('#kioskFilterPills .filter-pill').forEach(pill => {
  pill.onclick = async () => {
    getAudioContext();
    const fid = pill.dataset.filter;
    let next = [...activeFilters];
    if (fid === 'none') {
      next = [];
    } else if (fid === 'mono' || fid === 'sepia') {
      next = next.filter(f => f !== 'mono' && f !== 'sepia');
      if (!activeFilters.includes(fid)) next.push(fid);
    } else {
      if (next.includes(fid)) next = next.filter(f => f !== fid);
      else next.push(fid);
    }
    try {
      await api('/api/select', 'POST', { filters: next });
      activeFilters = next;
    } catch (e) {}
  };
});

// Start loop
setInterval(refresh, 600);
previewLoop();
````

## File: static/style.css
````css
/* ==========================================================================
   Pi Studio — Raspberry Photobooth Style Sheet
   ========================================================================== */

:root {
  --bg: #f5f2ec;
  --paper: #fffefa;
  --ink: #253b32;
  --muted: #72796e;
  --accent: #dafa7b;
  --line: #dde0d5;
  --green: #335c47;
  --danger: #97483b;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 16px/1.6 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}

header, main, footer {
  max-width: 1250px;
  margin: auto;
  padding: 24px 32px;
}

/* ==========================================================================
   Header & Navigation
   ========================================================================== */

header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--line);
  gap: 20px;
}

.brand {
  font-size: 23px;
  font-weight: 850;
  letter-spacing: 2px;
  text-decoration: none;
  color: var(--ink);
}

.brand small {
  display: block;
  font-size: 9px;
  letter-spacing: 2px;
  color: var(--muted);
}

nav {
  display: flex;
  align-items: center;
  gap: 24px;
}

a {
  color: var(--green);
}

nav a {
  font-size: 14px;
  text-decoration: none;
}

#connection {
  font-size: 11px;
  border: 1px solid var(--line);
  border-radius: 30px;
  padding: 5px 10px;
}

/* ==========================================================================
   Intro & Badges
   ========================================================================== */

.intro {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 25px 0 30px;
  gap: 15px;
}

.eyebrow {
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 2px;
  color: var(--green);
}

h1 {
  font-size: clamp(36px, 5vw, 62px);
  line-height: 1.1;
  letter-spacing: -2px;
  margin: 12px 0 16px;
}

h2 {
  font-size: 21px;
  line-height: 1.4;
  margin: 0 0 16px;
}

.intro p {
  margin: 0;
  color: var(--muted);
}

.badge {
  font-size: 11px;
  font-weight: 700;
  background: #e8eadf;
  border-radius: 20px;
  padding: 7px 12px;
  white-space: nowrap;
}

/* ==========================================================================
   Cards & Layout Grids
   ========================================================================== */

.card {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 20px;
  padding: 26px;
  box-shadow: 0 5px 15px #233b3103;
}

.booth-grid {
  display: grid;
  grid-template-columns: 1fr 330px;
  gap: 24px;
}

.camera-card {
  padding: 16px;
}

.camera-top {
  display: flex;
  justify-content: space-between;
  font: 11px monospace;
  padding: 2px 4px 14px;
}

#statusDot {
  display: inline-block;
  width: 8px;
  height: 8px;
  background: var(--green);
  border-radius: 50%;
}

/* ==========================================================================
   Viewfinder, Camera & Flash Effect
   ========================================================================== */

.viewfinder {
  position: relative;
  aspect-ratio: 4/3;
  overflow: hidden;
  background: #1f302a;
  border-radius: 12px;
  color: #f4f2e8;
  display: flex;
  align-items: center;
  justify-content: center;
}

#preview {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

#placeholder {
  text-align: center;
  padding: 20px;
}

#placeholder p {
  font-size: 14px;
  color: #b7c4b9;
  max-width: 340px;
}

.camera-symbol {
  font-size: 65px;
  color: var(--accent);
}

#countdown {
  position: absolute;
  font-size: 100px;
  font-weight: 900;
  text-shadow: 0 3px 30px #000;
  inset: 0;
  display: grid;
  place-items: center;
  background: #0002;
  z-index: 5;
}

#countdown[hidden] {
  display: none;
}

#progress {
  position: absolute;
  bottom: 16px;
  left: 16px;
  background: #17231ddd;
  border-radius: 20px;
  padding: 5px 12px;
  font-size: 12px;
  z-index: 5;
}

/* Flash overlay on capture */
#flashOverlay {
  position: absolute;
  inset: 0;
  background: #ffffff;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.15s ease-out;
  z-index: 20;
}

#flashOverlay.flash {
  opacity: 0.95;
  transition: none;
}

.muted {
  color: var(--muted);
  font-size: 13px;
}

.camera-card > p {
  margin: 12px 4px 0;
}

/* ==========================================================================
   Controls, Inputs & Buttons
   ========================================================================== */

.controls label {
  margin-top: 20px;
}

.controls button {
  width: 100%;
  margin-top: 10px;
}

button {
  border: 0;
  border-radius: 10px;
  background: var(--green);
  color: white;
  padding: 12px 18px;
  cursor: pointer;
  font: 600 14px system-ui, sans-serif;
  transition: filter 0.15s, transform 0.1s;
}

button:hover {
  filter: brightness(1.1);
}

button:active {
  transform: scale(0.98);
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
  transform: none;
}

#capture {
  background: var(--accent);
  color: var(--ink);
  padding: 18px;
  font-size: 17px;
  font-weight: 700;
}

.ghost {
  background: transparent;
  border: 1px solid var(--line);
  color: var(--ink);
}

.secondary {
  background: var(--accent);
  color: var(--ink);
}

.danger {
  background: var(--danger);
}

label {
  display: block;
  font-size: 13px;
  font-weight: 600;
}

input, select {
  display: block;
  margin: 7px 0 0;
  width: 100%;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: #fff;
  color: var(--ink);
  font: 14px system-ui, sans-serif;
}

input:focus, select:focus, button:focus-visible, a:focus-visible {
  outline: 3px solid #b1d688;
  outline-offset: 2px;
}

#frameSample {
  max-height: 130px;
  max-width: 100%;
  display: block;
  margin: 14px auto;
  object-fit: contain;
}

#frameSample[hidden] {
  display: none;
}

/* ==========================================================================
   Filter Checkboxes & Effect Controls
   ========================================================================== */

.controls fieldset {
  min-width: 0;
  margin: 20px 0 0;
}

.controls .checks {
  gap: 10px;
}

.controls .checks label {
  margin: 0;
  padding: 8px 10px;
  background: #f0f2e9;
  border-radius: 8px;
  cursor: pointer;
}

.controls .checks input {
  accent-color: var(--green);
}

.controls #clearEffects {
  padding: 8px;
  font-size: 12px;
}

/* ==========================================================================
   Gesture Panel
   ========================================================================== */

#gesturePanel {
  margin-top: 12px;
  padding: 10px 14px;
  background: #edf2e7;
  border-radius: 10px;
  font-size: 12px;
  overflow-wrap: anywhere;
}

#gestureCurrent {
  margin: 0;
  font-weight: 600;
}

#gestureLog {
  margin: 8px 0 0;
  padding-left: 20px;
  max-height: 145px;
  overflow: auto;
}

#gestureLog:empty {
  display: none;
}

#gestureLog li {
  padding: 3px 0;
}

/* ==========================================================================
   Results Gallery & Photos
   ========================================================================== */

.results {
  margin-top: 24px;
}

.section-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 14px;
}

.section-heading h2 {
  margin: 7px 0 18px;
}

.photos {
  display: flex;
  gap: 12px;
  overflow: auto;
  padding-bottom: 12px;
}

.photo {
  min-width: 145px;
  width: 180px;
  margin: 0;
}

.photo img {
  width: 100%;
  height: 140px;
  object-fit: contain;
  background: #eeeae1;
  border-radius: 9px;
}

.photo a {
  display: block;
  text-align: center;
  font-size: 12px;
  padding: 6px;
}

.session {
  border-top: 1px solid var(--line);
  padding: 18px 0;
}

.session-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  font-size: 13px;
  gap: 12px;
}

/* ==========================================================================
   Admin View Metrics & Events
   ========================================================================== */

.metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 22px;
}

.metrics small {
  font-size: 10px;
  letter-spacing: 1px;
  display: block;
}

.metrics strong {
  display: block;
  font-size: 23px;
  margin-top: 10px;
}

.actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.device-error {
  background: #fff0d6;
  color: #754f14;
  padding: 12px;
  border-radius: 10px;
}

.admin-grid {
  display: grid;
  grid-template-columns: 1.3fr 1fr;
  gap: 24px;
  margin: 24px 0;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

fieldset {
  border: 1px solid var(--line);
  border-radius: 10px;
  margin: 20px 0;
}

legend {
  font-size: 12px;
}

.checks {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}

.checks label {
  display: flex;
  align-items: center;
  gap: 6px;
}

.checks input {
  width: auto;
  margin: 0;
}

.events {
  padding: 0;
  list-style: none;
  max-height: 450px;
  overflow: auto;
}

.events li {
  border-bottom: 1px solid var(--line);
  padding: 12px 0;
  font-size: 13px;
}

.events time {
  display: block;
  color: var(--muted);
  font-size: 11px;
}

.narrow {
  max-width: 420px;
  margin: 40px auto;
}

.narrow button {
  margin-top: 20px;
  width: 100%;
}

#notice:not(:empty) {
  border-radius: 10px;
  padding: 12px 18px;
  margin-bottom: 20px;
  background: #fff0d6;
  color: #754f14;
  font-size: 14px;
}

footer {
  display: flex;
  justify-content: space-between;
  font: 10px monospace;
  letter-spacing: 1px;
  color: var(--muted);
  padding-top: 40px;
  padding-bottom: 35px;
}

[hidden] {
  display: none !important;
}

/* ==========================================================================
   Responsive Breakpoints
   ========================================================================== */

@media (max-width: 850px) {
  .booth-grid, .admin-grid {
    grid-template-columns: 1fr;
  }
  .controls {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0 16px;
  }
  .controls > h2,
  .controls > .eyebrow,
  .controls > p,
  .controls > #claim {
    grid-column: 1 / -1;
  }
  .controls > fieldset {
    grid-column: 1 / -1;
  }
  .metrics {
    grid-template-columns: 1fr 1fr;
  }
  header, main, footer {
    padding-left: 18px;
    padding-right: 18px;
  }
  nav {
    gap: 12px;
  }
  .intro {
    margin-top: 15px;
  }
}

@media (max-width: 480px) {
  nav #connection {
    display: none;
  }
  .badge {
    max-width: 110px;
    white-space: normal;
  }
  .card {
    padding: 18px;
  }
  .camera-card {
    padding: 10px;
  }
  .form-grid {
    grid-template-columns: 1fr;
  }
  .section-heading {
    align-items: start;
  }
  .section-heading > .muted {
    max-width: 110px;
  }
  .brand {
    font-size: 18px;
  }
  .brand small {
    font-size: 7px;
  }
  .metrics strong {
    font-size: 19px;
  }
  footer span {
    display: none;
  }
}
````

## File: templates/download.html
````html
<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tải ảnh kỷ niệm · Pi Studio Photobooth</title>
<link rel="stylesheet" href="/static/style.css">
<style>
.download-page {
  max-width: 540px;
  margin: 0 auto;
  padding: 20px 16px 60px;
}
.download-header {
  text-align: center;
  margin-bottom: 24px;
}
.download-header .brand {
  font-size: 26px;
  font-weight: 850;
  letter-spacing: 2px;
  color: var(--ink);
  text-decoration: none;
}
.download-card {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 20px;
  padding: 20px;
  box-shadow: 0 8px 24px rgba(35, 59, 49, 0.06);
  text-align: center;
}
.strip-preview {
  margin: 16px 0 20px;
}
.strip-preview img {
  max-width: 100%;
  max-height: 480px;
  border-radius: 12px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.12);
  object-fit: contain;
}
.btn-primary-dl {
  display: block;
  width: 100%;
  background: var(--accent);
  color: var(--ink);
  font-weight: 700;
  font-size: 16px;
  padding: 16px;
  border-radius: 12px;
  text-decoration: none;
  margin: 12px 0 24px;
  transition: transform 0.1s, filter 0.15s;
}
.btn-primary-dl:hover {
  filter: brightness(1.05);
}
.btn-primary-dl:active {
  transform: scale(0.98);
}
.single-photos-title {
  font-size: 15px;
  font-weight: 700;
  margin: 20px 0 12px;
  text-align: left;
  color: var(--ink);
}
.single-photos-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.single-photo-item {
  background: #f4f2ea;
  border-radius: 10px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.single-photo-item img {
  width: 100%;
  height: 120px;
  object-fit: contain;
  background: #eeeae1;
}
.single-photo-item a {
  padding: 8px 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--green);
  text-decoration: none;
  display: block;
}
</style>
</head>
<body>
<div class="download-page">
  <div class="download-header">
    <a class="brand" href="/">◉ PI STUDIO</a>
    <p class="muted" style="margin: 4px 0 0;">PHOTOBOOTH / KHOẢNH KHẮC CỦA BẠN</p>
  </div>

  <div class="download-card">
    <span class="eyebrow">TẢI VỀ ĐIỆN THOẠI</span>
    <h1 style="font-size: 24px; margin: 8px 0 4px;">Ảnh Kỷ Niệm Của Bạn</h1>
    <p class="muted" style="font-size: 13px;">Phiên chụp lúc: {{ sess.created[:19].replace('T', ' ') }} UTC</p>

    {% set strip_file = '' %}
    {% for f in sess.files %}
      {% if f.endswith('_strip.jpg') %}
        {% set strip_file = f %}
      {% endif %}
    {% endfor %}

    {% if strip_file %}
    <div class="strip-preview">
      <img src="/download/{{ sid }}/{{ strip_file }}?view=1" alt="Ảnh dải kỷ niệm Photobooth">
    </div>
    <a class="btn-primary-dl" href="/download/{{ sid }}/{{ strip_file }}" download="{{ strip_file }}">
      ↓ TẢI DẢI ẢNH PHOTOSTRIP
    </a>
    {% endif %}

    <div class="single-photos-title">Các tấm ảnh riêng lẻ:</div>
    <div class="single-photos-grid">
      {% for f in sess.files %}
        {% if not f.endswith('_strip.jpg') %}
        <div class="single-photo-item">
          <img src="/download/{{ sid }}/{{ f }}?view=1" alt="Ảnh chụp" loading="lazy">
          <a href="/download/{{ sid }}/{{ f }}" download="{{ f }}">↓ Tải ảnh này</a>
        </div>
        {% endif %}
      {% endfor %}
    </div>

    <p class="muted" style="font-size: 12px; margin-top: 24px;">
      💡 Mẹo: Nhấn và giữ vào ảnh để chọn <em>"Lưu hình ảnh"</em> vào thư viện ảnh trên điện thoại của bạn.
    </p>
  </div>
</div>
</body>
</html>
````

## File: templates/index.html
````html
<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="csrf-token" content="{{ csrf }}"><meta name="page" content="{{ 'admin' if admin_page else 'booth' }}">
<title>{{ 'Quản trị' if admin_page else 'Chụp ảnh' }} · Pi Studio</title>
<link rel="stylesheet" href="/static/style.css"><script src="/static/app.js" defer></script>
</head>
<body>
<header><a class="brand" href="/">◉ PI STUDIO <small>PHOTOBOOTH / NHÓM 12</small></a><nav><a href="/">Chụp ảnh</a><a href="/admin">Quản trị</a><span id="connection">Đang kết nối…</span></nav></header>
<main>
<div class="intro"><div><span class="eyebrow">MỘT KHOẢNH KHẮC. MỘT KỶ NIỆM.</span><h1>{{ 'Bàn điều khiển.' if admin_page else 'Cười lên nào!' }}</h1><p>{{ 'Theo dõi thiết bị và quản lý những phiên chụp của bạn.' if admin_page else 'Chọn hiệu ứng yêu thích, tạo dáng và lưu lại khoảnh khắc.' }}</p></div><span class="badge" id="mode"></span></div>
<div id="notice" role="status" aria-live="polite"></div>
{% if admin_page %}
<section id="loginPanel" class="card narrow"><h2>Đăng nhập quản trị</h2><form id="loginForm"><label>Mật khẩu<input type="password" id="password" autocomplete="current-password" required minlength="10"></label><button>Đăng nhập</button></form></section>
<div id="adminPanel" hidden>
<section class="metrics"><div class="card"><small>TRẠNG THÁI</small><strong id="adminState">—</strong></div><div class="card"><small>KHOẢNG CÁCH</small><strong id="distance">—</strong></div><div class="card"><small>LED</small><strong id="led">—</strong></div><div class="card"><small>BỘ NHỚ TRỐNG</small><strong id="disk">—</strong></div></section>
<section class="card"><h2>Vận hành</h2><p id="deviceError" class="device-error" role="status" hidden></p><div class="actions"><button id="start">▶ Start hệ thống</button><button id="stop" class="danger">■ Stop hệ thống</button><button id="logout" class="ghost">Đăng xuất</button></div><div id="simulation" hidden><p class="muted">Chế độ không dùng GPIO: mô phỏng khoảng cách để thử luồng. LED hiển thị trên web, không điều khiển đèn thật.</p><button id="near" class="secondary">Có người · 0,6 m</button><button id="far" class="ghost">Rời đi · 2,5 m</button></div></section>
<div class="admin-grid"><section class="card"><h2>Cấu hình booth</h2><form id="settingsForm"><div class="form-grid"><label>Khoảng cách kích hoạt (m)<input name="distance_m" type="number" min="0.2" max="3.5" step="0.1" required></label><label>Vắng người trước khi nghỉ (giây)<input name="absence_seconds" type="number" min="5" max="300" required></label><label>Số ảnh / phiên<input name="photo_count" type="number" min="1" max="8" required></label><label>Đếm ngược (giây)<input name="countdown" type="number" min="1" max="10" required></label><label>Lưu ảnh trong (ngày)<input name="retention_days" type="number" min="1" max="90" required></label><label>Filter mặc định<select name="default_filter"></select></label></div><fieldset><legend>Filter được phép sử dụng</legend><div id="enabledFilters" class="checks"></div></fieldset><button>Lưu cấu hình</button></form></section><section class="card"><h2>Nhật ký thiết bị</h2><ul id="events" class="events"></ul></section></div>
<section class="card"><div class="section-heading"><h2>Các phiên chụp</h2><button id="refreshSessions" class="ghost">Làm mới</button></div><div id="adminSessions"></div></section>
</div>
{% else %}
<div class="booth-grid"><section class="card camera-card"><div class="camera-top"><span><i id="statusDot"></i> <span id="state">Đang kết nối</span></span><span id="cameraLabel">CAM 01</span></div><div class="viewfinder"><img id="preview" alt="Hình xem trước từ webcam Raspberry Pi" hidden><div id="flashOverlay"></div><div id="placeholder"><span class="camera-symbol">◎</span><h2 id="placeholderTitle">Chào bạn!</h2><p id="placeholderText">Đang lấy trạng thái từ booth…</p></div><div id="countdown" hidden aria-live="assertive"></div><span id="progress" hidden></span></div><div id="gesturePanel" hidden><p id="gestureCurrent"></p><ol id="gestureLog" aria-live="polite" aria-relevant="additions text"></ol></div><p class="muted">Camera đặt tại Raspberry Pi · Hình xem trước được lật gương</p></section><aside class="card controls"><span class="eyebrow">GÓC SÁNG TẠO</span><h2>Phong cách của bạn</h2><p class="muted">Nhận quyền điều khiển để bắt đầu phiên riêng.</p><p id="gestureHelp" class="muted" aria-live="polite" hidden></p><button id="claim">Bắt đầu sử dụng</button><fieldset id="filter" disabled><legend>Hiệu ứng · có thể chọn nhiều</legend><div id="effectChoices" class="checks"></div><button id="clearEffects" type="button" class="ghost">Bỏ tất cả hiệu ứng</button></fieldset><label>Khung ảnh ghép<select id="frame" disabled></select></label><img id="frameSample" alt="Khung được chọn" hidden><p class="muted">Khung hiển thị trên camera, ảnh chụp và ảnh dải. Có thể kết hợp nhiều phụ kiện với một bộ lọc màu. Hãy giữ mặt hướng về camera để kính/mũ bám tốt hơn.</p><button id="capture" disabled>◉ Chụp ảnh</button><button id="release" class="ghost" disabled>Nhường lượt</button></aside></div>
<section class="card results"><div class="section-heading"><div><span class="eyebrow">KHOẢNH KHẮC CỦA BẠN</span><h2>Ảnh vừa chụp</h2></div><span class="muted">Ảnh của trình duyệt này</span></div><div id="sessions"><p class="muted">Ảnh sẽ xuất hiện tại đây sau khi chụp. Hãy tải ảnh trước khi hết thời gian lưu trữ.</p></div></section>
{% endif %}
</main><footer>PI STUDIO / EDGE PHOTOBOOTH <span>Chạy cục bộ trên Raspberry Pi</span></footer>
</body></html>
````

## File: templates/kiosk.html
````html
<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<meta name="csrf-token" content="{{ csrf }}">
<title>Pi Studio · Kiosk Photobooth</title>
<link rel="stylesheet" href="/static/kiosk.css">
<script src="/static/kiosk.js" defer></script>
</head>
<body class="kiosk-body">

<header class="kiosk-header">
  <div class="kiosk-brand">
    ◉ PI STUDIO <span>KIOSK PHOTOBOOTH</span>
  </div>
  <div class="kiosk-status-badge">
    <div class="status-indicator">
      <span class="dot" id="kioskDot"></span>
      <span id="kioskStatusText">Đang kết nối…</span>
    </div>
    <span id="kioskClock" style="color: var(--kiosk-muted);">--:--</span>
  </div>
</header>

<main class="kiosk-stage">

  <!-- View 1: Attract / Welcome Screen -->
  <section class="kiosk-view view-welcome active" id="viewWelcome">
    <div class="welcome-logo">◉</div>
    <h1 class="welcome-title">Cười Lên Nào!</h1>
    <p class="welcome-desc">Chào mừng bạn đến với quầy chụp ảnh tự động Pi Studio. Hãy bước lại gần hoặc giơ bàn tay mở để bắt đầu!</p>

    <div class="welcome-gestures-guide">
      <div class="gesture-guide-item">
        <span class="gesture-icon">🖐</span>
        <div class="gesture-text">
          <strong>Bàn tay mở</strong>
          <small>Bắt đầu chụp</small>
        </div>
      </div>
      <div class="gesture-guide-item">
        <span class="gesture-icon">👍</span>
        <div class="gesture-text">
          <strong>Ngón cái</strong>
          <small>Chụp ảnh (3-2-1)</small>
        </div>
      </div>
      <div class="gesture-guide-item">
        <span class="gesture-icon">✌</span>
        <div class="gesture-text">
          <strong>Chữ V</strong>
          <small>Đổi phụ kiện</small>
        </div>
      </div>
      <div class="gesture-guide-item">
        <span class="gesture-icon">✊</span>
        <div class="gesture-text">
          <strong>Nắm tay</strong>
          <small>Hủy lượt chụp</small>
        </div>
      </div>
    </div>

    <button class="btn-big-start" id="btnKioskStart">BẮT ĐẦU CHỤP ẢNH</button>
  </section>

  <!-- View 2: Active Camera Studio -->
  <section class="kiosk-view view-studio" id="viewStudio">
    <div class="studio-main">
      <div class="kiosk-viewfinder">
        <img id="kioskPreview" alt="Xem trước camera">
        <div id="kioskFlash"></div>
        <div class="kiosk-countdown" id="kioskCountdown" hidden>3</div>
        <div class="kiosk-progress" id="kioskProgress">Đã chụp 0 / 4</div>
      </div>
    </div>

    <aside class="kiosk-sidebar">
      <div class="kiosk-sidebar-panel">
        <h3>CHỌN PHỤ KIỆN</h3>
        <div class="filter-pills" id="kioskFilterPills">
          <div class="filter-pill active" data-filter="none">Tự nhiên</div>
          <div class="filter-pill" data-filter="glasses">Kính</div>
          <div class="filter-pill" data-filter="hat">Mũ</div>
          <div class="filter-pill" data-filter="mono">Đen trắng</div>
          <div class="filter-pill" data-filter="sepia">Hoài cổ</div>
        </div>
      </div>

      <div class="kiosk-gesture-banner" id="kioskGestureBanner">
        Đang theo dõi cử chỉ tay…
      </div>

      <button class="btn-kiosk-snap" id="btnKioskSnap">📸 CHỤP ẢNH (👍)</button>
      <button class="filter-pill" id="btnKioskLeave" style="background: transparent;">Nhường lượt cho người sau</button>
    </aside>
  </section>

  <!-- View 3: Result & QR Code Download -->
  <section class="kiosk-view view-result" id="viewResult">
    <div class="result-photo-column">
      <div class="result-photo-frame">
        <img id="kioskResultImg" src="" alt="Ảnh Photostrip vừa chụp">
      </div>
    </div>

    <div class="result-qr-column">
      <span class="eyebrow" style="color: var(--kiosk-accent);">XONG RỒI ĐẤY!</span>
      <h2>Khoảnh Khắc Của Bạn</h2>
      <p>Mở ứng dụng <strong>Camera</strong> hoặc <strong>Zalo</strong> trên điện thoại để quét mã QR và tải ảnh ngay về máy:</p>

      <div class="qr-box">
        <img id="kioskQrCode" src="" alt="Mã QR tải ảnh">
      </div>

      <div class="auto-reset-timer" id="kioskAutoResetTimer">Tự động kết thúc sau 45s</div>
      <button class="btn-next-customer" id="btnNextCustomer">LƯỢT TIẾP THEO</button>
    </div>
  </section>

</main>

</body>
</html>
````

## File: tests/browser_server.py
````python
import json, tempfile, secrets, sys, signal
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pathlib import Path
from werkzeug.security import generate_password_hash
from waitress import serve
from photobooth import create_app
temporary=tempfile.TemporaryDirectory(prefix='booth-browser-')
root=Path(temporary.name)
(root/'credentials.json').write_text(json.dumps(dict(secret=secrets.token_hex(32),password_hash=generate_password_hash('browser-test-only-123'))))
app=create_app(root,demo=True)
def terminate(*_): raise SystemExit(0)
signal.signal(signal.SIGTERM,terminate)
try: serve(app,host='127.0.0.1',port=5055,threads=8)
finally:
 app.extensions['booth'].close()
 temporary.cleanup()
````

## File: tests/browser_smoke.py
````python
import subprocess,time,urllib.request,sys,os
from pathlib import Path
from playwright.sync_api import sync_playwright
proc=subprocess.Popen([sys.executable,str(Path(__file__).with_name('browser_server.py'))])
try:
 for _ in range(60):
  try:
   urllib.request.urlopen('http://127.0.0.1:5055/',timeout=1).close();break
  except Exception: time.sleep(.25)
 else: raise RuntimeError('Server unavailable')
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_BIN','/usr/bin/chromium'),headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
  context=browser.new_context(viewport={'width':1280,'height':900})
  errors=[]
  page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto('http://127.0.0.1:5055/admin')
  page.fill('#password','browser-test-only-123');page.click('#loginForm button')
  page.wait_for_selector('#adminPanel',state='visible')
  page.fill('input[name=photo_count]','2');page.fill('input[name=countdown]','1');page.click('#settingsForm button')
  page.wait_for_function("() => document.querySelector('#notice').textContent.includes('Đã lưu')")
  page.click('#start');page.click('#near');page.wait_for_function("() => document.querySelector('#adminState').textContent==='Sẵn sàng'")
  page.screenshot(path='/tmp/booth-admin.png',full_page=True)
  client=context.new_page();client.on('pageerror',lambda e:errors.append(str(e)))
  client.goto('http://127.0.0.1:5055/');client.click('#claim')
  client.wait_for_function("() => document.querySelector('#preview').naturalWidth>0 && !document.querySelector('#preview').hidden")
  client.wait_for_selector('input[value=hat]')
  client.check('input[value=hat]')
  client.select_option('#frame','orange_photo.png')
  client.click('#capture')
  client.wait_for_function("() => document.querySelectorAll('.photo').length===3",timeout=25000)
  client.screenshot(path='/tmp/booth-client.png',full_page=True)
  client.set_viewport_size({'width':390,'height':844})
  client.screenshot(path='/tmp/booth-mobile.png',full_page=True)
  assert client.evaluate('document.documentElement.scrollWidth<=window.innerWidth'), 'Mobile overflow'
  other=browser.new_context();op=other.new_page();op.goto('http://127.0.0.1:5055/')
  op.wait_for_function("() => document.querySelector('#placeholderTitle').textContent==='Vui lòng chờ lượt'")
  page.click('#refreshSessions');page.wait_for_function("() => document.querySelectorAll('#adminSessions .photo').length===3")
  assert not errors, errors
  print('PASS: admin login/settings/start, proximity, camera preview, filter/frame selection, capture, gallery, second client lock, mobile width. JS errors:',errors)
  browser.close()
finally:
 proc.terminate()
 try:proc.wait(timeout=10)
 except subprocess.TimeoutExpired:proc.kill()
````

## File: tests/test_gestures.py
````python
import unittest
from unittest.mock import patch
import test_system
from photobooth.gestures import choose_hand, GestureDebouncer


class OwnershipTest(unittest.TestCase):
    def test_only_center_face_hands_accepted(self):
        faces=[(40,80,90,90),(270,80,100,100),(510,80,90,90)]
        left=dict(pts=[(100,240)],score=.99)
        middle=dict(pts=[(320,240)],score=.7)
        right=dict(pts=[(550,240)],score=.99)
        self.assertIs(choose_hand([left,middle,right],faces,640),middle)
        self.assertIsNone(choose_hand([left,right],faces,640))
        self.assertIsNone(choose_hand([middle],[],640))

    def test_ambiguous_hand_rejected(self):
        self.assertIsNone(choose_hand([dict(pts=[(235,240)],score=.99)],
            [(120,80,100,100),(250,80,100,100)],640))

    def test_hold_does_not_repeat(self):
        deb=GestureDebouncer(hold_frames=3)
        events=[deb.update('Victory',.9,t) for t in range(10)]
        self.assertEqual(events.count('Victory'),1)


class GestureSystemTest(unittest.TestCase):
    setUp=test_system.SystemTest.setUp
    tearDown=test_system.SystemTest.tearDown
    ready=test_system.SystemTest.ready
    post=test_system.SystemTest.post

    def test_gesture_actions_use_existing_session(self):
        self.ready()
        self.post('/api/claim')
        self.store.configure({'photo_count':2})
        with patch.object(self.booth.gestures,'process') as process:
            process.return_value=('Thumb_Up',None)
            self.booth.tick()
            self.assertEqual(self.booth.state,'ready')
            process.return_value=('Open_Palm',None)
            self.booth.tick()
            self.assertTrue(self.booth.gestures.active)
            process.return_value=('Victory',None)
            self.booth.tick()
            self.assertEqual(self.booth.effects,['glasses'])
            process.return_value=(None,2.0)
            self.booth.tick()
            self.assertEqual(self.booth.camera.zoom,2.0)
            process.return_value=('Thumb_Up',None)
            self.booth.tick()
            self.assertEqual(self.booth.state,'capturing')
            self.assertEqual(len(self.client.get('/api/sessions').json),1)
            self.assertEqual(self.other.get('/api/sessions').json,[])
            process.return_value=('Closed_Fist',None)
            self.booth.tick()
            self.assertEqual(self.booth.state,'ready')
            self.assertEqual(self.store.sessions()[0]['status'],'interrupted')
        self.post('/api/release')
        self.assertFalse(self.booth.gestures.active)
        self.assertEqual(self.booth.camera.zoom,1.0)
````

## File: tests/test_system.py
````python
import json
import tempfile
import time
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash
from photobooth import create_app


class SystemTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        (self.root/'credentials.json').write_text(json.dumps(dict(secret='test-secret',password_hash=generate_password_hash('test-password-123'))))
        self.app=create_app(self.root,demo=True,start_worker=False)
        self.client=self.app.test_client()
        self.other=self.app.test_client()
        self.booth=self.app.extensions['booth']
        self.store=self.app.extensions['store']
        for c in (self.client,self.other): c.get('/')

    def tearDown(self):
        self.booth.close()
        self.store.db.close()
        self.tmp.cleanup()

    def post(self,path,data=None,client=None):
        c=client or self.client
        with c.session_transaction() as s: token=s['csrf']
        return c.post(path,json=data or {},headers={'X-CSRF-Token':token})

    def login(self):
        self.assertEqual(self.post('/api/login',{'password':'test-password-123'}).status_code,200)

    def ready(self):
        self.booth.start()
        self.booth.hardware.simulated_distance=.6
        for _ in range(3): self.booth.tick()
        self.assertEqual(self.booth.state,'ready')
        self.assertTrue(self.booth.hardware.led_on)

    def test_skip_sensor_start_and_stop(self):
        from photobooth import ROOT
        from photobooth.engine import Booth
        self.booth.close()
        self.booth=Booth(self.store,ROOT/'assets',demo=True,skip_sensor=True)
        self.booth.start()
        self.assertEqual(self.booth.state,'ready')
        self.assertTrue(self.booth.hardware.led_on)
        self.assertIsNone(self.booth.hardware.distance())
        self.booth.tick(time.monotonic()+1000)
        self.assertEqual(self.booth.state,'ready')
        self.assertIsNotNone(self.booth.camera.frame)
        self.booth.stop()
        self.assertEqual(self.booth.state,'stopped')
        self.assertFalse(self.booth.hardware.led_on)

    def test_skip_sensor_does_not_initialize_hcsr04(self):
        from unittest.mock import patch
        from photobooth.hardware import Hardware
        with patch('gpiozero.LED'), patch('gpiozero.Button'), patch('gpiozero.DistanceSensor') as sensor:
            hw=Hardware(enabled=True,skip_sensor=True)
            sensor.assert_not_called()
            self.assertIsNone(hw.error)
            self.assertIsNone(hw.distance())
            hw.close()

    def test_auth_and_csrf(self):
        self.assertEqual(self.client.post('/api/control',json={'action':'start'}).status_code,403)
        self.assertEqual(self.post('/api/control',{'action':'start'}).status_code,403)
        self.assertEqual(self.post('/api/login',{'password':'wrong'}).status_code,403)
        self.login()
        self.assertEqual(self.post('/api/control',{'action':'start'}).status_code,200)
        self.assertEqual(self.client.get('/api/events').status_code,200)
        self.assertEqual(self.other.get('/api/events').status_code,403)

    def test_full_capture_and_privacy(self):
        self.ready()
        self.assertEqual(self.post('/api/claim').status_code,200)
        self.assertEqual(self.post('/api/claim',client=self.other).status_code,409)
        self.assertEqual(self.other.get('/api/preview.jpg').status_code,403)
        self.assertEqual(self.client.get('/api/preview.jpg').mimetype,'image/jpeg')
        self.assertEqual(self.post('/api/select',{'filter':'glasses','frame':'black_glossy.png'}).status_code,200)
        self.assertEqual(self.post('/api/capture').status_code,200)
        self.assertEqual(self.post('/api/capture').status_code,409)
        self.assertEqual(self.post('/api/release').status_code,409)
        for _ in range(4):
            self.booth.next_shot=time.monotonic()-1
            self.booth.tick()
        items=self.client.get('/api/sessions').json
        self.assertEqual(items[0]['status'],'complete')
        self.assertEqual(len(items[0]['files']),5)
        name=items[0]['files'][-1]
        response=self.client.get('/media/'+name+'?download=1')
        self.assertEqual(response.status_code,200)
        self.assertIn('attachment',response.headers['Content-Disposition'])
        response.close()
        self.assertEqual(self.other.get('/api/sessions').json,[])
        self.assertEqual(self.other.get('/media/'+name).status_code,404)
        self.login()
        with self.client.session_transaction() as s: token=s['csrf']
        self.assertEqual(self.client.delete('/api/sessions/'+items[0]['id'],headers={'X-CSRF-Token':token}).status_code,200)
        self.assertFalse((self.store.photos/name).exists())

    def test_absence_and_stop(self):
        self.ready()
        self.booth.hardware.simulated_distance=2.5
        self.booth.last_seen=time.monotonic()-31
        self.booth.tick()
        self.assertEqual(self.booth.state,'waiting')
        self.assertFalse(self.booth.hardware.led_on)
        self.assertIsNone(self.booth.camera.frame)
        self.ready()
        self.post('/api/claim')
        self.post('/api/capture')
        self.booth.next_shot=time.monotonic()-1
        self.booth.tick()
        self.booth.stop()
        item=self.store.sessions()[0]
        self.assertEqual(item['status'],'interrupted')
        self.assertEqual(len(item['files']),1)
        self.assertEqual(self.booth.state,'stopped')
        self.assertFalse(self.booth.hardware.led_on)

    def test_settings_validation_and_persistence(self):
        self.login()
        settings=self.store.settings()
        bad=dict(settings,photo_count=999)
        self.assertEqual(self.post('/api/settings',bad).status_code,400)
        good=dict(settings,photo_count=2,countdown=1)
        self.assertEqual(self.post('/api/settings',good).status_code,200)
        self.assertEqual(self.store.settings()['photo_count'],2)
        self.ready()
        self.post('/api/claim')
        self.assertEqual(self.post('/api/select',{'filter':'none','frame':'../../etc/passwd'}).status_code,400)
        self.post('/api/capture')
        self.assertEqual(self.post('/api/settings',good).status_code,409)
        for _ in range(2):
            self.booth.next_shot=time.monotonic()-1
            self.booth.tick()
        self.assertEqual(len(self.store.sessions()[0]['files']),3)

    def test_expired_lease_and_recovery(self):
        self.ready()
        self.post('/api/claim')
        self.booth.lease=0
        self.assertEqual(self.post('/api/claim',client=self.other).status_code,200)
        self.assertEqual(self.post('/api/capture').status_code,409)
        self.store.create('restart-session','owner')
        self.store.recover()
        self.assertEqual(self.store.sessions()[0]['status'],'interrupted')

    def test_camera_failure_and_disabled_filter(self):
        self.ready()
        self.post('/api/claim')
        self.store.configure({'enabled_filters':['none'], 'default_filter':'none'})
        self.assertEqual(self.post('/api/select',{'filter':'hat','frame':'none'}).status_code,400)
        self.post('/api/capture')
        self.booth.camera.read=lambda *args: False
        self.booth.tick()
        self.assertEqual(self.store.sessions()[0]['status'],'failed')
        self.assertEqual(self.booth.state,'ready')

    def test_absence_during_capture_finishes_sequence(self):
        self.ready()
        self.post('/api/claim')
        self.post('/api/capture')
        self.booth.hardware.simulated_distance=2.5
        self.booth.last_seen=time.monotonic()-31
        for _ in range(4):
            self.booth.next_shot=time.monotonic()-1
            self.booth.tick()
        self.assertEqual(self.store.sessions()[0]['status'],'complete')
        self.booth.tick()
        self.assertEqual(self.booth.state,'waiting')
        self.assertFalse(self.booth.hardware.led_on)

    def test_retention_and_pages(self):
        self.assertEqual(self.client.get('/').status_code,200)
        self.assertEqual(self.client.get('/admin').status_code,200)
        self.assertIn("default-src 'self'",self.client.get('/').headers['Content-Security-Policy'])
        self.store.create('old','owner')
        self.store.finish('old','complete',['old.jpg'])
        (self.store.photos/'old.jpg').write_bytes(b'test')
        old=(datetime.now(timezone.utc)-timedelta(days=10)).isoformat()
        self.store.db.execute('UPDATE sessions SET created=? WHERE id=?',(old,'old'))
        self.store.db.commit()
        self.booth.cleanup()
        self.assertFalse(self.store.sessions())
        self.assertFalse((self.store.photos/'old.jpg').exists())

    def test_rotation_without_cropping(self):
        import numpy as np
        from photobooth.imaging import Imaging
        img = np.zeros((100, 200, 4), dtype=np.uint8)
        img[20:80, 20:180] = (255, 0, 0, 255)
        same = Imaging.rotate_without_cropping(img, 0.0)
        self.assertEqual(same.shape, img.shape)
        rot45 = Imaging.rotate_without_cropping(img, 45.0)
        self.assertGreater(rot45.shape[0], img.shape[0])
        self.assertGreater(rot45.shape[1], img.shape[1])
        self.assertGreater(np.sum(rot45[:, :, 3] > 0), 0)
        self.booth.camera.face_angles = [25.0]
        ok = self.booth.camera.read(['glasses', 'hat'], 'none')
        self.assertTrue(ok)
        self.assertIsNotNone(self.booth.camera.frame)

    def test_kiosk_qr_and_download(self):
        res = self.client.get('/kiosk')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'KIOSK PHOTOBOOTH', res.data)
        self.assertEqual(self.client.get('/api/qr/nonexistent.png').status_code, 404)
        self.assertEqual(self.client.get('/download/nonexistent').status_code, 404)
        sid = 'test-session-12345'
        self.store.create(sid, 'test-visitor')
        test_file = f'{sid}_strip.jpg'
        (self.store.photos / test_file).write_bytes(b'dummy-image-data')
        self.store.finish(sid, 'complete', [test_file])
        qr_res = self.client.get(f'/api/qr/{sid}.png')
        self.assertEqual(qr_res.status_code, 200)
        self.assertEqual(qr_res.mimetype, 'image/png')
        self.assertGreater(len(qr_res.data), 100)
        dl_res = self.client.get(f'/download/{sid}')
        self.assertEqual(dl_res.status_code, 200)
        file_res = self.client.get(f'/download/{sid}/{test_file}')
        self.assertEqual(file_res.status_code, 200)
        self.assertEqual(file_res.data, b'dummy-image-data')
        file_res.close()


if __name__=='__main__': unittest.main()
````

## File: .gitignore
````
.venv*/
venv*/
__pycache__/
*.pyc
*.pt
*.onnx
instance/
*.db
````

## File: bash.txt
````
.venv-gestures/bin/python manage.py run --hardware --skip-sensor --led-pin 27
````

## File: manage.py
````python
#!/usr/bin/env python3
import argparse
import getpass
import json
import os
from pathlib import Path
import secrets
from werkzeug.security import generate_password_hash


def main():
    parser=argparse.ArgumentParser(description='Raspberry Photobooth')
    parser.add_argument('command',choices=['init','run'])
    parser.add_argument('--data',default=os.environ.get('BOOTH_DATA',str(Path(__file__).parent/'instance')))
    parser.add_argument('--demo',action='store_true',help='Camera mô phỏng, không phải camera thật')
    parser.add_argument('--hardware',action='store_true',help='Sử dụng GPIO thật')
    parser.add_argument('--skip-sensor',action='store_true',help='Bỏ qua HC-SR04; sẵn sàng ngay sau Start, không tự nghỉ khi vắng người')
    parser.add_argument('--led-pin',type=int,choices=range(2,28),default=18,help='Chân BCM cho LED, mặc định 18')
    parser.add_argument('--camera',type=int,default=0)
    parser.add_argument('--host',default='0.0.0.0')
    parser.add_argument('--port',type=int,default=5000)
    args=parser.parse_args()
    if args.hardware and (args.led_pin==17 or (not args.skip_sensor and args.led_pin in (23,24))):
        parser.error('Chân LED trùng nút hoặc cảm biến')
    if args.command=='init':
        root=Path(args.data)
        root.mkdir(parents=True,exist_ok=True,mode=0o700)
        path=root/'credentials.json'
        if path.exists():
            parser.error('Tài khoản đã tồn tại. Để đặt lại mật khẩu, sao lưu rồi xóa credentials.json; mọi phiên đăng nhập sẽ hết hiệu lực.')
        password=os.environ.get('BOOTH_ADMIN_PASSWORD') or getpass.getpass('Mật khẩu admin (ít nhất 10 ký tự): ')
        if len(password)<10: parser.error('Mật khẩu cần ít nhất 10 ký tự')
        with path.open('x') as f:
            os.chmod(path,0o600)
            json.dump(dict(secret=secrets.token_hex(32),password_hash=generate_password_hash(password)),f)
        print('Đã tạo tài khoản admin tại',root)
        return
    from photobooth import create_app
    from waitress import serve
    app=create_app(args.data,args.demo,args.hardware,args.camera,skip_sensor=args.skip_sensor,led_pin=args.led_pin)
    print(f'Photobooth: http://<IP-Pi>:{args.port} | Admin: /admin',flush=True)
    try: serve(app,host=args.host,port=args.port,threads=8)
    finally: app.extensions['booth'].close()


if __name__=='__main__': main()
````

## File: README.md
````markdown
# Pi Studio — Raspberry Photobooth

Photobooth chạy cục bộ trên Raspberry Pi 4. Điện thoại/laptop mở web để xem webcam trên Pi, chọn hiệu ứng, chụp và tải ảnh. Không cần HDMI, máy in, VPS hoặc mobile app.

## Những gì đã có

- Web tiếng Việt thích ứng điện thoại và desktop, không tải thư viện từ CDN.
- Trang `/admin`: đăng nhập, Start/Stop, xem cảm biến/LED/bộ nhớ, cấu hình số ảnh, đếm ngược, ngưỡng khoảng cách, thời gian vắng và lưu ảnh.
- Quản lý các phiên chụp: xem, tải, xóa ảnh; bật/tắt filter; chọn filter mặc định; nhật ký 500 sự kiện gần nhất.
- Nút GPIO17 dùng kiểu nhấn chuyển trạng thái Start/Stop, đồng bộ với admin web.
- Siêu âm GPIO23/24: 3 mẫu liên tiếp dưới ngưỡng mới bật LED GPIO18 và camera.
- Vắng liên tục quá thời gian cài đặt: tắt LED, ngừng camera, về chờ. Nếu đang chụp thì hoàn tất chuỗi trước.
- Một trình duyệt giữ quyền điều khiển tại một thời điểm. Quyền hết hạn sau 120 giây không có polling; người khác có thể nhận lượt. Khi đang chụp không chuyển lượt.
- Filter kính/mũ theo bounding box khuôn mặt OpenCV Haar Cascade; đen trắng và sepia. **Chưa có Face Mesh và xoay filter theo góc mặt.**
- Mặc định 4 ảnh có đếm ngược, lưu JPG và dải ảnh ghép có khung tùy chọn.
- Ảnh lưu theo quyền phiên trình duyệt; admin xem tất cả. Đóng/xóa cookie hoặc đổi trình duyệt có thể mất quyền truy cập ảnh cũ, nên tải ảnh ngay.
- Tự dọn ảnh quá hạn mỗi giờ; phiên bị ngắt do khởi động lại được đánh dấu `interrupted`.
- Camera và cảm biến mô phỏng để demo khi chưa có phần cứng.

## Cài trên Raspberry Pi OS

Cần Python 3.10 trở lên. Dùng OpenCV, NumPy, Pillow và gpiozero của Raspberry Pi OS để tránh phải biên dịch trên ARM:

```bash
sudo apt update
sudo apt install -y python3-venv python3-opencv opencv-data python3-numpy python3-pil python3-gpiozero python3-lgpio
cd /home/pi/cuoiky
./scripts/install.sh
.venv/bin/python manage.py init
```

`init` yêu cầu mật khẩu admin tối thiểu 10 ký tự, lưu hash và khóa phiên trong `instance/credentials.json` (quyền 0600). Không có mật khẩu mặc định. Có thể dùng biến `BOOTH_ADMIN_PASSWORD` cho khởi tạo tự động; không đưa mật khẩu vào repo.

Máy Linux khác có thể tạo venv rồi `pip install -r requirements.txt`; chế độ GPIO cần thêm `requirements-pi.txt`. Mô hình OpenCV đã có sẵn trong `assets/models`.

## Chạy

### Demo không có webcam/cảm biến

```bash
.venv/bin/python manage.py run --demo
```

### Webcam thật, cảm biến/LED mô phỏng

```bash
.venv/bin/python manage.py run
```

### Đủ phần cứng

```bash
.venv/bin/python manage.py run --hardware
```

Đổi webcam bằng `--camera 1`. Đổi cổng bằng `--port 5001`. Thư mục dữ liệu khác: `--data /path/to/data` cho cả `init` và `run`.

Dùng `hostname -I` để tìm IP Pi. Điện thoại và Pi phải cùng mạng, router không bật client isolation:

- Chụp ảnh: `http://<IP-Pi>:5000/`
- Admin: `http://<IP-Pi>:5000/admin`

Không cần Internet sau khi cài đặt. Không gọi camera điện thoại và không cần cấp quyền camera cho trình duyệt. Server dùng Waitress; preview là JPEG dùng chung cập nhật bằng HTTP khoảng 5–6 lần/giây; trạng thái được polling 800 ms thay vì Socket.IO để giảm phụ thuộc. Chất lượng thực tế cần đo với webcam và filter trên Pi.

## Luồng demo

1. Mở `/admin`, đăng nhập rồi nhấn **Start hệ thống**.
2. Nếu chưa bật `--hardware`, nhấn **Có người · 0,6 m** trong admin.
3. Mở `/` trên điện thoại hoặc tab khác; nhấn **Bắt đầu sử dụng**.
4. Xem camera, chọn kính/mũ/màu, chọn khung cho ảnh ghép.
5. Nhấn **Chụp ảnh**. Đếm ngược được Pi quyết định, lặp theo số ảnh đã cấu hình.
6. Tải từng ảnh hoặc dải ảnh từ mục **Ảnh vừa chụp**.
7. Nhấn **Nhường lượt** nếu có người tiếp theo. Admin có thể quản lý và xóa phiên.
8. Nhấn **Rời đi · 2,5 m** để thử vắng người; sau 30 giây mặc định LED và camera tắt. Nhấn Stop dừng booth ngay cả trong lúc chụp, giữ các ảnh đã lưu và đánh dấu phiên bị ngắt.

Cảm biến không tự mở trình duyệt điện thoại. Người dùng cần mở trang trước. Cảm biến siêu âm phát hiện vật thể ở gần, không xác minh đó là con người; bộ nhận diện mặt dùng riêng để ghép filter.

## Đấu dây (số GPIO theo BCM)

Tắt nguồn trước khi đấu dây.

| Thiết bị | Kết nối |
|---|---|
| HC-SR04 VCC | 5 V, chân vật lý 2 |
| HC-SR04 GND | GND, chân 6 |
| HC-SR04 TRIG | GPIO23, chân 16 |
| HC-SR04 ECHO | Qua chia áp tới GPIO24, chân 18 |
| Nút nhấn | Một chân GPIO17 (chân 11), chân còn lại GND; chương trình dùng pull-up nội bộ |
| LED đơn | GPIO18 (chân 12) → điện trở 330 Ω → anode LED; cathode → GND |
| Webcam | USB trên Pi |

**ECHO HC-SR04 là 5 V, không nối thẳng GPIO.** Dùng ECHO → 1 kΩ → điểm nối GPIO24 → 2 kΩ → GND, tạo mức khoảng 3,33 V. Không nối nút Start vào 5 V hoặc 3,3 V theo sơ đồ báo cáo cũ: bản code này dùng nút nối GND và pull-up.

GPIO18 chỉ điều khiển LED báo nhỏ. Đèn chiếu sáng chụp ảnh cần nguồn và MOSFET/driver riêng. Siêu âm phải đặt tránh vật cản cố định trước cảm biến. Tài khoản chạy dịch vụ cần quyền truy cập `video`, `gpio` của Raspberry Pi OS.

Nguồn tham khảo đấu siêu âm: https://gpiozero.readthedocs.io/en/stable/api_input.html#distancesensor-hc-sr04

## Tự chạy cùng Pi

Sau khi đã khởi tạo admin và thử phần cứng thành công:

```bash
sudo cp deploy/photobooth.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now photobooth
sudo systemctl status photobooth
journalctl -u photobooth -f
```

Unit mẫu dùng user `pi`, đường dẫn `/home/pi/cuoiky` và `--hardware`; sửa unit nếu máy khác. Không chạy đồng thời lệnh `manage.py run` và service: chỉ một tiến trình sở hữu camera/GPIO. Dịch vụ tự chạy nhưng booth vẫn **Đã dừng**, admin/nút vật lý cần Start để kích hoạt.

Không rút nguồn bằng nút Start/Stop. Muốn tắt Pi: dừng booth rồi tắt OS bằng cách thông thường.

## Thêm tài nguyên

- `assets/filters/*.png`: PNG nền trong suốt.
- `assets/filters/filters.json`: `label`, `file`, `width` (tỷ lệ so với bề rộng mặt), `anchor_y` (vị trí tâm filter theo chiều cao mặt; 0 là trán, 1 là cằm). Chỉnh để khớp từng PNG.
- `assets/frames/*.png`: tự xuất hiện trên web; vùng trong suốt là vùng hiển thị ảnh. Khung hiện tại co giãn theo dải ảnh; nên chuẩn bị khung đúng tỷ lệ dải để tránh méo. Khung không áp dụng lên preview/từng ảnh riêng.
- Sau khi thêm filter cần khởi động lại dịch vụ và bật filter trong admin. Danh sách filter tùy chỉnh được lấy từ file cấu hình.
- Nguồn khung/mô hình ghi trong các file `SOURCES.md`. Hai ảnh filter ban đầu do người dùng cung cấp.

## Cấu trúc

```text
manage.py                 CLI khởi tạo/chạy
photobooth/__init__.py     API, đăng nhập, phân quyền, CSRF
photobooth/engine.py       Trạng thái, phiên chụp, worker duy nhất
photobooth/imaging.py      Camera, nhận diện, filter, ảnh ghép
photobooth/hardware.py     Siêu âm, nút, LED, mô phỏng
photobooth/storage.py      SQLite, ảnh, nhật ký
static/                   CSS/JS cục bộ
templates/                Web chụp và admin
assets/                   Filter, khung, mô hình
instance/                 Dữ liệu runtime (không commit)
tests/                    Kiểm thử hệ thống bằng camera mô phỏng
deploy/                   Unit systemd mẫu
```

## Kiểm thử

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Kiểm thử luồng chụp/ảnh ghép, quyền ảnh/preview, khóa phiên, CSRF/admin, cấu hình, vắng người, Stop giữa phiên, phục hồi và xóa ảnh hết hạn. Kiểm thử mô phỏng không thay thế nghiệm thu phần cứng.

## Phạm vi vận hành

Hệ thống dành cho mạng LAN tin cậy, không mở cổng lên Internet. HTTP LAN chưa mã hóa mật khẩu/ảnh trên đường truyền; nếu triển khai mạng công cộng cần HTTPS và gia cố thêm. Admin được bảo vệ bằng hash mật khẩu, CSRF, cookie HttpOnly/SameSite và giới hạn thử đăng nhập. Ảnh có quyền theo cookie trình duyệt; không có QR chuyển ảnh sang thiết bị khác.

Bản hiện tại dùng detector OpenCV thay MediaPipe để chạy với Python/OpenCV có sẵn trên Pi, không nhận diện danh tính. Chưa hỗ trợ in, Face Mesh, tự phát Wi-Fi hoặc shutdown OS từ web. Không cần các tính năng này để chạy luồng đã thống nhất.

Kiểm thử trình duyệt tùy chọn (cần Chromium và `pip install playwright` trong venv):

```bash
.venv/bin/python tests/browser_smoke.py
```

Bài test tự chạy server demo ở loopback cổng 5055, tạo dữ liệu/tài khoản tạm, kiểm tra admin → Start → mô phỏng người → chọn filter/khung → chụp → xem ảnh, khóa lượt cho trình duyệt thứ hai và kích thước mobile 390 px. Ảnh kiểm tra ghi `/tmp/booth-admin.png`, `/tmp/booth-client.png`, `/tmp/booth-mobile.png`. Có thể đặt `CHROMIUM_BIN` nếu Chromium nằm ở đường dẫn khác.


## Chưa có HC-SR04: bỏ qua cảm biến

```bash
# Webcam thật, không cần cảm biến/GPIO
.venv/bin/python manage.py run --skip-sensor

# Webcam, LED và nút thật, không khởi tạo HC-SR04
.venv/bin/python manage.py run --hardware --skip-sensor

# Camera mô phỏng, bỏ qua thao tác mô phỏng khoảng cách
.venv/bin/python manage.py run --demo --skip-sensor
```

Nhấn Start trên admin (hoặc nút vật lý nếu dùng `--hardware`) → bật LED và chuyển Sẵn sàng ngay. Camera bắt đầu lấy hình ở vòng xử lý kế tiếp. Không cần nhấn Có người, không tự nghỉ sau 30 giây; dùng Stop để tắt booth. Chế độ `--hardware --skip-sensor` vẫn yêu cầu LED/nút và GPIO hoạt động; chỉ bỏ HC-SR04. Bỏ cờ để khôi phục luồng cảm biến cũ.


Nếu GPIO18 bị kernel chiếm (ví dụ chức năng PCM_CLK), chọn một GPIO trống bằng `--led-pin` (số BCM). Trên Pi đã kiểm tra, GPIO27 đang trống:

```bash
.venv/bin/python manage.py run --hardware --skip-sensor --led-pin 27
```

Tắt nguồn rồi chuyển dây LED từ chân vật lý 12 sang chân vật lý 13 (GPIO27); giữ điện trở 330 Ω và GND. Không tắt driver của hệ điều hành để giải phóng chân nếu chưa xác định tác dụng của driver. Dùng `gpioinfo` và `pinctrl get 18,27` để kiểm tra chân.

### Điều khiển bằng cử chỉ (không dùng YOLO)

Camera thật mặc định bật MediaPipe Gesture Recognizer; chế độ demo không chạy AI.
Môi trường `.venv` cũ dùng Python 3.13 ARM64 không cài được MediaPipe 0.10.x.
Dùng môi trường riêng `.venv-gestures` với Python 3.11, giữ nguyên Python hệ thống:

```bash
cd /home/pi/cuoiky
python3.11 -m venv .venv-gestures
.venv-gestures/bin/python -m pip install -r requirements-gestures.txt -r requirements-pi.txt
```

Model đã có ở `assets/models/gesture_recognizer.task`. Nếu triển khai máy mới:

```bash
curl -fL https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task -o assets/models/gesture_recognizer.task
```

Chạy camera thật không dùng GPIO/cảm biến:

```bash
.venv-gestures/bin/python manage.py run --skip-sensor
```

Chạy cùng nút và LED GPIO27 theo cấu hình thử nghiệm hiện tại:

```bash
.venv-gestures/bin/python manage.py run --hardware --skip-sensor --led-pin 27
```

Nếu terminal cũ còn chạy booth bằng `.venv/bin/python`, nhấn Ctrl+C ở terminal đó
trước khi chạy lệnh mới để giải phóng camera và cổng 5000.
Không thêm `--demo` khi thử cử chỉ vì chế độ đó dùng ảnh mô phỏng.
Nếu chạy qua systemd, `ExecStart` phải trỏ tới `.venv-gestures/bin/python`.

Sau khi Start, mở trang khách và nhấn **Bắt đầu sử dụng** để gắn ảnh với phiên riêng
của trình duyệt. Đứng ở giữa khung hình, giữ cử chỉ vài khung hình:

- **Open Palm**: kích hoạt điều khiển cử chỉ cho phiên đang nhận quyền.
- **Thumb Up**: bắt đầu chụp theo số ảnh và thời gian đếm ngược đã cấu hình.
- **Victory / Pointing Up**: hiệu ứng tiếp theo / trước đó trong danh sách được bật;
  mỗi lần chọn một hiệu ứng, thay thế tổ hợp hiệu ứng hiện tại.
- **Closed Fist**: hủy phần còn lại của phiên đang chụp; ảnh đã chụp vẫn được giữ.
- Co ba ngón giữa/áp út/út, mở hoặc khép ngón cái–trỏ: zoom 1–2.5x.

Dưới camera có bảng trạng thái nhận diện: cử chỉ hiện tại, độ tin cậy, số mặt/tay
và 8 lệnh gần nhất kèm kết quả. Terminal in `[GESTURE]` khi cử chỉ đã được xác nhận
sau khi giữ đủ khung hình; không in mỗi frame. Bảng cũng báo khi chưa thấy mặt/tay
hoặc không gán được tay cho người ở giữa. Log được xóa khi nhường lượt hoặc dừng.

Hệ thống dùng khuôn mặt OpenCV gần trục giữa nhất làm người điều khiển và gán tay
bằng khoảng cách tương đối với các khuôn mặt. Không có khuôn mặt hoặc tay có gán
quyền mơ hồ thì không nhận lệnh. Đây là quy tắc theo vị trí, không theo dõi danh tính;
người khác đi vào giữa có thể trở thành người điều khiển, tay che chéo vẫn có thể
bị gán nhầm. Nhận cử chỉ trên ảnh gốc, trước hiệu ứng và zoom. Zoom áp dụng cả preview,
ảnh lẻ và ảnh ghép, không vẽ thông tin AI lên ảnh lưu.

Nếu thiếu thư viện/model, web vẫn hoạt động; trường `gesture_error` trong
`/api/status` và thông báo trên trang cho biết lỗi cử chỉ. Không tải model tự động
trong worker. Cần thử camera thật trên Pi để kiểm tra tốc độ và độ chính xác.
````

## File: requirements-dev.txt
````
-r requirements.txt
playwright>=1.50,<2
````

## File: requirements-gestures.txt
````
-r requirements.txt
mediapipe>=0.10.18,<0.11
````

## File: requirements-pi.txt
````
gpiozero>=2,<3
lgpio>=0.2,<1
````

## File: requirements.txt
````
Flask>=3.1,<4
waitress>=3,<4
numpy>=1.24,<3
opencv-python-headless>=4.8,<5
Pillow>=10,<13
qrcode>=8.0,<9
````
