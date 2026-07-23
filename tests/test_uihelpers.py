"""Tests for the AppKit-free UI helpers and controller-adjacent logic."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from stormpad import models
from stormpad.errors import NoteNotFoundError
from stormpad.models import Note
from stormpad.session import NoteStore
from stormpad.uihelpers import (
    AutosaveController,
    SaveStatus,
    choose_selected_note,
    default_new_category,
    format_relative,
    preview_text,
    word_count,
)

TZ = timezone(timedelta(hours=2))
NOW = datetime(2026, 7, 23, 14, 0, 0, tzinfo=TZ)


def make_note(idx=0, *, body="", category=models.IDEAS, minutes=0) -> Note:
    ts = NOW + timedelta(minutes=minutes)
    return Note(
        id=f"n{idx}",
        path=Path(f"n{idx}.md"),
        title=f"Note {idx}",
        body=body,
        category=category,
        created_at=ts,
        updated_at=ts,
    )


# -- preview / word count ------------------------------------------------------


def test_preview_collapses_whitespace():
    note = make_note(body="First line.\n\n  Second   line.\nThird.")
    assert preview_text(note) == "First line. Second line. Third."


def test_preview_truncates():
    note = make_note(body="word " * 60)
    out = preview_text(note, max_len=40)
    assert len(out) <= 41 and out.endswith("…")


def test_word_count():
    assert word_count("") == 0
    assert word_count("one two   three\nfour") == 4


# -- relative time -------------------------------------------------------------


def test_format_relative_today():
    dt = NOW - timedelta(hours=2)
    assert format_relative(dt, NOW).startswith("Today, ")


def test_format_relative_yesterday():
    assert format_relative(NOW - timedelta(days=1), NOW) == "Yesterday"


def test_format_relative_weekday_and_date():
    assert format_relative(NOW - timedelta(days=3), NOW) == (NOW - timedelta(days=3)).strftime("%a")
    older = NOW - timedelta(days=40)
    assert format_relative(older, NOW) == older.strftime("%b %-d")


# -- selection restoration -----------------------------------------------------


def test_choose_selected_note_prefers_saved():
    notes = [make_note(1, minutes=10), make_note(2, minutes=5)]
    assert choose_selected_note(notes, "n2").id == "n2"


def test_choose_selected_note_falls_back_to_newest():
    notes = [make_note(1, minutes=10), make_note(2, minutes=5)]
    assert choose_selected_note(notes, "missing").id == "n1"  # notes are newest-first


def test_choose_selected_note_empty():
    assert choose_selected_note([], "anything") is None


# -- default category ----------------------------------------------------------


@pytest.mark.parametrize(
    "current,expected",
    [
        (models.ALL_NOTES, models.IDEAS),
        (None, models.IDEAS),
        (models.SESSIONS, models.SESSIONS),
        (models.DRAFTS, models.DRAFTS),
        ("garbage", models.IDEAS),
    ],
)
def test_default_new_category(current, expected):
    assert default_new_category(current) == expected


# -- autosave coordinator ------------------------------------------------------


class FakeScheduler:
    def __init__(self):
        self.entries: list[list] = []  # [token, callback, active]

    def schedule(self, delay, callback):
        token = object()
        self.entries.append([token, callback, True])
        return token

    def cancel(self, token):
        for entry in self.entries:
            if entry[0] is token:
                entry[2] = False

    def fire_pending(self):
        for entry in reversed(self.entries):
            if entry[2]:
                entry[2] = False
                entry[1]()
                return


def make_autosave():
    sched = FakeScheduler()
    saves = []
    ctrl = AutosaveController(
        lambda: saves.append(1),
        delay=0.4,
        schedule=sched.schedule,
        cancel=sched.cancel,
    )
    return ctrl, sched, saves


def test_autosave_debounces_and_fires():
    ctrl, sched, saves = make_autosave()
    ctrl.note_edited()
    ctrl.note_edited()  # restarts timer; earlier one cancelled
    assert ctrl.has_pending
    assert sum(1 for e in sched.entries if e[2]) == 1  # only one active timer
    sched.fire_pending()
    assert saves == [1]
    assert not ctrl.has_pending


def test_autosave_flush_saves_immediately():
    ctrl, sched, saves = make_autosave()
    ctrl.note_edited()
    ctrl.flush()
    assert saves == [1]
    assert not ctrl.has_pending
    # Firing the (cancelled) timer must not double-save.
    sched.fire_pending()
    assert saves == [1]


def test_autosave_reset_discards_without_saving():
    ctrl, sched, saves = make_autosave()
    ctrl.note_edited()
    ctrl.reset()
    sched.fire_pending()
    assert saves == []
    assert not ctrl.has_pending


def test_autosave_flush_noop_when_clean():
    ctrl, _sched, saves = make_autosave()
    ctrl.flush()
    assert saves == []


# -- editor text -> model body (what the controller's save does) ---------------


def test_editor_edits_map_to_model_and_persist(tmp_path):
    store = NoteStore(tmp_path / "Notes")
    note = store.create_note("Draft", models.DRAFTS)
    # Simulate the controller applying editor content on autosave.
    now = models.now_local()
    note.set_title("Renamed in editor", now)
    note.set_body("Body typed\nin the editor.", now)
    store.save_note(note)

    reloaded = store.load_note(note.id)
    assert reloaded.title == "Renamed in editor"
    assert reloaded.body == "Body typed\nin the editor."
    assert reloaded.path == note.path  # filename stable


def test_deleted_selected_note_load_raises(tmp_path):
    store = NoteStore(tmp_path / "Notes")
    note = store.create_note("Temp")
    store.delete_note(note.id)
    with pytest.raises(NoteNotFoundError):
        store.load_note(note.id)


def test_save_status_values():
    assert SaveStatus.SAVED.value == "Saved locally"
    assert SaveStatus.SAVING.value == "Saving…"
    assert SaveStatus.FAILED.value == "Save failed"
