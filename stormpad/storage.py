"""Markdown serialization, parsing, filenames, and safe file I/O.

Markdown files are the source of truth. This module is pure and AppKit-free.
Serialization is deterministic; parsing is *lenient* — files with malformed
metadata are recovered with safe defaults rather than raising, so note bodies
are never lost. (Strict validation lives on the write path, in the model and
session APIs.)

File layout::

    # Title

    Created: 2026-07-23 14:30:00+02:00
    Updated: 2026-07-23 14:30:00+02:00
    Category: Ideas

    ## Notes

    Typed content goes here.

    ## Transcript

    [00:00:04]
    Transcript content goes here.
"""

from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

from .errors import AtomicWriteError
from .models import (
    CATEGORIES,
    DEFAULT_CATEGORY,
    Note,
    TranscriptBlock,
    now_local,
)

DEFAULT_TITLE = "Untitled Note"
_MAX_SLUG_LEN = 60

_TITLE_RE = re.compile(r"^#\s+(.*)$")
_META_RE = re.compile(r"^(Created|Updated|Category):\s*(.*)$")
_TS_LINE_RE = re.compile(r"^\[(\d{1,2}:\d{2}:\d{2})\]\s*$")
_NOTES_HEADER = "## Notes"
_TRANSCRIPT_HEADER = "## Transcript"


# --- Filenames ----------------------------------------------------------------


def slugify(title: str, *, max_len: int = _MAX_SLUG_LEN) -> str:
    """Build a filesystem-safe, Unicode-friendly slug from a title.

    Keeps Unicode letters/digits (lower-cased), turns spaces/underscores/dashes
    into single hyphens, and drops everything else. Never returns an empty slug.
    """
    chars: list[str] = []
    for ch in (title or "").strip():
        if ch.isalnum():
            chars.append(ch.lower())
        elif ch in " -_":
            chars.append("-")
        # all other characters (path separators, punctuation, control) dropped
    slug = re.sub(r"-+", "-", "".join(chars)).strip("-")
    slug = slug[:max_len].strip("-")
    return slug or "untitled-note"


def build_filename(created_at: datetime, slug: str) -> str:
    """Return a stable ``YYYY-MM-DD-HHMM-slug.md`` filename."""
    return f"{created_at:%Y-%m-%d-%H%M}-{slug}.md"


def unique_path(notes_dir: Path, filename: str) -> Path:
    """Return a non-colliding path in ``notes_dir`` for ``filename``.

    If the name is taken, appends ``-2``, ``-3``, ... to the stem.
    """
    candidate = notes_dir / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    index = 2
    while (notes_dir / f"{stem}-{index}{suffix}").exists():
        index += 1
    return notes_dir / f"{stem}-{index}{suffix}"


# --- Serialization ------------------------------------------------------------


def serialize(note: Note) -> str:
    """Render a note to its deterministic Markdown representation."""
    parts: list[str] = [
        f"# {note.title or DEFAULT_TITLE}",
        "\n".join(
            [
                f"Created: {note.created_at.isoformat(sep=' ')}",
                f"Updated: {note.updated_at.isoformat(sep=' ')}",
                f"Category: {note.category}",
            ]
        ),
        _NOTES_HEADER,
    ]
    if note.body:
        parts.append(note.body)
    parts.append(_TRANSCRIPT_HEADER)
    for block in note.transcript:
        parts.append(f"[{block.timestamp}]\n{block.text}")
    return "\n\n".join(parts) + "\n"


# --- Parsing (lenient) --------------------------------------------------------


def _parse_datetime(value: str, fallback: datetime) -> datetime:
    try:
        return datetime.fromisoformat(value.strip())
    except (ValueError, TypeError):
        return fallback


