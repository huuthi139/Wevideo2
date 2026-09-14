"""clipper.py — Cắt video DÀI (ngang 16:9) thành nhiều CLIP NGẮN 9:16 cho Reels/Short.

Luồng: transcribe (faster-whisper) → tìm highlight (heuristic/LLM) → mỗi highlight:
cắt → reframe 9:16 (center / bám mặt bằng cv2) → caption tự động (PNG overlay) →
chuẩn âm lượng (loudnorm) → export. Báo tiến độ qua progress(pct, msg).

Degrade an toàn: thiếu faster-whisper → cắt theo mốc thời gian đều, không caption.
Thiếu cv2/không thấy mặt → center-crop.
"""
from __future__ import annotations

import json
import os
import re
import subprocess

FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def _ff(*a):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *a], check=True)


def _probe(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-show_entries", "format=duration",
         "-of", "json", path]).decode()
    d = json.loads(out)
    s = d["streams"][0]
    return int(s["width"]), int(s["height"]), float(d["format"]["duration"])


# ── 1) transcribe ────────────────────────────────────────────────
def transcribe(video, model_size="base", progress=lambda p, m: None):
    """Trả (segments, lang). segments=[{start,end,text,words:[{start,end,word}]}] hoặc (None,None)."""
    try:
        from faster_whisper import WhisperModel
    except Exception as e:
        print("[clipper] faster-whisper không có:", e)
        return None, None
    progress(12, "Tải model whisper + nhận dạng lời nói…")
    try:
        m = WhisperModel(model_size, device="cpu", compute_type="int8")
        segs, info = m.transcribe(video, word_timestamps=True, vad_filter=True)
        out = []
        for s in segs:
            words = [{"start": float(w.start), "end": float(w.end), "word": w.word}
                     for w in (s.words or []) if w.start is not None]
            out.append({"start": float(s.start), "end": float(s.end),
                        "text": s.text.strip(), "words": words})
        return out, (info.language if info else None)
    except Exception as e:
        print("[clipper] transcribe lỗi:", e)
        return None, None


# ── 2) tìm highlight (gom câu thành cửa sổ ~target giây) ──────────
def find_highlights(segments, target=45.0, n=None, min_dur=18.0, max_dur=75.0):
    """Gom segment kề nhau thành clip ~target giây, ưu tiên cắt ở cuối câu."""
    clips, cur = [], []

    def flush():
        if not cur:
            return
        st, en = cur[0]["start"], cur[-1]["end"]
        if en - st >= min_dur:
            clips.append({"start": round(st, 2), "end": round(en, 2),
                          "text": " ".join(x["text"] for x in cur).strip()})

    for s in segments:
        cur.append(s)
        dur = cur[-1]["end"] - cur[0]["start"]
        ends_sentence = bool(re.search(r"[.!?…。]\s*$", s["text"]))
        if (dur >= target and ends_sentence) or dur >= max_dur:
            flush(); cur = []
    flush()
    # sắp theo độ dài chữ (đoạn nhiều nội dung ~ hay hơn) — heuristic đơn giản
    clips.sort(key=lambda c: len(c["text"]), reverse=True)
    if n:
        clips = clips[:n]
    clips.sort(key=lambda c: c["start"])
    return clips


def fixed_windows(total, target=45.0, n=None):
    """Không có transcript → cắt cửa sổ đều target giây."""
    clips = []
    t = 0.0
    while t < total - 5:
        en = min(t + target, total)
        if en - t >= 12:
            clips.append({"start": round(t, 2), "end": round(en, 2), "text": ""})
        t = en
    if n:
        clips = clips[:n]
    return clips


# ── 3) reframe 16:9 → 9:16 ───────────────────────────────────────
def _face_center_x(video, start, end, iw, ih):
    """x-center (px nguồn) của mặt to nhất — chạy cv2 ở SUBPROCESS RIÊNG (tránh xung đột 'av')."""
    times = ",".join(f"{start + (end - start) * f:.2f}" for f in (0.15, 0.35, 0.55, 0.75, 0.9))
    helper = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_facedetect.py")
    try:
        import sys as _sys
        out = subprocess.run([_sys.executable, helper, video, str(iw), times],
                             capture_output=True, text=True, timeout=60).stdout.strip()
        return float(out) if out and out != "none" else None
    except Exception:
        return None


