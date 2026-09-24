#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A layer-aware A* router for the connections the autorouter leaves behind.

This is not a general-purpose router.  It finishes a handful of nets on a board
that is otherwise routed, and it does so under the same rules the rest of the
board obeys:

  * per-net-class track width and clearance, read from the board itself
  * both signal layers (F.Cu and B.Cu), with a via cost so it prefers to stay
    on one layer
  * every existing pad, track, via, rule area and board edge treated as an
    obstacle, on the layer where it actually blocks
  * 45 degree geometry only - the grid path is reduced to straight and
    diagonal runs, then straightened wherever the straighter route measures
    clear

It routes in order of increasing difficulty so the easy nets do not get boxed
in by the hard ones, and - this is the part that matters - it measures every
path against the board exactly before laying it, and throws away anything that
falls short.  A grid is an approximation; the board is not.

Run twice: once after route_pcb.py, where there is the most room, and once
after finish_pcb.py, for whatever the stitching vias reopened.
"""

import heapq
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
CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"

GRID = 0.25                    # mm, routing grid
VIA_D, VIA_DRILL = 0.6, 0.3
VIA_COST = 12.0                # in grid steps - discourages layer changes
EDGE_CLEAR = 0.5               # board setup: copper to board edge
MASK_WEB = 0.30                # narrowest solder-mask web worth leaving
RF_VIA_CLEAR = 0.7             # Quectel 4.4, 2 x W with W = 0.35 mm
BRIDGE_MAX = 1.5               # a gap this small is closed, not searched
INNER = "inner"                # a plane layer - this router does not route on one
MARGINS = (0.05, 0.15, 0.30, 0.50)   # grid margins tried, in order
DIAG = math.sqrt(2.0)

LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)
LAYER_NAME = {pcbnew.F_Cu: "F.Cu", pcbnew.B_Cu: "B.Cu"}


def mm(v):
    return pcbnew.FromMM(float(v))


def P(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


def tomm(v):
    return pcbnew.ToMM(v)


# ---------------------------------------------------------------------------
class Grid(object):
    """Occupancy per layer, in units of GRID."""

    def __init__(self, board, w, h):
        self.b = board
        self.w = int(w / GRID) + 1
        self.h = int(h / GRID) + 1
        self.blocked = {la: bytearray(self.w * self.h) for la in LAYERS}
        # a through via pierces all four layers, so it has its own map
        self.viablock = bytearray(self.w * self.h)

    def idx(self, i, j):
        return j * self.w + i

    def inside(self, i, j):
        return 0 <= i < self.w and 0 <= j < self.h

    def _span(self, x0, y0, x1, y1):
        """Cells whose centre falls inside the box.

        Rounding outward instead would cost a whole 0.25 mm cell on each side,
        which is the difference between a via fitting beside a keep-out and
        not.  What the rounding lets through is caught by the exact
        measurement before anything is laid.
        """
        return (range(max(0, int(math.ceil(x0 / GRID))),
                      min(self.w - 1, int(math.floor(x1 / GRID))) + 1),
                range(max(0, int(math.ceil(y0 / GRID))),
                      min(self.h - 1, int(math.floor(y1 / GRID))) + 1))

    def mark_box(self, layer, x0, y0, x1, y1):
        xs, ys = self._span(x0, y0, x1, y1)
        blk = self.blocked[layer]
        for i in xs:
            for j in ys:
                blk[j * self.w + i] = 1

    def mark_seg(self, layer, a, b, r):
        """Stamp a track corridor.  A bounding box would wall off the whole
        square a 45 degree run spans, which is most of a crowded corner."""
        n = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) / (GRID / 2.0)))
        for k in range(n + 1):
            u = float(k) / n
            x = a[0] + (b[0] - a[0]) * u
            y = a[1] + (b[1] - a[1]) * u
            self.mark_box(layer, x - r, y - r, x + r, y + r)

    def mark_via_seg(self, a, b, r):
        n = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) / (GRID / 2.0)))
        for k in range(n + 1):
            u = float(k) / n
            x = a[0] + (b[0] - a[0]) * u
            y = a[1] + (b[1] - a[1]) * u
            self.mark_via(x - r, y - r, x + r, y + r)

    def clear_box(self, layer, x0, y0, x1, y1):
        xs, ys = self._span(x0, y0, x1, y1)
        blk = self.blocked[layer]
        for i in xs:
            for j in ys:
                blk[j * self.w + i] = 0

    def mark_via(self, x0, y0, x1, y1):
        xs, ys = self._span(x0, y0, x1, y1)
        for i in xs:
            for j in ys:
                self.viablock[j * self.w + i] = 1

    def via_free(self, i, j):
        return self.inside(i, j) and not self.viablock[self.idx(i, j)]

    def free(self, layer, i, j):
        return self.inside(i, j) and not self.blocked[layer][self.idx(i, j)]


# ---------------------------------------------------------------------------
RULES_OF = {}


def net_rules(board, netname):
    """Track width and clearance for a net, from the board's own net classes."""
    if netname in RULES_OF:
        return RULES_OF[netname]
    RULES_OF[netname] = _net_rules(board, netname)
    return RULES_OF[netname]


