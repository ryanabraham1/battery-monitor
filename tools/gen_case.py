"""Generate the 3D-printable enclosure parts as STL files in case/.

    pip install manifold3d numpy pillow matplotlib
    python tools/gen_case.py

Parts (all print without supports, flat face on the bed, in the orientation they are saved):
    node_base.stl   tray the PCB sits in, with two screw-down ears
    node_lid.stl    cover, saved upside down (print as-is)
    nfc_holder.stl  optional: shallow tray for a PN532 breakout; the tag is read through its floor
    pi_tray.stl     open tray for the Raspberry Pi + CAN HAT

Four M3x16 screws go up through the base and the PCB and self-tap into posts in the lid.
All positions come from the board layout (tools/gen_pcb.py); PCB y runs downward, so
case y = 80 - pcb y.
"""
import os
import struct
import sys

import numpy as np
from manifold3d import CrossSection, FillRule, Manifold, OpType, set_circular_segments

set_circular_segments(48)
OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "case"))

# ---- board ----
BW, BH, PCB_T = 100.0, 80.0, 1.6
HOLES = [(3.5, 3.5), (96.5, 3.5), (3.5, 76.5), (96.5, 76.5)]

# ---- enclosure parameters (mm) ----
GAP = 0.6         # PCB edge to inner wall
WALL = 2.4
FLOOR = 2.0
STANDOFF = 6.0    # room under the PCB for through-hole leads and the M4 nuts/screw heads
HEAD_ROOM = 27.0  # above the PCB: the TO-220 (~20) and the M5 fuse studs (~19) are the tallest
TOP = 2.0
LIP = 2.0         # shiplap height between base and lid
FIT = 0.25        # clearance on mating faces
SCREW_CLEAR = 3.4
SCREW_HEAD = 6.4
SCREW_PILOT = 2.6  # M3 self-tapping into the lid posts
POST_D = 7.0
EAR_HOLE = 4.5

Z_PCB_TOP = FLOOR + STANDOFF + PCB_T          # split line between base and lid
Z_LID_IN = Z_PCB_TOP + HEAD_ROOM              # underside of the lid top
Z_TOP = Z_LID_IN + TOP
X0, X1 = -GAP - WALL, BW + GAP + WALL
Y0, Y1 = -GAP - WALL, BH + GAP + WALL


def box(x0, x1, y0, y1, z0, z1):
    return Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])


def pbox(x0, x1, py0, py1, z0, z1):
    """Box given in PCB coordinates (y down)."""
    return box(x0, x1, BH - py1, BH - py0, z0, z1)


def cyl(x, y, d, z0, z1):
    return Manifold.cylinder(z1 - z0, d / 2).translate([x, y, z0])


def pcyl(x, py, d, z0, z1):
    return cyl(x, BH - py, d, z0, z1)


def text(s, x, y, size, depth, z_top, halign="center"):
    """Engraving solid for string s, centred at (x, y) in case coordinates."""
    from matplotlib.font_manager import FontProperties
    from matplotlib.textpath import TextPath
    tp = TextPath((0, 0), s, size=size, prop=FontProperties(family="DejaVu Sans", weight="bold"))
    polys = [np.asarray(p[:-1], dtype=np.float64) for p in tp.to_polygons() if len(p) > 3]
    cs = CrossSection(polys, FillRule.EvenOdd)
    bx0, by0, bx1, by1 = cs.bounds()
    dx = {"center": -(bx0 + bx1) / 2, "left": -bx0, "right": -bx1}[halign]
    return Manifold.extrude(cs.translate([x + dx, y - (by0 + by1) / 2]), depth + 0.01).translate([0, 0, z_top - depth])


# ---- openings shared by base lip and lid: (wall, centre along wall in PCB coords, width, z below PCB top, z above) ----
OPENINGS = [
    ("bottom", 41.0, 13.0, 2.4, 6.0),    # USB-C: the plug overmold has to pass through the wall
    ("bottom", 58.57, 17.0, 0.4, 14.2),  # RJ45 J9
    ("bottom", 81.07, 17.0, 0.4, 14.2),  # RJ45 J10
    ("left", 10.0, 11.0, 0.0, 11.0),     # BATT- (sized for 6-8 AWG)
    ("left", 27.0, 11.0, 0.0, 11.0),     # BATT+
    ("left", 43.0, 5.0, 0.0, 7.0),       # thermostat lead (J13)
    ("right", 13.0, 9.5, 0.0, 9.5),      # CHG+
    ("right", 30.0, 9.5, 0.0, 9.5),      # CHG-
    ("right", 52.0, 12.0, 0.0, 5.0),     # PN532 6-wire lead
    ("top", 33.0, 11.0, 0.0, 11.0),      # LOAD-
    ("top", 57.0, 11.0, 0.0, 11.0),      # LOAD+
]