def _parse_transcript(lines: list[str]) -> list[TranscriptBlock]:
    blocks: list[TranscriptBlock] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        match = _TS_LINE_RE.match(line)
        if not match:
            i += 1
            continue
        timestamp = match.group(1)
        i += 1
        text_lines: list[str] = []
        while i < n and lines[i].strip() != "" and not _TS_LINE_RE.match(lines[i]):
            text_lines.append(lines[i])
            i += 1
        blocks.append(TranscriptBlock(timestamp=timestamp, text="\n".join(text_lines)))
    return blocks


def parse(text: str, *, note_id: str, path: Path, fallback: datetime | None = None) -> Note:
    """Parse Markdown into a :class:`Note`.

    ``note_id`` and ``path`` come from the filename (the stable identity);
    everything else is read from the document, with safe fallbacks for missing
    or malformed metadata.
    """
    fallback = fallback or now_local()
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    title = DEFAULT_TITLE
    created = fallback
    updated = fallback
    category = DEFAULT_CATEGORY

    # Locate section headers.
    notes_idx: int | None = None
    transcript_idx: int | None = None
    for idx, line in enumerate(lines):
        if line.rstrip() == _NOTES_HEADER and notes_idx is None:
            notes_idx = idx
        elif line.rstrip() == _TRANSCRIPT_HEADER and transcript_idx is None:
            transcript_idx = idx

    header_end = notes_idx if notes_idx is not None else len(lines)

    # Title: first level-1 heading before the body.
    for line in lines[:header_end]:
        m = _TITLE_RE.match(line)
        if m and not line.startswith("## "):
            title = m.group(1).strip() or DEFAULT_TITLE
            break

    # Metadata lines anywhere before the body.
    for line in lines[:header_end]:
        m = _META_RE.match(line.strip())
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip()
        if key == "Created":
            created = _parse_datetime(value, fallback)
        elif key == "Updated":
            updated = _parse_datetime(value, fallback)
        elif key == "Category":
            category = value if value in CATEGORIES else DEFAULT_CATEGORY

    # Body: between "## Notes" and "## Transcript" (or EOF).
    body = ""
    if notes_idx is not None:
        end = transcript_idx if transcript_idx is not None else len(lines)
        body = _strip_blank_edges(lines[notes_idx + 1 : end])

    # Transcript blocks.
    transcript: list[TranscriptBlock] = []
    if transcript_idx is not None:
        transcript = _parse_transcript(lines[transcript_idx + 1 :])

    return Note(
        id=note_id,
        path=path,
        title=title,
        body=body,
        category=category,
        created_at=created,
        updated_at=updated,
        transcript=transcript,
    )


def _strip_blank_edges(lines: list[str]) -> str:
    start = 0
    end = len(lines)
    while start < end and lines[start].strip() == "":
        start += 1
    while end > start and lines[end - 1].strip() == "":
        end -= 1
    return "\n".join(lines[start:end])


# --- File I/O -----------------------------------------------------------------


def atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically.

    Writes to a temporary file in the same directory, fsyncs, then replaces the
    destination. On failure the destination is left untouched and the temp file
    is cleaned up.
    """
    directory = path.parent
    fd, tmp_name = tempfile.mkstemp(dir=directory, prefix=".stormpad-", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except OSError as exc:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise AtomicWriteError(f"failed to write note: {path}") from exc


def write_note(note: Note) -> None:
    """Serialize and atomically write a note to ``note.path``."""
    atomic_write_text(note.path, serialize(note))


def read_note(path: Path) -> Note:
    """Read and parse the note at ``path`` (id derived from the filename)."""
    text = path.read_text(encoding="utf-8")
    fallback = _mtime_or_now(path)
    return parse(text, note_id=path.stem, path=path, fallback=fallback)


def list_note_paths(notes_dir: Path) -> list[Path]:
    """Return the Markdown note files in ``notes_dir`` (skipping temp files)."""
    if not notes_dir.exists():
        return []
    return sorted(
        p
        for p in notes_dir.glob("*.md")
        if p.is_file() and not p.name.startswith(".")
    )


def _mtime_or_now(path: Path) -> datetime:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).astimezone().replace(microsecond=0)
    except OSError:
        return now_local()
