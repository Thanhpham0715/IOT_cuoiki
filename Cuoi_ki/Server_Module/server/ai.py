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
