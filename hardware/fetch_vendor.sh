#!/bin/sh
# Download the official Luckfox Pico Mini mechanical data used by LFX_FC_R1
# (LuckfoxTECH/Luckfox-Pico-docs, Hardware/). The STEP gives the pin geometry.
set -e
cd "$(dirname "$0")/vendor"
B=https://raw.githubusercontent.com/LuckfoxTECH/Luckfox-Pico-docs/main/Hardware
curl -sL -o Luckfox-Pico-Step.zip "$B/3D%20Models/Luckfox-Pico-Step.zip"
curl -sL -o Luckfox-Pico-CAD.zip "$B/CAD/Luckfox-Pico-CAD.zip"
curl -sL -o Luckfox-Pico-Mini.pdf "$B/Schematic/Luckfox-Pico-Mini.pdf"
unzip -o -q -j Luckfox-Pico-Step.zip "Luckfox-Pico-Step/Luckfox Pico Mini.step" -d . && mv "Luckfox Pico Mini.step" Luckfox_Pico_Mini.step
ls -la
