# Changelog - Trimui-XiaoZhi

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
