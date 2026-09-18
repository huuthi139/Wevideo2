# Cơ chế tạo Video/Ảnh qua Extension (Flow Agent) — Hướng dẫn nhân bản

> Tài liệu để **nhân bản cơ chế tạo video/ảnh miễn phí** (dùng Google Flow + credit Ultra) vào
> app khác (WeVideo, PIC APP, hay bất kỳ app nào cần gen media). Viết theo bản đã chạy thật +
> verify trên Mac mini 2026-09-17. Ngôn ngữ code: xem `flow-agent/` (backend) + `flow-chrome-extension/`.

---

## 1. Ý tưởng cốt lõi

Google Flow v2 (`flow.google.com`) **không có API công khai** — dùng cookie auth + Ultra credits.
Thay vì gọi API, ta **lái giao diện web của Flow bằng một Chrome extension** (đóng vai người dùng bấm
chuột), còn app gọi vào **một backend HTTP chuẩn OpenAI** (`/v1/images/generations`,
`/v1/videos/generations`). Backend ↔ extension nói chuyện qua **WebSocket**.

**Lợi ích:** tạo ảnh/video **miễn phí** (tiêu credit Ultra, không tốn tiền API), model xịn
(Nano Banana 2 cho ảnh, Omni 1.1 Flash cho video).

**Ràng buộc:** cần 1 máy chạy Chrome đã đăng nhập Flow (Ultra) + 1 tab Flow mở. Mỗi tài khoản/tab
chạy **tuần tự** (không song song trên cùng tab).

---

## 2. Kiến trúc — 4 mảnh

```
┌─────────────┐   HTTP (OpenAI)   ┌──────────────────┐   WebSocket    ┌─────────────────────────┐
│  App gọi    │ ────────────────► │  Backend         │ ◄────ws:8001──►│  Chrome Extension       │
│ (WeVideo,   │  POST /v1/videos  │  `flow serve`    │  /ws           │  (Flow Agent)           │
│  PIC APP…)  │ ◄──── JSON ────── │  port 8001       │                │  background.js (SW)     │
└─────────────┘   {url, media_id} │  (FastAPI)       │                │   ├ content.js          │
                                  └──────────────────┘                │   └ injected.js (MAIN)  │
                                                                      └────────────┬────────────┘
                                                                    Chrome DevTools │ + DOM events
                                                                          Protocol  ▼
                                                                   ┌─────────────────────────────┐
                                                                   │  Tab Google Flow            │
                                                                   │  flow.google.com/project/…  │
                                                                   │  (cookie auth + Ultra)      │
                                                                   └─────────────────────────────┘
```

1. **Backend** (`flow-agent/`, chạy `flow serve`, port 8001): FastAPI, phơi API chuẩn OpenAI. Không
   giữ key (auth tắt nếu `SERVER_API_KEY` rỗng). Chuyển yêu cầu xuống extension qua WebSocket, chờ
   URL media rồi tải bytes trả về.
2. **background.js** (service worker của extension): giữ WebSocket tới backend, tìm/chọn tab Flow,
   attach Chrome DevTools Protocol (CDP) để gõ phím, điều phối 2 pha prep/submit.
3. **content.js**: chạy trong trang Flow (isolated world), tiêm `injected.js` vào **MAIN world**.
4. **injected.js** (MAIN world): **bộ lái UI thật sự** — đọc/điều khiển DOM Angular của Flow (đổi
   chế độ, tỉ lệ, thời lượng, right-click asset, gõ prompt, bấm gửi), bắt URL media từ network.

Config transport: `FLOW_TRANSPORT=ui` (bắt buộc cho Flow v2). Health: `GET /health` phải trả
`{"transport":"ui","status":"healthy","extension_connected":true}`.

---

## 3. Các luồng tạo VIDEO

### 3a. Text → Video (T2V)
App gọi `POST /v1/videos/generations` với `prompt` + `aspect` + `duration`. Backend
(`generate_video_ui` trong `omniflash/generators/ui.py`):
1. Đưa tab về **gallery** (`__GALLERY__`) — vì sau mỗi lần gen Flow nhảy sang `/edit/<id>`.
2. Chờ tập video cũ **ổn định** rồi chốt `vid_before` (tránh vơ nhầm clip cũ lazy-load).
3. Gửi payload xuống extension → injected.js: chọn chế độ **Video** + tỉ lệ + thời lượng → gõ
   prompt → bấm gửi.
