"""Sidebar view: brand header, search, category navigation, privacy footer.

Native AppKit views wired to a controller. Colors come from the palette; the
official logo image is passed in untouched. Library rows use SF Symbols, a
themed selected pill/border, and a hover state.
"""

from __future__ import annotations

from collections.abc import Callable

import objc
from AppKit import (
    NSColor,
    NSFont,
    NSImageScaleProportionallyUpOrDown,
    NSImageView,
    NSSearchField,
    NSTrackingActiveInKeyWindow,
    NSTrackingArea,
    NSTrackingInVisibleRect,
    NSTrackingMouseEnteredAndExited,
)
from Foundation import NSMakeRect

from ..models import ALL_NOTES, CATEGORIES
from .controls import FlippedView, flipped_view, icon_view, label, rounded_view, solid_view
from .layout import add, pin_edges, set_height, set_width
from .palette import Palette, symbol_image

_ROWS: tuple[str, ...] = (ALL_NOTES, *CATEGORIES)
_ICONS: dict[str, str] = {
    ALL_NOTES: "square.grid.2x2",
    "Ideas": "lightbulb",
    "Sessions": "waveform",
    "Drafts": "pencil.line",
}
_TRACKING_OPTS = (
    NSTrackingMouseEnteredAndExited | NSTrackingActiveInKeyWindow | NSTrackingInVisibleRect
)


class CategoryRow(FlippedView):
    """A clickable category row (icon + name + count) with selected/hover states."""

    def initWithCategory_(self, category):  # noqa: N802
        self = objc.super(CategoryRow, self).init()
        if self is None:
            return None
        self._category = category
        self._selected = False
        self._palette: Palette | None = None
        self.on_select: Callable[[str], None] | None = None
        area = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
            NSMakeRect(0, 0, 0, 0), _TRACKING_OPTS, self, None
        )
        self.addTrackingArea_(area)
        return self

    def mouseDown_(self, event):  # noqa: N802
        if self.on_select is not None:
            self.on_select(self._category)

    def mouseEntered_(self, event):  # noqa: N802
        if not self._selected and self._palette is not None:
            self.setBackgroundColor_(self._palette.hover_background)

    def mouseExited_(self, event):  # noqa: N802
        if not self._selected and self._palette is not None:
            self.setBackgroundColor_(NSColor.clearColor())

    def set_selected(self, selected: bool, palette: Palette) -> None:
        self._selected = selected
        self._palette = palette
        self.setBackgroundColor_(palette.selected_background if selected else NSColor.clearColor())
        self.layer().setBorderWidth_(1.0 if selected else 0.0)
        self.layer().setBorderColor_(
            palette.selected_border.CGColor() if selected else NSColor.clearColor().CGColor()
        )
        self._name.setTextColor_(palette.text_primary if selected else palette.text_secondary)
        self._count.setTextColor_(palette.text_secondary if selected else palette.text_muted)
        self._icon.setContentTintColor_(palette.accent_strong if selected else palette.text_muted)


