"""Targeted tests for the multi-select bulk-delete model.

Covers the confirmation copy (singular vs plural) and the "nearest surviving
note" selection that runs after a bulk delete. The AppKit table selection and
the safe-Trash deletion path are exercised at runtime; these lock the pure logic.
"""

from __future__ import annotations

from datetime import UTC, datetime

from stormpad.models import Note
from stormpad.uihelpers import delete_confirmation, select_after_bulk_delete

_NOW = datetime(2026, 7, 24, 9, 0, 0, tzinfo=UTC)


def _note(note_id: str) -> Note:
    return Note(
        id=note_id,
        path=None,  # unused by these helpers
        title=note_id,
        body="",
        category="Ideas",
        created_at=_NOW,
        updated_at=_NOW,
    )


def _displayed(*ids: str) -> list[Note]:
    return [_note(i) for i in ids]


# -- confirmation copy ---------------------------------------------------------


def test_single_note_keeps_the_singular_language():
    conf = delete_confirmation(1, single_title="My Note")
    assert conf.title == "Delete “My Note”?"
    assert conf.message == "This note will be moved to the Trash."
    assert conf.confirm_button == "Delete"
    assert conf.cancel_button == "Cancel"


def test_zero_selection_uses_the_singular_form():
    # Guard: an empty selection should never produce the plural dialog.
    assert delete_confirmation(0).confirm_button == "Delete"


def test_multiple_notes_use_the_exact_plural_copy():
    conf = delete_confirmation(3)
    assert conf.title == "Remove selected notes?"
    assert conf.message == (
        "Are you sure you want to remove these 3 notes? "
        "This action can be undone from the Trash."
    )
    assert conf.confirm_button == "Remove Notes"
    assert conf.cancel_button == "Cancel"


def test_plural_count_is_interpolated():
    assert "these 7 notes" in delete_confirmation(7).message


# -- nearest surviving note ----------------------------------------------------


def test_survivor_is_the_first_note_after_the_deleted_range():
    displayed = _displayed("A", "B", "C", "D", "E")
    assert select_after_bulk_delete(displayed, {"B", "C", "D"}) == "E"


def test_survivor_falls_back_to_the_note_before_when_tail_is_deleted():
    displayed = _displayed("A", "B", "C", "D", "E")
    assert select_after_bulk_delete(displayed, {"D", "E"}) == "C"


def test_survivor_skips_interior_deletions():
    displayed = _displayed("A", "B", "C", "D", "E")
    # Delete B and D: earliest removed is B (index 1); first survivor at/after is C.
    assert select_after_bulk_delete(displayed, {"B", "D"}) == "C"


def test_deleting_everything_yields_no_selection():
    displayed = _displayed("A", "B", "C")
    assert select_after_bulk_delete(displayed, {"A", "B", "C"}) is None


def test_deleting_nothing_keeps_the_first_note():
    displayed = _displayed("A", "B", "C")
    assert select_after_bulk_delete(displayed, set()) == "A"


def test_empty_list_is_safe():
    assert select_after_bulk_delete([], {"A"}) is None
