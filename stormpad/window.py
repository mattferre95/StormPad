"""Main window controller.

A native window (transparent titlebar + full-size content view + real traffic
lights) hosting a three-column ``NSSplitViewController``: sidebar, note list,
editor. Owns the :class:`~stormpad.session.NoteStore`, preferences, autosave,
and all selection/search/category state — consuming the Phase 2 API rather than
reimplementing storage.
"""

from __future__ import annotations

import os
from pathlib import Path

import objc
from AppKit import (
    NSAlert,
    NSBackingStoreBuffered,
    NSButton,
    NSColor,
    NSFont,
    NSImage,
    NSSplitViewController,
    NSSplitViewDividerStyleThin,
    NSSplitViewItem,
    NSTimer,
    NSViewController,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskFullSizeContentView,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
    NSWindowTitleHidden,
)
from Foundation import NSMakeRect, NSObject

from . import paths
from .defaults import UserDefaultsBackend
from .errors import NoteNotFoundError, NotesDirectoryError, StorageError
from .models import ALL_NOTES, CATEGORIES, now_local
from .preferences import Preferences
from .search import filter_by_category, search_notes
from .session import NoteStore
from .theme import get_theme
from .uihelpers import (
    AutosaveController,
    SaveStatus,
    choose_selected_note,
    default_new_category,
)
from .views import empty_state as es
from .views.controls import flipped_view, solid_view
from .views.editor import Editor
from .views.empty_state import EmptyState
from .views.layout import add, pin_edges, set_height, set_width
from .views.note_list import NoteList
from .views.palette import Palette
from .views.sidebar import Sidebar

_AUTOSAVE_DELAY = 0.4
_DEFAULT_SIZE = (1100.0, 720.0)
_MIN_SIZE = (900.0, 620.0)
_HEADER_HEIGHT = 52.0
_SIDEBAR_WIDTH = 248.0
_LIST_WIDTH = 326.0


def _wrap(view) -> NSViewController:
    vc = NSViewController.alloc().init()
    vc.setView_(view)
    return vc


