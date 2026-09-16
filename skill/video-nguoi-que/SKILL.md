---
name: video-nguoi-que
description: >-
  Tạo video DỌC 9:16 phong cách "người que" hoàn chỉnh — hình nhân vật đồng nhất,
  giọng đọc tiếng Việt, phụ đề kinetic (từ khoá IN HOA nổi to), chữ ký góc, thumbnail
  hook ở đầu. HAI phong cách: nền trắng nét mực (kinh doanh/giải thích) và phấn trắng
  trên bảng xanh (truyền cảm hứng/triết lý). Dùng skill này BẤT CỨ KHI NÀO người dùng
  muốn "tạo video người que", "video stick figure", "làm clip người que về chủ đề X",
  "video bảng phấn", "video mascot doanh nhân", "dựng video ngắn có phụ đề nổi chữ",
  hoặc đưa một kịch bản/nội dung và bảo dựng thành video dọc. Kích hoạt cả khi chỉ nói
  "làm video như lần trước", "video người que 30 giây", "tạo thumbnail cho video này".
  KHÔNG dùng cho: cắt short từ video có sẵn (video-hook-shorts), gen clip Veo động
  nhiều cảnh (wevideo-veo), video quay người thật (talking-head).
---

# VIDEO NGƯỜI QUE

Từ **một kịch bản chữ** ra **một video 9:16 hoàn chỉnh** — 3 bước, không cần dựng tay.
Ảnh miễn phí, giọng miễn phí. Thực chiến 18/08/2026; cập nhật đường ảnh mới 13–15/09/2026.
**Cài máy mới / quy trình đầy đủ / lỗi đã gặp → đọc `CAI-DAT-MAY-MOI.md`.**

## Chạy nhanh

```bash
mkdir duan && cd duan
S=~/.claude/skills/video-nguoi-que/scripts
cp ~/.claude/skills/video-nguoi-que/mau/vi-du-phan-that-bai.json kichban.json   # rồi sửa nội dung
python3 $S/1_tao_anh_ui.py prompts kichban.json   # B1a: in prompt
#   B1b: Claude lái Chrome (Claude in Chrome) → tab Flow project → chip cài đặt → Hình ảnh · 9:16 ·
#        Nano Banana 2 · x1 → dán từng prompt a01→a07, bấm →, cách ~4s → chờ hết ô %
python3 $S/1_tao_anh_ui.py tai kichban.json       # B1c: kéo 7 ảnh mới nhất về anh/ (AppleScript) → soi anh/_sheet.jpg
python3 $S/2_tao_giong.py  kichban.json           # B2 giọng (MIỄN PHÍ)
python3 $S/3_dung_video.py kichban.json           # B3 dựng
```
Ra `<ten>_9x16.mp4` + `thumbnail.jpg`. Kiểm: `ffprobe` 1080×1920, video ≈ audio, trích 2 khung đầu/cuối.

⚠ `1_tao_anh.py` (qua flow-agent :8001) **đã chết từ 11/09/2026** — Flow dời sang flow.google.com,
không còn token. Đừng khởi động flow-agent để làm ảnh; dùng `1_tao_anh_ui.py`.

### Biến thể B3 — CLIP ĐỘNG (video Flow thay ảnh Ken Burns)

Khi muốn cảnh **động thật** (clip Veo/Omni) thay ảnh tĩnh: thay B1 (ảnh) bằng gen+tải CLIP,
rồi chạy `3_dung_video_clip.py` thay `3_dung_video.py`. Hậu kỳ y hệt (giọng + phụ đề kinetic +
chữ ký + 1.12× + thumbnail); chỉ khác mỗi nhịp là 1 clip `clips/<key>.mp4`.

**CHẠY TRỌN 1 LỆNH (không LLM/agent)** — cần flow-agent :8001 chạy + tab Flow đã login:
```bash
cd <thư-mục-dự-án>   # có kichban.json (anh_can_gen mô tả cảnh + nhip có doc/phu_de)
python3 ~/.claude/skills/video-nguoi-que/scripts/lam_video_clip.py kichban.json
```
Tự: gen 6 cảnh qua `/v1/videos` (engine tự lấy URL + tải, retry+giãn nhịp) → giọng → ráp.
Đứt giữa chừng chạy lại: bỏ qua clip đã tải. Dưới đây là các bước tay tương đương:

