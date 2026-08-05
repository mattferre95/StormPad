"""Image selection geometry: the border must hug the bitmap, not the line.

The reported bug was a tall blue band above the image. Three causes compounded:
the image paragraph inflated its line fragment to 135% of the bitmap height, the
attachment character was selected so AppKit painted its own highlight across that
whole fragment, and the handles were positioned from the inflated rectangle so
clicks missed them. These pin all three.
"""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

import pytest
from AppKit import (
    NSApplication,
    NSAttachmentAttributeName,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSBitmapImageFileTypePNG,
    NSBitmapImageRep,
    NSColor,
    NSImage,
    NSTitledWindowMask,
    NSWindow,
)
from Foundation import NSMakePoint, NSMakeRange, NSMakeRect, NSMakeSize

from stormpad.models import IDEAS, Note
from stormpad.theme import get_theme
from stormpad.views.block_editor import (
    _IMAGE_HANDLE_HIT,
    Editor,
    _resize_edge_at,
)
from stormpad.views.palette import Palette

WIDE_W, WIDE_H = 640, 360  # 16:9, the shape from the bug report


def _wide_note(tmp: Path):
    notes = tmp / "Notes"
    notes.mkdir(parents=True, exist_ok=True)
    attachments = tmp / "Attachments" / "geo"
    attachments.mkdir(parents=True, exist_ok=True)
    image = NSImage.alloc().initWithSize_(NSMakeSize(WIDE_W, WIDE_H))
    image.lockFocus()
    NSColor.systemBlueColor().set()
    NSBezierPath.fillRect_(NSMakeRect(0, 0, WIDE_W, WIDE_H))
    image.unlockFocus()
    rep = NSBitmapImageRep.imageRepWithData_(image.TIFFRepresentation())
    rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, {}).writeToFile_atomically_(
        str(attachments / "wide.png"), True
    )
    note_path = notes / "geo.md"
    note_path.write_text("", encoding="utf-8")
    return notes, note_path


@pytest.fixture
def editor():
    NSApplication.sharedApplication()
    tmp = Path(tempfile.mkdtemp(prefix="stormpad-geo-"))
    notes, note_path = _wide_note(tmp)
    instance = Editor.alloc().initWithPalette_onTitle_onBody_onAttachment_(
        Palette(get_theme("deep_dark")),
        lambda _text: None,
        lambda _text: None,
        lambda _kind, _path: None,
    )
    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, 900, 700), NSTitledWindowMask, NSBackingStoreBuffered, False
    )
    instance.view.setFrame_(window.contentView().bounds())
    window.contentView().addSubview_(instance.view)
    instance.notes_dir = notes
    now = datetime.now()
    instance.load_note(
        Note(
            id="geo",
            path=note_path,
            title="Geo",
            body="Text before\n\n![Wide](../Attachments/geo/wide.png)\n\nText after",
            category=IDEAS,
            created_at=now,
            updated_at=now,
        )
    )
    instance._body.layoutManager().ensureLayoutForTextContainer_(
        instance._body.textContainer()
    )
    yield instance
    window.close()


def _attachment_index(editor):
    storage = editor._body.textStorage()
    for index in range(storage.length()):
        if storage.attributesAtIndex_effectiveRange_(index, None)[0].get(
            NSAttachmentAttributeName
        ):
            return index
    raise AssertionError("no attachment found")


def _cell(editor, index):
    attrs = editor._body.textStorage().attributesAtIndex_effectiveRange_(index, None)[0]
    return attrs.get(NSAttachmentAttributeName).attachmentCell()


# --- the oversized band --------------------------------------------------------


def test_image_line_hugs_the_bitmap_instead_of_inflating(editor):
    """The 135% line height multiple was the empty band above the image."""
    index = _attachment_index(editor)
    manager = editor._body.layoutManager()
    glyphs = manager.glyphRangeForCharacterRange_actualCharacterRange_(
        NSMakeRange(index, 1), None
    )
    if isinstance(glyphs, tuple):
        glyphs = glyphs[0]
    used = manager.lineFragmentUsedRectForGlyphAtIndex_effectiveRange_(glyphs.location, None)
    if isinstance(used, tuple):
        used = used[0]
    cell_height = float(_cell(editor, index).cellSize().height)

    # Within a point: the drawn line is the bitmap, with no spare band.
    assert abs(float(used.size.height) - cell_height) <= 1.0


def test_actual_image_rect_matches_the_displayed_bitmap(editor):
    index = _attachment_index(editor)
    cell = _cell(editor, index)
    rect = editor.actual_image_rect(index)

    assert rect is not None
    assert abs(float(rect.size.width) - float(cell.cellSize().width)) <= 1.0
    assert abs(float(rect.size.height) - float(cell.cellSize().height)) <= 1.0
    # Aspect ratio of the source survives.
    ratio = float(rect.size.width) / float(rect.size.height)
    assert abs(ratio - (WIDE_W / WIDE_H)) < 0.02


