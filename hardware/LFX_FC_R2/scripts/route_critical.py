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
SENSOR_NETS = {"SPI_SCK", "SPI_MOSI", "SPI_MISO", "IMU_CS", "BARO_CS"}
# external GPS (UART5 RX): from R44 on the bottom straight to header pin 14 on
# B.Cu, routed before the autorouter so it does not cut the crowded top-left
GPS_NETS = {"GPS_RX"}
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
    # VDD (pin 8) to that same cap, round the IMU's right side: the two supply
    # pins are then one node, and one island via (C16's or C18's) feeds both -
    # left to the fan-out, a run where both vias missed left them apart
    dx, dy, _ = _pad(board, "U4", "8")
    seg("+3V3S", [(dx, dy), (dx + 0.85, dy - 0.85), (cx, dy - 0.85), (cx, cy)])


def hand_route_baro(board):
    """BARO_CS since the external GPS took header pin 14: pin 15 (GPIO1_D3) sits
    level with the IMU, and left to the routers its chip select cut straight
    through the IMU's supply fan-out.  Drawn instead: a 0.9 mm stub out of CSB
    (bottom pad row) on F.Cu, a via 0.34 mm clear of the INT pad beside it,
    then on B.Cu above the IMU's decoupling and down beside the header into
    pin 15.  The top side around
    both sensors stays free for the SPI lines (a top-side run here walled
    U5's MISO in and came 0.13 mm from C17)."""
    px, py, _ = _pad(board, "MOD1", "15")
    bx, by, _ = _pad(board, "U5", "6")
    vy = by + 0.89                                   # via centre
    ni = board.FindNet("BARO_CS")

    def seg(layer, pts):
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(rm.mm(x0), rm.mm(y0)))
            t.SetEnd(pcbnew.VECTOR2I(rm.mm(x1), rm.mm(y1)))
            t.SetLayer(layer)
            t.SetWidth(rm.mm(0.2))
            t.SetNet(ni)
            t.SetLocked(True)
            board.Add(t)

    seg(pcbnew.F_Cu, [(bx, by), (bx, vy)])
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(rm.mm(bx), rm.mm(vy)))
    v.SetWidth(rm.mm(rm.VIA_D))
    v.SetDrill(rm.mm(rm.VIA_DRILL))
    v.SetNet(ni)
    v.SetLocked(True)
    board.Add(v)
    # B.Cu: up and over the IMU's decoupling instead of under the IMU, where it
    # took the spots of C16 / C18's island vias; y 12.65 runs above C17 and
    # clear of TP3 (29.6, 14.0), x 31.6 between TP3 and the header row, and
    # the GPS line (y 21.71) is never crossed
    y_run, x_down = 12.65, 31.6
    seg(pcbnew.B_Cu, [(bx, vy), (bx + (vy - y_run), y_run), (x_down, y_run),
                      (x_down, py), (px, py)])


def hand_route_sim(board):
    """The two short SIM legs from the ESD array U12 down to their series
    resistors.  RST (U12.4) drops to R37, CLK (U12.5) runs outside it to R38
    one row lower, so the two never cross.  With CLK on the inner pad the
    router walled it in, in 2 of 5 runs."""
    for net, (ref, num), (rref, rnum) in (
            ("SIM_RST", ("U12", "4"), ("R37", "2")),
            ("SIM_CLK", ("U12", "5"), ("R38", "2"))):
        ni = board.FindNet(net)
        ux, uy, _ = _pad(board, ref, num)
        rx, ry, _ = _pad(board, rref, rnum)
        pts = [(ux, uy), (ux, ry - (ux - rx)), (rx, ry)]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(rm.mm(x0), rm.mm(y0)))
            t.SetEnd(pcbnew.VECTOR2I(rm.mm(x1), rm.mm(y1)))
            t.SetLayer(pcbnew.F_Cu)
            t.SetWidth(rm.mm(0.2))
            t.SetNet(ni)
            t.SetLocked(True)
            board.Add(t)


def hand_route_buzzer(board):
    """BUZ_CTRL, modem pin 97 (bottom edge) up to the buzzer FET's gate
    resistor R22: 25 mm across the modem area, which the auto-router left
    open in 3 of 6 runs.  This is the path the router found for the committed
    board (dc53508): F.Cu stub, In2 (PWR) run east of the modem, B.Cu along
    the bottom edge to the LCC pad."""
    ni = board.FindNet("BUZ_CTRL")
    rx, ry, _ = _pad(board, "R22", "1")
    mx, my, _ = _pad(board, "U8", "97")
    v1, v2 = (41.63, 24.59), (36.25, 46.35)
    runs = ((pcbnew.F_Cu, [(rx, ry), (rx, ry + 0.26), v1]),
            (board.GetLayerID("PWR"), [v1, (43.04, 26.01), (43.04, 30.92),
                                       (40.40, 33.55), (40.40, 42.19), v2]),
            (pcbnew.B_Cu, [v2, (35.78, 46.82), (31.58, 46.82), (mx, my)]))
    for layer, pts in runs:
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(rm.mm(x0), rm.mm(y0)))
            t.SetEnd(pcbnew.VECTOR2I(rm.mm(x1), rm.mm(y1)))
            t.SetLayer(layer)
            t.SetWidth(rm.mm(0.2))
            t.SetNet(ni)
            t.SetLocked(True)
            board.Add(t)
    for x, y in (v1, v2):
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(rm.mm(x), rm.mm(y)))
        v.SetWidth(rm.mm(rm.VIA_D))
        v.SetDrill(rm.mm(rm.VIA_DRILL))
        v.SetNet(ni)
        v.SetLocked(True)
        board.Add(v)


