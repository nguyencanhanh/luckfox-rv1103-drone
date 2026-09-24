#!/bin/bash
# extract_sdk_ref.sh — trich DTS RV1103/RV1106 tu tarball SDK ra linux/dts/sdk/ de doc (khong nam trong git)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
T=$(mktemp -d)
tar -xzf "$ROOT/dl/luckfox-pico-main.tar.gz" -C "$T" \
	--include='*/kernel/arch/arm/boot/dts/rv1103*' --include='*/kernel/arch/arm/boot/dts/rv1106*'
mkdir -p "$ROOT/linux/dts/sdk"
cp "$(dirname "$(find "$T" -name rv1106.dtsi)")"/* "$ROOT/linux/dts/sdk/"
rm -rf "$T"
ls "$ROOT/linux/dts/sdk" | wc -l
