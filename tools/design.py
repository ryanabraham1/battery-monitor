"""Single source of truth for the FRC battery IR node: parts, pin->net map, BOM data.
Both the schematic generator (gen_sch.py) and the PCB generator (gen_pcb.py) read this.
"""
PROJECT = "ir_node"

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
C1206 = "Capacitor_SMD:C_1206_3216Metric"
M4PAD = "MountingHole:MountingHole_4.3mm_M4_Pad_Via"
M5PAD = "MountingHole:MountingHole_5.3mm_M5_Pad_Via"
TPAD = "TestPoint:TestPoint_THTPad_D2.0mm_Drill1.0mm"

NC = None  # explicit no-connect

# assembly: "smt" = JLC SMT assembled, "tht" = hand-solder / THT, "none" = not a purchased part
PARTS = []


def P(ref, sym, value, fp, pins, block, lcsc="", mpn="", asm="smt", price=0.0, note=""):
    PARTS.append(dict(ref=ref, sym=sym, value=value, fp=fp, pins=pins, block=block,
                      lcsc=lcsc, mpn=mpn, asm=asm, price=price, note=note))


def R(ref, value, a, b, block, lcsc, price=0.002, mpn=""):
    P(ref, "Device:R", value, R0603, {"1": a, "2": b}, block, lcsc, mpn, price=price)


def C(ref, value, a, b, block, lcsc, fp=C0603, price=0.01, mpn=""):
    P(ref, "Device:C", value, fp, {"1": a, "2": b}, block, lcsc, mpn, price=price)


# ------------------------------------------------------------------ POWER PATH
B = "1 High-current path: battery / bolt-down fuse / shunt / charger relay / 120 A pulse load"
P("J1", "Mechanical:MountingHole_Pad", "BATT+ lug + MIDI fuse end A (M5 stud)", M5PAD, {"1": "VBAT_RAW"}, B, asm="none")
P("J14", "Mechanical:MountingHole_Pad", "MIDI fuse end B (M5 stud)", M5PAD, {"1": "VBAT_F"}, B, asm="none")
P("J2", "Mechanical:MountingHole_Pad", "BATT- (M4 lug)", M4PAD, {"1": "GND"}, B, asm="none")
P("J3", "Mechanical:MountingHole_Pad", "CHG+ (M4 lug)", M4PAD, {"1": "CHG_P"}, B, asm="none")
P("J4", "Mechanical:MountingHole_Pad", "CHG- (M4 lug)", M4PAD, {"1": "GND"}, B, asm="none")
P("J5", "Mechanical:MountingHole_Pad", "LOAD+ (M4 lug)", M4PAD, {"1": "VNODE"}, B, asm="none")
P("J6", "Mechanical:MountingHole_Pad", "LOAD- (M4 lug)", M4PAD, {"1": "LOAD_N"}, B, asm="none")
P("F1", "Device:Fuse", "10A 125V 2410 (charger branch)", "Fuse:Fuse_Littelfuse-NANO2-451_453",
  {"1": "CHG_K", "2": "CHG_P"}, B, "C136391", "JDT JFC2410-2100TS", price=0.081)
P("R1", "Device:R", "0.5mR 1% 3W 75ppm", "Resistor_SMD:R_2512_6332Metric",
  {"1": "VBAT_F", "2": "VNODE"}, B, "C710260", "TA-I RLM25FEGMR50M", price=0.073)
P("D3", "Device:D_TVS", "SMBJ20A", "Diode_SMD:D_SMB", {"1": "VBAT_F", "2": "GND"}, B,
  "C151922", "BORN SMBJ20A", price=0.069)
P("K1", "Relay:G2RL-1-E", "G2RL-1-E-DC12", "Relay_THT:Relay_SPDT_Omron_G2RL-1-E",
  {"11": "VNODE", "12": "CHG_K", "14": NC, "A1": "VIN_PROT", "A2": "RLY_N"}, B,
  "C58243", "Omron G2RL-1-E-DC12", "tht", 1.90)
P("D1", "Device:D", "1N4148W", "Diode_SMD:D_SOD-123", {"1": "VIN_PROT", "2": "RLY_N"}, B,
  "C81598", "1N4148W", price=0.012)
