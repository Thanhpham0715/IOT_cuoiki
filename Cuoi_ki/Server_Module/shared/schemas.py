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
