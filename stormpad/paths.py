"""Filesystem locations for StormPad.

Pure module (no AppKit) so it stays unit-testable. Full directory-creation
logic lands in Phase 2; this defines the canonical, single source of truth for
where notes live.
"""

from __future__ import annotations

from pathlib import Path

# Canonical storage location. Used everywhere — do not hardcode this path
# elsewhere. (The design mockups show "~/StormPad/..." as flavor copy; the
# real, authoritative location is the one below.)
NOTES_DIRNAME = "Notes"
APP_DIRNAME = "StormPad"


def documents_dir() -> Path:
    """Return the user's Documents directory."""
    return Path.home() / "Documents"


def app_dir() -> Path:
    """Return the StormPad application data directory (~/Documents/StormPad)."""
    return documents_dir() / APP_DIRNAME


def notes_dir() -> Path:
    """Return the notes directory (~/Documents/StormPad/Notes)."""
    return app_dir() / NOTES_DIRNAME
