#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pictures of the board, for showing people who are not going to open KiCad.

Writes doc/img/ and a tarball beside it.  Everything here is derived from the
board file, so it is thrown away and regenerated rather than edited.

  python3 scripts/make_images.py
"""

import os
import subprocess
import sys
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PCB = os.path.join(ROOT, "LFX_FC_R1.kicad_pcb")
SCH = os.path.join(ROOT, "LFX_FC_R1.kicad_sch")
OUT = os.path.join(ROOT, "doc", "img")
CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"

# 3D renders.  "high" quality with the floor on gives shadows and ambient
# occlusion, which is what makes a render readable rather than flat.
RENDERS = (
    ("3d_top",      ["--side", "top"]),
    ("3d_bottom",   ["--side", "bottom"]),
    ("3d_iso",      ["--perspective", "--rotate", "-30,0,25", "--zoom", "0.9"]),
)

# 2D plots.  Each is the set of layers you would actually want to look at
# together; the copper plots carry the edge so the outline is visible.
PLOTS = (
    ("layout_top",     "F.Cu,F.Silkscreen,F.Mask,Edge.Cuts"),
    ("layout_bottom",  "B.Cu,B.Silkscreen,B.Mask,Edge.Cuts"),
    ("copper_top",     "F.Cu,Edge.Cuts"),
    ("copper_bottom",  "B.Cu,Edge.Cuts"),
    ("plane_gnd",      "GND,Edge.Cuts"),
    ("plane_pwr",      "PWR,Edge.Cuts"),
    ("assembly_top",   "F.Fab,F.Courtyard,Edge.Cuts"),
)


def strip_doctype(path):
    """Drop the SVG 1.1 DTD reference pcbnew writes.

    It is obsolete - SVG has not needed a DOCTYPE since 1.2 - and anything that
    parses the file as plain XML without fetching external entities rejects it.
    """
    with open(path) as f:
        text = f.read()
    i = text.find("<!DOCTYPE")
    if i < 0:
        return
    j = text.find(">", text.find("svg11.dtd", i))
    if j < 0:
        j = text.find(">", i)
    with open(path, "w") as f:
        f.write(text[:i] + text[j + 1:].lstrip("\n"))


def run(args):
    r = subprocess.run([CLI] + args, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write((r.stderr or r.stdout)[-400:] + "\n")
    return r.returncode == 0


def main():
    if not os.path.isdir(OUT):
        os.makedirs(OUT)
    made = []

    for name, extra in RENDERS:
        path = os.path.join(OUT, name + ".png")
        ok = run(["pcb", "render", "-o", path, "--quality", "high", "--floor",
                  "-w", "2400", "-h", "1600", "--background", "opaque"]
                 + extra + [PCB])
        print("  %-16s %s" % (name, "ok" if ok else "FAILED"))
        if ok:
            made.append(path)

    for name, layers in PLOTS:
        path = os.path.join(OUT, name + ".svg")
        ok = run(["pcb", "export", "svg", "-o", path, "--layers", layers,
                  "--page-size-mode", "2", "--exclude-drawing-sheet", PCB])
        if ok:
            strip_doctype(path)
        print("  %-16s %s" % (name, "ok" if ok else "FAILED"))
        if ok:
            made.append(path)

    path = os.path.join(OUT, "schematic.pdf")
    if run(["sch", "export", "pdf", "-o", path, SCH]):
        print("  %-16s ok" % "schematic")
        made.append(path)

    tar = os.path.join(ROOT, "doc", "LFX_FC_R1_images.tar.gz")
    with tarfile.open(tar, "w:gz") as t:
        for p in made:
            t.add(p, arcname=os.path.join("LFX_FC_R1_images",
                                          os.path.basename(p)))
    print("\n%d files -> %s (%.1f MB)"
          % (len(made), tar, os.path.getsize(tar) / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
