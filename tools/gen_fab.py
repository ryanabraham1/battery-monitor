"""Produce fab/ outputs: BOM (full + JLC format, with live stock), CPL, Gerbers + drill zip, renders."""
import os, sys, csv, subprocess, zipfile, glob, shutil
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


def cpl():
    b = pcbnew.LoadBoard(PCB)
    smt = {p["ref"] for p in D.PARTS if p["asm"] == "smt"}
    tmp = os.path.join(FAB, "_pos.csv")
    subprocess.run([CLI, "pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "front",
                    "--exclude-dnp", "-o", tmp, PCB], check=True, capture_output=True)
    out = []
    with open(tmp, encoding="utf8") as f:
        for r in csv.DictReader(f):
            if r["Ref"] in smt:
                out.append([r["Ref"], r["PosX"], r["PosY"], "Top", r["Rot"]])
    os.remove(tmp)
    out.sort(key=lambda r: natural(r[0]))
    with open(os.path.join(FAB, "ir_node_CPL_JLC.csv"), "w", newline="", encoding="utf8") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        w.writerows(out)
    missing = smt - {r[0] for r in out}
    print("CPL rows:", len(out), "missing:", missing)


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