P("Q2", "Transistor_FET:AO3400A", "AO3400A", "Package_TO_SOT_SMD:SOT-23",
  {"1": "RELAY_EN", "2": "GND", "3": "RLY_N"}, B, "C20917", "AOS AO3400A", price=0.079)
R("R3", "10k", "RELAY_EN", "GND", B, "C25804")
P("Q1", "Transistor_FET:IRLB8721PBF", "IRLB3034PBF", "Package_TO_SOT_THT:TO-220-3_Vertical",
  {"1": "GATE", "2": "LOAD_N", "3": "GND"}, B, "C144151", "Infineon IRLB3034PBF", "tht", 1.02)
P("D2", "Device:D_Schottky", "SS56C", "Diode_SMD:D_SMC", {"1": "VNODE", "2": "LOAD_N"}, B,
  "C24138", "MDD SS56C", price=0.095)
P("C18", "Device:C_Polarized", "100u 35V", "Capacitor_SMD:CP_Elec_6.3x7.7", {"1": "VNODE", "2": "GND"}, B,
  "C2836442", "KNSCHA RVT100UF35V67RV0034", price=0.038)

# ------------------------------------------------------------------ MEASUREMENT
B = "2 Measurement: INA226/INA228 (pin-compatible), Kelvin shunt + bus sense"
P("U2", "Sensor_Energy:INA226", "INA226AIDGSR (INA228 drop-in)", "Package_SO:VSSOP-10_3x3mm_P0.5mm",
  {"1": "GND", "2": "GND", "3": "INA_ALERT", "4": "I2C0_SDA", "5": "I2C0_SCL", "6": "+3V3",
   "7": "GND", "8": "INA_VBUS", "9": "INA_INN", "10": "INA_INP"}, B,
  "C49851", "TI INA226AIDGSR", price=0.67)
R("R4", "4R7", "VBAT_F", "INA_INP", B, "C23164", 0.004)
R("R5", "4R7", "VNODE", "INA_INN", B, "C23164", 0.004)
C("C1", "100n", "INA_INP", "INA_INN", B, "C14663")
R("R6", "10R", "VBAT_RAW", "INA_VBUS", B, "C22859")
C("C2", "100n", "INA_VBUS", "GND", B, "C14663")
C("C3", "100n", "+3V3", "GND", B, "C14663")
R("R7", "4k7", "+3V3", "I2C0_SDA", B, "C23162")
R("R8", "4k7", "+3V3", "I2C0_SCL", B, "C23162")
R("R9", "10k", "+3V3", "INA_ALERT", B, "C25804")

# ------------------------------------------------------------------ LOGIC SUPPLY
B = "3 Logic supply: reverse-polarity diode, 3V3 buck, gate-drive rail"
P("D4", "Device:D_Schottky", "SS34", "Diode_SMD:D_SMA", {"1": "VIN_PROT", "2": "VNODE"}, B,
  "C8678", "MDD SS34", price=0.035)
P("D5", "Device:D_Schottky", "B5819W", "Diode_SMD:D_SOD-123", {"1": "VIN_PROT", "2": "VBUS_USB"}, B,
  "C8598", "B5819W", price=0.026)
C("C4", "10u 50V", "VIN_PROT", "GND", B, "C13585", C1206, 0.121)
C("C5", "10u 50V", "VIN_PROT", "GND", B, "C13585", C1206, 0.121)
P("U4", "Regulator_Switching:AP63203WU", "AP63203WU-7", "Package_TO_SOT_SMD:TSOT-23-6",
  {"1": "+3V3", "2": "VIN_PROT", "3": "VIN_PROT", "4": "GND", "5": "BUCK_SW", "6": "BUCK_BST"}, B,
  "C780769", "Diodes AP63203WU-7", price=1.34)
C("C6", "100n", "BUCK_BST", "BUCK_SW", B, "C14663")
P("L1", "Device:L", "4.7uH 2A", "Inductor_SMD:L_Sunlord_SWPA4030S", {"1": "BUCK_SW", "2": "+3V3"}, B,
  "C57269", "Sunlord SWPA4030S4R7MT", price=0.057)
