"""Note list column: header + a native table of note rows.

Rows show title, a clean one-line preview, an updated timestamp, and a category
tag. Selection is themed (not the system accent) and drives editor loading.
"""

from __future__ import annotations

from collections.abc import Callable

import objc
from AppKit import (
    NSBezierPath,
    NSButton,
    NSFont,
    NSGraphicsContext,
    NSImageOnly,
    NSInsetRect,
    NSNoBorder,
    NSScrollView,
    NSShadow,
    NSTableColumn,
    NSTableRowView,
    NSTableView,
    NSTableViewSelectionHighlightStyleRegular,
    NSView,
)
from Foundation import NSIndexSet, NSMakeRect, NSObject

from ..models import ALL_NOTES, Note, now_local
from ..uihelpers import format_relative, preview_text
from .controls import FlippedView, flipped_view, label, rounded_view, solid_view
from .layout import add, pin_edges, set_height, set_width
from .palette import Palette, symbol_image


class _ThemedRowView(NSTableRowView):
    """Row view that draws the themed selected-background."""

    def initWithPalette_(self, palette):  # noqa: N802
        self = objc.super(_ThemedRowView, self).init()
        if self is None:
            return None
        self._palette = palette
        return self

    def drawSelectionInRect_(self, rect):  # noqa: N802
        if not self.isSelected():
            return
        p = self._palette
        inset = NSInsetRect(self.bounds(), 8.0, 3.0)
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(inset, 10.0, 10.0)
        glow = p.selection_glow(0.55)
        if glow is not None:
            NSGraphicsContext.saveGraphicsState()
            shadow = NSShadow.alloc().init()
            shadow.setShadowColor_(glow)
            shadow.setShadowBlurRadius_(11.0)
            shadow.setShadowOffset_((0.0, 0.0))
            shadow.set()
            p.selected_background.set()
            path.fill()
            NSGraphicsContext.restoreGraphicsState()
        else:
            p.selected_background.set()
            path.fill()
        p.selected_border.set()
        path.setLineWidth_(1.0)
        path.stroke()
        indicator_rect = NSMakeRect(
            float(inset.origin.x) + 2.0,
            float(inset.origin.y) + 12.0,
            4.0,
            max(4.0, float(inset.size.height) - 24.0),
        )
        indicator = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            indicator_rect, 2.0, 2.0
        )
        p.accent_strong.set()
        indicator.fill()


