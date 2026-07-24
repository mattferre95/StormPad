#!/usr/bin/env bash
# Build the unsigned compressed StormPad review disk image.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_PATH="$ROOT/dist/StormPad.app"
DMG_PATH="$ROOT/dist/StormPad-0.1.0.dmg"
TEMP_ROOT=""

fail() {
  echo "StormPad DMG build failed: $*" >&2
  exit 1
}

cleanup() {
  if [ -n "$TEMP_ROOT" ] && [ -d "$TEMP_ROOT" ]; then
    case "$TEMP_ROOT" in
      /tmp/stormpad-dmg.*)
        rm -rf -- "$TEMP_ROOT"
        ;;
      *)
        echo "Refusing to clean unexpected temporary path: $TEMP_ROOT" >&2
        ;;
    esac
  fi
}
trap cleanup EXIT

[ "$(uname -s)" = "Darwin" ] || fail "this build requires macOS"
command -v ditto >/dev/null 2>&1 || fail "required macOS tool is missing: ditto"
command -v hdiutil >/dev/null 2>&1 || fail "required macOS tool is missing: hdiutil"
[ -d "$APP_PATH" ] || fail "application bundle is missing: $APP_PATH"

TEMP_ROOT="$(mktemp -d /tmp/stormpad-dmg.XXXXXX)"
STAGING_PATH="$TEMP_ROOT/StormPad"
mkdir "$STAGING_PATH"

ditto "$APP_PATH" "$STAGING_PATH/StormPad.app"
ln -s /Applications "$STAGING_PATH/Applications"

if [ -e "$DMG_PATH" ]; then
  rm -f -- "$DMG_PATH"
fi

hdiutil create \
  -volname "StormPad" \
  -srcfolder "$STAGING_PATH" \
  -format UDZO \
  -ov \
  "$DMG_PATH"

[ -f "$DMG_PATH" ] || fail "hdiutil did not create $DMG_PATH"

echo "Built unsigned review disk image:"
echo "$DMG_PATH"
echo "Unsigned: no Developer ID signing or notarization was performed."
