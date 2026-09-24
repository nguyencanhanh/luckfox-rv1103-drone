#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LFX_FC_R1 -- design database.

Flight-controller carrier for a Luckfox Pico Mini B (Rockchip RV1103), built for
the rv1103-ai-drone project.  36 x 36 mm, 30.5 x 30.5 mm M3 stack pattern,
2S-6S LiPo through a 4-in-1 ESC on one JST-SH 8-pin cable.

Everything below is the single source of truth: the schematic generator, the
board generator, the BOM and the documentation are all derived from it.

Pin assignments on the Luckfox header come from the repo's own evidence:
docs/PERIPHERALS.md and docs/architecture.html (DTS pinctrl lines quoted there).

Rails
-----
    VBAT        2S-6S LiPo from the ESC connector (6.6-25.2 V, 60 V abs max buck)
    +5V         TPS54360 buck, TI SLVSBB4G figure 34 reference design
    VSYS        Luckfox VBUS / VSYS (header pin 1).  Fed from +5V through an
                LM66100 ideal diode, because the module ties its USB-C VBUS
                straight to this pin (Luckfox-Pico-Mini.pdf, "USB POWER IN").
    +3V3S       TLV75533 LDO from VSYS, IMU + barometer only
    +1V8        Luckfox 1V8_OUT (header pin 22), used only to clamp the ADC inputs
                (SARADC range is 0-1.8 V, Luckfox wiki ADC page)
