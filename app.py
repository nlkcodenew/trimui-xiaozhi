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

from ui import Anim, Canvas, THEMES, ease_in_out, ease_out_cubic, mix


INTRO_BG = (8, 8, 12)
INTRO_RED = (229, 9, 20)
INTRO_DARK = (60, 5, 8)
INTRO_WHITE = (255, 255, 255)
INTRO_DURATION = 2.2

# Intro ve bang PIXEL THAT cua man hinh (self.width/self.height), khong dung
# hang so 1280x720: tren Brick Pro 1024x768 hang so do lam chu lech sang phai
# (vi 1280 > 1024). Terminal (native) cung canh theo man hinh that nen chay
# duoc tren ca 4:3 va 16:9 - app nay lam y het.
LOGICAL_W, LOGICAL_H = 1280, 720  # giu de code doc lai duoc; KHONG dung de canh
# Dung nguyen khuon Music-Player: giant = 132 * max(0.75, min(w/1024, h/768)),
# fit = min(1, (w-80)/total). Tren man hinh chuan 1024x768 -> scale = 1.0 ->
# giant 132 va k = 1.0, tuc hinh anh y het Music-Player.
INTRO_REF_GIANT = 132.0

# Co chu UI. Chat dung dung 3 co chu trong setting (20/24/30) vao mot khoang
# nho gian de "Cỡ chữ" doi duoc that su.
UI_TINY = 15
UI_SMALL = 17
UI_BODY = 21
UI_MED = 25
UI_LG = 29
UI_TITLE = 38
CHAT_SIZES = (20, 24, 30)
GROUP = (
    ("GIAO DIỆN", ["language", "theme", "text_size", "intro"]),
    ("ÂM THANH", ["timeout", "auto_after_reply", "capture_device", "playback_device"]),
    ("ĐIỀU KHIỂN TỪ XA", ["remote_enabled", "remote_allow_control",
                            "remote_allow_text", "remote_port"]),
    ("BẢO TRÌ", ["reactivate", "unlink"]),
)
ACTION_KEYS = (None, "reactivate", "unlink")


