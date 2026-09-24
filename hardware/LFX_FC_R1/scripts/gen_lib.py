#!/usr/bin/env python3
"""
LFX_FC_R1 - custom library generator.

Only draws parts that are NOT in the KiCad 10 stock libraries.  Everything else
(TPS54360DDA, TLV75533PDBV, TPD4E05U06DQA, AO3400A, BAT54S, SM6T33A, JST-SH,
passives ...) is used straight from the bundled libraries.

Custom parts, each drawn from its datasheet:

  * ICM-42688-P       symbol only; land pattern is the stock
                      Package_LGA:LGA-14_3x2.5mm_P0.5mm_LayoutBorder3x4y, which
                      matches TDK DS-000347 v1.7 (2.5 x 3.0 body, 0.5 pitch,
                      4 + 3 pins per side, pin 1 at a 4-pin-side corner, CCW)
  * BMP390            symbol + footprint.  The stock ST_HLGA-10 2x2 land has
                      its 3-pad rows on the other axis and ST's numbering, so it
                      does NOT fit.  Drawn from Bosch BST-BMP390-DS002-07
                      figure 23 (pin-out) and figure 26 (outline = land pattern)
  * LM66100           symbol only (stock SOT-363_SC-70-6), TI SLVSEZ8A pin table
  * Luckfox_Pico_Mini symbol + socket footprint.  Pin names from
                      Luckfox-Pico-Mini.pdf "Pin Out"; geometry from the
                      official STEP (LuckfoxTECH/Luckfox-Pico-docs):
                      pins 1.0 mm drill, rows 17.78 mm apart, 2.54 mm pitch,
                      board 21.0 x 28.16 mm, pin 1 at 1.599 / 1.393 mm from the
                      USB-C corner
  * SolderPad_2.5x4mm bench-supply pads
  * TestPad_1.0mm     probe pad

Run:  python3 scripts/gen_lib.py
"""

import os
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYM_DIR = os.path.join(ROOT, "lib", "symbols")
FP_DIR = os.path.join(ROOT, "lib", "footprints", "LFX.pretty")

SYM_VERSION = 20251024
FP_VERSION = 20260206


