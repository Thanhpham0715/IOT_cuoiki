# Tài liệu chức năng Photobooth

> **Mục đích:** mô tả kiến trúc, chức năng đã triển khai, giới hạn hiện tại và
> các bước tiếp theo của dự án Photobooth.
>
> **Trạng thái tài liệu:** đối chiếu mã nguồn, cấu hình, tài nguyên và test hiện
> có tại thời điểm cập nhật. “Đã triển khai” nghĩa là chức năng đã có trong mã;
> không đồng nghĩa mọi tình huống đã được kiểm thử trên phần cứng thực tế.

## 1. Tổng quan dự án

Photobooth hiện được chia thành hai chương trình độc lập:

| Thành phần | Thư mục | Vai trò |
|---|---|---|
| Raspberry Pi client | `Raspberry_Pi/` | Đọc camera và phần cứng, gửi hình/video lên Server, nhận lệnh chụp/đèn qua MQTT. |
| Server | `Server_Module/` | Cung cấp API/Admin, nhận luồng camera, chạy AI, điều phối chụp, lưu dữ liệu và tạo ảnh xem trước. |

Hai module có cấu hình, dependency và bản sao package `shared/` riêng. Package
này chứa schema và MQTT topic dùng để giao tiếp; nếu thay đổi giao thức ở một
bên thì phải cập nhật bên còn lại tương ứng.

### Các kênh giao tiếp

- **Video trực tiếp và điều khiển gesture:** Raspberry Pi mở WebSocket tới
  Server (`/ws/frames`), gửi metadata cùng JPEG frame; Server trả kết quả nhận
  diện và trạng thái điều khiển.
- **Thiết bị, lệnh chụp và LED:** hai bên trao đổi trạng thái/lệnh qua MQTT.
- **Ảnh chụp:** Pi gửi ảnh JPEG lên API HTTP của Server. Ảnh chụp liên hoàn
  được lưu là ảnh gốc; bước ghép khung tạo bản xem trước riêng.
- **Admin:** giao diện web tĩnh được Server phục vụ tại `/admin`. Không mở file
  `admin.html` trực tiếp bằng `file:///`, vì khi đó trình duyệt không cùng
  origin với API và không lấy được trạng thái/frame từ Server.

## 2. Chức năng đã triển khai

### 2.1. Raspberry Pi

#### Camera và luồng trực tiếp

- Đọc hình từ camera cấu hình tại `camera.device_index`.
- Mặc định cấu hình luồng camera **480×360, 12 FPS**, JPEG quality 60; thông số
  có thể chỉnh trong `Raspberry_Pi/config/config.yaml`.
- Gửi frame qua WebSocket tới Server; Pi ghi log thời gian xử lý/nhịp frame và
  FPS đạt được.
- Ảnh chụp tĩnh sử dụng cấu hình riêng, mặc định **1920×1080**, JPEG quality
  90; sau khi chụp Pi trở lại cấu hình stream.
- Có lớp mock hardware để phát triển/test không cần camera thật. Cấu hình demo
  thực tế đang dùng `camera.mock_hardware: false`.

#### MQTT và trạng thái thiết bị

- Pi phát trạng thái `online` định kỳ và dùng Last Will để báo `offline` nếu
  mất kết nối bất thường.
- Pi đăng ký nhận lệnh chụp và lệnh điều khiển LED trên các topic của
  `device_id`.
- Pi gửi kết quả lệnh chụp theo `command_id`; Server dùng ID này để ghép trạng
  thái trả về với yêu cầu tương ứng.
- Có hỗ trợ telemetry cảm biến ánh sáng nếu cấu hình BH1750; hiện mẫu cấu hình
  để `camera.light_sensor_address: null`, tức cảm biến chưa được bật.

#### Phần cứng

