"""Produce fab/ outputs: BOM (full + JLC format, with live stock), CPL, Gerbers + drill zip, renders."""
import os, re, sys, csv, subprocess, zipfile, glob, shutil
sys.path.insert(0, os.path.dirname(__file__))
import wx
wx.DisableAsserts()
import pcbnew
import design as D
import jlc

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HW = os.path.join(ROOT, "hw")
FAB = os.path.join(ROOT, "fab")
REN = os.path.join(ROOT, "renders")
CLI = r"C:\Users\Ryan\AppData\Local\Programs\KiCad\9.0\bin\kicad-cli.exe"
PCB = os.path.join(HW, "ir_node.kicad_pcb")
os.makedirs(FAB, exist_ok=True)
os.makedirs(REN, exist_ok=True)


def natural(ref):
    import re
    m = re.match(r"([A-Za-z#]+)(\d+)", ref)
    return (m.group(1), int(m.group(2)))


def bom():
    groups = {}
    for p in D.PARTS:
        if p["asm"] == "none":
            continue
        key = (p["value"], p["fp"], p["lcsc"], p["mpn"], p["asm"])
        groups.setdefault(key, []).append(p)
    rows, jl = [], []
    total = 0.0
    for (value, fp, lcsc, mpn, asm), ps in sorted(groups.items(), key=lambda kv: natural(kv[1][0]["ref"])):
        refs = sorted((p["ref"] for p in ps), key=natural)
        stock, lib, live_price, live_mpn = "", "", None, ""
        if lcsc:
            hit = [c for c in jlc.search(lcsc, 5) if c.get("componentCode") == lcsc]
            if hit:
                r = jlc.row(hit[0])
                stock, lib, live_price, live_mpn = r["stock"], ("basic" if r["lib"] == "base" else "extended"), r["price"], r["mpn"]
        price = live_price if live_price is not None else ps[0]["price"]
        ext = price * len(refs)
        total += ext
        rows.append([",".join(refs), len(refs), value, mpn, live_mpn, fp.split(":")[1], lcsc, lib, stock,
                     "JLC SMT" if asm == "smt" else "hand-solder / THT", "%.4f" % price, "%.3f" % ext])
        if asm == "smt":
            jl.append([value, ",".join(refs), fp.split(":")[1], lcsc])
    with open(os.path.join(FAB, "ir_node_BOM_full.csv"), "w", newline="", encoding="utf8") as f:
        w = csv.writer(f)
        w.writerow(["Designators", "Qty", "Value", "MPN (design)", "MPN (JLC listing)", "Footprint", "LCSC", "JLC library",
                    "JLC stock (live)", "Assembly", "Unit USD (qty 1)", "Ext USD"])
        w.writerows(rows)
        w.writerow([])
        w.writerow(["TOTAL parts cost per board (qty-1 pricing, excl. PCB, assembly fees, off-board items)", "", "", "", "",
                    "", "", "", "", "", "", "%.2f" % total])
    with open(os.path.join(FAB, "ir_node_BOM_JLC.csv"), "w", newline="", encoding="utf8") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        w.writerows(jl)
    nb = sum(1 for r in rows if r[7] == "basic")
    ne = sum(1 for r in rows if r[7] == "extended")
    zero = [r for r in rows if r[6] and (r[8] == "" or r[8] == 0)]
    print("BOM lines: %d (basic %d, extended %d, no-LCSC %d)  total $%.2f" % (len(rows), nb, ne, len(rows) - nb - ne, total))
    print("lines with zero/unknown stock:", [(r[0], r[6]) for r in zero])
    for r in rows:
        print("  %-28s %-3s %-30s %-10s %-9s stock %s" % (r[0][:28], r[1], (r[4] or r[3])[:30], r[6], r[7], r[8]))


# JLC's part models for some packages sit at a different zero rotation from KiCad's footprints.
# These offsets (degrees, counter-clockwise positive, added to KiCad's rotation) were measured in
# JLC's placement viewer on 14 Nov 2026 by lining up each model's pin-1 dot with the footprint's
# pin-1 marker. Footprints not listed (diodes, LEDs, passives, CP_Elec, ESP32-S3-WROOM-1, USB-C)
# were checked and need no offset.
JLC_ROT = {
    "SOT-23": 180,
    "SOT-23-5": 180,
    "SOT-23-6": -90,
    "TSOT-23-6": -90,
    "SOIC-8_3.9x4.9mm_P1.27mm": -90,
    "VSSOP-10_3x3mm_P0.5mm": -90,
    "SSOP-8_2.95x2.8mm_P0.65mm": 180,
}


def jlc_rot(rot, fp):
    r = (float(rot) + JLC_ROT.get(fp.split(":")[1], 0)) % 360
    return "%.6f" % (r - 360 if r > 180 else r)


