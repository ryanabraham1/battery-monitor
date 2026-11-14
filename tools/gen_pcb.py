"""Build hw/ir_node.kicad_pcb from design.py: outline, placement, nets, pours, Kelvin pre-routes.
usage: python gen_pcb.py            -> writes board (unrouted signals) + DSN for Freerouting
"""
import os, sys, json, uuid
sys.path.insert(0, os.path.dirname(__file__))
import wx
wx.DisableAsserts()          # never pop wxWidgets debug dialogs from a script
import pcbnew
from pcbnew import VECTOR2I, FromMM, ToMM
import design as D
from sexp import FPDIR

HW = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "hw"))
NS = uuid.UUID("6f1d2c1e-0000-4000-8000-00000000f1c0")
OX, OY = 100.0, 50.0
BW, BH = 100.0, 80.0


def pt(x, y):
    return VECTOR2I(FromMM(OX + x), FromMM(OY + y))


# ---------------------------------------------------------------- placement (x, y, rot, layer)
PL = {
    # 120 A loop, top band: BATT- lug, MOSFET, LOAD- lug, flyback diode, LOAD+ lug
    "J2": (11, 10, 0), "Q1": (22, 12.54, 90), "J6": (33, 10, 0), "D2": (45.5, 10, 180), "J5": (57, 10, 0),
    # fuse row: BATT+ stud, (MIDI fuse bolted across), fuse stud B, shunt
    "J1": (11, 27, 0), "J14": (41, 27, 0), "R1": (51, 27, 0),
    "D3": (41, 19, 0), "C18": (63.5, 20, 270),
    # charger branch
    "K1": (77.5, 31, 180), "F1": (85.4, 20, 0),
    "J3": (91, 13, 0), "J4": (91, 30, 0),
    "D1": (83, 31, 90), "Q2": (83, 25.5, 0), "R3": (83, 35.2, 0),
    # measurement (below the shunt)
    "R4": (49.6, 32.2, 270), "R5": (52.4, 32.2, 270), "C1": (51, 35.6, 0),
    "U2": (51, 40, 0),
    "R6": (18.6, 30.5, 0), "C2": (46, 39.5, 90), "C3": (56, 39.5, 90),
    "R7": (59.5, 38.5, 0), "R8": (59.5, 40.5, 0), "R9": (59.5, 42.5, 0),
    # gate drive (driver + one-shot mid-board; gate resistors and NTC at the MOSFET)
    "U6": (51, 48.5, 0), "R12": (24.5, 18.6, 180), "R13": (20.5, 18.6, 0), "C9": (47.5, 47, 90),
    "D6": (47.5, 51.5, 90), "R10": (44.5, 51, 90), "R11": (44.5, 46.5, 90), "J13": (38, 44.5, 0),
    "U5": (41, 54.5, 0), "R14": (46, 56, 0), "C10": (46, 58, 0), "C11": (37, 54.5, 90),
    "R15": (37, 58.5, 0), "R16": (41, 58.5, 0), "TH1": (28.2, 18.6, 0), "R24": (31.4, 18.6, 0), "C17": (34.6, 18.6, 0),
    # supply
    "D4": (64.4, 32.5, 90), "D5": (32.5, 72.5, 90),
    "C4": (75, 38, 90), "C5": (78, 38, 90), "U4": (82, 38.5, 0), "C6": (82, 42, 0),
    "L1": (87.5, 40, 0), "C7": (92, 38, 90), "C8": (95, 38, 90),
    # MCU
    "U1": (15, 57, 0), "C13": (28, 44, 0), "C14": (28, 46.5, 0), "R17": (28, 49, 0), "C12": (28, 51, 0),
    "SW1": (30, 56, 90), "SW2": (30, 64, 90),
    "J7": (5, 39.5, 90),
    "J8": (41, 76.0, 0), "U7": (41, 66.5, 0), "R18": (35.5, 68, 90), "R19": (46.5, 68, 90),
    "D8": (20, 36.29, 270), "D9": (23.3, 36.29, 270), "D10": (24.83, 37.81, 270),
    "R25": (28, 35, 0), "R26": (28, 37, 0), "R27": (28, 39, 0),
    # CAN + NFC
    "J9": (55, 71.5, 0), "J10": (77.5, 71.5, 0),
    "U3": (72, 50, 0), "C15": (77, 50, 90), "D7": (72, 56.5, 0), "R20": (77, 56.5, 0),
    "JP1": (84, 51, 0),
    "J11": (89, 47, 0),
    "R21": (93, 51, 90), "R22": (95.5, 51, 90),
    # test points
    "TP1": (19, 23.5), "TP2": (46.6, 35.6), "TP3": (55.4, 35.6), "TP4": (16.2, 19.2), "TP5": (96, 44),
    "TP6": (93.5, 59.5), "TP7": (97, 65), "TP8": (5, 35.2), "TP9": (50.5, 56.5),
    "H1": (3.5, 3.5), "H2": (96.5, 3.5), "H3": (3.5, 76.5), "H4": (96.5, 76.5),
}