- Điều khiển LED PWM, mặc định BCM GPIO18.
- Nút vật lý, mặc định BCM GPIO17; nút phát sự kiện chụp thủ công.
- Có thể tắt nút bằng cách đặt `camera.button_gpio_pin: null`.
- LED/nút cần GPIO Zero và backend GPIO phù hợp trên Raspberry Pi OS (ví dụ
  `lgpio`); mô phỏng phần mềm không xác nhận được dây nối hoặc phần cứng thật.

#### Lưu ảnh khi mất mạng

- Nếu chụp thủ công nhưng không tải được ảnh lên Server, Pi ghi ảnh vào
  `data/offline_photos/`.
- Khi kết nối Server trở lại, Pi thử đồng bộ các ảnh đang chờ.
- Đây là hàng đợi lưu ảnh offline cơ bản; chưa phải một hệ thống đồng bộ có
  giao diện quản lý, retry policy theo từng lỗi và cảnh báo dung lượng ổ đĩa.

### 2.2. Server, API và dữ liệu

#### Quản lý phiên

- Pi tìm session đang hoạt động theo `device_id`; nếu chưa có thì yêu cầu Server
  tạo session mới.
- Server giới hạn một session đang hoạt động trên mỗi thiết bị.
- Session lưu trạng thái, thiết bị, filter/zoom và sticker mặc định cho ảnh
  chụp thông thường.
- Khi Pi dừng bình thường, Pi gọi API kết thúc session. Server lưu session và
  trạng thái chụp trong SQLite.

#### Nhận diện và điều khiển gesture

- Server dùng MediaPipe Gesture Recognizer để phân tích bàn tay trên frame
  nhận từ Pi.
- Các cử chỉ hiện được dùng trong luồng điều khiển:
  - **Open_Palm:** bật điều khiển gesture.
  - **Thumb_Up:** bắt đầu đếm ngược chụp.
  - **Victory:** chuyển sang filter tiếp theo.
  - **Pointing_Up:** chuyển về filter trước.
  - **Closed_Fist:** hủy đếm ngược đang chạy.
  - **Pinch:** điều chỉnh zoom trong khoảng 1.0×–2.5×.
- Có bộ debouncer theo confidence, số frame giữ, thời gian nghỉ và số frame
  release; Open_Palm có ngưỡng kích hoạt riêng thấp hơn ngưỡng gesture chung.
- Mặc định cấu hình: `min_score: 0.6`, `activation_min_score: 0.5`,
  `hold_frames: 4`, `release_frames: 5`.
- Kết quả gesture, confidence, filter/zoom, trạng thái và thời gian xử lý được
  trả về Admin. Một phần lịch sử kết quả được giữ trong bộ nhớ tới khi Server
  khởi động lại.

#### Ảnh chụp đơn

- Server gửi lệnh chụp qua MQTT.
- Pi chụp ảnh độ phân giải tĩnh, upload lên API; Server có nhánh xử lý ảnh chụp
  đơn gồm zoom, filter và sticker theo cấu hình session.
- Server kiểm tra định dạng/kích thước upload, ghi ảnh và metadata; có API xem
  ảnh, danh sách ảnh và tải ảnh gốc khi có.
- Live preview không bị ghép sticker; sticker chỉ áp dụng lên ảnh chụp.

#### Chụp liên hoàn, xem lại và chụp lại

- Admin có thể bắt đầu/hủy một batch chụp liên hoàn.
- Mặc định batch gồm **8 ảnh**, đếm ngược **10 giây** trước từng ảnh; mỗi lệnh
  có mã tương quan để xác nhận Pi đã chụp và upload xong.
- Số ảnh cho phép cấu hình từ **4 đến 8** để phù hợp các khung bốn ô; countdown
  từ 1–30 giây; timeout chờ mỗi ảnh từ 1–300 giây.
- Mỗi ảnh của batch được lưu là **ảnh gốc sạch**, không ghi đè ảnh cũ:
  `data/photos/raw/<session_id>/<batch_id>/raw_01.jpg` … `raw_08.jpg`.
