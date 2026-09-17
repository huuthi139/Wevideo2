#!/usr/bin/env bash
# WeVideo.command — mở app WeVideo dạng cửa sổ riêng (double-click).
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
[ -x ./.venv/bin/python ] || { echo "Chưa cài. Chạy trước: bash setup.sh"; read -n1 -s; exit 1; }
exec ./.venv/bin/python desktop.py
