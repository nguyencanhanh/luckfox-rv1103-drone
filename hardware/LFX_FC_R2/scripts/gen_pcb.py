#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build LFX_FC_R2.kicad_pcb from scripts/design.py.

50 x 50 mm, 4 layers, M3 holes on a 39 x 39 mm pattern (5.5 mm in from each
edge).  The LFX_FC_R1 flight controller and the LFX_LTE_R1 modem board on one
board:

  TOP     rear half: the Luckfox Pico Mini B on its socket, USB-C flush with
          the rear edge; under it the IMU, barometer, ideal diode and sensor
          LDO.  Left strip: RC receiver port.  Right strip: buzzer, the two
          UART level translators by module pins 12 / 13, the modem reset FET
          by pin 18 and the BOOT resistor by pin 20.
          front half: the nano-SIM holder in the middle, the battery pads,
          TVS and input filter on the left, the modem test pads and network
          LED on the right, the modem's VBAT capacitors along the front edge
          over its VBAT pins.  ESC S/G pads in the four corners.
  BOTTOM  front half: the Lierda NT26-KCN E, turned so its two antenna pins
          face the front corners, a U.FL in each corner.  Left strip: the
          TPS54360 5 V buck (> 10 mm from the gyro, In1 ground between).
          Right strip: the TLV62569 3.8 V modem buck.
  In2     VSYS plane, +3V3S island under the sensors, +3V8 island under the
          modem, ground islands under the two antenna feeds (B.Cu references
          In2 there).

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

BOARD_W, BOARD_H = 50.0, 50.0
EDGE_R = 2.0                          # corner radius
HOLE_IN = 5.5                         # M3 standoffs, 39 mm pattern
HOLE_PITCH = BOARD_W - 2 * HOLE_IN    # 39.0 mm square pattern
HOLE_KEEP = 3.3                       # keep-out radius around each M3 hole
HOLES = [(HOLE_IN, HOLE_IN), (BOARD_W - HOLE_IN, HOLE_IN),
         (HOLE_IN, BOARD_H - HOLE_IN), (BOARD_W - HOLE_IN, BOARD_H - HOLE_IN)]

CLEAR = 0.2                           # placement clearance between courtyards
MIN_HOLE = 0.25                       # fab minimum drill
EDGE_CLEAR = 0.3                      # copper to board edge

# Module socket: pin-field centre.  The module's USB-C edge sits 14.093 mm
# above it (official STEP), so this puts that edge on the board edge.
MOD_X, MOD_Y = BOARD_W / 2.0, 14.093


# In2 island for +3V3S under the sensor cluster, with a finger up to the LDO
# output (U3 pin 5, C14).  No VSYS pad lies inside it.
P3V3S_ISLAND = [(27.9, 0.7), (30.8, 0.7), (30.8, 22.8), (18.0, 22.8),
                (18.0, 7.2), (27.9, 7.2)]
# In2 islands for the modem: +3V8 under it (its VBAT through vias from a
# plane), ground under the two antenna feeds, which run on B.Cu over In2
P3V8_ISLAND = [(0.6, 9.2), (14.6, 9.2), (14.6, 28.9), (35.4, 28.9),
               (35.4, 49.5), (17.6, 49.5), (17.6, 40.4), (0.6, 40.4)]
# (the left arm reaches the 3.8 V buck on the bottom left strip and the
# modem LED / test pads above it; no VSYS pad lies in it)
RF_GND_ISLANDS = [[(7.6, 40.6), (17.4, 40.6), (17.4, 49.5), (7.6, 49.5)],
                  [(32.6, 40.6), (42.4, 40.6), (42.4, 49.5), (32.6, 49.5)]]


def mm(v):
    return pcbnew.FromMM(float(v))