class Screen:
    def __init__(self, service):
        self.service = service
        self.window = None
        self.renderer = None
        self.fonts = {}
        self.canvas = None
        self.controllers = []
        self.page = "chat"
        self.setting_index = 0
        self.scroll = 0
        self.running = True
        self.width = 1024
        self.height = 768
        self.options = [
            ("Ngôn ngữ / Language", "language", ["vi", "en"]),
            ("Giao diện", "theme", ["dark", "light"]),
            ("Cỡ chữ", "text_size", list(CHAT_SIZES)),
            ("Intro NLK", "intro", [True, False]),
            ("Thời gian chờ", "timeout", [0, 15, 30, 60, 120]),
            ("Tự nghe sau khi trả lời", "auto_after_reply", [False, True]),
            ("Micro", "capture_device", ["auto", "default", "plughw:0,0", "plughw:1,0"]),
            ("Loa", "playback_device", ["default", "plughw:0,0"]),
            ("Điều khiển từ xa", "remote_enabled", [False, True]),
            ("Web: điều khiển", "remote_allow_control", [False, True]),
            ("Web: nhập chữ", "remote_allow_text", [False, True]),
            ("Cổng web", "remote_port", [8788, 8789]),
            ("Thử micro (nói 4 giây)", None, []),
            ("Kích hoạt lại", "reactivate", []),
            ("Gỡ liên kết / đổi trợ lý", "unlink", []),
        ]
        self.confirm_unlink = False
        self.activation_page = (APP / "data/identity-unlinked").exists()
        self.ota_badge = ""
        self.ota_notice = ""
        self.ota_checked_at = 0.0
        # Chuyen dong UI
        self.page_anim = Anim(0.0, 0.24)
        self.select_anim = Anim(0.0, 0.16)
        self.toast_anim = Anim(0.0, 0.30)
        self._page_from = "chat"
        self._wave_phase = 0.0
        self._last_frame = 0.0
        self._dirty = True
        self._seen_history = 0
        self._last_status = ""

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
        # KHONG dung SDL_RenderSetLogicalSize: tren man hinh 1024x768 no se
        # lam noi dung bi letterbox (hai dai den lon), day la ly do giao dien
        # truoc nhin lech va chat. Moi thu ve bang pixel that.
        font = str(APP / "assets/font.ttf").encode()
        self.canvas = Canvas(self.renderer, self.fonts,
                             self.service.settings.get("theme", "dark"))
        self.canvas.resize(self.width, self.height)
        wanted = sorted({int(UI_TINY * self.canvas.scale),
                         int(UI_SMALL * self.canvas.scale),
                         int(UI_BODY * self.canvas.scale),
                         int(UI_MED * self.canvas.scale),
                         int(UI_LG * self.canvas.scale),
                         int(UI_TITLE * self.canvas.scale)} |
                        {int(size * self.canvas.scale) for size in CHAT_SIZES})
        for size in wanted:
            self.fonts[size] = ttf.TTF_OpenFont(font, size)
            if not self.fonts[size]:
                raise RuntimeError("Cannot load font %d" % size)
        # Giant glyphs for the NLK boot logo, pre-rendered once before the
        # intro loop. Non-fatal: intro falls back to plain text without it.
        #
        # Khuon y het Music-Player: giant = 132 * max(0.75, min(w/1024, h/768))
        # tinh tren KICH THUOC MAN HINH THAT, sau do ve trong logical space.
        # Neu SDL_ttf tu choi co chu do, thu nho dan theo thu tu.
        scale = max(0.75, min(self.width / 1024.0, self.height / 768.0))
        self.intro_giant = max(24, int(round(INTRO_REF_GIANT * scale)))
        self.intro_font = None
        self.intro_font_size = 0
        candidates = [self.intro_giant]
        for smaller in (self.intro_giant - 8, 132, 120, 100):
            if 0 < smaller < self.intro_giant and smaller not in candidates:
                candidates.append(smaller)
        for candidate in candidates:
            try:
                probe = ttf.TTF_OpenFont(font, candidate)
            except Exception:
                probe = None
            if probe:
                self.intro_font = probe
                self.intro_font_size = candidate
                break
        logging.info("intro giant font: size=%s (wanted %s, scale=%.3f)",
                     self.intro_font_size or "none", self.intro_giant, scale)
        for index in range(sdl2.SDL_NumJoysticks()):
            if sdl2.SDL_IsGameController(index):
                controller = sdl2.SDL_GameControllerOpen(index)
                if controller:
                    self.controllers.append(controller)
        logging.info("SDL ready: %sx%s controllers=%s", self.width, self.height, len(self.controllers))

    def tr(self, vietnamese, english):
        return english if self.service.settings["language"] == "en" else vietnamese

    # ---- wrapper giu API cu (intro + test cu nua) ----------------------
    def rect(self, x, y, width, height, color):
        if self.canvas:
            self.canvas.fill(int(x), int(y), int(width), int(height), color)

    def text(self, value, x, y, size=24, color=None, max_width=0):
        """API cu: ve chu, xuong dong neu vuot max_width. Giu cho intro/test."""
        if not self.canvas:
            return y
        if color is None:
            color = self.canvas.color("text")
        color = tuple(color) + (255,) if len(color) == 3 else tuple(color)
        if max_width <= 0:
            self.canvas.text(value, int(x), int(y), size, color[:3])
            return y
        step = int(size * 1.34)
        for line in self.canvas.wrap(value, size, max_width):
            self.canvas.text(line, int(x), int(y), size, color[:3])
            y += step
        return y

    # ---- khoang cach / bo cuc -----------------------------------------
    def _font(self, base):
        return max(8, int(base * self.canvas.scale))

    def _layout(self):
        """Cac moc ngang/dung canh theo man hinh that."""
        pad = self.canvas.px(30)
        header = self.canvas.px(96)
        footer = self.canvas.px(64)
        card_x = pad
        card_w = self.width - pad * 2
        return {
            "pad": pad,
            "header": header,
            "footer": footer,
            "content_y": header + self.canvas.px(8),
            "content_h": self.height - header - footer - self.canvas.px(8),
            "card_x": card_x,
            "card_w": card_w,
            "radius": self.canvas.px(20),
        }

    def _status_color(self):
        if self.service.speaking:
            return "accent_2"
        if self.service.active:
            return "accent"
        return "faint"

    def _goto_page(self, page):
        if page == self.page:
            return
        self._page_from = self.page
        self.page = page
        self.page_anim.jump(0.0)
        self.page_anim.set(1.0)
        self._dirty = True

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
        font = getattr(self, "intro_font", None)
        if not font:
            return (None, 0, 0)
        # color phai la (r, g, b) - alpha them o day. SDL_Color co dung 4 truong,
        # truyen 5 gia tri se nem TypeError va intro im lang ruc chu.
        if len(color) == 4:
            rgba = color
        else:
            rgba = tuple(color) + (255,)
        try:
            surface = ttf.TTF_RenderUTF8_Blended(font, letter.encode("utf-8"),
                                                 sdl2.SDL_Color(*rgba))
        except Exception:
            logging.exception("intro glyph %s failed", letter)
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

    @staticmethod
    def _intro_colors():
        """Mau glyph intro, dung y Music-Player: samm / tuoi Netflix / trang."""
        return {"dark": INTRO_DARK + (255,),
                "bright": INTRO_RED + (255,),
                "white": INTRO_WHITE + (255,)}

    def _build_intro_glyphs(self):
        cache = {}
        colors = self._intro_colors()
        for letter in "NLK":
            for name, color in colors.items():
                try:
                    texture, width, height = self._intro_glyph(letter, color)
                except Exception:
                    texture, width, height = (None, 0, 0)
                if texture:
                    cache[(letter, name)] = (texture, width, height)
        logging.info("intro glyphs cached=%d/%d font_size=%s",
                     len(cache), 9, getattr(self, "intro_font_size", 0))
        if not cache:
            logging.error("intro: khong render duoc glyph NLK - logo se ve bang "
                          "du phong (chu nho)")
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
        # k = giant / 132. Tren man hinh chuan 1024x768 k = 1.0 tuc hinh anh
        # y het Music-Player; man hinh nho hon thi moi hieu ung co lai theo
        # dung ty le hinh anh.
        size = getattr(self, "intro_font_size", 0) or INTRO_REF_GIANT
        return size / INTRO_REF_GIANT

    def _intro_fit(self, widths, total):
        """Dung y Music-Player: fit = min(1, (w-80)/total).

        Chi CO xuong cho man hinh nho, khong phong to len (giong ban goc).
        """
        if total <= 0:
            return 1.0
        return max(0.05, min(1.0, (self.width - 80) / float(total)))

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
            # Fallback khi khong mo duoc font giant: ve bang text thuong.
            # Moi toa do phai la int - SDL_Rect (pysdl2) khong nhan float.
            k = self._intro_scale()
            step = int(90 * k)
            cursor = self.width // 2 - step
            for index, letter in enumerate("NLK"):
                enter_at = 0.05 + index * 0.16
                local = (progress - enter_at) / 0.30
                if local > 0.0:
                    local = min(1.0, local)
                    rise = int((1.0 - local) * 90 * k)
                    self.text(letter, int(cursor), int(self.height // 2 - 30) + rise,
                              52, INTRO_RED)
                cursor += step
        sdl2.SDL_RenderPresent(self.renderer)

    def _render_intro_glyphs(self, progress, glyphs):
        center_y = self.height // 2
        k = self._intro_scale()
        spacing = self._intro_spread(progress)
        try:
            widths = [glyphs[(letter, "bright")][1] for letter in "NLK"]
        except (KeyError, TypeError):
            # Ty le chu cua DejaVu o co chu 132 (do bang PIL).
            widths = [int(99 * k), int(74 * k), int(90 * k)]
        total = sum(widths) + spacing * 2
        fit = self._intro_fit(widths, total)
        cursor = (self.width - total * fit) // 2
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
                        # Music-Player: quang lech +4/+6 (nhan theo fit).
                        self._intro_blit(glow, x + 4 * fit, y + 6 * fit,
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
            cursor = (self.width - total * fit) // 2
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

# ==================================================================
    # GIAO DIEN
    # ==================================================================
    def draw(self):
        """Ve khung hien tai. Khong co side effect ngoai man hinh."""
        now = time.monotonic()
        self.canvas.set_theme(self.service.settings.get("theme", "dark"))
        if now - self.ota_checked_at >= 1.0:
            self.ota_checked_at = now
            self.poll_ota()
        animating = self.page_anim.update() | self.select_anim.update()
        if self.toast_anim.update():
            animating = True
        if self.service.speaking or self.service.active:
            self._wave_phase += 0.14
            animating = True
        if not animating and not self._dirty and now - self._last_frame < 0.12:
            return
        self._last_frame = now
        self._dirty = False

        c = self.canvas
        box = self._layout()
        t = ease_in_out(max(0.0, min(1.0, self.page_anim.value)))
        alpha = int(255 * (0.35 + 0.65 * t))
        slide = int(self.canvas.px(26) * (1.0 - t))

        # nen gradient + phan sang goc tren
        c.vgradient(0, 0, self.width, self.height,
                    c.color("bg_top"), c.color("bg_bottom"))
        c.fill(0, 0, self.width, box["header"], c.color("surface"), 200)

        if self.page == "chat":
            self._draw_chat(c, box, slide, alpha)
        else:
            self._draw_settings(c, box, slide, alpha)

        self._draw_header(c, box)
        self._draw_footer(c, box)
        if self.confirm_unlink:
            self._draw_confirm(c, box)
        self._draw_toast(c, box)
        sdl2.SDL_RenderPresent(self.renderer)

    # ---- header ------------------------------------------------------
    def _draw_header(self, c, box):
        pad = box["pad"]
        y = (box["header"] - c.px(34)) // 2
        # vach accent gradient
        c.fill(0, box["header"] - c.px(2), self.width, c.px(2), c.color("accent"), 150)
        # ten app + chip version
        title_color = c.color("text")
        title = "Trimui-XiaoZhi"
        c.text(title, pad, y, self._font(UI_TITLE), title_color)
        chip_w = c.measure("v" + APP_VERSION, self._font(UI_TINY)) + c.px(20)
        chip_x = pad + c.measure(title, self._font(UI_TITLE)) + c.px(12)
        c.rounded(chip_x, y + c.px(6), chip_w, c.px(20), c.px(10),
                  c.color("accent_soft"))
        c.text("v" + APP_VERSION, chip_x + c.px(10), y + c.px(8),
               self._font(UI_TINY), c.color("accent"))

        # pill trang thai + dong song
        pill_text = self.service.status
        pill_w = c.measure(pill_text, self._font(UI_SMALL)) + c.px(72)
        pill_x = self.width - pad - pill_w
        pill_y = y + c.px(4)
        pill_h = c.px(28)
        c.rounded(pill_x, pill_y, pill_w, pill_h, pill_h // 2, c.color("surface_alt"),
                  235, c.color("border_soft"))
        status_color = c.color(self._status_color())
        dot_cx = pill_x + c.px(19)
        dot_cy = pill_y + pill_h // 2
        if self.service.speaking:
            c.wave(dot_cx, dot_cy, 3, c.px(13), status_color,
                   self._wave_phase, gap=c.px(7))
        else:
            if self.service.active:
                c.glow_dot(dot_cx, dot_cy, c.px(9), status_color, 1.0)
            c.rounded(dot_cx - c.px(4), dot_cy - c.px(4), c.px(8), c.px(8),
                      c.px(4), status_color, 255 if self.service.active else 150)
        c.text(pill_text, pill_x + c.px(36), pill_y + (pill_h - self._font(UI_SMALL)) // 2,
               self._font(UI_SMALL), c.color("dim"))
        if self.ota_badge:
            c.text(self.ota_badge, self.width - pad - c.measure(self.ota_badge, self._font(UI_TINY)),
                   pill_y + c.px(32), self._font(UI_TINY), c.color("faint"))

    # ---- footer ------------------------------------------------------
    def _draw_footer(self, c, box):
        hints = (self.tr("A  Nói", "A  Talk"), self.tr("B  Dừng / thoát", "B  Stop / exit"),
                 self.tr("SELECT  Cài đặt", "SELECT  Settings"),
                 self.tr("↑↓  Cuộn", "↑↓  Scroll")) if self.page == "chat" else \
                ("A  Đổi", self.tr("←→  Chọn", "←→  Choose"),
                 self.tr("B  Quay lại", "B  Back"),
                 self.tr("Web PIN  %s" % self.service.pin, "Web PIN  %s" % self.service.pin))
        y = self.height - box["footer"]
        c.fill(0, y, self.width, box["footer"], c.color("surface"), 200)
        c.fill(0, y, self.width, c.px(1), c.color("border_soft"), 140)
        x = box["pad"]
        for hint in hints:
            width = c.measure(hint, self._font(UI_TINY)) + c.px(20)
            c.rounded(x, y + c.px(14), width, c.px(26), c.px(13),
                      c.color("surface_alt"), 220, c.color("border_soft"))
            c.text(hint, x + c.px(10), y + c.px(19), self._font(UI_TINY), c.color("dim"))
            x += width + c.px(8)

    # ---- trang chat --------------------------------------------------
    def _draw_chat(self, c, box, slide, alpha):
        pad = box["pad"]
        x0 = box["card_x"] + slide
        y0 = box["content_y"]
        w = box["card_w"]
        h = box["content_h"]
        c.rounded(x0, y0, w, h, box["radius"], c.color("surface"), alpha)

        if self.service.activation_code and not self.service.activated:
            self._draw_activation(c, box, x0, y0, w, h, alpha)
        elif self.service.awaiting_new_code or (self.activation_page
                                                and not self.service.activated):
            self._draw_awaiting(c, box, x0, y0, w, h, alpha)
        else:
            self._draw_messages(c, box, x0, y0, w, h, alpha)
        c.text_left = None  # (khong dung)

    def _draw_messages(self, c, box, x0, y0, w, h, alpha):
        history = self.service.history
        pad_in = c.px(22)
        max_w = w - pad_in * 2 - c.px(72)
        end = len(history) - self.scroll
        visible = history[max(0, end - 40):end]
        if len(history) != self._seen_history:
            self._seen_history = len(history)
            self._dirty = True
        chat_size = self._font(self.service.settings.get("text_size", 24))
        line_h = int(chat_size * 1.36)

        if not visible:
            self._draw_empty(c, box, x0, y0, w, h)
            return

        # do cao khung moi truoc de can chinh cuoi danh sach
        blocks = []
        for entry in visible:
            mine = entry.get("role") == "U"
            color = c.color("bubble_me") if mine else c.color("bubble_ai")
            text_color = c.color("text")
            lines = c.wrap(entry.get("text", ""), chat_size, max_w - c.px(24))
            if not lines:
                continue
            label = self.tr("BẠN", "YOU") if mine else "XIAOZHI"
            blocks.append((mine, label, lines, color, text_color))
        total = sum(c.px(30) + len(ls) * line_h + c.px(10) for _m, _l, ls, _c, _t in blocks)
        y = y0 + h - pad_in - total
        if y < y0 + pad_in:
            y = y0 + pad_in
        newest = len(self.service.history) - 1 - self.scroll
        for index, (mine, label, lines, bubble, text_color) in enumerate(blocks):
            bubble_w = min(max_w, max(c.measure(ln, chat_size) for ln in lines) + c.px(24))
            bubble_h = len(lines) * line_h + c.px(16)
            if mine:
                bx = x0 + w - pad_in - bubble_w
            else:
                bx = x0 + pad_in + c.px(34)
            # tin moi nhat: truot len + mo dan
            entry_index = max(0, end - len(visible) + index) - 1
            entry_alpha = alpha
            by = y
            if entry_index == newest:
                self._wave_phase += 0.0  # giu phase song song
                grow = min(1.0, (time.monotonic() - self._last_frame) * 4.0 + 0.9)
                entry_alpha = int(alpha * grow)
                by = y + int(c.px(10) * (1.0 - ease_out_cubic(grow)))
            c.rounded(bx, by, bubble_w, bubble_h, c.px(16), bubble, entry_alpha)
            if not mine:
                # avatar tron nho cua tro ly: vong accent + song trang
                acx = bx - c.px(20)
                acy = by + c.px(15)
                c.rounded(acx - c.px(11), acy - c.px(11), c.px(22), c.px(22),
                          c.px(11), c.color("accent"), entry_alpha)
                c.wave(acx, acy, 3, c.px(12), c.color("bg_top"), 0.9,
                       entry_alpha, gap=c.px(5))
            ty = by + c.px(8)
            for line in lines:
                c.text(line, bx + c.px(12), ty, chat_size, text_color, entry_alpha)
                ty += line_h
            y = by + bubble_h + c.px(10)

    def _draw_empty(self, c, box, x0, y0, w, h):
        cx = x0 + w // 2
        cy = y0 + int(h * 0.40)
        # vong tron "mic" + song dong
        c.glow_dot(cx, cy, c.px(46), c.color("accent"), 1.0)
        c.rounded(cx - c.px(34), cy - c.px(34), c.px(68), c.px(68), c.px(34),
                  c.color("accent"), 60)
        c.wave(cx, cy, 5, c.px(30), c.color("accent"), self._wave_phase,
               220, gap=c.px(14))
        title = self.tr("Sẵn sàng trò chuyện", "Ready to talk")
        c.text_center(title, cx, cy + c.px(62), self._font(UI_LG), c.color("text"))
        hint = self.tr("Nhấn A để nói với Xiaozhi", "Press A to talk")
        c.text_center(hint, cx, cy + c.px(98), self._font(UI_BODY), c.color("dim"))

    def _draw_activation(self, c, box, x0, y0, w, h, alpha):
        cx = x0 + w // 2
        top = y0 + c.px(40)
        c.text_center(self.tr("KÍCH HOẠT THIẾT BỊ", "ACTIVATION REQUIRED"),
                      cx, top, self._font(UI_LG), c.color("accent"))
        c.text_center(self.tr("Trợ lý → Thêm thiết bị → nhập mã xác minh 6 số",
                              "Console → Add device → enter the 6-digit code"),
                      cx, top + c.px(44), self._font(UI_BODY), c.color("dim"))
        code = str(self.service.activation_code or "")
        digits = c.px(46)
        box_w = digits + c.px(26)
        total = len(code) * box_w - c.px(26)
        bx = cx - total // 2
        by = top + c.px(96)
        for index, char in enumerate(code):
            dx = bx + index * box_w
            c.rounded(dx, by, box_w, c.px(58), c.px(10), c.color("surface_alt"),
                      alpha, c.color("border"))
            c.text_center(char, dx + box_w // 2, by + c.px(14),
                          self._font(UI_TITLE), c.color("text"))
        c.text_center(self.tr("Nhấn A để làm mới mã", "Press A to refresh"),
                      cx, by + c.px(76), self._font(UI_BODY), c.color("faint"))

    def _draw_awaiting(self, c, box, x0, y0, w, h, alpha):
        cx = x0 + w // 2
        top = y0 + c.px(60)
        c.text_center(self.tr("ĐANG TẠO DANH TÍNH MỚI", "CREATING A NEW DEVICE IDENTITY"),
                      cx, top, self._font(UI_LG), c.color("accent"))
        c.text_center(self.tr("Đang chờ máy chủ cấp mã xác minh 6 số...",
                              "Waiting for the server to issue a 6-digit code..."),
                      cx, top + c.px(44), self._font(UI_BODY), c.color("dim"))
        c.wave(cx, top + c.px(104), 7, c.px(34), c.color("accent"),
               self._wave_phase, 200, gap=c.px(16))
        c.text_center(self.tr("Nếu không có mã, kiểm tra Wi-Fi rồi nhấn A để thử lại.",
                              "No code? Check Wi-Fi, then press A to retry."),
                      cx, top + c.px(140), self._font(UI_BODY), c.color("faint"))

    # ---- trang cai dat ----------------------------------------------
    def _draw_settings(self, c, box, slide, alpha):
        x0 = box["card_x"] + slide
        y = box["content_y"]
        c.rounded(x0, y, box["card_w"], box["content_h"], box["radius"],
                  c.color("surface"), alpha)
        pad_in = c.px(24)
        inner_x = x0 + pad_in
        inner_w = box["card_w"] - pad_in * 2
        row_h = c.px(46)
        group_h = c.px(30)

        self.select_anim.set(1.0 if self.page == "settings" else 0.0)
        entries = []
        for title, keys in GROUP:
            rows = [i for i, (_l, k, _c) in enumerate(self.options) if k in keys]
            if not rows:
                continue
            entries.append(("group", title, len(entries)))
            for index in rows:
                entries.append(("row", index, len(entries)))
        total = sum(group_h if e[0] == "group" else row_h for e in entries) + c.px(8)
        top = max(y + c.px(12), min(y + box["content_h"] - total - c.px(8),
                                    y + c.px(12) + self.setting_index * row_h
                                    - c.px(40)))

        for kind, payload, _order in entries:
            if kind == "group":
                if top + group_h > y + box["content_h"]:
                    break
                c.text(payload, inner_x, top + c.px(8), self._font(UI_TINY),
                       c.color("faint"))
                top += group_h
                continue
            index = payload
            if top + row_h > y + box["content_h"]:
                break
            self._draw_setting_row(c, inner_x, top, inner_w, row_h, index, alpha)
            top += row_h

    def _draw_setting_row(self, c, x, y, w, h, index, alpha):
        label, key, choices = self.options[index]
        selected = index == self.setting_index
        radius = c.px(12)
        if selected:
            c.rounded(x - c.px(8), y, w + c.px(16), h, radius,
                      c.color("surface_alt"), alpha, c.color("border"))
            # thanh accent ben trai
            bar_h = int(h * 0.55)
            c.rounded(x - c.px(8), y + (h - bar_h) // 2, c.px(4), bar_h, c.px(2),
                      c.color("accent"), alpha)
        text_color = c.color("text") if selected else c.color("dim")
        c.text(label, x + c.px(10), y + (h - self._font(UI_BODY)) // 2,
               self._font(UI_BODY), text_color, alpha)
        if key in ACTION_KEYS:
            value = self.tr("Nhấn A", "Press A")
            value_color = c.color("accent") if selected else c.color("faint")
        else:
            raw = self.service.settings.get(key, "")
            value = self._setting_value(key, raw)
            value_color = c.color("accent") if selected else c.color("dim")
        vw = c.measure(value, self._font(UI_BODY)) + c.px(24)
        vx = x + w - vw - c.px(6)
        if selected:
            c.rounded(vx - c.px(10), y + (h - c.px(26)) // 2, vw, c.px(26), c.px(13),
                      c.color("accent_soft"), alpha)
        c.text(value, vx, y + (h - self._font(UI_BODY)) // 2,
               self._font(UI_BODY), value_color, alpha)
        # mui ten ← → khi dang chon muc co nhieu lua chon
        if selected and key not in ACTION_KEYS and len(choices) > 1:
            cy = y + h // 2
            c.rounded(vx - c.px(16), cy - c.px(5), c.px(7), c.px(10), c.px(2),
                      c.color("faint"))
            c.rounded(vx + vw - c.px(2), cy - c.px(5), c.px(7), c.px(10), c.px(2),
                      c.color("faint"))

    def _setting_value(self, key, raw):
        if key == "language":
            return "Tiếng Việt" if raw == "vi" else "English"
        if key == "theme":
            return self.tr("Tối", "Dark") if raw == "dark" else self.tr("Sáng", "Light")
        if key == "text_size":
            return "%d px" % int(raw)
        if key == "intro":
            return self.tr("Bật", "On") if raw else self.tr("Tắt", "Off")
        if key == "auto_after_reply":
            return self.tr("Có", "Yes") if raw else self.tr("Không", "No")
        if key in ("remote_enabled", "remote_allow_control", "remote_allow_text"):
            return self.tr("Bật", "On") if raw else self.tr("Tắt", "Off")
        if key == "timeout":
            return self.tr("Không chờ", "No timeout") if not raw else "%d s" % int(raw)
        return str(raw)

    # ---- hop thoai xac nhan -----------------------------------------
    def _draw_confirm(self, c, box):
        w = int(self.width * 0.78)
        h = int(self.height * 0.46)
        x = (self.width - w) // 2
        y = (self.height - h) // 2
        c.fill(0, 0, self.width, self.height, c.color("bg_top"), 175)
        c.rounded(x, y, w, h, box["radius"], c.color("surface"), 255,
                  c.color("border"))
        cx = x + w // 2
        top = y + c.px(32)
        title = self.tr("TẠO DANH TÍNH THIẾT BỊ MỚI?", "CREATE A NEW DEVICE IDENTITY?")
        c.text_center(title, cx, top, self._font(UI_MED), c.color("accent"))
        note = self.tr("Gỡ thiết bị cũ trên xiaozhi.me/console trước.",
                       "Unlink the old device on xiaozhi.me/console first.")
        c.text_center(note, cx, top + c.px(42), self._font(UI_BODY), c.color("dim"))
        c.text_center(self.tr("Danh tính cũ sẽ được sao lưu tự động.",
                              "The current identity is backed up automatically."),
                      cx, top + c.px(72), self._font(UI_BODY), c.color("faint"))
        cancel = self.tr("B: Hủy", "B: Cancel")
        confirm = self.tr("A: Xác nhận", "A: Confirm")
        body = self._font(UI_BODY)
        pad = c.px(22)
        bw = max(c.measure(cancel, body), c.measure(confirm, body)) + pad * 2
        bh = c.px(46)
        gap = c.px(14)
        by = y + h - c.px(40) - bh
        c.rounded(cx - bw - gap // 2, by, bw, bh, c.px(14),
                  c.color("surface_alt"), 255, c.color("border"))
        c.text_center(cancel, cx - bw - gap // 2 + bw // 2,
                      by + (bh - body) // 2, body, c.color("dim"))
        c.rounded(cx + gap // 2, by, bw, bh, c.px(14), c.color("accent"), 255)
        c.text_center(confirm, cx + gap // 2 + bw // 2,
                      by + (bh - body) // 2, body, c.color("bg_top"))

    # ---- thong bao OTA ----------------------------------------------
    def _draw_toast(self, c, box):
        if self.ota_notice:
            self.toast_anim.set(1.0)
        elif self.toast_anim.target != 0.0:
            self.toast_anim.set(0.0)
        t = ease_out_cubic(max(0.0, min(1.0, self.toast_anim.value)))
        if t <= 0.01:
            return
        pad = box["pad"]
        w = box["card_w"]
        h = c.px(56)
        x = pad
        y = int(-h + (h + c.px(10)) * t)
        c.rounded(x, y, w, h, c.px(16), c.color("accent"), int(255 * t))
        c.text(self.ota_notice, x + c.px(20), y + (h - self._font(UI_BODY)) // 2,
               self._font(UI_BODY), c.color("bg_top"), int(255 * t))

    def action(self, action):
        if action == "quit":
            self.running = False
        elif self.confirm_unlink:
            if action == "back":
                self.confirm_unlink = False
                self._dirty = True
            elif action == "a":
                self.confirm_unlink = False
                if self.service.unlink_device():
                    self._goto_page("chat")
                    self.activation_page = True
                self._dirty = True
        elif self.page == "settings":
            if action == "back":
                self._goto_page("chat")
            elif action in ("up", "down"):
                step = 1 if action == "down" else -1
                self.setting_index = (self.setting_index + step) % len(self.options)
                self._dirty = True
            elif action in ("a", "left", "right"):
                _, key, choices = self.options[self.setting_index]
                if key is None:
                    if action == "a":
                        self.service.test_microphone()
                elif key == "reactivate":
                    if action == "a":
                        self.service.reactivate()
                        self._goto_page("chat")
                elif key == "unlink":
                    if action == "a":
                        self.confirm_unlink = True
                else:
                    old = self.service.settings[key]
                    position = choices.index(old) if old in choices else 0
                    self.service.settings[key] = choices[(position + (-1 if action == "left" else 1)) % len(choices)]
                    self.service.save_settings()
                    start_remote(self.service)
                self._dirty = True
        elif action == "back":
            if self.service.active:
                self.service.stop()
            else:
                self.running = False
        elif action == "settings":
            self._goto_page("settings")
        elif action == "a":
            if self.activation_page and not self.service.activated:
                self.service.refresh_activation_code()
            else:
                self.service.listen()
        elif action == "up":
            self.scroll = min(self.scroll + 1, max(0, len(self.service.history) - 1))
            self._dirty = True
        elif action == "down":
            self.scroll = max(self.scroll - 1, 0)
            self._dirty = True

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
        if self.canvas:
            self.canvas.clear_text_cache()
        giant = getattr(self, "intro_font", None)
        if giant:
            ttf.TTF_CloseFont(giant)
            self.intro_font = None
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
        last_status = ""
        while screen.running:
            screen.events()
            service.poll()
            # Chi ve lai khi co gi thay doi hoac dang co animation; khong
            # vong lap 60fps khi man hinh dang tinh (tiet pin + CPU).
            if service.status != last_status:
                last_status = service.status
                screen._dirty = True
            screen.draw()
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
