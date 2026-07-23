"""Tests for the AppKit-free UI helpers and controller-adjacent logic."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from stormpad import models
from stormpad.errors import NoteNotFoundError
from stormpad.models import Note, TranscriptBlock
from stormpad.session import NoteStore
from stormpad.uihelpers import (
    AutosaveController,
    SaveStatus,
    add_block_menu_mode,
    choose_selected_note,
    copy_text,
    default_new_category,
    format_relative,
    formatting_toolbar_visible,
    is_speakable,
    next_selection_after_delete,
    note_row_is_selected,
    preview_text,
    title_command_focus,
    title_display_text,
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


def test_preview_hides_markdown_formatting():
    note = make_note(body="## Direction\n\nA **bold** <u>thought</u>.")
    assert preview_text(note) == "Direction A bold thought."


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
    assert reloaded.path == note.path


def test_selected_note_preference_survives_filename_rename(tmp_path):
    store = NoteStore(tmp_path / "Notes")
    note = store.create_note("Before")
    stable_id = note.id
    renamed = store.update_title(stable_id, "After")
    assert renamed.path.name == "after.md"
    assert choose_selected_note(store.list_notes(), stable_id).id == stable_id


def test_deleted_selected_note_load_raises(tmp_path):
    store = NoteStore(tmp_path / "Notes")
    note = store.create_note("Temp")
    store.delete_note(note.id)
    with pytest.raises(NoteNotFoundError):
        store.load_note(note.id)


def test_external_file_deletion_detected(tmp_path):
    """A note file removed outside StormPad is detected, not resurrected on read."""
    store = NoteStore(tmp_path / "Notes")
    note = store.create_note("Gone soon")
    note.path.unlink()  # deleted in Finder / another app
    with pytest.raises(NoteNotFoundError):
        store.load_note(note.id)
    assert note.id not in [n.id for n in store.list_notes()]


def test_save_status_values():
    assert SaveStatus.SAVED.value == "Saved locally"
    assert SaveStatus.SAVING.value == "Saving…"
    assert SaveStatus.FAILED.value == "Save failed"


# -- Phase 5.1 UI states ------------------------------------------------------


def test_selected_row_state():
    assert note_row_is_selected("n1", "n1") is True
    assert note_row_is_selected("n1", "n2") is False


def test_blank_title_and_title_body_transition():
    note = make_note()
    note.title = "Untitled Note"
    assert title_display_text(note) == ""
    note.body = "has content"
    assert title_display_text(note) == "Untitled Note"
    assert title_command_focus("insertNewline:") == "body"
    assert title_command_focus("moveUp:") == "title"


def test_add_block_menu_state():
    assert add_block_menu_mode(current_empty=True, option_pressed=False) == "convert"
    assert add_block_menu_mode(current_empty=False, option_pressed=False) == "below"
    assert add_block_menu_mode(current_empty=False, option_pressed=True) == "above"


def test_formatting_toolbar_state():
    assert formatting_toolbar_visible(selection_length=4, editor_focused=True)
    assert not formatting_toolbar_visible(selection_length=0, editor_focused=True)
    assert not formatting_toolbar_visible(selection_length=4, editor_focused=False)


# -- copy formatting -----------------------------------------------------------


def test_copy_text_title_body_transcript():
    note = make_note(1, body="Line one.\nLine two.")
    note.transcript = [TranscriptBlock("00:00:04", "spoken chunk")]
    out = copy_text(note)
    assert "Note 1" in out
    assert "Line one.\nLine two." in out
    assert "[00:00:04]\nspoken chunk" in out
    assert "Transcript" in out
    # No internal metadata leaks.
    for leak in ("Created:", "Updated:", "Category:", "n1.md", "## Notes"):
        assert leak not in out


def test_copy_text_empty_body_and_no_transcript():
    note = make_note(2, body="")
    out = copy_text(note)
    assert out.strip() == "Note 2"
    assert "Transcript" not in out


def test_copy_text_unicode():
    note = make_note(3, body="naïve façade — 東京")
    note.title = "Café résumé"
    out = copy_text(note)
    assert "Café résumé" in out
    assert "naïve façade — 東京" in out


# -- next selection after delete ----------------------------------------------


def test_next_selection_after_delete_picks_newest_remaining():
    displayed = [make_note(1, minutes=10), make_note(2, minutes=5), make_note(3, minutes=1)]
    assert next_selection_after_delete(displayed, "n1") == "n2"  # newest remaining
    assert next_selection_after_delete(displayed, "n2") == "n1"


def test_next_selection_after_delete_last_note():
    displayed = [make_note(1)]
    assert next_selection_after_delete(displayed, "n1") is None


# -- speech validation ---------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("hello", True),
        ("  hi  ", True),
        ("", False),
        ("   ", False),
        ("\n\t", False),
        (None, False),
    ],
)
def test_is_speakable(text, expected):
    assert is_speakable(text) is expected
