"""Plain-text exporter coverage for every semantic block."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from stormpad import models
from stormpad.block_serializer import serialize_blocks
from stormpad.blocks import Block, BlockType, InlineMark, InlineRun, MarkType
from stormpad.exporter import export_note_txt, note_to_plain_text
from stormpad.models import Note, TranscriptBlock


def make_note(tmp_path: Path) -> Note:
    blocks = [
        Block(
            runs=[
                InlineRun(
                    "Formatted",
                    (
                        InlineMark(MarkType.BOLD),
                        InlineMark(MarkType.ITALIC),
                        InlineMark(MarkType.UNDERLINE),
                        InlineMark(MarkType.TEXT_COLOR, "cyan"),
                        InlineMark(MarkType.HIGHLIGHT, "yellow"),
                        InlineMark(MarkType.LINK, "https://inline.example"),
                    ),
                )
            ]
        ),
        Block.text_block("Heading", BlockType.HEADING_1),
        Block(kind=BlockType.TODO, runs=[InlineRun("Task")], checked=True),
        Block.text_block("Bullet", BlockType.BULLET),
        Block.text_block("Number", BlockType.NUMBERED),
        Block.text_block("Quoted", BlockType.QUOTE),
        Block(kind=BlockType.DIVIDER),
        Block(
            kind=BlockType.LINK,
            runs=[InlineRun("Site")],
            target="https://example.com",
        ),
        Block(
            kind=BlockType.IMAGE,
            alt="Photo",
            target="../Attachments/id/photo.png",
        ),
        Block(
            kind=BlockType.FILE,
            runs=[InlineRun("brief.pdf")],
            target="../Attachments/id/brief.pdf",
        ),
        Block(kind=BlockType.TRANSCRIPT),
        Block(kind=BlockType.RAW, raw="```custom\nopaque\n```"),
    ]
    stamp = datetime(2026, 7, 23, tzinfo=UTC)
    return Note(
        id="stable",
        path=tmp_path / "source.md",
        title="Complete note",
        body=serialize_blocks(blocks),
        category=models.IDEAS,
        created_at=stamp,
        updated_at=stamp,
        transcript=[TranscriptBlock("00:00:04", "Spoken words")],
    )


def test_plain_text_export_contains_all_content_without_storage_metadata(tmp_path):
    note = make_note(tmp_path)
    text = note_to_plain_text(note)
    for expected in (
        "Complete note",
        "Formatted — https://inline.example",
        "Heading",
        "[x] Task",
        "• Bullet",
        "1. Number",
        "“Quoted”",
        "Site — https://example.com",
        "Image: Photo",
        "File: brief.pdf",
        "[00:00:04]\nSpoken words",
        "opaque",
    ):
        assert expected in text
    for leak in (
        "Created:",
        "Updated:",
        "Category:",
        "ID:",
        "stormpad:transcript",
        "data-stormpad",
        "<u>",
        "**",
    ):
        assert leak not in text


def test_export_adds_txt_extension_and_writes_utf8(tmp_path):
    note = make_note(tmp_path)
    destination = export_note_txt(note, tmp_path / "exported")
    assert destination.name == "exported.txt"
    assert destination.read_text(encoding="utf-8") == note_to_plain_text(note)
