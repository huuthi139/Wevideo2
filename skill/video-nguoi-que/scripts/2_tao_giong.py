#!/usr/bin/env python3
"""B2 — Giọng đọc edge-tts + CẮT CHẶT. Miễn phí, chạy máy, không cần khoá.

    python3 2_tao_giong.py kichban.json

Mỗi nhịp một file `audio/b<i>.wav` đã bỏ khoảng lặng thừa; ghi độ dài thật
trở lại kichban.json (`nhip[i].dur`). Độ dài này quyết định nhịp cắt hình.

NGUYÊN TẮC VÀNG: GIỌNG LÀM TRƯỚC. Không bao giờ ép giọng theo hình.
"""
import json, os, subprocess, sys, time

os.environ["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + os.environ.get("PATH", "")  # ffmpeg Homebrew khi chạy headless (ssh/launchd)

HERE = os.path.dirname(os.path.abspath(__file__))
TTS_CANDIDATES = [
    os.path.join(HERE, "..", ".venv-tts", "bin", "edge-tts"),   # cài bằng cai-dat.sh
    os.path.expanduser("~/.venv-tts/bin/edge-tts"),
    "/Volumes/DATA/AI-APP/mascot-nguoi-que/.venv-tts/bin/edge-tts",
    os.path.expanduser("~/.local/bin/edge-tts"), "edge-tts",
]
# bỏ lặng đầu/cuối; stop_silence 0.10 = giữ lại nhịp thở tối thiểu
SILENCE = ("silenceremove=start_periods=1:start_silence=0.05:start_threshold=-45dB:"
           "stop_periods=-1:stop_silence=0.10:stop_threshold=-45dB")


def tts_bin():
    for c in TTS_CANDIDATES:
        if os.path.exists(c) or c == "edge-tts":
            if subprocess.run([c, "--version"], capture_output=True).returncode == 0:
                return c
    sys.exit("Không tìm thấy edge-tts. Cài: python3 -m venv .venv && .venv/bin/pip install edge-tts")


def dur(p):
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", p]).strip())


def main(cfg_path):
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    tts = tts_bin()
    voice = cfg.get("giong", "vi-VN-NamMinhNeural")
    rate = cfg.get("rate", "+6%")
    os.makedirs("audio", exist_ok=True)
    tong = 0.0
    for i, n in enumerate(cfg["nhip"], 1):
        mp3, wav = f"audio/b{i}.mp3", f"audio/b{i}.wav"
        for lan in range(4):          # edge-tts gọi máy chủ MS — thi thoảng rớt mạng
            r = subprocess.run([tts, "--voice", voice, "--rate", rate,
                                "--text", n["doc"], "--write-media", mp3],
                               capture_output=True)
            if r.returncode == 0:
                break
            time.sleep(2)
        else:
            sys.exit(f"nhịp {i}: edge-tts hỏng sau 4 lần thử")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp3,
                        "-af", SILENCE, "-ar", "44100", "-ac", "2", wav], check=True)
        n["dur"] = round(dur(wav), 3)
        tong += n["dur"]
        print(f"  nhịp {i:2d} [{n['anh']}] {n['dur']:5.2f}s  {n['doc'][:46]}")
    json.dump(cfg, open(cfg_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    tocdo = cfg.get("toc_do_cuoi", 1.15)
    print(f"\n{len(cfg['nhip'])} nhịp · giọng {tong:.2f}s · "
          f"{tong/len(cfg['nhip']):.2f}s/nhịp · sau {tocdo}× ≈ {tong/tocdo:.1f}s")
    if tong / len(cfg["nhip"]) > 2.2:
        print("⚠ nhịp DÀI hơn 2.2s — cắt câu ngắn lại, video sẽ lê thê.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "kichban.json")
