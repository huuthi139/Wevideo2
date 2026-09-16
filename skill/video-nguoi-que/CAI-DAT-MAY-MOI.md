# VIDEO NGƯỜI QUE — CÀI TRÊN MÁY MỚI & QUY TRÌNH TRỌN GÓI

Cập nhật 15/09/2026. Đã chạy thực chiến 2 video (`ky-luat`, `that-bai`) bằng đúng quy trình này.

## 1. Bức tranh toàn cảnh

```
kichban.json ──B1──▶ anh/a01..a07.jpg ──┐
             ──B2──▶ audio/b1..b7.wav ──┼──B3──▶ <ten>_9x16.mp4 + thumbnail.jpg
                     (edge-tts, miễn phí) ┘        (ffmpeg + Pillow, chạy máy)
```

| Bước | Công cụ | Tốn tiền? | Ai làm |
|---|---|---|---|
| B1 ảnh | Google Flow (flow.google.com) · model **Nano Banana 2** · **Chrome + extension Claude in Chrome** · AppleScript | 0 credit (gói AI Pro/Ultra) | Claude lái Chrome, script kéo ảnh |
| B2 giọng | `edge-tts` (Microsoft, không cần khoá) | 0 | script |
| B3 dựng | `ffmpeg` + `Pillow` | 0 | script |

**Không còn cần flow-agent** cho ảnh. (Xem mục 7 nếu muốn biết vì sao.)

## 2. Cài máy mới (macOS) — 10 phút

```bash
# 1. chép thư mục skill vào máy mới
mkdir -p ~/.claude/skills && cp -r video-nguoi-que ~/.claude/skills/
# 2. cài môi trường (ffmpeg, venv edge-tts + Pillow, kiểm font, kiểm Chrome)
bash ~/.claude/skills/video-nguoi-que/cai-dat.sh
```
Việc làm TAY một lần:
1. **Chrome**: cài extension **Claude in Chrome** (Anthropic) và bật trong app Claude (Code tab). Đây là extension DUY NHẤT cần — Claude dùng nó để bấm/gõ trên Flow.
2. **Chrome ▸ View ▸ Developer ▸ Allow JavaScript from Apple Events** = bật. Không bật thì bước kéo ảnh báo lỗi ngay, có hướng dẫn.
3. Chrome **đăng nhập Google có gói AI Pro/Ultra**, mở https://flow.google.com → tạo 1 project → giữ URL `https://flow.google.com/project/<id>`.
4. Chỉ mở **MỘT** tab Flow project khi kéo ảnh (mở 2 tab dễ kéo nhầm bộ cũ).

Windows/Linux: B2, B3 chạy bình thường (font tự tìm DejaVu/Liberation, hoặc thả `.ttf` vào `fonts/`).
B1 kéo ảnh dùng AppleScript nên **chỉ macOS**; máy khác thì tải ảnh tay từ Flow (nút ⬇) rồi đặt tên `anh/a01.jpg…`.

## 3. Quy trình làm một video (câu lệnh cho Claude)

> "Tạo video người que chủ đề X, phong cách bảng phấn, giọng NamMinh" — hoặc "làm như lần trước, nội dung khác".

Claude làm theo thứ tự, người dùng không cần đụng tay:

```bash
mkdir duan && cd duan
cp ~/.claude/skills/video-nguoi-que/mau/vi-du-phan-that-bai.json kichban.json   # sửa nội dung
S=~/.claude/skills/video-nguoi-que/scripts

# B1a — in 7 prompt
python3 $S/1_tao_anh_ui.py prompts kichban.json
# B1b — Claude lái Chrome (Claude in Chrome): mở tab project Flow → chip cài đặt cạnh ô prompt
#       → "Hình ảnh" · 9:16 · Nano Banana 2 · x1 → dán từng prompt (a01→a07), bấm → , cách nhau ~4s
#       → chờ lưới hết ô % (≈ 20–40s/ảnh, chạy song song)
# B1c — kéo 7 ảnh mới nhất về (AppleScript, dùng cookie của Chrome)
python3 $S/1_tao_anh_ui.py tai kichban.json      # → anh/a01..a07.jpg + anh/_sheet.jpg
#       SOI anh/_sheet.jpg: trái→phải phải đúng a01→a07. Sai thì đổi tên tay.

python3 $S/2_tao_giong.py  kichban.json           # B2 giọng, ghi dur vào kichban.json
python3 $S/3_dung_video.py kichban.json           # B3 → <ten>_9x16.mp4 + thumbnail.jpg
```

Kiểm trước khi giao (bắt buộc):
```bash
F=<ten>_9x16.mp4
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,duration -of csv=p=0 $F   # 1080,1920,~T
ffprobe -v error -select_streams a:0 -show_entries stream=duration -of csv=p=0 $F              # ≈ T
ffmpeg -y -ss 0.1 -i $F -frames:v 1 f0.jpg; ffmpeg -y -ss <T-0.3> -i $F -frames:v 1 f_cuoi.jpg   # xem 2 khung
```

