"""Managed attachment storage tests."""

from __future__ import annotations

import pytest

from stormpad import attachments
from stormpad.errors import StorageError

NOTE_ID = "d746bb5e-4b34-4bf9-a23e-1d98f69b1475"


def test_attachment_root_and_stable_id_directory(tmp_path):
    notes = tmp_path / "StormPad" / "Notes"
    assert attachments.attachment_root(notes) == tmp_path / "StormPad" / "Attachments"
    assert attachments.note_attachment_dir(notes, NOTE_ID).name == NOTE_ID


def test_copy_image_and_relative_path_survive_source_removal(tmp_path):
    notes = tmp_path / "StormPad" / "Notes"
    notes.mkdir(parents=True)
    note_path = notes / "idea.md"
    source = tmp_path / "mood.png"
    source.write_bytes(b"image")
    managed = attachments.import_attachment(source, notes, NOTE_ID)
    relative = attachments.relative_markdown_path(note_path, managed)
    source.unlink()
    assert managed.read_bytes() == b"image"
    assert relative == f"../Attachments/{NOTE_ID}/mood.png"
    assert attachments.is_image(managed)


def test_copy_file_collision_and_unsafe_filename(tmp_path):
    notes = tmp_path / "StormPad" / "Notes"
    source = tmp_path / "bad:name?.PDF"
    source.write_bytes(b"one")
    first = attachments.import_attachment(source, notes, NOTE_ID)
    second = attachments.import_attachment(source, notes, NOTE_ID)
    assert first.name == "bad-name.pdf"
    assert second.name == "bad-name-2.pdf"
    assert first.read_bytes() == second.read_bytes() == b"one"


def test_attachment_copy_failure_leaves_no_final_file(tmp_path, monkeypatch):
    notes = tmp_path / "StormPad" / "Notes"
    source = tmp_path / "brief.pdf"
    source.write_bytes(b"pdf")

    def fail_copy(source, target):
        raise OSError("copy failed")

    monkeypatch.setattr(attachments.shutil, "copy2", fail_copy)
    with pytest.raises(StorageError):
        attachments.import_attachment(source, notes, NOTE_ID)
    directory = attachments.note_attachment_dir(notes, NOTE_ID)
    assert not directory.exists() or list(directory.iterdir()) == []


def test_resolve_rejects_path_outside_stable_id_directory(tmp_path):
    notes = tmp_path / "StormPad" / "Notes"
    note_path = notes / "renamed.md"
    managed = attachments.note_attachment_dir(notes, NOTE_ID) / "brief.pdf"
    managed.parent.mkdir(parents=True)
    managed.write_bytes(b"pdf")
    relative = attachments.relative_markdown_path(note_path, managed)
    assert attachments.resolve_managed_path(note_path, relative, notes, NOTE_ID) == managed
    assert attachments.resolve_managed_path(note_path, "../../secret", notes, NOTE_ID) is None


def test_record_orphan_does_not_delete_attachment(tmp_path):
    notes = tmp_path / "StormPad" / "Notes"
    managed = attachments.note_attachment_dir(notes, NOTE_ID) / "brief.pdf"
    managed.parent.mkdir(parents=True)
    managed.write_bytes(b"pdf")
    relative = f"../Attachments/{NOTE_ID}/brief.pdf"
    attachments.record_orphan(notes, NOTE_ID, relative)
    assert managed.exists()
    assert relative in (managed.parent / ".orphans.json").read_text(encoding="utf-8")