C("C7", "22u 25V", "+3V3", "GND", B, "C45783", C0805, 0.108)
C("C8", "22u 25V", "+3V3", "GND", B, "C45783", C0805, 0.108)
R("R10", "470R", "VIN_PROT", "VDRV_IN", B, "C23179")
P("R11", "Device:R", "DNP (thermostat bypass, bench use only)", R0603, {"1": "VDRV_IN", "2": "VDRV"}, B, asm="none")
P("J13", "Connector_Generic:Conn_01x02", "TSW: NC thermostat on the load resistor (required)",
  "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical", {"1": "VDRV_IN", "2": "VDRV"}, B,
  "C20079", "XH-2A", "tht", 0.007)
P("D6", "Device:D_Zener", "BZT52C12", "Diode_SMD:D_SOD-123", {"1": "VDRV", "2": "GND"}, B,
  "C43491", "BZT52C12", price=0.021)
C("C9", "1u 50V", "VDRV", "GND", B, "C15849")

# ------------------------------------------------------------------ PULSE LOAD DRIVE
B = "4 Pulse-load gate drive with hardware one-shot timeout (~220 ms)"
P("U5", "74xGxx:74LVC1G123", "SN74LVC1G123DCTR", "Package_SO:SSOP-8_2.95x2.8mm_P0.65mm",
  {"1": "GND", "2": "LOAD_EN", "3": "LOAD_EN", "4": "GND", "5": "LOAD_PULSE", "6": "GND",
   "7": "OS_RC", "8": "+3V3"}, B, "C123302", "TI SN74LVC1G123DCTR", price=1.01)
R("R14", "100k", "+3V3", "OS_RC", B, "C25803")
C("C10", "2u2 16V", "OS_RC", "GND", B, "C23630")
C("C11", "100n", "+3V3", "GND", B, "C14663")
R("R15", "10k", "LOAD_EN", "GND", B, "C25804")
R("R16", "1k", "LOAD_PULSE", "LOAD_FB", B, "C21190")
P("U6", "IRNode:UCC27517DBV", "UCC27517DBVR", "Package_TO_SOT_SMD:SOT-23-5",
  {"1": "VDRV", "2": "GND", "3": "LOAD_PULSE", "4": "GND", "5": "DRV_OUT"}, B,
  "C99395", "TI UCC27517DBVR", price=0.30)
R("R12", "470R", "DRV_OUT", "GATE", B, "C23179")
R("R13", "10k", "GATE", "GND", B, "C25804")

# ------------------------------------------------------------------ MCU
B = "5 MCU: ESP32-S3-WROOM-1 (radio unused), USB-C, buttons, LED, MOSFET NTC"
P("U1", "RF_Module:ESP32-S3-WROOM-1", "ESP32-S3-WROOM-1-N4", "RF_Module:ESP32-S3-WROOM-1",
  {"1": "GND", "40": "GND", "41": "GND", "2": "+3V3", "3": "ESP_EN",
   "4": "CAN_TX", "5": "CAN_RX", "6": "LOAD_EN", "7": "LOAD_FB", "8": "RELAY_EN",
   "9": "LED_R", "10": "LED_G", "11": "LED_B", "12": "I2C0_SDA", "13": "USB_DM", "14": "USB_DP",
   "15": NC, "16": NC, "17": "I2C0_SCL", "18": "INA_ALERT", "19": "NFC_SDA", "20": "NFC_SCL",
   "21": "NFC_IRQ", "22": "NFC_RST", "23": NC, "24": NC, "25": NC, "26": NC, "27": "BOOT",
   "28": NC, "29": NC, "30": NC, "31": NC, "32": NC, "33": NC, "34": NC, "35": NC,
   "36": "UART_RX", "37": "UART_TX", "38": "NTC_FET", "39": NC}, B,
  "C2913197", "Espressif ESP32-S3-WROOM-1-N4", price=4.26)
C("C13", "22u 25V", "+3V3", "GND", B, "C45783", C0805, 0.108)
C("C14", "100n", "+3V3", "GND", B, "C14663")
R("R17", "10k", "+3V3", "ESP_EN", B, "C25804")
C("C12", "1u 50V", "ESP_EN", "GND", B, "C15849")
P("SW1", "Switch:SW_Push", "RESET", "Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A",
  {"1": "ESP_EN", "2": "GND"}, B, "C318884", "XKB TS-1187A-B-A-B", price=0.022)