# copper pours: (net, layers, polygon pts, priority)
ZONES = [
    ("VBAT_RAW", "FB", [(5.5, 21.5), (20.6, 21.5), (20.6, 25.5), (18.2, 25.5), (18.2, 32.5), (5.5, 32.5)], 5),
    ("VBAT_F", "FB", [(35.5, 21.5), (36.6, 21.5), (36.6, 17), (40.6, 17), (40.6, 21.5), (49.3, 21.5), (49.3, 29),
                      (46.5, 29), (46.5, 32.5), (35.5, 32.5)], 5),
    ("VNODE", "FB", [(47.2, 4), (62, 4), (62, 8.8), (79.5, 8.8), (79.5, 13.2), (66.8, 13.2), (66.8, 19.2), (62, 19.2),
                     (62, 28.4), (67, 28.4), (67, 31.4), (58.5, 31.4), (58.5, 29), (52.9, 29), (52.9, 16),
                     (47.2, 16)], 5),
    ("CHG_K", "FB", [(67.5, 14.2), (83.4, 14.2), (83.4, 21.6), (67.5, 21.6)], 5),
    ("CHG_P", "FB", [(84.6, 7), (97, 7), (97, 22), (84.6, 22)], 5),
    ("LOAD_N", "FB", [(23.4, 4), (44, 4), (44, 16), (23.4, 16), (23.4, 11.1), (21.9, 11.1), (21.9, 8.9), (23.4, 8.9)], 5),
    ("GND", "F", [(0.4, 0.4), (BW - 0.4, 0.4), (BW - 0.4, BH - 0.4), (0.4, BH - 0.4)], 0),
    ("GND", "B", [(0.4, 0.4), (BW - 0.4, 0.4), (BW - 0.4, BH - 0.4), (0.4, BH - 0.4)], 0),
]

# no foreign tracks may cut the main-current pours (both layers); (x0, y0, x1, y1)
KEEPOUTS = [(5, 4, 20.5, 16), (23.6, 4, 44, 16), (47.2, 4, 62, 16), (62, 8.8, 79.5, 13.2), (54.8, 16, 62, 29),
            (36, 22, 47.2, 29), (36, 29, 46.5, 32.5), (36.6, 17, 40.6, 22), (67.5, 14.2, 83.4, 21.6), (84.6, 7, 97, 22),
            (5.5, 21.5, 18.2, 32.5), (62, 13.2, 66.8, 19.2), (58.5, 28.4, 67, 31.4)]

NETCLASS = {
    "Power": ["VIN_PROT", "VDRV", "VDRV_IN", "RLY_N", "GATE", "DRV_OUT", "BUCK_SW", "BUCK_BST"],
    "HighCurrent": ["VBAT_RAW", "VBAT_F", "VNODE", "CHG_K", "CHG_P", "LOAD_N"],
}


def load_nc_nets():
    """(ref, pin) -> 'unconnected-(...)' net names taken from the schematic netlist export."""
    from sexp import parse, find, first
    path = os.path.join(HW, "ir_node.net")
    out = {}
    if os.path.exists(path):
        n = parse(open(path, encoding="utf8").read())
        for nt in find(first(n, "nets"), "net"):
            name = str(first(nt, "name")[1])
            if name.startswith("unconnected-"):
                for nd in find(nt, "node"):
                    out[(str(first(nd, "ref")[1]), str(first(nd, "pin")[1]))] = name
    return out


NCNETS = load_nc_nets()


