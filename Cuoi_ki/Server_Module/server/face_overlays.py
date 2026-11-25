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
