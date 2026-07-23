"""Tests for headless search and category filtering."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from stormpad import models, search
from stormpad.errors import InvalidCategoryError
from stormpad.models import Note, TranscriptBlock

TZ = timezone(timedelta(hours=2))
BASE = datetime(2026, 7, 23, 14, 30, 0, tzinfo=TZ)


def note(
    idx: int,
    *,
    title="",
    body="",
    category=models.IDEAS,
    transcript=None,
    minutes=0,
    project_id=None,
):
    ts = BASE + timedelta(minutes=minutes)
    return Note(
        id=f"n{idx}",
        path=Path(f"n{idx}.md"),
        title=title,
        body=body,
        category=category,
        created_at=ts,
        updated_at=ts,
        transcript=transcript or [],
        project_id=project_id,
    )


@pytest.fixture
def notes():
    return [
        note(1, title="Voice session notes", body="local first", minutes=30),
        note(2, title="Client brainstorm", body="hero and voice-over ideas", minutes=20),
        note(
            3,
            title="Random",
            body="nothing here",
            category=models.DRAFTS,
            transcript=[TranscriptBlock("00:00:04", "spoken voice chunk")],
            minutes=10,
        ),
        note(4, title="Café résumé", body="naïve façade", category=models.SESSIONS, minutes=5),
    ]


def test_title_match(notes):
    results = search.search_notes(notes, "session")
    assert [r.note.id for r in results] == ["n1"]
    assert results[0].matches[0].field == search.FIELD_TITLE


def test_body_match(notes):
    results = search.search_notes(notes, "hero")
    assert [r.note.id for r in results] == ["n2"]
    assert results[0].matches[0].field == search.FIELD_BODY


def test_transcript_match(notes):
    results = search.search_notes(notes, "chunk")
    assert [r.note.id for r in results] == ["n3"]
    assert results[0].matches[0].field == search.FIELD_TRANSCRIPT


def test_case_insensitive(notes):
    upper = search.search_notes(notes, "VOICE")
    lower = search.search_notes(notes, "voice")
    assert {r.note.id for r in upper} == {r.note.id for r in lower} == {"n1", "n2", "n3"}


def test_unicode_match(notes):
    results = search.search_notes(notes, "café")
    assert [r.note.id for r in results] == ["n4"]
    # Case-insensitive across accented letters.
    assert [r.note.id for r in search.search_notes(notes, "CAFÉ")] == ["n4"]


def test_match_spans_are_valid_indices(notes):
    result = search.search_notes(notes, "voice")[0]
    for m in result.matches:
        text = {
            search.FIELD_TITLE: result.note.title,
            search.FIELD_BODY: result.note.body,
            search.FIELD_TRANSCRIPT: search.transcript_text(result.note),
        }[m.field]
        assert text[m.start : m.end].lower() == "voice"


def test_empty_query_returns_all_sorted(notes):
    results = search.search_notes(notes, "   ")
    # Most recently updated first: n1(30) > n2(20) > n3(10) > n4(5).
    assert [r.note.id for r in results] == ["n1", "n2", "n3", "n4"]
    assert all(r.match_count == 0 for r in results)


def test_no_results(notes):
    assert search.search_notes(notes, "zzzznotfound") == []


def test_results_sorted_by_updated(notes):
    results = search.search_notes(notes, "voice")
    # n1(30), n2(20), n3(10) all match; ordered by updated desc.
    assert [r.note.id for r in results] == ["n1", "n2", "n3"]


def test_category_filter(notes):
    results = search.search_notes(notes, "", category=models.DRAFTS)
    assert [r.note.id for r in results] == ["n3"]


def test_category_filter_with_query(notes):
    # "voice" matches n1,n2,n3 but only n3 is a Draft.
    results = search.search_notes(notes, "voice", category=models.DRAFTS)
    assert [r.note.id for r in results] == ["n3"]


def test_all_notes_and_none_do_not_filter(notes):
    assert len(search.search_notes(notes, "", category=models.ALL_NOTES)) == 4
    assert len(search.search_notes(notes, "", category=None)) == 4


def test_filter_by_category_invalid(notes):
    with pytest.raises(InvalidCategoryError):
        search.filter_by_category(notes, "Bogus")


def test_all_notes_unfiled_and_project_filters(notes):
    notes[0].project_id = "build"
    notes[1].project_id = "stormpad"
    assert [item.id for item in search.filter_by_project(notes, None)] == [
        "n1",
        "n2",
        "n3",
        "n4",
    ]
    assert [item.id for item in search.filter_by_project(notes, "build")] == ["n1"]
    assert [item.id for item in search.filter_by_project(notes, models.UNFILED_PROJECT_ID)] == [
        "n3",
        "n4",
    ]


def test_search_across_projects_and_with_project_filter(notes):
    notes[0].project_id = "build"
    notes[1].project_id = "stormpad"
    assert [result.note.id for result in search.search_notes(notes, "voice")] == [
        "n1",
        "n2",
        "n3",
    ]
    assert [
        result.note.id for result in search.search_notes(notes, "voice", project_id="build")
    ] == ["n1"]
