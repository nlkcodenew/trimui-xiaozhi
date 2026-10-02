#!/bin/sh

SDCARD_PATH="${SDCARD_PATH:-/mnt/SDCARD}"
export SDCARD_PATH
case "$0" in
    /*) APP="${0%/*}" ;;
    */*) APP="$(cd "${0%/*}" 2>/dev/null && pwd)" ;;
    *) APP="$SDCARD_PATH/Apps/Trimui-XiaoZhi" ;;
esac
# Ten thu muc legacy (ban 0.1.0 phat hanh voi ten khac) van chay duoc.
[ -d "$APP" ] || APP="$SDCARD_PATH/Apps/Trimui-XiaoZhi"
[ -d "$APP" ] || APP="$SDCARD_PATH/Apps/TrimuiXiaozhi"

mkdir -p "$APP/logs" "$APP/data" 2>/dev/null
if [ -n "$LOGS_PATH" ] && [ -d "$LOGS_PATH" ]; then
    BOOT_LOG="$LOGS_PATH/Trimui-Xiaozhi.txt"
elif [ -d "$SDCARD_PATH/Logs" ]; then
    BOOT_LOG="$SDCARD_PATH/Logs/Trimui-Xiaozhi.txt"
else
    BOOT_LOG="$APP/Trimui-Xiaozhi-boot.log"
fi
SESSION_LOG="$APP/logs/launcher.log"
{
    echo "=== Trimui Xiaozhi launcher ==="
    date 2>/dev/null || true
    echo "app=$APP"
    echo "sdcard=$SDCARD_PATH"
} >> "$BOOT_LOG" 2>&1
if ! cd "$APP" 2>> "$BOOT_LOG"; then
    echo "Cannot enter app directory" >> "$BOOT_LOG"
    exit 1
fi

export PATH="$SDCARD_PATH/System/bin:$PATH"
export LD_LIBRARY_PATH="$APP/libs:$SDCARD_PATH/System/lib:/usr/trimui/lib:$SDCARD_PATH/App/PyUI/dll-mali:$SDCARD_PATH/App/PyUI/dll:/usr/lib64:/usr/lib:/lib:${LD_LIBRARY_PATH:-}"
export PYSDL2_DLL_PATH="$APP/libs:$SDCARD_PATH/System/lib:/usr/trimui/lib:/usr/lib64:/usr/lib:$SDCARD_PATH/App/PyUI/dll"
export PYTHONUNBUFFERED=1
echo "PYSDL2_DLL_PATH=$PYSDL2_DLL_PATH" >> "$BOOT_LOG"

find_python() {
    for candidate in "$(command -v python3 2>/dev/null)" \
        "$SDCARD_PATH/System/bin/python3" \
        "$SDCARD_PATH/Apps/PortMaster/PortMaster/exlibs/python3" \
        /usr/bin/python3 /usr/local/bin/python3; do
        [ -n "$candidate" ] && [ -f "$candidate" ] || continue
        [ -x "$candidate" ] || chmod +x "$candidate" 2>/dev/null
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}
PYTHON="$(find_python)"
if [ -z "$PYTHON" ]; then
    echo "Python 3.8+ not found" >> "$BOOT_LOG"
    exit 1
fi
echo "python=$PYTHON" >> "$BOOT_LOG"
chmod +x "$APP/bin/xiaozhi-core" "$APP/system_status.sh" 2>> "$BOOT_LOG" || true
echo "starting app.py" >> "$BOOT_LOG"
"$PYTHON" -u "$APP/app.py" >> "$SESSION_LOG" 2>&1
STATUS=$?
echo "app_exit=$STATUS" >> "$BOOT_LOG"
if [ "$STATUS" -ne 0 ]; then
    tail -n 60 "$SESSION_LOG" >> "$BOOT_LOG" 2>/dev/null || true
fi
exit "$STATUS"
