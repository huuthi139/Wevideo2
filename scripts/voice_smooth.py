#!/usr/bin/env python3
"""Giọng đọc MƯỢT cho video người que/Veo — công thức chốt 24/07/2026.

Vấn đề giải quyết: (1) gen TTS từng câu rời rồi ghép → chỗ nối cụt hơi, nghe
"sượng"; (2) đọc một mạch thì TTS nghỉ ~0.85s sau mỗi câu → nhịp nhanh nghe
như bị ngắt. Cách làm ĐÚNG: đọc MỘT MẠCH (ngữ điệu liền) → dò khoảng lặng →
SIẾT nghỉ giữa câu về --gap giây (giữ nghỉ dấu phẩy trong câu).

Dùng:
  python3 voice_smooth.py --sentences script.txt --outdir /path/du-an \\
      [--voice vi-VN-NamMinhNeural] [--rate +20%] [--gap 0.30] [--edge-tts /path/edge-tts]

  script.txt: mỗi dòng MỘT câu/nhóm ý (sẽ thành 1 nhóm mốc thời gian).

Ra:
  voice_full.mp3   — bản đọc một mạch (giữ để đối chiếu)
  voice_tight.m4a  — bản đã siết nghỉ + đệm 1s cuối → DÙNG BẢN NÀY để build
  timings.json     — mốc từng nhóm câu trên timeline MỚI:
                     {"groups":[{"i":1,"text":..., "start":..,"end":..,
                                 "inner":[mốc cắt nội bộ giữa các run]}],
                      "voice_end":..}
  → cắt cảnh theo "start"/"end" (ranh giới cảnh = trung điểm giữa end nhóm
    trước và start nhóm sau); câu dài muốn thêm nhịp cắt thì cắt tại "inner".
Sau khi build video: xuất thêm bản 1.15x (setpts=PTS/1.15 + atempo=1.15).
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

PAD_IN, PAD_OUT = 0.08, 0.10


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sentences", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--voice", default="vi-VN-NamMinhNeural")
    ap.add_argument("--rate", default="+20%")
    ap.add_argument("--gap", type=float, default=0.30)
    ap.add_argument("--edge-tts", default="edge-tts")
    args = ap.parse_args()

    out = Path(args.outdir); out.mkdir(parents=True, exist_ok=True)
    sentences = [l.strip() for l in open(args.sentences, encoding="utf-8")
                 if l.strip() and not l.strip().startswith("#")]
    if not sentences:
        sys.exit("script.txt rỗng")
    et = args.edge_tts if shutil.which(args.edge_tts) or Path(args.edge_tts).exists() else None
    if et is None:
        sys.exit(f"không thấy edge-tts ({args.edge_tts})")

    # 1) Đọc MỘT MẠCH
    mp3 = out / "voice_full.mp3"
    for att in range(4):
        r = sh([et, "--voice", args.voice, f"--rate={args.rate}",
                "--text", " ".join(sentences), "--write-media", str(mp3)])
        if r.returncode == 0:
            break
    else:
        sys.exit("TTS lỗi: " + r.stderr[-200:])

    # 2) Dò khoảng lặng → run → nhóm câu (gap > 0.6s = nghỉ hết câu)
    det = sh(["ffmpeg", "-i", str(mp3), "-af", "silencedetect=n=-33dB:d=0.22",
              "-f", "null", "-"]).stderr
    starts = [0.0]; ends = []
    for m in re.finditer(r"silence_start: ([\d.]+)", det): ends.append(float(m.group(1)))
    for m in re.finditer(r"silence_end: ([\d.]+)", det): starts.append(float(m.group(1)))
    dur = float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                    "-of", "csv=p=0", str(mp3)]).stdout.strip())
    if len(ends) < len(starts): ends.append(dur)
    runs = [[s, e] for s, e in zip(starts, ends) if e - s > 0.25]
    groups = [[runs[0]]]
    for prev, cur in zip(runs, runs[1:]):
        (groups.append([cur]) if cur[0] - prev[1] > 0.6 else groups[-1].append(cur))
    if len(groups) != len(sentences):
        print(f"⚠ {len(groups)} nhóm ≠ {len(sentences)} dòng script — kiểm tra "
              "câu có dấu chấm giữa chừng (mỗi dấu chấm = 1 lần nghỉ dài). "
              "timings.json vẫn xuất theo NHÓM.", file=sys.stderr)

    # 3) Cắt từng nhóm + ghép với khoảng nghỉ --gap → voice_tight
    segs = []
    for i, g in enumerate(groups, 1):
        s = max(0.0, g[0][0] - PAD_IN); e = min(dur, g[-1][1] + PAD_OUT)
        f = out / f"_seg{i}.wav"
        sh(["ffmpeg", "-y", "-i", str(mp3), "-ss", f"{s:.3f}", "-to", f"{e:.3f}",
            "-ar", "24000", "-ac", "1", str(f)])
        segs.append((f, e - s))
    gap_f = out / "_gap.wav"
    sh(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
        "-t", f"{args.gap:.2f}", str(gap_f)])
    lst = out / "_tight.txt"
    with open(lst, "w") as fh:
        for i, (f, _) in enumerate(segs):
            if i:
                fh.write(f"file '{gap_f}'\n")
            fh.write(f"file '{f}'\n")
    sh(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
        "-af", "apad=pad_dur=1.0", "-c:a", "aac", "-b:a", "192k",
        str(out / "voice_tight.m4a")])

    # 4) Mốc nhóm trên timeline mới
    result = []; pos = 0.0
    for i, ((f, seglen), g) in enumerate(zip(segs, groups), 1):
        ns = pos + PAD_IN; ne = pos + seglen - PAD_OUT
        inner = [round(ns + (a[1] + b[0]) / 2 - g[0][0], 3)
                 for a, b in zip(g, g[1:])]
        result.append({"i": i,
                       "text": sentences[i - 1] if i <= len(sentences) else "",
                       "start": round(ns, 3), "end": round(ne, 3), "inner": inner})
        pos += seglen + args.gap
    data = {"groups": result, "voice_end": round(pos - args.gap, 3)}
    json.dump(data, open(out / "timings.json", "w"), ensure_ascii=False, indent=1)
    print(json.dumps(data, ensure_ascii=False))


if __name__ == "__main__":
    main()
