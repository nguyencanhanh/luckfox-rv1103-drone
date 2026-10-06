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
  * NT26-KCN          Lierda NT26-KCN E LTE Cat.1 bis + GNSS: symbol +
                      LCC/LGA-109 footprint.  Pin table: Lierda NT26-KCN E
                      hardware design manual Rev1.0 ("HDM") table 2-5 and
                      fig. 2-2; land pattern: HDM fig. 8-3
  * SIM_Card_Shield   the stock Connector:SIM_Card plus the holder's
                      shield pads (SH), so they can be grounded
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
               keywords="", half_w=10.16, value=None, ref="U", hidden=()):
    """Rectangle symbol.  left/right: [(num, pin_name, etype), ...] top down;
    a None entry leaves a gap.  An entry may also be a list of such tuples:
    they are stacked on one row, the first visible and the rest hidden
    passive pins (KLC S4.3), so one wire joins them all.  `hidden` lists
    (num, name) no-connect pins kept out of sight inside the body, one grid
    point each."""
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
                stack = item if isinstance(item, list) else [item]
                for k, (num, nm, et) in enumerate(stack):
                    x, rot = ((-half_w - 5.08, 0) if side == 0
                              else (half_w + 5.08, 180))
                    pins.append(pin(num, nm, et if k == 0 else "passive",
                                    x, y, rot, hide=k > 0))
            y -= P
    # unused / reserved pins: a column of hidden no-connect pins in the body
    for k, (num, nm) in enumerate(hidden):
        pins.append(pin(num, nm, "no_connect", -half_w + 2.54 * (1 + k % 6),
                        top - P * (1 + k // 6), 0, length=0, hide=True))

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


# Lierda NT26-KCN E, HDM table 2-5
NT26_GND = (1, 10, 27, 34, 36, 37, 40, 41, 45, 46, 47, 48, 70, 71, 72, 73,
            88, 89, 90, 91, 92, 93, 94, 95)
NT26_REV = (3, 4, 26, 30, 31, 32, 33, 44, 49, 54, 55, 56, 68, 69, 74, 75, 76,
            77, 78, 80, 81, 83, 84, 85, 86, 87, 98, 100, 102, 103, 104, 105,
            106, 108, 109)


def nt26_symbol():
    gnd = [(str(n), "GND", "power_in") for n in NT26_GND]
    left = [[("42", "VBAT", "power_in"), ("43", "VBAT", "power_in")],
            None,
            ("7", "PWRKEY", "input"),
            ("15", "RESET_N", "input"),
            ("82", "USB_BOOT", "input"),
            None,
            ("17", "MAIN_RXD", "input"),
            ("18", "MAIN_TXD", "output"),
            ("19", "MAIN_DTR", "input"),
            ("20", "MAIN_RI", "output"),
            ("21", "MAIN_DCD", "output"),
            ("22", "MAIN_CTS", "output"),
            ("23", "MAIN_RTS", "input"),
            None,
            ("38", "DBG_RXD", "input"),
            ("39", "DBG_TXD", "output"),
            ("28", "AUX_RXD", "input"),
            ("29", "AUX_TXD", "output"),
            None,
            ("61", "USB_VBUS", "input"),
            ("59", "USB_DP", "bidirectional"),
            ("60", "USB_DM", "bidirectional"),
            None,
            ("66", "I2C_SDA", "bidirectional"),
            ("67", "I2C_SCL", "output"),
            ("58", "CAM_I2C_SDA", "bidirectional"),
            ("57", "CAM_I2C_SCL", "output"),
            None,
            gnd]
    right = [("24", "VDD_EXT", "power_out"),
             ("8", "GNSS_ANT_VCC", "power_out"),
             None,
             ("35", "ANT_MAIN", "bidirectional"),
             ("2", "GNSS_ANT", "bidirectional"),
             None,
             ("14", "USIM_VDD", "power_out"),
             ("13", "USIM_CLK", "output"),
             ("12", "USIM_RST", "output"),
             ("11", "USIM_DATA", "bidirectional"),
             ("79", "USIM_DET", "input"),
             ("65", "USIM2_VDD", "power_out"),
             ("62", "USIM2_CLK", "output"),
             ("63", "USIM2_RST", "output"),
             ("64", "USIM2_DATA", "bidirectional"),
             None,
             ("16", "NET_STATUS", "output"),
             ("25", "STATUS", "output"),
             None,
             ("9", "ADC0", "input"),
             ("96", "ADC1", "input"),
             ("5", "SPK_P", "output"),
             ("6", "SPK_N", "passive"),
             None,
             ("50", "GPIO1", "bidirectional"),
             ("51", "GPIO3", "bidirectional"),
             ("52", "GPIO4", "bidirectional"),
             ("53", "GPIO5", "bidirectional"),
             ("101", "AGPIO3", "bidirectional"),
             ("97", "AGPIO5", "bidirectional"),
             ("107", "AGPIO5", "bidirectional"),   # same signal, own pad
             ("99", "AGPIO6", "bidirectional")]
    return box_symbol(
        "NT26-KCN", left, right, "LFX:Lierda_NT26-KCN_LCC-LGA-109_15.8x17.7mm",
        "Lierda NT26-KCN E LTE Cat.1 bis module with GNSS, LCC+LGA 109 pins, "
        "17.7 x 15.8 x 2.4 mm",
        "https://opendocs.lierda.com/docs/CAT.1_Doc_Protal/zh_CN/index.html",
        "lte cat1 4g gnss gps beidou modem", half_w=12.7,
        hidden=[(str(n), "REV") for n in NT26_REV])


def sim_symbol():
    # pins as the stock Connector:SIM_Card (ISO 7816 contact numbers) plus
    # the holder's shield
    left = [("1", "VCC", "power_in"),
            ("2", "RST", "input"),
            ("3", "CLK", "input"),
            ("7", "I/O", "bidirectional"),
            ("6", "VPP", "passive")]
    right = [("5", "GND", "power_in"),
             None,
             ("SH", "SHIELD", "passive")]
    return box_symbol(
        "SIM_Card_Shield", left, right,
        "Connector_Card:nanoSIM_GCT_SIM8060-6-0-14-00",
        "SIM card holder with shield / mounting pads", "", "sim card holder",
        half_w=7.62, ref="J")


POWER_RAILS = ["VBAT", "VSYS", "+3V3S", "+1V8", "+3V8"]


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


# Lierda NT26-KCN E land pattern, HDM fig. 8-3 (top view, mm, origin at the
# module centre).  Module 15.8 (x) x 17.7 (y).
NT26_W, NT26_H = 15.8, 17.7
# LCC castellations: 1.1 mm pitch, 13 per long side (span 13.2), 11 per short
# side (span 11).  Pads 0.6 x 2.3 mm, 1.0 mm of it outside the outline.
LCC_W, LCC_L, LCC_OUT = 0.6, 2.3, 1.0
# LGA: outer ring 10.0 x 12.0 on a 1.2 mm pitch (7 x 1.2 = 7.2 between the
# corners on the short rows), inner columns 6.4 apart with 8 pads at 1.2,
# a row of 3 at the bottom, and a 2 x 3 field of 1.3 mm ground pads on a
# 1.8 mm pitch in the middle.
RING1 = {   # (column x, list top -> bottom) and (row y, list left -> right)
    "left":   [99, 45, 46, 47, 48, 49, 50, 51, 52, 53, 100],
    "right":  [104, 67, 66, 65, 64, 63, 62, 61, 60, 59, 103],
    "top":    [99, 106, 72, 71, 70, 69, 68, 105, 104],
    "bottom": [100, 101, 54, 55, 56, 57, 58, 102, 103],
}
RING2 = {
    "left":   [73, 74, 75, 76, 77, 78, 79, 80],
    "right":  [88, 87, 86, 85, 84, 83, 82, 81],
    "bottom": [107, 108, 109],
}
NT26_CENTRE = [(89, -0.9, -1.8), (94, 0.9, -1.8), (90, -0.9, 0.0),
               (93, 0.9, 0.0), (91, -0.9, 1.8), (92, 0.9, 1.8)]


def nt26_pads():
    """[(number, x, y, w, h)] for all 109 pads."""
    out = []
    hx, hy = NT26_W / 2, NT26_H / 2
    c = LCC_OUT - LCC_L / 2                   # pad centre beyond the edge
    for i in range(13):                       # left: 1..13 top -> bottom
        out.append((1 + i, -hx - c, -6.6 + 1.1 * i, LCC_L, LCC_W))
    for i in range(13):                       # right: 23..35 bottom -> top
        out.append((23 + i, hx + c, 6.6 - 1.1 * i, LCC_L, LCC_W))
    bottom = [95] + list(range(14, 23)) + [96]          # left -> right
    for i, n in enumerate(bottom):
        out.append((n, -5.5 + 1.1 * i, hy + c, LCC_W, LCC_L))
    top = [97] + list(range(36, 45)) + [98]             # right -> left
    for i, n in enumerate(top):
        out.append((n, 5.5 - 1.1 * i, -hy - c, LCC_W, LCC_L))
    seen = set()
    for side, lst in RING1.items():
        for i, n in enumerate(lst):
            if n in seen:
                continue
            seen.add(n)
            if side in ("left", "right"):
                x, y = (-5.0 if side == "left" else 5.0), -6.0 + 1.2 * i
            else:
                y = -6.0 if side == "top" else 6.0
                x = -5.0 if i == 0 else 5.0 if i == len(lst) - 1 \
                    else -3.6 + 1.2 * (i - 1)
            corner = abs(x) == 5.0
            out.append((n, x, y, 1.0 if corner or side in ("left", "right")
                        else 0.7, 0.7))
    for side, lst in RING2.items():
        for i, n in enumerate(lst):
            if side == "bottom":
                out.append((n, -1.2 + 1.2 * i, 4.2, 0.65, 0.9))
            else:
                out.append((n, -3.2 if side == "left" else 3.2,
                            -4.2 + 1.2 * i, 0.9, 0.65))
    for n, x, y in NT26_CENTRE:
        out.append((n, x, y, 1.3, 1.3))
    nums = sorted(p[0] for p in out)
    assert nums == list(range(1, 110)), "NT26 pad set is not 1..109"
    return out


def nt26_footprint():
    hx, hy = NT26_W / 2, NT26_H / 2
    cx, cy = hx + LCC_OUT + 0.25, hy + LCC_OUT + 0.25
    L = fp_header("Lierda_NT26-KCN_LCC-LGA-109_15.8x17.7mm",
                  "Lierda NT26-KCN E LTE Cat.1 bis + GNSS, LCC 48 + LGA 61, "
                  "15.8 x 17.7 mm. Land pattern per the Lierda NT26-KCN E "
                  "hardware design manual Rev1.0 fig. 8-3; keep other parts "
                  "2 mm off the pads for a stepped stencil (HDM 8.3)",
                  "lierda nt26 lte cat1 gnss lcc lga", "smd",
                  -cy - 1.0, cy + 1.0)
    L.append(rect(-hx, -hy, hx, hy, "F.Fab", 0.1))
    L.append(rect(-cx, -cy, cx, cy, "F.CrtYd", 0.05))
    # silk: the four corners only (castellations run up to them), pin-1 dot
    sx, sy = hx + 0.15, hy + 0.15
    for ax, ay in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        L.append(line(ax * sx, ay * sy, ax * 6.2, ay * sy, "F.SilkS", 0.12))
        L.append(line(ax * sx, ay * sy, ax * sx, ay * 7.3, "F.SilkS", 0.12))
    L.append('\t(fp_circle (center %g -6.6) (end %g -6.6) (stroke (width 0.2) '
             '(type solid)) (fill yes) (layer "F.SilkS"))'
             % (-hx - LCC_OUT - 0.6, -hx - LCC_OUT - 0.45))
    for n, x, y, w, h in nt26_pads():
        rr = 0.25 if (w == LCC_L or h == LCC_L) else 0.1
        L += [f'\t(pad "{n}" smd roundrect',
              f'\t\t(at {x:g} {y:g})',
              f'\t\t(size {w:g} {h:g})',
              '\t\t(layers "F.Cu" "F.Mask" "F.Paste")',
              f'\t\t(roundrect_rratio {rr:g})',
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


def edge_header_footprint(n=5):
    """1 x n, 2.54 mm right-angle pin header for a board edge: pads in a
    column at x 0 (pad 1 at y 0), the plastic body on the board at x -4.15 ..
    -1.39 and the bent pins running out over the edge to x -10.15, where a
    Dupont plug goes on from the side.  The courtyard covers only what sits on
    the board.  Geometry as the stock PinHeader_1xNN_P2.54mm_Horizontal,
    mirrored so the pins point to -x."""
    name = "PinHeader_1x%02d_P2.54mm_EdgeHorizontal" % n
    L = fp_header(name, "1 x %d 2.54 mm right-angle pin header for a board "
                  "edge: body on the board, bent pins over the edge (-x)" % n,
                  "pin header right angle edge dupont", "through_hole",
                  -2.2, (n - 1) * 2.54 + 2.2, ref="J**")
    ylo, yhi = -1.27, (n - 1) * 2.54 + 1.27
    L.append(rect(-3.9, ylo, -1.39, yhi, "F.SilkS", 0.12))   # inset: the
    # body may sit close to the board edge
    L.append(rect(-4.15, ylo, -1.39, yhi, "F.Fab", 0.1))
    for i in range(n):
        y = i * 2.54
        L.append(rect(-10.15, y - 0.32, -4.15, y + 0.32, "F.Fab", 0.1))
    L.append(line(1.4, -0.9, 1.4, 0.9, "F.SilkS", 0.12))       # pin 1
    L.append(rect(-4.2, ylo - 0.5, 1.1, yhi + 0.5, "F.CrtYd", 0.05))
    for i in range(n):
        L += ['\t(pad "%d" thru_hole %s' % (i + 1,
                                             "rect" if i == 0 else "oval"),
              '\t\t(at 0 %g)' % (i * 2.54),
              '\t\t(size 1.7 1.7)',
              '\t\t(drill 1.0)',
              '\t\t(layers "*.Cu" "*.Mask")',
              '\t\t(remove_unused_layers no)',
              '\t)']
    # the stock right-angle header model turned 180 degrees: pins to -x
    L += ['\t(embedded_fonts no)',
          '\t(model "${KICAD10_3DMODEL_DIR}/Connector_PinHeader_2.54mm.3dshapes/'
          'PinHeader_1x%02d_P2.54mm_Horizontal.step"' % n,
          '\t\t(offset (xyz 0 %g 0))' % (-(n - 1) * 2.54),
          '\t\t(scale (xyz 1 1 1))',
          '\t\t(rotate (xyz 0 0 180))',
          '\t)', ')']
    return name, "\n".join(L)


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
             luckfox_symbol(), nt26_symbol(), sim_symbol()]
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
                       ("Lierda_NT26-KCN_LCC-LGA-109_15.8x17.7mm",
                        nt26_footprint()),
                       ("SolderPad_2.5x4mm", solderpad_footprint()),
                       ("SolderPad_1.5x2.5mm", motorpad_footprint()),
                       ("TestPad_1.0mm", testpad_footprint()),
                       edge_header_footprint(5)):
        p = os.path.join(FP_DIR, name + ".kicad_mod")
        with open(p, "w") as fh:
            fh.write(text if text.endswith("\n") else text + "\n")
        print("wrote", p)


if __name__ == "__main__":
    main()
