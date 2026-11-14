"""Quick PIL renderer for review images.
usage: python render.py board.kicad_pcb out.png [mode] [x0 y0 x1 y1]   (mode: place | top | bottom | both)
"""
import sys, os
import wx
wx.DisableAsserts()
import pcbnew
from pcbnew import ToMM
from PIL import Image, ImageDraw, ImageFont

OX, OY, BW, BH = 100.0, 50.0, 100.0, 80.0


def render(board_path, out, mode="place", win=None, S=14):
    b = pcbnew.LoadBoard(board_path)
    x0, y0, x1, y1 = win or (-2, -2, BW + 2, BH + 2)
    W, H = int((x1 - x0) * S), int((y1 - y0) * S)
    im = Image.new("RGB", (W, H), (18, 18, 22))
    dr = ImageDraw.Draw(im, "RGBA")
    try:
        font = ImageFont.truetype("arial.ttf", max(9, int(S * 0.85)))
    except Exception:
        font = ImageFont.load_default()

    def X(v):
        return (ToMM(v) - OX - x0) * S

    def Y(v):
        return (ToMM(v) - OY - y0) * S

    COL = {pcbnew.F_Cu: (200, 60, 60), pcbnew.B_Cu: (60, 110, 220)}
    layers = {"place": [pcbnew.F_Cu], "top": [pcbnew.F_Cu], "bottom": [pcbnew.B_Cu],
              "both": [pcbnew.B_Cu, pcbnew.F_Cu]}[mode]
    dr.rectangle([X(pcbnew.FromMM(OX)), Y(pcbnew.FromMM(OY)), X(pcbnew.FromMM(OX + BW)), Y(pcbnew.FromMM(OY + BH))],
                 outline=(230, 230, 80), width=2)
    for L in layers:
        c = COL[L]
        for z in b.Zones():
            if z.GetLayer() != L and not z.IsOnLayer(L):
                continue
            if z.IsFilled():
                ps = z.GetFilledPolysList(L)
                for i in range(ps.OutlineCount()):
                    o = ps.Outline(i)
                    pts = [(X(o.CPoint(k).x), Y(o.CPoint(k).y)) for k in range(o.PointCount())]
                    if len(pts) > 2:
                        dr.polygon(pts, fill=c + (90,))
                    for h in range(ps.HoleCount(i)):
                        ho = ps.Hole(i, h)
                        hp = [(X(ho.CPoint(k).x), Y(ho.CPoint(k).y)) for k in range(ho.PointCount())]
                        if len(hp) > 2:
                            dr.polygon(hp, fill=(18, 18, 22, 255))
            else:
                o = z.Outline().Outline(0)
                pts = [(X(o.CPoint(k).x), Y(o.CPoint(k).y)) for k in range(o.PointCount())]
                if z.GetNetname() != "GND":
                    dr.polygon(pts, fill=c + (50,), outline=c + (255,))
                    dr.text((pts[0][0] + 3, pts[0][1] + 2), z.GetNetname(), fill=(255, 200, 120), font=font)
        for t in b.GetTracks():
            if t.Type() == pcbnew.PCB_VIA_T:
                continue
            if t.GetLayer() == L:
                dr.line([X(t.GetStart().x), Y(t.GetStart().y), X(t.GetEnd().x), Y(t.GetEnd().y)],
                        fill=c + (255,), width=max(1, int(ToMM(t.GetWidth()) * S)))
    for t in b.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            r = ToMM(t.GetWidth(pcbnew.F_Cu)) * S / 2
            dr.ellipse([X(t.GetPosition().x) - r, Y(t.GetPosition().y) - r, X(t.GetPosition().x) + r, Y(t.GetPosition().y) + r],
                       fill=(120, 200, 120, 255))
    for fp in b.GetFootprints():
        bb = fp.GetBoundingBox(False)
        if mode in ("place", "top", "both"):
            dr.rectangle([X(bb.GetLeft()), Y(bb.GetTop()), X(bb.GetRight()), Y(bb.GetBottom())], outline=(120, 120, 130, 255))
        for p in fp.Pads():
            pb = p.GetBoundingBox()
            th = p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH)
            if not th and not any(p.IsOnLayer(L) for L in layers):
                continue
            col = (210, 170, 60, 255) if th else (COL[pcbnew.F_Cu] if p.IsOnLayer(pcbnew.F_Cu) else COL[pcbnew.B_Cu]) + (255,)
            box = [X(pb.GetLeft()), Y(pb.GetTop()), X(pb.GetRight()), Y(pb.GetBottom())]
            if th:
                dr.ellipse(box, fill=col)
                d = ToMM(p.GetDrillSize().x) * S / 2
                cx, cy = X(p.GetPosition().x), Y(p.GetPosition().y)
                dr.ellipse([cx - d, cy - d, cx + d, cy + d], fill=(18, 18, 22, 255))
            else:
                dr.rectangle(box, fill=col)
        if mode in ("place", "top", "both"):
            dr.text((X(bb.GetLeft()) + 2, Y(bb.GetTop()) + 1), fp.GetReference(), fill=(240, 240, 240), font=font)
    # mm grid ticks
    for gx in range(0, int(BW) + 1, 10):
        dr.text(((gx - x0) * S + 2, 2), str(gx), fill=(150, 150, 150), font=font)
    for gy in range(0, int(BH) + 1, 10):
        dr.text((2, (gy - y0) * S + 2), str(gy), fill=(150, 150, 150), font=font)
    im.save(out)
    print("rendered", out, im.size)


if __name__ == "__main__":
    a = sys.argv
    win = tuple(float(v) for v in a[4:8]) if len(a) >= 8 else None
    render(a[1], a[2], a[3] if len(a) > 3 else "place", win, S=int(a[8]) if len(a) > 8 else 14)
