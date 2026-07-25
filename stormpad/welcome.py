"""One-time installation of the bundled starter note into a new workspace.

StormPad ships a single starter template, ``resources/welcome_note.md``. The
first time a genuinely new workspace is initialized it is copied in through the
normal storage layer, becoming an ordinary local Markdown note the user owns:
editable, renameable, movable, pinnable, and permanently deletable.

Installation happens exactly once per workspace. A durable preferences marker
(:data:`STARTER_TEMPLATE_KEY`) records it, so the note is never recreated after
a relaunch, an update, a rename, a move, or a deletion. The marker is written
*after* a successful copy, so a failed write is retried on the next launch
instead of being silently recorded as done.

Pure and AppKit-free, so the whole behavior is testable against a temporary
directory.
"""

from __future__ import annotations

import uuid
from importlib import resources
from pathlib import Path

from . import storage
from .models import Note, now_local
from .preferences import Preferences
from .session import NoteStore

TEMPLATE_PACKAGE = "stormpad.resources"
TEMPLATE_FILENAME = "welcome_note.md"

#: Title and opening line are part of the product copy and are asserted in
#: tests and in package verification.
WELCOME_TITLE = "Welcome to StormPad"
WELCOME_OPENING = (
    "This note shows everything you can create. Edit it, experiment with it, "
    "or delete it whenever you are ready."
)


def template_text() -> str:
    """Read the bundled starter template.

    Uses :mod:`importlib.resources` so the lookup works the same from a source
    checkout, an editable install, and the packaged ``.app``.
    """
    return (
        resources.files(TEMPLATE_PACKAGE)
        .joinpath(TEMPLATE_FILENAME)
        .read_text(encoding="utf-8")
    )


def load_template() -> Note:
    """Parse the bundled template with the production Markdown parser.

    The template carries no ``ID`` or timestamps; identity and dates belong to
    the copy that lands in the user's workspace, not to the shipped resource.
    """
    return storage.parse(template_text(), path=Path(TEMPLATE_FILENAME))


def workspace_is_new(notes_dir: Path | str) -> bool:
    """Whether ``notes_dir`` belongs to a workspace StormPad has never set up.

    A workspace is new only when the notes directory does not exist yet. An
    existing directory means StormPad already ran here, even when the user has
    since deleted every note. Callers must therefore ask *before* creating the
    directory.
    """
    return not Path(notes_dir).exists()


def install_starter_template(
    store: NoteStore,
    preferences: Preferences,
    *,
    clock=now_local,
) -> Note | None:
    """Install the starter note once, returning it only when it was created.

    Returns ``None`` when the marker is already set, or when the workspace
    predates this feature. In that second case the marker is recorded without
    touching any existing note, so an established user never receives the
    starter note retroactively.

    Raises whatever the storage layer raises on a failed write, leaving the
    marker unset so the next launch can retry.
    """
    if preferences.starter_template_installed:
        return None
    if not workspace_is_new(store.notes_dir):
        preferences.starter_template_installed = True
        return None

    note = _import_template(store, clock)
    preferences.starter_template_installed = True
    return note


def _import_template(store: NoteStore, clock) -> Note:
    """Copy the template into the workspace with a single atomic write.

    A failure rolls the empty notes directory back, so the next launch still
    sees a new workspace and can retry instead of silently skipping the note.
    """
    template = load_template()
    notes_dir = store.ensure_dir()
    created = clock()
    note = Note(
        id=str(uuid.uuid4()),
        path=storage.unique_path(notes_dir, storage.build_filename(template.title)),
        title=template.title,
        body=template.body,
        category=template.category,
        created_at=created,
        updated_at=created,
    )
    try:
        storage.write_note(note)
    except Exception:
        _remove_if_empty(notes_dir)
        raise
    return note


def _remove_if_empty(directory: Path) -> None:
    """Remove a directory only while it is still empty; never force anything."""
    try:
        directory.rmdir()
    except OSError:
        pass