- Khi batch hoàn thành, Admin hiện ảnh của batch theo thứ tự và cho phép:
  - Chụp lại cả bộ tối đa một lần.
  - Chọn tiếp tục/chốt bộ ảnh.
  - Tự chốt bộ hiện tại nếu hết timeout quyết định (mặc định 30 giây; cấu hình
    được 30–60 giây).
- Ảnh lượt chụp lại được lưu ở batch khác. Trạng thái batch/review được lưu bền
  trong SQLite; có xử lý khôi phục review khi retake bị hủy, lỗi hoặc Server
  khởi động lại.
- Endpoint tải ảnh gốc: `GET /api/v1/photos/{photo_id}/raw`.

#### Chọn khung, ảnh, filter/sticker và xem trước

- Server đọc danh mục khung từ
  `Server_Module/assets/photo_effects/manifest.json`.
- Hiện có ba khung bốn ô:
  - `classic_strip_4`: dải dọc cổ điển.
  - `pastel_pink_strip_4`: dải dọc hồng pastel.
  - `grid_2x2_retro`: lưới 2×2.
- Sau khi chốt bộ ảnh, Admin cho phép chọn một khung và chọn **4 ảnh khác nhau**
  từ batch đang được chốt. Thứ tự các ảnh tương ứng với thứ tự ô của khung.
- Mỗi ô có lựa chọn riêng:
  - Một ảnh trong bộ.
  - Một filter màu built-in: original, gray, sepia, warm, negative, cartoon
    hoặc pixel.
  - Sticker khuôn mặt tùy chọn nếu Face Landmarker và asset đã sẵn sàng.
- Server crop giữa ảnh gốc theo tỷ lệ ô, resize vào ô, phát hiện khuôn mặt trên
  vùng ảnh đã crop, áp filter màu, ghép sticker sau filter rồi đặt frame RGBA
  lên trên cùng.
- Các lựa chọn khung/ảnh/filter/sticker được lưu trong SQLite. Ảnh gốc không bị
  thay đổi; có thể lưu lại bố cục để dựng preview mới.
- Admin hiện preview do Server render trả về. Preview là ảnh ghép xem trước,
  **chưa phải file thành phẩm được lưu lâu dài**.

#### Nhận diện khuôn mặt và tài nguyên hiệu ứng

- Face sticker dùng MediaPipe Face Landmarker ở chế độ ảnh tĩnh và metadata
  từng overlay để căn chỉnh theo mắt/trán, tỷ lệ, pivot, offset và góc xoay.
- Hiện asset pack có bốn sticker: kính, vương miện, tai mèo và vòng hào quang.
- Face model được cấu hình tại
  `Server_Module/config/config.yaml` (`face_effects.model_path`); overlay nằm
  dưới `assets/photo_effects/face_overlays/`.
- Frame, manifest và metadata được đọc khi Server khởi động; thay đổi asset
  cần khởi động lại Server.

### 2.3. Admin dashboard

- Hiển thị tình trạng Server, AI, kết nối Server tới MQTT broker và số thiết bị
  online theo dữ liệu Server nhận được.
- Hiển thị live camera Pi, trạng thái gesture, confidence, gesture được chọn,
  số bàn tay, thời gian xử lý AI và FPS ước lượng từ frame Server xử lý.
- Có điều khiển LED, chụp đơn, chụp liên hoàn, hủy batch, chọn sticker mặc định
  cho nhánh ảnh chụp đơn, duyệt ảnh gốc.
- Có giao diện xem lại/chụp lại bộ ảnh và trình chỉnh bố cục bốn ô.
- Admin cần được truy cập qua Server, ví dụ:
  `http://<server-lan-ip>:8000/admin`. Nếu dùng token, nhập token trên trang.

### 2.4. Cấu hình và lưu trữ

- Cấu hình Server tại `Server_Module/config/config.yaml`; cấu hình Pi tại
  `Raspberry_Pi/config/config.yaml`.
- Broker, IP Server, device ID, camera, GPIO, FPS, độ phân giải, model AI,
  timeout chụp và đường dẫn lưu trữ đều cấu hình được.