def opening_cuts():
    cuts = []
    for wall, c, w, below, above in OPENINGS:
        z0, z1 = Z_PCB_TOP - below, Z_PCB_TOP + above
        if wall == "bottom":
            cuts.append(pbox(c - w / 2, c + w / 2, BH - 1, BH + GAP + WALL + 1, z0, z1))
        elif wall == "top":
            cuts.append(pbox(c - w / 2, c + w / 2, -GAP - WALL - 1, 1, z0, z1))
        elif wall == "left":
            cuts.append(pbox(X0 - 1, 1, c - w / 2, c + w / 2, z0, z1))
        else:
            cuts.append(pbox(BW - 1, X1 + 1, c - w / 2, c + w / 2, z0, z1))
    return Manifold.batch_boolean(cuts, OpType.Add)


def node_base():
    m = box(X0, X1, Y0, Y1, 0, Z_PCB_TOP) - box(-GAP, BW + GAP, -GAP, BH + GAP, FLOOR, Z_PCB_TOP + 1)
    # inner half of the wall continues up as an alignment lip
    lip = box(-GAP - WALL / 2, BW + GAP + WALL / 2, -GAP - WALL / 2, BH + GAP + WALL / 2, Z_PCB_TOP, Z_PCB_TOP + LIP) \
        - box(-GAP, BW + GAP, -GAP, BH + GAP, Z_PCB_TOP - 1, Z_PCB_TOP + LIP + 1)
    m += lip
    for hx, hy in HOLES:   # corner blocks the PCB rests on
        m += pbox(-GAP if hx < 50 else hx - 4, hx + 4 if hx < 50 else BW + GAP,
                  -GAP if hy < 40 else hy - 4, hy + 4 if hy < 40 else BH + GAP, FLOOR, FLOOR + STANDOFF)
    for side in (-1, 1):   # screw-down ears
        ex0, ex1 = (X0 - 13, X0) if side < 0 else (X1, X1 + 13)
        m += box(ex0 - (0.5 if side > 0 else 0), ex1 + (0.5 if side < 0 else 0), BH / 2 - 9, BH / 2 + 9, 0, 3.0)
        m -= cyl((ex0 + ex1) / 2, BH / 2, EAR_HOLE, -1, 4)
    for hx, hy in HOLES:
        m -= pcyl(hx, hy, SCREW_CLEAR, -1, Z_PCB_TOP)
        m -= pcyl(hx, hy, SCREW_HEAD, -1, 3.0)      # counterbore: head sits 3 mm up, 5 mm of plastic under the PCB
    return m - opening_cuts()


