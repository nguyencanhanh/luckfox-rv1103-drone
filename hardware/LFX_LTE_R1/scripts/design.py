#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LFX_LTE_R1 -- design database.

LTE Cat.1 bis + GNSS board for the LFX_FC_R1 flight controller (Luckfox Pico
Mini B, rv1103-ai-drone).  46 x 46 mm, the same four M3 holes (39 mm
pattern), stacked on the flight controller and joined to its J5 by a
straight-through JST-SH 10 cable.  All parts on the top side.

Modem: Lierda NT26-KCN E - order the GPS + BDS variant.  Every pin and value
of the modem circuit is from the Lierda NT26-KCN E hardware design manual
Rev1.0 (2025-04-27), "HDM" in the comments; that manual is written for the
BeiDou-only NT26KCNE20GNB, which shares pin-out and land pattern.

Rails
-----
    +5V         from the flight controller, J1 pins 1-2
    +3V8        TLV62569 buck, the modem's VBAT (3.3-4.5 V, 3.8 V typical,
                1.2 A bursts, HDM 3.4); In2 is one +3V8 plane
    +3V3        TLV75533 LDO: the Luckfox-side (3.3 V) half of the UART
                level translators and their pull-ups
    LTE_1V8     the modem's own VDD_EXT (1.8 V); its UART runs on it

Link to the flight controller (J1, pin n = FC J5 pin n)
    1,2 +5V   3,4 GND   5 TX (from the Luckfox UART3)   6 RX (to it)
    7 RESET (Luckfox pin 18, high = modem in reset)
    8 BOOT  (Luckfox pin 20, 1.8 V; high during reset = download mode)
    9 buzzer gate (modem GPIO1 -> FC buzzer FET)
    10 ESC current (FC J1 pin 3 -> modem ADC0)

Download from Linux: drive BOOT high, RESET high >= 300 ms, release RESET;
the modem comes up in emergency download (HDM 3.5.3, 4.1.3) and takes its
firmware over the same UART at 921600 bd (HDM 2.2).  USB test pads are the
fall-back from a PC.
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
    ("02_power",   "Link to the flight controller, 3.8 V and 3.3 V supplies"),
    ("03_modem",   "Lierda NT26-KCN E LTE Cat.1 bis + GNSS, UART translation, "
                   "reset / download"),
    ("04_rf",      "Nano-SIM and antennas (U.FL LTE + GNSS)"),
]

