"""Block model, Markdown round-trip, and inline formatting tests."""

from __future__ import annotations

import pytest

from stormpad.block_parser import parse_blocks, parse_inline
from stormpad.block_serializer import serialize_blocks, serialize_inline
from stormpad.blocks import (
    Block,
    BlockType,
    InlineMark,
    InlineRun,
    MarkType,
    backspace_empty_result,
    convert_block,
    empty_return_result,
    insert_block,
    move_block,
    next_block_after_return,
    toggle_todo,
)


@pytest.mark.parametrize(
    "markdown,kind",
    [
        ("Plain text", BlockType.TEXT),
        ("# Heading one", BlockType.HEADING_1),
        ("## Heading two", BlockType.HEADING_2),
        ("### Heading three", BlockType.HEADING_3),
        ("- [ ] Task", BlockType.TODO),
        ("- Bullet", BlockType.BULLET),
        ("1. Numbered", BlockType.NUMBERED),
        ("> Quote", BlockType.QUOTE),
        ("---", BlockType.DIVIDER),
        ("[OpenAI](https://openai.com)", BlockType.LINK),
        ("![Mood](../Attachments/id/mood.png)", BlockType.IMAGE),
        ("[Brief.pdf](../Attachments/id/brief.pdf)", BlockType.FILE),
        (
            '<!-- stormpad:transcript collapsed="true" -->',
            BlockType.TRANSCRIPT,
        ),
    ],
)
def test_parse_and_serialize_required_block_types(markdown, kind):
    block = parse_blocks(markdown)[0]
    assert block.kind == kind
    assert parse_blocks(serialize_blocks([block]))[0].kind == kind


def test_empty_body_is_one_clean_text_block():
    blocks = parse_blocks("")
    assert blocks == [Block()]
    assert serialize_blocks(blocks) == ""


def test_unknown_markdown_fence_preserved():
    source = "```custom\nopaque **content**\n```"
    blocks = parse_blocks(source)
    assert blocks[0].kind == BlockType.RAW
    assert serialize_blocks(blocks) == source


def test_block_insert_above_below_convert_and_reorder():
    blocks = [Block.text_block("A"), Block.text_block("B")]
    below, index = insert_block(blocks, 0, Block.text_block("X"))
    assert index == 1
    assert [block.text for block in below] == ["A", "X", "B"]
    above, index = insert_block(blocks, 1, Block.text_block("X"), above=True)
    assert index == 1
    converted = convert_block(above[index], BlockType.HEADING_2)
    assert converted.kind == BlockType.HEADING_2 and converted.text == "X"
    moved, index = move_block(above, 1, -1)
    assert index == 0 and [block.text for block in moved] == ["X", "A", "B"]


def test_list_and_todo_keyboard_transitions():
    bullet = Block.text_block("item", BlockType.BULLET)
    next_block = next_block_after_return(bullet)
    assert next_block.kind == BlockType.BULLET
    assert empty_return_result(Block(kind=BlockType.BULLET)).kind == BlockType.TEXT
    assert empty_return_result(Block(kind=BlockType.TODO)).kind == BlockType.TEXT
    assert backspace_empty_result(Block(kind=BlockType.QUOTE)).kind == BlockType.TEXT


def test_todo_completion():
    todo = Block.text_block("Ship", BlockType.TODO)
    assert toggle_todo(todo).checked is True
    assert toggle_todo(toggle_todo(todo)).checked is False


@pytest.mark.parametrize(
    "mark",
    [
        InlineMark(MarkType.BOLD),
        InlineMark(MarkType.ITALIC),
        InlineMark(MarkType.UNDERLINE),
        InlineMark(MarkType.TEXT_COLOR, "blue"),
        InlineMark(MarkType.HIGHLIGHT, "yellow"),
        InlineMark(MarkType.LINK, "https://example.com"),
    ],
)
def test_inline_format_round_trip(mark):
    runs = [InlineRun("formatted", (mark,))]
    parsed = parse_inline(serialize_inline(runs))
    assert parsed == runs


def test_overlapping_supported_styles_round_trip():
    marks = (
        InlineMark(MarkType.BOLD),
        InlineMark(MarkType.ITALIC),
        InlineMark(MarkType.UNDERLINE),
        InlineMark(MarkType.TEXT_COLOR, "cyan"),
        InlineMark(MarkType.HIGHLIGHT, "purple"),
        InlineMark(MarkType.LINK, "https://example.com/a"),
    )
    runs = [InlineRun("storm", marks)]
    assert parse_inline(serialize_inline(runs)) == runs


def test_unsafe_color_token_rejected():
    with pytest.raises(ValueError):
        InlineMark(MarkType.TEXT_COLOR, "chartreuse")
    unsafe = '<span data-stormpad-color="chartreuse">text</span>'
    serialized = serialize_inline(parse_inline(unsafe))
    assert "data-stormpad-color" not in serialized or "&lt;span" in serialized


def test_html_is_escaped_safely_in_normal_text():
    serialized = serialize_inline([InlineRun("hello <script>alert(1)</script>")])
    assert "<script>" not in serialized
    assert "&lt;script&gt;" in serialized
