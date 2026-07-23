"""Pure, AppKit-free helpers backing UI controllers.

Extracted so the tricky bits (preview text, word count, selection restoration,
default category for new notes, autosave debounce) are unit-testable without a
running GUI. The AppKit layer wires these to real views, timers, and defaults.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .block_parser import parse_blocks
from .blocks import BlockType
from .exporter import note_to_plain_text
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
    blocks = parse_blocks(note.body)
    visible = []
    for block in blocks:
        if block.kind in (BlockType.DIVIDER, BlockType.TRANSCRIPT):
            continue
        if block.kind == BlockType.RAW:
            visible.append(block.raw or "")
        else:
            visible.append(block.text or block.alt or "")
    collapsed = " ".join(" ".join(visible).split())
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
    return note_to_plain_text(note)


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


def title_display_text(note: Note) -> str:
    """Blank placeholder-facing title for a pristine new note."""
    if note.title == "Untitled Note" and not note.body.strip() and not note.transcript:
        return ""
    return note.title


def note_row_is_selected(note_id: str, selected_id: str | None) -> bool:
    return note_id == selected_id


def title_command_focus(selector: str) -> str:
    """Focus destination for a title command (headlessly testable)."""
    return "body" if selector == "insertNewline:" else "title"


def add_block_menu_mode(*, current_empty: bool, option_pressed: bool) -> str:
    if current_empty:
        return "convert"
    return "above" if option_pressed else "below"


@dataclass(frozen=True)
class GutterRect:
    """AppKit-free rectangle used to prove editor-gutter geometry."""

    x: float
    y: float
    width: float
    height: float

    @property
    def max_x(self) -> float:
        return self.x + self.width


@dataclass(frozen=True)
class BlockGutterLayout:
    add: GutterRect
    text_origin_x: float
    clearance: float

    @property
    def does_not_overlap_text(self) -> bool:
        return self.add.max_x + self.clearance <= self.text_origin_x


def block_gutter_layout(
    text_origin_x: float,
    y: float,
    *,
    control_size: float = 28.0,
    text_clearance: float = 8.0,
) -> BlockGutterLayout:
    """Place the sole add control wholly to the left of the text column."""
    add_x = text_origin_x - text_clearance - control_size
    return BlockGutterLayout(
        add=GutterRect(add_x, y, control_size, control_size),
        text_origin_x=text_origin_x,
        clearance=text_clearance,
    )


def block_gutter_canvas_y(
    *,
    scroll_origin_y: float,
    text_inset_y: float,
    block_origin_y: float,
    scroll_offset_y: float,
) -> float:
    """Map a text-layout block origin into editor-canvas coordinates."""
    return scroll_origin_y + text_inset_y + block_origin_y - scroll_offset_y


def gutter_hover_hit(
    *,
    x: float,
    y: float,
    gutter_width: float,
    block_area_top: float,
    block_area_bottom: float,
    interactive: bool,
) -> bool:
    """Whether a pointer is in the dedicated interactive block-gutter strip."""
    return interactive and 0.0 <= x <= gutter_width and block_area_top <= y <= block_area_bottom


def block_index_for_location(native_text: str, location: int) -> int:
    """Resolve a Cocoa UTF-16 location to its logical block line."""
    location = min(max(int(location), 0), _utf16_length(native_text))
    consumed = 0
    for index, line in enumerate(native_text.split("\n")):
        boundary = consumed + _utf16_length(line)
        if location <= boundary:
            return index
        consumed = boundary + 1
    return max(0, native_text.count("\n"))


def block_indices_for_selection(native_text: str, location: int, length: int) -> list[int]:
    """Map an actual Cocoa selection range to all intersected block lines."""
    total = _utf16_length(native_text)
    start = min(max(int(location), 0), total)
    end = min(max(start + int(length), start), total)
    if end == start:
        return [block_index_for_location(native_text, start)]
    result: list[int] = []
    cursor = 0
    lines = native_text.split("\n")
    for index, line in enumerate(lines):
        content_end = cursor + _utf16_length(line)
        line_end = content_end + (1 if index < len(lines) - 1 else 0)
        if cursor < end and line_end > start:
            result.append(index)
        cursor = line_end
    return result


def full_note_selection_ranges(
    title: str, native_body: str
) -> tuple[tuple[int, int], tuple[int, int]]:
    """Return Cocoa ranges covering the complete title and body canvases."""
    return ((0, _utf16_length(title)), (0, _utf16_length(native_body)))


def _utf16_length(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def formatting_toolbar_visible(*, selection_length: int, editor_focused: bool) -> bool:
    return editor_focused and selection_length > 0


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
            if note.id == saved_id or note.legacy_id == saved_id:
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
