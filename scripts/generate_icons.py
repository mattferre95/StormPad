"""Generate StormPad.icns from the untouched release artwork."""

from __future__ import annotations

import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_ARTWORK = ROOT / "assets" / "Stormpad_webapp.png"
RESOURCE_DIR = ROOT / "build" / "resources"
ICONSET_DIR = RESOURCE_DIR / "StormPad.iconset"
OUTPUT_ICNS = RESOURCE_DIR / "StormPad.icns"

ICON_FILES = {
    "icon_16x16.png": 16,
    "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32,
    "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
    "icon_512x512@2x.png": 1024,
}

ICNS_CHUNKS = (
    (b"icp4", "icon_16x16.png"),
    (b"ic11", "icon_16x16@2x.png"),
    (b"icp5", "icon_32x32.png"),
    (b"ic12", "icon_32x32@2x.png"),
    (b"ic07", "icon_128x128.png"),
    (b"ic13", "icon_128x128@2x.png"),
    (b"ic08", "icon_256x256.png"),
    (b"ic14", "icon_256x256@2x.png"),
    (b"ic09", "icon_512x512.png"),
    (b"ic10", "icon_512x512@2x.png"),
)


def _tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise RuntimeError(f"Required macOS tool is missing: {name}")
    return path


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise RuntimeError(f"Command failed ({' '.join(command)}): {detail}")


def _remove_temporary_iconset() -> None:
    if ICONSET_DIR.exists():
        if ICONSET_DIR.parent != RESOURCE_DIR or ICONSET_DIR.name != "StormPad.iconset":
            raise RuntimeError(f"Refusing to remove unexpected path: {ICONSET_DIR}")
        shutil.rmtree(ICONSET_DIR)


def _write_icns_from_png_chunks() -> None:
    """Write the documented PNG-backed ICNS container used by iconutil."""
    chunks = []
    for chunk_type, filename in ICNS_CHUNKS:
        image_data = (ICONSET_DIR / filename).read_bytes()
        chunks.append(chunk_type + struct.pack(">I", len(image_data) + 8) + image_data)
    payload = b"".join(chunks)
    OUTPUT_ICNS.write_bytes(b"icns" + struct.pack(">I", len(payload) + 8) + payload)


def generate() -> None:
    """Produce an .iconset and .icns from the source logo using sips/iconutil."""
    if sys.platform != "darwin":
        raise RuntimeError("StormPad icon generation requires macOS")
    if not SOURCE_ARTWORK.is_file():
        raise FileNotFoundError(f"Source artwork is missing: {SOURCE_ARTWORK}")

    sips = _tool("sips")
    iconutil = _tool("iconutil")
    RESOURCE_DIR.mkdir(parents=True, exist_ok=True)

    _remove_temporary_iconset()
    ICONSET_DIR.mkdir()
    if OUTPUT_ICNS.exists():
        OUTPUT_ICNS.unlink()

    try:
        for filename, pixels in ICON_FILES.items():
            destination = ICONSET_DIR / filename
            _run(
                [
                    sips,
                    "-z",
                    str(pixels),
                    str(pixels),
                    str(SOURCE_ARTWORK),
                    "--out",
                    str(destination),
                ]
            )
            if not destination.is_file():
                raise RuntimeError(f"sips did not create {destination}")

        iconutil_result = subprocess.run(
            [
                iconutil,
                "-c",
                "icns",
                str(ICONSET_DIR),
                "-o",
                str(OUTPUT_ICNS),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if iconutil_result.returncode != 0:
            # iconutil on macOS 26.5 rejects iconsets it can successfully
            # unpack. Build the same PNG-backed ICNS container directly, then
            # require iconutil to unpack it below as the native validity check.
            if OUTPUT_ICNS.exists():
                OUTPUT_ICNS.unlink()
            _write_icns_from_png_chunks()
            print(
                "iconutil could not pack the iconset; "
                "used the deterministic ICNS container fallback"
            )
        if not OUTPUT_ICNS.is_file() or OUTPUT_ICNS.stat().st_size == 0:
            raise RuntimeError(f"iconutil did not create a valid output: {OUTPUT_ICNS}")

        _remove_temporary_iconset()
        _run(
            [
                iconutil,
                "-c",
                "iconset",
                str(OUTPUT_ICNS),
                "-o",
                str(ICONSET_DIR),
            ]
        )
        missing = sorted(set(ICON_FILES) - {path.name for path in ICONSET_DIR.iterdir()})
        if missing:
            raise RuntimeError(
                "generated ICNS is missing required representations: "
                + ", ".join(missing)
            )
    finally:
        _remove_temporary_iconset()

    print(f"Generated {OUTPUT_ICNS}")


if __name__ == "__main__":
    try:
        generate()
    except (FileNotFoundError, RuntimeError) as exc:
        raise SystemExit(f"Icon generation failed: {exc}") from exc
