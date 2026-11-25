"""
tools/mock_server.py
--------------------
Server giả để Pi phát triển và test độc lập — KHÔNG cần AI thật.

Nhận frame từ Pi → trả PoseResult ngẫu nhiên mỗi vòng.
Chạy: python tools/mock_server.py
"""
import asyncio
import json
import random
import time
import websockets

# Thêm root vào path để import shared
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.schemas import PoseResult, FeedbackItem

PORT = 8765


async def handler(websocket):
    print(f"[mock_server] Pi kết nối: {websocket.remote_address}")
    frame_id = 0

    async for message in websocket:
        frame_id += 1

        # Bỏ qua binary frame (JPEG), chỉ parse JSON meta
        if isinstance(message, str):
            meta = json.loads(message)
            session_id = meta.get("session_id", "mock_session")
        else:
            session_id = "mock_session"
            # Nhận được ảnh — trong thực tế server sẽ gửi vào AI
            # print(f"[mock_server] Nhận frame {frame_id}, {len(message)} bytes")
            continue

        # Giả lập AI response — cứ 15 frame thì "sẵn sàng chụp"
        score = random.randint(55, 95)
        ready = (frame_id % 15 == 0)

        result = PoseResult(
            session_id=session_id,
            frame_id=frame_id,
            pose_score=score,
            status="ok" if score >= 75 else "adjusting",
            feedback=([] if score >= 75 else [
                FeedbackItem(body_part="right_arm", message="Giơ tay phải lên cao hơn")
            ]),
            ready_to_capture=ready,
        )

        await websocket.send(result.model_dump_json())
        if ready:
            print(f"[mock_server] Frame {frame_id}: READY TO CAPTURE (score={score})")


async def main():
    print(f"[mock_server] Đang chạy tại ws://0.0.0.0:{PORT}")
    print("[mock_server] Ctrl+C để dừng")
    async with websockets.serve(handler, "0.0.0.0", PORT):
        await asyncio.Future()  # chạy mãi


if __name__ == "__main__":
    asyncio.run(main())

