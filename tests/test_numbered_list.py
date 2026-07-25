"""Numbered lists count up on screen while Markdown keeps writing "1.".

The editor used to draw a hard-coded "1. " before every numbered block, so a
three-item list read "1. / 1. / 1." — visible on every new install through the
bundled welcome note. These lock the display counter and, just as importantly,
that the storage format is untouched: the Markdown still serializes each item
as "1.", which is valid and keeps diffs stable when items move.
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

from stormpad.block_serializer import serialize_blocks
from stormpad.blocks import Block, BlockType, numbered_display_number
from stormpad.models import IDEAS, Note
from stormpad.theme import get_theme
from stormpad.views.block_editor import Editor
from stormpad.views.palette import Palette


def _numbered(text: str = "", indent: int = 0) -> Block:
    return Block(kind=BlockType.NUMBERED, runs=[], indent=indent).with_text(text)


# -- the pure counter ----------------------------------------------------------


def test_consecutive_items_count_up():
    blocks = [_numbered("First"), _numbered("Second"), _numbered("Third")]
    assert [numbered_display_number(blocks, i) for i in range(3)] == [1, 2, 3]


def test_a_paragraph_between_lists_starts_a_new_run():
    blocks = [
        _numbered("First"),
        _numbered("Second"),
        Block.text_block("An aside"),
        _numbered("Fresh start"),
        _numbered("Second again"),
    ]
    assert [numbered_display_number(blocks, i) for i in (0, 1, 3, 4)] == [1, 2, 1, 2]


@pytest.mark.parametrize(
    "interrupting",
    [
        Block.text_block("Bullet", BlockType.BULLET),
        Block.text_block("To-do", BlockType.TODO),
        Block(kind=BlockType.DIVIDER),
        Block.text_block("Heading", BlockType.HEADING_1),
        Block.text_block("Heading", BlockType.HEADING_2),
        Block.text_block("Heading", BlockType.HEADING_3),
        Block.text_block("Quote", BlockType.QUOTE),
        Block(kind=BlockType.IMAGE, target="photo.png"),
        Block(kind=BlockType.FILE, target="brief.pdf"),
        Block(kind=BlockType.TRANSCRIPT),
        Block.text_block(""),
    ],
)
def test_any_other_block_at_the_same_level_restarts_the_count(interrupting):
    blocks = [_numbered("First"), interrupting, _numbered("Restarted")]
    assert numbered_display_number(blocks, 2) == 1


def test_a_nested_list_counts_itself_and_leaves_its_parent_alone():
    blocks = [
        _numbered("First"),
        _numbered("Nested one", indent=1),
        _numbered("Nested two", indent=1),
        _numbered("Second"),
    ]
    assert [numbered_display_number(blocks, i) for i in range(4)] == [1, 1, 2, 2]


def test_nested_content_of_any_kind_does_not_break_the_parent_run():
    blocks = [
        _numbered("First"),
        Block.text_block("Sub point", BlockType.BULLET),
        _numbered("Second"),
    ]
    blocks[1].indent = 1
    assert numbered_display_number(blocks, 2) == 2


def test_a_single_item_shows_one():
    assert numbered_display_number([_numbered("Alone")], 0) == 1


def test_removing_an_item_renumbers_the_rest():
    blocks = [_numbered("First"), _numbered("Second"), _numbered("Third")]
    del blocks[1]
    assert [numbered_display_number(blocks, i) for i in range(2)] == [1, 2]


def test_converting_an_item_away_splits_one_run_into_two():
    blocks = [_numbered(str(n)) for n in range(5)]
    assert [numbered_display_number(blocks, i) for i in range(5)] == [1, 2, 3, 4, 5]

    # The middle item becomes a paragraph: the run before it keeps its numbers
    # and the run after it starts over.
    blocks[2] = Block.text_block("Now a paragraph")
    assert [numbered_display_number(blocks, i) for i in (0, 1, 3, 4)] == [1, 2, 1, 2]


def test_converting_a_paragraph_into_an_item_joins_the_runs():
    blocks = [_numbered("First"), Block.text_block("Between"), _numbered("Third")]
    assert [numbered_display_number(blocks, i) for i in (0, 2)] == [1, 1]

    blocks[1] = _numbered("Between")
    assert [numbered_display_number(blocks, i) for i in range(3)] == [1, 2, 3]


def test_the_counter_rejects_blocks_that_carry_no_number():
    with pytest.raises(ValueError):
        numbered_display_number([Block.text_block("Plain")], 0)
    with pytest.raises(IndexError):
        numbered_display_number([_numbered("First")], 4)


# -- what the editor draws -----------------------------------------------------


def _native_editor():
    NSApplication.sharedApplication()
    editor = Editor.alloc().initWithPalette_onTitle_onBody_onAttachment_(
        Palette(get_theme(None)),
        lambda _text: None,
        lambda _text: None,
        lambda _path, _managed: None,
    )
    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, 900, 700),
        NSTitledWindowMask,
        NSBackingStoreBuffered,
        False,
    )
    editor.view.setFrame_(window.contentView().bounds())
    window.contentView().addSubview_(editor.view)
    return editor, window


def _display_lines(editor: Editor, body: str) -> list[str]:
    now = datetime.now()
    editor.load_note(
        Note(
            id="numbered",
            path=Path("/tmp/numbered.md"),
            title="Numbered",
            body=body,
            category=IDEAS,
            created_at=now,
            updated_at=now,
        )
    )
    return str(editor._body.string()).split("\n")


def test_native_list_displays_an_ascending_counter():
    editor, window = _native_editor()
    try:
        lines = _display_lines(editor, "1. First\n1. Second\n1. Third")
        assert lines == ["1. First", "2. Second", "3. Third"]
    finally:
        window.close()


def test_native_display_reaches_double_digits():
    editor, window = _native_editor()
    try:
        lines = _display_lines(editor, "\n".join("1. Item" for _ in range(12)))
        assert lines[9:] == ["10. Item", "11. Item", "12. Item"]
    finally:
        window.close()


def test_native_counter_restarts_after_a_paragraph_and_nests():
    editor, window = _native_editor()
    try:
        lines = _display_lines(
            editor,
            "1. First\n  1. Nested\n1. Second\n\nAn aside\n\n1. Fresh",
        )
        assert [line for line in lines if line.rstrip()] == [
            "1. First",
            "1. Nested",
            "2. Second",
            "An aside",
            "1. Fresh",
        ]
    finally:
        window.close()


def test_native_counter_renumbers_when_an_item_is_inserted_mid_list():
    """Return in the middle pushes the later items' numbers down, live."""
    editor, window = _native_editor()
    try:
        _display_lines(editor, "1. First\n1. Second\n1. Third")
        first_line_end = len("1. First")
        editor._body.setSelectedRange_(NSMakeRange(first_line_end, 0))
        editor._apply_structural_return(editor._extract_blocks(), (first_line_end, 0))
        assert str(editor._body.string()).split("\n") == [
            "1. First",
            "2. ",
            "3. Second",
            "4. Third",
        ]
    finally:
        window.close()


