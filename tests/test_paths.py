"""Tests for path resolution and safe directory creation."""

from __future__ import annotations

from pathlib import Path

import pytest

from stormpad import paths
from stormpad.errors import NotesDirectoryError


def test_notes_dir_is_canonical():
    assert paths.notes_dir() == Path.home() / "Documents" / "StormPad" / "Notes"
    assert paths.app_dir() == Path.home() / "Documents" / "StormPad"


def test_resolve_notes_dir_default_and_override(tmp_path):
    assert paths.resolve_notes_dir() == paths.notes_dir()
    override = tmp_path / "custom"
    assert paths.resolve_notes_dir(override) == override
    assert paths.resolve_notes_dir(str(override)) == override


def test_resolve_notes_dir_has_no_side_effects(tmp_path):
    target = tmp_path / "not-created-yet" / "Notes"
    resolved = paths.resolve_notes_dir(target)
    assert resolved == target
    assert not target.exists()  # resolving must never create anything


def test_ensure_notes_dir_creates_nested(tmp_path):
    target = tmp_path / "a" / "b" / "Notes"
    created = paths.ensure_notes_dir(target)
    assert created == target
    assert target.is_dir()
    # Idempotent.
    assert paths.ensure_notes_dir(target) == target


def test_ensure_notes_dir_wraps_oserror(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("nope")

    monkeypatch.setattr(Path, "mkdir", boom)
    with pytest.raises(NotesDirectoryError):
        paths.ensure_notes_dir(tmp_path / "x")
