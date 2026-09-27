#!/usr/bin/env bash
# Chay flight core tren HPMCU (board luckfox_mini-FC-NONE): fc_tick() 1 kHz voi SIM_SENSOR
# va mo hinh quad chay ngay tren MCU, do so chu ky CPU cua code bay. Khong cham motor/ESC.
#
#   tools/build_mcu.sh luckfox_mini-FC-NONE     # 1 lan
#   tools/run_fc_mcu.sh [giay]                  # mac dinh 60 s, log -> logs/fc_mcu_<thoi gian>.txt
#
# Duong ket noi: SSH qua USB-ECM (B=root@172.32.0.93) neu vao duoc, khong thi ADB.
# Yeu cau: board dang chay firmware Linux cua Milestone 1 (co reserved-memory mcu@1800000).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SECS="${1:-60}"
B="${B:-root@172.32.0.93}"
BIN="$ROOT/out/mcu/luckfox_mini-FC-NONE/rtthread.bin"
TOOL="$ROOT/out/linux-tools/mcu-tool"
LOG="$ROOT/logs/fc_mcu_$(date +%Y%m%d_%H%M%S).txt"

die() { echo "[x] $*" >&2; exit 1; }
say() { echo "==> $*"; }
[ -f "$BIN" ] || die "chua build: tools/build_mcu.sh luckfox_mini-FC-NONE"
[ -f "$TOOL" ] || die "chua build: tools/build_linux_tools.sh"

if ssh -o ConnectTimeout=3 -o BatchMode=yes "$B" true 2>/dev/null; then
	say "ket noi SSH $B"
	run() { ssh "$B" "$@"; }
	put() { cat "$1" | ssh "$B" "cat > $2"; }
elif adb get-state >/dev/null 2>&1; then
	say "ket noi ADB"
	run() { adb shell "$@"; }
	put() { adb push "$1" "$2" >/dev/null; }
else
	die "khong thay board (SSH $B va ADB deu khong vao duoc). Cam USB-C cua board roi chay lai."
fi

# Kiem tra vung nho MCU nhu MILESTONE1.md buoc 3: sai thi khong nap
reg=$(run 'hexdump -v -e "8/1 \"%02x\"" /proc/device-tree/reserved-memory/mcu@1800000/reg' 2>/dev/null | tr -d '\r' || true)
[ "$reg" = "0180000000040000" ] || die "reserved-memory mcu@1800000 khong dung (doc duoc: '${reg:-trong}'). Board phai chay firmware Linux M1."
run 'cat /proc/iomem' | tr -d '\r' | grep -qi "01800000-0183ffff : System RAM" && die "0x01800000 nam trong System RAM: dung lai"
say "vung MCU 0x01800000 + 256 KB da duoc giu rieng"

put "$BIN" /tmp/rtthread_fc.bin
put "$TOOL" /tmp/mcu-tool
run 'chmod +x /tmp/mcu-tool && /tmp/mcu-tool load /tmp/rtthread_fc.bin'
say "MCU dang chay flight core, cho ${SECS} s ..."
sleep "$SECS"
run '/tmp/mcu-tool log' | tr -d '\r' > "$LOG"
run '/tmp/mcu-tool status' | tr -d '\r' >> "$LOG" || true
say "log: $LOG"
grep "^fc:" "$LOG" | tail -12
echo
echo "MCU van chay. Dung: ssh $B /tmp/mcu-tool stop   (hoac adb shell /tmp/mcu-tool stop)"
