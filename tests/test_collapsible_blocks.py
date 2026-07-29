"""Collapsible toggle ownership, persistence, and content safety.

Collapsing must be presentation only. These tests pin the two ownership rules
and, more importantly, that hidden content stays in the document and in the
serialized Markdown no matter what the collapse state is.
"""

from __future__ import annotations

import pytest

from stormpad.block_parser import parse_blocks
from stormpad.block_serializer import serialize_blocks
from stormpad.blocks import (
    TOGGLE_TO_PLAIN,
    Block,
    BlockType,
    convert_block,
    heading_level,
    is_toggle,
)
from stormpad.collapse import (
    heading_section_range,
    hidden_indexes,
    owning_toggle,
    reveal_for_conversion,
    set_collapsed,
    toggle_child_range,
    toggle_range,
    visible_indexes,
)


def _toggle(text="Summary", *, indent=0, collapsed=False):
    return Block(kind=BlockType.TOGGLE, indent=indent, collapsed=collapsed).with_text(text)


def _th(level, text="Section", *, collapsed=False):
    kind = {
        1: BlockType.TOGGLE_HEADING_1,
        2: BlockType.TOGGLE_HEADING_2,
        3: BlockType.TOGGLE_HEADING_3,
    }[level]
    return Block(kind=kind, collapsed=collapsed).with_text(text)


def _h(level, text="Heading"):
    kind = {1: BlockType.HEADING_1, 2: BlockType.HEADING_2, 3: BlockType.HEADING_3}[level]
    return Block(kind=kind).with_text(text)


def _bullet(text, indent=1):
    return Block(kind=BlockType.BULLET, indent=indent).with_text(text)


def _text(value):
    return Block.text_block(value)


# --- Toggle List ownership ----------------------------------------------------


def test_toggle_with_no_child_owns_an_empty_range():
    blocks = [_toggle(), _text("outside")]

    assert toggle_child_range(blocks, 0) == (1, 1)
    assert hidden_indexes([_toggle(collapsed=True), _text("outside")]) == frozenset()


def test_toggle_owns_following_deeper_blocks():
    blocks = [_toggle(), _bullet("one"), _bullet("two"), _text("outside")]

    assert toggle_child_range(blocks, 0) == (1, 3)


def test_toggle_stops_at_the_first_same_indent_block():
    blocks = [_toggle(), _bullet("child"), _bullet("sibling", indent=0), _text("after")]

    assert toggle_child_range(blocks, 0) == (1, 2)


def test_toggle_stops_at_the_first_shallower_block():
    blocks = [_toggle(indent=1), _bullet("child", indent=2), _bullet("shallower", indent=0)]

    assert toggle_child_range(blocks, 0) == (1, 2)


def test_a_plain_paragraph_ends_a_toggle_because_it_carries_no_indent():
    blocks = [_toggle(), _bullet("child"), _text("paragraph")]

    assert toggle_child_range(blocks, 0) == (1, 2)


def test_nested_toggles_resolve_independently():
    blocks = [
        _toggle("outer"),
        _toggle("inner", indent=1),
        _bullet("inner child", indent=2),
        _bullet("outer child", indent=1),
        _text("outside"),
    ]

    assert toggle_child_range(blocks, 0) == (1, 4)
    assert toggle_child_range(blocks, 1) == (2, 3)


def test_collapsing_the_outer_toggle_hides_the_inner_one_and_keeps_its_state():
    blocks = [
        _toggle("outer", collapsed=True),
        _toggle("inner", indent=1, collapsed=True),
        _bullet("inner child", indent=2),
        _text("outside"),
    ]

    assert hidden_indexes(blocks) == frozenset({1, 2})
    # The inner toggle's own state is untouched, so expanding the outer one
    # brings back a still-collapsed inner toggle.
    assert blocks[1].collapsed is True
    blocks[0].collapsed = False
    assert hidden_indexes(blocks) == frozenset({2})


# --- Toggle Heading ownership -------------------------------------------------


@pytest.mark.parametrize("boundary_level", [1])
def test_toggle_heading_1_stops_at_the_next_level_1(boundary_level):
    blocks = [_th(1), _text("body"), _h(boundary_level, "next")]

    assert heading_section_range(blocks, 0) == (1, 2)


