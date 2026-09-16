"""Tìm font đậm có sẵn trên máy (macOS / Linux / Windows). Ưu tiên `font` trong kichban.json."""
import os

UNG_VIEN = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",          # macOS
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Helvetica.ttc",
    "/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf",     # Linux (ttf-mscorefonts)
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",       # Linux (dejavu)
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",                               # Windows
]


def tim_font(cfg=None):
    if cfg and cfg.get("font") and os.path.exists(cfg["font"]):
        return cfg["font"]
    here = os.path.dirname(os.path.abspath(__file__))
    local = os.path.join(here, "..", "fonts")
    if os.path.isdir(local):
        for f in sorted(os.listdir(local)):
            if f.lower().endswith((".ttf", ".otf")):
                return os.path.join(local, f)
    for p in UNG_VIEN:
        if os.path.exists(p):
            return p
    raise SystemExit("Không tìm thấy font đậm. Đặt file .ttf vào <skill>/fonts/ hoặc khai "
                     "\"font\": \"/đường/dẫn/Bold.ttf\" trong kichban.json")
