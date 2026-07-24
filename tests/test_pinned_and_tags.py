"""Targeted tests for pinned notes and note-row display tags.

Covers only the behavior added in this pass: pinned preference state, pinned
filtering across projects/Unfiled, stale pinned-UUID handling, and Project vs
Category tag selection.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from stormpad import models
from stormpad.models import Note
from stormpad.preferences import InMemoryBackend, Preferences
from stormpad.search import filter_by_pinned, prune_pinned_ids
from stormpad.uihelpers import display_tag

TZ = timezone(timedelta(hours=2))
BASE = datetime(2026, 7, 24, 10, 0, 0, tzinfo=TZ)


def note(note_id: str, *, category=models.IDEAS, project_id=None, minutes=0) -> Note:
    ts = BASE + timedelta(minutes=minutes)
    return Note(
        id=note_id,
        path=Path(f"{note_id}.md"),
        title=f"Note {note_id}",
        body="",
        category=category,
        created_at=ts,
        updated_at=ts,
        transcript=[],
        project_id=project_id,
    )


# -- pinned preference state ---------------------------------------------------


def test_pinned_defaults_to_empty():
    assert Preferences().pinned_note_ids == []


def test_pinned_ids_persist_through_backend():
    backend = InMemoryBackend()
    Preferences(backend).pinned_note_ids = ["uuid-a", "uuid-b"]
    # A fresh facade over the same backend (i.e. after relaunch) sees them.
    assert Preferences(backend).pinned_note_ids == ["uuid-a", "uuid-b"]


def test_pinned_ids_are_deduped_and_drop_empties():
    backend = InMemoryBackend()
    Preferences(backend).pinned_note_ids = ["a", "b", "a", "", "b"]
    assert Preferences(backend).pinned_note_ids == ["a", "b"]


def test_invalid_pinned_payload_falls_back_to_empty():
    assert Preferences(InMemoryBackend({"pinned_note_ids": "not-json"})).pinned_note_ids == []
    assert Preferences(InMemoryBackend({"pinned_note_ids": '{"a": 1}'})).pinned_note_ids == []
    assert Preferences(InMemoryBackend({"pinned_note_ids": '["ok", 5, null]'})).pinned_note_ids == [
        "ok"
    ]


# -- pinned filtering ----------------------------------------------------------


def test_filter_by_pinned_spans_projects_and_unfiled():
    notes = [
        note("a", project_id="build"),
        note("b", project_id=None),
        note("c", project_id="stormpad"),
    ]
    # Pinned notes come from a project and from Unfiled alike.
    assert [n.id for n in filter_by_pinned(notes, ["a", "b"])] == ["a", "b"]


def test_filter_by_pinned_preserves_list_order_not_pin_order():
    notes = [note("a"), note("b"), note("c")]
    assert [n.id for n in filter_by_pinned(notes, ["c", "a"])] == ["a", "c"]


def test_filter_by_pinned_empty_and_unknown_ids():
    notes = [note("a"), note("b")]
    assert filter_by_pinned(notes, []) == []
    assert filter_by_pinned(notes, None) == []
    assert filter_by_pinned(notes, ["missing"]) == []


def test_pinned_state_survives_moving_between_project_and_unfiled():
    """Pin state keys off the stable UUID, so moving a note keeps it pinned."""
    filed = note("a", project_id="build")
    assert [n.id for n in filter_by_pinned([filed], ["a"])] == ["a"]
    filed.project_id = None  # moved back to Unfiled; id unchanged
    assert [n.id for n in filter_by_pinned([filed], ["a"])] == ["a"]


# -- stale pinned UUID handling ------------------------------------------------


def test_prune_pinned_ids_drops_deleted_notes():
    assert prune_pinned_ids(["a", "b", "c"], ["a", "c"]) == ["a", "c"]


def test_prune_pinned_ids_preserves_pin_order_and_dedupes():
    assert prune_pinned_ids(["c", "a", "c"], ["a", "b", "c"]) == ["c", "a"]


def test_prune_pinned_ids_edge_cases():
    assert prune_pinned_ids([], ["a"]) == []
    assert prune_pinned_ids(["a"], []) == []
    assert prune_pinned_ids(None, None) == []


# -- note-row display tag ------------------------------------------------------


def test_project_note_shows_project_name_not_category():
    filed = note("a", category=models.IDEAS, project_id="p1")
    assert display_tag(filed, {"p1": "Build"}) == "Build"


def test_unfiled_note_shows_its_category():
    for category in (models.IDEAS, models.DRAFTS, models.SESSIONS):
        assert display_tag(note("a", category=category), {"p1": "Build"}) == category


def test_renamed_project_updates_tag_immediately():
    filed = note("a", project_id="p1")
    assert display_tag(filed, {"p1": "Build"}) == "Build"
    assert display_tag(filed, {"p1": "Build v2"}) == "Build v2"


def test_moving_note_between_project_and_unfiled_switches_tag():
    n = note("a", category=models.DRAFTS, project_id=None)
    assert display_tag(n, {"p1": "Build"}) == models.DRAFTS
    n.project_id = "p1"
    assert display_tag(n, {"p1": "Build"}) == "Build"
    n.project_id = None
    assert display_tag(n, {"p1": "Build"}) == models.DRAFTS


def test_unknown_project_falls_back_to_category():
    filed = note("a", category=models.SESSIONS, project_id="gone")
    assert display_tag(filed, {"p1": "Build"}) == models.SESSIONS
    assert display_tag(filed, None) == models.SESSIONS
