# -*- coding: utf-8 -*-
"""Test cho lop UI moi (ui.Canvas + Screen.draw).

Muc tieu:
  - Moi trang ve duoc o ca hai theme (dark/light) ma khong nem loi.
  - KHONG con letterbox: moi thu nam trong man hinh that (1024x768).
  - Chu duoc render 1 lan roi dung texture (khong TTF_Render moi khung ve).
  - Bo cuc khong tran man hinh va cac muc cai dat deu ve dung nhom.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "tests"))

import test_intro  # noqa: F401  (gac sdl2 gia truoc khi import app)

import app  # noqa: E402
import ui  # noqa: E402

sdl2 = test_intro.sdl2

SETTINGS = {
    "language": "vi", "theme": "dark", "text_size": 24, "intro": True,
    "timeout": 30, "auto_after_reply": True, "remote_enabled": False,
    "remote_allow_control": True, "remote_allow_text": True,
    "remote_port": 8788, "capture_device": "auto", "playback_device": "default",
}


def make_service(theme="dark", history=None, activated=True):
    settings = dict(SETTINGS)
    settings["theme"] = theme
    return SimpleNamespace(
        settings=settings, history=list(history or []), status="Sẵn sàng trò chuyện",
        activated=activated, activation_code="", awaiting_new_code=False,
        speaking=False, active=False, pin="085951", history_limit=150,
        remote=None, core=None,
    )


def make_screen(theme="dark", history=None, width=1024, height=768):
    screen = app.Screen(make_service(theme, history))
    screen.renderer = object()
    screen.width, screen.height = width, height
    screen.canvas = ui.Canvas(screen.renderer, screen.fonts, theme)
    screen.canvas.resize(width, height)
    # Font gia: moi co chu deu tra ve mot object dung duoc.
    screen.fonts = {size: object() for size in range(8, 130)}
    screen.canvas.fonts = screen.fonts
    screen.canvas.resize(width, height)
    return screen


def draw(screen):
    reset_state()
    screen.draw()
    return sdl2.state


def reset_state():
    sdl2.state.update({"present": 0, "blits": 0, "created": [], "destroyed": [],
                       "clears": 0, "delays": 0, "fills": 0, "rects": []})


def test_both_themes_render_chat_page():
    for theme in ("dark", "light"):
        screen = make_screen(theme)
        state = draw(screen)
        assert state["present"] == 1, "%s: must Present exactly one frame" % theme
        assert state["fills"] > 20, "%s: UI phau ve it qua" % theme
        assert state["blits"] > 0, "%s: phai co chu" % theme


def test_settings_page_renders_in_both_themes():
    for theme in ("dark", "light"):
        screen = make_screen(theme)
        screen._goto_page("settings")
        screen.page_anim.jump(1.0)
        state = draw(screen)
        assert state["present"] == 1, "%s: settings must render" % theme
        assert state["blits"] > 0


def test_theme_switch_changes_palette_and_clears_cache():
    screen = make_screen("dark")
    draw(screen)
    assert screen.canvas.theme_name == "dark"
    dark_text = screen.canvas.color("text")
    cached = len(screen.canvas._text_cache)
    assert cached > 0, "chu phai duoc cache lai"
    screen.service.settings["theme"] = "light"
    screen._dirty = True
    draw(screen)
    assert screen.canvas.theme_name == "light"
    assert screen.canvas.color("text") != dark_text, "light phai khac mau chu"
    assert len(screen.canvas._text_cache) < cached + 60, \
        "doi theme phai xoa cache chu cu (mau khac)"


def test_every_option_row_is_grouped_and_drawn():
    screen = make_screen()
    screen._goto_page("settings")
    screen.page_anim.jump(1.0)
    grouped = set()
    for _title, keys in app.GROUP:
        grouped.update(keys)
    for _label, key, _choices in screen.options:
        if key is None:
            continue
        assert key in grouped, "muc %s chua nam vao nhom nao" % key
    # Ve tung muc mot va khong duoc loi
    for index in range(len(screen.options)):
        screen.setting_index = index
        screen._dirty = True
        draw(screen)


def test_nothing_draws_outside_the_screen():
    """Khong duoc co dai den chiem khung hinh (letterbox la loi cu)."""
    for theme in ("dark", "light"):
        for page in ("chat", "settings"):
            screen = make_screen(theme, history=[{"role": "U", "text": "xin chào"},
                                                 {"role": "A", "text": "chào bạn"}])
            if page == "settings":
                screen._goto_page("settings")
                screen.page_anim.jump(1.0)
            state = draw(screen)
            for x, y, w, h in state["rects"]:
                assert x >= -2 and y >= -2, "%s/%s: ve ngoài trái/trên: %r" % (theme, page, (x, y))
                assert x + w <= screen.width + 2, \
                    "%s/%s: tran mep phai: %r > %d" % (theme, page, x + w, screen.width)
                assert y + h <= screen.height + 2, \
                    "%s/%s: tran mep duoi: %r > %d" % (theme, page, y + h, screen.height)


def test_text_is_cached_not_re_rendered_every_frame():
    """Ve lai 20 khung: so texture moi tao phai dung lai (khong phai 20 lan)."""
    screen = make_screen("dark", history=[{"role": "U", "text": "thử một hai ba"}])
    reset_state()
    screen.draw()
    after_first = len(sdl2.state["created"])
    assert after_first > 0, "khung dau phai render chu"
    for _ in range(20):
        screen._dirty = True
        screen.draw()
    assert len(sdl2.state["created"]) == after_first, \
        "khong duoc render lai chu moi khung ve (%d -> %d)" % (
            after_first, len(sdl2.state["created"]))


def test_logical_size_is_not_used():
    """Khong con SDL_RenderSetLogicalSize -> het letterbox tren 1024x768."""
    source = (APP / "app.py").read_text(encoding="utf-8")
    code = [line for line in source.splitlines()
            if "SDL_RenderSetLogicalSize" in line and not line.lstrip().startswith("#")]
    assert not code, "dung logical size se tao hai dai den tren man hinh 1024x768: %r" % code


def test_activation_and_awaiting_pages_render():
    screen = make_screen()
    screen.service.activation_code = "123456"
    screen.service.activated = False
    draw(screen)
    screen.service.activation_code = ""
    screen.service.activated = False
    screen.service.awaiting_new_code = True
    draw(screen)


def test_unlink_confirm_overlay_renders():
    screen = make_screen()
    screen._goto_page("settings")
    screen.page_anim.jump(1.0)
    screen.confirm_unlink = True
    draw(screen)


def test_ota_toast_animates_in():
    screen = make_screen()
    screen.ota_notice = "ĐÃ CẬP NHẬT LÊN v9.9.9 - MỞ LẠI APP ĐỂ DÙNG"
    draw(screen)
    screen.toast_anim.jump(1.0)
    screen._dirty = True
    draw(screen)


def test_small_and_large_screens_stay_inside_bounds():
    for width, height in ((1024, 768), (1280, 720), (800, 480), (1024, 600)):
        screen = make_screen("light", width=width, height=height,
                             history=[{"role": "A", "text": "một câu trả lời khá dài " * 3}])
        state = draw(screen)
        for x, y, w, h in state["rects"]:
            assert x >= -2 and y >= -2, "%dx%d: %r" % (width, height, (x, y))
            assert x + w <= width + 2 and y + h <= height + 2, \
                "%dx%d tran man hinh: %r" % (width, height, (x + w, y + h))


def test_scroll_and_history_changes_redraw():
    screen = make_screen("dark", history=[{"role": "U", "text": "một"},
                                         {"role": "A", "text": "hai"}])
    draw(screen)
    screen._dirty = False
    draw(screen)  # khong doi gi -> draw() co the bo qua khung
    screen.service.history.append({"role": "U", "text": "ba"})
    screen._dirty = True
    draw(screen)


def main():
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print("%d UI tests passed" % len(tests))


if __name__ == "__main__":
    main()