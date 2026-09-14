#!/usr/bin/env bash
# WEVIDEO-APP — chạy MỘT lệnh: bật engine gen Veo + web app.  bash run.sh
set -e
cd "$(dirname "$0")"
HERE="$(pwd)"
[ -x ./.venv/bin/python ] || { echo "Chưa cài. Chạy trước:  bash setup.sh"; exit 1; }
PORT=$(grep -E '^APP_PORT=' config.env | cut -d= -f2- | tr -d "\"'" ); PORT=${PORT:-8080}
FLOW=$(grep -E '^FLOW_AGENT_URL=' config.env | cut -d= -f2- | tr -d "\"'" ); FLOW=${FLOW:-http://127.0.0.1:8001}
ENGINE="$HERE/engine/flow-agent"
health() { curl -s --max-time 3 "$FLOW/health" 2>/dev/null; }

# 1) engine
if ! health | grep -q extension_connected; then
  if [ -x "$ENGINE/.venv/bin/flow" ]; then
    echo "→ Bật engine flow-agent… (log: engine.log)"
    ( cd "$ENGINE" && nohup ./.venv/bin/flow serve > "$HERE/engine.log" 2>&1 & )
    for i in $(seq 1 25); do health | grep -q '"extension_connected":true' && break; sleep 1; done
  else
    echo "⚠ Engine chưa cài ($ENGINE/.venv). Chạy: bash setup.sh"
  fi
fi
H=$(health)
EXT="$HERE/engine/flow-chrome-extension"
if echo "$H" | grep -q '"extension_connected":true'; then
  echo "✅ Engine + extension: SẴN SÀNG"
  touch "$HERE/.ext_loaded" 2>/dev/null   # đánh dấu extension đã nạp → lần sau khỏi mở helper
elif [ ! -f "$HERE/.ext_loaded" ]; then
  # LẦN ĐẦU: giúp nạp extension (Chrome không cho tự nạp) — mở sẵn trang + Finder + copy path
  echo "⚠ Lần đầu — nạp extension vào Chrome (mình mở sẵn giúp):"
  printf '%s' "$EXT" | pbcopy 2>/dev/null && echo "   • Đường dẫn extension đã COPY vào clipboard."
  open -R "$EXT" 2>/dev/null              && echo "   • Đã mở Finder ngay thư mục 'flow-chrome-extension'."
  open -a "Google Chrome" "chrome://extensions" 2>/dev/null && echo "   • Đã mở chrome://extensions."
  echo "   → CÁCH DỄ NHẤT: KÉO thư mục 'flow-chrome-extension' từ Finder, THẢ vào trang chrome://extensions (bật Developer mode trước)."
  echo "   → Hoặc: Developer mode → Load unpacked → dán đường dẫn (Cmd+V) → chọn."
  echo "   → Sau đó mở 1 tab https://flow.google.com đã ĐĂNG NHẬP. Xong là chấm trạng thái xanh."
else
  echo "⚠ Extension chưa nối lại — mở Chrome + 1 tab flow.google.com (đã đăng nhập) là được (không cần nạp lại)."
fi

# 2) app
echo "WeVideo App → http://127.0.0.1:$PORT"
exec ./.venv/bin/python server.py
