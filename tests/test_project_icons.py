"""Targeted tests for optional Project icons.

Covers the icon vocabulary, safe fallback for invalid/unavailable values, and
persistence — including that an icon survives a rename, survives a reload from
disk, and never affects a project's identity or its notes.
"""

from __future__ import annotations

import pytest

from stormpad import models, storage
from stormpad.icons import (
    DEFAULT_PROJECT_SYMBOL,
    PROJECT_SYMBOLS,
    SUGGESTED_EMOJI,
    emoji_icon,
    is_supported_emoji,
    normalize_project_icon,
    project_icon_kind,
    project_icon_payload,
    symbol_icon,
)
from stormpad.session import NoteStore
from stormpad.views.icon_picker import (
    CLEAR_IDENTIFIER,
    CUSTOM_EMOJI_IDENTIFIER,
    icon_picker_click_behavior,
    picker_selected_identifier,
    picker_selection_flags,
)


@pytest.fixture
def store(tmp_path) -> NoteStore:
    return NoteStore(tmp_path / "Notes")


# -- vocabulary ----------------------------------------------------------------


def test_curated_symbols_cover_the_requested_set():
    for name in ("folder", "bolt", "lightbulb", "briefcase", "camera", "waveform"):
        assert name in PROJECT_SYMBOLS


def test_default_is_the_folder():
    assert PROJECT_SYMBOLS[0] == DEFAULT_PROJECT_SYMBOL
    assert project_icon_kind(None) == "default"
    assert project_icon_payload(None) == DEFAULT_PROJECT_SYMBOL


def test_symbols_and_emoji_normalise_to_canonical_values():
    assert symbol_icon("bolt") == "symbol:bolt"
    assert normalize_project_icon("bolt") == "symbol:bolt"  # bare name accepted
    assert emoji_icon("🚀") == "emoji:🚀"
    assert normalize_project_icon("🚀") == "emoji:🚀"  # bare emoji accepted
    assert project_icon_kind("symbol:bolt") == "symbol"
    assert project_icon_kind("emoji:🚀") == "emoji"
    assert project_icon_payload("emoji:🚀") == "🚀"


def test_every_suggested_emoji_is_accepted():
    for glyph in SUGGESTED_EMOJI:
        assert emoji_icon(glyph) == f"emoji:{glyph}"


# -- invalid icons fall back safely --------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
        "symbol:definitely.not.a.real.symbol",  # unavailable SF Symbol
        "symbol:",
        "emoji:",
        "emoji:hello",  # a word, not an emoji
        "Work",
        "/etc/passwd",
        "🚀🚀🚀🚀🚀🚀🚀🚀🚀",  # more than one icon
        123,
        object(),
    ],
)
def test_invalid_icons_normalise_to_the_default_folder(value):
    assert normalize_project_icon(value) is None
    assert project_icon_kind(value) == "default"
    assert project_icon_payload(value) == DEFAULT_PROJECT_SYMBOL


def test_picker_selects_default_for_none_and_invalid_values():
    assert picker_selected_identifier(None) == CLEAR_IDENTIFIER
    assert picker_selected_identifier("symbol:not-real") == CLEAR_IDENTIFIER


def test_picker_restores_persisted_symbol_and_suggested_emoji():
    assert picker_selected_identifier("symbol:bolt") == "symbol:bolt"
    assert picker_selected_identifier("emoji:🚀") == "emoji:🚀"


def test_picker_marks_custom_persisted_emoji_choice():
    assert picker_selected_identifier("emoji:🫠") == CUSTOM_EMOJI_IDENTIFIER


def test_picker_immediate_state_update_selects_only_clicked_identifier():
    identifiers = ("symbol:bolt", "emoji:🚀", CLEAR_IDENTIFIER)
    assert picker_selection_flags(identifiers, "emoji:🚀") == (
        False,
        True,
        False,
    )


