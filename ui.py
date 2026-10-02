# -*- coding: utf-8 -*-
"""Bo ve giao dien cho Trimui-XiaoZhi.

Tach rieng khoi app.py de UI co the lap/tinh nhanh:
  - Bang mau (dark/light) + phong chu co scale theo man hinh that.
  - Ve bang texture: MOT LAN render chu xuoi texture, cac khung sau chi
    SDL_RenderCopy -> app chay duoc animation 30fps tren chip yeu.
  - Hinh hoc bo tron, gradient, pill, thanh tieng dong.
  - Tien ich chuyen dong (Anim) cho hien ung mo/truot/mo dan.

Quy uoc toa do: pixel that cua man hinh (KHONG dung logical size nen khong
bi letterbox 2 dai den tren man hinh 1024x768).
"""

import ctypes
import math
import time

try:
    import sdl2
    import sdl2.sdlttf as ttf
except Exception:  # pragma: no cover - app.py xu ly truoc
    sdl2 = None
    ttf = None


# --------------------------------------------------------------------------
# Bang mau
# --------------------------------------------------------------------------

THEMES = {
    "dark": {
        "bg_top": (11, 16, 32),
        "bg_bottom": (5, 7, 14),
        "surface": (19, 27, 46),
        "surface_alt": (26, 36, 62),
        "surface_soft": (23, 32, 54),
        "border": (42, 53, 85),
        "border_soft": (33, 42, 68),
        "text": (242, 246, 255),
        "dim": (150, 163, 194),
        "faint": (99, 111, 142),
        "accent": (37, 211, 202),
        "accent_2": (124, 92, 255),
        "accent_soft": (23, 66, 68),
        "success": (61, 220, 132),
        "warning": (255, 176, 32),
        "danger": (255, 92, 108),
        "bubble_me": (26, 46, 78),
        "bubble_ai": (20, 28, 48),
        "shadow": (0, 0, 0),
    },
    "light": {
        "bg_top": (247, 250, 254),
        "bg_bottom": (228, 235, 246),
        "surface": (255, 255, 255),
        "surface_alt": (240, 245, 252),
        "surface_soft": (246, 249, 254),
        "border": (216, 226, 241),
        "border_soft": (229, 236, 247),
        "text": (15, 27, 45),
        "dim": (88, 105, 133),
        "faint": (140, 154, 178),
        "accent": (12, 150, 145),
        "accent_2": (98, 80, 210),
        "accent_soft": (214, 240, 238),
        "success": (14, 148, 76),
        "warning": (186, 110, 0),
        "danger": (203, 44, 60),
        "bubble_me": (214, 240, 238),
        "bubble_ai": (255, 255, 255),
        "shadow": (30, 45, 70),
    },
}


