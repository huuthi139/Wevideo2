#!/usr/bin/env bash
# Bật/tắt TỰ CẬP NHẬT định kỳ (launchd) cho WeVideo App — chạy trên MÁY TRIỂN KHAI.
#   bash install_autoupdate.sh          # bật (mỗi 30 phút kiểm tra + cập nhật)
#   bash install_autoupdate.sh off      # tắt
set -e
cd "$(dirname "$0")"; HERE="$(pwd)"
LABEL="com.wevideo.autoupdate"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ "$1" = "off" ]; then
  launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  echo "✅ Đã TẮT tự cập nhật ($LABEL)."
  exit 0
fi

command -v gh >/dev/null 2>&1 || echo "⚠ Chưa có gh — auto-update sẽ tự bỏ qua tới khi cài: brew install gh && gh auth login"
mkdir -p "$HOME/Library/LaunchAgents"
sed "s#__APP__#$HERE#g" "$HERE/com.wevideo.autoupdate.plist.template" > "$PLIST"
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "✅ Đã BẬT tự cập nhật — kiểm tra GitHub mỗi 30 phút (log: autoupdate.log)."
echo "   Plist: $PLIST"
echo "   Tắt:   bash install_autoupdate.sh off"