```bash
# B1 (clip): Claude lái Chrome → tab Flow project → chip cài đặt → tab "Video" · 9:16 ·
#   Omni 1.1 Flash · 4 giây · x1 (7 tín dụng/clip) → dán từng prompt scene a01→aNN, bấm →, cách ~4s.
#   Prompt clip = mô tả cảnh + "hand-drawn chalk animation, gentle subtle chalk motion, no text".
# B1-tải: dùng flow-agent (URL /video/ cookie-gated, curl 403 → phải SW fetch có cookie):
curl -sX POST :8001/v2/play_tile                    # click tile mới nhất → prefetch URL /video/ cả loạt
curl -s :8001/v2/media_urls                          # lấy video_ids (URL đủ len~158 nhờ __normEsc)
curl -sX POST :8001/v2/fetch_video/<id>             # tải bytes → output/flow_vid_*.mp4 → đổi tên clips/aNN.mp4
#   Map clip↔cảnh: trích 1 khung mỗi clip, soi nội dung (không tin thứ tự id).
python3 $S/2_tao_giong.py       kichban.json         # B2 giọng
python3 $S/3_dung_video_clip.py kichban.json         # B3 clip động → <ten>_9x16.mp4
```
Điều kiện tải clip: **flow-agent :8001 đang chạy** + extension flow-agent nạp bản có `__normEsc`
(injected.js unescape `=`/`&` — thiếu thì URL /video/ cụt ở "?Expires" → tải 403).
Nút "Tải" của Flow qua Claude-in-Chrome bị chặn (download interrupted) → KHÔNG dùng được, phải qua flow-agent.
`3_dung_video_clip.py` cần `clips/<key>.mp4` (không cần `anh/` — thumbnail tự trích 1 khung từ clip).

## Điều kiện

| Cần | Kiểm bằng | Nếu thiếu |
|---|---|---|
| Chrome + extension **Claude in Chrome** + login Google có gói AI | Claude mở được flow.google.com/project/… | cài extension, đăng nhập |
| Chrome ▸ View ▸ Developer ▸ **Allow JavaScript from Apple Events** | `bash cai-dat.sh` → "AppleScript→JS: OK" | bật trong menu Chrome |
| edge-tts + Pillow + ffmpeg | `bash ~/.claude/skills/video-nguoi-que/cai-dat.sh` | script tự cài |

⚠ ffmpeg trên máy này **không có libass/drawtext** → phụ đề bắt buộc đi đường PNG + overlay
(`make_subs_v2.py` lo sẵn). Đừng cố dùng `-vf drawtext`.

## HAI phong cách — chọn trước khi làm

| | `"phong_cach": "trang"` | `"phong_cach": "phan"` |
|---|---|---|
| Hình | Nét mực đen trên nền trắng, điểm màu đỏ/xanh/vàng | Phấn trắng trên bảng xanh đen |
| Phụ đề | mực đậm `[20,20,20]` + **viền trắng** | vàng chanh `[235,255,130]` + viền `[20,28,12]` |
| Hợp với | Kinh doanh, giải thích, bán hàng, mascot thương hiệu | Truyền cảm hứng, thiền, triết lý |

🔴 **Bẫy chết người:** phụ đề vàng chanh trên nền TRẮNG là mất hút hoàn toàn.
Script tự chọn cặp màu theo `phong_cach` — đừng tự đặt tay.

## Giữ nhân vật đồng nhất (phong cách "trang")

```
anh_goc_giu_nhan_vat = 567788a4-3391-4b4f-b0e4-a18a3974cffd
kho ảnh mẫu: /Volumes/DATA/AI-APP/mascot-nguoi-que/  (10+ tư thế sẵn)
```
Mọi ảnh mới PHẢI truyền media_id này vào `ref_media_ids`. Bỏ ra là ra **người khác** —
cùng phong cách nhưng khác tỉ lệ đầu/thân, khác nét mặt. Script tự làm việc này.

## BA CON SỐ quyết định video hay hay dở

| | Giá trị | Vì sao |
|---|---|---|
| **Nhịp cắt** | **1.5–1.8 giây/nhịp** | Cảm giác "nhanh" đến từ ĐÂY, không phải từ tempo |
| **Kiểu cắt** | **hard cut, KHÔNG xfade** | xfade làm nhão nhịp |
| **Tăng tốc cuối** | **1.15×** | **Trần thực chiến.** Trên nữa giọng Việt bắt đầu líu |

