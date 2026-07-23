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
    apply_block_command,
    backspace_empty_result,
    convert_block,
    empty_return_result,
    insert_block,
    move_block,
    next_block_after_return,
    reorder_blocks,
    split_runs,
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


@pytest.mark.parametrize(
    "kind",
    [
        BlockType.HEADING_1,
        BlockType.HEADING_2,
        BlockType.HEADING_3,
        BlockType.TODO,
        BlockType.BULLET,
        BlockType.NUMBERED,
        BlockType.QUOTE,
        BlockType.DIVIDER,
        BlockType.TRANSCRIPT,
    ],
)
def test_empty_structural_block_round_trip(kind):
    serialized = serialize_blocks([Block(kind=kind)])
    parsed = parse_blocks(serialized)
    assert parsed == [Block(kind=kind)]


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


@pytest.mark.parametrize("kind", [kind for kind in BlockType if kind != BlockType.RAW])
def test_block_command_converts_empty_text_for_every_required_type(kind):
    requested = Block(
        kind=kind,
        runs=(
            [InlineRun("payload")]
            if kind not in (BlockType.DIVIDER, BlockType.TRANSCRIPT)
            else []
        ),
        checked=kind == BlockType.TODO,
        indent=2,
        target=(
            "target"
            if kind in (BlockType.LINK, BlockType.IMAGE, BlockType.FILE)
            else None
        ),
        alt="alt" if kind == BlockType.IMAGE else None,
        collapsed=kind == BlockType.TRANSCRIPT,
    )
    result, destination = apply_block_command([Block()], 0, requested)
    assert destination == 0
    assert result[0].kind == kind
    assert result[0].runs == requested.runs
    assert result[0].target == requested.target
    assert result[0].alt == requested.alt
    assert result[0].collapsed == requested.collapsed


def test_block_command_inserts_at_explicit_hovered_index():
    blocks = [Block.text_block("A"), Block.text_block("B"), Block.text_block("C")]
    below, destination = apply_block_command(
        blocks, 1, Block.text_block("X", BlockType.HEADING_2)
    )
    assert destination == 2
    assert [block.text for block in below] == ["A", "B", "X", "C"]
    above, destination = apply_block_command(
        blocks,
        1,
        Block.text_block("X", BlockType.HEADING_2),
        option_pressed=True,
    )
    assert destination == 1
    assert [block.text for block in above] == ["A", "X", "B", "C"]


def test_drag_reorder_preserves_complete_payload():
    marks = (
        InlineMark(MarkType.BOLD),
        InlineMark(MarkType.HIGHLIGHT, "yellow"),
    )
    todo = Block(
        kind=BlockType.TODO,
        runs=[InlineRun("Ship it", marks)],
        checked=True,
        indent=3,
    )
    attachment = Block(
        kind=BlockType.FILE,
        runs=[InlineRun("brief.pdf")],
        target="../Attachments/id/brief.pdf",
    )
    transcript = Block(kind=BlockType.TRANSCRIPT, collapsed=True)
    reordered, destination = reorder_blocks(
        [Block.text_block("A"), todo, attachment, transcript], 1, 4
    )
    assert destination == 3
    assert reordered[3] is todo
    assert reordered[3].checked is True
    assert reordered[3].indent == 3
    assert reordered[3].runs == [InlineRun("Ship it", marks)]
    assert reordered[1] is attachment
    assert reordered[2] is transcript


def test_split_runs_preserves_overlapping_marks():
    mark = InlineMark(MarkType.BOLD)
    before, after = split_runs([InlineRun("StormPad", (mark,))], 5)
    assert before == [InlineRun("Storm", (mark,))]
    assert after == [InlineRun("Pad", (mark,))]


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


def test_paragraph_beginning_with_supported_inline_html_is_not_raw():
    marks = (
        InlineMark(MarkType.BOLD),
        InlineMark(MarkType.ITALIC),
        InlineMark(MarkType.UNDERLINE),
        InlineMark(MarkType.TEXT_COLOR, "cyan"),
    )
    block = Block(kind=BlockType.TEXT, runs=[InlineRun("First", marks)])
    parsed = parse_blocks(serialize_blocks([block]))[0]
    assert parsed.kind == BlockType.TEXT
    assert parsed.runs == block.runs


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
