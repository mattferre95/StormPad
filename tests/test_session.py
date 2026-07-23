"""Tests for the NoteStore session/operations layer."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from stormpad import models
from stormpad.errors import (
    EmptyTranscriptError,
    InvalidCategoryError,
    NoteNotFoundError,
)
from stormpad.session import NoteStore

TZ = timezone(timedelta(hours=2))


class FakeClock:
    """Deterministic, monotonically-advancing clock."""

    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def tick(self, seconds: int = 60) -> datetime:
        self.now = self.now + timedelta(seconds=seconds)
        return self.now


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 7, 23, 14, 30, 0, tzinfo=TZ))


@pytest.fixture
def store(tmp_path, clock) -> NoteStore:
    return NoteStore(tmp_path / "Notes", clock=clock)


def test_create_note_writes_file(store):
    note = store.create_note("App idea", models.IDEAS)
    assert note.path.exists()
    assert note.title == "App idea"
    assert note.category == models.IDEAS
    assert note.path.name == "app-idea.md"
    assert str(uuid.UUID(note.id)) == note.id
    assert note.id != note.path.stem
    assert f"ID: {note.id}" in note.path.read_text(encoding="utf-8")


def test_create_note_invalid_category(store):
    with pytest.raises(InvalidCategoryError):
        store.create_note("x", "Bogus")


def test_rename_commits_filename_but_keeps_stable_id(store, clock):
    note = store.create_note("Original")
    original_path = note.path
    stable_id = note.id
    clock.tick()
    renamed = store.update_title(note.id, "A Completely Different Title")
    assert renamed.title == "A Completely Different Title"
    assert renamed.path.name == "a-completely-different-title.md"
    assert renamed.id == stable_id
    assert not original_path.exists()
    # Reload from disk confirms persistence.
    assert store.load_note(note.id).title == "A Completely Different Title"


def test_update_body_and_timestamp(store, clock):
    note = store.create_note("Note")
    created_updated = note.updated_at
    clock.tick()
    updated = store.update_body(note.id, "hello body")
    assert updated.body == "hello body"
    assert updated.updated_at > created_updated
    assert store.load_note(note.id).body == "hello body"


def test_update_category(store):
    note = store.create_note("Note", models.IDEAS)
    store.update_category(note.id, models.SESSIONS)
    assert store.load_note(note.id).category == models.SESSIONS
    with pytest.raises(InvalidCategoryError):
        store.update_category(note.id, "Nope")


def test_append_one_transcript_block(store):
    note = store.create_note("Session", models.SESSIONS)
    store.append_transcript_block(note.id, "First chunk", 4)
    reloaded = store.load_note(note.id)
    assert len(reloaded.transcript) == 1
    assert reloaded.transcript[0].timestamp == "00:00:04"
    assert reloaded.transcript[0].text == "First chunk"


def test_append_multiple_blocks_preserve_order(store):
    note = store.create_note("Session", models.SESSIONS)
    store.append_transcript_block(note.id, "one", 4)
    store.append_transcript_block(note.id, "two", "00:00:11")
    reloaded = store.load_note(note.id)
    assert [b.text for b in reloaded.transcript] == ["one", "two"]
    assert [b.timestamp for b in reloaded.transcript] == ["00:00:04", "00:00:11"]


def test_append_empty_transcript_rejected(store):
    note = store.create_note("Session")
    with pytest.raises(EmptyTranscriptError):
        store.append_transcript_block(note.id, "   ", 4)


def test_append_test_transcript_helper(store):
    note = store.create_note("Session", models.SESSIONS)
    store.append_test_transcript(note.id)
    store.append_test_transcript(note.id)
    reloaded = store.load_note(note.id)
    assert [b.timestamp for b in reloaded.transcript] == ["00:00:04", "00:00:11"]
    assert all(b.text for b in reloaded.transcript)


def test_list_notes_sorted_by_updated(store, clock):
    a = store.create_note("A")
    clock.tick()
    b = store.create_note("B")
    clock.tick()
    store.update_body(a.id, "touched last")  # a becomes most recent
    listed = store.list_notes()
    assert [n.id for n in listed] == [a.id, b.id]


def test_delete_note(store):
    note = store.create_note("Temp")
    removed = store.delete_note(note.id)
    assert removed == note.path
    assert not note.path.exists()
    with pytest.raises(NoteNotFoundError):
        store.load_note(note.id)


def test_delete_missing_note(store):
    with pytest.raises(NoteNotFoundError):
        store.delete_note("nope")


def test_custom_delete_strategy_is_used(tmp_path, clock):
    trashed: list = []
    trash_dir = tmp_path / "Trash"
    trash_dir.mkdir()

    def move_to_trash(path):
        target = trash_dir / path.name
        path.rename(target)
        trashed.append(target)

    store = NoteStore(tmp_path / "Notes", clock=clock, delete_strategy=move_to_trash)
    note = store.create_note("Temp")
    store.delete_note(note.id)
    assert not note.path.exists()
    assert len(trashed) == 1 and trashed[0].exists()


def test_full_reload_after_body_and_transcript(store, clock):
    """End-to-end: create, edit, append, reload — the manual scenario."""
    note = store.create_note("Reload me", models.SESSIONS)
    clock.tick()
    store.update_body(note.id, "line 1\nline 2")
    store.append_transcript_block(note.id, "chunk a", 4)
    store.append_transcript_block(note.id, "chunk b", 11)

    fresh = NoteStore(store.notes_dir, clock=clock).load_note(note.id)
    assert fresh.body == "line 1\nline 2"
    assert [b.text for b in fresh.transcript] == ["chunk a", "chunk b"]


def test_title_collision_uses_numbered_suffix(store):
    first = store.create_note("Same title")
    second = store.create_note("Other")
    renamed = store.update_title(second.id, "Same title")
    assert first.path.name == "same-title.md"
    assert renamed.path.name == "same-title-2.md"


def test_save_with_title_commit_updates_path(store):
    note = store.create_note("Original")
    stable_id = note.id
    note.title = "Committed later"
    store.save_note(note, commit_title=True)
    assert note.path.name == "committed-later.md"
    assert store.load_note(stable_id).path == note.path


def test_delete_stages_managed_attachments_with_note(tmp_path, clock):
    deleted_bundles = []

    def inspect_delete(bundle):
        assert (bundle / "Notes").is_dir()
        assert (bundle / "Attachments").is_dir()
        deleted_bundles.append(bundle)
        import shutil

        shutil.rmtree(bundle)

    store = NoteStore(tmp_path / "StormPad" / "Notes", clock=clock, delete_strategy=inspect_delete)
    note = store.create_note("With attachment")
    managed = tmp_path / "StormPad" / "Attachments" / note.id
    managed.mkdir(parents=True)
    (managed / "brief.pdf").write_bytes(b"pdf")
    store.delete_note(note.id)
    assert len(deleted_bundles) == 1
    assert not note.path.exists()
    assert not managed.exists()
