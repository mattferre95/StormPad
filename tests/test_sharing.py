"""Metadata-safe temporary note and project share export coverage."""

from __future__ import annotations

import os
import time
import zipfile
from datetime import UTC, datetime

from stormpad import attachments
from stormpad.models import TranscriptBlock
from stormpad.session import NoteStore
from stormpad.sharing import ShareExportManager, default_share_directory


def test_note_share_is_readable_collision_safe_and_outside_notes(tmp_path):
    notes_dir = tmp_path / "StormPad" / "Notes"
    store = NoteStore(notes_dir)
    note = store.create_note("My Business Plan")
    note.body = "## Direction\n\n- [x] Ship it\n\n> Keep it local."
    note.transcript = [TranscriptBlock("00:00:04", "Visible words")]
    note.metadata["Private"] = "do not share"
    store.save_note(note)
    before = note.path.read_bytes()
    manager = ShareExportManager(notes_dir, cache_dir=tmp_path / "ShareCache")
    first = manager.export_note(note)
    second = manager.export_note(note)
    assert first.name == "my-business-plan.txt"
    assert second.name == "my-business-plan-2.txt"
    assert notes_dir not in first.parents
    assert first.read_text(encoding="utf-8").startswith("My Business Plan")
    shared = first.read_text(encoding="utf-8")
    assert "[x] Ship it" in shared
    assert "[00:00:04]\nVisible words" in shared
    for private in (note.id, "Project-ID:", "Private:", "Created:", str(note.path)):
        assert private not in shared
    assert note.path.read_bytes() == before


def test_default_share_directory_is_not_inside_stormpad_notes(tmp_path):
    notes_dir = tmp_path / "StormPad" / "Notes"
    assert notes_dir not in default_share_directory().parents


def test_cleanup_removes_only_expired_manager_entries(tmp_path):
    now = time.time()
    manager = ShareExportManager(
        tmp_path / "Notes",
        cache_dir=tmp_path / "ShareCache",
        retention_seconds=60,
        now=lambda: now,
    )
    manager.cache_dir.mkdir()
    stale = manager.cache_dir / "stale.txt"
    recent = manager.cache_dir / "recent.txt"
    stale.write_text("old", encoding="utf-8")
    recent.write_text("new", encoding="utf-8")
    os.utime(stale, (now - 120, now - 120))
    os.utime(recent, (now - 30, now - 30))
    removed = manager.cleanup_expired()
    assert removed == [stale]
    assert not stale.exists()
    assert recent.exists()


def test_project_zip_is_sanitized_rewrites_links_and_copies_only_references(tmp_path):
    notes_dir = tmp_path / "StormPad" / "Notes"
    store = NoteStore(notes_dir, clock=lambda: datetime(2026, 7, 23, tzinfo=UTC))
    project = store.create_project("Build")
    note = store.create_note("Project Note", project_id=project.id)
    source = tmp_path / "photo.png"
    source.write_bytes(b"referenced")
    managed = attachments.import_attachment(source, notes_dir, note.id)
    orphan = managed.parent / "orphan.pdf"
    orphan.write_bytes(b"not referenced")
    relative = attachments.relative_markdown_path(note.path, managed)
    note.body = (
        f"## Plan\n\n![Photo]({relative})\n\n"
        f"Local path: /Users/example/private.txt\n\n"
        f"Project UUID should not leak: {project.id}"
    )
    note.transcript = [TranscriptBlock("00:00:05", "Project transcript")]
    store.save_note(note)
    original_note = note.path.read_bytes()
    original_project = (project.path / ".stormpad-project.json").read_bytes()

    manager = ShareExportManager(
        notes_dir,
        cache_dir=tmp_path / "ShareCache",
        now=lambda: datetime(2026, 7, 23, tzinfo=UTC).timestamp(),
    )
    archive_path = manager.export_project(project, store.list_notes())
    assert archive_path.name == "build.zip"
    assert notes_dir not in archive_path.parents

    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert "Build/README.txt" in names
        assert "Build/Notes/project-note.md" in names
        assert "Build/Notes/project-note.txt" in names
        assert "Build/Attachments/project-note/photo.png" in names
        assert all(".stormpad-project.json" not in name for name in names)
        assert all("orphan.pdf" not in name for name in names)
        markdown = archive.read("Build/Notes/project-note.md").decode()
        readme = archive.read("Build/README.txt").decode()
        assert "../Attachments/project-note/photo.png" in markdown
        assert "## Transcript" in markdown
        assert "Project transcript" in markdown
        assert "[local path removed]" in markdown
        assert project.id not in markdown
        assert note.id not in markdown
        assert "Project-ID:" not in markdown
        assert "Transcript-Block:" not in markdown
        assert ".stormpad-project.json" not in markdown
        assert str(note.path) not in markdown
        assert "Build" in readme
        assert "Notes: 1" in readme
        assert "exported locally from StormPad" in readme

    assert note.path.read_bytes() == original_note
    assert (project.path / ".stormpad-project.json").read_bytes() == original_project
    assert managed.exists()
    assert orphan.exists()


def test_project_share_filename_collisions_are_safe(tmp_path):
    notes_dir = tmp_path / "StormPad" / "Notes"
    store = NoteStore(notes_dir)
    project = store.create_project("StormPad Project")
    manager = ShareExportManager(notes_dir, cache_dir=tmp_path / "ShareCache")
    first = manager.export_project(project, [])
    second = manager.export_project(project, [])
    assert first.name == "stormpad-project.zip"
    assert second.name == "stormpad-project-2.zip"
