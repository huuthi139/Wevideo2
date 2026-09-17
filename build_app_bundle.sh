#!/usr/bin/env bash
# build_app_bundle.sh — tạo WeVideo.app (double-click, có icon Dock) trỏ vào thư mục app này.
# App bundle CHỈ là launcher mỏng: gọi .venv/bin/python desktop.py trong thư mục cài.
set -e
cd "$(dirname "$0")"
APPDIR="$(pwd)"
OUT="${1:-$HOME/Desktop/WeVideo.app}"
rm -rf "$OUT"
mkdir -p "$OUT/Contents/MacOS" "$OUT/Contents/Resources"
cat > "$OUT/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>WeVideo</string>
  <key>CFBundleDisplayName</key><string>WeVideo</string>
  <key>CFBundleIdentifier</key><string>com.wevideo.app</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>WeVideo</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
cat > "$OUT/Contents/MacOS/WeVideo" <<LAUNCH
#!/usr/bin/env bash
export PATH="/opt/homebrew/bin:/usr/local/bin:\$PATH"
cd "$APPDIR"
exec ./.venv/bin/python desktop.py
LAUNCH
chmod +x "$OUT/Contents/MacOS/WeVideo"
echo "✅ Tạo $OUT — kéo vào Dock hoặc double-click để mở WeVideo dạng app."
