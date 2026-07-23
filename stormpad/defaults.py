"""AppKit adapter: an NSUserDefaults-backed preferences backend.

Lives in the UI/adapter layer (imports Foundation). Implements the tiny
``PreferencesBackend`` protocol from :mod:`stormpad.preferences`, keeping the
domain preferences module AppKit-free. Also stores/restores window frame and
split divider positions (opaque strings the app manages).
"""

from __future__ import annotations

from Foundation import NSUserDefaults

_SUITE = "com.stormpad.StormPad"


class UserDefaultsBackend:
    """String key/value store backed by ``NSUserDefaults`` (get/set/delete)."""

    def __init__(self, suite: str = _SUITE) -> None:
        self._defaults = NSUserDefaults.alloc().initWithSuiteName_(suite)

    def get(self, key: str) -> str | None:
        value = self._defaults.stringForKey_(key)
        return str(value) if value is not None else None

    def set(self, key: str, value: str) -> None:
        self._defaults.setObject_forKey_(value, key)

    def delete(self, key: str) -> None:
        self._defaults.removeObjectForKey_(key)
