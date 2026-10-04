#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LFX_MOUNT_R1 - adapter plate between the LFX_FC_R1 / LFX_LTE_R1 stack and a
small FPV frame.

The boards use M3 holes on a 39 x 39 mm square; 3" toothpick and whoop frames
take 20 x 20 or 25.5 x 25.5 mm (M2).  Every one of those patterns is a square
centred on the same point, so all the holes lie on the two diagonals: the
plate is an X - two rounded arms corner to corner and a hub - in 1.0 mm FR4,
about 1.5 g.  Order it with the boards.

    M3 3.2 mm at +-19.5 mm   flight controller (nylon standoffs up)
    M2 2.2 mm at +-12.75 mm  frame, 25.5 x 25.5 pattern
    M2 2.2 mm at +-10.0 mm   frame, 20 x 20 pattern

A 4" frame with 30.5 x 30.5 M3 needs its own plate: its holes sit 3.5 mm
along the arm from the 25.5 ones, too close to share one.  Set PATTERNS.

Run with KiCad's python:
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/\\
Versions/3.9/bin/python3.9 gen_mount.py
"""

import math
import os

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "LFX_MOUNT_R1.kicad_pcb")
STOCK_FP = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"

C = 23.0                      # plate centre (= board centre, 46 / 2)
ARM_W = 7.4                   # arm width: 2.1 mm of FR4 beside an M3 hole
HUB_R = 9.0
FC_HALF = 19.5                # 39 x 39 mm: the boards
# (half pitch, footprint): the frame patterns
PATTERNS = [(12.75, "MountingHole_2.2mm_M2"),     # 25.5 x 25.5
            (10.0, "MountingHole_2.2mm_M2")]      # 20 x 20


def mm(v):
    return pcbnew.FromMM(float(v))


def P(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


def outline():
    """X of two stadium arms (rounded ends round the M3 holes) plus a hub."""
    shape = pcbnew.SHAPE_POLY_SET()
    r = ARM_W / 2.0
    for sx in (-1, 1):
        a = pcbnew.SHAPE_POLY_SET()
        a.NewOutline()
        # zero-width spine corner to corner, inflated by r with round ends
        x0, y0 = C - sx * FC_HALF, C - FC_HALF
        x1, y1 = C + sx * FC_HALF, C + FC_HALF
        nx, ny = (y1 - y0), -(x1 - x0)
        ln = math.hypot(nx, ny)
        nx, ny = nx / ln * 0.01, ny / ln * 0.01
        for x, y in ((x0 + nx, y0 + ny), (x1 + nx, y1 + ny),
                     (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)):
            a.Append(mm(x), mm(y))
        a.Inflate(mm(r), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, mm(0.01))
        shape.BooleanAdd(a)
    hub = pcbnew.SHAPE_POLY_SET()
    hub.NewOutline()
    for i in range(72):
        t = 2 * math.pi * i / 72
        hub.Append(mm(C + HUB_R * math.cos(t)), mm(C + HUB_R * math.sin(t)))
    shape.BooleanAdd(hub)
    shape.Simplify()
    return shape


def hole(board, name, x, y, ref):
    fp = pcbnew.FootprintLoad(os.path.join(STOCK_FP, "MountingHole.pretty"),
                              name)
    fp.SetFPID(pcbnew.LIB_ID("MountingHole", name))
    fp.SetReference(ref)
    fp.SetValue(name.split("_")[-1])
    fp.SetPosition(P(x, y))
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    board.Add(fp)


def main():
    board = pcbnew.NewBoard(OUT)
    board.SetCopperLayerCount(2)
    ds = board.GetDesignSettings()
    ds.SetBoardThickness(mm(1.0))

    poly = outline()
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_POLY)
    s.SetPolyShape(poly)
    s.SetFilled(False)
    s.SetLayer(pcbnew.Edge_Cuts)
    s.SetWidth(mm(0.1))
    board.Add(s)

    n = 1
    for sx in (-1, 1):
        for sy in (-1, 1):
            hole(board, "MountingHole_3.2mm_M3", C + sx * FC_HALF,
                 C + sy * FC_HALF, "H%d" % n)
            n += 1
            for half, name in PATTERNS:
                hole(board, name, C + sx * half, C + sy * half, "H%d" % n)
                n += 1

    t = pcbnew.PCB_TEXT(board)
    t.SetText("LFX MOUNT R1  39 / 25.5 / 20")
    t.SetPosition(P(C, C))
    t.SetLayer(pcbnew.F_SilkS)
    t.SetTextSize(pcbnew.VECTOR2I(mm(0.9), mm(0.9)))
    t.SetTextThickness(mm(0.15))
    t.SetTextAngle(pcbnew.EDA_ANGLE(45, pcbnew.DEGREES_T))
    board.Add(t)

    board.Save(OUT)
    # The 20 and 25.5 mm holes are alternatives - a frame uses one set - 3.9
    # mm apart (1.7 mm of FR4 between the drills), so their screw-head
    # courtyards overlap by design.  The plate carries nothing but holes:
    # the courtyard check has nothing else to protect here.
    import json
    pro = OUT.replace(".kicad_pcb", ".kicad_pro")
    doc = json.load(open(pro)) if os.path.exists(pro) else {}
    sev = doc.setdefault("board", {}).setdefault("design_settings", {}) \
             .setdefault("rule_severities", {})
    sev["courtyards_overlap"] = "ignore"
    doc.setdefault("meta", {"filename": os.path.basename(pro), "version": 3})
    with open(pro, "w") as fh:
        json.dump(doc, fh, indent=2)
    cm2 = poly.Area() / 1e12 / 100.0                # nm^2 -> mm^2 -> cm^2
    print("wrote", OUT)
    print("plate area %.1f cm2, ~%.1f g in 1.0 mm FR4" % (cm2, cm2 * 0.185))


if __name__ == "__main__":
    main()
