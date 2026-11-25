"""Run MediaPipe gesture inference on a machine on the booth's LAN."""
from pathlib import Path
from threading import Lock
import time

import cv2
from flask import Flask, request
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import numpy as np
from waitress import serve


def create_app():
    app = Flask(__name__)
    app.logger.setLevel('INFO')
    app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024
    model = Path(__file__).with_name('gesture_recognizer.task')
    recognizer = vision.GestureRecognizer.create_from_options(
        vision.GestureRecognizerOptions(
            base_options=python.BaseOptions(model_asset_path=str(model)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
        )
    )
    lock = Lock()
    timestamp = 0

    @app.get('/health')
    def health():
        return {'status': 'ok'}

    @app.post('/recognize')
    def recognize():
        nonlocal timestamp
        started = time.perf_counter()
        app.logger.info(
            'recognize_request client=%s content_length=%s',
            request.remote_addr,
            request.content_length,
        )
        body = request.get_data()
        if not body:
            app.logger.warning('recognize_rejected client=%s reason=empty_body', request.remote_addr)
            return {'error': 'Expected a JPEG image'}, 400
        frame = cv2.imdecode(np.frombuffer(body, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            app.logger.warning('recognize_rejected client=%s reason=invalid_image', request.remote_addr)
            return {'error': 'Expected a JPEG image'}, 400
        image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
        )
        with lock:
            timestamp = max(timestamp + 1, time.monotonic_ns() // 1_000_000)
            result = recognizer.recognize_for_video(image, timestamp)
        hands = []
        for index, landmarks in enumerate(result.hand_landmarks):
            categories = result.gestures[index]
            category = categories[0] if categories else None
            world = result.hand_world_landmarks[index] if result.hand_world_landmarks else []
            hands.append({
                'pts': [[p.x, p.y] for p in landmarks],
                'world': [[p.x, p.y, p.z] for p in world] or None,
                'label': category.category_name if category else None,
                'score': category.score if category else 0,
            })
        prediction_summary = [
            {'label': hand['label'], 'score': round(float(hand['score']), 4)}
            for hand in hands
        ]
        app.logger.info(
            'recognize_result client=%s hands=%d predictions=%s duration_ms=%.1f',
            request.remote_addr,
            len(hands),
            prediction_summary,
            (time.perf_counter() - started) * 1000,
        )
        return {'hands': hands}

    return app


if __name__ == '__main__':
    app = create_app()
    print('Gesture API: port 8080 (/health, /recognize)', flush=True)
    serve(app, host='0.0.0.0', port=8080)
