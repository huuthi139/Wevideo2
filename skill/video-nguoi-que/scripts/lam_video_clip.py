#!/usr/bin/env python3
"""LÀM VIDEO NGƯỜI-QUE ĐỘNG — TRỌN LUỒNG 1 LỆNH, KHÔNG CẦN LLM/AGENT.

    cd <thư-mục-dự-án>            # nơi có kichban.json
    python3 ~/.claude/skills/video-nguoi-que/scripts/lam_video_clip.py [kichban.json]

Điều kiện: flow-agent :8001 chạy + tab Flow đã đăng nhập + extension flow-agent
(có __normEsc) nạp trong Chrome. Luồng (thuần HTTP + script, không AI điều khiển):
  1) Mỗi cảnh: POST /v1/videos/generations {prompt}  → engine tự gen + lấy URL /video/
     + tải → clips/<key>.mp4 (thứ tự = thứ tự cảnh; retry 3× + giãn nhịp tránh Flow throttle).
  2) 2_tao_giong.py       — giọng edge-tts.
  3) 3_dung_video_clip.py — ráp clip + phụ đề kinetic + logo + 1.12×.
Ra: <ten>_9x16.mp4. Chạy lại thì bỏ qua clip đã tải (an toàn khi đứt giữa chừng).
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

os.environ["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + os.environ.get("PATH", "")  # ffmpeg Homebrew: con (2_tao_giong/3_dung_video) thừa kế khi chạy headless

SKILL = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(os.path.dirname(SKILL), ".venv-tts", "bin", "python")
if not os.path.exists(PY):
    PY = sys.executable
API = os.environ.get("FLOW_AGENT_URL", "http://127.0.0.1:8001") + "/v1/videos/generations"
STYLE = ("White chalk stick figure hand-drawn animation on a dark green chalkboard, "
         "simple chalk line art style, {scene}, gentle subtle chalk motion, "
         "no text, no words, no numbers")


def gen_clip(scene, out_path, duration=4):
    body = json.dumps({"prompt": STYLE.format(scene=scene),
                       "aspect_ratio": "VIDEO_ASPECT_RATIO_PORTRAIT",
                       "duration": duration}).encode()
    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=470) as r:
        d = json.loads(r.read())
    url = (d.get("data") or [{}])[0].get("url", "")
    if not url:
        raise RuntimeError(f"gen thất bại: {json.dumps(d)[:200]}")
    urllib.request.urlretrieve(url, out_path)
    return os.path.getsize(out_path)


def main(cfg_path):
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    os.makedirs("clips", exist_ok=True)
    n = len(cfg["nhip"])
    print(f"=== B1: GEN {n} CLIP VIDEO qua /v1/videos (engine tự gen+tải, không LLM) ===", flush=True)
    for i, nh in enumerate(cfg["nhip"], 1):
        key = nh["anh"]
        out = f"clips/{key}.mp4"
        if os.path.exists(out) and os.path.getsize(out) > 10000:
            print(f">>> [{i}/{n}] {key}: đã có, bỏ qua", flush=True)
            continue
        scene = cfg["anh_can_gen"][key]
        print(f">>> [{i}/{n}] {key}: {scene[:52]}…", flush=True)
        for attempt in range(1, 4):   # Flow đôi khi chặn nhịp gen nhanh → retry
            try:
                sz = gen_clip(scene, out)
                print(f"    ✓ {out} ({sz/1024:.0f} KB)", flush=True)
                break
            except Exception as e:
                print(f"    ! lần {attempt}/3 lỗi: {str(e)[:80]} — chờ 20s", flush=True)
                if attempt == 3:
                    raise
                time.sleep(20)
        time.sleep(8)   # giãn nhịp giữa các clip (tránh cờ "hoạt động bất thường")
    print("=== B2: GIỌNG (edge-tts) ===", flush=True)
    subprocess.run([PY, os.path.join(SKILL, "2_tao_giong.py"), cfg_path], check=True)
    print("=== B3: RÁP (clip + phụ đề + logo + 1.12×) ===", flush=True)
    subprocess.run([PY, os.path.join(SKILL, "3_dung_video_clip.py"), cfg_path], check=True)
    print(f"\n✅ XONG: {cfg['ten']}_9x16.mp4", flush=True)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "kichban.json")
