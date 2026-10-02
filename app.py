import ctypes
import logging
import math
import os
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parent
(APP / "logs").mkdir(exist_ok=True)


def _app_version():
    try:
        return (APP / "VERSION").read_text(encoding="utf-8").strip().strip("vV") or "0.1.0"
    except OSError:
        return "0.1.0"


APP_VERSION = _app_version()
sys.path.insert(0, str(APP / "vendor"))
logging.basicConfig(filename=APP / "logs/app.log", level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

from remote import start_remote
from service import XiaozhiService

try:
    import sdl2
    import sdl2.sdlttf as ttf
except Exception:
    logging.exception("SDL import failed")
    raise


BG = (8, 17, 31)
PANEL = (20, 37, 58)
TEXT = (242, 247, 252)
MUTED = (153, 176, 196)
ACCENT = (37, 211, 202)

INTRO_BG = (8, 8, 12)
INTRO_RED = (229, 9, 20)
INTRO_DARK = (60, 5, 8)
INTRO_WHITE = (255, 255, 255)
INTRO_DURATION = 2.2

# Intro ve trong LOGICAL space (khop SDL_RenderSetLogicalSize), khong phai kich
# thuoc man hinh that. Neu ve bang kich thuoc that (1024x768 tren Brick) thi
# chu lech khoi tam va nho hon tren man hinh.
LOGICAL_W, LOGICAL_H = 1280, 720
# Chieu cao chu xong doang ~30% man hinh. Music-Player/chiaki-ng dung
# giant = hero x 3 va hien "dung 3x"; ty le 30% cho logo kieu Netflix.
GIANT_SIZE = int(round(LOGICAL_H * 0.30 / 0.72))  # 0.72 = ty le caps/em cua DejaVu
# He so moi truong so voi Music-Player (giant 132) de rise/overshoot/glow/
# spread giu dung ty le hinh anh khi doi co chu.
INTRO_REF_GIANT = 132.0


class Screen:
    def __init__(self, service):
        self.service = service
        self.window = None
        self.renderer = None
        self.fonts = {}
        self.controllers = []
        self.page = "chat"
        self.setting_index = 0
        self.scroll = 0
        self.running = True
        self.width = 1280
        self.height = 720
        self.options = [
            ("Ngôn ngữ / Language", "language", ["vi", "en"]),
            ("Thời gian chờ", "timeout", [0, 15, 30, 60, 120]),
            ("Tự nghe sau khi trả lời", "auto_after_reply", [False, True]),
            ("Cỡ chữ", "text_size", [20, 24, 30]),
            ("Giao diện", "theme", ["dark", "light"]),
            ("Intro NLK", "intro", [True, False]),
            ("Điều khiển từ xa", "remote_enabled", [False, True]),
            ("Web: điều khiển", "remote_allow_control", [False, True]),
            ("Web: nhập chữ", "remote_allow_text", [False, True]),
            ("Cổng web", "remote_port", [8788, 8789]),
            ("Micro", "capture_device", ["auto", "default", "plughw:0,0", "plughw:1,0"]),
            ("Thử micro (nói 4 giây)", None, []),
            ("Loa", "playback_device", ["default", "plughw:0,0"]),
            ("Kích hoạt lại", "reactivate", []),
            ("Gỡ liên kết / đổi trợ lý", "unlink", []),
        ]
        self.confirm_unlink = False
        self.activation_page = (APP / "data/identity-unlinked").exists()
        self.ota_badge = ""
        self.ota_notice = ""
        self.ota_checked_at = 0.0

    def init(self):
        if sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO | sdl2.SDL_INIT_GAMECONTROLLER | sdl2.SDL_INIT_JOYSTICK) != 0:
            raise RuntimeError(sdl2.SDL_GetError().decode())
        if ttf.TTF_Init() != 0:
            raise RuntimeError("SDL_ttf init failed")
        mode = sdl2.SDL_DisplayMode()
        if sdl2.SDL_GetCurrentDisplayMode(0, mode) == 0:
            self.width, self.height = mode.w, mode.h
        self.window = sdl2.SDL_CreateWindow(b"Trimui-XiaoZhi", 0, 0, self.width, self.height,
                                             sdl2.SDL_WINDOW_SHOWN | sdl2.SDL_WINDOW_FULLSCREEN)
        if not self.window:
            self.window = sdl2.SDL_CreateWindow(b"Trimui-XiaoZhi", 0, 0, self.width, self.height,
                                                 sdl2.SDL_WINDOW_SHOWN)
        if not self.window:
            raise RuntimeError(sdl2.SDL_GetError().decode())
        self.renderer = sdl2.SDL_CreateRenderer(self.window, -1,
            sdl2.SDL_RENDERER_ACCELERATED | sdl2.SDL_RENDERER_PRESENTVSYNC)
        if not self.renderer:
            self.renderer = sdl2.SDL_CreateRenderer(self.window, -1, sdl2.SDL_RENDERER_SOFTWARE)
        if not self.renderer:
            raise RuntimeError(sdl2.SDL_GetError().decode())
        sdl2.SDL_SetRenderDrawBlendMode(self.renderer, sdl2.SDL_BLENDMODE_BLEND)
        sdl2.SDL_RenderSetLogicalSize(self.renderer, 1280, 720)
        font = str(APP / "assets/font.ttf").encode()
        for size in (20, 24, 30, 38, 52):
            self.fonts[size] = ttf.TTF_OpenFont(font, size)
            if not self.fonts[size]:
                raise RuntimeError("Cannot load font")
        # Giant glyphs for the NLK boot logo, pre-rendered once before the
        # intro loop. Non-fatal: intro falls back to plain text without it.
        try:
            giant = ttf.TTF_OpenFont(font, GIANT_SIZE)
        except Exception:
            giant = None
        self.fonts[GIANT_SIZE] = giant or None
        for index in range(sdl2.SDL_NumJoysticks()):
            if sdl2.SDL_IsGameController(index):
                controller = sdl2.SDL_GameControllerOpen(index)
                if controller:
                    self.controllers.append(controller)
        logging.info("SDL ready: %sx%s controllers=%s", self.width, self.height, len(self.controllers))

    def tr(self, vietnamese, english):
        return english if self.service.settings["language"] == "en" else vietnamese

    def rect(self, x, y, width, height, color):
        if self.service.settings["theme"] == "light":
            color = {BG: (231, 240, 246), PANEL: (249, 252, 255),
                     (33, 69, 91): (194, 223, 231)}.get(color, color)
        sdl2.SDL_SetRenderDrawColor(self.renderer, *color, 255)
        rectangle = sdl2.SDL_Rect(x, y, width, height)
        sdl2.SDL_RenderFillRect(self.renderer, rectangle)

    def text(self, value, x, y, size=24, color=TEXT, max_width=1140):
        if self.service.settings["theme"] == "light":
            color = {TEXT: (18, 37, 54), MUTED: (68, 91, 111),
                     ACCENT: (4, 113, 117)}.get(color, color)
        font = self.fonts[size]
        value = str(value).replace("\n", " ")
        while value:
            segment = value
            width = ctypes.c_int()
            while len(segment) > 1:
                ttf.TTF_SizeUTF8(font, segment.encode(), ctypes.byref(width), None)
                if width.value <= max_width:
                    break
                segment = segment[:-1]
            if len(segment) < len(value):
                cut = segment.rfind(" ")
                if cut > 0:
                    segment = segment[:cut]
            surface = ttf.TTF_RenderUTF8_Blended(font, segment.encode(), sdl2.SDL_Color(*color, 255))
            if surface:
                texture = sdl2.SDL_CreateTextureFromSurface(self.renderer, surface)
                if texture:
                    destination = sdl2.SDL_Rect(x, y, surface.contents.w, surface.contents.h)
                    sdl2.SDL_RenderCopy(self.renderer, texture, None, destination)
                    sdl2.SDL_DestroyTexture(texture)
                sdl2.SDL_FreeSurface(surface)
            value = value[len(segment):].lstrip()
            y += size + 10
            if y > 674:
                break
        return y

    def play_intro(self, duration=INTRO_DURATION):
        try:
            enabled = bool(self.service.settings.get("intro", True))
        except Exception:
            enabled = True
        if not enabled:
            return
        glyphs = self._build_intro_glyphs()
        try:
            start = time.monotonic()
            event = sdl2.SDL_Event()
            while True:
                elapsed = time.monotonic() - start
                if elapsed >= duration:
                    break
                while sdl2.SDL_PollEvent(ctypes.byref(event)):
                    if event.type == sdl2.SDL_QUIT:
                        self.running = False
                        return
                    if event.type in (sdl2.SDL_KEYDOWN,
                                      sdl2.SDL_CONTROLLERBUTTONDOWN,
                                      sdl2.SDL_JOYBUTTONDOWN,
                                      sdl2.SDL_JOYHATMOTION):
                        return
                self._render_intro_frame(min(1.0, elapsed / duration), glyphs)
                sdl2.SDL_Delay(16)
        finally:
            self._free_intro_glyphs(glyphs)

    def _intro_glyph(self, letter, color):
        font = self.fonts.get(GIANT_SIZE)
        if not font:
            return (None, 0, 0)
        try:
            surface = ttf.TTF_RenderUTF8_Blended(font, letter.encode("utf-8"),
                                                 sdl2.SDL_Color(*color, 255))
        except Exception:
            return (None, 0, 0)
        if not surface:
            return (None, 0, 0)
        texture = sdl2.SDL_CreateTextureFromSurface(self.renderer, surface)
        try:
            width, height = surface.contents.w, surface.contents.h
        except Exception:
            width, height = (0, 0)
        try:
            sdl2.SDL_FreeSurface(surface)
        except Exception:
            pass
        if not texture:
            return (None, 0, 0)
        return (texture, width, height)

    def _build_intro_glyphs(self):
        cache = {}
        colors = {"dark": INTRO_DARK + (255,), "bright": INTRO_RED + (255,),
                  "white": INTRO_WHITE + (255,)}
        for letter in "NLK":
            for name, color in colors.items():
                try:
                    texture, width, height = self._intro_glyph(letter, color)
                except Exception:
                    texture, width, height = (None, 0, 0)
                if texture:
                    cache[(letter, name)] = (texture, width, height)
        return cache

    def _free_intro_glyphs(self, glyphs):
        for texture, _width, _height in (glyphs or {}).values():
            try:
                if texture:
                    sdl2.SDL_DestroyTexture(texture)
            except Exception:
                pass

    def _intro_blit(self, texture, x, y, width, height):
        if not texture or width <= 0 or height <= 0:
            return False
        try:
            destination = sdl2.SDL_Rect(int(x), int(y), int(width), int(height))
            sdl2.SDL_RenderCopy(self.renderer, texture, None, destination)
            return True
        except Exception:
            return False

    def _intro_scale(self):
        return GIANT_SIZE / INTRO_REF_GIANT

    def _intro_spread(self, progress):
        ease = min(1.0, max(0.0, progress / 0.55))
        return (4 + (30 - 4) * (1 - (1 - ease) * (1 - ease))) * self._intro_scale()

    def _render_intro_frame(self, progress, glyphs=None):
        progress = max(0.0, min(1.0, float(progress)))
        sdl2.SDL_SetRenderDrawColor(self.renderer, *INTRO_BG, 255)
        sdl2.SDL_RenderClear(self.renderer)
        if glyphs:
            self._render_intro_glyphs(progress, glyphs)
        else:
            step = 90 * self._intro_scale()
            cursor = LOGICAL_W // 2 - step
            for index, letter in enumerate("NLK"):
                enter_at = 0.05 + index * 0.16
                local = (progress - enter_at) / 0.30
                if local > 0.0:
                    local = min(1.0, local)
                    rise = int((1.0 - local) * 90 * self._intro_scale())
                    self.text(letter, cursor, LOGICAL_H // 2 - 30 + rise, 52, INTRO_RED)
                cursor += step
        sdl2.SDL_RenderPresent(self.renderer)

    def _render_intro_glyphs(self, progress, glyphs):
        center_y = LOGICAL_H // 2
        k = self._intro_scale()
        spacing = self._intro_spread(progress)
        try:
            widths = [glyphs[(letter, "bright")][1] for letter in "NLK"]
        except (KeyError, TypeError):
            widths = [int(100 * k)] * 3
        total = sum(widths) + spacing * 2
        fit = min(1.0, (LOGICAL_W - 80) / total) if total > 0 else 1.0
        cursor = (LOGICAL_W - total * fit) // 2
        for index, letter in enumerate("NLK"):
            width = widths[index]
            try:
                _texture, tex_w, tex_h = glyphs[(letter, "bright")]
            except (KeyError, TypeError):
                cursor += (width + spacing) * fit
                continue
            if tex_w <= 0 or tex_h <= 0:
                cursor += (width + spacing) * fit
                continue
            dest_w, dest_h = tex_w * fit, tex_h * fit
            x = cursor + (width * fit - dest_w) // 2
            enter_at = 0.05 + index * 0.16
            local = (progress - enter_at) / 0.30
            if local > 0.0:
                local = min(1.0, local)
                rise = int((1.0 - local) * 90 * k)
                if local > 0.65:
                    rise += int(-14 * k * math.sin((local - 0.65) / 0.35 * math.pi))
                y = center_y - dest_h // 2 + rise
                if local * 1.5 >= 0.75:
                    try:
                        glow, _gw, _gh = glyphs[(letter, "dark")]
                        self._intro_blit(glow, x + 4 * fit * k, y + 6 * fit * k,
                                         dest_w, dest_h)
                    except (KeyError, TypeError):
                        pass
                    key = "bright"
                else:
                    key = "dark"
                try:
                    texture, _tw, _th = glyphs[(letter, key)]
                except (KeyError, TypeError):
                    texture = None
                self._intro_blit(texture, x, y, dest_w, dest_h)
            cursor += (width + spacing) * fit
        if progress > 0.72:
            sweep = (progress - 0.72) / 0.28
            cursor = (LOGICAL_W - total * fit) // 2
            for index, letter in enumerate("NLK"):
                width = widths[index]
                try:
                    texture, tex_w, tex_h = glyphs[(letter, "white")]
                except (KeyError, TypeError):
                    cursor += (width + spacing) * fit
                    continue
                center = index / 2.0
                if abs(sweep - center * 0.9) < 0.18:
                    self._intro_blit(texture, cursor + (width * fit - tex_w * fit) // 2,
                                     center_y - tex_h * fit // 2, tex_w * fit, tex_h * fit)
                cursor += (width + spacing) * fit

    def draw(self):
        self.rect(0, 0, 1280, 720, BG)
        self.text("Trimui-XiaoZhi v%s" % APP_VERSION, 42, 28, 38, ACCENT)
        self.text(self.service.status, 830, 40, 24, MUTED, 420)
        # OTA: doc .ota-status 1 lan/giay (khong doc file o moi khung ve).
        now = time.monotonic()
        if now - self.ota_checked_at >= 1.0:
            self.ota_checked_at = now
            self.poll_ota()
        if self.ota_badge:
            self.text(self.ota_badge, 830, 74, 20, MUTED, 420)
        self.rect(34, 92, 1212, 565, PANEL)
        if self.page == "chat":
            if self.service.activation_code and not self.service.activated:
                self.text("KÍCH HOẠT THIẾT BỊ", 72, 124, 30, ACCENT)
                self.text("Trợ lý → Thêm thiết bị → nhập mã xác minh 6 số", 72, 190, 24)
                self.text(self.service.activation_code, 72, 270, 52)
            elif self.service.awaiting_new_code or (self.activation_page and not self.service.activated):
                self.text("ĐANG TẠO DANH TÍNH MỚI", 72, 124, 30, ACCENT)
                self.text("Đang chờ máy chủ cấp mã xác minh 6 số...", 72, 208, 24)
                self.text("Nếu không có mã, kiểm tra Wi-Fi rồi nhấn A để thử lại.", 72, 267, 24)
            else:
                end = len(self.service.history) - self.scroll
                visible = self.service.history[max(0, end - 11):end]
                y = 118
                for entry in visible:
                    role = self.tr("BẠN", "YOU") if entry.get("role") == "U" else "XIAOZHI"
                    y = self.text(role + "  " + entry.get("text", ""), 66, y,
                                  self.service.settings["text_size"],
                                  ACCENT if role == "BẠN" else TEXT, 1110) + 11
                    if y > 620:
                        break
                if not visible:
                    self.text(self.tr("Sẵn sàng trò chuyện", "Ready to talk"), 128, 238, 52)
                    self.text(self.tr("Nhấn A để nói với Xiaozhi", "Press A to speak"), 134, 325, 30, MUTED)
            self.text(self.tr("A  Nói / nghe lại     B  Dừng / thoát     SELECT  Cài đặt     ↑↓  Cuộn",
                              "A  Talk / retry     B  Stop / exit     SELECT  Settings     ↑↓  Scroll"), 45, 673, 20, MUTED)
        else:
            first = max(0, min(self.setting_index - 8, len(self.options) - 10))
            for index in range(first, min(first + 10, len(self.options))):
                label, key, _ = self.options[index]
                y = 112 + (index - first) * 48
                if index == self.setting_index:
                    self.rect(50, y - 4, 1160, 44, (33, 69, 91))
                value = self.service.settings.get(key, "") if key and key not in ("reactivate", "unlink") else "Nhấn A"
                self.text(label, 70, y, 24)
                self.text(str(value), 760, y, 24, ACCENT, 420)
            self.text("Web PIN: " + self.service.pin + "     A  Đổi / chọn     B  Quay lại", 45, 673, 20, MUTED)
            if self.confirm_unlink:
                self.rect(100, 218, 1080, 290, BG)
                self.text("TẠO DANH TÍNH THIẾT BỊ MỚI?", 132, 248, 30, ACCENT)
                self.text("Gỡ thiết bị cũ trên xiaozhi.me/console trước.", 132, 306, 24)
                self.text("A: Xác nhận    B: Hủy", 132, 396, 24)
        if self.ota_notice:
            # Ve sau cung de thong bao OTA khong bi noi dung chat cat chu.
            self.rect(34, 612, 1212, 58, PANEL)
            self.text(self.ota_notice, 64, 628, 24, ACCENT, 1150)
        sdl2.SDL_RenderPresent(self.renderer)

    def action(self, action):
        if action == "quit":
            self.running = False
        elif self.confirm_unlink:
            if action == "back":
                self.confirm_unlink = False
            elif action == "a":
                self.confirm_unlink = False
                if self.service.unlink_device():
                    self.page = "chat"
                    self.activation_page = True
        elif self.page == "settings":
            if action == "back":
                self.page = "chat"
            elif action in ("up", "down"):
                self.setting_index = (self.setting_index + (1 if action == "down" else -1)) % len(self.options)
            elif action in ("a", "left", "right"):
                _, key, choices = self.options[self.setting_index]
                if key is None:
                    if action == "a":
                        self.service.test_microphone()
                elif key == "reactivate":
                    if action == "a":
                        self.service.reactivate()
                        self.page = "chat"
                elif key == "unlink":
                    if action == "a":
                        self.confirm_unlink = True
                else:
                    old = self.service.settings[key]
                    position = choices.index(old) if old in choices else 0
                    self.service.settings[key] = choices[(position + (-1 if action == "left" else 1)) % len(choices)]
                    self.service.save_settings()
                    start_remote(self.service)
        elif action == "back":
            if self.service.active:
                self.service.stop()
            else:
                self.running = False
        elif action == "settings":
            self.page = "settings"
        elif action == "a":
            if self.activation_page and not self.service.activated:
                self.service.refresh_activation_code()
            else:
                self.service.listen()
        elif action == "up":
            self.scroll = min(self.scroll + 1, max(0, len(self.service.history) - 1))
        elif action == "down":
            self.scroll = max(self.scroll - 1, 0)

    def events(self):
        event = sdl2.SDL_Event()
        while sdl2.SDL_PollEvent(ctypes.byref(event)):
            if event.type == sdl2.SDL_QUIT:
                self.action("quit")
            elif event.type == sdl2.SDL_KEYDOWN and not event.key.repeat:
                keys = {sdl2.SDLK_RETURN: "a", sdl2.SDLK_ESCAPE: "back",
                        sdl2.SDLK_F1: "settings", sdl2.SDLK_UP: "up",
                        sdl2.SDLK_DOWN: "down", sdl2.SDLK_LEFT: "left", sdl2.SDLK_RIGHT: "right"}
                self.action(keys.get(event.key.keysym.sym, ""))
            elif event.type == sdl2.SDL_CONTROLLERBUTTONDOWN:
                buttons = {0: "back", 1: "a", 4: "back", 6: "settings",
                           11: "up", 12: "down", 13: "left", 14: "right"}
                self.action(buttons.get(event.cbutton.button, ""))
            elif event.type == sdl2.SDL_JOYBUTTONDOWN and not self.controllers:
                buttons = {0: "back", 1: "a", 4: "settings", 8: "settings"}
                self.action(buttons.get(event.jbutton.button, ""))
            elif event.type == sdl2.SDL_JOYHATMOTION and not self.controllers:
                hats = {1: "up", 4: "down", 8: "left", 2: "right"}
                self.action(hats.get(event.jhat.value, ""))

    def poll_ota(self):
        """Doc .ota-status (ota-update.sh chay nen tu launch.sh).

        Tra ve ("badge", text) hoac ("done", version). Badge "Dang kiem tra..."
        phai bien mat khi file bi xoa - launch.sh xoa .ota-status truoc khi chay
        OTA nen lan app mo dau tien thuong khong co gi de hien.
        """
        path = APP / ".ota-status"
        try:
            raw = path.read_text(encoding="utf-8").strip()
        except OSError:
            self.ota_badge = ""
            return
        self.ota_badge = ""
        if not raw:
            return
        if raw.startswith("done "):
            version = raw[5:].strip()
            try:
                path.unlink()
            except OSError:
                pass
            # Version dang chay < version vua cai -> that su can mo lai app.
            if version and version != APP_VERSION:
                self.ota_notice = "ĐÃ CẬP NHẬT LÊN v%s - MỞ LẠI APP ĐỂ DÙNG" % version
        elif raw.startswith("downloading "):
            self.ota_badge = "Đang tải %s..." % raw[12:].strip()
        elif raw == "checking":
            self.ota_badge = "Đang kiểm tra..."
        else:
            try:
                path.unlink()
            except OSError:
                pass
            self.ota_notice = ""

    def close(self):
        for controller in self.controllers:
            sdl2.SDL_GameControllerClose(controller)
        for font in self.fonts.values():
            if font:
                ttf.TTF_CloseFont(font)
        if self.renderer:
            sdl2.SDL_DestroyRenderer(self.renderer)
        if self.window:
            sdl2.SDL_DestroyWindow(self.window)
        ttf.TTF_Quit()
        sdl2.SDL_Quit()


def main():
    service = XiaozhiService()
    screen = Screen(service)
    try:
        screen.init()
        screen.play_intro()
        start_remote(service)
        screen.draw()
        service.startup_probe = True
        service.start()
        last = 0
        while screen.running:
            screen.events()
            service.poll()
            if time.monotonic() - last > 0.15:
                screen.draw()
                last = time.monotonic()
            sdl2.SDL_Delay(20)
    finally:
        service.shutdown()
        screen.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("App failed")
        raise
