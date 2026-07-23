"""Note/session operations — the headless application core.

:class:`NoteStore` coordinates the in-memory model with the storage layer over
a configured notes directory. It exposes the clean, reusable API the PRD calls
for (including ``append_transcript_block``) — the same seam a future WisperFlow
Session Notes feature can reuse. No AppKit, no audio, no WisperFlow code here.

The notes directory, clock, and delete strategy are all injectable so the whole
layer is testable against a temporary directory.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from . import paths, storage
from .errors import NoteNotFoundError
from .models import (
    DEFAULT_CATEGORY,
    Note,
    TranscriptBlock,
    format_transcript_timestamp,
    now_local,
    validate_category,
)

Clock = Callable[[], datetime]
DeleteStrategy = Callable[[Path], None]

# Sample text used by the "Append Test Transcript" helper (Phase 4 UI button).
_TEST_TRANSCRIPT_TEXT = (
    "This is a captured thought that can later come from live voice transcription."
)


def permanent_delete(path: Path) -> None:
    """Delete strategy that removes a file permanently (default; used in tests)."""
    os.remove(path)


class NoteStore:
    """CRUD + transcript operations over a notes directory.

    Parameters
    ----------
    notes_dir:
        Directory that holds the Markdown files. Defaults to the canonical
        ``~/Documents/StormPad/Notes``. Pass a temporary directory in tests.
    clock:
        Returns the current timezone-aware time; injectable for deterministic
        timestamp tests.
    delete_strategy:
        How a note file is removed. Defaults to permanent deletion. Phase 4 can
        inject a strategy that moves the file to the macOS Trash instead.
    """

    def __init__(
        self,
        notes_dir: Path | str | None = None,
        *,
        clock: Clock = now_local,
        delete_strategy: DeleteStrategy = permanent_delete,
    ) -> None:
        self._notes_dir = paths.resolve_notes_dir(notes_dir)
        self._clock = clock
        self._delete = delete_strategy

    @property
    def notes_dir(self) -> Path:
        return self._notes_dir

    def ensure_dir(self) -> Path:
        """Create the notes directory if needed and return it."""
        return paths.ensure_notes_dir(self._notes_dir)

    def path_for(self, note_id: str) -> Path:
        """Return the on-disk path for a note id."""
        return self._notes_dir / f"{note_id}.md"

    # -- Create ---------------------------------------------------------------

    def create_note(self, title: str = "Untitled Note", category: str = DEFAULT_CATEGORY) -> Note:
        """Create, persist, and return a new note."""
        validate_category(category)
        self.ensure_dir()
        created = self._clock()
        filename = storage.build_filename(created, storage.slugify(title))
        path = storage.unique_path(self._notes_dir, filename)
        note = Note(
            id=path.stem,
            path=path,
            title=title,
            body="",
            category=category,
            created_at=created,
            updated_at=created,
            transcript=[],
        )
        storage.write_note(note)
        return note

    # -- Read -----------------------------------------------------------------

    def load_note(self, note_id: str) -> Note:
        """Load a note by id, or raise :class:`NoteNotFoundError`."""
        path = self.path_for(note_id)
        if not path.exists():
            raise NoteNotFoundError(f"note not found: {note_id}")
        return storage.read_note(path)

    def list_notes(self) -> list[Note]:
        """Return all notes, most recently updated first."""
        notes = [storage.read_note(p) for p in storage.list_note_paths(self._notes_dir)]
        notes.sort(key=lambda n: n.updated_at, reverse=True)
        return notes

    # -- Update ---------------------------------------------------------------

    def save_note(self, note: Note) -> None:
        """Persist a note as-is (does not touch ``updated_at``)."""
        storage.write_note(note)

    def update_title(self, note_id: str, title: str) -> Note:
        """Update a note's title. The underlying filename is *not* changed."""
        note = self.load_note(note_id)
        note.set_title(title, self._clock())
        storage.write_note(note)
        return note

    def update_body(self, note_id: str, body: str) -> Note:
        """Replace a note's body text."""
        note = self.load_note(note_id)
        note.set_body(body, self._clock())
        storage.write_note(note)
        return note

    def update_category(self, note_id: str, category: str) -> Note:
        """Change a note's category (validated)."""
        note = self.load_note(note_id)
        note.set_category(category, self._clock())
        storage.write_note(note)
        return note

    # -- Transcript -----------------------------------------------------------

    def append_transcript_block(
        self, note_id: str, text: str, timestamp: int | float | str
    ) -> Note:
        """Append a timestamped transcript block and persist immediately.

        The reusable integration boundary (PRD §13). ``timestamp`` may be a
        number of seconds or an ``[H]H:MM:SS`` / ``MM:SS`` string. Empty text is
        rejected. Existing blocks are preserved and ``updated_at`` is refreshed.
        """
        from .errors import EmptyTranscriptError

        if not text or not text.strip():
            raise EmptyTranscriptError("transcript text must not be empty")
        normalized = format_transcript_timestamp(timestamp)
        note = self.load_note(note_id)
        note.add_transcript_block(
            TranscriptBlock(timestamp=normalized, text=text.strip()), self._clock()
        )
        storage.write_note(note)
        return note

    def append_test_transcript(self, note_id: str) -> Note:
        """Append a canned transcript block (the future UI test button).

        Deterministic: the timestamp advances 7s per existing block (4s, 11s,
        18s, ...), matching the design mockups.
        """
        note = self.load_note(note_id)
        seconds = 4 + 7 * len(note.transcript)
        return self.append_transcript_block(note_id, _TEST_TRANSCRIPT_TEXT, seconds)

    # -- Delete ---------------------------------------------------------------

    def delete_note(self, note_id: str) -> Path:
        """Delete a note via the configured strategy; return the removed path."""
        path = self.path_for(note_id)
        if not path.exists():
            raise NoteNotFoundError(f"note not found: {note_id}")
        self._delete(path)
        return path
