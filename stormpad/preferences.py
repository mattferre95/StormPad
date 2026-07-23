"""Persisted user preferences (selected theme, last-open note).

Designed around an injectable key/value backend so the logic is testable
without AppKit: tests pass a plain dict; the app passes an NSUserDefaults-backed
adapter. Implemented in Phase 2 (persistence) / Phase 5 (theme wiring).
"""

from __future__ import annotations

# TODO(phase-2): Preferences facade over an injectable backend; keys for
# selected theme id and last-selected note id, with safe defaults.
