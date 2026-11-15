# FRC Battery IR Monitor Node — design document (rev A)

Inline node: charger → [node] → battery. Identifies the battery by NFC, measures internal
resistance with a 12 A / 100 ms pulse, reports over CAN. Scope of this revision: hardware only
(schematic, BOM, layout, fab files). Firmware and bring-up were dropped from scope on request.

All stock figures were read live from JLCPCB's parts library on 2026-11-14 (`tools/jlc.py`).

## 1. Deviations from the brief (read these first)

| # | Brief said | What is built | Why |
|---|---|---|---|
| 1 | TI INA228 | **INA226AIDGSR fitted**, INA228AIDGSR is a drop-in on the same footprint | INA228 stock is **0 at both JLCPCB and LCSC** today. KiCad's own INA228 symbol is derived from INA226 (same VSSOP-10 pinout). INA226 still meets ±0.5 mΩ — see §5. |
| 2 | Relay ≥ 30 A automotive | **Omron G2RL-1-E-DC12, 16 A SPDT** | Charger path carries 6 A (≤ 10 A pass-through). 16 A is ample, the part is in stock (900), and KiCad ships the exact Omron footprint. The fuse is sized to protect it (next row). |
| 3 | 30 A blade fuse | 30 A-rated **holder**, fit a **15 A ATO fuse** | Littelfuse FLR holder is rated 22.5 A continuous / 30 A max fuse. Nothing in the node needs more than 12.5 A; a 15 A fuse protects the 16 A relay contacts and the copper. |
| 4 | SMBJ18A | **SMBJ20A** (same SMB footprint) | "Survive 20 V" conflicts with SMBJ18A, whose breakdown starts at 20.0 V. SMBJ20A: standoff 20 V, clamp 32.4 V; the buck is rated 32 V. |
| 5 | Prefer JLC "basic" parts | 22 of 42 distinct LCSC parts are basic | The ICs, connectors and relay only exist as extended parts. 14 of the 20 extended parts are SMT (each adds a one-off JLC feeder fee); the other 6 are hand-soldered through-hole. |
| 6 | IPC-2152 calc | IPC-2221B closed-form used | IPC-2152 is chart-based with no formula; 2221B is the conservative of the two for boards with adjacent pours. |

## 2. Block diagram

```
 BATT+ lug ──F1 15A──R1 1mΩ shunt──┬────────────── K1 (NC contact) ── CHG+ lug
   │              │  │             │ VNODE
   │ VBUS sense   └──┴─ INA226     ├── LOAD+ lug ─[1Ω 100W off-board]─ LOAD- lug ── Q1 ── GND
   └────────────────────┘ (I2C0)   ├── D4 ── VIN_PROT ── buck U4 ── 3V3
                                   │              ├── K1 coil ── Q2 ── GND
 BATT- lug ── GND ── CHG- lug      │              └── 470Ω ── 12V zener ── VDRV (gate driver)
                                   D3 TVS (behind fuse)

 ESP32-S3 ── LOAD_EN ── U5 one-shot (220 ms max) ── U6 gate driver ── Q1 gate
          ── RELAY_EN ── Q2            ── CAN TX/RX ── SN65HVD230 ── 2x RJ45 (daisy-chain)
          ── I2C1 + IRQ/RST ── PN532 header        ── USB-C (native USB serial / flashing)
          ── ADC ── on-board NTC next to Q1                              ── 3 status LEDs
```

## 3. Part selection

