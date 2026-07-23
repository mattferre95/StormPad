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
    NSAlertSecondButtonReturn,
    NSAppearance,
    NSAppearanceNameAqua,
    NSAppearanceNameDarkAqua,
    NSBackingStoreBuffered,
    NSButton,
    NSColor,
    NSFont,
    NSImage,
    NSImageLeft,
    NSImageOnly,
    NSPasteboard,
    NSPasteboardTypeString,
    NSSplitViewController,
    NSSplitViewDividerStyleThin,
    NSSplitViewItem,
    NSStackView,
    NSTimer,
    NSUserInterfaceLayoutOrientationHorizontal,
    NSViewController,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskFullSizeContentView,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
    NSWindowTitleHidden,
    NSWorkspace,
)
from Foundation import NSURL, NSMakeRect, NSObject

from . import paths
from .defaults import UserDefaultsBackend
from .errors import NoteNotFoundError, NotesDirectoryError, StorageError
from .models import ALL_NOTES, CATEGORIES, now_local
from .preferences import Preferences
from .search import filter_by_category, search_notes
from .session import NoteStore
from .speech import SpeechController, SpeechUnavailableError
from .theme import get_theme, menu_state
from .uihelpers import (
    AutosaveController,
    SaveStatus,
    choose_selected_note,
    copy_text,
    default_new_category,
    is_speakable,
)
from .views import empty_state as es
from .views.controls import flipped_view, gradient_view, solid_view
from .views.editor import Editor
from .views.empty_state import EmptyState
from .views.layout import add, pin_edges, set_height, set_width
from .views.note_list import NoteList
from .views.palette import Palette, symbol_image
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
        # STORMPAD_THEME is a dev/test hook to force the initial theme.
        self._theme = get_theme(os.environ.get("STORMPAD_THEME") or self._prefs.theme)
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
        self._speech = SpeechController()
        self._action_buttons: list = []
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

    @objc.python_method
    def _toolbar_button(
        self,
        title: str,
        action: str,
        symbol: str,
        *,
        primary: bool = False,
        icon_only: bool = False,
        tint: object | None = None,
    ) -> NSButton:
        p = self._palette
        button = NSButton.alloc().init()
        button.setBordered_(False)
        button.setWantsLayer_(True)
        button.setTarget_(self)
        button.setAction_(action)
        button.setToolTip_(title)
        button.layer().setCornerRadius_(7.0)
        image = symbol_image(symbol, size=12.5, weight="semibold" if primary else "medium")
        if image is not None:
            button.setImage_(image)
            button.setImagePosition_(NSImageOnly if icon_only else NSImageLeft)
            if hasattr(button, "setImageHugsTitle_"):
                button.setImageHugsTitle_(True)
        if not icon_only:
            button.setTitle_(title)
            button.setFont_(NSFont.systemFontOfSize_(12.5))
        if primary:
            button.setContentTintColor_(NSColor.whiteColor())
            button.layer().setBackgroundColor_(p.accent.CGColor())
        else:
            button.setContentTintColor_(tint if tint is not None else p.text_secondary)
            button.layer().setBackgroundColor_(p.toolbar_button_background.CGColor())
            button.layer().setBorderWidth_(1.0)
            button.layer().setBorderColor_(p.border.CGColor())
        button.sizeToFit()
        width = 30.0 if icon_only else float(button.fittingSize().width) + 24.0
        set_width(button, width)
        set_height(button, 30)
        return button

    # -- window / layout -----------------------------------------------------

    @objc.python_method
    def _build_window(self) -> None:
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
        window.setDelegate_(self)
        window.setFrameAutosaveName_("StormPadWindow")
        self._window = window
        self._install_content()
        window.center()
        window.makeKeyAndOrderFront_(None)

    @objc.python_method
    def _install_content(self) -> None:
        """Build (or rebuild, on theme switch) the whole content view tree."""
        p = self._palette
        window = self._window

        # Per-theme appearance keeps traffic lights, cursor, selection, and
        # scrollbars consistent with the theme.
        appearance = NSAppearance.appearanceNamed_(
            NSAppearanceNameDarkAqua if self._theme.is_dark else NSAppearanceNameAqua
        )
        window.setAppearance_(appearance)
        window.setBackgroundColor_(p.app_background)

        top, bottom = p.window_gradient()
        root = gradient_view(top, bottom)

        # Header bar + action toolbar (right-aligned).
        header = add(root, solid_view(p.header_background))
        pin_edges(header, root, top=0, leading=0, trailing=0, bottom=None)
        set_height(header, _HEADER_HEIGHT)
        header_line = add(root, solid_view(p.separator))
        pin_edges(header_line, root, top=_HEADER_HEIGHT, leading=0, trailing=0, bottom=None)
        set_height(header_line, 1)

        copy_b = self._toolbar_button(
            "Copy Note", "copyNote:", "doc.on.doc", tint=p.accent_strong
        )
        append_b = self._toolbar_button("Append Transcript", "appendTranscript:", "waveform")
        open_b = self._toolbar_button(
            "Open File", "openFile:", "arrow.up.forward.square", icon_only=True
        )
        reveal_b = self._toolbar_button(
            "Reveal in Finder", "revealInFinder:", "folder", icon_only=True
        )
        delete_b = self._toolbar_button(
            "Delete Note", "deleteNote:", "trash", icon_only=True, tint=p.danger
        )
        new_b = self._toolbar_button("New Note", "newNote:", "plus", primary=True)
        self._action_buttons = [copy_b, append_b, open_b, reveal_b, delete_b]

        stack = NSStackView.alloc().init()
        stack.setOrientation_(NSUserInterfaceLayoutOrientationHorizontal)
        stack.setSpacing_(7.0)
        for button in [copy_b, append_b, open_b, reveal_b, delete_b, new_b]:
            stack.addArrangedSubview_(button)
        add(header, stack)
        stack.trailingAnchor().constraintEqualToAnchor_constant_(
            header.trailingAnchor(), -16.0
        ).setActive_(True)
        stack.centerYAnchor().constraintEqualToAnchor_(header.centerYAnchor()).setActive_(True)

        # Three-column split.
        self._sidebar = Sidebar(
            self._palette, self._logo, on_category=self._on_category, search_delegate=self
        )
        self._note_list = NoteList.alloc().initWithPalette_onSelect_(
            self._palette, self._on_note_selected
        )
        self._editor = Editor.alloc().initWithPalette_onTitle_onBody_(
            self._palette, self._on_title_edited, self._on_body_edited
        )
        self._editor.speech_target = self
        self._editor.set_transcript_append_target(self, "appendTranscript:")

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
        pin_edges(split.view(), root, top=_HEADER_HEIGHT + 1, leading=0, trailing=0, bottom=0)

        window.setContentView_(root)
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
        self._update_actions_enabled()

    @objc.python_method
    def _update_actions_enabled(self) -> None:
        enabled = self._current_id is not None
        for button in self._action_buttons:
            button.setEnabled_(enabled)
            button.setAlphaValue_(1.0 if enabled else 0.4)

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
        self._speech.stop()  # stop speech when switching notes
        note = self._displayed_by_id(note_id)
        if note is None:
            try:
                note = self._store.load_note(note_id)
            except NoteNotFoundError:
                self._handle_missing_note()
                return
        self._current_id = note_id
        self._prefs.last_note_id = note_id
        self._editor.load_note(note)
        self._autosave.reset()
        self._empty.hide()
        self._update_actions_enabled()

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

    @objc.IBAction
    def copyNote_(self, sender):  # noqa: N802
        note = self._selected_note_or_none()
        if note is None:
            return
        pasteboard = NSPasteboard.generalPasteboard()
        pasteboard.clearContents()
        if pasteboard.setString_forType_(copy_text(note), NSPasteboardTypeString):
            self._editor.flash_status("Copied")
        else:
            self._alert("Copy failed", "Could not write the note to the clipboard.")

    @objc.IBAction
    def appendTranscript_(self, sender):  # noqa: N802
        if self._current_id is None:
            return
        self._autosave.flush()
        try:
            note = self._store.append_test_transcript(self._current_id)
        except NoteNotFoundError:
            self._handle_missing_note()
            return
        except StorageError as exc:
            self._alert("Could not append transcript", str(exc))
            return
        self._replace_displayed(note)
        self._editor.load_note(note)
        self._autosave.reset()
        self._note_list.set_notes(
            self._displayed,
            header="Results" if self._query else self._category,
            subtitle=self._note_list_subtitle(),
        )

    @objc.IBAction
    def openFile_(self, sender):  # noqa: N802
        note = self._selected_note_or_none()
        if note is None:
            return
        self._autosave.flush()
        if not note.path.exists():
            self._handle_missing_note()
            return
        url = NSURL.fileURLWithPath_(str(note.path))
        if not NSWorkspace.sharedWorkspace().openURL_(url):
            self._alert("Could not open file", f"macOS could not open {note.path.name}.")

    @objc.IBAction
    def revealInFinder_(self, sender):  # noqa: N802
        note = self._selected_note_or_none()
        if note is None:
            return
        self._autosave.flush()
        if not note.path.exists():
            self._handle_missing_note()
            return
        url = NSURL.fileURLWithPath_(str(note.path))
        NSWorkspace.sharedWorkspace().activateFileViewerSelectingURLs_([url])

    @objc.IBAction
    def deleteNote_(self, sender):  # noqa: N802
        note = self._selected_note_or_none()
        if note is None:
            return
        self._autosave.reset()  # discard pending edits; the note is going away
        if not self._confirm_delete(note.title or "Untitled Note"):
            return
        self._speech.stop()  # stop if this note was being spoken
        try:
            self._store.delete_note(note.id)  # injectable strategy -> macOS Trash
        except NoteNotFoundError:
            self._handle_missing_note()
            return
        except StorageError as exc:
            self._alert("Couldn’t move to Trash", str(exc))  # keep note in the UI
            return
        if self._prefs.last_note_id == note.id:
            self._prefs.last_note_id = None
        self._current_id = None
        self._apply_filter()

    @objc.IBAction
    def speakSelection_(self, sender):  # noqa: N802
        text = self._editor.selected_body_text()
        if not is_speakable(text):
            return
        try:
            self._speech.speak(text)
        except SpeechUnavailableError as exc:
            self._alert("Speech unavailable", str(exc))

    @objc.IBAction
    def stopSpeaking_(self, sender):  # noqa: N802
        self._speech.stop()

    @objc.IBAction
    def selectTheme_(self, sender):  # noqa: N802
        theme_id = sender.representedObject()
        if theme_id is None or theme_id == self._theme.id:
            return
        self._autosave.flush()
        was_focused = self._editor.body_is_first_responder()
        selection = self._editor.body_selected_range()

        self._prefs.theme = theme_id  # persists; validated
        self._theme = get_theme(theme_id)
        self._palette = Palette(self._theme)

        self._install_content()  # rebuild the whole tree -> no stale colors
        self._apply_filter()  # repopulate + load current note into new editor

        if self._current_id is not None:
            self._editor.restore_selection(selection)
            if was_focused:
                self._editor.focus_body()

    def validateMenuItem_(self, item):  # noqa: N802
        name = str(item.action())
        note_actions = (
            "copyNote:",
            "appendTranscript:",
            "openFile:",
            "revealInFinder:",
            "deleteNote:",
        )
        if name in note_actions:
            return self._current_id is not None
        if name == "speakSelection:":
            return is_speakable(self._editor.selected_body_text())
        if name == "stopSpeaking:":
            return self._speech.is_speaking
        if name == "selectTheme:":
            item.setState_(menu_state(item.representedObject(), self._theme.id))
            return True
        return True

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
        self.cleanup()
        return True

    @objc.python_method
    def flush(self) -> None:
        """Persist any pending edit (selection change / window close / quit)."""
        self._autosave.flush()

    @objc.python_method
    def cleanup(self) -> None:
        """Stop speech and flush pending edits (window close / app quit)."""
        self._speech.cleanup()
        self._autosave.flush()

    # -- Phase 4 action helpers ----------------------------------------------

    @objc.python_method
    def _selected_note_or_none(self):
        if self._current_id is None:
            return None
        return self._displayed_by_id(self._current_id)

    @objc.python_method
    def _replace_displayed(self, note) -> None:
        for i, existing in enumerate(self._displayed):
            if existing.id == note.id:
                self._displayed[i] = note
                return

    @objc.python_method
    def _confirm_delete(self, title: str) -> bool:
        alert = NSAlert.alloc().init()
        alert.setMessageText_(f"Delete “{title}”?")
        alert.setInformativeText_("This note will be moved to the Trash.")
        alert.addButtonWithTitle_("Cancel")  # first button = default (safe)
        delete_button = alert.addButtonWithTitle_("Delete")
        if hasattr(delete_button, "setHasDestructiveAction_"):
            delete_button.setHasDestructiveAction_(True)
        return alert.runModal() == NSAlertSecondButtonReturn

    @objc.python_method
    def _handle_missing_note(self) -> None:
        self._speech.stop()
        if self._prefs.last_note_id == self._current_id:
            self._prefs.last_note_id = None
        self._current_id = None
        self._alert(
            "Note not found",
            "This note no longer exists on disk. The list has been refreshed.",
        )
        self._apply_filter()

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


def trash_file(path: Path) -> None:
    """Delete strategy that moves a file to the macOS Trash (Finder semantics).

    Raises :class:`StorageError` on failure so the UI can keep the note and show
    an error. This is the Phase-4 injection into the Phase-2 delete seam.
    """
    from Foundation import NSFileManager

    url = NSURL.fileURLWithPath_(str(path))
    ok, _resulting, error = NSFileManager.defaultManager().trashItemAtURL_resultingItemURL_error_(
        url, None, None
    )
    if not ok:
        detail = error.localizedDescription() if error is not None else "unknown error"
        raise StorageError(f"could not move to Trash: {detail}")


def make_store() -> NoteStore:
    """Build the NoteStore, honoring the STORMPAD_NOTES_DIR dev/test override.

    Uses the macOS-Trash delete strategy so deletions are recoverable from
    Finder rather than permanent.
    """
    override = os.environ.get("STORMPAD_NOTES_DIR")
    notes_dir = Path(override) if override else paths.notes_dir()
    return NoteStore(notes_dir, delete_strategy=trash_file)
