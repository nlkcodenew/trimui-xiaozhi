#!/bin/sh
UP=$(cut -d. -f1 /proc/uptime 2>/dev/null)
MEM=$(awk '/MemAvailable/{print $2}' /proc/meminfo 2>/dev/null)
LOAD=$(cut -d' ' -f1 /proc/loadavg 2>/dev/null)
printf '{"uptime_seconds":%s,"mem_available_kb":%s,"load":"%s"}\n' "${UP:-0}" "${MEM:-0}" "${LOAD:-0}"
