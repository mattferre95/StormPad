"""Editor view: title, metadata/status header, prose body, transcript section.

A premium native writing surface — normal prose editing, no visible Markdown
syntax. The body is a serif ``NSTextView``; the title is a serif field. Metadata
(created/updated/word count/filename) and save status are shown without exposing
storage syntax. The transcript section renders beneath the body, visually
separate and read-only.
"""

from __future__ import annotations

from collections.abc import Callable

import objc
from AppKit import (
    NSFont,
    NSMenuItem,
    NSMutableParagraphStyle,
    NSNoBorder,
    NSScrollView,
    NSTextField,
    NSTextView,
    NSTimer,
    NSViewHeightSizable,
    NSViewWidthSizable,
)
from Foundation import NSMakeRect, NSMakeSize, NSObject

from ..models import Note, now_local
from ..uihelpers import SaveStatus, format_relative, status_style, word_count
from .controls import icon_view, label, rounded_view, solid_view
from .layout import add, pin_edges, set_height, set_width
from .palette import Palette, mono_font, serif_font, symbol_image
from .transcript import TranscriptSection

_BODY_INSET = 96.0  # horizontal padding matching the design's centered column


class Editor(NSObject):
    """Owns the editor view tree; delegate for the title field and body view."""

    def initWithPalette_onTitle_onBody_(self, palette, on_title, on_body):  # noqa: N802
        self = objc.super(Editor, self).init()
        if self is None:
            return None
        self._palette: Palette = palette
        self._on_title: Callable[[str], None] = on_title
        self._on_body: Callable[[str], None] = on_body
        self._loading = False
        self._current: Note | None = None
        self._last_status = SaveStatus.SAVED
        # Set by the controller; target for the context-menu speech actions.
        self.speech_target = None
        self._build()
        return self

    # -- build ---------------------------------------------------------------

    def _build(self) -> None:
        p = self._palette
        self.view = solid_view(p.editor_background)

        # Status row: save-status pill + filename pill (left), word count (right).
        self._status_pill = add(self.view, rounded_view(p.success_background, 7.0))
        pin_edges(
            self._status_pill, self.view, top=48, leading=_BODY_INSET, trailing=None, bottom=None
        )
        set_height(self._status_pill, 24)
        set_width(self._status_pill, 128)
        self._status_icon = add(
            self._status_pill,
            icon_view(symbol_image("checkmark", size=11, weight="semibold"), p.success),
        )
        pin_edges(
            self._status_icon, self._status_pill, top=6, leading=9, trailing=None, bottom=None
        )
        set_width(self._status_icon, 13)
        set_height(self._status_icon, 12)
        self._status = add(
            self._status_pill, label("Saved locally", NSFont.boldSystemFontOfSize_(11), p.success)
        )
        pin_edges(self._status, self._status_pill, top=5, leading=28, trailing=8, bottom=None)

        self._filename_pill = add(self.view, rounded_view(p.pill_background, 7.0))
        pin_edges(
            self._filename_pill,
            self.view,
            top=48,
            leading=_BODY_INSET + 140,
            trailing=None,
            bottom=None,
        )
        set_height(self._filename_pill, 24)
        set_width(self._filename_pill, 250)
        doc = add(self._filename_pill, icon_view(symbol_image("doc.text", size=11), p.text_muted))
        pin_edges(doc, self._filename_pill, top=6, leading=9, trailing=None, bottom=None)
        set_width(doc, 13)
        set_height(doc, 12)
        self._filename = add(self._filename_pill, label("", mono_font(10.5), p.text_muted))
        pin_edges(self._filename, self._filename_pill, top=5, leading=28, trailing=8, bottom=None)

        self._wordcount = add(self.view, label("", NSFont.systemFontOfSize_(11.5), p.text_muted))
        pin_edges(
            self._wordcount, self.view, top=52, leading=None, trailing=_BODY_INSET, bottom=None
        )

        # Title field (serif, editable).
        title = NSTextField.alloc().init()
        title.setBordered_(False)
        title.setBezeled_(False)
        title.setDrawsBackground_(False)
        title.setFont_(serif_font(30.0))
        title.setTextColor_(p.text_primary)
        title.setPlaceholderString_("Title")
        title.setDelegate_(self)
        title.setFocusRingType_(1)  # none
        add(self.view, title)
        pin_edges(title, self.view, top=80, leading=_BODY_INSET, trailing=_BODY_INSET, bottom=None)
        set_height(title, 44)
        self._title = title

        # Meta row (created / updated).
        self._meta = add(self.view, label("", NSFont.systemFontOfSize_(12), p.text_muted))
        pin_edges(
            self._meta, self.view, top=128, leading=_BODY_INSET, trailing=_BODY_INSET, bottom=None
        )

        # Divider.
        divider = add(self.view, solid_view(p.separator))
        pin_edges(
            divider, self.view, top=154, leading=_BODY_INSET, trailing=_BODY_INSET, bottom=None
        )
        set_height(divider, 1)

        # Transcript card pinned to the bottom (always visible).
        self._transcript = TranscriptSection(p)
        add(self.view, self._transcript.view)
        pin_edges(
            self._transcript.view,
            self.view,
            top=None,
            leading=_BODY_INSET,
            trailing=_BODY_INSET,
            bottom=24,
        )
        set_height(self._transcript.view, TranscriptSection.SECTION_HEIGHT)

        # Body scroll + text view, filling between divider and transcript.
        scroll = add(self.view, NSScrollView.alloc().init())
        scroll.setDrawsBackground_(False)
        scroll.setBorderType_(NSNoBorder)
        scroll.setHasVerticalScroller_(True)
        pin_edges(
            scroll,
            self.view,
            top=170,
            leading=_BODY_INSET - 4,
            trailing=_BODY_INSET - 4,
            bottom=None,
        )
        scroll.bottomAnchor().constraintEqualToAnchor_constant_(
            self._transcript.view.topAnchor(), -18.0
        ).setActive_(True)

        body = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, 200, 400))
        body.setMinSize_(NSMakeSize(0.0, 0.0))
        body.setMaxSize_(NSMakeSize(1.0e7, 1.0e7))
        body.setVerticallyResizable_(True)
        body.setHorizontallyResizable_(False)
        body.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        body.textContainer().setWidthTracksTextView_(True)
        body.setDrawsBackground_(False)
        body.setFont_(serif_font(17.0))
        body.setTextColor_(p.text_primary)
        body.setInsertionPointColor_(p.accent_strong)
        body.setRichText_(False)
        body.setAllowsUndo_(True)
        body.setTextContainerInset_(NSMakeSize(4.0, 8.0))
        body.setDelegate_(self)
        scroll.setDocumentView_(body)
        self._body = body

    # -- public API ----------------------------------------------------------

    @objc.python_method
    def load_note(self, note: Note) -> None:
        """Populate controls from a note without firing edit callbacks."""
        self._loading = True
        try:
            self._current = note
            self._title.setStringValue_(note.title or "")
            self._apply_body_style()
            self._body.setString_(note.body)
            self._apply_body_style()
            self._filename.setStringValue_(note.path.name)
            now = now_local()
            self._meta.setStringValue_(
                f"Created {format_relative(note.created_at, now)}   ·   "
                f"Updated {format_relative(note.updated_at, now)}"
            )
            self._update_word_count()
            self.set_status(SaveStatus.SAVED)
            self._transcript.set_blocks(note.transcript)
            self.view.setHidden_(False)
        finally:
            self._loading = False

    def clear(self) -> None:
        self._current = None
        self.view.setHidden_(True)

    def focus_body(self) -> None:
        self.view.window().makeFirstResponder_(self._body)

    def focus_title(self) -> None:
        self.view.window().makeFirstResponder_(self._title)

    def title_text(self) -> str:
        return str(self._title.stringValue())

    def body_text(self) -> str:
        return str(self._body.string())

    @objc.python_method
    def set_status(self, status: SaveStatus) -> None:
        self._last_status = status
        p = self._palette
        color_token, background_token, symbol = status_style(status)
        color = getattr(p, color_token)
        background = getattr(p, background_token)
        self._status.setStringValue_(status.value)
        self._status.setTextColor_(color)
        self._status_pill.setBackgroundColor_(background)
        image = symbol_image(symbol, size=11, weight="semibold")
        if image is not None:
            self._status_icon.setImage_(image)
        self._status_icon.setContentTintColor_(color)

    @objc.python_method
    def flash_status(self, text: str) -> None:
        """Briefly show a transient status (e.g. 'Copied'), then restore."""
        p = self._palette
        self._status.setStringValue_(text)
        self._status.setTextColor_(p.accent_strong)
        self._status_pill.setBackgroundColor_(p.pill_background)
        image = symbol_image("checkmark.circle", size=11, weight="semibold")
        if image is not None:
            self._status_icon.setImage_(image)
        self._status_icon.setContentTintColor_(p.accent_strong)
        NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
            1.4, False, lambda timer: self.set_status(self._last_status)
        )

    @objc.python_method
    def selected_body_text(self) -> str:
        """The currently selected text in the body (empty string if none)."""
        rng = self._body.selectedRange()
        if rng.length == 0:
            return ""
        return str(self._body.string().substringWithRange_(rng))

    @objc.python_method
    def body_is_first_responder(self) -> bool:
        window = self.view.window()
        return window is not None and window.firstResponder() == self._body

    @objc.python_method
    def body_selected_range(self) -> tuple[int, int]:
        rng = self._body.selectedRange()
        return (int(rng.location), int(rng.length))

    @objc.python_method
    def restore_selection(self, selection: tuple[int, int]) -> None:
        """Reapply a (location, length) selection, clamped to the text length."""
        from Foundation import NSMakeRange

        length = self._body.string().length()
        loc = min(max(selection[0], 0), length)
        span = min(selection[1], length - loc)
        self._body.setSelectedRange_(NSMakeRange(loc, span))

    @objc.python_method
    def set_transcript_append_target(self, target, action: str) -> None:
        self._transcript.set_append_target(target, action)

    # -- helpers -------------------------------------------------------------

    def _apply_body_style(self) -> None:
        para = NSMutableParagraphStyle.alloc().init()
        para.setLineHeightMultiple_(1.5)
        para.setParagraphSpacing_(8.0)
        self._body.setDefaultParagraphStyle_(para)
        self._body.setFont_(serif_font(17.0))
        self._body.setTextColor_(self._palette.text_primary)
        storage = self._body.textStorage()
        if storage.length() > 0:
            from Foundation import NSMakeRange

            full = NSMakeRange(0, storage.length())
            from AppKit import NSParagraphStyleAttributeName

            storage.addAttribute_value_range_(NSParagraphStyleAttributeName, para, full)

    def _update_word_count(self) -> None:
        count = word_count(self.body_text())
        self._wordcount.setStringValue_(f"{count} word{'s' if count != 1 else ''}")

    # -- delegates -----------------------------------------------------------

    def controlTextDidChange_(self, notification):  # noqa: N802 (title field)
        if self._loading:
            return
        self._on_title(self.title_text())

    def textDidChange_(self, notification):  # noqa: N802 (body text view)
        if self._loading:
            return
        self._update_word_count()
        self._on_body(self.body_text())

    def textView_menu_forEvent_atIndex_(self, textView, menu, event, index):  # noqa: N802
        """Augment (not replace) the native context menu with speech actions."""
        if self.speech_target is None:
            return menu
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