def node_lid():
    outer = box(X0, X1, Y0, Y1, Z_PCB_TOP, Z_TOP)
    m = outer - box(-GAP, BW + GAP, -GAP, BH + GAP, Z_PCB_TOP - 1, Z_LID_IN)
    # relief for the base lip
    m -= box(-GAP - WALL / 2 - FIT, BW + GAP + WALL / 2 + FIT, -GAP - WALL / 2 - FIT, BH + GAP + WALL / 2 + FIT,
             Z_PCB_TOP - 1, Z_PCB_TOP + LIP + FIT)
    for hx, hy in HOLES:   # posts come down onto the PCB; the screws thread into them
        post = pcyl(hx, hy, POST_D, Z_PCB_TOP + 0.2, Z_LID_IN + 0.1)
        m += post
        # tie the post into the corner so it is not a free-standing pillar while printing
        m += pbox(-GAP - 0.1 if hx < 50 else hx, hx if hx < 50 else BW + GAP + 0.1,
                  -GAP - 0.1 if hy < 40 else hy - 3.5, hy + 3.5 if hy < 40 else BH + GAP + 0.1, Z_PCB_TOP + LIP + FIT, Z_LID_IN + 0.1)
        m += pbox(-GAP - 0.1 if hx < 50 else hx - 3.5, hx + 3.5 if hx < 50 else BW + GAP + 0.1,
                  -GAP - 0.1 if hy < 40 else hy, hy if hy < 40 else BH + GAP + 0.1, Z_PCB_TOP + LIP + FIT, Z_LID_IN + 0.1)
        m -= pcyl(hx, hy, SCREW_PILOT, Z_PCB_TOP, Z_PCB_TOP + 14)
    m -= opening_cuts()
    # top face: LED window, fuse window, BOOT / RESET poke holes
    m -= pbox(18.8, 26.0, 34.4, 39.7, Z_LID_IN - 1, Z_TOP + 1)   # window over the three status LEDs
    m -= pbox(17.0, 35.0, 21.5, 32.5, Z_LID_IN - 1, Z_TOP + 1)   # window over the bolt-down fuse
    m -= pcyl(30.0, 56.0, 3.6, Z_LID_IN - 1, Z_TOP + 1)
    m -= pcyl(30.0, 64.0, 3.6, Z_LID_IN - 1, Z_TOP + 1)
    d = 0.6
    for s, x, py, size, al in [("BATT −", 3, 10, 4.2, "left"), ("BATT +", 3, 18.5, 4.2, "left"),
                               ("CHG +", 97, 13, 4.2, "right"), ("CHG −", 97, 30, 4.2, "right"),
                               ("LOAD −", 33, 4.5, 4.0, "center"), ("LOAD +", 57, 4.5, 4.0, "center"), ("FUSE 60A", 46, 27, 3.6, "left"),
                               ("USB", 41, 75.5, 3.6, "center"), ("CAN", 58.57, 75.5, 3.6, "center"),
                               ("CAN", 81.07, 75.5, 3.6, "center"), ("NFC", 97, 52, 3.6, "right"),
                               ("BOOT", 33.5, 56, 3.0, "left"), ("RST", 33.5, 64, 3.0, "left"),
                               ("TSW", 3, 43, 3.0, "left"), ("FRC BATTERY IR NODE 120A", 52, 47, 4.4, "center")]:
        m -= text(s, x, BH - py, size, d, Z_TOP, al)
    return m


def pcb_mock():
    """Board plus boxes for the tall parts, used only to check that nothing collides with the case."""
    z = Z_PCB_TOP
    parts = [pbox(0, BW, 0, BH, z - PCB_T, z)]
    slab_top = pbox(0, BW, 0, BH, z, z + 3.5)               # generic SMT height everywhere
    slab_bot = pbox(0, BW, 0, BH, z - PCB_T - 4.5, z - PCB_T)  # leads and nuts underneath
    for hx, hy in HOLES:
        k = pbox(hx - 4.05, hx + 4.05, hy - 4.05, hy + 4.05, 0, 60)
        k += pbox(-1 if hx < 50 else hx - 4.05, hx + 4.05 if hx < 50 else BW + 1,
                  -1 if hy < 40 else hy - 4.05, hy + 4.05 if hy < 40 else BH + 1, 0, 60)
        slab_top -= k
        slab_bot -= k
    parts += [slab_top, slab_bot]
    parts.append(pbox(67.2, 80.4, 4.2, 33.7, z, z + 16.0))      # relay
    parts.append(pbox(15.0, 37.0, 20.8, 33.2, z + 3.0, z + 14.0))   # MIDI fuse body on its spacer nuts
    parts.append(pbox(18.6, 23.5, 4.7, 15.3, z, z + 20.5))      # TO-220
    parts.append(pbox(59.9, 67.1, 15.3, 24.7, z, z + 8.5))      # bulk capacitor
    for x in (11, 41):
        parts.append(pcyl(x, 27, 12.0, z, z + 19.5))            # M5 fuse studs with nuts and lug
    for c in (58.57, 81.07):
        parts.append(pbox(c - 8.0, c + 8.0, 62.5, 80.0, z, z + 13.6))   # RJ45
    parts.append(pbox(36.5, 45.5, 72.6, 80.0, z, z + 3.4))      # USB-C
    for x, py in [(11, 10), (33, 10), (57, 10), (91, 13), (91, 30)]:
        parts.append(pcyl(x, py, 10.0, z, z + 9.0))             # M4 lug + screw head / nut
    parts.append(pbox(87.2, 90.8, 45.2, 61.5, z, z + 17.0))     # PN532 header with Dupont housings
    parts.append(pbox(35.0, 43.5, 41.6, 48.4, z, z + 11.0))     # JST-XH + plug (thermostat)
    parts.append(pbox(3.2, 11.9, 37.2, 40.8, z, z + 9.0))       # UART header
    return parts


