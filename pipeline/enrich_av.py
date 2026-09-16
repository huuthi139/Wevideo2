"""enrich_av.py — Tăng sức hút cho video: nhạc nền (ducking dưới giọng), thẻ hook/CTA,
màu điện ảnh. Dùng chung cho cả luồng script→video (build_video2) và Auto-Shorts (clipper).
"""
from __future__ import annotations

import os
import random
import subprocess

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MUSIC_DIR = os.path.join(APP, "assets", "music")
FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def _ff(*a):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *a], check=True)


def _has_audio(path):
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
             "stream=index", "-of", "csv=p=0", path]).decode().strip()
        return bool(out)
    except Exception:
        return False


# ── nhạc nền + ducking ───────────────────────────────────────────
def pick_music(name=None):
    """Chọn 1 file nhạc: tên chỉ định > ngẫu nhiên trong assets/music/ > None."""
    if name and os.path.isabs(name) and os.path.exists(name):
        return name
    if not os.path.isdir(MUSIC_DIR):
        return None
    files = [os.path.join(MUSIC_DIR, f) for f in os.listdir(MUSIC_DIR)
             if f.lower().endswith((".mp3", ".m4a", ".wav", ".aac", ".ogg"))]
    if not files:
        return None
    if name:
        for f in files:
            if os.path.basename(f).startswith(name):
                return f
    return random.choice(sorted(files))


def add_music(video_in, out, music, gain=0.14):
    """Trộn nhạc nền (lặp) DƯỚI giọng, tự nhỏ lại khi có giọng (sidechain ducking)."""
    if not music or not os.path.exists(music):
        return False
    if not _has_audio(video_in):        # video không có giọng → nhạc phủ thẳng
        _ff("-i", video_in, "-stream_loop", "-1", "-i", music,
            "-filter_complex", f"[1:a]volume={gain*2.2}[a]", "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", out)
        return True
    fc = (f"[1:a]volume={gain}[m];"
          "[0:a]asplit=2[v1][v2];"
          "[m][v1]sidechaincompress=threshold=0.02:ratio=6:attack=5:release=260[dm];"
          "[v2][dm]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]")
    _ff("-i", video_in, "-stream_loop", "-1", "-i", music,
        "-filter_complex", fc, "-map", "0:v", "-map", "[a]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", out)
    return True


# ── màu điện ảnh (vf nối vào chuỗi filter) ───────────────────────
def grade_vf(kind="cine"):
    """Trả filter màu. cine = tương phản+bão hoà nhẹ+vignette; grain = thêm hạt phim."""
    if kind in (None, "", "none"):
        return None
    base = "eq=contrast=1.06:saturation=1.12:gamma=0.98:brightness=0.01,vignette=PI/5"
    if kind == "grain":
        return base + ",noise=alls=7:allf=t"
    return base


# ── thẻ hook (đầu) / CTA (cuối) — full-frame 1080x1920 ───────────
_CARD_BG = {"phan": (18, 42, 30), "trang": (245, 245, 245)}
_CARD_FG = {"phan": (235, 255, 130), "trang": (20, 20, 20)}


def _render_card(text, out_png, style="phan", sub=None, aspect="9:16"):
    from PIL import Image, ImageDraw, ImageFont
    W, H = (1920, 1080) if aspect == "16:9" else (1080, 1920)
    bg = _CARD_BG.get(style, _CARD_BG["phan"])
    fg = _CARD_FG.get(style, _CARD_FG["phan"])
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)

    def fit(txt, maxw, start=120, minf=54):
        f = start
        while f > minf:
            font = ImageFont.truetype(FONT, f)
            words = txt.split(); lines = []; cur = ""
            for w in words:
                t = (cur + " " + w).strip()
                if d.textlength(t, font=font) > maxw and cur:
                    lines.append(cur); cur = w
                else:
                    cur = t
            if cur:
                lines.append(cur)
            if all(d.textlength(l, font=font) <= maxw for l in lines) and len(lines) <= 4:
                return font, lines, f
            f -= 6
        font = ImageFont.truetype(FONT, minf)
        return font, [txt], minf

    font, lines, fs = fit(text.upper(), W - 160)
    total = len(lines) * (fs + 16)
    y = (H - total) // 2
    for ln in lines:
        tw = d.textlength(ln, font=font); x = (W - tw) / 2
        for ox in (-3, 3):
            d.text((x + ox, y), ln, font=font, fill=(0, 0, 0) if style == "trang" else (10, 20, 8))
        d.text((x, y), ln, font=font, fill=fg)
        y += fs + 16
    if sub:
        sf = ImageFont.truetype(FONT, 46)
        tw = d.textlength(sub, font=sf)
        d.text(((W - tw) / 2, y + 20), sub, font=sf, fill=fg)
    img.save(out_png)


def make_card_clip(text, out_mp4, style="phan", dur=1.2, sub=None, workdir=".", aspect="9:16"):
    """Thẻ tĩnh full-frame (im lặng) dur giây — để nối đầu (hook) hoặc cuối (CTA). aspect 9:16|16:9."""
    png = os.path.join(workdir, "_card.png")
    _render_card(text, png, style, sub, aspect)
    W, H = (1920, 1080) if aspect == "16:9" else (1080, 1920)
    _ff("-loop", "1", "-i", png, "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", str(dur), "-vf", f"scale={W}:{H},fps=30,format=yuv420p",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", out_mp4)
    try:
        os.remove(png)
    except Exception:
        pass
    return out_mp4


def concat_parts(parts, out):
    """Nối nhiều clip (khác kênh audio) → 1 video 1080x1920. Dùng cho hook+main+cta."""
    n = len(parts)
    ins = []
    for pth in parts:
        ins += ["-i", pth]
    fc = [f"[{i}:a]aresample=44100,aformat=channel_layouts=stereo[a{i}]" for i in range(n)]
    seq = "".join(f"[{i}:v][a{i}]" for i in range(n))
    fc.append(f"{seq}concat=n={n}:v=1:a=1[v][a]")
    _ff(*ins, "-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", out)
