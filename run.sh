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
if echo "$H" | grep -q '"extension_connected":true'; then
  echo "✅ Engine + extension: SẴN SÀNG"
else
  echo "⚠ Engine $(echo "$H" | grep -q extension_connected && echo 'đã chạy' || echo 'CHƯA chạy') — còn 2 việc thủ công (chỉ lần đầu):"
  echo "   1) Chrome → chrome://extensions → bật Developer mode → Load unpacked → chọn:"
  echo "      $HERE/engine/flow-chrome-extension"
  echo "   2) Mở tab https://flow.google.com và ĐĂNG NHẬP tài khoản có credit Flow."
  echo "   Chấm trạng thái trên web app sẽ xanh khi xong."
fi

# 2) app
echo "WeVideo App → http://127.0.0.1:$PORT"
exec ./.venv/bin/python server.py
