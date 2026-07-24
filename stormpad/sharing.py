"""Local, metadata-safe note and project exports for native sharing."""

from __future__ import annotations

import copy
import os
import re
import shutil
import tempfile
import time
import zipfile
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path

from . import attachments, storage
from .block_parser import parse_blocks
from .block_serializer import serialize_blocks
from .blocks import Block, BlockType, InlineMark, InlineRun, MarkType
from .errors import ShareExportError, StorageError
from .exporter import export_note_txt, note_to_plain_text
from .models import Note, Project

SHARE_DIRECTORY_NAME = "ShareExports"
DEFAULT_RETENTION_SECONDS = 24 * 60 * 60
_UNSAFE_ARCHIVE_COMPONENT = re.compile(r"[\x00-\x1f<>:\"/\\|?*]+")
_ABSOLUTE_LOCAL_PATH = re.compile(
    r"(?<!\w)(?:file://)?/(?:Users|Volumes|private|tmp|home)/[^\s)<>\]]+"
)


def default_share_directory() -> Path:
    """Return an OS-temporary StormPad-owned share cache outside the library."""
    return Path(tempfile.gettempdir()) / "StormPad" / SHARE_DIRECTORY_NAME


def safe_archive_component(value: str, *, fallback: str) -> str:
    """Return a readable, traversal-safe ZIP path component."""
    normalized = _UNSAFE_ARCHIVE_COMPONENT.sub("-", str(value)).strip(" .-")
    return (normalized[:120].rstrip(" .-") or fallback)


def unique_export_path(directory: Path, filename: str) -> Path:
    """Return a collision-safe destination without overwriting an active share."""
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    index = 2
    while (directory / f"{stem}-{index}{suffix}").exists():
        index += 1
    return directory / f"{stem}-{index}{suffix}"


def _safe_link_target(target: str | None) -> str | None:
    if not target:
        return target
    raw = str(target).strip()
    if raw.startswith("file://") or Path(raw).is_absolute():
        return safe_archive_component(Path(raw.removeprefix("file://")).name, fallback="local-file")
    return raw


def _sanitize_runs(runs: list[InlineRun]) -> list[InlineRun]:
    result: list[InlineRun] = []
    for run in runs:
        marks = tuple(
            InlineMark(mark.kind, _safe_link_target(mark.value))
            if mark.kind == MarkType.LINK and mark.value
            else mark
            for mark in run.marks
        )
        result.append(InlineRun(run.text, marks))
    return result


def _without_local_paths(text: str, *private_values: str) -> str:
    result = text
    for value in private_values:
        if value:
            result = result.replace(value, "[internal value removed]")
    return _ABSOLUTE_LOCAL_PATH.sub("[local path removed]", result)


def _sanitized_markdown(
    note: Note,
    *,
    notes_dir: Path,
    attachment_folder: str,
    attachment_destination: Path,
) -> tuple[str, set[Path]]:
    """Build shareable Markdown and copy only its referenced managed files."""
    blocks: list[Block] = []
    copied: set[Path] = set()
    archive_targets: dict[Path, str] = {}
    attachment_destination.mkdir(parents=True, exist_ok=True)
    for original in parse_blocks(note.body):
        if original.kind == BlockType.TRANSCRIPT:
            continue
        block = copy.deepcopy(original)
        block.runs = _sanitize_runs(block.runs)
        if block.kind == BlockType.LINK:
            block.target = _safe_link_target(block.target)
        if block.kind in (BlockType.IMAGE, BlockType.FILE) and block.target:
            managed = attachments.resolve_managed_path(
                note.path,
                block.target,
                notes_dir,
                note.id,
            )
            if managed is not None and managed.is_file():
                resolved = managed.resolve()
                target = archive_targets.get(resolved)
                if target is None:
                    filename = attachments.sanitize_filename(managed.name)
                    destination = attachments.unique_attachment_path(
                        attachment_destination,
                        filename,
                    )
                    shutil.copy2(managed, destination)
                    target = f"../Attachments/{attachment_folder}/{destination.name}"
                    archive_targets[resolved] = target
                    copied.add(resolved)
                block.target = target
            else:
                block.target = safe_archive_component(
                    Path(block.target).name,
                    fallback="attachment",
                )
        blocks.append(block)

    parts = [
        f"# {note.title.strip() or storage.DEFAULT_TITLE}",
        (
            f"Created: {note.created_at.isoformat(sep=' ')}\n"
            f"Updated: {note.updated_at.isoformat(sep=' ')}\n"
            f"Category: {note.category}"
        ),
        "## Notes",
    ]
    body = serialize_blocks(blocks)
    if body:
        parts.append(body)
    if note.transcript:
        transcript = ["## Transcript"]
        transcript.extend(
            f"[{chunk.timestamp}]\n{chunk.text}"
            for chunk in note.transcript
        )
        parts.append("\n\n".join(transcript))
    rendered = "\n\n".join(parts) + "\n"
    return (
        _without_local_paths(
            rendered,
            note.id,
            str(note.path),
            str(notes_dir),
        ),
        copied,
    )


