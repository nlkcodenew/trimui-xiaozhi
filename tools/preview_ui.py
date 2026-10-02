#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render giao dien moi ra PNG de xem truoc khi nap len may.

Dung Canvas cua ui.py nhung ve bang PIL thay vi SDL -> hinh ra y het thiet ke
(bo cuc, mau sac, hinh bo tron, dong song). Khong can SDL.
"""
import os
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "tests"))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import test_intro  # gac sdl2 gia de import app duoc  # noqa: E402

import app  # noqa: E402
import ui  # noqa: E402

FONT_PATH = APP / "assets" / "font.ttf"
OUT_DIR = Path(os.environ.get("PREVIEW_OUT", APP / "preview"))
WIDTH, HEIGHT = 1024, 768


class PilCanvas(ui.Canvas):
    """Canvas ve tren PIL Image, dung cung API voi ui.Canvas."""

    def __init__(self, fonts, theme, width=WIDTH, height=HEIGHT):
        super().__init__(None, fonts, theme)
        self.image = Image.new("RGB", (width, height), (0, 0, 0))
        self.draw = ImageDraw.Draw(self.image, "RGBA")
        self._pil_fonts = {}
        self.resize(width, height)

    # -- phong chu -----------------------------------------------------
    def _pil_font(self, size):
        size = max(8, int(round(size)))
        if size not in self._pil_fonts:
            self._pil_fonts[size] = ImageFont.truetype(str(FONT_PATH), size)
        return self._pil_fonts[size]

    def measure(self, value, size):
        font = self._pil_font(size)
        return int(self.draw.textlength(str(value), font=font))

    # -- hinh hoc ------------------------------------------------------
    def fill(self, x, y, width, height, color, alpha=255):
        if width <= 0 or height <= 0 or alpha <= 0:
            return
        self.draw.rectangle([x, y, x + width - 1, y + height - 1],
                            fill=tuple(color) + (int(alpha),))

    def rounded(self, x, y, width, height, radius, color, alpha=255,
                border=None, border_alpha=255):
        if width <= 0 or height <= 0:
            return
        radius = int(max(0, min(radius, width // 2, height // 2)))
        box = [x, y, x + width - 1, y + height - 1]
        if radius <= 0:
            self.fill(x, y, width, height, color, alpha)
        else:
            self.draw.rounded_rectangle(box, radius=radius,
                                        fill=tuple(color) + (int(alpha),))
        if border is not None:
            self.draw.rounded_rectangle(box, radius=radius,
                                        outline=tuple(border) + (int(border_alpha),),
                                        width=1)

    def rounded_outline(self, x, y, width, height, radius, color, alpha=255):
        box = [x, y, x + width - 1, y + height - 1]
        self.draw.rounded_rectangle(box, radius=int(max(0, radius)),
                                    outline=tuple(color) + (int(alpha),), width=1)

    def vgradient(self, x, y, width, height, top, bottom, alpha=255):
        steps = max(1, int(height))
        for index in range(steps):
            color = ui.mix(top, bottom, index / float(max(1, steps - 1)))
            self.fill(x, y + index, width, 1, color, alpha)

    def glow_dot(self, cx, cy, radius, color, intensity=1.0):
        for ring in range(4, 0, -1):
            r = radius * ring / 4.0
            alpha = int(46 * intensity * (1.0 - (ring - 1) / 4.0))
            if alpha <= 0:
                continue
            self.draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                              outline=tuple(color) + (alpha,), width=1)

    def hbar(self, x, y, width, height, fraction, track, fill):
        fraction = max(0.0, min(1.0, fraction))
        self.rounded(x, y, width, height, height // 2, track)
        if fraction > 0:
            self.rounded(x, y, max(height, int(width * fraction)), height,
                         height // 2, fill)

    # -- chu -----------------------------------------------------------
    def text(self, value, x, y, size, color, alpha=255):
        self.draw.text((x, y), str(value), font=self._pil_font(size),
                       fill=tuple(color) + (int(alpha),))
        return self.measure(value, size)

    def wrap(self, value, size, max_width):
        return ui.Canvas.wrap(self, value, size, max_width)


def build(theme, page, history=None, status="Sẵn sàng trò chuyện", **service_kwargs):
    from types import SimpleNamespace
    settings = {
        "language": "vi", "theme": theme, "text_size": 24, "intro": True,
        "timeout": 30, "auto_after_reply": True, "remote_enabled": False,
        "remote_allow_control": True, "remote_allow_text": True,
        "remote_port": 8788, "capture_device": "auto",
        "playback_device": "default",
    }
    service = SimpleNamespace(settings=settings, history=list(history or []),
                              status=status, activated=True, activation_code="",
                              awaiting_new_code=False, speaking=False, active=False,
                              pin="085951", remote=None, core=None)
    for key, value in service_kwargs.items():
        setattr(service, key, value)
    screen = app.Screen(service)
    screen.renderer = object()
    screen.width, screen.height = WIDTH, HEIGHT
    screen.canvas = PilCanvas(screen.fonts, theme, WIDTH, HEIGHT)
    screen.fonts = {size: object() for size in range(8, 130)}
    screen.canvas.fonts = screen.fonts
    screen.canvas.resize(WIDTH, HEIGHT)
    if page == "settings":
        screen._goto_page("settings")
        screen.page_anim.jump(1.0)
    return screen


CHAT = [
    {"role": "A", "text": "Chào bạn! Mình có thể giúp gì hôm nay?"},
    {"role": "U", "text": "Báo cho tôi thời tiết Hà Nội hôm nay"},
    {"role": "A", "text": "Hà Nội hôm nay trời nhiều mây, khoảng 24-29 độ C, có mưa rào nhẹ vào chiều tối. Bạn nhớ mang dù khi ra ngoài nhé."},
    {"role": "U", "text": "Cảm ơn"},
    {"role": "A", "text": "Không có gì! Bạn cứ gọi mình bất cứ lúc nào."},
]


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    shots = []
    for theme in ("dark", "light"):
        screen = build(theme, "chat", CHAT)
        screen._wave_phase = 0.6
        screen.draw()
        path = OUT_DIR / ("chat-%s.png" % theme)
        screen.canvas.image.save(path)
        shots.append(path)

        screen = build(theme, "settings")
        screen.draw()
        path = OUT_DIR / ("settings-%s.png" % theme)
        screen.canvas.image.save(path)
        shots.append(path)

    screen = build("dark", "chat", [], status="Đang lắng nghe...",
                   speaking=True, active=True)
    screen._wave_phase = 1.1
    screen.draw()
    path = OUT_DIR / "chat-empty-dark.png"
    screen.canvas.image.save(path)
    shots.append(path)

    screen = build("dark", "chat", [], status="Chờ kích hoạt")
    screen.service.activation_code = "417902"
    screen.service.activated = False
    screen.draw()
    path = OUT_DIR / "activation-dark.png"
    screen.canvas.image.save(path)
    shots.append(path)

    screen = build("dark", "settings")
    screen.confirm_unlink = True
    screen.draw()
    path = OUT_DIR / "confirm-dark.png"
    screen.canvas.image.save(path)
    shots.append(path)

    for path in shots:
        print(path)


if __name__ == "__main__":
    main()