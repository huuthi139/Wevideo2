#!/usr/bin/env bash
# build_installer.sh — đóng gói WeVideo App + ENGINE flow-agent thành 1 FILE cài đặt.
# Ra:  dist/WeVideo-Installer.command  → copy sang iMac/MacBook, double-click là cài + chạy được.
#
# File .command = bootstrap + archive (base64 tar.gz) nối phía sau. Khi chạy: giải nén ~/WeVideo-App,
# chạy setup.sh (cài ffmpeg qua brew, dựng venv engine + venv app).
# Engine lấy từ branch (mặc định flow-v2-ui-transport); đổi: WEVIDEO_ENGINE_BRANCH=... bash build_installer.sh
set -e
cd "$(dirname "$0")"
APP="$(pwd)"
OUT="dist/WeVideo-Installer.command"
# Nguồn engine (repo flow-agent trên máy build; branch đang checkout = bản đóng gói)
ENGINE_SRC="${WEVIDEO_ENGINE_SRC:-/Volumes/DATA/AI-APP/flow-agent}"
mkdir -p dist

# ── engine từ BRANCH (git archive = chỉ file đã COMMIT của branch; không lẫn venv/output/bak/working-tree drift) ──
ENGINE_BRANCH="${WEVIDEO_ENGINE_BRANCH:-flow-v2-ui-transport}"
[ -d "$ENGINE_SRC/flow-agent" ] || { echo "✗ Không thấy engine tại $ENGINE_SRC (đặt WEVIDEO_ENGINE_SRC=...)"; exit 1; }
rm -rf engine && mkdir -p engine
if git -C "$ENGINE_SRC" rev-parse --verify -q "$ENGINE_BRANCH" >/dev/null; then
  git -C "$ENGINE_SRC" archive --format=tar "$ENGINE_BRANCH" -- flow-agent flow-chrome-extension | tar -x -C engine
  ENG_COMMIT=$(git -C "$ENGINE_SRC" rev-parse --short "$ENGINE_BRANCH")
  echo "→ engine từ branch '$ENGINE_BRANCH' @ $ENG_COMMIT: $(du -sh engine | cut -f1)"
else
  echo "⚠ Branch '$ENGINE_BRANCH' không thấy trong $ENGINE_SRC → dùng rsync working tree."
  rsync -a --exclude='.venv' --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
        --exclude='*.bak-*' --exclude='output' --exclude='*.egg-info' \
        "$ENGINE_SRC/flow-agent/" engine/flow-agent/
  rsync -a --exclude='*.bak-*' "$ENGINE_SRC/flow-chrome-extension/" engine/flow-chrome-extension/
  echo "→ engine (working tree, fallback): $(du -sh engine | cut -f1)"
fi

# stamp phiên bản (sha app) để app biết bản của mình cho tính năng cập nhật
APP_SHA=$(git -C "$APP" rev-parse --short HEAD 2>/dev/null || echo unknown)
echo "$APP_SHA" > "$APP/VERSION"

TAR="$(mktemp -t wevideo).tar.gz"
tar --exclude='.venv' --exclude='projects' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='.git' --exclude='dist' --exclude='*.bak-*' --exclude='output' \
    --exclude='*.egg-info' --exclude='*.log' \
    -czf "$TAR" -C "$(dirname "$APP")" "$(basename "$APP")"
PAYLOAD=$(du -h "$TAR" | cut -f1)

cat > "$OUT" <<'BOOT'
#!/usr/bin/env bash
# ===== WeVideo App — trình cài 1 file (app + engine gen Veo) =====
# Double-click trong Finder, hoặc:  bash WeVideo-Installer.command
# Cài vào thư mục khác:  WEVIDEO_DEST="/duong/dan" bash WeVideo-Installer.command
set -e
DEST="${WEVIDEO_DEST:-$HOME/WeVideo-App}"
SELF="$0"
echo "════════════════════════════════════════"
echo "  Cài WeVideo App → $DEST"
echo "════════════════════════════════════════"
mkdir -p "$DEST"
if base64 --decode </dev/null >/dev/null 2>&1; then DEC=(base64 --decode); else DEC=(base64 -D); fi
LINE=$(awk '/^__ARCHIVE_BELOW__$/{print NR+1; exit}' "$SELF")
tail -n +"$LINE" "$SELF" | "${DEC[@]}" | tar -xz -C "$DEST" --strip-components=1
echo "→ Đã giải nén (app + engine)."
cd "$DEST"
bash setup.sh || echo "⚠ setup gặp cảnh báo — xem log phía trên."
echo
echo "✅ XONG. App ở: $DEST"
echo "   Bước tiếp:  cd \"$DEST\" && bash run.sh"
echo "   (run.sh tự bật engine + web app, rồi hướng dẫn 2 việc còn lại: nạp extension Chrome + login flow.google.com)"
exit 0
__ARCHIVE_BELOW__
BOOT
base64 < "$TAR" >> "$OUT"
chmod +x "$OUT"
rm -f "$TAR"
echo "✅ $OUT  ($(du -h "$OUT" | cut -f1) · payload $PAYLOAD)"
