# Changelog - Trimui-XiaoZhi

## v0.2.0 - 2026-10-02

- **Viết lại toàn bộ giao diện và menu** (module mới `ui.py`), cả chế độ **Tối** lẫn **Sáng**.

### Sửa lỗi bố cục

- Bỏ `SDL_RenderSetLogicalSize`: trên màn hình 1024×768 nó ép nội dung 1280×720 vào giữa, tạo **hai dải đen lớn** và làm mọi thứ lệch. Nay mọi thứ vẽ bằng **pixel thật**, tự co theo kích thước màn hình (đã kiểm ở 1024×768, 1280×720, 1024×600, 800×480).
- Chữ trước đây nằm trên nền phẳng và lệch lền; nay có header, thẻ bo tròn, footer dạng pill rõ ràng.

### Giao diện mới

- **Chat dạng bong bóng**: tin của bạn căn phải, tin trợ lý căn trái kèm avatar sóng nhỏ; tin mới nhất trượt lên + mờ dần.
- **Header**: tên app + chip phiên bản + pill trạng thái có chấm sáng/đồng sóng chuyển động khi đang nói.
- **Footer**: gợi ý phím dạng pill, đổi theo trang.
- **Cài đặt**: nhóm theo mục (Giao diện / Âm thanh / Điều khiển từ xa / Bảo trì), hàng được chọn có thanh accent, giá trị trong pill, mũi tên ← →.
- **Trang kích hoạt**: mã 6 số đóng khung ô vuông dễ đọc.
- **Hộp thoại xác nhận** gỡ liên kết: có nền làm mờ, hai nút bám đúng bề rộng chữ.
- **Thông báo OTA** trượt từ trên xuống.

### Hiệu năng

- `text()` trước gọi `TTF_RenderUTF8_Blended` **mỗi khung vẽ** — giờ mỗi chuỗi chỉ render **một lần** rồi dùng texture có cache (giới hạn 320 mục, tự xoá cache khi đổi theme). Nhờ vậy mới chạy được hiệu ứng chuyển động.
- Vòng lặp chỉ vẽ lại khi có thay đổi hoặc đang có animation; khi màn hình đứng yên không vẽ lại liên tục.

### Kiểm thử

- `tests/test_ui.py` — 12 test: cả hai theme vẽ được, **không có hình nào tràn ra ngoài màn hình**, chuỗi không render lại mỗi khung, mọi mục cài đặt thuộc nhóm và vẽ được, hộp thoại/toast/2 trang kích hoạt vẽ được.
- `tools/preview_ui.py` — render giao diện ra PNG bằng PIL để xem trước khi nạp lên máy (`python3 tools/preview_ui.py`).

## v0.1.4 - 2026-10-02

- **Sửa lỗi gốc khiến logo luôn bị nhỏ** (v0.1.0 → 0.1.3): màu glyph đã có sẵn alpha nhưng code lại truyền thêm `255` vào `SDL_Color` → `TypeError` bị nuốt im lặng, **0/9 texture được tạo**, app rơi về nhánh dự phòng vẽ chữ nhỏ. Đã sửa và log rõ `intro glyphs cached=9/9`.
- `_intro_glyph` giờ bỏ ngoại lệ ra log thay vì im lặng, kèm cảnh báo khi không render được glyph.
- Test mới: `SDL_Color` trong stub test **bắt buộc đúng 4 tham số** (stub cũ nhận vô hạn nên không bắt được lỗi này) + test kiểm màu intro đủ 4 kênh.

## v0.1.3 - 2026-10-02

- **Sửa crash khi mở app** (bản 0.1.2): nhánh vẽ chữ dự phòng truyền số thực vào `SDL_Rect`; `pysdl2` chỉ nhận `int`. Đã ép kiểu int mọi tọa độ.
- Nhánh dự phòng còn xảy ra vì `TTF_OpenFont(font, 300)` bị SDL_ttf trên máy từ chối → app rơi về chữ nhỏ. Giờ thử dần các cỡ chữ (giant → nhỏ dần) và ghi cỡ dùng được vào `logs/app.log`.
- Logo về **đúng thuật toán Music-Player**: `giant = 132 × max(0.75, min(w/1024, h/768))`, `fit = min(1, (w-80)/total)`, hằng số gốc (rise 90, overshoot −14, quầng +4/+6, giãn chữ 4→30, quét tráng 0.72→1.00), 2.2 giây, bấm phím bỏ qua. Trên máy 1024×768 cho `k = 1.0` → hình y hệt Music-Player.
- Test mới: tọa độ dự phòng phải là `int`; công thức `giant`; giá trị `spread`; `fit` không bao giờ phóng to.

## v0.1.2 - 2026-10-02

- Sửa logo NLK "bé và lệch": intro vẽ trong **logical space 1280x720** (đúng `SDL_RenderSetLogicalSize`) thay vì dùng kích thước màn hình thật (1024x768 trên Brick) — sai lệch này làm chữ lệch tâm và co lại.
- Chữ to lên gấp ~2 lần: `giant = 30% chiều cao màn hình` (300px thay vì 156px), logo chiếm 57% bề ngang thay vì 24%.
- Rise / overshoot / quầng đỏ / giãn chữ nhân thêm hệ số `giant/132` nên hiệu ứng giữ **đúng tỉ lệ hình ảnh** như Music-Player và chiaki-ng.
- `tests/test_intro.py`: thêm 2 test chốt tâm logo theo logical space và tỉ lệ chữ (chặn tái phát lỗi lệch/bé).

## v0.1.1 - 2026-10-02

- OTA tự động: `ota-update.sh` (shell thuần, không cần python3) chạy nền từ `launch.sh`, tự kiểm `manifest.json` trên GitHub, tải file lệch SHA-256, staging rồi apply. App mở ngay, không phải chờ.
  - Bật/tắt: `XIAOZHI_NO_OTA=1` để tắt. Mặc định bật.
  - App hiện badge "Đang kiểm tra..." / "Đang tải vX..." và bảng "ĐÃ CẬP NHẬT LÊN vX - MỞ LẠI APP ĐỂ DÙNG" khi xong (đọc `.ota-status` 1 lần/giây).
  - **Không bao giờ ghi đè `data/`** (danh tính + kích hoạt thiết bị) và `logs/`; cả trong đường tải bằng python3 lẫn đường tải bằng shell thuần.
  - Offline / lỗi mạng → bỏ qua êm, không chặn boot, log ở `logs/ota.log`.
  - Bundle `certs/cacert.pem` để kiểm chứng TLS.
- `tests/test_ota.py`: 10 test (contract script, bảo vệ `data/`, `.ota-status` atomic, OTA offline fail mềm) + E2E thật với repo đã publish.

## v0.1.0 - 2026-10-02

- Phien ban dau tien: tro ly giong noi Xiaozhi cho TrimUI (Python + SDL2).
- Doi ten hien thi tren may thanh **Trimui-XiaoZhi** (truoc day "Trimui Xiaozhi");
  thu muc cai dat `Apps/Trimui-XiaoZhi`, launch.sh van chay duoc voi ten thu muc cu.
- Logo khoi dong NLK kieu Netflix (2.2 giay, bam phim bat ky de bo qua,
  tat duoc trong Cai dat -> Intro NLK).
- Cai dat: giai nen ZIP vao goc the nho de co `Apps/TrimuiXiaozhi/launch.sh`.