def P(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


# ---------------------------------------------------------------------------
# functional placement zones  (x0, y0, x1, y1, side)
# ---------------------------------------------------------------------------
COL_L, COL_R = MOD_X - 8.89, MOD_X + 8.89          # header columns, 16.11 / 33.89
UNDER = (17.95, 0.45, 32.05, 28.6)                 # between the columns
# bottom right strip, clear of the header pins at x 33.9; U1's thermal vias
# land under the free patch of the top side between Q2 and the buzzer
BUCK = (35.4, 9.2, 49.6, 41.0)
ZONES = {
    "under_module": UNDER + ("F",),
    "left_strip":   (0.4, 9.2, 14.3, 28.4, "F"),
    "right_strip":  (35.7, 9.2, 49.6, 28.4, "F"),
    "front_left":   (0.4, 28.6, 17.4, 41.0, "F"),
    "front_mid":    (14.0, 28.6, 36.0, 49.6, "F"),
    # left of the SIM holder: the modem's USIM pins (bottom) are at x ~17
    "sim_left":     (13.4, 28.6, 17.6, 45.8, "F"),
    "front_right":  (32.6, 28.6, 49.6, 41.0, "F"),
    "buck":         BUCK + ("B",),
    "lte_buck":     (0.4, 9.2, 14.6, 41.0, "B"),
    "bottom_under": UNDER + ("B",),
    "bottom_front": (8.0, 28.6, 42.0, 49.6, "B"),
}
SPILL_ORDER = {"F": ["front_left", "front_right", "front_mid",
                     "left_strip", "right_strip", "under_module"],
               "B": ["bottom_under", "buck", "lte_buck", "bottom_front"]}

BLOCK_ZONE = {
    "Battery input": "front_right",
    "TPS54360 buck  VBAT -> +5V": "buck",
    "LM66100 ideal diode  +5V -> VSYS (blocks USB back-feed)": "under_module",
    "TLV75533 LDO  VSYS -> +3V3S (sensors only)": "under_module",
    "Luckfox Pico Mini B, 2x 1x11 female header": "under_module",
    "RC receiver UART2 (CRSF / ExpressLRS)": "left_strip",
    "GPS module UART5 (receive only)": "left_strip",
    "ICM-42688-P 6-axis IMU, SPI 4-wire": "under_module",
    "BMP390 barometer, SPI 4-wire": "under_module",
    "Separate ESC solder pads (quad-X corners)": "under_module",
    "Battery voltage sense (SARADC 0-1.8 V)": "bottom_under",
    "Buzzer driver (gate from NT26 AGPIO5)": "right_strip",
    "Lierda NT26-KCN E  LTE Cat.1 bis + GNSS": "front_left",
    "NT26-KCN E supply decoupling at VBAT (HDM 3.4.2)": "front_mid",
    "TLV62569 buck  +5V -> +3V8 (LTE module VBAT)": "lte_buck",
    "UART level translation 3.3 V <-> 1.8 V": "right_strip",
    "Reset and download-mode control from the Luckfox": "right_strip",
    "Network status LED (HDM 4.7.3)": "front_right",
    "Nano-SIM (HDM 4.3)": "sim_left",
    "LTE antenna (HDM 5.3)": "bottom_front",
    "GNSS active antenna (HDM 6.2, fig. 6-2)": "bottom_front",
}

# Hand placed anchors: ref -> (x, y, rotation, side).  (x, y) is the wanted
# centre of the COURTYARD.  JST-SH side-entry: the mouth is on the +y side of
# the footprint at rotation 0, so 90 faces the right edge and 270 the left.
X = 7.0          # under-module parts: the LFX_FC_R1 positions + 2 mm
ANCHORS = {
    "MOD1": (MOD_X, MOD_Y, 0, "F"),
    # --- connectors on the edges ------------------------------------------
    "J4":  (3.55, 16.0, 270, "F"),        # RC receiver, left edge
    "J18": (3.55, 36.9, 270, "F"),        # GPS module, left edge (UART5 RX)
    "U13": (8.2, 37.2, 90, "F"),          # its ESD right at the connector
    "R44": (9.8, 37.2, 90, "B"),          # series 33 R, bottom: the long run
                                          # to pin 14 stays on B.Cu, clear of
                                          # the RC / SIM lines on top
    "J6":  (46.45, 16.0, 90, "F"),        # buzzer, right edge
    # --- ESC S / G pads, inboard of each corner hole ----------------------
    "J9":  (10.6, 2.2, 0, "F"),  "J13": (12.8, 2.2, 0, "F"),   # M3 rear-left
    "J7":  (39.4, 2.2, 0, "F"),  "J11": (37.2, 2.2, 0, "F"),   # M1 rear-right
    "J10": (10.6, 47.8, 0, "F"), "J14": (12.8, 47.8, 0, "F"),  # M4 front-left
    "J8":  (39.4, 47.8, 0, "F"), "J12": (37.2, 47.8, 0, "F"),  # M2 front-right
    # --- under the module: power path by header pin 1, sensors ------------
    "U2":  (12.6 + X, 1.9, 0, "F"),
    "C15": (15.6 + X, 2.4, 90, "F"),
    "C11": (11.6 + X, 4.95, 90, "F"),
    "C12": (14.9 + X, 5.65, 0, "F"),
    "U3":  (19.4 + X, 2.6, 0, "F"),
    "C13": (18.6 + X, 5.3, 0, "F"),
    "C14": (22.4 + X, 2.4, 90, "F"),
    "U5":  (20.4, 11.8, 0, "F"),
    "R10": (19.6, 15.1, 0, "F"),
    "R11": (28.4, 17.0, 0, "F"),          # BARO_CS pull-up beside its hand route
    "U4":  (23.6, 18.4, 90, "F"),
    "R12": (24.0 + X, 16.63, 0, "F"),     # ESC series resistors at their pins
    "R13": (24.0 + X, 14.9, 0, "F"),
    "R14": (12.0 + X, 24.25, 0, "F"),
    "R15": (12.0 + X, 26.79, 0, "F"),
    "R17": (25.4, 9.6, 0, "B"),           # VBAT divider at module pin 19
    "C21": (25.4, 8.0, 0, "B"),
    "D5":  (29.6, 9.9, 0, "B"),
    # --- left strip: RC ESD and series resistors ---------------------------
    "U7":  (2.6, 22.6, 90, "F"),
    "R8":  (6.2, 26.6, 90, "F"),          # off U1's thermal vias
    "R9":  (7.6, 26.6, 90, "F"),
    "R24": (13.2, 9.8, 90, "F"),          # RC_RX pull-up by module pin 3
    # --- right strip: buzzer, translators by pins 12/13, reset by pin 18 ---
    "Q1":  (42.7, 21.0, 0, "F"),
    "D7":  (46.4, 21.0, 90, "F"),
    "R22": (41.6, 23.8, 0, "F"),
    "R23": (44.0, 23.8, 0, "F"),
    "U9":  (38.4, 26.4, 0, "F"),          # TX translator, pin 12 at y 26.8
    "U10": (43.2, 26.4, 0, "F"),          # RX translator, pin 13 at y 24.25
    "Q2":  (38.4, 11.6, 0, "F"),          # reset FET, pin 18 at y 11.55
    "R32": (41.0, 10.8, 90, "F"),         # its gate resistor and pull-down
    "R33": (42.4, 10.8, 90, "F"),
    "TP3": (29.6, 14.0, 0, "B"),          # +3V3S probe, inside its island
    # modem network LED right of the SIM holder (its left side is the SIM's
    # own parts, over the modem's USIM pins)
    "D8":  (34.5, 42.4, 90, "F"),
    "R36": (34.5, 38.8, 90, "F"),
    "Q3":  (34.6, 35.4, 0, "F"),
    # --- front, top: battery entry left, SIM middle, modem VBAT caps -------
    "J2":  (46.4, 31.4, 0, "F"),          # battery +, by the 5 V buck below
    "J3":  (46.4, 36.8, 0, "F"),          # battery -
    "D1":  (40.6, 30.4, 0, "F"),          # TVS at the entry
    "FB1": (40.6, 33.6, 0, "F"),
    "R16": (40.6, 36.4, 0, "F"),          # VBAT divider top, at the entry
    "J15": (25.0, 37.4, 0, "F"),          # nano-SIM, contacts toward the rear
    "C26": (17.6, 47.6, 0, "F"),          # bulk + HF caps over the modem's
    "C27": (32.4, 47.6, 0, "F"),          # VBAT pins (bottom, front edge)
    "C28": (22.9, 47.6, 90, "F"),
    "C29": (25.0, 47.6, 90, "F"),
    "C30": (27.1, 47.6, 90, "F"),
    # --- bottom: modem front, U.FL in the front corners, the two bucks -----
    # rotation 0 on the bottom: antenna pins 2 / 35 at the front corners,
    # VBAT (42/43) at the front edge under C26-C30, UART / SIM pins toward
    # the Luckfox and the SIM holder.  U.FL signal pad toward the modem.
    "U8":  (25.0, 39.2, 0, "B"),
    "J17": (11.4, 46.0, 180, "B"),        # GNSS, by pin 2
    "J16": (38.6, 46.0, 0, "B"),          # LTE, by pin 35
    # 5 V buck, right strip.  U1 turned 90: pins 1-4 (BOOT VIN EN RT) on
    # its lower row, 5-8 (FB COMP GND SW) on the upper; SW top right, so the
    # inductor and catch diode sit right of it, input caps below, the
    # FB / COMP network above
    "U1":  (38.5, 20.3, 90, "B"),         # pins 5-8 at y 17.6, 1-4 at y 23.0
    "L1":  (45.2, 13.0, 0, "B"),          # SW (pin 8, top right) -> L1, D3
    "D3":  (45.2, 19.6, 0, "B"),
    # FB / COMP network right over pins 5 / 6, two 0603 columns
    # 0402 block over pins 5 (FB, x 36.6) and 6 (COMP, x 37.9), pins'
    # top ends at y 16.8.  Row 1: R6 (FB pad toward pin 5) and R4 (COMP pad
    # toward pin 6, a short diagonal).  Row 2: R5 with its +5V end out to
    # the free space on the left / above for a via, C6 under R4's COMP5_C
    # end, C7 between them on the COMP node.
    "R6":  (35.9, 15.9, 180, "B"),        # FB -> GND
    "R4":  (38.9, 15.9, 0, "B"),          # COMP -> COMP5_C
    "R5":  (36.4, 13.6, 0, "B"),          # +5V -> FB
    "C7":  (37.9, 13.9, 90, "B"),         # COMP -> GND
    "C6":  (39.6, 13.6, 0, "B"),          # COMP5_C -> GND
    # below: bootstrap at pin 1, input caps at VIN (pin 2), EN / RT
    "C5":  (42.6, 25.6, 90, "B"),
    "C4":  (39.0, 25.4, 0, "B"),
    "C1":  (38.2, 27.8, 0, "B"),
    "C2":  (38.2, 30.6, 0, "B"),
    "R1":  (37.0, 33.0, 0, "B"),          # VBAT_F -> EN
    "R2":  (37.0, 34.8, 0, "B"),          # EN -> GND
    "D2":  (40.9, 33.6, 0, "B"),          # EN clamp
    "R3":  (40.8, 35.9, 0, "B"),          # RT
    "C8":  (46.8, 24.6, 0, "B"),          # output caps at L1's far end
    "C9":  (46.8, 28.2, 0, "B"),
    "C10": (46.8, 31.2, 0, "B"),
    "U11": (8.0, 23.0, 0, "B"),           # 3.8 V buck, left strip, clear of
                                          # J4's pads on the top side
}

# Parts placed at the pin they serve:
#   (ref, host, host_pad, dx, dy, rot, side, region)
INTERIOR = UNDER
NEAR = [
    # --- 5 V buck: each part at the TPS54360 pin it serves ----------------
    # --- sensor decoupling on the pins -------------------------------------
    ("C16", "U4", "8", 0.0, -1.5, 0),
    ("C17", "U4", "8", 0.0, -2.9, 0),
    ("C18", "U4", "5", 2.0, 0.0, 0),
    ("C19", "U5", "10", 2.2, 0.0, 90),
    ("C20", "U5", "1", 0.6, -2.2, 0),
    # --- modem: pi networks between its antenna pins and the U.FLs ---------
    ("R41", "U8", "35", 0.0, 0.0, 0, "B"),
    ("C39", "U8", "35", 0.0, 0.0, 90, "B"),
    ("C40", "J16", "1", 0.0, 0.0, 90, "B"),
    ("R42", "U8", "2", 0.0, 0.0, 0, "B"),
    ("C41", "U8", "2", 0.0, 0.0, 90, "B"),
    ("C42", "J17", "1", 0.0, 0.0, 90, "B"),
    ("C43", "J17", "1", 0.0, 0.0, 0, "B"),
    ("L3",  "J17", "1", 0.0, 0.0, 90, "B"),
    ("R43", "U8", "8", 0.0, 0.0, 0, "B"),
    ("C44", "U8", "8", 0.0, 0.0, 0, "B"),
    ("C45", "U8", "8", 0.0, 0.0, 0, "B"),
    ("R27", "U8", "7", 0.0, 0.0, 0, "B"),            # PWRKEY pull-down
    # --- modem control by its Luckfox pins ----------------------------------
    ("R30", "MOD1", "20", 3.2, 0.0, 90, "F"),         # BOOT series
    ("R31", "MOD1", "20", 4.6, 0.0, 90, "F"),
    # --- SIM: series R, caps and ESD between the holder and the modem -------
    ("U12", "J15", "1", -4.0, 1.0, 90, "F", (13.4, 28.6, 17.6, 45.8)),
    # --- 3.8 V buck ----------------------------------------------------------
    ("C23", "U11", "4", 0.0, -2.2, 0, "B"),
    ("L2",  "U11", "3", 4.0, 0.0, 0, "B"),
    ("R25", "U11", "5", -2.4, 0.0, 90, "B"),
    ("R26", "U11", "5", -3.6, 0.0, 90, "B"),
    ("C25", "U11", "5", -2.4, 2.2, 0, "B"),
]

FAB_REFS = ("U1", "U8", "U10", "U11", "L1", "J2", "J3", "J17", "D1", "TP10",
            "TP11", "TP12", "TP13", "J18", "U13")

# Routing channels reserved before auto placement: (refA, padA, refB, padB, w)
CHANNELS = [
    ("U1", "8", "L1", "1", 1.6),       # switch node
    ("U1", "8", "D3", "1", 1.6),
]

SILK = []            # every string laid down, for the self-check below


def add_silk(board, text, x, y, size=1.2, layer=pcbnew.F_SilkS, rot=0,
             thickness=0.2, anchor="center"):
    """Place silkscreen text.

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
    t.SetPosition(P(x, y))
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
SENSOR_BODIES = [("U4", 3.0, 2.5), ("U5", 2.0, 2.0)]


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
    """36 x 36 mm with rounded corners."""
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
    out = os.path.join(ROOT, "LFX_FC_R2.kicad_pcb")
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
        bx0, by0, bx1, by1 = put(fp, x, y, rot, side)
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

    # ---- silkscreen: every label a person needs to plug the board in -------
    add_silk(board, "LFX FC R2", 25.0, 24.6, size=1.0, layer=pcbnew.B_SilkS)
    add_silk(board, "RC", 3.55, 11.7, size=0.8)
    add_silk(board, "GPS", 3.55, 32.6, size=0.8)
    add_silk(board, "BUZ", 46.45, 11.7, size=0.8)
    add_silk(board, "BAT+", 48.4, 27.4, size=0.8)
    add_silk(board, "BAT-", 46.4, 39.8, size=0.8)
    add_silk(board, "FWD v", 25.0, 26.6, size=0.8, layer=pcbnew.B_SilkS)
    # motor pads: S / G under (or over) each pad, the motor name beside them
    for n, sig, gnd, dy in ((3, "J9", "J13", 2.35), (1, "J7", "J11", 2.35),
                            (4, "J10", "J14", -2.35), (2, "J8", "J12", -2.35)):
        for ref, ch in ((sig, "S"), (gnd, "G")):
            x, y = pad_xy(placed[ref][0], "1")
            add_silk(board, ch, x, y + dy, size=0.8)
        xs = [pad_xy(placed[r][0], "1")[0] for r in (sig, gnd)]
        y = pad_xy(placed[sig][0], "1")[1] + 2 * dy
        x = sum(xs) / 2.0
        if n == 1:          # R30 / R31 (modem BOOT) sit under the M1 pads
            x, y = max(xs) + 2.0, pad_xy(placed[sig][0], "1")[1] + 2.0
        add_silk(board, "M%d" % n, x, y, size=0.8)
    for ref, letters in (("J4", "+GTR"), ("J6", "+-"), ("J18", "+G R")):
        fp = placed[ref][0]
        for n, ch in enumerate(letters, start=1):
            if ch == " ":           # a pin with nothing on it
                continue
            x, y = pad_xy(fp, str(n))
            add_silk(board, ch, x, y, size=0.8, layer=pcbnew.B_SilkS)
    # dense board: these references would sit on pads - the assembly drawing
    # (Fab) carries them
    for ref in FAB_REFS:
        if ref in placed:
            fp = placed[ref][0]
            fp.Reference().SetLayer(pcbnew.B_Fab if fp.IsFlipped()
                                    else pcbnew.F_Fab)
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
