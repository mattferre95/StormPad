#!/usr/bin/env python3
"""Exercise StormPad's real AppKit command path against temporary notes."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

from AppKit import NSApplication, NSButton, NSMenuItem
from Foundation import NSDate, NSRunLoop, NSUserDefaults

from stormpad.app import _build_menu
from stormpad.block_parser import parse_blocks
from stormpad.blocks import BlockType
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


def main() -> int:
    suite = "com.stormpad.StormPad.NativeInteractionSmoke"
    os.environ["STORMPAD_DEFAULTS_SUITE"] = suite
    try:
        with TemporaryDirectory(prefix="stormpad-native-smoke-") as temporary:
            store = NoteStore(temporary)
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

            project = store.create_project("Build")
            controller._apply_filter()
            assert project.id in controller._sidebar._rows
            controller._on_project(project.id)
            controller.newNote_(None)
            project_note = store.load_note(controller._current_id)
            assert project_note.project_id == project.id
            controller.removeNoteFromProject_(None)
            assert store.load_note(project_note.id).project_id is None

            controller.cleanup()
            controller._window.close()
    finally:
        NSUserDefaults.standardUserDefaults().removePersistentDomainForName_(suite)
    print(
        "NATIVE INTERACTION SMOKE OK: menus, swatches, settings, "
        "selection conversion, full-note delete, projects, transcript, undo, redo, autosave, reload"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