def _reframe_vf(iw, ih, mode, cx):
    """Filter crop 9:16 + scale 1080x1920."""
    W, H = 1080, 1920
    tgt = 9 / 16
    if iw / ih >= tgt:                       # nguồn NGANG → crop bề rộng
        cw = int(round(ih * tgt)); cw -= cw % 2
        if mode == "face" and cx is not None:
            x = int(round(min(max(cx - cw / 2, 0), iw - cw)))
        else:
            x = (iw - cw) // 2
        crop = f"crop={cw}:{ih}:{x}:0"
    else:                                    # nguồn DỌC/vuông → crop chiều cao (giữa)
        ch = int(round(iw / tgt)); ch -= ch % 2
        crop = f"crop={iw}:{ch}:0:{(ih - ch) // 2}"
    return f"{crop},scale={W}:{H}:flags=lanczos,setsar=1,fps=30,format=yuv420p"


# ── 4) caption tự động (PNG overlay — ffmpeg máy này không có drawtext) ──
def _chunks(words, max_words=4, max_gap=0.55, max_dur=2.2):
    out, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or w["start"] - cur[-1]["end"] > max_gap
                    or w["end"] - cur[0]["start"] > max_dur):
            out.append(cur); cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    res = []
    for c in out:
        txt = "".join(x["word"] for x in c).strip()
        if txt:
            res.append({"start": c[0]["start"], "end": c[-1]["end"], "text": txt})
    return res


def _render_caption_png(text, path, w=1080, fs=62):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGBA", (w, 300), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(FONT, fs)
    except Exception:
        font = ImageFont.load_default()
    up = text.upper()
    # wrap ~ theo bề rộng
    words = up.split()
    lines, cur = [], ""
    for wd in words:
        t = (cur + " " + wd).strip()
        if d.textlength(t, font=font) > w - 120 and cur:
            lines.append(cur); cur = wd
        else:
            cur = t
    if cur:
        lines.append(cur)
    y = 300 - len(lines) * (fs + 10) - 10
    for ln in lines:
        tw = d.textlength(ln, font=font)
        x = (w - tw) / 2
        for ox in (-3, 0, 3):
            for oy in (-3, 0, 3):
                d.text((x + ox, y + oy), ln, font=font, fill=(0, 0, 0, 255))
        d.text((x, y), ln, font=font, fill=(255, 240, 90, 255))  # vàng, viền đen
        y += fs + 10
    img.save(path)


