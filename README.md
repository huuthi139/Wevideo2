# WeVideo App — Dán kịch bản → Video người que (một phát)

Web app chạy **local**: dán kịch bản tiếng Việt → tự làm **giọng đọc + phụ đề kinetic + gen clip Veo qua Google Flow + ráp** ra 1 video 9:16 hoàn chỉnh. Copy sang máy khác → cài 1 lần → nối extension → chạy.

## Kiến trúc (2 phần rời)

```
┌─ WeVideo App (thư mục này) ─┐        ┌─ flow-agent (engine gen Veo) ─┐
│ server.py  :8080  (FastAPI) │──HTTP──▶ :8001  /v1/videos/generations │
│ UI dán kịch bản + tiến độ   │        │ + Chrome extension MV3         │
└─────────────────────────────┘        │ + tab flow.google.com đã login│
                                        └───────────────────────────────┘
```
App **KHÔNG tự gen** clip — nó gọi **flow-agent** (engine **đóng gói kèm** ở `engine/`, lái Google Flow qua extension). App lo: phân tích kịch bản → giọng → điều phối gen → phụ đề → ráp.

## Cài (máy mới, 1 lần)

**Cách A — 1 file (khuyến nghị):** copy `dist/WeVideo-Installer.command` sang Mac khác → **double-click** (hoặc `bash WeVideo-Installer.command`). Nó tự giải nén vào `~/WeVideo-App` + cài ffmpeg (brew) + dựng venv engine + venv app. Cài chỗ khác: `WEVIDEO_DEST=/duong/dan bash WeVideo-Installer.command`.
Tạo lại file cài (sau khi sửa code): `bash build_installer.sh` → `dist/WeVideo-Installer.command`.

**Cách B — từ thư mục nguồn:**
```bash
bash setup.sh      # tạo .venv + cài fastapi/uvicorn/pillow/edge-tts/mcp, kiểm ffmpeg + flow-agent
```
Cần sẵn trên máy: **python3**, **ffmpeg** (`brew install ffmpeg`). Giọng đọc dùng **edge-tts** (miễn phí, cài tự động, giọng NamMinh) — **cần internet**. Thiếu/lỗi edge-tts app **báo lỗi rõ** (không tự lùi giọng máy robot).

## Engine gen Veo (flow-agent) — đóng gói kèm, `run.sh` tự bật

`bash run.sh` tự khởi động engine (`engine/flow-agent`, port :8001) rồi web app. Chỉ còn **2 việc thủ công, làm 1 lần** (Chrome không cho tự động):
1. Chrome → `chrome://extensions` → bật *Developer mode* → **Load unpacked** → chọn `engine/flow-chrome-extension`.
2. Mở tab **flow.google.com** và **đăng nhập** tài khoản có gói Flow (còn credit).

Kiểm: `curl -s http://127.0.0.1:8001/health` có `"extension_connected":true`. Trên UI, chấm xanh = sẵn sàng.

## Chạy

```bash
bash run.sh        # → http://127.0.0.1:8080
```
Mở trình duyệt, **dán kịch bản**, chọn phong cách/giọng/chuyển cảnh, bấm **Tạo video**. Theo dõi tiến độ; xong thì xem trước + tải về ngay trên trang.

## Kịch bản viết sao

- **Đơn giản nhất**: mỗi dòng = 1 câu ĐỌC (tiếng Việt thuần). App tự sinh hình + phụ đề.
- **Kiểm soát hình sát nội dung**: viết theo khối, mỗi cảnh cách nhau 1 dòng trống:
  ```
  doc: Hàng hoá phái sinh nghe phức tạp nhưng bản chất rất đơn giản.
  hinh: a stick figure looking at a big chart with gold bars and oil barrel icons
  phude: Phái sinh · *rất đơn giản*
  ```
  `doc` = lời đọc · `hinh` = mô tả hình tiếng Anh cho Veo · `phude` = phụ đề (`*từ khoá*` → IN HOA to).
- **B-roll cutaway** (tuỳ chọn): thêm dòng `broll: <mô tả hình tiếng Anh>` vào khối cảnh → app gen thêm 1 clip Veo, chèn đè ~1-1.5s giữa cảnh đó (giọng chạy tiếp, không lệch). B-roll lỗi thì tự bỏ qua.
- **Bật LLM** (tuỳ chọn) trong `config.env` để tự sinh `hinh`/`phude` tiếng Anh từ câu tiếng Việt — hình sát nội dung hơn mà không phải viết tay. Thiếu LLM → app vẫn ra video, hình chung chung hơn.

## Cấu hình — `config.env`

Sửa ở đây, không sửa code: cổng app, URL flow-agent, giọng, phong cách mặc định, LLM. Copy máy khác chỉ chỉnh file này.

## Chi phí & lưu ý

- Gen clip Veo tốn credit gói Flow (~7–12 credit/clip tuỳ độ dài). Giọng/phụ đề/ráp **miễn phí**.
- ffmpeg máy này không có drawtext → phụ đề đi đường PNG overlay (`make_subs_v2.py`) — đã lo sẵn.
- Video ra ở `projects/<job_id>/<job_id>_9x16.mp4`.

## Cho AI agent điều khiển (MCP) — vd Hermes

App có **MCP server** (`mcp_server.py`) để agent tự tạo video bằng lời. Là lớp mỏng bọc REST API, nên **web app phải đang chạy** (`bash run.sh`).

Cấu hình vào MCP client (mẫu: `hermes-mcp-config.json`, sửa `<HOME>`):
```json
{ "mcpServers": { "wevideo": {
  "command": "<HOME>/WeVideo-App/.venv/bin/python",
  "args": ["<HOME>/WeVideo-App/mcp_server.py"],
  "env": { "WEVIDEO_APP_URL": "http://127.0.0.1:8080" } } } }
```

4 tool agent gọi được:
| Tool | Việc |
|---|---|
| `app_health()` | Kiểm engine sẵn sàng chưa (gọi trước) |
| `list_options()` | Giá trị hợp lệ + mặc định + cách viết kịch bản |
| `create_video(script, style?, voice?, transition?, zoom?, duration?, speed?, wait=true)` | Tạo video; `wait=true` trả `video_path` (file mp4 trên máy); `wait=false` trả `job_id` |
| `video_status(job_id)` | Tiến độ khi `wait=false` |

> REST API thuần (không MCP) vẫn dùng được: `POST /api/create` · `GET /api/progress/{id}` · `GET /api/video/{id}` · `GET /api/health` · `GET /api/config`.

## Liên quan
Skill `wevideo-veo` (quy trình gốc) · `flow-agent` (engine) · `build_video2.py` (ráp + zoom/FX/B-roll).
