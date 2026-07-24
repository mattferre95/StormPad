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
    NSControlSizeSmall,
    NSDragOperationMove,
    NSDragOperationNone,
    NSFont,
    NSGraphicsContext,
    NSImageOnly,
    NSImageScaleProportionallyDown,
    NSInsetRect,
    NSNoBorder,
    NSPasteboardItem,
    NSScrollView,
    NSSegmentedControl,
    NSSegmentStyleRounded,
    NSSegmentSwitchTrackingSelectOne,
    NSShadow,
    NSTableColumn,
    NSTableRowView,
    NSTableView,
    NSTableViewSelectionHighlightStyleRegular,
    NSView,
)
from Foundation import NSIndexSet, NSMakeRect, NSObject

from ..dragdrop import NOTE_PASTEBOARD_TYPE, encode_drag_payload
from ..models import Note, now_local
from ..uihelpers import display_tag, format_relative, preview_text
from .controls import FlippedView, flipped_view, icon_view, label, rounded_view, solid_view
from .layout import add, pin_edges, set_height, set_width
from .palette import Palette, symbol_image

# Compact All/Pinned filter segments.
FILTER_ALL = 0
FILTER_PINNED = 1
_CHEVRON_BUTTON = 28.0  # square hit target
_CHEVRON_POINT = 13.0  # symbol point size


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


