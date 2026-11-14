"""Generate hw/ir_node.kicad_sch (KiCad 9) from design.py. Connections are made with net labels."""
import os, sys, uuid, json, math
sys.path.insert(0, os.path.dirname(__file__))
from sexp import Q, parse, dump, find, first, get_symbol, sym_pins, sym_units
import design as D

HW = os.path.join(os.path.dirname(__file__), "..", "hw")
os.makedirs(HW, exist_ok=True)
NS = uuid.UUID("6f1d2c1e-0000-4000-8000-00000000f1c0")
G = 1.27


def uid(s):
    return Q(str(uuid.uuid5(NS, s)))


ROOT = str(uuid.uuid5(NS, "root-sheet"))


def snap(v):
    return round(round(v / G) * G, 4)


FONT = ["effects", ["font", ["size", 1.27, 1.27]]]


def custom_symbol(name, ref, pins, w=7.62, desc=""):
    """pins: [(number, name, etype, side, slot)] side in LRTB"""
    nl = max([p[4] for p in pins if p[3] in "LR"] + [0]) + 1
    h = max(2, nl) * 2.54 / 2 + 1.27
    body = ["symbol", Q(name + "_0_1"),
            ["rectangle", ["start", -w, h], ["end", w, -h], ["stroke", ["width", 0.254], ["type", "default"]],
             ["fill", ["type", "background"]]]]
    ps = ["symbol", Q(name + "_1_1")]
    for num, pname, et, side, slot in pins:
        if side == "L":
            at = [-w - 2.54, h - 1.27 - slot * 2.54, 0]
        elif side == "R":
            at = [w + 2.54, h - 1.27 - slot * 2.54, 180]
        elif side == "T":
            at = [slot * 2.54, h + 2.54, 270]
        else:
            at = [slot * 2.54, -h - 2.54, 90]
        ps.append(["pin", et, "line", ["at"] + at, ["length", 2.54],
                   ["name", Q(pname), FONT], ["number", Q(num), FONT]])

    def prop(k, v, hide=True):
        e = ["effects", ["font", ["size", 1.27, 1.27]]] + ([["hide", "yes"]] if hide else [])
        return ["property", Q(k), Q(v), ["at", 0, 0, 0], e]
    return ["symbol", Q("IRNode:" + name), ["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"],
            prop("Reference", ref, False), prop("Value", name, False), prop("Footprint", ""),
            prop("Datasheet", ""), prop("Description", desc), body, ps]


CUSTOM = {
    "IRNode:UCC27517DBV": custom_symbol("UCC27517DBV", "U", [
        ("1", "VDD", "power_in", "T", 0), ("2", "GND", "power_in", "B", 0),
        ("3", "IN+", "input", "L", 0), ("4", "IN-", "input", "L", 1), ("5", "OUT", "output", "R", 0)],
        desc="4 A single low-side gate driver, SOT-23-5 (TI SLUSAY4 pinout)"),
    "IRNode:PESD2CAN": custom_symbol("PESD2CAN", "D", [
        ("1", "CANH", "passive", "L", 0), ("2", "CANL", "passive", "L", 1), ("3", "GND", "passive", "R", 0)],
        desc="Dual bidirectional CAN ESD diode, SOT-23"),
}

libsyms = {}


def symdef(lib_id):
    if lib_id not in libsyms:
        if lib_id in CUSTOM:
            libsyms[lib_id] = CUSTOM[lib_id]
        else:
            lib, name = lib_id.split(":")
            libsyms[lib_id] = get_symbol(lib, name)
    return libsyms[lib_id]


OUT = {0: (-1, 0), 180: (1, 0), 90: (0, 1), 270: (0, -1)}   # outward dir on screen for pin angle
STUB = 2.54


def lablen(t):
    return len(t) * 1.05 + 1.5


def cell_geometry(part):
    """returns list of unit-cells: (unit, pins, bbox) with bbox relative to symbol origin (screen coords)"""
    sd = symdef(part["sym"])
    allp = sym_pins(sd)
    cells = []
    for u in sym_units(sd):
        pins = [p for p in allp if p[0] in (0, u)]
        xs, ys, bx, by = [0], [0], [0], [0]
        for (_, num, nm, et, px, py, ang, ln) in pins:
            sx, sy = px, -py
            dx, dy = OUT[ang]
            net = part["pins"].get(num, "?")
            ext = STUB + (lablen(net) if isinstance(net, str) else 1.5)
            xs += [sx, sx + dx * ext]
            ys += [sy, sy + dy * ext]
            bx.append(sx - dx * ln)
            by.append(sy - dy * ln)
        vertical = all(p[6] in (90, 270) for p in pins) and len(pins) <= 2
        if vertical:
            xs += [-4, 4 + max(lablen(part["value"]), lablen(part["ref"]))]
        else:
            ys += [min(by) - 6, max(by) + 7]
            xs += [min(bx) + lablen(part["value"])]
        cells.append((u, pins, (min(xs), min(ys), max(xs), max(ys)), (min(bx), min(by), max(bx), max(by)), vertical))
    return cells