def _net_rules(board, netname):
    net = board.FindNet(netname)
    nc = net.GetNetClassName() if net else "Default"
    settings = board.GetDesignSettings()
    try:
        cls = settings.GetNetClasses().find(nc)
        return tomm(cls.GetTrackWidth()), tomm(cls.GetClearance())
    except Exception:                                   # noqa: BLE001
        pass
    # fall back to the project file
    import json
    pro = os.path.join(ROOT, "LFX_FC_R1.kicad_pro")
    try:
        doc = json.load(open(pro))
        for c in doc["net_settings"]["classes"]:
            if c["name"] == nc:
                return c["track_width"], c["clearance"]
    except Exception:                                   # noqa: BLE001
        pass
    return 0.25, 0.2


NETCLASS_OF = {}


def netclass(board, name):
    if name not in NETCLASS_OF:
        n = board.FindNet(name)
        NETCLASS_OF[name] = n.GetNetClassName() if n else "Default"
    return NETCLASS_OF[name]


def pair_clearance(board, netname, cls, other, base, safe):
    """Clearance the DRC will demand between our net and one other item.

    Two things the net class alone does not tell you: KiCad takes the larger of
    the two classes' clearances, not ours, and the custom rules in
    LFX_FC_R1.kicad_dru override both.  Miss either and the router lays
    copper the DRC then rejects.
    """
    ocls = netclass(board, other) if other else "Default"
    if other:
        base = max(base, net_rules(board, other)[1])
    if ocls == "HV" and cls != "HV":          # relay contacts to low voltage
        return 2.0 + safe
    if cls == "HV" and ocls != "HV":
        return 2.0 + safe
    return base + safe


