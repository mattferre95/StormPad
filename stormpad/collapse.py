"""Which blocks a collapsible toggle owns, and which are hidden right now.

Pure and AppKit-free on purpose. Every ownership and visibility decision lives
here so the editor only has to ask "which indexes are hidden" and then hide them
at the layout level. Nothing in this module removes, rewrites, or reorders
blocks: it returns index ranges over a complete block document, which is what
keeps collapsed content safe during autosave.

Two ownership rules, one shared implementation:

* A **Toggle List** owns the following blocks indented deeper than itself, and
  stops at the first block whose indent is equal or shallower.
* A **Toggle Heading** owns the following blocks until a heading of the same or
  higher level, counting normal and toggle headings alike as boundaries.
"""

from __future__ import annotations

from collections.abc import Sequence

from .blocks import Block, heading_level, is_toggle


def toggle_child_range(blocks: Sequence[Block], index: int) -> tuple[int, int]:
    """Half-open ``[start, end)`` index range a Toggle List owns.

    Membership is the existing indent model: deeper than the summary belongs to
    it, equal or shallower ends it. An empty range is ``(index + 1, index + 1)``.
    """
    start = index + 1
    if index < 0 or index >= len(blocks):
        return (start, start)
    parent_indent = blocks[index].indent
    end = start
    while end < len(blocks) and blocks[end].indent > parent_indent:
        end += 1
    return (start, end)


def heading_section_range(blocks: Sequence[Block], index: int) -> tuple[int, int]:
    """Half-open index range a Toggle Heading owns.

    Ends at the first following heading whose level is the same or higher. A
    deeper heading stays inside the section, so collapsing an H2 also hides the
    H3s beneath it while leaving the next H2 visible.
    """
    start = index + 1
    if index < 0 or index >= len(blocks):
        return (start, start)
    level = heading_level(blocks[index])
    if level is None:
        return (start, start)
    end = start
    while end < len(blocks):
        candidate = heading_level(blocks[end])
        if candidate is not None and candidate <= level:
            break
        end += 1
    return (start, end)


def toggle_range(blocks: Sequence[Block], index: int) -> tuple[int, int]:
    """Range owned by the toggle at ``index``, whichever kind it is."""
    if index < 0 or index >= len(blocks) or not is_toggle(blocks[index]):
        return (index + 1, index + 1)
    if heading_level(blocks[index]) is not None:
        return heading_section_range(blocks, index)
    return toggle_child_range(blocks, index)


def hidden_indexes(blocks: Sequence[Block]) -> frozenset[int]:
    """Indexes currently hidden by one or more collapsed toggles.

    A collapsed toggle hides everything it owns, including any nested toggles.
    Nested toggles inside a *hidden* region are skipped rather than resolved, so
    their own collapsed state is left untouched and comes back intact when the
    outer toggle expands.
    """
    hidden: set[int] = set()
    for index, block in enumerate(blocks):
        if index in hidden:
            continue
        if is_toggle(block) and block.collapsed:
            start, end = toggle_range(blocks, index)
            hidden.update(range(start, end))
    return frozenset(hidden)


def visible_indexes(blocks: Sequence[Block]) -> list[int]:
    """Indexes that should be drawn, in document order."""
    hidden = hidden_indexes(blocks)
    return [index for index in range(len(blocks)) if index not in hidden]


def is_hidden(blocks: Sequence[Block], index: int) -> bool:
    return index in hidden_indexes(blocks)


def owning_toggle(blocks: Sequence[Block], index: int) -> int | None:
    """Nearest collapsed toggle that hides ``index``, or ``None``.

    Used to move a caret out of content that is about to disappear: the caret
    goes to the toggle the user just collapsed, never into a hidden range.
    """
    best: int | None = None
    for candidate, block in enumerate(blocks):
        if candidate >= index or not is_toggle(block) or not block.collapsed:
            continue
        start, end = toggle_range(blocks, candidate)
        if start <= index < end:
            # A nested collapsed toggle is closer to the caret than its parent,
            # but a hidden parent wins because the child is not on screen.
            if best is None or candidate < best or not is_hidden(blocks, candidate):
                best = candidate if best is None else min(best, candidate)
    return best


def first_visible_destination(blocks: Sequence[Block], index: int) -> int:
    """Nearest index at or before ``index`` that is safe to put a caret in."""
    if not blocks:
        return 0
    index = min(max(index, 0), len(blocks) - 1)
    hidden = hidden_indexes(blocks)
    while index > 0 and index in hidden:
        index -= 1
    return index


def set_collapsed(blocks: list[Block], index: int, collapsed: bool) -> list[Block]:
    """Return blocks with one toggle's collapsed state changed.

    Only the summary block is touched. Owned content is never modified, which is
    what makes collapsing a presentation-only operation.
    """
    if index < 0 or index >= len(blocks) or not is_toggle(blocks[index]):
        return blocks
    blocks[index].collapsed = bool(collapsed)
    return blocks


def reveal_for_conversion(blocks: list[Block], index: int) -> list[Block]:
    """Expand a toggle before it stops being one.

    Converting a collapsed toggle to a normal block would otherwise leave its
    content hidden with nothing left to reveal it.
    """
    if 0 <= index < len(blocks) and is_toggle(blocks[index]):
        blocks[index].collapsed = False
    return blocks