def nfc_holder(bw=42.7, bh=40.4):
    """PN532 'V3' breakout tray. Sizes are for the common red 42.7 x 40.4 mm module - measure yours."""
    g, w, fl, h = 0.4, 2.0, 1.2, 7.0
    m = box(-g - w, bw + g + w, -g - w, bh + g + w, 0, h) - box(-g, bw + g, -g, bh + g, fl, h + 1)
    m -= box(bw / 2 - 11, bw / 2 + 11, bh - 1, bh + g + w + 1, fl + 1.6, h + 1)   # header / wire exit
    for y in (bh * 0.25, bh * 0.75):                                              # cable-tie slots across the board
        m -= box(-g - w - 1, bw + g + w + 1, y - 2, y + 2, h - 2.2, h + 1)
    for side in (-1, 1):
        ex0, ex1 = (-g - w - 11, -g - w) if side < 0 else (bw + g + w, bw + g + w + 11)
        m += box(ex0 - (0.5 if side > 0 else 0), ex1 + (0.5 if side < 0 else 0), bh / 2 - 7, bh / 2 + 7, 0, 3.0)
        m -= cyl((ex0 + ex1) / 2, bh / 2, EAR_HOLE, -1, 4)
    return m


def pi_tray():
    """Open tray for a Raspberry Pi (B-size boards: 3B+, 4, 5) with a HAT on top. Posts take M2.5 screws."""
    pw, ph, mar, fl, post_h = 85.0, 56.0, 4.0, 2.4, 5.0
    m = box(-mar, pw + mar, -mar, ph + mar, 0, fl)
    for px, py in [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)]:
        m += cyl(px, py, 6.5, fl, fl + post_h)
        m -= cyl(px, py, 2.2, fl + 0.6, fl + post_h + 1)
    m -= box(18, 48, 14, 42, -1, fl + 1)          # airflow / less plastic under the board
    for side in (-1, 1):
        ex0, ex1 = (-mar - 12, -mar) if side < 0 else (pw + mar, pw + mar + 12)
        m += box(ex0 - (0.5 if side > 0 else 0), ex1 + (0.5 if side < 0 else 0), ph / 2 - 8, ph / 2 + 8, 0, fl)
        m -= cyl((ex0 + ex1) / 2, ph / 2, EAR_HOLE, -1, fl + 1)
    return m


def write_stl(m, path):
    mesh = m.to_mesh()
    v = np.asarray(mesh.vert_properties, dtype=np.float32)[:, :3]
    t = np.asarray(mesh.tri_verts, dtype=np.uint32)
    tri = v[t]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    n = n / np.where(ln == 0, 1, ln)
    rec = np.zeros(len(t), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"], rec["v"] = n, tri
    with open(path, "wb") as f:
        f.write(b"FRC battery IR node case".ljust(80, b" "))
        f.write(struct.pack("<I", len(t)))
        f.write(rec.tobytes())
    return tri


def raster(tri, size=(900, 680), elev=38, azim=-62, color=(0.93, 0.55, 0.16)):
    """Small orthographic z-buffer renderer (flat shaded) so previews need nothing beyond numpy + PIL."""
    ss = 2
    W, H = size[0] * ss, size[1] * ss
    a, e = np.radians(azim), np.radians(elev)
    rz = np.array([[np.cos(a), np.sin(a), 0], [-np.sin(a), np.cos(a), 0], [0, 0, 1]])
    rx = np.array([[1, 0, 0], [0, np.sin(e), np.cos(e)], [0, -np.cos(e), np.sin(e)]])
    rot = rx @ rz                       # view space: x right, y up, z toward the camera
    t = tri @ rot.T
    lo, hi = t.reshape(-1, 3).min(0), t.reshape(-1, 3).max(0)
    sc = min((W * 0.92) / (hi[0] - lo[0]), (H * 0.92) / (hi[1] - lo[1]))
    px = (t[:, :, 0] - (lo[0] + hi[0]) / 2) * sc + W / 2
    py = H / 2 - (t[:, :, 1] - (lo[1] + hi[1]) / 2) * sc
    pz = t[:, :, 2]
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    light = np.array([-0.35, 0.55, 0.76])
    shade = 0.30 + 0.70 * np.clip(n @ light, 0, 1) + 0.12 * np.clip(n @ np.array([0.7, 0.1, 0.3]), 0, 1)
    img = np.ones((H, W, 3))
    zbuf = np.full((H, W), -1e9)
    for k in np.nonzero(n[:, 2] > 0)[0]:          # back faces are never visible on a closed solid
        x, y, z = px[k], py[k], pz[k]
        x0, x1 = max(int(np.floor(x.min())), 0), min(int(np.ceil(x.max())) + 1, W)
        y0, y1 = max(int(np.floor(y.min())), 0), min(int(np.ceil(y.max())) + 1, H)
        if x0 >= x1 or y0 >= y1:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
        den = (y[1] - y[2]) * (x[0] - x[2]) + (x[2] - x[1]) * (y[0] - y[2])
        if abs(den) < 1e-12:
            continue
        w0 = ((y[1] - y[2]) * (gx - x[2]) + (x[2] - x[1]) * (gy - y[2])) / den
        w1 = ((y[2] - y[0]) * (gx - x[2]) + (x[0] - x[2]) * (gy - y[2])) / den
        w2 = 1 - w0 - w1
        zz = w0 * z[0] + w1 * z[1] + w2 * z[2]
        sub = zbuf[y0:y1, x0:x1]
        m = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6) & (zz > sub)
        sub[m] = zz[m]
        img[y0:y1, x0:x1][m] = np.clip(np.array(color) * shade[k], 0, 1)
    img = img.reshape(size[1], ss, size[0], ss, 3).mean(axis=(1, 3))
    return (img * 255).astype(np.uint8)


