#!/bin/bash
# build_linux_tools.sh — build cac cong cu Linux cua repo (hien tai: mcu-tool) bang
# toolchain ARM cua SDK (tools/linux/toolchain/arm-rockchip830-linux-uclibcgnueabihf).
# Ket qua: out/linux-tools/mcu-tool

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="luckfox-build:22.04"
VOLUME="luckfox-src"

docker info >/dev/null 2>&1 || { echo "Docker engine chua chay (orb start)" >&2; exit 1; }
mkdir -p "$ROOT/out/linux-tools"

docker run --rm --platform linux/amd64 -v "$VOLUME":/work:ro -v "$ROOT/linux":/src:ro \
	-v "$ROOT/shared":/shared:ro -v "$ROOT/out/linux-tools":/out "$IMAGE" bash -c '
	set -e
	CC=/work/luckfox-pico/tools/linux/toolchain/arm-rockchip830-linux-uclibcgnueabihf/bin/arm-rockchip830-linux-uclibcgnueabihf-gcc
	$CC -std=gnu11 -O2 -Wall -Wextra -Werror -I/shared/ipc -o /out/mcu-tool /src/mcu-tool/mcu-tool.c
	file /out/mcu-tool
'
ls -la "$ROOT/out/linux-tools/"
