"""Transcript section shown beneath the note body.

Read-only in Phase 3: renders existing ``TranscriptBlock`` entries with
monospace timestamps in a visually separate native card. It is deliberately
*separate* from the editable body — transcript text is never merged into the
note body. Actual appending is wired in Phase 4.
"""

from __future__ import annotations

from AppKit import (
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSMutableParagraphStyle,
    NSNoBorder,
    NSParagraphStyleAttributeName,
    NSScrollView,
    NSTextView,
)
from Foundation import NSAttributedString, NSMutableAttributedString

from ..models import TranscriptBlock
from .controls import flipped_view, label, solid_view
from .layout import add, pin_edges, set_height
from .palette import Palette, mono_font


class TranscriptSection:
    """A bordered, read-only transcript card. Hidden when there are no blocks."""

    SECTION_HEIGHT = 176.0

    def __init__(self, palette: Palette) -> None:
        self.palette = palette
        self.view = solid_view(palette.transcript_background)
        self.view.layer().setCornerRadius_(14.0)
        self.view.layer().setBorderWidth_(1.0)
        self.view.layer().setBorderColor_(palette.border.CGColor())

        header = add(self.view, flipped_view())
        pin_edges(header, self.view, top=0, leading=0, trailing=0, bottom=None)
        set_height(header, 40)
        title = add(
            header, label("Transcript", NSFont.boldSystemFontOfSize_(13), palette.text_primary)
        )
        pin_edges(title, header, top=13, leading=16, trailing=16, bottom=None)

        scroll = add(self.view, NSScrollView.alloc().init())
        scroll.setDrawsBackground_(False)
        scroll.setBorderType_(NSNoBorder)
        scroll.setHasVerticalScroller_(True)
        pin_edges(scroll, self.view, top=40, leading=8, trailing=8, bottom=10)

        text = NSTextView.alloc().init()
        text.setEditable_(False)
        text.setSelectable_(True)
        text.setDrawsBackground_(False)
        text.setTextContainerInset_((8.0, 6.0))
        scroll.setDocumentView_(text)
        self._text = text

    def set_blocks(self, blocks: list[TranscriptBlock]) -> bool:
        """Render blocks. Returns True if the section has content to show."""
        p = self.palette
        result = NSMutableAttributedString.alloc().init()

        para = NSMutableParagraphStyle.alloc().init()
        para.setLineSpacing_(3.0)
        para.setParagraphSpacing_(10.0)

        ts_attrs = {
            NSFontAttributeName: mono_font(12.0),
            NSForegroundColorAttributeName: p.accent_strong,
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
        self._text.setTextColor_(p.text_secondary)
        has_content = len(blocks) > 0
        self.view.setHidden_(not has_content)
        return has_content
