"""
shared/mqtt_topics.py
---------------------
Tên topic MQTT dùng chung.
Mọi người import từ đây, không gõ tay chuỗi topic ở nhiều chỗ.

Dùng:
    from shared.mqtt_topics import Topics
    client.subscribe(Topics.led_set("pi01"))   # → "photobooth/pi01/led/set"
"""


class Topics:
    """Factory tạo topic theo device_id."""

    @staticmethod
    def status(device_id: str) -> str:
        """Pi publish online/offline (retained + LWT)."""
        return f"photobooth/{device_id}/status"

    @staticmethod
    def sensor_light(device_id: str) -> str:
        """Pi publish lux."""
        return f"photobooth/{device_id}/sensor/light"

    @staticmethod
    def led_set(device_id: str) -> str:
        """Server publish lệnh LED."""
        return f"photobooth/{device_id}/led/set"

    @staticmethod
    def led_status(device_id: str) -> str:
        """Pi publish trạng thái LED hiện tại."""
        return f"photobooth/{device_id}/led/status"

    @staticmethod
    def device_ack(device_id: str) -> str:
        """Pi publish ACK sau khi thực thi lệnh."""
        return f"photobooth/{device_id}/device/ack"

    @staticmethod
    def button(device_id: str) -> str:
        """Pi publish sự kiện nút nhấn."""
        return f"photobooth/{device_id}/button"

    @staticmethod
    def capture(device_id: str) -> str:
        """Server yêu cầu Pi chụp ảnh độ phân giải cao."""
        return f"photobooth/{device_id}/camera/capture"

    @staticmethod
    def photo_status(device_id: str) -> str:
        """Pi thông báo kết quả chụp ảnh."""
        return f"photobooth/{device_id}/camera/status"


# QoS mặc định theo loại dữ liệu
QOS = {
    "telemetry": 0,     # lux, LED status — mất 1 bản không sao
    "command": 1,       # led/set, capture — cần đảm bảo đến nơi
    "status": 1,        # online/offline — quan trọng
}

