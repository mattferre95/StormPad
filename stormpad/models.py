"""Note data structures and domain constants.

Pure, AppKit-free. A :class:`Note` is the in-memory representation of a single
Markdown file. UI-specific state (selection, hover, etc.) is intentionally kept
out of the model. Timestamps are timezone-aware and truncated to whole seconds
so serialized files round-trip exactly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .errors import InvalidCategoryError, InvalidTimestampError

# --- Categories ---------------------------------------------------------------
# "All Notes" is a UI filter, not a stored category.
IDEAS = "Ideas"
SESSIONS = "Sessions"
DRAFTS = "Drafts"
CATEGORIES: tuple[str, ...] = (IDEAS, SESSIONS, DRAFTS)
DEFAULT_CATEGORY = IDEAS
ALL_NOTES = "All Notes"  # filter sentinel, never written to disk


def validate_category(category: str) -> str:
    """Return ``category`` if allowed, else raise :class:`InvalidCategoryError`."""
    if category not in CATEGORIES:
        raise InvalidCategoryError(
            f"{category!r} is not a valid category; expected one of {CATEGORIES}"
        )
    return category


def now_local() -> datetime:
    """Timezone-aware 'now' in the local zone, truncated to whole seconds."""
    return datetime.now().astimezone().replace(microsecond=0)


# --- Transcript ---------------------------------------------------------------

_TS_HMS = re.compile(r"(?:(\d{1,2}):)?(\d{1,2}):(\d{1,2})")
_TS_INT = re.compile(r"\d+")


def format_transcript_timestamp(value: int | float | str) -> str:
    """Normalize a transcript timestamp to ``HH:MM:SS``.

    Accepts a non-negative number of seconds, a bare seconds string, or a
    ``[H]H:MM:SS`` / ``MM:SS`` string (optionally wrapped in brackets).
    """
    if isinstance(value, bool):  # bool is an int subclass — reject explicitly
        raise InvalidTimestampError(f"invalid timestamp: {value!r}")
    if isinstance(value, (int, float)):
        total = int(value)
        if total < 0:
            raise InvalidTimestampError(f"timestamp seconds must be >= 0: {value!r}")
        hours, rem = divmod(total, 3600)
        minutes, seconds = divmod(rem, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    if isinstance(value, str):
        raw = value.strip().strip("[]").strip()
        if _TS_INT.fullmatch(raw):
            return format_transcript_timestamp(int(raw))
        match = _TS_HMS.fullmatch(raw)
        if not match:
            raise InvalidTimestampError(f"invalid timestamp: {value!r}")
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2))
        seconds = int(match.group(3))
        if minutes >= 60 or seconds >= 60:
            raise InvalidTimestampError(f"invalid timestamp components: {value!r}")
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    raise InvalidTimestampError(f"unsupported timestamp type: {type(value).__name__}")


@dataclass
class TranscriptBlock:
    """One timestamped transcript entry (``[HH:MM:SS]`` + text)."""

    timestamp: str
    text: str


# --- Note ---------------------------------------------------------------------


@dataclass
class Note:
    """In-memory representation of a StormPad Markdown note.

    ``id`` is a stable UUID stored in Markdown metadata and never changes when
    the title or filename changes. ``legacy_id`` records a pre-Phase-5.1
    filename stem so an old selected-note preference can migrate safely.
    """

    id: str
    path: Path
    title: str
    body: str
    category: str
    created_at: datetime
    updated_at: datetime
    transcript: list[TranscriptBlock] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    transcript_visible: bool = False
    transcript_collapsed: bool = False
    id_persisted: bool = field(default=True, compare=False)
    legacy_id: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        validate_category(self.category)
        if self.transcript:
            self.transcript_visible = True

    # -- mutation helpers (each refreshes updated_at) --------------------------

    def set_title(self, title: str, now: datetime) -> None:
        self.title = title
        self.updated_at = now

    def set_body(self, body: str, now: datetime) -> None:
        self.body = body
        self.updated_at = now

    def set_category(self, category: str, now: datetime) -> None:
        validate_category(category)
        self.category = category
        self.updated_at = now

    def add_transcript_block(self, block: TranscriptBlock, now: datetime) -> None:
        self.transcript.append(block)
        self.transcript_visible = True
        self.transcript_collapsed = False
        self.updated_at = now
