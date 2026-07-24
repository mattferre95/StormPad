"""Persisted user preferences (selected theme, last note, last category).

Built around an injectable key/value backend so the logic is fully testable
without AppKit: tests use :class:`InMemoryBackend`; Phase 3 supplies an
NSUserDefaults-backed adapter with the same tiny protocol. Importing this module
never requires AppKit.

Reads are defensive: a corrupted/invalid stored value falls back to a safe
default rather than raising. Strict writes raise on invalid input so programming
mistakes surface early.
"""

from __future__ import annotations

import json
from typing import Protocol

from .errors import InvalidCategoryError, InvalidThemeError
from .models import ALL_NOTES, CATEGORIES

# Theme ids (visual tokens are defined later in theme.py; these are the stable
# identifiers persisted here).
STORM_BLUE = "storm_blue"
LIGHT = "light"
DEEP_DARK = "deep_dark"
THEMES: tuple[str, ...] = (STORM_BLUE, LIGHT, DEEP_DARK)
DEFAULT_THEME = STORM_BLUE

_KEY_THEME = "theme"
_KEY_LAST_NOTE = "last_note_id"
_KEY_LAST_CATEGORY = "last_category"
_KEY_NOTES_COLLAPSED = "notes_list_collapsed"
_KEY_SHOW_BLOCK_CONTROLS = "show_block_controls"
_KEY_SELECTED_PROJECT = "selected_project_id"
_KEY_PROJECTS_COLLAPSED = "projects_collapsed"
_KEY_PROJECT_ORDER = "project_order"
_KEY_PINNED_NOTES = "pinned_note_ids"
_KEY_RECENT_COLORS = "recent_colors"
RECENT_COLOR_LIMIT = 4


class PreferencesBackend(Protocol):
    """Minimal key/value string store."""

    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str) -> None: ...

    def delete(self, key: str) -> None: ...


class InMemoryBackend:
    """Dict-backed preferences store for tests and defaults."""

    def __init__(self, initial: dict[str, str] | None = None) -> None:
        self._data: dict[str, str] = dict(initial or {})

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def set(self, key: str, value: str) -> None:
        self._data[key] = value

    def delete(self, key: str) -> None:
        self._data.pop(key, None)


