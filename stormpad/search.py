"""Headless note search and category filtering.

Pure functions over a list of :class:`~stormpad.models.Note`. Case-insensitive
and Unicode-safe (via ``re.IGNORECASE`` on the original text, so match spans map
straight back onto the source strings for UI highlighting). No indexes, no
embeddings — this is deliberately simple substring search.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

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
    """A ranked note match with source spans and a useful one-line excerpt."""

    note: Note
    matches: tuple[Match, ...] = field(default_factory=tuple)
    score: int = 0
    snippet: str = ""
    snippet_field: str | None = None

    @property
    def match_count(self) -> int:
        return len(self.matches)


def transcript_text(note: Note) -> str:
    """Concatenate a note's transcript block texts for searching."""
    return "\n".join(block.text for block in note.transcript)


def notes_with_live_text(
    notes: list[Note],
    note_id: str | None,
    *,
    title: str,
    body: str,
) -> list[Note]:
    """Overlay one editor's live text without mutating persisted note objects."""
    if note_id is None:
        return list(notes)
    return [
        replace(note, title=title, body=body) if note.id == note_id else note
        for note in notes
    ]


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


def _excerpt(text: str, match: Match | None, *, limit: int = 96) -> str:
    """Return compact context around a match, preserving useful ellipses."""
    source = text or ""
    if not source:
        return ""
    if match is None:
        start = 0
        end = min(len(source), limit)
    else:
        context = max(16, (limit - (match.end - match.start)) // 2)
        start = max(0, match.start - context)
        end = min(len(source), match.end + context)
    excerpt = " ".join(source[start:end].split())
    if not excerpt:
        return ""
    return f"{'…' if start else ''}{excerpt}{'…' if end < len(source) else ''}"


def _rank_and_snippet(
    note: Note,
    query: str,
    matches: list[Match],
) -> tuple[int, str, str | None]:
    by_field = {
        field_name: [match for match in matches if match.field == field_name]
        for field_name in (FIELD_TITLE, FIELD_BODY, FIELD_TRANSCRIPT)
    }
    folded_title = note.title.casefold()
    folded_query = query.casefold()
    title_matches = by_field[FIELD_TITLE]
    if folded_title == folded_query:
        score = 400
    elif folded_title.startswith(folded_query):
        score = 300
    elif title_matches:
        score = 200
    elif by_field[FIELD_BODY]:
        score = 100
    else:
        score = 50
    score += min(len(title_matches), 9) * 4
    score += min(len(by_field[FIELD_BODY]), 9) * 2
    score += min(len(by_field[FIELD_TRANSCRIPT]), 9)

    if by_field[FIELD_BODY]:
        return score, _excerpt(note.body, by_field[FIELD_BODY][0]), FIELD_BODY
    transcript = transcript_text(note)
    if by_field[FIELD_TRANSCRIPT]:
        return (
            score,
            _excerpt(transcript, by_field[FIELD_TRANSCRIPT][0]),
            FIELD_TRANSCRIPT,
        )
    if note.body.strip():
        return score, _excerpt(note.body, None), FIELD_BODY
    if transcript.strip():
        return score, _excerpt(transcript, None), FIELD_TRANSCRIPT
    return score, _excerpt(note.title, title_matches[0] if title_matches else None), FIELD_TITLE


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
    - Title matches rank above body matches, which rank above transcript matches.
      Exact and prefix title matches rank above other title matches; recency
      breaks equal-relevance ties.
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
            score, snippet, snippet_field = _rank_and_snippet(
                note,
                trimmed,
                matches,
            )
            results.append(
                SearchResult(
                    note=note,
                    matches=tuple(matches),
                    score=score,
                    snippet=snippet,
                    snippet_field=snippet_field,
                )
            )
    results.sort(
        key=lambda result: (result.score, result.note.updated_at),
        reverse=True,
    )
    return results
