"""Focused verification for the unsigned Phase 6A StormPad.app bundle."""

from __future__ import annotations

import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_PATH = ROOT / "dist" / "StormPad.app"

EXPECTED_PLIST = {
    "CFBundleName": "StormPad",
    "CFBundleDisplayName": "StormPad",
    "CFBundleIdentifier": "com.mattferre.stormpad",
    "CFBundlePackageType": "APPL",
    "CFBundleShortVersionString": "0.1.0",
    "CFBundleVersion": "1",
    "CFBundleIconFile": "StormPad.icns",
    "CFBundleDevelopmentRegion": "en",
    "CFBundleInfoDictionaryVersion": "6.0",
    "LSMinimumSystemVersion": "13.0",
    "LSApplicationCategoryType": "public.app-category.productivity",
    "NSPrincipalClass": "NSApplication",
    "NSHighResolutionCapable": True,
    "NSRequiresAquaSystemAppearance": False,
    "NSHumanReadableCopyright": "© 2026 Matt Ferré",
    "NSDocumentsFolderUsageDescription": (
        "StormPad stores your local notes in Documents/StormPad."
    ),
}


def fail(message: str) -> None:
    raise SystemExit(f"Package verification failed: {message}")


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def main() -> int:
    if sys.platform != "darwin":
        fail("verification requires macOS")
    if not APP_PATH.is_dir():
        fail(f"application bundle is missing: {APP_PATH}")

    info_path = APP_PATH / "Contents" / "Info.plist"
    if not info_path.is_file():
        fail(f"Info.plist is missing: {info_path}")
    with info_path.open("rb") as stream:
        info = plistlib.load(stream)

    mismatches = [
        f"{key}: expected {expected!r}, found {info.get(key)!r}"
        for key, expected in EXPECTED_PLIST.items()
        if info.get(key) != expected
    ]
    if mismatches:
        fail("Info.plist mismatch:\n- " + "\n- ".join(mismatches))

    icon_path = APP_PATH / "Contents" / "Resources" / "StormPad.icns"
    if not icon_path.is_file() or icon_path.stat().st_size == 0:
        fail(f"bundle icon is missing or empty: {icon_path}")

    executable_name = info.get("CFBundleExecutable")
    if not isinstance(executable_name, str) or not executable_name:
        fail("CFBundleExecutable is missing")
    executable_path = APP_PATH / "Contents" / "MacOS" / executable_name
    if not executable_path.is_file():
        fail(f"bundle executable is missing: {executable_path}")

    lipo = shutil.which("lipo")
    if lipo is None:
        fail("required macOS tool is missing: lipo")
    architecture = run([lipo, "-archs", str(executable_path)])
    if architecture.returncode != 0:
        fail(architecture.stderr.strip() or "lipo could not inspect the executable")
    architectures = architecture.stdout.split()
    if architectures != ["arm64"]:
        fail(f"expected arm64 executable, found: {' '.join(architectures)}")

    forbidden_parts = {"tests", ".pytest_cache", ".ruff_cache", ".mypy_cache", "__pycache__"}
    forbidden_paths = []
    copied_note_paths = []
    for path in APP_PATH.rglob("*"):
        relative = path.relative_to(APP_PATH)
        lowered_parts = tuple(part.casefold() for part in relative.parts)
        if forbidden_parts.intersection(lowered_parts):
            forbidden_paths.append(str(relative))
        if ".stormpad-project.json" in lowered_parts:
            copied_note_paths.append(str(relative))
        if any(
            lowered_parts[index : index + 2] == ("documents", "stormpad")
            for index in range(max(0, len(lowered_parts) - 1))
        ):
            copied_note_paths.append(str(relative))
    if forbidden_paths:
        fail("development/test paths found:\n- " + "\n- ".join(forbidden_paths[:20]))
    if copied_note_paths:
        fail("possible user-note content found:\n- " + "\n- ".join(copied_note_paths[:20]))

    codesign = shutil.which("codesign")
    if codesign is None:
        fail("required macOS tool is missing: codesign")
    signature = run([codesign, "-dv", "--verbose=4", str(APP_PATH)])
    signature_detail = f"{signature.stdout}\n{signature.stderr}"
    if "Developer ID Application:" in signature_detail or "Authority=" in signature_detail:
        fail("the app has a distribution signing authority")
    if "TeamIdentifier=" in signature_detail and "TeamIdentifier=not set" not in signature_detail:
        fail("the app has a signing team identifier")

    signature_state = (
        "ad hoc linker signature only"
        if "Signature=adhoc" in signature_detail
        else "no bundle signature"
    )
    bundle_size = sum(
        path.stat().st_size
        for path in APP_PATH.rglob("*")
        if path.is_file() and not path.is_symlink()
    )

    print("StormPad Phase 6A package verification passed")
    print(f"Application: {APP_PATH}")
    print(f"Bundle size: {bundle_size} bytes")
    print(f"Executable: {executable_path}")
    print("Architecture: arm64")
    print("Info.plist: approved metadata verified")
    print(f"Icon: {icon_path}")
    print(f"Distribution signing: unsigned ({signature_state})")
    print("User-note content: not present in bundle")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
