#!/usr/bin/env bash
# WEVIDEO-APP — cài đặt 1 lần trên máy mới. Chạy:  bash setup.sh
# Cài: ffmpeg (brew) · venv engine flow-agent (editable, để engine đọc đúng config.env) · venv app.
set -e
cd "$(dirname "$0")"
ENGINE=engine/flow-agent

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
  python3 -m venv "$ENGINE/.venv"
  "$ENGINE/.venv/bin/pip" install -q --upgrade pip
  ( cd "$ENGINE" && ./.venv/bin/pip install -q -e . )   # editable: package ở tại chỗ → tìm thấy config.env
  "$ENGINE/.venv/bin/flow" serve --help >/dev/null 2>&1 && echo "   ok: engine sẵn sàng ($ENGINE/.venv/bin/flow)" \
    || { echo "   ✗ engine cài lỗi"; MISS=1; }
else
  echo "   ⚠ Không có $ENGINE (gói build thiếu engine?) — app sẽ không gen được clip."; MISS=1
fi

echo "==> 3/3  Web app — venv…"
python3 -m venv .venv
./.venv/bin/pip install -q --upgrade pip
./.venv/bin/pip install -q "fastapi>=0.110" "uvicorn>=0.29" pillow edge-tts "mcp>=2,<3"
# Auto-Shorts (cắt video dài → clip ngắn): transcribe + face-detect + upload (khá nặng ~250MB)
./.venv/bin/pip install -q python-multipart faster-whisper opencv-python-headless
echo "   ok: $(./.venv/bin/python -c 'import fastapi,PIL; from mcp.server import MCPServer; print("fastapi",fastapi.__version__,"| pillow",PIL.__version__,"| mcp ok")')"

echo
echo "Xong cài đặt.  Chạy:  bash run.sh"
[ -n "$MISS" ] && echo "‼ Có mục thiếu ở trên — xử lý trước khi tạo video."
exit 0
