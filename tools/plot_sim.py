#!/usr/bin/env python3
"""Draw two SVG charts from the simulator's own logs (standard library only).

    make -C simulator
    python3 tools/plot_sim.py          # -> docs/img/sim/rc_loss.svg, angle_step.svg

Each chart comes from running build/sim_cli --csv on one scenario, so the
picture is the scenario the test suite checks, not a hand-made example.
"""

import csv
import math
import os
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROOT, "simulator", "build", "sim_cli")
OUT = os.path.join(ROOT, "docs", "img", "sim")

INK, DIM, GRID, BG = "#1f2a30", "#66777f", "#e3e8ea", "#ffffff"
C1, C2, C3 = "#127c6a", "#d9542c", "#6b5bd6"
STATE = {0: ("DISARMED", "#eef1f2"), 1: ("ARMED", "#e2f4ea"),
         2: ("FAILSAFE HOLD", "#fff1cc"), 3: ("FAILSAFE LAND", "#ffe2c7")}


def run(scenario):
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        path = f.name
    subprocess.run([CLI, "--csv", path, scenario], check=True, stdout=subprocess.DEVNULL)
    with open(path) as f:
        rows = [{k: float(v) for k, v in r.items()} for r in csv.DictReader(f)]
    os.remove(path)
    return rows


def nice_ticks(lo, hi, n=5):
    span = hi - lo
    step = 10 ** math.floor(math.log10(span / n))
    for m in (1, 2, 5, 10):
        if span / (step * m) <= n:
            step *= m
            break
    t = math.ceil(lo / step) * step
    out = []
    while t <= hi + 1e-9:
        out.append(round(t, 6))
        t += step
    return out


def chart(rows, t0, t1, series, ylabel, title, note, fname, bands=True, ypad=0.1):
    W, H, L, R, T, B = 860, 380, 64, 180, 48, 46
    pw, ph = W - L - R, H - T - B
    rows = [r for r in rows if t0 <= r["t"] <= t1]
    vals = [s[1](r) for r in rows for s in series]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * ypad or 1.0
    lo, hi = lo - pad, hi + pad
    X = lambda t: L + (t - t0) / (t1 - t0) * pw
    Y = lambda v: T + (hi - v) / (hi - lo) * ph
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
         f'font-family="IBM Plex Sans, Helvetica, Arial, sans-serif" font-size="12">',
         f'<rect width="{W}" height="{H}" fill="{BG}"/>',
         f'<text x="{L}" y="24" font-size="15" font-weight="600" fill="{INK}">{title}</text>',
         f'<text x="{L}" y="40" fill="{DIM}">{note}</text>']
    if bands:                                   # flight-state background bands
        start, cur = rows[0]["t"], int(rows[0]["state"])
        for r in rows[1:] + [None]:
            s = int(r["state"]) if r else None
            if s != cur:
                end = r["t"] if r else rows[-1]["t"]
                name, col = STATE[cur]
                o.append(f'<rect x="{X(start):.1f}" y="{T}" width="{X(end) - X(start):.1f}" '
                         f'height="{ph}" fill="{col}"/>')
                if X(end) - X(start) > 70:
                    o.append(f'<text x="{X(start) + 6:.1f}" y="{T + 16}" fill="{DIM}" '
                             f'font-size="11">{name}</text>')
                if r:
                    start, cur = r["t"], s
    for v in nice_ticks(lo, hi):
        o.append(f'<line x1="{L}" x2="{L + pw}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="{GRID}"/>')
        o.append(f'<text x="{L - 8}" y="{Y(v) + 4:.1f}" text-anchor="end" fill="{DIM}">{v:g}</text>')
    for t in nice_ticks(t0, t1, 8):
        o.append(f'<text x="{X(t):.1f}" y="{T + ph + 18}" text-anchor="middle" fill="{DIM}">{t:g}</text>')
    o.append(f'<text x="{L + pw / 2}" y="{H - 8}" text-anchor="middle" fill="{DIM}">thời gian (s)</text>')
    o.append(f'<text transform="translate(16 {T + ph / 2}) rotate(-90)" text-anchor="middle" '
             f'fill="{DIM}">{ylabel}</text>')
    o.append(f'<rect x="{L}" y="{T}" width="{pw}" height="{ph}" fill="none" stroke="{GRID}"/>')
    for i, (name, f, col, dash) in enumerate(series):
        pts = " ".join(f"{X(r['t']):.1f},{Y(f(r)):.1f}" for r in rows)
        d = ' stroke-dasharray="6 4"' if dash else ""
        o.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2"{d}/>')
        ly = T + 14 + i * 20
        o.append(f'<line x1="{L + pw + 14}" x2="{L + pw + 38}" y1="{ly}" y2="{ly}" stroke="{col}" '
                 f'stroke-width="2"{d}/>')
        o.append(f'<text x="{L + pw + 44}" y="{ly + 4}" fill="{INK}">{name}</text>')
    o.append("</svg>")
    path = os.path.join(OUT, fname)
    with open(path, "w") as fh:
        fh.write("\n".join(o) + "\n")
    print("  " + path)


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = run("rc_loss")
    cut = next(r["t"] for r in rows if r["link_cut"] > 0.5)
    chart(rows, 0, rows[-1]["t"],
          [("độ cao thật", lambda r: -r["z"], C1, False),
           ("độ cao ước lượng", lambda r: r["est_h"], C2, True),
           ("ga (collective)", lambda r: r["collective"] * 4, C3, False)],
          "mét  (ga × 4)", "Mất sóng RC ở 4 m: giữ thăng bằng → tự hạ cánh → tự tắt motor",
          f"sim_cli rc_loss, sóng bị cắt lúc t = {cut:.1f} s; nền màu là trạng thái failsafe",
          "rc_loss.svg")
    rows = run("angle_step")
    d = 180 / math.pi
    step = next(r["t"] for r in rows if r["sp_roll"] > 0.01)
    chart(rows, step - 0.5, step + 2.2,
          [("góc đặt", lambda r: r["sp_roll"] * d, INK, True),
           ("góc thật", lambda r: r["roll"] * d, C1, False),
           ("góc ước lượng", lambda r: r["est_roll"] * d, C2, False)],
          "roll (độ)", "Bước nghiêng 15° ở chế độ ANGLE",
          "sim_cli angle_step: lệch thật / ước lượng ~2° là giới hạn khi chưa có GPS (xem README)",
          "angle_step.svg", bands=False)


if __name__ == "__main__":
    main()
