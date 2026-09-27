#!/bin/sh
# Download the vendor material LFX_FC_R1 relies on but that is not ours to
# redistribute: the official Luckfox Pico Mini mechanical data and schematic
# (LuckfoxTECH/Luckfox-Pico-docs, Hardware/; the STEP gives the pin geometry)
# and the component datasheets.  Needs curl, unzip, pdftotext (poppler).
set -e
cd "$(dirname "$0")/vendor"
B=https://raw.githubusercontent.com/LuckfoxTECH/Luckfox-Pico-docs/main/Hardware
curl -sL -o Luckfox-Pico-Step.zip "$B/3D%20Models/Luckfox-Pico-Step.zip"
curl -sL -o Luckfox-Pico-CAD.zip "$B/CAD/Luckfox-Pico-CAD.zip"
curl -sL -o Luckfox-Pico-Mini.pdf "$B/Schematic/Luckfox-Pico-Mini.pdf"
unzip -o -q -j Luckfox-Pico-Step.zip "Luckfox-Pico-Step/Luckfox Pico Mini.step" -d . && mv "Luckfox Pico Mini.step" Luckfox_Pico_Mini.step
ls -la

# datasheets (sources: datasheets/README.md); .txt copies are what the docs quote
cd ../datasheets
get() { curl -sL -A "Mozilla/5.0" -o "$1" "$2" && head -c 5 "$1" | grep -q "%PDF" || { echo "!! $1: not a PDF, download it by hand"; rm -f "$1"; }; }
get TPS54360.pdf  https://www.ti.com/lit/ds/symlink/tps54360.pdf
get TPS54560B.pdf https://www.ti.com/lit/ds/symlink/tps54560b.pdf
get LM66100.pdf   https://www.ti.com/lit/ds/symlink/lm66100.pdf
get TLV755P.pdf   https://www.ti.com/lit/ds/symlink/tlv755p.pdf
get BMP390.pdf    https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bmp390-ds002.pdf
[ -f ICM-42688-P_DS-000347_v1.7.pdf ] || echo "!! ICM-42688-P: download by hand, see datasheets/README.md"
for f in *.pdf; do [ -f "$f" ] && pdftotext -layout "$f" "${f%.pdf}.txt" 2>/dev/null || true; done
ls -la
