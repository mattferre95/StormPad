"""Phase 1 smoke tests.

Verify the package and all AppKit-free modules import cleanly and that the
canonical notes path resolves to ~/Documents/StormPad/Notes. Domain behavior
is tested from Phase 2 onward.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import stormpad
from stormpad import paths


def test_version_and_metadata():
    assert stormpad.__version__ == "0.1.0"
    assert stormpad.__app_name__ == "StormPad"
    assert isinstance(stormpad.__tagline__, str) and stormpad.__tagline__


def test_pure_modules_import_without_appkit():
    for name in [
        "stormpad.paths",
        "stormpad.models",
        "stormpad.storage",
        "stormpad.session",
        "stormpad.search",
        "stormpad.preferences",
        "stormpad.theme",
        "stormpad.app",
    ]:
        importlib.import_module(name)


def test_notes_dir_is_canonical():
    expected = Path.home() / "Documents" / "StormPad" / "Notes"
    assert paths.notes_dir() == expected
    assert paths.app_dir() == expected.parent


def test_app_main_runs_headless(capsys):
    from stormpad.app import main

    assert main([]) == 0
    assert "StormPad" in capsys.readouterr().out
