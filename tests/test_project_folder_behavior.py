"""Targeted tests for project-as-folder behaviour and the sidebar row icon.

Filtering, counts, and note movement are covered in
``test_project_rename_and_filter.py``. This file locks the two remaining
folder-behaviour contracts — an empty project shows nothing (never another
scope's notes) and the open note is reconciled when the scope changes — plus the
fixed, non-clipping geometry of the project row icon container.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from stormpad import models
from stormpad.search import filter_by_project
from stormpad.session import NoteStore
from stormpad.uihelpers import choose_selected_note


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 7, 24, 9, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def tick(self, seconds: int = 60) -> datetime:
        self.now = self.now + timedelta(seconds=seconds)
        return self.now


@pytest.fixture
def seeded(tmp_path):
    store = NoteStore(tmp_path / "Notes", clock=FakeClock())
    work = store.create_project("Work")
    personal = store.create_project("Personal")
    empty = store.create_project("Empty")
    store.create_note("Work A", models.IDEAS, project_id=work.id)
    store.create_note("Work B", models.DRAFTS, project_id=work.id)
    store.create_note("Personal One", models.IDEAS, project_id=personal.id)
    store.create_note("Loose", models.IDEAS)
    return store, work, personal, empty


# -- folder filtering ----------------------------------------------------------


def test_project_shows_only_its_own_notes(seeded):
    store, work, personal, _ = seeded
    notes = store.list_notes()
    work_notes = filter_by_project(notes, work.id)
    assert sorted(n.title for n in work_notes) == ["Work A", "Work B"]
    # No note from any other project or from Unfiled leaks in.
    assert all(n.project_id == work.id for n in work_notes)
    assert not any(n.title == "Personal One" for n in work_notes)
    assert not any(n.title == "Loose" for n in work_notes)


def test_switching_projects_refreshes_the_visible_set(seeded):
    store, work, personal, _ = seeded
    notes = store.list_notes()
    first = {n.title for n in filter_by_project(notes, work.id)}
    second = {n.title for n in filter_by_project(notes, personal.id)}
    assert first == {"Work A", "Work B"}
    assert second == {"Personal One"}
    assert first.isdisjoint(second)  # switching genuinely changes the set


def test_empty_project_shows_no_notes(seeded):
    store, _, _, empty = seeded
    assert filter_by_project(store.list_notes(), empty.id) == []


# -- selection reconciliation --------------------------------------------------


def test_open_note_from_another_project_is_replaced_by_the_first_in_scope(seeded):
    store, work, personal, _ = seeded
    notes = store.list_notes()
    open_note = next(n for n in notes if n.title == "Personal One")
    work_notes = filter_by_project(notes, work.id)
    # The open note is not in Work, so selection falls to Work's first note.
    reconciled = choose_selected_note(work_notes, open_note.id)
    assert reconciled is not None
    assert reconciled.project_id == work.id


def test_open_note_still_in_scope_is_kept(seeded):
    store, work, _, _ = seeded
    work_notes = filter_by_project(store.list_notes(), work.id)
    keep = work_notes[0]
    assert choose_selected_note(work_notes, keep.id).id == keep.id


def test_empty_project_clears_the_selection(seeded):
    store, work, _, empty = seeded
    open_note = filter_by_project(store.list_notes(), work.id)[0]
    empty_notes = filter_by_project(store.list_notes(), empty.id)
    # Nothing to select in an empty project -> caller clears the editor.
    assert choose_selected_note(empty_notes, open_note.id) is None


# -- sidebar row icon geometry -------------------------------------------------


def test_row_icon_container_is_fixed_and_vertically_centred():
    from stormpad.views import sidebar

    box = sidebar._ROW_ICON_BOX
    row_height = 34.0  # the fixed sidebar row height
    # A fixed, square container so geometry never changes with icon type/state.
    assert box.size.width == box.size.height == 24.0
    # Vertically centred in the row.
    assert box.origin.y + box.size.height / 2 == row_height / 2


def test_row_label_clears_the_icon_with_clean_spacing():
    from stormpad.views import sidebar

    box = sidebar._ROW_ICON_BOX
    gap = sidebar._ROW_LABEL_X - (box.origin.x + box.size.width)
    assert gap >= 6.0  # icon and name never touch


def test_symbol_point_size_fits_within_the_container():
    from stormpad.views import sidebar

    # Rendering at a point size below the box lets proportional scaling fit the
    # glyph without an aggressive upscale — full visibility, preserved aspect.
    assert sidebar._ROW_SYMBOL_POINT <= sidebar._ROW_ICON_BOX.size.width
    assert sidebar._ROW_EMOJI_POINT < sidebar._ROW_ICON_BOX.size.height


def test_navigation_signature_tracks_active_project_children_only(seeded):
    from stormpad.views.sidebar import Sidebar

    store, work, personal, _ = seeded
    projects = store.list_projects()
    notes = store.list_notes()
    signature = Sidebar._navigation_signature(
        None, projects, notes, work.id, False
    )
    child_ids = {item[0] for item in signature[2]}
    assert child_ids == {
        note.id for note in notes if note.project_id == work.id
    }
    assert not any(
        note.id in child_ids for note in notes if note.project_id == personal.id
    )


def test_repeated_project_click_toggles_only_expansion():
    from stormpad.views.sidebar import toggled_project_expansion

    project_id = "project-uuid"
    assert toggled_project_expansion(None, None, project_id) == project_id
    assert toggled_project_expansion(project_id, project_id, project_id) is None
    assert toggled_project_expansion(project_id, None, project_id) == project_id
    assert toggled_project_expansion(project_id, project_id, "other") == "other"


def test_project_row_hit_testing_separates_icon_name_and_actions():
    from stormpad.views.sidebar import project_row_hit_region

    assert project_row_hit_region(18, 17) == "icon"
    assert project_row_hit_region(60, 17) == "name"
    assert project_row_hit_region(160, 17) == "write"
    assert project_row_hit_region(190, 17) == "ellipsis"
    assert project_row_hit_region(140, 17) == "row"


def test_double_clicking_project_icon_opens_picker_for_exact_project():
    from stormpad.views.sidebar import SidebarRow

    opened = []
    selected = []

    class Target:
        def chooseProjectIcon_(self, sender):
            opened.append(sender.key)

    class Event:
        def clickCount(self):
            return 2

        def locationInWindow(self):
            return (18, 17)

    class Row:
        key = "project-exact"
        _renaming = False
        _drag_started = False
        drag_kind = "project"
        on_select = selected.append
        action_target = Target()
        _mouse_down_point = (18, 17)

        def _cancel_single_click(self):
            self.cancelled = True

        def convertPoint_fromView_(self, point, _view):
            return type("Point", (), {"x": point[0], "y": point[1]})()

        def begin_inline_rename(self):
            raise AssertionError("icon double-click must not rename")

    row = Row()
    SidebarRow.mouseUp_.callable(row, Event())
    assert opened == ["project-exact"]
    assert selected == []
    assert row.cancelled is True


def test_nested_note_selection_repaints_exactly_one_active_child():
    from stormpad.views.sidebar import Sidebar

    class ChildRow:
        def __init__(self):
            self.states = []

        def set_child_selected(self, selected, _palette):
            self.states.append(bool(selected))

    class ProjectRow:
        def set_selected(self, selected, _palette):
            self.selected = bool(selected)

    child_a = ChildRow()
    child_b = ChildRow()
    project = ProjectRow()
    sidebar = type(
        "SidebarState",
        (),
        {
            "_rows": {"project": project, "A": child_a, "B": child_b},
            "_note_rows": {"A": child_a, "B": child_b},
            "_active_note_id": "A",
            "_active_project_id": "project",
            "_active_category": "All Notes",
            "palette": object(),
        },
    )()

    Sidebar._apply_selection(sidebar)
    sidebar._active_note_id = "B"
    Sidebar._apply_selection(sidebar)

    assert child_a.states == [True, False]
    assert child_b.states == [False, True]
    assert sum((child_a.states[-1], child_b.states[-1])) == 1


def test_project_write_target_and_creation_use_exact_project(seeded):
    from stormpad.window import MainController

    store, work, personal, _ = seeded

    class Autosave:
        def flush(self):
            pass

    class Prefs:
        last_category = None
        selected_project_id = None

    class Sender:
        def representedObject(self):
            return personal.id

    class Controller:
        _autosave = Autosave()
        _prefs = Prefs()
        _represented_string = MainController._represented_string

        def newNote_(self, _sender):
            self.created_project_id = self._project_id

    controller = Controller()
    sender = Sender()
    MainController.newNoteInProject_.callable(controller, sender)
    created = store.create_note(
        "Untitled Note",
        models.IDEAS,
        project_id=controller.created_project_id,
    )
    assert created.project_id == personal.id
    assert created.project_id != work.id
    assert controller._expanded_project_id == personal.id


def test_native_glass_lookup_has_safe_fallback():
    from stormpad.window import native_glass_effect_class

    sentinel = object()
    assert native_glass_effect_class(lambda _name: sentinel) is sentinel

    def unavailable(_name):
        raise LookupError

    assert native_glass_effect_class(unavailable) is None
