#!/bin/sh
# Build the Courtyard menu bar app: build.sh <bundle path> <bundle id> <name> <version>
# swiftc comes with the Command Line Tools (xcode-select --install). The executable is
# always "Courtyard"; the name shows in the menu bar and the Finder.
set -eu
out="$1"; id="$2"; name="$3"; version="$4"
src="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$src/.." && pwd)"

rm -rf "$out"
mkdir -p "$out/Contents/MacOS" "$out/Contents/Resources"
swiftc -O -swift-version 5 -framework AppKit -framework ServiceManagement \
  -o "$out/Contents/MacOS/Courtyard" "$src"/Sources/*.swift

cat > "$out/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key><string>Courtyard</string>
  <key>CFBundleIdentifier</key><string>$id</string>
  <key>CFBundleName</key><string>$name</string>
  <key>CFBundleDisplayName</key><string>$name</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$version</string>
  <key>CFBundleVersion</key><string>$version</string>
  <key>CFBundleIconFile</key><string>Courtyard</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>LSUIElement</key><true/>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
EOF

# the icon from the WebUI's 512px PNG, with macOS's own tools; without them the bundle has none
png="$root/webui/icons/icon-512.png"
if [ -f "$png" ] && command -v sips >/dev/null && command -v iconutil >/dev/null; then
  iconset="$out/Contents/Resources/Courtyard.iconset"
  mkdir -p "$iconset"
  for size in 16 32 128 256 512; do
    sips -z "$size" "$size" "$png" --out "$iconset/icon_${size}x${size}.png" >/dev/null
    if [ "$size" -gt 16 ]; then
      half=$((size / 2))
      cp "$iconset/icon_${size}x${size}.png" "$iconset/icon_${half}x${half}@2x.png"
    fi
  done
  iconutil -c icns "$iconset" -o "$out/Contents/Resources/Courtyard.icns"
  sips -z 36 36 "$png" --out "$out/Contents/Resources/menu-icon.png" >/dev/null
  rm -rf "$iconset"
fi

codesign --force --sign - "$out" >/dev/null 2>&1 || true
echo "built $out ($id, $version)"
