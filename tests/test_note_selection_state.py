"""Focused UUID selection-state regressions for the native note list."""

from types import SimpleNamespace

from stormpad.views.note_list import (
    NoteList,
    note_selection_role,
    reconciled_note_selection,
)


def test_normal_click_replaces_the_previous_selection():
    class Table:
        deselected = False
        selected_row = None

        def deselectAll_(self, _sender):
            self.deselected = True

        def selectRowIndexes_byExtendingSelection_(self, indexes, extending):
            self.selected_row = int(indexes.firstIndex())
            assert extending is False

        def setNeedsDisplay_(self, _value):
            pass

    class Owner:
        _suppress = False
        _selected_ids = {"A", "B", "C"}
        _selected_id = "C"
        _selection_anchor_id = "A"
        _pending_clicked_row = 1
        _notes = [
            SimpleNamespace(id="A"),
            SimpleNamespace(id="B"),
            SimpleNamespace(id="C"),
        ]
        _table = Table()
        selected_callbacks = []

        def _on_select(self, note_id):
            self.selected_callbacks.append(note_id)

    owner = Owner()
    NoteList.prepare_normal_click(owner)
    assert owner._selected_ids == set()
    assert owner._table.deselected is True
    assert owner._suppress is False
    NoteList.commit_normal_click(owner, 1)
    assert owner._selected_ids == {"B"}
    assert owner._selected_id == "B"
    assert owner._selection_anchor_id == "B"
    assert note_selection_role("A", owner._selected_ids, "B") == "normal"
    assert note_selection_role("C", owner._selected_ids, "B") == "normal"


def test_shift_range_keeps_active_and_secondary_rows():
    selected = {"note-a", "note-b", "note-c"}
    assert note_selection_role("note-c", selected, "note-c") == "active"
    assert note_selection_role("note-a", selected, "note-c") == "secondary"
    assert note_selection_role("note-z", selected, "note-c") == "normal"


def test_scope_reconciliation_drops_hidden_selected_uuids():
    selected, active = reconciled_note_selection(
        {"note-b", "note-c"},
        {"note-a", "note-b", "hidden"},
        "note-b",
    )
    assert selected == {"note-b"}
    assert active == "note-b"


def test_scope_reconciliation_clears_hidden_active_note():
    selected, active = reconciled_note_selection(
        {"note-b"},
        {"note-a", "note-b"},
        "note-a",
    )
    assert selected == {"note-b"}
    assert active is None
