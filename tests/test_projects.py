"""Filesystem-backed project folders and safe note movement."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from stormpad import attachments, storage
from stormpad.block_parser import parse_blocks
from stormpad.blocks import BlockType
from stormpad.errors import ProjectNotEmptyError
from stormpad.models import UNFILED_PROJECT_ID
from stormpad.search import filter_by_project, search_notes
from stormpad.session import NoteStore

TZ = timezone(timedelta(hours=2))
NOW = datetime(2026, 7, 23, 14, 30, 0, tzinfo=TZ)


@pytest.fixture
def store(tmp_path):
    return NoteStore(tmp_path / "StormPad" / "Notes", clock=lambda: NOW)


def test_project_creation_safe_slug_metadata_and_duplicate_names(store):
    first = store.create_project("Build / 2026")
    second = store.create_project("Build / 2026")
    assert first.path.name == "build-2026"
    assert second.path.name == "build-2026-2"
    assert first.id != second.id
    payload = json.loads(
        (first.path / storage.PROJECT_METADATA_FILENAME).read_text(encoding="utf-8")
    )
    assert payload["id"] == first.id
    assert payload["name"] == "Build / 2026"
    assert str(uuid.UUID(payload["id"])) == payload["id"]


def test_project_rename_changes_folder_but_keeps_uuid_and_notes(store):
    project = store.create_project("Build")
    note = store.create_note("Editor plan", project_id=project.id)
    original_id = project.id
    original_note_id = note.id
    renamed = store.rename_project(project.id, "StormPad Build")
    assert renamed.id == original_id
    assert renamed.path.name == "stormpad-build"
    assert not project.path.parent.joinpath("build").exists()
    reloaded = store.load_note(original_note_id)
    assert reloaded.id == original_note_id
    assert reloaded.project_id == original_id
    assert reloaded.path.parent == renamed.path


def test_note_assignment_removal_collision_and_creation_in_project(store):
    project = store.create_project("Build")
    existing = store.create_note("Plan", project_id=project.id)
    unfiled = store.create_note("Plan")
    moved = store.move_note_to_project(unfiled.id, project.id)
    assert moved.path.name == "plan-2.md"
    assert moved.project_id == project.id
    inside = store.create_note("Direct", project_id=project.id)
    assert inside.path.parent == project.path
    removed = store.remove_note_from_project(existing.id)
    assert removed.path.parent == store.notes_dir
    assert removed.project_id is None


def test_move_preserves_note_uuid_and_attachment_files_and_retargets_markdown(store, tmp_path):
    project = store.create_project("Build")
    note = store.create_note("Assets")
    source = tmp_path / "image.png"
    source.write_bytes(b"png")
    managed = attachments.import_attachment(source, store.notes_dir, note.id)
    relative = attachments.relative_markdown_path(note.path, managed)
    note.body = f"![Image]({relative})"
    store.save_note(note)
    moved = store.move_note_to_project(note.id, project.id)
    block = parse_blocks(moved.body)[0]
    assert block.kind == BlockType.IMAGE
    assert moved.id == note.id
    assert managed.exists()
    assert (moved.path.parent / block.target).resolve() == managed.resolve()
    unfiled = store.remove_note_from_project(note.id)
    round_trip = parse_blocks(unfiled.body)[0]
    assert (unfiled.path.parent / round_trip.target).resolve() == managed.resolve()


def test_recursive_scan_legacy_root_and_unknown_project_metadata(store):
    root = store.create_note("Legacy root")
    project = store.create_project("Known")
    nested = store.create_note("Nested", project_id=project.id)
    unknown = store.notes_dir / "Projects" / "unknown"
    unknown.mkdir(parents=True)
    (unknown / storage.PROJECT_METADATA_FILENAME).write_text('{"future": true}\n', encoding="utf-8")
    unknown_note = unknown / "visible.md"
    unknown_note.write_text("# Visible\n\n## Notes\n\nStill here.\n", encoding="utf-8")
    notes = store.list_notes()
    assert {note.id for note in notes} >= {root.id, nested.id}
    assert any(note.path == unknown_note and note.project_id is None for note in notes)
    assert storage.PROJECT_METADATA_FILENAME not in {
        path.name for path in storage.list_note_paths(store.notes_dir)
    }


def test_search_all_unfiled_and_project_filters(store):
    project = store.create_project("Build")
    inside = store.create_note("StormPad project", project_id=project.id)
    root = store.create_note("StormPad root")
    notes = store.list_notes()
    assert {result.note.id for result in search_notes(notes, "StormPad")} == {
        inside.id,
        root.id,
    }
    assert [note.id for note in filter_by_project(notes, project.id)] == [inside.id]
    assert [note.id for note in filter_by_project(notes, UNFILED_PROJECT_ID)] == [root.id]


def test_empty_project_delete_uses_safe_strategy(tmp_path):
    moved = []

    def safe_delete(path: Path):
        destination = tmp_path / "Trash" / path.name
        destination.parent.mkdir()
        path.rename(destination)
        moved.append(destination)

    store = NoteStore(
        tmp_path / "StormPad" / "Notes",
        clock=lambda: NOW,
        delete_strategy=safe_delete,
    )
    project = store.create_project("Disposable")
    store.delete_project(project.id)
    assert moved[0].exists()
    assert store.list_projects() == []


def test_populated_project_requires_move_to_unfiled_and_preserves_notes(store):
    project = store.create_project("Disposable")
    note = store.create_note("Keep me", project_id=project.id)
    with pytest.raises(ProjectNotEmptyError):
        store.delete_project(project.id)
    store.delete_project(project.id, move_notes_to_unfiled=True)
    reloaded = store.load_note(note.id)
    assert reloaded.id == note.id
    assert reloaded.project_id is None
    assert reloaded.path.parent == store.notes_dir
    assert not project.path.exists()