items = []          # schematic body s-expressions
placed_nets = {}


def place_part(part, u, pins, x, y, body, vertical):
    sd = symdef(part["sym"])
    ref = part["ref"]
    inst = ["symbol", ["lib_id", Q(part["sym"])], ["at", x, y, 0], ["unit", u],
            ["exclude_from_sim", "no"], ["in_bom", "yes" if part["asm"] != "none" else "no"],
            ["on_board", "yes"], ["dnp", "no"], ["uuid", uid("sym:%s:%d" % (ref, u))]]
    if vertical:
        rp, vp, just = (x + 2.54, y - 1.27), (x + 2.54, y + 1.27), ["justify", "left"]
    else:
        rp, vp, just = (x + body[0], y + body[1] - 3.2), (x + body[0], y + body[3] + 3.4), ["justify", "left"]

    def prop(k, v, pos=None, hide=False):
        e = ["effects", ["font", ["size", 1.27, 1.27]]]
        if pos:
            e.append(just)
        if hide:
            e.append(["hide", "yes"])
        p = pos or (x, y)
        return ["property", Q(k), Q(v), ["at", round(p[0], 3), round(p[1], 3), 0], e]
    inst += [prop("Reference", ref, rp), prop("Value", part["value"], vp),
             prop("Footprint", part["fp"], hide=True), prop("Datasheet", "", hide=True),
             prop("Description", part.get("note", ""), hide=True),
             prop("LCSC", part["lcsc"], hide=True), prop("MPN", part["mpn"], hide=True)]
    for (_, num, nm, et, px, py, ang, ln) in pins:
        inst.append(["pin", Q(num), ["uuid", uid("pin:%s:%d:%s" % (ref, u, num))]])
    inst.append(["instances", ["project", Q(D.PROJECT), ["path", Q("/" + ROOT), ["reference", Q(ref)], ["unit", u]]]])
    items.append(inst)
    seen = set()
    for (_, num, nm, et, px, py, ang, ln) in pins:
        sx, sy = round(x + px, 4), round(y - py, 4)
        if (sx, sy) in seen:
            continue
        seen.add((sx, sy))
        if num not in part["pins"]:
            raise SystemExit("pin %s.%s (%s) has no net assignment" % (ref, num, nm))
        net = part["pins"][num]
        if net is None:
            items.append(["no_connect", ["at", sx, sy], ["uuid", uid("nc:%s:%s" % (ref, num))]])
            continue
        dx, dy = OUT[ang]
        ex, ey = round(sx + dx * STUB, 4), round(sy + dy * STUB, 4)
        items.append(["wire", ["pts", ["xy", sx, sy], ["xy", ex, ey]], ["stroke", ["width", 0], ["type", "default"]],
                      ["uuid", uid("w:%s:%d:%s" % (ref, u, num))]])
        lang = {(-1, 0): 180, (1, 0): 0, (0, -1): 90, (0, 1): 270}[(dx, dy)]
        jj = ["justify", "right", "bottom"] if lang in (180, 270) else ["justify", "left", "bottom"]
        items.append(["label", Q(net), ["at", ex, ey, lang], ["effects", ["font", ["size", 1.27, 1.27]], jj],
                      ["uuid", uid("l:%s:%d:%s" % (ref, u, num))]])
        placed_nets.setdefault(net, []).append(ref + "." + num)


def text(s, x, y, size=1.5, bold=False):
    f = ["font", ["size", size, size]] + ([["bold", "yes"]] if bold else [])
    items.append(["text", Q(s), ["exclude_from_sim", "no"], ["at", round(x, 2), round(y, 2), 0],
                  ["effects", f, ["justify", "left", "top"]], ["uuid", uid("t:" + s[:40] + str(x) + str(y))]])


def wrap(s, n):
    out, line = [], ""
    for w in s.split():
        if len(line) + len(w) + 1 > n:
            out.append(line)
            line = w
        else:
            line = (line + " " + w).strip()
    return "\n".join(out + [line])


# ---------------------------------------------------------------- layout
PAGE_W, PAGE_H = 841, 594      # A1 landscape
COLS = [(15, 400), (425, 400)]
MARGIN_TOP = 15
blocks = []
for p in D.PARTS:
    if p["block"] not in blocks:
        blocks.append(p["block"])

