#!/usr/bin/env bash
# build_ext_installer.sh — đóng gói RIÊNG extension Chrome thành 1 FILE cài đặt.
# Ra:  dist/WeVideo-Extension-Installer.command  → copy sang máy chưa nạp được extension, double-click.
#
# Vì Chrome CẤM script tự nạp unpacked extension (bảo mật), file này lo hết phần chuẩn bị:
# giải nén extension ra thư mục ổn định + mở chrome://extensions + hiện Finder + copy path vào clipboard.
# Người dùng chỉ còn 1 việc: bật Developer mode rồi KÉO-THẢ thư mục (hoặc Load unpacked → dán path).
set -e
cd "$(dirname "$0")"
APP="$(pwd)"
OUT="dist/WeVideo-Extension-Installer.command"
ENGINE_SRC="${WEVIDEO_ENGINE_SRC:-/Volumes/DATA/AI-APP/flow-agent}"
ENGINE_BRANCH="${WEVIDEO_ENGINE_BRANCH:-flow-v2-ui-transport}"
mkdir -p dist

# lấy extension SẠCH từ branch (chỉ file đã commit — không lẫn _metadata Chrome sinh / working-tree drift)
STAGE="$(mktemp -d)"
if git -C "$ENGINE_SRC" rev-parse --verify -q "$ENGINE_BRANCH" >/dev/null 2>&1; then
  git -C "$ENGINE_SRC" archive --format=tar "$ENGINE_BRANCH" -- flow-chrome-extension | tar -x -C "$STAGE"
  EXT_COMMIT=$(git -C "$ENGINE_SRC" rev-parse --short "$ENGINE_BRANCH")
  echo "→ extension từ branch '$ENGINE_BRANCH' @ $EXT_COMMIT"
elif [ -d "$APP/engine/flow-chrome-extension" ]; then
  rsync -a --exclude='_metadata' --exclude='*.bak-*' "$APP/engine/flow-chrome-extension" "$STAGE/"
  echo "→ extension từ app/engine (fallback, đã loại _metadata)"
else
  echo "✗ Không tìm được extension (branch '$ENGINE_BRANCH' lẫn app/engine)"; rm -rf "$STAGE"; exit 1
fi
[ -f "$STAGE/flow-chrome-extension/manifest.json" ] || { echo "✗ Thiếu manifest.json"; rm -rf "$STAGE"; exit 1; }

TAR="$(mktemp -t wevideo-ext).tar.gz"
tar -czf "$TAR" -C "$STAGE" flow-chrome-extension
PAYLOAD=$(du -h "$TAR" | cut -f1)
rm -rf "$STAGE"

cat > "$OUT" <<'BOOT'
#!/usr/bin/env bash
# ===== WeVideo — cài EXTENSION Chrome (1 file) =====
# Double-click trong Finder, hoặc:  bash WeVideo-Extension-Installer.command
set -e
echo "════════════════════════════════════════"
echo "  Cài extension Flow Agent vào Chrome"
echo "════════════════════════════════════════"
SELF="$0"
if base64 --decode </dev/null >/dev/null 2>&1; then DEC=(base64 --decode); else DEC=(base64 -D); fi

# Nếu máy đã có app → dùng LUÔN extension của app (khỏi tạo bản trùng, khớp health/.ext_loaded)
APPDIR="${WEVIDEO_APP:-$HOME/WeVideo-App}"
if [ -d "$APPDIR/engine/flow-chrome-extension" ]; then
  EXT="$APPDIR/engine/flow-chrome-extension"
  echo "→ Máy đã có app — dùng extension sẵn của app:"
else
  DEST="${WEVIDEO_EXT_DEST:-$HOME/WeVideo-Extension}"
  mkdir -p "$DEST"
  LINE=$(awk '/^__ARCHIVE_BELOW__$/{print NR+1; exit}' "$SELF")
  tail -n +"$LINE" "$SELF" | "${DEC[@]}" | tar -xz -C "$DEST"
  EXT="$DEST/flow-chrome-extension"
  echo "→ Đã giải nén extension vào:"
fi
echo "   $EXT"
echo

printf '%s' "$EXT" | pbcopy 2>/dev/null && echo "① Đường dẫn extension đã COPY vào clipboard (Cmd+V để dán)."
open -R "$EXT/manifest.json" 2>/dev/null && echo "② Đã mở Finder ngay thư mục 'flow-chrome-extension'."
open -a "Google Chrome" "chrome://extensions" 2>/dev/null && echo "③ Đã mở chrome://extensions." \
  || echo "③ Mở Chrome, vào  chrome://extensions"
echo
echo "CÒN 1 VIỆC (Chrome bắt buộc làm tay 1 lần):"
echo "  • Bật 'Developer mode' (góc trên phải trang chrome://extensions)."
echo "  • CÁCH DỄ: KÉO thư mục 'flow-chrome-extension' từ Finder → THẢ vào trang."
echo "  • Hoặc: 'Load unpacked' → dán đường dẫn (Cmd+V) → chọn."
echo
echo "Sau đó mở 1 tab  https://flow.google.com  đã ĐĂNG NHẬP tài khoản có gói Flow."
echo "⚠ ĐỪNG xoá/di chuyển thư mục '$EXT' — Chrome nạp theo đường dẫn này."
echo
echo "✅ Xong phần chuẩn bị. Kéo-thả là extension chạy."
exit 0
__ARCHIVE_BELOW__
BOOT
base64 < "$TAR" >> "$OUT"
chmod +x "$OUT"
rm -f "$TAR"
echo "✅ $OUT  ($(du -h "$OUT" | cut -f1) · payload $PAYLOAD)"