def build_grid(board, netname, width, clearance, safe):
    """Occupancy for one net.

    Three things block a track: copper of another net on the same routing
    layer, a keep-out, and the board edge.  A via is blocked by all of those on
    either layer plus anything on an inner layer, because a through via pierces
    all four.
    """
    bb = board.GetBoardEdgesBoundingBox()
    g = Grid(board, tomm(bb.GetX() + bb.GetWidth()) + 2,
             tomm(bb.GetY() + bb.GetHeight()) + 2)
    cls = netclass(board, netname)
    half = width / 2.0 + clearance + safe
    vhalf = VIA_D / 2.0 + clearance + safe

    def box(item_bb, pad):
        return (tomm(item_bb.GetX()) - pad, tomm(item_bb.GetY()) - pad,
                tomm(item_bb.GetX() + item_bb.GetWidth()) + pad,
                tomm(item_bb.GetY() + item_bb.GetHeight()) + pad)

    # --- board edge.  Copper must stand off EDGE_CLEAR from the outline, so
    #     the track centre line stands off EDGE_CLEAR + half the width.
    ex0 = tomm(bb.GetX()) + EDGE_CLEAR + width / 2.0
    ey0 = tomm(bb.GetY()) + EDGE_CLEAR + width / 2.0
    ex1 = tomm(bb.GetX() + bb.GetWidth()) - EDGE_CLEAR - width / 2.0
    ey1 = tomm(bb.GetY() + bb.GetHeight()) - EDGE_CLEAR - width / 2.0
    for i in range(g.w):
        x = i * GRID
        for j in range(g.h):
            y = j * GRID
            if not (ex0 <= x <= ex1 and ey0 <= y <= ey1):
                k = g.idx(i, j)
                for la in LAYERS:
                    g.blocked[la][k] = 1
                g.viablock[k] = 1
    # the isolation slot and any other interior cut-out
    for d in board.GetDrawings():
        if d.GetLayer() != pcbnew.Edge_Cuts:
            continue
        db = d.GetBoundingBox()
        if tomm(db.GetWidth()) > 20 and tomm(db.GetHeight()) > 20:
            continue                            # that is the outline itself
        x0, y0, x1, y1 = box(db, EDGE_CLEAR + width / 2.0)
        for la in LAYERS:
            g.mark_box(la, x0, y0, x1, y1)
        g.mark_via(x0, y0, x1, y1)

    # --- pads.  The halo is the larger of the electrical clearance and the
    #     solder-mask web, otherwise the mask opens into one aperture and the
    #     board fails the mask-bridge check instead of the clearance check.
    for fp in board.Footprints():
        for pad in fp.Pads():
            pn = pad.GetNetname()
            if pn == netname:
                continue                    # our own copper is not an obstacle
            c = pair_clearance(board, netname, cls, pn, clearance, safe)
            pad_half = width / 2.0 + max(c, MASK_WEB)
            x0, y0, x1, y1 = box(pad.GetBoundingBox(), pad_half)
            through = pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
            for la in LAYERS:
                if not through and not pad.IsOnLayer(la):
                    continue
                g.mark_box(la, x0, y0, x1, y1)
            vx0, vy0, vx1, vy1 = box(pad.GetBoundingBox(),
                                     VIA_D / 2.0 + max(c, MASK_WEB))
            g.mark_via(vx0, vy0, vx1, vy1)

    # --- tracks and vias, on the layer where each one actually sits
    for t in board.GetTracks():
        tn = t.GetNetname()
        if tn == netname:
            continue
        c = pair_clearance(board, netname, cls, tn, clearance, safe)
        la = t.GetLayer()
        is_via = t.Type() == pcbnew.PCB_VIA_T
        tw = tomm(t.GetWidth()) / 2.0
        a, b = t.GetStart(), t.GetEnd()
        th = width / 2.0 + c + tw
        vh = VIA_D / 2.0 + c + tw
        pa = (tomm(a.x), tomm(a.y))
        pb = (tomm(b.x), tomm(b.y))
        if is_via:
            for lb in LAYERS:
                g.mark_seg(lb, pa, pb, th)
            g.mark_via_seg(pa, pb, vh)
        elif la in LAYERS:
            g.mark_seg(la, pa, pb, th)
            g.mark_via_seg(pa, pb, vh)
        else:
            # inner layer: invisible to a track, fatal to a through via
            g.mark_via_seg(pa, pb, vh)
        # Quectel 4.4: a ground via stands 2 x W off an RF trace
        if netclass(board, tn) == "RF":
            g.mark_via_seg(pa, pb, VIA_D / 2.0 + RF_VIA_CLEAR + tw + safe)

    # --- keep-outs, honoured exactly as the DRC honours them
    zs = list(board.Zones())
    for fp in board.Footprints():
        try:
            zs += list(fp.Zones())
        except Exception:                               # noqa: BLE001
            pass
    for z in zs:
        if not z.GetIsRuleArea():
            continue
        zb = z.Outline().BBox()
        if z.GetDoNotAllowTracks():
            x0, y0, x1, y1 = box(zb, half)
            for la in LAYERS:
                g.mark_box(la, x0, y0, x1, y1)
            g.mark_via(x0, y0, x1, y1)
        elif z.GetDoNotAllowVias():
            x0, y0, x1, y1 = box(zb, vhalf)
            g.mark_via(x0, y0, x1, y1)

    # --- our own pads are copper that is already there.  A pad sitting inside
    #     a keep-out margin would otherwise be unreachable: the search could
    #     not step onto the one cell it has to finish on.
    for fp in board.Footprints():
        for pad in fp.Pads():
            if pad.GetNetname() != netname:
                continue
            pb = pad.GetBoundingBox()
            x0 = tomm(pb.GetX()) + width / 2.0
            y0 = tomm(pb.GetY()) + width / 2.0
            x1 = tomm(pb.GetX() + pb.GetWidth()) - width / 2.0
            y1 = tomm(pb.GetY() + pb.GetHeight()) - width / 2.0
            if x1 < x0 or y1 < y0:
                p = pad.GetPosition()
                x0 = x1 = tomm(p.x)
                y0 = y1 = tomm(p.y)
            through = pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
            for la in LAYERS:
                if not through and not pad.IsOnLayer(la):
                    continue
                g.clear_box(la, x0, y0, x1, y1)
    return g


# ---------------------------------------------------------------------------
NB = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
      (1, 1, DIAG), (1, -1, DIAG), (-1, 1, DIAG), (-1, -1, DIAG)]


def astar(g, netname, starts, goals):
    """3D A* over (i, j, layer).  Nodes in, node path out."""
    goalset = set(goals)
    if not goalset or not starts:
        return None

    def h(n):
        return min(max(abs(n[0] - q[0]), abs(n[1] - q[1])) for q in goalset)

    openq = []
    came, gsc = {}, {}
    for n in starts:
        gsc[n] = 0.0
        heapq.heappush(openq, (h(n), n))
    seen = set()
    while openq:
        _f, n = heapq.heappop(openq)
        if n in seen:
            continue
        seen.add(n)
        i, j, la = n
        if n in goalset:
            path = [n]
            while n in came:
                n = came[n]
                path.append(n)
            path.reverse()
            return path
        base = gsc[n]
        for di, dj, cost in NB:
            ni, nj = i + di, j + dj
            if not (g.free(la, ni, nj) or (ni, nj, la) in goalset):
                continue
            if di and dj:            # no corner cutting on a diagonal
                if not (g.free(la, i + di, j)
                        and g.free(la, i, j + dj)):
                    continue
            m = (ni, nj, la)
            ng = base + cost
            if ng < gsc.get(m, 1e18):
                gsc[m] = ng
                came[m] = n
                heapq.heappush(openq, (ng + h((ni, nj)), m))
        # layer change
        other = LAYERS[1] if la == LAYERS[0] else LAYERS[0]
        if (g.free(other, i, j) or (i, j, other) in goalset) \
                and g.via_free(i, j):
            m = (i, j, other)
            ng = base + VIA_COST
            if ng < gsc.get(m, 1e18):
                gsc[m] = ng
                came[m] = n
                heapq.heappush(openq, (ng + h((i, j)), m))
    return None