| Block | Part | LCSC | Stock | Reasoning |
|---|---|---|---|---|
| MCU | ESP32-S3-WROOM-1-N4 | C2913198 | 6 942 | As specified. Built-in TWAI (CAN) and native USB, so no USB-UART bridge. Radio is simply never initialised. |
| CAN | SN65HVD230DR | C12084 | 167 518 | 3.3 V transceiver named in the brief; JLC "preferred" part. |
| CAN connector | 2× Connfly DS1128-09 RJ45 | C86578 | 5 087 | **RJ45 over JST-XH**: ordinary Cat5 patch leads give a twisted pair, a latch and any length off the shelf. Pinout follows CANopen CiA 303-1 (1 = CAN_H, 2 = CAN_L, 3/7 = GND). Not a close call. |
| Termination | 120 Ω + 2-pin jumper | C22787 | — | Fit the jumper on the two end nodes only. |
| Current/voltage | INA226AIDGSR (INA228 alt.) | C49851 | 64 058 | See deviation 1. |
| Shunt | RALEC LR2512-22R001F4, 1 mΩ 1 % 2 W 75 ppm | C154668 | 7 151 | Metal-alloy element; sense traces leave the inside edges of its pads. |
| Pulse switch | IRLB3034PBF, 40 V, 2 mΩ max @ 4.5 V, TO-220 | C144151 | 187 | Meets the ≥ 40 V / ≤ 4 mΩ / TO-220 requirement. Stock is thin — it is a hand-soldered part, also stocked by DigiKey/Mouser. |
| Gate driver | UCC27517DBVR | C99395 | 19 889 | 4 A driver, TTL thresholds (3.3 V logic OK), under-voltage lockout holds the gate low at boot. |
| HW timeout | SN74LVC1G123DCTR one-shot | C123302 | 7 497 | Retriggerable monostable gates the driver; see §4.4. |
| Charger disconnect | Omron G2RL-1-E-DC12 on the **NC** contact | C58243 | 900 | **Relay over back-to-back MOSFETs**: de-energised = charger connected with zero firmware involvement, true isolation, no leakage, nothing to latch up when the charger voltage is above/below the battery. Coil only powered during a test (~35 s). |
| Relay driver | AO3400A + 1N4148W flyback | C20917 / C81598 | 1 M+ | Basic parts. |
| Buck | AP63203WU-7, fixed 3.3 V, 3.8–32 V in | C780769 | 5 483 | No feedback divider, 32 V rating covers the TVS clamp. |
| Protection | SMBJ20A, SS34 (reverse polarity), USBLC6-2SC6, PESD2CAN | C151922 / C8678 / C7519 / C2687131 | all > 40 k | SS34 in series with the logic supply only — the power path stays diode-free. |
| Fuse holder | Littelfuse 178.6165.0002 | C207061 | 1 311 | Exact KiCad library footprint. |
| Power terminals | 6× M4 plated lug pads with via rings | — | — | Bolt a 10 AWG ring lug straight to the board (M4 screw + nut). No connector to source; current limit is the copper, not a terminal block. |
| NFC | 6-pin header to a PN532 breakout | — | — | I2C on its own bus (I2C1) so PN532 clock-stretching can't disturb INA timing. |

## 4. Power and thermal calculations

**4.1 Pulse.** Resting 12.7 V into 1 Ω + ~30 mΩ of battery, leads, fuse, shunt and FET → **≈ 12.3 A**.
Resistor: 151 W for 100 ms = **15 J per pulse**, 45 J for three. Worst case with firmware hung, the
one-shot cuts off at ~0.22–0.3 s → 45 J in one pulse. 100 W aluminium-clad wirewounds are typically
rated 5× power for 5 s (2 500 J), so there is > 50× margin — check the short-time overload figure of
the resistor you actually buy.

**4.2 MOSFET.** Conduction: 12.3² × 2 mΩ = 0.30 W for 0.1 s = 30 mJ — no heatsink needed.
Partial-enhancement fault (worst case 6 V × 6 A = 36 W for ≤ 0.3 s ≈ 11 J): the TO-220 tab alone
(~0.8 J/K) rises ~14 °C. Turn-off energy in lead inductance (~5 µH): ½LI² ≈ 0.4 mJ against a
255 mJ avalanche rating, and D2 (SS54) freewheels it anyway.
*Not verified:* I could not render the datasheet's SOA figure on this machine; the numbers above are
from the electrical tables. Worth a glance at Fig. 8 of the IRLB3034 datasheet.

