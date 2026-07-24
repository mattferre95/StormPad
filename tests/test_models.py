"""Tests for the Note model and domain helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import stormpad
from stormpad import models
from stormpad.errors import InvalidCategoryError, InvalidTimestampError
from stormpad.models import (
    Note,
    TranscriptBlock,
    format_transcript_timestamp,
    move_transcript_chunk,
    remove_transcript_chunk,
)

TZ = timezone(timedelta(hours=2))


def make_note(**overrides) -> Note:
    base = dict(
        id="2026-07-23-1430-idea",
        path=Path("2026-07-23-1430-idea.md"),
        title="Idea",
        body="",
        category=models.IDEAS,
        created_at=datetime(2026, 7, 23, 14, 30, tzinfo=TZ),
        updated_at=datetime(2026, 7, 23, 14, 30, tzinfo=TZ),
    )
    base.update(overrides)
    return Note(**base)


def test_package_metadata():
    assert stormpad.__version__ == "0.1.0"
    assert stormpad.__app_name__ == "StormPad"


def test_valid_note_creation():
    note = make_note(title="Hello", body="world")
    assert note.title == "Hello"
    assert note.body == "world"
    assert note.category == models.IDEAS
    assert note.transcript == []


def test_invalid_category_raises():
    with pytest.raises(InvalidCategoryError):
        make_note(category="Nonsense")


def test_validate_category():
    assert models.validate_category(models.DRAFTS) == models.DRAFTS
    with pytest.raises(InvalidCategoryError):
        models.validate_category("All Notes")  # a filter, not a category


def test_update_helpers_refresh_timestamp():
    note = make_note()
    later = note.updated_at + timedelta(minutes=5)
    note.set_body("new body", later)
    assert note.body == "new body"
    assert note.updated_at == later

    later2 = later + timedelta(minutes=1)
    note.set_title("New title", later2)
    assert note.title == "New title"
    assert note.updated_at == later2


def test_set_category_validates():
    note = make_note()
    with pytest.raises(InvalidCategoryError):
        note.set_category("Bogus", note.updated_at)
    note.set_category(models.SESSIONS, note.updated_at)
    assert note.category == models.SESSIONS


def test_add_transcript_block():
    note = make_note()
    later = note.updated_at + timedelta(seconds=10)
    note.add_transcript_block(TranscriptBlock("00:00:04", "hi"), later)
    assert len(note.transcript) == 1
    assert note.updated_at == later


def test_transcript_chunk_remove_and_reorder():
    chunks = [
        TranscriptBlock("00:00:01", "one"),
        TranscriptBlock("00:00:02", "two"),
        TranscriptBlock("00:00:03", "three"),
    ]
    moved, destination = move_transcript_chunk(chunks, 0, 2)
    assert destination == 2
    assert [chunk.text for chunk in moved] == ["two", "three", "one"]
    assert [chunk.text for chunk in chunks] == ["one", "two", "three"]
    assert [chunk.text for chunk in remove_transcript_chunk(moved, 1)] == [
        "two",
        "one",
    ]


@pytest.mark.parametrize(
    "value,expected",
    [
        (4, "00:00:04"),
        (0, "00:00:00"),
        (3661, "01:01:01"),
        (75, "00:01:15"),
        ("4", "00:00:04"),
        ("00:04", "00:00:04"),
        ("1:02:03", "01:02:03"),
        ("[00:00:11]", "00:00:11"),
        (4.9, "00:00:04"),
    ],
)
def test_format_transcript_timestamp_valid(value, expected):
    assert format_transcript_timestamp(value) == expected


@pytest.mark.parametrize("value", [-1, "abc", "99:99", True, None])
def test_format_transcript_timestamp_invalid(value):
    with pytest.raises(InvalidTimestampError):
        format_transcript_timestamp(value)
