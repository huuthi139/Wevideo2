#!/usr/bin/env bash
# TỰ CẬP NHẬT WeVideo App từ GitHub — chạy ĐỊNH KỲ qua launchd (xem install_autoupdate.sh).
# Dùng CHUNG logic /api/update của app (whitelist CODE, giữ config.env/projects/engine) → 1 nguồn sự thật.
# Chỉ cài trên MÁY TRIỂN KHAI (Mac mini/iMac). ĐỪNG cài trên máy build (sẽ đè code đang sửa).
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
cd "$(dirname "$0")" || exit 0
HERE="$(pwd)"
PORT=$(grep -E '^APP_PORT=' config.env 2>/dev/null | cut -d= -f2- | tr -d "\"'"); PORT=${PORT:-8080}
LOG="$HERE/autoupdate.log"; exec >>"$LOG" 2>&1
# giữ log gọn (≤ 500 dòng)
[ -f "$LOG" ] && tail -n 500 "$LOG" > "$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG" 2>/dev/null

echo "── $(date '+%F %T') kiểm tra cập nhật ──"
command -v gh >/dev/null 2>&1 || { echo "thiếu gh → bỏ qua (cài: brew install gh && gh auth login)"; exit 0; }
gh auth status >/dev/null 2>&1 || { echo "gh chưa đăng nhập → bỏ qua (gh auth login)"; exit 0; }

ver() { curl -s --max-time 3 "http://127.0.0.1:$PORT/api/version" 2>/dev/null; }

# app chưa chạy → bật lên trước (endpoint /api/update cần app sống)
if ! ver | grep -q '"current"'; then
  echo "app chưa chạy → bật run.sh"
  nohup bash "$HERE/run.sh" >"$HERE/run.log" 2>&1 &
  for i in $(seq 1 20); do ver | grep -q '"current"' && break; sleep 1; done
fi

V=$(ver)
echo "version: $V"
echo "$V" | grep -q '"current"' || { echo "không hỏi được /api/version → app lỗi, bỏ qua."; exit 0; }
echo "$V" | grep -q '"update_available":true' || { echo "đã mới nhất."; exit 0; }

echo "→ có bản mới, đang cập nhật…"
R=$(curl -s --max-time 150 -X POST "http://127.0.0.1:$PORT/api/update")
echo "update: $R"
echo "$R" | grep -q '"ok": *true' || { echo "cập nhật lỗi → giữ bản cũ."; exit 0; }

# khởi động lại để áp code mới
pkill -f "$HERE/server.py" 2>/dev/null || true
sleep 2
nohup bash "$HERE/run.sh" >"$HERE/run.log" 2>&1 &
sleep 3
echo "✅ đã cập nhật + khởi động lại — $(ver | tr ',' '\n' | grep current)"
