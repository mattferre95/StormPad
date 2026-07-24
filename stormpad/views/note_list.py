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
    NSEventModifierFlagCommand,
    NSEventModifierFlagShift,
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
from Foundation import NSIndexSet, NSMakeRect, NSMutableIndexSet, NSNotFound, NSObject

from ..dragdrop import NOTE_PASTEBOARD_TYPE, encode_drag_payload
from ..models import Note, now_local
from ..motion import AnimationToken, Motion
from ..uihelpers import display_tag, format_relative, preview_text
from .controls import FlippedView, flipped_view, icon_view, label, rounded_view, solid_view
from .layout import MAIN_COLUMN_TOP_INSET, add, pin_edges, set_height, set_width
from .motion import anim, can_animate, current_policy, run
from .palette import Palette, symbol_image

# Compact All/Pinned filter segments.
FILTER_ALL = 0
FILTER_PINNED = 1
_CHEVRON_BUTTON = 28.0  # square hit target
_CHEVRON_POINT = 13.0  # symbol point size


def reconciled_note_selection(
    visible_ids,
    selected_ids,
    active_id: str | None,
) -> tuple[set[str], str | None]:
    """Drop hidden UUIDs while retaining a visible active selection."""
    visible = set(visible_ids)
    active = active_id if active_id in visible else None
    selected = {note_id for note_id in selected_ids if note_id in visible}
    if active is not None:
        selected.add(active)
    return selected, active


def note_selection_role(
    note_id: str,
    selected_ids,
    active_id: str | None,
) -> str:
    if note_id == active_id and note_id in selected_ids:
        return "active"
    if note_id in selected_ids:
        return "secondary"
    return "normal"


