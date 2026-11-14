"""Autoroute signals with Freerouting, refill pours, save. usage: python route.py <freerouting.jar> [passes]"""
import os, sys, subprocess
sys.path.insert(0, os.path.dirname(__file__))
import pcbnew
import gen_pcb

jar = sys.argv[1]
passes = sys.argv[2] if len(sys.argv) > 2 else "30"
HW = gen_pcb.HW
pcb = os.path.join(HW, "ir_node.kicad_pcb")
dsn = os.path.join(HW, "route", "ir_node.dsn")
ses = os.path.join(HW, "route", "ir_node.ses")
os.makedirs(os.path.dirname(dsn), exist_ok=True)

b, nets = gen_pcb.build(gnd_zones=False)
pcbnew.SaveBoard(pcb, b)
b = pcbnew.LoadBoard(pcb)
assert pcbnew.ExportSpecctraDSN(b, dsn), "DSN export failed"
if os.path.exists(ses):
    os.remove(ses)
r = subprocess.run(["java", "-jar", jar, "-de", dsn, "-do", ses, "-mp", passes, "-mt", "1"],
                   capture_output=True, text=True, timeout=1500)
print(r.stdout[-1500:]); print(r.stderr[-800:])
assert os.path.exists(ses), "no session file produced"
assert pcbnew.ImportSpecctraSES(b, ses), "SES import failed"
def net(name):
    return b.FindNet("/" + name)
gen_pcb.add_zones(b, net, gnd=True)
for fp in b.GetFootprints():
    for pd in fp.Pads():
        if pd.GetNetname() == "/GND":
            solid = (fp.GetReference(), pd.GetNumber()) in gen_pcb.SOLID_GND_PADS or pd.GetAttribute() == pcbnew.PAD_ATTRIB_SMD
            pd.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL if solid else pcbnew.ZONE_CONNECTION_THERMAL)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())

# GND stitching: tie top and bottom ground pours wherever both are present and clear
from pcbnew import VECTOR2I, FromMM
gz = [z for z in b.Zones() if z.GetNetname() == "/GND" and not z.GetIsRuleArea()]
def both(x, y):
    p = gen_pcb.pt(x, y)
    return all(any(z.IsOnLayer(L) and z.HitTestFilledArea(L, p, 0) for z in gz) for L in (pcbnew.F_Cu, pcbnew.B_Cu))
import math
RING = [(0, 0)] + [(rr * math.cos(k * math.pi / 12), rr * math.sin(k * math.pi / 12)) for rr in (0.35, 0.7, 1.0) for k in range(24)]
OBST = []
for fp in b.GetFootprints():
    for pd in fp.Pads():
        bb = pd.GetBoundingBox()
        OBST.append((pcbnew.ToMM(bb.GetLeft()) - gen_pcb.OX - 1.0, pcbnew.ToMM(bb.GetTop()) - gen_pcb.OY - 1.0,
                     pcbnew.ToMM(bb.GetRight()) - gen_pcb.OX + 1.0, pcbnew.ToMM(bb.GetBottom()) - gen_pcb.OY + 1.0))
for t in b.GetTracks():
    bb = t.GetBoundingBox()
    if t.Type() == pcbnew.PCB_VIA_T:
        OBST.append((pcbnew.ToMM(bb.GetLeft()) - gen_pcb.OX - 0.8, pcbnew.ToMM(bb.GetTop()) - gen_pcb.OY - 0.8,
                     pcbnew.ToMM(bb.GetRight()) - gen_pcb.OX + 0.8, pcbnew.ToMM(bb.GetBottom()) - gen_pcb.OY + 0.8))
def clear(x, y):
    return not any(o[0] < x < o[2] and o[1] < y < o[3] for o in OBST)
n = 0
y = 2.5
while y < gen_pcb.BH - 2:
    x = 2.5
    while x < gen_pcb.BW - 2:
        if clear(x, y) and all(both(x + dx, y + dy) for (dx, dy) in RING):
            v = pcbnew.PCB_VIA(b)
            v.SetPosition(gen_pcb.pt(x, y)); v.SetWidth(pcbnew.F_Cu, FromMM(0.7)); v.SetDrill(FromMM(0.3))
            v.SetNet(net("GND")); v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            b.Add(v); n += 1
        x += 4.0
    y += 4.0
print("GND stitching vias:", n)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
pcbnew.SaveBoard(pcb, b)
print("tracks:", len(b.GetTracks()))
