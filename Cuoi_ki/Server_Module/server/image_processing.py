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
