#!/usr/bin/env python3
"""make_icon.py — icon app WeVideo, tối giản & hiện đại kiểu AI.
Squircle gradient indigo→cyan, nút play trắng bo tròn ở giữa + 1 tia sáng (AI spark)."""
import os
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
S = 1024
r = int(S * 0.225)
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, S, S], radius=r, fill=255)

def lerp(a, b, t): return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
# gradient chéo: indigo → tím → cyan (tươi, techy/AI)
stops = [(0.0, (79, 70, 229)), (0.55, (124, 77, 255)), (1.0, (34, 211, 238))]
def grad_at(t):
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]; t1, c1 = stops[i + 1]
        if t <= t1:
            return lerp(c0, c1, (t - t0) / (t1 - t0))
    return stops[-1][1]
grad = Image.new("RGB", (S, S)); gp = grad.load()
for y in range(S):
    for x in range(S):
        gp[x, y] = grad_at((x + y) / (2 * S))
bg = Image.new("RGBA", (S, S), (0, 0, 0, 0))
bg.paste(grad, (0, 0), mask)

# gloss nhẹ trên đỉnh
gloss = Image.new("L", (S, S), 0)
ImageDraw.Draw(gloss).ellipse([-S*0.25, -S*0.6, S*1.25, S*0.4], fill=48)
gloss = gloss.filter(ImageFilter.GaussianBlur(46))
white = Image.new("RGBA", (S, S), (255, 255, 255, 255))
bg = Image.composite(Image.alpha_composite(bg, Image.merge("RGBA", (*white.split()[:3], gloss))), bg, mask)

d = ImageDraw.Draw(bg)

# nút play trắng bo góc, CĂN GIỮA (hơi lệch phải quang học)
cx, cy = int(S*0.50), int(S*0.54)
size = int(S*0.34); rad = int(S*0.045)
pts = [(cx - size*0.5, cy - size*0.62), (cx - size*0.5, cy + size*0.62), (cx + size*0.72, cy)]
d.polygon(pts, fill=(255, 255, 255, 255))
for p in pts:
    d.ellipse([p[0]-rad, p[1]-rad, p[0]+rad, p[1]+rad], fill=(255, 255, 255, 255))

# tia sáng AI (4 cánh) góc trên-trái, hai kích cỡ
def spark(draw, cx, cy, R, col):
    w = R * 0.34
    draw.polygon([(cx, cy-R), (cx+w, cy-w), (cx+R, cy), (cx+w, cy+w),
                  (cx, cy+R), (cx-w, cy+w), (cx-R, cy), (cx-w, cy-w)], fill=col)
spark(d, int(S*0.74), int(S*0.29), int(S*0.072), (255, 255, 255, 255))
spark(d, int(S*0.85), int(S*0.19), int(S*0.032), (255, 255, 255, 225))

img_mask = mask
out = os.path.join(HERE, "assets", "icon_1024.png")
Image.composite(bg, Image.new("RGBA",(S,S),(0,0,0,0)), img_mask).save(out)
print("saved", out)
