"""Tests for Markdown serialization/parsing, filenames, and file I/O."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from stormpad import models, storage
from stormpad.errors import AtomicWriteError
from stormpad.models import Note, TranscriptBlock

TZ = timezone(timedelta(hours=2))
T0 = datetime(2026, 7, 23, 14, 30, 0, tzinfo=TZ)


def make_note(tmp_path: Path, **overrides) -> Note:
    base = dict(
        id="2026-07-23-1430-idea",
        path=tmp_path / "2026-07-23-1430-idea.md",
        title="App idea",
        body="First line.\nSecond line.",
        category=models.IDEAS,
        created_at=T0,
        updated_at=T0,
        transcript=[],
    )
    base.update(overrides)
    return Note(**base)


# --- Round trips --------------------------------------------------------------


def test_serialize_parse_round_trip(tmp_path):
    note = make_note(
        tmp_path,
        transcript=[
            TranscriptBlock("00:00:04", "A captured thought."),
            TranscriptBlock("00:00:11", "Another chunk."),
        ],
    )
    text = storage.serialize(note)
    parsed = storage.parse(text, note_id=note.id, path=note.path)
    assert parsed == note


def test_serialize_is_deterministic_and_idempotent(tmp_path):
    note = make_note(tmp_path, transcript=[TranscriptBlock("00:00:04", "x")])
    once = storage.serialize(note)
    parsed = storage.parse(once, note_id=note.id, path=note.path)
    assert storage.serialize(parsed) == once


def test_empty_note_round_trip(tmp_path):
    note = make_note(tmp_path, title="Untitled Note", body="", transcript=[])
    text = storage.serialize(note)
    parsed = storage.parse(text, note_id=note.id, path=note.path)
    assert parsed.body == ""
    assert parsed.transcript == []
    assert parsed == note


def test_multiline_body_preserved(tmp_path):
    body = "Para one.\n\nPara two line a\nPara two line b"
    note = make_note(tmp_path, body=body)
    parsed = storage.parse(
        storage.serialize(note), note_id=note.id, path=note.path
    )
    assert parsed.body == body


def test_unicode_content_round_trip(tmp_path):
    note = make_note(
        tmp_path,
        title="Café résumé — 日本語",
        body="naïve façade — 東京",
        transcript=[TranscriptBlock("00:00:04", "café 東京")],
    )
    parsed = storage.parse(
        storage.serialize(note), note_id=note.id, path=note.path
    )
    assert parsed == note


# --- Filenames ----------------------------------------------------------------


def test_slugify_basic():
    assert storage.slugify("Hello World") == "hello-world"
    assert storage.slugify("  Spaced  Out  ") == "spaced-out"


def test_slugify_drops_unsafe_chars():
    assert storage.slugify("a/b:c*?<>|d") == "abcd"
    assert storage.slugify("weird___name") == "weird-name"


def test_slugify_keeps_unicode_letters():
    assert storage.slugify("Café Résumé") == "café-résumé"
    assert storage.slugify("東京 notes") == "東京-notes"


def test_slugify_empty_fallback():
    assert storage.slugify("") == "untitled-note"
    assert storage.slugify("///") == "untitled-note"


def test_build_filename():
    assert storage.build_filename(T0, "app-idea") == "2026-07-23-1430-app-idea.md"


def test_unique_path_avoids_collision(tmp_path):
    first = tmp_path / "2026-07-23-1430-idea.md"
    first.write_text("x", encoding="utf-8")
    second = storage.unique_path(tmp_path, "2026-07-23-1430-idea.md")
    assert second.name == "2026-07-23-1430-idea-2.md"
    second.write_text("y", encoding="utf-8")
    third = storage.unique_path(tmp_path, "2026-07-23-1430-idea.md")
    assert third.name == "2026-07-23-1430-idea-3.md"


def test_unique_path_no_collision(tmp_path):
    got = storage.unique_path(tmp_path, "fresh.md")
    assert got == tmp_path / "fresh.md"


# --- File I/O -----------------------------------------------------------------


def test_atomic_write_and_read(tmp_path):
    path = tmp_path / "note.md"
    storage.atomic_write_text(path, "hello\n")
    assert path.read_text(encoding="utf-8") == "hello\n"
    # No stray temp files left behind.
    assert [p.name for p in tmp_path.iterdir()] == ["note.md"]


def test_atomic_write_failure_leaves_destination_untouched(tmp_path, monkeypatch):
    path = tmp_path / "note.md"
    path.write_text("original\n", encoding="utf-8")

    def boom(src, dst):
        raise OSError("replace failed")

    monkeypatch.setattr(storage.os, "replace", boom)
    with pytest.raises(AtomicWriteError):
        storage.atomic_write_text(path, "new content\n")

    assert path.read_text(encoding="utf-8") == "original\n"
    # Temp file cleaned up: only the original remains.
    assert [p.name for p in tmp_path.iterdir()] == ["note.md"]


def test_write_and_read_note(tmp_path):
    note = make_note(tmp_path)
    storage.write_note(note)
    assert note.path.exists()
    loaded = storage.read_note(note.path)
    assert loaded.title == note.title
    assert loaded.body == note.body
    assert loaded.id == note.id


def test_list_note_paths(tmp_path):
    assert storage.list_note_paths(tmp_path) == []
    (tmp_path / "b.md").write_text("# B\n", encoding="utf-8")
    (tmp_path / "a.md").write_text("# A\n", encoding="utf-8")
    (tmp_path / ".hidden.md").write_text("# H\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("nope", encoding="utf-8")
    names = [p.name for p in storage.list_note_paths(tmp_path)]
    assert names == ["a.md", "b.md"]  # sorted, only .md, no dotfiles


def test_list_note_paths_missing_dir(tmp_path):
    assert storage.list_note_paths(tmp_path / "does-not-exist") == []


# --- Lenient parsing ----------------------------------------------------------


def test_malformed_metadata_recovers(tmp_path):
    text = (
        "# Broken Note\n\n"
        "Created: not-a-date\n"
        "Updated: also-bad\n"
        "Category: Wormhole\n\n"
        "## Notes\n\n"
        "The body survives.\n"
    )
    fallback = datetime(2020, 1, 1, tzinfo=TZ)
    note = storage.parse(text, note_id="x", path=tmp_path / "x.md", fallback=fallback)
    assert note.title == "Broken Note"
    assert note.body == "The body survives."
    assert note.category == models.DEFAULT_CATEGORY  # invalid -> default
    assert note.created_at == fallback  # unparseable -> fallback
    assert note.updated_at == fallback


def test_missing_transcript_section(tmp_path):
    text = "# T\n\nCategory: Ideas\n\n## Notes\n\nBody only.\n"
    note = storage.parse(text, note_id="x", path=tmp_path / "x.md")
    assert note.transcript == []
    assert note.body == "Body only."


def test_missing_title_defaults(tmp_path):
    text = "Category: Ideas\n\n## Notes\n\nBody.\n"
    note = storage.parse(text, note_id="x", path=tmp_path / "x.md")
    assert note.title == storage.DEFAULT_TITLE


def test_read_note_reflects_external_edit(tmp_path):
    note = make_note(tmp_path)
    storage.write_note(note)
    # Simulate an external editor changing the file.
    note.path.write_text(
        "# Edited Elsewhere\n\nCategory: Drafts\n\n## Notes\n\nchanged\n",
        encoding="utf-8",
    )
    reloaded = storage.read_note(note.path)
    assert reloaded.title == "Edited Elsewhere"
    assert reloaded.category == models.DRAFTS
    assert reloaded.body == "changed"
