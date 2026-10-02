# Trimui-XiaoZhi

Ứng dụng mới cho TrimUI Smart Pro S stock OS.

## Cài đặt

Tải `trimui-xiaozhi-vX.Y.Z.zip` từ
[Releases](https://github.com/nlkcodenew/trimui-xiaozhi/releases/latest) rồi giải nén
vào gốc thẻ nhớ để có `Apps/Trimui-XiaoZhi/launch.sh`. Tên hiển thị trên máy là
**Trimui-XiaoZhi**. Cần Python 3.8+, SDL2, SDL2_ttf như ứng dụng Chiaki đã chạy.
Thư mục `vendor/sdl2` và `assets/font.ttf` đi kèm. Lõi Xiaozhi AArch64 đi kèm trong
`bin/xiaozhi-core`.

Lần đầu tiên, ứng dụng sao chép *cấu hình thiết bị* từ thư mục app cũ
(`Apps/XIAOZHI`, `Apps/C-XIAOZHI`, `Apps/TrimuiXiaozhi`) nếu có để giữ danh tính; trạng thái kích hoạt luôn được xác nhận lại với máy chủ. Trên thẻ này, cấu hình định danh cũ đã được chép riêng vào `data/xiaozhi_config.json` (không nằm trong bộ mã nguồn). Bản gốc tự lưu thêm tại `data/xiaozhi_config.original.json` khi chạy. Không sao chép trạng thái tạm hoặc cache. Nếu chưa có cấu hình, lõi tự tạo danh tính; mã kích hoạt sẽ hiện trên màn hình. Cài đặt/nhật ký/lịch sử mới nằm trong `data/` và `logs/` của app mới. Không dùng `/dev/fb0` hoặc đọc `/dev/input/event3`.

Điều khiển: A bắt đầu/nghe lại; B dừng, B lần nữa thoát; SELECT mở cài đặt; UP/DOWN cuộn lịch sử; trong cài đặt A đổi giá trị, B quay lại. Có thể dùng bàn phím Enter/Escape/F1/mũi tên để kiểm thử. Truy cập web mặc định tắt, bật trong cài đặt rồi mở `http://<IP-máy>:8788/`; PIN được lưu trong `data/remote-pin` và hiện trong cài đặt.

Micro là cách dùng chính: nhấn A để bắt đầu, nói tự nhiên, B để dừng.

## Cập nhật tự động (OTA)

Mỗi lần mở app, `launch.sh` chạy nền `ota-update.sh`: kiểm `manifest.json` trên
GitHub, tải các file lệch SHA-256 và thay thế. App mở ngay không phải chờ, hiện
badge "Đang kiểm tra..." / "Đang tải vX..." và bảng **ĐÃ CẬP NHẬT LÊN vX - MỞ LẠI
APP ĐỂ DÙNG** khi xong.

- Tắt OTA: đặt `XIAOZHI_NO_OTA=1` trước khi mở app (tắt hẳn ở `launch.sh`).
- Offline hoặc lỗi mạng: bỏ qua êm, không chặn boot. Xem `logs/ota.log`.
- `data/` (danh tính + kích hoạt) và `logs/` **không bao giờ bị ghi đè**; danh
  tính và lịch sử chat giữ nguyên sau khi cập nhật.
- Kiểm thử tay: `sh ota-update.sh --check` (chỉ báo có bản mới), `sh ota-update.sh`
  để hỏi trước khi cài.

## Micro

Mặc định `Micro = auto` lấy thiết bị ghi âm đầu tiên từ `arecord -l`; nếu không nhận tiếng, đổi Micro trong cài đặt và xem thiết bị đã chọn trong `logs/app.log`. Nhập chữ trên web chỉ là tùy chọn phụ, không cần bật web để trò chuyện bằng giọng nói.

Nếu nhấn A nhưng không có phản hồi, mở Cài đặt → **Thử micro (nói 4 giây)** → A, nói bình thường trong 4 giây. App tạm dừng lõi để độc quyền thiết bị ghi âm, rồi hiện mức tín hiệu từng kênh và lưu số đo trong `logs/app.log`. Nếu gần -90 dB là im lặng; hãy thử `Micro = default` hoặc thiết bị còn lại, hay tăng mic gain trên thiết bị. Bản thử không tự ý đổi các điều khiển ALSA của Smart Pro S.

Nhật ký sớm nhất: `Trimui-Xiaozhi-boot.log` ở thư mục app, hoặc `Logs/Trimui-Xiaozhi.txt` nếu thẻ có thư mục `Logs` (hoặc đường `LOGS_PATH` do hệ thống cấp). Nhật ký Python: `logs/launcher.log`, `logs/app.log`; lõi: `logs/core.log`. Nếu không có cả log khởi động thì hệ thống chưa gọi `launch.sh` (thử làm mới danh sách app/khởi động lại máy). Nếu có log, xem lỗi cuối trước khi cài lại. Dữ liệu định danh/khóa API nằm trong `data/xiaozhi_config.json`, **không chia sẻ tập tin này**. Bản dựng chưa được kiểm thử trực tiếp trên máy; cần xác nhận SDL, micro và luồng kích hoạt với thiết bị thật.

Ứng dụng mới thay giao diện, điều khiển và web; giữ lõi giao thức Xiaozhi AArch64 đã hoạt động từ bộ cũ và công cụ truy vấn trạng thái máy. Các lệnh nhạc chuyên biệt của giao diện cũ chưa được chuyển sang bản này; chức năng nói chuyện, lịch sử, cài đặt, kích hoạt và chat web là phạm vi bản thử đầu tiên.

### Đổi trợ lý / gỡ liên kết

Trên xiaozhi.me/console, gỡ thiết bị khỏi trợ lý cũ bằng menu **Thiết bị** trước. Trong app vào **SELECT → Gỡ liên kết / đổi trợ lý → A → A xác nhận**. App dừng lõi, sao lưu danh tính hiện tại thành `data/xiaozhi_config.pre-unlink-YYYYMMDD-HHMMSS.json`, tạo danh tính thiết bị mới và hiện **mã xác minh 6 số do máy chủ cấp**; nhập mã này tại **Trợ lý → Thêm thiết bị**. Mục **Kích hoạt lại** chỉ kiểm tra lại danh tính cũ, không tạo mã mới nếu thiết bị vẫn được liên kết. Nếu Wi-Fi chưa sẵn sàng, giữ màn hình chờ rồi nhấn A để thử lại. Đây là thao tác thay danh tính cục bộ; app không thể tự xóa thiết bị cũ khỏi tài khoản trên web.