def write_project():
    pro = {
        "meta": {"filename": "ir_node.kicad_pro", "version": 3},
        "board": {"design_settings": {
            "rules": {"min_clearance": 0.2, "min_track_width": 0.2, "min_via_diameter": 0.6,
                      "min_through_hole_diameter": 0.3, "min_via_annular_width": 0.13,
                      "min_copper_edge_clearance": 0.3, "min_hole_clearance": 0.25,
                      "min_hole_to_hole": 0.5, "min_silk_clearance": 0.0, "min_text_height": 0.8,
                      "min_text_thickness": 0.08},
            "rule_severities": {"silk_overlap": "ignore", "silk_over_copper": "ignore",
                                "lib_footprint_mismatch": "ignore", "lib_footprint_issues": "ignore"},
            "defaults": {"zones": {"min_clearance": 0.3}},
        }},
        "net_settings": {
            "classes": [
                {"name": "Default", "clearance": 0.2, "track_width": 0.25, "via_diameter": 0.7, "via_drill": 0.3,
                 "microvia_diameter": 0.3, "microvia_drill": 0.1, "diff_pair_width": 0.2, "diff_pair_gap": 0.25,
                 "diff_pair_via_gap": 0.25, "priority": 2147483647, "pcb_color": "rgba(0, 0, 0, 0.000)",
                 "schematic_color": "rgba(0, 0, 0, 0.000)", "bus_width": 12, "wire_width": 6, "line_style": 0},
                {"name": "Power", "clearance": 0.2, "track_width": 0.5, "via_diameter": 0.8, "via_drill": 0.4,
                 "priority": 1, "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)"},
                {"name": "HighCurrent", "clearance": 0.3, "track_width": 0.5, "via_diameter": 0.8, "via_drill": 0.4,
                 "priority": 0, "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)"},
            ],
            "meta": {"version": 4},
            "netclass_patterns": [{"netclass": c, "pattern": "/" + n} for c, ns in NETCLASS.items() for n in ns],
        },
    }
    with open(os.path.join(HW, "ir_node.kicad_pro"), "w") as f:
        json.dump(pro, f, indent=2)