class Preferences:
    """Typed facade over a :class:`PreferencesBackend`."""

    def __init__(self, backend: PreferencesBackend | None = None) -> None:
        self._backend: PreferencesBackend = backend or InMemoryBackend()

    # -- Theme ----------------------------------------------------------------

    @property
    def theme(self) -> str:
        """The selected theme id; falls back to the default if missing/invalid."""
        value = self._backend.get(_KEY_THEME)
        return value if value in THEMES else DEFAULT_THEME

    @theme.setter
    def theme(self, value: str) -> None:
        if value not in THEMES:
            raise InvalidThemeError(f"{value!r} is not a valid theme; expected {THEMES}")
        self._backend.set(_KEY_THEME, value)

    # -- Last selected note ---------------------------------------------------

    @property
    def last_note_id(self) -> str | None:
        value = self._backend.get(_KEY_LAST_NOTE)
        return value or None

    @last_note_id.setter
    def last_note_id(self, value: str | None) -> None:
        if value:
            self._backend.set(_KEY_LAST_NOTE, value)
        else:
            self._backend.delete(_KEY_LAST_NOTE)

    # -- Last selected category ----------------------------------------------

    @property
    def last_category(self) -> str:
        """Last selected category; falls back to 'All Notes' if missing/invalid."""
        value = self._backend.get(_KEY_LAST_CATEGORY)
        if value == ALL_NOTES or value in CATEGORIES:
            return value
        return ALL_NOTES

    @last_category.setter
    def last_category(self, value: str) -> None:
        if value != ALL_NOTES and value not in CATEGORIES:
            raise InvalidCategoryError(f"{value!r} is not a valid category")
        self._backend.set(_KEY_LAST_CATEGORY, value)

    # -- Note-list column ----------------------------------------------------

    @property
    def notes_list_collapsed(self) -> bool:
        return self._backend.get(_KEY_NOTES_COLLAPSED) == "true"

    @notes_list_collapsed.setter
    def notes_list_collapsed(self, value: bool) -> None:
        self._backend.set(_KEY_NOTES_COLLAPSED, "true" if value else "false")

    # -- Editor -------------------------------------------------------------

    @property
    def show_block_controls(self) -> bool:
        """Whether the hover-only Add Block gutter control is enabled."""
        return self._backend.get(_KEY_SHOW_BLOCK_CONTROLS) != "false"

    @show_block_controls.setter
    def show_block_controls(self, value: bool) -> None:
        self._backend.set(_KEY_SHOW_BLOCK_CONTROLS, "true" if value else "false")

    # -- Projects ----------------------------------------------------------

    @property
    def selected_project_id(self) -> str | None:
        return self._backend.get(_KEY_SELECTED_PROJECT) or None

    @selected_project_id.setter
    def selected_project_id(self, value: str | None) -> None:
        if value:
            self._backend.set(_KEY_SELECTED_PROJECT, value)
        else:
            self._backend.delete(_KEY_SELECTED_PROJECT)

    @property
    def projects_collapsed(self) -> bool:
        return self._backend.get(_KEY_PROJECTS_COLLAPSED) == "true"

    @projects_collapsed.setter
    def projects_collapsed(self, value: bool) -> None:
        self._backend.set(_KEY_PROJECTS_COLLAPSED, "true" if value else "false")

    @property
    def project_order(self) -> list[str]:
        raw = self._backend.get(_KEY_PROJECT_ORDER)
        if not raw:
            return []
        try:
            values = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return []
        if not isinstance(values, list):
            return []
        result: list[str] = []
        for value in values:
            if isinstance(value, str) and value and value not in result:
                result.append(value)
        return result

    @project_order.setter
    def project_order(self, values: list[str]) -> None:
        unique = list(dict.fromkeys(value for value in values if value))
        self._backend.set(_KEY_PROJECT_ORDER, json.dumps(unique))

    # -- Pinned notes -------------------------------------------------------

    @property
    def pinned_note_ids(self) -> list[str]:
        """Ordered, de-duplicated stable note UUIDs the user has pinned.

        Defensive: a missing/corrupt value yields an empty list. Stale ids for
        deleted notes are harmless here and are pruned by the caller against the
        notes that actually exist.
        """
        raw = self._backend.get(_KEY_PINNED_NOTES)
        if not raw:
            return []
        try:
            values = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return []
        if not isinstance(values, list):
            return []
        result: list[str] = []
        for value in values:
            if isinstance(value, str) and value and value not in result:
                result.append(value)
        return result

    @pinned_note_ids.setter
    def pinned_note_ids(self, values: list[str]) -> None:
        unique = list(dict.fromkeys(value for value in values if value))
        self._backend.set(_KEY_PINNED_NOTES, json.dumps(unique))

    # -- Recently used colors ------------------------------------------------

    @property
    def recent_colors(self) -> list[str]:
        """Recently applied colors as ``"mode:token"``, most recent first.

        Small and bounded (see :data:`RECENT_COLOR_LIMIT`) — not a history
        system. Corrupt/invalid payloads fall back to an empty list.
        """
        raw = self._backend.get(_KEY_RECENT_COLORS)
        if not raw:
            return []
        try:
            values = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return []
        if not isinstance(values, list):
            return []
        result: list[str] = []
        for value in values:
            if isinstance(value, str) and ":" in value and value not in result:
                result.append(value)
        return result[:RECENT_COLOR_LIMIT]

    @recent_colors.setter
    def recent_colors(self, values: list[str]) -> None:
        unique = list(dict.fromkeys(v for v in values if v and ":" in v))
        self._backend.set(_KEY_RECENT_COLORS, json.dumps(unique[:RECENT_COLOR_LIMIT]))

    def record_recent_color(self, entry: str) -> list[str]:
        """Push ``"mode:token"`` to the front of the recents and persist."""
        if not entry or ":" not in entry:
            return self.recent_colors
        updated = [entry, *(v for v in self.recent_colors if v != entry)]
        self.recent_colors = updated
        return self.recent_colors
