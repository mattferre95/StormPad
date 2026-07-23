"""Managed local attachments stored by stable note ID."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path

from .errors import StorageError

IMAGE_EXTENSIONS = {
    ".avif",
    ".bmp",
    ".gif",
    ".heic",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}
_UNSAFE = re.compile(r"[\x00-\x1f<>:\"/\\|?*]+")


def attachment_root(notes_dir: Path | str) -> Path:
    return Path(notes_dir).expanduser().parent / "Attachments"


def note_attachment_dir(notes_dir: Path | str, note_id: str) -> Path:
    return attachment_root(notes_dir) / note_id


def sanitize_filename(name: str) -> str:
    """Return a safe filename while preserving a useful extension."""
    normalized = unicodedata.normalize("NFKC", Path(name).name).strip()
    normalized = _UNSAFE.sub("-", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip(" .-")
    if not normalized:
        return "attachment"
    stem = Path(normalized).stem.strip(" .-") or "attachment"
    suffix = Path(normalized).suffix.lower()
    stem = stem[:120].rstrip(" .-") or "attachment"
    return f"{stem}{suffix}"


def unique_attachment_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    index = 2
    while (directory / f"{stem}-{index}{suffix}").exists():
        index += 1
    return directory / f"{stem}-{index}{suffix}"


def import_attachment(source: Path | str, notes_dir: Path | str, note_id: str) -> Path:
    """Copy ``source`` atomically into the note's managed attachment directory."""
    source_path = Path(source).expanduser()
    if not source_path.is_file():
        raise StorageError(f"attachment source is not a file: {source_path}")
    directory = note_attachment_dir(notes_dir, note_id)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        destination = unique_attachment_path(directory, sanitize_filename(source_path.name))
        fd, tmp_name = tempfile.mkstemp(
            dir=directory, prefix=".stormpad-attachment-", suffix=".tmp"
        )
        os.close(fd)
        tmp_path = Path(tmp_name)
        try:
            shutil.copy2(source_path, tmp_path)
            os.replace(tmp_path, destination)
        except OSError:
            tmp_path.unlink(missing_ok=True)
            raise
        return destination
    except OSError as exc:
        raise StorageError(f"could not import attachment: {source_path.name}") from exc


def relative_markdown_path(note_path: Path, attachment_path: Path) -> str:
    return Path(os.path.relpath(attachment_path, note_path.parent)).as_posix()


def resolve_managed_path(
    note_path: Path, relative_path: str, notes_dir: Path | str, note_id: str
) -> Path | None:
    """Resolve a Markdown path only when it remains inside this note's folder."""
    candidate = (note_path.parent / relative_path).resolve()
    managed = note_attachment_dir(notes_dir, note_id).resolve()
    try:
        candidate.relative_to(managed)
    except ValueError:
        return None
    return candidate


def is_image(path: Path | str) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTENSIONS


def record_orphan(notes_dir: Path | str, note_id: str, relative_path: str) -> None:
    """Record a removed block's managed path without deleting user data."""
    directory = note_attachment_dir(notes_dir, note_id)
    directory.mkdir(parents=True, exist_ok=True)
    manifest = directory / ".orphans.json"
    values: list[str] = []
    if manifest.exists():
        try:
            loaded = json.loads(manifest.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                values = [str(value) for value in loaded]
        except (OSError, json.JSONDecodeError):
            values = []
    if relative_path not in values:
        values.append(relative_path)
    payload = json.dumps(sorted(values), indent=2, ensure_ascii=False) + "\n"
    fd, tmp_name = tempfile.mkstemp(dir=directory, prefix=".orphans-", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, manifest)
    except OSError as exc:
        tmp_path.unlink(missing_ok=True)
        raise StorageError("could not record orphaned attachment") from exc
