"""Mock-based tests for the NLK boot logo intro in app.py.

No SDL hardware needed: sdl2/sdl2.sdlttf are stubbed before importing app.
"""
import ctypes
import sys
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))


class FakeEvent(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int)]


def make_sdl2():
    mod = ModuleType("sdl2")
    mod.SDL_QUIT = 256
    mod.SDL_KEYDOWN = 768
    mod.SDL_CONTROLLERBUTTONDOWN = 1617
    mod.SDL_JOYBUTTONDOWN = 1539
    mod.SDL_JOYHATMOTION = 1540
    mod.SDL_Event = FakeEvent
    mod.state = {"present": 0, "blits": 0, "created": [], "destroyed": [],
                 "clears": 0, "delays": 0}
    mod.event_queue = []

    class Rect:
        def __init__(self, x, y, w, h):
            self.x, self.y, self.w, self.h = x, y, w, h

    class Color:
        def __init__(self, *args):
            self.args = args

    mod.SDL_Rect = Rect
    mod.SDL_Color = Color

    class SurfaceContents:
        def __init__(self, w=100, h=150):
            self.w, self.h = w, h

    class Surface:
        def __init__(self, w=100, h=150):
            self.contents = SurfaceContents(w, h)

    mod.Surface = Surface

    def poll(ptr):
        if not mod.event_queue:
            return 0
        code = mod.event_queue.pop(0)
        ev = ctypes.cast(ptr, ctypes.POINTER(FakeEvent)).contents
        ev.type = code
        return 1

    def create_texture(renderer, surface):
        token = object()
        mod.state["created"].append(token)
        return token

    def destroy_texture(texture):
        mod.state["destroyed"].append(texture)

    def render_copy(renderer, texture, src, dst):
        mod.state["blits"] += 1
        return 0

    def present(renderer):
        mod.state["present"] += 1

    def clear(renderer):
        mod.state["clears"] += 1
        return 0

    def delay(ms):
        mod.state["delays"] += 1

    mod.SDL_PollEvent = poll
    mod.SDL_CreateTextureFromSurface = create_texture
    mod.SDL_DestroyTexture = destroy_texture
    mod.SDL_RenderCopy = render_copy
    mod.SDL_RenderPresent = present
    mod.SDL_RenderClear = clear
    mod.SDL_Delay = delay
    mod.SDL_SetRenderDrawColor = lambda *a: 0
    mod.SDL_FreeSurface = lambda *a: None
    return mod


def make_ttf(sdl2):
    mod = ModuleType("sdl2.sdlttf")
    mod.TTF_RenderUTF8_Blended = lambda font, text, color: sdl2.Surface()
    mod.TTF_OpenFont = lambda path, size: object()
    mod.TTF_CloseFont = lambda font: None
    mod.TTF_Init = lambda: 0
    mod.TTF_Quit = lambda: None
    return mod


sdl2 = make_sdl2()
sys.modules["sdl2"] = sdl2
sys.modules["sdl2.sdlttf"] = make_ttf(sdl2)

import app  # noqa: E402


def make_screen(intro=True):
    service = SimpleNamespace(settings={"intro": intro, "theme": "dark",
                                        "language": "vi"})
    screen = app.Screen(service)
    screen.renderer = object()
    return screen


def reset():
    sdl2.state.update({"present": 0, "blits": 0, "created": [], "destroyed": [],
                       "clears": 0, "delays": 0})
    sdl2.event_queue.clear()


def with_giant(screen, size=None):
    """Font giant hien nay giu rieng (intro_font); mac dinh size 132 cua
    Music-Player tren man hinh chuan 1024x768."""
    screen.fonts = {}
    screen.intro_font = object()
    screen.intro_font_size = size or int(app.INTRO_REF_GIANT)
    return screen


def test_intro_presents_and_frees_textures():
    reset()
    screen = with_giant(make_screen())
    screen.play_intro(duration=0.05)
    assert sdl2.state["present"] > 0, "every intro frame must Present"
    assert sdl2.state["blits"] > 0, "pre-rendered glyphs must be blitted"
    assert len(sdl2.state["created"]) == 9, "N/L/K x dark/bright/white"
    assert sorted(map(id, sdl2.state["destroyed"])) == sorted(map(id, sdl2.state["created"])), \
        "all intro textures must be freed"


def test_intro_skip_on_key_frees_textures():
    reset()
    screen = with_giant(make_screen())
    sdl2.event_queue.append(sdl2.SDL_KEYDOWN)
    started = time.monotonic()
    screen.play_intro(duration=30.0)
    assert time.monotonic() - started < 5.0, "any key must skip instantly"
    assert sorted(map(id, sdl2.state["destroyed"])) == sorted(map(id, sdl2.state["created"]))
    assert len(sdl2.state["created"]) == 9


def test_intro_fallback_without_giant_font():
    reset()
    screen = make_screen()
    screen.fonts = {}
    screen.intro_font = None
    screen.intro_font_size = 0
    screen.text = lambda *a, **k: 0  # stub out TTF text path
    screen.play_intro(duration=0.05)  # must not crash
    assert sdl2.state["present"] > 0
    assert sdl2.state["created"] == [] and sdl2.state["destroyed"] == []


