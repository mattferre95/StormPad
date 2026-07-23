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

import json
import os
import re
import tempfile
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path

from .errors import AtomicWriteError, FilenameRenameError
from .models import (
    CATEGORIES,
    DEFAULT_CATEGORY,
    Note,
    Project,
    TranscriptBlock,
    now_local,
)

DEFAULT_TITLE = "Untitled Note"
_MAX_SLUG_LEN = 60
_LEGACY_ID_NAMESPACE = uuid.UUID("f3f78d64-8147-5f70-8bd0-03cf1d29f7f3")

_TITLE_RE = re.compile(r"^#\s+(.*)$")
_META_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 _-]{0,63}):\s*(.*)$")
_TS_LINE_RE = re.compile(r"^\[(\d{1,2}:\d{2}:\d{2})\]\s*$")
_NOTES_HEADER = "## Notes"
_TRANSCRIPT_HEADER = "## Transcript"
_KNOWN_METADATA = {"Created", "Updated", "Category", "ID", "Transcript-Block"}
PROJECTS_DIRNAME = "Projects"
PROJECT_METADATA_FILENAME = ".stormpad-project.json"
_KNOWN_METADATA.add("Project-ID")


# --- Filenames ----------------------------------------------------------------


def slugify(title: str, *, max_len: int = _MAX_SLUG_LEN) -> str:
    """Build a filesystem-safe, Unicode-friendly slug from a title.

    Keeps Unicode letters/digits (lower-cased), turns spaces/underscores/dashes
    into single hyphens, and drops everything else. Never returns an empty slug.
    """
    chars: list[str] = []
    normalized = unicodedata.normalize("NFKC", title or "")
    for ch in normalized.strip():
        if ch.isalnum():
            chars.append(ch.lower())
        elif ch.isspace() or ch in "-_":
            chars.append("-")
        # all other characters (path separators, punctuation, control) dropped
    slug = re.sub(r"-+", "-", "".join(chars)).strip("-")
    slug = slug[:max_len].strip("-")
    return slug or "untitled-note"


def build_filename(title_or_slug: str) -> str:
    """Return a lowercase title-derived kebab filename."""
    return f"{slugify(title_or_slug)}.md"


def build_manual_filename(requested: str) -> str:
    """Sanitize a user-entered filename and enforce the ``.md`` extension."""
    leaf = Path(str(requested).strip()).name
    stem = Path(leaf).stem if Path(leaf).suffix.lower() == ".md" else leaf
    return build_filename(stem)


def project_slug(name: str) -> str:
    """Return a safe project-folder slug with a project-specific fallback."""
    value = slugify(name)
    return "untitled-project" if value == "untitled-note" else value


def unique_path(notes_dir: Path, filename: str, *, excluding: Path | None = None) -> Path:
    """Return a non-colliding path in ``notes_dir`` for ``filename``.

    If the name is taken, appends ``-2``, ``-3``, ... to the stem.
    """
    candidate = notes_dir / filename
    if candidate == excluding or not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    index = 2
    while (notes_dir / f"{stem}-{index}{suffix}").exists() and (
        notes_dir / f"{stem}-{index}{suffix}"
    ) != excluding:
        index += 1
    return notes_dir / f"{stem}-{index}{suffix}"


# --- Serialization ------------------------------------------------------------


def serialize(note: Note) -> str:
    """Render a note to its deterministic Markdown representation."""
    metadata_lines = [
        f"Created: {note.created_at.isoformat(sep=' ')}",
        f"Updated: {note.updated_at.isoformat(sep=' ')}",
        f"Category: {note.category}",
        f"ID: {note.id}",
    ]
    if note.project_id:
        metadata_lines.append(f"Project-ID: {note.project_id}")
    if note.transcript_visible or note.transcript:
        state = (
            "hidden"
            if not note.transcript_visible
            else ("collapsed" if note.transcript_collapsed else "expanded")
        )
        metadata_lines.append(f"Transcript-Block: {state}")
    metadata_lines.extend(
        f"{key}: {value}" for key, value in note.metadata.items() if key not in _KNOWN_METADATA
    )
    parts: list[str] = [
        f"# {note.title or DEFAULT_TITLE}",
        "\n".join(metadata_lines),
        _NOTES_HEADER,
    ]
    if note.body:
        parts.append(note.body)
    if note.transcript_visible or note.transcript:
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


def _legacy_uuid(path: Path) -> str:
    """Deterministic migration identity for a legacy file with no ID."""
    try:
        identity = str(path.resolve())
    except OSError:
        identity = str(path.absolute())
    return str(uuid.uuid5(_LEGACY_ID_NAMESPACE, identity))


def _valid_stored_id(value: str) -> str | None:
    try:
        return str(uuid.UUID(value.strip()))
    except (ValueError, AttributeError):
        return None


