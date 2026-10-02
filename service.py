import json
import logging
import math
import os
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
from array import array
from pathlib import Path


APP = Path(__file__).resolve().parent
DATA = APP / "data"
LOGS = APP / "logs"
CONFIG = DATA / "xiaozhi_config.json"
SETTINGS = DATA / "settings.json"
HISTORY = DATA / "history.json"
DEFAULTS = {
    "language": "vi", "timeout": 30, "auto_after_reply": True,
    "text_size": 24, "theme": "dark", "remote_enabled": False,
    "remote_allow_control": True, "remote_allow_text": True,
    "remote_port": 8788, "capture_device": "auto", "playback_device": "default",
    "intro": True,
}


def save_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def load_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


class XiaozhiService:
    def __init__(self):
        DATA.mkdir(exist_ok=True)
        LOGS.mkdir(exist_ok=True)
        self.settings = dict(DEFAULTS)
        self.settings.update(load_json(SETTINGS, {}))
        self.history = load_json(HISTORY, [])
        if not isinstance(self.history, list):
            self.history = []
        self.events = []
        self.status = "Chờ bắt đầu"
        self.activation_code = ""
        self.awaiting_new_code = False
        self.activated = False
        self.connected = False
        self.active = False
        self.speaking = False
        self.last_activity = time.monotonic()
        self.session_id = ""
        self.core = None
        self.core_log = None
        self.bootstrap_deadline = 0
        self.startup_probe = False
        self.log_offset = 0
        self.partial = ""
        self.last_assistant = ""
        self.remote = None
        self.pin = self._pin()
        self._prepare_config()
        self.awaiting_new_code = (DATA / "identity-unlinked").exists() and not self.activated

    def _pin(self):
        path = DATA / "remote-pin"
        if not path.exists():
            path.write_text(f"{secrets.randbelow(1000000):06d}", encoding="ascii")
        return path.read_text(encoding="ascii").strip()

    def _choose_capture(self):
        selected = self.settings["capture_device"]
        if selected != "auto":
            return selected
        try:
            result = subprocess.run(["arecord", "-l"], capture_output=True, text=True,
                                    timeout=3, check=False)
            match = re.search(r"^card (\d+):.*?device (\d+):", result.stdout, re.MULTILINE)
            if match:
                return f"plughw:{match.group(1)},{match.group(2)}"
        except (OSError, subprocess.TimeoutExpired):
            pass
        logging.warning("arecord found no capture device; using ALSA default")
        return "default"

    def _apply_audio_config(self):
        config = load_json(CONFIG, {})
        if not config:
            return False
        capture = self._choose_capture()
        playback = self.settings["playback_device"]
        if config.get("capture_device") == capture and config.get("playback_device") == playback:
            return False
        config["capture_device"] = capture
        config["playback_device"] = playback
        logging.info("microphone capture device: %s", capture)
        save_json(CONFIG, config)
        return True

    def _prepare_config(self):
        if not CONFIG.exists() and not (DATA / "identity-unlinked").exists():
            root = Path(os.environ.get("SDCARD_PATH", "/mnt/SDCARD")) / "Apps"
            # Cac ten thu muc da tung phat hanh, dung de giu nguyen dinh danh
            # khi nguoi dung cai app moi chung de luu thu muc cu.
            for old_app in ("Trimui-XiaoZhi", "XIAOZHI", "C-XIAOZHI", "TrimuiXiaozhi"):
                old = root / old_app / "data" / "xiaozhi_config.json"
                if old.exists():
                    shutil.copyfile(old, CONFIG)
                    logging.info("Migrated device identity from %s", old)
                    break
        if CONFIG.exists():
            config = load_json(CONFIG, {})
            if config:
                preserved = DATA / "xiaozhi_config.original.json"
                if not preserved.exists():
                    shutil.copyfile(CONFIG, preserved)
                capture = self._choose_capture()
                logging.info("microphone capture device: %s", capture)
                config.update({"capture_device": capture,
                               "playback_device": self.settings["playback_device"],
                               "hello_sample_rate": 16000, "hello_channels": 1,
                               "hello_frame_duration": 20,
                               "gui_local_ip": "127.0.0.1", "gui_remote_ip": "127.0.0.1",
                               "gui_local_port": 5678, "gui_remote_port": 5679,
                               "enable_tts_display": True})
                config["mcp"] = {"enabled": True, "tools": [{
                    "name": "get_system_status",
                    "description": "Get system uptime, available memory and load",
                    "type": "subprocess", "executable": str(APP / "system_status.sh"),
                    "mode": "sync", "timeout_ms": 5000,
                    "input_schema": {"type": "object", "properties": {}}
                }]}
                save_json(CONFIG, config)

    def save_settings(self):
        save_json(SETTINGS, self.settings)
        self._prepare_config()

    def add_message(self, role, text):
        text = text.strip()
        if text:
            self.history.append({"role": role, "text": text})
            self.history = self.history[-150:]
            save_json(HISTORY, self.history)

    def start(self):
        if self.core and self.core.poll() is None:
            return
        self._apply_audio_config()
        executable = APP / "bin/xiaozhi-core"
        if not executable.exists():
            self.status = "Thiếu lõi Xiaozhi"
            return
        self.core_log = open(LOGS / "core.log", "ab", buffering=0)
        self.log_offset = (LOGS / "core.log").stat().st_size
        self.partial = ""
        self.last_assistant = ""
        self.session_id = ""
        self.active = True
        self.connected = False
        self.last_activity = time.monotonic()
        self.status = "Đang kết nối..."
        try:
            self.core = subprocess.Popen([str(executable)], cwd=DATA,
                                         stdout=self.core_log, stderr=subprocess.STDOUT,
                                         start_new_session=True)
        except OSError:
            self.core_log.close()
            self.core_log = None
            self.active = False
            self.status = "Không khởi chạy được lõi; xem logs/app.log"
            logging.exception("Cannot start Xiaozhi core")
            return False
        return True

    def stop(self):
        self.active = False
        self.speaking = False
        if self.core and self.core.poll() is None:
            try:
                self.send({"type": "listen", "state": "stop"})
                self.core.terminate()
                self.core.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                self.core.kill()
                self.core.wait()
        self.core = None
        if self.core_log:
            self.core_log.close()
            self.core_log = None
        self.session_id = ""
        self.connected = False
        self.status = "Chờ bắt đầu"
        self.bootstrap_deadline = 0

    def refresh_activation_code(self):
        if not self.activated and not self.activation_code and (DATA / "identity-unlinked").exists() and (not self.core or self.core.poll() is not None):
            self.start()

    def waiting_for_activation(self):
        return (DATA / "identity-unlinked").exists() and not self.activated

    def send(self, payload):
        if self.session_id:
            payload["session_id"] = self.session_id
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(json.dumps(payload).encode(), ("127.0.0.1", 5678))
            sock.close()
            return True
        except OSError:
            return False

    def listen(self):
        self.startup_probe = False
        if not self.active:
            self.start()
            if self.active:
                self.bootstrap_deadline = time.monotonic() + 12
            return
        if not self.session_id:
            self.bootstrap_deadline = time.monotonic() + 12
            self.status = "Đang kết nối..."
            return
        self.last_activity = time.monotonic()
        self.send({"type": "abort", "reason": "wake_word_detected"})
        self.send({"type": "listen", "state": "start", "mode": "auto"})
        self.status = "Đang nghe..."

    def send_text(self, text):
        text = text.strip()[:1000]
        if not text:
            return False
        if not self.active:
            self.start()
        if not self.session_id:
            deadline = time.monotonic() + 5
            while not self.session_id and self.core and self.core.poll() is None and time.monotonic() < deadline:
                self.poll()
                time.sleep(0.1)
        if not self.session_id:
            return False
        self.send({"type": "abort", "reason": "remote_text"})
        if self.send({"type": "listen", "state": "detect", "text": text}):
            self.add_message("U", text)
            self.last_activity = time.monotonic()
            return True
        return False

    def reactivate(self):
        self.stop()
        self.activation_code = ""
        self.activated = False
        self.start()

    def unlink_device(self):
        if not CONFIG.exists():
            self.status = "Chưa có danh tính thiết bị để gỡ"
            return False
        self.stop()
        backup = DATA / ("xiaozhi_config.pre-unlink-%s.json" % time.strftime("%Y%m%d-%H%M%S"))
        if backup.exists():
            self.status = "Bản sao lưu đã tồn tại; thử lại sau một giây"
            return False
        try:
            CONFIG.replace(backup)
            (DATA / "identity-unlinked").touch()
        except OSError:
            logging.exception("Could not back up identity before unlink")
            if backup.exists() and not CONFIG.exists():
                backup.replace(CONFIG)
            (DATA / "identity-unlinked").unlink(missing_ok=True)
            self.status = "Không sao lưu được danh tính; chưa gỡ liên kết"
            return False
        self.activated = False
        self.activation_code = ""
        self.awaiting_new_code = True
        if not self.start():
            self.status = "Chưa lấy được mã; nhấn A để thử lại"
        else:
            self.status = "Đang lấy mã 6 số mới..."
        logging.info("Local identity rotated; waiting for a new six-digit server activation code")
        return True

    def test_microphone(self):
        self.stop()
        device = self._choose_capture()
        self.status = "Đang đo micro 4 giây; hãy nói to..."
        try:
            with tempfile.TemporaryFile(dir="/tmp") as recording:
                process = subprocess.Popen(
                    ["arecord", "-q", "-D", device, "-t", "raw", "-f", "S16_LE",
                     "-r", "16000", "-c", "2", "-d", "4"],
                    stdout=recording, stderr=subprocess.PIPE,
                )
                try:
                    _, error = process.communicate(timeout=7)
                    timed_out = False
                except subprocess.TimeoutExpired:
                    process.kill()
                    _, error = process.communicate()
                    timed_out = True
                recording.seek(0)
                audio = recording.read()
            if process.returncode and not timed_out and len(audio) < 64000:
                detail = error.decode("utf-8", "replace").strip()[-300:]
                self.status = "Micro không ghi được; xem logs/app.log"
                logging.error("Micro test failed device=%s rc=%s bytes=%s: %s",
                              device, process.returncode, len(audio), detail)
                return
            if len(audio) < 64000:
                self.status = "Micro treo: chỉ thu %s byte; thử thiết bị khác" % len(audio)
                logging.error("Micro test stalled device=%s bytes=%s timeout=%s stderr=%s",
                              device, len(audio), timed_out,
                              error.decode("utf-8", "replace").strip()[-300:])
                return
            if timed_out:
                logging.warning("Micro test has audio but arecord did not exit after -d 4: device=%s bytes=%s",
                                device, len(audio))
            samples = array("h")
            samples.frombytes(audio[:len(audio) & ~3])
            levels = []
            for channel in (0, 1):
                values = samples[channel::2]
                mean_square = sum(sample * sample for sample in values) / len(values)
                levels.append(20 * math.log10(max(1, math.sqrt(mean_square)) / 32768))
            mono_energy = sum(((samples[index] + samples[index + 1]) / 2) ** 2
                              for index in range(0, len(samples), 2)) / (len(samples) // 2)
            mono_level = 20 * math.log10(max(1, math.sqrt(mono_energy)) / 32768)
            logging.info("Micro test device=%s bytes=%s timeout=%s channels=2 rms_dbfs=%.1f,%.1f mono=%.1f",
                         device, len(audio), timed_out, *levels, mono_level)
            strongest = max(levels)
            if strongest < -45:
                self.status = "Micro rất nhỏ / im lặng (%.0f dB); đổi Micro hoặc tăng mic gain" % strongest
            elif strongest - mono_level > 18:
                self.status = "Hai kênh triệt tiêu nhau! Trái %.0f, phải %.0f dB" % tuple(levels)
            else:
                self.status = "Micro: trái %.0f, phải %.0f, trộn %.0f dB" % (*levels, mono_level)
        except (OSError, subprocess.TimeoutExpired):
            logging.exception("Micro test could not run for %s", device)
            self.status = "Không chạy được phép thử micro; xem logs/app.log"

    def _line(self, line):
        match = re.search(r"New Session ID: ([^\s]+)", line)
        if match:
            self.session_id = match.group(1)
        match = re.search(r"Device NOT activated\. Code: (\d{6})\b", line)
        if match:
            self.activation_code = match.group(1)
            self.awaiting_new_code = False
            self.activated = False
            self.status = "Cần kích hoạt"
            logging.info("Six-digit activation code received for new identity")
        if "Device is activated" in line or "WebSocket Connected" in line:
            self.activated = True
            self.connected = "WebSocket Connected" in line or self.connected
            self.activation_code = ""
            self.awaiting_new_code = False
            self.status = "Sẵn sàng nói chuyện"
            (DATA / "identity-unlinked").unlink(missing_ok=True)
        if "WebSocket Disconnected" in line or "Connection error:" in line:
            self.connected = False
            self.status = "Mất kết nối"
        if "Device NOT activated" in line and not self.activation_code:
            self.status = "Đang chờ mã 6 số; xem core.log"
        match = re.search(r"STT Result: (.*)", line)
        if match:
            self.add_message("U", match.group(1))
            self.last_activity = time.monotonic()
        match = re.search(r"TTS: (.*)", line)
        if match and match.group(1).strip():
            if match.group(1) != self.last_assistant:
                self.add_message("A", match.group(1))
                self.last_assistant = match.group(1)
            self.speaking = True
            self.status = "Xiaozhi đang trả lời"
        if "TTS Stopped (state=stop" in line:
            self.speaking = False
            self.last_activity = time.monotonic()
            if not self.settings["auto_after_reply"]:
                self.events.append("reply-ended")
        if "Server closed connection:" in line:
            self.events.append("server-ended")

    def poll(self):
        if self.waiting_for_activation() and CONFIG.exists():
            self._apply_audio_config()
        path = LOGS / "core.log"
        if self.core and path.exists():
            with path.open("rb") as stream:
                stream.seek(self.log_offset)
                block = stream.read(65536)
                self.log_offset = stream.tell()
            if block:
                self.partial += block.decode("utf-8", "replace")
                if len(self.partial) > 131072:
                    self.partial = self.partial[-65536:]
                *lines, self.partial = self.partial.split("\n")
                for line in lines:
                    self._line(line)
        if self.events:
            ended = "server-ended" in self.events
            self.events.clear()
            self.stop()
            self.status = "Phiên đã kết thúc; nhấn A để thử lại" if ended else "Chờ bắt đầu"
        if self.startup_probe and self.connected:
            self.startup_probe = False
            self.stop()
            self.status = "Sẵn sàng trò chuyện"
        if self.core and self.core.poll() is not None:
            self.stop()
            if (DATA / "identity-unlinked").exists() and not self.activation_code:
                self.status = "Chưa lấy được mã; nhấn A để thử lại"
        if self.bootstrap_deadline and self.connected and self.session_id:
            self.bootstrap_deadline = 0
            self.send({"type": "listen", "state": "start", "mode": "auto"})
            self.status = "Đang nghe..."
        if self.bootstrap_deadline and time.monotonic() > self.bootstrap_deadline:
            self.bootstrap_deadline = 0
        timeout = int(self.settings["timeout"])
        if self.active and self.connected and not self.speaking and timeout and time.monotonic() - self.last_activity > timeout:
            self.stop()

    def shutdown(self):
        self.stop()
        if self.remote:
            self.remote.shutdown()
            self.remote.server_close()
