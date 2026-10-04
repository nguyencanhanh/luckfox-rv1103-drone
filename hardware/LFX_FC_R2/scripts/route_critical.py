#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Critical routing for LFX_FC_R2, done on the empty board and then LOCKED, so the
autorouter works around it instead of through it.

  1. every SMD pad on a plane net (GND on In1, VSYS on In2) gets a short
     dog-bone via to its plane.  The ICM-42688-P and BMP390 have 0.15 mm
     between LGA pads: the escape track takes the pad's own width (<= 0.25 mm)
     so it can leave between its neighbours
  2. the copper pours are laid and filled, so those vias land on real planes
  3. the power train (switch node, VBAT, input filter, +5V, bootstrap,
     EN / RT / FB / COMP) is routed by the maze router on the empty board:
     its shape is the circuit, so it goes first and is locked
  4. then the sensor cluster - the SPI bus, both chip selects, the IMU
     interrupt - while the area is still clear.  +3V3S reaches the sensors
     through the In2 island, so it only needs the fan-out vias of step 1

Run with KiCad's python, after gen_pcb.py and before route_pcb.py.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import pcbnew                                          # noqa: E402
import route_maze as rm                                # noqa: E402
import route_pcb                                       # noqa: E402

PLANE_NETS = ("GND", "VSYS", "+3V3S")   # In1 / In2 / In2 island
# nets of the converter itself: B.Cu only
BUCK_NETS = {"SW38", "FB38",
             "SW5", "VBAT_F", "BOOT5", "EN5", "RT5", "FB5", "COMP5",
             "COMP5_C"}
# power nets that also serve the top side (TVS and ADC divider on VBAT,
# the LM66100 on +5V): routed after, on either outer layer
POWER_NETS = {"VBAT", "+5V"}
SENSOR_NETS = {"SPI_SCK", "SPI_MOSI", "SPI_MISO", "IMU_CS", "BARO_CS",
               "IMU_INT1"}
# antenna feeds: millimetres long, on B.Cu with the modem and the U.FLs, over
# the In2 ground islands, laid before anything else (HDM 5.4)
RF_NETS = {"LTE_ANT", "LTE_ANT_J", "GNSS_ANT", "GNSS_ANT_M", "GNSS_ANT_J"}
ESCAPE_W = 0.25


def _pad(board, ref, num):
    p = board.FindFootprintByReference(ref).FindPadByNumber(num)
    return (pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y), p)


def hand_route_imu(board):
    """The IMU bus, drawn rather than searched.

    Module pins 6..9 (CS, SCK, MOSI, MISO) sit in one column and the IMU,
    turned 90 degrees, shows CS, SCK, MOSI on its left edge and MISO at the
    left end of its bottom row - the same order, so four parallel 0.2 mm
    lines join them on F.Cu with no crossing and no via.  CS runs through its
    pull-up (R10) at the module end.  The barometer then branches off these
    nets on B.Cu from the module's through-hole pins.
    """
    def seg(net, pts):
        ni = board.FindNet(net)
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(rm.mm(x0), rm.mm(y0)))
            t.SetEnd(pcbnew.VECTOR2I(rm.mm(x1), rm.mm(y1)))
            t.SetLayer(pcbnew.F_Cu)
            t.SetWidth(rm.mm(0.2))
            t.SetNet(ni)
            t.SetLocked(True)
            board.Add(t)

    mx, cs_y, _ = _pad(board, "MOD1", "6")
    _, sck_y, _ = _pad(board, "MOD1", "7")
    _, mosi_y, _ = _pad(board, "MOD1", "8")
    _, miso_y, _ = _pad(board, "MOD1", "9")
    ix, ics, _ = _pad(board, "U4", "12")
    _, isck, _ = _pad(board, "U4", "13")
    _, imosi, _ = _pad(board, "U4", "14")
    bx, by, _ = _pad(board, "U4", "1")
    rx, ry, _ = _pad(board, "R10", "2")

    # CS: over the pull-up's supply pad at 45 degrees, into R10, then down
    # to the IMU's top-left pad, 0.5 mm clear of the GND row above it
    d = ry - cs_y
    jog = ix - 0.69
    seg("IMU_CS", [(mx, cs_y), (rx - d, cs_y), (rx, ry),
                   (rx + 0.3, ry), (jog, ry + (jog - rx - 0.3)),
                   (jog, ics), (ix, ics)])
    # SCK: 45 degree drop from the pin row to the pad row
    d = isck - sck_y
    seg("SPI_SCK", [(mx, sck_y), (ix - 2.92 - d, sck_y),
                    (ix - 2.92, isck), (ix, isck)])
    # MOSI: nearly level, a short 45 degree lift
    d = mosi_y - imosi
    seg("SPI_MOSI", [(mx, mosi_y), (ix - 3.42 - d, mosi_y),
                     (ix - 3.42, imosi), (ix, imosi)])
    # MISO: under the others, up into pad 1 from below
    d = miso_y - (by + 0.94)
    seg("SPI_MISO", [(mx, miso_y), (bx - d, miso_y), (bx, by + 0.94),
                     (bx, by)])
    # VDDIO (pin 5) straight out to its own 100 nF: the GND pads either
    # side leave no room for a via, and the cap's via feeds both
    vx, vy, _ = _pad(board, "U4", "5")
    cx, cy, _ = _pad(board, "C18", "1")
    seg("+3V3S", [(vx, vy), (cx, cy)])