POWER_NETS = {
    "GND": "power:GND",
    "+5V": "power:+5V",
    "+3V3": "power:+3V3",
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
# SHEET 02 -- LINK AND POWER
# ===========================================================================
S = "02_power"

B = "Flight-controller link (JST-SH 10)"
C("J1", "Connector_Generic_MountingPin:Conn_01x10_MountingPin",
  "SM10B-SRSS-TB", jst_sh(10),
  {"1": "+5V", "2": "+5V", "3": "GND", "4": "GND", "5": "LTE_TX_X",
   "6": "LTE_RX_X", "7": "LTE_RST_X", "8": "LTE_BOOT_X", "9": "BUZ_CTRL_X",
   "10": "ESC_CUR", "MP": "GND"}, S, B,
  Description="To LFX_FC_R1 J5, straight-through. 1,2:5V 3,4:GND 5:TX in "
              "6:RX out 7:RESET 8:BOOT 9:buzzer gate out 10:ESC current in")
C("U1", "Power_Protection:TPD4E05U06DQA", "TPD4E05U06DQA", USON10,
  {"1": "LTE_TX_X", "2": "LTE_RX_X", "3": "GND", "4": "LTE_RST_X",
   "5": "LTE_BOOT_X", "6": "", "7": "", "8": "GND", "9": "", "10": ""}, S, B,
  Description="ESD at the cable connector")
R("R1", "33R", R0402, "LTE_TX_X", "LTE_TX", S, B)
R("R2", "33R", R0402, "LTE_RX", "LTE_RX_X", S, B)
R("R3", "100R", R0402, "BUZ_CTRL", "BUZ_CTRL_X", S, B,
  Description="Modem GPIO1 out to the FC buzzer FET gate")
Cap("C1", "10u/10V", C0805, "+5V", "GND", S, B,
    Description="Cable-end reservoir for the modem's TX bursts")
C("#FLG01", "power:PWR_FLAG", "PWR_FLAG", "", {"1": "+5V"}, S, B)
C("#FLG02", "power:PWR_FLAG", "PWR_FLAG", "", {"1": "GND"}, S, B)

B = "TLV62569 buck  +5V -> +3V8 (modem VBAT)"
# HDM 3.4: VBAT 3.3-4.5 V, 3.8 V typical, 1.2 A transient at full TX power,
# never below 3.3 V.  TI SLVSDG1C: VOUT = 0.6 V x (1 + R1/R2) (eq. 2), R2
# <= 200k, 6.8 pF feed-forward for R2 = 100k, 2.2 uH with 22 uF out is the
# standard pair (table 4), 4.7 uF in is enough.  536k / 100k -> 3.816 V.
# Not straight from the battery: the flight controller runs on 2S-6S
# (6.6-25.2 V) and VBAT is 4.5 V max, 5.0 V absolute (HDM 7.1).
C("U2", "Regulator_Switching:TLV62569DBV", "TLV62569DBV", SOT235,
  {"1": "+5V", "2": "GND", "3": "SW38", "4": "+5V", "5": "FB38"}, S, B,
  Description="2 A sync buck, EN tied to VIN: the modem is powered with "
              "the board")
Cap("C2", "10u/10V", C0805, "+5V", "GND", S, B)
L("L1", "2.2uH", IND_XAL4020, "SW38", "+3V8", S, B,
  Description="2.2 uH, Isat >= 2.5 A (Coilcraft XAL4020-222, the SLVSDG1C "
              "BOM part)")
Cap("C3", "22u/10V X5R", C1206, "+3V8", "GND", S, B)
R("R4", "536k 1%", R0402, "+3V8", "FB38", S, B)
R("R5", "100k 1%", R0402, "FB38", "GND", S, B)
Cap("C4", "6p8/50V C0G", C0402, "+3V8", "FB38", S, B,
    Description="Feed-forward, SLVSDG1C 8.2.2.2")
C("#FLG03", "power:PWR_FLAG", "PWR_FLAG", "", {"1": "+3V8"}, S, B)
TP("TP1", "+3V8", S, B)

B = "Modem supply decoupling at VBAT (HDM 3.4.2)"
# HDM 3.4.2 asks for 100 uF of low-ESR (< 0.7 R) bulk plus 100 nF, 33 pF and
# 8.2 pF at the VBAT pins.  Two 47 uF X5R MLCCs give the bulk at a few mOhm.
Cap("C5", "47u/10V", C1210, "+3V8", "GND", S, B)
Cap("C6", "47u/10V", C1210, "+3V8", "GND", S, B)
Cap("C7", "100n/16V", C0402, "+3V8", "GND", S, B)
Cap("C8", "33p/50V C0G", C0402, "+3V8", "GND", S, B)
Cap("C9", "8p2/50V C0G", C0402, "+3V8", "GND", S, B)

B = "TLV75533 LDO  +5V -> +3V3 (translator A side)"
C("U3", "Regulator_Linear:TLV75533PDBV", "TLV75533PDBV", SOT235,
  {"1": "+5V", "2": "GND", "3": "+5V", "4": "", "5": "+3V3"}, S, B)
Cap("C10", "1u/16V", C0603, "+5V", "GND", S, B)
Cap("C11", "1u/16V", C0603, "+3V3", "GND", S, B)

B = "ESC current sense -> modem ADC0 (0-1.05 V)"
# HDM 4.6: ADC0 reads 0-1.05 V directly; divider resistors <= 100k.
# 3.3 V ESC current output x 6k8 / 21k8 = 1.03 V.
R("R6", "15k 1%", R0603, "ESC_CUR", "ADC_CUR", S, B)
R("R7", "6k8 1%", R0603, "ADC_CUR", "GND", S, B,
  Description="Ratio 0.312: 3.3 V ESC current output -> 1.03 V")
Cap("C12", "100n/16V", C0402, "ADC_CUR", "GND", S, B)

# ===========================================================================
# SHEET 03 -- MODEM
# ===========================================================================
S = "03_modem"

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
    "9": "ADC_CUR", "96": "",            # ADC0 0-1.05 V direct, ADC1
    "16": "LTE_NET", "25": "",           # NET_STATUS, STATUS
    "50": "BUZ_CTRL",                    # GPIO1 drives the FC buzzer FET
    "51": "", "52": "", "53": "",        # GPIO4/5 belong to the GNSS
    "97": "", "107": "", "99": "", "101": "",   # AGPIO5 x2, AGPIO6, AGPIO3
})
C("U4", "LFX:NT26-KCN", "NT26-KCN E (GPS+BDS)", NT26_FP, nt26, S, B,
  Description="Lierda NT26-KCN E LTE Cat.1 bis (B1/3/5/8/34/38/39/40/41) "
              "+ GNSS, LCC+LGA 109, 17.7 x 15.8 x 2.4 mm. Order the GPS+BDS "
              "variant",
  Datasheet="https://opendocs.lierda.com/docs/CAT.1_Doc_Protal/zh_CN/"
            "index.html")
