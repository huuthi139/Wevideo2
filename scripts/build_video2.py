#!/usr/bin/env python3
"""build_video2.py — Dựng video 9:16 CÓ zoom Ken Burns + FX chuyển cảnh + B-roll cutaway.

Nâng cấp build_video: mọi thứ khai báo trong project.json (không sửa code cho từng video).

    python3 build_video2.py project.json

project.json (các khoá; thiếu thì mặc định):
{
  "out": "ten_9x16.mp4",
  "voice": "voice_tight.m4a",           # track giọng (bắt buộc để lồng tiếng)
  "speed": 1.15,                         # tăng tốc xuất bản (setpts+atempo); 1.0 = không
  "delogo": true,                        # xoá logo Veo góc phải-dưới (clip 720x1280)
  "transition": {"type": "hardcut", "dur": 0.25},  # type: hardcut|fade|dissolve|slideleft|
                                         #   slideright|slideup|slidedown|wipeleft|circleopen|zoomin
  "scenes": [
    {"clip": "clip1.mp4", "dur": 4.0, "zoom": "in",   "sub": ["Hàng hoá *phái sinh*", "rất *đơn giản*"]},
    {"clip": "clip2.mp4", "dur": 3.9, "zoom": "out",  "sub": ["..."]}
  ],
  "broll": [                             # cutaway: THAY khung hình trong cửa sổ [at, at+dur]
    {"clip": "broll_gold.mp4", "at": 6.0, "dur": 1.6, "zoom": "in"}  # giọng CHẠY TIẾP (giữ khớp)
  ],
  "subs": {"style": "phan"}              # phan=vàng chanh/bảng phấn · trang=mực đậm/nền trắng
}

Nguyên tắc đồng bộ: cảnh xếp theo mốc giọng (dur = độ dài câu, hard-cut TỔNG = độ dài giọng).
- transition xfade rút ngắn tổng d*(n-1) → script TỰ bù bằng cách kéo dài đuôi mỗi cảnh d giây
  (freeze frame cuối) nên khung nội dung mỗi cảnh vẫn = câu, tổng vẫn = giọng → KHỚP.
- B-roll là OVERLAY THAY khung (không thêm thời lượng) → giọng không lệch.
"""
import json, os, subprocess, sys

W, H, FPS = 1080, 1920, 30
DELOGO = "delogo=x=560:y=1095:w=112:h=112"   # logo Veo trên clip GỐC 720x1280 (xoá TRƯỚC upscale)
# Zoom Ken Burns cho VIDEO bằng zoompan (output CỐ ĐỊNH s=WxH; crop động làm x264 fail vì khung đổi cỡ).
# {F} = tổng số frame của cảnh; on = frame đầu ra. Đặt SAU scale=1080x1920 + fps.
_ZP = ":d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=%dx%d:fps=%d" % (W, H, FPS)
ZOOM = {
    "in":    "zoompan=z='min(1.0+0.06*on/{F},1.06)'" + _ZP,
    "out":   "zoompan=z='max(1.06-0.06*on/{F},1.0)'" + _ZP,
    "tight": "zoompan=z='min(1.10+0.06*on/{F},1.16)'" + _ZP,
    "punch": "zoompan=z='min(1.0+0.13*on/{F},1.13)'" + _ZP,
    "none":  None,
}
# xfade transition hợp lệ của ffmpeg (subset hữu dụng); "hardcut" xử lý riêng (concat).
XFADE = {"fade", "dissolve", "slideleft", "slideright", "slideup", "slidedown",
         "wipeleft", "wiperight", "circleopen", "circleclose", "zoomin", "smoothleft", "fadeblack"}
SUB_COLORS = {"phan": ([235, 255, 130, 255], [18, 26, 10, 255]),
              "trang": ([20, 20, 20, 255], [255, 255, 255, 255])}
HERE = os.path.dirname(os.path.abspath(__file__))


def run(cmd):
    subprocess.run(cmd, check=True)


def ff(*a):
    run(["ffmpeg", "-y", "-loglevel", "error", *a])


def probe_dur(p):
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", p]).decode().strip())

def _synth_sfx(kind, path):
    """SFX chuyển cảnh nhẹ, sinh bằng ffmpeg lavfi (không cần file ngoài)."""
    if kind == "ting":
        ff("-f", "lavfi", "-i", "sine=frequency=1568:duration=0.35",
           "-af", "afade=t=out:st=0.04:d=0.31", "-ar", "44100", path)
    elif kind == "pop":
        ff("-f", "lavfi", "-i", "sine=frequency=1046:duration=0.09",
           "-af", "afade=t=out:st=0.01:d=0.08", "-ar", "44100", path)
    else:  # whoosh (woo)
        ff("-f", "lavfi", "-i", "anoisesrc=d=0.35:color=pink:amplitude=0.6",
           "-af", "highpass=f=400,lowpass=f=5000,afade=t=in:d=0.12,afade=t=out:st=0.18:d=0.17",
           "-ar", "44100", path)


