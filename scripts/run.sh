#!/usr/bin/env bash
# Launch StormPad. Creates a local .venv on first run and installs the app
# (with runtime deps) if needed.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3.12}"

if [ ! -d .venv ]; then
  echo "Creating .venv ..."
  "$PYTHON" -m venv .venv
  ./.venv/bin/python -m pip install --upgrade pip >/dev/null
  ./.venv/bin/python -m pip install -e . >/dev/null
fi

exec ./.venv/bin/python -m stormpad "$@"