class Sidebar:
    """Owns the sidebar view tree and exposes update hooks."""

    def __init__(
        self,
        palette: Palette,
        logo_image,
        *,
        on_category: Callable[[str], None],
        search_delegate,
    ) -> None:
        self.palette = palette
        self.view = solid_view(palette.sidebar_background)
        self._rows: dict[str, CategoryRow] = {}
        self._counts: dict[str, object] = {}
        self._on_category = on_category
        self.search_field = self._build(logo_image, search_delegate)

    def _build(self, logo_image, search_delegate) -> NSSearchField:
        p = self.palette
        header = add(self.view, flipped_view())
        pin_edges(header, self.view, top=52, leading=16, trailing=14, bottom=None)
        set_height(header, 40)

        logo = add(header, NSImageView.alloc().init())
        if logo_image is not None:
            logo.setImage_(logo_image)
        logo.setImageScaling_(NSImageScaleProportionallyUpOrDown)
        logo.setWantsLayer_(True)
        if logo.layer() is not None:
            logo.layer().setCornerRadius_(9.0)
            logo.layer().setMasksToBounds_(True)
        pin_edges(logo, header, top=2, leading=0, trailing=None, bottom=None)
        set_width(logo, 34)
        set_height(logo, 34)

        name = add(header, label("StormPad", NSFont.boldSystemFontOfSize_(16), p.text_primary))
        pin_edges(name, header, top=0, leading=46, trailing=0, bottom=None)
        tagline = add(
            header,
            label("Capture ideas as they happen", NSFont.systemFontOfSize_(10.5), p.text_muted),
        )
        pin_edges(tagline, header, top=20, leading=46, trailing=0, bottom=None)

        search = add(self.view, NSSearchField.alloc().init())
        search.setDelegate_(search_delegate)
        search.setPlaceholderString_("Search notes")
        search.setFont_(NSFont.systemFontOfSize_(13))
        search.setSendsSearchStringImmediately_(True)
        search.setSendsWholeSearchString_(False)
        pin_edges(search, self.view, top=104, leading=14, trailing=14, bottom=None)
        set_height(search, 30)

        lib = add(self.view, label("LIBRARY", NSFont.systemFontOfSize_(10.5), p.text_muted))
        pin_edges(lib, self.view, top=150, leading=20, trailing=14, bottom=None)

        y = 172.0
        for category in _ROWS:
            row = CategoryRow.alloc().initWithCategory_(category)
            row.on_select = self._on_category
            add(self.view, row)
            row.setWantsLayer_(True)
            row.layer().setCornerRadius_(8.0)
            pin_edges(row, self.view, top=y, leading=10, trailing=10, bottom=None)
            set_height(row, 34)

            icon = add(
                row, icon_view(symbol_image(_ICONS.get(category, "circle"), size=13), p.text_muted)
            )
            pin_edges(icon, row, top=9, leading=12, trailing=None, bottom=None)
            set_width(icon, 17)
            set_height(icon, 16)
            title = add(row, label(category, NSFont.systemFontOfSize_(13.5), p.text_secondary))
            pin_edges(title, row, top=8, leading=38, trailing=None, bottom=None)
            count = add(row, label("0", NSFont.systemFontOfSize_(11.5), p.text_muted))
            pin_edges(count, row, top=8, leading=None, trailing=12, bottom=None)

            row._icon = icon
            row._name = title
            row._count = count
            self._rows[category] = row
            self._counts[category] = count
            y += 38

        # Privacy footer (non-interactive).
        footer = add(
            self.view,
            rounded_view(
                p.privacy_background, 10.0, border_color=p.privacy_border, border_width=1.0
            ),
        )
        pin_edges(footer, self.view, top=None, leading=14, trailing=14, bottom=16)
        set_height(footer, 52)
        shield = add(footer, icon_view(symbol_image("checkmark.shield", size=15), p.accent_strong))
        pin_edges(shield, footer, top=17, leading=12, trailing=None, bottom=None)
        set_width(shield, 20)
        set_height(shield, 18)
        f_title = add(
            footer,
            label("Local-first & private", NSFont.boldSystemFontOfSize_(12), p.text_secondary),
        )
        pin_edges(f_title, footer, top=10, leading=40, trailing=12, bottom=None)
        f_sub = add(
            footer,
            label("Everything stays on this Mac", NSFont.systemFontOfSize_(10.5), p.text_muted),
        )
        pin_edges(f_sub, footer, top=28, leading=40, trailing=12, bottom=None)

        self.set_active_category(ALL_NOTES)
        return search

    def set_active_category(self, category: str) -> None:
        for cat, row in self._rows.items():
            row.set_selected(cat == category, self.palette)

    def set_counts(self, counts: dict[str, int]) -> None:
        for cat, view in self._counts.items():
            view.setStringValue_(str(counts.get(cat, 0)))

    def search_string(self) -> str:
        return str(self.search_field.stringValue())

    def clear_search(self) -> None:
        self.search_field.setStringValue_("")