class _ThemedRowView(NSTableRowView):
    """Row view that draws the themed selected-background."""

    def initWithPalette_owner_noteID_(self, palette, owner, note_id):  # noqa: N802
        self = objc.super(_ThemedRowView, self).init()
        if self is None:
            return None
        self._palette = palette
        self._owner = owner
        self._note_id = str(note_id)
        return self

    def drawSelectionInRect_(self, rect):  # noqa: N802
        if not self.isSelected():
            return
        p = self._palette
        active = (
            note_selection_role(
                self._note_id,
                self._owner._selected_ids,
                self._owner._selected_id,
            )
            == "active"
        )
        inset = NSInsetRect(self.bounds(), 8.0, 3.0)
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(inset, 10.0, 10.0)
        glow = p.selection_glow(0.55) if active else None
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
            (
                p.selected_background
                if active
                else p.selected_background.colorWithAlphaComponent_(0.52)
            ).set()
            path.fill()
        (
            p.selected_border
            if active
            else p.selected_border.colorWithAlphaComponent_(0.48)
        ).set()
        path.setLineWidth_(1.0)
        path.stroke()
        if not active:
            return
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
        # Right-clicking a note that is already part of the selection targets the
        # whole selection; right-clicking any other note first selects just that
        # note, so a context-menu delete never surprises the user by acting on a
        # previous range.
        note_id = owner._notes[row].id
        if note_id not in owner._selected_ids or self.numberOfSelectedRows() <= 1:
            self.selectRowIndexes_byExtendingSelection_(
                NSIndexSet.indexSetWithIndex_(row), False
            )
        return owner.menu_for_note(owner._notes[row])

    def mouseDown_(self, event):  # noqa: N802
        owner = getattr(self, "stormpad_owner", None)
        normal_row = None
        if owner is not None:
            flags = int(event.modifierFlags())
            extending = bool(
                flags
                & int(NSEventModifierFlagShift | NSEventModifierFlagCommand)
            )
            point = self.convertPoint_fromView_(event.locationInWindow(), None)
            row = int(self.rowAtPoint_(point))
            if 0 <= row < len(owner._notes):
                owner._pending_clicked_row = row
                if not extending:
                    normal_row = row
                    owner.prepare_normal_click()
        objc.super(NoteTableView, self).mouseDown_(event)
        if owner is not None and normal_row is not None:
            owner.commit_normal_click(normal_row)

    def keyDown_(self, event):  # noqa: N802
        owner = getattr(self, "stormpad_owner", None)
        chars = str(event.charactersIgnoringModifiers() or "")
        codes = {ord(ch) for ch in chars}
        # Delete (Backspace, U+007F) and Forward Delete (NSDeleteFunctionKey,
        # U+F728) request removal of the current selection through the owner's
        # confirmed, safe (Trash) delete path.
        if owner is not None and codes & {0x7F, 0xF728}:
            owner.request_delete_selection()
            return
        objc.super(NoteTableView, self).keyDown_(event)


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
        self._on_new_note: Callable[[], None] | None = None
        self._collapse_token = AnimationToken()
        self._notes: list[Note] = []
        self._selected_id: str | None = None
        # Multi-selection tracked by stable UUID (never by path or row index).
        self._selected_ids: set[str] = set()
        self._on_delete: Callable[[], None] | None = None
        self._suppress = False
        self._collapsed = False
        self._menu_provider = None
        self._dragging_note_id: str | None = None
        self._pending_clicked_row: int | None = None
        self._selection_anchor_id: str | None = None
        self._pinned_ids: set[str] = set()
        self._project_names: dict[str, str] = {}
        self._search_previews: dict[str, str] = {}
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
        pin_edges(
            self._header,
            self.view,
            top=MAIN_COLUMN_TOP_INSET,
            leading=20,
            trailing=20,
            bottom=None,
        )
        self._subtitle = add(self.view, label("", NSFont.systemFontOfSize_(11.5), p.text_muted))
        pin_edges(
            self._subtitle,
            self.view,
            top=MAIN_COLUMN_TOP_INSET + 26,
            leading=20,
            trailing=20,
            bottom=None,
        )

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
        pin_edges(
            collapse,
            self.view,
            top=MAIN_COLUMN_TOP_INSET - 3,
            leading=None,
            trailing=14,
            bottom=None,
        )
        set_width(collapse, _CHEVRON_BUTTON)
        set_height(collapse, _CHEVRON_BUTTON)
        self._collapse_button = collapse

        # New Note, mirroring the Projects section's create control.
        new_note = NSButton.alloc().init()
        new_note.setBordered_(False)
        new_note.setImagePosition_(NSImageOnly)
        new_note.setImage_(symbol_image("plus", size=12.0, weight="semibold"))
        new_note.setImageScaling_(NSImageScaleProportionallyDown)
        new_note.setContentTintColor_(p.text_muted)
        new_note.setTarget_(self)
        new_note.setAction_("createNote:")
        new_note.setToolTip_("New Note")
        new_note.setAccessibilityLabel_("New Note")
        add(self.view, new_note)
        pin_edges(
            new_note,
            self.view,
            top=MAIN_COLUMN_TOP_INSET - 3,
            leading=None,
            trailing=44,
            bottom=None,
        )
        set_width(new_note, _CHEVRON_BUTTON)
        set_height(new_note, _CHEVRON_BUTTON)
        self._new_note_button = new_note

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
        pin_edges(
            seg,
            self.view,
            top=MAIN_COLUMN_TOP_INSET + 22,
            leading=None,
            trailing=14,
            bottom=None,
        )
        set_width(seg, 112)
        set_height(seg, 20)
        self._filter_control = seg

        scroll = add(self.view, NSScrollView.alloc().init())
        scroll.setDrawsBackground_(False)
        scroll.setBorderType_(NSNoBorder)
        scroll.setHasVerticalScroller_(True)
        scroll.setAutohidesScrollers_(True)
        pin_edges(
            scroll,
            self.view,
            top=MAIN_COLUMN_TOP_INSET + 50,
            leading=0,
            trailing=0,
            bottom=0,
        )

        table = NoteTableView.alloc().init()
        table.stormpad_owner = self
        table.setBackgroundColor_(p.note_list_background)
        table.setHeaderView_(None)
        table.setRowHeight_(78.0)
        table.setSelectionHighlightStyle_(NSTableViewSelectionHighlightStyleRegular)
        table.setIntercellSpacing_((0.0, 2.0))
        # Native contiguous range selection: a click sets the anchor, Shift-click
        # extends the range (both directions). Empty clicks keep a selection.
        table.setAllowsMultipleSelection_(True)
        table.setAllowsEmptySelection_(True)
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
    def set_notes(
        self,
        notes: list[Note],
        *,
        header: str,
        subtitle: str,
        transition: bool = False,
        search_previews: dict[str, str] | None = None,
    ) -> None:
        self._notes = notes
        self._search_previews = dict(search_previews or {})
        self._header.setStringValue_(header)
        self._subtitle.setStringValue_(subtitle)
        # The collapsed control is an image-only chevron: a title would draw on
        # top of the glyph. Surface the count through the tooltip instead.
        self._collapsed_tab.setToolTip_(f"Expand Notes ({len(notes)})")
        self._table.reloadData()
        # Reconcile the multi-selection against the notes now visible: any
        # selected UUID whose note is no longer shown is dropped, so a scope,
        # filter, or search change can never leave a hidden note silently
        # selected. Same visible set (e.g. after autosave) keeps the selection.
        self._reconcile_selection()
        if transition:
            self._fade_in_list()

    @objc.python_method
    def _reconcile_selection(self) -> None:
        self._selected_ids, self._selected_id = reconciled_note_selection(
            (note.id for note in self._notes),
            self._selected_ids,
            self._selected_id,
        )
        indices = [i for i, n in enumerate(self._notes) if n.id in self._selected_ids]
        self._suppress = True
        if indices:
            index_set = NSMutableIndexSet.alloc().init()
            for i in indices:
                index_set.addIndex_(i)
            self._table.selectRowIndexes_byExtendingSelection_(index_set, False)
            if self._selected_id is not None:
                active = next(
                    (i for i, n in enumerate(self._notes) if n.id == self._selected_id),
                    None,
                )
                if active is not None:
                    self._table.scrollRowToVisible_(active)
        else:
            self._table.deselectAll_(None)
        self._suppress = False
        self._table.setNeedsDisplay_(True)

    @objc.python_method
    def prepare_normal_click(self) -> None:
        """Clear a previous range before AppKit selects the clicked row."""
        self._suppress = True
        self._table.deselectAll_(None)
        self._suppress = False
        self._selected_ids.clear()

    @objc.python_method
    def commit_normal_click(self, row: int) -> None:
        """Make the completed ordinary click the sole selection source."""
        if not 0 <= int(row) < len(self._notes):
            return
        note_id = self._notes[int(row)].id
        previous = self._selected_id
        self._selected_id = note_id
        self._selected_ids = {note_id}
        self._selection_anchor_id = note_id
        self._pending_clicked_row = None
        self._suppress = True
        self._table.selectRowIndexes_byExtendingSelection_(
            NSIndexSet.indexSetWithIndex_(int(row)), False
        )
        self._suppress = False
        self._table.setNeedsDisplay_(True)
        if previous != note_id:
            self._on_select(note_id)

    @objc.python_method
    def restore_active_note_id(self, note_id: str | None) -> None:
        """Keep an existing visible range only when its active UUID is unchanged."""
        if note_id == self._selected_id and note_id in self._selected_ids:
            self._reconcile_selection()
            return
        self.select_note_id(note_id, notify=False)

    @objc.python_method
    def _fade_in_list(self) -> None:
        """A restrained opacity lift on the reloaded rows — never a slide.

        The content is already correct before the fade starts, so an interrupted
        transition simply restarts and still ends fully opaque.
        """
        if not can_animate(self._scroll) or self._collapsed:
            return
        duration = current_policy().duration(Motion.LIST)
        if duration <= 0.0:
            self._scroll.setAlphaValue_(1.0)
            return
        self._scroll.setAlphaValue_(0.45)
        run(duration, lambda animated: anim(self._scroll, animated).setAlphaValue_(1.0))

    @objc.python_method
    def _content_views(self) -> tuple:
        return (
            self._header,
            self._subtitle,
            self._collapse_button,
            self._new_note_button,
            self._filter_control,
            self._scroll,
        )

    @objc.python_method
    def _apply_collapsed_visibility(self) -> None:
        """Write the final visibility for the current state.

        Recomputed from ``self._collapsed`` rather than from the direction that
        started the animation, so an interrupted collapse still finishes in the
        correct state and never leaves an invisible view accepting clicks.
        """
        for view in self._content_views():
            view.setHidden_(self._collapsed)
            view.setAlphaValue_(1.0)
        self._collapsed_tab.setHidden_(not self._collapsed)
        self._collapsed_tab.setAlphaValue_(1.0)

    @objc.python_method
    def set_collapsed(self, collapsed: bool, *, duration: float = 0.0) -> None:
        collapsed = bool(collapsed)
        unchanged = collapsed == self._collapsed
        self._collapsed = collapsed
        if duration <= 0.0 or not can_animate(self.view) or unchanged:
            self._collapse_token.cancel()
            self._apply_collapsed_visibility()
            return

        # Both surfaces are on screen for the crossfade; the one that is leaving
        # is hidden again only once the transition completes.
        for view in self._content_views():
            view.setHidden_(False)
            view.setAlphaValue_(1.0 if collapsed else 0.0)
        self._collapsed_tab.setHidden_(False)
        self._collapsed_tab.setAlphaValue_(0.0 if collapsed else 1.0)

        def body(animated: bool) -> None:
            for view in self._content_views():
                anim(view, animated).setAlphaValue_(0.0 if collapsed else 1.0)
            anim(self._collapsed_tab, animated).setAlphaValue_(1.0 if collapsed else 0.0)

        token = self._collapse_token.begin()

        def done() -> None:
            if self._collapse_token.is_current(token):
                self._apply_collapsed_visibility()

        run(duration, body, completion=done)

    @objc.python_method
    def set_new_note_handler(self, handler: Callable[[], None] | None) -> None:
        self._on_new_note = handler

    @objc.IBAction
    def createNote_(self, sender):  # noqa: N802
        if self._on_new_note is not None:
            self._on_new_note()

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
        # A programmatic single-note selection also resets the multi-selection to
        # just that note, so the anchor and the set stay consistent.
        self._selected_ids = {note_id} if note_id is not None else set()
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
    def set_active_note_id(self, note_id: str | None) -> None:
        """Track the active (editor-focused) note without touching the table
        selection or the multi-selection set. Used when the table's own
        selection change already reflects the user's click/Shift-click.
        """
        self._selected_id = note_id

    @objc.python_method
    def selected_note(self) -> Note | None:
        return next((n for n in self._notes if n.id == self._selected_id), None)

    @objc.python_method
    def selected_note_ids(self) -> list[str]:
        """Visible selected notes as stable UUIDs, in list order."""
        return [n.id for n in self._notes if n.id in self._selected_ids]

    @objc.python_method
    def set_delete_handler(self, handler: Callable[[], None] | None) -> None:
        self._on_delete = handler

    @objc.python_method
    def request_delete_selection(self) -> None:
        if self._on_delete is not None:
            self._on_delete()

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
        return _ThemedRowView.alloc().initWithPalette_owner_noteID_(
            self._palette, self, self._notes[row].id
        )

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
        # Capture the full selection as stable UUIDs (native shift-click has
        # already computed the contiguous range).
        selected = self._table.selectedRowIndexes()
        ids: set[str] = set()
        index = selected.firstIndex()
        while index != NSNotFound and index < len(self._notes):
            ids.add(self._notes[index].id)
            index = selected.indexGreaterThanIndex_(index)
        self._selected_ids = ids
        # The active/focused note is the clicked row; the editor follows it.
        pending = self._pending_clicked_row
        self._pending_clicked_row = None
        row = (
            pending
            if pending is not None
            and 0 <= pending < len(self._notes)
            and self._notes[pending].id in ids
            else self._table.selectedRow()
        )
        if 0 <= row < len(self._notes):
            note = self._notes[row]
            if len(ids) == 1:
                self._selection_anchor_id = note.id
            if note.id != self._selected_id:
                self._selected_id = note.id
                self._on_select(note.id)
        elif not ids:
            self._selected_id = None
        self._table.setNeedsDisplay_(True)

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

        preview_value = self._search_previews.get(note.id) or preview_text(note)
        preview = add(
            cell,
            label(
                preview_value,
                NSFont.systemFontOfSize_(12.5),
                p.text_secondary,
            ),
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
