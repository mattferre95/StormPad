"""Dedicated py2app configuration for the unsigned StormPad release bundle."""

from __future__ import annotations

import sys
from pathlib import Path

from setuptools import setup

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

APP = [
    {
        "script": str(ROOT / "scripts" / "stormpad_app_launcher.py"),
        "dest_base": "StormPad",
    }
]

PY2APP_OPTIONS = {
    "argv_emulation": False,
    "arch": "arm64",
    "bdist_base": str(ROOT / "build" / "py2app"),
    "dist_dir": str(ROOT / "dist"),
    "iconfile": str(ROOT / "build" / "resources" / "StormPad.icns"),
    "packages": ["stormpad"],
    "includes": ["AppKit", "AVFoundation", "Foundation", "objc"],
    "excludes": [
        "packaging",
        "pkg_resources",
        "pytest",
        "ruff",
        "setuptools",
        "test",
        "wheel",
    ],
    "plist": {
        "CFBundleName": "StormPad",
        "CFBundleDisplayName": "StormPad",
        "CFBundleIdentifier": "com.mattferre.stormpad",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "0.1.2",
        "CFBundleVersion": "3",
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
    },
}

setup(
    name="StormPad",
    version="0.1.2",
    description="A local-first notepad for capturing ideas as they happen.",
    app=APP,
    install_requires=[],
    options={"py2app": PY2APP_OPTIONS},
)