def _add_sfx(out, cuts, gain):
    """Trộn SFX nhẹ vào các mốc cắt cảnh của video CUỐI (voice giữ nguyên; sfx nhỏ theo gain)."""
    kinds = ["ting", "whoosh", "pop"]
    files = {}
    for k in ("ting", "whoosh", "pop"):
        files[k] = f"_sfx_{k}.wav"; _synth_sfx(k, files[k])
    args = ["-i", out]; fl = []; labels = []
    for j, t in enumerate(cuts):
        k = kinds[j % len(kinds)]
        args += ["-i", files[k]]
        ms = max(0, int(round(t * 1000)))
        fl.append(f"[{j+1}:a]adelay={ms}:all=1,volume={gain}[s{j}]")
        labels.append(f"[s{j}]")
    fl.append(f"[0:a]{''.join(labels)}amix=inputs={len(cuts)+1}:normalize=0[aout]")
    tmp = "_sfxout.mp4"
    ff(*args, "-filter_complex", ";".join(fl), "-map", "0:v", "-map", "[aout]",
       "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", tmp)
    os.replace(tmp, out)


def render_scene(clip, dur, zoom, delogo, out, tail=0.0):
    """1 cảnh: [delogo] → zoom Ken Burns → upscale 1080x1920 → dài (dur+tail) giây.
    tail = đuôi freeze để bù overlap xfade (khung nội dung vẫn = dur)."""
    total = round(dur + tail, 3)
    frames = max(1, int(total * FPS))
    chain = []
    if delogo:
        chain.append(DELOGO)                       # xoá logo trên clip GỐC 720x1280 TRƯỚC upscale
    chain += [f"scale={W}:{H}:flags=lanczos", f"fps={FPS}"]
    z = ZOOM.get(zoom or "none")
    if z:
        chain.append(z.format(F=frames))           # zoompan sau scale → output cố định WxH
    chain += ["setsar=1", "format=yuv420p"]
    pad = f",tpad=stop_mode=clone:stop_duration={max(tail,0.5)+0.5}"
    ff("-i", clip, "-vf", ",".join(chain) + pad, "-t", str(total),
       "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", out)
    return total


