"""Native editor behaviour for collapsible toggles.

The point of these is content safety. Collapsing is layout-only, so the checks
that matter most are that the text storage and the serialized note stay complete
while blocks are hidden, and that a caret can never end up inside a hidden run.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from AppKit import (
    NSApplication,
    NSBackingStoreBuffered,
    NSTitledWindowMask,
    NSWindow,
)
from Foundation import NSMakeRange, NSMakeRect

from stormpad.block_parser import parse_blocks
from stormpad.blocks import BlockType, is_toggle
from stormpad.collapse import hidden_indexes
from stormpad.models import IDEAS, Note
from stormpad.theme import get_theme
from stormpad.views.block_editor import Editor
from stormpad.views.palette import Palette

TOGGLE_LIST_NOTE = (
    '<!-- stormpad:toggle collapsed="false" -->\n'
    "- Launch checklist\n\n"
    "  - Finalize homepage\n\n"
    "  - Build the DMG\n\n"
    "Normal paragraph outside the toggle"
)

TOGGLE_HEADING_NOTE = (
    '<!-- stormpad:toggle collapsed="false" -->\n'
    "## Product direction\n\n"
    "Normal paragraph\n\n"
    "- Bulleted list\n\n"
    "### Native experience\n\n"
    "More content\n\n"
    "## Next major section"
)


def _editor(body, theme_id="deep_dark"):
    NSApplication.sharedApplication()
    editor = Editor.alloc().initWithPalette_onTitle_onBody_onAttachment_(
        Palette(get_theme(theme_id)),
        lambda _text: None,
        lambda _text: None,
        lambda _path, _managed: None,
    )
    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, 900, 700), NSTitledWindowMask, NSBackingStoreBuffered, False
    )
    editor.view.setFrame_(window.contentView().bounds())
    window.contentView().addSubview_(editor.view)
    now = datetime.now()
    editor.load_note(
        Note(
            id="toggle",
            path=Path("/tmp/toggle.md"),
            title="Toggle",
            body=body,
            category=IDEAS,
            created_at=now,
            updated_at=now,
        )
    )
    return editor, window


def _line_start(editor, block_index):
    lines = str(editor._body.string()).split("\n")
    return sum(len(line) + 1 for line in lines[:block_index])


def _collapse_first_toggle(editor):
    editor.toggle_collapsed_at_location(_line_start(editor, 0))


# --- content safety while collapsed -------------------------------------------


@pytest.mark.parametrize("body", [TOGGLE_LIST_NOTE, TOGGLE_HEADING_NOTE])
def test_collapsing_keeps_the_whole_note_in_storage_and_markdown(body):
    """The heart of the feature: hiding must not subtract anything."""
    editor, window = _editor(body)
    try:
        before_storage = str(editor._body.string())
        before_markdown = editor.body_text()

        _collapse_first_toggle(editor)

        # Text storage is untouched apart from the chevron glyph.
        after_storage = str(editor._body.string())
        assert after_storage.replace("▸", "▾") == before_storage
        # Autosave persists body_text(), so this is the anti-data-loss assertion.
        assert editor.body_text().replace(
            'collapsed="true"', 'collapsed="false"'
        ) == before_markdown
        assert hidden_indexes(editor._extract_blocks())
    finally:
        window.close()


@pytest.mark.parametrize("body", [TOGGLE_LIST_NOTE, TOGGLE_HEADING_NOTE])
def test_expanding_restores_identical_content(body):
    editor, window = _editor(body)
    try:
        original = editor.body_text()
        _collapse_first_toggle(editor)
        _collapse_first_toggle(editor)
        assert editor.body_text() == original
        assert hidden_indexes(editor._extract_blocks()) == frozenset()
    finally:
        window.close()


def test_hidden_children_are_still_present_for_search_and_export():
    editor, window = _editor(TOGGLE_LIST_NOTE)
    try:
        _collapse_first_toggle(editor)
        markdown = editor.body_text()
        # Search, export, sharing, and Copy Note all read the full note text.
        assert "Finalize homepage" in markdown
        assert "Build the DMG" in markdown
        assert "Finalize homepage" in str(editor._body.string())
    finally:
        window.close()


def test_collapse_metadata_never_appears_in_plain_text_export():
    from stormpad.exporter import note_to_plain_text

    editor, window = _editor(TOGGLE_LIST_NOTE)
    try:
        _collapse_first_toggle(editor)
        now = datetime.now()
        note = Note(
            id="t",
            path=Path("/tmp/t.md"),
            title="Toggle",
            body=editor.body_text(),
            category=IDEAS,
            created_at=now,
            updated_at=now,
        )
        plain = note_to_plain_text(note)
        assert "stormpad:toggle" not in plain
        assert "collapsed=" not in plain
        assert "Finalize homepage" in plain
        assert "Build the DMG" in plain
    finally:
        window.close()


# --- presentation --------------------------------------------------------------


def test_chevron_reflects_and_changes_state():
    editor, window = _editor(TOGGLE_LIST_NOTE)
    try:
        assert "▾ Launch checklist" in str(editor._body.string())
        _collapse_first_toggle(editor)
        assert "▸ Launch checklist" in str(editor._body.string())
        assert editor._extract_blocks()[0].collapsed is True
        _collapse_first_toggle(editor)
        assert "▾ Launch checklist" in str(editor._body.string())
        assert editor._extract_blocks()[0].collapsed is False
    finally:
        window.close()


def test_collapsing_hides_layout_without_shrinking_storage():
    editor, window = _editor(TOGGLE_LIST_NOTE)
    try:
        manager = editor._body.layoutManager()
        container = editor._body.textContainer()
        manager.ensureLayoutForTextContainer_(container)
        expanded_height = manager.usedRectForTextContainer_(container)[1][1]
        storage_length = editor._body.textStorage().length()

        _collapse_first_toggle(editor)
        manager.ensureLayoutForTextContainer_(container)
        collapsed_height = manager.usedRectForTextContainer_(container)[1][1]

        assert collapsed_height < expanded_height
        assert editor._body.textStorage().length() == storage_length
    finally:
        window.close()


@pytest.mark.parametrize("theme_id", ["storm_blue", "deep_dark", "light"])
def test_toggle_heading_uses_the_same_typography_as_a_normal_heading(theme_id):
    from AppKit import NSFontAttributeName

    from stormpad.blocks import Block

    editor, window = _editor(TOGGLE_HEADING_NOTE, theme_id)
    try:
        plain = editor._block_base_attributes(Block(kind=BlockType.HEADING_2))
        toggled = editor._block_base_attributes(Block(kind=BlockType.TOGGLE_HEADING_2))
        assert toggled[NSFontAttributeName] == plain[NSFontAttributeName]
    finally:
        window.close()


# --- caret safety --------------------------------------------------------------


def test_collapsing_with_the_caret_inside_a_child_moves_it_to_the_parent():
    editor, window = _editor(TOGGLE_LIST_NOTE)
    try:
        child_start = _line_start(editor, 1)
        editor._body.setSelectedRange_(NSMakeRange(child_start + 2, 0))
        _collapse_first_toggle(editor)

        caret = int(editor._body.selectedRange().location)
        assert not editor._location_is_hidden(caret)
        assert caret < _line_start(editor, 1)
    finally:
        window.close()


def test_a_caret_cannot_be_placed_inside_hidden_content():
    editor, window = _editor(TOGGLE_LIST_NOTE)
    try:
        _collapse_first_toggle(editor)
        hidden_location = _line_start(editor, 1) + 1
        assert editor._location_is_hidden(hidden_location)

        editor._body.setSelectedRange_(NSMakeRange(hidden_location, 0))
        editor._move_caret_out_of_hidden()
        assert not editor._location_is_hidden(int(editor._body.selectedRange().location))
    finally:
        window.close()


def test_selection_guard_redirects_a_hidden_target():
    editor, window = _editor(TOGGLE_LIST_NOTE)
    try:
        _collapse_first_toggle(editor)
        hidden_location = _line_start(editor, 1) + 1
        result = editor.textView_willChangeSelectionFromCharacterRange_toCharacterRange_(
            editor._body, NSMakeRange(0, 0), NSMakeRange(hidden_location, 0)
        )
        assert not editor._location_is_hidden(int(result.location))
    finally:
        window.close()


# --- editing ------------------------------------------------------------------


def test_return_on_a_collapsed_summary_expands_and_focuses_a_child():
    editor, window = _editor(TOGGLE_LIST_NOTE)
    try:
        _collapse_first_toggle(editor)
        blocks = editor._extract_blocks()
        assert blocks[0].collapsed is True

        editor._body.setSelectedRange_(NSMakeRange(_line_start(editor, 1) - 1, 0))
        assert editor._toggle_return(editor._extract_blocks(), 0) is True

        blocks = editor._extract_blocks()
        assert blocks[0].collapsed is False
        assert hidden_indexes(blocks) == frozenset()
        caret = int(editor._body.selectedRange().location)
        assert not editor._location_is_hidden(caret)
    finally:
        window.close()


def test_return_on_a_childless_summary_creates_one_child():
    editor, window = _editor('<!-- stormpad:toggle collapsed="false" -->\n- Lonely')
    try:
        assert editor._toggle_return(editor._extract_blocks(), 0) is True
        blocks = editor._extract_blocks()
        assert len(blocks) == 2
        assert blocks[1].indent == blocks[0].indent + 1
        assert blocks[1].kind == BlockType.BULLET
    finally:
        window.close()


def test_converting_a_collapsed_toggle_reveals_its_content_first():
    editor, window = _editor(TOGGLE_LIST_NOTE)
    try:
        _collapse_first_toggle(editor)
        assert hidden_indexes(editor._extract_blocks())

        editor._convert_block_at_index(BlockType.TEXT, 0)

        blocks = editor._extract_blocks()
        assert blocks[0].kind == BlockType.TEXT
        assert not any(is_toggle(block) for block in blocks)
        assert hidden_indexes(blocks) == frozenset()
        assert "Finalize homepage" in editor.body_text()
    finally:
        window.close()


def test_undo_restores_collapse_state_without_losing_content():
    editor, window = _editor(TOGGLE_LIST_NOTE)
    try:
        original = editor.body_text()
        _collapse_first_toggle(editor)
        assert editor._extract_blocks()[0].collapsed is True

        editor._body.undoManager().undo()

        blocks = editor._extract_blocks()
        assert blocks[0].collapsed is False
        assert editor.body_text() == original
        assert not editor._location_is_hidden(int(editor._body.selectedRange().location))
    finally:
        window.close()


def test_save_and_reopen_preserves_nested_collapse_state():
    nested = (
        '<!-- stormpad:toggle collapsed="false" -->\n'
        "- Outer\n\n"
        '<!-- stormpad:toggle collapsed="true" -->\n'
        "  - Inner\n\n"
        "    - Inner child\n\n"
        "  - Outer child"
    )
    editor, window = _editor(nested)
    try:
        saved = editor.body_text()
    finally:
        window.close()

    reopened, window = _editor(saved)
    try:
        blocks = reopened._extract_blocks()
        assert [block.collapsed for block in blocks if is_toggle(block)] == [False, True]
        assert "Inner child" in reopened.body_text()
        assert parse_blocks(saved) == parse_blocks(reopened.body_text())
    finally:
        window.close()


# --- paste integration ---------------------------------------------------------


def _plain_pasteboard(value):
    from AppKit import NSPasteboard, NSPasteboardTypeString

    pasteboard = NSPasteboard.pasteboardWithUniqueName()
    pasteboard.declareTypes_owner_([NSPasteboardTypeString], None)
    pasteboard.setString_forType_(value, NSPasteboardTypeString)
    return pasteboard


def test_pasting_into_an_expanded_toggle_child_still_sanitizes():
    """Toggles must not bypass readSelectionFromPasteboard: sanitization."""
    from AppKit import NSForegroundColorAttributeName

    editor, window = _editor(TOGGLE_LIST_NOTE)
    try:
        child_end = _line_start(editor, 2) - 1
        editor._body.setSelectedRange_(NSMakeRange(child_end, 0))
        editor._body.readSelectionFromPasteboard_(_plain_pasteboard(" pasted"))

        assert " pasted" in editor.body_text()
        storage = editor._body.textStorage()
        expected = editor._palette.editor_text
        attrs = storage.attributesAtIndex_effectiveRange_(child_end, None)[0]
        assert attrs.get(NSForegroundColorAttributeName) == expected
    finally:
        window.close()


def test_a_hidden_child_cannot_be_a_paste_target():
    editor, window = _editor(TOGGLE_LIST_NOTE)
    try:
        _collapse_first_toggle(editor)
        hidden_location = _line_start(editor, 1) + 1
        assert editor._location_is_hidden(hidden_location)

        # The selection guard refuses the hidden destination, so a paste can
        # never be aimed into content the user cannot see.
        redirected = editor.textView_willChangeSelectionFromCharacterRange_toCharacterRange_(
            editor._body, NSMakeRange(0, 0), NSMakeRange(hidden_location, 0)
        )
        assert not editor._location_is_hidden(int(redirected.location))
    finally:
        window.close()
