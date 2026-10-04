#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Critical routing for LFX_LTE_R1, done on the empty board and then LOCKED, so the
autorouter works around it instead of through it.

  1. every SMD pad on a plane net (GND on In1, +3V8 on In2) gets a short
     dog-bone via to its plane - the modem's 24 ground pads and both VBAT
     pins included
  2. the copper pours are laid and filled, so those vias land on real planes
  3. the antenna feeds (module pin -> pi match -> U.FL), F.Cu only
  4. the 3.8 V buck's switch node and feedback on F.Cu, then +5V / +3V3

Run with KiCad's python, after gen_pcb.py and before route_pcb.py.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import pcbnew                                          # noqa: E402
import route_maze as rm                                # noqa: E402
import route_pcb                                       # noqa: E402

PLANE_NETS = ("GND", "+3V8")            # In1 / In2
# the 3.8 V buck's own nets: short, on the top side with the converter
BUCK_NETS = {"SW38", "FB38"}
POWER_NETS = {"+5V", "+3V3"}
SENSOR_NETS = set()
# antenna feeds: millimetres long, F.Cu only, over unbroken In1 ground, laid
# before anything else can take the space (HDM 5.4: nothing under them)
RF_NETS = {"LTE_ANT", "LTE_ANT_J", "GNSS_ANT", "GNSS_ANT_M", "GNSS_ANT_J"}
ESCAPE_W = 0.25


def fanout_planes(board):
    done, missed = 0, []
    # sensor supply and fine-pitch pads first: the LGA escapes are the ones
    # with no second chance, so they may not be walled in by ground vias
    order = {"+3V8": 1, "GND": 2}
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

    n, missed = fanout_planes(board)
    print("plane fan-out: %d vias" % n)
    if missed:
        print("  !! no room for a via at", ", ".join(missed))

    if not [z for z in board.Zones() if not z.GetIsRuleArea()]:
        route_pcb.add_zones(board)

    rm.ALLOWED = {pcbnew.F_Cu}
    left_rf = rm.route_open(board, only=RF_NETS, fanout_zones=False)
    rm.ALLOWED = None
    print("antenna feeds: %d connections still open" % left_rf)
    # switch node and feedback stay on F.Cu, the side the converter sits on
    rm.ALLOWED = {pcbnew.F_Cu}
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
