#!/usr/bin/env python3
"""Exercise StormPad's real AppKit command path against temporary notes."""

from __future__ import annotations

import os
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from AppKit import (
    NSApplication,
    NSButton,
    NSCommandKeyMask,
    NSEvent,
    NSEventTypeKeyDown,
    NSMenuItem,
    NSPasteboard,
)
from Foundation import NSDate, NSRunLoop, NSUserDefaults

from stormpad.app import _build_menu
from stormpad.block_parser import parse_blocks
from stormpad.blocks import Block, BlockType, InlineMark, InlineRun, MarkType
from stormpad.dragdrop import (
    NOTE_PASTEBOARD_TYPE,
    PROJECT_PASTEBOARD_TYPE,
    encode_drag_payload,
)
from stormpad.models import UNFILED_PROJECT_ID
from stormpad.session import NoteStore
from stormpad.window import MainController


def menu_sender(value: str):
    item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Smoke", None, "")
    item.setRepresentedObject_(value)
    return item


def settle() -> None:
    """Close AppKit's event-grouped undo transaction in this no-event-loop smoke."""
    NSRunLoop.currentRunLoop().runUntilDate_(
        NSDate.dateWithTimeIntervalSinceNow_(0.01)
    )


def native_key(window, characters: str, key_code: int, modifiers: int = 0) -> None:
    """Send a constructed native keyDown event through the real first responder."""
    event = NSEvent.keyEventWithType_location_modifierFlags_timestamp_windowNumber_context_characters_charactersIgnoringModifiers_isARepeat_keyCode_(  # noqa: E501
        NSEventTypeKeyDown,
        (0, 0),
        modifiers,
        0.0,
        window.windowNumber(),
        None,
        characters,
        characters,
        False,
        key_code,
    )
    window.firstResponder().keyDown_(event)


def native_text(window, value: str) -> None:
    for character in value:
        native_key(window, character, 0)


class DraggingInfo:
    """Minimal UUID-only native dragging-info stand-in for deterministic smoke."""

    def __init__(self, pasteboard, location):
        self._pasteboard = pasteboard
        self._location = location

    def draggingPasteboard(self):
        return self._pasteboard

    def draggingLocation(self):
        return self._location


def drag_info(pasteboard_type: str, raw: str, row, *, y: float) -> DraggingInfo:
    pasteboard = NSPasteboard.pasteboardWithUniqueName()
    pasteboard.declareTypes_owner_([pasteboard_type], None)
    assert pasteboard.setString_forType_(raw, pasteboard_type)
    location = row.convertPoint_toView_((12.0, y), None)
    return DraggingInfo(pasteboard, location)


