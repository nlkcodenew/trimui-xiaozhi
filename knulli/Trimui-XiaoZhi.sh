#!/bin/bash
# Trimui-XiaoZhi.sh — launcher Tools trên Knulli.
# Payload tại /userdata/system/trimui-xiaozhi (bản phát hành v0.2.4 của repo
# TrimuiXiaozhi). launch.sh của app tự suy APP từ $0 nên trỏ thẳng là chạy;
# vòng OTA nền trong launch.sh đã redirect FD vào log riêng (an toàn pipe
# của emulatorlauncher — xem PORTING-NOTES.md mục 1).
APP=/userdata/system/trimui-xiaozhi

if [ ! -e /mnt/SDCARD ]; then
  mkdir -p /mnt 2>/dev/null
  ln -sfn /userdata /mnt/SDCARD 2>/dev/null
fi

exec sh "$APP/launch.sh"
