#!/usr/bin/env python3
"""B1 — Gen ảnh nhân vật qua flow-agent. MIỄN PHÍ, không tốn credit.

    python3 1_tao_anh.py kichban.json

Đọc `anh_can_gen` (mô tả tiếng Anh) → gọi :8001 → lưu vào ./anh/<key>.jpg
Luôn truyền `anh_goc_giu_nhan_vat` vào ref_media_ids → CÙNG một nhân vật.
Bỏ ref là ra người khác — đây là lỗi hay gặp nhất.
"""
import json, os, sys, time, urllib.request

API = "http://127.0.0.1:8001/v1/images/generations"

NEN = {
 "trang": ("Minimalist black stick figure businessman drawn with bold black ink brush lines "
           "on a clean pure white background, hand-drawn doodle style, red necktie, cute "
           "friendly rounded face, a few bright accent colors used sparingly, lots of empty "
           "white space, flat 2D vector illustration, crisp edges, "),
 "phan":  ("White chalk stick figure drawn on a dark green chalkboard, shaky hand-drawn chalk "
           "lines, chalk dust texture, simple minimal chalk drawing, vertical composition, "),
}
CAM = "no text, no words, no letters, no numbers. "


def main(cfg_path):
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    base = NEN[cfg.get("phong_cach", "trang")] + CAM
    ref = cfg.get("anh_goc_giu_nhan_vat")
    os.makedirs("anh", exist_ok=True)
    ok = 0
    for key, mota in cfg["anh_can_gen"].items():
        dst = f"anh/{key}.jpg"
        if os.path.exists(dst):
            print(f"bỏ qua {key} (đã có)"); ok += 1; continue
        body = {"prompt": base + mota, "size": "1080x1920", "n": 1}
        if ref:
            body["ref_media_ids"] = [ref]
        req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=240) as r:
                item = json.load(r)["data"][0]
            urllib.request.urlretrieve(item["url"], dst)
            print(f"OK {key} {int(time.time()-t0)}s  {item.get('media_id','')[:8]}")
            ok += 1
        except Exception as e:
            print(f"LỖI {key}: {str(e)[:110]}")
            print("  → kiểm: curl -s http://127.0.0.1:8001/health "
                  "(cần extension_connected:true). Token ya29 hết hạn thì chạy lại lần nữa.")
        time.sleep(2)
    print(f"\n{ok}/{len(cfg['anh_can_gen'])} ảnh")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "kichban.json")