**4.3 Shunt / fuse / relay.** Shunt: 0.225 W at 15 A, 0.15 W in the pulse, against 2 W. A 15 A ATO fuse
carries 12.3 A for 100 ms indefinitely (82 % of rating). Relay coil 360 Ω → 33–40 mA; must-operate
voltage is 70 % of 12 V = 8.4 V, so with the SS34 drop the test works down to ~8.8 V battery.

**4.4 Hardware timeout.** `LOAD_EN` (GPIO6, 10 k pull-down) drives both B and /CLR of the one-shot.
Q follows the pin while it is high, but only for t = R14·C10 = 100 kΩ × 2.2 µF ≈ **220 ms**
(tolerance puts it at 180–300 ms, under the 500 ms limit). Q drives the gate driver. Reset state of
the pin is high-Z → pulled low → load off. R13 holds the gate low when the driver is unpowered.
A fresh pulse needs a new low→high edge, so a hung pin cannot hold the load on.

**4.5 Residual hazard — please act on this.** Nothing electronic protects against Q1 failing short
(MOSFETs fail short) or a firmware crash-loop re-triggering pulses: either puts ~150 W into the
resistor continuously. J13 lets a normally-closed thermostat on the resistor cut gate drive (covers
the firmware case). For the shorted-FET case, put a **≥ 15 A normally-closed thermostat or thermal
fuse (70–80 °C) in series with the resistor lead**, bonded to the resistor body.

**4.6 Copper (2 oz, both layers poured and stitched).** IPC-2221B external:
I = 0.048·ΔT^0.44·A^0.725. For 15 A at ΔT = 20 °C: A = 448 mil² → **4.2 mm of 2 oz copper on one layer**.
Narrowest part of the path is the VNODE strip to the relay, 4.4 mm wide on **each** layer:
one layer alone → ΔT ≈ 18.5 °C at 15 A; both layers sharing → ΔT ≈ 6 °C. That strip only carries
charger current (6 A in practice), where the rise is under 2 °C. Sheet resistance 0.25 mΩ/sq gives
~0.7 mΩ from BATT+ to LOAD+ excluding the shunt and fuse. 55 stitching vias (0.4 mm drill) tie the
high-current pours top to bottom, plus 100 ground-stitching vias, in addition to the lug and
through-hole barrels. Track keep-outs on both layers stop any signal trace from cutting these pours.

## 5. IR accuracy budget (target ±0.5 mΩ over 5–40 mΩ)

IR = (V1 − V2) / (I2 − I1). Differencing cancels bus-voltage offset, shunt offset, the node's own
supply current and the relay coil current.

| Term | INA226 (fitted) | INA228 (alt.) |
|---|---|---|
| Shunt LSB / counts at 12.3 A | 2.5 µV / 4 920 | 78 nV (±41 mV range) / 157 000 |
| Bus LSB | 1.25 mV | 195 µV |
| Gain error, max (each of V and I) | 0.1 % | 0.05 % |

| Error source | at 5 mΩ | at 40 mΩ |
|---|---|---|
| Bus quantisation, worst case ±1.25 mV on ΔV | ±0.10 mΩ | ±0.10 mΩ |
| INA gain (V + I) + calibration residual, ~0.4 % | ±0.02 mΩ | ±0.16 mΩ |
| Shunt drift, 75 ppm/°C × 20 °C | — | ±0.06 mΩ |
| **Worst-case sum (INA226)** | **±0.12 mΩ** | **±0.32 mΩ** |
| Worst-case sum (INA228) | ±0.04 mΩ | ±0.20 mΩ |

Both meet ±0.5 mΩ, **but only after calibrating the shunt**: its raw 1 % tolerance alone is ±0.4 mΩ at 40 mΩ.