4. Chờ **URL `/video/` MỚI** xuất hiện trong `bridge.media_urls` (media_id chưa từng có) → tải bytes
   → trả `{url, media_id}`.

### 3b. Ảnh → Video ("Tạo ảnh động" / I2V) — GIỮ NHÂN VẬT
Đây là cơ chế **cố định nhân vật cho video**: lấy 1 ảnh có sẵn trong Flow làm khung đầu.

App gọi `POST /v1/videos/generations` với `start_media_id` = **media_id của ảnh nguồn** (+ `aspect`,
`duration`, `prompt` mô tả chuyển động). Luồng (injected.js, nhánh `d.animateFrom`):
1. `animateImageByRef(id)`: tìm tile ảnh theo `data-media-id` → **right-click** → menu **"Tạo ảnh
   động"**. Flow tự chuyển sang chế độ Video + đặt ảnh làm **khung đầu**.
2. Mở popover cài đặt → **set tỉ lệ (16:9/9:16) + thời lượng (4/6/8/10 giây)** theo yêu cầu.
   > Quan trọng: composer **NHỚ** giá trị lần trước (sticky) → phải set tường minh, nếu không xin 4s
   > có thể ra 10s. Đã verify: mở popover + click radio KHÔNG làm mất khung đầu.
3. Gõ prompt chuyển động → bấm gửi → chờ URL `/video/` mới.

Video I2V chỉ có **2 tỉ lệ**: 16:9 (landscape) / 9:16 (portrait) — crop từ ảnh nguồn.

### 3c. (Bonus) Cố định nhân vật cho ẢNH
Cùng cơ chế right-click, nhưng menu **"Thêm vào câu lệnh"**: `POST /v1/images/generations` với
`ref_media_ids: ["<media_id ảnh nhân vật>"]`. injected.js `addRefByMediaId(id)` gắn ảnh làm tham
chiếu → tạo ảnh mới giữ nhân vật (bối cảnh khác).

---

## 4. Hợp đồng API (chuẩn OpenAI, cổng 8001)

### Tạo ảnh — `POST /v1/images/generations`
```jsonc
{
  "prompt": "NV01: mèo vàng đội nơ đỏ ngồi quán cà phê, 3D pixar",
  "size": "1024x1024",              // 1:1 | 1024x1792 (9:16) | 1792x1024 (16:9)… map sang tỉ lệ
  "n": 1,
  "ref_media_ids": ["<media_id>"]   // (tuỳ) CỐ ĐỊNH NHÂN VẬT: id ảnh gốc, driver right-click "Thêm vào câu lệnh"
}
// → { "data": [ { "url": "http://…/download/…png", "media_id": "<uuid>" } ] }
```

### Tạo video — `POST /v1/videos/generations`
```jsonc
{
  "prompt": "mèo chớp mắt, sóng biển nhẹ, cinematic",
  "aspect": "portrait",             // "portrait"=9:16 | "landscape"=16:9
  "duration": 4,                    // 4 | 6 | 8 | 10 (giây)
  "n": 1,
  "start_media_id": "<media_id>"    // (tuỳ) ẢNH→VIDEO: id ảnh nguồn → "Tạo ảnh động". Bỏ trống = T2V.
}
// → { "data": [ { "url": "http://…/download/…mp4", "media_id": "<uuid>" } ] }
```

Các endpoint khác: `GET /health` (trạng thái), `GET /v1/models`, `GET /v2/media_urls` (debug URL đã
bắt). Auth: gửi `Authorization: Bearer <key>` nếu `SERVER_API_KEY` được đặt trong `config.env`; rỗng
= không cần key.

> **`media_id` là chìa khoá của registry.** Mỗi lần gen ảnh, response trả `media_id` = **`data-media-id`**
> trên tile Flow. App **tự lưu** map `code → media_id` (vd `NV01 → 1744959a-…`) rồi truyền lại làm
> `ref_media_ids`/`start_media_id`. Đây là cách "đặt tên nhân vật" ổn định (KHÔNG dựa tên caption tile
> tự sinh vì nó không chứa mã).

---

## 5. Nội bộ automation — cách injected.js lái UI Flow

Flow là Angular Material. Các "nguyên thủy" then chốt (đều trong `flow-chrome-extension/injected.js`):