@pytest.mark.parametrize("boundary", [_h(1), _th(1), _h(2), _th(2)])
def test_toggle_heading_2_stops_at_level_1_or_2(boundary):
    blocks = [_th(2), _text("body"), boundary]

    assert heading_section_range(blocks, 0) == (1, 2)


@pytest.mark.parametrize("boundary", [_h(1), _h(2), _h(3), _th(3)])
def test_toggle_heading_3_stops_at_level_1_2_or_3(boundary):
    blocks = [_th(3), _text("body"), boundary]

    assert heading_section_range(blocks, 0) == (1, 2)


def test_lower_level_headings_stay_inside_a_higher_level_section():
    blocks = [
        _th(2, "Product direction"),
        _text("Normal paragraph"),
        _bullet("Bulleted list", indent=0),
        _th(3, "Native experience"),
        _text("More content"),
        _h(2, "Next major section"),
    ]

    # Everything down to, but not including, the next Heading 2.
    assert heading_section_range(blocks, 0) == (1, 5)
    blocks[0].collapsed = True
    assert hidden_indexes(blocks) == frozenset({1, 2, 3, 4})
    assert visible_indexes(blocks) == [0, 5]


def test_normal_headings_are_boundaries_but_never_collapse_anything():
    blocks = [_h(2, "plain"), _text("body"), _h(2, "next")]

    assert heading_level(blocks[0]) == 2
    assert not is_toggle(blocks[0])
    assert hidden_indexes(blocks) == frozenset()


def test_multiple_collapsed_ranges_combine_without_corrupting_indexes():
    blocks = [
        _th(2, "first", collapsed=True),
        _text("a"),
        _h(2, "boundary"),
        _toggle("third", collapsed=True),
        _bullet("c"),
        _text("tail"),
    ]

    assert hidden_indexes(blocks) == frozenset({1, 4})
    assert visible_indexes(blocks) == [0, 2, 3, 5]


def test_a_toggle_heading_with_no_following_heading_owns_the_rest():
    """Deliberate: a section runs to the end of the note when nothing bounds it."""
    blocks = [_th(2, "only section", collapsed=True), _text("a"), _bullet("b"), _text("c")]

    assert heading_section_range(blocks, 0) == (1, 4)
    assert visible_indexes(blocks) == [0]


def test_toggle_range_dispatches_on_kind():
    listish = [_toggle(), _bullet("child")]
    headingish = [_th(1), _text("body")]

    assert toggle_range(listish, 0) == (1, 2)
    assert toggle_range(headingish, 0) == (1, 2)
    # A non-toggle owns nothing.
    assert toggle_range([_text("plain")], 0) == (1, 1)


def test_owning_toggle_finds_the_collapsed_parent_for_a_caret():
    blocks = [_toggle("outer", collapsed=True), _bullet("child"), _text("outside")]

    assert owning_toggle(blocks, 1) == 0
    assert owning_toggle(blocks, 2) is None


# --- persistence and content safety -------------------------------------------


@pytest.mark.parametrize(
    "kind",
    [
        BlockType.TOGGLE,
        BlockType.TOGGLE_HEADING_1,
        BlockType.TOGGLE_HEADING_2,
        BlockType.TOGGLE_HEADING_3,
    ],
)
@pytest.mark.parametrize("collapsed", [True, False])
def test_toggle_blocks_round_trip_with_their_state(kind, collapsed):
    original = [Block(kind=kind, collapsed=collapsed).with_text("Summary text")]
    markdown = serialize_blocks(original)
    reparsed = parse_blocks(markdown)

    assert [block.kind for block in reparsed] == [kind]
    assert reparsed[0].collapsed is collapsed
    assert reparsed[0].text == "Summary text"
    assert serialize_blocks(reparsed) == markdown


def test_hidden_child_content_survives_serialization():
    blocks = [
        _toggle("Launch checklist", collapsed=True),
        _bullet("Finalize homepage"),
        _bullet("Build the DMG"),
        _text("Normal paragraph outside the toggle"),
    ]
    assert hidden_indexes(blocks) == frozenset({1, 2})

    markdown = serialize_blocks(blocks)

    # Collapsed or not, every child is still in the note.
    assert "Finalize homepage" in markdown
    assert "Build the DMG" in markdown
    assert parse_blocks(markdown) == blocks