*Timing:* conversion time 1.1 ms for both channels with 4× averaging gives a V+I pair every 8.8 ms,
~11 pairs per 100 ms pulse; use the last two (≈ 80–98 ms), triggered from the ALERT (conversion-ready)
pin on GPIO10. *Not verified:* I confirmed the INA226 LSBs, gain and offset limits against TI's
SBOS547; the 1.1 ms setting is from memory of the same table.

*Calibration plan (two constants in flash):*
1. **Current gain** — pass ~12 A through the node in series with a reference meter or 0.1 % 4-wire shunt; store measured/true.
2. **Zero offset** — the reading includes fixed series resistance the node cannot separate from the
   battery: SB50 contact, pigtails, and ~0.3 mΩ of board ground. VBUS is single-ended, so the
   negative side cannot be Kelvin-sensed. Measure one battery with a known-good reference
   (Battery Beak), store the difference, and subtract it. Being copper, it moves < 0.05 mΩ over 20 °C.

## 6. Layout (100 × 80 mm, 2 layers, 2 oz, four #10 holes)

- **Top band, left to right:** BATT+ / BATT− lugs → fuse → shunt → LOAD+ lug → relay → CHG+ / CHG− lugs.
  The whole charger and pulse path is poured on both layers.
- **Analog corner** (INA226, filters, test points) sits directly under the shunt, ~40 mm from the
  buck converter and ~25 mm from the relay.
- **Centre:** LOAD− lug, Q1, flyback diode, gate driver and one-shot; the on-board NTC is beside Q1.
- **Right:** buck converter and relay driver. **Bottom:** ESP32, USB-C and the two RJ45 jacks on the board edge.
- Result: DRC 0 violations / 0 unconnected / 0 schematic-parity issues; ERC 0 errors, 0 warnings.

Things in the layout I am not sure of, or chose deliberately:

1. **Silkscreen checks are switched off in DRC** (`silk_overlap`, `silk_over_copper`). Some reference
   designators overlap pads or each other; the fab clips silk off pads automatically. Cosmetic only.
2. **ESP32 antenna keep-out is removed** and the module's 0.2 mm thermal vias deleted, because the radio
   is never used. Do not reuse this layout for a Wi-Fi/BLE product. (This is also why
   `lib_footprint_mismatch` is ignored in DRC.)
3. **Status LEDs** are three separate 0603 parts (red, green, blue) placed by JLC, replacing the
   5 mm RGB LED of the first draft. They sit on the board under a window in the lid.
4. **Signal routing is autorouted** (Freerouting). It is electrically correct and DRC-clean but not
   pretty, and USB D+/D− are not length-matched (fine for full-speed USB at this length).
5. **Solid ground connections** on SMD pads and on the BATT−, CHG−, Q1-source and USB-shell pads.
   Hand-soldering the through-hole parts into 2 oz pours needs a hot iron.
6. **Ground return of the pulse** crosses the bottom ground pour past the INA226; this is the ~0.3 mΩ
   fixed offset handled by the zero calibration in §5.
7. **JLC rotation offsets:** check every polarised part in JLC's placement preview before ordering.

## 7. Open questions

1. **Charger behaviour:** does your charger restart cleanly after the relay drops it for ~35 s, and does it output voltage with no battery attached (which would keep the node powered and hide a battery swap)?
2. **Grounds:** the CAN ground wire ties every battery negative together, and USB ties it to the laptop. That is fine only if each charger output is isolated — worth confirming for your charger model.
3. **RJ45:** never plug a node into an Ethernet switch. Label the cables.
4. **Battery ID lifetime:** the node loses power when the battery is unplugged unless the charger holds it up. Firmware should clear the ID on any voltage collapse and require a new tap.
5. **INA228 or INA226?** If you want the INA228 specifically, order boards with U2 unpopulated and hand-fit it when stock returns.
