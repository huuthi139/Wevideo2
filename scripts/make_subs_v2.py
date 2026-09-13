#!/usr/bin/env python3
"""Phụ đề PNG kiểu kinetic: từ đánh dấu *như này* render TO 1.5x + IN HOA.

Nâng cấp từ make_subs.py (skill video-nguoi-que của PTL) — giữ nguyên màu
vàng chanh + viền + auto-shrink, thêm mixed-size trong 1 dòng, căn baseline.

Dùng:  python3 make_subs_v2.py project.json
Cues:  {"lines": ["Đừng coi thường", "*bước nhỏ*"]}  → "BƯỚC NHỎ" to gấp rưỡi.
"""
import json
import os
import re
import sys
from PIL import Image, ImageDraw, ImageFont

cfg_path = sys.argv[1]
cfg = json.load(open(cfg_path))
out_dir = cfg.get("subs_dir") or os.path.dirname(os.path.abspath(cfg_path))
os.makedirs(out_dir, exist_ok=True)

cues = cfg["cues"]
W, H = 1080, 1920
FONT = cfg.get("font", "/System/Library/Fonts/Supplemental/Arial Bold.ttf")
FILL = tuple(cfg.get("fill", [235, 255, 130, 255]))
STROKE = tuple(cfg.get("stroke", [20, 28, 12, 255]))
CENTER_Y = cfg.get("center_y", 1430)
LINE_GAP = cfg.get("line_gap", 14)
MAX_W = cfg.get("max_text_w", 980)
BASE = cfg.get("font_size", 64)
BIG_RATIO = cfg.get("big_ratio", 1.55)

_probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
_fonts: dict[int, ImageFont.FreeTypeFont] = {}


def font_at(size: int) -> ImageFont.FreeTypeFont:
    if size not in _fonts:
        _fonts[size] = ImageFont.truetype(FONT, size)
    return _fonts[size]


def parse_line(line: str):
    """'abc *key* xyz' → [(('abc ', False), ('KEY', True), (' xyz', False)]"""
    segs = []
    for part in re.split(r"(\*[^*]+\*)", line):
        if not part:
            continue
        if part.startswith("*") and part.endswith("*"):
            segs.append((part[1:-1].upper(), True))
        else:
            segs.append((part, False))
    return segs


def seg_font(big: bool, scale: float) -> ImageFont.FreeTypeFont:
    return font_at(max(16, int((BASE * (BIG_RATIO if big else 1.0)) * scale)))


def line_width(segs, scale: float) -> int:
    return sum(int(_probe.textlength(t, font=seg_font(b, scale))) for t, b in segs)


for i, cue in enumerate(cues, 1):
    lines = [parse_line(ln) for ln in cue["lines"]]
    # auto-shrink cả cụm để dòng rộng nhất vừa MAX_W
    scale = 1.0
    while scale > 0.4 and max(line_width(s, scale) for s in lines) > MAX_W:
        scale -= 0.05

    # đo chiều cao từng dòng theo font lớn nhất trong dòng
    metrics = []
    for segs in lines:
        fonts = [seg_font(b, scale) for _, b in segs]
        ascent = max(f.getmetrics()[0] for f in fonts)
        descent = max(f.getmetrics()[1] for f in fonts)
        metrics.append((ascent, descent))
    total_h = sum(a + d for a, d in metrics) + LINE_GAP * (len(lines) - 1)

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    y = CENTER_Y - total_h // 2
    for segs, (ascent, descent) in zip(lines, metrics):
        x = (W - line_width(segs, scale)) // 2
        for text, big in segs:
            f = seg_font(big, scale)
            a_seg = f.getmetrics()[0]
            sw = max(3, int(f.size * 0.085))
            draw.text((x, y + (ascent - a_seg)), text, font=f, fill=FILL,
                      stroke_width=sw, stroke_fill=STROKE)
            x += int(_probe.textlength(text, font=f))
        y += ascent + descent + LINE_GAP

    img.save(os.path.join(out_dir, f"sub{i}.png"))

print(f"rendered {len(cues)} kinetic subtitle PNGs (base {BASE}, big x{BIG_RATIO}) -> {out_dir}")