def build(gnd_zones=True):
    write_project()
    path = os.path.join(HW, "ir_node.kicad_pcb")
    if os.path.exists(path):
        os.remove(path)
    b = pcbnew.NewBoard(path)
    ds = b.GetDesignSettings()
    ds.SetCopperLayerCount(2)
    ds.SetBoardThickness(FromMM(1.6))

    # outline
    r = pcbnew.PCB_SHAPE(b)
    r.SetShape(pcbnew.SHAPE_T_RECT)
    r.SetStart(pt(0, 0)); r.SetEnd(pt(BW, BH))
    r.SetLayer(pcbnew.Edge_Cuts); r.SetWidth(FromMM(0.1))
    b.Add(r)

    nets = {}

    def net(name):
        if name not in nets:
            ni = pcbnew.NETINFO_ITEM(b, "/" + name)
            b.Add(ni)
            nets[name] = ni
        return nets[name]

    def rawnet(name):
        if name not in nets:
            ni = pcbnew.NETINFO_ITEM(b, name)
            b.Add(ni)
            nets[name] = ni
        return nets[name]

    missing = []
    for p in D.PARTS:
        lib, name = p["fp"].split(":")
        fp = pcbnew.FootprintLoad(os.path.join(FPDIR, lib + ".pretty"), name)
        fp.SetReference(p["ref"])
        fp.SetValue(p["value"])
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        fp.SetPath(pcbnew.KIID_PATH("/" + str(uuid.uuid5(NS, "sym:%s:%d" % (p["ref"], 1)))))
        for k in ("LCSC", "MPN"):
            if p[k.lower()]:
                fp.SetField(k, p[k.lower()])
                fp.GetFieldByName(k).SetVisible(False)
        if p["asm"] == "none":
            fp.SetAttributes(fp.GetAttributes() | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
        padnums = set(pd.GetNumber() for pd in fp.Pads())
        for pin, n in p["pins"].items():
            if pin not in padnums:
                missing.append((p["ref"], pin))
        for pd in fp.Pads():
            n = p["pins"].get(pd.GetNumber())
            if n:
                pd.SetNet(net(n))
            elif (p["ref"], pd.GetNumber()) in NCNETS:      # keep schematic parity for no-connect pins
                pd.SetNet(rawnet(NCNETS[(p["ref"], pd.GetNumber())]))
        if p["ref"] not in PL:
            raise SystemExit("no placement for " + p["ref"])
        pl = PL[p["ref"]]
        if p["ref"] == "U1":          # radio is never enabled: waive the antenna keep-out
            for z in list(fp.Zones()):
                fp.Remove(z)
            for pd in list(fp.Pads()):   # drop the 0.2 mm thermal vias (below JLC standard drill); SMD pad 41 stays
                if pd.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and ToMM(pd.GetDrillSize().x) < 0.3:
                    fp.Remove(pd)
            for g in list(fp.GraphicalItems()):
                if g.GetLayer() == pcbnew.F_CrtYd:
                    fp.Remove(g)
            cr = pcbnew.PCB_SHAPE(fp)
            cr.SetShape(pcbnew.SHAPE_T_RECT); cr.SetLayer(pcbnew.F_CrtYd); cr.SetWidth(FromMM(0.05))
            cr.SetStart(VECTOR2I(FromMM(-9.25), FromMM(-13.0))); cr.SetEnd(VECTOR2I(FromMM(9.25), FromMM(13.0)))
            fp.Add(cr)
        b.Add(fp)
        fp.SetPosition(pt(pl[0], pl[1]))
        if len(pl) > 2 and pl[2]:
            fp.SetOrientationDegrees(pl[2])
        fp.Value().SetVisible(False)
    if missing:
        raise SystemExit("symbol pins without footprint pads: %s" % missing)

    add_zones(b, net, gnd=False)
    for i, (x0, y0, x1, y1) in enumerate(KEEPOUTS):
        for L in (pcbnew.F_Cu, pcbnew.B_Cu):
            z = pcbnew.ZONE(b)
            z.SetIsRuleArea(True)
            z.SetLayer(L)
            z.SetDoNotAllowTracks(True); z.SetDoNotAllowVias(False); z.SetDoNotAllowPads(False)
            z.SetDoNotAllowFootprints(False)
            try:
                z.SetDoNotAllowCopperPour(False)
            except AttributeError:
                pass
            ol = z.Outline(); ol.NewOutline()
            for (x, y) in [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]:
                ol.Append(pt(x, y))
            ol.Outline(0).SetClosed(True)
            z.SetZoneName("HC_keepout_%d" % i)
            b.Add(z)
    if gnd_zones:
        add_zones(b, net, gnd=True)
    kelvin(b, nets)
    stitch(b, nets)
    silk(b)
    return b, nets


SOLID_GND_PADS = {("J2", "1"), ("J4", "1"), ("Q1", "3"), ("J8", "S1")}


def add_zones(b, net, gnd):
    for (n, layers, poly, prio) in ZONES:
        if (n == "GND") != gnd:
            continue
        for L in layers:
            z = pcbnew.ZONE(b)
            z.SetLayer(pcbnew.F_Cu if L == "F" else pcbnew.B_Cu)
            z.SetNet(net(n))
            z.SetAssignedPriority(prio)
            ol = z.Outline()
            ol.NewOutline()
            for (x, y) in poly:
                ol.Append(pt(x, y))
            ol.Outline(0).SetClosed(True)
            hc = n != "GND"
            z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL if hc else pcbnew.ZONE_CONNECTION_THERMAL)
            z.SetLocalClearance(FromMM(0.4 if hc else 0.3))
            z.SetMinThickness(FromMM(0.25))
            z.SetThermalReliefGap(FromMM(0.3))
            z.SetThermalReliefSpokeWidth(FromMM(0.5))
            z.SetIsFilled(False)
            z.SetZoneName(n + "_" + L)
            b.Add(z)


def padpos(b, ref, netname):
    fp = b.FindFootprintByReference(ref)
    for pd in fp.Pads():
        if pd.GetNetname() == "/" + netname:
            return ToMM(pd.GetPosition().x) - OX, ToMM(pd.GetPosition().y) - OY
    raise KeyError((ref, netname))


def track(b, nets, netname, pts, w=0.25, layer=pcbnew.F_Cu, lock=True):
    for (a, c) in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(pt(*a)); t.SetEnd(pt(*c)); t.SetWidth(FromMM(w)); t.SetLayer(layer)
        t.SetNet(nets[netname]); t.SetLocked(lock)
        b.Add(t)