| Việc | Cách làm |
|---|---|
| **Tìm asset theo id** | Tile ảnh mang `data-media-id="<uuid>"`. `document.querySelector('[data-media-id="…"]').closest('flow-image-tile,flow-video-tile')`. |
| **Bật menu chuột phải** | Extension chạy trong page → không right-click OS được. Dùng **contextmenu tổng hợp**: `dispatchEvent(new MouseEvent('contextmenu', {bubbles,cancelable,composed:true,button:2,clientX,clientY}))` (kèm pointerdown/mousedown/mouseup). |
| **Chọn item menu** | Item = `mat-mdc-menu-item[role=menuitem]`. Text có prefix icon ligature (vd `motion_blur…`) → strip `<mat-icon>` rồi khớp đuôi: `/tạo ảnh động$/`, `/thêm vào câu lệnh$/`. |
| **Đổi chế độ / tỉ lệ / thời lượng** | Popover cài đặt = `mat-button-toggle-group[role=radiogroup]` chứa `button[role=radio][aria-checked]`. Mở popover (bấm chip cài đặt) → tìm radio khớp nhãn (`16:9`, `9:16`, `4 giây`…) → click nếu chưa checked. |
| **Đính ảnh i2i (upload)** | `attachImagesToComposer(b64)` — nhét File vào `input[type=file]` ẩn (fallback synthetic paste). |
| **Bắt URL media** | Hook `fetch`/XHR trong MAIN world → mọi URL `/image/` `/video/` ký sẵn đẩy vào `bridge.media_urls` (SW tải bytes vì CDN cookie-gated, urllib 403). |

Hàm chính: `tileByMediaId`, `addRefByMediaId` (nhân vật ảnh), `animateImageByRef` (ảnh→video),
`applySettings2` (mode/tỉ lệ/thời lượng cho gen thường), `openPopover`/`closePopover`, `editorEl`.
Marker phiên bản: `window.__flowAgentDriver.ver` (vd `charref-3`) — dùng để xác minh đúng bản đã nạp.

---

## 6. Điều phối 2 pha (prep → submit)

`background.js handleUiGenerate` chia mỗi request thành 2 pha để gõ prompt ổn định (không bị popover
re-render nuốt chữ):

1. **prep** (injected.js, `d.phase='prep'`): tắt chế độ "Tác nhân" → set chế độ/tỉ lệ/thời lượng
   (hoặc right-click "Tạo ảnh động" / "Thêm vào câu lệnh") → focus ô soạn → xoá → trả `ready`.
2. **background gõ prompt** qua **CDP** (`dbgAttach` → `dbgType`) vào ô đang focus.
3. **submit** (`d.phase='submit'`): kiểm ô soạn có chữ + nút gửi bật → bấm gửi → chờ URL media mới.

`background.js findFlowV2ProjectTab` lo tìm/tái dùng tab Flow đúng (tự lái tab `/edit/` về
`/project/<id>` gallery khi cần). `params` từ WebSocket được **truyền thẳng** xuống prep+submit → thêm
field mới (vd `refId`, `animateFrom`) chỉ cần sửa backend payload + injected.js, KHÔNG cần sửa
background.js.

---

## 7. Nhân bản sang máy/app mới

### A. Dựng engine (1 lần / máy chạy)
1. Copy `flow-agent/` (backend) + `flow-chrome-extension/` (extension) sang máy đích.
2. Cài Python deps vào `.venv`, đặt `config.env`: `FLOW_TRANSPORT=ui`, `APP_PORT`/project mặc định,
   `SERVER_API_KEY` (rỗng = không auth).
