"""Filesystem locations for StormPad.

Pure module (no AppKit). Importing it has **no side effects** — nothing is
created on disk until :func:`ensure_notes_dir` is called explicitly. The notes
directory is injectable so tests can point at a temporary directory and never
touch the user's real Documents folder.
"""

from __future__ import annotations

from pathlib import Path

from .errors import NotesDirectoryError

# Canonical, authoritative location. The design mockups show "~/StormPad/..."
# as flavor copy; the real location is the one built here.
APP_DIRNAME = "StormPad"
NOTES_DIRNAME = "Notes"


def documents_dir() -> Path:
    """Return the user's Documents directory."""
    return Path.home() / "Documents"


def app_dir() -> Path:
    """Return the StormPad application directory (~/Documents/StormPad)."""
    return documents_dir() / APP_DIRNAME


def notes_dir() -> Path:
    """Return the default notes directory (~/Documents/StormPad/Notes)."""
    return app_dir() / NOTES_DIRNAME


def attachments_dir() -> Path:
    """Return the managed attachment root (not created on import)."""
    return app_dir() / "Attachments"


def resolve_notes_dir(override: Path | str | None = None) -> Path:
    """Return ``override`` (as a Path) if given, else the default notes dir.

    This is the single seam used by the app and by tests: the app passes
    nothing (default), tests pass a temporary directory.
    """
    if override is not None:
        return Path(override)
    return notes_dir()


def ensure_notes_dir(override: Path | str | None = None) -> Path:
    """Create (if needed) and return the notes directory.

    Raises :class:`NotesDirectoryError` if the directory cannot be created.
    """
    target = resolve_notes_dir(override)
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:  # pragma: no cover - exercised via monkeypatch in tests
        raise NotesDirectoryError(f"could not create notes directory: {target}") from exc
    return target