- Server lưu SQLite, ảnh và log dưới `Server_Module/data/` theo mặc định.
- Khi chạy LAN, Pi cần dùng IP LAN của PC trong cả `server.client_host` và
  `mqtt.broker_host`. Server dùng `127.0.0.1` làm broker host nếu Mosquitto
  chạy trên cùng PC; broker phải cho phép kết nối từ Pi.
- API có hỗ trợ Bearer token tùy chọn; cấu hình token trên Pi và Server phải
  trùng nhau nếu bật.

## 3. Những phần chưa làm hoặc chưa hoàn chỉnh

Các mục sau đây không nên xem là đã có chỉ vì đã có ảnh, manifest hoặc chỗ dành
trên khung:

### 3.1. Thanh toán và kiosk cho khách hàng

- Chưa có tích hợp thanh toán, xác nhận thanh toán thành công, giá/gói chụp
  hoặc tự mở session sau thanh toán.
- Session hiện được Pi tự tạo/tìm khi kết nối; chưa có luồng kiosk độc lập dành
  cho khách hàng kết thúc phiên và bắt đầu lượt tiếp theo.
- Dashboard hiện là giao diện **Admin/kiểm thử**, chưa phải UI kiosk hoàn chỉnh
  có hướng dẫn tạo dáng và thao tác thân thiện trên màn cảm ứng.

### 3.2. Thời hạn phiên và khôi phục

- Có timeout cho quyết định chụp lại; chưa có timeout áp dụng cho mọi màn hình
  lựa chọn/chỉnh sửa theo yêu cầu ban đầu.
- Chưa có cơ chế tổng quát cho khách quay lại tiếp tục phiên sau khi đóng
  trình duyệt hoặc mất điện trong mọi giai đoạn hậu kỳ.
- Session được kết thúc theo vòng đời tiến trình Pi hiện tại; cần kiểm thử
  hành vi nhiều lượt chụp liên tiếp và thao tác kết thúc phiên trong môi trường
  kiosk thực tế.

### 3.3. Tùy chỉnh và trải nghiệm chọn ảnh

- Chọn ảnh hiện là các danh sách thả xuống theo ô; chưa có giao diện thumbnail
  trực quan để kéo-thả, đổi thứ tự hoặc xem từng ảnh lớn trước khi chọn.
- Chưa có preview trực tiếp của từng ô sau mỗi lần thay filter/sticker; người
  dùng cần lưu lựa chọn để Server dựng lại ảnh ghép hoàn chỉnh.
- Sticker chỉ được ghép khi MediaPipe Face Landmarker khả dụng. Nếu thiếu model
  hoặc model không khởi tạo được, tùy chọn sticker phải bị vô hiệu hóa/báo lỗi.
- Chưa có thao tác tinh chỉnh vị trí sticker bằng tay trên từng ô sau nhận diện.
- Các filter ngoài danh sách built-in/LUT tùy chỉnh chưa được triển khai; thư
  mục `filters/` hiện chỉ là chỗ dành sẵn.
- Khả năng nhận diện sticker trên ảnh thiếu sáng, nhiều khuôn mặt, mặt nghiêng
  hoặc ảnh bị crop chặt cần đánh giá bằng ảnh thực.

### 3.4. Thành phẩm, in và trả ảnh

- Chưa lưu ảnh ghép preview thành một file final bền vững có metadata riêng.
- Chưa tạo QR, upload bộ ảnh lên cloud, trang tải ảnh qua QR hoặc chính sách
  hết hạn/xóa dữ liệu.
- Chưa tích hợp máy in, chọn khổ giấy, căn lề, số bản in, retry và trạng thái
  máy in.
- Trường `qr_slot` có trong manifest chỉ mô tả vùng dành cho QR; chưa có code
  sinh/ghép QR vào ảnh.
- Chưa có nút tải final image trong Admin; preview được trả trực tiếp từ API.

### 3.5. Vận hành và triển khai