def cpl():
    smt = {p["ref"] for p in D.PARTS if p["asm"] == "smt"}
    fps = {p["ref"]: p["fp"] for p in D.PARTS}
    tmp = os.path.join(FAB, "_pos.csv")
    subprocess.run([CLI, "pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "front",
                    "--exclude-dnp", "-o", tmp, PCB], check=True, capture_output=True)
    out = []
    with open(tmp, encoding="utf8") as f:
        for r in csv.DictReader(f):
            if r["Ref"] in smt:
                out.append([r["Ref"], r["PosX"], r["PosY"], "Top", jlc_rot(r["Rot"], fps[r["Ref"]])])
    os.remove(tmp)
    out.sort(key=lambda r: natural(r[0]))
    with open(os.path.join(FAB, "ir_node_CPL_JLC.csv"), "w", newline="", encoding="utf8") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        w.writerows(out)
    missing = smt - {r[0] for r in out}
    print("CPL rows:", len(out), "missing:", missing)


# ---------------------------------------------------------------------------------- PCBWay
# PCBWay buys parts by manufacturer part number and its engineers review the BOM by hand, so the
# BOM carries manufacturer + MPN, the LCSC number as a sourcing reference, and what may be
# substituted. Keyed by LCSC number.
ANY_R = "Any 0603 1% thick-film resistor of the same value"
ANY_C = "Any X5R/X7R MLCC of the same value, voltage and package"
NO_SUB = "No substitute without asking"
PCBWAY_ALT = {
    "C14663": ANY_C, "C13585": ANY_C, "C45783": ANY_C, "C15849": ANY_C,
    "C23630": "Any X5R/X7R 2.2 uF 10% 16 V or higher 0603 (sets the one-shot timeout)",
    "C2836442": "Panasonic EEE-FK1V101XP, or any 100 uF 35 V 6.3 x 7.7 mm SMD electrolytic",
    "C81598": "Any 1N4148W, SOD-123",
    "C24138": "Any SS56 (5 A 60 V Schottky), SMC / DO-214AB",
    "C151922": "Any SMBJ20A (unidirectional), e.g. Littelfuse SMBJ20A",
    "C8678": "Any SS34 (3 A 40 V Schottky), SMA / DO-214AC",
    "C8598": "Any B5819W / 1N5819HW, SOD-123",
    "C43491": "Any BZT52C12 (12 V zener), SOD-123",
    "C2687131": "Nexperia PESD2CAN,215",
    "C2286": "Any 0603 red LED", "C12624": "Any 0603 green LED", "C2288": "Any 0603 blue LED",
    "C136391": "Littelfuse 0451010.MRL (10 A 125 V fast, Nano2)",
    "C710260": "0.5 mOhm 1% 2512 metal-strip shunt, 3 W or more, 75 ppm/K or better; ask before substituting",
    "C2892547": "Any 0603 NTC 10 k 1% with B25/50 = 3950 K (firmware uses B = 3950)",
    "C38117": "Ask before substituting (10 uH shielded, Isat 1.5 A or more, same 4 x 4 mm pads)",
    "C20079": "JST B2B-XH-A", "C5663": "JST B6B-XH-A",
}
for _c in ("C25804", "C23164", "C22859", "C23162", "C23179", "C25803", "C21190", "C23186", "C22787", "C22775", "C25967"):
    PCBWAY_ALT[_c] = ANY_R
PCBWAY_NOTE = {
    "Q1": "Push fully down onto the board before soldering so the legs are as short as possible (120 A pulse)",
    "J11": "Optional connector; fit it",
    "K1": "12 V coil, 16 A high-capacity version (-E)",
    "U1": "4 MB flash version (N4). N8/N16 also work",
    "R1": "Current-sense shunt: value and tolerance are critical",
}
HEADERS = {"J7": ("Generic", "2.54 mm male pin header, 1x3, straight", "PinHeader 1x03 P2.54mm"),
           "JP1": ("Generic", "2.54 mm male pin header, 1x2, straight (no jumper cap)", "PinHeader 1x02 P2.54mm")}


