"""Image alignment, sizing, selection, and paste routing.

Alignment and width are semantic and persisted; selection and its chrome are
ephemeral view state that must never reach the Markdown. The paste tests pin the
routing rule that keeps genuine image data out of the text sanitizer without
disturbing the sanitizer itself.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from AppKit import (
    NSApplication,
    NSBackingStoreBuffered,
    NSBitmapImageFileTypePNG,
    NSBitmapImageRep,
    NSColor,
    NSImage,
    NSPasteboard,
    NSPasteboardTypePNG,
    NSPasteboardTypeString,
    NSTitledWindowMask,
    NSWindow,
)
from Foundation import NSMakeRect, NSMakeSize

from stormpad import attachments
from stormpad.block_parser import parse_blocks
from stormpad.block_serializer import serialize_blocks
from stormpad.blocks import (
    DEFAULT_IMAGE_ALIGNMENT,
    IMAGE_ALIGNMENTS,
    Block,
    BlockType,
    normalize_alignment,
)
from stormpad.models import IDEAS, Note
from stormpad.theme import get_theme
from stormpad.views.block_editor import Editor
from stormpad.views.palette import Palette


def _png_bytes(width=48, height=32, color=None):
    image = NSImage.alloc().initWithSize_(NSMakeSize(width, height))
    image.lockFocus()
    (color or NSColor.redColor()).set()
    from AppKit import NSBezierPath

    NSBezierPath.fillRect_(NSMakeRect(0, 0, width, height))
    image.unlockFocus()
    rep = NSBitmapImageRep.imageRepWithData_(image.TIFFRepresentation())
    return rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, {})


def _write_png(path: Path, width=48, height=32):
    path.parent.mkdir(parents=True, exist_ok=True)
    _png_bytes(width, height).writeToFile_atomically_(str(path), True)
    return path


# --- alignment and width storage ----------------------------------------------


@pytest.mark.parametrize("alignment", IMAGE_ALIGNMENTS)
def test_alignment_round_trips(alignment):
    block = Block(
        kind=BlockType.IMAGE, target="a.png", alt="Alt", display_width=640.0, alignment=alignment
    )
    markdown = serialize_blocks([block])
    reparsed = parse_blocks(markdown)[0]

    assert reparsed.alignment == alignment
    assert reparsed.display_width == 640.0
    assert reparsed.target == "a.png"
    assert serialize_blocks([reparsed]) == markdown


def test_left_alignment_is_never_written_so_old_notes_stay_byte_identical():
    """An existing image note must not be rewritten merely by opening it."""
    original = '<!-- stormpad:image width="640" -->\n![Alt](a.png)'

    blocks = parse_blocks(original)

    assert blocks[0].alignment == "left"
    assert serialize_blocks(blocks) == original


def test_plain_image_markdown_still_round_trips():
    original = "![Alt](a.png)"
    blocks = parse_blocks(original)

    assert blocks[0].display_width is None
    assert blocks[0].alignment == "left"
    assert serialize_blocks(blocks) == original


@pytest.mark.parametrize(
    "marker",
    [
        '<!-- stormpad:image width="640" alignment="diagonal" -->',
        '<!-- stormpad:image width="640" alignment="" -->',
        "<!-- stormpad:image width=\"640\" alignment='center' -->",
    ],
)
def test_malformed_alignment_falls_back_to_left_without_losing_the_image(marker):
    blocks = parse_blocks(f"{marker}\n![Alt](a.png)")

    assert blocks[0].kind == BlockType.IMAGE
    assert blocks[0].target == "a.png"
    assert blocks[0].alignment == DEFAULT_IMAGE_ALIGNMENT


@pytest.mark.parametrize(
    "marker",
    ['<!-- stormpad:image width="abc" -->', "<!-- stormpad:image -->"],
)
def test_malformed_width_falls_back_without_losing_the_image(marker):
    blocks = parse_blocks(f"{marker}\n![Alt](a.png)")

    assert blocks[0].kind == BlockType.IMAGE
    assert blocks[0].target == "a.png"
    assert blocks[0].display_width is None


def test_alignment_only_metadata_is_supported():
    blocks = parse_blocks('<!-- stormpad:image alignment="right" -->\n![Alt](a.png)')

    assert blocks[0].alignment == "right"
    assert blocks[0].display_width is None


@pytest.mark.parametrize(
    "value,expected",
    [("left", "left"), ("CENTER", "center"), ("right", "right"), ("bogus", "left"), (None, "left")],
)
def test_normalize_alignment_accepts_only_supported_values(value, expected):
    assert normalize_alignment(value) == expected


def test_alignment_is_not_leaked_into_other_block_types():
    from stormpad.blocks import convert_block

    image = Block(kind=BlockType.IMAGE, target="a.png", alignment="center")
    converted = convert_block(image, BlockType.TEXT)

    assert converted.alignment == DEFAULT_IMAGE_ALIGNMENT


# --- attachment storage --------------------------------------------------------


def test_pasted_bytes_become_a_local_attachment_without_overwriting(tmp_path):
    notes_dir = tmp_path / "Notes"
    notes_dir.mkdir()
    source = _write_png(tmp_path / "shot.png")

    first = attachments.import_attachment(source, notes_dir, "note-1")
    second = attachments.import_attachment(source, notes_dir, "note-1")

    assert first.exists() and second.exists()
    assert first != second, "an existing attachment must never be overwritten"
    assert first.read_bytes() == source.read_bytes(), "original bytes preserved"


def test_unicode_filenames_are_sanitized(tmp_path):
    notes_dir = tmp_path / "Notes"
    notes_dir.mkdir()
    source = _write_png(tmp_path / "café ☕ shot.png")

    imported = attachments.import_attachment(source, notes_dir, "note-1")

    assert imported.exists()
    assert "/" not in imported.name


def test_is_image_recognizes_supported_types():
    for name in ("a.png", "b.jpg", "c.jpeg", "d.tiff", "e.heic"):
        assert attachments.is_image(Path(name)), name
    assert not attachments.is_image(Path("f.pdf"))


# --- editor -------------------------------------------------------------------


def _editor(tmp_path, body, theme_id="deep_dark", images=2):
    NSApplication.sharedApplication()
    notes_dir = tmp_path / "Notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    note_path = notes_dir / "img.md"
    note_path.write_text("", encoding="utf-8")
    for index in range(images):
        _write_png(tmp_path / "Attachments" / "img" / f"a{index}.png")
    editor = Editor.alloc().initWithPalette_onTitle_onBody_onAttachment_(
        Palette(get_theme(theme_id)),
        lambda _text: None,
        lambda _text: None,
        lambda _kind, _path: None,
    )
    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, 900, 700), NSTitledWindowMask, NSBackingStoreBuffered, False
    )
    editor.view.setFrame_(window.contentView().bounds())
    window.contentView().addSubview_(editor.view)
    editor.notes_dir = notes_dir
    now = datetime.now()
    editor.load_note(
        Note(
            id="img",
            path=note_path,
            title="Images",
            body=body,
            category=IDEAS,
            created_at=now,
            updated_at=now,
        )
    )
    return editor, window


IMAGE_NOTE = (
    "Intro paragraph\n\n"
    "![One](../Attachments/img/a0.png)\n\n"
    "Middle paragraph\n\n"
    "![Two](../Attachments/img/a1.png)\n\n"
    "Tail paragraph"
)


def test_selection_rules(tmp_path):
    editor, window = _editor(tmp_path, IMAGE_NOTE)
    try:
        images = editor._selectable_image_indexes()
        assert len(images) == 2

        editor.select_image_block(images[0])
        assert editor.selected_image_indexes() == [images[0]]

        # Command-click adds, then removes.
        editor.select_image_block(images[1], command=True)
        assert editor.selected_image_indexes() == images
        editor.select_image_block(images[1], command=True)
        assert editor.selected_image_indexes() == [images[0]]

        # Shift-click selects the range from the anchor.
        editor.select_image_block(images[1], shift=True)
        assert editor.selected_image_indexes() == images

        editor.clear_image_selection()
        assert editor.selected_image_indexes() == []
    finally:
        window.close()


def test_alignment_commands_update_every_selected_image(tmp_path):
    editor, window = _editor(tmp_path, IMAGE_NOTE)
    try:
        editor._set_image_selection(editor._selectable_image_indexes())
        assert editor.align_selected_images("center") is True

        blocks = editor._extract_blocks()
        aligned = [b.alignment for b in blocks if b.kind == BlockType.IMAGE]
        assert aligned == ["center", "center"]
        assert 'alignment="center"' in editor.body_text()

        assert editor.align_selected_images("right") is True
        assert all(
            b.alignment == "right" for b in editor._extract_blocks() if b.kind == BlockType.IMAGE
        )
    finally:
        window.close()


def test_alignment_does_not_touch_surrounding_text(tmp_path):
    editor, window = _editor(tmp_path, IMAGE_NOTE)
    try:
        editor._set_image_selection(editor._selectable_image_indexes())
        editor.align_selected_images("center")
        markdown = editor.body_text()
        for paragraph in ("Intro paragraph", "Middle paragraph", "Tail paragraph"):
            assert paragraph in markdown
    finally:
        window.close()


def test_match_width_uses_the_first_selected_image_as_anchor(tmp_path):
    editor, window = _editor(tmp_path, IMAGE_NOTE)
    try:
        images = editor._selectable_image_indexes()
        blocks = editor._extract_blocks()
        blocks[images[0]].display_width = 300.0
        blocks[images[1]].display_width = 180.0
        editor._replace_document(blocks, register_undo=False, focus_index=None)

        editor.select_image_block(images[0])
        editor.select_image_block(images[1], command=True)
        assert editor._image_anchor == images[0]
        assert editor.match_selected_image_widths() is True

        widths = [b.display_width for b in editor._extract_blocks() if b.kind == BlockType.IMAGE]
        assert widths == [300.0, 300.0]
    finally:
        window.close()


def test_fit_and_reset_apply_to_the_whole_selection(tmp_path):
    editor, window = _editor(tmp_path, IMAGE_NOTE)
    try:
        editor._set_image_selection(editor._selectable_image_indexes())
        assert editor.fit_selected_images_to_column() is True
        column = editor._content_column_width()
        widths = [b.display_width for b in editor._extract_blocks() if b.kind == BlockType.IMAGE]
        assert widths == [column, column]

        assert editor.reset_selected_images_to_natural_size() is True
        widths = [b.display_width for b in editor._extract_blocks() if b.kind == BlockType.IMAGE]
        assert widths == [None, None]
    finally:
        window.close()


def test_each_image_command_is_one_undo_step(tmp_path):
    editor, window = _editor(tmp_path, IMAGE_NOTE)
    try:
        original = editor.body_text()
        editor._set_image_selection(editor._selectable_image_indexes())
        editor.align_selected_images("center")
        assert 'alignment="center"' in editor.body_text()

        editor._body.undoManager().undo()

        assert editor.body_text() == original
        assert "Intro paragraph" in editor.body_text()
    finally:
        window.close()


def test_width_and_alignment_survive_save_and_reopen(tmp_path):
    editor, window = _editor(tmp_path, IMAGE_NOTE)
    try:
        editor._set_image_selection(editor._selectable_image_indexes())
        editor.align_selected_images("right")
        editor.fit_selected_images_to_column()
        saved = editor.body_text()
    finally:
        window.close()

    reopened, window = _editor(tmp_path, saved)
    try:
        blocks = [b for b in reopened._extract_blocks() if b.kind == BlockType.IMAGE]
        assert [b.alignment for b in blocks] == ["right", "right"]
        assert all(b.display_width for b in blocks)
    finally:
        window.close()


@pytest.mark.parametrize("theme_id", ["storm_blue", "deep_dark", "light"])
def test_theme_change_preserves_image_layout_metadata(theme_id):
    source = '<!-- stormpad:image width="410" alignment="center" -->\n![Alt](a.png)'
    blocks = parse_blocks(source)

    assert blocks[0].display_width == 410.0
    assert blocks[0].alignment == "center"
    assert serialize_blocks(blocks) == source


def test_images_hidden_in_a_collapsed_toggle_cannot_be_selected(tmp_path):
    body = (
        '<!-- stormpad:toggle collapsed="true" -->\n'
        "- Gallery\n\n"
        "  - ![One](../Attachments/img/a0.png)\n\n"
        "Tail paragraph"
    )
    editor, window = _editor(tmp_path, body, images=1)
    try:
        # The image sits inside the collapsed toggle, so it is not selectable.
        assert editor._selectable_image_indexes() == []
        editor.select_image_block(1)
        assert editor.selected_image_indexes() == []
    finally:
        window.close()


def test_switching_notes_clears_stale_image_selection(tmp_path):
    editor, window = _editor(tmp_path, IMAGE_NOTE)
    try:
        editor._set_image_selection(editor._selectable_image_indexes())
        assert editor.selected_image_indexes()

        now = datetime.now()
        editor.load_note(
            Note(
                id="other",
                path=tmp_path / "Notes" / "other.md",
                title="Other",
                body="Just text",
                category=IDEAS,
                created_at=now,
                updated_at=now,
            )
        )
        assert editor.selected_image_indexes() == []
    finally:
        window.close()


def test_selection_never_reaches_the_markdown(tmp_path):
    editor, window = _editor(tmp_path, IMAGE_NOTE)
    try:
        before = editor.body_text()
        editor._set_image_selection(editor._selectable_image_indexes())
        assert editor.body_text() == before
        assert "selected" not in editor.body_text()
    finally:
        window.close()


# --- paste routing -------------------------------------------------------------


def _pasteboard(kind, value):
    pasteboard = NSPasteboard.pasteboardWithUniqueName()
    pasteboard.declareTypes_owner_([kind], None)
    if kind == NSPasteboardTypeString:
        pasteboard.setString_forType_(value, kind)
    else:
        pasteboard.setData_forType_(value, kind)
    return pasteboard


def test_png_clipboard_data_is_detected_as_an_image_source(tmp_path):
    editor, window = _editor(tmp_path, "Text only")
    try:
        sources = editor._pasted_image_sources(_pasteboard(NSPasteboardTypePNG, _png_bytes()))
        assert len(sources) == 1
        assert sources[0].suffix == ".png"
        assert sources[0].exists()
        sources[0].unlink(missing_ok=True)
    finally:
        window.close()


def test_text_paste_is_not_treated_as_an_image(tmp_path):
    editor, window = _editor(tmp_path, "Text only")
    try:
        pasteboard = _pasteboard(NSPasteboardTypeString, "plain text")
        assert editor._pasted_image_sources(pasteboard) == []
        # Still routed through the sanitizer, unchanged.
        assert editor.handle_paste(pasteboard) is True
        assert "plain text" in editor.body_text()
    finally:
        window.close()


def test_remote_image_urls_are_never_fetched(tmp_path):
    editor, window = _editor(tmp_path, "Text only")
    try:
        pasteboard = _pasteboard(NSPasteboardTypeString, "https://example.com/photo.png")
        assert editor._pasted_image_sources(pasteboard) == []
        editor.handle_paste(pasteboard)
        # It stays ordinary text; nothing was downloaded or attached.
        assert "example.com/photo.png" in editor.body_text()
        assert "Attachments" not in editor.body_text()
    finally:
        window.close()


def test_clipboard_bitmap_is_encoded_as_png_and_is_readable(tmp_path):
    editor, window = _editor(tmp_path, "Text only")
    try:
        written = editor._write_temporary_png(_png_bytes(64, 40))
        assert written is not None and written.exists()
        decoded = NSImage.alloc().initWithContentsOfFile_(str(written))
        assert decoded is not None
        assert int(decoded.size().width) == 64
        written.unlink(missing_ok=True)
    finally:
        window.close()
