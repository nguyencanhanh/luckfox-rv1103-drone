#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Produce the manufacturing package in fab/ :

  gerbers/          Gerber X2 for all copper, mask, silk, paste, edge
  drill/            Excellon plated + non-plated, with a map
  LFX_FC_R2_schematic.pdf
  LFX_FC_R2_assembly_top.pdf / _bottom.pdf
  LFX_FC_R2_bom.csv          grouped, with DNF flagged
  LFX_FC_R2_pos_top.csv      pick and place
  LFX_FC_R2.step             3D model
  LFX_FC_R2_stats.txt        board statistics
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
SCH = os.path.join(ROOT, "LFX_FC_R2.kicad_sch")
PCB = os.path.join(ROOT, "LFX_FC_R2.kicad_pcb")
FAB = os.path.join(ROOT, "fab")

FAB_README = """LFX FC R2 - fabrication notes
=============================

Board
  size              50.0 x 50.0 mm, 2 mm corner radius
  mounting          4 x M3 NPTH (3.2 mm), 39 x 39 mm pattern, unplated on
                    purpose (no frame ground through the standoffs)
  layers            4 (F.Cu / GND / PWR / B.Cu)
  thickness         1.6 mm
  stack-up          JLC04161H-7628 or equivalent:
                      F.Cu   35 um
                      prepreg 7628 x1   0.2104 mm   Er 4.4
                      In1.Cu 17 um   SOLID GROUND
                      core              1.065 mm
                      In2.Cu 17 um   VSYS plane, +3V3S island, ground
                                     islands under the antenna feeds, and
                                     some signal routing
                      prepreg 7628 x1   0.2104 mm
                      B.Cu   35 um
  outer copper      1 oz finished
  min track / gap   0.15 / 0.15 mm (0.5 mm pitch LGA sensors)
  min drill         0.25 mm vias (0.50 mm pad), tented both sides
  copper to edge    0.25 mm minimum
  surface finish    ENIG required: ICM-42688-P (LGA-14), BMP390 (LGA-10) and
                    the Lierda NT26-KCN E (LCC + LGA, 109 pads) need flat pads
  solder mask       both sides
  silkscreen        both sides

CONTROLLED IMPEDANCE
  Not ordered as a controlled-impedance build.  The two antenna feeds (a few
  mm each, B.Cu over In2 ground islands) are 0.35 mm wide: 50 ohm on the
  JLC04161H-7628 stack above.  Keep that stack-up.

EXPOSED COPPER
  J2 / J3 (battery, 2.5 x 4 mm) and J7..J14 (ESC signal / ground,
  1.5 x 2.5 mm) are bare solder pads for wires: normal mask openings.

ASSEMBLY
  Both sides carry SMD parts.  Top: Luckfox socket, sensors, RC / buzzer
  connectors, nano-SIM holder, level translators, ESC pads.  Bottom: the
  Lierda NT26-KCN E (U8 - order the GPS + BDS variant; X-ray or at least an
  electrical check of its LGA joints), the two U.FL jacks, the 5 V and
  3.8 V bucks.  MOD1 is two 1 x 11, 2.54 mm female headers (the module
  plugs in) - hand soldered, through hole.
  Parts marked DNF in the BOM (the antenna pi-match shunts) are not fitted.
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
        os.path.join(FAB, "LFX_FC_R2_schematic.pdf"), SCH)
    run("pcb", "export", "pdf", "--layers",
        "F.SilkS,F.Fab,Edge.Cuts", "--mode-single",
        "-o", os.path.join(FAB, "LFX_FC_R2_assembly_top.pdf"), PCB)
    run("pcb", "export", "pdf", "--layers",
        "B.SilkS,B.Fab,Edge.Cuts", "--mode-single", "--mirror",
        "-o", os.path.join(FAB, "LFX_FC_R2_assembly_bottom.pdf"), PCB)

    print("bom and placement")
    run("sch", "export", "bom",
        "--fields", "Reference,Value,Footprint,${QUANTITY},Description,"
                    "Manufacturer,MPN,${DNP}",
        "--labels", "Refs,Value,Footprint,Qty,Description,Manufacturer,MPN,DNF",
        "--group-by", "Value,Footprint",
        "--sort-field", "Reference",
        "-o", os.path.join(FAB, "LFX_FC_R2_bom.csv"), SCH)
    run("pcb", "export", "pos", "--format", "csv", "--units", "mm",
        "--side", "both", "--use-drill-file-origin",
        "-o", os.path.join(FAB, "LFX_FC_R2_pos.csv"), PCB)

    print("verification reports")
    run("pcb", "drc", "--severity-all", "--schematic-parity",
        "-o", os.path.join(FAB, "drc.rpt"), PCB)
    run("sch", "erc", "--severity-all",
        "-o", os.path.join(FAB, "erc.rpt"), SCH)

    print("3d and statistics")
    run("pcb", "export", "step", "--subst-models", "--no-dnp",
        "-o", os.path.join(FAB, "LFX_FC_R2.step"), PCB)
    run("pcb", "export", "stats", "-o",
        os.path.join(FAB, "LFX_FC_R2_stats.txt"), PCB)

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
