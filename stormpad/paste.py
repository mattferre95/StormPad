"""Sanitize externally pasted rich text down to StormPad's supported formatting.

External sources (browsers, TextEdit, Apple Notes) carry their own foreground
colors, backgrounds, fonts, and sizes. Importing those verbatim is what made
pasted text render black, and therefore unreadable, on StormPad's dark themes.

This module is the single place that decides what survives a paste. It is pure
and AppKit-free: the view layer reads native attributes into :class:`PastedRun`
values, and everything below turns those into StormPad's own semantic marks.
Anything not represented here is dropped, so no external color, background,
font, or size can reach the editor or the saved Markdown. The theme supplies
the actual appearance when the sanitized runs are drawn.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .blocks import Block, BlockType, InlineMark, InlineRun, MarkType, coalesce_runs

#: Paragraph separators any source might use, normalized to "\n" before split.
#: U+2028 and U+2029 are what AppKit and web content commonly carry.
_LINE_BREAKS = ("\r\n", "\r", "\u2028", "\u2029")

#: Only these schemes are kept for a pasted link. Anything else (javascript:,
#: data:, file:) is dropped and the text is kept unlinked.
_SAFE_LINK_SCHEMES = ("http://", "https://", "mailto:")


@dataclass(frozen=True)
class PastedRun:
    """One stretch of pasted text plus the few attributes StormPad understands.

    Deliberately narrow. The view layer maps native AppKit attributes onto these
    fields and discards the rest, so unsupported styling cannot leak through by
    simply appearing in the pasteboard.
    """

    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    link: str | None = None


def safe_link(target: str | None) -> str | None:
    """Return a link target StormPad is willing to keep, else ``None``."""
    if not target:
        return None
    value = str(target).strip()
    if not value:
        return None
    lowered = value.casefold()
    if any(lowered.startswith(scheme) for scheme in _SAFE_LINK_SCHEMES):
        return value
    # A bare "example.com/page" is a normal paste; anything with a foreign
    # scheme is not worth the risk.
    return None if ":" in lowered.split("/", 1)[0] else value


def normalize_breaks(text: str) -> str:
    """Collapse every paragraph separator style onto ``\\n``."""
    for separator in _LINE_BREAKS:
        text = text.replace(separator, "\n")
    return text


def _marks(run: PastedRun) -> tuple[InlineMark, ...]:
    marks: list[InlineMark] = []
    if run.bold:
        marks.append(InlineMark(MarkType.BOLD))
    if run.italic:
        marks.append(InlineMark(MarkType.ITALIC))
    if run.underline:
        marks.append(InlineMark(MarkType.UNDERLINE))
    target = safe_link(run.link)
    if target:
        marks.append(InlineMark(MarkType.LINK, target))
    return tuple(marks)


def sanitize_pasted_runs(runs: Sequence[PastedRun]) -> list[InlineRun]:
    """Convert pasted runs into StormPad inline runs, dropping all styling.

    Bold, italic, underline, and safe links survive. Colors, highlights,
    backgrounds, fonts, and sizes are never produced here, so pasted text always
    renders in the current theme's default body appearance.
    """
    result: list[InlineRun] = []
    for run in runs:
        text = normalize_breaks(run.text)
        if not text:
            continue
        result.append(InlineRun(text, _marks(run)))
    return coalesce_runs(result)


def pasted_blocks(runs: Sequence[PastedRun]) -> list[Block]:
    """Split sanitized runs into one plain text block per pasted paragraph.

    Inline marks are carried across the split, so a bold phrase spanning a line
    break stays bold in both paragraphs.
    """
    blocks: list[Block] = []
    current: list[InlineRun] = []
    for run in sanitize_pasted_runs(runs):
        pieces = run.text.split("\n")
        for index, piece in enumerate(pieces):
            if index:
                blocks.append(Block(kind=BlockType.TEXT, runs=coalesce_runs(current)))
                current = []
            if piece:
                current.append(InlineRun(piece, run.marks))
    blocks.append(Block(kind=BlockType.TEXT, runs=coalesce_runs(current)))
    return blocks
