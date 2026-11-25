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