## 4. Viết kịch bản (kichban.json) — quy tắc đã chốt

- 7 nhịp cho video ~14–16s; muốn nhanh hơn thì **thêm nhịp, câu ngắn hơn**, đừng đẩy `toc_do_cuoi` quá 1.15.
- Mỗi nhịp: `doc` (lời đọc, viết số bằng chữ) + `phu_de` 1–2 dòng, **đúng một** `*từ khoá*` nổi.
- Ảnh: mô tả TƯ THẾ + ĐẠO CỤ bằng tiếng Anh, script tự ghép nền phong cách + "no text".
- `thumbnail.anh` = ảnh cuối (a07) để hook và cảnh kết trùng nhau.
- Hai ví dụ chạy thật: `mau/vi-du-phan-ky-luat.json`, `mau/vi-du-phan-that-bai.json`.

## 5. Tải VIDEO từ Flow (khi cần clip Veo, không phải ảnh)

Flow v2 (từ 11/09/2026) trả video qua CDN **khoá bằng cookie**, trang **không** cho JS đọc bytes chéo domain.
Hai cách còn dùng được:
1. **flow-agent V2** (`/Volumes/DATA/AI-APP/flow-agent`, bản vá riêng 11/09): extension của nó fetch trong
   service worker (có cookie) rồi đẩy base64 về :8001. Chạy `.venv/bin/flow serve`, gọi `/v1/videos/generations`.
   Chỉ dùng cho VIDEO; đường ảnh của nó đã chết.
2. **Tay**: bấm ⬇ trên thẻ video → Chrome lưu vào ~/Downloads (nếu Chrome không hỏi nơi lưu).
Skill `wevideo-veo` / `talking-head-video` mô tả chi tiết cách 1.

## 6. Lỗi đã gặp & cách xử

| Triệu chứng | Nguyên nhân | Xử |
|---|---|---|
| `1_tao_anh.py` → `CAPTCHA_FAILED: NO_FLOW_TAB`, `has_flow_key:false` | Flow dời sang flow.google.com, token ya29 không còn | Dùng `1_tao_anh_ui.py` (mục 3). Đừng sửa flow-agent cho ảnh nữa |
| `curl` ảnh Flow ra file HTML | Ảnh cần cookie đăng nhập | Kéo qua AppleScript (`tai`) |
| `tai` báo "0 ảnh mới phù hợp" | Ảnh chưa render xong, hoặc tab Flow không phải project | Chờ hết ô %, reload tab, chạy lại |
| `tai` kéo về BỘ CŨ | Mở 2 tab Flow, tab cũ chưa reload | Đóng tab thừa, reload, chạy lại |
| "Executing JavaScript through AppleScript is turned off" | Chưa bật Allow JavaScript from Apple Events | Bật trong Chrome ▸ View ▸ Developer |
| Gửi prompt mà không thấy ô % mới | Bấm Enter khi Flow chưa sẵn | Bấm nút → thay vì Enter, cách 4s giữa hai lần |
| Phụ đề mất hút | Sai cặp màu theo phong cách | Không tự đặt màu; script chọn theo `phong_cach` |
| Cảnh báo "nhịp DÀI hơn 2.2s" | Câu dài | Cắt câu, thêm nhịp |
| Video 1280×720 khi tự viết ffmpeg | zsh ăn `$frames:s=` | Dùng `${frames}` |

## 7. Vì sao không dùng các đường khác (đã thử, đã fail — đừng thử lại)

- **flow-agent API ảnh**: Bearer ya29 chỉ có trên labs.google cũ; flow.google.com dùng cookie + batchexecute.
- **fetch từ trang → localhost**: Chrome chặn Private Network Access, treo 45s.
- **navigator.clipboard.writeText**: đòi document focus; AppleScript chạy lúc Chrome không ở trước.
- **Kênh JS của extension Claude**: lọc chuỗi base64 và URL có query → không mang ảnh ra được.
- **AppleScript `execute javascript`**: đi thẳng vào tab, mang base64 ra stdout → cách duy nhất ổn. Đã chốt.

## 8. Cấu trúc gói

```
video-nguoi-que/
├── SKILL.md                 ← Claude đọc để kích hoạt
├── CAI-DAT-MAY-MOI.md       ← file này
├── cai-dat.sh               ← cài môi trường + tự kiểm
├── fonts/Arial Bold.ttf     ← font phụ đề (mang theo, khỏi phụ thuộc máy)
├── mau/                     ← kịch bản mẫu (2 ví dụ chạy thật + mẫu nền trắng)
├── references/              ← nhân vật mẫu, ví dụ 19 nhịp
└── scripts/
    ├── 1_tao_anh_ui.py      ← B1 HIỆN HÀNH (prompts | tai)
    ├── 1_tao_anh.py         ← B1 cũ qua flow-agent (giữ để tham khảo, đã chết 11/09/2026)
    ├── 2_tao_giong.py       ← B2
    ├── 3_dung_video.py      ← B3 (+ make_subs_v2.py, tim_font.py, detect_silence.py)
    └── _v1/                 ← bản đầu, không dùng
```
