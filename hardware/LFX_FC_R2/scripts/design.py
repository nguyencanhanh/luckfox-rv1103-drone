#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LFX_FC_R2 -- design database.

Flight controller for a Luckfox Pico Mini B (Rockchip RV1103), built for the
rv1103-ai-drone project: one 50 x 50 mm board with the LTE Cat.1 bis + GNSS
modem on it (Lierda NT26-KCN E, nano-SIM, two U.FL).  M3 holes on a 39 mm
pattern, 2S-6S LiPo, four separate ESCs on the corner S/G pads.

It merges LFX_FC_R1 (flight controller) and LFX_LTE_R1 (the stacked LTE
board) into one: the 4-in-1 ESC connector and the board-to-board cable are
gone, the modem sits under the front half, the nano-SIM over it.

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
    +3V8        TLV62569 buck from +5V, the modem's VBAT (3.3-4.5 V, 3.8 V
                typical, 1.2 A bursts: Lierda NT26-KCN E hardware design
                manual Rev1.0, "HDM" below, 3.4)
    LTE_1V8     the modem's own VDD_EXT output (1.8 V); its UART runs on it

Luckfox pins for the modem
--------------------------
Every header pin was already in use.  The external GPS connector (UART3) is
gone - the modem has GNSS on board and reports it over the same UART - and
the buzzer moved onto the modem's AGPIO5, which frees the four pins needed to
talk to the modem AND reflash it from Linux:
    12 / 13     UART3 TX / RX -> MAIN_RXD / MAIN_TXD through 3.3 <-> 1.8 V
                translators (AT, GNSS, firmware download at 921600 bd)
    18          LTE_RST  -> RESET_N through an open-drain FET (HDM 3.7)
    20          LTE_BOOT -> USB_BOOT: GPIO4_C1 is a 1.8 V-only bank, the
                modem's level; high while the modem resets = download mode
                (HDM 3.5.3, 4.1.3)
