"""core.py — Orchestration "kịch bản → video" một phát.

Bước: enrich (kịch bản→cảnh) → giọng (edge-tts) → gen clip Veo (flow-agent :8001)
→ phụ đề (make_subs_v2) → ráp (build_video2). Báo tiến độ qua callback progress(pct, msg).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

from . import prompts

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
SCRIPTS = os.path.join(APP, "scripts")
# edge-tts: ưu tiên venv app, rồi venv mascot, rồi PATH
EDGE_CANDIDATES = [
    os.path.join(APP, ".venv", "bin", "edge-tts"),
    "/Volumes/DATA/AI-APP/mascot-nguoi-que/.venv-tts/bin/edge-tts",
    os.path.expanduser("~/.local/bin/edge-tts"), "edge-tts",
]


def _edge_tts():
    for c in EDGE_CANDIDATES:
        if c == "edge-tts" or os.path.exists(c):
            try:
                if subprocess.run([c, "--version"], capture_output=True).returncode == 0:
                    return c
            except Exception:
                pass
    return None


def _ff_dur(p):
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", p]).decode().strip())


def _gen_clip(flow_url, prompt, duration, out_path, timeout=280, aspect="9:16"):
    """Gọi flow-agent gen 1 clip Veo, tải về out_path. Trả (ok, msg). aspect 9:16|16:9."""
    body = json.dumps({"prompt": prompt, "duration": int(duration),
                       "aspect": "landscape" if aspect == "16:9" else "portrait", "n": 1}).encode()
    req = urllib.request.Request(flow_url.rstrip("/") + "/v1/videos/generations",
                                 data=body, headers={"Content-Type": "application/json"})
    return _fetch_media(flow_url, req, out_path, timeout)


def _gen_image(flow_url, prompt, out_path, timeout=280, aspect="9:16"):
    """[16/09] Gọi flow-agent gen 1 ẢNH (rẻ hơn clip Veo), tải về out_path. Trả (ok, msg)."""
    body = json.dumps({"prompt": prompt, "n": 1,
                       "size": "1920x1080" if aspect == "16:9" else "1080x1920"}).encode()
    req = urllib.request.Request(flow_url.rstrip("/") + "/v1/images/generations",
                                 data=body, headers={"Content-Type": "application/json"})
    return _fetch_media(flow_url, req, out_path, timeout, min_size=20000)


def _img_to_clip(img_path, out_path, duration, aspect="9:16"):
    """[16/09] Ảnh tĩnh → clip mp4 (duration+1.5s, khung đúng aspect) để build_video2 zoom Ken Burns như clip Veo."""
    W, H = (1920, 1080) if aspect == "16:9" else (1080, 1920)
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", img_path,
                        "-t", str(float(duration) + 1.5), "-r", "30",
                        "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},format=yuv420p",
                        "-c:v", "libx264", "-preset", "fast", "-crf", "18", out_path],
                       check=True, capture_output=True, timeout=120)
    except Exception as e:
        return False, f"ảnh→clip lỗi: {str(e)[:140]}"
    return True, "ok"


def _fetch_media(flow_url, req, out_path, timeout, min_size=50000):
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            res = json.load(r)
    except Exception as e:
        return False, f"gen lỗi: {str(e)[:140]}"
    url = ((res.get("data") or [{}])[0]).get("url", "")
    if not url:
        return False, f"không có url: {str(res)[:140]}"
    # url dạng http://localhost:8001/download/<file> — tải thẳng
    try:
        if url.startswith("http"):
            urllib.request.urlretrieve(url, out_path)
        else:
            urllib.request.urlretrieve(flow_url.rstrip("/") + url, out_path)
    except Exception as e:
        return False, f"tải lỗi: {str(e)[:140]}"
    if os.path.getsize(out_path) < min_size:
        return False, "file quá nhỏ"
    return True, "ok"


def _gen_visual(flow_url, prompt, duration, out_path, aspect="9:16", visual="video"):
    """[16/09] 1 cảnh = clip Veo (visual=video) hoặc ảnh Flow → clip tĩnh (visual=image). Trả (ok, msg)."""
    if visual != "image":
        return _gen_clip(flow_url, prompt, duration, out_path, aspect=aspect)
    img = out_path[:-4] + ".png"
    ok, msg = _gen_image(flow_url, prompt, img, aspect=aspect)
    if not ok:
        return ok, msg
    return _img_to_clip(img, out_path, duration, aspect)


ZOOM_CYCLE = ["in", "out", "tight", "in", "out", "punch"]


def run(opts: dict, progress=lambda p, m: None) -> dict:
    """opts: script, style, voice, rate, gap, transition, zoom, duration, speed,
    aspect (9:16|16:9), visual (video|image), flow_agent_url, llm_cfg, job_dir, name.
    Trả {ok, out, scenes, source, error}."""
    job = opts["job_dir"]
    os.makedirs(job, exist_ok=True)
    style = opts.get("style", "phan")
    dur_each = int(opts.get("duration", 4))
    name = opts.get("name") or "video"
    aspect = "16:9" if opts.get("aspect") == "16:9" else "9:16"       # [16/09] khung ra
    visual = "image" if opts.get("visual") == "image" else "video"     # [16/09] nguồn hình mỗi cảnh
    vtag = "ảnh" if visual == "image" else "Veo"

    # 1) enrich kịch bản → cảnh
    progress(3, "Phân tích kịch bản…")
    scenes, source = prompts.enrich_script(opts["script"], style, opts.get("llm_cfg"))
    if not scenes:
        return {"ok": False, "error": "Kịch bản rỗng / không phân tích được"}
    n = len(scenes)
    progress(6, f"{n} cảnh (nguồn prompt: {source}).")

    # 2) giọng — CHỈ edge-tts NamMinh (đọc một mạch + siết nghỉ, đúng công thức skill).
    # KHÔNG fallback giọng máy macOS: robot = "giọng sai". Thiếu edge-tts thì BÁO LỖI RÕ.
    edge = _edge_tts()
    if not edge:
        return {"ok": False, "scenes": scenes, "error": (
            "Thiếu edge-tts (giọng đọc). Cài lại: chạy 'bash setup.sh', "
            "hoặc '.venv/bin/pip install edge-tts'. (App khong dung giong may macOS.)")}
    progress(10, "Tạo giọng đọc (edge-tts NamMinh)…")
    with open(os.path.join(job, "script.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(s["doc"] for s in scenes) + "\n")
    try:
        subprocess.run(["python3", os.path.join(SCRIPTS, "voice_smooth.py"),
                        "--sentences", os.path.join(job, "script.txt"), "--outdir", job,
                        "--voice", opts.get("voice", "vi-VN-NamMinhNeural"),
                        "--rate", opts.get("rate", "+8%"), "--gap", str(opts.get("gap", 0.30)),
                        "--edge-tts", edge], check=True, capture_output=True, timeout=180)
    except subprocess.CalledProcessError as e:
        return {"ok": False, "scenes": scenes, "error": (
            "Tạo giọng edge-tts lỗi (thường do MẤT MẠNG — edge-tts cần internet): "
            + (e.stderr or b"").decode(errors="replace")[-200:])}
    except Exception as e:
        return {"ok": False, "scenes": scenes, "error": f"Tạo giọng lỗi: {str(e)[:200]}"}
    if not os.path.exists(os.path.join(job, "voice_tight.m4a")):
        return {"ok": False, "scenes": scenes,
                "error": "edge-tts chạy xong nhưng không tạo được voice_tight.m4a (giọng lỗi)."}
    tim = json.load(open(os.path.join(job, "timings.json")))
    g = tim["groups"]; vend = tim.get("voice_end", g[-1]["end"])
    starts = [x["start"] for x in g]; bounds = starts[1:] + [vend]
    durs = [round(bounds[i] - starts[i], 3) for i in range(n)]

    # auto-B-roll: nếu bật, TỰ đặt broll cho cảnh xen kẽ đủ dài (cảnh chưa có broll thủ công)
    if opts.get("auto_broll"):
        for i, sc in enumerate(scenes):
            if not sc.get("broll") and durs[i] >= 1.2 and i % 2 == 1:
                sc["broll"] = ("cinematic extreme close-up insert shot, "
                               + (sc.get("hinh") or "the key object") + ", shallow depth of field")

    # 3) gen clip Veo từng cảnh + B-roll cutaway (cảnh nào có broll thì gen thêm 1 clip phụ)
    flow = opts.get("flow_agent_url", "http://127.0.0.1:8001")
    clips = []
    broll_clips = {}                       # i (0-based) -> path clip B-roll
    n_broll = sum(1 for sc in scenes if sc.get("broll"))
    total = n + n_broll                    # tổng clip để chia % (chính + B-roll)
    done = 0
    for i, sc in enumerate(scenes):
        progress(15 + int(58 * done / max(1, total)), f"Gen cảnh {i+1}/{n} ({vtag} {aspect})…")
        p = prompts.build_video_prompt(style, sc["hinh"], aspect)
        out = os.path.join(job, f"clip{i+1}.mp4")
        ok, msg = _gen_visual(flow, p, dur_each, out, aspect, visual)
        if not ok:
            ok, msg = _gen_visual(flow, p, dur_each, out, aspect, visual)  # retry 1 lần
        if not ok:
            return {"ok": False, "error": f"Cảnh {i+1} gen hỏng: {msg}", "scenes": scenes}
        clips.append(out); done += 1
        if sc.get("broll"):                # B-roll: gen clip phụ; LỖI thì bỏ qua (không hỏng video)
            progress(15 + int(58 * done / max(1, total)), f"Gen B-roll cảnh {i+1} ({vtag})…")
            bp = prompts.build_video_prompt(style, sc["broll"], aspect)
            bout = os.path.join(job, f"broll{i+1}.mp4")
            bok, _ = _gen_visual(flow, bp, dur_each, bout, aspect, visual)
            if not bok:
                bok, _ = _gen_visual(flow, bp, dur_each, bout, aspect, visual)
            if bok:
                broll_clips[i] = bout; done += 1

    # 4) project.json cho build_video2
    progress(78, "Dựng phụ đề + ráp video…")
    zoom_opt = opts.get("zoom", "auto")
    # mốc bắt đầu mỗi cảnh = cộng dồn durs (khớp scene_start của build_video2, cả hardcut & xfade)
    scene_start = [0.0]
    for i in range(1, n):
        scene_start.append(round(scene_start[-1] + durs[i - 1], 3))
    broll_list = []
    for i, bclip in sorted(broll_clips.items()):
        bdur = round(min(1.5, durs[i] * 0.5), 2)                 # cutaway ngắn, ≤ nửa cảnh
        at = round(scene_start[i] + max(0.3, durs[i] * 0.25), 2)  # chèn ~1/4 sau khi vào cảnh
        broll_list.append({"clip": bclip, "at": at, "dur": bdur, "zoom": "in"})
    project = {
        "out": os.path.join(job, f"{name}_{'16x9' if aspect == '16:9' else '9x16'}.mp4"),
        "aspect": aspect,
        "voice": os.path.join(job, "voice_tight.m4a"),
        "speed": float(opts.get("speed", 1.15)),
        "delogo": visual == "video",       # ảnh Flow không có logo Veo góc phải
        "transition": {"type": opts.get("transition", "hardcut"), "dur": 0.25},
        "subs": {"style": prompts.SUB_STYLE.get(style, "phan")},
        "scenes": [
            {"clip": clips[i], "dur": durs[i],
             "zoom": (ZOOM_CYCLE[i % len(ZOOM_CYCLE)] if zoom_opt == "auto" else zoom_opt),
             "sub": scenes[i]["phude"]}
            for i in range(n)
        ],
        "broll": broll_list,
        "sfx": {"enabled": bool(opts.get("sfx", True)), "gain": float(opts.get("sfx_gain", 0.3))},
    }
    pj = os.path.join(job, "project.json")
    json.dump(project, open(pj, "w", encoding="utf-8"), ensure_ascii=False)
    try:
        # sys.executable = python venv app (có Pillow) — build_video2 gọi make_subs_v2 (cần PIL) qua sys.executable
        subprocess.run([sys.executable, os.path.join(SCRIPTS, "build_video2.py"), pj],
                       check=True, capture_output=True, timeout=900)
    except subprocess.CalledProcessError as e:
        return {"ok": False, "error": f"Ráp lỗi: {(e.stderr or b'').decode()[-200:]}", "scenes": scenes}

    out = project["out"]
    if not os.path.exists(out):
        return {"ok": False, "error": "Không tạo được file cuối", "scenes": scenes}

    # 5) ENHANCE (tuỳ chọn): màu điện ảnh + thẻ hook/CTA + nhạc nền
    try:
        from . import enrich_av
        grade = opts.get("grade")
        if grade and grade != "none":
            gvf = enrich_av.grade_vf(grade)
            if gvf:
                g = os.path.join(job, "_graded.mp4")
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", out, "-vf", gvf,
                                "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                                "-pix_fmt", "yuv420p", "-c:a", "copy", g], check=True)
                os.replace(g, out)
        parts = []
        if opts.get("hook"):
            hk = os.path.join(job, "_hook.mp4")
            enrich_av.make_card_clip(opts["hook"], hk, style=style, dur=1.2,
                                     sub=opts.get("hook_sub"), workdir=job, aspect=aspect); parts.append(hk)
        parts.append(out)
        if opts.get("cta"):
            ct = os.path.join(job, "_cta.mp4")
            enrich_av.make_card_clip(opts["cta"], ct, style=style, dur=1.4, workdir=job, aspect=aspect); parts.append(ct)
        if len(parts) > 1:
            full = os.path.join(job, "_full.mp4")
            enrich_av.concat_parts(parts, full); os.replace(full, out)
        if opts.get("music"):
            mus = enrich_av.pick_music(opts.get("music_name"))
            if mus:
                mo = os.path.join(job, "_mus.mp4")
                if enrich_av.add_music(out, mo, mus, float(opts.get("music_gain", 0.12))):
                    os.replace(mo, out)
    except Exception as e:
        print("[core] enhance lỗi (bỏ qua):", e)

    progress(100, "Xong.")
    return {"ok": True, "out": out, "scenes": scenes, "source": source,
            "duration": round(_ff_dur(out), 2)}