class MainController(NSObject):
    """Application window controller (window/split delegate + actions)."""

    def initWithStore_(self, store):  # noqa: N802
        self = objc.super(MainController, self).init()
        if self is None:
            return None
        self._store: NoteStore = store
        self._prefs = Preferences(UserDefaultsBackend())
        self._theme = get_theme(self._prefs.theme)
        self._palette = Palette(self._theme)
        self._logo = self._load_logo()

        self._category = self._prefs.last_category
        self._query = os.environ.get("STORMPAD_INITIAL_QUERY", "").strip()
        self._current_id: str | None = None
        self._displayed: list = []

        self._autosave = AutosaveController(
            self._perform_save,
            delay=_AUTOSAVE_DELAY,
            schedule=self._schedule_timer,
            cancel=self._cancel_timer,
        )
        self._build_window()
        self._ensure_ready()
        self._apply_filter()
        return self

    # -- assets --------------------------------------------------------------

    @objc.python_method
    def _load_logo(self):
        logo_path = Path(__file__).resolve().parent.parent / "assets" / "Stormpad_logo.png"
        if logo_path.exists():
            return NSImage.alloc().initWithContentsOfFile_(str(logo_path))
        return None

    # -- window / layout -----------------------------------------------------

    @objc.python_method
    def _build_window(self) -> None:
        p = self._palette
        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskMiniaturizable
            | NSWindowStyleMaskResizable
            | NSWindowStyleMaskFullSizeContentView
        )
        rect = NSMakeRect(0, 0, _DEFAULT_SIZE[0], _DEFAULT_SIZE[1])
        window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, style, NSBackingStoreBuffered, False
        )
        window.setTitle_("StormPad")
        window.setTitlebarAppearsTransparent_(True)
        window.setTitleVisibility_(NSWindowTitleHidden)
        window.setMinSize_(_MIN_SIZE)
        window.setBackgroundColor_(p.app_background)
        window.setDelegate_(self)
        window.setFrameAutosaveName_("StormPadWindow")

        root = solid_view(p.app_background)
        window.setContentView_(root)

        # Header bar with the New Note button (right-aligned).
        header = add(root, solid_view(p.toolbar_background))
        pin_edges(header, root, top=0, leading=0, trailing=0, bottom=None)
        set_height(header, _HEADER_HEIGHT)
        new_button = NSButton.alloc().init()
        new_button.setTitle_("+  New Note")
        new_button.setBordered_(False)
        new_button.setWantsLayer_(True)
        new_button.setFont_(NSFont.boldSystemFontOfSize_(12.5))
        new_button.setContentTintColor_(NSColor.whiteColor())
        new_button.layer().setBackgroundColor_(p.accent.CGColor())
        new_button.layer().setCornerRadius_(8.0)
        new_button.setTarget_(self)
        new_button.setAction_("newNote:")
        add(header, new_button)
        new_button.trailingAnchor().constraintEqualToAnchor_constant_(
            header.trailingAnchor(), -16.0
        ).setActive_(True)
        new_button.centerYAnchor().constraintEqualToAnchor_(header.centerYAnchor()).setActive_(True)
        set_width(new_button, 108)
        set_height(new_button, 30)

        # Three-column split.
        self._sidebar = Sidebar(
            self._palette,
            self._logo,
            on_category=self._on_category,
            search_delegate=self,
        )
        self._note_list = NoteList.alloc().initWithPalette_onSelect_(
            self._palette, self._on_note_selected
        )
        self._editor = Editor.alloc().initWithPalette_onTitle_onBody_(
            self._palette, self._on_title_edited, self._on_body_edited
        )

        # Editor column = editor + empty-state overlay.
        editor_col = flipped_view()
        editor_col.setWantsLayer_(True)
        add(editor_col, self._editor.view)
        pin_edges(self._editor.view, editor_col, top=0, leading=0, trailing=0, bottom=0)
        self._empty = EmptyState(
            self._palette, self._logo, create_target=self, create_action="newNote:"
        )
        add(editor_col, self._empty.view)
        pin_edges(self._empty.view, editor_col, top=0, leading=0, trailing=0, bottom=0)

        split = NSSplitViewController.alloc().init()
        side_item = NSSplitViewItem.splitViewItemWithViewController_(_wrap(self._sidebar.view))
        side_item.setMinimumThickness_(210.0)
        side_item.setMaximumThickness_(320.0)
        side_item.setCanCollapse_(False)
        side_item.setHoldingPriority_(260.0)
        list_item = NSSplitViewItem.splitViewItemWithViewController_(_wrap(self._note_list.view))
        list_item.setMinimumThickness_(260.0)
        list_item.setMaximumThickness_(440.0)
        list_item.setHoldingPriority_(250.0)
        editor_item = NSSplitViewItem.splitViewItemWithViewController_(_wrap(editor_col))
        editor_item.setMinimumThickness_(420.0)
        editor_item.setHoldingPriority_(200.0)
        split.addSplitViewItem_(side_item)
        split.addSplitViewItem_(list_item)
        split.addSplitViewItem_(editor_item)
        split.splitView().setVertical_(True)
        split.splitView().setDividerStyle_(NSSplitViewDividerStyleThin)
        split.splitView().setAutosaveName_("StormPadSplit")
        self._split_vc = split

        add(root, split.view())
        pin_edges(split.view(), root, top=_HEADER_HEIGHT, leading=0, trailing=0, bottom=0)

        self._window = window
        window.center()
        window.makeKeyAndOrderFront_(None)
        # Set initial divider positions (after the window has a real size).
        split.splitView().setPosition_ofDividerAtIndex_(_SIDEBAR_WIDTH, 0)
        split.splitView().setPosition_ofDividerAtIndex_(_SIDEBAR_WIDTH + _LIST_WIDTH, 1)

    # -- timers (autosave scheduler) -----------------------------------------

    @objc.python_method
    def _schedule_timer(self, delay, callback):
        return NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
            delay, False, lambda timer: callback()
        )

    @objc.python_method
    def _cancel_timer(self, token):
        if token is not None:
            token.invalidate()

    # -- data / filtering ----------------------------------------------------

    @objc.python_method
    def _ensure_ready(self) -> None:
        try:
            self._store.ensure_dir()
        except NotesDirectoryError as exc:
            self._alert("Cannot access notes folder", str(exc))

    @objc.python_method
    def _all_notes(self) -> list:
        try:
            return self._store.list_notes()
        except StorageError as exc:
            self._alert("Could not load notes", str(exc))
            return []

    @objc.python_method
    def _apply_filter(self) -> None:
        all_notes = self._all_notes()
        self._update_counts(all_notes)

        if self._query:
            results = search_notes(
                all_notes,
                self._query,
                category=None if self._category == ALL_NOTES else self._category,
            )
            displayed = [r.note for r in results]
            header = "Results"
            n = len(displayed)
            subtitle = f'{n} note{"s" if n != 1 else ""} matching "{self._query}"'
        else:
            displayed = filter_by_category(all_notes, self._category)
            header = self._category
            n = len(displayed)
            subtitle = f'{n} note{"s" if n != 1 else ""}'

        self._displayed = displayed
        self._note_list.set_notes(displayed, header=header, subtitle=subtitle)
        self._sidebar.set_active_category(self._category)

        selected = choose_selected_note(displayed, self._current_id)
        if selected is not None:
            self._current_id = selected.id
            self._prefs.last_note_id = selected.id
            self._note_list.select_note_id(selected.id, notify=False)
            self._editor.load_note(selected)
            self._autosave.reset()
            self._empty.hide()
        else:
            self._current_id = None
            self._editor.clear()
            if self._query:
                self._empty.set_mode(es.NO_RESULTS)
            elif not all_notes:
                self._empty.set_mode(es.NO_NOTES)
            else:
                self._empty.set_mode(es.NO_SELECTION)

    @objc.python_method
    def _update_counts(self, all_notes: list) -> None:
        counts = {ALL_NOTES: len(all_notes)}
        for category in CATEGORIES:
            counts[category] = sum(1 for n in all_notes if n.category == category)
        self._sidebar.set_counts(counts)

    @objc.python_method
    def _displayed_by_id(self, note_id: str):
        return next((n for n in self._displayed if n.id == note_id), None)

    # -- callbacks from views ------------------------------------------------

    @objc.python_method
    def _on_category(self, category: str) -> None:
        self._autosave.flush()
        self._category = category
        if category == ALL_NOTES or category in CATEGORIES:
            self._prefs.last_category = category
        self._apply_filter()

    @objc.python_method
    def _on_note_selected(self, note_id: str) -> None:
        if note_id == self._current_id:
            return
        self._autosave.flush()
        note = self._displayed_by_id(note_id)
        if note is None:
            try:
                note = self._store.load_note(note_id)
            except NoteNotFoundError:
                self._apply_filter()
                return
        self._current_id = note_id
        self._prefs.last_note_id = note_id
        self._editor.load_note(note)
        self._autosave.reset()
        self._empty.hide()

    @objc.python_method
    def _on_title_edited(self, _text: str) -> None:
        self._autosave.note_edited()
        self._editor.set_status(SaveStatus.SAVING)

    @objc.python_method
    def _on_body_edited(self, _text: str) -> None:
        self._autosave.note_edited()
        self._editor.set_status(SaveStatus.SAVING)

    @objc.python_method
    def _perform_save(self) -> None:
        if self._current_id is None:
            return
        note = self._displayed_by_id(self._current_id)
        if note is None:
            return
        now = now_local()
        note.set_title(self._editor.title_text(), now)
        note.set_body(self._editor.body_text(), now)
        try:
            self._store.save_note(note)
        except StorageError as exc:
            self._editor.set_status(SaveStatus.FAILED)
            self._alert("Save failed", str(exc))
            return
        self._editor.set_status(SaveStatus.SAVED)
        self._note_list.set_notes(
            self._displayed,
            header="Results" if self._query else self._category,
            subtitle=self._note_list_subtitle(),
        )

    @objc.python_method
    def _note_list_subtitle(self) -> str:
        n = len(self._displayed)
        if self._query:
            return f'{n} note{"s" if n != 1 else ""} matching "{self._query}"'
        return f'{n} note{"s" if n != 1 else ""}'

    # -- actions -------------------------------------------------------------

    @objc.IBAction
    def newNote_(self, sender):  # noqa: N802
        self._autosave.flush()
        category = default_new_category(self._category)
        try:
            note = self._store.create_note("Untitled Note", category)
        except StorageError as exc:
            self._alert("Could not create note", str(exc))
            return
        self._current_id = note.id
        self._prefs.last_note_id = note.id
        self._query = ""
        self._sidebar.clear_search()
        self._apply_filter()
        self._editor.focus_title()

    @objc.IBAction
    def saveNote_(self, sender):  # noqa: N802
        self._autosave.flush()

    @objc.IBAction
    def focusSearch_(self, sender):  # noqa: N802
        self._window.makeFirstResponder_(self._sidebar.search_field)

    # -- search field delegate -----------------------------------------------

    def controlTextDidChange_(self, notification):  # noqa: N802
        if notification.object() is self._sidebar.search_field:
            self._autosave.flush()
            self._query = str(self._sidebar.search_field.stringValue()).strip()
            self._apply_filter()

    def control_textView_doCommandBySelector_(self, control, textView, selector):  # noqa: N802
        if control is self._sidebar.search_field and str(selector) == "cancelOperation:":
            self._sidebar.clear_search()
            self._query = ""
            self._apply_filter()
            return True
        return False

    # -- window delegate / lifecycle -----------------------------------------

    def windowShouldClose_(self, sender):  # noqa: N802
        self.flush()
        return True

    @objc.python_method
    def flush(self) -> None:
        """Persist any pending edit (selection change / window close / quit)."""
        self._autosave.flush()

    @objc.python_method
    def smoke_summary(self) -> str:
        """One-line runtime introspection (used by ``python -m stormpad --smoke``)."""
        sel = next((n for n in self._displayed if n.id == self._current_id), None)
        counts = {"All": len(self._store.list_notes())}
        parts = [
            f"displayed={len(self._displayed)}",
            f"category={self._category!r}",
            f"query={self._query!r}",
            f"selected={sel.title if sel else None!r}",
            f"transcript_blocks={len(sel.transcript) if sel else 0}",
            f"all_notes={counts['All']}",
        ]
        return "SMOKE OK: " + "  ".join(parts)

    @objc.python_method
    def show(self) -> None:
        self._window.makeKeyAndOrderFront_(None)

    # -- helpers -------------------------------------------------------------

    @objc.python_method
    def _alert(self, title: str, message: str) -> None:
        alert = NSAlert.alloc().init()
        alert.setMessageText_(title)
        alert.setInformativeText_(message)
        alert.runModal()


def make_store() -> NoteStore:
    """Build the NoteStore, honoring the STORMPAD_NOTES_DIR dev/test override."""
    override = os.environ.get("STORMPAD_NOTES_DIR")
    notes_dir = Path(override) if override else paths.notes_dir()
    return NoteStore(notes_dir)
