"""Domain and storage exceptions for StormPad.

Small, explicit hierarchy so callers (and tests) can distinguish user-input
errors from filesystem failures. All inherit from :class:`StormPadError`.
"""

from __future__ import annotations


class StormPadError(Exception):
    """Base class for all StormPad errors."""


# --- Input / validation errors ------------------------------------------------


class InvalidCategoryError(StormPadError, ValueError):
    """A category outside the allowed set was supplied via a strict API."""


class InvalidThemeError(StormPadError, ValueError):
    """A theme id outside the allowed set was supplied via a strict API."""


class InvalidProjectError(StormPadError, ValueError):
    """A requested project name or identifier is invalid."""


class EmptyTranscriptError(StormPadError, ValueError):
    """Attempted to append a transcript block with empty text."""


class InvalidTimestampError(StormPadError, ValueError):
    """A transcript timestamp could not be parsed/normalized."""


# --- Storage errors -----------------------------------------------------------


class StorageError(StormPadError):
    """Base class for filesystem/storage failures."""


class NotesDirectoryError(StorageError):
    """The notes directory could not be created or accessed."""


class NoteNotFoundError(StorageError):
    """No note exists on disk for the requested id."""


class ProjectNotFoundError(StorageError):
    """No project exists on disk for the requested id."""


class ProjectNotEmptyError(StorageError):
    """A populated project was asked to be deleted without moving its notes."""


class AtomicWriteError(StorageError):
    """An atomic write failed; the destination was left untouched."""


class FilenameRenameError(StorageError):
    """A title-based filename commit failed; the previous path remains valid."""