class NoteTableView(NSTableView):
    """Table view that asks its owner for a selected-note context menu."""

    def menuForEvent_(self, event):  # noqa: N802
        owner = getattr(self, "stormpad_owner", None)
        if owner is None:
            return objc.super(NoteTableView, self).menuForEvent_(event)
        point = self.convertPoint_fromView_(event.locationInWindow(), None)
        row = int(self.rowAtPoint_(point))
        if not 0 <= row < len(owner._notes):
            return None
        self.selectRowIndexes_byExtendingSelection_(
            NSIndexSet.indexSetWithIndex_(row), False
        )
        return owner.menu_for_note(owner._notes[row])


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
        self._menu_provider = None
        self._dragging_note_id: str | None = None
        self._pinned_ids: set[str] = set()
        self._project_names: dict[str, str] = {}
        self._on_filter: Callable[[bool], None] | None = None
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

        # Collapse chevron — square hit target, proportional scaling so the SF
        # Symbol keeps its aspect ratio and is never clipped or stretched.
        collapse = NSButton.alloc().init()
        collapse.setBordered_(False)
        collapse.setImagePosition_(NSImageOnly)
        collapse.setImage_(
            symbol_image("chevron.left", size=_CHEVRON_POINT, weight="semibold")
        )
        collapse.setImageScaling_(NSImageScaleProportionallyDown)
        collapse.setContentTintColor_(p.text_muted)
        collapse.setTarget_(self)
        collapse.setAction_("toggleCollapse:")
        collapse.setToolTip_("Collapse Notes")
        collapse.setAccessibilityLabel_("Collapse Notes")
        add(self.view, collapse)
        # Vertically centred on the "All Notes" header (header top 54, ~22 tall).
        pin_edges(collapse, self.view, top=51, leading=None, trailing=14, bottom=None)
        set_width(collapse, _CHEVRON_BUTTON)
        set_height(collapse, _CHEVRON_BUTTON)
        self._collapse_button = collapse

        # Compact All / Pinned filter.
        seg = NSSegmentedControl.alloc().init()
        seg.setSegmentCount_(2)
        seg.setSegmentStyle_(NSSegmentStyleRounded)
        seg.setTrackingMode_(NSSegmentSwitchTrackingSelectOne)
        seg.setControlSize_(NSControlSizeSmall)
        seg.setFont_(NSFont.systemFontOfSize_(10.5))
        seg.setLabel_forSegment_("All", FILTER_ALL)
        seg.setLabel_forSegment_("Pinned", FILTER_PINNED)
        seg.setSelectedSegment_(FILTER_ALL)
        seg.setTarget_(self)
        seg.setAction_("filterChanged:")
        seg.setAccessibilityLabel_("Filter notes: All or Pinned")
        seg.setToolTip_("Show all notes or only pinned notes")
        add(self.view, seg)
        pin_edges(seg, self.view, top=76, leading=None, trailing=14, bottom=None)
        set_width(seg, 112)
        set_height(seg, 20)
        self._filter_control = seg

        scroll = add(self.view, NSScrollView.alloc().init())
        scroll.setDrawsBackground_(False)
        scroll.setBorderType_(NSNoBorder)
        scroll.setHasVerticalScroller_(True)
        scroll.setAutohidesScrollers_(True)
        pin_edges(scroll, self.view, top=104, leading=0, trailing=0, bottom=0)

        table = NoteTableView.alloc().init()
        table.stormpad_owner = self
        table.setBackgroundColor_(p.note_list_background)
        table.setHeaderView_(None)
        table.setRowHeight_(78.0)
        table.setSelectionHighlightStyle_(NSTableViewSelectionHighlightStyleRegular)
        table.setIntercellSpacing_((0.0, 2.0))
        table.setDataSource_(self)
        table.setDelegate_(self)
        table.setAccessibilityLabel_("Notes, rows are drag sources")
        table.setDraggingSourceOperationMask_forLocal_(NSDragOperationMove, True)
        table.setDraggingSourceOperationMask_forLocal_(NSDragOperationNone, False)
        column = NSTableColumn.alloc().initWithIdentifier_("note")
        column.setResizingMask_(1)  # NSTableColumnAutoresizingMask
        table.addTableColumn_(column)
        scroll.setDocumentView_(table)
        self._table = table
        self._scroll = scroll

        # Collapsed-state chevron. Square and horizontally centred (previously it
        # was pinned to both edges, which stretched the button), anchored near the
        # top rather than centred in the window.
        tab = NSButton.alloc().init()
        tab.setBordered_(False)
        tab.setImagePosition_(NSImageOnly)
        tab.setImage_(
            symbol_image("chevron.right", size=_CHEVRON_POINT, weight="semibold")
        )
        tab.setImageScaling_(NSImageScaleProportionallyDown)
        tab.setContentTintColor_(p.text_secondary)
        tab.setTarget_(self)
        tab.setAction_("toggleCollapse:")
        tab.setToolTip_("Expand Notes")
        tab.setAccessibilityLabel_("Expand Notes")
        add(self.view, tab)
        pin_edges(tab, self.view, top=51, leading=None, trailing=None, bottom=None)
        tab.centerXAnchor().constraintEqualToAnchor_(self.view.centerXAnchor()).setActive_(True)
        set_width(tab, _CHEVRON_BUTTON)
        set_height(tab, _CHEVRON_BUTTON)
        tab.setHidden_(True)
        self._collapsed_tab = tab

    # -- public API ----------------------------------------------------------

    @objc.python_method
    def set_notes(self, notes: list[Note], *, header: str, subtitle: str) -> None:
        self._notes = notes
        self._header.setStringValue_(header)
        self._subtitle.setStringValue_(subtitle)
        # The collapsed control is an image-only chevron: a title would draw on
        # top of the glyph. Surface the count through the tooltip instead.
        self._collapsed_tab.setToolTip_(f"Expand Notes ({len(notes)})")
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
            self._filter_control,
            self._scroll,
        ):
            view.setHidden_(self._collapsed)
        self._collapsed_tab.setHidden_(not self._collapsed)

    @objc.IBAction
    def toggleCollapse_(self, sender):  # noqa: N802
        self._on_collapse()

    # -- pinned / tag presentation -------------------------------------------

    @objc.python_method
    def set_filter_handler(self, handler: Callable[[bool], None] | None) -> None:
        """Called with True when the user selects Pinned, False for All."""
        self._on_filter = handler

    @objc.python_method
    def set_pinned_only(self, pinned_only: bool) -> None:
        self._filter_control.setSelectedSegment_(
            FILTER_PINNED if pinned_only else FILTER_ALL
        )

    @objc.python_method
    def set_pinned_ids(self, pinned_ids) -> None:
        self._pinned_ids = set(pinned_ids or ())

    @objc.python_method
    def set_project_names(self, names: dict[str, str] | None) -> None:
        self._project_names = dict(names or {})

    @objc.IBAction
    def filterChanged_(self, sender):  # noqa: N802
        if self._on_filter is not None:
            self._on_filter(int(sender.selectedSegment()) == FILTER_PINNED)

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

    @objc.python_method
    def set_menu_provider(self, provider) -> None:
        self._menu_provider = provider

    @objc.python_method
    def menu_for_note(self, note: Note):
        return self._menu_provider(note) if self._menu_provider is not None else None

    # -- NSTableView data source / delegate ----------------------------------

    def numberOfRowsInTableView_(self, table):  # noqa: N802
        return len(self._notes)

    def tableView_rowViewForRow_(self, table, row):  # noqa: N802
        return _ThemedRowView.alloc().initWithPalette_(self._palette)

    def tableView_viewForTableColumn_row_(self, table, column, row):  # noqa: N802
        return self._make_cell(self._notes[row])

    def tableView_shouldSelectRow_(self, table, row):  # noqa: N802
        return True

    def tableView_pasteboardWriterForRow_(self, table, row):  # noqa: N802
        if not 0 <= int(row) < len(self._notes):
            return None
        note = self._notes[int(row)]
        raw = encode_drag_payload(
            "note",
            note.id,
            source_project_id=note.project_id,
            source_index=int(row),
        )
        item = NSPasteboardItem.alloc().init()
        item.setString_forType_(raw, NOTE_PASTEBOARD_TYPE)
        return item

    def tableView_draggingSession_willBeginAtPoint_forRowIndexes_(  # noqa: N802
        self, table, session, point, row_indexes
    ):
        index = int(row_indexes.firstIndex())
        self._dragging_note_id = (
            self._notes[index].id if 0 <= index < len(self._notes) else None
        )
        if self._dragging_note_id is not None:
            table.setAccessibilityLabel_(
                f"Dragging note {self._notes[index].title or 'Untitled Note'}"
            )

    def tableView_draggingSession_endedAtPoint_operation_(  # noqa: N802
        self, table, session, point, operation
    ):
        self._dragging_note_id = None
        table.setAccessibilityLabel_("Notes, rows are drag sources")

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
        cell.setAccessibilityLabel_(
            f"Note {note.title or 'Untitled Note'}, drag source"
        )

        selected = note.id == self._selected_id
        pinned = note.id in self._pinned_ids
        title = add(
            cell,
            label(
                note.title or "Untitled Note",
                (NSFont.boldSystemFontOfSize_(14) if selected else NSFont.systemFontOfSize_(14)),
                p.text_primary,
            ),
        )
        # Leave room for the restrained pin glyph when the note is pinned.
        pin_edges(title, cell, top=12, leading=16, trailing=(34 if pinned else 16), bottom=None)

        if pinned:
            pin_icon = add(
                cell, icon_view(symbol_image("pin.fill", size=10.5), p.text_muted)
            )
            pin_icon.setToolTip_("Pinned")
            pin_icon.setAccessibilityLabel_("Pinned")
            pin_edges(pin_icon, cell, top=14, leading=None, trailing=16, bottom=None)
            set_width(pin_icon, 14)
            set_height(pin_icon, 13)

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

        # Project name when the note is filed, otherwise its Category. The
        # underlying Category is never modified — this is presentation only.
        tag = display_tag(note, self._project_names)
        if tag:
            chip = add(cell, rounded_view(p.pill_background, 6.0))
            pin_edges(chip, cell, top=54, leading=None, trailing=16, bottom=None)
            set_height(chip, 18)
            chip_label = add(chip, label(tag, NSFont.systemFontOfSize_(10), p.accent_strong))
            pin_edges(chip_label, chip, top=3, leading=8, trailing=8, bottom=None)
            # Width the chip to its label, clamped so long Project names truncate
            # cleanly; the full name stays available as a tooltip.
            chip_label.sizeToFit()
            set_width(chip, min(float(chip_label.fittingSize().width) + 16.0, 140.0))
            chip.setToolTip_(tag)
            chip_label.setToolTip_(tag)

        return cell
