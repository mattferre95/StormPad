#!/usr/bin/env python3
"""Exercise StormPad's real AppKit command path against temporary notes."""

from __future__ import annotations

import os
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


class DragPasteboard:
    def stringForType_(self, pasteboard_type):  # noqa: N802
        return "0"


class DragSender:
    def draggingPasteboard(self):  # noqa: N802
        return DragPasteboard()


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

            controller.showSettings_(None)
            assert controller._settings._window.isVisible()
            controller._settings._window.close()

            editor = controller._editor
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

            editor._select_block(0)
            controller.insertBlockType_(menu_sender(BlockType.HEADING_2.value))
            settle()
            changed = parse_blocks(editor.body_text())
            changed_kinds = [block.kind for block in changed]
            assert changed_kinds == [
                BlockType.TEXT,
                BlockType.HEADING_2,
                BlockType.TEXT,
            ], (editor.body_text(), changed_kinds)

            editor._body.undoManager().undo()
            assert [block.text for block in parse_blocks(editor.body_text())] == [
                "First block.",
                "Second block.",
            ]
            editor._body.undoManager().redo()
            settle()
            assert parse_blocks(editor.body_text())[1].kind == BlockType.HEADING_2

            editor._drag_insertion_index = 3
            assert editor.perform_block_drop(DragSender())
            settle()
            assert parse_blocks(editor.body_text())[-1].text == "First block."
            editor._body.undoManager().undo()
            assert parse_blocks(editor.body_text())[0].text == "First block."

            editor._select_block(2)
            controller.insertBlockType_(menu_sender(BlockType.TRANSCRIPT.value))
            settle()
            assert any(
                block.kind == BlockType.TRANSCRIPT
                for block in parse_blocks(editor.body_text())
            )
            native_transcript = str(editor._body.string())
            assert "No transcript yet" in native_transcript, native_transcript
            editor._context_block_index = 3
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

            controller.flush()
            reloaded = store.load_note(note.id)
            kinds = [block.kind for block in parse_blocks(reloaded.body)]
            assert BlockType.HEADING_2 in kinds
            assert BlockType.TRANSCRIPT in kinds
            assert reloaded.transcript_visible is True
            assert len(reloaded.transcript) == 2

            controller.cleanup()
            controller._window.close()
    finally:
        NSUserDefaults.standardUserDefaults().removePersistentDomainForName_(suite)
    print(
        "NATIVE INTERACTION SMOKE OK: menus, swatches, settings, "
        "insert, drag, transcript, undo, redo, autosave, reload"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
