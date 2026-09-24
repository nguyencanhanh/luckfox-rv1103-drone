#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Route pcb/LFX_FC_R1.kicad_pcb:

  1. export a Specctra .dsn
  2. run freerouting head-less
  3. import the .ses session back
  4. pour the copper zones (GND on In1, PWR on In2, GND/GND_ISO on the outers)

Run with KiCad's python; freerouting is located through FREEROUTING_JAR.
"""

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import pcbnew                                          # noqa: E402

PCB = os.path.join(ROOT, "LFX_FC_R1.kicad_pcb")
DSN = os.path.join(ROOT, "pcb", "LFX_FC_R1.dsn")
INNER_LAYERS = ("GND",)     # In1 stays a solid reference; In2 may carry signal
SES = os.path.join(ROOT, "pcb", "LFX_FC_R1.ses")
JAR = os.environ.get("FREEROUTING_JAR", "")

BOARD_W, BOARD_H = 140.0, 90.0
SLOT_X, SLOT_W = 92.0, 2.5
SLOT_Y0, SLOT_Y1 = 12.0, 78.0


def mm(v):
    return pcbnew.FromMM(float(v))


def P(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


def poly(pts):
    ch = pcbnew.SHAPE_POLY_SET()
    ch.NewOutline()
    for x, y in pts:
        ch.Append(mm(x), mm(y))
    return ch


def add_zone(board, netname, layers, pts, priority=0, name="", solid=False):
    z = pcbnew.ZONE(board)
    ls = pcbnew.LSET()
    for la in layers:
        ls.addLayer(la)
    z.SetLayerSet(ls)
    net = board.FindNet(netname)
    if net is None:
        raise SystemExit("zone net not found: " + netname)
    z.SetNet(net)
    z.SetAssignedPriority(priority)
    z.SetLocalClearance(mm(0.35))
    z.SetMinThickness(mm(0.25))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL if solid
                       else pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(mm(0.3))
    z.SetThermalReliefSpokeWidth(mm(0.4))
    # drop copper islands that end up stranded from the rest of the plane -
    # they look like a connection in the plot but carry nothing
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    z.SetIsFilled(False)
    z.SetZoneName(name or (netname + " " + str(layers)))
    z.Outline().RemoveAllContours()
    z.Outline().NewOutline()
    for x, y in pts:
        z.Outline().Append(mm(x), mm(y))
    board.Add(z)
    return z


def reserve_planes():
    """Tell the autorouter the two inner layers are planes, not routing space.

    KiCad exports every copper layer as "(type signal)", so freerouting treats
    the ground and power planes as two more places to run tracks.  Left alone
    it put 1.8 m of signal on the ground plane and 1.0 m on the power plane -
    53 and 34 nets - while B.Cu, the actual second signal layer, carried 342 mm.

    Every one of those tracks cuts a slot in a reference plane.  That is the
    return path for the signals above it, and it is also the assumption behind
    the 50 ohm microstrip number in stackup.py.  A four-layer board is two
    signal layers and two solid planes; this makes the DSN say so.
    """
    with open(DSN) as fh:
        text = fh.read()
    changed = []
    for name in INNER_LAYERS:
        marker = "(layer %s\n      (type signal)" % name
        if marker in text:
            text = text.replace(marker, "(layer %s\n      (type power)" % name)
            changed.append(name)
    if changed:
        with open(DSN, "w") as fh:
            fh.write(text)
    return changed


def export_dsn(board):
    ok = pcbnew.ExportSpecctraDSN(board, DSN)
    if not ok or not os.path.exists(DSN):
        raise SystemExit("DSN export failed")
    reserved = reserve_planes()
    print("dsn  ->", DSN, "%.1f kB" % (os.path.getsize(DSN) / 1024.0))
    print("     planes reserved (not routable):", ", ".join(reserved) or "none")


def run_freerouting():
    if os.environ.get("SKIP_ROUTE") and os.path.exists(SES):
        print("re-using the existing session file", SES)
        return True
    if not JAR or not os.path.exists(JAR):
        print("!! FREEROUTING_JAR not set, skipping the auto-route step")
        return False
    # Greedy, single-thread optimisation.  The hybrid strategy churns for
    # hours on this board because the isolation slot is a long wall the router
    # has to work around; greedy converges in minutes and the critical nets are
    # hand-routed and locked anyway.
    java = os.environ.get("JAVA_BIN", "java")
    cmd = [java, "-jar", JAR, "-de", DSN, "-do", SES,
           "-mp", str(os.environ.get("FR_PASSES", "20")),
           "-mt", str(os.environ.get("FR_THREADS", "1"))]
    # freerouting's rip-up is randomised: the same .dsn routes in ~20 s most
    # of the time and occasionally wanders for an hour.  Give it a short leash
    # and simply start over rather than waiting it out.
    attempts = int(os.environ.get("FR_ATTEMPTS", "4"))
    budget = int(os.environ.get("FR_TIMEOUT", "300"))
    best, best_ses = None, SES + ".best"
    for attempt in range(1, attempts + 1):
        if os.path.exists(SES):
            os.remove(SES)
        print("running (attempt %d/%d, %ds budget)" % (attempt, attempts,
                                                       budget))
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=budget)
        except subprocess.TimeoutExpired:
            print("   timed out")
            continue
        for ln in (r.stdout + r.stderr).strip().splitlines()[-3:]:
            print("   ", ln)
        if not os.path.exists(SES):
            continue
        # score it: how much did this run actually connect?
        probe = pcbnew.LoadBoard(PCB)
        pcbnew.ImportSpecctraSES(probe, SES)
        left = probe.GetConnectivity().GetUnconnectedCount(False)
        print("    -> %d unconnected" % left)
        if best is None or left < best:
            best = left
            shutil.copyfile(SES, best_ses)
        if left == 0:
            break
    if best is None:
        print("!! freerouting did not finish - keeping the hand-routed board")
        return False
    shutil.copyfile(best_ses, SES)
    os.remove(best_ses)
    print("best of %d attempts: %d unconnected" % (attempts, best))
    return True


def import_ses(board):
    pcbnew.ImportSpecctraSES(board, SES)
    n = len([t for t in board.GetTracks()])
    print("tracks/vias after import:", n)


def add_zones(board):
    m = 0.6                       # inset from the board edge
    lv = [(m, m), (SLOT_X - 0.8, m), (SLOT_X - 0.8, BOARD_H - m),
          (m, BOARD_H - m)]
    iso = [(SLOT_X + SLOT_W + 0.8, m), (BOARD_W - m, m),
           (BOARD_W - m, BOARD_H - m), (SLOT_X + SLOT_W + 0.8, BOARD_H - m)]

    add_zone(board, "GND", [pcbnew.F_Cu], lv, 10, "GND top LV", True)
    add_zone(board, "GND", [pcbnew.B_Cu], lv, 10, "GND bottom LV", True)
    add_zone(board, "GND", [pcbnew.In1_Cu], lv, 10, "GND plane LV")
    add_zone(board, "+3V3", [pcbnew.In2_Cu], lv, 10, "3V3 plane LV")

    add_zone(board, "GND_ISO", [pcbnew.F_Cu], iso, 10, "GND_ISO top", True)
    add_zone(board, "GND_ISO", [pcbnew.B_Cu], iso, 10, "GND_ISO bottom", True)
    add_zone(board, "GND_ISO", [pcbnew.In1_Cu], iso, 10, "GND_ISO plane")
    add_zone(board, "VRLY", [pcbnew.In2_Cu], iso, 10, "VRLY plane")

    zones = list(board.Zones())
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill([z for z in zones if not z.GetIsRuleArea()])
    print("zones:", len(zones))


def main():
    board = pcbnew.LoadBoard(PCB)
    export_dsn(board)
    routed = run_freerouting()
    if routed:
        board = pcbnew.LoadBoard(PCB)
        import_ses(board)
    add_zones(board)
    board.Save(PCB)
    print("saved", PCB)

    print("done")


if __name__ == "__main__":
    main()
