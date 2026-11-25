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
