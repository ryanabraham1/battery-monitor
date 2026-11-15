# FRC Battery IR Monitor Node — hardware rev A

An inline node that sits between a charger and a 12 V FRC battery (charger → node → battery).
It measures internal resistance with a 12 A / 100 ms pulse
load, and reports to a pit hub over wired CAN. No Wi-Fi or Bluetooth is used.

![3D render of the top of the board](renders/3d_top.png)

**Status:** schematic and layout are complete (ERC and DRC clean) and ready to order. Node
firmware, the Raspberry Pi hub software and printable cases are included. Nothing has been built
or tested on real hardware yet: the firmware compiles and the hub passes a simulated-node test.

- **[docs/BOM.md](docs/BOM.md): everything to buy, with purchase links.**
- **[docs/setup.md](docs/setup.md): full shopping list (including the Pi and CAN HAT), assembly,
  flashing, hub install, CAN wiring.** Start here.
- [docs/design.md](docs/design.md): calculations, parts that differ from the original brief, open questions.

## Board at a glance

- 100 × 80 mm, 2 layers, 2 oz copper, four #10 mounting holes (0.196 in)
- ESP32-S3 (radio unused), INA226 current/voltage monitor with a 1 mΩ Kelvin-sensed shunt
- Charger relay on its normally-closed contact, so an unpowered node leaves the charger connected
- Pulse-load MOSFET with a hardware one-shot that cuts the load after ~220 ms even if firmware hangs
- Two RJ45 jacks for daisy-chained CAN, USB-C for flashing and serial, header for an optional PN532 NFC reader
- Six M4 bolt-down lug pads: BATT±, CHG±, LOAD± (off-board 1 Ω 100 W resistor)

| Top copper | Bottom copper |
|---|---|
| ![Top copper layer](renders/top.png) | ![Bottom copper layer](renders/bottom.png) |

| Component placement | Underside (3D) |
|---|---|
| ![Component placement](renders/place.png) | ![3D render of the bottom](renders/3d_bottom.png) |

Full schematic: [hw/ir_node_schematic.pdf](hw/ir_node_schematic.pdf). The image below is a partial
view (the sheet is cropped at the right and bottom).

![Partial view of the schematic](renders/schematic.png)

## Repository layout