class NoteList(NSObject):
    """Table of notes; also its own data source & delegate."""

    def initWithPalette_onSelect_onCollapse_(  # noqa: N802
        self, palette, on_select, on_collapse
    ):
        self = objc.super(NoteList, self).init()
        if self is None:
            return None
        self._palette: Palette = palette
        self._on_select: Callable[[str | None], None] = on_select
        self._on_collapse: Callable[[], None] = on_collapse
        self._notes: list[Note] = []
        self._selected_id: str | None = None
        self._suppress = False
        self._collapsed = False
        self._build()
        return self

    # -- build ---------------------------------------------------------------

    def _build(self) -> None:
        p = self._palette
        self.view: NSView = solid_view(p.note_list_background)

        self._header = add(
            self.view, label("All Notes", NSFont.boldSystemFontOfSize_(18), p.text_primary)
        )
        pin_edges(self._header, self.view, top=54, leading=20, trailing=20, bottom=None)
        self._subtitle = add(self.view, label("", NSFont.systemFontOfSize_(11.5), p.text_muted))
        pin_edges(self._subtitle, self.view, top=80, leading=20, trailing=20, bottom=None)

        collapse = NSButton.alloc().init()
        collapse.setBordered_(False)
        collapse.setImagePosition_(NSImageOnly)
        collapse.setImage_(symbol_image("sidebar.right", size=12, weight="semibold"))
        collapse.setContentTintColor_(p.text_muted)
        collapse.setTarget_(self)
        collapse.setAction_("toggleCollapse:")
        collapse.setToolTip_("Collapse Notes")
        collapse.setAccessibilityLabel_("Collapse Notes")
        add(self.view, collapse)
        pin_edges(collapse, self.view, top=52, leading=None, trailing=14, bottom=None)
        set_width(collapse, 28)
        set_height(collapse, 28)
        self._collapse_button = collapse

        scroll = add(self.view, NSScrollView.alloc().init())
        scroll.setDrawsBackground_(False)
        scroll.setBorderType_(NSNoBorder)
        scroll.setHasVerticalScroller_(True)
        scroll.setAutohidesScrollers_(True)
        pin_edges(scroll, self.view, top=104, leading=0, trailing=0, bottom=0)

        table = NSTableView.alloc().init()
        table.setBackgroundColor_(p.note_list_background)
        table.setHeaderView_(None)
        table.setRowHeight_(78.0)
        table.setSelectionHighlightStyle_(NSTableViewSelectionHighlightStyleRegular)
        table.setIntercellSpacing_((0.0, 2.0))
        table.setDataSource_(self)
        table.setDelegate_(self)
        column = NSTableColumn.alloc().initWithIdentifier_("note")
        column.setResizingMask_(1)  # NSTableColumnAutoresizingMask
        table.addTableColumn_(column)
        scroll.setDocumentView_(table)
        self._table = table
        self._scroll = scroll

        tab = NSButton.alloc().init()
        tab.setBordered_(False)
        tab.setImagePosition_(NSImageOnly)
        tab.setImage_(symbol_image("list.bullet", size=15, weight="semibold"))
        tab.setContentTintColor_(p.text_secondary)
        tab.setTarget_(self)
        tab.setAction_("toggleCollapse:")
        tab.setToolTip_("Expand Notes")
        tab.setAccessibilityLabel_("Expand Notes")
        add(self.view, tab)
        pin_edges(tab, self.view, top=16, leading=6, trailing=6, bottom=16)
        tab.setHidden_(True)
        self._collapsed_tab = tab

    # -- public API ----------------------------------------------------------

    @objc.python_method
    def set_notes(self, notes: list[Note], *, header: str, subtitle: str) -> None:
        self._notes = notes
        self._header.setStringValue_(header)
        self._subtitle.setStringValue_(subtitle)
        self._collapsed_tab.setTitle_(str(len(notes)))
        self._table.reloadData()
        if self._selected_id is not None:
            self.select_note_id(self._selected_id, notify=False)

    @objc.python_method
    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = bool(collapsed)
        for view in (
            self._header,
            self._subtitle,
            self._collapse_button,
            self._scroll,
        ):
            view.setHidden_(self._collapsed)
        self._collapsed_tab.setHidden_(not self._collapsed)

    @objc.IBAction
    def toggleCollapse_(self, sender):  # noqa: N802
        self._on_collapse()

    @objc.python_method
    def select_note_id(self, note_id: str | None, *, notify: bool = True) -> None:
        self._selected_id = note_id
        index = next((i for i, n in enumerate(self._notes) if n.id == note_id), None)
        self._suppress = not notify
        if index is None:
            self._table.deselectAll_(None)
        else:
            self._table.selectRowIndexes_byExtendingSelection_(
                NSIndexSet.indexSetWithIndex_(index), False
            )
            self._table.scrollRowToVisible_(index)
        self._suppress = False

    @objc.python_method
    def selected_note(self) -> Note | None:
        return next((n for n in self._notes if n.id == self._selected_id), None)

    # -- NSTableView data source / delegate ----------------------------------

    def numberOfRowsInTableView_(self, table):  # noqa: N802
        return len(self._notes)

    def tableView_rowViewForRow_(self, table, row):  # noqa: N802
        return _ThemedRowView.alloc().initWithPalette_(self._palette)

    def tableView_viewForTableColumn_row_(self, table, column, row):  # noqa: N802
        return self._make_cell(self._notes[row])

    def tableView_shouldSelectRow_(self, table, row):  # noqa: N802
        return True

    def tableViewSelectionDidChange_(self, notification):  # noqa: N802
        if self._suppress:
            return
        row = self._table.selectedRow()
        if 0 <= row < len(self._notes):
            note = self._notes[row]
            self._selected_id = note.id
            self._on_select(note.id)

    # -- cell view -----------------------------------------------------------

    @objc.python_method
    def _make_cell(self, note: Note) -> NSView:
        p = self._palette
        cell: FlippedView = flipped_view()

        selected = note.id == self._selected_id
        title = add(
            cell,
            label(
                note.title or "Untitled Note",
                (
                    NSFont.boldSystemFontOfSize_(14)
                    if selected
                    else NSFont.systemFontOfSize_(14)
                ),
                p.text_primary,
            ),
        )
        pin_edges(title, cell, top=12, leading=16, trailing=16, bottom=None)

        preview = add(
            cell, label(preview_text(note), NSFont.systemFontOfSize_(12.5), p.text_secondary)
        )
        pin_edges(preview, cell, top=34, leading=16, trailing=16, bottom=None)

        date = add(
            cell,
            label(
                format_relative(note.updated_at, now_local()),
                NSFont.systemFontOfSize_(10.5),
                p.text_muted,
            ),
        )
        pin_edges(date, cell, top=56, leading=16, trailing=None, bottom=None)

        if note.category != ALL_NOTES:
            chip = add(cell, rounded_view(p.pill_background, 6.0))
            pin_edges(chip, cell, top=54, leading=None, trailing=16, bottom=None)
            set_height(chip, 18)
            chip_label = add(
                chip, label(note.category, NSFont.systemFontOfSize_(10), p.accent_strong)
            )
            pin_edges(chip_label, chip, top=3, leading=8, trailing=8, bottom=None)
            # Width the chip to its label.
            chip_label.sizeToFit()
            set_width(chip, float(chip_label.fittingSize().width) + 16.0)

        return cell
