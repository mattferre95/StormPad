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
import shutil
import tempfile
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from . import paths, storage
from .attachments import note_attachment_dir
from .block_parser import parse_blocks
from .block_serializer import serialize_blocks
from .blocks import BlockType
from .errors import (
    InvalidProjectError,
    NoteNotFoundError,
    ProjectNotEmptyError,
    ProjectNotFoundError,
    StorageError,
)
from .icons import normalize_project_icon
from .models import (
    DEFAULT_CATEGORY,
    Note,
    Project,
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
    """Delete strategy that permanently removes a staged file or directory."""
    if path.is_dir():
        shutil.rmtree(path)
    else:
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
        """Resolve a stable metadata ID (or legacy stem) to its current path."""
        for path in storage.list_note_paths(self._notes_dir):
            note = storage.read_note(path)
            if note.id == note_id or note.legacy_id == note_id:
                return path
        return self._notes_dir / f"{note_id}.md"

    def list_projects(self) -> list[Project]:
        """Return valid filesystem-backed projects in stable creation order."""
        return storage.list_projects(self._notes_dir)

    def load_project(self, project_id: str) -> Project:
        project = next(
            (candidate for candidate in self.list_projects() if candidate.id == project_id),
            None,
        )
        if project is None:
            raise ProjectNotFoundError(f"project not found: {project_id}")
        return project

    def create_project(self, name: str) -> Project:
        """Create a real project directory with stable metadata."""
        display_name = str(name).strip()
        if not display_name:
            raise InvalidProjectError("project name must not be empty")
        self.ensure_dir()
        created = self._clock()
        project = Project(
            id=str(uuid.uuid4()),
            path=storage.unique_project_path(self._notes_dir, display_name),
            name=display_name,
            created_at=created,
            updated_at=created,
        )
        storage.write_project(project)
        return project

    def rename_project(self, project_id: str, name: str) -> Project:
        """Rename project metadata and its safe folder without changing identity."""
        display_name = str(name).strip()
        if not display_name:
            raise InvalidProjectError("project name must not be empty")
        project = self.load_project(project_id)
        previous_path = project.path
        previous_name = project.name
        previous_updated = project.updated_at
        target = storage.unique_project_path(
            self._notes_dir,
            display_name,
            excluding=previous_path,
        )
        try:
            if target != previous_path:
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(previous_path, target)
            project.path = target
            project.name = display_name
            project.updated_at = self._clock()
            storage.write_project(project)
        except (OSError, StorageError):
            if target != previous_path and target.exists() and not previous_path.exists():
                os.replace(target, previous_path)
            project.path = previous_path
            project.name = previous_name
            project.updated_at = previous_updated
            raise
        return project

    def set_project_icon(self, project_id: str, icon: str | None) -> Project:
        """Set (or clear) a project's optional icon.

        Presentation only: the project's UUID, folder, name, and notes are all
        untouched. An unknown or malformed value clears the icon rather than
        being stored, so a row can never end up with an undrawable glyph.
        """
        project = self.load_project(project_id)
        project.icon = normalize_project_icon(icon)
        project.updated_at = self._clock()
        storage.write_project(project)
        return project

    # -- Create ---------------------------------------------------------------

    def create_note(
        self,
        title: str = "Untitled Note",
        category: str = DEFAULT_CATEGORY,
        *,
        project_id: str | None = None,
    ) -> Note:
        """Create, persist, and return a new note."""
        validate_category(category)
        self.ensure_dir()
        project = self.load_project(project_id) if project_id else None
        created = self._clock()
        filename = storage.build_filename(title)
        directory = project.path if project is not None else self._notes_dir
        path = storage.unique_path(directory, filename)
        note = Note(
            id=str(uuid.uuid4()),
            path=path,
            title=title,
            body="",
            category=category,
            created_at=created,
            updated_at=created,
            transcript=[],
            project_id=project.id if project is not None else None,
        )
        storage.write_note(note)
        return note

    # -- Read -----------------------------------------------------------------

    def load_note(self, note_id: str) -> Note:
        """Load a note by id, or raise :class:`NoteNotFoundError`."""
        path = self.path_for(note_id)
        if not path.exists():
            raise NoteNotFoundError(f"note not found: {note_id}")
        note = storage.read_note(path)
        if note.id != note_id and note.legacy_id != note_id:
            raise NoteNotFoundError(f"note not found: {note_id}")
        note.project_id = self._project_id_for_path(path)
        return note

    def list_notes(self) -> list[Note]:
        """Return all notes, most recently updated first."""
        notes = []
        for path in storage.list_note_paths(self._notes_dir):
            note = storage.read_note(path)
            note.project_id = self._project_id_for_path(path)
            notes.append(note)
        notes.sort(key=lambda n: n.updated_at, reverse=True)
        return notes

    def _project_id_for_path(self, path: Path) -> str | None:
        return next(
            (project.id for project in self.list_projects() if path.parent == project.path),
            None,
        )

    # -- Update ---------------------------------------------------------------

    def save_note(self, note: Note, *, commit_title: bool = False) -> None:
        """Persist, then optionally commit a safe title-derived filename."""
        storage.write_note(note)
        if commit_title:
            storage.commit_title_filename(note)

    def update_title(self, note_id: str, title: str) -> Note:
        """Update a note title and commit its collision-safe filename."""
        note = self.load_note(note_id)
        note.set_title(title, self._clock())
        storage.write_note(note)
        storage.commit_title_filename(note)
        return note

    def rename_filename(self, note_id: str, requested: str) -> Note:
        """Commit a manual safe filename without changing title or stable id."""
        note = self.load_note(note_id)
        previous_mode = note.metadata.get("Filename-Mode")
        note.metadata["Filename-Mode"] = "manual"
        storage.write_note(note)
        try:
            storage.commit_manual_filename(note, requested)
        except StorageError:
            if previous_mode is None:
                note.metadata.pop("Filename-Mode", None)
            else:
                note.metadata["Filename-Mode"] = previous_mode
            storage.write_note(note)
            raise
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

    # -- Project membership ---------------------------------------------------

    def move_note_to_project(self, note_id: str, project_id: str | None) -> Note:
        """Move a note between Unfiled and a project, preserving UUID/attachments."""
        note = self.load_note(note_id)
        project = self.load_project(project_id) if project_id else None
        destination_dir = project.path if project is not None else self._notes_dir
        destination_dir.mkdir(parents=True, exist_ok=True)
        old_path = note.path
        old_body = note.body
        old_project_id = note.project_id
        target = storage.unique_path(
            destination_dir,
            old_path.name,
            excluding=old_path,
        )
        if target == old_path and old_project_id == project_id:
            return note
        note.body = self._body_for_moved_note(note, target)
        note.project_id = project.id if project is not None else None
        try:
            os.replace(old_path, target)
            note.path = target
            storage.write_note(note)
        except (OSError, StorageError):
            if target.exists() and not old_path.exists():
                os.replace(target, old_path)
            note.path = old_path
            note.body = old_body
            note.project_id = old_project_id
            raise
        return note

    def remove_note_from_project(self, note_id: str) -> Note:
        return self.move_note_to_project(note_id, None)

    def _body_for_moved_note(self, note: Note, new_path: Path) -> str:
        managed_root = note_attachment_dir(self._notes_dir, note.id).resolve()
        changed = False
        blocks = parse_blocks(note.body)
        for block in blocks:
            if block.kind not in (BlockType.IMAGE, BlockType.FILE) or not block.target:
                continue
            candidate = (note.path.parent / block.target).resolve()
            try:
                candidate.relative_to(managed_root)
            except ValueError:
                continue
            block.target = Path(os.path.relpath(candidate, new_path.parent)).as_posix()
            changed = True
        return serialize_blocks(blocks) if changed else note.body

    def delete_project(self, project_id: str, *, move_notes_to_unfiled: bool = False) -> Path:
        """Delete a project safely, never deleting its notes implicitly."""
        project = self.load_project(project_id)
        notes = [note for note in self.list_notes() if note.project_id == project.id]
        if notes and not move_notes_to_unfiled:
            raise ProjectNotEmptyError(f'project "{project.name}" contains {len(notes)} note(s)')
        for note in notes:
            self.remove_note_from_project(note.id)
        self._delete(project.path)
        return project.path

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
        """Stage note and attachments together, then invoke the delete strategy."""
        path = self.path_for(note_id)
        if not path.exists():
            raise NoteNotFoundError(f"note not found: {note_id}")
        note = storage.read_note(path)
        attachment_dir = note_attachment_dir(self._notes_dir, note.id)
        app_directory = self._notes_dir.parent
        app_directory.mkdir(parents=True, exist_ok=True)
        stage = Path(
            tempfile.mkdtemp(
                prefix=f"StormPad-{storage.slugify(note.title)}-",
                dir=app_directory,
            )
        )
        staged_note = stage / "Notes" / path.name
        staged_attachments = stage / "Attachments" / note.id
        staged_note.parent.mkdir(parents=True, exist_ok=True)
        moved_attachments = False
        try:
            os.replace(path, staged_note)
            if attachment_dir.exists():
                staged_attachments.parent.mkdir(parents=True, exist_ok=True)
                os.replace(attachment_dir, staged_attachments)
                moved_attachments = True
            self._delete(stage)
        except Exception:
            if moved_attachments and staged_attachments.exists():
                attachment_dir.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staged_attachments, attachment_dir)
            if staged_note.exists():
                os.replace(staged_note, path)
            shutil.rmtree(stage, ignore_errors=True)
            raise
        return path
