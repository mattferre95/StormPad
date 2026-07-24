"""Headless note search and category filtering.

Pure functions over a list of :class:`~stormpad.models.Note`. Case-insensitive
and Unicode-safe (via ``re.IGNORECASE`` on the original text, so match spans map
straight back onto the source strings for UI highlighting). No indexes, no
embeddings — this is deliberately simple substring search.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .errors import InvalidCategoryError
from .models import ALL_NOTES, CATEGORIES, UNFILED_PROJECT_ID, Note

FIELD_TITLE = "title"
FIELD_BODY = "body"
FIELD_TRANSCRIPT = "transcript"


@dataclass(frozen=True)
class Match:
    """A single match: which field, and the [start, end) span within it."""

    field: str
    start: int
    end: int


@dataclass
class SearchResult:
    """A note that matched, plus per-field match spans for highlighting."""

    note: Note
    matches: tuple[Match, ...] = field(default_factory=tuple)

    @property
    def match_count(self) -> int:
        return len(self.matches)


def transcript_text(note: Note) -> str:
    """Concatenate a note's transcript block texts for searching."""
    return "\n".join(block.text for block in note.transcript)


def filter_by_category(notes: list[Note], category: str | None) -> list[Note]:
    """Return notes in ``category``.

    ``None`` or ``"All Notes"`` means no filtering. Any other value must be a
    valid category, else :class:`InvalidCategoryError` is raised.
    """
    if category is None or category == ALL_NOTES:
        return list(notes)
    if category not in CATEGORIES:
        raise InvalidCategoryError(f"{category!r} is not a valid category")
    return [n for n in notes if n.category == category]


def filter_by_project(notes: list[Note], project_id: str | None) -> list[Note]:
    """Filter by project identity; ``None`` means all and Unfiled means no project."""
    if project_id is None:
        return list(notes)
    if project_id == UNFILED_PROJECT_ID:
        return [note for note in notes if note.project_id is None]
    return [note for note in notes if note.project_id == project_id]


def filter_by_pinned(notes: list[Note], pinned_ids) -> list[Note]:
    """Return only notes whose stable id is pinned, preserving list order.

    Works across projects and Unfiled because it matches on the note's stable
    UUID only. Unknown/stale ids simply match nothing.
    """
    pinned = set(pinned_ids or ())
    if not pinned:
        return []
    return [note for note in notes if note.id in pinned]


def prune_pinned_ids(pinned_ids, existing_ids) -> list[str]:
    """Drop pinned ids whose notes no longer exist, preserving pin order."""
    existing = set(existing_ids or ())
    result: list[str] = []
    for note_id in pinned_ids or ():
        if note_id in existing and note_id not in result:
            result.append(note_id)
    return result


def _spans(text: str, pattern: re.Pattern[str], field_name: str) -> list[Match]:
    return [Match(field_name, m.start(), m.end()) for m in pattern.finditer(text)]


def search_notes(
    notes: list[Note],
    query: str,
    *,
    category: str | None = None,
    project_id: str | None = None,
) -> list[SearchResult]:
    """Search notes by title, body, and transcript text.

    - The query is trimmed; an empty query returns every note (still filtered by
      ``category`` and sorted).
    - Matching is case-insensitive and Unicode-safe.
    - Results are ordered by most recently updated.
    - ``category`` filters independently of the text query.
    """
    pool = filter_by_project(filter_by_category(notes, category), project_id)
    pool.sort(key=lambda n: n.updated_at, reverse=True)

    trimmed = (query or "").strip()
    if not trimmed:
        return [SearchResult(note=n) for n in pool]

    pattern = re.compile(re.escape(trimmed), re.IGNORECASE)
    results: list[SearchResult] = []
    for note in pool:
        matches = (
            _spans(note.title, pattern, FIELD_TITLE)
            + _spans(note.body, pattern, FIELD_BODY)
            + _spans(transcript_text(note), pattern, FIELD_TRANSCRIPT)
        )
        if matches:
            results.append(SearchResult(note=note, matches=tuple(matches)))
    return results