R("R8", "4k7", R0402, "LTE_PWRKEY", "GND", S, B,
  Description="PWRKEY held low: the modem starts as soon as VBAT is up "
              "(HDM 3.5.3); reset and reflash go through RESET_N")
TP("TP2", "LTE_1V8", S, B)            # HDM 2.5: leave a probe on VDD_EXT
TP("TP3", "LTE_USB_DP", S, B)         # USB 2.0 device port: AT, logs and
TP("TP4", "LTE_USB_DM", S, B)         # the emergency download from a PC
TP("TP5", "LTE_USB_VBUS", S, B)       # (HDM 4.1, fig. 4-1: 5 V straight in)
TP("TP6", "LTE_DBG_TX", S, B)
TP("TP7", "LTE_DBG_RX", S, B)

B = "UART level translation 3.3 V <-> 1.8 V"
# The modem's UART is 1.8 V (VO_LDOIO) and has no back-feed protection
# (HDM 4.2 notes); the Luckfox UART3 is 3.3 V.  SN74LVC1T45: VCC isolation -
# either supply at 0 V puts both ports in Hi-Z - so nothing drives the
# modem's pins while it is off (VDD_EXT also drops in modem sleep: do not
# enable AT+QSCLK sleep, the UART cannot wake it through this path).
# DIR high = A -> B.
C("U5", "Logic_LevelTranslator:SN74LVC1T45DBV", "SN74LVC1T45DBV", SOT23_6,
  {"1": "+3V3", "2": "GND", "3": "LTE_TX", "4": "LTE_TX_1V8",
   "5": "+3V3", "6": "LTE_1V8"}, S, B,
  Description="Luckfox UART3 TX -> modem MAIN_RXD")
C("U6", "Logic_LevelTranslator:SN74LVC1T45DBV", "SN74LVC1T45DBV", SOT23_6,
  {"1": "+3V3", "2": "GND", "3": "LTE_RX", "4": "LTE_RX_1V8",
   "5": "GND", "6": "LTE_1V8"}, S, B,
  Description="Modem MAIN_TXD -> Luckfox UART3 RX")
Cap("C13", "100n/16V", C0402, "+3V3", "GND", S, B)
Cap("C14", "100n/16V", C0402, "LTE_1V8", "GND", S, B)
Cap("C15", "100n/16V", C0402, "+3V3", "GND", S, B)
Cap("C16", "100n/16V", C0402, "LTE_1V8", "GND", S, B)
R("R9", "100k", R0402, "LTE_TX", "+3V3", S, B,
  Description="UART idle while the cable is out or Linux has not claimed "
              "the pin")
R("R10", "100k", R0402, "LTE_RX", "+3V3", S, B,
  Description="UART idle while the modem is off and U6 is Hi-Z")

B = "Reset and download-mode control from the Luckfox"
# Download: BOOT high, RESET >= 300 ms, release; the modem comes up in
# emergency download (HDM 3.5.3 / 4.1.3: USB_BOOT high at power-on or reset).
# BOOT is Luckfox pin 20, GPIO4_C1 - a 1.8 V-only bank (Luckfox-Pico-Mini.pdf,
# "SARADC/PWM (1.8V only)") - the same level as USB_BOOT: a series resistor,
# no translator.
C("Q1", "Transistor_FET:AO3400A", "AO3400A", SOT23,
  {"1": "LTE_RST_G", "2": "GND", "3": "LTE_RESET_N"}, S, B,
  Description="Open drain on RESET_N (internal pull-up, VIL <= 0.3 V)")
R("R11", "100R", R0402, "LTE_RST_X", "LTE_RST_G", S, B)
R("R12", "100k", R0402, "LTE_RST_G", "GND", S, B,
  Description="Modem runs while the cable is out or the SoC pin floats")
R("R13", "1k", R0402, "LTE_BOOT_X", "LTE_BOOT_M", S, B,
  Description="Limits back-feed into USB_BOOT if driven with the modem off")
R("R14", "100k", R0402, "LTE_BOOT_X", "GND", S, B,
  Description="Normal boot unless Linux asks for download mode")

B = "Network status LED (HDM 4.7.3)"
C("Q2", "Transistor_BJT:MMBT3904", "MMBT3904", SOT23,
  {"1": "LTE_NET_B", "2": "GND", "3": "LTE_LED_K"}, S, B)