def main(cfg_path):
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    base_dir = os.path.dirname(os.path.abspath(cfg_path)) or "."
    os.chdir(base_dir)
    scenes = cfg["scenes"]
    n = len(scenes)
    delogo = cfg.get("delogo", True)
    tr = cfg.get("transition", {}) or {}
    tr_type = tr.get("type", "hardcut")
    tr_dur = float(tr.get("dur", 0.25)) if tr_type != "hardcut" else 0.0
    use_xfade = tr_type in XFADE and tr_dur > 0 and n > 1
    # Mỗi cảnh dài = câu; nếu xfade thì +tr_dur đuôi để overlap không ăn vào nội dung.
    tail = tr_dur if use_xfade else 0.0

    # ── 1) render từng cảnh (zoom + delogo + upscale) ──
    seg, seg_dur = [], []
    for i, sc in enumerate(scenes, 1):
        out = f"_sc{i}.mp4"
        d = render_scene(sc["clip"], float(sc["dur"]), sc.get("zoom", "none"), delogo, out, tail)
        seg.append(out); seg_dur.append(d)

    # ── 2) ghép: hardcut (concat) hoặc xfade chain ──
    # scene_start[i] = mốc BẮT ĐẦU cảnh i trong video nền (để đặt phụ đề + B-roll đúng chỗ)
    scene_start = [0.0]
    if not use_xfade:
        open("_list.txt", "w").write("".join(f"file '{s}'\n" for s in seg))
        ff("-f", "concat", "-safe", "0", "-i", "_list.txt", "-c", "copy", "_base.mp4")
        for i in range(1, n):
            scene_start.append(round(scene_start[-1] + float(scenes[i - 1]["dur"]), 3))
    else:
        # xfade nối tiếp: offset_k = (mốc bắt đầu chuyển ở đầu ra). Cảnh visible = dur (không kể đuôi).
        cur = "[0:v]"; fl = []; ins = []
        for s in seg:
            ins += ["-i", s]
        off = 0.0
        for i in range(1, n):
            off = round(off + float(scenes[i - 1]["dur"]), 3)   # chuyển cảnh xảy ra ở cuối câu i
            scene_start.append(off)
            nxt = "[vout]" if i == n - 1 else f"[v{i}]"
            fl.append(f"{cur}[{i}:v]xfade=transition={tr_type}:duration={tr_dur}:offset={off}{nxt}")
            cur = nxt
        ff(*ins, "-filter_complex", ";".join(fl), "-map", "[vout]",
           "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "_base.mp4")

    base_dur = probe_dur("_base.mp4")

    # ── 3) B-roll cutaway: THAY khung trong [at, at+dur] (giọng chạy tiếp) ──
    brolls = cfg.get("broll", []) or []
    cur_video = "_base.mp4"
    for j, b in enumerate(brolls, 1):
        at = float(b["at"]); bdur = float(b["dur"]); bz = b.get("zoom", "none")
        bseg = f"_br{j}.mp4"
        render_scene(b["clip"], bdur, bz, delogo, bseg, tail=0.0)
        nxt = f"_bmix{j}.mp4"
        # overlay clip broll đè lên nền trong cửa sổ thời gian [at, at+dur]
        ff("-i", cur_video, "-i", bseg, "-filter_complex",
           f"[1:v]setpts=PTS-STARTPTS+{at}/TB[b];[0:v][b]overlay=0:0:enable='between(t,{at},{at+bdur})'[v]",
           "-map", "[v]", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
           "-pix_fmt", "yuv420p", "-t", str(round(base_dur, 3)), nxt)
        cur_video = nxt

    # ── 4) phụ đề kinetic (make_subs_v2) đặt theo scene_start ──
    have_subs = any(sc.get("sub") for sc in scenes)
    sub_imgs = []
    if have_subs:
        style = (cfg.get("subs", {}) or {}).get("style", "phan")
        fill, stroke = SUB_COLORS.get(style, SUB_COLORS["phan"])
        proj = {"subs_dir": os.path.abspath("_subs2"), "center_y": 1500, "font_size": 66,
                "big_ratio": 1.5, "max_text_w": 980, "fill": fill, "stroke": stroke,
                "cues": [{"lines": sc.get("sub") or [""]} for sc in scenes]}
        os.makedirs("_subs2", exist_ok=True)
        json.dump(proj, open("_subs2.json", "w", encoding="utf-8"), ensure_ascii=False)
        run([sys.executable, os.path.join(HERE, "make_subs_v2.py"), "_subs2.json"])
        sub_imgs = [f"_subs2/sub{i}.png" for i in range(1, n + 1)]

    # ── 5) overlay phụ đề (mỗi cảnh) + lồng giọng ──
    voice = cfg.get("voice")
    ins = ["-i", cur_video]
    if voice:
        ins += ["-i", voice]
    a_idx = 1 if voice else None
    for im in sub_imgs:
        ins += ["-i", im]
    fl = []; cur = "[0:v]"
    base_in = (2 if voice else 1)
    for i in range(n):
        if not sub_imgs:
            break
        s = round(scene_start[i] + 0.05, 2)
        e = round((scene_start[i + 1] if i + 1 < len(scene_start) else base_dur) - 0.05, 2)
        idx = base_in + i
        fl.append(f"{cur}[{idx}:v]overlay=0:0:enable='between(t,{s},{e})'[v{i}]"); cur = f"[v{i}]"
    maps = ["-map", cur if sub_imgs else "0:v"]
    if voice:
        maps += ["-map", f"{a_idx}:a"]
    args = ins + (["-filter_complex", ";".join(fl)] if fl else []) + maps + \
        ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p"]
    if voice:
        args += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
    args += ["_1x.mp4"]
    ff(*args)

    # ── 6) xuất bản tăng tốc ──
    out = cfg.get("out", "output_9x16.mp4")
    speed = float(cfg.get("speed", 1.15))
    if abs(speed - 1.0) < 1e-3:
        os.replace("_1x.mp4", out)
    else:
        af = f"atempo={speed}" if voice else None
        vf = f"setpts=PTS/{speed},fps={FPS}"
        a = ["-i", "_1x.mp4", "-vf", vf]
        if voice:
            a += ["-af", af]
        a += ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p"]
        if voice:
            a += ["-c:a", "aac", "-b:a", "192k"]
        a += [out]
        ff(*a)

    # ── 6.5) SFX chuyển cảnh (ting/woo/tích nhẹ) ──
    sfx = cfg.get("sfx", {}) or {}
    n_sfx = 0
    if sfx.get("enabled") and voice and n > 1:
        cuts = [round(scene_start[i] / speed, 3) for i in range(1, n)]  # mốc cắt ở video cuối
        try:
            _add_sfx(out, cuts, float(sfx.get("gain", 0.3)))
            n_sfx = len(cuts)
        except Exception as e:
            print(f"[sfx] bỏ qua ({e})")

    out_abs = os.path.abspath(out)
    for f in os.listdir("."):
        if f.startswith("_") and os.path.isfile(f) and os.path.abspath(f) != out_abs:
            try:
                os.remove(f)
            except Exception:
                pass
    import shutil
    shutil.rmtree("_subs2", ignore_errors=True)
    d = probe_dur(out)
    print(f"\n✅ {out} · {d:.2f}s · {n} cảnh · transition={tr_type} · broll={len(brolls)} · sfx={n_sfx} · speed={speed}×")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "project.json")
