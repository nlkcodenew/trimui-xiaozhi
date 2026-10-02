#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gate truoc khi release Trimui-XiaoZhi: file cai dat, OTA, ZIP, secret."""
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
FAIL = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        FAIL.append(msg)


def main():
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip().strip("vV")
    check(bool(version), "VERSION co gia tri (%s)" % version)

    for rel in ("app.py", "service.py", "remote.py", "launch.sh", "config.json",
                "icon.png", "background.png", "system_status.sh", "ota-update.sh",
                "bin/xiaozhi-core", "assets/font.ttf", "certs/cacert.pem"):
        check((ROOT / rel).is_file(), "%s ton tai" % rel)

    core = ROOT / "bin" / "xiaozhi-core"
    if core.is_file():
        magic = core.read_bytes()[:20]
        check(magic[:4] == b"\x7fELF", "xiaozhi-core la ELF")
        check(int.from_bytes(magic[18:20], "little") == 0xB7,
              "xiaozhi-core la AArch64 (EM=183)")

    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    check(config.get("label") == "Trimui-XiaoZhi",
          "config.json label = %r" % config.get("label"))
    check(config.get("launch") == "launch.sh", "config.json tro dung launch.sh")

    ota = (ROOT / "ota-update.sh").read_text(encoding="utf-8", errors="replace")
    check('nlkcodenew/trimui-xiaozhi' in ota, "OTA tro toi repo nay")
    check('case "$rel" in data/*|logs/*' in ota, "OTA khong ghi de data/ logs/")
    check('rm -rf "$TMPD" "$MANIFEST_JSON" "$LIST"' in ota, "OTA don sach staging")
    # BusyBox thieu `sort -V`; chi chan khi script that su goi lenh do
    # (comment giai thich duoc phep).
    uses_sort_v = any(re.match(r"\s*(?:sort\s+-V|\|\s*sort\s+-V)", line)
                      for line in ota.splitlines())
    check(not uses_sort_v, "OTA khong chay `sort -V` (BusyBox co the thieu)")

    launch = (ROOT / "launch.sh").read_text(encoding="utf-8", errors="replace")
    check("ota-update.sh\" --apply" in launch, "launch.sh chay OTA nen")
    check("XIAOZHI_NO_OTA" in launch, "launch.sh cho phep tat OTA")

    app = (ROOT / "app.py").read_text(encoding="utf-8", errors="replace")
    check("def poll_ota(self):" in app, "app.py doc .ota-status")
    check("Trimui-XiaoZhi v%s" in app, "app.py hien ten + version dung cach")

    for test in ("tests/test_intro.py", "tests/test_ota.py"):
        proc = subprocess.run([sys.executable, test], cwd=str(ROOT),
                              capture_output=True, text=True)
        check(proc.returncode == 0, "%s pass" % test)
        if proc.returncode != 0:
            print(proc.stdout[-2000:])
            print(proc.stderr[-2000:])

    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    check(manifest.get("version") == version,
          "manifest version khop VERSION (%s)" % manifest.get("version"))
    listed = {item["path"] for item in manifest.get("files", [])}
    for rel in ("ota-update.sh", "app.py", "certs/cacert.pem", "bin/xiaozhi-core"):
        check(rel in listed, "manifest co %s" % rel)
    check(not any(p.startswith(("data/", "logs/", "dist/")) for p in listed),
          "manifest khong chua data/ logs/ dist/")

    zips = sorted(DIST.glob("trimui-xiaozhi-v*.zip")) if DIST.is_dir() else []
    if zips:
        archive = zips[-1]
        expected = "trimui-xiaozhi-v%s.zip" % version
        check(archive.name == expected, "ZIP khop version (%s)" % archive.name)
        names = zipfile.ZipFile(archive).namelist()
        prefix = "Apps/Trimui-XiaoZhi/"
        check(prefix + "launch.sh" in names, "ZIP co launch.sh")
        check(prefix + "ota-update.sh" in names, "ZIP co ota-update.sh")
        check(prefix + "bin/xiaozhi-core" in names, "ZIP co xiaozhi-core")
        check(not any("data/" in n or "logs/" in n for n in names),
              "ZIP khong chua data/ logs/")
        check(not any("secrets" in n for n in names), "ZIP khong chua secret")
        asset = manifest.get("release_asset", {})
        check(asset.get("name") == expected, "manifest release_asset khop")
        check(asset.get("size") == archive.stat().st_size, "manifest release_asset size")
    else:
        print("SKIP kiem tra ZIP (chua chay tools/make_release.py)")

    if FAIL:
        print("FAILED: %d" % len(FAIL))
        return 1
    print("ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())