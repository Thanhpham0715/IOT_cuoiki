# API nhận diện cử chỉ

Chép toàn bộ thư mục này sang laptop có IP `10.190.22.213`. Thư mục đã có
file model `gesture_recognizer.task`.

Mở terminal trong thư mục đã chép. Ví dụ dùng Python 3.11 trên Linux hoặc macOS:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python server.py
```

Trên Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe server.py
```

Giữ terminal chạy và cho phép Raspberry Pi truy cập cổng TCP 8080 qua tường
lửa laptop. Dùng mạng LAN tin cậy vì API nhận ảnh camera qua HTTP. Từ Pi,
kiểm tra kết nối:

```bash
curl --max-time 3 http://10.190.22.213:8080/health
```

Kết quả mong đợi là `{"status":"ok"}`. Sau đó chạy booth và nhận quyền trên
trang khách hoặc kiosk để Pi bắt đầu gửi ảnh. Mỗi request `/recognize` và kết
quả dự đoán (nhãn, confidence, số tay, thời gian xử lý) sẽ được in ở terminal
đang chạy server; ảnh và tọa độ landmark không được ghi vào log.