- Chưa có kiểm thử end-to-end tự động bao phủ Pi thật + Mosquitto + Server +
  camera/GPIO.
- Chưa xác nhận mọi firewall/router/Wi-Fi isolation cho từng địa điểm demo.
- Cấu hình IP LAN thay đổi theo mạng; cần kiểm tra và cập nhật IP trước demo.
- API hiện dùng token tùy chọn; nếu triển khai ngoài mạng tin cậy cần bật token
  và có thể cần HTTPS, giới hạn truy cập, backup và chính sách lưu dữ liệu.
- Chưa có dashboard giám sát dung lượng đĩa, dọn ảnh cũ, backup/restore SQLite,
  hay cảnh báo lỗi phần cứng.
- Bộ test hiện có nhưng lần chạy trong môi trường phát triển trước đó bị
  sandbox chặn đọc một số dependency Python trong `site-packages`; cần chạy
  suite trong virtual environment có quyền truy cập dependency để có kết quả
  kiểm thử đầy đủ.

## 4. Việc nên làm tiếp theo

### Ưu tiên 1 — Ổn định luồng đang có trên LAN

1. Chạy Mosquitto, Server và Pi; đảm bảo cả ba dùng cùng device ID và đúng IP.
2. Truy cập Admin bằng URL HTTP do Server phục vụ, không dùng `file:///`.
3. Xác nhận lần lượt: thiết bị online, live frame, điều khiển LED, chụp đơn,
   chụp đủ 8 ảnh, ảnh gốc đúng thứ tự, retake tối đa một lần.
4. Chạy thử chọn cả ba khung, chọn 4 ảnh bất kỳ/khác nhau, đổi filter/sticker
   từng ô, reload Admin và xác nhận cấu hình được khôi phục.
5. Ghi lại lỗi theo log Server/Pi và thêm test hồi quy cho lỗi đã gặp.

**Tiêu chí hoàn thành:** một lượt chụp thật đi từ Pi tới preview ghép khung mà
không phải thao tác sửa dữ liệu trực tiếp trong SQLite.

### Ưu tiên 2 — Hoàn thiện trải nghiệm chọn ảnh và xem trước

1. Thay select ảnh bằng thumbnail 8 ảnh, cho phép gán ảnh vào ô và thể hiện rõ
   thứ tự 1–4.
2. Hiển thị preview khung có ảnh thật sau khi chọn; cho phép đổi khung/ảnh/
   filter/sticker rồi render lại.
3. Thêm chỉ báo rõ khi Face Landmarker hoặc asset sticker không sẵn sàng.
4. Kiểm tra ảnh theo các kích thước/tỷ lệ khác nhau, crop khuôn mặt, vị trí
   sticker và chất lượng render.

**Tiêu chí hoàn thành:** người dùng có thể tự chọn và xác nhận bố cục trên màn
hình cảm ứng, không cần hiểu tên file hay nhờ Admin thao tác.

### Ưu tiên 3 — Xuất ảnh thành phẩm

1. Tạo artifact final có định dạng/chất lượng xác định và lưu vào thư mục của
   session.
2. Lưu trạng thái export và metadata (khung, slot, effect, overlay, ảnh nguồn,
   thời gian) để có thể dựng lại.
3. Thêm API/UI tải thành phẩm và bảo đảm tải ảnh gốc vẫn hoạt động.
4. Định nghĩa cách xử lý nếu render lỗi, session kết thúc hoặc người dùng đổi
   lựa chọn sau khi đã export.

**Tiêu chí hoàn thành:** ảnh final có thể tải lại sau khi Server restart và
không làm thay đổi các ảnh gốc.

### Ưu tiên 4 — QR và giao ảnh

1. Chọn nơi lưu ảnh (Server nội bộ hoặc cloud) và thời hạn truy cập.
2. Tạo URL tải ảnh có kiểm soát quyền/hạn sử dụng; sinh QR từ URL.
3. Ghép QR vào đúng `qr_slot` và kiểm tra mã quét được trên ảnh in.
4. Tạo trang nhận ảnh qua QR cho final image và bộ ảnh gốc theo yêu cầu.

