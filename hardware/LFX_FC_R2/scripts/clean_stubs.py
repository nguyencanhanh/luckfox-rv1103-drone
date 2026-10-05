#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Remove copper that leads nowhere.

An autorouter and a rip-up pass both leave stubs: a track whose end touches no
pad, via or other track.  They carry no current and they are not a DRC error,
so nothing forces them out - but a 1.8 mm stub hanging off a switching
regulator's feedback node is a small antenna on the most sensitive net on the
board, and one of these was 0.0123 mm long, which is nothing but a sliver.

KiCad's own connectivity engine already finds them, so rather than
re-implementing that, this asks it and deletes exactly what it names.  Locked
copper is never touched: it was placed by hand on purpose.

One pass per run.  Removing a stub can expose another, so build.sh calls this
after the routing has settled and, if it removed anything, the next attempt's
DRC sees the result.
"""

import os
import re
import subprocess
import sys

import pcbnew

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PCB = os.path.join(ROOT, "LFX_FC_R2.kicad_pcb")
CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
TOL = 0.002          # mm, matching a reported endpoint to a real one


def tomm(v):
    return pcbnew.ToMM(v)


DANGLING_VIAS = []


def dangling(board):
    """Ask KiCad which track ends are connected to nothing."""
    board.Save(PCB)
    rpt = os.path.join(ROOT, "_stubs.rpt")
    subprocess.run([CLI, "pcb", "drc", "--severity-all", "-o", rpt, PCB],
                   capture_output=True, text=True)
    if not os.path.exists(rpt):
        return []
    out, inblock, via_block = [], False, False
    global DANGLING_VIAS
    DANGLING_VIAS = []
    for line in open(rpt):
        mv = re.match(r"\s*@\((-?[\d.]+) mm, (-?[\d.]+) mm\): Via \[([^\]]*)\]", line)
        if mv and via_block:
            DANGLING_VIAS.append((float(mv.group(1)), float(mv.group(2)), mv.group(3)))
        via_block = line.startswith("[via_dangling]") or (via_block and not line.startswith("["))
        if line.startswith("[track_dangling]"):
            inblock = True
            continue
        if not inblock:
            continue
        if line.startswith("["):
            inblock = False
            continue
        m = re.match(r"\s*@\((-?[\d.]+) mm, (-?[\d.]+) mm\): "
                     r"Track \[([^\]]*)\][^,]*, length ([\d.]+)", line)
        if m:
            out.append((float(m.group(1)), float(m.group(2)),
                        m.group(3), float(m.group(4))))
            inblock = False
    os.remove(rpt)
    return out


def snapshot(board):
    """Track geometry as plain data, plus the live object beside it.

    Read before anything else happens.  Reading geometry back off these
    wrappers after the script has shelled out to kicad-cli fails now and then
    with 'SwigPyObject has no attribute x' - not reproducibly, which is worse
    than reproducibly.  Taking the numbers out of the C++ objects while they
    are known good sidesteps the whole question.
    """
    rows = []
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            continue
        try:
            rows.append((t,
                         tomm(t.GetStart().x), tomm(t.GetStart().y),
                         tomm(t.GetLength()), t.GetNetname(), t.IsLocked()))
        except AttributeError:
            return None          # tell the caller rather than half-doing it
    return rows


def main():
    board = pcbnew.LoadBoard(PCB)
    rows = snapshot(board)
    if rows is None:
        print("clean_stubs: could not read the track geometry, nothing removed")
        return 0

    stubs = dangling(board)
    removed, kept = 0, []
    for x, y, net, length in stubs:
        for t, ax, ay, ln, tnet, locked in rows:
            if tnet != net or abs(ln - length) > TOL:
                continue
            if abs(ax - x) >= TOL or abs(ay - y) >= TOL:
                continue
            if locked:
                kept.append((net, ln))
            else:
                board.Remove(t)
                removed += 1
            break

    # a via joined on one layer only carries nothing: drop it, and the single
    # escape track that led to it (a track passing through on to somewhere
    # else - two or more at the point - stays)
    vias_removed = 0
    for x, y, net in DANGLING_VIAS:
        for v in list(board.GetTracks()):
            if v.Type() != pcbnew.PCB_VIA_T or v.GetNetname() != net:
                continue
            p = v.GetPosition()
            if abs(tomm(p.x) - x) >= TOL or abs(tomm(p.y) - y) >= TOL:
                continue
            touching = [t for t in board.GetTracks()
                        if t.Type() != pcbnew.PCB_VIA_T and t.GetNetname() == net
                        and (t.GetStart() == p or t.GetEnd() == p)]
            if len(touching) == 1:
                board.Remove(touching[0])
            board.Remove(v)
            vias_removed += 1
            break

    board.Save(PCB)
    print("dangling stubs removed: %d, dangling vias removed: %d" % (removed, vias_removed))
    for net, length in kept:
        print("  kept (locked) %-12s %.3f mm - drawn by hand, left alone"
              % (net, length))
    return 0


if __name__ == "__main__":
    sys.exit(main())
