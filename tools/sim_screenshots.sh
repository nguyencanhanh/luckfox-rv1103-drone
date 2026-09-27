#!/usr/bin/env bash
# Chup anh man hinh mo phong cho README: lai drone qua POST /input cua simulator/server.py
# roi chup trang 3D (che do ?watch, khong gui input) bang Chrome headless.
#
#   make -C simulator            # can build/libsim
#   tools/sim_screenshots.sh     # anh -> docs/img/sim/*.jpg
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/docs/img/sim"
PORT=8799
URL="http://127.0.0.1:$PORT"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
mkdir -p "$OUT"

python3 "$ROOT/simulator/server.py" --port $PORT >/dev/null 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null' EXIT
for _ in $(seq 20); do curl -s -o /dev/null "$URL/" && break; sleep 0.3; done

post() { curl -s -X POST -H 'Content-Type: application/json' -d "$1" "$URL/input"; }
shot() {                                   # shot <ten> <camera 0|1|2>
	local tmp="$OUT/.$1.png"
	timeout 60 "$CHROME" --headless=new --use-angle=swiftshader --enable-unsafe-swiftshader \
		--hide-scrollbars --window-size=1400,820 --timeout=5000 --screenshot="$tmp" \
		"$URL/?watch&cam=$2" >/dev/null 2>&1 || true
	sips -s format jpeg -s formatOptions 82 "$tmp" --out "$OUT/$1.jpg" >/dev/null
	rm -f "$tmp"
	echo "  $OUT/$1.jpg"
}
take_off() {                               # calibrate, arm, climb, hold height
	post '{"reset":1}'; sleep 1.8
	post '{"arm":1,"throttle":0,"mode":0}'; sleep 0.3
	post '{"arm":1,"throttle":0.62,"mode":0}'; sleep "${1:-1.0}"
	post '{"arm":1,"throttle":0.5,"mode":1}'; sleep 1.5
}

echo "==> chup anh mo phong"
# 1. bat ARM bi tu choi: ga dang cao
post '{"reset":1}'; sleep 1.8
post '{"arm":0,"throttle":0.4,"mode":0}'; sleep 0.3
post '{"arm":1,"throttle":0.4,"mode":0}'; sleep 0.5
shot 01_arm_refused 0

# 2. giu do cao, bay toi cham, camera duoi theo
take_off 1.0
post '{"arm":1,"throttle":0.5,"mode":1,"pitch":0.3}'; sleep 1.5
shot 02_alt_hold_chase 0

# 3. vong trai trong gio 6 m/s
post '{"arm":1,"throttle":0.5,"mode":1,"pitch":0.25,"roll":-0.35,"yaw":-0.3,"wind":6}'; sleep 2
shot 03_turn_in_wind 0

# 4. nguoi dung duoi dat nhin len (cat canh lai cho gan bai dap)
take_off 1.2
post '{"arm":1,"throttle":0.5,"mode":1,"roll":0.12,"yaw":0.2}'; sleep 0.2
shot 04_ground_view 1

# 5. FPV
post '{"arm":1,"throttle":0.5,"mode":1,"pitch":0.45,"yaw":0.15}'; sleep 1
shot 05_fpv 2

# 6. mat song RC: failsafe tu ha canh
take_off 1.4
post '{"arm":1,"throttle":0.5,"mode":1,"link_cut":1}'; sleep 0.5
shot 06_failsafe_landing 0
echo "==> xong"
