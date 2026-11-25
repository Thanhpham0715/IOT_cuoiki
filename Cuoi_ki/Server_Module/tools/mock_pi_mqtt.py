"""
tools/mock_pi_mqtt.py
---------------------
Giả lập Pi publish MQTT — để test dashboard và server mà không cần Pi thật.

Chạy: python tools/mock_pi_mqtt.py
"""
import json
import random
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import paho.mqtt.client as mqtt
from shared.config import cfg
from shared.mqtt_topics import Topics
from shared.schemas import LightSensor, DeviceStatus, LEDAck

DEVICE_ID = cfg["mqtt"]["device_id"]
BROKER    = cfg["mqtt"]["broker_host"]
PORT      = cfg["mqtt"]["broker_port"]
INTERVAL  = cfg["mqtt"]["heartbeat_interval_sec"]


def on_message(client, userdata, msg):
    """Nhận lệnh LED từ server và gửi ACK giả."""
    try:
        payload = json.loads(msg.payload.decode())
        cmd_id  = payload.get("command_id", "unknown")
        brightness = payload.get("brightness", 50)
        print(f"[mock_pi] Nhận lệnh LED: brightness={brightness} (cmd={cmd_id})")

        ack = LEDAck(command_id=cmd_id, applied=brightness)
        client.publish(Topics.device_ack(DEVICE_ID), ack.model_dump_json(), qos=1)
        print(f"[mock_pi] Gửi ACK: {ack.model_dump_json()}")
    except Exception as e:
        print(f"[mock_pi] Lỗi xử lý lệnh LED: {e}")


def main():
    client = mqtt.Client(client_id=f"mock_pi_{DEVICE_ID}")

    # LWT: broker tự gửi "offline" nếu mock_pi mất kết nối đột ngột
    lwt_payload = DeviceStatus(device_id=DEVICE_ID, status="offline").model_dump_json()
    client.will_set(Topics.status(DEVICE_ID), lwt_payload, qos=1, retain=True)

    client.on_message = on_message
    client.connect(BROKER, PORT)
    client.subscribe(Topics.led_set(DEVICE_ID), qos=1)

    # Publish online
    online = DeviceStatus(device_id=DEVICE_ID, status="online", version="mock-0.1")
    client.publish(Topics.status(DEVICE_ID), online.model_dump_json(), qos=1, retain=True)
    print(f"[mock_pi] Đã kết nối broker {BROKER}:{PORT}, device_id={DEVICE_ID}")
    print("[mock_pi] Đang publish lux mỗi 2 giây. Ctrl+C để dừng.")

    client.loop_start()

    lux = 200.0
    try:
        while True:
            # Lux dao động ngẫu nhiên (mô phỏng cảm biến)
            lux += random.uniform(-10, 10)
            lux = max(50, min(500, lux))

            sensor = LightSensor(device_id=DEVICE_ID, lux=round(lux, 1), timestamp=time.time())
            client.publish(Topics.sensor_light(DEVICE_ID), sensor.model_dump_json(), qos=0)
            print(f"[mock_pi] lux={lux:.1f}")

            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        print("\n[mock_pi] Dừng.")
        # Không gọi disconnect() → broker sẽ gửi LWT "offline"
        client.loop_stop()


if __name__ == "__main__":
    main()

