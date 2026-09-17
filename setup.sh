#!/usr/bin/env bash
# WEVIDEO-APP — cài đặt 1 lần trên máy mới. Chạy:  bash setup.sh
# Cài: ffmpeg (brew) · venv engine flow-agent (editable, để engine đọc đúng config.env) · venv app.
set -e
cd "$(dirname "$0")"
ENGINE=engine/flow-agent

# Chọn Python >=3.10 — engine flow-agent yêu cầu >=3.10, mà macOS system python3 hay là 3.9.
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  command -v "$c" >/dev/null 2>&1 || continue
  v=$("$c" -c 'import sys;print(sys.version_info[0]*100+sys.version_info[1])' 2>/dev/null)
  [ -n "$v" ] && [ "$v" -ge 310 ] && { PY="$c"; break; }
done
[ -n "$PY" ] && echo "==> Python: $PY ($($PY --version 2>&1))" \
  || { echo "‼ Cần Python >=3.10 (engine flow-agent yêu cầu). Cài:  brew install python@3.12"; exit 1; }

echo "==> 1/3  ffmpeg…"
if ! command -v ffmpeg >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "   chưa có → brew install ffmpeg (vài phút)…"; brew install ffmpeg
  else
    echo "   ⚠ THIẾU ffmpeg và không có Homebrew. Cài Homebrew (brew.sh) rồi:  brew install ffmpeg"; MISS=1
  fi
fi
command -v ffmpeg >/dev/null 2>&1 && echo "   ok: $(ffmpeg -version | head -1 | cut -d' ' -f1-3)"

echo "==> 2/3  Engine gen Veo (flow-agent) — venv riêng…"
if [ -f "$ENGINE/pyproject.toml" ]; then
  "$PY" -m venv "$ENGINE/.venv"
  "$ENGINE/.venv/bin/pip" install -q --upgrade pip
  ( cd "$ENGINE" && ./.venv/bin/pip install -q -e . )   # editable: package ở tại chỗ → tìm thấy config.env
  # [16/09] tạo config.env engine từ mẫu nếu máy chưa có (clone/installer sạch không kèm id máy build)
  [ -f "$ENGINE/config.env" ] || { [ -f "$ENGINE/config.env.example" ] && cp "$ENGINE/config.env.example" "$ENGINE/config.env" && echo "   → tạo engine/config.env từ mẫu (sửa DEFAULT_PROJECT nếu cần)"; }
  "$ENGINE/.venv/bin/flow" serve --help >/dev/null 2>&1 && echo "   ok: engine sẵn sàng ($ENGINE/.venv/bin/flow)" \
    || { echo "   ✗ engine cài lỗi"; MISS=1; }
else
  echo "   ⚠ Không có $ENGINE (gói build thiếu engine?) — app sẽ không gen được clip."; MISS=1
fi

echo "==> 3/3  Web app — venv…"
"$PY" -m venv .venv
./.venv/bin/pip install -q --upgrade pip
./.venv/bin/pip install -q "fastapi>=0.110" "uvicorn>=0.29" pillow edge-tts "mcp>=2,<3"
# Auto-Shorts (cắt video dài → clip ngắn): transcribe + face-detect + upload (khá nặng ~250MB)
./.venv/bin/pip install -q python-multipart faster-whisper opencv-python-headless
# Cửa sổ app native trên macOS (desktop.py) — pywebview + pyobjc
./.venv/bin/pip install -q pywebview 2>/dev/null || echo "   ⚠ pywebview cài lỗi (cửa sổ native bỏ qua; vẫn dùng được qua http://127.0.0.1:PORT)"
echo "   ok: $(./.venv/bin/python -c 'import fastapi,PIL; from mcp.server import MCPServer; print("fastapi",fastapi.__version__,"| pillow",PIL.__version__,"| mcp ok")')"

echo
echo "Xong cài đặt.  Chạy:  bash run.sh"
[ -n "$MISS" ] && echo "‼ Có mục thiếu ở trên — xử lý trước khi tạo video."
exit 0
