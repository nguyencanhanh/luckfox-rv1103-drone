#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Produce the manufacturing package in fab/ :

  gerbers/          Gerber X2 for all copper, mask, silk, paste, edge
  drill/            Excellon plated + non-plated, with a map
  LFX_FC_R1_schematic.pdf
  LFX_FC_R1_assembly_top.pdf / _bottom.pdf
  LFX_FC_R1_bom.csv          grouped, with DNF flagged
  LFX_FC_R1_pos_top.csv      pick and place
  LFX_FC_R1.step             3D model
  LFX_FC_R1_stats.txt        board statistics
  README_FAB.txt                what to tell the fab house

Run:  python3 scripts/make_fab.py
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
SCH = os.path.join(ROOT, "LFX_FC_R1.kicad_sch")
PCB = os.path.join(ROOT, "LFX_FC_R1.kicad_pcb")
FAB = os.path.join(ROOT, "fab")

FAB_README = """LFX FC R1 - fabrication notes
=================================

Board
  size              140.0 x 90.0 mm, rounded 3 mm corners
  layers            4 (F.Cu / GND / PWR / B.Cu)
  thickness         1.6 mm
  stack-up          JLC04161H-7628 or equivalent:
                      F.Cu   35 um
                      prepreg 7628 x1   0.2104 mm   Er 4.4
                      In1.Cu 17 um   SOLID GROUND
                      core              1.065 mm
                      In2.Cu 17 um   power planes
                      prepreg 7628 x1   0.2104 mm
                      B.Cu   35 um
  outer copper      1 oz finished
  min track/gap     0.20 / 0.20 mm
  min drill         0.30 mm
  surface finish    ENIG preferred (HASL acceptable)
  solder mask       green, both sides
  silkscreen        white, both sides

CONTROLLED IMPEDANCE
  The antenna feed between U8 pin 35 and J10 is a 0.35 mm track on F.Cu
  referenced to the In1 ground plane and must come out at 50 ohm +/- 10 %.
  Please keep the 0.2104 mm F.Cu-to-In1 spacing; tell us if your stack-up
  differs so the track width can be re-calculated.

MILLED SLOT
  A 2.5 mm wide slot runs from (92.0, 12.0) to (94.5, 78.0).  It is the
  isolation barrier between the low-voltage section and the relay section and
  must be routed, not scored.  Do not add tooling tabs inside it.

EXPOSED COPPER
  The six relay-contact tracks between K1/K2 and J11/J12 have solder-mask
  apertures on F.Cu.  They are meant to be tinned so they carry 10 A.  Please
  leave the mask open there.

ASSEMBLY
  Parts marked DNF in the BOM are not fitted.
  LK1 and LK2 are wire links, fitted by default (shared-ground mode).
  J9 (nano-SIM) is on the bottom side; everything else is top side.
"""


def run(*args):
    cmd = [CLI] + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    tag = " ".join(args[:3])
    if r.returncode != 0:
        print("  FAIL %-28s %s" % (tag, out.splitlines()[-1] if out else ""))
    else:
        print("  ok   %s" % tag)
    return r.returncode == 0


def main():
    gerb = os.path.join(FAB, "gerbers")
    drill = os.path.join(FAB, "drill")
    for d in (FAB, gerb, drill):
        os.makedirs(d, exist_ok=True)

    print("gerbers")
    run("pcb", "export", "gerbers",
        "--layers", "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,"
                    "F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts",
        "--no-protel-ext", "--use-drill-file-origin", "--subtract-soldermask",
        "-o", gerb + os.sep, PCB)

    print("drill")
    run("pcb", "export", "drill", "--format", "excellon",
        "--drill-origin", "plot", "--excellon-separate-th",
        "--generate-map", "--map-format", "gerberx2",
        "-o", drill + os.sep, PCB)

    print("documents")
    run("sch", "export", "pdf", "-o",
        os.path.join(FAB, "LFX_FC_R1_schematic.pdf"), SCH)
    run("pcb", "export", "pdf", "--layers",
        "F.SilkS,F.Fab,Edge.Cuts", "--mode-single",
        "-o", os.path.join(FAB, "LFX_FC_R1_assembly_top.pdf"), PCB)
    run("pcb", "export", "pdf", "--layers",
        "B.SilkS,B.Fab,Edge.Cuts", "--mode-single", "--mirror",
        "-o", os.path.join(FAB, "LFX_FC_R1_assembly_bottom.pdf"), PCB)

    print("bom and placement")
    run("sch", "export", "bom",
        "--fields", "Reference,Value,Footprint,${QUANTITY},Description,"
                    "Manufacturer,MPN,${DNP}",
        "--labels", "Refs,Value,Footprint,Qty,Description,Manufacturer,MPN,DNF",
        "--group-by", "Value,Footprint",
        "--sort-field", "Reference",
        "-o", os.path.join(FAB, "LFX_FC_R1_bom.csv"), SCH)
    run("pcb", "export", "pos", "--format", "csv", "--units", "mm",
        "--side", "both", "--use-drill-file-origin",
        "-o", os.path.join(FAB, "LFX_FC_R1_pos.csv"), PCB)

    print("verification reports")
    run("pcb", "drc", "--severity-all", "--schematic-parity",
        "-o", os.path.join(FAB, "drc.rpt"), PCB)
    run("sch", "erc", "--severity-all",
        "-o", os.path.join(FAB, "erc.rpt"), SCH)

    print("3d and statistics")
    run("pcb", "export", "step", "--subst-models", "--no-dnp",
        "-o", os.path.join(FAB, "LFX_FC_R1.step"), PCB)
    run("pcb", "export", "stats", "-o",
        os.path.join(FAB, "LFX_FC_R1_stats.txt"), PCB)

    with open(os.path.join(FAB, "README_FAB.txt"), "w") as fh:
        fh.write(FAB_README)
    print("  ok   README_FAB.txt")

    total = 0
    for base, _dirs, files in os.walk(FAB):
        for f in files:
            total += os.path.getsize(os.path.join(base, f))
    print("fab package: %.1f MB" % (total / 1048576.0))


if __name__ == "__main__":
    main()