"""

# ---------------------------------------------------------------------------
# footprint short-hands
# ---------------------------------------------------------------------------
R0402 = "Resistor_SMD:R_0402_1005Metric"
R0603 = "Resistor_SMD:R_0603_1608Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
C1210 = "Capacitor_SMD:C_1210_3225Metric"
FB1206 = "Inductor_SMD:L_1206_3216Metric"
LED0603 = "LED_SMD:LED_0603_1608Metric"
SOD323 = "Diode_SMD:D_SOD-323"
SMB = "Diode_SMD:D_SMB"
SMC = "Diode_SMD:D_SMC"
SOT23 = "Package_TO_SOT_SMD:SOT-23"
SOT235 = "Package_TO_SOT_SMD:SOT-23-5"
SC70_6 = "Package_TO_SOT_SMD:SOT-363_SC-70-6"
PWRPAD8 = "Package_SO:TI_SO-PowerPAD-8_ThermalVias"
USON10 = "Package_SON:USON-10_2.5x1.0mm_P0.5mm"
LGA14 = "Package_LGA:LGA-14_3x2.5mm_P0.5mm_LayoutBorder3x4y"
IND_XAL6060 = "Inductor_SMD:L_Coilcraft_XAL6060-XXX"
JST_SH = "Connector_JST:JST_SH_SM%02dB-SRSS-TB_1x%02d-1MP_P1.00mm_Horizontal"
BMP390_FP = "LFX:Bosch_BMP390_LGA-10_2x2mm_P0.5mm"
MODULE_FP = "LFX:Luckfox_Pico_Mini_Socket"
PAD_BATT = "LFX:SolderPad_2.5x4mm"
TESTPAD = "LFX:TestPad_1.0mm"


def jst_sh(n):
    return JST_SH % (n, n)


# ---------------------------------------------------------------------------
# sheets
# ---------------------------------------------------------------------------
SHEETS = [
    ("02_power",   "Power: ESC input, 5 V buck, ideal diode, sensor LDO"),
    ("03_module",  "Luckfox Pico Mini B socket and debug UART"),
    ("04_sensors", "IMU ICM-42688-P and barometer BMP390 on SPI0"),
    ("05_io",      "ESC signals, GPS, buzzer, battery sense"),
]

POWER_NETS = {
    "GND": "power:GND",
    "+5V": "power:+5V",
    "VBAT": "LFX:VBAT",
    "VSYS": "LFX:VSYS",
    "+3V3S": "LFX:+3V3S",
    "+1V8": "LFX:+1V8",
}
GROUND_NETS = {"GND"}

COMPONENTS = []


def C(ref, lib_id, value, fp, pins, sheet, block, unit=1, dnf=False, **fields):
    COMPONENTS.append(dict(ref=ref, lib_id=lib_id, value=value, fp=fp,
                           pins=pins, sheet=sheet, block=block, unit=unit,
                           dnf=dnf, fields=fields))


def R(ref, val, fp, a, b, sheet, block, **kw):
    C(ref, "Device:R", val, fp, {"1": a, "2": b}, sheet, block, **kw)


def Cap(ref, val, fp, a, b, sheet, block, **kw):
    C(ref, "Device:C", val, fp, {"1": a, "2": b}, sheet, block, **kw)


# KiCad Device:D*, Device:LED: pin 1 = K, pin 2 = A.  Arguments are named by
# ROLE so a call can never be read the wrong way round.
def Diode(ref, val, fp, anode, cathode, sheet, block, kind="Device:D", **kw):
    C(ref, kind, val, fp, {"1": cathode, "2": anode}, sheet, block, **kw)


def LED(ref, val, fp, anode, cathode, sheet, block, **kw):
    C(ref, "Device:LED", val, fp, {"1": cathode, "2": anode}, sheet, block, **kw)


def L(ref, val, fp, a, b, sheet, block, **kw):
    C(ref, "Device:L", val, fp, {"1": a, "2": b}, sheet, block, **kw)


def FB(ref, val, fp, a, b, sheet, block, **kw):
    C(ref, "Device:FerriteBead_Small", val, fp, {"1": a, "2": b}, sheet, block,
      **kw)


def TP(ref, net, sheet, block):
    C(ref, "Connector:TestPoint", "TP", TESTPAD, {"1": net}, sheet, block)


# ===========================================================================
# SHEET 02 -- POWER
# ===========================================================================
S = "02_power"

B = "Battery input from the 4-in-1 ESC"
# J1 is on sheet 05 (it carries the motor signals too); VBAT arrives here.
C("J2", "Connector:TestPoint", "VBAT pad", PAD_BATT, {"1": "VBAT"}, S, B,
  Description="Bench supply / XT30 pigtail, only when no ESC is fitted")
C("J3", "Connector:TestPoint", "GND pad", PAD_BATT, {"1": "GND"}, S, B,
  Description="Bench supply ground")
C("D1", "Diode:SM6T33A", "SM6T33A", SMB, {"1": "VBAT_F", "2": "GND"}, S, B,
  Description="600 W unidirectional TVS, VRM 28.2 V > 6S full charge 25.2 V")
FB("FB1", "600R@100MHz 3A", FB1206, "VBAT", "VBAT_F", S, B,
   Description="Keeps ESC switching noise out of the buck input")
Cap("C1", "2u2/100V", C1210, "VBAT_F", "GND", S, B)
Cap("C2", "2u2/100V", C1210, "VBAT_F", "GND", S, B)
Cap("C3", "10u/50V", C1210, "VBAT_F", "GND", S, B)
Cap("C4", "100n/100V", C0603, "VBAT_F", "GND", S, B)
C("FLG4", "power:PWR_FLAG", "PWR_FLAG", "", {"1": "VBAT_F"}, S, B)

B = "TPS54360 buck  VBAT -> +5V"
# Values: TI SLVSBB4G figure 34 (5 V / 3.5 A, 600 kHz) except R1/R2, which are
# recomputed with SLVSBB4G equations 4 and 5 for a 2S cut-in:
#   R1 = (Vstart - Vstop) / 3.4 uA,  R2 = 1.2 / ((Vstart - 1.2)/R1 + 1.2 uA)
#   178k / 39.2k -> start 6.44 V, stop 5.83 V
C("U1", "Regulator_Switching:TPS54360DDA", "TPS54360DDA", PWRPAD8,
  {"1": "BOOT5", "2": "VBAT_F", "3": "EN5", "4": "RT5", "5": "FB5",
   "6": "COMP5", "7": "GND", "8": "SW5", "9": "GND"}, S, B)
Cap("C5", "100n/16V", C0603, "BOOT5", "SW5", S, B)
R("R1", "178k 1%", R0603, "VBAT_F", "EN5", S, B)
R("R2", "39k2 1%", R0603, "EN5", "GND", S, B)
Diode("D2", "BZX384-C5V6", SOD323, "GND", "EN5", S, B, kind="Device:D_Zener",
      Description="Clamps EN below its 8.4 V abs max on a 45 V transient "
                  "(SLVSBB4G 7.3.7)")
R("R3", "162k 1%", R0603, "RT5", "GND", S, B, Description="600 kHz")
R("R4", "13k0 1%", R0603, "COMP5", "COMP5_C", S, B)
Cap("C6", "6n8/50V", C0603, "COMP5_C", "GND", S, B)
Cap("C7", "39p/50V", C0603, "COMP5", "GND", S, B)
Diode("D3", "B560C", SMC, "GND", "SW5", S, B, kind="Device:D_Schottky",
      Description="60 V 5 A catch diode, as SLVSBB4G figure 34")
L("L1", "8.2uH", IND_XAL6060, "SW5", "+5V", S, B,
  Description="8.2 uH, Isat >= 5 A, DCR <= 20 mOhm (SLVSBB4G fig. 34 value)")
R("R5", "53k6 1%", R0603, "+5V", "FB5", S, B)
R("R6", "10k2 1%", R0603, "FB5", "GND", S, B)
Cap("C8", "47u/10V", C1210, "+5V", "GND", S, B)
Cap("C9", "47u/10V", C1210, "+5V", "GND", S, B)
Cap("C10", "100n/16V", C0603, "+5V", "GND", S, B)
LED("D4", "GREEN", LED0603, "LED5_A", "GND", S, B)
R("R7", "2k2", R0603, "+5V", "LED5_A", S, B)
C("FLG1", "power:PWR_FLAG", "PWR_FLAG", "", {"1": "VBAT"}, S, B)
C("FLG2", "power:PWR_FLAG", "PWR_FLAG", "", {"1": "GND"}, S, B)
C("FLG3", "power:PWR_FLAG", "PWR_FLAG", "", {"1": "+5V"}, S, B)
TP("TP1", "+5V", S, B)

B = "LM66100 ideal diode  +5V -> VSYS (blocks USB back-feed)"
C("U2", "LFX:LM66100", "LM66100DCK", SC70_6,
  {"1": "+5V", "2": "GND", "3": "VSYS", "4": "", "5": "GND", "6": "VSYS"},
  S, B, Description="1.5 A max; CE tied to VOUT for reverse-current "
                    "blocking (TI SLVSEZ8A pin table)")
Cap("C11", "1u/16V", C0603, "+5V", "GND", S, B)
Cap("C12", "10u/10V", C0805, "VSYS", "GND", S, B)
TP("TP2", "VSYS", S, B)

B = "TLV75533 LDO  VSYS -> +3V3S (sensors only)"
C("U3", "Regulator_Linear:TLV75533PDBV", "TLV75533PDBV", SOT235,
  {"1": "VSYS", "2": "GND", "3": "VSYS", "4": "", "5": "+3V3S"}, S, B)
Cap("C13", "1u/16V", C0603, "VSYS", "GND", S, B)
Cap("C14", "1u/16V", C0603, "+3V3S", "GND", S, B)
TP("TP3", "+3V3S", S, B)

# ===========================================================================
# SHEET 03 -- LUCKFOX MODULE
# ===========================================================================
S = "03_module"
B = "Luckfox Pico Mini B, 2x 1x11 female header"
# Header pin n == module pin n (Luckfox-Pico-Mini.pdf "Pin Out" H2).
C("MOD1", "LFX:Luckfox_Pico_Mini", "Luckfox Pico Mini B", MODULE_FP, {
    "1": "VSYS",            # VBUS
    "2": "GND",
    "3": "",                # 3V3_O: module's own rail, not loaded
    "4": "DBG_TX",          # UART2_TX_M1  GPIO1_B2
    "5": "DBG_RX",          # UART2_RX_M1  GPIO1_B3
    "6": "IMU_CS",          # SPI0_CS0_M0  GPIO1_C0
    "7": "SPI_SCK",         # SPI0_CLK_M0  GPIO1_C1
    "8": "SPI_MOSI",        # SPI0_MOSI_M0 GPIO1_C2
    "9": "SPI_MISO",        # SPI0_MISO_M0 GPIO1_C3
    "10": "ESC_M1_IO",      # PWM8_M1      GPIO1_C4
    "11": "ESC_M2_IO",      # PWM9_M1      GPIO1_C5
    "12": "GPS_TX",         # UART3_TX_M1  GPIO1_D0
    "13": "GPS_RX",         # UART3_RX_M1  GPIO1_D1
    "14": "BARO_CS",        # SPI0_CS1_M0  GPIO1_D2 (pinctrl:852-855)
    "15": "IMU_INT1",       # GPIO1_D3
    "16": "ESC_M3_IO",      # PWM10_M1     GPIO1_C6
    "17": "ESC_M4_IO",      # PWM11_M1     GPIO1_C7
    "18": "BUZ_CTRL",       # GPIO0_A4
    "19": "ADC_VBAT",       # SARADC_IN0   GPIO4_C0
    "20": "ADC_CUR",        # SARADC_IN1   GPIO4_C1
    "21": "GND",
    "22": "+1V8",           # 1V8_OUT (10 R inside the module)
}, S, B, Description="Plugs in with USB-C at the board edge; 2x 1x11 "
                     "female header 2.54 mm, 17.78 mm row pitch")
Cap("C15", "10u/10V", C0805, "VSYS", "GND", S, B,
    Description="Local reservoir at header pin 1")

B = "Debug console UART2 (115200 8N1)"
C("J4", "Connector:Conn_01x03_Pin", "SM03B-SRSS-TB", jst_sh(3),
  {"1": "DBG_TX_X", "2": "DBG_RX_X", "3": "GND", "MP": "GND"}, S, B,
  Description="1:TX (board out) 2:RX (board in) 3:GND")
R("R8", "33R", R0402, "DBG_TX", "DBG_TX_X", S, B)
R("R9", "33R", R0402, "DBG_RX_X", "DBG_RX", S, B)

# ===========================================================================
# SHEET 04 -- SENSORS
# ===========================================================================
S = "04_sensors"
B = "ICM-42688-P 6-axis IMU, SPI 4-wire"
# Pin table: TDK DS-000347 v1.7 table 10.  RESV 2/3/10/11 "NC or GND" -> GND,
# RESV 7 "connect to GND", FSYNC (9) "connect to GND if not used".
C("U4", "LFX:ICM-42688-P", "ICM-42688-P", LGA14,
  {"1": "SPI_MISO", "2": "GND", "3": "GND", "4": "IMU_INT1", "5": "+3V3S",
   "6": "GND", "7": "GND", "8": "+3V3S", "9": "GND", "10": "GND",
   "11": "GND", "12": "IMU_CS", "13": "SPI_SCK", "14": "SPI_MOSI"}, S, B)
Cap("C16", "100n/16V", C0402, "+3V3S", "GND", S, B,
    Description="VDD bypass 0.1 uF (DS-000347 bypass table)")
Cap("C17", "2u2/10V", C0402, "+3V3S", "GND", S, B,
    Description="VDD bypass 2.2 uF")
Cap("C18", "10n/16V", C0402, "+3V3S", "GND", S, B,
    Description="VDDIO bypass 10 nF")
R("R10", "10k", R0402, "+3V3S", "IMU_CS", S, B,
  Description="Holds CS high while the SoC pins float at boot")

B = "BMP390 barometer, SPI 4-wire"
# Pin table: Bosch BST-BMP390-DS002-07 table 52.
C("U5", "LFX:BMP390", "BMP390", BMP390_FP,
  {"1": "+3V3S", "2": "SPI_SCK", "3": "GND", "4": "SPI_MOSI",
   "5": "SPI_MISO", "6": "BARO_CS", "7": "", "8": "GND", "9": "GND",
   "10": "+3V3S"}, S, B)
Cap("C19", "100n/16V", C0402, "+3V3S", "GND", S, B,
    Description="VDD 100 nF (BMP390 DS 6.2)")
Cap("C20", "100n/16V", C0402, "+3V3S", "GND", S, B,
    Description="VDDIO 100 nF")
R("R11", "10k", R0402, "+3V3S", "BARO_CS", S, B,
  Description="CSB must stay high until SPI is selected")

# ===========================================================================
# SHEET 05 -- IO
# ===========================================================================
S = "05_io"
B = "4-in-1 ESC connector (JST-SH 8)"
C("J1", "Connector:Conn_01x08_Pin", "SM08B-SRSS-TB", jst_sh(8),
  {"1": "VBAT", "2": "GND", "3": "ESC_CUR", "4": "ESC_TLM",
   "5": "ESC_M1", "6": "ESC_M2", "7": "ESC_M3", "8": "ESC_M4", "MP": "GND"},
  S, B, Description="1:VBAT 2:GND 3:CUR 4:TLM 5-8:M1-M4. Pin order differs "
                    "between ESC brands: check the ESC cable before powering")
for n in (1, 2, 3, 4):
    R("R%d" % (11 + n), "47R", R0402, "ESC_M%d_IO" % n, "ESC_M%d" % n, S, B,
      Description="Series termination for the ESC cable")
TP("TP4", "ESC_TLM", S, B)

B = "Battery voltage and current sense (SARADC 0-1.8 V)"
R("R16", "100k 1%", R0603, "VBAT", "ADC_VBAT", S, B)
R("R17", "6k8 1%", R0603, "ADC_VBAT", "GND", S, B,
  Description="Ratio 0.0637: 25.2 V -> 1.60 V, 1.8 V at 28.3 V")
Cap("C21", "100n/16V", C0402, "ADC_VBAT", "GND", S, B)
C("D5", "Diode:BAT54S", "BAT54S", SOT23,
  {"1": "GND", "2": "+1V8", "3": "ADC_VBAT"}, S, B,
  Description="Clamps the ADC pin between GND and 1V8")
R("R18", "10k 1%", R0603, "ESC_CUR", "ADC_CUR", S, B)
R("R19", "12k 1%", R0603, "ADC_CUR", "GND", S, B,
  Description="Ratio 0.545: 3.3 V ESC current output -> 1.80 V")
Cap("C22", "100n/16V", C0402, "ADC_CUR", "GND", S, B)
C("D6", "Diode:BAT54S", "BAT54S", SOT23,
  {"1": "GND", "2": "+1V8", "3": "ADC_CUR"}, S, B)

B = "GPS / GNSS (UART3)"
C("J5", "Connector:Conn_01x04_Pin", "SM04B-SRSS-TB", jst_sh(4),
  {"1": "+5V", "2": "GND", "3": "GPS_TX_X", "4": "GPS_RX_X", "MP": "GND"},
  S, B, Description="1:5V 2:GND 3:TX (board out) 4:RX (board in)")
R("R20", "33R", R0402, "GPS_TX", "GPS_TX_X", S, B)
R("R21", "33R", R0402, "GPS_RX_X", "GPS_RX", S, B)
C("U6", "Power_Protection:TPD4E05U06DQA", "TPD4E05U06DQA", USON10,
  {"1": "GPS_TX_X", "2": "GPS_RX_X", "3": "GND", "4": "DBG_TX_X",
   "5": "DBG_RX_X", "6": "", "7": "", "8": "GND", "9": "", "10": ""}, S, B,
  Description="ESD on the two external UART connectors")

B = "Buzzer driver"
C("J6", "Connector:Conn_01x02_Pin", "SM02B-SRSS-TB", jst_sh(2),
  {"1": "+5V", "2": "BUZ_N", "MP": "GND"}, S, B,
  Description="1:+5V 2:buzzer - (low side switched)")
C("Q1", "Transistor_FET:AO3400A", "AO3400A", SOT23,
  {"1": "BUZ_G", "2": "GND", "3": "BUZ_N"}, S, B)
R("R22", "100R", R0402, "BUZ_CTRL", "BUZ_G", S, B)
R("R23", "100k", R0402, "BUZ_G", "GND", S, B,
  Description="Buzzer off while the SoC pin floats")
Diode("D7", "BAT54", SOD323, "BUZ_N", "+5V", S, B, kind="Device:D_Schottky",
      Description="Flyback for a magnetic buzzer")

B = "Mounting"
for i in range(1, 5):
    C("H%d" % i, "Mechanical:MountingHole", "M3", "", {}, S, B)


# ---------------------------------------------------------------------------
def nets():
    """net name -> [(ref, pin), ...]"""
    out = {}
    for c in COMPONENTS:
        for pin, net in c["pins"].items():
            if not net:
                continue
            out.setdefault(net, []).append((c["ref"], pin))
    return out


def check():
    problems = []
    refs = [(c["ref"], c["unit"]) for c in COMPONENTS]
    dup = {r for r in refs if refs.count(r) > 1}
    if dup:
        problems.append("duplicate refs: %s" % sorted(dup))
    for net, conns in sorted(nets().items()):
        if len(conns) < 2:
            problems.append("single-pin net %-16s %s" % (net, conns))
    return problems


def diode_report():
    """Print anode/cathode nets of every diode, the check that caught the
    reversed diodes on the reference project."""
    rows = []
    for c in COMPONENTS:
        lid = c["lib_id"]
        if lid.startswith("Device:D") or lid == "Device:LED" \
                or lid.startswith("Diode:SM6T"):
            rows.append((c["ref"], c["value"], c["pins"].get("2"),
                         c["pins"].get("1")))
    return rows


if __name__ == "__main__":
    n = nets()
    print("components : %d" % len(COMPONENTS))
    print("nets       : %d" % len(n))
    print("pins       : %d" % sum(len(v) for v in n.values()))
    for ref, val, a, k in diode_report():
        print("  diode %-4s %-12s A=%-10s K=%s" % (ref, val, a, k))
    for p in check():
        print("  !!", p)
