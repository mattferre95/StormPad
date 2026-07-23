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
    NSBitmapImageFileTypePNG,
    NSButton,
    NSColor,
    NSFont,
    NSImage,
    NSImageLeft,
    NSImageOnly,
    NSMenu,
    NSMenuItem,
    NSModalResponseOK,
    NSOpenPanel,
    NSPasteboard,
    NSPasteboardTypeString,
    NSSavePanel,
    NSSplitViewController,
    NSSplitViewDividerStyleThin,
    NSSplitViewItem,
    NSStackView,
    NSTextField,
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
from Foundation import NSURL, NSMakeRect, NSObject, NSRunLoop, NSRunLoopCommonModes

from . import attachments, paths
from .blocks import Block, BlockType, InlineRun
from .defaults import UserDefaultsBackend
from .errors import (
    InvalidProjectError,
    NoteNotFoundError,
    NotesDirectoryError,
    ProjectNotFoundError,
    StorageError,
)
from .exporter import export_note_txt, note_to_plain_text
from .models import (
    ALL_NOTES,
    CATEGORIES,
    UNFILED,
    UNFILED_PROJECT_ID,
    now_local,
)
from .preferences import Preferences
from .search import filter_by_category, filter_by_project, search_notes
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
    word_count,
)
from .views import empty_state as es
from .views.controls import flipped_view, gradient_view, solid_view
from .views.editor import Editor
from .views.empty_state import EmptyState
from .views.layout import add, pin_edges, set_height, set_width
from .views.note_list import NoteList
from .views.palette import Palette, symbol_image
from .views.settings import SettingsController
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
        self._prefs = Preferences(
            UserDefaultsBackend(
                os.environ.get("STORMPAD_DEFAULTS_SUITE") or "com.stormpad.StormPad"
            )
        )
        # STORMPAD_THEME is a dev/test hook to force the initial theme.
        self._theme = get_theme(os.environ.get("STORMPAD_THEME") or self._prefs.theme)
        self._palette = Palette(self._theme)
        self._logo = self._load_logo()

        self._category = self._prefs.last_category
        self._project_id = self._prefs.selected_project_id
        self._query = os.environ.get("STORMPAD_INITIAL_QUERY", "").strip()
        self._current_id: str | None = self._prefs.last_note_id
        self._displayed: list = []
        self._dev_notes_collapsed = True if os.environ.get("STORMPAD_COLLAPSE_NOTES") else None

        self._autosave = AutosaveController(
            self._perform_save,
            delay=_AUTOSAVE_DELAY,
            schedule=self._schedule_timer,
            cancel=self._cancel_timer,
        )
        self._speech = SpeechController()
        self._action_buttons: list = []
        self._note_info_menu = None
        self._settings = SettingsController.alloc().initWithOnTheme_onBlockControls_onReveal_(
            self._set_theme,
            self._set_block_controls,
            self._reveal_notes_folder,
        )
        self._build_window()
        self._ensure_ready()
        self._apply_filter()
        if os.environ.get("STORMPAD_FOCUS_EDITOR"):
            NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                0.3, False, lambda timer: self._apply_editor_dev_focus()
            )
        if os.environ.get("STORMPAD_SHOW_SETTINGS"):
            NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                0.2, False, lambda timer: self.showSettings_(None)
            )
        if os.environ.get("STORMPAD_HOVER_BLOCK"):
            NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                0.4, False, lambda timer: self._apply_hover_dev_hook()
            )
        if os.environ.get("STORMPAD_SHOW_NOTE_INFO"):
            NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                0.25,
                False,
                lambda timer: self.showNoteInfo_(self._action_buttons[0]),
            )
        if os.environ.get("STORMPAD_SHOW_EXPORT"):
            NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                0.25, False, lambda timer: self.exportNoteTXT_(None)
            )
        if os.environ.get("STORMPAD_CREATE_PROJECT_DIALOG"):
            NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                0.25, False, lambda timer: self.createProject_(None)
            )
        if os.environ.get("STORMPAD_SELECT_PROJECT"):
            NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                0.15, False, lambda timer: self._apply_project_dev_hook()
            )
        if os.environ.get("STORMPAD_SELECT_NOTE"):
            NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                0.2, False, lambda timer: self._apply_note_dev_hook()
            )
        if os.environ.get("STORMPAD_SHOW_MOVE_PROJECT_MENU"):
            NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                0.25, False, lambda timer: self._show_move_project_dev_menu()
            )
        if os.environ.get("STORMPAD_SELECT_ALL_NOTE"):
            NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                0.4, False, lambda timer: self._editor.select_all_note_content()
            )
        if os.environ.get("STORMPAD_DELETE_ALL_NOTE"):
            NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                0.45, False, lambda timer: self._apply_delete_all_dev_hook()
            )
        if os.environ.get("STORMPAD_CAPTURE_PATH"):
            capture_timer = NSTimer.timerWithTimeInterval_repeats_block_(
                0.8, False, lambda timer: self._capture_dev_windows()
            )
            NSRunLoop.mainRunLoop().addTimer_forMode_(
                capture_timer, NSRunLoopCommonModes
            )
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
        button.setAccessibilityLabel_(title)
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

        collapse_b = self._toolbar_button(
            "Toggle Notes", "toggleNotesPanel:", "sidebar.right", icon_only=True
        )
        info_b = self._toolbar_button(
            "Open Note Info", "showNoteInfo:", "ellipsis.circle", icon_only=True
        )
        new_b = self._toolbar_button("New Note", "newNote:", "plus", primary=True)
        self._action_buttons = [info_b]

        stack = NSStackView.alloc().init()
        stack.setOrientation_(NSUserInterfaceLayoutOrientationHorizontal)
        stack.setSpacing_(7.0)
        for button in [collapse_b, info_b, new_b]:
            stack.addArrangedSubview_(button)
        add(header, stack)
        stack.trailingAnchor().constraintEqualToAnchor_constant_(
            header.trailingAnchor(), -16.0
        ).setActive_(True)
        stack.centerYAnchor().constraintEqualToAnchor_(header.centerYAnchor()).setActive_(True)

        # Three-column split.
        self._sidebar = Sidebar(
            self._palette,
            self._logo,
            on_category=self._on_category,
            on_project=self._on_project,
            search_delegate=self,
            project_action_target=self,
        )
        self._note_list = NoteList.alloc().initWithPalette_onSelect_onCollapse_(
            self._palette, self._on_note_selected, self._toggle_notes_panel
        )
        self._note_list.set_menu_provider(self._note_context_menu)
        self._editor = Editor.alloc().initWithPalette_onTitle_onBody_onAttachment_(
            self._palette,
            self._on_title_edited,
            self._on_body_edited,
            self._attachment_block,
        )
        self._editor.speech_target = self
        self._editor.transcript_target = self
        self._editor.notes_dir = self._store.notes_dir
        self._editor.set_block_controls_enabled(self._prefs.show_block_controls)

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
        self._list_item = list_item
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
        self._apply_notes_panel_state()

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

    @objc.python_method
    def _apply_editor_dev_focus(self) -> None:
        """Sanitized screenshot hook; never enabled in a normal launch."""
        if self._current_id is None:
            return
        self._editor.focus_body()
        raw_selection = os.environ.get("STORMPAD_EDITOR_SELECTION", "")
        if raw_selection:
            try:
                location, length = (int(part.strip()) for part in raw_selection.split(",", 1))
                self._editor.restore_selection((location, length))
            except (TypeError, ValueError):
                pass
        if os.environ.get("STORMPAD_SHOW_BLOCK_MENU"):
            NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                0.1,
                False,
                lambda timer: self._editor.showBlockMenu_(self._editor._plus),
            )
        color_mode = os.environ.get("STORMPAD_SHOW_COLOR_MENU", "").strip()
        if color_mode in {"text", "highlight"}:
            NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                0.1,
                False,
                lambda timer: self._editor._show_color_menu(self._editor._plus, color_mode),
            )

    @objc.python_method
    def _apply_hover_dev_hook(self) -> None:
        try:
            index = int(os.environ.get("STORMPAD_HOVER_BLOCK", "0"))
        except ValueError:
            index = 0
        self._editor.show_block_hover(index)

    @objc.python_method
    def _apply_project_dev_hook(self) -> None:
        requested = os.environ.get("STORMPAD_SELECT_PROJECT", "")
        project = next(
            (
                item
                for item in self._projects()
                if item.id == requested or item.name == requested
            ),
            None,
        )
        if project is not None:
            self._on_project(project.id)

    @objc.python_method
    def _apply_note_dev_hook(self) -> None:
        requested = os.environ.get("STORMPAD_SELECT_NOTE", "")
        note = next(
            (
                item
                for item in self._store.list_notes()
                if item.id == requested or item.title == requested
            ),
            None,
        )
        if note is not None:
            self._on_note_selected(note.id)

    @objc.python_method
    def _show_move_project_dev_menu(self) -> None:
        note = self._selected_note_or_none()
        if note is None:
            return
        menu = self._move_to_project_item(note).submenu()
        menu.popUpMenuPositioningItem_atLocation_inView_(
            None, (0.0, 0.0), self._action_buttons[0]
        )

    @objc.python_method
    def _apply_delete_all_dev_hook(self) -> None:
        self._editor.select_all_note_content()
        self._editor.clear_note_content()

    @objc.python_method
    def _capture_dev_windows(self) -> None:
        """Render only this process's visible AppKit windows for safe fixtures."""
        from AppKit import NSApplication

        requested = Path(os.environ["STORMPAD_CAPTURE_PATH"])
        windows = [
            window
            for window in NSApplication.sharedApplication().windows()
            if window.isVisible() and window.contentView() is not None
        ]
        for index, window in enumerate(windows):
            view = window.contentView()
            bounds = view.bounds()
            image = view.bitmapImageRepForCachingDisplayInRect_(bounds)
            if image is None:
                continue
            view.cacheDisplayInRect_toBitmapImageRep_(bounds, image)
            data = image.representationUsingType_properties_(
                NSBitmapImageFileTypePNG, {}
            )
            if data is None:
                continue
            path = (
                requested
                if len(windows) == 1
                else requested.with_name(
                    f"{requested.stem}-{index + 1}{requested.suffix}"
                )
            )
            data.writeToFile_atomically_(str(path), True)
            print(path, flush=True)
        if os.environ.get("STORMPAD_CAPTURE_AND_QUIT"):
            NSApplication.sharedApplication().terminate_(None)

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
        except (OSError, StorageError) as exc:
            self._alert("Could not load notes", str(exc))
            return []

    @objc.python_method
    def _projects(self) -> list:
        try:
            projects = self._store.list_projects()
        except (OSError, StorageError) as exc:
            self._alert("Could not load projects", str(exc))
            return []
        by_id = {project.id: project for project in projects}
        ordered = [
            by_id[project_id]
            for project_id in self._prefs.project_order
            if project_id in by_id
        ]
        ordered_ids = {project.id for project in ordered}
        ordered.extend(
            project for project in projects if project.id not in ordered_ids
        )
        current_order = [project.id for project in ordered]
        if current_order != self._prefs.project_order:
            self._prefs.project_order = current_order
        return ordered

    def _validated_project_id(self, projects) -> str | None:
        if self._project_id in (None, UNFILED_PROJECT_ID):
            return self._project_id
        if any(project.id == self._project_id for project in projects):
            return self._project_id
        self._project_id = None
        self._prefs.selected_project_id = None
        return None

    def _navigation_header(self, projects) -> str:
        if self._project_id == UNFILED_PROJECT_ID:
            return UNFILED
        if self._project_id:
            project = next(
                (item for item in projects if item.id == self._project_id),
                None,
            )
            if project is not None:
                return project.name
        return self._category

    @objc.python_method
    def _apply_filter(self) -> None:
        all_notes = self._all_notes()
        projects = self._projects()
        self._project_id = self._validated_project_id(projects)
        counts = self._update_counts(all_notes, projects)

        if self._query:
            results = search_notes(
                all_notes,
                self._query,
                category=None if self._category == ALL_NOTES else self._category,
                project_id=self._project_id,
            )
            displayed = [r.note for r in results]
            header = "Results"
            n = len(displayed)
            subtitle = f'{n} note{"s" if n != 1 else ""} matching "{self._query}"'
        else:
            displayed = filter_by_project(
                filter_by_category(all_notes, self._category),
                self._project_id,
            )
            header = self._navigation_header(projects)
            n = len(displayed)
            subtitle = f"{n} note{'s' if n != 1 else ''}"

        self._displayed = displayed
        self._note_list.set_notes(displayed, header=header, subtitle=subtitle)
        self._sidebar.set_navigation(
            projects,
            counts,
            category=self._category,
            project_id=self._project_id,
            collapsed=self._prefs.projects_collapsed,
        )

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
    def _update_counts(self, all_notes: list, projects: list) -> dict[str, int]:
        counts = {
            ALL_NOTES: len(all_notes),
            UNFILED_PROJECT_ID: sum(
                1 for note in all_notes if note.project_id is None
            ),
        }
        for category in CATEGORIES:
            counts[category] = sum(1 for n in all_notes if n.category == category)
        for project in projects:
            counts[project.id] = sum(
                1 for note in all_notes if note.project_id == project.id
            )
        return counts

    @objc.python_method
    def _displayed_by_id(self, note_id: str):
        return next((n for n in self._displayed if n.id == note_id), None)

    # -- callbacks from views ------------------------------------------------

    @objc.python_method
    def _on_category(self, category: str) -> None:
        self._autosave.flush()
        self._category = category
        self._project_id = None
        self._prefs.selected_project_id = None
        if category == ALL_NOTES or category in CATEGORIES:
            self._prefs.last_category = category
        self._apply_filter()

    @objc.python_method
    def _on_project(self, project_id: str | None) -> None:
        self._autosave.flush()
        self._project_id = project_id
        self._category = ALL_NOTES
        self._prefs.last_category = ALL_NOTES
        self._prefs.selected_project_id = project_id
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
        self._note_list.select_note_id(note_id, notify=False)
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
        save_id = self._current_id
        note = self._displayed_by_id(save_id)
        if note is None:
            return
        now = now_local()
        note.set_title(self._editor.title_text().strip() or "Untitled Note", now)
        note.set_body(self._editor.body_text(), now)
        visible, collapsed = self._editor.transcript_state()
        note.transcript_visible = visible
        note.transcript_collapsed = collapsed
        # A stale debounce callback must never write editor content into a note
        # selected after this save began.
        if self._current_id != save_id:
            return
        try:
            self._store.save_note(
                note,
                commit_title=note.metadata.get("Filename-Mode") != "manual",
            )
        except StorageError as exc:
            self._editor.set_status(SaveStatus.FAILED)
            self._alert("Save failed", str(exc))
            return
        self._editor.set_status(SaveStatus.SAVED)
        self._note_list.set_notes(
            self._displayed,
            header=(
                "Results"
                if self._query
                else self._navigation_header(self._projects())
            ),
            subtitle=self._note_list_subtitle(),
        )
        self._note_list.select_note_id(save_id, notify=False)

    @objc.python_method
    def _note_list_subtitle(self) -> str:
        n = len(self._displayed)
        if self._query:
            return f'{n} note{"s" if n != 1 else ""} matching "{self._query}"'
        return f"{n} note{'s' if n != 1 else ''}"

    # -- actions -------------------------------------------------------------

    @objc.IBAction
    def newNote_(self, sender):  # noqa: N802
        self._autosave.flush()
        category = default_new_category(self._category)
        project_id = (
            self._project_id
            if self._project_id not in (None, UNFILED_PROJECT_ID)
            else None
        )
        try:
            note = self._store.create_note(
                "Untitled Note",
                category,
                project_id=project_id,
            )
        except (ProjectNotFoundError, StorageError) as exc:
            self._alert("Could not create note", str(exc))
            return
        self._current_id = note.id
        self._prefs.last_note_id = note.id
        self._query = ""
        self._sidebar.clear_search()
        self._apply_filter()
        self._editor.focus_title()

    def _represented_string(self, sender) -> str | None:
        if sender is None or not hasattr(sender, "representedObject"):
            return None
        value = sender.representedObject()
        return str(value) if value is not None else None

    @objc.IBAction
    def createProject_(self, sender):  # noqa: N802
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Create Project")
        alert.setInformativeText_(
            "Projects group related notes in a real local folder."
        )
        field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 340, 24))
        field.setPlaceholderString_("Project name")
        field.setAccessibilityLabel_("Project name")
        alert.setAccessoryView_(field)
        alert.addButtonWithTitle_("Create")
        alert.addButtonWithTitle_("Cancel")
        if alert.runModal() != 1000:
            return
        try:
            project = self._store.create_project(str(field.stringValue()))
        except (InvalidProjectError, StorageError) as exc:
            self._alert("Could not create project", str(exc))
            return
        order = self._prefs.project_order
        self._prefs.project_order = [*order, project.id]
        self._project_id = project.id
        self._category = ALL_NOTES
        self._prefs.selected_project_id = project.id
        self._prefs.last_category = ALL_NOTES
        self._apply_filter()

    @objc.IBAction
    def toggleProjectsSection_(self, sender):  # noqa: N802
        self._prefs.projects_collapsed = not self._prefs.projects_collapsed
        self._apply_filter()

    @objc.IBAction
    def newNoteInProject_(self, sender):  # noqa: N802
        project_id = self._represented_string(sender)
        if project_id is None:
            return
        self._on_project(project_id)
        self.newNote_(sender)

    @objc.IBAction
    def renameProject_(self, sender):  # noqa: N802
        project_id = self._represented_string(sender)
        if project_id is None:
            return
        try:
            project = self._store.load_project(project_id)
        except ProjectNotFoundError as exc:
            self._alert("Project not found", str(exc))
            self._apply_filter()
            return
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Rename Project")
        alert.setInformativeText_(
            "The project folder will be renamed safely; note IDs and attachments stay unchanged."
        )
        field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 340, 24))
        field.setStringValue_(project.name)
        field.setAccessibilityLabel_("Project name")
        alert.setAccessoryView_(field)
        alert.addButtonWithTitle_("Rename")
        alert.addButtonWithTitle_("Cancel")
        if alert.runModal() != 1000:
            return
        self._autosave.flush()
        try:
            self._store.rename_project(project.id, str(field.stringValue()))
        except (InvalidProjectError, StorageError, OSError) as exc:
            self._alert("Could not rename project", str(exc))
            return
        self._apply_filter()

    @objc.IBAction
    def revealProject_(self, sender):  # noqa: N802
        project_id = self._represented_string(sender)
        if project_id is None:
            return
        try:
            project = self._store.load_project(project_id)
        except ProjectNotFoundError as exc:
            self._alert("Project not found", str(exc))
            self._apply_filter()
            return
        NSWorkspace.sharedWorkspace().activateFileViewerSelectingURLs_(
            [NSURL.fileURLWithPath_(str(project.path))]
        )

    @objc.IBAction
    def deleteProject_(self, sender):  # noqa: N802
        project_id = self._represented_string(sender)
        if project_id is None:
            return
        self._autosave.flush()
        try:
            project = self._store.load_project(project_id)
            note_count = sum(
                1
                for note in self._store.list_notes()
                if note.project_id == project.id
            )
        except (ProjectNotFoundError, StorageError) as exc:
            self._alert("Project not found", str(exc))
            self._apply_filter()
            return
        alert = NSAlert.alloc().init()
        alert.setMessageText_(f"Delete “{project.name}”?")
        if note_count:
            alert.setInformativeText_(
                f"{note_count} note{'s' if note_count != 1 else ''} will be moved to Unfiled. "
                "No note or attachment will be deleted."
            )
            alert.addButtonWithTitle_("Cancel")
            action = alert.addButtonWithTitle_(
                "Move Notes to Unfiled and Delete Project"
            )
        else:
            alert.setInformativeText_(
                "The empty project folder will be moved to Trash."
            )
            alert.addButtonWithTitle_("Cancel")
            action = alert.addButtonWithTitle_("Delete Project")
        if hasattr(action, "setHasDestructiveAction_"):
            action.setHasDestructiveAction_(True)
        if alert.runModal() != NSAlertSecondButtonReturn:
            return
        try:
            self._store.delete_project(
                project.id,
                move_notes_to_unfiled=bool(note_count),
            )
        except (StorageError, OSError) as exc:
            self._alert("Could not delete project", str(exc))
            return
        self._prefs.project_order = [
            value
            for value in self._prefs.project_order
            if value != project.id
        ]
        if self._project_id == project.id:
            self._project_id = UNFILED_PROJECT_ID if note_count else None
            self._prefs.selected_project_id = self._project_id
        self._apply_filter()

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
            header=(
                "Results"
                if self._query
                else self._navigation_header(self._projects())
            ),
            subtitle=self._note_list_subtitle(),
        )
        self._note_list.select_note_id(note.id, notify=False)

    @objc.IBAction
    def toggleNotesPanel_(self, sender):  # noqa: N802
        self._toggle_notes_panel()

    @objc.python_method
    def _toggle_notes_panel(self) -> None:
        collapsed = self._notes_panel_collapsed()
        self._dev_notes_collapsed = None
        self._prefs.notes_list_collapsed = not collapsed
        self._apply_notes_panel_state()

    @objc.python_method
    def _apply_notes_panel_state(self) -> None:
        collapsed = self._notes_panel_collapsed()
        self._note_list.set_collapsed(collapsed)
        width = 46.0 if collapsed else _LIST_WIDTH
        self._list_item.setMinimumThickness_(width if collapsed else 260.0)
        self._list_item.setMaximumThickness_(width if collapsed else 440.0)
        self._split_vc.splitView().setPosition_ofDividerAtIndex_(_SIDEBAR_WIDTH + width, 1)

    @objc.python_method
    def _notes_panel_collapsed(self) -> bool:
        if self._dev_notes_collapsed is not None:
            return self._dev_notes_collapsed
        return self._prefs.notes_list_collapsed

    @objc.python_method
    def _attachment_block(self, kind: str, source: Path | None):
        note = self._selected_note_or_none()
        if note is None:
            return None
        selected = source
        if selected is None:
            panel = NSOpenPanel.openPanel()
            panel.setCanChooseFiles_(True)
            panel.setCanChooseDirectories_(False)
            panel.setAllowsMultipleSelection_(False)
            panel.setMessage_(
                "Choose an image" if kind == BlockType.IMAGE.value else "Choose a file"
            )
            if panel.runModal() != NSModalResponseOK:
                return None
            selected = Path(str(panel.URL().path()))
        try:
            managed = attachments.import_attachment(selected, self._store.notes_dir, note.id)
        except StorageError as exc:
            self._alert("Could not import attachment", str(exc))
            return None
        relative = attachments.relative_markdown_path(note.path, managed)
        if kind == BlockType.IMAGE.value:
            alt = managed.stem.replace("-", " ").replace("_", " ").strip()
            return Block(
                kind=BlockType.IMAGE,
                runs=[InlineRun(alt)],
                alt=alt,
                target=relative,
            )
        return Block(
            kind=BlockType.FILE,
            runs=[InlineRun(managed.name)],
            target=relative,
        )

    @objc.python_method
    def _move_to_project_item(self, note):
        parent = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Move to Project", None, ""
        )
        submenu = NSMenu.alloc().initWithTitle_("Move to Project")
        projects = self._projects()
        if not projects:
            empty = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "No Projects", None, ""
            )
            empty.setEnabled_(False)
            submenu.addItem_(empty)
        for project in projects:
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                project.name, "moveNoteToProject:", ""
            )
            item.setTarget_(self)
            item.setRepresentedObject_(f"{note.id}|{project.id}")
            item.setState_(1 if note.project_id == project.id else 0)
            submenu.addItem_(item)
        parent.setSubmenu_(submenu)
        return parent

    @objc.python_method
    def _note_context_menu(self, note):
        menu = NSMenu.alloc().initWithTitle_("Note")
        menu.addItem_(self._move_to_project_item(note))
        if note.project_id is not None:
            remove = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Remove from Project", "removeNoteFromProject:", ""
            )
            remove.setTarget_(self)
            remove.setRepresentedObject_(note.id)
            menu.addItem_(remove)
        return menu

    @objc.IBAction
    def moveNoteToProject_(self, sender):  # noqa: N802
        payload = self._represented_string(sender)
        if payload is None or "|" not in payload:
            return
        note_id, project_id = payload.split("|", 1)
        self._autosave.flush()
        try:
            moved = self._store.move_note_to_project(note_id, project_id)
        except (NoteNotFoundError, ProjectNotFoundError, StorageError, OSError) as exc:
            self._alert("Could not move note", str(exc))
            self._apply_filter()
            return
        self._current_id = moved.id
        self._prefs.last_note_id = moved.id
        self._apply_filter()

    @objc.IBAction
    def removeNoteFromProject_(self, sender):  # noqa: N802
        note_id = self._represented_string(sender) or self._current_id
        if note_id is None:
            return
        self._autosave.flush()
        try:
            moved = self._store.remove_note_from_project(note_id)
        except (NoteNotFoundError, StorageError, OSError) as exc:
            self._alert("Could not remove note from project", str(exc))
            self._apply_filter()
            return
        self._current_id = moved.id
        self._prefs.last_note_id = moved.id
        self._apply_filter()

    @objc.IBAction
    def showNoteInfo_(self, sender):  # noqa: N802
        note = self._selected_note_or_none()
        if note is None:
            return
        self._autosave.flush()
        if not hasattr(sender, "bounds"):
            self._show_note_info_alert(note)
            return
        menu = NSMenu.alloc().initWithTitle_("Note Info")

        def info(text: str) -> None:
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(text, None, "")
            item.setEnabled_(False)
            menu.addItem_(item)

        info(f"Filename: {note.path.name}")
        info(f"Path: {note.path}")
        info(f"Created: {note.created_at.isoformat(sep=' ', timespec='seconds')}")
        info(f"Updated: {note.updated_at.isoformat(sep=' ', timespec='seconds')}")
        info(f"Category: {note.category}")
        project = next(
            (
                project
                for project in self._projects()
                if project.id == note.project_id
            ),
            None,
        )
        info(f"Project: {project.name if project is not None else UNFILED}")
        info(f"Words: {word_count(note_to_plain_text(note))}")
        menu.addItem_(NSMenuItem.separatorItem())
        menu.addItem_(self._move_to_project_item(note))
        if note.project_id is not None:
            remove_project = (
                NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    "Remove from Project", "removeNoteFromProject:", ""
                )
            )
            remove_project.setTarget_(self)
            remove_project.setRepresentedObject_(note.id)
            menu.addItem_(remove_project)
        menu.addItem_(NSMenuItem.separatorItem())
        for title, action in (
            ("Rename Filename…", "renameFilename:"),
            ("Export as TXT…", "exportNoteTXT:"),
            ("Reveal in Finder", "revealInFinder:"),
            ("Open Markdown File", "openFile:"),
            ("Settings…", "showSettings:"),
        ):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, "")
            item.setTarget_(self)
            menu.addItem_(item)
        menu.addItem_(NSMenuItem.separatorItem())
        delete = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Delete Note…", "deleteNote:", ""
        )
        delete.setTarget_(self)
        menu.addItem_(delete)
        self._note_info_menu = menu
        menu.popUpMenuPositioningItem_atLocation_inView_(None, (0.0, 0.0), sender)

    @objc.python_method
    def _show_note_info_alert(self, note) -> None:
        project = next(
            (
                project
                for project in self._projects()
                if project.id == note.project_id
            ),
            None,
        )
        alert = NSAlert.alloc().init()
        alert.setMessageText_(note.title or "Untitled Note")
        alert.setInformativeText_(
            f"Filename: {note.path.name}\n"
            f"Full path: {note.path}\n"
            f"Created: {note.created_at.isoformat(sep=' ', timespec='seconds')}\n"
            f"Updated: {note.updated_at.isoformat(sep=' ', timespec='seconds')}\n"
            f"Category: {note.category}\n"
            f"Project: {project.name if project is not None else UNFILED}\n"
            f"Words: {word_count(note_to_plain_text(note))}\n"
            f"Stable ID: {note.id}"
        )
        alert.addButtonWithTitle_("OK")
        alert.runModal()

    @objc.IBAction
    def renameFilename_(self, sender):  # noqa: N802
        note = self._selected_note_or_none()
        if note is None:
            return
        self._autosave.flush()
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Rename Note Filename")
        alert.setInformativeText_(
            "Enter a filename. StormPad sanitizes it, preserves .md, and avoids collisions."
        )
        field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 360, 24))
        field.setStringValue_(note.path.name)
        field.setAccessibilityLabel_("Note filename")
        alert.setAccessoryView_(field)
        alert.addButtonWithTitle_("Rename")
        alert.addButtonWithTitle_("Cancel")
        if alert.runModal() != 1000:
            return
        try:
            renamed = self._store.rename_filename(note.id, str(field.stringValue()))
        except StorageError as exc:
            self._alert("Could not rename filename", str(exc))
            return
        self._replace_displayed(renamed)
        self._editor.load_note(renamed)
        self._note_list.set_notes(
            self._displayed,
            header=(
                "Results"
                if self._query
                else self._navigation_header(self._projects())
            ),
            subtitle=self._note_list_subtitle(),
        )
        self._note_list.select_note_id(renamed.id, notify=False)
        self._editor.flash_status(f"Renamed to {renamed.path.name}")

    @objc.IBAction
    def exportNoteTXT_(self, sender):  # noqa: N802
        note = self._selected_note_or_none()
        if note is None:
            return
        self._autosave.flush()
        panel = NSSavePanel.savePanel()
        panel.setTitle_("Export Note as Plain Text")
        panel.setNameFieldStringValue_(f"{note.path.stem}.txt")
        if hasattr(panel, "setAllowedFileTypes_"):
            panel.setAllowedFileTypes_(["txt"])
        if panel.runModal() != NSModalResponseOK:
            return
        destination = Path(str(panel.URL().path()))
        try:
            exported = export_note_txt(note, destination)
        except StorageError as exc:
            self._alert("Export failed", str(exc))
            return
        self._editor.flash_status(f"Exported {exported.name}")

    @objc.IBAction
    def toggleBold_(self, sender):  # noqa: N802
        self._editor.toggleBold_(sender)

    @objc.IBAction
    def toggleItalic_(self, sender):  # noqa: N802
        self._editor.toggleItalic_(sender)

    @objc.IBAction
    def toggleUnderline_(self, sender):  # noqa: N802
        self._editor.toggleUnderline_(sender)

    @objc.IBAction
    def editLink_(self, sender):  # noqa: N802
        self._editor.editLink_(sender)

    @objc.IBAction
    def chooseColor_(self, sender):  # noqa: N802
        self._editor.chooseColor_(sender)

    @objc.IBAction
    def insertBlockType_(self, sender):  # noqa: N802
        if self._current_id is None:
            return
        self._editor.prepare_block_command(option_pressed=False)
        self._editor.chooseBlockType_(sender)

    @objc.python_method
    def color_swatch_image(self, token: str, mode: str):
        return self._editor._color_swatch_image(token, mode)

    @objc.python_method
    def color_menu_title(self, token: str, mode: str) -> str:
        return self._editor.color_menu_title(token, mode)

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
        self._autosave.flush()
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
        if theme_id is None:
            return
        self._set_theme(str(theme_id))

    @objc.python_method
    def _set_theme(self, theme_id: str) -> None:
        if theme_id == self._theme.id:
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

        if self._settings._window.isVisible():
            self._settings.show(
                self._palette,
                theme_id=self._theme.id,
                show_controls=self._prefs.show_block_controls,
                notes_path=self._store.notes_dir,
            )

    @objc.IBAction
    def showSettings_(self, sender):  # noqa: N802
        self._settings.show(
            self._palette,
            theme_id=self._theme.id,
            show_controls=self._prefs.show_block_controls,
            notes_path=self._store.notes_dir,
        )

    @objc.IBAction
    def toggleBlockControls_(self, sender):  # noqa: N802
        self._set_block_controls(not self._prefs.show_block_controls)

    @objc.python_method
    def _set_block_controls(self, enabled: bool) -> None:
        self._prefs.show_block_controls = bool(enabled)
        self._editor.set_block_controls_enabled(bool(enabled))

    @objc.python_method
    def _reveal_notes_folder(self, kind: str) -> None:
        try:
            notes = self._store.ensure_dir()
            path = {
                "root": notes.parent,
                "notes": notes,
                "attachments": notes.parent / "Attachments",
            }.get(kind, notes)
            path.mkdir(parents=True, exist_ok=True)
        except (OSError, StorageError) as exc:
            self._alert("Could not reveal storage folder", str(exc))
            return
        NSWorkspace.sharedWorkspace().activateFileViewerSelectingURLs_(
            [NSURL.fileURLWithPath_(str(path))]
        )

    @objc.IBAction
    def showHelp_(self, sender):  # noqa: N802
        self._alert(
            "StormPad Help",
            "Hover a block row to reveal the Add Block control. "
            "Use the Format menu for block types and colors. "
            "Projects group related notes in local folders. "
            "Notes autosave as local Markdown files.",
        )

    def validateMenuItem_(self, item):  # noqa: N802
        name = str(item.action())
        note_actions = (
            "copyNote:",
            "appendTranscript:",
            "exportNoteTXT:",
            "renameFilename:",
            "openFile:",
            "revealInFinder:",
            "deleteNote:",
            "showNoteInfo:",
        )
        if name in note_actions:
            return self._current_id is not None
        if name == "speakSelection:":
            return is_speakable(self._editor.selected_body_text())
        if name == "stopSpeaking:":
            return self._speech.is_speaking
        if name in (
            "toggleBold:",
            "toggleItalic:",
            "toggleUnderline:",
            "editLink:",
        ):
            item.setState_(1 if self._editor.formatting_state(name) else 0)
            return bool(self._editor.selected_body_text())
        if name == "chooseColor:":
            payload = str(item.representedObject())
            mode, token = payload.split(":", 1)
            item.setState_(1 if self._editor.selected_color_token(mode) == token else 0)
            return bool(self._editor.selected_body_text())
        if name == "insertBlockType:":
            item.setState_(
                1 if str(item.representedObject()) == self._editor.current_block_type() else 0
            )
            return self._current_id is not None
        if name == "selectTheme:":
            item.setState_(menu_state(item.representedObject(), self._theme.id))
            return True
        if name == "toggleBlockControls:":
            item.setState_(1 if self._prefs.show_block_controls else 0)
            return True
        if name == "toggleNotesPanel:":
            item.setTitle_("Expand Notes" if self._notes_panel_collapsed() else "Collapse Notes")
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
