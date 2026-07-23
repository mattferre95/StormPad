"""Generate macOS .icns icon sizes from the official logo.

Reproducible, documented derivation of app-icon assets from the untouched
source logo (``assets/Stormpad_logo.png``). The source file is never modified.

This is a Phase 6 (packaging) utility and is intentionally a documented stub in
Phase 1 — it defines the reproducible workflow without running it yet. It uses
only the macOS-native ``sips`` and ``iconutil`` tools (no third-party image
libraries), so the repo stays dependency-light.

Usage (Phase 6):
    python scripts/generate_icons.py
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_LOGO = ROOT / "assets" / "Stormpad_logo.png"
ICON_DIR = ROOT / "assets" / "icon"

# Standard macOS iconset sizes (1x and 2x).
ICON_SIZES = [16, 32, 64, 128, 256, 512, 1024]


def generate() -> None:
    """Produce an .iconset and .icns from the source logo using sips/iconutil."""
    raise NotImplementedError(
        "Icon generation is wired up in Phase 6 (packaging). "
        "It will build an .iconset from assets/Stormpad_logo.png via `sips` "
        "and package it with `iconutil`, never modifying the source file."
    )


if __name__ == "__main__":
    generate()
