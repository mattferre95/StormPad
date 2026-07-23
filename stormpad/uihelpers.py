"""Pure, AppKit-free helpers backing UI controllers.

Extracted so the tricky bits (preview text, word count, selection restoration,
default category for new notes, autosave debounce) are unit-testable without a
running GUI. The AppKit layer wires these to real views, timers, and defaults.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from enum import StrEnum

from .models import CATEGORIES, DEFAULT_CATEGORY, Note


class SaveStatus(StrEnum):
    """UI save-state, reflecting real persistence state."""

    SAVED = "Saved locally"
    SAVING = "Saving…"
    FAILED = "Save failed"


def preview_text(note: Note, *, max_len: int = 140) -> str:
    """A short, clean one-line preview of a note's body.

    Collapses whitespace and never exposes Markdown metadata (the body already
    excludes the title/Created/Updated/Category lines and the section headers,
    which live outside ``note.body``).
    """
    collapsed = " ".join(note.body.split())
    if len(collapsed) <= max_len:
        return collapsed
    return collapsed[:max_len].rstrip() + "…"


def word_count(text: str) -> int:
    """Count whitespace-delimited words."""
    return len(text.split())


def copy_text(note: Note) -> str:
    """User-visible plain text for Copy Note.

    Includes the title, body, and transcript (timestamps + text). Excludes all
    internal storage metadata (file path, Created/Updated/Category lines, ids)
    and the serialized Markdown header. Paragraph breaks are preserved.
    """
    parts: list[str] = [note.title or "Untitled Note"]
    if note.body.strip():
        parts.append(note.body.rstrip())
    if note.transcript:
        block_lines = ["Transcript"]
        for block in note.transcript:
            block_lines.append(f"[{block.timestamp}]\n{block.text}")
        parts.append("\n\n".join(block_lines))
    return "\n\n".join(parts).strip() + "\n"


def next_selection_after_delete(displayed: list[Note], deleted_id: str) -> str | None:
    """Choose the note to select after deleting ``deleted_id``.

    The newest remaining visible note (``displayed`` is newest-first), else
    ``None`` (empty state).
    """
    for note in displayed:
        if note.id != deleted_id:
            return note.id
    return None


def is_speakable(text: str | None) -> bool:
    """True if ``text`` has non-whitespace content worth speaking."""
    return bool(text and text.strip())


def status_style(status: SaveStatus) -> tuple[str, str, str]:
    """Map a save status to (text-token, background-token, SF-Symbol) names.

    Pure so the mapping is testable; the editor resolves the token names against
    the active palette.
    """
    return {
        SaveStatus.SAVED: ("success", "success_background", "checkmark"),
        SaveStatus.SAVING: ("text_muted", "pill_background", "arrow.triangle.2.circlepath"),
        SaveStatus.FAILED: ("destructive", "destructive_background", "exclamationmark.triangle"),
    }[status]


def format_relative(dt: datetime, now: datetime) -> str:
    """Human-friendly note timestamp, à la the design ('Today, 2:14 PM')."""
    # Compare in the reference ('now') timezone.
    local = dt.astimezone(now.tzinfo) if now.tzinfo else dt
    delta_days = (now.date() - local.date()).days
    time_str = local.strftime("%-I:%M %p")
    if delta_days <= 0:
        return f"Today, {time_str}"
    if delta_days == 1:
        return "Yesterday"
    if delta_days < 7:
        return local.strftime("%a")
    if local.year == now.year:
        return local.strftime("%b %-d")
    return local.strftime("%b %-d, %Y")


def choose_selected_note(notes: list[Note], saved_id: str | None) -> Note | None:
    """Pick which note to select on load.

    The previously-selected note if it still exists; otherwise the most recently
    updated note; otherwise ``None`` (empty state). ``notes`` is assumed sorted
    most-recent-first (as :meth:`NoteStore.list_notes` returns).
    """
    if saved_id:
        for note in notes:
            if note.id == saved_id:
                return note
    return notes[0] if notes else None


def default_new_category(last_category: str | None) -> str:
    """Category for a newly created note.

    Uses the current category when it is a real stored category
    (Ideas/Sessions/Drafts); otherwise falls back to the default (Ideas). This
    means creating a note while viewing "All Notes" yields an Ideas note.
    """
    if last_category in CATEGORIES:
        return last_category
    return DEFAULT_CATEGORY


class AutosaveController:
    """Debounce coordinator for autosave, with an injectable scheduler.

    The scheduler abstracts the timer so this class is testable without AppKit:
    ``schedule(delay, callback)`` must return a cancel-token and arrange for
    ``callback`` to run after ``delay`` seconds; ``cancel(token)`` cancels a
    pending callback. In the app these are backed by ``NSTimer``; in tests by a
    fake scheduler that fires on demand.
    """

    def __init__(
        self,
        save: Callable[[], None],
        *,
        delay: float,
        schedule: Callable[[float, Callable[[], None]], object],
        cancel: Callable[[object], None],
    ) -> None:
        self._save = save
        self._delay = delay
        self._schedule = schedule
        self._cancel = cancel
        self._token: object | None = None
        self._dirty = False

    @property
    def has_pending(self) -> bool:
        return self._dirty

    def note_edited(self) -> None:
        """Mark dirty and (re)start the debounce timer."""
        self._dirty = True
        if self._token is not None:
            self._cancel(self._token)
        self._token = self._schedule(self._delay, self._fire)

    def _fire(self) -> None:
        self._token = None
        if self._dirty:
            self._dirty = False
            self._save()

    def flush(self) -> None:
        """Immediately persist any pending edit (selection change / quit)."""
        if self._token is not None:
            self._cancel(self._token)
            self._token = None
        if self._dirty:
            self._dirty = False
            self._save()

    def reset(self) -> None:
        """Drop any pending state without saving (e.g. after an external load)."""
        if self._token is not None:
            self._cancel(self._token)
            self._token = None
        self._dirty = False
