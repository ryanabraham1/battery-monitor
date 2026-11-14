# Setup guide: from boxes of parts to a working pit system

Nothing here has been run on real hardware yet. The firmware compiles and the hub passes its
simulated-node test, but expect some bring-up debugging on the first board.

The system is: one **node** per charger (the PCB in this repo, in its printed case), and one
**hub** (a Raspberry Pi with a CAN HAT) that logs results and serves a web page. Nodes and hub
are chained together with ordinary Ethernet patch cables carrying CAN.

```
 charger ──SB50──┐                       ┌──SB50── battery (NFC tag stuck on it)
                 │  CHG±           BATT± │
              ┌──┴───────── node ────────┴──┐
              │  LOAD± ── 1 Ω 100 W resistor (+ thermostat → J13)
              │  J11 ──── PN532 NFC reader (sits where the battery's tag lands)
              │  J12 ──── temperature probe taped to the battery bay
              └── CAN (RJ45) ── next node ── … ── Raspberry Pi + CAN HAT
```

## 1. Everything to buy

Prices are rough single-quantity figures from typical hobby suppliers, not quotes.

### Per node (one per charger bay)

| Item | Qty | Notes | ~USD |
|---|---|---|---|
| Assembled PCB from JLCPCB | 1 | `fab/` files; see README for ordering | 30–45 |
| Hand-solder parts for the PCB | 1 set | The "hand-solder / THT" rows in `fab/ir_node_BOM_full.csv`: relay, fuse holder, MOSFET, RJ45 ×2, RGB LED, headers, JST-XH ×2 | (in BOM) |
| ATO/ATC blade fuse, **15 A** | 1 | Plus spares | 0.50 |
| Load resistor, **1 Ω 100 W**, aluminium-housed | 1 | Bolt it to a metal plate or heatsink | 6–10 |
| Thermostat, **normally closed**, opens at 70–80 °C (KSD9700 or KSD301 style) | 1 | Bolted or epoxied to the load resistor, wired to J13. **Desolder R11** (0 Ω, next to J13) when you fit it, or it does nothing | 2 |
| JST-XH 2-pin plug with leads | 2 | One for the thermostat (J13), one for the temperature probe (J12) if it doesn't come with one | 1 |
| NTC temperature probe, 10 kΩ B3950 | 1 | Optional; the node runs without it | 2 |
| PN532 NFC module (the common red "V3" board) | 1 | Set its mode switches/jumpers to **I2C**. Optional; without it results are logged per station instead of per battery | 6–9 |
| Female–female jumper wires, 20–30 cm | 6 | PN532 to J11 | 1 |
| Anderson SB50 housing + contacts for 10–12 AWG | 2 | One mates the battery, one mates the charger. Match the housing colour your team uses | 8 |
| 10 AWG wire, red and black | ~0.5 m each | Battery and charger pigtails; keep the battery pigtail short | 4 |
| 14 AWG wire | ~0.5 m | Node to load resistor | 1 |
| Ring terminals, M4 (#8) stud | 6 | 4 for 10–12 AWG (yellow), 2 for 14–16 AWG (blue) | 2 |
| M4 × 10 screws, nuts, lock washers | 6 each | Bolt the ring terminals to the PCB pads | 1 |
| M3 × 16 screws | 4 | Case: up through base and PCB into the lid | 0.50 |
| Screws to mount the case and resistor plate | a few | Up to M4 through the case ears | 0.50 |
| Ethernet patch cable (Cat5e or better) | 1 | To the next node or the hub. Length to suit; keep the whole chain under ~50 m | 2 |
| Printed case | 1 | `case/node_base.stl`, `case/node_lid.stl`, optionally `case/nfc_holder.stl`; ~75 g of PETG | 2 |

### Per battery

| Item | Qty | Notes | ~USD |
|---|---|---|---|
| NFC sticker tag, NTAG213 or NTAG215 | 1 | Stick it where it lands on the reader when the battery is in the bay. If read range is poor against the battery, use "on-metal" (ferrite-backed) tags | 0.30–1 |

### Hub (one for the whole pit)

| Item | Qty | Notes | ~USD |
|---|---|---|---|
| Raspberry Pi 4 Model B (2 GB is plenty); a 3B+ or 5 also works | 1 | Needs the 40-pin header | 45–60 |
| CAN HAT with an **MCP2515** controller, e.g. Waveshare RS485 CAN HAT | 1 | Has a 3.3 V transceiver, screw terminals for CAN_H / CAN_L, and a 120 Ω termination jumper | 14–18 |
| microSD card, 16 GB or larger | 1 | Raspberry Pi OS Lite (64-bit) | 8 |
| Official Raspberry Pi power supply (USB-C 5 V 3 A for a Pi 4) | 1 | The node boards do not power the Pi | 8–10 |
| Ethernet patch cable to cut in half | 1 | Bare end goes into the HAT's screw terminals | 2 |
| M2.5 × 6 screws | 4 | Pi to `case/pi_tray.stl` | 0.50 |
| 2.54 mm jumper cap | 1 | For JP1 on the last node (often supplied with header strips) | 0.10 |

### Tools

Soldering iron, crimper for ring terminals and SB50 contacts, multimeter, USB-C **data** cable,
a computer with [PlatformIO](https://platformio.org/install/cli) for flashing.

## 2. Print the cases

All parts print flat-side-down with no supports, 0.2 mm layers, 3 perimeters, 20–30 % infill.
PETG or ASA is better than PLA near a charger. `node_lid.stl` is already saved upside down.

![Case parts](../case/preview.png)

- The four M3 × 16 screws go in from underneath: through the base, through the PCB's corner
  holes, and self-tap into the lid's corner posts. Don't overtighten.
- Lid openings: fuse window, LED hole, two pin holes for BOOT and RESET (press with a paperclip),
  wire slots labelled on the lid. Leave the LED's legs long enough that it reaches the lid.
- `nfc_holder.stl` is sized for a 42.7 × 40.4 mm PN532 board; measure yours. The tag reads
  through the 1.2 mm floor, so mount it floor-toward-battery. Cable-tie the module in.
- To change any dimension, edit the parameters at the top of `tools/gen_case.py` and rerun it.
- Do not print a cover for the load resistor. It needs air, and in a fault it gets hot.

## 3. Build a node

1. Solder the through-hole parts onto the JLC-assembled board. Check the RGB LED pin order
   against the silkscreen before soldering (see the design doc's open questions).
2. Before connecting a battery: plug in USB-C only and flash the firmware (section 4). The
   console should answer `status`.
3. Crimp ring terminals and bolt the wires on. The lid and the PCB silkscreen label every pad:

   | Pads | Goes to | Wire |
   |---|---|---|
   | BATT+ / BATT− | SB50 that mates the **battery** | 10 AWG, as short as practical |
   | CHG+ / CHG− | SB50 that mates the **charger** | 10 AWG |
   | LOAD+ / LOAD− | the two lugs of the 1 Ω resistor | 14 AWG |

   Polarity matters. The board has reverse-polarity protection on its own electronics, but a
   reversed battery with a charger attached is still a short through the charger.
4. Thermostat: fix it to the resistor body, wire it to J13, and desolder R11.
5. PN532 to J11 (pin 1 is marked on the silkscreen):

   | J11 pin | 1 | 2 | 3 | 4 | 5 | 6 |
   |---|---|---|---|---|---|---|
   | PN532 | VCC (3.3 V) | GND | SDA | SCL | IRQ | RSTO/RST |
6. Temperature probe to J12. Fit the 15 A fuse last.

## 4. Flash and configure a node

```bash
cd firmware
```
```bash
pio run -t upload
```
```bash
pio device monitor
```

If the upload can't find the board, hold BOOT, tap RESET, release BOOT, and try again.

In the monitor, type `help`. The settings that matter:

| Command | What it does |
|---|---|
| `id 3` | CAN id, 1–31. **Every node needs a different one.** |
| `test` | Run an IR test now |
| `status` | Readings, detected hardware, last result |
| `lead 2.4` | Milliohms to subtract for your pigtail (below) |
| `auto 30` | Retest every N minutes while a battery is connected (0 = only on arrival / on command) |
| `settle 5` | Seconds to rest after disconnecting the charger before the pulse |
| `good 15`, `warn 20` | LED thresholds in mΩ |

**Lead resistance.** The node measures voltage at its own BATT pads, so the pigtail and SB50
contacts between the pads and the battery are included in the reading. Estimate it and enter it
with `lead`: 10 AWG is about 3.3 mΩ per metre, both conductors count, plus roughly 0.2 mΩ per
SB50 contact. A 30 cm pigtail is about 0.6 m × 3.3 + 0.4 ≈ 2.4 mΩ. If you have a tester you
trust, measure one battery with both and adjust `lead` until they agree.

**LED colours.**

| LED | Meaning |
|---|---|
| Short blue blink | No battery |
| Cyan | Battery present, not tested yet |
| Fast blue blink, then white flash | Charger disconnected and settling, then the pulse |
| Green / yellow / red | Last result: good / marginal / replace |
| Magenta | Last test failed (type `status`, or look at the hub page) |
| Fast red blink | Load current did not stop. Unplug the battery and inspect the MOSFET. |
| Blinks off briefly every 2 s | Charging current is flowing |
| Fast white blink | "Blink LED" pressed on the hub page |

## 5. Set up the hub

1. Write Raspberry Pi OS Lite to the SD card with Raspberry Pi Imager; set a hostname, user and
   your network in its settings, and enable SSH.
2. Fit the CAN HAT. Look at the crystal next to the MCP2515 chip: it is marked 12.000 or 8.000.
3. Copy the `hub/` folder to the Pi and run the installer with that crystal frequency:

   ```bash
   sudo ./install.sh 12000000
   ```
   ```bash
   sudo reboot
   ```
4. After the reboot, open `http://<pi-hostname>.local:8080` from a phone or laptop on the same
   network. The page has no login; keep the Pi on a network you control.

To try the hub before any node exists, see the top of `hub/sim_node.py`.

## 6. Wire the CAN bus

- Chain the nodes with patch cables: either RJ45 jack on a node works for in or out.
- Cut one patch cable in half for the hub end. With the usual T568B colours:

  | RJ45 pin | Colour (T568B) | Signal | HAT terminal |
  |---|---|---|---|
  | 1 | white/orange | CAN_H | H |
  | 2 | orange | CAN_L | L |
  | 3 | white/green | GND | GND (or Pi header pin 6 if the HAT has no GND terminal) |

  Check with a multimeter against the plug if your cable's colours differ.
- **Terminate both ends and nothing in between.** With the hub at one end: enable the HAT's
  120 Ω jumper, and fit the JP1 jumper cap on the node farthest from the hub. With the power
  off, CAN_H to CAN_L should measure about 60 Ω.
- The cable's ground wire ties every node's battery negative together. That is intended and
  harmless with normal isolated chargers.

## 7. Using it

1. Name each battery: put it on a station, wait for its tag to appear in the Batteries table,
   press Rename.
2. A test runs 5 seconds after a battery arrives, then every `auto` minutes, and whenever you
   press "Test now". Each test opens the charger relay, rests, pulls about 12 A for 0.1 s, and
   reconnects the charger.
3. Compare each battery against its own history. A reading right after charging is lower than
   one taken on a rested battery, and cold batteries read higher.
4. "Download all tests (CSV)" at the bottom of the page gives you everything for a spreadsheet.

## 8. CAN protocol (250 kbit/s, 11-bit ids, little-endian)

| Id | Direction | Bytes |
|---|---|---|
| `0x100 + id` | node → hub, 1 Hz | state, flags, voltage mV (u16), current ×10 mA (i16, + = discharge), battery °C (i8, −128 = none), MOSFET °C (i8) |
| `0x180 + id` | node → hub, on change and every 5 s | tag UID length (0 = none), then up to 7 UID bytes |
| `0x200 + id` | node → hub, 3× after each test | IR ×0.01 mΩ (u16, 0xFFFF = failed), open volts mV (u16), loaded volts mV (u16), pulse current ×0.1 A (u8; error code if failed), sequence number (u8) |
| `0x080 + id`, or `0x080` for all | hub → node | command: 1 test, 2 charger (byte 1: 1 = hold disconnected, 0 = normal), 3 blink LED, 4 clear fault |

State, flag and error values are in `firmware/include/config.h`.
