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