P("SW2", "Switch:SW_Push", "BOOT", "Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A",
  {"1": "BOOT", "2": "GND"}, B, "C318884", "XKB TS-1187A-B-A-B", price=0.022)
P("J7", "Connector_Generic:Conn_01x03", "UART0 debug", "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
  {"1": "UART_TX", "2": "UART_RX", "3": "GND"}, B, "", "2.54mm header 1x3", "tht", 0.02)
P("J8", "Connector:USB_C_Receptacle_USB2.0_16P", "USB-C", "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
  {"A1": "GND", "A12": "GND", "B1": "GND", "B12": "GND", "S1": "GND",
   "A4": "VBUS_USB", "A9": "VBUS_USB", "B4": "VBUS_USB", "B9": "VBUS_USB",
   "A5": "USB_CC1", "B5": "USB_CC2", "A6": "USB_DP", "B6": "USB_DP", "A7": "USB_DM", "B7": "USB_DM",
   "A8": NC, "B8": NC}, B, "C165948", "HRO TYPE-C-31-M-12", price=0.187)
R("R18", "5k1", "USB_CC1", "GND", B, "C23186")
R("R19", "5k1", "USB_CC2", "GND", B, "C23186")
P("U7", "Power_Protection:USBLC6-2SC6", "USBLC6-2SC6", "Package_TO_SOT_SMD:SOT-23-6",
  {"1": "USB_DP", "6": "USB_DP", "3": "USB_DM", "4": "USB_DM", "2": "GND", "5": "VBUS_USB"}, B,
  "C7519", "ST USBLC6-2SC6", price=0.157)
LED0603 = "LED_SMD:LED_0603_1608Metric"
P("D8", "Device:LED", "RED", LED0603, {"1": "LEDK_R", "2": "+3V3"}, B, "C2286", "KENTO KT-0603R", price=0.008)
P("D9", "Device:LED", "GREEN", LED0603, {"1": "LEDK_G", "2": "+3V3"}, B, "C12624", "KENTO KT-0603G", price=0.012)
P("D10", "Device:LED", "BLUE", LED0603, {"1": "LEDK_B", "2": "+3V3"}, B, "C2288", "KENTO KT-0603B", price=0.011)
R("R25", "470R", "LEDK_R", "LED_R", B, "C23179")
R("R26", "100R", "LEDK_G", "LED_G", B, "C22775")
R("R27", "100R", "LEDK_B", "LED_B", B, "C22775")
P("TH1", "Device:Thermistor_NTC", "10k B3950 1%", R0603, {"1": "NTC_FET", "2": "GND"}, B,
  "C2892547", "KUU KNTC0603/10KF3950", price=0.03)
R("R24", "10k", "+3V3", "NTC_FET", B, "C25804")
C("C17", "100n", "NTC_FET", "GND", B, "C14663")

# ------------------------------------------------------------------ CAN + NFC
B = "6 CAN bus (2x RJ45 daisy-chain, CiA-303 pinout, jumper termination) + optional NFC header"
P("U3", "Interface_CAN_LIN:SN65HVD230", "SN65HVD230DR", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
  {"1": "CAN_TX", "2": "GND", "3": "+3V3", "4": "CAN_RX", "5": NC, "6": "CANL", "7": "CANH", "8": "GND"}, B,
  "C12084", "TI SN65HVD230DR", price=0.56)
C("C15", "100n", "+3V3", "GND", B, "C14663")
P("D7", "IRNode:PESD2CAN", "PESD2CAN", "Package_TO_SOT_SMD:SOT-23",
  {"1": "CANH", "2": "CANL", "3": "GND"}, B, "C2687131", "UMW PESD2CAN", price=0.037)
R("R20", "120R", "CANH", "CAN_TERM", B, "C22787")
P("JP1", "Connector_Generic:Conn_01x02", "TERM jumper", "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
  {"1": "CAN_TERM", "2": "CANL"}, B, "", "2.54mm header 1x2 + jumper cap", "tht", 0.02)
RJ = {"1": "CANH", "2": "CANL", "3": "GND", "4": NC, "5": NC, "6": NC, "7": "GND", "8": NC,
      "9": NC, "10": NC, "11": NC, "12": NC, "SH": "GND"}