def parse(
    text: str,
    *,
    note_id: str | None = None,
    path: Path,
    fallback: datetime | None = None,
) -> Note:
    """Parse Markdown into a :class:`Note`.

    Stable identity comes from ``ID`` metadata, or a deterministic UUID when
    loading a legacy file. ``note_id`` remains a compatibility alias for the
    legacy filename stem and is never the new stable identity.
    """
    fallback = fallback or now_local()
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    title = DEFAULT_TITLE
    created = fallback
    updated = fallback
    category = DEFAULT_CATEGORY
    stored_id: str | None = None
    unknown_metadata: dict[str, str] = {}
    transcript_visible = False
    transcript_collapsed = False
    transcript_hidden = False
    project_id: str | None = None

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
        elif key == "ID":
            stored_id = _valid_stored_id(value)
        elif key == "Transcript-Block":
            transcript_visible = value.lower() in ("expanded", "collapsed")
            transcript_collapsed = value.lower() == "collapsed"
            transcript_hidden = value.lower() == "hidden"
        elif key == "Project-ID":
            project_id = _valid_stored_id(value)
        else:
            unknown_metadata[key] = value

    # Body: between "## Notes" and "## Transcript" (or EOF).
    body = ""
    if notes_idx is not None:
        end = transcript_idx if transcript_idx is not None else len(lines)
        body = _strip_blank_edges(lines[notes_idx + 1 : end])

    # Transcript blocks.
    transcript: list[TranscriptBlock] = []
    if transcript_idx is not None:
        transcript = _parse_transcript(lines[transcript_idx + 1 :])
        transcript_visible = transcript_visible or (bool(transcript) and not transcript_hidden)

    legacy_id = note_id or path.stem
    stable_id = stored_id or _legacy_uuid(path)

    note = Note(
        id=stable_id,
        path=path,
        title=title,
        body=body,
        category=category,
        created_at=created,
        updated_at=updated,
        transcript=transcript,
        metadata=unknown_metadata,
        transcript_visible=transcript_visible,
        transcript_collapsed=transcript_collapsed,
        id_persisted=stored_id is not None,
        legacy_id=None if stored_id else legacy_id,
        project_id=project_id,
    )
    if transcript_hidden:
        note.transcript_visible = False
    return note


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
    note.id_persisted = True


def read_note(path: Path) -> Note:
    """Read a note, migrating legacy identity in memory without rewriting."""
    text = path.read_text(encoding="utf-8")
    fallback = _mtime_or_now(path)
    return parse(text, note_id=path.stem, path=path, fallback=fallback)


def commit_title_filename(note: Note) -> Path:
    """Move a safely-written note to its collision-free title filename.

    The target never exists and ``note.path`` changes only after the filesystem
    move succeeds. A failure therefore preserves the previous valid file.
    """
    target = unique_path(
        note.path.parent,
        build_filename(note.title or DEFAULT_TITLE),
        excluding=note.path,
    )
    if target == note.path:
        return note.path
    try:
        os.replace(note.path, target)
    except OSError as exc:
        raise FilenameRenameError(
            f"saved note but could not rename {note.path.name} to {target.name}"
        ) from exc
    note.path = target
    return target


def commit_manual_filename(note: Note, requested: str) -> Path:
    """Move a saved note to a safe, collision-free user-requested filename."""
    target = unique_path(
        note.path.parent,
        build_manual_filename(requested),
        excluding=note.path,
    )
    if target == note.path:
        return note.path
    try:
        os.replace(note.path, target)
    except OSError as exc:
        raise FilenameRenameError(
            f"saved note but could not rename {note.path.name} to {target.name}"
        ) from exc
    note.path = target
    return target


# --- Projects -----------------------------------------------------------------


def projects_dir(notes_dir: Path | str) -> Path:
    return Path(notes_dir) / PROJECTS_DIRNAME


def unique_project_path(notes_dir: Path | str, name: str, *, excluding: Path | None = None) -> Path:
    root = projects_dir(notes_dir)
    slug = project_slug(name)
    candidate = root / slug
    if candidate == excluding or not candidate.exists():
        return candidate
    index = 2
    while (root / f"{slug}-{index}").exists() and (root / f"{slug}-{index}") != excluding:
        index += 1
    return root / f"{slug}-{index}"


def project_metadata(project: Project) -> str:
    """Serialize stable project metadata as deterministic UTF-8 JSON."""
    return (
        json.dumps(
            {
                "id": project.id,
                "name": project.name,
                "created_at": project.created_at.isoformat(),
                "updated_at": project.updated_at.isoformat(),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def write_project(project: Project) -> None:
    project.path.mkdir(parents=True, exist_ok=True)
    atomic_write_text(project.path / PROJECT_METADATA_FILENAME, project_metadata(project))


def read_project(path: Path) -> Project | None:
    """Read valid project metadata; malformed/unknown folders stay non-fatal."""
    metadata_path = path / PROJECT_METADATA_FILENAME
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        project_id = str(uuid.UUID(str(payload["id"])))
        name = str(payload["name"]).strip()
        created = datetime.fromisoformat(str(payload["created_at"]))
        updated = datetime.fromisoformat(str(payload["updated_at"]))
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if not name:
        return None
    return Project(
        id=project_id,
        path=path,
        name=name,
        created_at=created,
        updated_at=updated,
    )


def list_projects(notes_dir: Path | str) -> list[Project]:
    root = projects_dir(notes_dir)
    if not root.exists():
        return []
    projects = [
        project
        for path in sorted(root.iterdir())
        if path.is_dir() and (project := read_project(path)) is not None
    ]
    projects.sort(key=lambda project: (project.created_at, project.name.casefold()))
    return projects


def list_note_paths(notes_dir: Path) -> list[Path]:
    """Return root and project Markdown notes, skipping hidden/temp metadata."""
    if not notes_dir.exists():
        return []
    root_notes = [
        path for path in notes_dir.glob("*.md") if path.is_file() and not path.name.startswith(".")
    ]
    project_root = projects_dir(notes_dir)
    project_notes = (
        [
            path
            for path in project_root.rglob("*.md")
            if path.is_file() and not path.name.startswith(".")
        ]
        if project_root.exists()
        else []
    )
    return sorted([*root_notes, *project_notes], key=lambda path: str(path))


def _mtime_or_now(path: Path) -> datetime:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).astimezone().replace(microsecond=0)
    except OSError:
        return now_local()
