#!/usr/bin/env bash
# Install a locally built StormPad DMG into /Applications on this Mac.
#
# Local development only. The bundle this installs is ad hoc signed, not
# Developer ID signed and not notarized, so it is not suitable for public
# distribution. Public releases need their own signing and notarization path.
#
# Usage:
#   ./scripts/install-local.sh "dist/StormPad-0.1.2.dmg"
set -euo pipefail

APP_NAME="StormPad.app"
TARGET="/Applications/$APP_NAME"
MOUNT_POINT=""

fail() {
  echo "StormPad local install failed: $*" >&2
  exit 1
}

cleanup() {
  if [ -n "$MOUNT_POINT" ] && [ -d "$MOUNT_POINT" ]; then
    # Best effort: the install already succeeded or already failed loudly.
    hdiutil detach "$MOUNT_POINT" -quiet 2>/dev/null \
      || hdiutil detach "$MOUNT_POINT" -force -quiet 2>/dev/null \
      || echo "Warning: could not unmount $MOUNT_POINT" >&2
    rmdir "$MOUNT_POINT" 2>/dev/null || true
  fi
}
trap cleanup EXIT

[ "$(uname -s)" = "Darwin" ] || fail "this installer requires macOS"
[ "$#" -eq 1 ] || fail "usage: $0 <path-to-dmg>"

DMG_PATH="$1"
[ -f "$DMG_PATH" ] || fail "disk image not found: $DMG_PATH"

for tool in hdiutil ditto xattr codesign; do
  command -v "$tool" >/dev/null 2>&1 || fail "required macOS tool is missing: $tool"
done

MOUNT_POINT="$(mktemp -d /tmp/stormpad-install.XXXXXX)" \
  || fail "could not create a temporary mount point"

echo "Mounting $DMG_PATH"
hdiutil attach "$DMG_PATH" -mountpoint "$MOUNT_POINT" -nobrowse -quiet \
  || fail "could not mount $DMG_PATH"

SOURCE_APP="$MOUNT_POINT/$APP_NAME"
[ -d "$SOURCE_APP" ] || fail "$APP_NAME not found inside $DMG_PATH"

# Refuse to install a bundle whose signature is already broken; that is the
# exact condition that makes macOS report the app as damaged.
codesign --verify --deep --strict "$SOURCE_APP" 2>/dev/null \
  || fail "the app in the disk image has an invalid signature; rebuild with scripts/build_app.sh"

# Replace any previous install. Guarded to the literal target path so this can
# never expand into something else.
if [ -e "$TARGET" ]; then
  [ "$TARGET" = "/Applications/$APP_NAME" ] || fail "refusing to remove unexpected path: $TARGET"
  echo "Removing previous $TARGET"
  rm -rf -- "$TARGET" || fail "could not remove the previous install at $TARGET"
fi

echo "Copying $APP_NAME into /Applications"
ditto "$SOURCE_APP" "$TARGET" || fail "could not copy $APP_NAME into /Applications"

# Clear the download flag for this one locally installed bundle. Gatekeeper is
# left fully enabled system wide.
echo "Clearing com.apple.quarantine on $TARGET"
xattr -dr com.apple.quarantine "$TARGET" 2>/dev/null || true

codesign --verify --deep --strict "$TARGET" \
  || fail "the installed app does not verify at $TARGET"

echo "Unmounting $MOUNT_POINT"
hdiutil detach "$MOUNT_POINT" -quiet || fail "could not unmount $MOUNT_POINT"
rmdir "$MOUNT_POINT" 2>/dev/null || true
MOUNT_POINT=""

echo "Opening $TARGET"
open "$TARGET" || fail "could not open $TARGET"

echo "StormPad installed and launched from $TARGET"
echo "Ad hoc signed local build: not notarized, not for public distribution."