### Ưu tiên 5 — In ảnh

1. Chọn máy in, driver, kích thước giấy và DPI.
2. Hiệu chỉnh tỷ lệ/cắt/lề theo từng frame.
3. Thêm hàng đợi in, retry, báo hết giấy/mất kết nối và hiển thị kết quả trên
   Admin.

### Ưu tiên 6 — Kiosk và thanh toán

1. Chốt UX cho khách hàng: chọn gói, thanh toán, chụp, duyệt, chọn khung, xác
   nhận và nhận ảnh.
2. Tích hợp thiết bị/cổng thanh toán phù hợp; chỉ tạo phiên sau khi nhận được
   xác nhận hợp lệ.
3. Thêm timeout cho từng màn hình, mặc định khi hết giờ và dọn phiên để máy
   sẵn sàng cho khách tiếp theo.
4. Tách rõ Admin vận hành với màn hình khách hàng.

### Ưu tiên 7 — Vận hành ổn định

- Chạy test suite trong môi trường cài dependency dự án; bổ sung test API cho
  xác thực, trạng thái review, chọn layout và preview.
- Chạy test phần cứng thực tế cho camera, GPIO, button, MQTT và mất kết nối.
- Thêm backup/restore, quản lý dung lượng và chính sách xóa ảnh.
- Bật xác thực cho mạng không tin cậy; đánh giá TLS/HTTPS và quyền truy cập
  trước khi đưa hệ thống ra ngoài LAN demo.

## 5. Hướng dẫn chạy nhanh để kiểm tra

### Server (PC/laptop)

Từ thư mục `Cuoi_ki/Server_Module`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[server]"
python -m server.main
```

Khởi động MQTT broker trước Server. Admin chạy tại
`http://127.0.0.1:8000/admin`; máy khác trong cùng LAN dùng
`http://<IP-PC>:8000/admin`.

### Raspberry Pi

Từ thư mục `Raspberry_Pi`, cấu hình `server.client_host` và
`mqtt.broker_host` thành IP LAN của PC rồi cài và chạy:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[pi]"
python -m pi.main
```

Trên firewall/router cần cho phép Pi tới API/WebSocket (mặc định TCP 8000) và
MQTT broker (mặc định TCP 1883). Nếu Mosquitto ở một máy khác, Server và Pi
phải cùng trỏ tới địa chỉ broker đó; `127.0.0.1` chỉ trỏ về chính thiết bị
đang chạy chương trình.

### Test

Từ `Cuoi_ki/Server_Module`:

```powershell
python -m unittest discover -s tests
```

Test tự động không thay thế kiểm thử camera/GPIO/MQTT trên thiết bị thật.

## 6. Các vị trí mã nguồn quan trọng

| Nội dung | Vị trí |
|---|---|
| Cấu hình Server | `Server_Module/config/config.yaml` |
| Cấu hình Pi | `Raspberry_Pi/config/config.yaml` |
| API, WebSocket, điều phối chụp | `Server_Module/server/main.py` |
| SQLite, session, batch, layout, ảnh | `Server_Module/server/storage.py` |
| Filter built-in | `Server_Module/server/image_processing.py` |
| Face Landmarker và ghép sticker | `Server_Module/server/face_overlays.py` |
| Tải khung, crop và render layout | `Server_Module/server/photo_layout.py` |
| Admin dashboard | `Server_Module/server/static/admin.html` |
| MQTT phía Server | `Server_Module/server/iot.py` |
| Client, MQTT, upload, camera stream phía Pi | `Raspberry_Pi/pi/main.py` |
| Camera, LED, button, cảm biến phía Pi | `Raspberry_Pi/pi/hardware.py` |
| Frame, sticker, manifest | `Server_Module/assets/photo_effects/` |
| Test Server | `Server_Module/tests/` |

