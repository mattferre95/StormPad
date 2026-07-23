"""Small shared AppKit control builders.

Thin helpers that keep view modules terse and consistent. All colors/fonts come
from a :class:`~stormpad.views.palette.Palette`, so nothing here hardcodes a
literal color.
"""

from __future__ import annotations

import objc
from AppKit import (
    NSColor,
    NSFont,
    NSLineBreakByTruncatingTail,
    NSLineBreakByWordWrapping,
    NSRectFill,
    NSTextField,
    NSView,
)


class FlippedView(NSView):
    """NSView with a top-left origin and an assignable background color."""

    def init(self):
        self = objc.super(FlippedView, self).init()
        if self is None:
            return None
        self._bg = None
        return self

    def isFlipped(self):  # noqa: N802 (AppKit selector name)
        return True

    def setBackgroundColor_(self, color):  # noqa: N802
        self._bg = color
        self.setWantsLayer_(True)
        if self.layer() is not None and color is not None:
            self.layer().setBackgroundColor_(color.CGColor())

    def backgroundColor(self):  # noqa: N802
        return self._bg

    def drawRect_(self, rect):  # noqa: N802
        if self._bg is not None:
            self._bg.set()
            NSRectFill(self.bounds())


def flipped_view() -> FlippedView:
    """A layer-backed, top-left-origin container view."""
    view = FlippedView.alloc().init()
    view.setWantsLayer_(True)
    return view


def solid_view(color: NSColor) -> FlippedView:
    """A view filled with a solid background color."""
    view = flipped_view()
    view.setBackgroundColor_(color)
    return view


def label(
    text: str,
    font: NSFont,
    color: NSColor,
    *,
    multiline: bool = False,
) -> NSTextField:
    """A non-editable, borderless, transparent text label."""
    field = NSTextField.alloc().init()
    field.setStringValue_(text)
    field.setFont_(font)
    field.setTextColor_(color)
    field.setEditable_(False)
    field.setSelectable_(False)
    field.setBordered_(False)
    field.setDrawsBackground_(False)
    field.setBezeled_(False)
    if multiline:
        field.setUsesSingleLineMode_(False)
        field.cell().setWraps_(True)
        field.cell().setLineBreakMode_(NSLineBreakByWordWrapping)
    else:
        field.setUsesSingleLineMode_(True)
        field.cell().setLineBreakMode_(NSLineBreakByTruncatingTail)
        field.cell().setTruncatesLastVisibleLine_(True)
    return field