"""

# ---------------------------------------------------------------------------
# footprint short-hands
# ---------------------------------------------------------------------------
R0402 = "Resistor_SMD:R_0402_1005Metric"
R0603 = "Resistor_SMD:R_0603_1608Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
C1206 = "Capacitor_SMD:C_1206_3216Metric"
C1210 = "Capacitor_SMD:C_1210_3225Metric"
FB1206 = "Inductor_SMD:L_1206_3216Metric"
LED0603 = "LED_SMD:LED_0603_1608Metric"
SOD323 = "Diode_SMD:D_SOD-323"
SMA = "Diode_SMD:D_SMA"
SMB = "Diode_SMD:D_SMB"
SOT23 = "Package_TO_SOT_SMD:SOT-23"
SOT235 = "Package_TO_SOT_SMD:SOT-23-5"
SC70_6 = "Package_TO_SOT_SMD:SOT-363_SC-70-6"
PWRPAD8 = "Package_SO:TI_SO-PowerPAD-8_ThermalVias"
USON10 = "Package_SON:USON-10_2.5x1.0mm_P0.5mm"
LGA14 = "Package_LGA:LGA-14_3x2.5mm_P0.5mm_LayoutBorder3x4y"
IND_XAL5050 = "Inductor_SMD:L_Coilcraft_XAL5050-XXX"
JST_SH = "Connector_JST:JST_SH_SM%02dB-SRSS-TB_1x%02d-1MP_P1.00mm_Horizontal"
BMP390_FP = "LFX:Bosch_BMP390_LGA-10_2x2mm_P0.5mm"
MODULE_FP = "LFX:Luckfox_Pico_Mini_Socket"
PAD_BATT = "LFX:SolderPad_2.5x4mm"
PAD_MOTOR = "LFX:SolderPad_1.5x2.5mm"
TESTPAD = "LFX:TestPad_1.0mm"
L0402 = "Inductor_SMD:L_0402_1005Metric"
IND_XAL4020 = "Inductor_SMD:L_Coilcraft_XAL4020-XXX"
SOT23_6 = "Package_TO_SOT_SMD:SOT-23-6"
NT26_FP = "LFX:Lierda_NT26-KCN_LCC-LGA-109_15.8x17.7mm"
NANOSIM = "Connector_Card:nanoSIM_GCT_SIM8060-6-0-14-00"
UFL = "Connector_Coaxial:U.FL_Hirose_U.FL-R-SMT-1_Vertical"


def jst_sh(n):
    return JST_SH % (n, n)


# ---------------------------------------------------------------------------
# sheets
# ---------------------------------------------------------------------------
SHEETS = [
    ("02_power",   "Power: ESC input, 5 V buck, ideal diode, sensor LDO"),
    ("03_module",  "Luckfox Pico Mini B socket and RC receiver port"),
    ("04_sensors", "IMU ICM-42688-P and barometer BMP390 on SPI0"),
    ("05_io",      "ESC pads, buzzer, battery sense"),
    ("06_lte",     "Lierda NT26-KCN E LTE Cat.1 bis + GNSS: supply, UART, "
                   "reset / download"),
    ("07_lte_rf",  "LTE nano-SIM and antennas (U.FL LTE + GNSS)"),
]

POWER_NETS = {
    "GND": "power:GND",
    "+5V": "power:+5V",
    "VBAT": "LFX:VBAT",
    "VSYS": "LFX:VSYS",
    "+3V3S": "LFX:+3V3S",
    "+1V8": "LFX:+1V8",
    "+3V8": "LFX:+3V8",
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

B = "Battery input"
# The battery lead (XT30 pigtail) is soldered here; the four ESCs take their
# power straight from the same pigtail.
C("J2", "Connector:TestPoint", "VBAT pad", PAD_BATT, {"1": "VBAT"}, S, B,
  Description="2S-6S LiPo +, from the XT30 pigtail that also feeds the ESCs")
C("J3", "Connector:TestPoint", "GND pad", PAD_BATT, {"1": "GND"}, S, B,
  Description="LiPo -")
C("D1", "Diode:SMAJ33A", "SMAJ33A", SMA, {"1": "VBAT", "2": "GND"}, S, B,
  Description="400 W unidirectional TVS, 33 V standoff > 6S full charge "
              "25.2 V; at the battery entry, ahead of FB1; pad 1 (band) on "
              "VBAT")
FB("FB1", "600R@100MHz 3A", FB1206, "VBAT", "VBAT_F", S, B,
   Description="Keeps ESC switching noise out of the buck input")
Cap("C1", "2u2/100V X7S", C1206, "VBAT_F", "GND", S, B,
    Description="Input caps as SLVSBB4G fig. 34: 2 x 2.2 uF, 100 V")
Cap("C2", "2u2/100V X7S", C1206, "VBAT_F", "GND", S, B)
Cap("C4", "100n/100V", C0603, "VBAT_F", "GND", S, B)
C("#FLG04", "power:PWR_FLAG", "PWR_FLAG", "", {"1": "VBAT_F"}, S, B)

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
# the FB / COMP network is 0402 on this board: it sits in one tight block
# right over U1's FB / COMP pins
R("R4", "13k0 1%", R0402, "COMP5", "COMP5_C", S, B)
Cap("C6", "6n8/50V", C0402, "COMP5_C", "GND", S, B)
Cap("C7", "39p/50V", C0402, "COMP5", "GND", S, B)
Diode("D3", "B360B", SMB, "GND", "SW5", S, B, kind="Device:D_Schottky",
      Description="60 V 3 A catch diode.  SLVSBB4G fig. 34 uses a 5 A B560C "
                  "for 3.5 A out; this board draws <= 2.6 A (LM66100 1.5 A + "
                  "the modem buck's 1.05 A input peak + buzzer), and the "
                  "SMC package does not fit")
L("L1", "8.2uH", IND_XAL5050, "SW5", "+5V", S, B,
  Description="8.2 uH (SLVSBB4G fig. 34 value), Isat >= 3.5 A, "
              "DCR <= 40 mOhm, 5 x 5 mm (Coilcraft XAL5050-822 class). "
              "Ripple at 25.2 V in: 0.81 A p-p, peak 2.4 A at 2 A load")
R("R5", "53k6 1%", R0402, "+5V", "FB5", S, B)
R("R6", "10k2 1%", R0402, "FB5", "GND", S, B)
Cap("C8", "47u/10V", C1210, "+5V", "GND", S, B)
Cap("C9", "47u/10V", C1210, "+5V", "GND", S, B)
Cap("C10", "100n/16V", C0603, "+5V", "GND", S, B)
LED("D4", "GREEN", LED0603, "LED5_A", "GND", S, B)
R("R7", "2k2", R0603, "+5V", "LED5_A", S, B)
C("#FLG01", "power:PWR_FLAG", "PWR_FLAG", "", {"1": "VBAT"}, S, B)
C("#FLG02", "power:PWR_FLAG", "PWR_FLAG", "", {"1": "GND"}, S, B)
C("#FLG03", "power:PWR_FLAG", "PWR_FLAG", "", {"1": "+5V"}, S, B)
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
    "3": "3V3_MOD",         # 3V3_O: the SoC's own IO rail; only the RC_RX
                            # pull-up (R24, <= 3.3 mA) hangs on it
    "4": "RC_TX",           # UART2_TX_M1  GPIO1_B2  -> receiver RX (telemetry)
    "5": "RC_RX",           # UART2_RX_M1  GPIO1_B3  <- receiver TX (CRSF)
    "6": "IMU_CS",          # SPI0_CS0_M0  GPIO1_C0
    "7": "SPI_SCK",         # SPI0_CLK_M0  GPIO1_C1
    "8": "SPI_MOSI",        # SPI0_MOSI_M0 GPIO1_C2
    "9": "SPI_MISO",        # SPI0_MISO_M0 GPIO1_C3
    "10": "ESC_M3_IO",      # PWM8_M1      GPIO1_C4   rear-left motor
    "11": "ESC_M4_IO",      # PWM9_M1      GPIO1_C5   front-left motor
    "12": "LTE_TX",         # UART3_TX_M1  GPIO1_D0  -> modem MAIN_RXD
    "13": "LTE_RX",         # UART3_RX_M1  GPIO1_D1  <- modem MAIN_TXD
    "14": "BARO_CS",        # SPI0_CS1_M0  GPIO1_D2 (pinctrl:852-855)
    "15": "IMU_INT1",       # GPIO1_D3
    "16": "ESC_M1_IO",      # PWM10_M1     GPIO1_C6   rear-right motor
    "17": "ESC_M2_IO",      # PWM11_M1     GPIO1_C7   front-right motor
    "18": "LTE_RST",        # GPIO0_A4     high = modem in reset
    "19": "ADC_VBAT",       # SARADC_IN0   GPIO4_C0
    "20": "LTE_BOOT",       # GPIO4_C1     high at reset = modem download
    "21": "GND",
    "22": "+1V8",           # 1V8_OUT (10 R inside the module)
}, S, B, Description="Plugs in with USB-C at the board edge; 2x 1x11 "
                     "female header 2.54 mm, 17.78 mm row pitch")
Cap("C15", "10u/10V", C0805, "VSYS", "GND", S, B,
    Description="Local reservoir at header pin 1")

B = "RC receiver UART2 (CRSF / ExpressLRS)"
# The only UART left on the module.  An ExpressLRS / Crossfire receiver talks
# CRSF: a full, non-inverted UART pair at 420000 baud (ELRS default; TBS spec
# 416666), powered from 5 V (expresslrs.org, "Receiver Wiring").  UART2 has
# its own fractional divider (clk-rv1106.c:441): 16 x 420000 = 6.72 MHz =
# 24 MHz x 7/25.  Linux's console (earlycon 0xff4c0000, fiq-debugger
# serial-id 2, rv1106.dtsi:225-232) has to move off UART2 in software; debug
# goes over ADB, or through TP5/TP6 with the receiver unplugged.
# Pin order: power, ground, then the board's TX and RX.
C("J4", "Connector_Generic_MountingPin:Conn_01x04_MountingPin",
  "SM04B-SRSS-TB", jst_sh(4),
  {"1": "+5V", "2": "GND", "3": "RC_TX_X", "4": "RC_RX_X", "MP": "GND"},
  S, B, Description="RC receiver (ELRS/CRSF). 1:5V 2:GND 3:TX (board out, "
                    "to receiver RX) 4:RX (board in, from receiver TX)")
R("R8", "33R", R0402, "RC_TX", "RC_TX_X", S, B)
R("R9", "33R", R0402, "RC_RX_X", "RC_RX", S, B)
# ESP-based ELRS receivers stall in their bootloader when the line from their
# TX pin is held low at power-up; ExpressLRS suggests 300-1000 R to 3.3 V on
# the FC RX pad.  The SoC pin's reset pull state is UNKNOWN, so fit it, to
# the module's own 3.3 V (pin 3): the rail the GPIO bank itself runs from.
R("R24", "1k", R0402, "RC_RX", "3V3_MOD", S, B,
  Description="Keeps the receiver TX line high at power-up (ELRS wiring "
              "guide: 300-1000 R pull-up on the FC RX pad)")
C("U7", "Power_Protection:TPD4E05U06DQA", "TPD4E05U06DQA", USON10,
  {"1": "RC_TX_X", "2": "RC_RX_X", "3": "GND", "4": "", "5": "",
   "6": "", "7": "", "8": "GND", "9": "", "10": ""}, S, B,
  Description="ESD at the RC receiver connector")
TP("TP5", "RC_TX", S, B)      # UART2 console tap when no receiver is fitted
TP("TP6", "RC_RX", S, B)

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
B = "Separate ESC solder pads (quad-X corners)"
# Betaflight quad-X numbering, front = the camera edge: M1 rear-right,
# M2 front-right, M3 rear-left, M4 front-left.  PWM pins follow the module
# column on the same side, so no motor signal crosses the board.
for n, (sig, gnd) in enumerate((("J7", "J11"), ("J8", "J12"),
                                ("J9", "J13"), ("J10", "J14")), start=1):
    C(sig, "Connector:TestPoint", "M%d pad" % n, PAD_MOTOR,
      {"1": "ESC_M%d" % n}, S, B, Description="Motor %d signal pad" % n)
    C(gnd, "Connector:TestPoint", "M%d GND" % n, PAD_MOTOR,
      {"1": "GND"}, S, B, Description="Motor %d signal ground" % n)
    R("R%d" % (11 + n), "47R", R0402, "ESC_M%d_IO" % n, "ESC_M%d" % n, S, B,
      Description="Series termination for the ESC lead")

B = "Battery voltage sense (SARADC 0-1.8 V)"
R("R16", "100k 1%", R0603, "VBAT", "ADC_VBAT", S, B)
R("R17", "6k8 1%", R0603, "ADC_VBAT", "GND", S, B,
  Description="Ratio 0.0637: 25.2 V -> 1.60 V, 1.8 V at 28.3 V")
Cap("C21", "100n/16V", C0402, "ADC_VBAT", "GND", S, B)
C("D5", "Diode:BAT54S", "BAT54S", SOT23,
  {"1": "GND", "2": "+1V8", "3": "ADC_VBAT"}, S, B,
  Description="Clamps the ADC pin between GND and 1V8")

B = "Buzzer driver (gate from NT26 AGPIO5)"
C("J6", "Connector_Generic_MountingPin:Conn_01x02_MountingPin", "SM02B-SRSS-TB", jst_sh(2),
  {"1": "+5V", "2": "BUZ_N", "MP": "GND"}, S, B,
  Description="1:+5V 2:buzzer - (low side switched)")
C("Q1", "Transistor_FET:AO3400A", "AO3400A", SOT23,
  {"1": "BUZ_G", "2": "GND", "3": "BUZ_N"}, S, B)
# BUZ_CTRL is the modem's AGPIO5 (pin 97, 1.8 V, LDO_AONIO).  AO3400A VGS(th) is
# 0.65-1.45 V: 1.8 V of gate drive is enough for a ~30 mA buzzer.
R("R22", "100R", R0402, "BUZ_CTRL", "BUZ_G", S, B)
R("R23", "100k", R0402, "BUZ_G", "GND", S, B,
  Description="Buzzer off while the modem GPIO floats or the modem is off")
Diode("D7", "BAT54", SOD323, "BUZ_N", "+5V", S, B, kind="Device:D_Schottky",
      Description="Flyback for a magnetic buzzer")

B = "Mounting"
for i in range(1, 5):
    C("H%d" % i, "Mechanical:MountingHole", "M3",
      "MountingHole:MountingHole_3.2mm_M3", {}, S, B)


# ===========================================================================
# SHEET 06 -- LTE Cat.1 bis + GNSS (Lierda NT26-KCN E)
# ===========================================================================
# Every pin and value below is from the Lierda NT26-KCN E hardware design
# manual Rev1.0 (2025-04-27), "HDM" in the comments.  Order the GPS + BDS
# variant: the NT26KCNE20GNB that manual is written for is BeiDou-only
# (HDM 6, table 6-2); both share the pin-out and land pattern.
S = "06_lte"

B = "Lierda NT26-KCN E  LTE Cat.1 bis + GNSS"
# HDM 2.5 table 2-5.  Pins left "" are unused and carry a no-connect flag;
# the REV pins are no-connect pins of the symbol itself (HDM: 68, 69, 75,
# 86, 87 and 105 must stay open).
NT26_GND = (1, 10, 27, 34, 36, 37, 40, 41, 45, 46, 47, 48, 70, 71, 72, 73,
            88, 89, 90, 91, 92, 93, 94, 95)
nt26 = {str(n): "GND" for n in NT26_GND}
nt26.update({
    "42": "+3V8", "43": "+3V8",          # VBAT
    "24": "LTE_1V8",                     # VDD_EXT, 1.8 V out
    "8": "GNSS_VCC",                     # GNSS_ANT_VCC, 3.3 V / 200 mA out
    "7": "LTE_PWRKEY",
    "15": "LTE_RESET_N",
    "17": "LTE_TX_1V8",                  # MAIN_RXD
    "18": "LTE_RX_1V8",                  # MAIN_TXD
    "19": "", "20": "", "21": "", "22": "", "23": "",   # DTR RI DCD CTS RTS
    "38": "LTE_DBG_RX", "39": "LTE_DBG_TX",             # 3 Mbd log port
    "28": "", "29": "",                  # AUX UART: the internal GNSS's
    "59": "LTE_USB_DP", "60": "LTE_USB_DM", "61": "LTE_USB_VBUS",
    "82": "LTE_BOOT_M",                  # USB_BOOT
    "11": "SIM_DATA_M", "12": "SIM_RST_M", "13": "SIM_CLK_M",
    "14": "SIM_VDD", "79": "",           # USIM_DET: holder has no switch
    "62": "", "63": "", "64": "", "65": "",             # USIM2
    "35": "LTE_ANT", "2": "GNSS_ANT",
    "57": "", "58": "", "66": "", "67": "",             # I2C
    "5": "", "6": "",                    # SPK
    "9": "", "96": "",                   # ADC0, ADC1 (no ESC current)
    "16": "LTE_NET", "25": "",           # NET_STATUS, STATUS
    "50": "",                            # GPIO1: an inner LGA pad, no escape
    "51": "", "52": "", "53": "",        # GPIO4/5 belong to the GNSS
    "97": "BUZ_CTRL",                    # AGPIO5, an edge (LCC) pad, drives
    "107": "", "99": "", "101": "",      # the buzzer FET; 107 = AGPIO5 too
})
C("U8", "LFX:NT26-KCN", "NT26-KCN E (GPS+BDS)", NT26_FP, nt26, S, B,
  Description="Lierda NT26-KCN E LTE Cat.1 bis (B1/3/5/8/34/38/39/40/41) "
              "+ GNSS, LCC+LGA 109, 17.7 x 15.8 x 2.4 mm. Order the GPS+BDS "
              "variant",
  Datasheet="https://opendocs.lierda.com/docs/CAT.1_Doc_Protal/zh_CN/"
            "index.html")
R("R27", "4k7", R0402, "LTE_PWRKEY", "GND", S, B,
  Description="PWRKEY held low: the module starts as soon as VBAT is up "
              "(HDM 3.5.3); reset and reflash go through RESET_N")
TP("TP8", "LTE_1V8", S, B)            # HDM 2.5: leave a probe on VDD_EXT
TP("TP9", "LTE_USB_DP", S, B)         # USB 2.0 device port: AT, logs and
TP("TP10", "LTE_USB_DM", S, B)        # the emergency download from a PC
TP("TP11", "LTE_USB_VBUS", S, B)      # (HDM 4.1, fig. 4-1: 5 V straight in)
TP("TP12", "LTE_DBG_TX", S, B)
TP("TP13", "LTE_DBG_RX", S, B)

B = "NT26-KCN E supply decoupling at VBAT (HDM 3.4.2)"
# HDM 3.4.2 asks for 100 uF of low-ESR (< 0.7 R) bulk plus 100 nF, 33 pF and
# 8.2 pF at the VBAT pins.  Two 47 uF X5R MLCCs give the bulk at a few mOhm;
# they are the same part as C8/C9.
Cap("C26", "47u/10V", C1210, "+3V8", "GND", S, B)
Cap("C27", "47u/10V", C1210, "+3V8", "GND", S, B)
Cap("C28", "100n/16V", C0402, "+3V8", "GND", S, B)
Cap("C29", "33p/50V C0G", C0402, "+3V8", "GND", S, B)
Cap("C30", "8p2/50V C0G", C0402, "+3V8", "GND", S, B)

B = "TLV62569 buck  +5V -> +3V8 (LTE module VBAT)"
# HDM 3.4: VBAT 3.3-4.5 V, 3.8 V typical, 1.2 A transient at full TX power,
# never below 3.3 V.  TI SLVSDG1C: VOUT = 0.6 V x (1 + R1/R2) (eq. 2), R2
# <= 200k, 6.8 pF feed-forward for R2 = 100k, 2.2 uH with 22 uF out is the
# standard pair (table 4), 4.7 uF in is enough.  536k / 100k -> 3.816 V.
# +5V in, 3.8 V out: the part runs at 100 % duty if +5V sags (7.3.2).
C("U11", "Regulator_Switching:TLV62569DBV", "TLV62569DBV", SOT235,
  {"1": "+5V", "2": "GND", "3": "SW38", "4": "+5V", "5": "FB38"}, S, B,
  Description="2 A sync buck, EN tied to VIN: the module is powered with "
              "the board")
Cap("C23", "10u/10V", C0805, "+5V", "GND", S, B)
L("L2", "2.2uH", IND_XAL4020, "SW38", "+3V8", S, B,
  Description="2.2 uH, Isat >= 2.5 A (Coilcraft XAL4020-222, the SLVSDG1C "
              "BOM part)")
Cap("C24", "22u/10V X5R", C1206, "+3V8", "GND", S, B)
R("R25", "536k 1%", R0402, "+3V8", "FB38", S, B)
R("R26", "100k 1%", R0402, "FB38", "GND", S, B)
Cap("C25", "6p8/50V C0G", C0402, "+3V8", "FB38", S, B,
    Description="Feed-forward, SLVSDG1C 8.2.2.2")
C("#FLG05", "power:PWR_FLAG", "PWR_FLAG", "", {"1": "+3V8"}, S, B)
TP("TP7", "+3V8", S, B)

B = "UART level translation 3.3 V <-> 1.8 V"
# The module's UART is 1.8 V (VO_LDOIO) and has no back-feed protection
# (HDM 4.2 notes); UART3 on the Luckfox is 3.3 V.  SN74LVC1T45: VCC
# isolation - either supply at 0 V puts both ports in Hi-Z - so nothing
# drives the module's pins while it is off.  DIR high = A -> B.
C("U9", "Logic_LevelTranslator:SN74LVC1T45DBV", "SN74LVC1T45DBV", SOT23_6,
  {"1": "3V3_MOD", "2": "GND", "3": "LTE_TX", "4": "LTE_TX_1V8",
   "5": "3V3_MOD", "6": "LTE_1V8"}, S, B,
  Description="Luckfox UART3 TX -> NT26 MAIN_RXD")
C("U10", "Logic_LevelTranslator:SN74LVC1T45DBV", "SN74LVC1T45DBV", SOT23_6,
  {"1": "3V3_MOD", "2": "GND", "3": "LTE_RX", "4": "LTE_RX_1V8",
   "5": "GND", "6": "LTE_1V8"}, S, B,
  Description="NT26 MAIN_TXD -> Luckfox UART3 RX")
Cap("C31", "100n/16V", C0402, "3V3_MOD", "GND", S, B)
Cap("C32", "100n/16V", C0402, "LTE_1V8", "GND", S, B)
Cap("C33", "100n/16V", C0402, "3V3_MOD", "GND", S, B)
Cap("C34", "100n/16V", C0402, "LTE_1V8", "GND", S, B)
R("R28", "100k", R0402, "LTE_TX", "3V3_MOD", S, B,
  Description="UART idle while Linux has not claimed the pin")
R("R29", "100k", R0402, "LTE_RX", "3V3_MOD", S, B,
  Description="UART idle while the module is off and U10 is Hi-Z")

B = "Reset and download-mode control from the Luckfox"
# Download: LTE_BOOT high, pulse LTE_RST >= 300 ms, release; the module comes
# up in emergency download (HDM 3.5.3 / 4.1.3: USB_BOOT high at power-on or
# reset).  LTE_BOOT is module pin 20, GPIO4_C1 - a 1.8 V-only bank on the
# Luckfox (Luckfox-Pico-Mini.pdf, "SARADC/PWM (1.8V only)") - the same level
# as USB_BOOT, so it needs no translator, only a series resistor in case it
# is driven while the module is unpowered.
C("Q2", "Transistor_FET:AO3400A", "AO3400A", SOT23,
  {"1": "LTE_RST_G", "2": "GND", "3": "LTE_RESET_N"}, S, B,
  Description="Open drain on RESET_N (internal pull-up, VIL <= 0.3 V)")
R("R32", "100R", R0402, "LTE_RST", "LTE_RST_G", S, B)
R("R33", "100k", R0402, "LTE_RST_G", "GND", S, B,
  Description="Module runs while the SoC pin floats")
R("R30", "1k", R0402, "LTE_BOOT", "LTE_BOOT_M", S, B,
  Description="Limits back-feed into USB_BOOT if driven with the module off")
R("R31", "100k", R0402, "LTE_BOOT", "GND", S, B,
  Description="Normal boot unless Linux asks for download mode")

B = "Network status LED (HDM 4.7.3)"
C("Q3", "Transistor_BJT:MMBT3904", "MMBT3904", SOT23,
  {"1": "LTE_NET_B", "2": "GND", "3": "LTE_LED_K"}, S, B)
R("R34", "4k7", R0402, "LTE_NET", "LTE_NET_B", S, B)
R("R35", "47k", R0402, "LTE_NET_B", "GND", S, B)
LED("D8", "GREEN", LED0603, "LTE_LED_A", "LTE_LED_K", S, B,
    Description="Slow blink: searching / idle, fast: data (HDM table 4-8)")
R("R36", "1k", R0402, "+3V8", "LTE_LED_A", S, B,
  Description="~1.6 mA; HDM fig. 4-9 uses 2.2k from VBAT")

# ===========================================================================
# SHEET 07 -- LTE nano-SIM and antennas
# ===========================================================================
S = "07_lte_rf"

B = "Nano-SIM (HDM 4.3)"
# HDM fig. 4-7: 22 R in series, 33 pF to ground and ESD at the holder,
# <= 1 uF on USIM_VDD, 10k pull-up on DATA.
C("J15", "LFX:SIM_Card_Shield", "SIM8060-6-0-14-00", NANOSIM,
  {"1": "SIM_VDD", "2": "SIM_RST", "3": "SIM_CLK", "5": "GND", "6": "",
   "7": "SIM_DATA", "SH": "GND"}, S, B,
  Description="GCT hinged nano-SIM, no card detect; a hinged lid keeps the "
              "card in under vibration")
R("R37", "22R", R0402, "SIM_RST_M", "SIM_RST", S, B)
R("R38", "22R", R0402, "SIM_CLK_M", "SIM_CLK", S, B)
R("R39", "22R", R0402, "SIM_DATA_M", "SIM_DATA", S, B)
Cap("C35", "33p/50V C0G", C0402, "SIM_RST", "GND", S, B)
Cap("C36", "33p/50V C0G", C0402, "SIM_CLK", "GND", S, B)
Cap("C37", "33p/50V C0G", C0402, "SIM_DATA", "GND", S, B)
Cap("C38", "100n/16V", C0402, "SIM_VDD", "GND", S, B)
R("R40", "10k", R0402, "SIM_DATA", "SIM_VDD", S, B)
C("U12", "Power_Protection:TPD4E05U06DQA", "TPD4E05U06DQA", USON10,
  {"1": "SIM_VDD", "2": "SIM_DATA", "3": "GND", "4": "SIM_CLK",
   "5": "SIM_RST", "6": "", "7": "", "8": "GND", "9": "", "10": ""}, S, B,
  Description="ESD at the SIM holder, 0.5 pF (HDM asks <= 15 pF); the "
              "four channels are alike, assigned in the order the lines "
              "pass it")

B = "LTE antenna (HDM 5.3)"
# Pi match: 0 R in series, both shunts not fitted until the antenna is tuned.
C("J16", "Connector:Conn_Coaxial", "U.FL-R-SMT-1", UFL,
  {"1": "LTE_ANT_J", "2": "GND"}, S, B, Description="LTE antenna")
Cap("C39", "DNF", C0402, "LTE_ANT", "GND", S, B, dnf=True)
R("R41", "0R", R0402, "LTE_ANT", "LTE_ANT_J", S, B)
Cap("C40", "DNF", C0402, "LTE_ANT_J", "GND", S, B, dnf=True)

B = "GNSS active antenna (HDM 6.2, fig. 6-2)"
C("J17", "Connector:Conn_Coaxial", "U.FL-R-SMT-1", UFL,
  {"1": "GNSS_ANT_J", "2": "GND"}, S, B,
  Description="GNSS antenna, active 3.3 V (fed from GNSS_ANT_VCC) or "
              "passive")
Cap("C41", "DNF", C0402, "GNSS_ANT", "GND", S, B, dnf=True)
R("R42", "0R", R0402, "GNSS_ANT", "GNSS_ANT_M", S, B)
Cap("C42", "DNF", C0402, "GNSS_ANT_M", "GND", S, B, dnf=True)
Cap("C43", "33p/50V C0G", C0402, "GNSS_ANT_M", "GNSS_ANT_J", S, B,
    Description="DC block: the antenna bias stays off the module's RF pin")
Cap("C44", "1u/16V", C0402, "GNSS_VCC", "GND", S, B)
Cap("C45", "100p/50V C0G", C0402, "GNSS_VCC", "GND", S, B)
R("R43", "0R", R0402, "GNSS_VCC", "GNSS_BIAS", S, B,
  Description="Remove for a passive antenna")
L("L3", "56nH", L0402, "GNSS_BIAS", "GNSS_ANT_J", S, B,
  Description="RF choke for the antenna bias, high SRF (> 2 GHz)")


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
