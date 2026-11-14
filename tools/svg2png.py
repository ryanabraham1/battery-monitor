"""svg2png.py in.svg out.png [width_px] [crop x0 y0 x1 y1 as 0..1 fractions]"""
import sys, wx, wx.svg
app = wx.App(False)
img = wx.svg.SVGimage.CreateFromFile(sys.argv[1])
wpx = int(sys.argv[3]) if len(sys.argv) > 3 else 2400
scale = wpx / img.width
bmp = img.ConvertToScaledBitmap(wx.Size(int(img.width * scale), int(img.height * scale)))
im = bmp.ConvertToImage()
# white background
if im.HasAlpha():
    w, h = im.GetWidth(), im.GetHeight()
    from PIL import Image
    rgb = Image.frombytes("RGB", (w, h), bytes(im.GetData()))
    a = Image.frombytes("L", (w, h), bytes(im.GetAlpha()))
    bg = Image.new("RGB", (w, h), "white")
    bg.paste(rgb, mask=a)
    if len(sys.argv) > 7:
        x0, y0, x1, y1 = [float(v) for v in sys.argv[4:8]]
        bg = bg.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))
    bg.save(sys.argv[2])
else:
    im.SaveFile(sys.argv[2], wx.BITMAP_TYPE_PNG)
print("ok", sys.argv[2])
