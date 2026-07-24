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
    convert_selected_blocks,
    empty_return_result,
    insert_block,
    insert_block_after_selection,
    merge_empty_block_backward,
    move_block,
    next_block_after_return,
    remove_inline_mark,
    reorder_blocks,
    split_block_after_return,
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
            [InlineRun("payload")] if kind not in (BlockType.DIVIDER, BlockType.TRANSCRIPT) else []
        ),
        checked=kind == BlockType.TODO,
        indent=2,
        target=("target" if kind in (BlockType.LINK, BlockType.IMAGE, BlockType.FILE) else None),
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
    below, destination = apply_block_command(blocks, 1, Block.text_block("X", BlockType.HEADING_2))
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
        BlockType.TEXT,
    ],
)
def test_selected_paragraph_conversion_preserves_content_and_marks(kind):
    marks = (InlineMark(MarkType.BOLD), InlineMark(MarkType.TEXT_COLOR, "blue"))
    source = Block(kind=BlockType.HEADING_2, runs=[InlineRun("Exact text", marks)])
    result = convert_selected_blocks([source], [0], kind)
    assert result[0].kind == kind
    assert result[0].text == "Exact text"
    assert result[0].runs == source.runs
    assert len(result) == 1


def test_selection_spanning_multiple_blocks_converts_once_in_order():
    blocks = [
        Block.text_block("Alpha"),
        Block.text_block("Beta", BlockType.HEADING_3),
        Block(kind=BlockType.DIVIDER),
        Block.text_block("Gamma"),
    ]
    result = convert_selected_blocks(blocks, [0, 1, 2], BlockType.QUOTE)
    assert [(block.kind, block.text) for block in result] == [
        (BlockType.QUOTE, "Alpha"),
        (BlockType.QUOTE, "Beta"),
        (BlockType.DIVIDER, ""),
        (BlockType.TEXT, "Gamma"),
    ]


def test_selected_conversion_survives_markdown_round_trip_without_duplicates():
    source = [
        Block.text_block("Alpha"),
        Block(
            kind=BlockType.TEXT,
            runs=[
                InlineRun(
                    "Beta",
                    (InlineMark(MarkType.BOLD),),
                )
            ],
        ),
    ]
    converted = convert_selected_blocks(
        source,
        [0, 1],
        BlockType.HEADING_2,
    )
    reloaded = parse_blocks(serialize_blocks(converted))
    assert [(block.kind, block.text) for block in reloaded] == [
        (BlockType.HEADING_2, "Alpha"),
        (BlockType.HEADING_2, "Beta"),
    ]
    assert reloaded[1].runs == converted[1].runs


def test_clear_text_color_and_highlight_leave_no_empty_spans():
    runs = [
        InlineRun(
            "mixed",
            (
                InlineMark(MarkType.BOLD),
                InlineMark(MarkType.TEXT_COLOR, "purple"),
                InlineMark(MarkType.HIGHLIGHT, "yellow"),
            ),
        )
    ]
    no_color = remove_inline_mark(runs, MarkType.TEXT_COLOR)
    cleared = remove_inline_mark(no_color, MarkType.HIGHLIGHT)
    assert cleared == [InlineRun("mixed", (InlineMark(MarkType.BOLD),))]
    markdown = serialize_inline(cleared)
    assert "data-stormpad-color" not in markdown
    assert "data-stormpad-highlight" not in markdown
    assert "<span" not in markdown


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


def test_return_splits_normal_block_at_caret_and_preserves_marks():
    bold = InlineMark(MarkType.BOLD)
    block = Block(
        runs=[
            InlineRun("before", (bold,)),
            InlineRun("after", (InlineMark(MarkType.ITALIC),)),
        ]
    )
    first, second = split_block_after_return(block, 4)
    assert first.text == "befo"
    assert second.text == "reafter"
    assert first.runs == [InlineRun("befo", (bold,))]
    assert second.runs[0] == InlineRun("re", (bold,))


def test_return_with_selection_inside_one_block_preserves_selected_text():
    original = Block.text_block("keep this selected text")
    result, destination = insert_block_after_selection([original], [0])
    assert destination == 1
    assert result[0] is original
    assert result[0].text == "keep this selected text"
    assert result[1].is_empty