def test_native_counter_renumbers_after_an_item_is_removed():
    editor, window = _native_editor()
    try:
        _display_lines(editor, "1. First\n1. Second\n1. Third")
        blocks = editor._extract_blocks()
        del blocks[1]
        editor._replace_document(blocks, register_undo=False, focus_index=None)
        assert str(editor._body.string()).split("\n") == ["1. First", "2. Third"]
    finally:
        window.close()


def test_native_bullet_and_todo_prefixes_are_unchanged():
    editor, window = _native_editor()
    try:
        lines = _display_lines(
            editor,
            "- One\n- Two\n\n- [ ] Open\n- [x] Done",
        )
        # To-do boxes carry no trailing space; the visual gap is kerning.
        assert [line for line in lines if line.rstrip()] == [
            "• One",
            "• Two",
            "☐Open",
            "☑Done",
        ]
    finally:
        window.close()


def test_the_bundled_welcome_note_numbers_its_list_sequentially():
    from stormpad import welcome

    editor, window = _native_editor()
    try:
        lines = _display_lines(editor, welcome.load_template().body)
        numbered = [
            line
            for line in lines
            if line.startswith(("1. ", "2. ", "3. ")) and "Heading" not in line
        ]
        assert numbered == [
            "1. Write the idea down while it is fresh",
            "2. Give it a title you will recognize later",
            "3. Move it into a Project once it matters",
        ]
    finally:
        window.close()


def test_native_counter_is_display_only_and_never_enters_the_markdown():
    """The prefix is decoration: extraction and storage keep writing 1."""
    editor, window = _native_editor()
    try:
        source = "1. First\n1. Second\n1. Third"
        assert _display_lines(editor, source) == ["1. First", "2. Second", "3. Third"]

        blocks = editor._extract_blocks()
        assert [block.kind for block in blocks] == [BlockType.NUMBERED] * 3
        # The counter is not content: it never lands in the block's text.
        assert [block.text for block in blocks] == ["First", "Second", "Third"]
        # Every stored marker is still "1." — no "2."/"3." leaks into the file.
        stored = editor.body_text()
        assert stored == serialize_blocks(blocks)
        assert [line for line in stored.split("\n") if line] == [
            "1. First",
            "1. Second",
            "1. Third",
        ]
    finally:
        window.close()
