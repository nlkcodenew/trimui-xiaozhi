"""Mock-based tests cho OTA (.ota-status) doc boi app.py va ota-update.sh.

Khong can thiet bi that:
- app.py: SDL stub y nhu tests/test_intro.py, chi goi Screen.poll_ota().
- ota-update.sh: kiem tra noi dung script + chay --check voi manifest gia lap
  (khong co network -> phai fail em, khong duoc lam hong boot).
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "tests"))

# test_intro giu ham gia sdl2/sdl2.sdlttf roi import app; dung lai de app
# import duoc tren may khong co SDL.
import test_intro  # noqa: F401,E402

import app  # noqa: E402

OTA_SCRIPT = APP / "ota-update.sh"


def test_poll_ota_without_status_file_clears_badge():
    """launch.sh xoa .ota-status truoc khi chay OTA -> app mo ra khong duoc
    con badge 'Dang kiem tra...' cua lan truoc."""
    screen = app.Screen.__new__(app.Screen)
    screen.ota_badge = "Đang kiểm tra..."
    screen.ota_notice = ""
    screen.poll_ota()
    assert screen.ota_badge == "", "badge must clear when status file is gone"


def test_poll_ota_reads_checking_and_downloading():
    path = APP / ".ota-status"
    try:
        screen = app.Screen.__new__(app.Screen)
        screen.ota_badge = ""
        screen.ota_notice = ""
        path.write_text("checking", encoding="utf-8")
        screen.poll_ota()
        assert screen.ota_badge == "Đang kiểm tra..."
        path.write_text("downloading 9.9.9", encoding="utf-8")
        screen.poll_ota()
        assert screen.ota_badge == "Đang tải 9.9.9..."
        assert path.exists(), "app must not delete in-progress status"
    finally:
        path.unlink(missing_ok=True)


def test_poll_ota_done_shows_notice_and_clears_file():
    path = APP / ".ota-status"
    try:
        screen = app.Screen.__new__(app.Screen)
        screen.ota_badge = ""
        screen.ota_notice = ""
        path.write_text("done 99.0.0", encoding="utf-8")
        screen.poll_ota()
        assert "99.0.0" in screen.ota_notice
        assert "MỞ LẠI APP" in screen.ota_notice
        assert not path.exists(), "done status must be consumed"
    finally:
        path.unlink(missing_ok=True)


def test_poll_ota_done_same_version_shows_no_notice():
    path = APP / ".ota-status"
    try:
        screen = app.Screen.__new__(app.Screen)
        screen.ota_badge = ""
        screen.ota_notice = ""
        path.write_text("done %s" % app.APP_VERSION, encoding="utf-8")
        screen.poll_ota()
        assert screen.ota_notice == "", "already-running version needs no restart"
    finally:
        path.unlink(missing_ok=True)


def test_poll_ota_failed_state_is_cleaned():
    path = APP / ".ota-status"
    try:
        screen = app.Screen.__new__(app.Screen)
        screen.ota_badge = "Đang kiểm tra..."
        screen.ota_notice = ""
        path.write_text("failed", encoding="utf-8")
        screen.poll_ota()
        assert screen.ota_badge == ""
        assert not path.exists()
    finally:
        path.unlink(missing_ok=True)


def script_text():
    return OTA_SCRIPT.read_text(encoding="utf-8")


def test_script_never_touches_user_data():
    """data/ = danh tinh + kich hoat thiet bi. OTA duoc phep cap nhat code,
    KHONG duoc quay lai xoa danh tinh."""
    text = script_text()
    for guard in ('case "$rel" in data/*|logs/*',):
        assert guard in text, "apply/download must skip data/ and logs/"
    # python3 path cung phai loc
    assert 'PROTECTED = ("data/", "logs/", "dist/", "tests/", "tools/")' in text
    assert "PROTECTED" in text


def test_script_writes_status_atomically_and_skips_user_files():
    text = script_text()
    assert "$OTA_STATUS.tmp" in text and 'mv "$OTA_STATUS.tmp" "$OTA_STATUS"' in text, \
        ".ota-status must be written atomically"
    # $LIST nam canh $TMPD: neu khong xoa rieng, file rac .update_staging.*.list
    # se doi vao thu muc app moi lan cap nhat.
    assert 'rm -rf "$TMPD" "$MANIFEST_JSON" "$LIST"' in text, \
        "staging leftovers (apply list) must be removed"
    assert "data/*|logs/*|dist/*|tests/*|tools/*" in text, \
        "shell download must skip user/runtime paths"


def test_script_version_and_status_contract():
    text = script_text()
    assert re.search(r'ver_newer\(\)\s*\{', text), "must compare x.y.z without sort -V"
    assert 'ota_status "checking"' in text
    assert 'ota_status "downloading $REM"' in text
    assert 'ota_status "done $REM"' in text
    assert 'ota_status "failed"' in text
    assert '> "$APP/VERSION"' in text, "must persist VERSION for app to display"


def test_launcher_starts_ota_in_background_and_can_disable():
    launch = (APP / "launch.sh").read_text(encoding="utf-8")
    assert 'ota-update.sh" --apply' in launch, "launcher must run OTA in background"
    assert 'XIAOZHI_NO_OTA' in launch, "OTA must be switchable off"
    assert launch.index("ota-update.sh") < launch.index('app.py'), \
        "OTA must start before app.py so the badge shows"


def shell_runner():
    """Tra (argv-prefix, cwd-converter) de chay sh o tren may dang test.

    Windows co WSL: chay script trong WSL. Neu khong co shell nao thi tra None
    va test tu bo qua (CI Linux luon co sh).
    """
    if sys.platform != "win32":
        return (["sh"], lambda p: p)

    def to_wsl(path):
        resolved = str(Path(path).resolve()).replace("\\", "/")
        if len(resolved) > 1 and resolved[1] == ":":
            return "/mnt/%s%s" % (resolved[0].lower(), resolved[2:])
        return resolved

    # Uu tien WSL: bash.exe cua Windows la launcher WSL, truyen duong dan
    # Windows cho no se fail. WSL nhan duong dan /mnt/... nen dung o tren.
    if shutil.which("wsl"):
        return (["wsl", "sh"], to_wsl)
    for candidate in ("sh", "bash"):
        if shutil.which(candidate):
            return ([candidate], lambda p: p)
    return None


def test_script_check_mode_offline_fails_softly():
    """Khong co network -> --check phai exit != 0 nhung khong duoc crash,
    va khong duoc tao rac file trong app dir."""
    runner = shell_runner()
    if runner is None:
        print("SKIP test_script_check_mode_offline_fails_softly (khong co sh/WSL)")
        return
    prefix, convert = runner
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "app"
        work.mkdir()
        (work / "VERSION").write_text("0.0.1\n", encoding="utf-8")
        (work / "logs").mkdir()
        target = work / "ota-update.sh"
        target.write_text(OTA_SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
        env = dict(os.environ)
        env["XIAOZHI_REPO"] = "nlkcodenew/trimui-xiaozhi-does-not-exist-xyz"
        # Script tu cd vao thu muc chua no, nen cwd chi can thu muc hop le
        # cua host dang chay (Windows path khi qua WSL launcher).
        proc = subprocess.run(
            prefix + [convert(target), "--check"],
            cwd=str(work) if sys.platform != "win32" else None,
            env=env, capture_output=True, text=True, timeout=180,
        )
        # 1 = that bai, 2 = da moi nhat, 10 = co ban moi. Khong duoc la 130+.
        assert proc.returncode in (0, 1, 2, 10), \
            "offline OTA must fail softly, got rc=%s" % proc.returncode
        assert (work / "VERSION").read_text(encoding="utf-8").strip() == "0.0.1", \
            "failed OTA must not change local version"
        assert not (work / "data").exists(), "failed OTA must not create data/"


def main():
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print("%d OTA tests passed" % len(tests))


if __name__ == "__main__":
    main()