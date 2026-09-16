#!/usr/bin/env python3
"""B1 (cách HIỆN HÀNH, từ 13/09/2026) — Gen ảnh trên GIAO DIỆN Flow rồi kéo về qua AppleScript.

Flow đã dời labs.google → flow.google.com (11/09/2026): API aisandbox + token ya29 CHẾT,
`1_tao_anh.py` (qua flow-agent :8001) không còn chạy được. Cách này KHÔNG cần flow-agent.

    python3 1_tao_anh_ui.py prompts kichban.json     # in các prompt để dán lên Flow (từng cái)
    python3 1_tao_anh_ui.py tai     kichban.json     # kéo N ảnh MỚI NHẤT từ tab Flow → anh/<key>.jpg
    python3 1_tao_anh_ui.py tai     kichban.json --bo-qua a03   # ảnh nào đã có thì giữ, chỉ kéo phần thiếu

Quy trình (Claude lái Chrome bằng extension "Claude in Chrome", hoặc người làm tay):
  1. Mở tab Chrome: https://flow.google.com/project/<id> (đã đăng nhập Google có gói AI).
  2. Chip cài đặt cạnh ô prompt → chọn "Hình ảnh" · 9:16 · Nano Banana 2 · x1 (0 tín dụng).
  3. Dán từng prompt (lệnh `prompts`), bấm → gửi. Gửi cái sau cách cái trước ~4s.
  4. Chờ tất cả render xong (không còn ô % ở đầu lưới).
  5. Chạy `tai`: script bảo Chrome (AppleScript) fetch N ảnh mới nhất BẰNG COOKIE của trang,
     trả base64 về, lưu anh/<key>.jpg + anh/_sheet.jpg để soi lại thứ tự.

Điều kiện: macOS + Google Chrome + bật  View ▸ Developer ▸ Allow JavaScript from Apple Events.
Vì sao phải đi đường này: ảnh Flow nằm sau cookie đăng nhập (curl → HTML login), trang chặn
fetch tới localhost (Private Network Access), clipboard cần focus, còn kênh JS của extension
Claude lọc chuỗi base64. AppleScript `execute javascript` là kênh duy nhất trả bytes sạch.
"""
import base64, io, json, os, subprocess, sys

NEN = {
 "trang": ("Minimalist black stick figure businessman drawn with bold black ink brush lines "
           "on a clean pure white background, hand-drawn doodle style, red necktie, cute "
           "friendly rounded face, a few bright accent colors used sparingly, lots of empty "
           "white space, flat 2D vector illustration, crisp edges, "),
 "phan":  ("White chalk stick figure drawn on a dark green chalkboard, hand-drawn chalk line art, "
           "simple minimal, slightly rough chalk texture, no color, vertical 9:16 composition, "),
}
CAM = "no text, no words, no letters, no numbers. "

# JS chạy TRONG tab Flow: gom ô ẢNH đã gen — src dạng /asb/...=s512-rw (thumbnail VIDEO không có đuôi =sNNN-rw),
# mới nhất trước; nâng lên bản =s1600 (768×1376) rồi trả base64 nối bằng xuống dòng.
JS_FETCH = r"""
window.__nq_imgs=null;
(async()=>{
  const want=%(n)d, portrait=%(portrait)s;
  const imgs=Array.from(document.querySelectorAll('img')).filter(i=>
      /\/asb\/.*=s\d+-rw$/.test(i.src) && i.naturalWidth>100 &&
      ((i.naturalHeight>i.naturalWidth)===portrait)).slice(0,want);
  const arr=[];
  for(const im of imgs){
    const u=im.src.replace(/=s\d+-rw$/,'=s1600-rw');
    const b=await (await fetch(u)).blob();
    arr.push(await new Promise(r=>{const f=new FileReader();f.onload=()=>r(f.result.split(',')[1]);f.readAsDataURL(b);}));
  }
  window.__nq_imgs=arr; return 'n='+arr.length;
})(); 'started'
"""
JS_READ = "window.__nq_imgs ? window.__nq_imgs.join(String.fromCharCode(10)) : 'none'"

