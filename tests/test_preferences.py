"""Tests for the preferences abstraction."""

from __future__ import annotations

import pytest

from stormpad import models
from stormpad.errors import InvalidCategoryError, InvalidThemeError
from stormpad.preferences import (
    DEFAULT_THEME,
    LIGHT,
    STORM_BLUE,
    InMemoryBackend,
    Preferences,
)


def test_defaults():
    prefs = Preferences()
    assert prefs.theme == STORM_BLUE == DEFAULT_THEME
    assert prefs.last_note_id is None
    assert prefs.last_category == models.ALL_NOTES
    assert prefs.show_block_controls is True


def test_theme_persists_through_backend():
    backend = InMemoryBackend()
    Preferences(backend).theme = LIGHT
    # A fresh facade over the same backend sees the stored value.
    assert Preferences(backend).theme == LIGHT


def test_invalid_stored_theme_falls_back():
    backend = InMemoryBackend({"theme": "not-a-theme"})
    assert Preferences(backend).theme == DEFAULT_THEME


def test_set_invalid_theme_raises():
    prefs = Preferences()
    with pytest.raises(InvalidThemeError):
        prefs.theme = "rainbow"


def test_last_note_id_roundtrip_and_clear():
    backend = InMemoryBackend()
    prefs = Preferences(backend)
    prefs.last_note_id = "2026-07-23-1430-idea"
    assert Preferences(backend).last_note_id == "2026-07-23-1430-idea"
    prefs.last_note_id = None
    assert Preferences(backend).last_note_id is None


def test_last_category_roundtrip_and_validation():
    backend = InMemoryBackend()
    prefs = Preferences(backend)
    prefs.last_category = models.SESSIONS
    assert Preferences(backend).last_category == models.SESSIONS

    prefs.last_category = models.ALL_NOTES  # the filter sentinel is allowed
    assert Preferences(backend).last_category == models.ALL_NOTES

    with pytest.raises(InvalidCategoryError):
        prefs.last_category = "Bogus"


def test_invalid_stored_category_falls_back():
    backend = InMemoryBackend({"last_category": "garbage"})
    assert Preferences(backend).last_category == models.ALL_NOTES


def test_note_list_collapse_persists():
    backend = InMemoryBackend()
    prefs = Preferences(backend)
    assert prefs.notes_list_collapsed is False
    prefs.notes_list_collapsed = True
    assert Preferences(backend).notes_list_collapsed is True
    prefs.notes_list_collapsed = False
    assert Preferences(backend).notes_list_collapsed is False


def test_show_block_controls_persists():
    backend = InMemoryBackend()
    prefs = Preferences(backend)
    prefs.show_block_controls = False
    assert Preferences(backend).show_block_controls is False
    prefs.show_block_controls = True
    assert Preferences(backend).show_block_controls is True


def test_project_selection_collapse_and_order_persist_defensively():
    backend = InMemoryBackend()
    prefs = Preferences(backend)
    assert prefs.selected_project_id is None
    assert prefs.projects_collapsed is False
    assert prefs.project_order == []
    prefs.selected_project_id = "project-a"
    prefs.projects_collapsed = True
    prefs.project_order = ["project-b", "project-a", "project-b"]
    restored = Preferences(backend)
    assert restored.selected_project_id == "project-a"
    assert restored.projects_collapsed is True
    assert restored.project_order == ["project-b", "project-a"]


def test_invalid_project_order_falls_back_to_empty():
    backend = InMemoryBackend({"project_order": "not-json"})
    assert Preferences(backend).project_order == []