# power flags as pseudo-parts in the supply block
flag_parts = [dict(ref="#FLG%02d" % (i + 1), sym="power:PWR_FLAG", value="PWR_FLAG", fp="", pins={"1": n},
                   block=blocks[2], lcsc="", mpn="", asm="none") for i, n in enumerate(D.POWER_FLAG_NETS)]

col, cy = 0, MARGIN_TOP
maxy = 0
for b in blocks:
    parts = [p for p in D.PARTS if p["block"] == b] + [f for f in flag_parts if f["block"] == b]
    # big parts first
    cells = []
    for p in parts:
        for (u, pins, bb, body, vert) in cell_geometry(p):
            cells.append((p, u, pins, bb, body, vert))
    cells.sort(key=lambda c: -(c[3][3] - c[3][1]) if not c[5] else 0)
    x0, W = COLS[col]
    note = wrap(D.NOTES[b[0]], 150)
    hdr = 8 + 3.2 * (note.count("\n") + 1) + 6

    def flow(y0):
        out, cx, cyy, rowh = [], x0 + 6, y0 + hdr, 0
        for (p, u, pins, bb, body, vert) in cells:
            w, h = bb[2] - bb[0] + 7, bb[3] - bb[1] + 6
            if cx + w > x0 + W - 4 and cx > x0 + 6:
                cx, cyy, rowh = x0 + 6, cyy + rowh, 0
            out.append((p, u, pins, snap(cx - bb[0]), snap(cyy - bb[1]), body, vert))
            cx += w
            rowh = max(rowh, h)
        return out, cyy + rowh + 4
    placed, yend = flow(cy)
    if yend > PAGE_H - 25 and col + 1 < len(COLS):
        col, cy = col + 1, MARGIN_TOP
        x0, W = COLS[col]
        placed, yend = flow(cy)
    for (p, u, pins, x, y, body, vert) in placed:
        place_part(p, u, pins, x, y, body, vert)
    items.append(["rectangle", ["start", x0, cy], ["end", x0 + W, round(yend, 2)],
                  ["stroke", ["width", 0.25], ["type", "dash"]], ["fill", ["type", "none"]], ["uuid", uid("rect:" + b)]])
    text("BLOCK " + b, x0 + 3, cy + 2.5, 2.6, True)
    text(note, x0 + 3, cy + 8, 1.6)
    cy = yend + 6
    maxy = max(maxy, yend)

print("sheet extents: max y = %.0f (page %d), last column %d" % (maxy, PAGE_H, col))

sch = ["kicad_sch", ["version", 20250114], ["generator", Q("eeschema")], ["generator_version", Q("9.0")],
       ["uuid", Q(ROOT)], ["paper", Q("A1")],
       ["title_block", ["title", Q("FRC Battery IR Monitor Node")], ["date", Q("2026-11-14")], ["rev", Q("A")],
        ["company", Q("generated from tools/design.py")],
        ["comment", 1, Q("charger -> [node] -> battery; pulse-load IR test; CAN to pit hub")]],
       ["lib_symbols"] + [libsyms[k] for k in sorted(libsyms)]] + items + [
       ["sheet_instances", ["path", Q("/"), ["page", Q("1")]]], ["embedded_fonts", "no"]]

with open(os.path.join(HW, D.PROJECT + ".kicad_sch"), "w", encoding="utf8", newline="\n") as f:
    f.write(dump(sch) + "\n")

single = {n: v for n, v in placed_nets.items() if len(v) < 2}
print("nets:", len(placed_nets), " single-pin nets:", single)

pro = os.path.join(HW, D.PROJECT + ".kicad_pro")
if not os.path.exists(pro):
    with open(pro, "w") as f:
        json.dump({"meta": {"filename": D.PROJECT + ".kicad_pro", "version": 3}}, f, indent=2)
print("wrote schematic with", len(D.PARTS), "parts")

# project-local symbol library for the two custom symbols
import copy
lib = ["kicad_symbol_lib", ["version", 20241209], ["generator", Q("ir_node_gen")], ["generator_version", Q("9.0")]]
for k, v in CUSTOM.items():
    s = copy.deepcopy(v)
    s[1] = Q(k.split(":")[1])
    lib.append(s)
with open(os.path.join(HW, "IRNode.kicad_sym"), "w", encoding="utf8", newline="\n") as f:
    f.write(dump(lib) + "\n")
with open(os.path.join(HW, "sym-lib-table"), "w", encoding="utf8", newline="\n") as f:
    f.write('(sym_lib_table\n  (version 7)\n  (lib (name "IRNode")(type "KiCad")(uri "${KIPRJMOD}/IRNode.kicad_sym")(options "")(descr "IR node custom symbols"))\n)\n')
