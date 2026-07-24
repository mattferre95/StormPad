"""Minimal py2app launcher for the packaged StormPad application."""

from __future__ import annotations

from stormpad.app import main

if __name__ == "__main__":
    raise SystemExit(main())