def kelvin(b, nets):
    """Sense traces leave the INSIDE edges of the shunt pads and go straight to the filter resistors."""
    sx1, sy = padpos(b, "R1", "VBAT_F")
    sx2, _ = padpos(b, "R1", "VNODE")
    ax, ay = padpos(b, "R4", "VBAT_F")
    bx, by = padpos(b, "R5", "VNODE")
    track(b, nets, "VBAT_F", [(sx1 + 0.45, sy + 0.8), (sx1 + 0.45, sy + 2.2), (ax, sy + 3.2), (ax, ay)])
    track(b, nets, "VNODE", [(sx2 - 0.45, sy + 0.8), (sx2 - 0.45, sy + 2.2), (bx, sy + 3.2), (bx, by)])


def inside(poly, x, y):
    c = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def stitch(b, nets, pitch=2.5, margin=1.0):
    """Via-stitch the top and bottom copies of every high-current pour."""
    obstacles = []
    for fp in b.GetFootprints():
        for pd in fp.Pads():
            bb = pd.GetBoundingBox()
            obstacles.append((ToMM(bb.GetLeft()) - OX, ToMM(bb.GetTop()) - OY, ToMM(bb.GetRight()) - OX, ToMM(bb.GetBottom()) - OY))
    for t in b.GetTracks():
        x1, y1 = ToMM(t.GetStart().x) - OX, ToMM(t.GetStart().y) - OY
        x2, y2 = ToMM(t.GetEnd().x) - OX, ToMM(t.GetEnd().y) - OY
        obstacles.append((min(x1, x2) - 0.3, min(y1, y2) - 0.3, max(x1, x2) + 0.3, max(y1, y2) + 0.3))
    count = 0
    for (n, layers, poly, prio) in ZONES:
        if n == "GND" or layers != "FB":
            continue
        xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
        y = min(ys) + margin
        while y <= max(ys) - margin:
            x = min(xs) + margin
            while x <= max(xs) - margin:
                ok = all(inside(poly, x + dx, y + dy) for dx in (-margin, margin) for dy in (-margin, margin))
                ok = ok and not any(o[0] - 0.9 < x < o[2] + 0.9 and o[1] - 0.9 < y < o[3] + 0.9 for o in obstacles)
                if ok:
                    v = pcbnew.PCB_VIA(b)
                    v.SetPosition(pt(x, y)); v.SetWidth(pcbnew.F_Cu, FromMM(0.8)); v.SetDrill(FromMM(0.4))
                    v.SetNet(nets[n]); v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetLocked(True)
                    b.Add(v)
                    count += 1
                x += pitch
            y += pitch
    print("stitching vias:", count)


def silk(b):
    def txt(s, x, y, size=1.2, layer=pcbnew.F_SilkS):
        t = pcbnew.PCB_TEXT(b)
        t.SetText(s); t.SetPosition(pt(x, y)); t.SetLayer(layer)
        t.SetTextSize(VECTOR2I(FromMM(size), FromMM(size))); t.SetTextThickness(FromMM(size * 0.15))
        b.Add(t)
    for ref, label, dx, dy in [("J1", "BATT+", 0, -6.4), ("J2", "BATT-", 0, 6.2), ("J3", "CHG+", 0, -7.3), ("J4", "CHG-", 0, -6.3),
                               ("J5", "LOAD+", 0, 6.2), ("J6", "LOAD-", 0, 6.2), ("J14", "FUSE", 0, 6.6)]:
        x, y = PL[ref][0], PL[ref][1]
        txt(label, x + dx, y + dy, 1.3)
    txt("FRC BATTERY IR NODE  rev B 120A", 22, 78.3, 1.3)
    txt("F2: 60A MIDI FUSE BOLTS HERE", 26, 27, 1.0)
    txt("F1 10A", 85.4, 23.6, 0.9)
    txt("CAN A", 55, 61.5, 1.0); txt("CAN B", 77.5, 61.5, 1.0)
    txt("TERM", 84, 47, 0.9);
    txt("RST", 30, 60, 0.8); txt("BOOT", 30, 68, 0.8)


if __name__ == "__main__":
    b, nets = build()
    pcbnew.SaveBoard(os.path.join(HW, "ir_node.kicad_pcb"), b)
    print("placed", len(D.PARTS), "footprints,", len(nets), "nets")
