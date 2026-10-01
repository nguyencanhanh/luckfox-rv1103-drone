#!/bin/bash
# build_linux_tools.sh — build cac cong cu Linux cua repo (mcu-tool, rc-bridge) bang
# toolchain ARM cua SDK (tools/linux/toolchain/arm-rockchip830-linux-uclibcgnueabihf).
# Ket qua: out/linux-tools/mcu-tool, out/linux-tools/rc-bridge

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
	$CC -std=gnu99 -O2 -Wall -Wextra -Werror -o /out/rc-bridge /src/rc-bridge/rc_bridge.c \
		/src/rc-bridge/uart.c /shared/ipc/fc_ipc.c /shared/rc/crsf.c -lrt
	file /out/mcu-tool /out/rc-bridge
'
ls -la "$ROOT/out/linux-tools/"
