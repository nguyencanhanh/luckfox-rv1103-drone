#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Finishing pass on pcb/LFX_FC_R1.kicad_pcb.

  1. ground stitching vias on a 5 mm grid so the F.Cu / B.Cu pours are tied to
     the In1 plane everywhere and no pour island is left floating
  2. a via fence down both sides of the isolation slot: GND on the low-voltage
     side, GND_ISO on the coil side, so each domain has a continuous return
     right up to the barrier and neither one wanders across it
  3. via stitching around the board edge (EMC: stops the pours acting as a slot
     antenna at the module's 900 MHz fundamental)
  4. re-fill every zone and report what is still unrouted

Run after route_pcb.py.
"""

import math
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import pcbnew                                          # noqa: E402

PCB = os.path.join(ROOT, "LFX_FC_R1.kicad_pcb")

BOARD_W, BOARD_H = 140.0, 90.0
SLOT_X, SLOT_W = 92.0, 2.5
SLOT_Y0, SLOT_Y1 = 12.0, 78.0
MOUNT_INSET, MOUNT_PAD = 4.5, 6.0

VIA_D, VIA_DRILL = 0.8, 0.4
GRID = 5.0
EDGE_PITCH = 5.0
EDGE_INSET = 1.6
KEEPOUTS = [(106.0, 9.0, BOARD_W, 31.0), (106.0, 45.0, BOARD_W, 67.0),
            (84.0, 42.0, 92.0, 51.0)]      # U.FL antenna connector keep-out


def mm(v):
    return pcbnew.FromMM(float(v))


def P(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


def boxes(board):
    out = []
    for fp in board.Footprints():
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            out.append((pcbnew.ToMM(bb.GetX()) - 0.28,
                        pcbnew.ToMM(bb.GetY()) - 0.28,
                        pcbnew.ToMM(bb.GetX() + bb.GetWidth()) + 0.28,
                        pcbnew.ToMM(bb.GetY() + bb.GetHeight()) + 0.28,
                        pad.GetNetname()))
    return out


def track_segs(board):
    out = []
    for t in board.GetTracks():
        a = t.GetStart()
        b = t.GetEnd()
        half = pcbnew.ToMM(t.GetWidth()) / 2.0 + 0.40
        if t.Type() == pcbnew.PCB_VIA_T:
            half = pcbnew.ToMM(t.GetWidth()) / 2.0 + 0.42
        out.append(((pcbnew.ToMM(a.x), pcbnew.ToMM(a.y)),
                    (pcbnew.ToMM(b.x), pcbnew.ToMM(b.y)), half,
                    t.GetNetname()))
    return out


def point_clear(p, pad_boxes, segs, netname, r=VIA_D / 2.0, skip_tracks=False):
    x, y = p
    for x0, y0, x1, y1, pnet in pad_boxes:
        if pnet == netname:
            continue
        if x0 - r <= x <= x1 + r and y0 - r <= y <= y1 + r:
            return False
    if skip_tracks:
        # B.Cu detour: only through-hole obstacles (pads, vias) matter, and
        # those are all in pad_boxes or are zero-length via entries below
        segs = [s for s in segs if abs(s[0][0] - s[1][0]) < 1e-9
                and abs(s[0][1] - s[1][1]) < 1e-9]
    for a, b, half, net in segs:
        if net == netname:
            continue
        dx, dy = b[0] - a[0], b[1] - a[1]
        ln2 = dx * dx + dy * dy
        if ln2 < 1e-12:
            d = math.hypot(x - a[0], y - a[1])
        else:
            t = max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / ln2))
            d = math.hypot(x - (a[0] + t * dx), y - (a[1] + t * dy))
        if d < half + r:
            return False
    return True


HV_NETS = ("RLY1_COM", "RLY1_NO", "RLY1_NC", "RLY1_SNUB",
           "RLY2_COM", "RLY2_NO", "RLY2_NC", "RLY2_SNUB")
HV_KEEP = 2.0 + 3.0 / 2 + VIA_D / 2        # 2 mm rule + half track + half via
HV_SEGS = []

RF_NETS = ("ANT_RF", "ANT_FEED")
RF_KEEP = 0.70 + 0.35 / 2 + VIA_D / 2      # 2 x W + half trace + half via
RF_SEGS = []

RULE_AREAS = []          # filled from the board: every keep-out, including
                         # the ones embedded in footprints (J9 SIM, J10 U.FL)


def collect_rf(board):
    del RF_SEGS[:]
    del HV_SEGS[:]
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            continue
        seg = ((pcbnew.ToMM(t.GetStart().x), pcbnew.ToMM(t.GetStart().y)),
               (pcbnew.ToMM(t.GetEnd().x), pcbnew.ToMM(t.GetEnd().y)))
        if t.GetNetname() in RF_NETS:
            RF_SEGS.append(seg)
        elif t.GetNetname() in HV_NETS:
            HV_SEGS.append(seg)
    # mains-carrying pads count too - the snubber and terminal pads sit near
    # the board edge where the edge stitching runs
    for fp in board.Footprints():
        for pad in fp.Pads():
            if pad.GetNetname() in HV_NETS:
                p = (pcbnew.ToMM(pad.GetPosition().x),
                     pcbnew.ToMM(pad.GetPosition().y))
                HV_SEGS.append((p, p))
    return len(RF_SEGS), len(HV_SEGS)


def _near(p, segs, keep):
    for a, b in segs:
        dx, dy = b[0] - a[0], b[1] - a[1]
        l2 = dx * dx + dy * dy
        if l2 < 1e-12:
            d = math.hypot(p[0] - a[0], p[1] - a[1])
        else:
            t = max(0.0, min(1.0, ((p[0] - a[0]) * dx
                                   + (p[1] - a[1]) * dy) / l2))
            d = math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))
        if d < keep:
            return True
    return False


def near_rf(p):
    return _near(p, RF_SEGS, RF_KEEP)


def near_hv(p):
    return _near(p, HV_SEGS, HV_KEEP)


def collect_rule_areas(board):
    del RULE_AREAS[:]
    zs = list(board.Zones())
    for fp in board.Footprints():
        try:
            zs += list(fp.Zones())
        except Exception:                                  # noqa: BLE001
            pass
    for z in zs:
        if not z.GetIsRuleArea():
            continue
        bb = z.Outline().BBox()
        RULE_AREAS.append((pcbnew.ToMM(bb.GetX()) - 0.3,
                           pcbnew.ToMM(bb.GetY()) - 0.3,
                           pcbnew.ToMM(bb.GetX() + bb.GetWidth()) + 0.3,
                           pcbnew.ToMM(bb.GetY() + bb.GetHeight()) + 0.3))
    return len(RULE_AREAS)


def in_rule_area(p):
    x, y = p
    for x0, y0, x1, y1 in RULE_AREAS:
        if x0 <= x <= x1 and y0 <= y <= y1:
            return True
    return False


def in_board(p, margin=1.6):
    x, y = p
    if not (margin <= x <= BOARD_W - margin and margin <= y <= BOARD_H - margin):
        return False
    # the isolation band runs the full height of the board; only the two
    # wire-link windows are open, and nothing is stitched there anyway
    if SLOT_X - 2.4 <= x <= SLOT_X + SLOT_W + 2.4:
        return False
    for x0, y0, x1, y1 in KEEPOUTS:
        if x0 <= x <= x1 and y0 <= y <= y1:
            return False
    if in_rule_area(p):
        return False
    if near_rf(p) or near_hv(p):
        return False
    for mx, my in ((MOUNT_INSET, MOUNT_INSET),
                   (BOARD_W - MOUNT_INSET, MOUNT_INSET),
                   (MOUNT_INSET, BOARD_H - MOUNT_INSET),
                   (BOARD_W - MOUNT_INSET, BOARD_H - MOUNT_INSET)):
        if math.hypot(x - mx, y - my) < MOUNT_PAD:
            return False
    return True


def domain_net(p):
    return "GND" if p[0] < SLOT_X else "GND_ISO"


def _fence_ok(p):
    """The slot fence is the one place vias may sit beside the band."""
    return abs(p[0] - (SLOT_X - 3.0)) < 0.01 or \
        abs(p[0] - (SLOT_X + SLOT_W + 3.0)) < 0.01


def add_via(board, p, netname):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(P(*p))
    v.SetWidth(mm(VIA_D))
    v.SetDrill(mm(VIA_DRILL))
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    net = board.FindNet(netname)
    if net is None:
        return False
    v.SetNet(net)
    board.Add(v)
    return True


def escape(p, netname, pad_boxes, segs, rmax=9.0):
    """Nearest spot beside a pad where a via will fit and the stub is clear."""
    for r in [i * 0.25 for i in range(3, int(rmax / 0.25) + 1)]:
        for d in range(0, 360, 5):
            q = (p[0] + r * math.cos(math.radians(d)),
                 p[1] + r * math.sin(math.radians(d)))
            if not in_board(q, 1.4):
                continue
            if point_clear(q, pad_boxes, segs, netname, 0.45) and \
                    seg_clear(p, q, pad_boxes, segs, netname, 0.28):
                return q
    return None


def seg_clear(a, b, pad_boxes, segs, netname, half, bottom=False):
    """Sample the path; good enough for the short two-pad hops left over."""
    steps = max(2, int(math.hypot(b[0] - a[0], b[1] - a[1]) / 0.25))
    for i in range(steps + 1):
        t = i / float(steps)
        p = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        if not point_clear(p, pad_boxes, segs, netname, half,
                           skip_tracks=bottom):
            return False
    return True



# ---------------------------------------------------------------------------
# A real maze router for the handful of nets freerouting leaves behind.
# Works on B.Cu, which is nearly empty after the autorouter has filled F.Cu:
# escape each endpoint with a via, then BFS on a 0.5 mm grid.
# ---------------------------------------------------------------------------
MG = 0.5                     # maze grid pitch, mm
MW = int(BOARD_W / MG) + 1
MH = int(BOARD_H / MG) + 1


def _blocked_grid(board, netname, track_width=0.25):
    """Cells a B.Cu track of this net may not occupy."""
    half = track_width / 2.0 + 0.25
    blocked = bytearray(MW * MH)

    def mark(x0, y0, x1, y1):
        for i in range(max(0, int((x0 - half) / MG)),
                       min(MW - 1, int((x1 + half) / MG)) + 1):
            for j in range(max(0, int((y0 - half) / MG)),
                           min(MH - 1, int((y1 + half) / MG)) + 1):
                blocked[j * MW + i] = 1

    # board edge, slot and mains keep-outs
    for i in range(MW):
        for j in range(MH):
            x, y = i * MG, j * MG
            if not in_board((x, y), 1.4):
                blocked[j * MW + i] = 1

    for fp in board.Footprints():
        for pad in fp.Pads():
            if pad.GetNetname() == netname:
                continue
            # SMD pads on F.Cu do not block a B.Cu track
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD and \
                    not pad.IsOnLayer(pcbnew.B_Cu):
                continue
            bb = pad.GetBoundingBox()
            mark(pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY()),
                 pcbnew.ToMM(bb.GetX() + bb.GetWidth()),
                 pcbnew.ToMM(bb.GetY() + bb.GetHeight()))

    for t in board.GetTracks():
        if t.GetNetname() == netname:
            continue
        is_via = t.Type() == pcbnew.PCB_VIA_T
        if not is_via and t.GetLayer() != pcbnew.B_Cu:
            continue
        a, b = t.GetStart(), t.GetEnd()
        w = pcbnew.ToMM(t.GetWidth()) / 2.0
        ax, ay = pcbnew.ToMM(a.x), pcbnew.ToMM(a.y)
        bx, by = pcbnew.ToMM(b.x), pcbnew.ToMM(b.y)
        mark(min(ax, bx) - w, min(ay, by) - w,
             max(ax, bx) + w, max(ay, by) + w)
    return blocked


def _bfs(blocked, start, goal):
    si, sj = int(round(start[0] / MG)), int(round(start[1] / MG))
    gi, gj = int(round(goal[0] / MG)), int(round(goal[1] / MG))
    if not (0 <= si < MW and 0 <= sj < MH and 0 <= gi < MW and 0 <= gj < MH):
        return None
    prev = {}
    from collections import deque
    q = deque([(si, sj)])
    seen = bytearray(MW * MH)
    seen[sj * MW + si] = 1
    while q:
        i, j = q.popleft()
        if (i, j) == (gi, gj):
            path, cur = [], (i, j)
            while cur in prev:
                path.append(cur)
                cur = prev[cur]
            path.append((si, sj))
            path.reverse()
            return path
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ni, nj = i + di, j + dj
            if not (0 <= ni < MW and 0 <= nj < MH):
                continue
            k = nj * MW + ni
            if seen[k] or (blocked[k] and (ni, nj) != (gi, gj)):
                continue
            seen[k] = 1
            prev[(ni, nj)] = (i, j)
            q.append((ni, nj))
    return None


def _simplify(path):
    """Collapse collinear grid steps into segments."""
    pts = [(i * MG, j * MG) for i, j in path]
    out = [pts[0]]
    for k in range(1, len(pts) - 1):
        ax, ay = out[-1]
        bx, by = pts[k]
        cx, cy = pts[k + 1]
        if (bx - ax) * (cy - by) != (by - ay) * (cx - bx):
            out.append(pts[k])
    out.append(pts[-1])
    return out


def _anchor_points(board, netname, p):
    """Where a detour may pick this net up: the pad itself, or the end of any
    copper the autorouter already laid for it (nearest first)."""
    pts = [p]
    for t in board.GetTracks():
        if t.GetNetname() != netname:
            continue
        for e in (t.GetStart(), t.GetEnd()):
            pts.append((pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)))
    seen, out = set(), []
    for q in sorted(pts, key=lambda q: math.hypot(q[0] - p[0], q[1] - p[1])):
        k = (round(q[0], 2), round(q[1], 2))
        if k not in seen:
            seen.add(k)
            out.append(q)
    return out[:40]


def maze_route(board, netname, a, b, pad_boxes, segs, width=0.25):
    """Escape both ends with a via, then BFS across B.Cu.  If a pad is walled
    in by its own fan-out, pick the net up further along instead."""
    ea = eb = None
    for cand in _anchor_points(board, netname, a):
        ea = escape(cand, netname, pad_boxes, segs)
        if ea:
            a = cand
            break
    for cand in _anchor_points(board, netname, b):
        eb = escape(cand, netname, pad_boxes, segs)
        if eb:
            b = cand
            break
    if ea is None or eb is None:
        return False
    blocked = _blocked_grid(board, netname, width)
    path = _bfs(blocked, ea, eb)
    if not path or len(path) < 2:
        return False
    pts = _simplify(path)
    net = board.FindNet(netname)

    def lay(p, q, layer):
        if abs(p[0] - q[0]) < 1e-9 and abs(p[1] - q[1]) < 1e-9:
            return
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(P(*p))
        t.SetEnd(P(*q))
        t.SetWidth(mm(width))
        t.SetLayer(layer)
        t.SetNet(net)
        board.Add(t)
        segs.append((p, q, width / 2.0 + 0.28, netname))

    lay(a, ea, pcbnew.F_Cu)
    add_via(board, ea, netname)
    lay(ea, pts[0], pcbnew.B_Cu)
    for k in range(len(pts) - 1):
        lay(pts[k], pts[k + 1], pcbnew.B_Cu)
    lay(pts[-1], eb, pcbnew.B_Cu)
    add_via(board, eb, netname)
    lay(eb, b, pcbnew.F_Cu)
    segs.append((ea, ea, 0.55, netname))
    segs.append((eb, eb, 0.55, netname))
    return True


ZONE_NETS = {"GND", "GND_ISO", "+3V3", "VRLY"}


CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"


def drc_unconnected(board):
    """Ask KiCad which items are unconnected; returns [(x1,y1,x2,y2,net)]."""
    board.Save(PCB)
    rpt = os.path.join(os.path.dirname(PCB), "_drc_scratch.rpt")
    subprocess.run([CLI, "pcb", "drc", "--severity-error", "-o", rpt, PCB],
                   capture_output=True, text=True)
    if not os.path.exists(rpt):
        return []
    out, block = [], None
    for line in open(rpt):
        if line.startswith("[unconnected_items]"):
            block = []
            continue
        if block is not None:
            m = re.match(r"\s*@\((-?[\d.]+) mm, (-?[\d.]+) mm\):.*?\[([^\]]+)\]",
                         line)
            if m:
                block.append((float(m.group(1)), float(m.group(2)),
                              m.group(3)))
                if len(block) == 2:
                    out.append((block[0][0], block[0][1],
                                block[1][0], block[1][1], block[0][2]))
                    block = None
            elif line.startswith("["):
                block = None
    os.remove(rpt)
    return out


def _net_components(board, netname, pads):
    """Union-find over the copper of one net; returns the pad indices grouped
    into electrically connected sets."""
    parent = {}

    def find(k):
        parent.setdefault(k, k)
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    nodes = []                       # (key, x, y)
    for i, (x, y, _pad) in enumerate(pads):
        nodes.append(("pad%d" % i, x, y))
        find("pad%d" % i)
    for t in board.GetTracks():
        if t.GetNetname() != netname:
            continue
        a = (pcbnew.ToMM(t.GetStart().x), pcbnew.ToMM(t.GetStart().y))
        b = (pcbnew.ToMM(t.GetEnd().x), pcbnew.ToMM(t.GetEnd().y))
        ka = "n%.3f_%.3f" % a
        kb = "n%.3f_%.3f" % b
        union(ka, kb)
        nodes.append((ka, a[0], a[1]))
        nodes.append((kb, b[0], b[1]))
    # join anything that physically coincides
    for i in range(len(nodes)):
        ki, xi, yi = nodes[i]
        for j in range(i + 1, len(nodes)):
            kj, xj, yj = nodes[j]
            if abs(xi - xj) < 0.30 and abs(yi - yj) < 0.30:
                union(ki, kj)
    groups = {}
    for i in range(len(pads)):
        groups.setdefault(find("pad%d" % i), []).append(i)
    return list(groups.values())


def route_leftovers(board, pad_boxes, segs, width=0.25):
    """Route any net the autorouter could not finish, with an L, a Z, or a
    short escape onto B.Cu when the top layer is full."""
    pads = {}
    for fp in board.Footprints():
        for pad in fp.Pads():
            n = pad.GetNetname()
            if n:
                pads.setdefault(n, []).append(
                    (pcbnew.ToMM(pad.GetPosition().x),
                     pcbnew.ToMM(pad.GetPosition().y), pad))
    done, failed = 0, []
    for _pass in range(4):
        gaps = drc_unconnected(board)
        if not gaps:
            break
        # This is a touch-up tool for the handful of nets freerouting leaves,
        # not a router.  If the board is largely unrouted the autoroute step
        # failed, and scribbling L-paths over it would only create violations.
        if _pass == 0 and len(gaps) > 12:
            print("  !! %d unconnected nets - the autoroute step did not "
                  "complete; skipping the touch-up sweep" % len(gaps))
            return 0
        progress = 0
        for x1, y1, x2, y2, netname in gaps:
            if netname in ZONE_NETS:
                continue
            a, b = (x1, y1), (x2, y2)
            half = width / 2.0 + 0.2
            net = board.FindNet(netname)

            def lay(p, q, layer):
                if abs(p[0] - q[0]) < 1e-9 and abs(p[1] - q[1]) < 1e-9:
                    return
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(P(*p))
                t.SetEnd(P(*q))
                t.SetWidth(mm(width))
                t.SetLayer(layer)
                t.SetNet(net)
                board.Add(t)
                segs.append((p, q, width / 2.0 + 0.28, netname))

            routed = False
            # a straight diagonal first - the shortest hop needs no corner
            if seg_clear(a, b, pad_boxes, segs, netname, half):
                    lay(a, b, pcbnew.F_Cu)
                    routed = True
            for mid in (() if routed else
                        ((b[0], a[1]), (a[0], b[1]),
                         ((a[0] + b[0]) / 2.0, a[1]),
                         ((a[0] + b[0]) / 2.0, b[1]))):
                if seg_clear(a, mid, pad_boxes, segs, netname, half) and \
                        seg_clear(mid, b, pad_boxes, segs, netname, half):
                    lay(a, mid, pcbnew.F_Cu)
                    lay(mid, b, pcbnew.F_Cu)
                    routed = True
                    break
            if not routed:
                ea = escape(a, netname, pad_boxes, segs)
                eb = escape(b, netname, pad_boxes, segs)
                if ea and eb:
                    # try a Z route with a free corridor: straight L first,
                    # then any horizontal or vertical lane that is clear
                    cands = [((eb[0], ea[1]),), ((ea[0], eb[1]),)]
                    for yc in [1.8 + i * 1.0 for i in range(int(BOARD_H - 4))]:
                        cands.append(((ea[0], yc), (eb[0], yc)))
                    for xc in [1.8 + i * 1.0 for i in range(int(BOARD_W - 4))]:
                        cands.append(((xc, ea[1]), (xc, eb[1])))
                    for mids in cands:
                        pts = [ea] + list(mids) + [eb]
                        if all(seg_clear(pts[k], pts[k + 1], pad_boxes, segs,
                                         netname, half, bottom=True)
                               for k in range(len(pts) - 1)):
                            lay(a, ea, pcbnew.F_Cu)
                            add_via(board, ea, netname)
                            for k in range(len(pts) - 1):
                                lay(pts[k], pts[k + 1], pcbnew.B_Cu)
                            add_via(board, eb, netname)
                            lay(eb, b, pcbnew.F_Cu)
                            segs.append((ea, ea, 0.55, netname))
                            segs.append((eb, eb, 0.55, netname))
                            routed = True
                            break
            if routed:
                done += 1
                progress += 1
            else:
                failed.append("%s (%.1f,%.1f)->(%.1f,%.1f)"
                              % (netname, a[0], a[1], b[0], b[1]))
        if not progress:
            break
    print("leftover nets routed: %d" % done)
    if failed:
        print("  !! still unrouted:", ", ".join(failed))
    return done


VALUE_SYNC = {"C21": "100n/16V", "C22": "100n/16V"}


def main():
    board = pcbnew.LoadBoard(PCB)
    for ref, val in VALUE_SYNC.items():
        fp = board.FindFootprintByReference(ref)
        if fp is not None:
            fp.SetValue(val)
    print("rule areas honoured:", collect_rule_areas(board))
    nrf, nhv = collect_rf(board)
    print("keep-outs: RF %d segs (%.2f mm), mains %d items (%.2f mm)"
          % (nrf, RF_KEEP, nhv, HV_KEEP))
    pad_boxes = boxes(board)
    segs = track_segs(board)
    placed = []

    def try_via(p, fence=False):
        netname = domain_net(p)
        if not in_board(p) and not (fence and _fence_ok(p)
                                    and 1.4 < p[1] < BOARD_H - 1.4
                                    and not in_rule_area(p)
                                    and not near_rf(p)
                                    and not near_hv(p)
                                    and not any(x0 <= p[0] <= x1
                                                and y0 <= p[1] <= y1
                                                for x0, y0, x1, y1
                                                in KEEPOUTS)):
            return False
        if not point_clear(p, pad_boxes, segs, netname):
            return False
        for q in placed:
            if math.hypot(p[0] - q[0], p[1] - q[1]) < 1.6:
                return False
        if add_via(board, p, netname):
            placed.append(p)
            segs.append((p, p, VIA_D / 2.0 + 0.45, netname))
            return True
        return False

    # 1. sweep up anything the autorouter left unrouted, while the board is
    #    still open - the stitching grid below would otherwise block the path
    # The leftover sweep used to live here.  It drew L-shaped paths without
    # measuring them, and after a router time-out it once laid 120 of them and
    # 83 DRC violations with it.  scripts/route_maze.py does that job now, and
    # refuses any path it cannot verify, so it runs after this script instead.

    # 2. stitching grid
    grid = 0
    y = GRID
    while y < BOARD_H:
        x = GRID
        while x < BOARD_W:
            if try_via((x, y)):
                grid += 1
            x += GRID
        y += GRID

    # 3. fence along both sides of the isolation slot
    fence = 0
    yy = SLOT_Y0
    while yy <= SLOT_Y1:
        if try_via((SLOT_X - 3.0, yy), fence=True):
            fence += 1
        if try_via((SLOT_X + SLOT_W + 3.0, yy), fence=True):
            fence += 1
        yy += 2.5

    # 4. board-edge stitching
    edge = 0
    for i in range(int(BOARD_W / EDGE_PITCH) + 1):
        x = i * EDGE_PITCH
        for y in (EDGE_INSET, BOARD_H - EDGE_INSET):
            if try_via((x, y)):
                edge += 1
    for i in range(int(BOARD_H / EDGE_PITCH) + 1):
        y = i * EDGE_PITCH
        for x in (EDGE_INSET, BOARD_W - EDGE_INSET):
            if try_via((x, y)):
                edge += 1

    # 5. enforce the 50 ohm width on every RF segment the router may have
    #    added at the default width  [Q] 4.3 / 4.4
    fixed = 0
    for t in board.GetTracks():
        if t.GetNetname() in ("ANT_RF", "ANT_FEED") and \
                t.Type() != pcbnew.PCB_VIA_T and \
                abs(pcbnew.ToMM(t.GetWidth()) - 0.35) > 0.001:
            t.SetWidth(mm(0.35))
            fixed += 1
    if fixed:
        print("RF segments widened to 0.35 mm:", fixed)

    # 6. re-fill
    zones = [z for z in board.Zones() if not z.GetIsRuleArea()]
    pcbnew.ZONE_FILLER(board).Fill(zones)
    board.Save(PCB)

    print("stitching vias: grid %d, slot fence %d, board edge %d (total %d)"
          % (grid, fence, edge, len(placed)))
    print("zones refilled:", len(zones))

    conn = board.GetConnectivity()
    print("unconnected items remaining:", conn.GetUnconnectedCount(False))


if __name__ == "__main__":
    main()
