#!/usr/bin/env python3
"""Render burned-in Vietnamese subtitles as transparent PNGs (one per cue).

Why PNGs instead of ffmpeg's subtitles/drawtext filter: the local ffmpeg build
has no libass / libfreetype, so text must be rasterised with PIL and then
overlaid. Font size auto-shrinks so the widest line always fits the frame.

Usage:  python3 make_subs.py project.json [out_dir]
        (out_dir defaults to the JSON's "subs_dir", else the JSON's folder)

project.json needs a "cues" array of {"lines": ["line1", "line2"], ...}.
Optional styling keys (sensible defaults for the "người que" look):
  fill [r,g,b,a]      default [235,255,130,255]  (vàng chanh nhẹ)
  stroke [r,g,b,a]    default [20,28,12,255]
  stroke_w            default 7
  font                default Arial Bold
  font_size           default 74  (max; auto-shrinks to fit)
  center_y            default 1430 (caption block center, lower third)
  line_gap            default 12
  max_text_w          default 960  (usable width; keeps text off the edges)
"""
import json
import os
import sys
from PIL import Image, ImageDraw, ImageFont

cfg_path = sys.argv[1]
cfg = json.load(open(cfg_path))
out_dir = sys.argv[2] if len(sys.argv) > 2 else cfg.get("subs_dir") or os.path.dirname(os.path.abspath(cfg_path))
os.makedirs(out_dir, exist_ok=True)

cues = cfg["cues"]
W, H = 1080, 1920
FONT = cfg.get("font", "/System/Library/Fonts/Supplemental/Arial Bold.ttf")
FILL = tuple(cfg.get("fill", [235, 255, 130, 255]))
STROKE = tuple(cfg.get("stroke", [20, 28, 12, 255]))
STROKE_W = cfg.get("stroke_w", 7)
CENTER_Y = cfg.get("center_y", 1430)
LINE_GAP = cfg.get("line_gap", 12)
MAX_W = cfg.get("max_text_w", 960)
MAX_SIZE = cfg.get("font_size", 74)

_probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))


def widest(size):
    f = ImageFont.truetype(FONT, size)
    w = 0
    for c in cues:
        for ln in c["lines"]:
            b = _probe.textbbox((0, 0), ln, font=f, stroke_width=STROKE_W)
            w = max(w, b[2] - b[0])
    return w


size = MAX_SIZE
while size > 34 and widest(size) > MAX_W:
    size -= 2

font = ImageFont.truetype(FONT, size)
asc, desc = font.getmetrics()
lh = asc + desc

for i, c in enumerate(cues, 1):
    lines = c["lines"]
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    total = len(lines) * lh + (len(lines) - 1) * LINE_GAP
    y = CENTER_Y - total / 2
    for ln in lines:
        b = dr.textbbox((0, 0), ln, font=font, stroke_width=STROKE_W)
        x = (W - (b[2] - b[0])) / 2 - b[0]
        dr.text((x, y + 4), ln, font=font, fill=(0, 0, 0, 120),
                stroke_width=STROKE_W, stroke_fill=(0, 0, 0, 120))
        dr.text((x, y), ln, font=font, fill=FILL,
                stroke_width=STROKE_W, stroke_fill=STROKE)
        y += lh + LINE_GAP
    img.save(os.path.join(out_dir, f"sub{i}.png"))

print(f"rendered {len(cues)} subtitle PNGs at font size {size} -> {out_dir}")
