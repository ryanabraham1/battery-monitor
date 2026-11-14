# FRC Battery IR Monitor Node — hardware rev A

| Folder | Contents |
|---|---|
| `docs/design.md` | Phase 1 design document: deviations, part choices, calculations, accuracy budget, open questions |
| `hw/` | KiCad 9 project: `ir_node.kicad_pro`, `.kicad_sch`, `.kicad_pcb`, schematic PDF, ERC and DRC reports |
| `fab/` | `ir_node_gerbers.zip` (Gerbers + drill), `ir_node_BOM_JLC.csv`, `ir_node_CPL_JLC.csv`, `ir_node_BOM_full.csv` |
| `renders/` | PNG previews of each copper layer and 3D views |
| `tools/` | The Python scripts that generate everything (run with KiCad's bundled Python) |

## Ordering (JLCPCB)

1. Upload `fab/ir_node_gerbers.zip`. Options: 2 layers, 1.6 mm, **2 oz outer copper**, 100 × 80 mm.
2. Enable PCB assembly, top side. Upload `ir_node_BOM_JLC.csv` and `ir_node_CPL_JLC.csv`.
3. **Check every part's orientation in JLC's placement preview** before paying — rotation
   conventions differ between KiCad and JLC for some packages (SOT-23, diodes, the ESP32 module).
4. Hand-solder the through-hole parts listed as "hand-solder / THT" in `ir_node_BOM_full.csv`.

PCBWay or any other fab can use the same Gerber zip; give them `ir_node_BOM_full.csv`, which has
manufacturer part numbers as well as LCSC numbers.

## Off-board items to buy separately

- 1 Ω 100 W aluminium-clad resistor, bolted to a heatsink or metal plate
- 15 A ATO blade fuse
- 10k B3950 NTC probe on a lead with a JST-XH 2-pin plug
- PN532 NFC breakout and a 6-wire lead
- M4 screws/nuts and 10 AWG ring lugs ×6, two SB50 pigtails
- Normally-closed thermostat(s) for the load resistor (see design doc §4.5)

## Regenerating

```
python tools/gen_sch.py     # schematic from tools/design.py
python tools/route.py <freerouting.jar>   # place, autoroute, pour
python tools/gen_fab.py     # BOM, CPL, Gerbers, renders
```