def test_collapsing_changes_nothing_but_the_summary_flag():
    blocks = [_toggle("s"), _bullet("child"), _text("after")]
    before = serialize_blocks(blocks)

    set_collapsed(blocks, 0, True)
    collapsed_markdown = serialize_blocks(blocks)
    set_collapsed(blocks, 0, False)

    assert serialize_blocks(blocks) == before
    assert 'collapsed="true"' in collapsed_markdown
    # The children serialize identically either way.
    assert collapsed_markdown.replace('collapsed="true"', 'collapsed="false"') == before


def test_existing_notes_parse_exactly_as_before():
    """No toggle metadata means nothing about parsing may change."""
    source = (
        "# Heading 1\n\n## Heading 2\n\n- [ ] todo\n\n- bullet\n\n"
        "  - nested bullet\n\n1. numbered\n\n> quote\n\n---\n\n"
        "Plain paragraph with **bold** and <u>underline</u>."
    )

    blocks = parse_blocks(source)

    assert not any(is_toggle(block) for block in blocks)
    assert hidden_indexes(blocks) == frozenset()
    assert serialize_blocks(blocks) == source


def test_conversion_to_a_normal_block_preserves_children_and_reveals_them():
    blocks = [_toggle("Launch checklist", collapsed=True), _bullet("child"), _text("after")]

    reveal_for_conversion(blocks, 0)
    blocks[0] = convert_block(blocks[0], TOGGLE_TO_PLAIN[BlockType.TOGGLE])

    assert blocks[0].kind == BlockType.TEXT
    assert blocks[0].text == "Launch checklist"
    assert [block.text for block in blocks[1:]] == ["child", "after"]
    assert hidden_indexes(blocks) == frozenset()


def test_converting_a_heading_to_a_toggle_heading_keeps_the_section():
    blocks = [_h(2, "Product direction"), _text("body"), _h(2, "next")]

    blocks[0] = convert_block(blocks[0], BlockType.TOGGLE_HEADING_2)

    assert blocks[0].kind == BlockType.TOGGLE_HEADING_2
    assert blocks[0].collapsed is False
    assert heading_section_range(blocks, 0) == (1, 2)
    assert "body" in serialize_blocks(blocks)


def test_deleting_only_the_toggle_summary_keeps_following_content():
    blocks = [_toggle("summary", collapsed=True), _bullet("child"), _text("after")]

    del blocks[0]

    assert [block.text for block in blocks] == ["child", "after"]
    assert hidden_indexes(blocks) == frozenset()
    assert "child" in serialize_blocks(blocks)


@pytest.mark.parametrize(
    "marker",
    [
        '<!-- stormpad:toggle collapsed="maybe" -->',
        "<!-- stormpad:toggle -->",
        "<!-- stormpad:toggle collapsed -->",
    ],
)
def test_malformed_toggle_metadata_keeps_content_visible(marker):
    blocks = parse_blocks(f"{marker}\n## Product direction\n\nBody paragraph")

    assert hidden_indexes(blocks) == frozenset()
    markdown = serialize_blocks(blocks)
    assert "Product direction" in markdown
    assert "Body paragraph" in markdown


def test_a_bare_toggle_marker_without_a_summary_is_preserved():
    blocks = parse_blocks('<!-- stormpad:toggle collapsed="true" -->')

    assert hidden_indexes(blocks) == frozenset()
    assert "stormpad:toggle" in serialize_blocks(blocks)


def test_nested_collapse_states_survive_save_and_reopen():
    blocks = [
        _toggle("outer", collapsed=False),
        _toggle("inner", indent=1, collapsed=True),
        _bullet("inner child", indent=2),
        _bullet("outer child", indent=1),
    ]

    reopened = parse_blocks(serialize_blocks(blocks))

    assert [block.collapsed for block in reopened if is_toggle(block)] == [False, True]
    assert hidden_indexes(reopened) == frozenset({2})
    assert reopened == blocks


def test_the_bundled_welcome_note_is_unaffected():
    from stormpad import welcome

    blocks = parse_blocks(welcome.load_template().body)

    assert not any(is_toggle(block) for block in blocks)
    assert hidden_indexes(blocks) == frozenset()
    assert serialize_blocks(blocks) == welcome.load_template().body
