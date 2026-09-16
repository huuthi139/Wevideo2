#!/usr/bin/env python3
"""B3 (CLIP ĐỘNG) — như 3_dung_video.py nhưng mỗi nhịp là 1 CLIP VIDEO Flow
(Veo/Omni) thay vì Ken Burns trên ảnh tĩnh.

    python3 3_dung_video_clip.py kichban.json

Cần:
  · clips/<key>.mp4   — clip Flow đã tải (key = nhip[].anh, vd a01.mp4)
  · audio/b<i>.wav + nhip[].dur   — chạy 2_tao_giong.py trước
  · anh/<key>.jpg     — CHỈ cho thumbnail; thiếu thì script tự trích 1 khung từ clip

Khác 3_dung_video.py DUY NHẤT ở hàm canh(): cắt clip tới độ dài nhịp (dur+gap),
scale/crop về 1080x1920, KHÔNG zoompan. Mọi bước khác (phụ đề kinetic, chữ ký WSS,
giọng, 1.12×, thumbnail) tái dùng nguyên từ 3_dung_video.py.

Lấy clip từ Flow v2 (cookie-gated, curl 403): gen ở chế độ Video 9:16 rồi tải bằng
flow-agent (SW fetch có cookie). Xem CAI-DAT-MAY-MOI.md mục "Tải VIDEO từ Flow".
"""
import importlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
d3 = importlib.import_module("3_dung_video")   # tái dùng toàn bộ B3 ảnh


def canh(cfg):
    """[CLIP ĐỘNG] Mỗi nhịp = 1 clip clips/<key>.mp4, cắt tới dur+gap, scale/crop 1080x1920."""
    W, H, FPS, ff = d3.W, d3.H, d3.FPS, d3.ff
    gap = cfg.get("gap", 0.10)
    t = 0.0
    for k, n in enumerate(cfg["nhip"]):
        d_ = round(n["dur"] + gap, 3)
        n["clip"] = d_
        n["start"] = round(t, 3)
        t = round(t + d_, 3)
        src = f"clips/{n['anh']}.mp4"
        if not os.path.exists(src):
            sys.exit(f"Thiếu clip {src} — gen clip Flow (Video 9:16) rồi tải về clips/.")
        ff("-i", src, "-t", str(d_), "-vf",
           (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},setsar=1,fps={FPS},format=yuv420p"),
           "-an", "-r", str(FPS), "-c:v", "libx264", "-preset", "medium",
           "-crf", "19", f"_sc{k+1}.mp4")
    open("_list.txt", "w").write("".join(f"file '_sc{i}.mp4'\n" for i in range(1, len(cfg["nhip"]) + 1)))
    ff("-f", "concat", "-safe", "0", "-i", "_list.txt", "-c", "copy", "_base.mp4")
    return t


# Thay Ken-Burns-ảnh bằng clip-video; main() của d3 gọi canh() qua global nên nhận bản này.
d3.canh = canh


def main(cfg_path):
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    th = cfg.get("thumbnail")
    if th:  # thiếu ảnh thumbnail → tự trích 1 khung từ clip tương ứng
        os.makedirs("anh", exist_ok=True)
        jpg = f"anh/{th['anh']}.jpg"
        clip = f"clips/{th['anh']}.mp4"
        if not os.path.exists(jpg) and os.path.exists(clip):
            d3.ff("-ss", "2", "-i", clip, "-frames:v", "1", "-vf", "scale=1080:1920", jpg)
    d3.main(cfg_path)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "kichban.json")
