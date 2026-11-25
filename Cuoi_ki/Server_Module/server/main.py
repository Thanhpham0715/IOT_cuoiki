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
