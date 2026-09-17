#!/usr/bin/env bash
# cai-extension.command — Cài / nạp lại extension Flow Agent vào Chrome (double-click).
# Chrome cấm script tự nạp unpacked extension → file này lo hết phần chuẩn bị, còn 1 thao tác tay.
cd "$(dirname "$0")"
EXT="$(pwd)/engine/flow-chrome-extension"
echo "════════════════════════════════════════════"
echo "  Cài / nạp lại extension Flow Agent"
echo "════════════════════════════════════════════"
[ -f "$EXT/manifest.json" ] || { echo "✗ Không thấy $EXT — chạy trong thư mục app (đã setup)."; read -n1 -s; exit 1; }
VER=$(grep '"version"' "$EXT/manifest.json" | head -1 | tr -dc '0-9.')
echo "Extension: $EXT  (v$VER)"
echo
printf '%s' "$EXT" | pbcopy 2>/dev/null && echo "① Đường dẫn đã COPY vào clipboard (Cmd+V để dán)."
open -R "$EXT/manifest.json" 2>/dev/null && echo "② Đã mở Finder ngay thư mục 'flow-chrome-extension'."
open -a "Google Chrome" "chrome://extensions" 2>/dev/null && echo "③ Đã mở chrome://extensions."
echo
echo "LÀM 1 LẦN (Chrome bắt buộc tay):"
echo "  • Bật 'Chế độ dành cho nhà phát triển' (góc phải trên)."
echo "  • Nếu ĐÃ có 'Flow Agent' cũ → bấm ↻ (nạp lại) là đủ."
echo "  • Nếu CHƯA có → 'Tải tiện ích đã giải nén' → Cmd+Shift+G → dán (Cmd+V) → chọn."
echo "    (hoặc KÉO thư mục 'flow-chrome-extension' từ Finder thả vào trang)."
echo
echo "  • Mở 1 tab  https://flow.google.com  đã ĐĂNG NHẬP tài khoản có gói Flow."
echo "  • Trên app, bấm '📌 Ghim tab hiện tại' để mọi video tạo đúng tab đó."
echo
echo "⚠ ĐỪNG xoá/di chuyển thư mục này — Chrome nạp theo đúng đường dẫn."
echo "✅ Xong phần chuẩn bị."
echo
echo "(Nhấn phím bất kỳ để đóng)"; read -n1 -s
