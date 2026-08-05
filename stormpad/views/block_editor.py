"""Native page-like block editor built on AppKit's text system.

The title is a native text field and body blocks live in one rich NSTextView.
Paragraph attributes carry block semantics; inline attributes carry formatting
semantics. Markdown conversion remains in the AppKit-free parser/serializer.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import objc
from AppKit import (
    NSAlert,
    NSAttachmentAttributeName,
    NSAttributedString,
    NSBackgroundColorAttributeName,
    NSBaselineOffsetAttributeName,
    NSBezierPath,
    NSBitmapImageFileTypePNG,
    NSBitmapImageRep,
    NSBoldFontMask,
    NSButton,
    NSColor,
    NSDirectionalEdgeInsetsMake,
    NSDragOperationCopy,
    NSEventModifierFlagCommand,
    NSEventModifierFlagOption,
    NSEventModifierFlagShift,
    NSFilenamesPboardType,
    NSFont,
    NSFontAttributeName,
    NSFontManager,
    NSForegroundColorAttributeName,
    NSImage,
    NSImageOnly,
    NSItalicFontMask,
    NSKernAttributeName,
    NSLinkAttributeName,
    NSMenu,
    NSMenuItem,
    NSMutableAttributedString,
    NSMutableParagraphStyle,
    NSNoBorder,
    NSParagraphStyleAttributeName,
    NSPasteboardTypePNG,
    NSPasteboardTypeRTF,
    NSPasteboardTypeRTFD,
    NSPasteboardTypeString,
    NSPasteboardTypeTIFF,
    NSPasteboardURLReadingFileURLsOnlyKey,
    NSScrollerStyleOverlay,
    NSScrollView,
    NSTextAlignmentCenter,
    NSTextAlignmentLeft,
    NSTextAlignmentRight,
    NSTextAttachment,
    NSTextAttachmentCell,
    NSTextField,
    NSTextView,
    NSTimer,
    NSTrackingActiveInKeyWindow,
    NSTrackingArea,
    NSTrackingInVisibleRect,
    NSTrackingMouseEnteredAndExited,
    NSTrackingMouseMoved,
    NSUnderlineStyleAttributeName,
    NSUnderlineStyleSingle,
    NSViewHeightSizable,
    NSViewWidthSizable,
    NSWorkspace,
)
from Foundation import NSURL, NSMakePoint, NSMakeRange, NSMakeRect, NSMakeSize, NSObject

from .. import attachments
from ..block_parser import parse_blocks
from ..block_serializer import serialize_blocks
from ..blocks import (
    COLOR_TOKENS,
    PARAGRAPH_BLOCK_TYPES,
    Block,
    BlockType,
    InlineMark,
    InlineRun,
    MarkType,
    apply_block_command,
    backspace_empty_result,
    convert_selected_blocks,
    empty_return_result,
    insert_block,
    insert_block_after_selection,
    is_toggle,
    merge_empty_block_backward,
    next_block_after_return,
    normalize_alignment,
    numbered_display_number,
    reorder_blocks,
    split_block_after_return,
    toggle_todo,
)
from ..collapse import (
    hidden_indexes,
    reveal_for_conversion,
    toggle_range,
)
from ..models import Note, move_transcript_chunk, remove_transcript_chunk
from ..motion import AnimationToken, Motion
from ..paste import PastedRun, pasted_blocks
from ..uihelpers import (
    SaveStatus,
    block_gutter_canvas_y,
    block_gutter_layout,
    block_index_for_location,
    block_indices_for_selection,
    formatting_toolbar_visible,
    gutter_hover_hit,
    title_command_focus,
    title_display_text,
)
from .color_palette import build_color_palette_view
from .controls import FlippedView, label, rounded_view
from .layout import MAIN_COLUMN_TOP_INSET, add, pin_edges, set_height, set_width
from .motion import anim, can_animate, current_policy
from .motion import run as run_animation  # `run` is a local name in this module
from .palette import Palette, serif_font, symbol_image

_ATTR_BLOCK = "StormPadBlockType"
_ATTR_CHECKED = "StormPadChecked"
_ATTR_INDENT = "StormPadIndent"
_ATTR_TARGET = "StormPadTarget"
_ATTR_ALT = "StormPadAlt"
_ATTR_COLLAPSED = "StormPadCollapsed"
_ATTR_DECORATION = "StormPadDecoration"
_ATTR_READ_ONLY = "StormPadReadOnly"
_ATTR_BOLD = "StormPadBold"
_ATTR_ITALIC = "StormPadItalic"
_ATTR_UNDERLINE = "StormPadUnderline"
_ATTR_TEXT_COLOR = "StormPadTextColor"
_ATTR_HIGHLIGHT = "StormPadHighlight"
_ATTR_LINK = "StormPadLink"
_ATTR_RAW = "StormPadRaw"
_ATTR_TRANSCRIPT_CHUNK = "StormPadTranscriptChunk"
_ATTR_IMAGE_WIDTH = "StormPadImageWidth"
_ATTR_IMAGE_ALIGNMENT = "StormPadImageAlignment"
_ZERO_WIDTH = "\u200b"
# NSFontDescriptor symbolic traits. Read from the descriptor rather than
# NSFontManager so pasted-font detection does not depend on the shared manager.
_TRAIT_ITALIC = 1 << 0
_TRAIT_BOLD = 1 << 1
_LINE_SEPARATOR = "\u2028"
_BODY_INSET = 92.0
_TODO_TEXT_GAP = 9.0
_CARET_BOTTOM_MARGIN = 88.0
_EDITOR_BOTTOM_INSET = 200.0
# Divider block: a deliberate inset from the writing margins, and the vertical
# room the rule occupies on its own line.
_DIVIDER_INSET = 6.0
_DIVIDER_ROW_HEIGHT = 13.0
_DIVIDER_MIN_WIDTH = 24.0
_DIVIDER_THICKNESS = 1.0
_IMAGE_MIN_WIDTH = 96.0
_IMAGE_DEFAULT_MAX_WIDTH = 520.0
_IMAGE_HANDLE_SIZE = 10.0
_IMAGE_HANDLE_HIT = 22.0
_IMAGE_EDGE_BAND = 8.0
_IMAGE_ALIGNMENT_MAP = {
    "left": NSTextAlignmentLeft,
    "center": NSTextAlignmentCenter,
    "right": NSTextAlignmentRight,
}


class DividerAttachmentCell(NSTextAttachmentCell):
    """Draws a horizontal rule that spans the editor's usable text width.

    The width comes from the proposed line-fragment rect supplied by the text
    system, so the rule follows the real writing canvas: it re-lays out for free
    on window resize, fullscreen, and notes-panel collapse, stays aligned with
    the note's text, and never reaches under the block gutter (which lives
    outside the text container inset).
    """

    def initWithColor_(self, color):  # noqa: N802
        self = objc.super(DividerAttachmentCell, self).init()
        if self is None:
            return None
        self._rule_color = color
        return self

    def cellSize(self):  # noqa: N802
        return NSMakeSize(_DIVIDER_MIN_WIDTH, _DIVIDER_ROW_HEIGHT)

    def cellBaselineOffset(self):  # noqa: N802
        return NSMakePoint(0.0, -4.0)

    def cellFrameForTextContainer_proposedLineFragment_glyphPosition_characterIndex_(  # noqa: N802
        self, container, line_fragment, position, char_index
    ):
        available = float(line_fragment.size.width) - float(position.x)
        return NSMakeRect(
            0.0, 0.0, max(_DIVIDER_MIN_WIDTH, available), _DIVIDER_ROW_HEIGHT
        )

    def drawWithFrame_inView_(self, frame, view):  # noqa: N802
        color = getattr(self, "_rule_color", None)
        if color is None:
            return
        width = float(frame.size.width) - (_DIVIDER_INSET * 2.0)
        if width <= 0:
            return
        rule = NSMakeRect(
            float(frame.origin.x) + _DIVIDER_INSET,
            float(frame.origin.y) + (float(frame.size.height) - _DIVIDER_THICKNESS) / 2.0,
            width,
            _DIVIDER_THICKNESS,
        )
        color.set()
        NSBezierPath.fillRect_(rule)



def _within_hit_area(point, rect, minimum: float) -> bool:
    """Whether a click lands on a handle, padded out to a usable target size."""
    pad_x = max(0.0, (minimum - float(rect.size.width)) / 2.0)
    pad_y = max(0.0, (minimum - float(rect.size.height)) / 2.0)
    return (
        float(rect.origin.x) - pad_x <= float(point.x)
        <= float(rect.origin.x) + float(rect.size.width) + pad_x
        and float(rect.origin.y) - pad_y <= float(point.y)
        <= float(rect.origin.y) + float(rect.size.height) + pad_y
    )



def _resize_edge_at(point, bitmap, cell):
    """Which resize edge a click lands on, or ``None`` for the image interior.

    Handles win, then a forgiving band along the left and right borders, so the
    user never has to hit the small square exactly. The interior is deliberately
    excluded: dragging there moves the image rather than resizing it.
    """
    for edge, rect in cell.handle_rects(bitmap).items():
        if _within_hit_area(point, rect, _IMAGE_HANDLE_HIT):
            return edge
    x, y = float(point.x), float(point.y)
    left, right = float(bitmap.origin.x), float(bitmap.origin.x + bitmap.size.width)
    top, bottom = float(bitmap.origin.y), float(bitmap.origin.y + bitmap.size.height)
    if not (top - _IMAGE_EDGE_BAND <= y <= bottom + _IMAGE_EDGE_BAND):
        return None
    if abs(x - left) <= _IMAGE_EDGE_BAND:
        return "left"
    if abs(x - right) <= _IMAGE_EDGE_BAND:
        return "right"
    return None


class ImageAttachmentCell(NSTextAttachmentCell):
    """Width-aware image cell with a restrained selection outline and handle."""

    def initWithImage_width_editor_index_(self, image, width, editor, index):  # noqa: N802
        self = objc.super(ImageAttachmentCell, self).initImageCell_(image)
        if self is None:
            return None
        source = image.size()
        self._aspect = max(0.01, float(source.width) / max(1.0, float(source.height)))
        self.display_width = max(_IMAGE_MIN_WIDTH, float(width))
        self.editor = editor
        self.block_index = int(index)
        return self

    def cellSize(self):  # noqa: N802
        return NSMakeSize(self.display_width, self.display_width / self._aspect)

    def cellFrameForTextContainer_proposedLineFragment_glyphPosition_characterIndex_(  # noqa: N802
        self, container, line_fragment, position, char_index
    ):
        available = max(
            _IMAGE_MIN_WIDTH,
            float(line_fragment.size.width) - float(position.x),
        )
        width = min(float(self.display_width), available)
        return NSMakeRect(0.0, 0.0, width, width / self._aspect)

    @objc.python_method
    def handle_rects(self, frame) -> dict:
        """Visible handle rectangles keyed by the edge each one drags.

        Corners plus left and right midpoints. Every handle resizes on width and
        keeps the aspect ratio, so there is no way to distort an image.
        """
        size = _IMAGE_HANDLE_SIZE
        half = size / 2.0
        x0, y0 = float(frame.origin.x), float(frame.origin.y)
        width, height = float(frame.size.width), float(frame.size.height)
        return {
            "top_left": NSMakeRect(x0 - half, y0 - half, size, size),
            "top_right": NSMakeRect(x0 + width - half, y0 - half, size, size),
            "bottom_left": NSMakeRect(x0 - half, y0 + height - half, size, size),
            "bottom_right": NSMakeRect(x0 + width - half, y0 + height - half, size, size),
            "left": NSMakeRect(x0 - half, y0 + height / 2.0 - half, size, size),
            "right": NSMakeRect(x0 + width - half, y0 + height / 2.0 - half, size, size),
        }

    def drawWithFrame_inView_(self, frame, view):  # noqa: N802
        objc.super(ImageAttachmentCell, self).drawWithFrame_inView_(frame, view)
        editor = getattr(self, "editor", None)
        if editor is None or self.block_index not in editor._selected_image_indexes:
            return
        # `frame` is already the cell's own rectangle, which is the bitmap, so the
        # chrome hugs the image rather than the taller line fragment.
        palette = editor._palette
        # Theme tokens only, so the chrome stays readable on every theme and
        # never bakes a colour into the image itself.
        palette.accent.colorWithAlphaComponent_(0.14).set()
        NSBezierPath.fillRect_(frame)
        palette.accent.colorWithAlphaComponent_(0.9).set()
        border = NSBezierPath.bezierPathWithRect_(frame)
        border.setLineWidth_(2.0)
        border.stroke()
        for rect in self.handle_rects(frame).values():
            palette.editor_background.set()
            NSBezierPath.fillRect_(rect)
            palette.accent.set()
            outline = NSBezierPath.bezierPathWithRect_(rect)
            outline.setLineWidth_(1.5)
            outline.stroke()
_BLOCK_MENU: tuple[tuple[str, BlockType, str], ...] = (
    ("Text", BlockType.TEXT, "text.alignleft"),
    ("Heading 1", BlockType.HEADING_1, "textformat.size.larger"),
    ("Heading 2", BlockType.HEADING_2, "textformat.size"),
    ("Heading 3", BlockType.HEADING_3, "textformat"),
    ("To-do", BlockType.TODO, "checkmark.square"),
    ("Bulleted List", BlockType.BULLET, "list.bullet"),
    ("Numbered List", BlockType.NUMBERED, "list.number"),
    ("Quote", BlockType.QUOTE, "quote.opening"),
    ("Toggle List", BlockType.TOGGLE, "chevron.right"),
    ("Toggle Heading 1", BlockType.TOGGLE_HEADING_1, "chevron.right.square"),
    ("Toggle Heading 2", BlockType.TOGGLE_HEADING_2, "chevron.right.square"),
    ("Toggle Heading 3", BlockType.TOGGLE_HEADING_3, "chevron.right.square"),
    ("Divider", BlockType.DIVIDER, "minus"),
    ("Link", BlockType.LINK, "link"),
    ("Image", BlockType.IMAGE, "photo"),
    ("File", BlockType.FILE, "doc"),
    ("Transcript", BlockType.TRANSCRIPT, "waveform"),
)
# Block-edit menu: paragraph types this block can be turned into, in place.
_BLOCK_EDIT_MENU: tuple[tuple[str, BlockType, str], ...] = (
    ("Text", BlockType.TEXT, "text.alignleft"),
    ("Heading 1", BlockType.HEADING_1, "textformat.size.larger"),
    ("Heading 2", BlockType.HEADING_2, "textformat.size"),
    ("Heading 3", BlockType.HEADING_3, "textformat"),
    ("To-do", BlockType.TODO, "checkmark.square"),
    ("Bulleted List", BlockType.BULLET, "list.bullet"),
    ("Numbered List", BlockType.NUMBERED, "list.number"),
    ("Quote", BlockType.QUOTE, "quote.opening"),
    ("Toggle List", BlockType.TOGGLE, "chevron.right"),
    ("Toggle Heading 1", BlockType.TOGGLE_HEADING_1, "chevron.right.square"),
    ("Toggle Heading 2", BlockType.TOGGLE_HEADING_2, "chevron.right.square"),
    ("Toggle Heading 3", BlockType.TOGGLE_HEADING_3, "chevron.right.square"),
)


class EditorCanvas(FlippedView):
    """Editor surface that reports hover motion across text and gutter."""

    def init(self):
        self = objc.super(EditorCanvas, self).init()
        if self is None:
            return None
        self._tracking = None
        self.stormpad_editor = None
        return self

    def updateTrackingAreas(self):  # noqa: N802
        objc.super(EditorCanvas, self).updateTrackingAreas()
        if self._tracking is not None:
            self.removeTrackingArea_(self._tracking)
        options = (
            NSTrackingMouseMoved
            | NSTrackingMouseEnteredAndExited
            | NSTrackingActiveInKeyWindow
            | NSTrackingInVisibleRect
        )
        self._tracking = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
            self.bounds(), options, self, None
        )
        self.addTrackingArea_(self._tracking)

    def viewDidMoveToWindow(self):  # noqa: N802
        objc.super(EditorCanvas, self).viewDidMoveToWindow()
        if self.window() is not None:
            self.window().setAcceptsMouseMovedEvents_(True)

    def mouseMoved_(self, event):  # noqa: N802
        if self.stormpad_editor is not None:
            point = self.convertPoint_fromView_(event.locationInWindow(), None)
            self.stormpad_editor.hover_canvas_point(point)

    def mouseExited_(self, event):  # noqa: N802
        if self.stormpad_editor is not None:
            self.stormpad_editor.clear_block_hover()


class GutterButton(NSButton):
    """Theme-aware gutter button with a visible native hover state."""

    def init(self):
        self = objc.super(GutterButton, self).init()
        if self is None:
            return None
        self._tracking = None
        self.stormpad_idle_color = None
        self.stormpad_hover_color = None
        return self

    def updateTrackingAreas(self):  # noqa: N802
        objc.super(GutterButton, self).updateTrackingAreas()
        if self._tracking is not None:
            self.removeTrackingArea_(self._tracking)
        options = (
            NSTrackingMouseEnteredAndExited | NSTrackingActiveInKeyWindow | NSTrackingInVisibleRect
        )
        self._tracking = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
            self.bounds(), options, self, None
        )
        self.addTrackingArea_(self._tracking)

    def mouseEntered_(self, event):  # noqa: N802
        if self.stormpad_hover_color is not None:
            self.layer().setBackgroundColor_(self.stormpad_hover_color.CGColor())

    def mouseExited_(self, event):  # noqa: N802
        if self.stormpad_idle_color is not None:
            self.layer().setBackgroundColor_(self.stormpad_idle_color.CGColor())


class GutterHoverView(FlippedView):
    """Transparent tracker covering only the reserved left block gutter."""

    def init(self):
        self = objc.super(GutterHoverView, self).init()
        if self is None:
            return None
        self._tracking = None
        self.stormpad_editor = None
        return self

    def updateTrackingAreas(self):  # noqa: N802
        objc.super(GutterHoverView, self).updateTrackingAreas()
        if self._tracking is not None:
            self.removeTrackingArea_(self._tracking)
        options = (
            NSTrackingMouseMoved
            | NSTrackingMouseEnteredAndExited
            | NSTrackingActiveInKeyWindow
            | NSTrackingInVisibleRect
        )
        self._tracking = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
            self.bounds(), options, self, None
        )
        self.addTrackingArea_(self._tracking)

    def mouseMoved_(self, event):  # noqa: N802
        if self.stormpad_editor is not None:
            point = self.stormpad_editor.view.convertPoint_fromView_(event.locationInWindow(), None)
            self.stormpad_editor.hover_canvas_point(point)

    def mouseExited_(self, event):  # noqa: N802
        if self.stormpad_editor is not None:
            self.stormpad_editor.clear_block_hover()

    def scrollWheel_(self, event):  # noqa: N802
        if self.stormpad_editor is not None:
            self.stormpad_editor._body.scrollWheel_(event)


def _attr_value(attrs: dict, key: str, default=None):
    value = attrs.get(key)
    return default if value is None else value


def _utf16_length(value: str) -> int:
    """Return the range length used by Cocoa's UTF-16 text APIs."""
    return len(value.encode("utf-16-le")) // 2