AS = '''tell application "Google Chrome"
set out to ""
set hit to missing value
-- ưu tiên tab ĐANG ACTIVE của cửa sổ trước; tránh dính tab Flow cũ chưa reload
repeat with w in windows
  if URL of active tab of w contains "flow.google.com/project" then
    set hit to active tab of w
    exit repeat
  end if
end repeat
if hit is missing value then
  repeat with w in windows
    repeat with t in tabs of w
      if URL of t contains "flow.google.com/project" then
        set hit to t
        exit repeat
      end if
    end repeat
    if hit is not missing value then exit repeat
  end repeat
end if
if hit is missing value then return "NO_TAB"
return execute hit javascript "%s"
end tell'''


def osa(js):
    js = js.replace("\\", "\\\\").replace('"', '\\"')
    r = subprocess.run(["osascript", "-e", AS % js], capture_output=True, text=True)
    if r.returncode:
        err = r.stderr.strip()
        if "Executing JavaScript through AppleScript is turned off" in err or "-1743" in err or "not allowed" in err:
            sys.exit("Chrome chưa cho AppleScript chạy JS. Bật: Chrome ▸ menu View ▸ Developer ▸ "
                     "Allow JavaScript from Apple Events, rồi chạy lại.")
        sys.exit("osascript lỗi: " + err[:300])
    out = r.stdout.rstrip("\n")
    if out == "NO_TAB":
        sys.exit("Chrome không có tab flow.google.com/project nào đang mở.")
    return out


def cmd_prompts(cfg):
    base = NEN[cfg.get("phong_cach", "trang")] + CAM
    os.makedirs("anh", exist_ok=True)
    with open("anh/_prompts.txt", "w", encoding="utf-8") as f:
        for k, v in cfg["anh_can_gen"].items():
            print(f"===== {k}\n{base}{v}\n"); f.write(f"{k}\t{base}{v}\n")
    print("→ đã ghi anh/_prompts.txt. Dán LẦN LƯỢT lên Flow (Hình ảnh · 9:16 · x1), a01 trước.")


def cmd_tai(cfg, bo_qua):
    keys = [k for k in cfg["anh_can_gen"] if k not in bo_qua and not os.path.exists(f"anh/{k}.jpg")]
    if not keys:
        print("đã đủ ảnh, không kéo gì."); return
    n = len(keys)
    portrait = "true" if cfg.get("khung", "9:16") != "16:9" else "false"
    if osa(JS_FETCH % {"n": n, "portrait": portrait}) != "started":
        sys.exit("không khởi động được fetch trong tab Flow (tab có mở đúng project chưa?)")
    import time
    for _ in range(30):
        time.sleep(3)
        data = osa(JS_READ)
        if data != "none": break
    else:
        sys.exit("tab Flow không trả ảnh sau 90s")
    lines = [l for l in data.split("\n") if l.strip()]
    if len(lines) != n:
        sys.exit(f"cần {n} ảnh, tab chỉ có {len(lines)} ảnh mới phù hợp — chờ render xong rồi chạy lại")
    from PIL import Image
    os.makedirs("anh", exist_ok=True)
    thumbs = []
    # lưới Flow: MỚI NHẤT trước → ảnh đầu tiên = key gửi SAU CÙNG
    for line, key in zip(lines, reversed(keys)):
        im = Image.open(io.BytesIO(base64.b64decode(line))).convert("RGB")
        im.save(f"anh/{key}.jpg", quality=95); thumbs.append((key, im.resize((192, 344))))
        print(f"OK {key} {im.size[0]}x{im.size[1]}")
    thumbs.sort()
    sheet = Image.new("RGB", (192 * len(thumbs), 344), "white")
    for i, (_, t) in enumerate(thumbs): sheet.paste(t, (192 * i, 0))
    sheet.save("anh/_sheet.jpg", quality=80)
    print(f"\n{n} ảnh → anh/. SOI anh/_sheet.jpg (trái→phải = a01→): sai thứ tự thì đổi tên tay.")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("prompts", "tai"):
        sys.exit(__doc__)
    cfg_path = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "kichban.json"
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    bo_qua = sys.argv[sys.argv.index("--bo-qua") + 1].split(",") if "--bo-qua" in sys.argv else []
    cmd_prompts(cfg) if sys.argv[1] == "prompts" else cmd_tai(cfg, bo_qua)