3. Chạy backend: `./.venv/bin/flow serve` (port 8001). Kiểm `GET /health`.
4. **Nạp extension vào Chrome**: `chrome://extensions` → Developer mode → **Load unpacked** → trỏ tới
   thư mục `flow-chrome-extension`. Ghi nhớ **ĐÚNG thư mục đã load** (xem Gotcha #1).
5. Mở 1 tab `flow.google.com`, **đăng nhập tài khoản có Ultra**, vào 1 project
   (`flow.google.com/project/<id>`). `/health` phải thấy `extension_connected:true`.

### B. App khác gọi vào (như WeVideo)
- Cách đơn giản nhất: gọi HTTP tới `http://<host>:8001/v1/videos/generations` (và `/v1/images/…`).
  Đây là API chuẩn OpenAI → dùng SDK openai-compatible cũng được.
- Muốn nhúng sâu: đóng gói `engine/` (backend + extension) kèm app, chạy `flow serve` như service nền.
  Xem cách WeVideo làm: repo `huuthi139/Wevideo2`, thư mục `engine/` (auto-update merge-copy engine từ
  GitHub — xem Gotcha #4).
- **Registry** (code→media_id) do app tự quản: lưu `media_id` từ response khi gen ảnh, truyền lại làm
  `ref_media_ids`/`start_media_id`.

---

## 8. Gotchas (bài học đắt — đọc kỹ)

1. **Thư mục extension Chrome THỰC SỰ load ≠ nơi bạn nghĩ.** Chrome nhớ **đường tuyệt đối** đã Load
   unpacked. Nếu có nhiều bản (vd `~/Desktop/flow-ext-…` vs `~/App/engine/flow-chrome-extension`),
   sửa file phải sửa **đúng thư mục đang load**. Tìm nó ở
   `~/Library/Application Support/Google/Chrome/*/Secure Preferences` → `extensions.settings[*].path`
   (path tuyệt đối = unpacked).
2. **Đổi `injected.js` phải RELOAD extension.** Chrome cache bản cũ; navigation/reload trang KHÔNG đủ.
   Cách reload: `chrome://extensions` bấm ⟳, HOẶC restart Chrome (`killall "Google Chrome"; open -a
   "Google Chrome"` — nạp lại extension từ disk). Sau reload phải mở **TAB Flow MỚI** (content script
   cũ mồ côi → "Extension context invalidated"). Xác minh: `window.__flowAgentDriver.ver`.
3. **Composer sticky.** Flow nhớ chế độ/tỉ lệ/thời lượng lần trước. Luôn **set tường minh** trước mỗi
   gen (nhất là animate — mặc định crop 16:9 + duration lần trước).
4. **Auto-update có thể ĐÈ engine.** Nếu app (như WeVideo) có auto-update kéo code từ GitHub và
   `copytree(src/engine → engine)`, thì patch tay ở `engine/` sẽ bị đè. → commit vào repo deploy
   (đúng nhánh, thư mục `engine/`) cho vĩnh viễn. (Bản `flow-chrome-extension` Chrome load ở NGOÀI
   `engine/` thì không bị đè, nhưng nên đồng bộ cả 2 cho nhất quán.)
5. **1 tab / 1 tài khoản / tuần tự.** UI transport dùng chung tab → chạy song song sẽ bắt nhầm media
   của nhau. Mỗi lần gen xong Flow nhảy `/edit/` → luôn `__GALLERY__` về gallery trước khi gen tiếp.
6. **CDN cookie-gated.** URL `/image//video/` cần cookie Chrome để tải → **service worker tải bytes**
   (không phải Python), rồi trả base64/bytes cho backend.
7. **Credit.** Tạo ảnh Nano Banana thường 0 credit; video Omni tốn credit Ultra (vd ~7–12/clip). Hết
   credit → không render, báo lỗi "không có clip mới".

---

## 9. Bản đồ file

| File | Vai trò |
|---|---|
| `flow-agent/cli/api.py` | FastAPI endpoints `/v1/images` `/v1/videos` `/v1/upload` `/health`, map field → generator. |
| `flow-agent/omniflash/generators/ui.py` | `generate_image_ui` (t2i/i2i/char-ref), `generate_video_ui` (t2v/animate), map tỉ lệ, bắt URL mới. |
| `flow-agent/omniflash/bridge.py` | `ExtensionBridge`: WebSocket, `media_urls`, `ui_generate()`. |
| `flow-chrome-extension/background.js` | SW: WebSocket, `handleUiGenerate` (2 pha), `findFlowV2ProjectTab`, CDP type, tải video bytes. |
| `flow-chrome-extension/content.js` | Tiêm `injected.js` vào MAIN world. |
| `flow-chrome-extension/injected.js` | **Bộ lái UI**: tileByMediaId, right-click menu, popover radios, editor, hook fetch/XHR. |
| `SPEC-flow-v2-ui-transport.md` | Spec gốc transport v2. |

Skill nhân bản kèm sẵn assets: `~/.claude/skills/tao-anh-flow/` (có extension + backend source + guide).