def preview(views, path):
    """views: list of (title, triangles, elev, azim) laid out two per row."""
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype("arial.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    cw, ch = 900, 680
    rows = (len(views) + 1) // 2
    sheet = Image.new("RGB", (cw * 2, (ch + 44) * rows), "white")
    d = ImageDraw.Draw(sheet)
    for k, (title, tri, elev, azim) in enumerate(views):
        x, y = (k % 2) * cw, (k // 2) * (ch + 44)
        sheet.paste(Image.fromarray(raster(tri, (cw, ch), elev, azim)), (x, y + 44))
        d.text((x + 24, y + 12), title, fill=(30, 30, 30), font=font)
    sheet.save(path)


def tris_of(m):
    mesh = m.to_mesh()
    return np.asarray(mesh.vert_properties, dtype=np.float64)[:, :3][np.asarray(mesh.tri_verts)]


def main():
    os.makedirs(OUT, exist_ok=True)
    base, lid = node_base(), node_lid()

    # ---- checks ----
    ok = True
    for name, m in (("base", base), ("lid", lid)):
        hit = sum((m ^ p).volume() for p in pcb_mock())
        print("%-5s volume %.1f cm3, collision with PCB/parts %.3f mm3" % (name, m.volume() / 1000, hit))
        ok &= hit < 0.5
    overlap = (base ^ lid).volume()
    print("base/lid overlap %.3f mm3" % overlap)
    ok &= overlap < 0.5

    # the lid is saved upside down so its flat top is on the bed
    lid_print = lid.rotate([180, 0, 0]).translate([0, BH, Z_TOP])
    parts = [("node_base", base), ("node_lid", lid_print), ("nfc_holder", nfc_holder()), ("pi_tray", pi_tray())]
    for name, m in parts:
        bb = m.bounding_box()
        solid = len(m.decompose()) == 1 and not m.is_empty()
        print("%-11s %6.1f x %5.1f x %4.1f mm  z-min %.2f  one solid: %s" % (
            name, bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2], bb[2], solid))
        ok &= solid and abs(bb[2]) < 1e-6
        write_stl(m, os.path.join(OUT, name + ".stl"))
    d = dict(parts)
    preview([("Assembled node case, connector side (USB-C, 2x CAN)", tris_of(base + lid), 32, -25),
             ("Assembled, from above", tris_of(base + lid), 62, -70),
             ("node_base.stl", tris_of(base), 45, -30),
             ("node_lid.stl (as printed, top face down)", tris_of(lid_print), 45, -30),
             ("nfc_holder.stl", tris_of(d["nfc_holder"]), 45, -30),
             ("pi_tray.stl", tris_of(d["pi_tray"]), 45, -30)], os.path.join(OUT, "preview.png"))
    print("OK" if ok else "CHECK FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
