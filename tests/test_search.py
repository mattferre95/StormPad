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
    # Relevance tiers happen to agree with recency here: title, body, transcript.
    assert [r.note.id for r in results] == ["n1", "n2", "n3"]


def test_relevance_ranks_exact_prefix_title_body_then_transcript():
    ranked = [
        note(1, title="Storm", body="", minutes=1),
        note(2, title="Storm planning", body="", minutes=5),
        note(3, title="A storm note", body="", minutes=10),
        note(4, title="Body", body="storm details", minutes=20),
        note(
            5,
            title="Transcript",
            transcript=[TranscriptBlock("00:00:01", "storm recording")],
            minutes=30,
        ),
    ]
    results = search.search_notes(ranked, "storm")
    assert [result.note.id for result in results] == ["n1", "n2", "n3", "n4", "n5"]
    assert [result.score for result in results] == sorted(
        (result.score for result in results),
        reverse=True,
    )


def test_recency_breaks_ties_within_same_relevance_tier():
    tied = [
        note(1, title="One", body="shared phrase", minutes=1),
        note(2, title="Two", body="shared phrase", minutes=10),
    ]
    assert [result.note.id for result in search.search_notes(tied, "shared")] == [
        "n2",
        "n1",
    ]


def test_matching_body_and_transcript_snippets_show_local_context():
    long_body = "begin " + ("filler " * 30) + "needle body context " + ("tail " * 20)
    body_result = search.search_notes(
        [note(1, title="Body", body=long_body)],
        "needle",
    )[0]
    assert body_result.snippet_field == search.FIELD_BODY
    assert "needle body context" in body_result.snippet
    assert body_result.snippet.startswith("…")
    assert body_result.snippet.endswith("…")

    transcript_result = search.search_notes(
        [
            note(
                2,
                title="Audio",
                transcript=[
                    TranscriptBlock("00:00:01", "opening"),
                    TranscriptBlock("00:00:03", "needle spoken context"),
                ],
            )
        ],
        "needle",
    )[0]
    assert transcript_result.snippet_field == search.FIELD_TRANSCRIPT
    assert "needle spoken context" in transcript_result.snippet


def test_title_match_uses_readable_body_preview_when_available():
    result = search.search_notes(
        [note(1, title="Needle plan", body="The useful plan summary")],
        "needle",
    )[0]
    assert result.snippet_field == search.FIELD_BODY
    assert result.snippet == "The useful plan summary"


def test_live_editor_overlay_is_searchable_without_mutating_persisted_note():
    saved = note(1, title="Saved", body="old body")
    overlaid = search.notes_with_live_text(
        [saved],
        saved.id,
        title="Unsaved title",
        body="live needle text",
    )
    assert search.search_notes(overlaid, "needle")[0].note.id == saved.id
    assert saved.title == "Saved"
    assert saved.body == "old body"


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


def test_global_search_includes_unfiled_and_nested_project_children():
    project_child = note(
        1,
        title="Project child",
        body="global needle",
        project_id="build",
    )
    other_child = note(
        2,
        title="Other child",
        body="global needle",
        project_id="stormpad",
    )
    unfiled = note(3, title="Root", body="global needle", project_id=None)
    results = search.search_notes([project_child, other_child, unfiled], "needle")
    assert {result.note.id for result in results} == {"n1", "n2", "n3"}
    assert {result.note.project_id for result in results} == {
        "build",
        "stormpad",
        None,
    }
