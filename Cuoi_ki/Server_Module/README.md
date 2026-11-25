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

