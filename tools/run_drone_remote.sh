#!/usr/bin/env bash
# Dieu khien tu xa tren board that, khong motor:
#   MCU: luckfox_mini-FC-NONE (code bay + SIM_SENSOR, nhan RC qua IPC, gui telemetry)
#   Linux: rc-bridge --devmem (RC tu tram mat dat qua UDP 7700; ELRS khi co --uart)
#   Camera: rkipc cua firmware (RTSP rtsp://BOARD/live/1)
# Sau do tren Mac: python3 ground/gcs.py --drone 172.32.0.93 --video rtsp://172.32.0.93/live/1
#
#   tools/build_mcu.sh luckfox_mini-FC-NONE && tools/build_linux_tools.sh   # 1 lan
#   tools/run_drone_remote.sh          # nap + chay
#   tools/run_drone_remote.sh stop     # dung rc-bridge va MCU
#
# Yeu cau: board chay firmware Linux cua Milestone 1 (reserved-memory mcu@1800000).
# Khong cham ESC/motor: firmware nay chua co dau ra PWM.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
B="${B:-root@172.32.0.93}"
IP="${B#*@}"
BIN="$ROOT/out/mcu/luckfox_mini-FC-NONE/rtthread.bin"
TOOLS="$ROOT/out/linux-tools"
die() { echo "[x] $*" >&2; exit 1; }
say() { echo "==> $*"; }

if ssh -o ConnectTimeout=3 -o BatchMode=yes "$B" true 2>/dev/null; then
	run() { ssh "$B" "$@"; }
	put() { cat "$1" | ssh "$B" "cat > $2"; }
elif adb get-state >/dev/null 2>&1; then
	run() { adb shell "$@"; }
	put() { adb push "$1" "$2" >/dev/null; }
else
	die "khong thay board (SSH $B / ADB). Cam USB-C cua board roi chay lai."
fi

if [ "${1:-}" = "stop" ]; then
	run 'killall rc-bridge 2>/dev/null; /tmp/mcu-tool stop' || true
	say "da dung rc-bridge va MCU"
	exit 0
fi

[ -f "$BIN" ] || die "chua build: tools/build_mcu.sh luckfox_mini-FC-NONE"
[ -f "$TOOLS/rc-bridge" ] && [ -f "$TOOLS/mcu-tool" ] || die "chua build: tools/build_linux_tools.sh"

# vung nho MCU nhu MILESTONE1.md buoc 3
reg=$(run 'hexdump -v -e "8/1 \"%02x\"" /proc/device-tree/reserved-memory/mcu@1800000/reg' 2>/dev/null | tr -d '\r' || true)
[ "$reg" = "0180000000040000" ] || die "reserved-memory mcu@1800000 khong dung ('${reg:-trong}'): can firmware Linux M1"

put "$BIN" /tmp/rtthread_fc.bin
put "$TOOLS/mcu-tool" /tmp/mcu-tool
put "$TOOLS/rc-bridge" /tmp/rc-bridge
run 'chmod +x /tmp/mcu-tool /tmp/rc-bridge; killall rc-bridge 2>/dev/null; true'
run '/tmp/mcu-tool load /tmp/rtthread_fc.bin'
sleep 2
run 'nohup /tmp/rc-bridge --devmem --udp 7700 -v > /tmp/rc-bridge.log 2>&1 &'
sleep 1
run 'head -3 /tmp/rc-bridge.log' | tr -d '\r'
if run 'pidof rkipc' >/dev/null 2>&1; then
	say "camera: rkipc dang chay, RTSP rtsp://$IP/live/0 (2304x1296) va /live/1 (704x576)"
else
	echo "[!] rkipc khong chay: khong co video (firmware stock khoi dong no bang RkLunch.sh)"
fi
say "MCU + rc-bridge dang chay. Tren Mac:"
echo "    python3 ground/gcs.py --drone $IP --video rtsp://$IP/live/1"
echo "    mo http://127.0.0.1:8780"
echo "  Log: ssh $B 'tail -f /tmp/rc-bridge.log' ; ssh $B /tmp/mcu-tool log"
