"""Targeted tests for the responsive Divider block.

Covers only this pass's change: the divider rule derives its width from the
text system's proposed line fragment (so it follows the editor content width)
rather than a fixed run of glyphs, and its Markdown stays ``---``.
"""

from __future__ import annotations

from Foundation import NSMakePoint, NSMakeRect

from stormpad.block_serializer import serialize_blocks
from stormpad.blocks import Block, BlockType
from stormpad.views.block_editor import (
    _DIVIDER_INSET,
    _DIVIDER_MIN_WIDTH,
    DividerAttachmentCell,
)


def cell_width(line_width: float, *, origin_x: float = 0.0) -> float:
    cell = DividerAttachmentCell.alloc().initWithColor_(None)
    frame = cell.cellFrameForTextContainer_proposedLineFragment_glyphPosition_characterIndex_(
        None,
        NSMakeRect(0.0, 0.0, line_width, 20.0),
        NSMakePoint(origin_x, 0.0),
        0,
    )
    return float(frame.size.width)


def test_divider_width_follows_line_fragment():
    """A wider editor (resize / fullscreen / collapsed panel) yields a wider rule."""
    narrow = cell_width(400.0)
    wide = cell_width(900.0)
    assert wide > narrow
    # Tracks the available width rather than a fixed pixel value.
    assert narrow == 400.0
    assert wide == 900.0


def test_divider_width_is_not_fixed_across_many_widths():
    widths = [cell_width(w) for w in (320.0, 640.0, 1280.0, 1920.0)]
    assert widths == [320.0, 640.0, 1280.0, 1920.0]
    assert len(set(widths)) == len(widths)


def test_divider_respects_glyph_origin_indent():
    """An indented line fragment shortens the rule by the indent."""
    assert cell_width(800.0, origin_x=120.0) == 680.0


def test_divider_never_collapses_below_minimum():
    assert cell_width(10.0) == _DIVIDER_MIN_WIDTH
    assert cell_width(0.0) == _DIVIDER_MIN_WIDTH


def test_divider_keeps_inset_from_writing_margins():
    """The drawn rule is inset inside the cell frame on both sides."""
    assert _DIVIDER_INSET > 0
    drawn = cell_width(600.0) - (_DIVIDER_INSET * 2.0)
    assert drawn < 600.0
    assert drawn == 600.0 - (_DIVIDER_INSET * 2.0)


def test_divider_markdown_is_unchanged():
    assert serialize_blocks([Block(kind=BlockType.DIVIDER)]).strip() == "---"