def _python_offset_from_utf16(value: str, offset: int) -> int:
    """Map an AppKit UTF-16 offset onto a safe Python string boundary."""
    target = max(0, int(offset))
    consumed = 0
    for index, character in enumerate(value):
        next_consumed = consumed + _utf16_length(character)
        if next_consumed > target:
            return index
        consumed = next_consumed
    return len(value)


def editable_prefix_end(
    decoration: str | None,
    line_start: int,
    decorated_end: int,
    line_end: int,
) -> int:
    """To-do caret floor; the checkbox decoration is never editable text."""
    if decoration != "todo":
        return int(line_start)
    return min(int(line_end), max(int(line_start), int(decorated_end)))


def _font_traits(font) -> int:
    """Symbolic traits for a pasted font, tolerating fonts without a descriptor."""
    if font is None:
        return 0
    try:
        return int(font.fontDescriptor().symbolicTraits())
    except (AttributeError, TypeError, ValueError):
        try:
            return int(NSFontManager.sharedFontManager().traitsOfFont_(font))
        except (AttributeError, TypeError, ValueError):
            return 0



class FoldingLayoutDelegate(NSObject):
    """Collapses hidden lines to zero height without touching text storage.

    The complete note always stays in ``NSTextStorage``; only the layout of the
    ranges listed in ``hidden_ranges`` is suppressed. Combined with a clear
    temporary foreground attribute (also layout-only), that hides content while
    leaving every block available to extraction, autosave, search, and export.
    """

    def initWithEditor_(self, editor):  # noqa: N802
        self = objc.super(FoldingLayoutDelegate, self).init()
        if self is None:
            return None
        self._hidden: list[tuple[int, int]] = []
        return self

    def setHiddenRanges_(self, ranges):  # noqa: N802
        self._hidden = [(int(start), int(length)) for start, length in ranges]

    @objc.python_method
    def _is_hidden(self, location: int) -> bool:
        return any(start <= location < start + length for start, length in self._hidden)

    def layoutManager_shouldSetLineFragmentRect_lineFragmentUsedRect_baselineOffset_inTextContainer_forGlyphRange_(  # noqa: N802,E501
        self, manager, rect, used, baseline, container, glyph_range
    ):
        if not self._hidden:
            return (False, rect, used, baseline)
        try:
            chars = manager.characterRangeForGlyphRange_actualGlyphRange_(glyph_range, None)[0]
            location = int(chars.location)
        except (AttributeError, IndexError, TypeError, ValueError):
            return (False, rect, used, baseline)
        if not self._is_hidden(location):
            return (False, rect, used, baseline)
        flat = ((rect[0][0], rect[0][1]), (rect[1][0], 0.0))
        flat_used = ((used[0][0], used[0][1]), (used[1][0], 0.0))
        return (True, flat, flat_used, 0.0)


class BlockTextView(NSTextView):
    """NSTextView with local file-drop and to-do click handling."""

    def initWithFrame_(self, frame):  # noqa: N802
        self = objc.super(BlockTextView, self).initWithFrame_(frame)
        if self is not None:
            self._image_resize = None
        return self

    def draggingEntered_(self, sender):  # noqa: N802
        pasteboard = sender.draggingPasteboard()
        files = pasteboard.propertyListForType_(NSFilenamesPboardType)
        return NSDragOperationCopy if files else 0

    def draggingUpdated_(self, sender):  # noqa: N802
        return self.draggingEntered_(sender)

    def draggingExited_(self, sender):  # noqa: N802
        pass

    def performDragOperation_(self, sender):  # noqa: N802
        pasteboard = sender.draggingPasteboard()
        editor = getattr(self, "stormpad_editor", None)
        files = pasteboard.propertyListForType_(NSFilenamesPboardType) or []
        return bool(editor and editor.handle_dropped_files([Path(str(item)) for item in files]))

    def readSelectionFromPasteboard_(self, pasteboard):  # noqa: N802
        """Single choke point for every paste and text drop into the body.

        ``paste:``, ``pasteAsRichText:``, and text drags all funnel through
        here, so sanitizing once covers them all. Falling through to super
        keeps AppKit's own handling for anything the editor declines.
        """
        editor = getattr(self, "stormpad_editor", None)
        if editor is not None and editor.handle_paste(pasteboard):
            return True
        return objc.super(BlockTextView, self).readSelectionFromPasteboard_(pasteboard)

    def mouseDown_(self, event):  # noqa: N802
        editor = getattr(self, "stormpad_editor", None)
        if editor is not None:
            point = self.convertPoint_fromView_(event.locationInWindow(), None)
            try:
                index = self.characterIndexForInsertionAtPoint_(point)
                index = min(int(index), max(0, int(self.textStorage().length()) - 1))
                lines = str(self.string()).split("\n")
                block_index = block_index_for_location(str(self.string()), index)
                line_start = sum(
                    _utf16_length(line) + 1 for line in lines[:block_index]
                )
                line_attrs = self.textStorage().attributesAtIndex_effectiveRange_(
                    min(line_start, self.textStorage().length() - 1), None
                )[0]
                if line_attrs.get(_ATTR_DECORATION) in ("todo", "toggle"):
                    is_chevron = line_attrs.get(_ATTR_DECORATION) == "toggle"
                    layout = self.layoutManager()
                    glyph = layout.glyphRangeForCharacterRange_actualCharacterRange_(
                        NSMakeRange(line_start, 1), None
                    )
                    if isinstance(glyph, tuple):
                        glyph = glyph[0]
                    hit = layout.boundingRectForGlyphRange_inTextContainer_(
                        glyph, self.textContainer()
                    )
                    inset = self.textContainerInset()
                    if (
                        float(hit.origin.x + inset.width) - 4.0
                        <= float(point.x)
                        <= float(hit.origin.x + inset.width + hit.size.width) + 4.0
                        and float(hit.origin.y + inset.height) - 4.0
                        <= float(point.y)
                        <= float(hit.origin.y + inset.height + hit.size.height) + 4.0
                    ):
                        if is_chevron:
                            editor.toggle_collapsed_at_location(line_start)
                        else:
                            editor.toggle_todo_at_location(line_start)
                        return
                attrs = self.textStorage().attributesAtIndex_effectiveRange_(index, None)[0]
                if attrs.get(_ATTR_BLOCK) == BlockType.IMAGE.value:
                    modifiers = int(event.modifierFlags())
                    editor.select_image_block(
                        block_index,
                        command=bool(modifiers & NSEventModifierFlagCommand),
                        shift=bool(modifiers & NSEventModifierFlagShift),
                    )
                    # Object selection, not text selection. A selected
                    # attachment character makes AppKit paint its own highlight
                    # across the whole line fragment, which is the tall blue band
                    # above the bitmap, and it also raises the text formatting
                    # toolbar. Collapsing to a caret avoids both.
                    self.setSelectedRange_(NSMakeRange(index, 0))
                    self.setNeedsDisplay_(True)
                    attachment = attrs.get(NSAttachmentAttributeName)
                    cell = attachment.attachmentCell() if attachment is not None else None
                    bitmap = editor.actual_image_rect(index)
                    if cell is not None and bitmap is not None and hasattr(cell, "handle_rects"):
                        # Handles and edges come from the real bitmap rectangle,
                        # so a click lands where the user actually sees them.
                        edge = _resize_edge_at(point, bitmap, cell)
                        if edge is not None:
                            self._image_resize = (
                                block_index,
                                index,
                                float(point.x),
                                float(cell.display_width),
                                cell,
                                edge,
                            )
                    return
                editor.clear_image_selection()
                if attrs.get(_ATTR_DECORATION) == "todo":
                    editor.toggle_todo_at_location(index)
                    return
                if attrs.get(_ATTR_DECORATION) == "transcript-header":
                    self.setSelectedRange_(NSMakeRange(index, 0))
                    editor.toggle_current_transcript()
                    return
                if attrs.get(_ATTR_DECORATION) == "transcript-append":
                    if editor.transcript_target is not None:
                        editor.transcript_target.appendTranscript_(None)
                    return
                if attrs.get(_ATTR_BLOCK) == BlockType.FILE.value and int(event.clickCount()) >= 2:
                    self.setSelectedRange_(NSMakeRange(index, 0))
                    editor.openAttachment_(None)
                    return
            except (IndexError, TypeError, ValueError):
                pass
        objc.super(BlockTextView, self).mouseDown_(event)

    def mouseDragged_(self, event):  # noqa: N802
        if self._image_resize is None:
            objc.super(BlockTextView, self).mouseDragged_(event)
            return
        block_index, character_index, start_x, start_width, cell, edge = self._image_resize
        point = self.convertPoint_fromView_(event.locationInWindow(), None)
        usable = max(
            _IMAGE_MIN_WIDTH,
            float(self.textContainer().containerSize().width) - 8.0,
        )
        delta = float(point.x) - start_x
        if edge in ("top_left", "bottom_left", "left"):
            delta = -delta
        width = min(usable, max(_IMAGE_MIN_WIDTH, start_width + delta))
        cell.display_width = width
        self.layoutManager().invalidateLayoutForCharacterRange_actualCharacterRange_(
            NSMakeRange(character_index, 1), None
        )
        self.setNeedsDisplay_(True)

    def mouseUp_(self, event):  # noqa: N802
        if self._image_resize is None:
            objc.super(BlockTextView, self).mouseUp_(event)
            return
        block_index, _character_index, _start_x, _start_width, cell, _edge = self._image_resize
        self._image_resize = None
        editor = getattr(self, "stormpad_editor", None)
        if editor is not None:
            editor.persist_image_width(block_index, float(cell.display_width))

    def scrollWheel_(self, event):  # noqa: N802
        objc.super(BlockTextView, self).scrollWheel_(event)
        editor = getattr(self, "stormpad_editor", None)
        if editor is not None:
            editor._position_overlays()


