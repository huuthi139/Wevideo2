#!/usr/bin/env python3
"""Assemble the final vertical video: concat chalk clips -> overlay timed
subtitle PNGs -> mix Vietnamese voice + royalty-free music.

Reads ONE project.json (same file make_subs.py uses) so cue timings never
drift between the subtitles and the overlay windows.

Usage:  python3 build_video.py project.json

project.json schema:
{
  "output": "/abs/path/KET-QUA.mp4",
  "clips":  ["c1.mp4", "c2.mp4", ...],   // 1 clip (15s) or many (concat, 15s each)
  "voice":  "voice.mp3",                  // Vietnamese narration
  "music":  "music.m4a",                  // optional; omit for no background music
  "subs_dir": ".",                        // where sub1.png.. live (from make_subs.py)
  "lead_in": 1.2,                          // seconds before narration starts
  "music_volume": 0.09,                    // 9% under the voice (locked default)
  "cues": [ {"start": 1.20, "end": 3.53, "lines": ["...", "..."]}, ... ]
}
All media paths are resolved relative to the JSON file's folder if not absolute.
"""
import json
import os
import subprocess
import sys

cfg_path = os.path.abspath(sys.argv[1])
base_dir = os.path.dirname(cfg_path)
cfg = json.load(open(cfg_path))


def rp(p):
    return p if os.path.isabs(p) else os.path.join(base_dir, p)


clips = [rp(c) for c in cfg["clips"]]
voice = rp(cfg["voice"])
music = rp(cfg["music"]) if cfg.get("music") else None
out = cfg["output"]
subs_dir = rp(cfg.get("subs_dir", base_dir))
lead = cfg.get("lead_in", 1.2)
mvol = cfg.get("music_volume", 0.09)
cues = cfg["cues"]
work = base_dir


def ffprobe_dur(path):
    return float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path]).strip())


# 1) concat clips if more than one
if len(clips) == 1:
    basev = clips[0]
else:
    lst = os.path.join(work, "_concat_list.txt")
    with open(lst, "w") as f:
        for c in clips:
            f.write(f"file '{os.path.abspath(c)}'\n")
    basev = os.path.join(work, "_concat.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat",
                    "-safe", "0", "-i", lst, "-c", "copy", basev], check=True)

dur = ffprobe_dur(basev)

# 2) build filter_complex
n = len(cues)
fc = []
for i, c in enumerate(cues, 1):
    s, e = c["start"], c["end"]
    fo = round(e - 0.22, 2)
    fc.append(f"[{i}:v]format=rgba,fade=t=in:st={s}:d=0.16:alpha=1,"
              f"fade=t=out:st={fo}:d=0.22:alpha=1[o{i}]")
prev = "0:v"
for i, c in enumerate(cues, 1):
    s, e = c["start"], c["end"]
    fc.append(f"[{prev}][o{i}]overlay=enable='between(t,{s},{e})'[v{i}]")
    prev = f"v{i}"

v_idx = n + 1  # voice input index
ms = int(round(lead * 1000))
fc.append(f"[{v_idx}:a]adelay={ms}|{ms},apad,atrim=0:{dur},volume=1.0[va]")
if music:
    m_idx = n + 2
    fo = round(dur - 1.2, 2)
    fc.append(f"[{m_idx}:a]atrim=0:{dur},afade=t=in:st=0:d=1.0,"
              f"afade=t=out:st={fo}:d=1.1,volume={mvol}[ma]")
    fc.append("[va][ma]amix=inputs=2:normalize=0[a]")
    amap = "[a]"
else:
    amap = "[va]"

# 3) assemble command
cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", basev]
for i in range(1, n + 1):
    cmd += ["-loop", "1", "-i", os.path.join(subs_dir, f"sub{i}.png")]
cmd += ["-i", voice]
if music:
    cmd += ["-i", music]
cmd += ["-filter_complex", ";".join(fc),
        "-map", f"[v{n}]", "-map", amap,
        "-c:v", "libx264", "-crf", "19", "-preset", "medium", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-t", str(dur), out]
subprocess.run(cmd, check=True)
print("OUTPUT:", out, f"({dur:.1f}s)")
