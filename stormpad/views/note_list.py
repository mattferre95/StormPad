"""Note list column: header + a native table of note rows.

Rows show title, a clean one-line preview, an updated timestamp, and a category
tag. Selection is themed (not the system accent) and drives editor loading.
"""

from __future__ import annotations

from collections.abc import Callable

import objc
from AppKit import (
    NSBezierPath,
    NSFont,
    NSInsetRect,
    NSNoBorder,
    NSScrollView,
    NSTableColumn,
    NSTableRowView,
    NSTableView,
    NSTableViewSelectionHighlightStyleNone,
    NSView,
)
from Foundation import NSIndexSet, NSObject

from ..models import ALL_NOTES, Note, now_local
from ..uihelpers import format_relative, preview_text
from .controls import FlippedView, flipped_view, label, solid_view
from .layout import add, pin_edges
from .palette import Palette


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
        self._palette.selected_background.set()
        inset = NSInsetRect(self.bounds(), 8.0, 3.0)
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(inset, 10.0, 10.0).fill()


class NoteList(NSObject):
    """Table of notes; also its own data source & delegate."""

    def initWithPalette_onSelect_(self, palette, on_select):  # noqa: N802
        self = objc.super(NoteList, self).init()
        if self is None:
            return None
        self._palette: Palette = palette
        self._on_select: Callable[[str | None], None] = on_select
        self._notes: list[Note] = []
        self._selected_id: str | None = None
        self._suppress = False
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

        scroll = add(self.view, NSScrollView.alloc().init())
        scroll.setDrawsBackground_(False)
        scroll.setBorderType_(NSNoBorder)
        scroll.setHasVerticalScroller_(True)
        pin_edges(scroll, self.view, top=104, leading=0, trailing=0, bottom=0)

        table = NSTableView.alloc().init()
        table.setBackgroundColor_(p.note_list_background)
        table.setHeaderView_(None)
        table.setRowHeight_(78.0)
        table.setSelectionHighlightStyle_(NSTableViewSelectionHighlightStyleNone)
        table.setIntercellSpacing_((0.0, 2.0))
        table.setDataSource_(self)
        table.setDelegate_(self)
        column = NSTableColumn.alloc().initWithIdentifier_("note")
        column.setResizingMask_(1)  # NSTableColumnAutoresizingMask
        table.addTableColumn_(column)
        scroll.setDocumentView_(table)
        self._table = table

    # -- public API ----------------------------------------------------------

    @objc.python_method
    def set_notes(self, notes: list[Note], *, header: str, subtitle: str) -> None:
        self._notes = notes
        self._header.setStringValue_(header)
        self._subtitle.setStringValue_(subtitle)
        self._table.reloadData()
        if self._selected_id is not None:
            self.select_note_id(self._selected_id, notify=False)

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

        title = add(
            cell, label(note.title or "Untitled Note", NSFont.systemFontOfSize_(14), p.text_primary)
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
            tag = add(cell, label(note.category, NSFont.systemFontOfSize_(10), p.accent_strong))
            pin_edges(tag, cell, top=56, leading=None, trailing=16, bottom=None)

        return cell