def test_return_with_selection_spanning_blocks_preserves_every_block():
    original = [Block.text_block("Alpha"), Block.text_block("Beta"), Block.text_block("Gamma")]
    result, destination = insert_block_after_selection(original, [0, 1])
    assert destination == 2
    assert [block.text for block in result] == ["Alpha", "Beta", "", "Gamma"]


def test_return_with_unicode_selection_preserves_graphemes():
    original = Block.text_block("Café 🌩️ 東京")
    result, _destination = insert_block_after_selection([original], [0])
    assert result[0].text == "Café 🌩️ 東京"


def test_return_with_formatted_selection_preserves_runs_exactly():
    marks = (
        InlineMark(MarkType.BOLD),
        InlineMark(MarkType.HIGHLIGHT, "yellow"),
    )
    original = Block(runs=[InlineRun("formatted", marks)])
    result, _destination = insert_block_after_selection([original], [0])
    assert result[0].runs == [InlineRun("formatted", marks)]


def test_rapid_return_then_typing_keeps_original_and_targets_new_block():
    original = Block.text_block("already typed")
    result, destination = insert_block_after_selection([original], [0])
    result[destination].runs = [InlineRun("immediate typing")]
    assert [block.text for block in result] == ["already typed", "immediate typing"]


def test_backspace_in_new_empty_block_merges_to_previous_without_data_loss():
    bold = InlineMark(MarkType.BOLD)
    previous = Block(runs=[InlineRun("preserved", (bold,))])
    result, destination = merge_empty_block_backward([previous, Block()], 1)
    assert destination == 0
    assert result == [previous]
    assert result[0].runs == [InlineRun("preserved", (bold,))]


def test_image_display_width_round_trips_in_readable_metadata():
    block = Block(
        kind=BlockType.IMAGE,
        runs=[InlineRun("Storm")],
        target="../Attachments/id/storm.png",
        alt="Storm",
        display_width=384.5,
    )
    markdown = serialize_blocks([block])
    assert '<!-- stormpad:image width="384.5" -->' in markdown
    assert "![Storm](../Attachments/id/storm.png)" in markdown
    assert parse_blocks(markdown) == [block]


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


# -- block-edit control: convert exactly one targeted block --------------------


def test_block_edit_converts_only_the_targeted_block():
    """Hovering Block A and converting must not touch Block B."""
    blocks = [
        Block.text_block("Alpha"),
        Block.text_block("Beta"),
        Block.text_block("Gamma"),
    ]
    result = convert_selected_blocks(blocks, [1], BlockType.HEADING_1)
    assert [(b.kind, b.text) for b in result] == [
        (BlockType.TEXT, "Alpha"),
        (BlockType.HEADING_1, "Beta"),
        (BlockType.TEXT, "Gamma"),
    ]


def test_block_edit_conversion_never_inserts_a_duplicate_block():
    blocks = [Block.text_block("Alpha"), Block.text_block("Beta")]
    for kind in (
        BlockType.HEADING_1,
        BlockType.HEADING_2,
        BlockType.HEADING_3,
        BlockType.TODO,
        BlockType.BULLET,
        BlockType.NUMBERED,
        BlockType.QUOTE,
        BlockType.TEXT,
    ):
        result = convert_selected_blocks(blocks, [0], kind)
        assert len(result) == len(blocks)
        assert result[0].text == "Alpha"
        assert result[1].text == "Beta"


def test_block_edit_conversion_preserves_inline_formatting():
    marks = (InlineMark(MarkType.BOLD), InlineMark(MarkType.HIGHLIGHT, "yellow"))
    blocks = [
        Block.text_block("Plain"),
        Block(kind=BlockType.TEXT, runs=[InlineRun("Rich", marks)]),
    ]
    result = convert_selected_blocks(blocks, [1], BlockType.QUOTE)
    assert result[1].kind == BlockType.QUOTE
    assert result[1].runs == blocks[1].runs
    assert result[0].kind == BlockType.TEXT  # untouched neighbour


def test_targeting_a_different_block_next_time_affects_only_that_block():
    blocks = [Block.text_block("A"), Block.text_block("B")]
    first = convert_selected_blocks(blocks, [0], BlockType.QUOTE)
    second = convert_selected_blocks(first, [1], BlockType.HEADING_2)
    assert [(b.kind, b.text) for b in second] == [
        (BlockType.QUOTE, "A"),
        (BlockType.HEADING_2, "B"),
    ]
