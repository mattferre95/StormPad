#!/usr/bin/env bash
# Build the unsigned arm64 StormPad.app review artifact.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${STORMPAD_RELEASE_PYTHON:-python3.12}"
PY2APP_BUILD="$ROOT/build/py2app"
APP_PATH="$ROOT/dist/StormPad.app"

fail() {
  echo "StormPad app build failed: $*" >&2
  exit 1
}

remove_generated_directory() {
  local target="$1"
  case "$target" in
    "$PY2APP_BUILD"|"$APP_PATH")
      ;;
    *)
      fail "refusing to remove unexpected path: $target"
      ;;
  esac
  if [ -e "$target" ]; then
    rm -rf -- "$target"
  fi
}

[ "$(uname -s)" = "Darwin" ] || fail "this build requires macOS"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || fail "Python not found: $PYTHON_BIN"

"$PYTHON_BIN" - <<'PY'
import platform
import sys
from importlib.metadata import PackageNotFoundError, version

if sys.version_info[:2] != (3, 12):
    raise SystemExit(
        f"Release build requires Python 3.12; found {sys.version.split()[0]}"
    )
if platform.machine() != "arm64":
    raise SystemExit(
        f"Phase 6A requires an arm64 Python; found {platform.machine()}"
    )

required = {
    "py2app": "0.28.10",
    "setuptools": "80.9.0",
    "wheel": "0.45.1",
    "pyobjc-core": "12.2.1",
    "pyobjc-framework-Cocoa": "12.2.1",
    "pyobjc-framework-AVFoundation": "12.2.1",
}
errors = []
for distribution, expected in required.items():
    try:
        actual = version(distribution)
    except PackageNotFoundError:
        errors.append(f"{distribution} is not installed")
    else:
        if actual != expected:
            errors.append(f"{distribution} must be {expected}, found {actual}")
if errors:
    raise SystemExit(
        "Release environment does not match requirements-release.txt:\n- "
        + "\n- ".join(errors)
    )
PY

cd "$ROOT"
"$PYTHON_BIN" scripts/generate_icons.py
remove_generated_directory "$PY2APP_BUILD"
remove_generated_directory "$APP_PATH"
mkdir -p "$ROOT/dist"

cd "$ROOT/release"
MACOSX_DEPLOYMENT_TARGET=13.0 "$PYTHON_BIN" setup_app.py py2app

[ -d "$APP_PATH" ] || fail "py2app did not create $APP_PATH"

find "$APP_PATH/Contents/Resources" \
  -type d \
  \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache -o -name .mypy_cache \) \
  -prune \
  -exec rm -rf -- {} +

echo "Built unsigned review application:"
echo "$APP_PATH"
echo "Unsigned: no Developer ID signing or notarization was performed."