def simplify(path):
    """Collapse the grid path, keeping every change of direction.

    Only steps with the same direction vector are merged, so what comes out is
    made of 90 and 45 degree runs and nothing else.  Testing collinearity
    against the last kept point instead - which is what this did at first -
    turns a staircase into one straight line of some arbitrary slope: a line
    that was never searched, and that lands wherever it lands.  That is how a
    track ended up 1.67 mm from a mains pad the grid had walled off at 2.0 mm.
    """
    out = [path[0]]
    for k in range(1, len(path) - 1):
        a, b, c = path[k - 1], path[k], path[k + 1]
        if a[2] != b[2] or b[2] != c[2]:
            out.append(b)
            continue
        if (b[0] - a[0], b[1] - a[1]) != (c[0] - b[0], c[1] - b[1]):
            out.append(b)
    out.append(path[-1])
    return out


def _corner(p, q):
    """The two 45 degree ways to get from p to q: diagonal first, or last."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    m = min(abs(dx), abs(dy))
    sx = 1.0 if dx >= 0 else -1.0
    sy = 1.0 if dy >= 0 else -1.0
    return ((p[0] + sx * m, p[1] + sy * m),
            (q[0] - sx * m, q[1] - sy * m))


def straighten(board, netname, pts, width, clearance, obs):
    """Pull the staircase out of a grid path.

    A search on a 0.25 mm grid walks a diagonal as a flight of steps.  It is
    electrically fine and it looks like nothing a person would draw, so each
    run of points is replaced by the two-segment 45 degree route between its
    ends wherever that route measures clear.  Anything that does not measure
    clear keeps its steps.
    """
    changed = True
    while changed and len(pts) > 2:
        changed = False
        for i in range(len(pts) - 2):
            for j in range(len(pts) - 1, i + 1, -1):
                if pts[i][2] != pts[j][2]:
                    continue
                if any(p[2] != pts[i][2] for p in pts[i:j + 1]):
                    continue
                for knee in _corner(pts[i], pts[j]):
                    cand = pts[:i + 1]
                    if abs(knee[0] - pts[i][0]) > 1e-9 \
                            or abs(knee[1] - pts[i][1]) > 1e-9:
                        cand.append((knee[0], knee[1], pts[i][2]))
                    cand += pts[j:]
                    if len(cand) >= len(pts):
                        continue
                    if shortfall(board, netname, cand, width, clearance,
                                 obs) <= 1e-6:
                        pts = cand
                        changed = True
                        break
                if changed:
                    break
            if changed:
                break
    return pts


# ---------------------------------------------------------------------------
# Exact verification.
#
# The search runs on a 0.25 mm grid, and the two ends of a path are pulled onto
# the real items they have to meet, so a finished path can sit a fraction of a
# cell closer to something than the grid believed.  Rather than inflate the
# grid margin until nothing routes, every candidate path is measured against
# the board before it is laid, and only a path that clears everything is kept.
# ---------------------------------------------------------------------------
def seg_seg_dist(p, q, r, t):
    """Shortest distance between segments p-q and r-t."""
    def clamp(v):
        return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)

    ux, uy = q[0] - p[0], q[1] - p[1]
    vx, vy = t[0] - r[0], t[1] - r[1]
    wx, wy = p[0] - r[0], p[1] - r[1]
    a = ux * ux + uy * uy
    b = ux * vx + uy * vy
    c = vx * vx + vy * vy
    d = ux * wx + uy * wy
    e = vx * wx + vy * wy
    den = a * c - b * b
    if den > 1e-12:
        sc = clamp((b * e - c * d) / den)
    else:
        sc = 0.0
    tc = (b * sc + e) / c if c > 1e-12 else 0.0
    tc = clamp(tc)
    sc = clamp((b * tc - d) / a) if a > 1e-12 else 0.0
    dx = (p[0] + sc * ux) - (r[0] + tc * vx)
    dy = (p[1] + sc * uy) - (r[1] + tc * vy)
    return math.hypot(dx, dy)


def seg_rect_dist(p, q, x0, y0, x1, y1):
    """Shortest distance between a segment and an axis-aligned rectangle."""
    if (min(p[0], q[0]) <= x1 and max(p[0], q[0]) >= x0
            and min(p[1], q[1]) <= y1 and max(p[1], q[1]) >= y0):
        # cheap reject only; fall through to the edge tests
        pass
    edges = (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)),
             ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0)))
    d = min(seg_seg_dist(p, q, a, b) for a, b in edges)
    if x0 <= p[0] <= x1 and y0 <= p[1] <= y1:
        return 0.0
    return d


def obstacles(board, netname):
    """Every foreign item, as (layers, kind, geometry, net)."""
    out = []
    for fp in board.Footprints():
        for pad in fp.Pads():
            pn = pad.GetNetname()
            if pn == netname:
                continue
            bbx = pad.GetBoundingBox()
            rect = (tomm(bbx.GetX()), tomm(bbx.GetY()),
                    tomm(bbx.GetX() + bbx.GetWidth()),
                    tomm(bbx.GetY() + bbx.GetHeight()))
            through = pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
            las = set(LAYERS) if through else {la for la in LAYERS
                                               if pad.IsOnLayer(la)}
            out.append((las, "rect", rect, 0.0, pn))
    for t in board.GetTracks():
        tn = t.GetNetname()
        if tn == netname:
            continue
        a, b = t.GetStart(), t.GetEnd()
        g = ((tomm(a.x), tomm(a.y)), (tomm(b.x), tomm(b.y)))
        hw = tomm(t.GetWidth()) / 2.0
        if t.Type() == pcbnew.PCB_VIA_T:
            out.append((set(LAYERS) | {"inner"}, "seg", g, hw, tn))
        elif t.GetLayer() in LAYERS:
            out.append(({t.GetLayer()}, "seg", g, hw, tn))
        else:
            out.append(({"inner"}, "seg", g, hw, tn))
    return out


def shortfall(board, netname, pts, width, clearance, obs):
    """How far the worst point of this path falls short, in mm.  0 means clear."""
    cls = netclass(board, netname)
    worst = 0.0
    pieces = []
    for a, b in zip(pts, pts[1:]):
        if a[2] != b[2]:
            pieces.append(((a[0], a[1]), (a[0], a[1]),
                           VIA_D / 2.0, set(LAYERS) | {"inner"}))
        elif math.hypot(b[0] - a[0], b[1] - a[1]) >= 1e-4:
            pieces.append(((a[0], a[1]), (b[0], b[1]),
                           width / 2.0, {a[2]}))
    for p, q, hw, las in pieces:
        for olas, kind, geo, ohw, onet in obs:
            if not (las & olas):
                continue
            need = pair_clearance(board, netname, cls, onet, clearance, 0.0)
            if kind == "rect":
                d = seg_rect_dist(p, q, *geo) - hw
                need = max(need, MASK_WEB) if las & set(LAYERS) else need
            else:
                d = seg_seg_dist(p, q, geo[0], geo[1]) - hw - ohw
            if d < need:
                worst = max(worst, need - d)
    return worst


def drc_gaps(board):
    """The item pairs KiCad reports as unconnected.

    Each entry is (x, y, kind, net) per end.  A pair that names a zone is not a
    routing job - the pour reaches it or it does not - so those are handed back
    separately for a fan-out via instead of a track.
    """
    board.Save(PCB)
    rpt = os.path.join(ROOT, "_maze_drc.rpt")
    subprocess.run([CLI, "pcb", "drc", "--severity-error", "-o", rpt, PCB],
                   capture_output=True, text=True)
    if not os.path.exists(rpt):
        return [], []
    tracks, zones = [], []
    block, inblock = [], False
    for line in open(rpt):
        if line.startswith("[unconnected_items]"):
            inblock, block = True, []
            continue
        if not inblock:
            continue
        if line.startswith("["):
            inblock = False
            continue
        m = re.match(r"\s*@\((-?[\d.]+) mm, (-?[\d.]+) mm\): "
                     r"(\w+)[^\[]*\[([^\]]+)\]", line)
        if not m:
            continue
        # "on F.Cu", "on B.Cu", or an inner plane by its name ("on GND").
        # Reading a plane as F.Cu - which is what matching only F and B does -
        # turns "these two meet at a point but on different layers" into
        # "these two are the same point on one layer", and the via that is the
        # whole answer never gets placed.
        lm = re.search(r" on ([A-Za-z0-9_.&]+)", line)
        lname = lm.group(1) if lm else ""
        if lname.startswith("F.Cu"):
            layer = pcbnew.F_Cu
        elif lname.startswith("B.Cu"):
            layer = pcbnew.B_Cu
        elif lname:
            layer = INNER
        else:
            layer = None
        block.append((float(m.group(1)), float(m.group(2)),
                      m.group(3), m.group(4), layer))
        if len(block) == 2:
            a, b = block
            if a[2] == "Zone" and b[2] == "Zone":
                pass          # two pours of one net: stitching vias, not a route
            elif a[2] == "Zone" or b[2] == "Zone":
                zones.append((a, b))
            else:
                tracks.append((a, b))
            block = []
    os.remove(rpt)
    return tracks, zones


def cell(x, y, layer):
    return (int(round(x / GRID)), int(round(y / GRID)), layer)


def ends_at(anchors, item, reach=2):
    """The cells the search may start from, or must finish on, for one end.

    Only copper of this net within a couple of cells of the item the DRC named
    counts.  Accepting every anchor on the net - which is what happens if the
    item's layer is unknown and the filter is skipped - lets the search finish
    next to the other end in one step and then have its start point dragged
    back across the board, which is a straight line through whatever lies
    between.
    """
    i0, j0 = int(round(item[0] / GRID)), int(round(item[1] / GRID))
    near = [n for n in anchors
            if abs(n[0] - i0) + abs(n[1] - j0) <= reach]
    if near:
        return near
    if item[4] is not None and item[4] != INNER:
        return [(i0, j0, item[4])]
    return [(i0, j0, la) for la in LAYERS]


def item_geometry(board, x, y, net, kind, layer):
    """The real extent of the item the DRC named, not just its origin.

    A DRC line reports a track at its *start point*.  For a 21 mm track the
    place two nets need joining can be 21 mm from the coordinate in the
    report, and a via dropped at the reported point connects nothing.  That is
    what put eight stacked vias at one end of an inner-layer track while the
    far end stayed open, and what made the router report the same gap as
    "0.0 mm apart" pass after pass.
    """
    best = None
    for t in board.GetTracks():
        if t.GetNetname() != net or t.Type() == pcbnew.PCB_VIA_T:
            continue
        a = (tomm(t.GetStart().x), tomm(t.GetStart().y))
        b = (tomm(t.GetEnd().x), tomm(t.GetEnd().y))
        if abs(a[0] - x) < 1e-3 and abs(a[1] - y) < 1e-3:
            best = (a, b)
            break
    if best is None:
        return ((x, y), (x, y))
    return best


def closest_points(g1, g2):
    """The two points, one on each item, where they come nearest."""
    best = (1e18, g1[0], g2[0])
    for p in g1:
        for q in g2:
            d = math.hypot(p[0] - q[0], p[1] - q[1])
            if d < best[0]:
                best = (d, p, q)
    # also the perpendicular foot of each endpoint on the other segment
    for (a, b), other in ((g1, g2), (g2, g1)):
        for p in other:
            ux, uy = b[0] - a[0], b[1] - a[1]
            L = ux * ux + uy * uy
            if L < 1e-12:
                continue
            u = max(0.0, min(1.0, ((p[0] - a[0]) * ux
                                   + (p[1] - a[1]) * uy) / L))
            f = (a[0] + u * ux, a[1] + u * uy)
            d = math.hypot(f[0] - p[0], f[1] - p[1])
            if d < best[0]:
                best = (d, f, p) if (a, b) is g1 else (d, p, f)
    return best[1], best[2]


def already_there(board, net, a, b, layer=None, via=False):
    """True if this exact piece of copper is on the board already."""
    for t in board.GetTracks():
        if t.GetNetname() != net:
            continue
        isv = t.Type() == pcbnew.PCB_VIA_T
        if isv != via:
            continue
        ta = (tomm(t.GetStart().x), tomm(t.GetStart().y))
        tb = (tomm(t.GetEnd().x), tomm(t.GetEnd().y))
        if via:
            if math.hypot(ta[0] - a[0], ta[1] - a[1]) < 0.02:
                return True
            continue
        if layer is not None and t.GetLayer() != layer:
            continue
        if (math.hypot(ta[0] - a[0], ta[1] - a[1]) < 0.02
                and math.hypot(tb[0] - b[0], tb[1] - b[1]) < 0.02) or \
           (math.hypot(ta[0] - b[0], ta[1] - b[1]) < 0.02
                and math.hypot(tb[0] - a[0], tb[1] - a[1]) < 0.02):
            return True
    return False


def net_anchors(board, netname):
    """Every (cell, layer) this net already occupies - pads, tracks, vias."""
    out = set()
    for fp in board.Footprints():
        for pad in fp.Pads():
            if pad.GetNetname() != netname:
                continue
            p = pad.GetPosition()
            for la in LAYERS:
                if pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD \
                        and not pad.IsOnLayer(la):
                    continue
                out.add(cell(tomm(p.x), tomm(p.y), la))
    for t in board.GetTracks():
        if t.GetNetname() != netname:
            continue
        las = LAYERS if t.Type() == pcbnew.PCB_VIA_T else (t.GetLayer(),)
        for e in (t.GetStart(), t.GetEnd()):
            for la in las:
                if la in LAYERS:
                    out.add(cell(tomm(e.x), tomm(e.y), la))
    return out


def lay(board, netname, pts, width):
    """Lay a polyline given in millimetres.  pts is [(x, y, layer), ...]."""
    net = board.FindNet(netname)
    laid, vias = 0, 0
    for a, b in zip(pts, pts[1:]):
        if a[2] != b[2]:
            if already_there(board, netname, (a[0], a[1]), None, via=True):
                continue
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(P(a[0], a[1]))
            v.SetWidth(mm(VIA_D))
            v.SetDrill(mm(VIA_DRILL))
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            v.SetNet(net)
            board.Add(v)
            vias += 1
            continue
        if math.hypot(b[0] - a[0], b[1] - a[1]) < 1e-4:
            continue                      # never lay a zero length segment
        if already_there(board, netname, (a[0], a[1]), (b[0], b[1]), a[2]):
            continue                      # this copper is on the board already
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(P(a[0], a[1]))
        t.SetEnd(P(b[0], b[1]))
        t.SetWidth(mm(width))
        t.SetLayer(a[2])
        t.SetNet(net)
        board.Add(t)
        laid += 1
    return laid, vias


def to_mm_path(path, ax, ay, bx, by):
    """Grid path -> millimetre polyline, with both ends on the real items."""
    pts = [(p[0] * GRID, p[1] * GRID, p[2]) for p in path]
    pts[0] = (ax, ay, pts[0][2])
    pts[-1] = (bx, by, pts[-1][2])
    return pts


def bridge_path(a, b):
    """Two ends of the same net a hair apart - close them directly.

    The autorouter leaves these behind when a segment stops just short of the
    next one.  There is nothing to search for: the gap is smaller than the
    track is wide.  When the two ends are on different layers the answer is a
    via, and when one of them is on an inner plane a via is the only answer,
    because a through via reaches every layer.
    """
    la = a[4] if a[4] is not None else pcbnew.F_Cu
    lb = b[4] if b[4] is not None else la
    # Two items the DRC puts at the same coordinate are not separated by any
    # distance a track could cover: whatever the report says about their
    # layers, what is missing between them is a via.  Without this the router
    # reports "0.0 mm apart - no path", which reads as nonsense and is.
    if math.hypot(b[0] - a[0], b[1] - a[1]) < 0.05:
        return [(a[0], a[1], pcbnew.F_Cu), (a[0], a[1], pcbnew.B_Cu)]
    if la == INNER and lb == INNER:
        return None                     # nothing here a surface route can fix
    if la == INNER:
        return [(a[0], a[1], pcbnew.F_Cu), (a[0], a[1], pcbnew.B_Cu)]
    if lb == INNER:
        return [(b[0], b[1], pcbnew.F_Cu), (b[0], b[1], pcbnew.B_Cu)]
    if la == lb:
        return [(a[0], a[1], la), (b[0], b[1], lb)]
    return [(a[0], a[1], la), (a[0], a[1], lb), (b[0], b[1], lb)]


def fanout(board, netname, x, y, layer, width, clearance):
    """Drop a via beside a pad the pour never reached.

    A ground pin that the outer pour cannot get to is not a routing problem -
    there is nothing on the far side to route to.  It wants a via down to the
    plane, as close to the pin as the rules allow.
    """
    obs = obstacles(board, netname)
    la = layer if layer is not None else pcbnew.F_Cu
    start = cell(x, y, la)
    for safe in MARGINS:
        g = build_grid(board, netname, width, clearance, safe)
        for r in range(1, 13):
            ring = []
            for di in range(-r, r + 1):
                for dj in range(-r, r + 1):
                    if max(abs(di), abs(dj)) != r:
                        continue
                    i, j = start[0] + di, start[1] + dj
                    if g.via_free(i, j) and g.free(la, i, j):
                        ring.append((i, j, la))
            if not ring:
                continue
            ring.sort(key=lambda n: (n[0] - start[0]) ** 2
                      + (n[1] - start[1]) ** 2)
            for goal in ring[:8]:
                path = astar(g, netname, [start], [goal])
                if not path:
                    continue
                pts = [(p[0] * GRID, p[1] * GRID, p[2])
                       for p in simplify(path)]
                pts[0] = (x, y, la)
                other = LAYERS[1] if la == LAYERS[0] else LAYERS[0]
                pts.append((pts[-1][0], pts[-1][1], other))
                if shortfall(board, netname, pts, width, clearance,
                             obs) > 1e-6:
                    continue
                return lay(board, netname, pts, width)
    return 0, 0


def main():
    board = pcbnew.LoadBoard(PCB)
    bb = board.GetBoardEdgesBoundingBox()
    print("board %.0f x %.0f mm, grid %.2f mm"
          % (tomm(bb.GetWidth()), tomm(bb.GetHeight()), GRID))

    total_t, total_v, done = 0, 0, 0
    failed, zone_gaps, reasons_out = [], [], {}
    for _attempt in range(12):
        gaps, zone_gaps = drc_gaps(board)
        if not gaps:
            break
        # easiest first, so a short hop is not walled in by a long one
        gaps.sort(key=lambda p: math.hypot(p[1][0] - p[0][0],
                                           p[1][1] - p[0][1]))
        progress = 0
        obs_cache, reasons = {}, reasons_out
        for a, b in gaps:
            netname = a[3]
            # the DRC names each item by its origin; join them where they are
            # actually nearest each other
            if a[2] == "Track" or b[2] == "Track":
                ga = item_geometry(board, a[0], a[1], netname, a[2], a[4])
                gb = item_geometry(board, b[0], b[1], netname, b[2], b[4])
                pa, pb = closest_points(ga, gb)
                a = (pa[0], pa[1], a[2], a[3], a[4])
                b = (pb[0], pb[1], b[2], b[3], b[4])
            span = math.hypot(b[0] - a[0], b[1] - a[1])
            width, clearance = net_rules(board, netname)
            if netname not in obs_cache:
                obs_cache[netname] = obstacles(board, netname)
            obs = obs_cache[netname]
            pts, kind = None, "routed "
            if a[4] == INNER and b[4] == INNER:
                reasons[(netname, round(span, 1))] = (
                    "both ends are on a plane layer - not a surface route")
                continue
            if span <= BRIDGE_MAX or a[4] == INNER or b[4] == INNER:
                pts = bridge_path(a, b)
                kind = "bridged"
                if pts and shortfall(board, netname, pts, width, clearance,
                                     obs) > 1e-6:
                    # even a hop this short can graze something: fall through
                    # and let the search find its way round instead
                    pts, kind = None, "routed "
            if pts is None and kind == "routed ":
                anchors = net_anchors(board, netname)
                starts = ends_at(anchors, a)
                goals = ends_at(anchors, b)
                if not starts or not goals:
                    continue
                # widen the grid margin until the path the search returns also
                # survives an exact measurement against the board
                why = "no path"
                for safe in MARGINS:
                    g = build_grid(board, netname, width, clearance, safe)
                    path = astar(g, netname, starts, goals)
                    if not path:
                        # the search is not symmetric - one end may have a
                        # dozen anchors to leave from and the other one cell to
                        # arrive on, so it is worth asking the other way round
                        back = astar(g, netname, goals, starts)
                        if back:
                            back.reverse()
                            path = back
                    if not path:
                        continue
                    cand = to_mm_path(simplify(path), a[0], a[1], b[0], b[1])
                    bad = shortfall(board, netname, cand, width, clearance,
                                    obs)
                    if bad <= 1e-6:
                        pts = straighten(board, netname, cand, width,
                                         clearance, obs)
                        break
                    why = "%.3f mm short at margin %.2f" % (bad, safe)
                    pts = None
                if pts is None:
                    reasons[(netname, round(span, 1))] = why
            if pts is None:
                continue
            bad = shortfall(board, netname, pts, width, clearance, obs)
            if bad > 1e-6:
                print("  refused %-12s %5.1f mm - %.3f mm short of clearance"
                      % (netname, span, bad))
                continue
            nt, nv = lay(board, netname, pts, width)
            if nt == 0 and nv == 0:
                continue
            total_t += nt
            total_v += nv
            done += 1
            progress += 1
            obs_cache.clear()
            print("  %s %-12s %5.1f mm, %d segments, %d vias"
                  % (kind, netname, span, nt, nv))
        if not progress:
            failed = [(a[3], math.hypot(b[0] - a[0], b[1] - a[1]))
                      for a, b in gaps]
            break

    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(PCB)
    print("maze router: %d connections, %d segments, %d vias"
          % (done, total_t, total_v))
    for n, d in sorted(set(failed)):
        print("  unrouted  %-12s %.1f mm apart  (%s)"
              % (n, d, reasons_out.get((n, round(d, 1)), "no path")))
    for a, b in zone_gaps:
        item = a if a[2] != "Zone" else b
        width, clearance = net_rules(board, item[3])
        nt, nv = fanout(board, item[3], item[0], item[1], item[4],
                        width, clearance)
        if nv:
            print("  fan-out   %-12s at (%.2f, %.2f), %d segments, %d vias"
                  % (item[3], item[0], item[1], nt, nv))
        else:
            print("  zone gap  %-12s at (%.2f, %.2f) - no room for a via"
                  % (item[3], item[0], item[1]))
    board.Save(PCB)
    return 0


if __name__ == "__main__":
    sys.exit(main())