def q(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def pin(num, name, etype, x, y, rot, length=5.08, hide=False):
    out = [f'\t\t\t(pin {etype} line',
           f'\t\t\t\t(at {x:g} {y:g} {rot})',
           f'\t\t\t\t(length {length:g})']
    if hide:
        out.append('\t\t\t\t(hide yes)')
    out += [f'\t\t\t\t(name {q(name)} (effects (font (size 1.27 1.27))))',
            f'\t\t\t\t(number {q(num)} (effects (font (size 1.27 1.27))))',
            '\t\t\t)']
    return "\n".join(out)


def box_symbol(name, left, right, footprint, description, datasheet="",
               keywords="", half_w=10.16, value=None, ref="U"):
    """Rectangle symbol.  left/right: [(num, pin_name, etype), ...] top down;
    a None entry leaves a gap."""
    P = 2.54
    rows = max(len(left), len(right))
    top = (rows // 2) * P + P
    bot = top - (rows + 1) * P
    body = [f'\t\t(rectangle (start {-half_w:g} {top:g}) (end {half_w:g} {bot:g})',
            '\t\t\t(stroke (width 0.254) (type default))',
            '\t\t\t(fill (type background))',
            '\t\t)']
    pins = []
    for side, lst in ((0, left), (1, right)):
        y = top - P
        for item in lst:
            if item is not None:
                num, nm, et = item
                if side == 0:
                    pins.append(pin(num, nm, et, -half_w - 5.08, y, 0))
                else:
                    pins.append(pin(num, nm, et, half_w + 5.08, y, 180))
            y -= P

    def prop(k, v, py, hide):
        return (f'\t\t(property {q(k)} {q(v)} (at 0 {py:g} 0)'
                ' (effects (font (size 1.27 1.27))'
                + (' (hide yes)' if hide else '') + '))')
    props = [prop("Reference", ref, top + 2.54, False),
             prop("Value", value or name, top + 5.08, False),
             prop("Footprint", footprint, top + 7.62, True),
             prop("Datasheet", datasheet, top + 10.16, True),
             prop("Description", description, top + 12.7, True)]
    if keywords:
        props.append(prop("ki_keywords", keywords, top + 15.24, True))
    return (f'\t(symbol {q(name)}\n'
            '\t\t(pin_names (offset 0.762))\n'
            '\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n'
            + "\n".join(props) + "\n"
            + f'\t(symbol {q(name + "_1_1")}\n'
            + "\n".join(body + pins) + "\n\t)\n\t)")


# --------------------------------------------------------------------------
# symbols
# --------------------------------------------------------------------------
def icm42688_symbol():
    # TDK DS-000347 v1.7 table 10
    left = [("12", "AP_CS", "input"),
            ("13", "AP_SCLK", "input"),
            ("14", "AP_SDI", "bidirectional"),
            ("1", "AP_SDO/AD0", "bidirectional"),
            None,
            ("4", "INT1", "output"),
            ("9", "INT2/FSYNC", "input")]      # FSYNC input, tied to GND
    right = [("8", "VDD", "power_in"),
             ("5", "VDDIO", "power_in"),
             None,
             ("6", "GND", "power_in"),
             ("7", "RESV_GND", "passive"),
             ("2", "RESV", "passive"),
             ("3", "RESV", "passive"),
             ("10", "RESV", "passive"),
             ("11", "RESV", "passive")]
    return box_symbol(
        "ICM-42688-P", left, right,
        "Package_LGA:LGA-14_3x2.5mm_P0.5mm_LayoutBorder3x4y",
        "TDK InvenSense 6-axis IMU, SPI 24 MHz / I2C / I3C, LGA-14 2.5x3x0.91",
        "https://invensense.tdk.com/products/motion-tracking/6-axis/icm-42688-p/",
        "imu gyroscope accelerometer")


def bmp390_symbol():
    # Bosch BST-BMP390-DS002-07 table 52
    left = [("6", "CSB", "input"),
            ("2", "SCK", "input"),
            ("4", "SDI", "bidirectional"),
            ("5", "SDO", "bidirectional"),
            None,
            ("7", "INT", "output")]
    right = [("10", "VDD", "power_in"),
             ("1", "VDDIO", "power_in"),
             None,
             ("3", "VSS", "power_in"),
             ("8", "VSS", "power_in"),
             ("9", "VSS", "power_in")]
    return box_symbol(
        "BMP390", left, right, "LFX:Bosch_BMP390_LGA-10_2x2mm_P0.5mm",
        "Bosch barometric pressure sensor, SPI 10 MHz / I2C, LGA-10 2x2x0.75",
        "https://www.bosch-sensortec.com/products/environmental-sensors/"
        "pressure-sensors/bmp390/", "pressure barometer altitude",
        half_w=7.62)


def lm66100_symbol():
    # TI SLVSEZ8A pin functions
    left = [("1", "VIN", "power_in"),
            ("3", "~{CE}", "input"),
            None,
            ("4", "N/C", "no_connect")]
    right = [("6", "VOUT", "power_out"),
             ("5", "~{ST}", "passive"),      # open-drain; tied to GND per SLVSEZ8A
             None,
             ("2", "GND", "power_in")]
    return box_symbol(
        "LM66100", left, right, "Package_TO_SOT_SMD:SOT-363_SC-70-6",
        "TI ideal diode, 1.5-5.5 V, 1.5 A, reverse current blocking, SC-70-6",
        "https://www.ti.com/lit/ds/symlink/lm66100.pdf", "ideal diode oring",
        half_w=7.62)


# name, electrical type, per Luckfox-Pico-Mini.pdf "Pin Out" (H2)
LUCKFOX_PINS = {
    1: ("VBUS", "power_in"), 2: ("GND", "power_in"),
    3: ("3V3_O", "power_out"),
    4: ("GPIO1_B2/UART2_TX", "bidirectional"),
    5: ("GPIO1_B3/UART2_RX", "bidirectional"),
    6: ("GPIO1_C0/SPI0_CS0", "bidirectional"),
    7: ("GPIO1_C1/SPI0_CLK", "bidirectional"),
    8: ("GPIO1_C2/SPI0_MOSI", "bidirectional"),
    9: ("GPIO1_C3/SPI0_MISO", "bidirectional"),
    10: ("GPIO1_C4/PWM8", "bidirectional"),
    11: ("GPIO1_C5/PWM9", "bidirectional"),
    12: ("GPIO1_D0/UART3_TX", "bidirectional"),
    13: ("GPIO1_D1/UART3_RX", "bidirectional"),
    14: ("GPIO1_D2/SPI0_CS1", "bidirectional"),
    15: ("GPIO1_D3", "bidirectional"),
    16: ("GPIO1_C6/PWM10", "bidirectional"),
    17: ("GPIO1_C7/PWM11", "bidirectional"),
    18: ("GPIO0_A4", "bidirectional"),
    19: ("GPIO4_C0/SARADC_IN0", "bidirectional"),
    20: ("GPIO4_C1/SARADC_IN1", "bidirectional"),
    21: ("GND", "power_in"),
    22: ("1V8_OUT", "power_out"),
}


def luckfox_symbol():
    left = [(str(n), LUCKFOX_PINS[n][0], LUCKFOX_PINS[n][1])
            for n in range(1, 12)]
    right = [(str(n), LUCKFOX_PINS[n][0], LUCKFOX_PINS[n][1])
             for n in range(22, 11, -1)]
    return box_symbol(
        "Luckfox_Pico_Mini", left, right, "LFX:Luckfox_Pico_Mini_Socket",
        "Luckfox Pico Mini B (Rockchip RV1103) module, 2x11 pins 2.54 mm, "
        "rows 17.78 mm apart", "https://wiki.luckfox.com/Luckfox-Pico-Plus-Mini",
        "luckfox rv1103 linux module", half_w=15.24, ref="MOD")


POWER_RAILS = ["VBAT", "VSYS", "+3V3S", "+1V8"]


def power_symbol(name):
    esc = name.replace('"', '')
    graph = [
        '\t\t(polyline (pts (xy 0 0) (xy 0 1.27))'
        ' (stroke (width 0) (type default)) (fill (type none)))',
        '\t\t(polyline (pts (xy -0.762 1.27) (xy 0 2.54) (xy 0.762 1.27))'
        ' (stroke (width 0) (type default)) (fill (type none)))',
    ]
    p = pin("1", esc, "power_in", 0, 0, 270, length=0, hide=True)
    return ('\t(symbol %s\n'
            '\t\t(power)\n'
            '\t\t(pin_numbers (hide yes))\n'
            '\t\t(pin_names (offset 0) (hide yes))\n'
            '\t\t(exclude_from_sim no)\n\t\t(in_bom no)\n\t\t(on_board yes)\n'
            '\t\t(property "Reference" "#PWR" (at 0 -1.27 0)'
            ' (effects (font (size 1.27 1.27)) (hide yes)))\n'
            '\t\t(property "Value" %s (at 0 3.556 0)'
            ' (effects (font (size 1.27 1.27))))\n'
            '\t\t(property "Footprint" "" (at 0 0 0)'
            ' (effects (font (size 1.27 1.27)) (hide yes)))\n'
            '\t\t(property "Datasheet" "" (at 0 0 0)'
            ' (effects (font (size 1.27 1.27)) (hide yes)))\n'
            '\t\t(property "Description" "Power rail %s" (at 0 0 0)'
            ' (effects (font (size 1.27 1.27)) (hide yes)))\n'
            '\t(symbol %s\n%s\n%s\n\t)\n\t)'
            % (q(esc), q(esc), esc, q(esc + "_0_1"), "\n".join(graph), p))


# --------------------------------------------------------------------------
# footprints
# --------------------------------------------------------------------------
def fp_header(name, descr, tags, attr, ref_y, val_y, ref="U**"):
    return [f'(footprint {q(name)}',
            f'\t(version {FP_VERSION})',
            '\t(generator "lfx_gen_lib")',
            '\t(generator_version "10.0")',
            '\t(layer "F.Cu")',
            f'\t(descr {q(descr)})',
            f'\t(tags {q(tags)})',
            f'\t(attr {attr})',
            f'\t(property "Reference" {q(ref)}',
            f'\t\t(at 0 {ref_y:g} 0)',
            '\t\t(layer "F.SilkS")',
            '\t\t(effects (font (size 0.8 0.8) (thickness 0.12)))',
            '\t)',
            f'\t(property "Value" {q(name)}',
            f'\t\t(at 0 {val_y:g} 0)',
            '\t\t(layer "F.Fab")',
            '\t\t(effects (font (size 0.8 0.8) (thickness 0.12)))',
            '\t)']


def line(x1, y1, x2, y2, layer, w):
    return (f'\t(fp_line (start {x1:g} {y1:g}) (end {x2:g} {y2:g}) '
            f'(stroke (width {w:g}) (type solid)) (layer {q(layer)}))')


def rect(x0, y0, x1, y1, layer, w):
    return (f'\t(fp_rect (start {x0:g} {y0:g}) (end {x1:g} {y1:g}) '
            f'(stroke (width {w:g}) (type solid)) (fill no) (layer {q(layer)}))')


# BMP390, KiCad top view (y down).  Bottom view (fig. 26) mirrored in x:
# pin 1 VDDIO top row right, then counter-clockwise.  Centres 0.7625 mm
# = 1.0 half body - 0.1 edge gap - 0.1375 half pad; rows 0.5 mm pitch.
BMP_PADS = [
    (1, 0.25, -0.7625, 0.25, 0.275), (2, -0.25, -0.7625, 0.25, 0.275),
    (3, -0.7625, -0.5, 0.275, 0.25), (4, -0.7625, 0.0, 0.275, 0.25),
    (5, -0.7625, 0.5, 0.275, 0.25),
    (6, -0.25, 0.7625, 0.25, 0.275), (7, 0.25, 0.7625, 0.25, 0.275),
    (8, 0.7625, 0.5, 0.275, 0.25), (9, 0.7625, 0.0, 0.275, 0.25),
    (10, 0.7625, -0.5, 0.275, 0.25),
]


def bmp390_footprint():
    L = fp_header("Bosch_BMP390_LGA-10_2x2mm_P0.5mm",
                  "Bosch BMP390 10-pin metal-lid LGA 2.0x2.0x0.75 mm. Land = "
                  "package bottom view, BST-BMP390-DS002-07 fig. 26 / 7.2. "
                  "Keep the vent hole on the lid uncovered.",
                  "bosch bmp390 lga barometer", "smd", -1.8, 1.8)
    h = 1.0
    L.append(rect(-h, -h, h, h, "F.Fab", 0.1))
    L.append(line(0.5, -h, h, -0.5, "F.Fab", 0.1))      # pin-1 corner (top right)
    L.append(rect(-1.25, -1.25, 1.25, 1.25, "F.CrtYd", 0.05))
    # silk: corner ticks outside the body, pin-1 dot at the top-right
    for sx, sy in ((-1, -1), (1, 1), (-1, 1)):
        L.append(line(sx * 1.1, sy * 1.1, sx * 1.1, sy * 0.7, "F.SilkS", 0.12))
        L.append(line(sx * 1.1, sy * 1.1, sx * 0.7, sy * 1.1, "F.SilkS", 0.12))
    L.append('\t(fp_circle (center 1.25 -1.25) (end 1.35 -1.25) '
             '(stroke (width 0.12) (type solid)) (fill solid) (layer "F.SilkS"))')
    for n, x, y, w, hh in BMP_PADS:
        L += [f'\t(pad "{n}" smd roundrect',
              f'\t\t(at {x:g} {y:g})',
              f'\t\t(size {w:g} {hh:g})',
              '\t\t(layers "F.Cu" "F.Paste" "F.Mask")',
              '\t\t(roundrect_rratio 0.2)',
              '\t)']
    L += ['\t(embedded_fonts no)', ')']
    return "\n".join(L)


# Luckfox Pico Mini, origin = centre of the 2x11 pin field.
#   STEP: rows at x = 1.599 / 19.379, pins y = -1.393 ... -26.793,
#   board x 0 ... 20.998, y 0 (USB-C edge) ... -28.160
LF_ROW = 17.78 / 2.0                   # 8.89
LF_PITCH = 2.54
LF_PIN1_Y = -5 * LF_PITCH              # -12.7
LF_X0, LF_X1 = -10.489, 10.509         # module edges relative to the origin
LF_Y0, LF_Y1 = -14.093, 14.067         # USB-C edge ... camera edge


def luckfox_pad(n):
    if n <= 11:
        return -LF_ROW, LF_PIN1_Y + (n - 1) * LF_PITCH
    return LF_ROW, LF_PIN1_Y + (22 - n) * LF_PITCH


def luckfox_footprint():
    L = fp_header("Luckfox_Pico_Mini_Socket",
                  "Luckfox Pico Mini A/B on 2x 1x11 female headers, 2.54 mm "
                  "pitch, rows 17.78 mm apart. Pad n = module pin n. Module "
                  "outline 21.0 x 28.16 mm on F.Fab; USB-C at the -Y edge. "
                  "Courtyard covers the headers only: parts under the module "
                  "are allowed up to the socket height minus 1 mm.",
                  "luckfox rv1103 module socket header", "through_hole",
                  LF_Y0 - 1.2, LF_Y1 + 1.2, ref="MOD**")
    # module outline + USB-C and camera markers
    L.append(rect(LF_X0, LF_Y0, LF_X1, LF_Y1, "F.Fab", 0.1))
    L.append(rect(-4.5, LF_Y0 - 1.0, 4.5, LF_Y0 + 6.5, "F.Fab", 0.1))  # USB-C
    L.append('\t(fp_text user "USB-C" (at 0 %g 0) (layer "F.Fab") '
             '(effects (font (size 0.8 0.8) (thickness 0.12))))' % (LF_Y0 + 2.5))
    L.append('\t(fp_text user "CAM FPC" (at 0 %g 0) (layer "F.Fab") '
             '(effects (font (size 0.8 0.8) (thickness 0.12))))' % (LF_Y1 - 2.0))
    # silk: header strips and the module corners
    # The USB-C end of the module is flush with the board edge, so nothing is
    # drawn along it: the strips are open-topped and only the far corners get
    # ticks.
    for sx in (-1, 1):
        x0, x1 = sx * LF_ROW - 1.4, sx * LF_ROW + 1.4
        yt, yb = LF_PIN1_Y - 1.0, -LF_PIN1_Y + 1.4
        L.append(line(x0, yt, x0, yb, "F.SilkS", 0.12))
        L.append(line(x1, yt, x1, yb, "F.SilkS", 0.12))
        L.append(line(x0, yb, x1, yb, "F.SilkS", 0.12))
        L.append(rect(x0 - 0.1, LF_PIN1_Y - 1.5, x1 + 0.1, -LF_PIN1_Y + 1.5,
                      "F.CrtYd", 0.05))
    for x, y, dx, dy in ((LF_X0, LF_Y1, 1, -1), (LF_X1, LF_Y1, -1, -1)):
        L.append(line(x, y, x + dx * 1.5, y, "F.SilkS", 0.12))
        L.append(line(x, y, x, y + dy * 1.5, "F.SilkS", 0.12))
    # pin-1 arrow outside the left strip
    L.append(line(-LF_ROW - 2.2, LF_PIN1_Y, -LF_ROW - 1.7, LF_PIN1_Y,
                  "F.SilkS", 0.12))
    for n in range(1, 23):
        x, y = luckfox_pad(n)
        shape = "rect" if n == 1 else "circle"
        L += [f'\t(pad "{n}" thru_hole {shape}',
              f'\t\t(at {x:g} {y:g})',
              '\t\t(size 1.7 1.7)',
              '\t\t(drill 1.0)',
              '\t\t(layers "*.Cu" "*.Mask")',
              '\t\t(remove_unused_layers no)',
              '\t)']
    L += ['\t(embedded_fonts no)', ')']
    return "\n".join(L)


def solderpad_footprint():
    return textwrap.dedent(f'''\
        (footprint "SolderPad_2.5x4mm"
        \t(version {FP_VERSION})
        \t(generator "lfx_gen_lib")
        \t(generator_version "10.0")
        \t(layer "F.Cu")
        \t(descr "2.5 x 4 mm SMD solder pad for a battery / bench-supply lead")
        \t(tags "solder pad wire battery")
        \t(attr smd exclude_from_bom)
        \t(property "Reference" "J**"
        \t\t(at 0 -2.8 0)
        \t\t(layer "F.SilkS")
        \t\t(effects (font (size 0.8 0.8) (thickness 0.12)))
        \t)
        \t(property "Value" "SolderPad"
        \t\t(at 0 2.8 0)
        \t\t(layer "F.Fab")
        \t\t(effects (font (size 0.8 0.8) (thickness 0.12)))
        \t)
        \t(fp_rect (start -1.5 -2.25) (end 1.5 2.25)
        \t\t(stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd"))
        \t(pad "1" smd roundrect
        \t\t(at 0 0)
        \t\t(size 2.5 4)
        \t\t(layers "F.Cu" "F.Mask")
        \t\t(roundrect_rratio 0.15)
        \t)
        \t(embedded_fonts no)
        )
        ''')


def motorpad_footprint():
    return textwrap.dedent(f'''\
        (footprint "SolderPad_1.5x2.5mm"
        \t(version {FP_VERSION})
        \t(generator "lfx_gen_lib")
        \t(generator_version "10.0")
        \t(layer "F.Cu")
        \t(descr "1.5 x 2.5 mm SMD solder pad for an ESC signal / ground wire")
        \t(tags "solder pad wire esc")
        \t(attr smd exclude_from_bom)
        \t(property "Reference" "J**"
        \t\t(at 0 -2.0 0)
        \t\t(layer "F.Fab")
        \t\t(effects (font (size 0.8 0.8) (thickness 0.12)))
        \t)
        \t(property "Value" "SolderPad"
        \t\t(at 0 2.0 0)
        \t\t(layer "F.Fab")
        \t\t(effects (font (size 0.8 0.8) (thickness 0.12)))
        \t)
        \t(fp_rect (start -1.0 -1.5) (end 1.0 1.5)
        \t\t(stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd"))
        \t(pad "1" smd roundrect
        \t\t(at 0 0)
        \t\t(size 1.5 2.5)
        \t\t(layers "F.Cu" "F.Mask")
        \t\t(roundrect_rratio 0.2)
        \t)
        \t(embedded_fonts no)
        )
        ''')


def testpad_footprint():
    return textwrap.dedent(f'''\
        (footprint "TestPad_1.0mm"
        \t(version {FP_VERSION})
        \t(generator "lfx_gen_lib")
        \t(generator_version "10.0")
        \t(layer "F.Cu")
        \t(descr "1.0 mm round SMD test / probe pad")
        \t(tags "test point pad smd")
        \t(attr smd exclude_from_bom)
        \t(property "Reference" "TP**"
        \t\t(at 0 -1.4 0)
        \t\t(layer "F.SilkS")
        \t\t(effects (font (size 0.7 0.7) (thickness 0.12)))
        \t)
        \t(property "Value" "TestPoint"
        \t\t(at 0 1.4 0)
        \t\t(layer "F.Fab")
        \t\t(effects (font (size 0.7 0.7) (thickness 0.12)))
        \t)
        \t(fp_circle (center 0 0) (end 0.75 0)
        \t\t(stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd"))
        \t(pad "1" smd circle
        \t\t(at 0 0)
        \t\t(size 1 1)
        \t\t(layers "F.Cu" "F.Mask")
        \t)
        \t(embedded_fonts no)
        )
        ''')


def main():
    os.makedirs(SYM_DIR, exist_ok=True)
    os.makedirs(FP_DIR, exist_ok=True)

    parts = [icm42688_symbol(), bmp390_symbol(), lm66100_symbol(),
             luckfox_symbol()]
    parts += [power_symbol(n) for n in POWER_RAILS]
    lib = ['(kicad_symbol_lib',
           f'\t(version {SYM_VERSION})',
           '\t(generator "lfx_gen_lib")',
           '\t(generator_version "10.0")',
           *parts,
           ')']
    path = os.path.join(SYM_DIR, "LFX.kicad_sym")
    with open(path, "w") as fh:
        fh.write("\n".join(lib) + "\n")
    print("wrote", path)

    for name, text in (("Bosch_BMP390_LGA-10_2x2mm_P0.5mm", bmp390_footprint()),
                       ("Luckfox_Pico_Mini_Socket", luckfox_footprint()),
                       ("SolderPad_2.5x4mm", solderpad_footprint()),
                       ("SolderPad_1.5x2.5mm", motorpad_footprint()),
                       ("TestPad_1.0mm", testpad_footprint())):
        p = os.path.join(FP_DIR, name + ".kicad_mod")
        with open(p, "w") as fh:
            fh.write(text if text.endswith("\n") else text + "\n")
        print("wrote", p)


if __name__ == "__main__":
    main()