def main() -> int:
    suite = "com.stormpad.StormPad.NativeInteractionSmoke"
    os.environ["STORMPAD_DEFAULTS_SUITE"] = suite
    try:
        with TemporaryDirectory(prefix="stormpad-native-smoke-") as temporary:
            os.environ["STORMPAD_SHARE_PREPARE_ONLY"] = "1"
            os.environ["STORMPAD_SHARE_DIR"] = str(Path(temporary) / "ShareExports")
            store = NoteStore(Path(temporary) / "Notes")
            note = store.create_note("Native interaction smoke")
            note.body = "First block.\n\nSecond block."
            store.save_note(note)

            app = NSApplication.sharedApplication()
            controller = MainController.alloc().initWithStore_(store)
            _build_menu(app, controller)
            main_menu = app.mainMenu()
            top_level = [
                str(main_menu.itemAtIndex_(index).submenu().title())
                for index in range(main_menu.numberOfItems())
            ]
            assert top_level == [
                "StormPad",
                "File",
                "Edit",
                "Note",
                "Format",
                "View",
                "Window",
                "Help",
                "Development",
            ]
            file_menu = next(
                main_menu.itemAtIndex_(index).submenu()
                for index in range(main_menu.numberOfItems())
                if str(main_menu.itemAtIndex_(index).submenu().title()) == "File"
            )
            assert any(
                str(file_menu.itemAtIndex_(index).title()) == "Share Note…"
                for index in range(file_menu.numberOfItems())
            )
            assert not controller._share_button.isHidden()
            assert str(controller._share_button.toolTip()) == "Share Note"
            assert str(controller._share_button.accessibilityLabel()) == "Share Note"
            note_writer = controller._note_list.tableView_pasteboardWriterForRow_(
                controller._note_list._table,
                0,
            )
            assert note_writer.stringForType_(NOTE_PASTEBOARD_TYPE) is not None
            format_menu = next(
                main_menu.itemAtIndex_(index).submenu()
                for index in range(main_menu.numberOfItems())
                if str(main_menu.itemAtIndex_(index).submenu().title()) == "Format"
            )
            block_types = next(
                format_menu.itemAtIndex_(index).submenu()
                for index in range(format_menu.numberOfItems())
                if str(format_menu.itemAtIndex_(index).title()) == "Block Type"
            )
            assert block_types.numberOfItems() == 13
            for color_title in ("Text Color", "Highlight Color"):
                colors = next(
                    format_menu.itemAtIndex_(index).submenu()
                    for index in range(format_menu.numberOfItems())
                    if str(format_menu.itemAtIndex_(index).title()) == color_title
                )
                assert colors.numberOfItems() == 9
                assert all(
                    colors.itemAtIndex_(index).image() is not None
                    for index in range(colors.numberOfItems())
                )
                assert str(colors.itemAtIndex_(0).title()) == (
                    "Clear"
                    if color_title == "Text Color"
                    else "Clear / Transparent"
                )

            controller.showSettings_(None)
            assert controller._settings._window.isVisible()
            controller._settings._window.close()

            editor = controller._editor
            assert not hasattr(editor, "_handle")
            assert not hasattr(editor, "_drag_indicator")

            # Real NSTextInputClient key events: title-to-body transition,
            # blank/rapid/Unicode body Return, post-edit continuation, and
            # native undo/redo. These intentionally do not call the delegate
            # command methods directly.
            window = controller._window
            title = editor._title
            window.makeFirstResponder_(title)
            assert title.currentEditor() is not None
            native_key(window, "a", 0, NSCommandKeyMask)
            native_text(window, "My Project Plan")
            native_key(window, "\r", 36)
            assert editor.title_text() == "My Project Plan"
            assert window.firstResponder() is editor._body

            editor._replace_document([Block()], register_undo=False, focus_index=0)
            native_text(window, "First line")
            assert controller._autosave.has_pending
            native_key(window, "\r", 36)
            assert editor.body_text() == "First line"
            assert str(editor._body.string()) == "First line\n\u200b"
            editor._body.undoManager().undo()
            assert editor.body_text() == "First line"
            editor._body.undoManager().redo()
            assert str(editor._body.string()) == "First line\n\u200b"
            native_key(window, "\r", 36)
            assert len(editor._extract_blocks()) == 3

            editor._replace_document(
                [Block.text_block("Alpha Beta")],
                register_undo=False,
                focus_index=0,
            )
            editor.restore_selection((6, 4))
            native_key(window, "\r", 36)
            assert [block.text for block in editor._extract_blocks()] == [
                "Alpha ",
                "",
            ]

            bold = InlineMark(MarkType.BOLD)
            editor._replace_document(
                [
                    Block(
                        runs=[
                            InlineRun("Bold", (bold,)),
                            InlineRun("Tail"),
                        ]
                    )
                ],
                register_undo=False,
                focus_index=0,
            )
            editor.restore_selection((4, 0))
            native_key(window, "\r", 36)
            inline_split = editor._extract_blocks()
            assert [block.text for block in inline_split] == ["Bold", "Tail"]
            assert inline_split[0].runs == [InlineRun("Bold", (bold,))]

            editor._replace_document([Block()], register_undo=False, focus_index=0)
            native_text(window, "Café 🚀")
            native_key(window, "\r", 36)
            assert editor.body_text() == "Café 🚀"
            controller.flush()
            key_reloaded = store.load_note(note.id)
            assert key_reloaded.title == "My Project Plan"
            assert key_reloaded.body == "Café 🚀"

            editor._replace_document(
                [Block.text_block("Item", BlockType.BULLET)],
                register_undo=False,
                focus_index=0,
            )
            native_key(window, "\r", 36)
            continued = editor._extract_blocks()
            assert [block.kind for block in continued] == [
                BlockType.BULLET,
                BlockType.BULLET,
            ]
            editor._replace_document(
                [Block(kind=BlockType.BULLET)],
                register_undo=False,
                focus_index=0,
            )
            native_key(window, "\r", 36)
            assert editor._extract_blocks() == [Block()]

            # Restore the fixture before the broader editor checks.
            note = store.load_note(note.id)
            note.title = "Native interaction smoke"
            note.body = "First block.\n\nSecond block."
            store.save_note(note, commit_title=True)
            controller._replace_displayed(note)
            controller._autosave.reset()
            editor.load_note(store.load_note(note.id))
            editor._body.undoManager().removeAllActions()
            original_body = editor.body_text()
            editor.restore_selection((5, 14))
            editor._body.deleteBackward_(None)
            settle()
            assert len(parse_blocks(editor.body_text())) == 1
            editor._body.undoManager().undo()
            settle()
            assert editor.body_text() == original_body
            editor.restore_selection((0, 5))
            editor.toggleBold_(None)
            editor.toggleItalic_(None)
            editor.toggleUnderline_(None)
            color = NSButton.alloc().init()
            color.setIdentifier_("text:cyan")
            editor.chooseColor_(color)
            formatted_blocks = parse_blocks(editor.body_text())
            assert formatted_blocks[0].runs, editor.body_text()
            formatted = formatted_blocks[0].runs[0]
            assert {mark.kind.value for mark in formatted.marks} == {
                "bold",
                "italic",
                "underline",
                "text_color",
            }
            assert editor.selected_color_token("text") == "cyan"
            editor.restore_selection((0, 10))
            assert editor.selected_color_token("text") == "mixed"
            editor.restore_selection((0, 5))
            settle()
            clear = NSButton.alloc().init()
            clear.setIdentifier_("text:default")
            editor.chooseColor_(clear)
            settle()
            assert editor.selected_color_token("text") == "default"
            assert "data-stormpad-color" not in editor.body_text()
            editor._body.undoManager().undo()
            settle()
            assert editor.selected_color_token("text") == "cyan"
            editor._body.undoManager().redo()
            settle()
            assert editor.selected_color_token("text") == "default"
            highlight = NSButton.alloc().init()
            highlight.setIdentifier_("highlight:yellow")
            editor.chooseColor_(highlight)
            settle()
            assert editor.selected_color_token("highlight") == "yellow"
            transparent = NSButton.alloc().init()
            transparent.setIdentifier_("highlight:default")
            editor.chooseColor_(transparent)
            settle()
            assert editor.selected_color_token("highlight") == "default"
            assert "data-stormpad-highlight" not in editor.body_text()
            editor._body.undoManager().undo()
            settle()
            assert editor.selected_color_token("highlight") == "yellow"
            editor._body.undoManager().redo()
            settle()
            assert editor.selected_color_token("highlight") == "default"

            editor.restore_selection((0, 5))
            controller.insertBlockType_(menu_sender(BlockType.HEADING_2.value))
            settle()
            changed = parse_blocks(editor.body_text())
            changed_kinds = [block.kind for block in changed]
            assert changed_kinds == [
                BlockType.HEADING_2,
                BlockType.TEXT,
            ], (editor.body_text(), changed_kinds)
            assert changed[0].text == "First block."

            editor._body.undoManager().undo()
            assert [block.text for block in parse_blocks(editor.body_text())] == [
                "First block.",
                "Second block.",
            ]
            editor._body.undoManager().redo()
            settle()
            assert parse_blocks(editor.body_text())[0].kind == BlockType.HEADING_2

            full_body_length = int(editor._body.string().length())
            editor.restore_selection((0, full_body_length))
            controller.insertBlockType_(menu_sender(BlockType.QUOTE.value))
            converted = parse_blocks(editor.body_text())
            assert [block.kind for block in converted] == [
                BlockType.QUOTE,
                BlockType.QUOTE,
            ]
            assert [block.text for block in converted] == [
                "First block.",
                "Second block.",
            ]

            editor._select_block(1)
            controller.insertBlockType_(menu_sender(BlockType.TRANSCRIPT.value))
            settle()
            assert any(
                block.kind == BlockType.TRANSCRIPT
                for block in parse_blocks(editor.body_text())
            )
            native_transcript = str(editor._body.string())
            assert "No transcript yet" in native_transcript, native_transcript
            editor._context_block_index = 2
            editor.toggle_current_transcript()
            settle()
            assert "No transcript yet" not in str(editor._body.string())
            editor._body.undoManager().undo()
            restored_transcript = str(editor._body.string())
            assert "No transcript yet" in restored_transcript, restored_transcript

            controller.flush()
            controller.appendTranscript_(None)
            controller.appendTranscript_(None)
            settle()
            assert [chunk.timestamp for chunk in editor._current.transcript] == [
                "00:00:04",
                "00:00:11",
            ]
            editor._context_transcript_chunk = 1
            editor.moveTranscriptChunkUp_(None)
            settle()
            assert [chunk.timestamp for chunk in editor._current.transcript] == [
                "00:00:11",
                "00:00:04",
            ]
            editor._body.undoManager().undo()
            assert [chunk.timestamp for chunk in editor._current.transcript] == [
                "00:00:04",
                "00:00:11",
            ]
            editor._context_transcript_chunk = 1
            editor.removeTranscriptChunk_(None)
            settle()
            assert len(editor._current.transcript) == 1
            editor._body.undoManager().undo()
            assert len(editor._current.transcript) == 2

            image_source = Path(temporary) / "fixture.png"
            image_source.write_bytes(b"not-a-real-image")
            file_source = Path(temporary) / "brief.txt"
            file_source.write_text("attachment survives", encoding="utf-8")
            editor.prepare_block_command(hovered_index=1)
            image_block = controller._attachment_block(
                BlockType.IMAGE.value, image_source
            )
            editor._insert_requested_block(image_block)
            settle()
            editor.prepare_block_command(hovered_index=2)
            file_block = controller._attachment_block(
                BlockType.FILE.value, file_source
            )
            editor._insert_requested_block(file_block)
            settle()
            managed_paths = [
                (editor._current.path.parent / block.target).resolve()
                for block in parse_blocks(editor.body_text())
                if block.kind in (BlockType.IMAGE, BlockType.FILE)
            ]
            assert len(managed_paths) == 2
            assert all(path.exists() for path in managed_paths)

            title_before = editor.title_text()
            body_before = editor.body_text()
            chunks_before = list(editor._current.transcript)
            editor.select_all_note_content()
            selected_all, title_range, body_range = (
                editor.full_note_selection_state()
            )
            assert selected_all
            assert title_range[1] == len(title_before)
            assert body_range == (0, int(editor._body.string().length()))
            assert editor.textView_doCommandBySelector_(
                editor._body, "deleteBackward:"
            )
            assert editor.title_text() == ""
            assert editor.body_text() == ""
            assert editor._current.transcript == []
            assert all(path.exists() for path in managed_paths)
            editor._body.undoManager().undo()
            settle()
            assert editor.title_text() == title_before
            assert editor.body_text() == body_before, (
                editor.body_text(),
                body_before,
            )
            assert editor._current.transcript == chunks_before
            assert all(path.exists() for path in managed_paths)
            editor._body.undoManager().redo()
            settle()
            assert editor.title_text() == ""
            assert editor.body_text() == ""
            assert editor._current.transcript == []
            controller.flush()
            blank_reloaded = store.load_note(note.id)
            assert blank_reloaded.title == "Untitled Note"
            assert blank_reloaded.body == ""
            assert blank_reloaded.transcript == []
            assert blank_reloaded.transcript_visible is False
            editor._body.undoManager().undo()
            settle()
            assert editor.title_text() == title_before
            assert editor.body_text() == body_before
            assert editor._current.transcript == chunks_before

            controller.flush()
            reloaded = store.load_note(note.id)
            kinds = [block.kind for block in parse_blocks(reloaded.body)]
            assert kinds[:2] == [BlockType.QUOTE, BlockType.QUOTE]
            assert BlockType.TRANSCRIPT in kinds
            assert reloaded.transcript_visible is True
            assert len(reloaded.transcript) == 2

            build = store.create_project("Build")
            stormpad_project = store.create_project("StormPad")
            wisperflow_project = store.create_project("WisperFlow")
            controller._prefs.project_order = [
                build.id,
                stormpad_project.id,
                wisperflow_project.id,
            ]
            controller._apply_filter()
            assert all(
                project.id in controller._sidebar._rows
                for project in (build, stormpad_project, wisperflow_project)
            )
            build_row_before_drag = controller._sidebar._rows[build.id]
            assert build_row_before_drag.drag_kind == "project"
            assert "drag source" in str(
                build_row_before_drag.accessibilityLabel()
            )
            assert not hasattr(build_row_before_drag, "_drag_handle")
            row_point = controller._sidebar._nav.convertPoint_fromView_(
                (40.0, 17.0),
                build_row_before_drag,
            )
            assert (
                controller._sidebar._nav.hitTest_(row_point)
                is build_row_before_drag
            )

            target_row = controller._sidebar._rows[wisperflow_project.id]
            project_drag = drag_info(
                PROJECT_PASTEBOARD_TYPE,
                encode_drag_payload(
                    "project",
                    build.id,
                    source_project_id=None,
                    source_index=0,
                ),
                target_row,
                y=32.0,
            )
            assert controller._sidebar.perform_drop(target_row, project_drag)
            settle()
            assert controller._prefs.project_order == [
                stormpad_project.id,
                wisperflow_project.id,
                build.id,
            ]
            controller._editor._body.undoManager().undo()
            settle()
            assert controller._prefs.project_order == [
                build.id,
                stormpad_project.id,
                wisperflow_project.id,
            ]
            controller._editor._body.undoManager().redo()
            settle()
            assert controller._prefs.project_order == [
                stormpad_project.id,
                wisperflow_project.id,
                build.id,
            ]
            order_before_click = list(controller._prefs.project_order)
            controller._sidebar._rows[stormpad_project.id].mouseDown_(None)
            assert controller._project_id == stormpad_project.id
            assert controller._prefs.project_order == order_before_click

            attachment_directory = managed_paths[0].parent
            controller._on_project(UNFILED_PROJECT_ID)
            controller._on_note_selected(note.id)
            stormpad_row = controller._sidebar._rows[stormpad_project.id]
            note_drag = drag_info(
                NOTE_PASTEBOARD_TYPE,
                encode_drag_payload(
                    "note",
                    note.id,
                    source_project_id=UNFILED_PROJECT_ID,
                    source_index=0,
                ),
                stormpad_row,
                y=17.0,
            )
            assert controller._sidebar.perform_drop(stormpad_row, note_drag)
            settle()
            moved = store.load_note(note.id)
            assert moved.project_id == stormpad_project.id
            assert moved.path.parent == stormpad_project.path
            assert attachment_directory.exists()

            build_row = controller._sidebar._rows[build.id]
            between_projects = drag_info(
                NOTE_PASTEBOARD_TYPE,
                encode_drag_payload(
                    "note",
                    note.id,
                    source_project_id=stormpad_project.id,
                    source_index=0,
                ),
                build_row,
                y=17.0,
            )
            assert controller._sidebar.perform_drop(build_row, between_projects)
            settle()
            assert store.load_note(note.id).project_id == build.id
            organization_undo = controller._controller_undo_manager()
            assert str(organization_undo.undoActionName()) == "Move Note", (
                organization_undo.undoActionName(),
                organization_undo.canUndo(),
            )
            organization_undo.undo()
            settle()
            undo_project_id = store.load_note(note.id).project_id
            assert undo_project_id == stormpad_project.id, undo_project_id
            controller._editor._body.undoManager().redo()
            settle()
            assert store.load_note(note.id).project_id == build.id

            unfiled_row = controller._sidebar._rows[UNFILED_PROJECT_ID]
            to_unfiled = drag_info(
                NOTE_PASTEBOARD_TYPE,
                encode_drag_payload(
                    "note",
                    note.id,
                    source_project_id=build.id,
                    source_index=0,
                ),
                unfiled_row,
                y=17.0,
            )
            assert controller._sidebar.perform_drop(unfiled_row, to_unfiled)
            unfiled = store.load_note(note.id)
            assert unfiled.project_id is None
            assert unfiled.path.parent == store.notes_dir
            assert attachment_directory.exists()
            assert controller._sidebar._counts[UNFILED_PROJECT_ID] >= 1

            controller._on_project(build.id)
            controller.newNote_(None)
            project_note = store.load_note(controller._current_id)
            assert project_note.project_id == build.id
            controller.removeNoteFromProject_(None)
            assert store.load_note(project_note.id).project_id is None

            controller._on_project(UNFILED_PROJECT_ID)
            controller._on_note_selected(note.id)
            controller._editor._title.setStringValue_("Shared Current Note")
            controller._on_title_edited("Shared Current Note")
            controller.shareNote_(None)
            shared_note = controller._last_share_path
            assert shared_note is not None and shared_note.exists()
            assert store.notes_dir not in shared_note.parents
            shared_text = shared_note.read_text(encoding="utf-8")
            assert "Shared Current Note" in shared_text
            assert note.id not in shared_text
            assert controller._sharing_picker is not None

            packaged = store.create_note("Build package", project_id=build.id)
            packaged.body = "## Package\n\n- [x] Included"
            store.save_note(packaged)
            original_package = packaged.path.read_bytes()
            controller.shareProject_(menu_sender(build.id))
            shared_project = controller._last_share_path
            assert shared_project is not None and shared_project.suffix == ".zip"
            assert shared_project.exists()
            with zipfile.ZipFile(shared_project) as archive:
                names = archive.namelist()
                assert any(name.endswith("/README.txt") for name in names)
                assert any(name.endswith("/build-package.md") for name in names)
                assert all(".stormpad-project.json" not in name for name in names)
            assert packaged.path.read_bytes() == original_package

            project_menu = controller._sidebar._rows[build.id].project_context_menu()
            project_titles = [
                str(project_menu.itemAtIndex_(index).title())
                for index in range(project_menu.numberOfItems())
            ]
            assert "Share Project…" in project_titles
            assert "Move Project Up" in project_titles
            assert "Move Project Down" in project_titles

            controller.cleanup()
            same_window = controller._window
            assert not same_window.isReleasedWhenClosed()
            same_window.close()
            assert not same_window.isVisible()
            controller.show()
            assert controller._window is same_window
            assert same_window.isVisible()
            same_window.close()
            reopened = MainController.alloc().initWithStore_(store)
            assert [project.id for project in reopened._projects()] == [
                stormpad_project.id,
                wisperflow_project.id,
                build.id,
            ]
            assert store.load_note(note.id).project_id is None
            reopened.cleanup()
            reopened._window.close()
    finally:
        os.environ.pop("STORMPAD_SHARE_PREPARE_ONLY", None)
        os.environ.pop("STORMPAD_SHARE_DIR", None)
        NSUserDefaults.standardUserDefaults().removePersistentDomainForName_(suite)
    print(
        "NATIVE INTERACTION SMOKE OK: menus, swatches, settings, "
        "selection conversion, full-note delete, sharing, project reorder, "
        "note drag, transcript, undo, redo, autosave, reload"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