def pcbway():
    """fab/pcbway/: BOM by manufacturer part number (SMT only, and a version that also has the
    through-hole parts) and a placement file with KiCad's own rotations (no JLC offsets)."""
    out = os.path.join(FAB, "pcbway")
    os.makedirs(out, exist_ok=True)
    groups = {}
    for p in D.PARTS:
        if p["asm"] != "none":
            groups.setdefault((p["value"], p["fp"], p["lcsc"], p["mpn"], p["asm"]), []).append(p)
    rows, problems = [], []
    for (value, fp, lcsc, mpn, asm), ps in sorted(groups.items(), key=lambda kv: natural(kv[1][0]["ref"])):
        refs = sorted((p["ref"] for p in ps), key=natural)
        plain = re.sub(r"\s*\(.*?\)", "", value)
        mfr, part, desc, stock = "", mpn, plain, ""
        if lcsc:
            hit = [c for c in jlc.search(lcsc, 5) if c.get("componentCode") == lcsc]
            if hit:
                r = jlc.row(hit[0])
                mfr, part, stock = r["brand"], r["mpn"], r["stock"]
                desc = "%s; %s" % (plain, r["desc"].replace("插件", "THT")) if r["desc"] else plain
            if not hit or not stock or stock < 500 and asm == "smt":
                problems.append((refs[0], lcsc, stock))
        else:
            mfr, part, _ = HEADERS[refs[0]]
            desc = plain
        note = PCBWAY_NOTE.get(refs[0], "")
        rows.append([",".join(refs), len(refs), mfr, part, desc, fp.split(":")[1], "SMD" if asm == "smt" else "THT",
                     lcsc, PCBWAY_ALT.get(lcsc, "Generic part, any make" if not lcsc else NO_SUB), note])
    hdr = ["Item", "Designator", "Qty", "Manufacturer", "Mfg Part #", "Description / Value", "Package / Footprint",
           "Type", "LCSC # (reference)", "Acceptable substitute", "Notes"]
    for name, keep in (("ir_node_BOM_PCBWay.csv", ("SMD",)), ("ir_node_BOM_PCBWay_with_THT.csv", ("SMD", "THT"))):
        with open(os.path.join(out, name), "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(hdr)
            for i, r in enumerate([r for r in rows if r[6] in keep], 1):
                w.writerow([i] + r)

    val = {p["ref"]: p["value"] for p in D.PARTS}
    fps = {p["ref"]: p["fp"].split(":")[1] for p in D.PARTS}
    smt = {p["ref"] for p in D.PARTS if p["asm"] == "smt"}
    tmp = os.path.join(out, "_pos.csv")
    subprocess.run([CLI, "pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "front",
                    "--exclude-dnp", "-o", tmp, PCB], check=True, capture_output=True)
    pos = []
    with open(tmp, encoding="utf8") as f:
        for r in csv.DictReader(f):
            if r["Ref"] in smt:
                pos.append([r["Ref"], val[r["Ref"]], fps[r["Ref"]], r["PosX"], r["PosY"], r["Rot"], "Top"])
    os.remove(tmp)
    pos.sort(key=lambda r: natural(r[0]))
    with open(os.path.join(out, "ir_node_CPL_PCBWay.csv"), "w", newline="", encoding="utf8") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Value", "Package", "Mid X (mm)", "Mid Y (mm)", "Rotation", "Layer"])
        w.writerows(pos)
    bom_refs = {x for r in rows if r[6] == "SMD" for x in r[0].split(",")}
    print("PCBWay BOM lines: %d SMD + %d THT; CPL rows %d; BOM/CPL designator mismatch: %s" % (
        sum(1 for r in rows if r[6] == "SMD"), sum(1 for r in rows if r[6] == "THT"), len(pos),
        sorted(bom_refs ^ {r[0] for r in pos}) or "none"))
    print("not found / low stock at LCSC-JLC:", problems or "none")


def gerbers():
    g = os.path.join(FAB, "gerbers")
    shutil.rmtree(g, ignore_errors=True)
    os.makedirs(g)
    subprocess.run([CLI, "pcb", "export", "gerbers", "--layers",
                    "F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts",
                    "--subtract-soldermask", "--no-protel-ext", "-o", g + os.sep, PCB], check=True, capture_output=True)
    subprocess.run([CLI, "pcb", "export", "drill", "--format", "excellon", "--excellon-separate-th",
                    "--excellon-units", "mm", "--generate-map", "--map-format", "pdf", "-o", g + os.sep, PCB],
                   check=True, capture_output=True)
    z = os.path.join(FAB, "ir_node_gerbers.zip")
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(glob.glob(os.path.join(g, "*"))):
            if not f.endswith(".pdf") and not f.endswith(".gbrjob"):
                zf.write(f, os.path.basename(f))
    print("gerber files:", sorted(os.path.basename(f) for f in glob.glob(os.path.join(g, "*"))))


def renders():
    for side in ("top", "bottom"):
        r = subprocess.run([CLI, "pcb", "render", "--side", side, "--width", "2000", "--height", "1600",
                            "--quality", "basic", "-o", os.path.join(REN, "3d_%s.png" % side), PCB],
                           capture_output=True, text=True)
        print("3d", side, r.returncode, (r.stderr or "")[-200:])
    subprocess.run([CLI, "pcb", "export", "pdf", "--layers", "F.Cu,B.Cu,F.SilkS,F.Fab,Edge.Cuts", "--mode-separate",
                    "--include-border-title", "-o", os.path.join(FAB, "layers_pdf") + os.sep, PCB], capture_output=True)
    subprocess.run([CLI, "sch", "export", "pdf", "-o", os.path.join(HW, "ir_node_schematic.pdf"),
                    os.path.join(HW, "ir_node.kicad_sch")], capture_output=True)


if __name__ == "__main__":
    what = sys.argv[1:] or ["bom", "cpl", "gerbers", "renders"]
    for w in what:
        globals()[w]()
