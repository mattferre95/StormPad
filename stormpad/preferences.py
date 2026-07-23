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
