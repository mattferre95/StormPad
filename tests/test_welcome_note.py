"""Tests for the bundled welcome note and its one-time workspace installation."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from stormpad import storage, welcome
from stormpad.block_parser import parse_blocks
from stormpad.block_serializer import serialize_blocks
from stormpad.blocks import BlockType
from stormpad.errors import AtomicWriteError
from stormpad.preferences import InMemoryBackend, Preferences
from stormpad.session import NoteStore
from stormpad.uihelpers import choose_selected_note

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def prefs() -> Preferences:
    return Preferences(InMemoryBackend())


@pytest.fixture
def notes_dir(tmp_path: Path) -> Path:
    """A path for a workspace that does not exist yet (a truly new install)."""
    return tmp_path / "StormPad" / "Notes"


@pytest.fixture
def store(notes_dir: Path) -> NoteStore:
    return NoteStore(notes_dir)


# --- New workspace ------------------------------------------------------------


def test_new_workspace_receives_exactly_one_welcome_note(store, prefs):
    installed = welcome.install_starter_template(store, prefs)

    assert installed is not None
    notes = store.list_notes()
    assert len(notes) == 1
    assert notes[0].id == installed.id


def test_welcome_note_title_is_correct(store, prefs):
    welcome.install_starter_template(store, prefs)

    (note,) = store.list_notes()
    assert note.title == "Welcome to StormPad"
    assert note.title == welcome.WELCOME_TITLE


def test_welcome_note_opening_copy_is_correct(store, prefs):
    welcome.install_starter_template(store, prefs)

    (note,) = store.list_notes()
    first = parse_blocks(note.body)[0]
    assert first.kind == BlockType.TEXT
    assert first.text == (
        "This note shows everything you can create. Edit it, experiment with it, "
        "or delete it whenever you are ready."
    )
    assert first.text == welcome.WELCOME_OPENING


def test_welcome_note_is_unfiled_and_not_pinned(store, prefs):
    welcome.install_starter_template(store, prefs)

    (note,) = store.list_notes()
    assert note.project_id is None
    assert note.path.parent == store.notes_dir
    assert store.list_projects() == []
    assert prefs.pinned_note_ids == []


def test_welcome_note_is_the_initial_selection(store, prefs):
    installed = welcome.install_starter_template(store, prefs)

    selected = choose_selected_note(store.list_notes(), prefs.last_note_id)
    assert selected is not None
    assert selected.id == installed.id


def test_welcome_note_is_an_ordinary_local_markdown_file(store, prefs):
    installed = welcome.install_starter_template(store, prefs)

    assert installed.path.suffix == ".md"
    assert installed.path.name == "welcome-to-stormpad.md"
    reloaded = store.load_note(installed.id)
    assert reloaded.body == installed.body
    assert reloaded.title == installed.title


# --- One-time installation ----------------------------------------------------


def test_relaunch_does_not_create_a_duplicate(store, prefs):
    welcome.install_starter_template(store, prefs)

    assert welcome.install_starter_template(store, prefs) is None
    assert welcome.install_starter_template(store, prefs) is None
    assert len(store.list_notes()) == 1


def test_renaming_the_welcome_note_does_not_create_another_copy(store, prefs):
    installed = welcome.install_starter_template(store, prefs)
    store.update_title(installed.id, "My Working Notes")

    assert welcome.install_starter_template(store, prefs) is None
    (note,) = store.list_notes()
    assert note.title == "My Working Notes"


def test_moving_the_welcome_note_into_a_project_does_not_create_another_copy(store, prefs):
    installed = welcome.install_starter_template(store, prefs)
    project = store.create_project("Ideas")
    store.move_note_to_project(installed.id, project.id)

    assert welcome.install_starter_template(store, prefs) is None
    (note,) = store.list_notes()
    assert note.project_id == project.id


def test_deleting_the_welcome_note_does_not_recreate_it(store, prefs):
    installed = welcome.install_starter_template(store, prefs)
    store.delete_note(installed.id)

    assert welcome.install_starter_template(store, prefs) is None
    assert store.list_notes() == []


# --- Existing workspaces ------------------------------------------------------


def test_existing_workspace_with_notes_does_not_receive_it(notes_dir, prefs):
    existing = NoteStore(notes_dir)
    existing.create_note("A note I already wrote")

    assert welcome.install_starter_template(existing, prefs) is None
    (note,) = existing.list_notes()
    assert note.title == "A note I already wrote"
    assert prefs.starter_template_installed is True


def test_existing_empty_workspace_with_prior_metadata_does_not_receive_it(notes_dir, prefs):
    # An established user who deleted every note: the directory exists, so the
    # workspace is not new even though it holds nothing.
    notes_dir.mkdir(parents=True)
    store = NoteStore(notes_dir)

    assert welcome.install_starter_template(store, prefs) is None
    assert store.list_notes() == []
    assert prefs.starter_template_installed is True


def test_workspace_is_new_only_before_the_notes_directory_exists(notes_dir):
    assert welcome.workspace_is_new(notes_dir) is True
    notes_dir.mkdir(parents=True)
    assert welcome.workspace_is_new(notes_dir) is False


def test_failed_installation_does_not_mark_completion(store, prefs, monkeypatch):
    def explode(note):
        raise AtomicWriteError("disk is full")

    monkeypatch.setattr(storage, "write_note", explode)

    with pytest.raises(AtomicWriteError):
        welcome.install_starter_template(store, prefs)

    assert prefs.starter_template_installed is False
    assert store.list_notes() == []

    # The next launch retries and succeeds without leaving a duplicate behind.
    monkeypatch.undo()
    assert welcome.install_starter_template(store, prefs) is not None
    assert len(store.list_notes()) == 1


# --- Bundled template ---------------------------------------------------------


def test_template_round_trips_through_parser_and_serializer():
    body = welcome.load_template().body

    assert serialize_blocks(parse_blocks(body)) == body


def test_template_survives_a_full_note_round_trip(store, prefs):
    installed = welcome.install_starter_template(store, prefs)

    reparsed = storage.parse(storage.serialize(installed), path=installed.path)
    assert reparsed.body == installed.body
    assert reparsed.title == installed.title
    assert [block.kind for block in parse_blocks(reparsed.body)] == [
        block.kind for block in parse_blocks(installed.body)
    ]


def test_template_contains_all_supported_heading_levels():
    kinds = [block.kind for block in parse_blocks(welcome.load_template().body)]

    assert BlockType.HEADING_1 in kinds
    assert BlockType.HEADING_2 in kinds
    assert BlockType.HEADING_3 in kinds


def test_template_contains_the_demonstrated_block_types():
    kinds = [block.kind for block in parse_blocks(welcome.load_template().body)]

    for kind in (
        BlockType.TODO,
        BlockType.BULLET,
        BlockType.NUMBERED,
        BlockType.QUOTE,
        BlockType.DIVIDER,
        BlockType.LINK,
    ):
        assert kind in kinds, f"template is missing a {kind.value} block"

    todos = [block for block in parse_blocks(welcome.load_template().body)
             if block.kind == BlockType.TODO]
    assert any(block.checked for block in todos)
    assert any(not block.checked for block in todos)


def test_template_demonstrates_inline_formatting():
    from stormpad.blocks import MarkType

    marks = {
        mark.kind
        for block in parse_blocks(welcome.load_template().body)
        for run in block.runs
        for mark in run.marks
    }

    assert MarkType.BOLD in marks
    assert MarkType.ITALIC in marks
    assert MarkType.UNDERLINE in marks
    assert MarkType.TEXT_COLOR in marks
    assert MarkType.HIGHLIGHT in marks
    assert MarkType.LINK in marks


def test_template_links_to_the_official_website():
    targets = {
        mark.value
        for block in parse_blocks(welcome.load_template().body)
        for run in block.runs
        for mark in run.marks
    } | {
        block.target
        for block in parse_blocks(welcome.load_template().body)
        if block.target
    }

    assert "https://mattferre95.github.io/StormPad/" in targets


def test_template_has_no_broken_attachment_references():
    blocks = parse_blocks(welcome.load_template().body)

    assert not [block for block in blocks if block.kind in (BlockType.IMAGE, BlockType.FILE)]
    for block in blocks:
        target = block.target or ""
        assert "Attachments" not in target
        assert not target.startswith(("./", "../"))


def test_template_uses_no_em_dashes():
    assert "—" not in welcome.template_text()


def test_bundled_resource_is_included_by_package_configuration():
    resource = ROOT / "stormpad" / "resources" / "welcome_note.md"
    assert resource.is_file()
    assert welcome.template_text() == resource.read_text(encoding="utf-8")

    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package_data = config["tool"]["setuptools"]["package-data"]
    assert "*.md" in package_data["stormpad.resources"]

    py2app_config = (ROOT / "release" / "setup_app.py").read_text(encoding="utf-8")
    assert '"packages": ["stormpad"]' in py2app_config