| Folder | Contents |
|---|---|
| `docs/design.md` | Phase 1 design document: deviations, part choices, calculations, accuracy budget, open questions |
| `hw/` | KiCad 9 project: `ir_node.kicad_pro`, `.kicad_sch`, `.kicad_pcb`, schematic PDF, ERC and DRC reports |
| `fab/` | `ir_node_gerbers.zip` (Gerbers + drill), `ir_node_BOM_JLC.csv`, `ir_node_CPL_JLC.csv`, `ir_node_BOM_full.csv` |
| `renders/` | PNG previews of each copper layer and 3D views |
| `firmware/` | ESP32-S3 node firmware (PlatformIO, Arduino framework) |
| `hub/` | Raspberry Pi hub: CAN logger, SQLite history, web page, installer, simulated node and test |
| `case/` | Printable STLs: node base and lid, Pi tray, optional NFC reader holder |
| `tools/` | The Python scripts that generate everything (run with KiCad's bundled Python) |

## Ordering (JLCPCB)

### Saved quotes, ready to order

Both boards are already set up on JLCPCB with Gerbers, BOM, CPL, options and corrected part
rotations, and sit in the cart. The links only open while you're signed in to the JLCPCB
account that made them. Anyone else gets a sign-in page or "not found".

| Board | Quote | Qty | Price (14 Nov 2026, before shipping) |
|---|---|---|---|
| Rev A, 12 A (`main`) | [ir_node_gerbers_Y2](https://cart.jlcpcb.com/smt-order/?pcbFileNo=817ec2df53a0476d98992071956ca152) | 10 PCB + 10 assembled | $44.10 + $208.83 = **$252.93** (5 pcs: $199.50) |
| Rev B, 120 A (`rev-b-120a`) | [ir_node_gerbers_Y3](https://cart.jlcpcb.com/smt-order/?pcbFileNo=c6244d6d3c0043389400a579e429804d) | 10 PCB + 10 assembled | $44.10 + $213.49 = **$257.59** (5 pcs: $203.47) |
| **Both** | | | **$510.52** + shipping (UPS about $26) |

To order from that account, open the [cart](https://cart.jlcpcb.com/shopcart/cart), tick the items
and check out.

### If someone else is paying (school purchasing)

JLCPCB has no public share link for a quote, so the purchaser rebuilds it in their own account.
It takes about five minutes per board, and the price comes out the same:

1. Give them the three files for each board: `fab/ir_node_gerbers.zip`, `fab/ir_node_BOM_JLC.csv`
   and `fab/ir_node_CPL_JLC.csv` (the Rev B files are on the `rev-b-120a` branch).
2. On [jlcpcb.com/quote](https://cart.jlcpcb.com/quote), upload the Gerber zip. Set PCB Qty 10 and
   Outer Copper Weight **2 oz**, and leave everything else at its default.
3. Turn on PCB Assembly: Standard, top side, PCBA Qty 10. Click Next, then upload the BOM and CPL
   and click Process.
4. Tick SW1 and SW2 (JLC unticks them because they share a part number). Click Next through the
   placement preview; the rotations are already correct in the CPL.
5. Product description: Sensor/Controller/Precision Instrument → Current Sensor. Then Save to Cart.

If the school pays by purchase order and not by card, ask JLCPCB support which payment and
invoice options they accept for schools before building the cart.

Settings used: FR-4, 2 layers, 1.6 mm, green, OSP finish, **2 oz outer copper**, Standard PCBA,
top side only, edge rails added by JLC, product description "Current Sensor (HS 903090)".
SW1 and SW2 share a part number, so JLC unticks them both. Both are re-ticked in these quotes.

**Rotation corrections.** JLC's models for these packages sit at a different zero rotation from
KiCad's footprints. `tools/gen_fab.py` now adds these offsets when it writes the CPL (`JLC_ROT`),
so a fresh upload places them correctly. Check in JLC's preview that each pink pin-1 dot sits on
the footprint's pin-1 triangle.

| Part | Package | Offset added to CPL rotation |
|---|---|---|
| U2 | VSSOP-10 | −90° (90° clockwise) |
| U3 | SOIC-8 | −90° |
| U4 | TSOT-23-6 | −90° |
| U7 | SOT-23-6 | −90° |
| U5 | SSOP-8 | 180° |
| U6 | SOT-23-5 | 180° |
| Q2 | SOT-23 | 180° |
| D7 | SOT-23 | 180° |

Diodes, LEDs, C18 (rev B), U1 (ESP32) and J8 (USB-C) were checked and are correct as placed.

### From scratch

1. Upload `fab/ir_node_gerbers.zip`. Options: 2 layers, 1.6 mm, **2 oz outer copper**, 100 × 80 mm.
   To save money on rev A you can order **1 oz** instead: the pours are wide enough for the 12 A
   pulse and for chargers up to about 10 A. Stay with 2 oz if your charger is larger.
2. Enable PCB assembly, top side. Upload `ir_node_BOM_JLC.csv` and `ir_node_CPL_JLC.csv`.
3. **Check every part's orientation in JLC's placement preview** before paying — rotation
   conventions differ between KiCad and JLC for some packages (SOT-23, diodes, the ESP32 module).
4. Hand-solder the through-hole parts listed as "hand-solder / THT" in `ir_node_BOM_full.csv`.

PCBWay or any other fab can use the same Gerber zip; give them `ir_node_BOM_full.csv`, which has
manufacturer part numbers as well as LCSC numbers.

## What else you need

The PCB is one part of the system. The complete list with quantities, notes and rough prices is
in [docs/setup.md](docs/setup.md#1-everything-to-buy). In short:

- **Per node:** 1 Ω 100 W resistor, normally-closed thermostat, 15 A blade fuse, two SB50 connectors, 10 and 14 AWG wire, M4 ring terminals and hardware,
  an Ethernet patch cable, four #10-32 × 5/8 in screws, printed case
- **Hub (one per pit):** Raspberry Pi (3B+, 4 or 5), MCP2515 CAN HAT, microSD card, Pi power
  supply, one patch cable cut in half, printed tray

## Cases

![Printable case parts](case/preview.png)

## Regenerating

```
python tools/gen_sch.py     # schematic from tools/design.py
python tools/route.py <freerouting.jar>   # place, autoroute, pour
python tools/gen_fab.py     # BOM, CPL, Gerbers, renders
python tools/gen_case.py    # case STLs (needs: pip install manifold3d numpy pillow matplotlib)
python hub/test_hub.py      # hub against a simulated node (needs: pip install python-can)
```
