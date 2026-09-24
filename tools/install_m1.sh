#!/bin/bash
# install_m1.sh — dua cau hinh Linux cua Milestone 1 vao SDK (volume luckfox-src):
#   - linux/dts/rv1103g-luckfox-pico-mini-m1.dts  -> kernel/arch/arm/boot/dts/
#   - BoardConfig moi = BoardConfig Mini goc, chi doi RK_KERNEL_DTS
# Sau do chon board bang ./run.sh board, build bang ./run.sh build (xem docs/MILESTONE1.md).
# Khong sua file nao cua SDK goc; chay lai bao nhieu lan cung duoc.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="luckfox-build:22.04"
VOLUME="luckfox-src"
SRC_CFG="BoardConfig-SPI_NAND-Buildroot-RV1103_Luckfox_Pico_Mini-IPC.mk"
M1_CFG="BoardConfig-SPI_NAND-Buildroot-RV1103_Luckfox_Pico_Mini_M1-IPC.mk"

docker info >/dev/null 2>&1 || { echo "Docker engine chua chay (orb start)" >&2; exit 1; }

docker run --rm --platform linux/amd64 -v "$VOLUME":/work -v "$ROOT/linux/dts":/dts:ro \
	-w /work/luckfox-pico "$IMAGE" bash -c '
	set -e
	SRC_CFG="$1"; M1_CFG="$2"
	C=project/cfg/BoardConfig_IPC
	cp /dts/rv1103g-luckfox-pico-mini-m1.dts sysdrv/source/kernel/arch/arm/boot/dts/
	sed "s/^export RK_KERNEL_DTS=.*/export RK_KERNEL_DTS=rv1103g-luckfox-pico-mini-m1.dts/" \
		"$C/$SRC_CFG" > "$C/$M1_CFG"
	diff "$C/$SRC_CFG" "$C/$M1_CFG" || true
	ls -la "$C/$M1_CFG" sysdrv/source/kernel/arch/arm/boot/dts/rv1103g-luckfox-pico-mini-m1.dts
' _ "$SRC_CFG" "$M1_CFG"

echo
echo "Da cai. Buoc tiep: ./run.sh board  (chon ...Mini_M1-IPC), roi ./run.sh build"