class Editor(NSObject):
    """Own the clean editor canvas and acts as text/title delegate."""

    def initWithPalette_onTitle_onBody_onAttachment_(  # noqa: N802
        self, palette, on_title, on_body, on_attachment
    ):
        self = objc.super(Editor, self).init()
        if self is None:
            return None
        self._palette: Palette = palette
        self._on_title: Callable[[str], None] = on_title
        self._on_body: Callable[[str], None] = on_body
        self._on_attachment: Callable[[str, Path | None], Block | None] = on_attachment
        self._loading = False
        self._current: Note | None = None
        self._last_status = SaveStatus.SAVED
        self._hovered_block_index: int | None = None
        self._command_block_index: int | None = None
        self._command_option_pressed = False
        self._command_selection: tuple[int, int] | None = None
        self._context_block_index: int | None = None
        self._context_transcript_chunk: int | None = None
        # Multi-selection is ephemeral: block indexes only, recalculated after
        # every document change. `_selected_image_index` stays available as the
        # anchor so the existing selection code keeps working unchanged.
        self._selected_image_indexes: set[int] = set()
        self._image_anchor: int | None = None
        self._block_controls_enabled = True
        self._gutter_token = AnimationToken()
        self._block_menu = None
        self._color_menu = None
        self._color_recents: list[str] = []
        self.on_color_used = None
        self.before_structural_return: Callable[[], None] | None = None
        self._pending_return_token = 0
        self._pending_return_timer = None
        self._pending_return_note_id: str | None = None
        self._pending_caret_visibility_token = 0
        self._pending_caret_visibility_timer = None
        self._pending_caret_visibility_note_id: str | None = None
        self._full_note_selected = False
        self._setting_full_note_selection = False
        self.notes_dir: Path | None = None
        self.speech_target = None
        self.attachment_target = None
        self.transcript_target = None
        self._build()
        return self

    # -- construction -------------------------------------------------------

    def _build(self) -> None:
        p = self._palette
        self.view = EditorCanvas.alloc().init()
        self.view.setBackgroundColor_(p.editor_background)
        self.view.stormpad_editor = self

        self._status = add(self.view, label("", NSFont.systemFontOfSize_(11), p.text_muted))
        pin_edges(self._status, self.view, top=22, leading=None, trailing=28, bottom=None)
        self._status.setHidden_(True)

        title = NSTextField.alloc().init()
        title.setBordered_(False)
        title.setBezeled_(False)
        title.setDrawsBackground_(False)
        title.setFont_(serif_font(34.0))
        title.setTextColor_(p.title_text)
        title.setPlaceholderString_("Untitled")
        title.setDelegate_(self)
        title.setFocusRingType_(1)
        title.setAccessibilityLabel_("Note title")
        add(self.view, title)
        pin_edges(
            title,
            self.view,
            top=MAIN_COLUMN_TOP_INSET,
            leading=_BODY_INSET,
            trailing=_BODY_INSET,
            bottom=None,
        )
        set_height(title, 48)
        self._title = title

        scroll = add(self.view, NSScrollView.alloc().init())
        scroll.setDrawsBackground_(False)
        scroll.setBorderType_(NSNoBorder)
        scroll.setHasVerticalScroller_(True)
        scroll.setAutohidesScrollers_(True)
        scroll.setAutomaticallyAdjustsContentInsets_(False)
        scroll.setContentInsets_(
            NSDirectionalEdgeInsetsMake(0.0, 0.0, _EDITOR_BOTTOM_INSET, 0.0)
        )
        if hasattr(scroll, "setScrollerStyle_"):
            scroll.setScrollerStyle_(NSScrollerStyleOverlay)
        pin_edges(
            scroll,
            self.view,
            top=MAIN_COLUMN_TOP_INSET + 58,
            leading=52,
            trailing=52,
            bottom=18,
        )

        body = BlockTextView.alloc().initWithFrame_(NSMakeRect(0, 0, 500, 500))
        body.stormpad_editor = self
        # Layout-only folding. Retained on the editor so the delegate outlives
        # this method; the layout manager holds it weakly.
        self._folding = FoldingLayoutDelegate.alloc().initWithEditor_(self)
        body.layoutManager().setDelegate_(self._folding)
        body.setMinSize_(NSMakeSize(0.0, 0.0))
        body.setMaxSize_(NSMakeSize(1.0e7, 1.0e7))
        body.setVerticallyResizable_(True)
        body.setHorizontallyResizable_(False)
        body.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        body.textContainer().setWidthTracksTextView_(True)
        body.setDrawsBackground_(False)
        body.setRichText_(True)
        body.setImportsGraphics_(True)
        body.setAllowsUndo_(True)
        body.setAutomaticQuoteSubstitutionEnabled_(False)
        body.setAutomaticDashSubstitutionEnabled_(False)
        body.setAutomaticLinkDetectionEnabled_(False)
        body.setInsertionPointColor_(p.accent_strong)
        body.setTextContainerInset_(NSMakeSize(40.0, 12.0))
        body.setDelegate_(self)
        body.registerForDraggedTypes_([NSFilenamesPboardType])
        body.setAccessibilityLabel_("Note blocks")
        scroll.setDocumentView_(body)
        self._scroll = scroll
        self._body = body

        gutter = GutterHoverView.alloc().init()
        gutter.stormpad_editor = self
        add(self.view, gutter)
        pin_edges(gutter, self.view, top=102, leading=0, trailing=None, bottom=18)
        set_width(gutter, _BODY_INSET)
        self._gutter_hover = gutter

        self._plus = self._overlay_button("+", "showBlockMenu:", "Add Block", symbol="plus")
        self._block_edit = self._overlay_button(
            "", "showBlockEditMenu:", "Edit Block", symbol="ellipsis"
        )
        initial = block_gutter_layout(_BODY_INSET, 16.0)
        self._plus.setFrame_(
            NSMakeRect(
                initial.add.x,
                initial.add.y,
                initial.add.width,
                initial.add.height,
            )
        )
        self._block_edit.setFrame_(
            NSMakeRect(
                initial.edit.x,
                initial.edit.y,
                initial.edit.width,
                initial.edit.height,
            )
        )
        self._set_gutter_hidden(True)

        self._formatting = rounded_view(
            p.formatting_background,
            8.0,
            border_color=p.formatting_border,
            border_width=1.0,
        )
        self._formatting.setFrame_(NSMakeRect(160, 110, 210, 32))
        self.view.addSubview_(self._formatting)
        self._build_formatting_toolbar()
        self._formatting.setHidden_(True)

    def _overlay_button(
        self,
        title: str,
        action: str | None,
        accessibility: str,
        *,
        symbol: str | None = None,
    ) -> NSButton:
        p = self._palette
        button = GutterButton.alloc().init()
        button.setTitle_(title)
        button.setBordered_(False)
        button.setWantsLayer_(True)
        button.layer().setCornerRadius_(7.0)
        button.layer().setBackgroundColor_(p.gutter_background.CGColor())
        button.stormpad_idle_color = p.gutter_background
        button.stormpad_hover_color = p.toolbar_button_hover
        button.layer().setBorderWidth_(1.0)
        button.layer().setBorderColor_(p.gutter_border.CGColor())
        button.setContentTintColor_(p.text_secondary)
        if symbol:
            image = symbol_image(symbol, size=12, weight="semibold")
            if image is not None:
                button.setImage_(image)
                button.setImagePosition_(NSImageOnly)
        button.setTarget_(self)
        if action is not None:
            button.setAction_(action)
        button.setAccessibilityLabel_(accessibility)
        button.setToolTip_(accessibility)
        self._gutter_hover.addSubview_(button)
        return button

    def _build_formatting_toolbar(self) -> None:
        controls = (
            ("B", "toggleBold:", "Bold"),
            ("I", "toggleItalic:", "Italic"),
            ("U", "toggleUnderline:", "Underline"),
            ("", "editLink:", "Link"),
            ("A", "showTextColorMenu:", "Text Color"),
            ("▰", "showHighlightMenu:", "Highlight Color"),
        )
        width = 32.0
        for index, (title, action, accessibility) in enumerate(controls):
            button = NSButton.alloc().initWithFrame_(NSMakeRect(index * width + 6, 4, 28, 24))
            button.setTitle_(title)
            button.setBordered_(False)
            button.setFont_(
                NSFont.boldSystemFontOfSize_(12)
                if accessibility == "Bold"
                else NSFont.systemFontOfSize_(12)
            )
            button.setContentTintColor_(self._palette.text_secondary)
            if accessibility == "Link":
                image = symbol_image("link", size=11)
                if image is not None:
                    button.setImage_(image)
                    button.setImagePosition_(NSImageOnly)
            button.setTarget_(self)
            button.setAction_(action)
            button.setAccessibilityLabel_(accessibility)
            button.setToolTip_(accessibility)
            self._formatting.addSubview_(button)

    # -- note conversion ----------------------------------------------------

    @objc.python_method
    def load_note(self, note: Note) -> None:
        self._cancel_pending_return()
        self._cancel_pending_caret_visibility()
        self._loading = True
        try:
            self._clear_full_note_selection_visual()
            self._current = note
            self.clear_block_hover()
            self._title.setStringValue_(title_display_text(note))
            blocks = parse_blocks(note.body)
            transcript = next(
                (block for block in blocks if block.kind == BlockType.TRANSCRIPT), None
            )
            if note.transcript_visible:
                if transcript is None:
                    blocks.append(
                        Block(
                            kind=BlockType.TRANSCRIPT,
                            collapsed=note.transcript_collapsed,
                        )
                    )
                else:
                    transcript.collapsed = note.transcript_collapsed or transcript.collapsed
            self._replace_document(blocks, register_undo=False, focus_index=None)
            self.set_status(SaveStatus.SAVED)
            self.view.setHidden_(False)
        finally:
            self._loading = False

    def clear(self) -> None:
        self._cancel_pending_return()
        self._cancel_pending_caret_visibility()
        self._clear_full_note_selection_visual()
        self._current = None
        self.view.setHidden_(True)
        self._set_gutter_hidden(True)
        self._formatting.setHidden_(True)

    def title_text(self) -> str:
        return str(self._title.stringValue())

    def body_text(self) -> str:
        return serialize_blocks(self._extract_blocks())

    def transcript_state(self) -> tuple[bool, bool]:
        transcript = next(
            (block for block in self._extract_blocks() if block.kind == BlockType.TRANSCRIPT),
            None,
        )
        return (
            transcript is not None,
            bool(transcript and transcript.collapsed),
        )

    def _replace_document(
        self,
        blocks: list[Block],
        *,
        register_undo: bool,
        focus_index: int | None,
    ) -> None:
        storage = self._body.textStorage()
        if register_undo:
            snapshot = storage.copy()
            selection = self.body_selected_range()
            self._body.undoManager().registerUndoWithTarget_selector_object_(
                self, "restoreDocument:", {"text": snapshot, "selection": selection}
            )
        result = NSMutableAttributedString.alloc().init()
        document = blocks or [Block()]
        for index, block in enumerate(document):
            if index:
                previous_attrs = self._block_base_attributes(block)
                result.appendAttributedString_(
                    NSAttributedString.alloc().initWithString_attributes_("\n", previous_attrs)
                )
            result.appendAttributedString_(self._attributed_block(block, index, document))
        was_loading = self._loading
        self._loading = True
        try:
            storage.setAttributedString_(result)
        finally:
            self._loading = was_loading
        self._apply_folding(document)
        if focus_index is not None:
            self._select_block(focus_index)
            self.focus_body()
        self._emit_body_change()

    @objc.python_method
    def _line_ranges(self) -> list[tuple[int, int]]:
        """Character range of every rendered line, including its newline."""
        ranges: list[tuple[int, int]] = []
        location = 0
        for line in str(self._body.string()).split("\n"):
            length = _utf16_length(line) + 1
            ranges.append((location, length))
            location += length
        return ranges

    @objc.python_method
    def _apply_folding(self, blocks: list[Block]) -> None:
        """Hide collapsed content at the layout level only.

        Text storage is never modified here. Hidden lines get a clear temporary
        attribute (which lives in the layout manager, not the storage) and a
        zero-height line fragment, so extraction and autosave continue to see the
        complete note.
        """
        manager = self._body.layoutManager()
        if manager is None:
            return
        total = int(self._body.textStorage().length())
        full = NSMakeRange(0, total)
        manager.setTemporaryAttributes_forCharacterRange_({}, full)
        hidden = hidden_indexes(blocks)
        ranges: list[tuple[int, int]] = []
        if hidden:
            lines = self._line_ranges()
            for index in sorted(hidden):
                if index >= len(lines):
                    continue
                start, length = lines[index]
                length = min(length, max(0, total - start))
                if length <= 0:
                    continue
                ranges.append((start, length))
                manager.setTemporaryAttributes_forCharacterRange_(
                    {NSForegroundColorAttributeName: NSColor.clearColor()},
                    NSMakeRange(start, length),
                )
        self._folding.setHiddenRanges_(ranges)
        self._hidden_ranges = ranges
        manager.invalidateLayoutForCharacterRange_actualCharacterRange_(full, None)

    @objc.python_method
    def _hidden_character_ranges(self) -> list[tuple[int, int]]:
        return list(getattr(self, "_hidden_ranges", []))

    @objc.python_method
    def _location_is_hidden(self, location: int) -> bool:
        return any(
            start <= int(location) < start + length
            for start, length in self._hidden_character_ranges()
        )

    def restoreDocument_(self, payload):  # noqa: N802
        current = self._body.textStorage().copy()
        current_selection = self.body_selected_range()
        self._body.undoManager().registerUndoWithTarget_selector_object_(
            self,
            "restoreDocument:",
            {"text": current, "selection": current_selection},
        )
        self._loading = True
        try:
            self._body.textStorage().setAttributedString_(payload["text"])
            self.restore_selection(tuple(payload["selection"]))
            self._sync_selected_image_from_selection()
        finally:
            self._loading = False
        # Collapse state travels inside the restored attributes, so recompute the
        # hidden ranges rather than trusting the ones from before the undo.
        self._apply_folding(self._extract_blocks())
        self._move_caret_out_of_hidden()
        self._emit_body_change()

    def _display_number(
        self, block: Block, block_index: int, document: list[Block] | None
    ) -> int:
        """Counter shown before a numbered block, or 1 without a document."""
        if document is None:
            return 1
        try:
            if document[block_index] is not block:
                return 1
            return numbered_display_number(document, block_index)
        except (IndexError, ValueError):
            return 1

    def _attributed_block(
        self,
        block: Block,
        block_index: int = 0,
        document: list[Block] | None = None,
    ) -> NSMutableAttributedString:
        attrs = self._block_base_attributes(block)
        result = NSMutableAttributedString.alloc().init()

        prefix = ""
        decoration = None
        if block.kind == BlockType.TODO:
            prefix, decoration = ("☑" if block.checked else "☐"), "todo"
        elif block.kind == BlockType.BULLET:
            prefix, decoration = "• ", "prefix"
        elif block.kind == BlockType.NUMBERED:
            # Markdown keeps every item as "1."; only the display counts up.
            prefix, decoration = f"{self._display_number(block, block_index, document)}. ", "prefix"
        elif is_toggle(block):
            # Disclosure chevron: right when collapsed, down when expanded. It is
            # decoration, so it never reaches the block's text or the Markdown.
            prefix, decoration = ("▸ " if block.collapsed else "▾ "), "toggle"
        elif block.kind == BlockType.QUOTE:
            prefix, decoration = "❝ ", "prefix"
        elif block.kind == BlockType.FILE:
            prefix, decoration = "📎 ", "prefix"
        if prefix:
            prefix_attrs = dict(attrs)
            prefix_attrs[_ATTR_DECORATION] = decoration
            if decoration == "todo":
                # A 19 pt square stays native and restrained. Kerning creates
                # the visual text gap without adding content padding.
                prefix_attrs[NSFontAttributeName] = NSFont.systemFontOfSize_(19.0)
                prefix_attrs[NSBaselineOffsetAttributeName] = -1.0
                # A typographic gap, not content: Markdown and extracted text
                # contain no padding spaces, while checked/unchecked align.
                prefix_attrs[NSKernAttributeName] = _TODO_TEXT_GAP
            result.appendAttributedString_(
                NSAttributedString.alloc().initWithString_attributes_(prefix, prefix_attrs)
            )

        if block.kind == BlockType.DIVIDER:
            divider_attrs = dict(attrs)
            divider_attrs[_ATTR_DECORATION] = "divider"
            divider_attrs[_ATTR_READ_ONLY] = True
            divider_attrs[NSForegroundColorAttributeName] = self._palette.divider_line
            # A width-tracking attachment rather than a fixed run of glyphs, so
            # the rule follows the editor's content width. Markdown stays "---".
            attachment = NSTextAttachment.alloc().init()
            attachment.setAttachmentCell_(
                DividerAttachmentCell.alloc().initWithColor_(self._palette.divider_line)
            )
            divider_string = NSMutableAttributedString.alloc().initWithAttributedString_(
                NSAttributedString.attributedStringWithAttachment_(attachment)
            )
            divider_string.addAttributes_range_(
                divider_attrs, NSMakeRange(0, divider_string.length())
            )
            result.appendAttributedString_(divider_string)
            return result

        if block.kind == BlockType.RAW:
            raw_attrs = dict(attrs)
            raw_attrs[_ATTR_DECORATION] = "raw"
            raw_attrs[_ATTR_READ_ONLY] = True
            raw_attrs[NSFontAttributeName] = NSFont.monospacedSystemFontOfSize_weight_(12.5, 0.0)
            raw_attrs[NSForegroundColorAttributeName] = self._palette.text_muted
            display = (block.raw or "").replace("\n", "  ↵  ")
            result.appendAttributedString_(
                NSAttributedString.alloc().initWithString_attributes_(
                    display or "Unsupported Markdown", raw_attrs
                )
            )
            return result

        if block.kind == BlockType.TRANSCRIPT:
            transcript_attrs = dict(attrs)
            transcript_attrs[_ATTR_DECORATION] = "transcript-header"
            transcript_attrs[_ATTR_READ_ONLY] = True
            transcript_attrs[NSFontAttributeName] = NSFont.boldSystemFontOfSize_(13.0)
            transcript_attrs[NSForegroundColorAttributeName] = self._palette.text_primary
            transcript_attrs[NSBackgroundColorAttributeName] = self._palette.transcript_background
            caret = "▸" if block.collapsed else "▾"
            result.appendAttributedString_(
                NSAttributedString.alloc().initWithString_attributes_(
                    f"  {caret}  Transcript  ", transcript_attrs
                )
            )
            if not block.collapsed:
                chunks = self._current.transcript if self._current is not None else []
                if chunks:
                    for index, chunk in enumerate(chunks):
                        chunk_attrs = dict(attrs)
                        chunk_attrs[_ATTR_DECORATION] = "transcript-chunk"
                        chunk_attrs[_ATTR_READ_ONLY] = True
                        chunk_attrs[_ATTR_TRANSCRIPT_CHUNK] = index
                        chunk_attrs[NSFontAttributeName] = NSFont.systemFontOfSize_(12.5)
                        chunk_attrs[NSForegroundColorAttributeName] = self._palette.text_secondary
                        chunk_attrs[NSBackgroundColorAttributeName] = (
                            self._palette.transcript_background
                        )
                        result.appendAttributedString_(
                            NSAttributedString.alloc().initWithString_attributes_(
                                f"{_LINE_SEPARATOR}     [{chunk.timestamp}]  {chunk.text}  ",
                                chunk_attrs,
                            )
                        )
                else:
                    empty_attrs = dict(attrs)
                    empty_attrs[_ATTR_DECORATION] = "transcript-empty"
                    empty_attrs[_ATTR_READ_ONLY] = True
                    empty_attrs[NSFontAttributeName] = NSFont.systemFontOfSize_(12.5)
                    empty_attrs[NSForegroundColorAttributeName] = self._palette.text_muted
                    empty_attrs[NSBackgroundColorAttributeName] = (
                        self._palette.transcript_background
                    )
                    result.appendAttributedString_(
                        NSAttributedString.alloc().initWithString_attributes_(
                            f"{_LINE_SEPARATOR}     No transcript yet  ",
                            empty_attrs,
                        )
                    )
                    append_attrs = dict(attrs)
                    append_attrs[_ATTR_DECORATION] = "transcript-append"
                    append_attrs[_ATTR_READ_ONLY] = True
                    append_attrs[NSFontAttributeName] = NSFont.boldSystemFontOfSize_(12.5)
                    append_attrs[NSForegroundColorAttributeName] = self._palette.accent
                    append_attrs[NSBackgroundColorAttributeName] = (
                        self._palette.transcript_background
                    )
                    result.appendAttributedString_(
                        NSAttributedString.alloc().initWithString_attributes_(
                            f"{_LINE_SEPARATOR}     Append Test Transcript  ",
                            append_attrs,
                        )
                    )
            return result

        if block.kind == BlockType.IMAGE and block.target:
            attachment = self._image_attachment(
                block.target,
                block.display_width,
                block_index,
            )
            if attachment is not None:
                image_string = NSAttributedString.attributedStringWithAttachment_(
                    attachment
                ).mutableCopy()
                image_string.addAttributes_range_(
                    {**attrs, _ATTR_DECORATION: "image", _ATTR_READ_ONLY: True},
                    NSMakeRange(0, image_string.length()),
                )
                result.appendAttributedString_(image_string)
                # The alt text is metadata, not a caption: rendering it after the
                # attachment put stray words beside the image on the same line.
                return result

        for run in block.runs:
            run_attrs = self._inline_attributes(attrs, run)
            result.appendAttributedString_(
                NSAttributedString.alloc().initWithString_attributes_(run.text, run_attrs)
            )

        if block.kind == BlockType.FILE and block.target:
            detail = self._file_detail(block.target)
            if detail:
                detail_attrs = dict(attrs)
                detail_attrs[_ATTR_DECORATION] = "file-detail"
                detail_attrs[_ATTR_READ_ONLY] = True
                detail_attrs[NSFontAttributeName] = NSFont.systemFontOfSize_(11.5)
                detail_attrs[NSForegroundColorAttributeName] = self._palette.text_muted
                result.appendAttributedString_(
                    NSAttributedString.alloc().initWithString_attributes_(
                        f"  ·  {detail}", detail_attrs
                    )
                )

        if result.length() == 0:
            result.appendAttributedString_(
                NSAttributedString.alloc().initWithString_attributes_(_ZERO_WIDTH, attrs)
            )
        return result

    def _image_attachment(
        self,
        relative: str,
        display_width: float | None,
        block_index: int,
    ):
        if self._current is None:
            return None
        path = (self._current.path.parent / relative).resolve()
        image = NSImage.alloc().initWithContentsOfFile_(str(path))
        if image is None:
            return None
        size = image.size()
        # Natural width when it fits the column, otherwise scaled down. Never
        # upscaled: a small image keeps its own size.
        natural = float(size.width)
        column = self._content_column_width()
        width = display_width or min(natural, column)
        attachment = NSTextAttachment.alloc().init()
        cell = ImageAttachmentCell.alloc().initWithImage_width_editor_index_(
            image,
            width,
            self,
            block_index,
        )
        blocks = self._extract_blocks() if self._body.textStorage().length() else []
        alt = ""
        if 0 <= block_index < len(blocks):
            alt = blocks[block_index].alt or ""
        selected = "selected" if block_index in self._selected_image_indexes else "not selected"
        label = f"Image{': ' + alt if alt else ''}, {int(width)} points wide, {selected}"
        try:
            cell.setAccessibilityLabel_(label)
        except (AttributeError, TypeError, ValueError):
            pass
        attachment.setAttachmentCell_(cell)
        return attachment

    def _file_detail(self, relative: str) -> str:
        if self._current is None:
            return ""
        path = (self._current.path.parent / relative).resolve()
        kind = path.suffix.lstrip(".").upper() or "FILE"
        try:
            size = path.stat().st_size
        except OSError:
            return kind
        units = ("B", "KB", "MB", "GB")
        value = float(size)
        unit = units[0]
        for candidate in units:
            unit = candidate
            if value < 1024.0 or candidate == units[-1]:
                break
            value /= 1024.0
        size_text = f"{value:.0f} {unit}" if value >= 10 or unit == "B" else f"{value:.1f} {unit}"
        return f"{kind} · {size_text}"

    def _block_base_attributes(self, block: Block) -> dict:
        paragraph = NSMutableParagraphStyle.alloc().init()
        # An image line must hug its bitmap. A line height multiple inflates the
        # fragment to 135% of the attachment height, and because the attachment
        # is baseline anchored every extra point lands above the image, which is
        # what produced the tall empty selection band.
        if block.kind != BlockType.IMAGE:
            paragraph.setLineHeightMultiple_(1.35)
        paragraph.setParagraphSpacingBefore_(3.0)
        paragraph.setParagraphSpacing_(12.0)
        paragraph.setHeadIndent_(float(block.indent) * 20.0)
        paragraph.setFirstLineHeadIndent_(float(block.indent) * 20.0)
        if block.kind == BlockType.QUOTE:
            paragraph.setHeadIndent_(18.0)
            paragraph.setFirstLineHeadIndent_(18.0)
        if block.kind == BlockType.IMAGE:
            # Alignment within the content column. Presentation only: the value
            # is stored semantically, never as coordinates.
            paragraph.setAlignment_(
                _IMAGE_ALIGNMENT_MAP.get(
                    normalize_alignment(block.alignment), NSTextAlignmentLeft
                )
            )
        size = {
            BlockType.HEADING_1: 26.0,
            BlockType.HEADING_2: 22.0,
            BlockType.HEADING_3: 19.0,
            # A toggle heading is the same heading, so it gets the same size.
            BlockType.TOGGLE_HEADING_1: 26.0,
            BlockType.TOGGLE_HEADING_2: 22.0,
            BlockType.TOGGLE_HEADING_3: 19.0,
        }.get(block.kind, 16.5)
        font = serif_font(size)
        if block.kind in (
            BlockType.HEADING_1,
            BlockType.HEADING_2,
            BlockType.HEADING_3,
            BlockType.TOGGLE_HEADING_1,
            BlockType.TOGGLE_HEADING_2,
            BlockType.TOGGLE_HEADING_3,
        ):
            font = NSFontManager.sharedFontManager().convertFont_toHaveTrait_(font, NSBoldFontMask)
        return {
            NSFontAttributeName: font,
            NSForegroundColorAttributeName: self._palette.editor_text,
            NSParagraphStyleAttributeName: paragraph,
            _ATTR_BLOCK: block.kind.value,
            _ATTR_CHECKED: bool(block.checked),
            _ATTR_INDENT: int(block.indent),
            _ATTR_TARGET: block.target or "",
            _ATTR_ALT: block.alt or "",
            _ATTR_COLLAPSED: bool(block.collapsed),
            _ATTR_RAW: block.raw or "",
            _ATTR_IMAGE_WIDTH: block.display_width or 0.0,
            _ATTR_IMAGE_ALIGNMENT: normalize_alignment(block.alignment),
        }

    def _inline_attributes(self, base: dict, run: InlineRun) -> dict:
        attrs = dict(base)
        for mark in run.marks:
            if mark.kind == MarkType.BOLD:
                attrs[_ATTR_BOLD] = True
            elif mark.kind == MarkType.ITALIC:
                attrs[_ATTR_ITALIC] = True
            elif mark.kind == MarkType.UNDERLINE:
                attrs[_ATTR_UNDERLINE] = True
                attrs[NSUnderlineStyleAttributeName] = NSUnderlineStyleSingle
            elif mark.kind == MarkType.TEXT_COLOR and mark.value:
                attrs[_ATTR_TEXT_COLOR] = mark.value
                attrs[NSForegroundColorAttributeName] = self._semantic_color(mark.value)
            elif mark.kind == MarkType.HIGHLIGHT and mark.value:
                attrs[_ATTR_HIGHLIGHT] = mark.value
                attrs[NSBackgroundColorAttributeName] = self._semantic_color(mark.value, alpha=0.28)
            elif mark.kind == MarkType.LINK and mark.value:
                attrs[_ATTR_LINK] = mark.value
                attrs[NSLinkAttributeName] = mark.value
                attrs[NSForegroundColorAttributeName] = self._palette.accent
        font = attrs[NSFontAttributeName]
        traits = 0
        if attrs.get(_ATTR_BOLD):
            traits |= NSBoldFontMask
        if attrs.get(_ATTR_ITALIC):
            traits |= NSItalicFontMask
        if traits:
            attrs[NSFontAttributeName] = NSFontManager.sharedFontManager().convertFont_toHaveTrait_(
                font, traits
            )
        return attrs

    def _semantic_color(self, token: str, alpha: float = 1.0) -> NSColor:
        if token == "default":
            color = self._palette.editor_text
            return color.colorWithAlphaComponent_(alpha)
        return self._palette.color(f"inline_{token}", alpha)

    def _extract_blocks(self) -> list[Block]:
        attributed = self._body.textStorage()
        value = str(attributed.string())
        lines = value.split("\n")
        blocks: list[Block] = []
        location = 0
        for line in lines:
            length = _utf16_length(line)
            probe = min(location, max(0, attributed.length() - 1))
            attrs = {}
            if attributed.length() > 0:
                try:
                    attrs = attributed.attributesAtIndex_effectiveRange_(probe, None)[0]
                except (IndexError, TypeError, ValueError):
                    attrs = {}
            try:
                kind = BlockType(str(_attr_value(attrs, _ATTR_BLOCK, BlockType.TEXT.value)))
            except ValueError:
                kind = BlockType.TEXT

            if kind == BlockType.TRANSCRIPT:
                if not any(block.kind == BlockType.TRANSCRIPT for block in blocks):
                    blocks.append(
                        Block(
                            kind=kind,
                            collapsed=bool(attrs.get(_ATTR_COLLAPSED, False)),
                        )
                    )
                location += length + 1
                continue
            if kind == BlockType.RAW:
                blocks.append(Block(kind=kind, raw=str(attrs.get(_ATTR_RAW) or "")))
                location += length + 1
                continue
            if kind == BlockType.DIVIDER:
                blocks.append(Block(kind=kind))
                location += length + 1
                continue

            runs: list[InlineRun] = []
            cursor = location
            end = location + length
            while cursor < end and cursor < attributed.length():
                try:
                    run_attrs, effective = attributed.attributesAtIndex_effectiveRange_(
                        cursor, None
                    )
                    run_end = min(end, int(effective.location + effective.length))
                except (IndexError, TypeError, ValueError):
                    run_attrs = attrs
                    run_end = min(end, cursor + 1)
                text = str(
                    attributed.attributedSubstringFromRange_(
                        NSMakeRange(cursor, max(1, run_end - cursor))
                    ).string()
                )
                if not run_attrs.get(_ATTR_DECORATION):
                    text = text.replace(_ZERO_WIDTH, "")
                    if text:
                        marks: list[InlineMark] = []
                        if run_attrs.get(_ATTR_BOLD):
                            marks.append(InlineMark(MarkType.BOLD))
                        if run_attrs.get(_ATTR_ITALIC):
                            marks.append(InlineMark(MarkType.ITALIC))
                        if run_attrs.get(_ATTR_UNDERLINE):
                            marks.append(InlineMark(MarkType.UNDERLINE))
                        color = run_attrs.get(_ATTR_TEXT_COLOR)
                        if color in COLOR_TOKENS:
                            marks.append(InlineMark(MarkType.TEXT_COLOR, str(color)))
                        highlight = run_attrs.get(_ATTR_HIGHLIGHT)
                        if highlight in COLOR_TOKENS:
                            marks.append(InlineMark(MarkType.HIGHLIGHT, str(highlight)))
                        link = run_attrs.get(_ATTR_LINK)
                        if link:
                            marks.append(InlineMark(MarkType.LINK, str(link)))
                        runs.append(InlineRun(text, tuple(marks)))
                cursor = max(cursor + 1, run_end)

            block = Block(
                kind=kind,
                runs=runs,
                checked=bool(attrs.get(_ATTR_CHECKED, False)),
                indent=int(attrs.get(_ATTR_INDENT, 0) or 0),
                target=str(attrs.get(_ATTR_TARGET) or "") or None,
                alt=str(attrs.get(_ATTR_ALT) or "") or None,
                collapsed=bool(attrs.get(_ATTR_COLLAPSED, False)),
                display_width=(
                    float(attrs.get(_ATTR_IMAGE_WIDTH))
                    if float(attrs.get(_ATTR_IMAGE_WIDTH, 0.0) or 0.0) > 0.0
                    else None
                ),
                alignment=normalize_alignment(attrs.get(_ATTR_IMAGE_ALIGNMENT)),
            )
            if kind == BlockType.RAW:
                block.raw = block.text
            blocks.append(block)
            location += length + 1
        return blocks or [Block()]

    # -- selection / focus --------------------------------------------------

    def focus_body(self) -> None:
        self.view.window().makeFirstResponder_(self._body)

    def focus_title(self) -> None:
        self.clear_block_hover()
        self._formatting.setHidden_(True)
        self.view.window().makeFirstResponder_(self._title)

    @objc.python_method
    def selected_body_text(self) -> str:
        selected = self._body.selectedRange()
        if selected.length == 0:
            return ""
        return str(self._body.string().substringWithRange_(selected))

    @objc.python_method
    def body_is_first_responder(self) -> bool:
        window = self.view.window()
        return window is not None and window.firstResponder() == self._body

    @objc.python_method
    def body_selected_range(self) -> tuple[int, int]:
        selected = self._body.selectedRange()
        return (int(selected.location), int(selected.length))

    @objc.python_method
    def current_block_type(self) -> str:
        blocks = self._extract_blocks()
        index = min(self._current_block_index(), len(blocks) - 1)
        return blocks[index].kind.value

    @objc.python_method
    def formatting_state(self, action: str) -> bool:
        selected = self._selected_range()
        if selected is None or self._body.textStorage().length() == 0:
            return False
        attribute = {
            "toggleBold:": _ATTR_BOLD,
            "toggleItalic:": _ATTR_ITALIC,
            "toggleUnderline:": _ATTR_UNDERLINE,
            "editLink:": _ATTR_LINK,
        }.get(action)
        if attribute is None:
            return False
        probe = min(int(selected.location), self._body.textStorage().length() - 1)
        attrs = self._body.textStorage().attributesAtIndex_effectiveRange_(probe, None)[0]
        return bool(attrs.get(attribute))

    @objc.python_method
    def restore_selection(self, selection: tuple[int, int]) -> None:
        length = self._body.string().length()
        location = min(max(selection[0], 0), length)
        span = min(max(selection[1], 0), length - location)
        self._body.setSelectedRange_(NSMakeRange(location, span))

    @objc.python_method
    def select_all_note_content(self) -> None:
        """Select the title and complete body as one editor-wide operation."""
        self._setting_full_note_selection = True
        self._full_note_selected = True
        try:
            self._body.setSelectedRange_(
                NSMakeRange(0, int(self._body.string().length()))
            )
            self._title.setDrawsBackground_(True)
            self._title.setBackgroundColor_(self._palette.selected_background)
            self.focus_body()
        finally:
            self._setting_full_note_selection = False

    @objc.python_method
    def full_note_selection_state(
        self,
    ) -> tuple[bool, tuple[int, int], tuple[int, int]]:
        return (
            self._full_note_selected,
            (0, _utf16_length(self.title_text())),
            self.body_selected_range(),
        )

    def _clear_full_note_selection_visual(self) -> None:
        self._full_note_selected = False
        title = getattr(self, "_title", None)
        if title is not None:
            title.setDrawsBackground_(False)

    def _full_note_snapshot(self) -> dict:
        return {
            "title": self.title_text(),
            "text": self._body.textStorage().copy(),
            "transcript": (
                list(self._current.transcript) if self._current is not None else []
            ),
            "selection": self.body_selected_range(),
        }

    def _register_full_note_undo(self, payload: dict) -> None:
        manager = self._body.undoManager()
        manager.registerUndoWithTarget_selector_object_(
            self, "restoreFullNote:", payload
        )
        manager.setActionName_("Clear Note")

    @objc.python_method
    def clear_note_content(self) -> None:
        """Clear title/body/Transcript without deleting the note or attachments."""
        self._register_full_note_undo(self._full_note_snapshot())
        was_loading = self._loading
        self._loading = True
        try:
            self._title.setStringValue_("")
            if self._current is not None:
                self._current.transcript = []
            self._body.textStorage().setAttributedString_(
                self._attributed_block(Block())
            )
            self._body.setSelectedRange_(NSMakeRange(0, 0))
            self._clear_full_note_selection_visual()
        finally:
            self._loading = was_loading
        self._on_title("")
        self._emit_body_change()
        self.focus_body()

    def restoreFullNote_(self, payload):  # noqa: N802
        self._register_full_note_undo(self._full_note_snapshot())
        was_loading = self._loading
        self._loading = True
        try:
            self._title.setStringValue_(payload["title"])
            self._body.textStorage().setAttributedString_(payload["text"])
            if self._current is not None:
                self._current.transcript = list(payload["transcript"])
            self.restore_selection(tuple(payload["selection"]))
            self._clear_full_note_selection_visual()
        finally:
            self._loading = was_loading
        self._on_title(self.title_text())
        self._emit_body_change()

    def _current_block_index(self) -> int:
        return block_index_for_location(
            str(self._body.string()), int(self._body.selectedRange().location)
        )

    def _select_block(self, index: int) -> None:
        lines = str(self._body.string()).split("\n")
        index = min(max(index, 0), max(0, len(lines) - 1))
        location = sum(_utf16_length(line) + 1 for line in lines[:index])
        line = lines[index] if lines else ""
        visible = line.replace(_ZERO_WIDTH, "")
        self._body.setSelectedRange_(
            NSMakeRange(location + _utf16_length(line), 0 if visible else 0)
        )

    def _select_block_start(self, index: int) -> None:
        lines = str(self._body.string()).split("\n")
        index = min(max(index, 0), max(0, len(lines) - 1))
        location = sum(_utf16_length(line) + 1 for line in lines[:index])
        self._body.setSelectedRange_(
            NSMakeRange(self._editable_block_start(index, location), 0)
        )

    def _editable_block_start(self, index: int, location: int | None = None) -> int:
        """First caret position after a non-content block prefix."""
        lines = str(self._body.string()).split("\n")
        index = min(max(int(index), 0), max(0, len(lines) - 1))
        start = (
            int(location)
            if location is not None
            else sum(_utf16_length(line) + 1 for line in lines[:index])
        )
        storage = self._body.textStorage()
        if start >= int(storage.length()):
            return start
        try:
            attrs, effective = storage.attributesAtIndex_effectiveRange_(start, None)
        except (IndexError, TypeError, ValueError):
            return start
        line_end = start + _utf16_length(lines[index])
        return editable_prefix_end(
            attrs.get(_ATTR_DECORATION),
            start,
            int(effective.location + effective.length),
            line_end,
        )

    @property
    def _selected_image_index(self) -> int | None:
        """Anchor image, and the Match Width reference. ``None`` when unselected."""
        return self._image_anchor

    @_selected_image_index.setter
    def _selected_image_index(self, value: int | None) -> None:
        if value is None:
            self._selected_image_indexes = set()
            self._image_anchor = None
        else:
            self._selected_image_indexes = {int(value)}
            self._image_anchor = int(value)

    @objc.python_method
    def actual_image_rect(self, character_index: int):
        """The rendered bitmap's rectangle in text view coordinates.

        The single source of truth for the selection border, the handles, hit
        testing, and any anchoring. Derived from the line fragment origin plus
        the glyph location, then lifted by the cell height because an attachment
        sits on the baseline. Never the line fragment itself, which is taller
        than the bitmap.
        """
        storage = self._body.textStorage()
        if storage.length() == 0 or not (0 <= character_index < storage.length()):
            return None
        attrs = storage.attributesAtIndex_effectiveRange_(character_index, None)[0]
        attachment = attrs.get(NSAttachmentAttributeName)
        cell = attachment.attachmentCell() if attachment is not None else None
        if cell is None:
            return None
        manager = self._body.layoutManager()
        container = self._body.textContainer()
        if manager is None or container is None:
            return None
        try:
            glyphs = manager.glyphRangeForCharacterRange_actualCharacterRange_(
                NSMakeRange(character_index, 1), None
            )
            if isinstance(glyphs, tuple):
                glyphs = glyphs[0]
            fragment = manager.lineFragmentRectForGlyphAtIndex_effectiveRange_(
                glyphs.location, None
            )
            if isinstance(fragment, tuple):
                fragment = fragment[0]
            location = manager.locationForGlyphAtIndex_(glyphs.location)
            size = cell.cellSize()
        except (AttributeError, IndexError, TypeError, ValueError):
            return None
        inset = self._body.textContainerInset()
        width = float(size.width if hasattr(size, "width") else size[0])
        height = float(size.height if hasattr(size, "height") else size[1])
        return NSMakeRect(
            float(fragment.origin.x) + float(location.x) + float(inset.width),
            float(fragment.origin.y) + float(location.y) - height + float(inset.height),
            width,
            height,
        )

    @objc.python_method
    def _image_character_index(self, block_index: int) -> int | None:
        """Character index of the attachment glyph for a given image block."""
        lines = str(self._body.string()).split("\n")
        if not (0 <= block_index < len(lines)):
            return None
        start = sum(_utf16_length(line) + 1 for line in lines[:block_index])
        storage = self._body.textStorage()
        for offset in range(len(lines[block_index])):
            probe = start + offset
            if probe >= storage.length():
                break
            attrs = storage.attributesAtIndex_effectiveRange_(probe, None)[0]
            if attrs.get(NSAttachmentAttributeName) is not None:
                return probe
        return None

    @objc.python_method
    def _selectable_image_indexes(self) -> list[int]:
        """Image blocks the user can actually reach, in document order.

        Images hidden inside a collapsed toggle are excluded, so a click or a
        range selection can never pick up something that is not on screen.
        """
        blocks = self._extract_blocks()
        hidden = hidden_indexes(blocks)
        return [
            index
            for index, block in enumerate(blocks)
            if block.kind == BlockType.IMAGE and index not in hidden
        ]

    @objc.python_method
    def _set_image_selection(self, indexes, anchor: int | None = None) -> None:
        allowed = set(self._selectable_image_indexes())
        self._selected_image_indexes = {int(i) for i in indexes} & allowed
        if anchor is not None and int(anchor) in self._selected_image_indexes:
            self._image_anchor = int(anchor)
        elif self._image_anchor not in self._selected_image_indexes:
            self._image_anchor = (
                min(self._selected_image_indexes) if self._selected_image_indexes else None
            )
        self._refresh_image_selection_chrome()

    @objc.python_method
    def select_image_block(self, index, command=False, shift=False) -> None:
        """Apply click, Command-click, or Shift-click selection rules."""
        index = int(index)
        if index not in self._selectable_image_indexes():
            return
        if command:
            updated = set(self._selected_image_indexes)
            if index in updated:
                updated.discard(index)
            else:
                updated.add(index)
            # The anchor stays on the first selected image so Match Width has a
            # stable reference; a Command-click only adds or removes.
            keep = self._image_anchor if self._image_anchor in updated else None
            self._set_image_selection(updated, anchor=keep if keep is not None else index)
            return
        if shift and self._image_anchor is not None:
            low, high = sorted((self._image_anchor, index))
            span = [i for i in self._selectable_image_indexes() if low <= i <= high]
            self._set_image_selection(span, anchor=self._image_anchor)
            return
        self._set_image_selection({index}, anchor=index)

    @objc.python_method
    def clear_image_selection(self) -> None:
        if not self._selected_image_indexes and self._image_anchor is None:
            return
        self._selected_image_indexes = set()
        self._image_anchor = None
        self._refresh_image_selection_chrome()

    @objc.python_method
    def _refresh_image_selection_chrome(self) -> None:
        self._body.setNeedsDisplay_(True)

    @objc.python_method
    def selected_image_indexes(self) -> list[int]:
        return sorted(self._selected_image_indexes)

    # -- image commands ---------------------------------------------------------

    @objc.python_method
    def _content_column_width(self) -> float:
        container = self._body.textContainer()
        try:
            usable = float(container.size().width) - 2.0 * float(
                container.lineFragmentPadding()
            )
        except (AttributeError, TypeError, ValueError):
            usable = _IMAGE_DEFAULT_MAX_WIDTH
        return max(_IMAGE_MIN_WIDTH, usable)

    @objc.python_method
    def _apply_to_selected_images(self, mutate, status: str) -> bool:
        """Run one mutation over every selected image as a single undo step."""
        selection = self.selected_image_indexes()
        if not selection:
            return False
        blocks = self._extract_blocks()
        changed = False
        for index in selection:
            if 0 <= index < len(blocks) and blocks[index].kind == BlockType.IMAGE:
                if mutate(blocks, index):
                    changed = True
        if not changed:
            return False
        self._replace_document(blocks, register_undo=True, focus_index=None)
        self._set_image_selection(selection, anchor=self._image_anchor)
        self.flash_status(status)
        return True

    @objc.python_method
    def align_selected_images(self, alignment: str) -> bool:
        alignment = normalize_alignment(alignment)

        def mutate(blocks, index):
            if blocks[index].alignment == alignment:
                return False
            blocks[index].alignment = alignment
            return True

        return self._apply_to_selected_images(mutate, f"Aligned {alignment}")

    @objc.python_method
    def fit_selected_images_to_column(self) -> bool:
        width = self._content_column_width()

        def mutate(blocks, index):
            blocks[index].display_width = width
            return True

        return self._apply_to_selected_images(mutate, "Fitted to column")

    @objc.python_method
    def reset_selected_images_to_natural_size(self) -> bool:
        def mutate(blocks, index):
            blocks[index].display_width = None
            return True

        return self._apply_to_selected_images(mutate, "Reset to natural size")

    @objc.python_method
    def match_selected_image_widths(self) -> bool:
        """Apply the anchor image's width to every other selected image.

        The anchor is the first image of the selection unless a later
        Command-click made a different one the anchor.
        """
        selection = self.selected_image_indexes()
        if len(selection) < 2:
            return False
        blocks = self._extract_blocks()
        anchor = self._image_anchor if self._image_anchor in selection else selection[0]
        reference = blocks[anchor].display_width or self._natural_width_for(blocks[anchor])
        reference = min(self._content_column_width(), max(_IMAGE_MIN_WIDTH, float(reference)))

        def mutate(blocks, index):
            if blocks[index].display_width == reference:
                return False
            blocks[index].display_width = reference
            return True

        return self._apply_to_selected_images(mutate, "Matched widths")

    @objc.python_method
    def _natural_width_for(self, block: Block) -> float:
        """Point width of the source image, clamped to the content column."""
        target = block.target or ""
        if target and self._current is not None:
            notes_dir = self.notes_dir or self._current.path.parent
            resolved = attachments.resolve_managed_path(
                self._current.path, target, notes_dir, self._current.id
            )
            if resolved is not None:
                image = NSImage.alloc().initWithContentsOfFile_(str(resolved))
                if image is not None and float(image.size().width) > 0.0:
                    return min(self._content_column_width(), float(image.size().width))
        return self._content_column_width()

    @objc.python_method
    def delete_selected_images(self) -> bool:
        selection = self.selected_image_indexes()
        if not selection:
            return False
        blocks = self._extract_blocks()
        remaining = [
            block for index, block in enumerate(blocks) if index not in set(selection)
        ]
        if not remaining:
            remaining = [Block()]
        self.clear_image_selection()
        self._replace_document(remaining, register_undo=True, focus_index=None)
        self.flash_status(
            f"Deleted {len(selection)} image{'s' if len(selection) != 1 else ''}"
        )
        return True

    def _sync_selected_image_from_selection(self) -> None:
        selected = self._body.selectedRange()
        self._selected_image_index = None
        if int(selected.length) != 1 or self._body.textStorage().length() == 0:
            return
        probe = min(int(selected.location), self._body.textStorage().length() - 1)
        try:
            attrs = self._body.textStorage().attributesAtIndex_effectiveRange_(
                probe, None
            )[0]
            if attrs.get(_ATTR_BLOCK) == BlockType.IMAGE.value:
                self._selected_image_index = block_index_for_location(
                    str(self._body.string()), probe
                )
        except (IndexError, TypeError, ValueError):
            pass
        self._body.setNeedsDisplay_(True)

    def _set_gutter_hidden(self, hidden: bool) -> None:
        should_hide = hidden or not self._block_controls_enabled
        controls = (self._plus, self._block_edit)
        duration = (
            current_policy().duration(Motion.FAST)
            if can_animate(self.view)
            else 0.0
        )
        if duration <= 0.0:
            self._gutter_token.cancel()
            for control in controls:
                control.setHidden_(should_hide)
                control.setAlphaValue_(1.0)
            return
        if not should_hide:
            # Appear immediately and fade up: the control must be clickable the
            # instant it is visible, with no reveal delay.
            for control in controls:
                if control.isHidden():
                    control.setAlphaValue_(0.0)
                control.setHidden_(False)
        token = self._gutter_token.begin()

        def body(animated: bool) -> None:
            for control in controls:
                anim(control, animated).setAlphaValue_(0.0 if should_hide else 1.0)

        def done() -> None:
            # Hidden only at the end, so a faded-out control never keeps
            # swallowing clicks; a newer hover cancels this cleanly.
            if self._gutter_token.is_current(token) and should_hide:
                for control in controls:
                    control.setHidden_(True)
                    control.setAlphaValue_(1.0)

        run_animation(duration, body, completion=done)

    @objc.python_method
    def set_block_controls_enabled(self, enabled: bool) -> None:
        self._block_controls_enabled = bool(enabled)
        if not self._block_controls_enabled:
            self.clear_block_hover()

    @objc.python_method
    def clear_block_hover(self) -> None:
        self._hovered_block_index = None
        self._set_gutter_hidden(True)

    @objc.python_method
    def hover_canvas_point(self, point) -> None:
        """Show controls only for the block row currently under the pointer."""
        if (
            not self._block_controls_enabled
            or self._current is None
            or self._body.textStorage().length() == 0
        ):
            self.clear_block_hover()
            return
        scroll = self._scroll.frame()
        x = float(point.x)
        y = float(point.y)
        if not gutter_hover_hit(
            x=x,
            y=y,
            gutter_width=_BODY_INSET,
            block_area_top=float(scroll.origin.y),
            block_area_bottom=float(scroll.origin.y + scroll.size.height),
            interactive=self._current is not None,
        ):
            self.clear_block_hover()
            return
        body_point = self._body.convertPoint_fromView_(point, self.view)
        used = self._body.layoutManager().usedRectForTextContainer_(self._body.textContainer())
        inset = self._body.textContainerInset()
        if float(body_point.y) > float(used.origin.y + used.size.height + inset.height):
            self.clear_block_hover()
            return
        location = int(self._body.characterIndexForInsertionAtPoint_(body_point))
        index = block_index_for_location(str(self._body.string()), location)
        self.show_block_hover(index)

    @objc.python_method
    def show_block_hover(self, index: int) -> None:
        """Set the hovered block (also used by deterministic screenshot checks)."""
        self._hovered_block_index = index
        self._position_overlays()

    def _position_overlays(self) -> None:
        if (
            self._hovered_block_index is None
            or self._body.textStorage().length() == 0
            or not self._block_controls_enabled
        ):
            self._set_gutter_hidden(True)
            return
        lines = str(self._body.string()).split("\n")
        index = min(max(self._hovered_block_index, 0), len(lines) - 1)
        location = sum(_utf16_length(line) + 1 for line in lines[:index])
        location = min(location, self._body.textStorage().length() - 1)
        try:
            layout = self._body.layoutManager()
            glyph = layout.glyphRangeForCharacterRange_actualCharacterRange_(
                NSMakeRange(location, 0), None
            )
            if isinstance(glyph, tuple):
                glyph = glyph[0]
            rect = layout.boundingRectForGlyphRange_inTextContainer_(
                glyph, self._body.textContainer()
            )
            visible = self._body.visibleRect()
            scroll_frame = self._scroll.frame()
            inset = self._body.textContainerInset()
            y = block_gutter_canvas_y(
                scroll_origin_y=float(scroll_frame.origin.y),
                text_inset_y=float(inset.height),
                block_origin_y=float(rect.origin.y),
                scroll_offset_y=float(visible.origin.y),
            )
            visible_top = float(scroll_frame.origin.y) + 4.0
            visible_bottom = float(scroll_frame.origin.y) + float(scroll_frame.size.height) - 32.0
            on_screen = visible_top <= y <= visible_bottom
            self._set_gutter_hidden(not on_screen)
            if not on_screen:
                return
            geometry = block_gutter_layout(
                _BODY_INSET, y - float(self._gutter_hover.frame().origin.y)
            )
            self._plus.setFrameOrigin_((geometry.add.x, geometry.add.y))
            self._block_edit.setFrameOrigin_((geometry.edit.x, geometry.edit.y))
        except (AttributeError, TypeError, ValueError):
            self._set_gutter_hidden(True)

    # -- block actions ------------------------------------------------------

    @objc.python_method
    def prepare_block_command(
        self, *, hovered_index: int | None = None, option_pressed: bool = False
    ) -> None:
        """Capture the real selection before a retained menu changes focus."""
        blocks = self._extract_blocks()
        selection = self.body_selected_range()
        self._command_selection = selection
        selected_indices = (
            block_indices_for_selection(
                str(self._body.string()), selection[0], selection[1]
            )
            if selection[1] > 0
            else []
        )
        candidate = (
            max(selected_indices)
            if selected_indices
            else (
                hovered_index
                if hovered_index is not None
                else self._current_block_index()
            )
        )
        self._command_block_index = min(max(candidate, 0), len(blocks) - 1)
        self._command_option_pressed = bool(option_pressed)

    @objc.IBAction
    def showBlockMenu_(self, sender):  # noqa: N802
        event = self.view.window().currentEvent()
        option_pressed = bool(
            event is not None and int(event.modifierFlags()) & int(NSEventModifierFlagOption)
        )
        self.prepare_block_command(
            hovered_index=self._hovered_block_index,
            option_pressed=option_pressed,
        )
        menu = NSMenu.alloc().initWithTitle_("Add Block")
        for title, kind, symbol in _BLOCK_MENU:
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                title, "chooseBlockType:", ""
            )
            item.setTarget_(self)
            item.setRepresentedObject_(kind.value)
            image = symbol_image(symbol, size=12)
            if image is not None:
                item.setImage_(image)
            menu.addItem_(item)
        self._block_menu = menu
        menu.popUpMenuPositioningItem_atLocation_inView_(None, (0.0, 0.0), sender)

    @objc.IBAction
    def showBlockEditMenu_(self, sender):  # noqa: N802
        """Menu that edits the exact block the gutter is currently beside."""
        # Resolve the target from the hovered block before the menu takes focus,
        # so it never acts on a previously selected block.
        self.prepare_block_command(hovered_index=self._hovered_block_index)
        target = self._command_block_index
        menu = NSMenu.alloc().initWithTitle_("Edit Block")
        for title, kind, symbol in _BLOCK_EDIT_MENU:
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                title, "convertBlockType:", ""
            )
            item.setTarget_(self)
            item.setRepresentedObject_(f"{kind.value}|{target}")
            image = symbol_image(symbol, size=12)
            if image is not None:
                item.setImage_(image)
            menu.addItem_(item)
        menu.addItem_(NSMenuItem.separatorItem())
        for title, action, symbol in (
            ("Duplicate Block", "duplicateBlock:", "plus.square.on.square"),
            ("Delete Block", "deleteBlock:", "trash"),
        ):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, "")
            item.setTarget_(self)
            item.setRepresentedObject_(str(target))
            image = symbol_image(symbol, size=12)
            if image is not None:
                item.setImage_(image)
            menu.addItem_(item)
        self._block_menu = menu
        menu.popUpMenuPositioningItem_atLocation_inView_(None, (0.0, 0.0), sender)

    @objc.IBAction
    def convertBlockType_(self, sender):  # noqa: N802
        payload = str(sender.representedObject())
        raw_kind, _, raw_index = payload.partition("|")
        try:
            kind = BlockType(raw_kind)
            index = int(raw_index)
        except (ValueError, TypeError):
            self._clear_command_context()
            return
        self._convert_block_at_index(kind, index)

    @objc.python_method
    def _convert_block_at_index(self, kind: BlockType, index: int) -> None:
        """Convert exactly one block in place, preserving its text and marks."""
        blocks = self._extract_blocks()
        if not blocks:
            self._clear_command_context()
            return
        index = min(max(int(index), 0), len(blocks) - 1)
        # A collapsed toggle losing its chevron would leave its content hidden
        # with nothing left to reveal it, so expand first.
        blocks = reveal_for_conversion(blocks, index)
        converted = convert_selected_blocks(blocks, [index], kind)
        if converted == blocks:
            self._clear_command_context()
            return
        self._replace_document(converted, register_undo=True, focus_index=index)
        self.focus_body()
        self.flash_status(f"Converted to {self._block_title(kind)}")
        self._clear_command_context()

    @objc.IBAction
    def duplicateBlock_(self, sender):  # noqa: N802
        blocks = self._extract_blocks()
        if not blocks:
            return
        try:
            index = int(str(sender.representedObject()))
        except (ValueError, TypeError):
            return
        index = min(max(index, 0), len(blocks) - 1)
        duplicated = [*blocks[: index + 1], replace(blocks[index]), *blocks[index + 1 :]]
        self._replace_document(duplicated, register_undo=True, focus_index=index + 1)
        self.focus_body()
        self.flash_status("Duplicated block")
        self._clear_command_context()

    @objc.IBAction
    def deleteBlock_(self, sender):  # noqa: N802
        blocks = self._extract_blocks()
        if len(blocks) <= 1:
            return  # never leave the document with no block
        try:
            index = int(str(sender.representedObject()))
        except (ValueError, TypeError):
            return
        index = min(max(index, 0), len(blocks) - 1)
        remaining = [*blocks[:index], *blocks[index + 1 :]]
        self._replace_document(
            remaining, register_undo=True, focus_index=max(0, index - 1)
        )
        self.focus_body()
        self.flash_status("Deleted block")
        self._clear_command_context()

    @objc.IBAction
    def chooseBlockType_(self, sender):  # noqa: N802
        kind = BlockType(str(sender.representedObject()))
        selection = self._command_selection or self.body_selected_range()
        if selection[1] > 0 and kind in PARAGRAPH_BLOCK_TYPES:
            self._convert_command_selection(kind, selection)
            return
        if selection[1] > 0 and kind == BlockType.LINK:
            self.restore_selection(selection)
            self.editLink_(sender)
            self._clear_command_context()
            return
        if kind in (BlockType.IMAGE, BlockType.FILE):
            block = self._on_attachment(kind.value, None)
            if block is not None:
                self._insert_requested_block(block)
            return
        block = Block(kind=kind)
        if kind == BlockType.LINK:
            target = self._prompt_for_link("")
            if target is None:
                return
            block.target = target
        self._insert_requested_block(block)

    def _convert_command_selection(
        self, kind: BlockType, selection: tuple[int, int]
    ) -> None:
        blocks = self._extract_blocks()
        indices = block_indices_for_selection(
            str(self._body.string()), selection[0], selection[1]
        )
        for candidate in indices:
            blocks = reveal_for_conversion(blocks, candidate)
        converted = convert_selected_blocks(blocks, indices, kind)
        if converted == blocks:
            self._clear_command_context()
            return
        self._replace_document(converted, register_undo=True, focus_index=None)
        self.restore_selection(selection)
        self.focus_body()
        self.flash_status(f"Converted to {self._block_title(kind)}")
        self._clear_command_context()

    def _insert_requested_block(self, block: Block) -> None:
        blocks = self._extract_blocks()
        index = min(
            self._command_block_index
            if self._command_block_index is not None
            else self._current_block_index(),
            len(blocks) - 1,
        )
        blocks, destination = apply_block_command(
            blocks,
            index,
            block,
            option_pressed=self._command_option_pressed,
        )
        self._replace_document(blocks, register_undo=True, focus_index=destination)
        self.flash_status(f"{self._block_title(block.kind)} block added")
        self._clear_command_context()

    def _clear_command_context(self) -> None:
        self._command_block_index = None
        self._command_selection = None
        self._command_option_pressed = False

    @objc.python_method
    def _block_title(self, kind: BlockType) -> str:
        return next(
            (title for title, candidate, _symbol in _BLOCK_MENU if candidate == kind),
            "Block",
        )

    def toggle_todo_at_location(self, location: int) -> None:
        self._body.setSelectedRange_(NSMakeRange(location, 0))
        blocks = self._extract_blocks()
        index = min(self._current_block_index(), len(blocks) - 1)
        if blocks[index].kind == BlockType.TODO:
            blocks[index] = toggle_todo(blocks[index])
            self._replace_document(blocks, register_undo=True, focus_index=index)

    def toggle_current_transcript(self) -> None:
        blocks = self._extract_blocks()
        index = min(
            self._context_block_index
            if self._context_block_index is not None
            else self._current_block_index(),
            len(blocks) - 1,
        )
        if blocks[index].kind == BlockType.TRANSCRIPT:
            blocks[index].collapsed = not blocks[index].collapsed
            self._replace_document(blocks, register_undo=True, focus_index=index)

    # -- paste ---------------------------------------------------------------

    @objc.python_method
    def _pasted_runs(self, pasteboard) -> list[PastedRun]:
        """Read a pasteboard into plain, styling-free run descriptions.

        RTF is preferred because it carries bold/italic/underline/links while
        staying inert. HTML is deliberately never parsed: building an attributed
        string from HTML can fetch remote resources, and the plain-text fallback
        below is both safer and sufficient.
        """
        data = pasteboard.dataForType_(NSPasteboardTypeRTF)
        if data is None:
            data = pasteboard.dataForType_(NSPasteboardTypeRTFD)
        if data is not None:
            attributed = NSAttributedString.alloc().initWithRTF_documentAttributes_(data, None)
            if isinstance(attributed, tuple):
                attributed = attributed[0]
            if attributed is not None and attributed.length():
                return self._runs_from_attributed(attributed)
        plain = pasteboard.stringForType_(NSPasteboardTypeString)
        return [PastedRun(str(plain))] if plain else []

    @objc.python_method
    def _runs_from_attributed(self, attributed) -> list[PastedRun]:
        """Map native attributes onto the few fields StormPad understands."""
        runs: list[PastedRun] = []
        cursor = 0
        total = int(attributed.length())
        while cursor < total:
            try:
                attrs, effective = attributed.attributesAtIndex_effectiveRange_(cursor, None)
                end = min(total, int(effective.location + effective.length))
            except (IndexError, TypeError, ValueError):
                attrs, end = {}, cursor + 1
            end = max(end, cursor + 1)
            text = str(
                attributed.attributedSubstringFromRange_(
                    NSMakeRange(cursor, end - cursor)
                ).string()
            )
            traits = _font_traits(attrs.get(NSFontAttributeName))
            link = attrs.get(NSLinkAttributeName)
            if link is not None and not isinstance(link, str):
                link = str(link.absoluteString()) if hasattr(link, "absoluteString") else str(link)
            runs.append(
                PastedRun(
                    text=text,
                    bold=bool(traits & _TRAIT_BOLD),
                    italic=bool(traits & _TRAIT_ITALIC),
                    underline=bool(attrs.get(NSUnderlineStyleAttributeName)),
                    link=link,
                )
            )
            cursor = end
        return runs

    @objc.python_method
    def _sanitized_paste_string(self, runs: list[PastedRun]):
        """Render sanitized runs with the current theme's own attributes.

        The first pasted paragraph joins the block under the caret so pasting
        mid-sentence keeps that block's appearance. Later paragraphs become
        ordinary text blocks rather than inheriting a heading or list prefix.
        """
        blocks = pasted_blocks(runs)
        if not blocks:
            return None
        live = self._extract_blocks()
        index = min(self._current_block_index(), max(0, len(live) - 1))
        caret_block = live[index] if live else Block()
        first_base = self._block_base_attributes(
            Block(kind=caret_block.kind, indent=caret_block.indent)
            if caret_block.kind in PARAGRAPH_BLOCK_TYPES
            else Block()
        )
        text_base = self._block_base_attributes(Block())
        result = NSMutableAttributedString.alloc().init()
        for position, block in enumerate(blocks):
            base = first_base if position == 0 else text_base
            if position:
                result.appendAttributedString_(
                    NSAttributedString.alloc().initWithString_attributes_("\n", text_base)
                )
            for run in block.runs:
                result.appendAttributedString_(
                    NSAttributedString.alloc().initWithString_attributes_(
                        run.text, self._inline_attributes(base, run)
                    )
                )
        return result

    @objc.python_method
    def _pasted_image_sources(self, pasteboard) -> list[Path]:
        """Local image files to import for this paste, newest temp files last.

        Only real bitmap data and local file URLs qualify. Remote URLs and HTML
        are deliberately ignored: StormPad never fetches anything over the
        network to satisfy a paste.
        """
        try:
            urls = (
                pasteboard.readObjectsForClasses_options_(
                    [NSURL], {NSPasteboardURLReadingFileURLsOnlyKey: True}
                )
                or []
            )
        except (AttributeError, TypeError, ValueError):
            urls = []
        files: list[Path] = []
        for url in urls:
            try:
                if not url.isFileURL():
                    continue
                candidate = Path(str(url.path()))
            except (AttributeError, TypeError, ValueError):
                continue
            if candidate.is_file() and attachments.is_image(candidate):
                files.append(candidate)
        if files:
            return files
        for pasteboard_type in (NSPasteboardTypePNG, NSPasteboardTypeTIFF):
            data = pasteboard.dataForType_(pasteboard_type)
            if data is None:
                continue
            written = self._write_temporary_png(data)
            if written is not None:
                return [written]
        return []

    @objc.python_method
    def _write_temporary_png(self, data):
        """Re-encode clipboard bitmap data as PNG in a temporary file.

        PNG keeps transparency and avoids recompression loss. The file is only a
        staging area: the attachment layer copies it into the note's own folder
        and the temporary copy is removed, so no pasteboard path ever reaches
        the Markdown.
        """
        representation = NSBitmapImageRep.imageRepWithData_(data)
        if representation is None:
            return None
        encoded = representation.representationUsingType_properties_(
            NSBitmapImageFileTypePNG, {}
        )
        if encoded is None:
            return None
        handle, name = tempfile.mkstemp(prefix="stormpad-paste-", suffix=".png")
        os.close(handle)
        target = Path(name)
        if not encoded.writeToFile_atomically_(str(target), True):
            target.unlink(missing_ok=True)
            return None
        return target

    @objc.python_method
    def _insert_pasted_images(self, sources: list[Path]) -> bool:
        """Import pasted images and insert them as one undoable edit."""
        created: list[Block] = []
        for source in sources:
            try:
                block = self._on_attachment(BlockType.IMAGE.value, source)
            finally:
                if source.name.startswith("stormpad-paste-"):
                    source.unlink(missing_ok=True)
            if block is not None:
                created.append(block)
        if not created:
            return False
        blocks = self._extract_blocks()
        index = min(self._current_block_index(), max(0, len(blocks) - 1))
        destination = index
        for offset, block in enumerate(created):
            blocks, destination = apply_block_command(
                blocks, destination if offset else index, block
            )
        self._replace_document(blocks, register_undo=True, focus_index=destination)
        self._selected_image_indexes = {
            position
            for position, block in enumerate(blocks)
            if block.kind == BlockType.IMAGE and block in created
        }
        self._refresh_image_selection_chrome()
        self.flash_status(
            f"{len(created)} image{'s' if len(created) != 1 else ''} added"
        )
        return True

    @objc.python_method
    def handle_paste(self, pasteboard) -> bool:
        """Replace the selection with sanitized pasted content, as one edit."""
        sources = self._pasted_image_sources(pasteboard)
        if sources and self._insert_pasted_images(sources):
            return True
        runs = self._pasted_runs(pasteboard)
        if not runs:
            return False
        attributed = self._sanitized_paste_string(runs)
        if attributed is None or not attributed.length():
            return False
        target = self._body.selectedRange()
        replacement = str(attributed.string())
        if not self._body.shouldChangeTextInRange_replacementString_(target, replacement):
            return False
        storage = self._body.textStorage()
        storage.beginEditing()
        storage.replaceCharactersInRange_withAttributedString_(target, attributed)
        storage.endEditing()
        # One didChangeText call keeps the whole paste on a single undo step and
        # lets the delegate run its normal change handling.
        self._body.didChangeText()
        caret = int(target.location) + int(attributed.length())
        self._body.setSelectedRange_(NSMakeRange(caret, 0))
        # Typing after a paste must not inherit the source's styling.
        self._reset_typing_attributes_at_caret()
        return True

    @objc.python_method
    def _reset_typing_attributes_at_caret(self) -> None:
        blocks = self._extract_blocks()
        if not blocks:
            return
        index = min(self._current_block_index(), len(blocks) - 1)
        block = blocks[index]
        self._body.setTypingAttributes_(
            self._block_base_attributes(
                Block(kind=block.kind, checked=block.checked, indent=block.indent)
            )
        )

    # -- collapsible toggles -------------------------------------------------

    @objc.python_method
    def toggle_collapsed_at_location(self, location: int) -> None:
        """Flip one toggle's collapse state from a chevron click.

        Only the summary block changes. Owned content is never touched, so this
        can never remove anything from the note.
        """
        blocks = self._extract_blocks()
        index = block_index_for_location(str(self._body.string()), int(location))
        if not (0 <= index < len(blocks)) or not is_toggle(blocks[index]):
            return
        collapsing = not blocks[index].collapsed
        blocks[index].collapsed = collapsing
        focus = None
        if collapsing:
            start, end = toggle_range(blocks, index)
            caret = block_index_for_location(
                str(self._body.string()), int(self._body.selectedRange().location)
            )
            if start <= caret < end:
                # The caret is inside content that is about to disappear.
                focus = index
        self._replace_document(blocks, register_undo=True, focus_index=focus)

    @objc.python_method
    def _move_caret_out_of_hidden(self) -> None:
        location = int(self._body.selectedRange().location)
        if not self._location_is_hidden(location):
            return
        safe = location
        while safe > 0 and self._location_is_hidden(safe):
            safe -= 1
        self._body.setSelectedRange_(NSMakeRange(max(0, safe), 0))

    @objc.python_method
    def _toggle_return(self, blocks: list[Block], index: int) -> bool:
        """Return on a Toggle List summary. See the feature notes for the rule.

        Expanding first is deliberate: text is never inserted into a range the
        user cannot see.
        """
        block = blocks[index]
        if block.kind != BlockType.TOGGLE or block.is_empty:
            return False
        blocks[index].collapsed = False
        start, end = toggle_range(blocks, index)
        if end > start:
            # Already has children: land in the first one.
            self._replace_document(blocks, register_undo=True, focus_index=None)
            self._select_block_start(start)
            self.focus_body()
            self._schedule_caret_visibility(self._body)
            return True
        child = Block(kind=BlockType.BULLET, indent=block.indent + 1)
        blocks.insert(start, child)
        self._replace_document(blocks, register_undo=True, focus_index=None)
        self._select_block_start(start)
        self.focus_body()
        self._schedule_caret_visibility(self._body)
        return True

    @objc.python_method
    def reveal_before_conversion(self, blocks: list[Block], index: int) -> list[Block]:
        """Expand a toggle that is about to become a normal block."""
        return reveal_for_conversion(blocks, index)

    def handle_dropped_files(self, files: list[Path]) -> bool:
        inserted = False
        for path in files:
            kind = (
                BlockType.IMAGE
                if path.suffix.lower()
                in {
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".gif",
                    ".heic",
                    ".tif",
                    ".tiff",
                    ".webp",
                }
                else BlockType.FILE
            )
            block = self._on_attachment(kind.value, path)
            if block is not None:
                self._insert_requested_block(block)
                inserted = True
        return inserted

    # -- inline formatting --------------------------------------------------

    def _selected_range(self):
        selected = self._body.selectedRange()
        return selected if selected.length > 0 else None

    def _toggle_attribute(self, semantic_key: str, native_key=None, native_value=None) -> None:
        selected = self._selected_range()
        if selected is None:
            return
        text_storage = self._body.textStorage()
        snapshot = text_storage.attributedSubstringFromRange_(selected).copy()
        self._body.undoManager().registerUndoWithTarget_selector_object_(
            self,
            "restoreFormatting:",
            {"range": (int(selected.location), int(selected.length)), "text": snapshot},
        )
        existing = text_storage.attribute_atIndex_effectiveRange_(
            semantic_key, selected.location, None
        )[0]
        text_storage.beginEditing()
        if existing:
            text_storage.removeAttribute_range_(semantic_key, selected)
            if native_key is not None:
                text_storage.removeAttribute_range_(native_key, selected)
        else:
            text_storage.addAttribute_value_range_(semantic_key, True, selected)
            if native_key is not None:
                text_storage.addAttribute_value_range_(native_key, native_value, selected)
        text_storage.endEditing()
        self._refresh_fonts(selected)
        self._emit_body_change()

    def _refresh_fonts(self, selected) -> None:
        storage = self._body.textStorage()
        cursor = int(selected.location)
        end = cursor + int(selected.length)
        while cursor < end:
            attrs, effective = storage.attributesAtIndex_effectiveRange_(cursor, None)
            run_end = min(end, int(effective.location + effective.length))
            base = self._block_base_attributes(
                Block(kind=BlockType(str(attrs.get(_ATTR_BLOCK, BlockType.TEXT.value))))
            )[NSFontAttributeName]
            traits = 0
            if attrs.get(_ATTR_BOLD):
                traits |= NSBoldFontMask
            if attrs.get(_ATTR_ITALIC):
                traits |= NSItalicFontMask
            font = (
                NSFontManager.sharedFontManager().convertFont_toHaveTrait_(base, traits)
                if traits
                else base
            )
            storage.addAttribute_value_range_(
                NSFontAttributeName,
                font,
                NSMakeRange(cursor, max(1, run_end - cursor)),
            )
            cursor = max(cursor + 1, run_end)

    @objc.IBAction
    def toggleBold_(self, sender):  # noqa: N802
        self._toggle_attribute(_ATTR_BOLD)

    @objc.IBAction
    def toggleItalic_(self, sender):  # noqa: N802
        self._toggle_attribute(_ATTR_ITALIC)

    @objc.IBAction
    def toggleUnderline_(self, sender):  # noqa: N802
        self._toggle_attribute(
            _ATTR_UNDERLINE,
            NSUnderlineStyleAttributeName,
            NSUnderlineStyleSingle,
        )

    @objc.IBAction
    def editLink_(self, sender):  # noqa: N802
        selected = self._selected_range()
        if selected is None:
            return
        target = self._prompt_for_link("")
        if target is None:
            return
        storage = self._body.textStorage()
        snapshot = storage.attributedSubstringFromRange_(selected).copy()
        self._body.undoManager().registerUndoWithTarget_selector_object_(
            self,
            "restoreFormatting:",
            {"range": (int(selected.location), int(selected.length)), "text": snapshot},
        )
        storage.addAttributes_range_(
            {
                _ATTR_LINK: target,
                NSLinkAttributeName: target,
                NSForegroundColorAttributeName: self._palette.accent,
            },
            selected,
        )
        self._emit_body_change()

    def _prompt_for_link(self, initial: str) -> str | None:
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Add Link")
        alert.setInformativeText_("Enter a URL or local relative path.")
        field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 320, 24))
        field.setStringValue_(initial)
        field.setAccessibilityLabel_("Link destination")
        alert.setAccessoryView_(field)
        alert.addButtonWithTitle_("Add")
        alert.addButtonWithTitle_("Cancel")
        if alert.runModal() != 1000:
            return None
        value = str(field.stringValue()).strip()
        return value or None

    @objc.IBAction
    def showTextColorMenu_(self, sender):  # noqa: N802
        self._show_color_menu(sender, "text")

    @objc.IBAction
    def showHighlightMenu_(self, sender):  # noqa: N802
        self._show_color_menu(sender, "highlight")

    def _show_color_menu(self, sender, mode: str) -> None:
        """Show the compact palette panel (Recently used / Text / Background).

        ``mode`` only decides which section the caller cares about; the panel
        always exposes both so one floating surface covers text and background.
        """
        menu = NSMenu.alloc().initWithTitle_("Color")
        item = NSMenuItem.alloc().init()
        item.setView_(
            build_color_palette_view(
                self._palette,
                recents=self._color_recents,
                selected_text=self.selected_color_token("text"),
                selected_highlight=self.selected_color_token("highlight"),
                target=self,
            )
        )
        menu.addItem_(item)
        self._color_menu = menu
        menu.popUpMenuPositioningItem_atLocation_inView_(None, (0.0, 0.0), sender)

    @objc.python_method
    def set_color_recents(self, recents) -> None:
        self._color_recents = [entry for entry in (recents or []) if ":" in entry]

    @objc.python_method
    def color_menu_title(self, token: str, mode: str) -> str:
        if token == "default":
            return "Clear" if mode == "text" else "Clear / Transparent"
        return token.replace("_", " ").title()

    @objc.python_method
    def _color_swatch_image(self, token: str, mode: str, *, selected: bool = False):
        image = NSImage.alloc().initWithSize_(NSMakeSize(16.0, 16.0))
        image.lockFocus()
        rect = NSMakeRect(2.0, 2.0, 12.0, 12.0)
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(rect, 3.0, 3.0)
        color = (
            self._palette.formatting_background
            if token == "default"
            else self._semantic_color(token)
        )
        color.colorWithAlphaComponent_(0.45 if mode == "highlight" else 1.0).setFill()
        path.fill()
        (self._palette.accent_strong if selected else self._palette.formatting_border).setStroke()
        path.setLineWidth_(2.0 if selected else 1.0)
        path.stroke()
        if token == "default":
            slash = NSBezierPath.bezierPath()
            slash.moveToPoint_((4.0, 4.0))
            slash.lineToPoint_((12.0, 12.0))
            slash.setLineWidth_(1.5)
            self._palette.text_muted.setStroke()
            slash.stroke()
        image.unlockFocus()
        return image

    @objc.python_method
    def selected_color_token(self, mode: str) -> str:
        selected = self._selected_range()
        if selected is None or self._body.textStorage().length() == 0:
            return "default"
        semantic = _ATTR_TEXT_COLOR if mode == "text" else _ATTR_HIGHLIGHT
        storage = self._body.textStorage()
        cursor = int(selected.location)
        end = cursor + int(selected.length)
        tokens: set[str] = set()
        while cursor < end:
            attrs, effective = storage.attributesAtIndex_effectiveRange_(
                cursor, None
            )
            token = str(attrs.get(semantic) or "default")
            tokens.add(token if token in COLOR_TOKENS else "default")
            cursor = max(cursor + 1, min(end, int(effective.location + effective.length)))
        return next(iter(tokens)) if len(tokens) == 1 else "mixed"

    @objc.IBAction
    def chooseColor_(self, sender):  # noqa: N802
        selected = self._selected_range()
        if selected is None:
            return
        payload = None
        if hasattr(sender, "representedObject"):
            payload = sender.representedObject()
        if payload is None and hasattr(sender, "identifier"):
            payload = sender.identifier()
        parts = str(payload).split(":", 1)
        if len(parts) != 2:
            return
        mode, token = parts
        if mode not in {"text", "highlight"} or token not in COLOR_TOKENS:
            return
        semantic = _ATTR_TEXT_COLOR if mode == "text" else _ATTR_HIGHLIGHT
        native = (
            NSForegroundColorAttributeName if mode == "text" else NSBackgroundColorAttributeName
        )
        storage = self._body.textStorage()
        snapshot = storage.attributedSubstringFromRange_(selected).copy()
        self._body.undoManager().registerUndoWithTarget_selector_object_(
            self,
            "restoreFormatting:",
            {"range": (int(selected.location), int(selected.length)), "text": snapshot},
        )
        if token == "default":
            storage.removeAttribute_range_(semantic, selected)
            if mode == "text":
                self._restore_semantic_foreground(selected)
            else:
                storage.removeAttribute_range_(native, selected)
        else:
            storage.addAttribute_value_range_(semantic, token, selected)
            storage.addAttribute_value_range_(
                native,
                self._semantic_color(token, alpha=1.0 if mode == "text" else 0.28),
                selected,
            )
        self._emit_body_change()
        if self.on_color_used is not None:
            self.on_color_used(f"{mode}:{token}")
        if self._color_menu is not None:
            self._color_menu.cancelTracking()

    def _restore_semantic_foreground(self, selected) -> None:
        storage = self._body.textStorage()
        cursor = int(selected.location)
        end = cursor + int(selected.length)
        while cursor < end:
            attrs, effective = storage.attributesAtIndex_effectiveRange_(
                cursor, None
            )
            run_end = max(
                cursor + 1,
                min(end, int(effective.location + effective.length)),
            )
            color = (
                self._palette.accent
                if attrs.get(_ATTR_LINK)
                else self._palette.editor_text
            )
            storage.addAttribute_value_range_(
                NSForegroundColorAttributeName,
                color,
                NSMakeRange(cursor, run_end - cursor),
            )
            cursor = run_end

    def restoreFormatting_(self, payload):  # noqa: N802
        location, length = payload["range"]
        selected = NSMakeRange(location, length)
        current = self._body.textStorage().attributedSubstringFromRange_(selected).copy()
        self._body.undoManager().registerUndoWithTarget_selector_object_(
            self,
            "restoreFormatting:",
            {"range": (location, length), "text": current},
        )
        self._body.textStorage().replaceCharactersInRange_withAttributedString_(
            selected, payload["text"]
        )
        self.restore_selection((location, length))
        self._emit_body_change()

    # -- status -------------------------------------------------------------

    @objc.python_method
    def set_status(self, status: SaveStatus) -> None:
        self._last_status = status
        self._status.setStringValue_(status.value)
        self._status.setTextColor_(
            self._palette.destructive if status == SaveStatus.FAILED else self._palette.text_muted
        )
        self._status.setHidden_(False)
        if status == SaveStatus.SAVED:
            NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                1.0, False, lambda timer: self._hide_saved_status()
            )

    def _hide_saved_status(self) -> None:
        if self._last_status == SaveStatus.SAVED:
            self._status.setHidden_(True)

    @objc.python_method
    def flash_status(self, text: str) -> None:
        self._status.setStringValue_(text)
        self._status.setTextColor_(self._palette.accent_strong)
        self._status.setHidden_(False)
        NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
            1.2, False, lambda timer: self._hide_saved_status()
        )

    # -- delegates / keyboard ----------------------------------------------

    def controlTextDidChange_(self, notification):  # noqa: N802
        if not self._loading:
            self._clear_full_note_selection_visual()
            self._on_title(self.title_text())

    def controlTextDidEndEditing_(self, notification):  # noqa: N802
        if not self._loading:
            self._on_title(self.title_text())

    def textDidBeginEditing_(self, notification):  # noqa: N802
        pass

    def textDidEndEditing_(self, notification):  # noqa: N802
        self._formatting.setHidden_(True)

    @objc.python_method
    def _authoritative_return_state(self) -> tuple[list[Block], tuple[int, int]]:
        """Snapshot only the current AppKit storage and NSTextView selection."""
        if self._body.hasMarkedText():
            self._body.unmarkText()

        storage = self._body.textStorage()
        length = int(storage.length())
        if hasattr(storage, "ensureAttributesAreFixedInRange_"):
            storage.ensureAttributesAreFixedInRange_(NSMakeRange(0, length))
        self._body.layoutManager().ensureLayoutForTextContainer_(
            self._body.textContainer()
        )

        selected = self._body.selectedRange()
        location = int(selected.location)
        span = int(selected.length)
        if location < 0 or location > length or span < 0 or location + span > length:
            location = min(max(location, 0), length)
            span = min(max(span, 0), length - location)
        return self._extract_blocks(), (location, span)

    @objc.python_method
    def _cancel_pending_return(self) -> None:
        self._pending_return_token += 1
        timer = self._pending_return_timer
        self._pending_return_timer = None
        self._pending_return_note_id = None
        if timer is not None:
            timer.invalidate()

    @objc.python_method
    def _cancel_pending_caret_visibility(self) -> None:
        self._pending_caret_visibility_token += 1
        timer = self._pending_caret_visibility_timer
        self._pending_caret_visibility_timer = None
        self._pending_caret_visibility_note_id = None
        if timer is not None:
            timer.invalidate()

    @objc.python_method
    def _caret_context_is_active(
        self,
        note_id: str | None,
        block_index: int,
        text_view,
    ) -> bool:
        current_id = self._current.id if self._current is not None else None
        return (
            text_view is self._body
            and current_id == note_id
            and self.body_is_first_responder()
            and self._current_block_index() == block_index
        )

    @objc.python_method
    def _schedule_caret_visibility(self, text_view) -> None:
        """Check the moved caret after AppKit completes text layout."""
        self._cancel_pending_caret_visibility()
        text_view.layoutManager().ensureLayoutForTextContainer_(
            text_view.textContainer()
        )
        token = self._pending_caret_visibility_token
        note_id = self._current.id if self._current is not None else None
        block_index = self._current_block_index()
        self._pending_caret_visibility_note_id = note_id

        def fire(_timer):
            self._perform_pending_caret_visibility(
                token,
                note_id,
                block_index,
                text_view,
            )

        self._pending_caret_visibility_timer = (
            NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                0.01,
                False,
                fire,
            )
        )

    @objc.python_method
    def _perform_pending_caret_visibility(
        self,
        token: int,
        note_id: str | None,
        block_index: int,
        text_view,
    ) -> None:
        if token != self._pending_caret_visibility_token:
            return
        try:
            if not self._caret_context_is_active(note_id, block_index, text_view):
                return
            self._scroll_caret_into_comfortable_view(text_view)
        finally:
            if token == self._pending_caret_visibility_token:
                self._pending_caret_visibility_token += 1
                self._pending_caret_visibility_timer = None
                self._pending_caret_visibility_note_id = None

    @objc.python_method
    def _scroll_caret_into_comfortable_view(self, text_view) -> bool:
        """Minimally reveal the actual insertion rect, preserving horizontal scroll."""
        selected = text_view.selectedRange()
        if int(selected.length) != 0:
            return False
        did_scroll = False
        # NSTextView can finalize its document height as the first scroll is
        # applied. Re-measure once so a newly inserted tall block cannot leave
        # the actual insertion rect outside the final clip bounds.
        for _layout_pass in range(2):
            caret_in_document = self._caret_rect_in_document(
                text_view,
                int(selected.location),
            )

            clip = self._scroll.contentView()
            visible = clip.bounds()
            visible_top = float(visible.origin.y)
            visible_bottom = visible_top + float(visible.size.height)
            bottom_inset = float(self._scroll.contentInsets().bottom)
            caret_top = float(caret_in_document.origin.y)
            caret_bottom = caret_top + max(
                1.0,
                float(caret_in_document.size.height),
            )
            comfortable_top = visible_top + 8.0
            comfortable_bottom = (
                visible_bottom + bottom_inset - _CARET_BOTTOM_MARGIN
            )

            if comfortable_top <= caret_top and caret_bottom <= comfortable_bottom:
                return did_scroll
            if caret_bottom > comfortable_bottom:
                target_y = (
                    caret_bottom
                    + _CARET_BOTTOM_MARGIN
                    - float(visible.size.height)
                    - bottom_inset
                )
            else:
                target_y = caret_top - 8.0

            document = self._scroll.documentView()
            document_height = max(
                float(document.frame().size.height),
                float(document.bounds().size.height),
            )
            maximum_y = max(
                0.0,
                document_height
                - float(visible.size.height)
                + _EDITOR_BOTTOM_INSET,
            )
            target_y = min(max(0.0, target_y), maximum_y)
            if abs(target_y - visible_top) < 0.5:
                return did_scroll
            clip.scrollToPoint_(NSMakePoint(float(visible.origin.x), target_y))
            self._scroll.reflectScrolledClipView_(clip)
            did_scroll = True
        return did_scroll

    @objc.python_method
    def _caret_rect_in_document(self, text_view, location: int):
        """Convert the active NSTextView insertion rect into document coordinates."""
        layout = text_view.layoutManager()
        container = text_view.textContainer()
        layout.ensureLayoutForTextContainer_(container)
        glyph_range = layout.glyphRangeForCharacterRange_actualCharacterRange_(
            NSMakeRange(int(location), 0),
            None,
        )
        if isinstance(glyph_range, tuple):
            glyph_range = glyph_range[0]
        caret = layout.boundingRectForGlyphRange_inTextContainer_(
            glyph_range,
            container,
        )
        inset = text_view.textContainerInset()
        return NSMakeRect(
            float(caret.origin.x) + float(inset.width),
            float(caret.origin.y) + float(inset.height),
            max(1.0, float(caret.size.width)),
            max(1.0, float(caret.size.height)),
        )

    @objc.python_method
    def _return_context_is_active(self, note_id: str | None, text_view) -> bool:
        current_id = self._current.id if self._current is not None else None
        return (
            text_view is self._body
            and current_id == note_id
            and self.body_is_first_responder()
        )

    @objc.python_method
    def _schedule_structural_return(self, text_view) -> None:
        """Consume Return now and split from live AppKit state next run-loop turn."""
        self._cancel_pending_return()
        token = self._pending_return_token
        note_id = self._current.id if self._current is not None else None
        self._pending_return_note_id = note_id

        def fire(_timer):
            self._perform_pending_structural_return(token, note_id, text_view)

        self._pending_return_timer = (
            NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                0.0,
                False,
                fire,
            )
        )

    @objc.python_method
    def _flush_pending_return_text_change(self) -> None:
        # The next-turn boundary makes the final key authoritative in storage.
        # Emit from that storage before autosave is flushed so persistence sees
        # the same complete text that the structural split will consume.
        self._emit_body_change()
        if self.before_structural_return is not None:
            self.before_structural_return()

    @objc.python_method
    def _perform_pending_structural_return(
        self,
        token: int,
        note_id: str | None,
        text_view,
    ) -> None:
        if token != self._pending_return_token:
            return
        try:
            if not self._return_context_is_active(note_id, text_view):
                return
            self._flush_pending_return_text_change()
            if not self._return_context_is_active(note_id, text_view):
                return
            blocks, selection = self._authoritative_return_state()
            self._apply_structural_return(blocks, selection)
        finally:
            if token == self._pending_return_token:
                self._pending_return_token += 1
                self._pending_return_timer = None
                self._pending_return_note_id = None

    @objc.python_method
    def _apply_structural_return(
        self,
        blocks: list[Block],
        selection: tuple[int, int],
    ) -> None:
        """Apply one structural Return from an authoritative live snapshot."""
        index = min(
            block_index_for_location(str(self._body.string()), selection[0]),
            len(blocks) - 1,
        )
        block = blocks[index]
        if selection[1] == 0 and self._toggle_return(blocks, index):
            return
        if selection[1] > 0:
            indices = block_indices_for_selection(
                str(self._body.string()), selection[0], selection[1]
            )
            blocks, destination = insert_block_after_selection(blocks, indices)
            self._replace_document(
                blocks,
                register_undo=True,
                focus_index=None,
            )
            self._select_block_start(destination)
            self.focus_body()
            self._schedule_caret_visibility(self._body)
            return
        if block.is_empty and block.kind != BlockType.TEXT:
            blocks[index] = empty_return_result(block)
            self._replace_document(blocks, register_undo=True, focus_index=index)
            self._schedule_caret_visibility(self._body)
            return

        if block.kind in PARAGRAPH_BLOCK_TYPES:
            lines = str(self._body.string()).split("\n")
            line_start = sum(_utf16_length(line) + 1 for line in lines[:index])
            display = lines[index] if index < len(lines) else ""
            prefix_length = max(
                0,
                _utf16_length(display) - _utf16_length(block.text),
            )
            text_offset = max(
                0,
                int(selection[0]) - line_start - prefix_length,
            )
            first, second = split_block_after_return(
                block,
                _python_offset_from_utf16(block.text, text_offset),
            )
            blocks[index] = first
            blocks.insert(index + 1, second)
            destination = index + 1
        else:
            blocks, destination = insert_block(
                blocks,
                index,
                next_block_after_return(block),
            )
        self._replace_document(
            blocks,
            register_undo=True,
            focus_index=None,
        )
        self._select_block_start(destination)
        self.focus_body()
        self._schedule_caret_visibility(self._body)

    def control_textView_doCommandBySelector_(  # noqa: N802
        self, control, text_view, selector
    ):
        if control is self._title and str(selector) == "selectAll:":
            self.select_all_note_content()
            return True
        if control is self._title and title_command_focus(str(selector)) == "body":
            self._on_title(self.title_text())
            self.focus_body()
            self._select_block(0)
            return True
        return False

    def textDidChange_(self, notification):  # noqa: N802
        if not self._loading:
            self._emit_body_change()

    def textViewDidChangeSelection_(self, notification):  # noqa: N802
        if self._full_note_selected and not self._setting_full_note_selection:
            selected = self.body_selected_range()
            if selected != (0, int(self._body.string().length())):
                self._clear_full_note_selection_visual()
        selected = self._body.selectedRange()
        if int(selected.length) == 0 and self._body.textStorage().length() > 0:
            block_index = block_index_for_location(
                str(self._body.string()), int(selected.location)
            )
            editable_start = self._editable_block_start(block_index)
            if int(selected.location) < editable_start:
                self._body.setSelectedRange_(NSMakeRange(editable_start, 0))
                selected = self._body.selectedRange()
        if self._selected_image_index is not None:
            probe = min(
                int(selected.location),
                max(0, int(self._body.textStorage().length()) - 1),
            )
            try:
                attrs = self._body.textStorage().attributesAtIndex_effectiveRange_(
                    probe, None
                )[0]
                if (
                    int(selected.length) != 1
                    or attrs.get(_ATTR_BLOCK) != BlockType.IMAGE.value
                ):
                    self._selected_image_index = None
                    self._body.setNeedsDisplay_(True)
            except (IndexError, TypeError, ValueError):
                self._selected_image_index = None
        if not self._loading:
            self._normalize_typing_attributes()
        show_formatting = formatting_toolbar_visible(
            selection_length=int(selected.length),
            editor_focused=self.body_is_first_responder(),
        )
        self._formatting.setHidden_(not show_formatting)
        if show_formatting:
            self._position_formatting_toolbar()

    @objc.python_method
    def _normalize_typing_attributes(self) -> None:
        """Stop typed text from inheriting a block's leading decoration.

        A To-do/bullet/quote/file prefix (e.g. the ``☐`` checkbox glyph) carries
        ``_ATTR_DECORATION`` and a larger prefix font. When the caret sits just
        after the prefix — the common case right after typing the first character
        — NSTextView derives its typing attributes from that decorated prefix, so
        the newly typed text is tagged as decoration and later dropped by
        ``_extract_blocks`` (losing the whole line on Return or autosave).
        Rewriting the typing attributes to the block's clean content attributes
        keeps typed text as real content.
        """
        typing = self._body.typingAttributes()
        if not typing or typing.get(_ATTR_DECORATION) not in ("todo", "prefix"):
            return
        try:
            kind = BlockType(str(_attr_value(typing, _ATTR_BLOCK, BlockType.TEXT.value)))
        except ValueError:
            kind = BlockType.TEXT
        block = Block(
            kind=kind,
            checked=bool(typing.get(_ATTR_CHECKED, False)),
            indent=int(typing.get(_ATTR_INDENT, 0) or 0),
        )
        self._body.setTypingAttributes_(self._block_base_attributes(block))

    def _position_formatting_toolbar(self) -> None:
        selected = self._body.selectedRange()
        try:
            layout = self._body.layoutManager()
            glyph = layout.glyphRangeForCharacterRange_actualCharacterRange_(selected, None)
            if isinstance(glyph, tuple):
                glyph = glyph[0]
            rect = layout.boundingRectForGlyphRange_inTextContainer_(
                glyph, self._body.textContainer()
            )
            visible = self._body.visibleRect()
            scroll_frame = self._scroll.frame()
            inset = self._body.textContainerInset()
            x = max(
                112.0,
                min(
                    float(scroll_frame.origin.x)
                    + float(inset.width)
                    + float(rect.origin.x)
                    - float(visible.origin.x),
                    float(self.view.bounds().size.width) - 220.0,
                ),
            )
            y = max(
                108.0,
                float(scroll_frame.origin.y)
                + float(inset.height)
                + float(rect.origin.y)
                - float(visible.origin.y)
                - 40.0,
            )
            self._formatting.setFrameOrigin_((x, y))
        except (AttributeError, TypeError, ValueError):
            pass

    def textView_doCommandBySelector_(self, text_view, selector):  # noqa: N802
        command = str(selector)
        if command == "selectAll:":
            self.select_all_note_content()
            return True
        if command == "cancelOperation:" and self._selected_image_indexes:
            self.clear_image_selection()
            return True
        if command in ("deleteBackward:", "deleteForward:", "delete:"):
            if self._full_note_selected:
                self.clear_note_content()
                return True
            if len(self._selected_image_indexes) > 1:
                self.delete_selected_images()
                return True
            if self._selected_image_index is not None:
                self._remove_attachment_at_index(self._selected_image_index)
                return True
        if command == "insertNewline:":
            self._schedule_structural_return(text_view)
            return True
        blocks = self._extract_blocks()
        index = min(self._current_block_index(), len(blocks) - 1)
        block = blocks[index]
        if command == "deleteBackward:" and block.is_empty:
            if index > 0:
                blocks, destination = merge_empty_block_backward(blocks, index)
                self._replace_document(
                    blocks,
                    register_undo=True,
                    focus_index=destination,
                )
                self._schedule_caret_visibility(self._body)
                return True
            if block.kind != BlockType.TEXT:
                blocks[index] = backspace_empty_result(block)
                self._replace_document(blocks, register_undo=True, focus_index=index)
                return True
        if command in ("insertTab:", "insertBacktab:") and block.kind in (
            BlockType.BULLET,
            BlockType.NUMBERED,
            BlockType.TODO,
        ):
            block.indent = max(0, block.indent + (1 if command == "insertTab:" else -1))
            self._replace_document(blocks, register_undo=True, focus_index=index)
            return True
        if command == "moveUp:" and int(self._body.selectedRange().location) == 0:
            self.focus_title()
            return True
        return False

    def textView_willChangeSelectionFromCharacterRange_toCharacterRange_(  # noqa: N802
        self, text_view, old_range, new_range
    ):
        """Never let a caret or selection land inside collapsed content.

        Hidden text is still in the storage, so arrow keys and clicks would
        otherwise walk straight into it. Snapping back to the last visible
        position keeps hidden ranges unreachable without deleting anything.
        """
        if not self._hidden_character_ranges():
            return new_range
        location = int(new_range.location)
        if not self._location_is_hidden(location):
            return new_range
        safe = location
        while safe > 0 and self._location_is_hidden(safe):
            safe -= 1
        return NSMakeRange(max(0, safe), 0)

    def textView_shouldChangeTextInRange_replacementString_(  # noqa: N802
        self, text_view, selected, replacement
    ):
        if self._body.textStorage().length() == 0:
            return True
        if int(selected.length) > 0:
            indices = block_indices_for_selection(
                str(self._body.string()),
                int(selected.location),
                int(selected.length),
            )
            if len(indices) > 1:
                return True
        probe = min(int(selected.location), self._body.textStorage().length() - 1)
        try:
            attrs = self._body.textStorage().attributesAtIndex_effectiveRange_(probe, None)[0]
            return not bool(attrs.get(_ATTR_READ_ONLY))
        except (IndexError, TypeError, ValueError):
            return True

    def textView_menu_forEvent_atIndex_(  # noqa: N802
        self, text_view, menu, event, index
    ):
        self._context_block_index = block_index_for_location(str(self._body.string()), int(index))
        self._context_transcript_chunk = None
        attrs = {}
        if self._body.textStorage().length() > 0:
            probe = min(int(index), self._body.textStorage().length() - 1)
            attrs = self._body.textStorage().attributesAtIndex_effectiveRange_(probe, None)[0]
        kind = attrs.get(_ATTR_BLOCK)
        if kind in (BlockType.IMAGE.value, BlockType.FILE.value):
            if kind == BlockType.IMAGE.value:
                self._selected_image_index = self._context_block_index
                self._body.setSelectedRange_(NSMakeRange(int(index), 1))
                self._body.setNeedsDisplay_(True)
            menu.addItem_(NSMenuItem.separatorItem())
            if kind == BlockType.IMAGE.value:
                multiple = len(self._selected_image_indexes) > 1
                entries = [
                    ("Align Left Edges" if multiple else "Align Left", "alignImageLeft:"),
                    (
                        "Align Horizontal Centers" if multiple else "Align Center",
                        "alignImageCenter:",
                    ),
                    ("Align Right Edges" if multiple else "Align Right", "alignImageRight:"),
                ]
                if multiple:
                    entries.append(("Match Width", "matchImageWidths:"))
                entries.append(
                    ("Fit All to Column" if multiple else "Fit to Column", "fitImageToColumn:")
                )
                entries.append(("Reset Size", "resetImageSize:"))
                for title, action in entries:
                    item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                        title, action, ""
                    )
                    item.setTarget_(self)
                    item.setToolTip_(title)
                    item.setAccessibilityLabel_(title)
                    menu.addItem_(item)
                menu.addItem_(NSMenuItem.separatorItem())
            open_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Open" if kind == BlockType.IMAGE.value else "Open Managed File",
                "openAttachment:",
                "",
            )
            open_item.setTarget_(self)
            open_item.setRepresentedObject_(self._context_block_index)
            menu.addItem_(open_item)
            reveal = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                (
                    "Reveal in Finder"
                    if kind == BlockType.IMAGE.value
                    else "Reveal Managed Attachment"
                ),
                "revealAttachment:",
                "",
            )
            reveal.setTarget_(self)
            reveal.setRepresentedObject_(self._context_block_index)
            menu.addItem_(reveal)
            remove = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                (
                    "Remove Image"
                    if kind == BlockType.IMAGE.value
                    else "Remove Attachment Block"
                ),
                "removeAttachmentBlock:",
                "",
            )
            remove.setTarget_(self)
            remove.setRepresentedObject_(self._context_block_index)
            menu.addItem_(remove)
        if kind == BlockType.TRANSCRIPT.value:
            chunk_index = attrs.get(_ATTR_TRANSCRIPT_CHUNK)
            self._context_transcript_chunk = int(chunk_index) if chunk_index is not None else None
            menu.addItem_(NSMenuItem.separatorItem())
            toggle = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Collapse / Expand Transcript", "toggleTranscript:", ""
            )
            toggle.setTarget_(self)
            menu.addItem_(toggle)
            if self.transcript_target is not None:
                append = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    "Append Test Transcript", "appendTranscript:", ""
                )
                append.setTarget_(self.transcript_target)
                menu.addItem_(append)
            if self._context_transcript_chunk is not None:
                remove_chunk = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    "Remove Transcript Chunk", "removeTranscriptChunk:", ""
                )
                remove_chunk.setTarget_(self)
                menu.addItem_(remove_chunk)
            menu.addItem_(NSMenuItem.separatorItem())
            remove_container = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Remove Transcript Container", "removeTranscriptContainer:", ""
            )
            remove_container.setTarget_(self)
            menu.addItem_(remove_container)
        if self.speech_target is not None:
            menu.addItem_(NSMenuItem.separatorItem())
            speak = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Speak Selection", "speakSelection:", ""
            )
            speak.setTarget_(self.speech_target)
            menu.addItem_(speak)
            stop = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Stop Speaking", "stopSpeaking:", ""
            )
            stop.setTarget_(self.speech_target)
            menu.addItem_(stop)
        return menu

    @objc.IBAction
    def toggleTranscript_(self, sender):  # noqa: N802
        self.toggle_current_transcript()

    @objc.IBAction
    def removeTranscriptContainer_(self, sender):  # noqa: N802
        blocks = self._extract_blocks()
        index = min(
            self._context_block_index
            if self._context_block_index is not None
            else self._current_block_index(),
            len(blocks) - 1,
        )
        if blocks[index].kind != BlockType.TRANSCRIPT:
            return
        blocks.pop(index)
        self._replace_document(
            blocks or [Block()],
            register_undo=True,
            focus_index=min(index, max(0, len(blocks) - 1)),
        )

    @objc.IBAction
    def moveTranscriptBlockUp_(self, sender):  # noqa: N802
        self._move_context_block(-1)

    @objc.IBAction
    def moveTranscriptBlockDown_(self, sender):  # noqa: N802
        self._move_context_block(1)

    @objc.python_method
    def _move_context_block(self, offset: int) -> None:
        blocks = self._extract_blocks()
        source = min(
            self._context_block_index
            if self._context_block_index is not None
            else self._current_block_index(),
            len(blocks) - 1,
        )
        if blocks[source].kind != BlockType.TRANSCRIPT:
            return
        insertion = source - 1 if offset < 0 else source + 2
        blocks, destination = reorder_blocks(blocks, source, insertion)
        self._context_block_index = destination
        self._replace_document(blocks, register_undo=True, focus_index=destination)

    @objc.IBAction
    def removeTranscriptChunk_(self, sender):  # noqa: N802
        if self._current is None or self._context_transcript_chunk is None:
            return
        index = self._context_transcript_chunk
        if not 0 <= index < len(self._current.transcript):
            return
        previous = list(self._current.transcript)
        self._current.transcript = remove_transcript_chunk(self._current.transcript, index)
        self._register_transcript_undo(previous)
        self._refresh_transcript_after_chunk_change()

    @objc.IBAction
    def moveTranscriptChunkUp_(self, sender):  # noqa: N802
        self._move_transcript_chunk(-1)

    @objc.IBAction
    def moveTranscriptChunkDown_(self, sender):  # noqa: N802
        self._move_transcript_chunk(1)

    @objc.python_method
    def _move_transcript_chunk(self, offset: int) -> None:
        if self._current is None or self._context_transcript_chunk is None:
            return
        source = self._context_transcript_chunk
        if not 0 <= source < len(self._current.transcript):
            return
        previous = list(self._current.transcript)
        self._current.transcript, destination = move_transcript_chunk(
            self._current.transcript, source, offset
        )
        if destination == source:
            return
        self._register_transcript_undo(previous)
        self._context_transcript_chunk = destination
        self._refresh_transcript_after_chunk_change()

    @objc.python_method
    def _register_transcript_undo(self, chunks: list) -> None:
        self._body.undoManager().registerUndoWithTarget_selector_object_(
            self, "restoreTranscriptChunks:", chunks
        )

    def restoreTranscriptChunks_(self, chunks):  # noqa: N802
        if self._current is None:
            return
        current = list(self._current.transcript)
        self._register_transcript_undo(current)
        self._current.transcript = list(chunks)
        self._refresh_transcript_after_chunk_change()

    @objc.python_method
    def _refresh_transcript_after_chunk_change(self) -> None:
        blocks = self._extract_blocks()
        index = next(
            (i for i, block in enumerate(blocks) if block.kind == BlockType.TRANSCRIPT),
            None,
        )
        if index is None:
            return
        self._replace_document(blocks, register_undo=False, focus_index=index)

    def _attachment_index_from_sender(self, sender) -> int:
        represented = sender.representedObject() if sender is not None else None
        if represented is not None:
            return int(represented)
        return self._current_block_index()

    def _attachment_path_at_index(
        self, index: int
    ) -> tuple[Path | None, str | None]:
        if self._current is None:
            return None, None
        blocks = self._extract_blocks()
        index = min(max(index, 0), len(blocks) - 1)
        target = blocks[index].target
        if not target:
            return None, None
        notes_dir = self.notes_dir or self._current.path.parent
        resolved = attachments.resolve_managed_path(
            self._current.path,
            target,
            notes_dir,
            self._current.id,
        )
        return resolved, target

    # -- image command actions --------------------------------------------------

    @objc.IBAction
    def alignImageLeft_(self, sender):  # noqa: N802
        self.align_selected_images("left")

    @objc.IBAction
    def alignImageCenter_(self, sender):  # noqa: N802
        self.align_selected_images("center")

    @objc.IBAction
    def alignImageRight_(self, sender):  # noqa: N802
        self.align_selected_images("right")

    @objc.IBAction
    def matchImageWidths_(self, sender):  # noqa: N802
        self.match_selected_image_widths()

    @objc.IBAction
    def fitImageToColumn_(self, sender):  # noqa: N802
        self.fit_selected_images_to_column()

    @objc.IBAction
    def resetImageSize_(self, sender):  # noqa: N802
        self.reset_selected_images_to_natural_size()

    @objc.IBAction
    def openAttachment_(self, sender):  # noqa: N802
        path, _target = self._attachment_path_at_index(
            self._attachment_index_from_sender(sender)
        )
        if path is not None and path.exists():
            NSWorkspace.sharedWorkspace().openURL_(NSURL.fileURLWithPath_(str(path)))

    @objc.IBAction
    def revealAttachment_(self, sender):  # noqa: N802
        path, _target = self._attachment_path_at_index(
            self._attachment_index_from_sender(sender)
        )
        if path is not None and path.exists():
            NSWorkspace.sharedWorkspace().activateFileViewerSelectingURLs_(
                [NSURL.fileURLWithPath_(str(path))]
            )

    @objc.IBAction
    def removeAttachmentBlock_(self, sender):  # noqa: N802
        self._remove_attachment_at_index(self._attachment_index_from_sender(sender))

    @objc.python_method
    def _remove_attachment_at_index(self, index: int) -> None:
        if self._current is None:
            return
        blocks = self._extract_blocks()
        index = min(max(index, 0), len(blocks) - 1)
        block = blocks[index]
        if block.kind not in (BlockType.IMAGE, BlockType.FILE) or not block.target:
            return
        attachments.record_orphan(
            self.notes_dir or self._current.path.parent,
            self._current.id,
            block.target,
        )
        blocks.pop(index)
        if not blocks:
            blocks = [Block()]
        self._selected_image_index = None
        self._replace_document(
            blocks,
            register_undo=True,
            focus_index=min(index, len(blocks) - 1),
        )

    @objc.python_method
    def persist_image_width(self, index: int, width: float) -> None:
        blocks = self._extract_blocks()
        if not 0 <= index < len(blocks) or blocks[index].kind != BlockType.IMAGE:
            return
        usable = max(
            _IMAGE_MIN_WIDTH,
            float(self._body.textContainer().containerSize().width) - 8.0,
        )
        blocks[index].display_width = min(usable, max(_IMAGE_MIN_WIDTH, width))
        self._replace_document(blocks, register_undo=True, focus_index=None)
        self._selected_image_index = index
        lines = str(self._body.string()).split("\n")
        location = sum(_utf16_length(line) + 1 for line in lines[:index])
        self._body.setSelectedRange_(NSMakeRange(location, 1))
        self._body.setNeedsDisplay_(True)
        self.focus_body()

    def _emit_body_change(self) -> None:
        if not self._loading:
            self._on_body(self.body_text())
