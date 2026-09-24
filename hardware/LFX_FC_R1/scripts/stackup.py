#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LFX_FC_R1 stack-up, impedance and current-carrying calculations.

Everything the layout uses for track widths comes from here, so the numbers in
the board, in the net classes and in the documentation can never drift apart.

Stack-up (JLCPCB JLC04161H-7628 equivalent, 1.6 mm, 4 layer):

    F.Cu    35 um  (1 oz)          signal: Luckfox socket, sensors, connectors
    ------  prepreg 7628 x1  0.2104 mm, Er 4.4
    In1.Cu  ~17 um (0.5 oz)        SOLID GROUND - the reference for everything
    ------  core            1.065 mm,  Er 4.6
    In2.Cu  ~17 um (0.5 oz)        power: +5V / VSYS / +3V3S islands over GND
    ------  prepreg 7628 x1  0.2104 mm, Er 4.4
    B.Cu    35 um  (1 oz)          buck converter, ESC connector, battery pads

The IMU sits on F.Cu over In1 GND; the buck sits on B.Cu under the other
half of the board, so the ground plane lies between the switch node and the
gyro.
"""

import math

# --- physical stack ---------------------------------------------------------
H_TOP_TO_GND = 0.2104          # mm, F.Cu to In1.Cu dielectric
ER_PREPREG = 4.4
T_OUTER = 0.035                # mm, 1 oz finished outer copper
T_INNER = 0.0152               # mm, 0.5 oz inner copper
BOARD_T = 1.6


def microstrip_z0(w, h=H_TOP_TO_GND, t=T_OUTER, er=ER_PREPREG):
    """Hammerstad/IPC-2141 microstrip impedance, mm in, ohm out."""
    return (87.0 / math.sqrt(er + 1.41)) * math.log(5.98 * h / (0.8 * w + t))


def microstrip_width(z0=50.0, h=H_TOP_TO_GND, t=T_OUTER, er=ER_PREPREG):
    lo, hi = 0.05, 5.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if microstrip_z0(mid, h, t, er) > z0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def ipc2221_width(current, dt=10.0, outer=True, thickness_oz=1.0):
    """IPC-2221 track width in mm for a given current and temperature rise."""
    k = 0.048 if outer else 0.024
    area_mils2 = (current / (k * dt ** 0.44)) ** (1 / 0.725)
    return area_mils2 / (1.378 * thickness_oz) * 0.0254


def ipc2221_current(width_mm, dt=10.0, outer=True, thickness_oz=1.0):
    k = 0.048 if outer else 0.024
    area_mils2 = width_mm / 0.0254 * 1.378 * thickness_oz
    return k * dt ** 0.44 * area_mils2 ** 0.725


# --- what the layout actually uses ------------------------------------------
# name -> (track width mm, clearance mm, via dia mm, via drill mm, note)
NETCLASS = {
    # 0.15 mm clearance is forced by the land patterns, not chosen: the
    # ICM-42688-P LGA-14 pads are 0.35 mm wide on a 0.5 mm pitch (0.15 mm gap)
    # and the BMP390 pads 0.25 mm on 0.5 mm.  JLCPCB 4-layer minimum is
    # 0.09 / 0.09 mm, so 0.15 keeps a 60 % margin.
    "Default": (0.20, 0.15, 0.50, 0.25,
                "logic, SPI, UART, PWM; 1.0 A @ 20 C rise is far above need"),
    "Power":   (0.40, 0.15, 0.60, 0.30,
                "VSYS / +3V3S / GND stubs.  VSYS peaks at the LM66100 "
                "1.5 A limit; 0.40 mm carries 1.67 A at a 20 C rise.  VBAT "
                "(1.8 A at a flat 2S pack: 5 V x 2 A / (6.6 V x 0.85)) gets "
                "the 0.80 mm override below, good for 2.76 A"),
    "PowerHi": (0.60, 0.20, 0.60, 0.30,
                "+5V buck output: 2.0 A (LM66100 1.5 A + GPS + buzzer) "
                "needs 0.51 mm at a 20 C rise; 0.60 mm carries 2.24 A"),
    "Sense":   (0.20, 0.25, 0.50, 0.25,
                "buck FB / COMP / RT: small, kept away from SW5 by a "
                "custom rule"),
}

# per-net width overrides where a single net needs more than its class
WIDTH_OVERRIDE = {
    "SW5": 1.2,            # buck switching node: wide and very short
    "VBAT": 0.8,
    "VBAT_F": 0.8,
    "+5V": 0.8,
    "GND": 0.5,
}


def report():
    print("stack-up")
    print("  F.Cu -> In1.Cu (GND)      %.4f mm prepreg, Er %.2f"
          % (H_TOP_TO_GND, ER_PREPREG))
    print("  board thickness           %.2f mm, 4 layers" % BOARD_T)
    print()
    print("SPI / PWM traces on F.Cu at the Default width")
    print("  0.20 mm microstrip        Z0 = %.1f ohm (reference only)"
          % microstrip_z0(0.20))
    print()
    print("IPC-2221 external track width")
    for i in (0.5, 1.0, 2.0, 3.0, 10.0):
        print("  %5.1f A  10 C rise -> %5.2f mm      30 C rise -> %5.2f mm"
              % (i, ipc2221_width(i, 10), ipc2221_width(i, 30)))
    print()
    print("net classes")
    for n, (w, c, vd, vdr, note) in NETCLASS.items():
        amp10 = ipc2221_current(w, 10)
        amp30 = ipc2221_current(w, 30)
        print("  %-8s w=%.2f clr=%.2f via=%.2f/%.2f  %4.1f A@10C %5.1f A@30C"
              "   %s" % (n, w, c, vd, vdr, amp10, amp30, note))


if __name__ == "__main__":
    report()
