"""Hardware abstraction for mock development and Raspberry Pi deployment."""

import logging
import random
import time
from collections.abc import Callable

import cv2
import numpy as np

from shared.config import cfg

logger = logging.getLogger(__name__)


class MockHardware:
    def __init__(self) -> None:
        camera = cfg.get("camera", {})
        self.width = int(camera.get("width", 640))
        self.height = int(camera.get("height", 480))
        self._started_at = time.monotonic()
        self._lux = 220.0
        self.brightness = int(cfg.get("light_control", {}).get("default_brightness", 50))

    def read_frame(self) -> np.ndarray:
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        elapsed = int(time.monotonic() - self._started_at)
        cv2.putText(
            frame,
            "MOCK CAMERA",
            (30, self.height // 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.1,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            time.strftime("%H:%M:%S"),
            (30, self.height // 2 + 45),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (180, 180, 180),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            f"frame {elapsed}",
            (30, self.height // 2 + 85),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (180, 180, 180),
            2,
            cv2.LINE_AA,
        )
        return frame

    def read_lux(self) -> float:
        self._lux = min(500, max(50, self._lux + random.uniform(-8, 8)))
        return round(self._lux, 1)

    def capture_photo(self) -> np.ndarray:
        return self.read_frame()

    def set_led(self, brightness: int) -> int:
        self.brightness = min(100, max(0, brightness))
        return self.brightness

    def close(self) -> None:
        return None


class RaspberryPiHardware:
    def __init__(self, button_callback: Callable[[str], None] | None = None) -> None:
        camera = cfg.get("camera", {})
        self._camera = cv2.VideoCapture(int(camera.get("device_index", 0)))
        if not self._camera.isOpened():
            self._camera.release()
            raise RuntimeError(
                f"Could not open camera index {camera.get('device_index', 0)}"
            )
        self._camera.set(cv2.CAP_PROP_FRAME_WIDTH, int(camera.get("width", 640)))
        self._camera.set(cv2.CAP_PROP_FRAME_HEIGHT, int(camera.get("height", 480)))
        self._led = None
        self._bus = None
        self._button = None
        led_pin = camera.get("led_gpio_pin")
        if led_pin is not None:
            try:
                from gpiozero import PWMLED
            except ImportError as exc:
                self.close()
                raise RuntimeError("Install gpiozero to control the LED on Raspberry Pi") from exc
            self._led = PWMLED(int(led_pin))
            logger.info("PWM LED configured on BCM GPIO%s", led_pin)
        button_pin = camera.get("button_gpio_pin")
        if button_pin is not None and button_callback is not None:
            try:
                from gpiozero import Button
            except ImportError as exc:
                self.close()
                raise RuntimeError("Install gpiozero to use the physical button") from exc
            self._button = Button(int(button_pin), bounce_time=0.1)
            self._button.when_pressed = lambda: button_callback("manual_capture")
            logger.info("Physical button configured on BCM GPIO%s", button_pin)

    def read_frame(self) -> np.ndarray:
        success, frame = self._camera.read()
        if not success or frame is None:
            raise RuntimeError("Camera did not return a frame")
        return frame

    def capture_photo(self) -> np.ndarray:
        camera = cfg.get("camera", {})
        stream_width = int(camera.get("width", 640))
        stream_height = int(camera.get("height", 480))
        photo_width = int(camera.get("photo_width", 1920))
        photo_height = int(camera.get("photo_height", 1080))
        self._camera.set(cv2.CAP_PROP_FRAME_WIDTH, photo_width)
        self._camera.set(cv2.CAP_PROP_FRAME_HEIGHT, photo_height)
        try:
            return self.read_frame()
        finally:
            self._camera.set(cv2.CAP_PROP_FRAME_WIDTH, stream_width)
            self._camera.set(cv2.CAP_PROP_FRAME_HEIGHT, stream_height)

    def read_lux(self) -> float:
        camera = cfg.get("camera", {})
        address = camera.get("light_sensor_address")
        if address is None:
            raise RuntimeError("BH1750 light sensor address is not configured")
        if self._bus is None:
            try:
                from smbus2 import SMBus
            except ImportError as exc:
                raise RuntimeError("Install smbus2 to read the BH1750 light sensor") from exc
            try:
                self._bus = SMBus(1)
            except OSError as exc:
                raise RuntimeError("Could not open the I2C bus") from exc
        sensor_address = int(address)
        try:
            self._bus.write_byte(sensor_address, 0x10)
            time.sleep(0.18)
            reading = self._bus.read_i2c_block_data(sensor_address, 0x00, 2)
        except (OSError, IndexError) as exc:
            raise RuntimeError("Could not read the BH1750 light sensor") from exc
        return round(((reading[0] << 8) | reading[1]) / 1.2, 1)

    def set_led(self, brightness: int) -> int:
        if self._led is None:
            raise RuntimeError("LED GPIO is disabled; configure camera.led_gpio_pin")
        applied = min(100, max(0, brightness))
        self._led.value = applied / 100
        return applied

    def close(self) -> None:
        if self._camera is not None:
            self._camera.release()
        if self._led is not None:
            self._led.close()
        if self._button is not None:
            self._button.close()
        if self._bus is not None:
            self._bus.close()
