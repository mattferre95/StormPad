"""Native page-like block editor built on AppKit's text system.

The title is a native text field and body blocks live in one rich NSTextView.
Paragraph attributes carry block semantics; inline attributes carry formatting
semantics. Markdown conversion remains in the AppKit-free parser/serializer.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import objc
from AppKit import (
    NSAlert,
    NSAttributedString,
    NSBackgroundColorAttributeName,
    NSBezierPath,
    NSBoldFontMask,
    NSButton,
    NSColor,
    NSDraggingItem,
    NSDragOperationCopy,
    NSDragOperationMove,
    NSEventModifierFlagOption,
    NSFilenamesPboardType,
    NSFont,
    NSFontAttributeName,
    NSFontManager,
    NSForegroundColorAttributeName,
    NSImage,
    NSImageOnly,
    NSItalicFontMask,
    NSLinkAttributeName,
    NSMenu,
    NSMenuItem,
    NSMutableAttributedString,
    NSMutableParagraphStyle,
    NSNoBorder,
    NSParagraphStyleAttributeName,
    NSPasteboardItem,
    NSScrollerStyleOverlay,
    NSScrollView,
    NSTextAttachment,
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
from Foundation import NSURL, NSMakeRange, NSMakeRect, NSMakeSize, NSObject

from .. import attachments
from ..block_parser import parse_blocks
from ..block_serializer import serialize_blocks
from ..blocks import (
    COLOR_TOKENS,
    Block,
    BlockType,
    InlineMark,
    InlineRun,
    MarkType,
    apply_block_command,
    backspace_empty_result,
    empty_return_result,
    insert_block,
    next_block_after_return,
    reorder_blocks,
    split_runs,
    toggle_todo,
)
from ..models import Note, move_transcript_chunk, remove_transcript_chunk
from ..uihelpers import (
    SaveStatus,
    block_gutter_canvas_y,
    block_gutter_layout,
    block_index_for_location,
    formatting_toolbar_visible,
    gutter_hover_hit,
    title_command_focus,
    title_display_text,
)
from .controls import FlippedView, label, rounded_view, solid_view
from .layout import add, pin_edges, set_height, set_width
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
_ZERO_WIDTH = "\u200b"
_LINE_SEPARATOR = "\u2028"
_BLOCK_DRAG_TYPE = "com.stormpad.block-index"

_BODY_INSET = 92.0
_BLOCK_MENU: tuple[tuple[str, BlockType, str], ...] = (
    ("Text", BlockType.TEXT, "text.alignleft"),
    ("Heading 1", BlockType.HEADING_1, "textformat.size.larger"),
    ("Heading 2", BlockType.HEADING_2, "textformat.size"),
    ("Heading 3", BlockType.HEADING_3, "textformat"),
    ("To-do", BlockType.TODO, "checkmark.square"),
    ("Bulleted List", BlockType.BULLET, "list.bullet"),
    ("Numbered List", BlockType.NUMBERED, "list.number"),
    ("Quote", BlockType.QUOTE, "quote.opening"),
    ("Divider", BlockType.DIVIDER, "minus"),
    ("Link", BlockType.LINK, "link"),
    ("Image", BlockType.IMAGE, "photo"),
    ("File", BlockType.FILE, "doc"),
    ("Transcript", BlockType.TRANSCRIPT, "waveform"),
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
            NSTrackingMouseEnteredAndExited
            | NSTrackingActiveInKeyWindow
            | NSTrackingInVisibleRect
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


class BlockDragButton(GutterButton):
    """Gutter handle that starts a native AppKit drag session."""

    def mouseDown_(self, event):  # noqa: N802
        editor = getattr(self, "stormpad_editor", None)
        if editor is None or not editor.begin_block_drag(event, self):
            objc.super(BlockDragButton, self).mouseDown_(event)


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
            point = self.stormpad_editor.view.convertPoint_fromView_(
                event.locationInWindow(), None
            )
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


class BlockTextView(NSTextView):
    """NSTextView with local file-drop and to-do click handling."""

    def draggingEntered_(self, sender):  # noqa: N802
        pasteboard = sender.draggingPasteboard()
        editor = getattr(self, "stormpad_editor", None)
        if pasteboard.stringForType_(_BLOCK_DRAG_TYPE) is not None:
            if editor is not None:
                editor.update_block_drag_destination(sender)
            return NSDragOperationMove
        files = pasteboard.propertyListForType_(NSFilenamesPboardType)
        return NSDragOperationCopy if files else 0

    def draggingUpdated_(self, sender):  # noqa: N802
        pasteboard = sender.draggingPasteboard()
        if pasteboard.stringForType_(_BLOCK_DRAG_TYPE) is not None:
            editor = getattr(self, "stormpad_editor", None)
            if editor is not None:
                editor.update_block_drag_destination(sender)
            return NSDragOperationMove
        return self.draggingEntered_(sender)

    def draggingExited_(self, sender):  # noqa: N802
        editor = getattr(self, "stormpad_editor", None)
        if editor is not None:
            editor.end_block_drag()

    def performDragOperation_(self, sender):  # noqa: N802
        pasteboard = sender.draggingPasteboard()
        editor = getattr(self, "stormpad_editor", None)
        if pasteboard.stringForType_(_BLOCK_DRAG_TYPE) is not None:
            return bool(editor and editor.perform_block_drop(sender))
        files = pasteboard.propertyListForType_(NSFilenamesPboardType) or []
        return bool(editor and editor.handle_dropped_files([Path(str(item)) for item in files]))

    def mouseDown_(self, event):  # noqa: N802
        editor = getattr(self, "stormpad_editor", None)
        if editor is not None:
            point = self.convertPoint_fromView_(event.locationInWindow(), None)
            try:
                index = self.characterIndexForInsertionAtPoint_(point)
                attrs = self.textStorage().attributesAtIndex_effectiveRange_(index, None)[0]
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
                if (
                    attrs.get(_ATTR_BLOCK) == BlockType.FILE.value
                    and int(event.clickCount()) >= 2
                ):
                    self.setSelectedRange_(NSMakeRange(index, 0))
                    editor.openAttachment_(None)
                    return
            except (IndexError, TypeError, ValueError):
                pass
        objc.super(BlockTextView, self).mouseDown_(event)

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
        self._drag_source_index: int | None = None
        self._drag_insertion_index: int | None = None
        self._context_block_index: int | None = None
        self._context_transcript_chunk: int | None = None
        self._block_controls_enabled = True
        self._block_menu = None
        self._color_menu = None
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

        self._status = add(
            self.view, label("", NSFont.systemFontOfSize_(11), p.text_muted)
        )
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
        pin_edges(title, self.view, top=44, leading=_BODY_INSET, trailing=_BODY_INSET, bottom=None)
        set_height(title, 48)
        self._title = title

        scroll = add(self.view, NSScrollView.alloc().init())
        scroll.setDrawsBackground_(False)
        scroll.setBorderType_(NSNoBorder)
        scroll.setHasVerticalScroller_(True)
        scroll.setAutohidesScrollers_(True)
        if hasattr(scroll, "setScrollerStyle_"):
            scroll.setScrollerStyle_(NSScrollerStyleOverlay)
        pin_edges(scroll, self.view, top=102, leading=52, trailing=52, bottom=18)

        body = BlockTextView.alloc().initWithFrame_(NSMakeRect(0, 0, 500, 500))
        body.stormpad_editor = self
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
        body.registerForDraggedTypes_([NSFilenamesPboardType, _BLOCK_DRAG_TYPE])
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

        self._plus = self._overlay_button(
            "+", "showBlockMenu:", "Add Block", symbol="plus"
        )
        self._handle = self._overlay_button(
            "", None, "Drag Block", symbol="line.3.horizontal", drag=True
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
        self._handle.setFrame_(
            NSMakeRect(
                initial.drag.x,
                initial.drag.y,
                initial.drag.width,
                initial.drag.height,
            )
        )
        self._set_gutter_hidden(True)

        self._drag_indicator = solid_view(p.accent_strong)
        self._drag_indicator.setFrame_(NSMakeRect(24, 118, 68, 2))
        self.view.addSubview_(self._drag_indicator)
        self._drag_indicator.setHidden_(True)

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
        drag: bool = False,
    ) -> NSButton:
        p = self._palette
        button = (
            BlockDragButton.alloc().init()
            if drag
            else GutterButton.alloc().init()
        )
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
        if drag:
            button.stormpad_editor = self
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
            button = NSButton.alloc().initWithFrame_(
                NSMakeRect(index * width + 6, 4, 28, 24)
            )
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
        self._loading = True
        try:
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
            (
                block
                for block in self._extract_blocks()
                if block.kind == BlockType.TRANSCRIPT
            ),
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
        for index, block in enumerate(blocks or [Block()]):
            if index:
                previous_attrs = self._block_base_attributes(block)
                result.appendAttributedString_(
                    NSAttributedString.alloc().initWithString_attributes_(
                        "\n", previous_attrs
                    )
                )
            result.appendAttributedString_(self._attributed_block(block))
        was_loading = self._loading
        self._loading = True
        try:
            storage.setAttributedString_(result)
        finally:
            self._loading = was_loading
        if focus_index is not None:
            self._select_block(focus_index)
            self.focus_body()
        self._emit_body_change()

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
        finally:
            self._loading = False
        self._emit_body_change()

    def _attributed_block(self, block: Block) -> NSMutableAttributedString:
        attrs = self._block_base_attributes(block)
        result = NSMutableAttributedString.alloc().init()

        prefix = ""
        decoration = None
        if block.kind == BlockType.TODO:
            prefix, decoration = ("☑ " if block.checked else "☐ "), "todo"
        elif block.kind == BlockType.BULLET:
            prefix, decoration = "• ", "prefix"
        elif block.kind == BlockType.NUMBERED:
            prefix, decoration = "1. ", "prefix"
        elif block.kind == BlockType.QUOTE:
            prefix, decoration = "❝ ", "prefix"
        elif block.kind == BlockType.FILE:
            prefix, decoration = "📎 ", "prefix"
        if prefix:
            prefix_attrs = dict(attrs)
            prefix_attrs[_ATTR_DECORATION] = decoration
            result.appendAttributedString_(
                NSAttributedString.alloc().initWithString_attributes_(
                    prefix, prefix_attrs
                )
            )

        if block.kind == BlockType.DIVIDER:
            divider_attrs = dict(attrs)
            divider_attrs[_ATTR_DECORATION] = "divider"
            divider_attrs[_ATTR_READ_ONLY] = True
            divider_attrs[NSForegroundColorAttributeName] = self._palette.divider_line
            result.appendAttributedString_(
                NSAttributedString.alloc().initWithString_attributes_(
                    "────────────────────────", divider_attrs
                )
            )
            return result

        if block.kind == BlockType.RAW:
            raw_attrs = dict(attrs)
            raw_attrs[_ATTR_DECORATION] = "raw"
            raw_attrs[_ATTR_READ_ONLY] = True
            raw_attrs[NSFontAttributeName] = NSFont.monospacedSystemFontOfSize_weight_(
                12.5, 0.0
            )
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
            transcript_attrs[NSBackgroundColorAttributeName] = (
                self._palette.transcript_background
            )
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
                        chunk_attrs[NSForegroundColorAttributeName] = (
                            self._palette.text_secondary
                        )
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
                    append_attrs[NSFontAttributeName] = NSFont.boldSystemFontOfSize_(
                        12.5
                    )
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
            attachment = self._image_attachment(block.target)
            if attachment is not None:
                image_string = NSAttributedString.attributedStringWithAttachment_(
                    attachment
                ).mutableCopy()
                image_string.addAttributes_range_(
                    {**attrs, _ATTR_DECORATION: "image", _ATTR_READ_ONLY: True},
                    NSMakeRange(0, image_string.length()),
                )
                result.appendAttributedString_(image_string)
                result.appendAttributedString_(
                    NSAttributedString.alloc().initWithString_attributes_("  ", attrs)
                )

        for run in block.runs:
            run_attrs = self._inline_attributes(attrs, run)
            result.appendAttributedString_(
                NSAttributedString.alloc().initWithString_attributes_(
                    run.text, run_attrs
                )
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
                NSAttributedString.alloc().initWithString_attributes_(
                    _ZERO_WIDTH, attrs
                )
            )
        return result

    def _image_attachment(self, relative: str):
        if self._current is None:
            return None
        path = (self._current.path.parent / relative).resolve()
        image = NSImage.alloc().initWithContentsOfFile_(str(path))
        if image is None:
            return None
        size = image.size()
        if size.width > 520:
            ratio = 520.0 / size.width
            image.setSize_(NSMakeSize(520.0, max(1.0, size.height * ratio)))
        attachment = NSTextAttachment.alloc().init()
        if hasattr(attachment, "setImage_"):
            attachment.setImage_(image)
        elif attachment.attachmentCell() is not None:
            attachment.attachmentCell().setImage_(image)
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
        paragraph.setLineHeightMultiple_(1.35)
        paragraph.setParagraphSpacingBefore_(3.0)
        paragraph.setParagraphSpacing_(12.0)
        paragraph.setHeadIndent_(float(block.indent) * 20.0)
        paragraph.setFirstLineHeadIndent_(float(block.indent) * 20.0)
        if block.kind == BlockType.QUOTE:
            paragraph.setHeadIndent_(18.0)
            paragraph.setFirstLineHeadIndent_(18.0)
        size = {
            BlockType.HEADING_1: 26.0,
            BlockType.HEADING_2: 22.0,
            BlockType.HEADING_3: 19.0,
        }.get(block.kind, 16.5)
        font = serif_font(size)
        if block.kind in (
            BlockType.HEADING_1,
            BlockType.HEADING_2,
            BlockType.HEADING_3,
        ):
            font = NSFontManager.sharedFontManager().convertFont_toHaveTrait_(
                font, NSBoldFontMask
            )
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
                attrs[NSBackgroundColorAttributeName] = self._semantic_color(
                    mark.value, alpha=0.28
                )
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
            attrs[NSFontAttributeName] = (
                NSFontManager.sharedFontManager().convertFont_toHaveTrait_(
                    font, traits
                )
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
                blocks.append(
                    Block(kind=kind, raw=str(attrs.get(_ATTR_RAW) or ""))
                )
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
        attrs = self._body.textStorage().attributesAtIndex_effectiveRange_(
            probe, None
        )[0]
        return bool(attrs.get(attribute))

    @objc.python_method
    def restore_selection(self, selection: tuple[int, int]) -> None:
        length = self._body.string().length()
        location = min(max(selection[0], 0), length)
        span = min(max(selection[1], 0), length - location)
        self._body.setSelectedRange_(NSMakeRange(location, span))

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

    def _set_gutter_hidden(self, hidden: bool) -> None:
        should_hide = hidden or not self._block_controls_enabled
        self._plus.setHidden_(should_hide)
        self._handle.setHidden_(should_hide)

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
        used = self._body.layoutManager().usedRectForTextContainer_(
            self._body.textContainer()
        )
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
            visible_bottom = (
                float(scroll_frame.origin.y) + float(scroll_frame.size.height) - 32.0
            )
            on_screen = visible_top <= y <= visible_bottom
            self._set_gutter_hidden(not on_screen)
            if not on_screen:
                return
            geometry = block_gutter_layout(
                _BODY_INSET, y - float(self._gutter_hover.frame().origin.y)
            )
            self._plus.setFrameOrigin_((geometry.add.x, geometry.add.y))
            self._handle.setFrameOrigin_((geometry.drag.x, geometry.drag.y))
        except (AttributeError, TypeError, ValueError):
            self._set_gutter_hidden(True)

    # -- block actions ------------------------------------------------------

    @objc.IBAction
    def showBlockMenu_(self, sender):  # noqa: N802
        blocks = self._extract_blocks()
        self._command_block_index = min(
            self._hovered_block_index
            if self._hovered_block_index is not None
            else self._current_block_index(),
            len(blocks) - 1,
        )
        event = self.view.window().currentEvent()
        self._command_option_pressed = bool(
            event is not None
            and int(event.modifierFlags()) & int(NSEventModifierFlagOption)
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
    def chooseBlockType_(self, sender):  # noqa: N802
        kind = BlockType(str(sender.representedObject()))
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
        self._command_block_index = None

    @objc.python_method
    def _block_title(self, kind: BlockType) -> str:
        return next(
            (title for title, candidate, _symbol in _BLOCK_MENU if candidate == kind),
            "Block",
        )

    @objc.python_method
    def begin_block_drag(self, event, source_view) -> bool:
        """Start an internal native drag from the hovered block handle."""
        if self._hovered_block_index is None or self._current is None:
            return False
        self._drag_source_index = self._hovered_block_index
        pasteboard_item = NSPasteboardItem.alloc().init()
        pasteboard_item.setString_forType_(
            str(self._drag_source_index), _BLOCK_DRAG_TYPE
        )
        dragging_item = NSDraggingItem.alloc().initWithPasteboardWriter_(
            pasteboard_item
        )
        image = symbol_image("line.3.horizontal", size=14, weight="semibold")
        dragging_item.setDraggingFrame_contents_(source_view.bounds(), image)
        source_view.beginDraggingSessionWithItems_event_source_(
            [dragging_item], event, self
        )
        return True

    def draggingSession_sourceOperationMaskForDraggingContext_(  # noqa: N802
        self, session, context
    ):
        return NSDragOperationMove

    def draggingSession_endedAtPoint_operation_(  # noqa: N802
        self, session, point, operation
    ):
        self.end_block_drag()

    @objc.python_method
    def update_block_drag_destination(self, sender) -> None:
        """Resolve a drag location to a before/after block boundary."""
        if self._drag_source_index is None:
            return
        point = self._body.convertPoint_fromView_(sender.draggingLocation(), None)
        location = int(self._body.characterIndexForInsertionAtPoint_(point))
        native = str(self._body.string())
        native_lines = native.split("\n")
        index = min(
            block_index_for_location(native, location),
            max(0, len(native_lines) - 1),
        )
        line_location = sum(
            _utf16_length(line) + 1 for line in native_lines[:index]
        )
        rect = self._glyph_rect_for_location(line_location)
        insertion = index + (
            1
            if rect is not None and float(point.y) > float(rect.origin.y + rect.size.height / 2)
            else 0
        )
        self._drag_insertion_index = insertion
        self._position_drag_indicator(insertion)

    @objc.python_method
    def _glyph_rect_for_location(self, location: int):
        if self._body.textStorage().length() == 0:
            return None
        location = min(max(location, 0), self._body.textStorage().length() - 1)
        layout = self._body.layoutManager()
        glyph = layout.glyphRangeForCharacterRange_actualCharacterRange_(
            NSMakeRange(location, 0), None
        )
        if isinstance(glyph, tuple):
            glyph = glyph[0]
        return layout.boundingRectForGlyphRange_inTextContainer_(
            glyph, self._body.textContainer()
        )

    @objc.python_method
    def _position_drag_indicator(self, insertion: int) -> None:
        native_lines = str(self._body.string()).split("\n")
        if not native_lines:
            return
        probe_index = min(max(insertion, 0), len(native_lines) - 1)
        location = sum(
            _utf16_length(line) + 1 for line in native_lines[:probe_index]
        )
        rect = self._glyph_rect_for_location(location)
        if rect is None:
            return
        visible = self._body.visibleRect()
        scroll_frame = self._scroll.frame()
        inset = self._body.textContainerInset()
        y = (
            float(scroll_frame.origin.y)
            + float(inset.height)
            + float(rect.origin.y)
            - float(visible.origin.y)
        )
        if insertion >= len(native_lines):
            y += float(rect.size.height)
        width = max(20.0, float(self.view.bounds().size.width) - _BODY_INSET * 2)
        self._drag_indicator.setFrame_(NSMakeRect(_BODY_INSET, y, width, 2.0))
        self._drag_indicator.setHidden_(False)

    @objc.python_method
    def perform_block_drop(self, sender) -> bool:
        payload = sender.draggingPasteboard().stringForType_(_BLOCK_DRAG_TYPE)
        if payload is None or self._drag_insertion_index is None:
            self.end_block_drag()
            return False
        try:
            source = int(str(payload))
        except ValueError:
            self.end_block_drag()
            return False
        blocks, destination = reorder_blocks(
            self._extract_blocks(), source, self._drag_insertion_index
        )
        self._replace_document(blocks, register_undo=True, focus_index=destination)
        self.flash_status("Block moved")
        self.end_block_drag()
        return True

    @objc.python_method
    def end_block_drag(self) -> None:
        self._drag_source_index = None
        self._drag_insertion_index = None
        self._drag_indicator.setHidden_(True)

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

    def handle_dropped_files(self, files: list[Path]) -> bool:
        inserted = False
        for path in files:
            kind = BlockType.IMAGE if path.suffix.lower() in {
                ".png",
                ".jpg",
                ".jpeg",
                ".gif",
                ".heic",
                ".tif",
                ".tiff",
                ".webp",
            } else BlockType.FILE
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
                Block(
                    kind=BlockType(
                        str(attrs.get(_ATTR_BLOCK, BlockType.TEXT.value))
                    )
                )
            )[NSFontAttributeName]
            traits = 0
            if attrs.get(_ATTR_BOLD):
                traits |= NSBoldFontMask
            if attrs.get(_ATTR_ITALIC):
                traits |= NSItalicFontMask
            font = (
                NSFontManager.sharedFontManager().convertFont_toHaveTrait_(
                    base, traits
                )
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
        menu = NSMenu.alloc().initWithTitle_("Color")
        selected_token = self.selected_color_token(mode)
        for token in COLOR_TOKENS:
            title = token.replace("_", " ").title()
            swatch = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "      ", "chooseColor:", ""
            )
            swatch.setTarget_(self)
            swatch.setRepresentedObject_(f"{mode}:{token}")
            swatch.setImage_(
                self._color_swatch_image(
                    token, mode, selected=token == selected_token
                )
            )
            swatch.setToolTip_(f"{mode.title()} color {title}")
            swatch.setAccessibilityLabel_(f"{mode.title()} color {title}")
            if token == selected_token:
                swatch.setState_(1)
            menu.addItem_(swatch)
        self._color_menu = menu
        menu.popUpMenuPositioningItem_atLocation_inView_(None, (0.0, 0.0), sender)

    @objc.python_method
    def _color_swatch_image(self, token: str, mode: str, *, selected: bool = False):
        image = NSImage.alloc().initWithSize_(NSMakeSize(16.0, 16.0))
        image.lockFocus()
        rect = NSMakeRect(2.0, 2.0, 12.0, 12.0)
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            rect, 3.0, 3.0
        )
        color = (
            self._palette.formatting_background
            if token == "default"
            else self._semantic_color(token)
        )
        color.colorWithAlphaComponent_(0.45 if mode == "highlight" else 1.0).setFill()
        path.fill()
        (
            self._palette.accent_strong
            if selected
            else self._palette.formatting_border
        ).setStroke()
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
        probe = min(int(selected.location), self._body.textStorage().length() - 1)
        attrs = self._body.textStorage().attributesAtIndex_effectiveRange_(
            probe, None
        )[0]
        token = str(attrs.get(semantic) or "default")
        return token if token in COLOR_TOKENS else "default"

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
            NSForegroundColorAttributeName
            if mode == "text"
            else NSBackgroundColorAttributeName
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
            storage.removeAttribute_range_(native, selected)
        else:
            storage.addAttribute_value_range_(semantic, token, selected)
            storage.addAttribute_value_range_(
                native,
                self._semantic_color(
                    token, alpha=1.0 if mode == "text" else 0.28
                ),
                selected,
            )
        self._emit_body_change()
        if self._color_menu is not None:
            self._color_menu.cancelTracking()

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
        self._emit_body_change()

    # -- status -------------------------------------------------------------

    @objc.python_method
    def set_status(self, status: SaveStatus) -> None:
        self._last_status = status
        self._status.setStringValue_(status.value)
        self._status.setTextColor_(
            self._palette.destructive
            if status == SaveStatus.FAILED
            else self._palette.text_muted
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
            self._on_title(self.title_text())

    def controlTextDidEndEditing_(self, notification):  # noqa: N802
        if not self._loading:
            self._on_title(self.title_text())

    def textDidBeginEditing_(self, notification):  # noqa: N802
        pass

    def textDidEndEditing_(self, notification):  # noqa: N802
        self._formatting.setHidden_(True)

    def control_textView_doCommandBySelector_(  # noqa: N802
        self, control, text_view, selector
    ):
        if (
            control is self._title
            and title_command_focus(str(selector)) == "body"
        ):
            self._on_title(self.title_text())
            self.focus_body()
            self._select_block(0)
            return True
        return False

    def textDidChange_(self, notification):  # noqa: N802
        if not self._loading:
            self._emit_body_change()

    def textViewDidChangeSelection_(self, notification):  # noqa: N802
        selected = self._body.selectedRange()
        show_formatting = formatting_toolbar_visible(
            selection_length=int(selected.length),
            editor_focused=self.body_is_first_responder(),
        )
        self._formatting.setHidden_(not show_formatting)
        if show_formatting:
            self._position_formatting_toolbar()

    def _position_formatting_toolbar(self) -> None:
        selected = self._body.selectedRange()
        try:
            layout = self._body.layoutManager()
            glyph = layout.glyphRangeForCharacterRange_actualCharacterRange_(
                selected, None
            )
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
        blocks = self._extract_blocks()
        index = min(self._current_block_index(), len(blocks) - 1)
        block = blocks[index]
        if command == "insertNewline:":
            if block.is_empty and block.kind != BlockType.TEXT:
                blocks[index] = empty_return_result(block)
                self._replace_document(blocks, register_undo=True, focus_index=index)
                return True
            selected_location = int(self._body.selectedRange().location)
            native_prefix = str(
                self._body.string().substringWithRange_(
                    NSMakeRange(0, selected_location)
                )
            )
            display_prefix = native_prefix.rsplit("\n", 1)[-1].replace(_ZERO_WIDTH, "")
            decoration = {
                BlockType.TODO: 2,
                BlockType.BULLET: 2,
                BlockType.NUMBERED: 3,
                BlockType.QUOTE: 2,
                BlockType.FILE: 2,
            }.get(block.kind, 0)
            offset = max(0, len(display_prefix) - decoration)
            before, after = split_runs(block.runs, offset)
            blocks[index].runs = before
            next_block = next_block_after_return(block)
            next_block.runs = after
            blocks, destination = insert_block(blocks, index, next_block)
            self._replace_document(
                blocks, register_undo=True, focus_index=destination
            )
            return True
        if command == "deleteBackward:" and block.is_empty and block.kind != BlockType.TEXT:
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

    def textView_shouldChangeTextInRange_replacementString_(  # noqa: N802
        self, text_view, selected, replacement
    ):
        if self._body.textStorage().length() == 0:
            return True
        probe = min(int(selected.location), self._body.textStorage().length() - 1)
        try:
            attrs = self._body.textStorage().attributesAtIndex_effectiveRange_(
                probe, None
            )[0]
            return not bool(attrs.get(_ATTR_READ_ONLY))
        except (IndexError, TypeError, ValueError):
            return True

    def textView_menu_forEvent_atIndex_(  # noqa: N802
        self, text_view, menu, event, index
    ):
        self._context_block_index = block_index_for_location(
            str(self._body.string()), int(index)
        )
        self._context_transcript_chunk = None
        attrs = {}
        if self._body.textStorage().length() > 0:
            probe = min(int(index), self._body.textStorage().length() - 1)
            attrs = self._body.textStorage().attributesAtIndex_effectiveRange_(
                probe, None
            )[0]
        kind = attrs.get(_ATTR_BLOCK)
        if kind in (BlockType.IMAGE.value, BlockType.FILE.value):
            menu.addItem_(NSMenuItem.separatorItem())
            if kind == BlockType.FILE.value:
                open_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    "Open Managed File", "openAttachment:", ""
                )
                open_item.setTarget_(self)
                menu.addItem_(open_item)
            reveal = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Reveal Managed Attachment", "revealAttachment:", ""
            )
            reveal.setTarget_(self)
            menu.addItem_(reveal)
            remove = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Remove Attachment Block", "removeAttachmentBlock:", ""
            )
            remove.setTarget_(self)
            menu.addItem_(remove)
        if kind == BlockType.TRANSCRIPT.value:
            chunk_index = attrs.get(_ATTR_TRANSCRIPT_CHUNK)
            self._context_transcript_chunk = (
                int(chunk_index) if chunk_index is not None else None
            )
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
                move_up = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    "Move Chunk Up", "moveTranscriptChunkUp:", ""
                )
                move_up.setTarget_(self)
                menu.addItem_(move_up)
                move_down = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    "Move Chunk Down", "moveTranscriptChunkDown:", ""
                )
                move_down.setTarget_(self)
                menu.addItem_(move_down)
            menu.addItem_(NSMenuItem.separatorItem())
            move_block_up = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Move Transcript Block Up", "moveTranscriptBlockUp:", ""
            )
            move_block_up.setTarget_(self)
            menu.addItem_(move_block_up)
            move_block_down = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Move Transcript Block Down", "moveTranscriptBlockDown:", ""
            )
            move_block_down.setTarget_(self)
            menu.addItem_(move_block_down)
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
        self._current.transcript = remove_transcript_chunk(
            self._current.transcript, index
        )
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

    def _current_attachment_path(self) -> tuple[Path | None, str | None]:
        if self._current is None:
            return None, None
        blocks = self._extract_blocks()
        index = min(self._current_block_index(), len(blocks) - 1)
        target = blocks[index].target
        if not target:
            return None, None
        resolved = attachments.resolve_managed_path(
            self._current.path,
            target,
            self._current.path.parent,
            self._current.id,
        )
        return resolved, target

    @objc.IBAction
    def openAttachment_(self, sender):  # noqa: N802
        path, _target = self._current_attachment_path()
        if path is not None and path.exists():
            NSWorkspace.sharedWorkspace().openURL_(
                NSURL.fileURLWithPath_(str(path))
            )

    @objc.IBAction
    def revealAttachment_(self, sender):  # noqa: N802
        path, _target = self._current_attachment_path()
        if path is not None and path.exists():
            NSWorkspace.sharedWorkspace().activateFileViewerSelectingURLs_(
                [NSURL.fileURLWithPath_(str(path))]
            )

    @objc.IBAction
    def removeAttachmentBlock_(self, sender):  # noqa: N802
        if self._current is None:
            return
        blocks = self._extract_blocks()
        index = min(self._current_block_index(), len(blocks) - 1)
        block = blocks[index]
        if block.kind not in (BlockType.IMAGE, BlockType.FILE) or not block.target:
            return
        attachments.record_orphan(
            self._current.path.parent,
            self._current.id,
            block.target,
        )
        blocks.pop(index)
        if not blocks:
            blocks = [Block()]
        self._replace_document(
            blocks,
            register_undo=True,
            focus_index=min(index, len(blocks) - 1),
        )

    def _emit_body_change(self) -> None:
        if not self._loading:
            self._on_body(self.body_text())
