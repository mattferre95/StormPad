"""Deterministic Markdown serialization for StormPad blocks."""

from __future__ import annotations

import html
from urllib.parse import quote

from .blocks import (
    COLOR_TOKENS,
    Block,
    BlockType,
    InlineMark,
    InlineRun,
    MarkType,
    coalesce_runs,
)


def _escape_text(text: str) -> str:
    escaped = html.escape(text, quote=False)
    for character in ("\\", "*", "[", "]"):
        escaped = escaped.replace(character, f"\\{character}")
    return escaped


def _safe_target(value: str) -> str:
    return quote(value.strip(), safe="/:#?&=%+@,.;~_-")


def _mark(runs: tuple[InlineMark, ...], kind: MarkType) -> InlineMark | None:
    return next((mark for mark in runs if mark.kind == kind), None)


def serialize_inline(runs: list[InlineRun]) -> str:
    """Serialize semantic inline runs using Markdown and allow-listed HTML."""
    pieces: list[str] = []
    for run in coalesce_runs(runs):
        value = _escape_text(run.text)
        bold = _mark(run.marks, MarkType.BOLD)
        italic = _mark(run.marks, MarkType.ITALIC)
        if bold and italic:
            value = f"***{value}***"
        elif bold:
            value = f"**{value}**"
        elif italic:
            value = f"*{value}*"
        if _mark(run.marks, MarkType.UNDERLINE):
            value = f"<u>{value}</u>"
        color = _mark(run.marks, MarkType.TEXT_COLOR)
        if color and color.value in COLOR_TOKENS and color.value != "default":
            value = f'<span data-stormpad-color="{color.value}">{value}</span>'
        highlight = _mark(run.marks, MarkType.HIGHLIGHT)
        if highlight and highlight.value in COLOR_TOKENS and highlight.value != "default":
            value = f'<span data-stormpad-highlight="{highlight.value}">{value}</span>'
        link = _mark(run.marks, MarkType.LINK)
        if link and link.value:
            value = f"[{value}]({_safe_target(link.value)})"
        pieces.append(value)
    return "".join(pieces)


def serialize_block(block: Block) -> str:
    text = serialize_inline(block.runs)
    indent = "  " * block.indent
    if block.kind == BlockType.TEXT:
        return text
    if block.kind == BlockType.HEADING_1:
        return f"# {text}".rstrip()
    if block.kind == BlockType.HEADING_2:
        return f"## {text}".rstrip()
    if block.kind == BlockType.HEADING_3:
        return f"### {text}".rstrip()
    if block.kind == BlockType.TODO:
        return f"{indent}- [{'x' if block.checked else ' '}] {text}".rstrip()
    if block.kind == BlockType.BULLET:
        return f"{indent}- {text}".rstrip()
    if block.kind == BlockType.NUMBERED:
        return f"{indent}1. {text}".rstrip()
    if block.kind == BlockType.QUOTE:
        return f"> {text}".rstrip()
    if block.kind == BlockType.DIVIDER:
        return "---"
    if block.kind == BlockType.LINK:
        return f"[{text}]({_safe_target(block.target or '')})"
    if block.kind == BlockType.IMAGE:
        alt = block.alt if block.alt is not None else block.text
        return f"![{_escape_text(alt)}]({_safe_target(block.target or '')})"
    if block.kind == BlockType.FILE:
        return f"[{text}]({_safe_target(block.target or '')})"
    if block.kind == BlockType.TRANSCRIPT:
        collapsed = "true" if block.collapsed else "false"
        return f'<!-- stormpad:transcript collapsed="{collapsed}" -->'
    if block.kind == BlockType.RAW:
        return block.raw or ""
    raise ValueError(f"unsupported block kind: {block.kind}")


def serialize_blocks(blocks: list[Block]) -> str:
    """Serialize blocks with blank lines for readable, deterministic Markdown."""
    if not blocks or (len(blocks) == 1 and blocks[0].kind == BlockType.TEXT and blocks[0].is_empty):
        return ""
    return "\n\n".join(serialize_block(block) for block in blocks).rstrip()
