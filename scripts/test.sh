#!/usr/bin/env bash
# Run the test suite. Creates a local .venv with dev deps on first run.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3.12}"

if [ ! -d .venv ]; then
  echo "Creating .venv ..."
  "$PYTHON" -m venv .venv
  ./.venv/bin/python -m pip install --upgrade pip >/dev/null
  ./.venv/bin/python -m pip install -e '.[dev]' >/dev/null
fi

exec ./.venv/bin/python -m pytest "$@"