# ── 5) làm 1 clip ────────────────────────────────────────────────
def make_clip(video, clip, out, workdir, reframe="auto", captions=True,
              loudnorm=True, words=None):
    """Cắt [start,end] → reframe 9:16 → caption → loudnorm → out."""
    iw, ih, _ = _probe(video)
    st, en = clip["start"], clip["end"]
    dur = round(en - st, 2)
    cx = None
    mode = reframe
    if reframe in ("auto", "face"):
        cx = _face_center_x(video, st, en, iw, ih)
        mode = "face" if cx is not None else "center"
    vf = _reframe_vf(iw, ih, mode, cx)

    base = os.path.join(workdir, "_seg.mp4")
    af = "loudnorm=I=-16:TP=-1.5:LRA=11" if loudnorm else None
    args = ["-ss", str(st), "-t", str(dur), "-i", video, "-vf", vf]
    if af:
        args += ["-af", af]
    args += ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "192k", base]
    _ff(*args)

    # caption overlay
    if captions and words:
        cw = [w for w in words if w["end"] > st and w["start"] < en]
        for w in cw:
            w = dict(w)
        chunks = _chunks([{"start": w["start"] - st, "end": w["end"] - st, "word": w["word"]}
                          for w in cw if w["end"] - st > 0])
        chunks = [c for c in chunks if c["end"] > 0 and c["start"] < dur]
        if chunks:
            subs_dir = os.path.join(workdir, "_caps"); os.makedirs(subs_dir, exist_ok=True)
            ins = ["-i", base]; fl = []; cur = "[0:v]"
            for i, c in enumerate(chunks):
                p = os.path.join(subs_dir, f"c{i}.png")
                _render_caption_png(c["text"], p)
                ins += ["-i", p]
                s0 = max(0, round(c["start"], 2)); e0 = round(min(c["end"], dur), 2)
                fl.append(f"{cur}[{i+1}:v]overlay=(W-w)/2:H-360:enable='between(t,{s0},{e0})'[v{i}]")
                cur = f"[v{i}]"
            _ff(*ins, "-filter_complex", ";".join(fl), "-map", cur, "-map", "0:a",
                "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                "-c:a", "copy", out)
            return {"out": out, "dur": dur, "reframe": mode, "captions": len(chunks)}
    os.replace(base, out)
    return {"out": out, "dur": dur, "reframe": mode, "captions": 0}


# ── 6) orchestration ─────────────────────────────────────────────
def run(opts, progress=lambda p, m: None):
    """opts: video, job_dir, name, target(giây), n_clips, reframe(auto/center/face),
    captions(bool), loudnorm(bool), model(base/small). Trả {ok, clips:[...], error}."""
    video = opts["video"]
    job = opts["job_dir"]; os.makedirs(job, exist_ok=True)
    name = opts.get("name", "short")
    target = float(opts.get("target", 45))
    n = opts.get("n_clips") or None
    reframe = opts.get("reframe", "auto")
    captions = bool(opts.get("captions", True))
    loudnorm = bool(opts.get("loudnorm", True))
    model = opts.get("model", "base")

    if not os.path.exists(video):
        return {"ok": False, "error": "Không thấy file video"}
    iw, ih, total = _probe(video)
    progress(5, f"Video {iw}x{ih} · {total:.0f}s. Phân tích nội dung…")

    segments, lang = transcribe(video, model, progress) if captions or True else (None, None)
    all_words = []
    if segments:
        for s in segments:
            all_words += s["words"]
        progress(45, f"Nhận dạng xong ({lang}). Tìm đoạn hay…")
        clips = find_highlights(segments, target=target, n=n)
        if not clips:
            clips = fixed_windows(total, target, n)
    else:
        progress(45, "Không transcribe được → cắt theo mốc đều.")
        clips = fixed_windows(total, target, n)
        captions = False

    if not clips:
        return {"ok": False, "error": "Không tách được đoạn nào"}

    results = []
    for i, c in enumerate(clips):
        pct = 50 + int(45 * i / max(1, len(clips)))
        progress(pct, f"Dựng clip {i+1}/{len(clips)} ({c['end']-c['start']:.0f}s)…")
        out = os.path.join(job, f"{name}_{i+1:02d}_9x16.mp4")
        wd = os.path.join(job, f"_w{i+1}"); os.makedirs(wd, exist_ok=True)
        try:
            r = make_clip(video, c, out, wd, reframe=reframe, captions=captions,
                          loudnorm=loudnorm, words=all_words if captions else None)
            if opts.get("music"):
                from . import enrich_av
                mus = enrich_av.pick_music(opts.get("music_name"))
                if mus:
                    tmp = out + ".mus.mp4"
                    try:
                        if enrich_av.add_music(out, tmp, mus, float(opts.get("music_gain", 0.12))):
                            os.replace(tmp, out)
                            r["music"] = os.path.basename(mus)
                    except Exception as e:
                        print("[clipper] music lỗi:", e)
            r["start"] = c["start"]; r["title"] = (c["text"][:70] or f"Clip {i+1}")
            results.append(r)
        except Exception as e:
            print(f"[clipper] clip {i+1} lỗi:", e)
        finally:
            import shutil as _sh; _sh.rmtree(wd, ignore_errors=True)

    if not results:
        return {"ok": False, "error": "Không dựng được clip nào"}
    progress(100, f"Xong {len(results)} clip.")
    return {"ok": True, "clips": results, "lang": lang, "count": len(results)}
