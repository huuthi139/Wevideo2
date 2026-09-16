#!/usr/bin/env python3
"""B3 — Dựng video hoàn chỉnh: phụ đề kinetic + hard cut + chữ ký + tăng tốc + thumbnail.

    python3 3_dung_video.py kichban.json

Cần: anh/<key>.jpg (B1) · audio/b<i>.wav + nhip[].dur (B2).
Ra:  <ten>_9x16.mp4  ·  thumbnail.jpg

CÁC HẰNG SỐ ĐÃ CHỐT (đừng đổi nếu chưa đo lại):
  · nhịp 1.5–1.8s   · hard cut, KHÔNG xfade   · tăng tốc cuối 1.15× (trần)
  · phụ đề: nền trắng → mực đậm/viền trắng; bảng phấn → vàng chanh/viền xanh đen
"""
import json, os, subprocess, sys

os.environ["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + os.environ.get("PATH", "")  # ffmpeg Homebrew khi chạy headless (ssh/launchd)

from PIL import Image, ImageDraw, ImageFont
from tim_font import tim_font

W, H, FPS = 1080, 1920, 30
BOLD = None   # đặt trong main() qua tim_font(cfg) — không hardcode đường dẫn máy
RED, WHITE = (214, 40, 40), (255, 255, 255)
MAU = {  # (fill, stroke) — SAI cặp này là chữ mất hút
    "trang": ([20, 20, 20], [255, 255, 255]),
    "phan":  ([235, 255, 130], [20, 28, 12]),
}
ZOOM = {"in":    "z='min(1.0+0.07*on/{n},1.07)'",
        "out":   "z='max(1.07-0.07*on/{n},1.0)'",
        "tight": "z='min(1.10+0.06*on/{n},1.16)'"}
HERE = os.path.dirname(os.path.abspath(__file__))


def run(cmd): subprocess.run(cmd, check=True)
def ff(*a):   run(["ffmpeg", "-y", "-loglevel", "error", *a])


def phu_de(cfg):
    fill, stroke = MAU[cfg.get("phong_cach", "trang")]
    proj = {"font": BOLD, "fill": fill, "stroke": stroke, "font_size": 72,
            "big_ratio": 1.55, "center_y": 1520, "max_text_w": 950,
            "subs_dir": os.path.abspath("subs"),
            "cues": [{"lines": n["phu_de"]} for n in cfg["nhip"]]}
    os.makedirs("subs", exist_ok=True)
    json.dump(proj, open("_subs.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    run([sys.executable, os.path.join(HERE, "make_subs_v2.py"), "_subs.json"])


def chu_ky(text):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    f = ImageFont.truetype(BOLD, 58); bb = d.textbbox((0, 0), text, font=f)
    d.text((W - (bb[2] - bb[0]) - 70, H - 150), text, font=f, fill=RED,
           stroke_width=4, stroke_fill=WHITE)
    img.save("_wss.png")


def canh(cfg):
    """Mỗi nhịp 1 cảnh; ảnh dùng LẠI thì đổi kiểu zoom cho đỡ trùng mắt."""
    gap = cfg.get("gap", 0.10); seen = {}; t = 0.0
    for k, n in enumerate(cfg["nhip"]):
        kind = "tight" if seen.get(n["anh"]) else ("in" if k % 2 == 0 else "out")
        seen[n["anh"]] = True
        d_ = round(n["dur"] + gap, 3); n["clip"] = d_; n["start"] = round(t, 3); t = round(t + d_, 3)
        fr = max(2, int(d_ * FPS))
        ff("-loop", "1", "-i", f"anh/{n['anh']}.jpg", "-vf",
           (f"scale={W*2}:-1,zoompan={ZOOM[kind].format(n=fr)}:d={fr}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},"
            f"crop={W}:{H},setsar=1,format=yuv420p"),
           "-t", str(d_), "-r", str(FPS), "-c:v", "libx264", "-preset", "medium",
           "-crf", "19", f"_sc{k+1}.mp4")
    open("_list.txt", "w").write("".join(f"file '_sc{i}.mp4'\n" for i in range(1, len(cfg["nhip"]) + 1)))
    ff("-f", "concat", "-safe", "0", "-i", "_list.txt", "-c", "copy", "_base.mp4")
    return t


def tieng(cfg):
    gap = cfg.get("gap", 0.10)
    ff("-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", str(gap), "_gap.wav")
    L = []
    for i in range(1, len(cfg["nhip"]) + 1):
        L.append(f"file '{os.path.abspath(f'audio/b{i}.wav')}'")
        if i < len(cfg["nhip"]): L.append(f"file '{os.path.abspath('_gap.wav')}'")
    open("_tight.txt", "w").write("\n".join(L) + "\n")
    ff("-f", "concat", "-safe", "0", "-i", "_tight.txt", "-c:a", "aac", "-b:a", "192k", "_voice.m4a")


def ghep(cfg):
    n = len(cfg["nhip"])
    ins = ["-i", "_base.mp4", "-i", "_voice.m4a"]
    for i in range(1, n + 1): ins += ["-i", f"subs/sub{i}.png"]
    ins += ["-i", "_wss.png"]
    fl, cur = [], "[0:v]"
    for i, b in enumerate(cfg["nhip"], 1):
        s, e = b["start"] + 0.03, b["start"] + b["clip"] - 0.03
        fl.append(f"{cur}[{1+i}:v]overlay=0:0:enable='between(t,{s:.2f},{e:.2f})'[v{i}]"); cur = f"[v{i}]"
    fl.append(f"{cur}[{n+2}:v]overlay=0:0[vout]")
    ff(*ins, "-filter_complex", ";".join(fl), "-map", "[vout]", "-map", "1:a",
       "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "192k", "-shortest", "_1x.mp4")
    r = cfg.get("toc_do_cuoi", 1.15)
    ff("-i", "_1x.mp4", "-vf", f"setpts=PTS/{r},fps={FPS}", "-af", f"atempo={r}",
       "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "192k", "_body.mp4")


def thumbnail(cfg):
    """Bìa hook: dòng trên đen · dòng chính đỏ · nhãn đỏ chữ trắng · ảnh lấp đầy."""
    th = cfg.get("thumbnail")
    if not th: return None
    c = Image.new("RGB", (W, H), "white")
    im = Image.open(f"anh/{th['anh']}.jpg").convert("RGB")
    top, bh = 700, H - 700
    r = max(W / im.width, bh / im.height) * 1.05
    im = im.resize((int(im.width * r), int(im.height * r)), Image.LANCZOS)
    c.paste(im.crop(((im.width - W) // 2, (im.height - bh) // 2,
                     (im.width - W) // 2 + W, (im.height - bh) // 2 + bh)), (0, top))
    d = ImageDraw.Draw(c)

    def fit(t, s, mw):
        while s > 26:
            f = ImageFont.truetype(BOLD, s)
            if d.textbbox((0, 0), t, font=f)[2] <= mw: return f
            s -= 2
        return ImageFont.truetype(BOLD, 26)

    def ctr(t, y, f, fill):
        bb = d.textbbox((0, 0), t, font=f)
        d.text(((W - (bb[2] - bb[0])) // 2, y - bb[1]), t, font=f, fill=fill,
               stroke_width=9, stroke_fill=WHITE)
        return bb[3] - bb[1]

    y = 150
    y += ctr(th["dong_tren"], y, fit(th["dong_tren"], 100, 930), (18, 18, 18)) + 40
    y += ctr(th["dong_chinh"], y, fit(th["dong_chinh"], 172, 980), RED) + 46
    # nhãn đỏ PHẢI co chữ như 2 dòng trên — nhãn dài (vd "KHÔNG RỦ NGƯỜI QUEN")
    # ở cỡ cứng 92px tràn khỏi khung 1080px. max_w chừa 64px lề mỗi bên cho padding.
    f = fit(th["nhan_do"], 92, W - 200)
    bb = d.textbbox((0, 0), th["nhan_do"], font=f)
    tw, thh = bb[2] - bb[0], bb[3] - bb[1]
    d.rounded_rectangle([(W - tw) // 2 - 32, y, (W + tw) // 2 + 32, y + thh + 64], radius=24, fill=RED)
    d.text(((W - tw) // 2, y + 32 - bb[1]), th["nhan_do"], font=f, fill=WHITE)
    fw = ImageFont.truetype(BOLD, 56); bb = d.textbbox((0, 0), cfg.get("chu_ky", "WSS"), font=fw)
    d.text((W - (bb[2] - bb[0]) - 64, H - 108), cfg.get("chu_ky", "WSS"), font=fw,
           fill=RED, stroke_width=5, stroke_fill=WHITE)
    c.save("thumbnail.jpg", quality=93)
    return th.get("giay", 0.3)


def main(cfg_path):
    global BOLD
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    BOLD = tim_font(cfg)
    if any("dur" not in n for n in cfg["nhip"]):
        sys.exit("Thiếu độ dài giọng — chạy 2_tao_giong.py trước.")
    phu_de(cfg); chu_ky(cfg.get("chu_ky", "WSS"))
    tong = canh(cfg); tieng(cfg); ghep(cfg)
    out = f"{cfg['ten']}_9x16.mp4"
    giay = thumbnail(cfg)
    if giay:
        ff("-loop", "1", "-i", "thumbnail.jpg", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
           "-t", str(giay), "-r", str(FPS), "-vf", f"scale={W}:{H},setsar=1,format=yuv420p",
           "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-c:a", "aac",
           "-b:a", "192k", "-shortest", "_thumb.mp4")
        open("_cat.txt", "w").write("file '_thumb.mp4'\nfile '_body.mp4'\n")
        ff("-f", "concat", "-safe", "0", "-i", "_cat.txt", "-c", "copy", out)
    else:
        os.replace("_body.mp4", out)
    for f in os.listdir("."):
        if f.startswith("_"): os.remove(f)
    json.dump(cfg, open(cfg_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    d = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "default=nw=1:nk=1", out]).decode().strip()
    print(f"\n✅ {out} · {float(d):.2f}s · {len(cfg['nhip'])} nhịp "
          f"({tong/len(cfg['nhip']):.2f}s/nhịp) · tăng tốc {cfg.get('toc_do_cuoi',1.15)}×")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "kichban.json")
