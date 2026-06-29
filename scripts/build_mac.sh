#!/bin/bash
# macOS packaging — lean .app + .dmg (uses project venv to avoid conda bloat)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

VENV="$PROJECT_DIR/.build-venv"
ICON_PNG="assets/comparex_icon.png"
ICON_ICNS="assets/comparex_icon.icns"
ICONSET="assets/comparex.iconset"

echo "=== CompareX macOS packaging (lean) ==="

if [ ! -d "$VENV" ]; then
    echo "Creating build venv at .build-venv ..."
    python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "Rendering app icon (transparent squircle) ..."
python assets/render_icon.py
echo "Generating $ICON_ICNS ..."
rm -rf "$ICONSET"
mkdir -p "$ICONSET"
for size in 16 32 128 256 512; do
    sips -z "$size" "$size" "$ICON_PNG" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
    s2=$((size * 2))
    sips -z "$s2" "$s2" "$ICON_PNG" --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$ICON_ICNS"

echo "Installing CompareX runtime deps into build venv ..."
python -m pip install -U pip wheel setuptools >/dev/null
python -m pip install -r requirements-build.txt

rm -rf build dist

echo "Running PyInstaller ..."
python -m PyInstaller CompareX.spec --noconfirm --clean

APP_PATH="dist/CompareX.app"
if [ ! -d "$APP_PATH" ]; then
    echo "Error: $APP_PATH not found"
    exit 1
fi

# Smoke test (must not crash on import)
echo "Smoke test ..."
"$APP_PATH/Contents/MacOS/CompareX" --help 2>/dev/null || true
if ! "$APP_PATH/Contents/MacOS/CompareX" 2>&1 | head -5 | grep -q "ImportError\|Failed to execute"; then
    echo "Startup check: no immediate import error (GUI may still be opening)."
else
    echo "Warning: app reported import errors — check dist/CompareX.app manually."
fi

DMG_PATH="dist/CompareX.dmg"
rm -f "$DMG_PATH"
hdiutil create -volname "CompareX" -srcfolder "$APP_PATH" -ov -format UDZO "$DMG_PATH"

APP_MB=$(du -sm "$APP_PATH" | cut -f1)
DMG_MB=$(du -sm "$DMG_PATH" | cut -f1)
echo ""
echo "Done."
echo "   App:  $APP_PATH  (${APP_MB} MB)"
echo "   DMG:  $DMG_PATH  (${DMG_MB} MB)"
echo ""
echo "First launch: if macOS blocks the app, right-click CompareX.app → Open."
