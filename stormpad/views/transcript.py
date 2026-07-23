"""Transcript card shown beneath the note body.

A visually separate, rounded native card: header (waveform icon + "Transcript"
+ a "ready" indicator), the read-only timestamped blocks (monospace timestamps),
and an "Append Test Transcript" action. Read-only text — transcript content is
never merged into the editable body. Fully themed.
"""

from __future__ import annotations

from AppKit import (
    NSButton,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSImageLeft,
    NSMutableParagraphStyle,
    NSNoBorder,
    NSParagraphStyleAttributeName,
    NSScrollView,
    NSTextView,
)
from Foundation import NSAttributedString, NSMutableAttributedString

from ..models import TranscriptBlock
from .controls import flipped_view, icon_view, label, rounded_view
from .layout import add, pin_edges, set_height, set_width
from .palette import Palette, mono_font, symbol_image


class TranscriptSection:
    """A bordered, read-only transcript card (always visible)."""

    SECTION_HEIGHT = 202.0

    def __init__(self, palette: Palette) -> None:
        self.palette = palette
        p = palette
        self.view = rounded_view(
            p.transcript_background, 14.0, border_color=p.transcript_border, border_width=1.0
        )

        # Header: icon + title + readiness indicator.
        header = add(self.view, flipped_view())
        pin_edges(header, self.view, top=0, leading=0, trailing=0, bottom=None)
        set_height(header, 42)
        wave = add(
            header,
            icon_view(symbol_image("waveform", size=13, weight="semibold"), p.accent_strong),
        )
        pin_edges(wave, header, top=14, leading=16, trailing=None, bottom=None)
        set_width(wave, 18)
        set_height(wave, 16)
        title = add(header, label("Transcript", NSFont.boldSystemFontOfSize_(13), p.text_primary))
        pin_edges(title, header, top=13, leading=40, trailing=None, bottom=None)
        dot = add(header, rounded_view(p.accent_strong, 3.0))
        pin_edges(dot, header, top=18, leading=None, trailing=178, bottom=None)
        set_width(dot, 6)
        set_height(dot, 6)
        ready = add(
            header,
            label(
                "Ready for live transcript chunks",
                NSFont.systemFontOfSize_(10.5),
                p.accent_strong,
            ),
        )
        pin_edges(ready, header, top=14, leading=None, trailing=16, bottom=None)

        # Append action (bottom-left).
        self._append = NSButton.alloc().init()
        self._append.setTitle_("Append Test Transcript")
        self._append.setBordered_(False)
        self._append.setWantsLayer_(True)
        self._append.setFont_(NSFont.systemFontOfSize_(12))
        self._append.setContentTintColor_(p.accent_strong)
        img = symbol_image("plus", size=11, weight="semibold")
        if img is not None:
            self._append.setImage_(img)
            self._append.setImagePosition_(NSImageLeft)
        self._append.layer().setCornerRadius_(8.0)
        self._append.layer().setBorderWidth_(1.0)
        self._append.layer().setBorderColor_(p.transcript_border.CGColor())
        self._append.layer().setBackgroundColor_(p.secondary_surface.CGColor())
        add(self.view, self._append)
        pin_edges(self._append, self.view, top=None, leading=16, trailing=None, bottom=12)
        set_height(self._append, 30)
        set_width(self._append, 188)

        # Blocks (read-only).
        scroll = add(self.view, NSScrollView.alloc().init())
        scroll.setDrawsBackground_(False)
        scroll.setBorderType_(NSNoBorder)
        scroll.setHasVerticalScroller_(True)
        pin_edges(scroll, self.view, top=44, leading=8, trailing=8, bottom=52)
        text = NSTextView.alloc().init()
        text.setEditable_(False)
        text.setSelectable_(True)
        text.setDrawsBackground_(False)
        text.setTextContainerInset_((8.0, 6.0))
        scroll.setDocumentView_(text)
        self._text = text

    def set_append_target(self, target, action: str) -> None:
        self._append.setTarget_(target)
        self._append.setAction_(action)

    def set_blocks(self, blocks: list[TranscriptBlock]) -> None:
        """Render the transcript blocks (or an intentional empty state)."""
        p = self.palette
        para = NSMutableParagraphStyle.alloc().init()
        para.setLineSpacing_(3.0)
        para.setParagraphSpacing_(10.0)

        result = NSMutableAttributedString.alloc().init()
        if not blocks:
            result.appendAttributedString_(
                NSAttributedString.alloc().initWithString_attributes_(
                    "No transcript yet — append a timestamped block to get started.",
                    {
                        NSFontAttributeName: NSFont.systemFontOfSize_(12.5),
                        NSForegroundColorAttributeName: p.text_muted,
                        NSParagraphStyleAttributeName: para,
                    },
                )
            )
        else:
            ts_attrs = {
                NSFontAttributeName: mono_font(12.0),
                NSForegroundColorAttributeName: p.timestamp_text,
                NSParagraphStyleAttributeName: para,
            }
            body_attrs = {
                NSFontAttributeName: NSFont.systemFontOfSize_(13.5),
                NSForegroundColorAttributeName: p.text_secondary,
                NSParagraphStyleAttributeName: para,
            }
            for block in blocks:
                result.appendAttributedString_(
                    NSAttributedString.alloc().initWithString_attributes_(
                        f"[{block.timestamp}]\n", ts_attrs
                    )
                )
                result.appendAttributedString_(
                    NSAttributedString.alloc().initWithString_attributes_(
                        f"{block.text}\n\n", body_attrs
                    )
                )
        self._text.textStorage().setAttributedString_(result)