def test_actual_image_rect_is_not_the_line_fragment(editor):
    """Regression guard: the old code used the taller bounding rectangle."""
    index = _attachment_index(editor)
    manager = editor._body.layoutManager()
    glyphs = manager.glyphRangeForCharacterRange_actualCharacterRange_(
        NSMakeRange(index, 1), None
    )
    if isinstance(glyphs, tuple):
        glyphs = glyphs[0]
    fragment = manager.lineFragmentRectForGlyphAtIndex_effectiveRange_(glyphs.location, None)
    if isinstance(fragment, tuple):
        fragment = fragment[0]
    rect = editor.actual_image_rect(index)

    assert float(rect.size.height) <= float(fragment.size.height)


# --- object selection versus text selection ------------------------------------


def test_selecting_an_image_leaves_a_zero_length_text_selection(editor):
    index = _attachment_index(editor)
    editor._body.setSelectedRange_(NSMakeRange(index, 0))
    block_index = editor._selectable_image_indexes()[0]
    editor.select_image_block(block_index)

    assert int(editor._body.selectedRange().length) == 0
    assert editor.selected_image_indexes() == [block_index]


def test_zero_length_selection_keeps_the_text_toolbar_away(editor):
    from stormpad.uihelpers import formatting_toolbar_visible

    index = _attachment_index(editor)
    editor._body.setSelectedRange_(NSMakeRange(index, 0))

    # The text formatting toolbar is driven by a non-empty text selection, so
    # collapsing to a caret is what keeps it away from a selected image.
    length = int(editor._body.selectedRange().length)
    assert length == 0
    assert formatting_toolbar_visible(selection_length=length, editor_focused=True) is False
    # The old behaviour selected the attachment character, which raised it.
    assert formatting_toolbar_visible(selection_length=1, editor_focused=True) is True


def test_image_selection_never_reaches_the_markdown(editor):
    before = editor.body_text()
    editor.select_image_block(editor._selectable_image_indexes()[0])

    assert editor.body_text() == before
    assert "selected" not in editor.body_text()


# --- text flow -----------------------------------------------------------------


def test_alt_text_does_not_render_beside_the_image(editor):
    """The alt text used to be drawn on the image's own line."""
    lines = str(editor._body.string()).split("\n")
    image_line = next(line for line in lines if "￼" in line)

    assert image_line.strip() == "￼"
    assert "Wide" not in image_line


def test_following_text_starts_on_its_own_line_below(editor):
    lines = str(editor._body.string()).split("\n")
    image_row = next(i for i, line in enumerate(lines) if "￼" in line)

    assert lines[image_row + 1].strip() == "Text after"


def test_alt_text_is_still_preserved_in_the_markdown(editor):
    assert "![Wide](" in editor.body_text()


# --- handles and edges ---------------------------------------------------------


@pytest.mark.parametrize(
    "edge",
    ["top_left", "top_right", "bottom_left", "bottom_right", "left", "right"],
)
def test_every_handle_is_hit_at_its_centre(editor, edge):
    index = _attachment_index(editor)
    cell = _cell(editor, index)
    rect = editor.actual_image_rect(index)
    handle = cell.handle_rects(rect)[edge]
    centre = NSMakePoint(
        float(handle.origin.x) + float(handle.size.width) / 2.0,
        float(handle.origin.y) + float(handle.size.height) / 2.0,
    )

    assert _resize_edge_at(centre, rect, cell) == edge


def test_handles_have_a_forgiving_hit_area(editor):
    """A near miss still grabs the handle: no pixel-perfect clicking."""
    index = _attachment_index(editor)
    cell = _cell(editor, index)
    rect = editor.actual_image_rect(index)
    handle = cell.handle_rects(rect)["bottom_right"]
    near = NSMakePoint(
        float(handle.origin.x) + float(handle.size.width) / 2.0 + _IMAGE_HANDLE_HIT / 3.0,
        float(handle.origin.y) + float(handle.size.height) / 2.0,
    )

    assert _resize_edge_at(near, rect, cell) is not None


def test_the_image_interior_is_not_a_resize_target(editor):
    index = _attachment_index(editor)
    cell = _cell(editor, index)
    rect = editor.actual_image_rect(index)
    centre = NSMakePoint(
        float(rect.origin.x) + float(rect.size.width) / 2.0,
        float(rect.origin.y) + float(rect.size.height) / 2.0,
    )

    assert _resize_edge_at(centre, rect, cell) is None