def escape_ideal_diode(board):
    """+5V into the ideal diode U2 (pin 1, top edge): pin 1 sits in a corner
    between the board edge, the module's pad 1 and U2's own GND pin, and the
    ground fan-out of pin 2 used to take the only way out (open in 2 of 3
    runs).  Claim it first: the committed board's escape (dc53508), a stub to
    a Power-class via at (17.59, 1.11); the plane layer carries it on."""
    ni = board.FindNet("+5V")
    px, py, _ = _pad(board, "U2", "1")
    pts = [(px, py), (px - 0.14, 1.11), (17.59, 1.11)]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(rm.mm(x0), rm.mm(y0)))
        t.SetEnd(pcbnew.VECTOR2I(rm.mm(x1), rm.mm(y1)))
        t.SetLayer(pcbnew.F_Cu)
        t.SetWidth(rm.mm(0.35))
        t.SetNet(ni)
        t.SetLocked(True)
        board.Add(t)
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(rm.mm(17.59), rm.mm(1.11)))
    v.SetWidth(rm.mm(0.6))
    v.SetDrill(rm.mm(0.3))
    v.SetNet(ni)
    v.SetLocked(True)
    board.Add(v)


def hand_route_lte_1v8(board):
    """LTE_1V8 between the two level shifters' VCCA pins (U9.6, U10.6), the
    committed board's path (dc53508) - left open by the router in 4 of 10
    runs, the original R2 included.  The feed from the module joins at the
    U9 via."""
    ni = board.FindNet("LTE_1V8")
    ax, ay, _ = _pad(board, "U9", "6")
    bx, by, _ = _pad(board, "U10", "6")
    v1, v2 = (40.78, 25.30), (44.11, 28.12)
    runs = ((pcbnew.F_Cu, [(ax, ay), (ax + 0.14, v1[1]), v1]),
            (board.GetLayerID("PWR"), [v1, (40.78, 24.09), (41.85, 24.09),
                                       (43.44, 25.68), (43.44, 27.44), v2]),
            (pcbnew.F_Cu, [v2, (44.88, 28.12), (45.27, 27.72),
                           (45.27, 26.07), (bx + 0.31, by), (bx, by)]))
    for layer, pts in runs:
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(rm.mm(x0), rm.mm(y0)))
            t.SetEnd(pcbnew.VECTOR2I(rm.mm(x1), rm.mm(y1)))
            t.SetLayer(layer)
            t.SetWidth(rm.mm(0.2))
            t.SetNet(ni)
            t.SetLocked(True)
            board.Add(t)
    for x, y in (v1, v2):
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(rm.mm(x), rm.mm(y)))
        v.SetWidth(rm.mm(rm.VIA_D))
        v.SetDrill(rm.mm(rm.VIA_DRILL))
        v.SetNet(ni)
        v.SetLocked(True)
        board.Add(v)


def hand_route_gps_power(board):
    """+5V for the GPS port J18, from the RC port J4's pin 1: a via inside each
    connector's outline, and between them a B.Cu run hugging the left board
    edge (x 0.75: 0.55 mm copper-to-edge, rule 0.25).  Everything on the board
    lies east of it, so it walls nothing in; an earlier run at x 3.2 cut the
    RC ESD array U7 (x 1.6-3.6) off from the bottom layer and RC_RX_X failed
    to route.  0.4 mm: the GPS draws ~25 mA (ATGM336H)."""
    ni = board.FindNet("+5V")
    jx, jy, _ = _pad(board, "J4", "1")
    gx, gy, _ = _pad(board, "J18", "1")
    # vias under the housings, 0.26 mm off the mounting pads, so the B.Cu
    # corridor east of them (x > 2.85) stays open for +3V8
    vx, xb = 2.6, 0.75

    def seg(layer, pts):
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(rm.mm(x0), rm.mm(y0)))
            t.SetEnd(pcbnew.VECTOR2I(rm.mm(x1), rm.mm(y1)))
            t.SetLayer(layer)
            t.SetWidth(rm.mm(0.4))
            t.SetNet(ni)
            t.SetLocked(True)
            board.Add(t)

    def via(x, y):
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(rm.mm(x), rm.mm(y)))
        v.SetWidth(rm.mm(rm.VIA_D))
        v.SetDrill(rm.mm(rm.VIA_DRILL))
        v.SetNet(ni)
        v.SetLocked(True)
        board.Add(v)

    seg(pcbnew.F_Cu, [(jx, jy), (vx, jy)])
    via(vx, jy)
    gpad = board.FindFootprintByReference("J18").FindPadByNumber("1")
    if gpad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
        # a through-hole header: the B.Cu run ends on its pin 1 itself
        seg(pcbnew.B_Cu, [(vx, jy), (xb + 1.0, jy), (xb, jy + 1.0),
                          (xb, gy - 1.0), (xb + 1.0, gy), (gx, gy)])
        return
    seg(pcbnew.B_Cu, [(vx, jy), (xb + 1.0, jy), (xb, jy + 1.0),
                      (xb, gy - 1.0), (xb + 1.0, gy), (vx, gy)])
    via(vx, gy)
    seg(pcbnew.F_Cu, [(vx, gy), (gx, gy)])


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
    hand_route_baro(board)
    hand_route_gps_power(board)
    hand_route_sim(board)
    hand_route_buzzer(board)
    escape_ideal_diode(board)
    hand_route_lte_1v8(board)
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
    rm.ALLOWED = {pcbnew.B_Cu}
    left += rm.route_open(board, only=GPS_NETS, fanout_zones=False)
    rm.ALLOWED = None
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