def test_picker_single_click_dispatches_and_stays_open():
    assert icon_picker_click_behavior(1, False) == (True, False)


def test_picker_double_click_closes_without_second_dispatch():
    assert icon_picker_click_behavior(2, True) == (False, True)


def test_picker_double_click_dispatches_if_first_action_was_not_delivered():
    assert icon_picker_click_behavior(2, False) == (True, True)


def test_only_curated_symbols_are_accepted():
    """An uncurated symbol name is not stored, so a row cannot render blank."""
    assert normalize_project_icon("symbol:trash.slash.circle.fill") is None


def test_emoji_validation_rejects_text_and_accepts_clusters():
    assert is_supported_emoji("⭐")
    assert is_supported_emoji("👨‍👩‍👧‍👦")  # ZWJ sequence is one icon
    assert not is_supported_emoji("A")
    assert not is_supported_emoji("A⭐")
    assert not is_supported_emoji("")


# -- persistence ---------------------------------------------------------------


def test_icon_persists_across_a_reload(store):
    project = store.create_project("Work")
    store.set_project_icon(project.id, "symbol:briefcase")
    # A fresh store re-reads the metadata from disk, exactly like a relaunch.
    reloaded = NoteStore(store.notes_dir).load_project(project.id)
    assert reloaded.icon == "symbol:briefcase"


def test_emoji_icon_persists_across_a_reload(store):
    project = store.create_project("Music")
    store.set_project_icon(project.id, "🎵")
    assert NoteStore(store.notes_dir).load_project(project.id).icon == "emoji:🎵"


def test_setting_an_icon_keeps_identity_notes_and_folder(store):
    project = store.create_project("Work")
    note = store.create_note("Alpha", models.IDEAS, project_id=project.id)
    path_before = project.path
    updated = store.set_project_icon(project.id, "symbol:bolt")
    assert updated.id == project.id  # UUID unchanged
    assert updated.path == path_before  # folder unchanged
    assert [n.id for n in store.list_notes() if n.project_id == project.id] == [note.id]


def test_rename_does_not_affect_the_icon(store):
    project = store.create_project("Work")
    store.set_project_icon(project.id, "emoji:🚀")
    renamed = store.rename_project(project.id, "Work Renamed")
    assert renamed.icon == "emoji:🚀"
    assert NoteStore(store.notes_dir).load_project(project.id).icon == "emoji:🚀"


def test_clearing_an_icon_returns_to_the_folder(store):
    project = store.create_project("Work")
    store.set_project_icon(project.id, "symbol:star")
    store.set_project_icon(project.id, None)
    reloaded = NoteStore(store.notes_dir).load_project(project.id)
    assert reloaded.icon is None
    assert project_icon_payload(reloaded.icon) == DEFAULT_PROJECT_SYMBOL


def test_an_invalid_icon_is_never_written(store):
    project = store.create_project("Work")
    store.set_project_icon(project.id, "symbol:not.real")
    assert NoteStore(store.notes_dir).load_project(project.id).icon is None


def test_projects_without_an_icon_keep_clean_metadata(store):
    """No icon means no icon key — existing projects are untouched on disk."""
    project = store.create_project("Work")
    raw = (project.path / storage.PROJECT_METADATA_FILENAME).read_text(encoding="utf-8")
    assert "icon" not in raw


def test_a_corrupt_stored_icon_falls_back_without_losing_the_project(tmp_path):
    store = NoteStore(tmp_path / "Notes")
    project = store.create_project("Work")
    metadata = project.path / storage.PROJECT_METADATA_FILENAME
    payload = metadata.read_text(encoding="utf-8").replace(
        '"name"', '"icon": "symbol:bogus", "name"'
    )
    metadata.write_text(payload, encoding="utf-8")
    reloaded = NoteStore(store.notes_dir).load_project(project.id)
    assert reloaded.name == "Work"  # the project still loads
    assert reloaded.icon is None  # the bad icon simply falls back