def test_border_bands_resize_from_the_left_and_right_edges(editor):
    index = _attachment_index(editor)
    cell = _cell(editor, index)
    rect = editor.actual_image_rect(index)
    mid_y = float(rect.origin.y) + float(rect.size.height) / 3.0

    assert _resize_edge_at(NSMakePoint(float(rect.origin.x), mid_y), rect, cell) is not None
    right_x = float(rect.origin.x) + float(rect.size.width)
    assert _resize_edge_at(NSMakePoint(right_x, mid_y), rect, cell) is not None


def test_geometry_survives_a_width_change(editor):
    """Resizing must keep the border attached to the bitmap."""
    index = _attachment_index(editor)
    cell = _cell(editor, index)
    cell.display_width = 240.0
    editor._body.layoutManager().invalidateLayoutForCharacterRange_actualCharacterRange_(
        NSMakeRange(0, editor._body.textStorage().length()), None
    )
    editor._body.layoutManager().ensureLayoutForTextContainer_(editor._body.textContainer())

    rect = editor.actual_image_rect(index)
    assert abs(float(rect.size.width) - 240.0) <= 1.0
    ratio = float(rect.size.width) / float(rect.size.height)
    assert abs(ratio - (WIDE_W / WIDE_H)) < 0.02


# --- geometry-first hit testing -------------------------------------------------
#
# characterIndexForInsertionAtPoint_ returns an *insertion* index, so anywhere
# right of the attachment glyph's midpoint it reports the following character.
# Hit testing that relied on it therefore failed across the entire right half of
# every image, taking the right-hand resize handles with it. These pin the
# geometry-based replacement.


def test_image_interior_is_hit_across_its_full_width(editor):
    index = _attachment_index(editor)
    rect = editor.actual_image_rect(index)
    for fraction in (0.1, 0.3, 0.5, 0.7, 0.9):
        point = NSMakePoint(
            float(rect.origin.x) + float(rect.size.width) * fraction,
            float(rect.origin.y) + float(rect.size.height) / 2.0,
        )
        assert editor.image_hit_test(point) is not None, f"missed at {fraction:.0%} width"


def test_the_right_half_of_an_image_resolves_to_the_wrong_character_index(editor):
    """Documents the underlying AppKit behaviour the hit test works around."""
    index = _attachment_index(editor)
    rect = editor.actual_image_rect(index)
    right_of_middle = NSMakePoint(
        float(rect.origin.x) + float(rect.size.width) * 0.9,
        float(rect.origin.y) + float(rect.size.height) / 2.0,
    )
    reported = int(editor._body.characterIndexForInsertionAtPoint_(right_of_middle))

    assert reported != index, "insertion index no longer drifts; the workaround may be removable"
    # Geometry still finds the image despite the drifting index.
    assert editor.image_hit_test(right_of_middle) is not None


@pytest.mark.parametrize(
    "edge",
    ["top_left", "top_right", "bottom_left", "bottom_right", "left", "right"],
)
def test_every_handle_is_reachable_through_hit_testing(editor, edge):
    index = _attachment_index(editor)
    cell = _cell(editor, index)
    rect = editor.actual_image_rect(index)
    handle = cell.handle_rects(rect)[edge]
    centre = NSMakePoint(
        float(handle.origin.x) + float(handle.size.width) / 2.0,
        float(handle.origin.y) + float(handle.size.height) / 2.0,
    )

    hit = editor.image_hit_test(centre)
    assert hit is not None
    assert hit[4] == edge, "handle must report its own edge, not an interior hit"


def test_interior_hit_reports_no_edge_so_it_will_not_resize(editor):
    index = _attachment_index(editor)
    rect = editor.actual_image_rect(index)
    centre = NSMakePoint(
        float(rect.origin.x) + float(rect.size.width) / 2.0,
        float(rect.origin.y) + float(rect.size.height) / 2.0,
    )

    hit = editor.image_hit_test(centre)
    assert hit is not None
    assert hit[4] is None


def test_points_outside_every_image_are_not_hits(editor):
    index = _attachment_index(editor)
    rect = editor.actual_image_rect(index)
    far_below = NSMakePoint(
        float(rect.origin.x) + float(rect.size.width) / 2.0,
        float(rect.origin.y) + float(rect.size.height) + 120.0,
    )

    assert editor.image_hit_test(far_below) is None


def test_hidden_images_are_not_hit_targets(editor):
    """A collapsed toggle must make its image unreachable by the mouse."""
    index = _attachment_index(editor)
    rect = editor.actual_image_rect(index)
    centre = NSMakePoint(
        float(rect.origin.x) + float(rect.size.width) / 2.0,
        float(rect.origin.y) + float(rect.size.height) / 2.0,
    )
    assert editor.image_hit_test(centre) is not None

    # Hidden blocks are excluded from the selectable set the hit test walks.
    original = editor._selectable_image_indexes
    editor._selectable_image_indexes = lambda: []
    try:
        assert editor.image_hit_test(centre) is None
    finally:
        editor._selectable_image_indexes = original
