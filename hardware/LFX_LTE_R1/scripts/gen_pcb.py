#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build LFX_LTE_R1.kicad_pcb from scripts/design.py.

46 x 46 mm, 4 layers, the flight controller's four M3 holes (39 x 39 mm
pattern, 3.5 mm from each edge) so the two boards stack.  Every part is on
the top side (one reflow pass):

  * Lierda NT26-KCN E in the middle, nudged toward the rear edge; its VBAT
    pins (42/43) face that edge, with their caps and the 3.8 V buck in the
    strip behind them
  * the antenna pins (2 left, 35 right) sit near the rear of its long sides,
    each in line with a U.FL jack: GNSS on the left, LTE on the right
  * the hinged nano-SIM below the module, contacts toward it
  * the JST-SH 10 to the flight controller on the right edge at the same
    height as the flight controller's J5, so the cable runs straight down
  * In1 solid ground, In2 one +3V8 plane for the modem's 1.2 A bursts

The placement / packing machinery is the flight controller's
(LFX_FC_R1/scripts/gen_pcb.py); only the board, zones and anchors differ.

Run with KiCad's python:

  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/\
Versions/3.9/bin/python3.9 scripts/gen_pcb.py
"""

import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import pcbnew                                          # noqa: E402
import design
import kisym                                          # noqa: E402

STOCK_FP = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"
LOCAL_FP = os.path.join(os.path.dirname(ROOT), "LFX_FC_R1", "lib",
                        "footprints")        # shared LFX library

FC_W = 46.0                           # same square as the flight controller
FC_DY = 0.0                           # no offset: one square, board coords
BOARD_W, BOARD_H = FC_W, FC_W
EDGE_R = 2.0                          # corner radius
HOLE_IN = 3.5                         # M3 standoffs in the corners
HOLE_PITCH = FC_W - 2 * HOLE_IN       # 39.0 mm square pattern
HOLE_KEEP = 3.3                       # keep-out radius around each M3 hole
HOLES = [(HOLE_IN, HOLE_IN), (FC_W - HOLE_IN, HOLE_IN),
         (HOLE_IN, FC_W - HOLE_IN), (FC_W - HOLE_IN, FC_W - HOLE_IN)]

CLEAR = 0.2                           # placement clearance between courtyards
MIN_HOLE = 0.25                       # fab minimum drill
EDGE_CLEAR = 0.3                      # copper to board edge

# In2 is one +3V8 plane over the whole board
P3V8_ISLAND = [(0.5, 0.5), (BOARD_W - 0.5, 0.5), (BOARD_W - 0.5, BOARD_H - 0.5),
               (0.5, BOARD_H - 0.5)]


def mm(v):
    return pcbnew.FromMM(float(v))


def P(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


# ---------------------------------------------------------------------------
# functional placement zones  (x0, y0, x1, y1, side)
# ---------------------------------------------------------------------------
ZONES = {
    "left_strip":  (0.6, 7.2, 13.6, 45.4, "F"),
    "right_strip": (32.4, 7.2, 45.4, 45.4, "F"),
    "rear_strip":  (6.8, 0.6, 39.2, 8.6, "F"),
    "below":       (6.8, 29.4, 39.2, 45.4, "F"),
    "bottom":      (0.6, 0.6, 45.4, 45.4, "B"),
}
SPILL_ORDER = {"F": ["left_strip", "right_strip", "rear_strip", "below"],
               "B": ["bottom"]}

BLOCK_ZONE = {
    "Flight-controller link (JST-SH 10)": "right_strip",
    "TLV62569 buck  +5V -> +3V8 (modem VBAT)": "rear_strip",
    "Modem supply decoupling at VBAT (HDM 3.4.2)": "rear_strip",
    "TLV75533 LDO  +5V -> +3V3 (translator A side)": "right_strip",
    "ESC current sense -> modem ADC0 (0-1.05 V)": "left_strip",
    "Lierda NT26-KCN E  LTE Cat.1 bis + GNSS": "left_strip",
    "UART level translation 3.3 V <-> 1.8 V": "right_strip",
    "Reset and download-mode control from the Luckfox": "right_strip",
    "Network status LED (HDM 4.7.3)": "right_strip",
    "Nano-SIM (HDM 4.3)": "below",
    "LTE antenna (HDM 5.3)": "right_strip",
    "GNSS active antenna (HDM 6.2, fig. 6-2)": "left_strip",
}

# Hand placed anchors: ref -> (x, y, rotation, side).  (x, y) is the wanted
# centre of the COURTYARD.  JST-SH side-entry: the mouth is on the +y side of
# the footprint at rotation 0, so 90 faces the right edge.  The signal pad of
# a U.FL is on its -x side at rotation 0.
ANCHORS = {
    "U4":  (23.0, 19.0, 0, "F"),          # modem; pin 2 at y 13.5, 35 at 12.4
    "J4":  (7.4, 13.5, 180, "F"),         # GNSS U.FL in line with pin 2
    "J3":  (38.6, 12.4, 0, "F"),          # LTE U.FL in line with pin 35
    "J2":  (23.0, 37.6, 0, "F"),          # nano-SIM, contacts toward the modem
    "J1":  (42.45, 30.3, 90, "F"),        # to FC J5 (same place on the FC)
    "U1":  (37.4, 30.3, 180, "F"),        # its ESD
    # VBAT (pins 42/43 at x 19.7 / 20.8): HF caps right behind the pads,
    # bulk behind them, the buck beside
    "C7":  (20.2, 7.4, 0, "F"),
    "C8":  (22.3, 7.4, 0, "F"),
    "C9":  (18.1, 7.4, 0, "F"),
    "C5":  (16.6, 3.6, 0, "F"),
    "C6":  (21.6, 3.6, 0, "F"),
    "U2":  (27.4, 3.8, 0, "F"),
    "L1":  (33.6, 4.0, 0, "F"),
    "D1":  (40.6, 21.0, 0, "F"),          # network LED
}

# Parts placed at the pin they serve:
#   (ref, host, host_pad, dx, dy, rot, side, region)
INTERIOR = None
NEAR = [
    # LTE: pi network in line between pin 35 and J3
    ("R22", "U4", "35", 2.6, 0.0, 0, "F"),
    ("C21", "U4", "35", 2.0, 1.5, 90, "F"),
    ("C22", "J3", "1", -1.8, 1.5, 90, "F"),
    # GNSS chain on one line: J4.1 -> C25 -> R23 -> pin 2, pad 1 of each part
    # toward the modem
    ("R23", "U4", "2", -2.8, 0.0, 180, "F"),
    ("C23", "U4", "2", -2.4, 1.5, 90, "F"),
    ("C25", "J4", "1", 1.9, 0.0, 180, "F"),
    ("C24", "J4", "1", 3.0, 1.5, 90, "F"),
    ("L2",  "J4", "1", 0.6, 2.4, 90, "F"),
    ("R24", "U4", "8", -3.0, 0.0, 0, "F"),
    ("C26", "U4", "8", -3.0, 1.3, 0, "F"),
    ("C27", "U4", "8", -3.0, -1.1, 0, "F"),
    ("R8",  "U4", "7", -2.6, 0.0, 0, "F"),     # PWRKEY pull-down
    ("C12", "U4", "9", -2.4, 0.0, 0, "F"),     # ADC0 filter at the pin
    # buck: input cap at VIN, output cap at L1, feedback at FB
    ("C2",  "U2", "4", 0.0, -1.6, 0, "F"),
    ("C3",  "L1", "2", 0.0, 3.6, 0, "F"),
    ("R4",  "U2", "5", -1.0, 2.0, 90, "F"),
    ("R5",  "U2", "5", 0.2, 2.0, 90, "F"),
    ("C4",  "U2", "5", 1.4, 2.0, 90, "F"),
    # SIM: series R, caps, ESD between the holder contacts and the modem
    ("U7",  "J2", "3", -9.0, 0.0, 90, "F"),
    # BOOT resistor at USB_BOOT (pin 82, inner ring) - just outside the
    # module on its right; reset FET by RESET_N (pin 15, bottom row)
    ("R13", "U4", "82", 7.0, 0.0, 90, "F"),
    ("Q1",  "U4", "15", -6.0, 1.0, 0, "F"),
    # translators by the cable connector
    ("U5",  "J1", "5", -6.5, -2.0, 0, "F"),
    ("U6",  "J1", "6", -6.5, 2.0, 0, "F"),
]

# Routing channels reserved before auto placement: (refA, padA, refB, padB, w)
CHANNELS = []

SILK = []            # every string laid down, for the self-check below


def add_silk(board, text, x, y, size=1.2, layer=pcbnew.F_SilkS, rot=0,
             thickness=0.2, anchor="center", absolute=False):
    """Place silkscreen text at square-local (x, y), or board (x, y) with
    absolute=True.

    `anchor` says what (x, y) means.  It defaults to the centre, which is
    KiCad's own default and was the bug behind 'AQUANODE R10' hanging 4.3 mm
    off the left edge of the board: the call read like a left margin.
    """
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text)
    if anchor == "left":
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
    elif anchor == "right":
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_RIGHT)
    t.SetPosition(P(x, y if absolute else y + FC_DY))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(thickness))
    t.SetTextAngle(pcbnew.EDA_ANGLE(rot, pcbnew.DEGREES_T))
    if layer == pcbnew.B_SilkS:
        t.SetMirrored(True)
    board.Add(t)
    SILK.append(t)


SILK_MARGIN = 0.4        # silk to board edge / to a mounting hole


def check_silk(board, refs):
    """Silkscreen has to be true and has to be on the board.

    Two failures got this far unnoticed and both are the kind a person only
    catches by looking at a render:

      * 'JP1+R61 = ONLY BARRIER CROSSINGS' named two parts that do not exist.
        It is the line an assembler reads to know what may bridge a safety
        barrier, and it was left over from an earlier revision.
      * add_silk() anchors text at its centre, so passing a left margin put
        'AQUANODE R10' at x = -4.32: a third of it off the edge of the board.

    Neither is a DRC error, so nothing else was ever going to catch them.
    """
    bad = []
    holes = [(pcbnew.ToMM(f.GetPosition().x), pcbnew.ToMM(f.GetPosition().y))
             for f in board.Footprints()
             if f.GetReference().startswith("H") and len(f.GetReference()) <= 3]

    for t in SILK:
        txt = t.GetText()
        bb = t.GetBoundingBox()
        x0, y0 = pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY())
        x1 = pcbnew.ToMM(bb.GetX() + bb.GetWidth())
        y1 = pcbnew.ToMM(bb.GetY() + bb.GetHeight())

        # every reference designator named in the text must be a real part
        # (motor labels M1-M4 are names, not references)
        for word in re.findall(r"\b([A-Z]{1,3}\d{1,3})\b", txt):
            if word not in refs and word not in ("M1", "M2", "M3", "M4"):
                bad.append("%r names %s, which is not in the netlist"
                           % (txt, word))

        # the text has to sit on the board, corner radius included
        if (x0 < SILK_MARGIN or y0 < SILK_MARGIN
                or x1 > BOARD_W - SILK_MARGIN or y1 > BOARD_H - SILK_MARGIN):
            bad.append("%r runs off the board: x %.2f..%.2f  y %.2f..%.2f"
                       % (txt, x0, x1, y0, y1))
        else:
            # A rounded corner only bites when the text reaches into that
            # corner's quadrant.  The point that decides it is the corner of
            # the text box furthest into the quadrant, not the nearest point
            # to the arc centre - testing the nearest point flags every string
            # on the board, which is what the first version of this did.
            for cx, cy, px, py in (
                    (EDGE_R, EDGE_R, x0, y0),
                    (BOARD_W - EDGE_R, EDGE_R, x1, y0),
                    (EDGE_R, BOARD_H - EDGE_R, x0, y1),
                    (BOARD_W - EDGE_R, BOARD_H - EDGE_R, x1, y1)):
                in_quadrant = ((px < cx) == (cx < BOARD_W / 2)
                               and (py < cy) == (cy < BOARD_H / 2))
                if in_quadrant and math.hypot(px - cx, py - cy) > \
                        EDGE_R - SILK_MARGIN:
                    bad.append("%r crosses the corner radius at (%.0f, %.0f)"
                               % (txt, cx, cy))
                    break

        # and clear of the mounting holes, which are drilled 3.2 mm
        for hx, hy in holes:
            nx = min(max(hx, x0), x1)
            ny = min(max(hy, y0), y1)
            if math.hypot(nx - hx, ny - hy) < 1.6 + SILK_MARGIN:
                bad.append("%r overlaps the mounting hole at (%.1f, %.1f)"
                           % (txt, hx, hy))

    for line in bad:
        print("  !! silk:", line)
    return len(bad)


# ---------------------------------------------------------------------------
class Packer(object):
    """Coarse occupancy grid so auto-placed parts never overlap, and never
    leave the usable board area."""

    STEP = 0.25

    def __init__(self, bounds=None):
        self.occ = {"F": set(), "B": set()}
        self.bounds = bounds

    def _cells(self, x0, y0, x1, y1):
        s = self.STEP
        for i in range(int(math.floor(x0 / s)), int(math.ceil(x1 / s)) + 1):
            for j in range(int(math.floor(y0 / s)), int(math.ceil(y1 / s)) + 1):
                yield (i, j)

    def occupy(self, x0, y0, x1, y1, layer=None):
        cells = set(self._cells(x0, y0, x1, y1))
        for side in (("F", "B") if layer is None else (layer,)):
            self.occ[side].update(cells)

    def free(self, x0, y0, x1, y1, bounds=None, layer="F"):
        b = bounds or self.bounds
        if b:
            bx0, by0, bx1, by1 = b
            if x0 < bx0 or y0 < by0 or x1 > bx1 or y1 > by1:
                return False
        occ = self.occ[layer]
        return not any(c in occ for c in self._cells(x0, y0, x1, y1))

    def find(self, zone, w, h, bounds=None, layer="F"):
        zx0, zy0, zx1, zy1 = zone
        if bounds:
            zx0 = max(zx0, bounds[0]); zy0 = max(zy0, bounds[1])
            zx1 = min(zx1, bounds[2]); zy1 = min(zy1, bounds[3])
        s = self.STEP
        y = zy0
        while y + h <= zy1 + 1e-6:
            x = zx0
            while x + w <= zx1 + 1e-6:
                if self.free(x, y, x + w, y + h, bounds, layer):
                    return x, y
                x += s
            y += s
        return None


def courtyard_box(fp):
    """Absolute courtyard bounding box in mm (x0, y0, x1, y1)."""
    fp.BuildCourtyardCaches()
    bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
    if bb.GetWidth() == 0:
        bb = fp.GetCourtyard(pcbnew.B_CrtYd).BBox()
    if bb.GetWidth() == 0:
        bb = fp.GetBoundingBox(False, False)
    return (pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY()),
            pcbnew.ToMM(bb.GetX() + bb.GetWidth()),
            pcbnew.ToMM(bb.GetY() + bb.GetHeight()))


def courtyard_size(fp):
    fp.BuildCourtyardCaches()
    bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
    if bb.GetWidth() == 0:
        bb = fp.GetCourtyard(pcbnew.B_CrtYd).BBox()
    if bb.GetWidth() == 0:
        bb = fp.GetBoundingBox(False, False)
    return (pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight()),
            pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY()))
def _check_unique_anchors():
    import ast
    src = open(os.path.abspath(__file__)).read()
    body = src[src.index("ANCHORS = {"):src.index("\n}\n", src.index("ANCHORS = {"))]
    keys = re.findall(r'^\s+"([A-Z]+\d+)":', body, re.M)
    dup = sorted({k for k in keys if keys.count(k) > 1})
    if dup:
        raise SystemExit("ANCHORS lists these parts twice: %s" % dup)


_check_unique_anchors()


# Package bodies that must stay clear underneath: (ref, body w, body h).
# TDK and Bosch both keep copper activity away from the MEMS die; a via under
# an LGA also cannot be tented reliably between 0.15 mm pad gaps.
EDGE_KEEP = 0.5
SENSOR_BODIES = []


def add_sensor_keepouts(board, placed):
    def area(name, x0, y0, x1, y1, layers, vias, tracks):
        z = pcbnew.ZONE(board)
        ls = pcbnew.LSET()
        for la in layers:
            ls.addLayer(la)
        z.SetLayerSet(ls)
        z.SetIsRuleArea(True)
        z.SetDoNotAllowZoneFills(False)
        z.SetDoNotAllowVias(vias)
        z.SetDoNotAllowTracks(tracks)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
        z.Outline().RemoveAllContours()
        z.Outline().NewOutline()
        for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            z.Outline().Append(mm(x), mm(y))
        z.SetZoneName(name)
        board.Add(z)

    every = (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)
    # Freerouting holds only its default 0.15 mm off the outline; the board
    # wants 0.25 mm copper-to-edge.  A 0.5 mm routing keep-out round the rim
    # (pours still reach in) makes both routers honour it.
    e, W, H = EDGE_KEEP, BOARD_W, BOARD_H
    for i, (x0, y0, x1, y1) in enumerate(((0, 0, W, e), (0, H - e, W, H),
                                          (0, e, e, H - e),
                                          (W - e, e, W, H - e))):
        area("edge keep-out %d" % i, x0, y0, x1, y1, every, True, True)
    for ref, w, h in SENSOR_BODIES:
        fp = placed[ref][0]
        cx = pcbnew.ToMM(fp.GetPosition().x)
        cy = pcbnew.ToMM(fp.GetPosition().y)
        if int(round(fp.GetOrientationDegrees())) % 180:
            w, h = h, w
        m = 0.35
        area("no vias under " + ref, cx - w / 2 - m, cy - h / 2 - m,
             cx + w / 2 + m, cy + h / 2 + m, every, True, False)
        i = 0.55                                  # pads reach 0.475 in
        area("no tracks under " + ref, cx - w / 2 + i, cy - h / 2 + i,
             cx + w / 2 - i, cy + h / 2 - i, (pcbnew.F_Cu,), False, True)


def fp_path(lib):
    for base in (LOCAL_FP, STOCK_FP):
        p = os.path.join(base, lib + ".pretty")
        if os.path.isdir(p):
            return p
    raise SystemExit("footprint library missing: " + lib)


def make_outline(board):
    """BOARD_W x BOARD_H with rounded corners."""
    def seg(x1, y1, x2, y2):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(P(x1, y1))
        s.SetEnd(P(x2, y2))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        board.Add(s)

    def arc(cx, cy, r, a0, a1):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_ARC)
        am = (a0 + a1) / 2.0

        def pt(a):
            return P(cx + r * math.cos(math.radians(a)),
                     cy + r * math.sin(math.radians(a)))
        s.SetArcGeometry(pt(a0), pt(am), pt(a1))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        board.Add(s)

    W, H, R = BOARD_W, BOARD_H, EDGE_R
    seg(R, 0, W - R, 0)
    seg(W, R, W, H - R)
    seg(W - R, H, R, H)
    seg(0, H - R, 0, R)
    arc(R, R, R, 180, 270)
    arc(W - R, R, R, 270, 360)
    arc(W - R, H - R, R, 0, 90)
    arc(R, H - R, R, 90, 180)


def add_mounting_holes(board):
    """Unplated M3 on the 30.5 mm pattern, no net: the stack uses nylon
    standoffs and rubber grommets for the gyro, so the holes must not tie the
    frame to ground."""
    lib = fp_path("MountingHole")
    for i, (x, y) in enumerate(HOLES, start=1):
        fp = pcbnew.FootprintLoad(lib, "MountingHole_3.2mm_M3")
        fp.SetFPID(pcbnew.LIB_ID("MountingHole", "MountingHole_3.2mm_M3"))
        fp.SetReference("H%d" % i)
        fp.SetValue("M3")
        fp.SetPosition(P(x, y))
        fp.Reference().SetVisible(False)
        fp.Value().SetVisible(False)
        board.Add(fp)


def pin_names(lib_id):
    """{pin number: pin name} over every unit of a schematic symbol."""
    out = {}
    for pins in kisym.pin_geometry(lib_id).values():
        for num, name, *_ in pins:
            out[num] = name
    return out


def load_footprint(c):
    lib, name = c["fp"].split(":", 1)
    fp = pcbnew.FootprintLoad(fp_path(lib), name)
    if fp is None:
        raise SystemExit("cannot load " + c["fp"])
    # library nickname, description and value exactly as the schematic has
    # them, so a --schematic-parity DRC finds nothing to disagree about
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    fp.SetReference(c["ref"])
    fp.SetValue(str(c["value"]))
    desc = c["fields"].get("Description")
    if desc:
        fp.GetField(pcbnew.FIELD_T_DESCRIPTION).SetText(desc)
    ds = c["fields"].get("Datasheet")
    if ds:
        fp.GetField(pcbnew.FIELD_T_DATASHEET).SetText(ds)
    fp.Value().SetVisible(False)
    fp.Reference().SetTextSize(pcbnew.VECTOR2I(mm(0.8), mm(0.8)))
    fp.Reference().SetTextThickness(mm(0.15))
    for pad in fp.Pads():
        d = pad.GetDrillSizeX()
        if 0 < d < mm(MIN_HOLE):
            pad.SetDrillSize(pcbnew.VECTOR2I(mm(MIN_HOLE), mm(MIN_HOLE)))
    if c["dnf"]:
        fp.SetDNP(True)
    # Dense board: passives, diodes and SOT parts carry their reference on
    # F.Fab (assembly drawing) instead of silk, where it would sit on pads.
    fp.BuildCourtyardCaches()
    bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
    area = pcbnew.ToMM(bb.GetWidth()) * pcbnew.ToMM(bb.GetHeight())
    if (area < 16.0 and not c["ref"].startswith(("J", "TP", "U", "MOD"))) \
            or c["ref"] in ("U2", "U3", "U4", "U5", "U6", "U7"):
        fp.Reference().SetLayer(pcbnew.F_Fab)
    return fp


def put(fp, x, y, rot, side):
    """Place so the courtyard centre lands on (x, y)."""
    fp.SetOrientationDegrees(rot)
    if side == "B" and not fp.IsFlipped():
        fp.Flip(P(x, y), False)
        fp.SetOrientationDegrees(rot)
    fp.SetPosition(P(x, y))
    bx0, by0, bx1, by1 = courtyard_box(fp)
    fp.SetPosition(P(x + (x - (bx0 + bx1) / 2.0), y + (y - (by0 + by1) / 2.0)))
    return courtyard_box(fp)


def tht_boxes(fp, pad_clear=0.25):
    """Every plated / unplated hole in a footprint - pins, thermal vias -
    as a box: it goes through the board, so it occupies BOTH sides."""
    out = []
    for q in fp.Pads():
        if q.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
            b = q.GetBoundingBox()
            out.append((pcbnew.ToMM(b.GetX()) - pad_clear,
                        pcbnew.ToMM(b.GetY()) - pad_clear,
                        pcbnew.ToMM(b.GetX() + b.GetWidth()) + pad_clear,
                        pcbnew.ToMM(b.GetY() + b.GetHeight()) + pad_clear))
    return out


def pad_xy(fp, num):
    for q in fp.Pads():
        if q.GetNumber() == num:
            return pcbnew.ToMM(q.GetPosition().x), pcbnew.ToMM(q.GetPosition().y)
    return None


BOARD_BOUNDS = (0.35, 0.35, BOARD_W - 0.35, BOARD_H - 0.35)


def main():
    out = os.path.join(ROOT, "LFX_LTE_R1.kicad_pcb")
    board = pcbnew.NewBoard(out)
    board.SetCopperLayerCount(4)
    board.SetLayerName(pcbnew.In1_Cu, "GND")
    board.SetLayerName(pcbnew.In2_Cu, "PWR")
    ds = board.GetDesignSettings()
    ds.SetBoardThickness(mm(1.6))
    # JLCPCB 4-layer standard capability, with margin
    ds.m_MinThroughDrill = mm(0.2)
    ds.m_ViasMinSize = mm(0.45)
    ds.m_ViasMinAnnularWidth = mm(0.1)
    ds.m_HoleToHoleMin = mm(0.25)
    ds.m_HoleClearance = mm(0.2)
    ds.m_MinClearance = mm(0.1)
    ds.m_TrackMinWidth = mm(0.15)
    ds.m_CopperEdgeClearance = mm(0.25)
    ds.m_MinSilkTextHeight = mm(0.8)
    ds.m_MinSilkTextThickness = mm(0.15)
    ds.m_TentViasFront = True
    ds.m_TentViasBack = True

    # ---- nets ----------------------------------------------------------
    netmap = {}
    for c in design.COMPONENTS:
        for n in c["pins"].values():
            if n and n not in netmap:
                ni = pcbnew.NETINFO_ITEM(board, n)
                board.Add(ni)
                netmap[n] = ni

    # ---- footprints ----------------------------------------------------
    placed, auto = {}, []
    for c in design.COMPONENTS:
        if not c["fp"] or c["unit"] != 1:
            continue
        if c["lib_id"] == "Mechanical:MountingHole":
            continue                  # placed by add_mounting_holes()
        fp = load_footprint(c)
        board.Add(fp)
        names = pin_names(c["lib_id"])
        for pad in fp.Pads():
            num = pad.GetNumber()
            net = c["pins"].get(num)
            if not net and num in names:
                # a pin left open gets KiCad's own single-pad net name, the
                # one the schematic netlist gives it
                net = "unconnected-(%s-%s-Pad%s)" % (
                    c["ref"], names[num].replace("/", "{slash}"), num)
                if net not in netmap:
                    netmap[net] = pcbnew.NETINFO_ITEM(board, net)
                    board.Add(netmap[net])
            if net:
                pad.SetNet(netmap[net])
        placed[c["ref"]] = (fp, c)
        auto.append(c["ref"])

    # ---- placement -----------------------------------------------------
    packer = Packer(BOARD_BOUNDS)
    for x, y in HOLES:
        packer.occupy(x - HOLE_KEEP, y - HOLE_KEEP, x + HOLE_KEEP, y + HOLE_KEEP)
    # rounded corners
    for cx, cy in ((0, 0), (BOARD_W, 0), (0, BOARD_H), (BOARD_W, BOARD_H)):
        packer.occupy(cx - 1.5, cy - 1.5, cx + 1.5, cy + 1.5)

    for ref, (x, y, rot, side) in ANCHORS.items():
        if ref not in placed:
            continue
        fp = placed[ref][0]
        bx0, by0, bx1, by1 = put(fp, x, y + FC_DY, rot, side)
        if ref == "U4":
            # HDM 8.3: 2 mm round the pads for a stepped stencil on the
            # same side; the HF caps behind VBAT are the one exception
            packer.occupy(bx0 - CLEAR, by0 - CLEAR, bx1 + CLEAR, by1 + CLEAR,
                          side)
        if ref == "MOD1":
            # the socket courtyard is two header strips; the space between
            # them is free for low parts under the module
            for sx in (-1, 1):
                cx = MOD_X + sx * 8.89
                packer.occupy(cx - 1.6 - CLEAR, by0 - CLEAR,
                              cx + 1.6 + CLEAR, by1 + CLEAR)   # THT: both sides
        else:
            packer.occupy(bx0 - CLEAR, by0 - CLEAR, bx1 + CLEAR, by1 + CLEAR,
                          side)
        for box in tht_boxes(fp):
            packer.occupy(*box)                       # both sides
        auto.remove(ref)

    for entry in NEAR:
        ref, host, hpad, dx, dy, rot = entry[:6]
        side = entry[6] if len(entry) > 6 else "F"
        region = entry[7] if len(entry) > 7 else None
        if ref not in placed or host not in placed:
            print("  !! NEAR skipped, missing", ref, host)
            continue
        hp = pad_xy(placed[host][0], hpad)
        if hp is None:
            print("  !! NEAR host pad missing", host, hpad)
            continue
        fp = placed[ref][0]
        fp.SetOrientationDegrees(rot)
        if side == "B" and not fp.IsFlipped():
            fp.Flip(P(*hp), False)
            fp.SetOrientationDegrees(rot)
        w, h, _ox, _oy = courtyard_size(fp)
        w += 2 * CLEAR
        h += 2 * CLEAR
        a0 = math.degrees(math.atan2(dy, dx)) if (dx or dy) else 0.0
        spot = None
        for r in [i * 0.1 for i in range(0, 161)]:
            cands = [(hp[0] + dx, hp[1] + dy)] if r == 0 else [
                (hp[0] + dx + r * math.cos(math.radians(a0 + d)),
                 hp[1] + dy + r * math.sin(math.radians(a0 + d)))
                for d in range(0, 360, 10)]
            for cx, cy in cands:
                if packer.free(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2,
                               region, side):
                    spot = (cx, cy)
                    break
            if spot:
                break
        if spot is None:
            print("  !! NEAR no room for", ref)
            continue
        bx0, by0, bx1, by1 = put(fp, spot[0], spot[1], rot, side)
        packer.occupy(bx0 - CLEAR, by0 - CLEAR, bx1 + CLEAR, by1 + CLEAR, side)
        if ref in auto:
            auto.remove(ref)
        ANCHORS.setdefault(ref, (spot[0], spot[1], rot, side))

    # a hole through the board must not land under a part on the other side
    for ra in placed:
        for bx in tht_boxes(placed[ra][0], 0.0):
            for rb in placed:
                if rb == ra or placed[rb][0].IsFlipped() == \
                        placed[ra][0].IsFlipped():
                    continue
                c = courtyard_box(placed[rb][0])
                if rb != "MOD1" and bx[0] < c[2] and bx[2] > c[0] and \
                        bx[1] < c[3] and bx[3] > c[1]:
                    print("  !! hole of %s under %s on the other side"
                          % (ra, rb))
                    break

    # hand anchors must not collide
    boxes = [(r, courtyard_box(placed[r][0])) for r in ANCHORS
             if r in placed and r != "MOD1"]
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            (ra, a), (rb, b) = boxes[i], boxes[j]
            if placed[ra][0].IsFlipped() != placed[rb][0].IsFlipped():
                continue
            if a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]:
                print("  !! courtyards overlap: %s / %s" % (ra, rb))

    for ra, pa, rb, pb, cw in CHANNELS:
        A = pad_xy(placed[ra][0], pa)
        Bp = pad_xy(placed[rb][0], pb)
        side = "B" if placed[ra][0].IsFlipped() else "F"
        h = cw / 2.0
        for (x0, y0), (x1, y1) in (((A[0], A[1]), (Bp[0], A[1])),
                                   ((Bp[0], A[1]), (Bp[0], Bp[1]))):
            packer.occupy(min(x0, x1) - h, min(y0, y1) - h,
                          max(x0, x1) + h, max(y0, y1) + h, side)

    unplaced = []
    auto.sort(key=lambda r: -(courtyard_size(placed[r][0])[0]
                              * courtyard_size(placed[r][0])[1]))
    for ref in auto:
        fp, c = placed[ref]
        zname = BLOCK_ZONE.get(c["block"])
        if zname is None:
            unplaced.append(ref)
            continue
        side = ZONES[zname][4]
        if side == "B" and not fp.IsFlipped():
            fp.Flip(fp.GetPosition(), False)
        w, h, ox, oy = courtyard_size(fp)
        w += 2 * CLEAR
        h += 2 * CLEAR
        spot = packer.find(ZONES[zname][:4], w, h, None, side)
        if spot is None:
            for zn in SPILL_ORDER[side]:
                spot = packer.find(ZONES[zn][:4], w, h, None, side)
                if spot:
                    break
        if spot is None:
            unplaced.append(ref)
            continue
        x, y = spot
        packer.occupy(x, y, x + w, y + h, side)
        cx, cy = x + w / 2.0, y + h / 2.0
        put(fp, cx, cy, fp.GetOrientationDegrees(), side)

    make_outline(board)
    add_mounting_holes(board)
    add_sensor_keepouts(board, placed)

    # ---- silkscreen -------------------------------------------------------
    add_silk(board, "LFX LTE R1", 23.0, 23.0, size=1.0, layer=pcbnew.B_SilkS)
    add_silk(board, "GNSS", 4.2, 13.5, size=0.8, rot=90)
    add_silk(board, "LTE", 38.6, 12.4, size=0.8, layer=pcbnew.B_SilkS)
    add_silk(board, "NET", 40.6, 22.8, size=0.8)
    add_silk(board, "TO FC", 42.45, 38.4, size=0.8)
    # J1: 5V 5V G G TX RX reSet Boot buZzer Current, under each pad; the
    # pads are 1 mm apart, so the letters stagger left / right
    for ref, letters in (("J1", "++GGTRSBZC"),):
        fp = placed[ref][0]
        for n, ch in enumerate(letters, start=1):
            x, y = pad_xy(fp, str(n))
            add_silk(board, ch, x + (0.5 if n % 2 else -0.5), y, size=0.8,
                     layer=pcbnew.B_SilkS, absolute=True)
    # connector / jack / probe references sit next to other parts here:
    # assembly drawing only, the silk labels above name them for a person
    for ref in ("J1", "J2", "J3", "J4", "TP1", "TP6"):
        placed[ref][0].Reference().SetLayer(pcbnew.F_Fab)
    bad_silk = check_silk(board, set(placed))
    if bad_silk:
        print("  !! %d silkscreen problems" % bad_silk)

    board.BuildListOfNets()
    board.Save(out)
    print("wrote", out)
    print("footprints placed:", len(placed) - len(unplaced), "of", len(placed))
    if unplaced:
        print("  !! could not place:", unplaced)
    print("nets:", len(netmap))
    return 1 if unplaced else 0


if __name__ == "__main__":
    sys.exit(main())