class ShareExportManager:
    """Create temporary note/project exports and age out stale share files."""

    def __init__(
        self,
        notes_dir: Path | str,
        *,
        cache_dir: Path | str | None = None,
        retention_seconds: int = DEFAULT_RETENTION_SECONDS,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.notes_dir = Path(notes_dir)
        self.cache_dir = Path(cache_dir) if cache_dir is not None else default_share_directory()
        self.retention_seconds = max(int(retention_seconds), 60)
        self._now = now

    def _prepare(self) -> Path:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ShareExportError("could not create the temporary share directory") from exc
        return self.cache_dir

    def cleanup_expired(self) -> list[Path]:
        """Remove only manager-owned entries older than the retention window."""
        if not self.cache_dir.exists():
            return []
        removed: list[Path] = []
        cutoff = self._now() - self.retention_seconds
        for path in self.cache_dir.iterdir():
            try:
                if path.stat().st_mtime >= cutoff:
                    continue
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                removed.append(path)
            except OSError:
                continue
        return removed

    def export_note(self, note: Note) -> Path:
        """Create a collision-safe readable TXT share without changing Markdown."""
        directory = self._prepare()
        destination = unique_export_path(
            directory,
            f"{storage.slugify(note.title)}.txt",
        )
        try:
            return export_note_txt(note, destination)
        except OSError as exc:
            raise ShareExportError("could not prepare the note for sharing") from exc

    def export_project(self, project: Project, notes: Iterable[Note]) -> Path:
        """Create an atomic sanitized ZIP containing project notes and references."""
        directory = self._prepare()
        project_notes = sorted(
            (note for note in notes if note.project_id == project.id),
            key=lambda note: (note.title.casefold(), note.path.name.casefold()),
        )
        destination = unique_export_path(
            directory,
            f"{storage.project_slug(project.name)}.zip",
        )
        root_name = safe_archive_component(project.name, fallback="StormPad Project")
        try:
            with tempfile.TemporaryDirectory(
                dir=directory,
                prefix=".stormpad-share-project-",
            ) as temporary:
                staging = Path(temporary) / root_name
                notes_folder = staging / "Notes"
                attachments_folder = staging / "Attachments"
                notes_folder.mkdir(parents=True)
                used_note_stems: set[str] = set()
                for note in project_notes:
                    stem = storage.slugify(note.title)
                    candidate = stem
                    index = 2
                    while candidate in used_note_stems:
                        candidate = f"{stem}-{index}"
                        index += 1
                    used_note_stems.add(candidate)
                    note_attachments = attachments_folder / candidate
                    markdown, copied = _sanitized_markdown(
                        note,
                        notes_dir=self.notes_dir,
                        attachment_folder=candidate,
                        attachment_destination=note_attachments,
                    )
                    markdown = _without_local_paths(
                        markdown,
                        project.id,
                        str(project.path),
                    )
                    storage.atomic_write_text(notes_folder / f"{candidate}.md", markdown)
                    storage.atomic_write_text(
                        notes_folder / f"{candidate}.txt",
                        _without_local_paths(
                            note_to_plain_text(note),
                            note.id,
                            project.id,
                            str(note.path),
                            str(project.path),
                        ),
                    )
                    if not copied:
                        shutil.rmtree(note_attachments, ignore_errors=True)

                export_date = datetime.fromtimestamp(self._now()).astimezone().isoformat(
                    timespec="seconds"
                )
                storage.atomic_write_text(
                    staging / "README.txt",
                    (
                        f"{project.name}\n\n"
                        f"Exported: {export_date}\n"
                        f"Notes: {len(project_notes)}\n\n"
                        "This package was exported locally from StormPad.\n"
                    ),
                )
                fd, temporary_zip_name = tempfile.mkstemp(
                    dir=directory,
                    prefix=".stormpad-share-",
                    suffix=".tmp",
                )
                os.close(fd)
                temporary_zip = Path(temporary_zip_name)
                try:
                    with zipfile.ZipFile(
                        temporary_zip,
                        "w",
                        compression=zipfile.ZIP_DEFLATED,
                    ) as archive:
                        for path in sorted(staging.rglob("*")):
                            if path.is_file():
                                archive.write(
                                    path,
                                    Path(root_name) / path.relative_to(staging),
                                )
                    with temporary_zip.open("rb") as handle:
                        os.fsync(handle.fileno())
                    os.replace(temporary_zip, destination)
                except Exception:
                    temporary_zip.unlink(missing_ok=True)
                    raise
        except (OSError, StorageError, zipfile.BadZipFile) as exc:
            if isinstance(exc, ShareExportError):
                raise
            raise ShareExportError("could not prepare the project for sharing") from exc
        return destination
