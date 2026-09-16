#!/usr/bin/env bash
# Cài môi trường cho skill video-nguoi-que trên máy MỚI (macOS). Chạy: bash cai-dat.sh
set -e
cd "$(dirname "$0")"
echo "== 1) ffmpeg / python3 =="
command -v ffmpeg >/dev/null || { command -v brew >/dev/null || { echo "Cần Homebrew: https://brew.sh"; exit 1; }; brew install ffmpeg; }
command -v python3 >/dev/null || brew install python
ffmpeg -version | head -1
echo "== 2) venv edge-tts + Pillow (cục bộ trong skill: .venv-tts) =="
[ -d .venv-tts ] || python3 -m venv .venv-tts
.venv-tts/bin/pip install -q --upgrade pip edge-tts pillow
.venv-tts/bin/edge-tts --version
python3 -c "import PIL" 2>/dev/null || python3 -m pip install -q --user pillow || echo "⚠ python3 hệ thống thiếu Pillow — chạy script bằng .venv-tts/bin/python3 thay cho python3"
echo "== 3) font =="
python3 - <<'PY'
import sys; sys.path.insert(0,"scripts")
from tim_font import tim_font; print("font:", tim_font())
PY
echo "== 4) Chrome =="
if osascript -e 'tell application "Google Chrome" to execute (active tab of front window) javascript "1+1"' >/dev/null 2>&1; then
  echo "AppleScript→JS: OK"
else
  echo "⚠ Chrome chưa cho AppleScript chạy JS. Mở Chrome ▸ menu View ▸ Developer ▸ bật 'Allow JavaScript from Apple Events'"
fi
cat <<'TXT'
== 5) Việc phải làm TAY (một lần) ==
  a. Chrome cài extension "Claude in Chrome" (Anthropic) và bật kết nối trong app Claude → Claude lái được Flow.
  b. Chrome đăng nhập Google có gói AI Pro/Ultra; mở https://flow.google.com → tạo 1 project → ghi URL project.
  c. Kiểm: bash cai-dat.sh không còn dấu ⚠ là xong. Đọc CAI-DAT-MAY-MOI.md để chạy video đầu tiên.
TXT
