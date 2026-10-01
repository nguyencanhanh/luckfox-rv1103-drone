#!/bin/bash
# build_mcu.sh — build firmware RT-Thread cho HPMCU (RISC-V SCR1) cua RV1103
# bang dung luong build cua SDK: ./build.sh mcu <board>  (project/build.sh:876-919).
#
#   tools/build_mcu.sh                          board mac dinh: luckfox_mini-HELLO-NONE
#   tools/build_mcu.sh rv1106_evb-SC3338-ADC    build board mau cua Rockchip (nguyen ban)
#
# Board trong mcu/bsp/ cua repo nay duoc chep vao SDK truoc khi build.
# Ket qua: out/mcu/<board>/rtthread.{bin,elf,map}, log: logs/mcu_<board>.log
# Can build SDK truoc it nhat mot lan (./run.sh build) de co volume SDK.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BOARD="${1:-luckfox_mini-HELLO-NONE}"

IMAGE="luckfox-build:22.04"
MCU_IMAGE="luckfox-build:22.04-mcu"
VOLUME="luckfox-src"
BSP=sysdrv/source/mcu/rt-thread/bsp/rockchip/rv1106-mcu

die() { printf '\033[1;31m[x] %s\033[0m\n' "$*" >&2; exit 1; }
say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

docker info >/dev/null 2>&1 || die "Docker engine chua chay (orb start)"
docker image inspect "$IMAGE" >/dev/null 2>&1 || die "Chua co image $IMAGE, chay ./run.sh build truoc"

# SCons khong co trong image build Linux; tao image rieng thay vi sua image goc
if ! docker image inspect "$MCU_IMAGE" >/dev/null 2>&1; then
	say "Tao image $MCU_IMAGE (them scons)"
	docker rm -f mcu-img-tmp >/dev/null 2>&1 || true
	docker run --name mcu-img-tmp --user 0 --platform linux/amd64 "$IMAGE" bash -c \
		'apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends scons'
	docker commit --change 'USER luckfox' mcu-img-tmp "$MCU_IMAGE" >/dev/null
	docker rm mcu-img-tmp >/dev/null
fi

mkdir -p "$ROOT/logs" "$ROOT/out/mcu/$BOARD"
LOG="$ROOT/logs/mcu_${BOARD}.log"

# Board co mcu_region.env thi chay o vung DDR rieng: kiem tra 3 noi khai bao dia chi khop nhau
REGION_ENV="$ROOT/mcu/bsp/$BOARD/mcu_region.env"
LINK_ORIGIN=""
if [ -f "$REGION_ENV" ]; then
	. "$REGION_ENV"
	LINK_ORIGIN="$MCU_LINK_ORIGIN"
	layout=$(sed -n 's/^#define MCU_REGION_BASE *\(0x[0-9a-fA-F]*\)u.*/\1/p' "$ROOT/shared/ipc/mcu_layout.h")
	pstore=$(sed -n 's/^CONFIG_PERSISTENT_RAM_ADDR=//p' "$ROOT/mcu/bsp/$BOARD/defconfig")
	[ $((layout)) = $((MCU_LINK_ORIGIN)) ] || die "mcu_layout.h ($layout) khac mcu_region.env ($MCU_LINK_ORIGIN)"
	[ $((pstore)) = $((MCU_LINK_ORIGIN + 0x3c000)) ] || die "defconfig PERSISTENT_RAM_ADDR ($pstore) phai = origin + 0x3c000"
	say "Vung MCU: $MCU_LINK_ORIGIN (dai $MCU_LINK_LENGTH), log $pstore"
fi

say "Build MCU: $BOARD"
set +e
docker run --rm --platform linux/amd64 -v "$VOLUME":/work -v "$ROOT/mcu":/src:ro \
	-v "$ROOT/shared":/shared:ro -v "$ROOT/simulator":/sim:ro \
	-v "$ROOT/out/mcu/$BOARD":/out -w /work/luckfox-pico "$MCU_IMAGE" bash -c '
	set -e
	BOARD="$1"; BSP="$2"; ORIGIN="$3"
	if [ -d "/src/bsp/$BOARD" ]; then
		rm -rf "$BSP/board/$BOARD"
		cp -r "/src/bsp/$BOARD" "$BSP/board/$BOARD"
		cp /shared/ipc/*.h "$BSP/board/$BOARD/"
		# boards that run the flight core get it as tree/, in the repository layout
		if [ -f "/src/bsp/$BOARD/FLIGHT_CORE" ]; then
			T="$BSP/board/$BOARD/tree"
			mkdir -p "$T/mcu" "$T/shared" "$T/simulator"
			for d in common sensors estimator control mixer failsafe fc link; do
				cp -r "/src/$d" "$T/mcu/"
			done
			cp -r /shared/rc "$T/shared/"
			mkdir -p "$T/shared/ipc" && cp /shared/ipc/fc_ipc.[ch] /shared/ipc/mcu_layout.h "$T/shared/ipc/"
			cp /sim/quad_model.[ch] /sim/sim_sensors.[ch] "$T/simulator/"
		fi
	fi
	[ -d "$BSP/board/$BOARD" ] || { echo "Khong co board $BOARD"; exit 1; }

	# link.lds cua SDK co dinh ORIGIN = 0x40000 (link.lds:5); doi tam roi tra lai
	[ -f "$BSP/link.lds.sdk" ] || cp "$BSP/link.lds" "$BSP/link.lds.sdk"
	cp "$BSP/link.lds.sdk" "$BSP/link.lds"
	trap "cp \"$BSP/link.lds.sdk\" \"$BSP/link.lds\"" EXIT
	if [ -n "$ORIGIN" ]; then
		sed -i "s/ORIGIN = 0x40000, LENGTH = 0x3c000/ORIGIN = $ORIGIN, LENGTH = 0x3c000/" "$BSP/link.lds"
		grep -q "ORIGIN = $ORIGIN," "$BSP/link.lds" || { echo "Khong doi duoc ORIGIN trong link.lds"; exit 1; }
	fi

	./build.sh mcu "$BOARD"
	cp -f "$BSP/rtthread.bin" "$BSP/rtthread.elf" "$BSP/rtthread.map" /out/
' _ "$BOARD" "$BSP" "$LINK_ORIGIN" >"$LOG" 2>&1
code=$?
set -e

[ "$code" = 0 ] || { tail -20 "$LOG"; die "Build MCU loi (ma $code). Log: $LOG"; }
grep -A2 "riscv-none-embed-size" "$LOG" | tail -2
ls -la "$ROOT/images/mcu/$BOARD/"
