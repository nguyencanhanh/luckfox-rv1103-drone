#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build the whole LFX_FC_R2 KiCad project from scripts/design.py:

    LFX_FC_R2.kicad_pro         project
    LFX_FC_R2.kicad_sch         root sheet (4 hierarchical sheets)
    sch/02_power.kicad_sch ...  the four leaf sheets
    sym-lib-table / fp-lib-table

Layout style: every component is placed on a coarse grid and each of its pins
gets a short stub terminated by a net label (or a power symbol for the supply
rails).  Nets that cross sheets use global labels, everything else uses local
labels, which is what makes the result ERC-clean without any hand routing.
"""

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import design                                          # noqa: E402
import stackup                                         # noqa: E402
import kisym                                           # noqa: E402

PROJECT = "LFX_FC_R2"
SCH_VERSION = 20250114
PAPER = "A3"                      # 420 x 297 mm
PAGE_W, PAGE_H = 420.0, 297.0
MARGIN_L, MARGIN_T = 15.0, 22.0
MARGIN_R, MARGIN_B = 15.0, 22.0

GRID = 1.27
STUB = 3.81                       # wire length from the pin to its label
CHAR_W = 0.95                     # approximate width of one label character
BLOCK_GAP = 7.62
TITLE_H = 7.62


def snap(v, g=GRID):
    return round(v / g) * g


def uid(*parts):
    h = hashlib.md5(("LFX_FC_R2|" + "|".join(str(p) for p in parts))
                    .encode()).hexdigest()
    return "%s-%s-%s-%s-%s" % (h[0:8], h[8:12], h[12:16], h[16:20], h[20:32])


def esc(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


# ---------------------------------------------------------------------------
# net classification
# ---------------------------------------------------------------------------
def classify_nets():
    sheets_of = {}
    for c in design.COMPONENTS:
        for net in c["pins"].values():
            if net:
                sheets_of.setdefault(net, set()).add(c["sheet"])
    kind = {}
    for net, sh in sheets_of.items():
        if net in design.POWER_NETS:
            kind[net] = "power"
        else:
            # every signal net is a global label, sheet-local ones included:
            # KiCad scopes a local label to its sheet ("/Power.../SW5"), and
            # the board, the net classes and the routing scripts all name
            # nets bare - one name per net everywhere keeps parity exact
            kind[net] = "global"
    return kind


NET_KIND = classify_nets()


# ---------------------------------------------------------------------------
# geometry of one placed component, including its labels
# ---------------------------------------------------------------------------
def outward(angle):
    """schematic-space unit vector pointing away from the symbol body."""
    a = int(round(angle)) % 360
    return {0: (-1.0, 0.0), 180: (1.0, 0.0),
            90: (0.0, 1.0), 270: (0.0, -1.0)}[a]


def label_len(net):
    return len(net) * CHAR_W + 3.0


class Placed(object):
    def __init__(self, comp):
        self.c = comp
        self.lib_id = comp["lib_id"]
        self.unit = comp["unit"]
        geo = kisym.pin_geometry(self.lib_id)
        self.pins = geo.get(self.unit, [])
        self.bx0, self.by0, self.bx1, self.by1 = kisym.body_bbox(self.lib_id,
                                                                 self.unit)
        # extents needed for the labels, per direction
        ext = {(-1.0, 0.0): 0.0, (1.0, 0.0): 0.0,
               (0.0, 1.0): 0.0, (0.0, -1.0): 0.0}
        for num, _nm, _et, px, py, ang, _ln in self.pins:
            net = comp["pins"].get(num)
            if not net:
                continue
            d = outward(ang)
            need = STUB + (5.08 if NET_KIND.get(net) == "power"
                           else label_len(net))
            ext[d] = max(ext[d], need)
        self.ext = ext
        # local bbox in symbol coordinates -> schematic offsets
        self.w = (self.bx1 - self.bx0) + ext[(-1.0, 0.0)] + ext[(1.0, 0.0)]
        self.h = (self.by1 - self.by0) + ext[(0.0, 1.0)] + ext[(0.0, -1.0)]
        text_w = max(len(str(comp["value"])), len(comp["ref"])) * 0.95 + 2.54
        self.w = max(self.w, text_w) + 7.62
        self.h += 6.35 + 5.08          # reference + value text
        self.x = self.y = 0.0

    def origin_offset(self):
        """Where the symbol origin sits inside the cell (dx, dy from top-left)."""
        dx = self.ext[(-1.0, 0.0)] + (-self.bx0) + 2.54
        dy = self.ext[(0.0, -1.0)] + self.by1 + 6.35
        return dx, dy


# ---------------------------------------------------------------------------
# sheet layout
# ---------------------------------------------------------------------------
NCOLS = 3


def _wrap(ps, max_w):
    rows, cur, cur_w = [], [], 0.0
    for p in ps:
        if cur and cur_w + p.w > max_w:
            rows.append(cur)
            cur, cur_w = [], 0.0
        cur.append(p)
        cur_w += p.w
    if cur:
        rows.append(cur)
    return rows


def layout_sheet(comps):
    """Magazine layout: components -> blocks -> rows -> NCOLS page columns."""
    blocks = []
    for c in comps:
        if not blocks or blocks[-1][0] != c["block"]:
            blocks.append((c["block"], []))
        blocks[-1][1].append(c)

    usable_w = PAGE_W - MARGIN_L - MARGIN_R
    usable_h = PAGE_H - MARGIN_T - MARGIN_B
    col_w = (usable_w - (NCOLS - 1) * BLOCK_GAP) / NCOLS

    # 1. shape every block into rows no wider than one page column
    shaped = []
    for title, items in blocks:
        ps = [Placed(c) for c in items]
        wide = max(p.w for p in ps)
        span = 1
        while wide > col_w * span + (span - 1) * BLOCK_GAP and span < NCOLS:
            span += 1
        max_w = col_w * span + (span - 1) * BLOCK_GAP
        rows = _wrap(ps, max_w)
        h = TITLE_H + sum(max(q.h for q in r) for r in rows) + BLOCK_GAP
        w = max(sum(q.w for q in r) for r in rows)
        shaped.append(dict(title=title, rows=rows, w=w, h=h, span=span,
                           max_w=max_w))

    # 2. balance: aim for equal column heights
    target = sum(b["h"] for b in shaped) / float(NCOLS)
    cols = [[] for _ in range(NCOLS)]
    col_h = [0.0] * NCOLS
    ci = 0
    for b in shaped:
        if b["span"] > 1:
            ci = 0
        if ci < NCOLS - 1 and col_h[ci] > 0 and \
                (col_h[ci] + b["h"] * 0.5 > target
                 or col_h[ci] + b["h"] > usable_h):
            ci += 1
        cols[ci].append(b)
        for k in range(ci, min(NCOLS, ci + b["span"])):
            col_h[k] = col_h[ci] + b["h"]

    # 3. emit
    placements, titles = [], []
    for ci, col in enumerate(cols):
        x = MARGIN_L + ci * (col_w + BLOCK_GAP)
        y = MARGIN_T
        for b in col:
            titles.append((b["title"], snap(x + 1.27), snap(y + 4.6),
                           snap(b["w"]), snap(b["h"] - BLOCK_GAP)))
            yy = y + TITLE_H
            for r in b["rows"]:
                xx = x
                rh = max(q.h for q in r)
                for p in r:
                    dx, dy = p.origin_offset()
                    p.x = snap(xx + dx)
                    p.y = snap(yy + dy)
                    placements.append(p)
                    xx += p.w
                yy += rh
            y += b["h"]
    return placements, titles


# ---------------------------------------------------------------------------
# emitters
# ---------------------------------------------------------------------------
def emit_wire(x1, y1, x2, y2, key):
    if abs(x1 - x2) < 1e-6 and abs(y1 - y2) < 1e-6:
        return []
    return ['\t(wire',
            f'\t\t(pts (xy {x1:g} {y1:g}) (xy {x2:g} {y2:g}))',
            '\t\t(stroke (width 0) (type default))',
            f'\t\t(uuid {esc(uid("w", key))})',
            '\t)']


def emit_label(net, x, y, direction, kind, key):
    dx, dy = direction
    if dx < 0:
        ang = 180
    elif dx > 0:
        ang = 0
    elif dy > 0:
        ang = 270
    else:
        ang = 90
    node = "global_label" if kind == "global" else "label"
    out = [f'\t({node} {esc(net)}']
    if kind == "global":
        out.append('\t\t(shape bidirectional)')
    out += [f'\t\t(at {x:g} {y:g} {ang})',
            '\t\t(effects (font (size 1.27 1.27)) '
            + ('(justify left))' if ang in (0, 90) else '(justify right))'),
            f'\t\t(uuid {esc(uid("lbl", key))})']
    if kind == "global":
        out += ['\t\t(property "Intersheetrefs" "${INTERSHEET_REFS}"',
                f'\t\t\t(at {x:g} {y:g} 0)',
                '\t\t\t(effects (font (size 1.27 1.27)) (hide yes))',
                '\t\t)']
    out.append('\t)')
    return out


def not_in_bom(c):
    """Bare copper - solder pads, test pads, mounting holes - is nothing to
    buy; their footprints say so and the symbol has to agree."""
    return any(k in c["fp"] for k in ("SolderPad", "TestPad", "TestPoint",
                                      "MountingHole"))


def emit_power(net, x, y, sheet_uuid, key, index):
    lib_id = design.POWER_NETS[net]
    ang = 0
    ref = "#PWR%04d" % index
    return ['\t(symbol',
            f'\t\t(lib_id {esc(lib_id)})',
            f'\t\t(at {x:g} {y:g} {ang})',
            '\t\t(unit 1)',
            '\t\t(exclude_from_sim no) (in_bom no) (on_board yes) (dnp no)',
            f'\t\t(uuid {esc(uid("pwr", key))})',
            f'\t\t(property "Reference" {esc(ref)}',
            f'\t\t\t(at {x:g} {y - 3.81:g} 0)',
            '\t\t\t(effects (font (size 1.27 1.27)) (hide yes))',
            '\t\t)',
            f'\t\t(property "Value" {esc(net)}',
            f'\t\t\t(at {x:g} {y + (4.5 if net in design.GROUND_NETS else -4.5):g} 0)',
            '\t\t\t(effects (font (size 1.27 1.27)))',
            '\t\t)',
            '\t\t(property "Footprint" "" (at 0 0 0) '
            '(effects (font (size 1.27 1.27)) (hide yes)))',
            '\t\t(property "Datasheet" "" (at 0 0 0) '
            '(effects (font (size 1.27 1.27)) (hide yes)))',
            '\t\t(instances',
            f'\t\t\t(project {esc(PROJECT)}',
            f'\t\t\t\t(path "/{ROOT_UUID}/{sheet_uuid}"',
            f'\t\t\t\t\t(reference {esc(ref)}) (unit 1)',
            '\t\t\t\t)',
            '\t\t\t)',
            '\t\t)',
            '\t)']


def emit_symbol(p, sheet_uuid):
    c = p.c
    ref, val = c["ref"], c["value"]
    x, y = p.x, p.y
    ry = y + p.by1 + 3.81
    vy = y - p.by0 + 2.54
    out = ['\t(symbol',
           f'\t\t(lib_id {esc(c["lib_id"])})',
           f'\t\t(at {x:g} {y:g} 0)',
           f'\t\t(unit {c["unit"]})',
           '\t\t(exclude_from_sim no) (in_bom %s) (on_board yes)'
           % ("no" if not_in_bom(c) else "yes"),
           f'\t\t(dnp {"yes" if c["dnf"] else "no"})',
           f'\t\t(uuid {esc(uid("sym", ref, c["unit"]))})',
           f'\t\t(property "Reference" {esc(ref)}',
           f'\t\t\t(at {x:g} {ry - 2 * (ry - y):g} 0)'
           if False else f'\t\t\t(at {x:g} {y - (p.by1 + 3.81):g} 0)',
           '\t\t\t(effects (font (size 1.27 1.27)))',
           '\t\t)',
           f'\t\t(property "Value" {esc(val)}',
           f'\t\t\t(at {x:g} {y - p.by0 + 2.54:g} 0)',
           '\t\t\t(effects (font (size 1.27 1.27)))',
           '\t\t)',
           f'\t\t(property "Footprint" {esc(c["fp"])}',
           f'\t\t\t(at {x:g} {y:g} 0)',
           '\t\t\t(effects (font (size 1.27 1.27)) (hide yes))',
           '\t\t)']
    ds = c["fields"].get("Datasheet", "")
    out += [f'\t\t(property "Datasheet" {esc(ds)}',
            f'\t\t\t(at {x:g} {y:g} 0)',
            '\t\t\t(effects (font (size 1.27 1.27)) (hide yes))',
            '\t\t)']
    for k, v in c["fields"].items():
        if k == "Datasheet":
            continue
        out += [f'\t\t(property {esc(k)} {esc(v)}',
                f'\t\t\t(at {x:g} {y:g} 0)',
                '\t\t\t(effects (font (size 1.27 1.27)) (hide yes))',
                '\t\t)']
    for num, _nm, _et, px, py, _a, _l in p.pins:
        out += [f'\t\t(pin {esc(num)} (uuid {esc(uid("pin", ref, num))}))']
    out += ['\t\t(instances',
            f'\t\t\t(project {esc(PROJECT)}',
            f'\t\t\t\t(path "/{ROOT_UUID}/{sheet_uuid}"',
            f'\t\t\t\t\t(reference {esc(ref)}) (unit {c["unit"]})',
            '\t\t\t\t)',
            '\t\t\t)',
            '\t\t)',
            '\t)']
    return out


def emit_text(s, x, y, size=2.0, bold=True):
    return [f'\t(text {esc(s)}',
            f'\t\t(at {x:g} {y:g} 0)',
            f'\t\t(effects (font (size {size:g} {size:g})'
            + (' (bold yes)' if bold else '') + ') (justify left bottom))',
            f'\t\t(uuid {esc(uid("txt", s, x, y))})',
            '\t)']


def emit_nc(x, y, key):
    return ['\t(no_connect',
            f'\t\t(at {x:g} {y:g})',
            f'\t\t(uuid {esc(uid("nc", key))})',
            '\t)']


def emit_box(x, y, w, h, key):
    return ['\t(rectangle',
            f'\t\t(start {x:g} {y:g}) (end {x + w:g} {y + h:g})',
            '\t\t(stroke (width 0.1) (type dash))',
            '\t\t(fill (type none))',
            f'\t\t(uuid {esc(uid("box", key))})',
            '\t)']


# ---------------------------------------------------------------------------
PWR_COUNTER = [1]
ROOT_UUID = uid("root")
SHEET_UUID = {name: uid("sheet", name) for name, _t in design.SHEETS}


def lib_symbols_block(lib_ids):
    out = ['\t(lib_symbols']
    for lid in sorted(set(lib_ids)):
        node = kisym.get_symbol(lid)
        out.append(kisym.dump([kisym.Atom("symbol")] + node, indent=2))
    out.append('\t)')
    return out


def title_block(title, rev="R1", date="2026-09-24", sheetno=None):
    return ['\t(title_block',
            f'\t\t(title {esc("LFX FC R2 - Luckfox RV1103 flight controller + LTE / GNSS")})',
            f'\t\t(date {esc(date)})',
            f'\t\t(rev {esc(rev)})',
            f'\t\t(company {esc("")})',
            f'\t\t(comment 1 {esc(title)})',
            f'\t\t(comment 2 {esc("Generated from scripts/design.py")})',
            '\t)']


def build_sheet(name, title):
    comps = [c for c in design.COMPONENTS if c["sheet"] == name]
    placements, titles = layout_sheet(comps)
    su = SHEET_UUID[name]

    body = []
    pwr_index = [PWR_COUNTER[0]]
    for bt, bx, by, bw, bh in titles:
        body += emit_text(bt, bx, by, size=2.2)
    for p in placements:
        body += emit_symbol(p, su)
        done = set()                         # stacked pins share one point
        for num, _nm, _et, px, py, ang, _ln in p.pins:
            net = p.c["pins"].get(num)
            ax, ay = p.x + px, p.y - py          # pin connection point
            if (ax, ay) in done:
                continue
            done.add((ax, ay))
            if not net:
                if num in p.c["pins"]:
                    body += emit_nc(ax, ay, (name, p.c["ref"], num))
                continue
            dx, dy = outward(ang)
            ex, ey = snap(ax + dx * STUB), snap(ay + dy * STUB)
            key = (name, p.c["ref"], num)
            body += emit_wire(ax, ay, ex, ey, key)
            if NET_KIND[net] == "power":
                body += emit_power(net, ex, ey, su, key, pwr_index[0])
                pwr_index[0] += 1
            else:
                body += emit_label(net, ex, ey, (dx, dy), NET_KIND[net], key)

    PWR_COUNTER[0] = pwr_index[0]
    lib_ids = [p.c["lib_id"] for p in placements]
    lib_ids += [design.POWER_NETS[n] for n, k in NET_KIND.items()
                if k == "power"
                and any(n in c["pins"].values() for c in comps)]

    out = ['(kicad_sch',
           f'\t(version {SCH_VERSION})',
           '\t(generator "lfx_gen_sch")',
           '\t(generator_version "10.0")',
           f'\t(uuid {esc(su)})',
           f'\t(paper {esc(PAPER)})']
    out += title_block(title)
    out += lib_symbols_block(lib_ids)
    out += body
    out += ['\t(sheet_instances',
            '\t\t(path "/" (page "1"))',
            '\t)',
            ')']
    return "\n".join(out) + "\n"


def build_root():
    out = ['(kicad_sch',
           f'\t(version {SCH_VERSION})',
           '\t(generator "lfx_gen_sch")',
           '\t(generator_version "10.0")',
           f'\t(uuid {esc(ROOT_UUID)})',
           f'\t(paper {esc("A3")})']
    out += title_block("Root - system block diagram")
    out += ['\t(lib_symbols)']

    out += emit_text("LFX FC R2  -  Luckfox Pico Mini B (RV1103) flight "
                     "controller + LTE / GNSS, one 50 x 50 mm board", 20, 24,
                     size=3.2)
    notes = [
        "Rails : VBAT 2S-6S (ESC JST-SH 8) -> TPS54360 buck -> +5V -> LM66100 ideal diode -> VSYS (Luckfox VBUS)",
        "        VSYS -> TLV75533 -> +3V3S (IMU + barometer only)    +1V8 from the module, ADC clamps only",
        "SPI0  : ICM-42688-P (CS0, pin 6) + BMP390 (CS1, pin 14), MCU-owned per docs/architecture.html",
        "ESC   : PWM8-11_M1 on module pins 10, 11, 16, 17 -> 47R -> S/G pads in the corners, four separate ESCs",
        "UART  : UART2 RC receiver (pins 4/5) on JST-SH, ESD by TPD4E05U06",
        "LTE   : Lierda NT26-KCN E (bottom) on UART3 (pins 12/13) via SN74LVC1T45, RESET pin 18, BOOT pin 20;",
        "        nano-SIM (top), U.FL LTE + GNSS (bottom front corners), +5V -> TLV62569 -> +3V8, buzzer on its AGPIO5",
    ]
    for i, n in enumerate(notes):
        out += emit_text(n, 20, 32 + i * 5.0, size=1.8, bold=False)

    x, y = 25.0, 70.0
    for i, (name, title) in enumerate(design.SHEETS):
        w, h = 160.0, 26.0
        sx = x + (i % 2) * (w + 14.0)
        sy = y + (i // 2) * (h + 12.0)
        out += ['\t(sheet',
                f'\t\t(at {sx:g} {sy:g})',
                f'\t\t(size {w:g} {h:g})',
                '\t\t(exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)',
                '\t\t(stroke (width 0.2) (type solid))',
                '\t\t(fill (color 0 0 0 0.0))',
                f'\t\t(uuid {esc(SHEET_UUID[name])})',
                f'\t\t(property "Sheetname" {esc(title)}',
                f'\t\t\t(at {sx:g} {sy - 1.5:g} 0)',
                '\t\t\t(effects (font (size 1.8 1.8)) (justify left bottom))',
                '\t\t)',
                f'\t\t(property "Sheetfile" {esc("sch/%s.kicad_sch" % name)}',
                f'\t\t\t(at {sx:g} {sy + h + 3.5:g} 0)',
                '\t\t\t(effects (font (size 1.4 1.4)) (justify left top))',
                '\t\t)',
                '\t\t(instances',
                f'\t\t\t(project {esc(PROJECT)}',
                f'\t\t\t\t(path "/{ROOT_UUID}" (page "{i + 2}"))',
                '\t\t\t)',
                '\t\t)',
                '\t)']

    out += ['\t(sheet_instances',
            '\t\t(path "/" (page "1"))',
            '\t)',
            ')']
    return "\n".join(out) + "\n"


PROJECT_JSON = """{
  "board": {
    "3dviewports": [],
    "design_settings": {
      "defaults": {},
      "diff_pair_dimensions": [],
      "drc_exclusions": [],
      "rules": {},
      "track_widths": [],
      "via_dimensions": []
    },
    "layer_presets": [],
    "viewports": []
  },
  "boards": [],
  "cvpcb": { "equivalence_files": [] },
  "libraries": { "pinned_footprint_libs": [], "pinned_symbol_libs": [] },
  "meta": { "filename": "LFX_FC_R2.kicad_pro", "version": 3 },
  "net_settings": {
    "classes": [
      { "name": "Default", "clearance": 0.2, "track_width": 0.25,
        "via_diameter": 0.6, "via_drill": 0.3, "microvia_diameter": 0.3,
        "microvia_drill": 0.1, "diff_pair_width": 0.2, "diff_pair_gap": 0.25,
        "diff_pair_via_gap": 0.25, "wire_width": 6, "bus_width": 12,
        "line_style": 0, "schematic_color": "rgba(0, 0, 0, 0.000)",
        "pcb_color": "rgba(0, 0, 0, 0.000)" },
      { "name": "Power", "clearance": 0.2, "track_width": 0.25,
        "via_diameter": 0.6, "via_drill": 0.3, "microvia_diameter": 0.3,
        "microvia_drill": 0.1, "diff_pair_width": 0.2, "diff_pair_gap": 0.25,
        "diff_pair_via_gap": 0.25, "wire_width": 6, "bus_width": 12,
        "line_style": 0, "schematic_color": "rgba(0, 0, 0, 0.000)",
        "pcb_color": "rgba(0, 0, 0, 0.000)" },
      { "name": "PowerHi", "clearance": 0.2, "track_width": 0.25,
        "via_diameter": 0.6, "via_drill": 0.3, "microvia_diameter": 0.3,
        "microvia_drill": 0.1, "diff_pair_width": 0.2, "diff_pair_gap": 0.25,
        "diff_pair_via_gap": 0.25, "wire_width": 6, "bus_width": 12,
        "line_style": 0, "schematic_color": "rgba(0, 0, 0, 0.000)",
        "pcb_color": "rgba(0, 0, 0, 0.000)" },
      { "name": "RF", "clearance": 0.2, "track_width": 0.25,
        "via_diameter": 0.6, "via_drill": 0.3, "microvia_diameter": 0.3,
        "microvia_drill": 0.1, "diff_pair_width": 0.2, "diff_pair_gap": 0.25,
        "diff_pair_via_gap": 0.25, "wire_width": 6, "bus_width": 12,
        "line_style": 0, "schematic_color": "rgba(0, 0, 0, 0.000)",
        "pcb_color": "rgba(0, 0, 0, 0.000)" },
      { "name": "Sense", "clearance": 0.2, "track_width": 0.25,
        "via_diameter": 0.6, "via_drill": 0.3, "microvia_diameter": 0.3,
        "microvia_drill": 0.1, "diff_pair_width": 0.2, "diff_pair_gap": 0.25,
        "diff_pair_via_gap": 0.25, "wire_width": 6, "bus_width": 12,
        "line_style": 0, "schematic_color": "rgba(0, 0, 0, 0.000)",
        "pcb_color": "rgba(0, 0, 0, 0.000)" }
    ],
    "meta": { "version": 4 },
    "net_colors": null,
    "netclass_assignments": null,
    "netclass_patterns": [
      { "netclass": "Power", "pattern": "GND" },
      { "netclass": "PowerHi", "pattern": "VBAT" },
      { "netclass": "PowerHi", "pattern": "VBAT_F" },
      { "netclass": "Power", "pattern": "VSYS" },
      { "netclass": "Power", "pattern": "+3V3S" },
      { "netclass": "PowerHi", "pattern": "+5V" },
      { "netclass": "PowerHi", "pattern": "SW5" },
      { "netclass": "Sense", "pattern": "FB5" },
      { "netclass": "Sense", "pattern": "COMP5" },
      { "netclass": "Sense", "pattern": "COMP5_C" },
      { "netclass": "Sense", "pattern": "RT5" },
      { "netclass": "Sense", "pattern": "EN5" },
      { "netclass": "PowerHi", "pattern": "+3V8" },
      { "netclass": "PowerHi", "pattern": "SW38" },
      { "netclass": "Sense", "pattern": "FB38" },
      { "netclass": "RF", "pattern": "LTE_ANT" },
      { "netclass": "RF", "pattern": "LTE_ANT_J" },
      { "netclass": "RF", "pattern": "GNSS_ANT" },
      { "netclass": "RF", "pattern": "GNSS_ANT_M" },
      { "netclass": "RF", "pattern": "GNSS_ANT_J" }
    ]
  },
  "pcbnew": {
    "last_paths": { "gencad": "", "idf": "", "netlist": "", "plot": "",
                    "pos_files": "", "specctra_dsn": "", "step": "",
                    "svg": "", "vrml": "" },
    "page_layout_descr_file": ""
  },
  "schematic": {
    "annotate_start_num": 0,
    "bom_fmt_presets": [],
    "bom_fmt_settings": {},
    "bom_presets": [],
    "bom_settings": {},
    "connection_grid_size": 50.0,
    "drawing": { "dashed_lines_dash_length_ratio": 12.0,
                 "dashed_lines_gap_length_ratio": 3.0,
                 "default_line_thickness": 6.0,
                 "default_text_size": 50.0, "field_names": [],
                 "intersheets_ref_own_page": false,
                 "intersheets_ref_prefix": "",
                 "intersheets_ref_short": false,
                 "intersheets_ref_show": true,
                 "intersheets_ref_suffix": "",
                 "junction_size_choice": 3,
                 "label_size_ratio": 0.375,
                 "pin_symbol_size": 25.0,
                 "text_offset_ratio": 0.15 },
    "legacy_lib_dir": "",
    "legacy_lib_list": [],
    "meta": { "version": 1 },
    "net_format_name": "",
    "page_layout_descr_file": "",
    "plot_directory": "fab/",
    "spice_current_sheet_as_root": false,
    "spice_external_command": "spice \\"%I\\"",
    "spice_model_current_sheet_as_root": true,
    "spice_save_all_currents": false,
    "spice_save_all_dissipations": false,
    "spice_save_all_voltages": false,
    "subpart_first_id": 65,
    "subpart_id_separator": 0
  },
  "sheets": [],
  "text_variables": {}
}
"""

SYM_LIB_TABLE = """(sym_lib_table
  (version 7)
  (lib (name "LFX")(type "KiCad")(uri "${KIPRJMOD}/../LFX_FC_R1/lib/symbols/LFX.kicad_sym")(options "")(descr "LFX custom symbols, shared with LFX_FC_R1"))
)
"""

FP_LIB_TABLE = """(fp_lib_table
  (version 7)
  (lib (name "LFX")(type "KiCad")(uri "${KIPRJMOD}/../LFX_FC_R1/lib/footprints/LFX.pretty")(options "")(descr "LFX custom footprints, shared with LFX_FC_R1"))
)
"""


def sync_netclass_widths(text):
    """Take the track widths straight from scripts/stackup.py so the project
    file can never drift from the IPC-2221 numbers it was derived from."""
    import json
    import re
    doc = json.loads(text)
    for cls in doc["net_settings"]["classes"]:
        spec = stackup.NETCLASS.get(cls["name"])
        if not spec:
            continue
        w, clr, vd, vdr, _note = spec
        cls["track_width"] = w
        cls["clearance"] = clr
        if vd:
            cls["via_diameter"] = vd
            cls["via_drill"] = vdr
    return json.dumps(doc, indent=2) + "\n"


def main():
    os.makedirs(os.path.join(ROOT, "sch"), exist_ok=True)

    # the project file also holds the BOARD's design rules (min drill 0.2,
    # track widths, ...), which only the PCB side writes: keep that part of
    # an existing file, regenerate the rest - rewriting it whole set the board
    # back to KiCad's defaults (min hole 0.3 mm) and 199 vias failed DRC
    pro_path = os.path.join(ROOT, PROJECT + ".kicad_pro")
    doc = json.loads(sync_netclass_widths(PROJECT_JSON))
    if os.path.exists(pro_path):
        try:
            old = json.load(open(pro_path))
            if "board" in old:
                doc["board"] = old["board"]
            for k in old:                    # sections KiCad added on its own
                doc.setdefault(k, old[k])
        except ValueError:
            pass
    with open(pro_path, "w") as fh:
        fh.write(json.dumps(doc, indent=2) + "\n")
    with open(os.path.join(ROOT, "sym-lib-table"), "w") as fh:
        fh.write(SYM_LIB_TABLE)
    with open(os.path.join(ROOT, "fp-lib-table"), "w") as fh:
        fh.write(FP_LIB_TABLE)

    with open(os.path.join(ROOT, PROJECT + ".kicad_sch"), "w") as fh:
        fh.write(build_root())
    print("wrote", PROJECT + ".kicad_sch")

    for name, title in design.SHEETS:
        p = os.path.join(ROOT, "sch", name + ".kicad_sch")
        with open(p, "w") as fh:
            fh.write(build_sheet(name, title))
        n = len([c for c in design.COMPONENTS if c["sheet"] == name])
        print("wrote sch/%s.kicad_sch  (%d components)" % (name, n))

    g = sum(1 for v in NET_KIND.values() if v == "global")
    print("nets: %d  (global %d, power %d, local %d)"
          % (len(NET_KIND), g,
             sum(1 for v in NET_KIND.values() if v == "power"),
             sum(1 for v in NET_KIND.values() if v == "local")))


if __name__ == "__main__":
    main()