P("J9", "Connector:RJ45_LED_Shielded", "CAN A", "Connector_RJ:RJ45_Connfly_DS1128-09-S8xx-S_Horizontal",
  dict(RJ), B, "C86578", "Connfly DS1128-09-S8B8X", "tht", 0.57)
P("J10", "Connector:RJ45_LED_Shielded", "CAN B", "Connector_RJ:RJ45_Connfly_DS1128-09-S8xx-S_Horizontal",
  dict(RJ), B, "C86578", "Connfly DS1128-09-S8B8X", "tht", 0.57)
P("J11", "Connector_Generic:Conn_01x06", "optional: PN532 NFC reader (I2C)", "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical",
  {"1": "+3V3", "2": "GND", "3": "NFC_SDA", "4": "NFC_SCL", "5": "NFC_IRQ", "6": "NFC_RST"}, B,
  "", "2.54mm header 1x6 (optional)", "tht", 0.03)
R("R21", "4k7", "+3V3", "NFC_SDA", B, "C23162")
R("R22", "4k7", "+3V3", "NFC_SCL", B, "C23162")

# ------------------------------------------------------------------ TEST POINTS / MECH
B = "7 Test points and mounting"
for i, net in enumerate(["VBAT_RAW", "INA_INP", "INA_INN", "GATE", "+3V3", "CANH", "CANL", "GND", "LOAD_PULSE"], 1):
    P("TP%d" % i, "Connector:TestPoint", net, TPAD, {"1": net}, B, asm="none")
for i in range(1, 5):
    P("H%d" % i, "Mechanical:MountingHole", "M3", "MountingHole:MountingHole_3.2mm_M3", {}, B, asm="none")

POWER_FLAG_NETS = ["GND", "+3V3", "VIN_PROT", "VDRV"]

# nets carried by copper pours, excluded from autorouting
HC_NETS = ["VBAT_RAW", "VBAT_F", "VNODE", "CHG_K", "CHG_P", "LOAD_N", "GND"]

NOTES = {
    "1": "REV B, 120 A PULSE. BATT+ ring terminal and one end of a bolt-down MIDI fuse (60 A, off-board part) "
         "share stud J1; the other fuse end bolts to J14. J14 -> R1 0.5 mOhm shunt -> VNODE. Q1 switches the "
         "off-board ~0.1 Ohm load (LOAD+/LOAD-) right next to the BATT- lug. D2 freewheels the load leads, C18 and "
         "D3 absorb battery-lead inductance at turn-off. Charger joins VNODE through K1 normally-closed contact "
         "and its own 10 A fuse F1, so an unpowered node leaves the charger CONNECTED.",
    "2": "U2 senses the shunt Kelvin-style (R4/R5/C1 filter). VBUS is taken from the BATT+ lug itself (ahead of "
         "the fuse) through R6. Address 0x40. INA228AIDGSR is a pin-compatible drop-in when back in stock.",
    "3": "D4 = reverse-polarity protection for logic. D5 lets USB power the MCU on the bench. U4 fixed 3.3 V "
         "buck, 3.8-32 V in. VDRV = zener-clamped 12 V rail for the gate driver. A normally-closed thermostat on the load resistor plugs into J13 and "
         "breaks that rail when hot, so no pulse can fire. R11 (not fitted) bypasses it for bench work.",
    "4": "LOAD_EN (GPIO6, pulled low) drives B and /CLR of the one-shot: Q follows LOAD_EN but is forced low "
         "after t = R14*C10 ~ 220 ms even if firmware hangs with the pin high. U6 UVLO + R13 keep Q1 off at boot. "
         "R12 = 470 R slows the gate so 120 A is switched over ~10 us instead of <1 us.",
    "5": "Native USB (GPIO19/20) for flashing + serial CLI. On-board MOSFET NTC divider 10k/10k to ADC1 (GPIO2). "
         "Status LEDs (red, green, blue 0603) are active-low. Wi-Fi/BLE are never initialised in firmware.",
    "6": "RJ45 pin 1 = CAN_H, 2 = CAN_L, 3 & 7 = GND (CiA 303-1). Both jacks are paralleled for daisy-chain. "
         "Fit JP1 on the two end nodes only. J11 takes an optional PN532 NFC reader (3V3, I2C1, IRQ, RST).",
    "7": "Test points per spec; four M3 mounting holes.",
}