def test_intro_fallback_passes_int_coordinates():
    """Regression: SDL_Rect cua pysdl2 khong nhan float. Nhanh fallback ve
    bang text thuong, toa do phai int - truoc day app crash ngay khi mo."""
    screen = make_screen()
    screen.fonts = {}
    screen.intro_font = None
    screen.intro_font_size = 0
    seen = []

    def fake_text(value, x, y, size=24, color=None, max_width=1140):
        seen.append((x, y))
        return y

    screen.text = fake_text
    screen._render_intro_frame(1.0, glyphs=None)
    assert seen, "fallback must draw letters"
    for x, y in seen:
        assert isinstance(x, int) and isinstance(y, int), \
            "SDL_Rect needs int, got %r" % (type(x),)


def test_intro_scale_follows_actual_font_size():
    """Neu SDL_ttf tu choi co chu lon, moi hieu ung phai scale theo co chu
    that su mo duoc de hinh anh giong het."""
    screen = with_giant(make_screen(), size=100)
    assert abs(screen._intro_scale() - 100 / app.INTRO_REF_GIANT) < 1e-9


def test_intro_disabled_setting():
    reset()
    screen = make_screen(intro=False)
    with_giant(screen)
    screen.play_intro(duration=0.05)
    assert sdl2.state["present"] == 0
    assert sdl2.state["created"] == []


def test_intro_layout_uses_logical_space_not_screen_size():
    """Regression: intro ve trong logical 1280x720 (SDL_RenderSetLogicalSize).
    Tinh toa do bang kich thuoc man hinh that (1024x768 tren Brick) lam chu
    lech khoi tam va nho hon - dung la ly do logo "be va lech"."""
    screen = with_giant(make_screen())
    recorded = []
    bright = {("N", "bright"): object(), ("L", "bright"): object(), ("K", "bright"): object()}
    glyphs = {}
    # Be rong chu that cua DejaVu o co chu 132 (do bang PIL), scale theo giant.
    ratios = {"N": 99.0, "L": 74.0, "K": 90.0}
    for letter in "NLK":
        width = int(ratios[letter] * screen._intro_scale())
        for name in ("dark", "bright", "white"):
            glyphs[(letter, name)] = (bright[(letter, "bright")] if name == "bright"
                                      else object(), width, 160)
    screen._intro_blit = lambda texture, x, y, w, h: recorded.append((texture, x, y, w, h))
    # progress = 1.0: chu da bay len va dung choi, khong con sweep.
    screen._render_intro_glyphs(1.0, glyphs)
    # Chi do 3 chu chinh; glow lech +4*k nen khong tinh vao bounding box.
    letters = [item for item in recorded if item[0] in bright.values()]
    assert len(letters) == 3, "3 letters must be blitted, got %d" % len(letters)
    left = min(x for _t, x, _y, _w, _h in letters)
    right = max(x + w for _t, x, _y, w, _h in letters)
    center_x = (left + right) / 2.0
    assert abs(center_x - app.LOGICAL_W / 2.0) < 2.0, \
        "logo must be centered in logical space, got center %.1f" % center_x
    # Ty le chu phai Y HET Music-Player tren man hinh chuan: giant 132 ->
    # k = 1.0, khong phong to, khong thu nho.
    assert abs(screen._intro_scale() - 1.0) < 1e-9, \
        "giant phai 132 tren man hinh chuan, got k=%.3f" % screen._intro_scale()
    assert screen._intro_fit([99, 74, 90], 99 + 74 + 90 + 60) == 1.0, \
        "fit phai = 1 tren man hinh chuan (khong phong to)"
    # Man hinh nho: chi co xuong, khong tran (fit <= 1).
    tiny = app.Screen.__new__(app.Screen)
    tiny.intro_font_size = 132
    assert tiny._intro_fit([99, 74, 90], 2000) <= 1.0


def test_intro_giant_matches_music_player_formula():
    """giant = 132 * max(0.75, min(w/1024, h/768)) - dung cong thuc cu
    Music-Player de chu co giong het tren may Brick (1024x768 -> 132)."""
    for width, height, expected_scale in ((1024, 768, 1.0), (1280, 720, 0.9375),
                                          (640, 480, 0.75), (1920, 1080, 1.40625)):
        scale = max(0.75, min(width / 1024.0, height / 768.0))
        assert abs(scale - expected_scale) < 1e-6, (width, height, scale)
        assert max(24, int(round(app.INTRO_REF_GIANT * scale))) == int(round(132 * expected_scale))


def test_intro_spread_matches_music_player():
    screen = with_giant(make_screen())
    # Spread 4..30 (don via chuan), k = 1.0 tren man hinh chuan.
    assert abs(screen._intro_spread(0.0) - 4.0) < 1e-6
    assert abs(screen._intro_spread(1.0) - 30.0) < 1e-6
    assert abs(screen._intro_spread(0.275) - 23.5) < 1e-6, "ease-out tai progress/0.55 = 0.5"


def test_intro_setting_registered():
    from service import DEFAULTS
    assert DEFAULTS.get("intro") is True
    screen = make_screen()
    row = [r for r in screen.options if r[1] == "intro"]
    assert row and row[0][2] == [True, False]


if __name__ == "__main__":
    test_intro_presents_and_frees_textures()
    test_intro_skip_on_key_frees_textures()
    test_intro_fallback_without_giant_font()
    test_intro_fallback_passes_int_coordinates()
    test_intro_scale_follows_actual_font_size()
    test_intro_disabled_setting()
    test_intro_layout_uses_logical_space_not_screen_size()
    test_intro_giant_matches_music_player_formula()
    test_intro_spread_matches_music_player()
    test_intro_setting_registered()
    print("intro tests passed")