def mix(a, b, t):
    """Tron 2 mau RGB, t=0 -> a, t=1 -> b."""
    t = max(0.0, min(1.0, t))
    return (int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def ease_out_cubic(t):
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def ease_in_out(t):
    t = max(0.0, min(1.0, t))
    return 3 * t * t - 2 * t * t * t


class Anim:
    """Gia tri chuyen dan cham den muc tieu trong `duration` giay."""

    def __init__(self, value=0.0, duration=0.22):
        self.value = float(value)
        self.target = float(value)
        self.duration = duration
        self.started = time.monotonic()
        self.origin = float(value)

    def set(self, target):
        target = float(target)
        if abs(target - self.target) < 1e-6:
            return
        self.origin = self.value
        self.target = target
        self.started = time.monotonic()

    def jump(self, value):
        self.value = self.target = self.origin = float(value)
        self.started = time.monotonic()

    def update(self):
        if abs(self.value - self.target) < 1e-6:
            self.value = self.target
            return False
        elapsed = time.monotonic() - self.started
        t = 1.0 if self.duration <= 0 else elapsed / self.duration
        self.value = self.origin + (self.target - self.origin) * ease_out_cubic(t)
        return True

    @property
    def done(self):
        return abs(self.value - self.target) < 1e-6


# --------------------------------------------------------------------------
# Lop ve
# --------------------------------------------------------------------------

class Canvas:
    """Ve len renderer cua SDL. Toan bo toa do la pixel that."""

    TEXT_CACHE_LIMIT = 320

    def __init__(self, renderer, fonts, theme="dark"):
        self.renderer = renderer
        self.fonts = fonts
        self.theme_name = theme
        self.theme = THEMES.get(theme, THEMES["dark"])
        self.width = 0
        self.height = 0
        self.scale = 1.0
        self._text_cache = {}

    # ---- theme / kich thuc -------------------------------------------
    def set_theme(self, name):
        if name in THEMES and name != self.theme_name:
            self.theme_name = name
            self.theme = THEMES[name]
            self.clear_text_cache()

    def resize(self, width, height):
        """Canh moi toan bo UI theo man hinh that (khong letterbox)."""
        if width == self.width and height == self.height:
            return
        self.width = width
        self.height = height
        self.scale = max(0.70, min(1.60, height / 768.0))
        self.clear_text_cache()

    def px(self, value):
        """Do dai thiet ke -> pixel that theo man hinh."""
        return max(1, int(round(value * self.scale)))

    def color(self, name):
        return self.theme[name]

    def clear_text_cache(self):
        for entry in self._text_cache.values():
            try:
                sdl2.SDL_DestroyTexture(entry[0])
            except Exception:
                pass
        self._text_cache.clear()

    def invalidate_text(self):
        self.clear_text_cache()

    # ---- hinh hoc ------------------------------------------------------
    def fill(self, x, y, width, height, color, alpha=255):
        if width <= 0 or height <= 0 or alpha <= 0:
            return
        sdl2.SDL_SetRenderDrawColor(self.renderer, color[0], color[1], color[2], alpha)
        sdl2.SDL_RenderFillRect(self.renderer, sdl2.SDL_Rect(int(x), int(y),
                                                            int(width), int(height)))

    def rounded(self, x, y, width, height, radius, color, alpha=255,
                border=None, border_alpha=255):
        """Hinh chu nhat bo tron bang Rect (SDL2 khong co API bo tron san)."""
        if width <= 0 or height <= 0 or alpha <= 0:
            return
        radius = int(max(0, min(radius, width // 2, height // 2)))
        if radius <= 0:
            self.fill(x, y, width, height, color, alpha)
            return
        sdl2.SDL_SetRenderDrawColor(self.renderer, color[0], color[1], color[2], alpha)
        # phan thanh giua
        self.fill(x + radius, y, width - 2 * radius, height, color, alpha)
        self.fill(x, y + radius, width, height - 2 * radius, color, alpha)
        # bo goc: moi dong lech 1px, cham hon se co gai nho
        span = radius + 1
        for dy in range(span):
            dy2 = span - 1 - dy
            inset = radius - int(math.sqrt(max(0.0, radius * radius - dy2 * dy2)))
            w = max(0, radius - inset)
            if w <= 0:
                continue
            self.fill(x + inset, y + dy, w, 1, color, alpha)
            self.fill(x + width - inset - w, y + dy, w, 1, color, alpha)
            self.fill(x + inset, y + height - 1 - dy, w, 1, color, alpha)
            self.fill(x + width - inset - w, y + height - 1 - dy, w, 1, color, alpha)
        if border is not None:
            self.rounded_outline(x, y, width, height, radius, border, border_alpha)

    def rounded_outline(self, x, y, width, height, radius, color, alpha=255):
        """Viet vien 1px quanh hinh bo tron."""
        radius = int(max(0, min(radius, width // 2, height // 2)))
        if radius <= 0:
            self.fill(x, y, width, 1, color, alpha)
            self.fill(x, y + height - 1, width, 1, color, alpha)
            self.fill(x, y, 1, height, color, alpha)
            self.fill(x + width - 1, y, 1, height, color, alpha)
            return
        sdl2.SDL_SetRenderDrawColor(self.renderer, color[0], color[1], color[2], alpha)
        self.fill(x + radius, y, width - 2 * radius, 1, color, alpha)
        self.fill(x + radius, y + height - 1, width - 2 * radius, 1, color, alpha)
        span = radius + 1
        for dy in range(span):
            dy2 = span - 1 - dy
            inset = radius - int(math.sqrt(max(0.0, radius * radius - dy2 * dy2)))
            w = max(0, radius - inset)
            if w <= 0:
                continue
            self.fill(x + inset, y + dy, w, 1, color, alpha)
            self.fill(x + width - inset - w, y + dy, w, 1, color, alpha)
            self.fill(x + inset, y + height - 1 - dy, w, 1, color, alpha)
            self.fill(x + width - inset - w, y + height - 1 - dy, w, 1, color, alpha)

    def vgradient(self, x, y, width, height, top, bottom, alpha=255):
        """Gradient doc bang ~48 duong mau (re nhe tren chip yeu)."""
        if height <= 0:
            return
        steps = min(48, height)
        band = height / float(steps)
        for index in range(steps):
            color = mix(top, bottom, index / float(max(1, steps - 1)))
            self.fill(x, y + int(index * band), width, int(band) + 1, color, alpha)

    def glow_dot(self, cx, cy, radius, color, intensity=1.0):
        """Quang tròn phat sang: vong tron trong -> ngoai, alpha giam dan."""
        rings = 4
        sdl2.SDL_SetRenderDrawBlendMode(self.renderer, sdl2.SDL_BLENDMODE_BLEND)
        for ring in range(rings, 0, -1):
            r = radius * ring / float(rings)
            alpha = int(46 * intensity * (1.0 - (ring - 1) / float(rings)))
            if alpha <= 0:
                continue
            sdl2.SDL_SetRenderDrawColor(self.renderer, color[0], color[1], color[2], alpha)
            sdl2.SDL_RenderDrawRect(self.renderer,
                                    sdl2.SDL_Rect(int(cx - r), int(cy - r),
                                                  int(r * 2), int(r * 2)))

    def hbar(self, x, y, width, height, fraction, track, fill):
        fraction = max(0.0, min(1.0, fraction))
        self.rounded(x, y, width, height, height // 2, track)
        if fraction > 0:
            self.rounded(x, y, max(height, int(width * fraction)), height,
                         height // 2, fill)

    # ---- chu ------------------------------------------------------------
    def font(self, size):
        key = max(8, int(round(size)))
        font = self.fonts.get(key)
        if font is None and self.fonts:
            # Gan nhat co san: dung kich thuoc gan nhat de tranh crash.
            key = min(self.fonts, key=lambda s: abs(s - key))
            font = self.fonts[key]
        return font

    def measure(self, value, size):
        font = self.font(size)
        if not font:
            return 0
        width = ctypes.c_int()
        try:
            if ttf.TTF_SizeUTF8(font, str(value).encode("utf-8"),
                                ctypes.byref(width), None) == 0:
                return width.value
        except Exception:
            pass
        return int(len(str(value)) * size * 0.55)

    def _texture(self, value, size, color):
        """Render mot lan roi giu texture (ke ca chu dong trong khung ve)."""
        key = (value, int(size), color)
        entry = self._text_cache.get(key)
        if entry is not None:
            return entry
        font = self.font(size)
        if not font:
            return (None, 0, 0)
        try:
            surface = ttf.TTF_RenderUTF8_Blended(
                font, str(value).encode("utf-8"), sdl2.SDL_Color(color[0], color[1], color[2], 255))
        except Exception:
            return (None, 0, 0)
        if not surface:
            return (None, 0, 0)
        width, height = surface.contents.w, surface.contents.h
        texture = sdl2.SDL_CreateTextureFromSurface(self.renderer, surface)
        sdl2.SDL_FreeSurface(surface)
        if not texture:
            return (None, 0, 0)
        entry = (texture, width, height)
        if len(self._text_cache) >= self.TEXT_CACHE_LIMIT:
            # Bo phan tu dau (dien Bien FIFO don gian, du cho UI nay).
            for old_key in list(self._text_cache)[:64]:
                stale = self._text_cache.pop(old_key, None)
                if stale:
                    try:
                        sdl2.SDL_DestroyTexture(stale[0])
                    except Exception:
                        pass
        self._text_cache[key] = entry
        return entry

    def text(self, value, x, y, size, color, alpha=255):
        """Ve mot dong chu. Tra ve be rong hien thi."""
        texture, width, height = self._texture(value, size, color)
        if not texture:
            return 0
        sdl2.SDL_SetTextureAlphaMod(texture, max(0, min(255, int(alpha))))
        sdl2.SDL_RenderCopy(self.renderer, texture, None,
                            sdl2.SDL_Rect(int(x), int(y), int(width), int(height)))
        sdl2.SDL_SetTextureAlphaMod(texture, 255)
        return width

    def text_center(self, value, cx, y, size, color, alpha=255):
        width = self.measure(value, size)
        return self.text(value, cx - width // 2, y, size, color, alpha)

    def text_right(self, value, right, y, size, color, alpha=255):
        width = self.measure(value, size)
        return self.text(value, right - width, y, size, color, alpha)

    def wrap(self, value, size, max_width):
        """Tach dong theo be rong, khong cat giua tu (tieng Viet khop)."""
        value = str(value).replace("\n", " ").strip()
        if not value:
            return []
        words = value.split(" ")
        lines = []
        current = ""
        for word in words:
            candidate = word if not current else current + " " + word
            if self.measure(candidate, size) <= max_width or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    def paragraph(self, value, x, y, size, color, max_width, line_gap=0.34,
                  max_lines=None, alpha=255):
        """Chu nhieu dong. Tra ve y sau dong cuoi + 1."""
        step = int(size * (1.0 + line_gap))
        lines = self.wrap(value, size, max_width)
        if max_lines is not None and len(lines) > max_lines:
            lines = lines[:max_lines]
        for index, line in enumerate(lines):
            self.text(line, x, y + index * step, size, color, alpha)
        return y + len(lines) * step

    # ---- thanh tieng dong ------------------------------------------------
    def wave(self, cx, cy, bars, height, color, phase, alpha=255, gap=None):
        """Dong song: sin/cos theo phase - dung cho trang thai 'dang nghe'."""
        gap = gap or max(3, height // 2)
        width = bars * gap
        left = cx - width // 2
        for index in range(bars):
            angle = phase + index * 0.72
            value = (math.sin(angle) * 0.6 + math.sin(angle * 1.9 + 1.1) * 0.4 + 1.0) * 0.5
            bar_h = max(2, int(height * (0.28 + 0.72 * value)))
            x = left + index * gap + gap // 2
            self.rounded(x - 2, cy - bar_h // 2, 4, bar_h, 2, color, alpha)