def fanout_planes(board):
    done, missed = 0, []
    # sensor supply and fine-pitch pads first: the LGA escapes are the ones
    # with no second chance, so they may not be walled in by ground vias
    order = {"+3V3S": 0, "VSYS": 1, "GND": 2}
    pads = [(fp, pad) for fp in board.Footprints() for pad in fp.Pads()]
    pads.sort(key=lambda fq: (order.get(fq[1].GetNetname(), 9),
                              min(fq[1].GetSizeX(), fq[1].GetSizeY())))
    for fp, pad in pads:
        if True:
            net = pad.GetNetname()
            if net not in PLANE_NETS or \
                    pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            x = pcbnew.ToMM(pad.GetPosition().x)
            y = pcbnew.ToMM(pad.GetPosition().y)
            layer = pcbnew.B_Cu if pad.IsOnLayer(pcbnew.B_Cu) else pcbnew.F_Cu
            sx, sy = pcbnew.ToMM(pad.GetSizeX()), pcbnew.ToMM(pad.GetSizeY())
            # fine-pitch pads (USON, LGA: <= 0.3 mm wide) escape at 0.15 mm
            short = min(sx, sy)
            width = 0.15 if short <= 0.3 else min(ESCAPE_W, short)
            _w, clearance = rm.net_rules(board, net)
            nt, nv = rm.fanout(board, net, x, y, layer, width, clearance)
            if nv:
                done += 1
            else:
                missed.append("%s.%s" % (fp.GetReference(), pad.GetNumber()))
    return done, missed


def drop_blind_fanouts(board):
    """A plane via that lands outside its plane (the +3V3S island is small)
    reaches nothing: remove it and the escape that fed it."""
    inner = (pcbnew.In1_Cu, pcbnew.In2_Cu)
    zones = [z for z in board.Zones() if not z.GetIsRuleArea()]
    gone = 0
    for v in [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]:
        net = v.GetNetname()
        if net not in PLANE_NETS:
            continue
        pos = v.GetPosition()
        if any(z.GetNetname() == net and z.IsOnLayer(la)
               and z.HitTestFilledArea(la, pos)
               for z in zones for la in inner):
            continue
        for t in list(board.GetTracks()):
            if t.Type() != pcbnew.PCB_VIA_T and t.GetNetname() == net and \
                    (t.GetStart() == pos or t.GetEnd() == pos):
                board.Remove(t)
        board.Remove(v)
        gone += 1
    return gone


def main():
    board = pcbnew.LoadBoard(rm.PCB)
    for t in list(board.GetTracks()):
        board.Remove(t)

    hand_route_imu(board)
    n, missed = fanout_planes(board)
    print("plane fan-out: %d vias" % n)
    if missed:
        print("  !! no room for a via at", ", ".join(missed))

    if not [z for z in board.Zones() if not z.GetIsRuleArea()]:
        route_pcb.add_zones(board)

    # The sensor cluster is the tightest spot on the board (0.5 mm pitch LGAs
    # under the module), so it goes first; the power train is on the bottom
    # side and its few vias can step round the sensors.
    rm.ALLOWED = {pcbnew.B_Cu}
    left_rf = rm.route_open(board, only=RF_NETS, fanout_zones=False)
    rm.ALLOWED = None
    print("antenna feeds: %d connections still open" % left_rf)
    left = rm.route_open(board, only=SENSOR_NETS, fanout_zones=False)
    # switch node, input loop and control pins stay on B.Cu, the side the
    # converter sits on; only +5V may climb to the top toward the LM66100
    rm.ALLOWED = {pcbnew.B_Cu}
    left_buck = rm.route_open(board, only=BUCK_NETS, fanout_zones=False)
    rm.ALLOWED = None
    left_buck += rm.route_open(board, only=POWER_NETS, fanout_zones=False)
    print("power train: %d connections still open" % left_buck)
    for t in board.GetTracks():
        t.SetLocked(True)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    n = drop_blind_fanouts(board)
    if n:
        print("fan-out vias off their plane, removed: %d" % n)
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(rm.PCB)
    print("sensor cluster: %d connections still open" % left)
    return 0


if __name__ == "__main__":
    sys.exit(main())