R("R15", "4k7", R0402, "LTE_NET", "LTE_NET_B", S, B)
R("R16", "47k", R0402, "LTE_NET_B", "GND", S, B)
LED("D1", "GREEN", LED0603, "LTE_LED_A", "LTE_LED_K", S, B,
    Description="Slow blink: searching / idle, fast: data (HDM table 4-8)")
R("R17", "1k", R0402, "+3V8", "LTE_LED_A", S, B,
  Description="~1.6 mA; HDM fig. 4-9 uses 2.2k from VBAT")

# ===========================================================================
# SHEET 04 -- SIM AND ANTENNAS
# ===========================================================================
S = "04_rf"

B = "Nano-SIM (HDM 4.3)"
# HDM fig. 4-7: 22 R in series, 33 pF to ground and ESD at the holder,
# <= 1 uF on USIM_VDD, 10k pull-up on DATA.
C("J2", "LFX:SIM_Card_Shield", "SIM8060-6-0-14-00", NANOSIM,
  {"1": "SIM_VDD", "2": "SIM_RST", "3": "SIM_CLK", "5": "GND", "6": "",
   "7": "SIM_DATA", "SH": "GND"}, S, B,
  Description="GCT hinged nano-SIM, no card detect; the hinged lid keeps "
              "the card in under vibration")
R("R18", "22R", R0402, "SIM_RST_M", "SIM_RST", S, B)
R("R19", "22R", R0402, "SIM_CLK_M", "SIM_CLK", S, B)
R("R20", "22R", R0402, "SIM_DATA_M", "SIM_DATA", S, B)
Cap("C17", "33p/50V C0G", C0402, "SIM_RST", "GND", S, B)
Cap("C18", "33p/50V C0G", C0402, "SIM_CLK", "GND", S, B)
Cap("C19", "33p/50V C0G", C0402, "SIM_DATA", "GND", S, B)
Cap("C20", "100n/16V", C0402, "SIM_VDD", "GND", S, B)
R("R21", "10k", R0402, "SIM_DATA", "SIM_VDD", S, B)
C("U7", "Power_Protection:TPD4E05U06DQA", "TPD4E05U06DQA", USON10,
  {"1": "SIM_DATA", "2": "SIM_CLK", "3": "GND", "4": "SIM_RST",
   "5": "SIM_VDD", "6": "", "7": "", "8": "GND", "9": "", "10": ""}, S, B,
  Description="ESD at the SIM holder, 0.5 pF (HDM asks <= 15 pF)")

B = "LTE antenna (HDM 5.3)"
# Pi match: 0 R in series, both shunts not fitted until the antenna is tuned.
C("J3", "Connector:Conn_Coaxial", "U.FL-R-SMT-1", UFL,
  {"1": "LTE_ANT_J", "2": "GND"}, S, B, Description="LTE antenna")
Cap("C21", "DNF", C0402, "LTE_ANT", "GND", S, B, dnf=True)
R("R22", "0R", R0402, "LTE_ANT", "LTE_ANT_J", S, B)
Cap("C22", "DNF", C0402, "LTE_ANT_J", "GND", S, B, dnf=True)

B = "GNSS active antenna (HDM 6.2, fig. 6-2)"
C("J4", "Connector:Conn_Coaxial", "U.FL-R-SMT-1", UFL,
  {"1": "GNSS_ANT_J", "2": "GND"}, S, B,
  Description="GNSS antenna, active 3.3 V (fed from GNSS_ANT_VCC) or "
              "passive")
Cap("C23", "DNF", C0402, "GNSS_ANT", "GND", S, B, dnf=True)
R("R23", "0R", R0402, "GNSS_ANT", "GNSS_ANT_M", S, B)
Cap("C24", "DNF", C0402, "GNSS_ANT_M", "GND", S, B, dnf=True)
Cap("C25", "33p/50V C0G", C0402, "GNSS_ANT_M", "GNSS_ANT_J", S, B,
    Description="DC block: the antenna bias stays off the modem's RF pin")
Cap("C26", "1u/16V", C0402, "GNSS_VCC", "GND", S, B)
Cap("C27", "100p/50V C0G", C0402, "GNSS_VCC", "GND", S, B)
R("R24", "0R", R0402, "GNSS_VCC", "GNSS_BIAS", S, B,
  Description="Remove for a passive antenna")
L("L2", "56nH", L0402, "GNSS_BIAS", "GNSS_ANT_J", S, B,
  Description="RF choke for the antenna bias, high SRF (> 2 GHz)")

B = "Mounting"
for i in range(1, 5):
    C("H%d" % i, "Mechanical:MountingHole", "M3",
      "MountingHole:MountingHole_3.2mm_M3", {}, S, B)


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
