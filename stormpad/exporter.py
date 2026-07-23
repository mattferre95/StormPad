"""Plain-text export for complete StormPad notes."""

from __future__ import annotations

import re
from pathlib import Path

from .block_parser import parse_blocks
from .blocks import Block, BlockType, MarkType
from .models import Note
from .storage import atomic_write_text

_RAW_MARKUP = re.compile(r"(^|\s)(#{1,6}|[-*>])\s+|[`*_]")


def _block_text(block: Block) -> str:
    pieces: list[str] = []
    for run in block.runs:
        link = next((mark.value for mark in run.marks if mark.kind == MarkType.LINK), None)
        pieces.append(f"{run.text} — {link}" if link else run.text)
    text = "".join(pieces).strip()
    if block.kind in (
        BlockType.TEXT,
        BlockType.HEADING_1,
        BlockType.HEADING_2,
        BlockType.HEADING_3,
    ):
        return text
    if block.kind == BlockType.TODO:
        return f"[{'x' if block.checked else ' '}] {text}".rstrip()
    if block.kind == BlockType.BULLET:
        return f"• {text}".rstrip()
    if block.kind == BlockType.NUMBERED:
        return f"1. {text}".rstrip()
    if block.kind == BlockType.QUOTE:
        return f"“{text}”" if text else ""
    if block.kind == BlockType.DIVIDER:
        return "────────"
    if block.kind == BlockType.LINK:
        return f"{text or 'Link'} — {block.target or ''}".rstrip(" —")
    if block.kind == BlockType.IMAGE:
        return f"Image: {block.alt or text or 'Untitled'}"
    if block.kind == BlockType.FILE:
        return f"File: {text or Path(block.target or '').name or 'Untitled'}"
    if block.kind == BlockType.RAW:
        return _RAW_MARKUP.sub(" ", block.raw or "").strip()
    return ""


def note_to_plain_text(note: Note) -> str:
    """Return title, every visible body block, and transcript without metadata."""
    sections: list[str] = [note.title.strip() or "Untitled Note"]
    body_lines = [
        rendered
        for block in parse_blocks(note.body)
        if block.kind != BlockType.TRANSCRIPT
        and (rendered := _block_text(block))
    ]
    if body_lines:
        sections.append("\n".join(body_lines))
    if note.transcript:
        transcript = ["Transcript"]
        transcript.extend(f"[{chunk.timestamp}]\n{chunk.text}" for chunk in note.transcript)
        sections.append("\n\n".join(transcript))
    return "\n\n".join(sections).strip() + "\n"


def export_note_txt(note: Note, destination: Path | str) -> Path:
    """Atomically export ``note`` to a UTF-8 ``.txt`` file."""
    path = Path(destination)
    if path.suffix.lower() != ".txt":
        path = path.with_suffix(".txt")
    atomic_write_text(path, note_to_plain_text(note))
    return path