**Muốn nhanh hơn → TĂNG SỐ NHỊP, đừng đẩy tempo.** 30 giây chia 19–20 nhịp thay vì 12.
Script cảnh báo khi nhịp trung bình > 2.2s.

## Viết phụ đề kinetic

Mỗi nhịp 1–2 dòng NGẮN. Đánh dấu `*từ khoá*` → tự **IN HOA + to 1.55×**:

```json
{"phu_de": ["Tôi có *100 F1*", "trong *30 ngày*"]}
```
→ `Tôi có` thường · **`100 F1`** to gấp rưỡi · `trong` thường · **`30 NGÀY`** to gấp rưỡi.

Mỗi nhịp nên có **đúng một** từ khoá nổi. Nổi hết = không có gì nổi.

## Kịch bản: lời ĐỌC khác chữ HIỆN

| | Ví dụ |
|---|---|
| `doc` (đọc lên) | `"Tôi có một trăm F một trong ba mươi ngày."` |
| `phu_de` (hiện ra) | `["Tôi có *100 F1*", "trong *30 ngày*"]` |

Đọc số bằng chữ ("một trăm", "F một") để TTS không đọc sai; phụ đề vẫn viết "100 F1".

## Thumbnail

Khối `thumbnail` trong kịch bản → sinh `thumbnail.jpg` và **dán vào đầu video**
(mặc định 0.3s). Facebook/TikTok lấy khung đầu làm ảnh bìa nên đây vừa là hook vừa là cover.

```json
"thumbnail": {"anh":"a01","giay":0.3,"dong_tren":"HỆ THỐNG TUYỂN",
              "dong_chinh":"HÀNG TRĂM F1","nhan_do":"TỰ ĐỘNG"}
```
Ba tầng tương phản: dòng trên đen vừa → dòng chính **đỏ cỡ lớn** → nhãn **nền đỏ chữ trắng**.
Mẹo: chọn `anh` trùng cảnh đầu tiên → khi chữ biến mất nhân vật đứng nguyên chỗ, mắt không giật.

## Lưu ý thực chiến (đã trả giá)

- **Ảnh KHÔNG tốn credit** (Nano Banana 2 báo "0 tín dụng"), video Veo mới tốn. Thử ảnh thoải mái.
- Lưới Flow xếp **mới nhất trước** → `tai` gán ảnh đầu lưới = key gửi sau cùng. Luôn soi `anh/_sheet.jpg`.
- Chỉ mở MỘT tab Flow project; mở hai tab là kéo nhầm bộ cũ (đã dính).
- Gửi prompt bằng nút → (không Enter), cách nhau ~4s; Enter lúc Flow bận thì lệnh rơi mất (đã dính).
- Luôn chốt `no text, no words, no letters, no numbers` trong prompt ảnh. Chữ AI vẽ ra méo;
  để trống rồi tự chèn chữ Việt lên sau vừa sắc vừa sửa được.
- Flow hay tự thêm **mặt cười** và **bóng đổ**. Không muốn thì thêm `no face, no shadow`.
- Nhân vật thường hơi nhỏ trong khung 9:16 → `full body centered, fills 70% of frame`.
- `rm -f k*.jpg` sẽ xoá luôn `kiem.jpg` — đặt tên file tạm bằng tiền tố `_`.

## Cấu trúc dự án

```
duan/
├── kichban.json      ← nguồn sự thật duy nhất (nội dung + tham số + độ dài giọng)
├── anh/<key>.jpg     ← B1 (bản ẢNH — 3_dung_video.py)
├── clips/<key>.mp4   ← B1 (bản CLIP ĐỘNG — 3_dung_video_clip.py; thay anh/)
├── audio/b<i>.wav    ← B2 (đã cắt chặt)
├── subs/sub<i>.png   ← B3
├── thumbnail.jpg
└── <ten>_9x16.mp4    ← thành phẩm
```
Sửa một câu → sửa `kichban.json`, chạy lại B2 (chỉ nhịp đó) + B3. Không phải làm lại cả video.

## Liên quan
`CAI-DAT-MAY-MOI.md` (cài máy mới, quy trình, tải video, lỗi) ·
`wevideo-veo` (clip Veo động nhiều cảnh, `make_subs_v2.py` gốc) · `flow-studio` (lái Flow bằng giao diện) ·
bản mẫu cũ `/Volumes/DATA/wepower-videos/triet-ly-kd/build_trietly.sh`
