"""Targeted tests for inline Project rename and Project note filtering.

The inline (double-click) rename commits through the same store call as the
context-menu Rename Project, so these cover the behaviour that rename relies on:
identity is preserved, notes stay inside, empty names are rejected, and
duplicate names stay safe. Filtering/count tests back the Project note list.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from stormpad import models
from stormpad.errors import InvalidProjectError
from stormpad.models import UNFILED_PROJECT_ID
from stormpad.search import filter_by_project, search_notes
from stormpad.session import NoteStore
from stormpad.uihelpers import display_tag

TZ = timezone(timedelta(hours=2))


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 7, 24, 9, 0, 0, tzinfo=TZ)

    def __call__(self) -> datetime:
        return self.now

    def tick(self, seconds: int = 60) -> datetime:
        self.now = self.now + timedelta(seconds=seconds)
        return self.now


@pytest.fixture
def store(tmp_path) -> NoteStore:
    return NoteStore(tmp_path / "Notes", clock=FakeClock())


@pytest.fixture
def seeded(store):
    p1 = store.create_project("test1")
    p2 = store.create_project("other")
    a = store.create_note("Alpha", models.IDEAS)
    b = store.create_note("Beta", models.DRAFTS)
    c = store.create_note("Gamma", models.IDEAS)
    store.create_note("Loose", models.IDEAS)  # unfiled
    store.move_note_to_project(a.id, p1.id)
    store.move_note_to_project(b.id, p1.id)
    store.move_note_to_project(c.id, p2.id)
    return store, p1, p2


# -- inline rename -------------------------------------------------------------


def test_rename_keeps_project_id_and_notes(seeded):
    store, p1, _ = seeded
    renamed = store.rename_project(p1.id, "test1 renamed")
    assert renamed.id == p1.id  # UUID unchanged
    assert renamed.name == "test1 renamed"
    still_inside = [n.id for n in store.list_notes() if n.project_id == p1.id]
    assert len(still_inside) == 2  # notes remain inside the project


def test_rename_updates_visible_note_tags_immediately(seeded):
    store, p1, _ = seeded
    store.rename_project(p1.id, "test1 renamed")
    names = {p.id: p.name for p in store.list_projects()}
    filed = [n for n in store.list_notes() if n.project_id == p1.id]
    assert filed and all(display_tag(n, names) == "test1 renamed" for n in filed)


def test_empty_rename_is_rejected(seeded):
    store, p1, _ = seeded
    for candidate in ("", "   ", "\t"):
        with pytest.raises(InvalidProjectError):
            store.rename_project(p1.id, candidate)
    assert store.load_project(p1.id).name == "test1"


def test_rename_trims_whitespace(seeded):
    store, p1, _ = seeded
    assert store.rename_project(p1.id, "  spaced  ").name == "spaced"


def test_duplicate_name_is_handled_safely(seeded):
    """Renaming onto an existing name keeps both projects on distinct folders."""
    store, p1, p2 = seeded
    renamed = store.rename_project(p1.id, "other")
    assert renamed.id == p1.id
    assert renamed.path != store.load_project(p2.id).path
    assert renamed.path.exists()


def test_unsafe_filesystem_characters_are_sanitised(seeded):
    store, p1, _ = seeded
    renamed = store.rename_project(p1.id, "a/b:c*?name")
    assert renamed.name == "a/b:c*?name"  # display name preserved
    for bad in ("/", ":", "*", "?"):
        assert bad not in renamed.path.name  # folder name is safe
    assert renamed.path.exists()


# -- project filtering and counts ---------------------------------------------


def test_selecting_a_project_shows_only_its_notes(seeded):
    store, p1, _ = seeded
    notes = store.list_notes()
    filed = filter_by_project(notes, p1.id)
    assert sorted(n.title for n in filed) == ["Alpha", "Beta"]
    assert all(n.project_id == p1.id for n in filed)


def test_count_matches_visible_project_notes(seeded):
    store, p1, p2 = seeded
    notes = store.list_notes()
    assert len(filter_by_project(notes, p1.id)) == 2
    assert len(filter_by_project(notes, p2.id)) == 1


def test_all_notes_and_unfiled_still_work(seeded):
    store, _, _ = seeded
    notes = store.list_notes()
    assert len(filter_by_project(notes, None)) == 4
    unfiled = filter_by_project(notes, UNFILED_PROJECT_ID)
    assert [n.title for n in unfiled] == ["Loose"]


def test_new_note_created_in_project_appears_immediately(seeded):
    store, p1, _ = seeded
    fresh = store.create_note("Delta", models.IDEAS, project_id=p1.id)
    filed = filter_by_project(store.list_notes(), p1.id)
    assert fresh.id in [n.id for n in filed]
    assert len(filed) == 3


def test_note_moved_in_and_out_updates_both_lists(seeded):
    store, p1, p2 = seeded
    loose = next(n for n in store.list_notes() if n.title == "Loose")
    store.move_note_to_project(loose.id, p1.id)
    assert len(filter_by_project(store.list_notes(), p1.id)) == 3
    store.move_note_to_project(loose.id, p2.id)  # moved to another project
    assert len(filter_by_project(store.list_notes(), p1.id)) == 2
    assert len(filter_by_project(store.list_notes(), p2.id)) == 2
    store.move_note_to_project(loose.id, None)  # back to unfiled
    assert len(filter_by_project(store.list_notes(), p2.id)) == 1
    assert [n.title for n in filter_by_project(store.list_notes(), UNFILED_PROJECT_ID)] == ["Loose"]


def test_search_within_a_selected_project(seeded):
    store, p1, p2 = seeded
    notes = store.list_notes()
    # "a" matches notes across projects; scoping to p1 limits the results.
    scoped = search_notes(notes, "Alpha", project_id=p1.id)
    assert [r.note.title for r in scoped] == ["Alpha"]
    assert search_notes(notes, "Gamma", project_id=p1.id) == []
