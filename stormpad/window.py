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
    NSMinYEdge,
    NSModalResponseOK,
    NSOpenPanel,
    NSPasteboard,
    NSPasteboardTypeString,
    NSSavePanel,
    NSSharingServicePicker,
    NSSplitViewController,
    NSSplitViewDividerStyleThin,
    NSSplitViewItem,
    NSStackView,
    NSTextField,
    NSTimer,
    NSUserInterfaceLayoutOrientationHorizontal,
    NSViewController,
    NSVisualEffectBlendingModeWithinWindow,
    NSVisualEffectMaterialTitlebar,
    NSVisualEffectStateFollowsWindowActiveState,
    NSVisualEffectView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskFullSizeContentView,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
    NSWindowTitleHidden,
    NSWorkspace,
)
from Foundation import (
    NSURL,
    NSClassFromString,
    NSMakeRect,
    NSObject,
    NSRunLoop,
    NSRunLoopCommonModes,
)

from . import attachments, paths
from .blocks import Block, BlockType, InlineRun
from .defaults import UserDefaultsBackend
from .dragdrop import move_project_id, reorder_project_ids, share_menu_options
from .errors import (
    InvalidProjectError,
    NoteNotFoundError,
    NotesDirectoryError,
    ProjectNotFoundError,
    ShareExportError,
    StorageError,
)
from .exporter import export_note_txt, note_to_plain_text
from .icons import normalize_project_icon
from .models import (
    ALL_NOTES,
    CATEGORIES,
    UNFILED,
    UNFILED_PROJECT_ID,
    now_local,
)
from .motion import AnimationToken, Motion
from .preferences import Preferences
from .search import (
    filter_by_category,
    filter_by_pinned,
    filter_by_project,
    notes_with_live_text,
    prune_pinned_ids,
    search_notes,
)
from .session import NoteStore
from .sharing import ShareExportManager
from .speech import SpeechController, SpeechUnavailableError
from .theme import all_themes, get_theme, menu_state
from .uihelpers import (
    AutosaveController,
    SaveStatus,
    choose_selected_note,
    copy_text,
    default_new_category,
    delete_confirmation,
    is_speakable,
    notes_panel_geometry,
    select_after_bulk_delete,
    word_count,
)
from .views import empty_state as es
from .views.controls import flipped_view, gradient_view, solid_view
from .views.editor import Editor
from .views.empty_state import EmptyState
from .views.icon_picker import (
    CLEAR_IDENTIFIER,
    CUSTOM_EMOJI_IDENTIFIER,
    build_icon_picker_view,
)
from .views.layout import add, pin_edges, set_height, set_width
from .views.motion import anim, can_animate, current_policy, run
from .views.note_list import NoteList
from .views.palette import Palette, symbol_image
from .views.settings import SettingsController
from .views.sidebar import Sidebar, toggled_project_expansion

_AUTOSAVE_DELAY = 0.4
_DEFAULT_SIZE = (1100.0, 720.0)
_MIN_SIZE = (900.0, 620.0)
_HEADER_HEIGHT = 52.0
_SIDEBAR_WIDTH = 248.0
_LIST_WIDTH = 326.0


def native_glass_effect_class(lookup=NSClassFromString):
    """Return the runtime glass class, or ``None`` on pre-glass macOS."""
    try:
        return lookup("NSGlassEffectView")
    except (LookupError, TypeError):
        return None


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
        self._expanded_project_id = (
            self._project_id
            if self._project_id not in (None, UNFILED_PROJECT_ID)
            else None
        )
        self._query = os.environ.get("STORMPAD_INITIAL_QUERY", "").strip()
        self._current_id: str | None = self._prefs.last_note_id
        self._displayed: list = []
        self._search_previews: dict[str, str] = {}
        # STORMPAD_PIN_FILTER is a dev/test hook to boot into the Pinned filter.
        self._pinned_only = bool(os.environ.get("STORMPAD_PIN_FILTER"))
        self._dev_notes_collapsed = True if os.environ.get("STORMPAD_COLLAPSE_NOTES") else None

        self._autosave = AutosaveController(
            self._perform_save,
            delay=_AUTOSAVE_DELAY,
            schedule=self._schedule_timer,
            cancel=self._cancel_timer,
        )
        self._speech = SpeechController()
        self._share_exports = ShareExportManager(
            self._store.notes_dir,
            cache_dir=os.environ.get("STORMPAD_SHARE_DIR") or None,
        )
        self._share_exports.cleanup_expired()
        self._sharing_picker = None
        self._last_share_path: Path | None = None
        self._action_buttons: list = []
        self._note_info_menu = None
        self._icon_menu = None
        self._icon_menu_project_id: str | None = None
        self._panel_token = AnimationToken()
        self._displayed_signature: tuple = ()
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
                lambda timer: self.showNoteInfo_(self._action_buttons[1]),
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
        if os.environ.get("STORMPAD_SHOW_SHARE_NOTE"):
            try:
                share_delay = float(os.environ.get("STORMPAD_SHARE_DELAY", "0.65"))
            except ValueError:
                share_delay = 0.65
            NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                share_delay, False, lambda timer: self.shareNote_(self._share_button)
            )
        if os.environ.get("STORMPAD_SHOW_SHARE_PROJECT"):
            NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                0.25, False, lambda timer: self._apply_share_project_dev_hook()
            )
        if os.environ.get("STORMPAD_SHOW_PROJECT_CONTEXT"):
            NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                0.25, False, lambda timer: self._show_project_context_dev_menu()
            )
        if os.environ.get("STORMPAD_SHOW_ICON_PICKER"):
            NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                0.25, False, lambda timer: self._show_icon_picker_dev_menu()
            )
        if os.environ.get("STORMPAD_SHOW_PROFILE_MENU"):
            NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                0.25, False, lambda timer: self._sidebar.profile_row.mouseDown_(None)
            )
        if (
            os.environ.get("STORMPAD_DRAG_PROJECT")
            or os.environ.get("STORMPAD_DRAG_NOTE_OVER")
        ):
            NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                0.35, False, lambda timer: self._apply_sidebar_drag_dev_hook()
            )
        if os.environ.get("STORMPAD_CAPTURE_PATH"):
            capture_timer = NSTimer.timerWithTimeInterval_repeats_block_(
                1.1, False, lambda timer: self._capture_dev_windows()
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
    ):
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
        else:
            button.setContentTintColor_(tint if tint is not None else p.text_secondary)
            button.layer().setBackgroundColor_(p.toolbar_button_background.CGColor())
            button.layer().setBorderWidth_(1.0)
            button.layer().setBorderColor_(p.border.CGColor())
        button.sizeToFit()
        width = 30.0 if icon_only else float(button.fittingSize().width) + 24.0
        set_width(button, width)
        set_height(button, 30)
        if primary:
            return self._glass_toolbar_button(button, width)
        return button

    @objc.python_method
    def _glass_toolbar_button(self, button: NSButton, width: float):
        """Embed the existing action button in native glass with a safe fallback."""
        p = self._palette
        outer = flipped_view()
        outer.setWantsLayer_(True)
        outer.layer().setCornerRadius_(15.0)
        outer.layer().setBorderWidth_(1.0)
        outer.layer().setBorderColor_(
            NSColor.whiteColor().colorWithAlphaComponent_(0.42).CGColor()
        )
        outer.layer().setShadowColor_(p.accent.CGColor())
        outer.layer().setShadowOpacity_(0.22)
        outer.layer().setShadowRadius_(5.0)
        outer.layer().setShadowOffset_((0.0, -1.5))

        glass_class = native_glass_effect_class()
        effect = None
        if glass_class is not None:
            candidate = glass_class.alloc().init()
            if candidate is not None and hasattr(candidate, "setContentView_"):
                effect = candidate
                if hasattr(effect, "setCornerRadius_"):
                    effect.setCornerRadius_(15.0)
                if hasattr(effect, "setTintColor_"):
                    effect.setTintColor_(
                        p.accent.colorWithAlphaComponent_(0.30)
                    )
                if hasattr(effect, "setEffectIsInteractive_"):
                    effect.setEffectIsInteractive_(True)
                button.setFrame_(NSMakeRect(0, 0, width, 30))
                effect.setContentView_(button)
                outer._glass_backend = "NSGlassEffectView"

        if effect is None:
            effect = NSVisualEffectView.alloc().init()
            effect.setMaterial_(NSVisualEffectMaterialTitlebar)
            effect.setBlendingMode_(NSVisualEffectBlendingModeWithinWindow)
            effect.setState_(NSVisualEffectStateFollowsWindowActiveState)
            effect.setWantsLayer_(True)
            effect.layer().setCornerRadius_(15.0)
            effect.layer().setMasksToBounds_(True)
            effect.layer().setBackgroundColor_(
                p.accent.colorWithAlphaComponent_(0.38).CGColor()
            )
            effect.addSubview_(button)
            pin_edges(button, effect, top=0, leading=0, trailing=0, bottom=0)
            outer._glass_backend = "NSVisualEffectView"

        add(outer, effect)
        pin_edges(effect, outer, top=0, leading=0, trailing=0, bottom=0)
        set_width(outer, width)
        set_height(outer, 30)
        return outer

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
        # The application remains running when its last window closes. Keep
        # this controller-owned window alive so Dock reopen can show the same
        # native window instead of messaging a released NSWindow instance.
        window.setReleasedWhenClosed_(False)
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
        share_b = self._toolbar_button(
            "Share Note", "shareNote:", "square.and.arrow.up", icon_only=True
        )
        new_b = self._toolbar_button("New Note", "newNote:", "plus", primary=True)
        self._share_button = share_b
        self._action_buttons = [share_b, info_b]

        stack = NSStackView.alloc().init()
        stack.setOrientation_(NSUserInterfaceLayoutOrientationHorizontal)
        stack.setSpacing_(7.0)
        for button in [collapse_b, share_b, info_b, new_b]:
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
            on_note=self._on_sidebar_note_selected,
            search_delegate=self,
            project_action_target=self,
            on_reorder_project=self._on_reorder_project,
            on_move_note=self._on_note_drop,
            themes=[(theme_id, theme.name) for theme_id, theme in all_themes().items()],
        )
        self._note_list = NoteList.alloc().initWithPalette_onSelect_onCollapse_(
            self._palette, self._on_note_selected, self._toggle_notes_panel
        )
        # Every creation path goes through newNote_, so the + button, Cmd+N,
        # File → New Note, and New Note in Project cannot drift apart.
        self._note_list.set_new_note_handler(lambda: self.newNote_(None))
        self._note_list.set_delete_handler(self._request_delete_selection)
        self._note_list.set_menu_provider(self._note_context_menu)
        self._note_list.set_filter_handler(self._on_pin_filter_changed)
        self._note_list.set_pinned_only(self._pinned_only)
        self._editor = Editor.alloc().initWithPalette_onTitle_onBody_onAttachment_(
            self._palette,
            self._on_title_edited,
            self._on_body_edited,
            self._attachment_block,
        )
        self._editor.speech_target = self
        self._editor.transcript_target = self
        self._editor.before_structural_return = self._autosave.flush
        self._editor.notes_dir = self._store.notes_dir
        self._editor.set_block_controls_enabled(self._prefs.show_block_controls)
        self._editor.set_color_recents(self._prefs.recent_colors)
        self._editor.on_color_used = self._record_recent_color

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
        project = self._project_for_dev_value(requested)
        if project is not None:
            self._on_project(project.id)

    @objc.python_method
    def _project_for_dev_value(self, requested: str):
        return next(
            (
                item
                for item in self._projects()
                if item.id == requested or item.name == requested
            ),
            None,
        )

    @objc.python_method
    def _apply_share_project_dev_hook(self) -> None:
        requested = os.environ.get("STORMPAD_SHOW_SHARE_PROJECT", "")
        project = self._project_for_dev_value(requested)
        if project is None:
            return
        sender = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Share Project", None, ""
        )
        sender.setRepresentedObject_(project.id)
        self.shareProject_(sender)

    @objc.python_method
    def _show_project_context_dev_menu(self) -> None:
        requested = os.environ.get("STORMPAD_SHOW_PROJECT_CONTEXT", "")
        project = self._project_for_dev_value(requested)
        if project is None:
            return
        row = self._sidebar._rows.get(project.id)
        if row is None:
            return
        menu = row.project_context_menu()
        menu.popUpMenuPositioningItem_atLocation_inView_(
            None,
            (0.0, 0.0),
            row,
        )

    @objc.python_method
    def _show_icon_picker_dev_menu(self) -> None:
        """Sanitized screenshot hook; inert in normal launches."""
        project = self._project_for_dev_value(
            os.environ.get("STORMPAD_SHOW_ICON_PICKER", "")
        )
        if project is None:
            return
        sender = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Choose Icon", None, ""
        )
        sender.setRepresentedObject_(project.id)
        self.chooseProjectIcon_(sender)

    @objc.python_method
    def _apply_sidebar_drag_dev_hook(self) -> None:
        project_name = os.environ.get("STORMPAD_DRAG_PROJECT", "")
        if project_name:
            project = self._project_for_dev_value(project_name)
            if project is not None:
                try:
                    insertion = int(
                        os.environ.get(
                            "STORMPAD_PROJECT_INSERTION_INDEX",
                            str(len(self._projects())),
                        )
                    )
                except ValueError:
                    insertion = len(self._projects())
                self._sidebar.show_project_drag_preview(project.id, insertion)
        note_target = os.environ.get("STORMPAD_DRAG_NOTE_OVER", "")
        if note_target:
            if note_target == UNFILED:
                self._sidebar.show_note_drop_preview(None)
            else:
                project = self._project_for_dev_value(note_target)
                if project is not None:
                    self._sidebar.show_note_drop_preview(project.id)

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
            # Programmatic selection: drive the table so the row highlights, then
            # load the editor (notify routes through the normal selection path).
            self._note_list.select_note_id(note.id, notify=False)
            self._on_note_selected(note.id)

    @objc.python_method
    def _show_move_project_dev_menu(self) -> None:
        note = self._selected_note_or_none()
        if note is None:
            return
        menu = self._move_to_project_item(note).submenu()
        menu.popUpMenuPositioningItem_atLocation_inView_(
            None, (0.0, 0.0), self._action_buttons[1]
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
        self._expanded_project_id = None
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
        current = getattr(self._editor, "_current", None)
        if (
            self._current_id is not None
            and current is not None
            and current.id == self._current_id
        ):
            all_notes = notes_with_live_text(
                all_notes,
                self._current_id,
                title=self._editor.title_text(),
                body=self._editor.body_text(),
            )
        projects = self._projects()
        self._project_id = self._validated_project_id(projects)
        counts = self._update_counts(all_notes, projects)

        # Drop pins for notes that no longer exist, then hand presentation state
        # to the list (pin indicators + Project-name tags).
        pinned_ids = self._pinned_ids(all_notes)
        self._note_list.set_pinned_ids(pinned_ids)
        self._note_list.set_project_names(
            {project.id: project.name for project in projects}
        )

        if self._query:
            results = search_notes(
                all_notes,
                self._query,
            )
            displayed = [r.note for r in results]
            self._search_previews = {
                result.note.id: result.snippet
                for result in results
                if result.snippet
            }
            header = "Results"
            n = len(displayed)
            subtitle = f'{n} note{"s" if n != 1 else ""} matching "{self._query}"'
        else:
            self._search_previews = {}
            displayed = filter_by_project(
                filter_by_category(all_notes, self._category),
                self._project_id,
            )
            header = self._navigation_header(projects)
            n = len(displayed)
            subtitle = f"{n} note{'s' if n != 1 else ''}"

        # Pinned narrows the global result set during search, or the current
        # category/Project scope when there is no query.
        if self._pinned_only:
            displayed = filter_by_pinned(displayed, pinned_ids)
            n = len(displayed)
            subtitle = f"{n} pinned note{'s' if n != 1 else ''}"

        # A subtle list transition only when the visible set actually changed,
        # and never while the user is typing in search.
        signature = tuple(note.id for note in displayed)
        transition = not self._query and signature != self._displayed_signature
        self._displayed_signature = signature

        self._displayed = displayed
        self._note_list.set_notes(
            displayed,
            header=header,
            subtitle=subtitle,
            transition=transition,
            search_previews=self._search_previews,
        )
        self._sidebar.set_navigation(
            projects,
            all_notes,
            counts,
            category=self._category,
            project_id=self._project_id,
            expanded_project_id=self._expanded_project_id,
            note_id=self._current_id,
            collapsed=self._prefs.projects_collapsed,
        )

        selected = choose_selected_note(displayed, self._current_id)
        if selected is not None:
            self._current_id = selected.id
            self._prefs.last_note_id = selected.id
            self._note_list.restore_active_note_id(selected.id)
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
        self._sidebar.set_active_note_id(self._current_id)
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
        self._expanded_project_id = None
        self._prefs.selected_project_id = None
        if category == ALL_NOTES or category in CATEGORIES:
            self._prefs.last_category = category
        self._apply_filter()

    @objc.python_method
    def _on_project(self, project_id: str | None) -> None:
        self._autosave.flush()
        if project_id in (None, UNFILED_PROJECT_ID):
            self._expanded_project_id = None
        else:
            self._expanded_project_id = toggled_project_expansion(
                self._project_id,
                self._expanded_project_id,
                project_id,
            )
        self._project_id = project_id
        self._category = ALL_NOTES
        self._prefs.last_category = ALL_NOTES
        self._prefs.selected_project_id = project_id
        self._apply_filter()

    @objc.python_method
    def _on_note_selected(self, note_id: str) -> None:
        self._sidebar.set_active_note_id(note_id)
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
        # This is the table's own selection change (the active row within a
        # possibly larger native range): the table selection is already correct,
        # so re-selecting the single row here would collapse a Shift-click range.
        # Just track the active note; the editor follows it.
        self._note_list.set_active_note_id(note_id)
        self._editor.load_note(note)
        self._autosave.reset()
        self._empty.hide()
        self._update_actions_enabled()

    @objc.python_method
    def _on_sidebar_note_selected(self, note_id: str) -> None:
        """Open a Project child shortcut in its unfiltered Project scope."""
        self._autosave.flush()
        self._speech.stop()
        self._current_id = note_id
        self._prefs.last_note_id = note_id
        self._query = ""
        self._sidebar.clear_search()
        if self._pinned_only:
            self._pinned_only = False
            self._note_list.set_pinned_only(False)
        # Project children are direct navigation, not range selection. Collapse
        # any prior table selection even when the child is already the active note.
        self._note_list.select_note_id(note_id, notify=False)
        self._apply_filter()

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
            search_previews=self._search_previews,
        )
        self._note_list.restore_active_note_id(save_id)
        self._sidebar.update_note_title(save_id, note.title)

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
        # Creating while Pinned is active must still work and must not silently
        # pin the note — so return to All, where the new note is visible.
        if self._pinned_only:
            self._pinned_only = False
            self._note_list.set_pinned_only(False)
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
        self._expanded_project_id = project.id
        self._category = ALL_NOTES
        self._prefs.selected_project_id = project.id
        self._prefs.last_category = ALL_NOTES
        self._apply_filter()

    @objc.IBAction
    def toggleProjectsSection_(self, sender):  # noqa: N802
        self._prefs.projects_collapsed = not self._prefs.projects_collapsed
        self._apply_filter()

    @objc.python_method
    def _controller_undo_manager(self):
        return self._editor._body.undoManager()

    @objc.python_method
    def _register_controller_undo(
        self,
        selector: str,
        payload,
        action_name: str,
    ) -> None:
        manager = self._controller_undo_manager()
        manager.registerUndoWithTarget_selector_object_(
            self,
            selector,
            payload,
        )
        manager.setActionName_(action_name)

    @objc.python_method
    def _set_project_order(
        self,
        order: list[str],
        *,
        register_undo: bool,
    ) -> bool:
        current = [project.id for project in self._projects()]
        if len(order) != len(current) or set(order) != set(current):
            return False
        if order == current:
            return False
        self._prefs.project_order = list(order)
        self._apply_filter()
        if register_undo:
            self._register_controller_undo(
                "restoreProjectOrder:",
                current,
                "Reorder Project",
            )
        return True

    @objc.python_method
    def _on_reorder_project(self, project_id: str, insertion_index: int) -> bool:
        current = [project.id for project in self._projects()]
        updated = reorder_project_ids(current, project_id, insertion_index)
        return self._set_project_order(updated, register_undo=True)

    def restoreProjectOrder_(self, order):  # noqa: N802
        self._set_project_order(list(order), register_undo=True)

    @objc.python_method
    def _move_project_by(self, project_id: str, offset: int) -> bool:
        current = [project.id for project in self._projects()]
        updated = move_project_id(current, project_id, offset)
        return self._set_project_order(updated, register_undo=True)

    @objc.IBAction
    def moveProjectUp_(self, sender):  # noqa: N802
        project_id = self._represented_string(sender)
        if project_id is not None:
            self._move_project_by(project_id, -1)

    @objc.IBAction
    def moveProjectDown_(self, sender):  # noqa: N802
        project_id = self._represented_string(sender)
        if project_id is not None:
            self._move_project_by(project_id, 1)

    @objc.IBAction
    def newNoteInProject_(self, sender):  # noqa: N802
        project_id = self._represented_string(sender)
        if project_id is None:
            return
        self._autosave.flush()
        self._project_id = project_id
        self._expanded_project_id = project_id
        self._category = ALL_NOTES
        self._prefs.last_category = ALL_NOTES
        self._prefs.selected_project_id = project_id
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
    def chooseProjectIcon_(self, sender):  # noqa: N802
        """Present the compact icon picker beside the project's row."""
        project_id = self._represented_string(sender)
        if project_id is None:
            return
        try:
            project = self._store.load_project(project_id)
        except ProjectNotFoundError as exc:
            self._alert("Project not found", str(exc))
            self._apply_filter()
            return
        row = self._sidebar._rows.get(project.id)
        if row is None:
            return
        menu = NSMenu.alloc().initWithTitle_("Project Icon")
        menu.setDelegate_(self)
        item = NSMenuItem.alloc().init()
        item.setView_(
            build_icon_picker_view(self._palette, current=project.icon, target=self)
        )
        menu.addItem_(item)
        # Retained until dismissed, and the target project is captured now so a
        # later click cannot apply an icon to whatever is selected by then.
        self._icon_menu = menu
        self._icon_menu_project_id = project.id
        menu.popUpMenuPositioningItem_atLocation_inView_(None, (0.0, 0.0), row)

    @objc.IBAction
    def setProjectIcon_(self, sender):  # noqa: N802
        project_id = self._icon_menu_project_id
        identifier = sender.identifier() if hasattr(sender, "identifier") else None
        if project_id is None or identifier is None:
            return
        raw = str(identifier)
        if raw == CUSTOM_EMOJI_IDENTIFIER:
            raw = self._prompt_project_emoji()
            if raw is None:
                return
        icon = None if raw == CLEAR_IDENTIFIER else normalize_project_icon(raw)
        self._set_project_icon(project_id, icon)

    @objc.IBAction
    def closeProjectIconPicker_(self, sender):  # noqa: N802
        menu = self._icon_menu
        self._icon_menu = None
        self._icon_menu_project_id = None
        if menu is not None:
            menu.cancelTracking()

    def menuDidClose_(self, menu):  # noqa: N802
        if menu is self._icon_menu:
            self._icon_menu = None
            self._icon_menu_project_id = None

    @objc.python_method
    def _prompt_project_emoji(self) -> str | None:
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Project Emoji")
        alert.setInformativeText_(
            "Enter one emoji. Press Control-Command-Space for the macOS emoji picker."
        )
        field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 200, 24))
        field.setAccessibilityLabel_("Project emoji")
        alert.setAccessoryView_(field)
        alert.addButtonWithTitle_("Use Emoji")
        alert.addButtonWithTitle_("Cancel")
        if alert.runModal() != 1000:
            return None
        return str(field.stringValue())

    @objc.python_method
    def _set_project_icon(self, project_id: str, icon: str | None) -> None:
        try:
            self._store.set_project_icon(project_id, icon)
        except (ProjectNotFoundError, StorageError, OSError) as exc:
            self._alert("Could not set project icon", str(exc))
        self._apply_filter()

    @objc.IBAction
    def revealStormPadFolder_(self, sender):  # noqa: N802
        self._reveal_notes_folder("root")

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
    def shareProject_(self, sender):  # noqa: N802
        project_id = self._represented_string(sender)
        if project_id is None and self._project_id not in (
            None,
            UNFILED_PROJECT_ID,
        ):
            project_id = self._project_id
        if project_id is None:
            return
        self._autosave.flush()
        try:
            project = self._store.load_project(project_id)
            exported = self._share_exports.export_project(
                project,
                self._store.list_notes(),
            )
        except (
            ProjectNotFoundError,
            ShareExportError,
            StorageError,
            OSError,
        ) as exc:
            self._alert("Could not share project", str(exc))
            self._apply_filter()
            return
        self._present_share_picker(exported, sender)

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
    def shareNote_(self, sender):  # noqa: N802
        if self._current_id is None:
            return
        self._autosave.flush()
        try:
            note = self._store.load_note(self._current_id)
            exported = self._share_exports.export_note(note)
        except (NoteNotFoundError, ShareExportError, StorageError, OSError) as exc:
            self._alert("Could not share note", str(exc))
            return
        self._present_share_picker(exported, sender)

    @objc.python_method
    def _present_share_picker(self, path: Path, sender) -> None:
        """Present macOS's native picker without choosing or sending a service."""
        self._last_share_path = Path(path)
        picker = NSSharingServicePicker.alloc().initWithItems_(
            [NSURL.fileURLWithPath_(str(path))]
        )
        self._sharing_picker = picker
        if os.environ.get("STORMPAD_SHARE_PREPARE_ONLY"):
            return
        anchor = sender if sender is not None and hasattr(sender, "bounds") else self._share_button
        picker.showRelativeToRect_ofView_preferredEdge_(
            anchor.bounds(),
            anchor,
            NSMinYEdge,
        )

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
            search_previews=self._search_previews,
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
        self._apply_notes_panel_state(animated=True)

    @objc.python_method
    def _panel_geometry(self, collapsed: bool):
        return notes_panel_geometry(
            collapsed,
            sidebar_width=_SIDEBAR_WIDTH,
            expanded_width=_LIST_WIDTH,
        )

    @objc.python_method
    def _write_panel_geometry(self, geometry) -> None:
        """Write a panel end state verbatim (thickness clamps then divider)."""
        self._list_item.setMinimumThickness_(geometry.minimum)
        self._list_item.setMaximumThickness_(geometry.maximum)
        self._split_vc.splitView().setPosition_ofDividerAtIndex_(
            geometry.divider_position, 1
        )

    @objc.python_method
    def _apply_notes_panel_state(self, *, animated: bool = False) -> None:
        collapsed = self._notes_panel_collapsed()
        geometry = self._panel_geometry(collapsed)
        split = self._split_vc.splitView()
        duration = (
            current_policy().duration(Motion.PANEL)
            if animated and can_animate(split)
            else 0.0
        )
        if duration <= 0.0:
            # Initial build, theme rebuild, and Reduce Motion all land here: the
            # panel simply is in its final state.
            self._panel_token.cancel()
            self._note_list.set_collapsed(collapsed)
            self._write_panel_geometry(geometry)
            return

        # Relax the thickness clamps to bracket the journey, otherwise the
        # split view's constraints pin the divider and it jumps at the end.
        current = float(self._note_list.view.frame().size.width) or geometry.width
        self._list_item.setMinimumThickness_(min(current, geometry.width))
        self._list_item.setMaximumThickness_(max(current, geometry.width))
        # The editor column is driven by the same divider, so it grows and
        # shrinks with the notes panel rather than snapping afterwards.
        self._note_list.set_collapsed(collapsed, duration=duration)
        token = self._panel_token.begin()

        def body(animated_: bool) -> None:
            anim(split, animated_).setPosition_ofDividerAtIndex_(
                geometry.divider_position, 1
            )

        def done() -> None:
            if not self._panel_token.is_current(token):
                return
            # Recomputed, so an interrupted transition still restores the exact
            # final widths and the column stays resizable afterwards.
            self._write_panel_geometry(self._panel_geometry(self._notes_panel_collapsed()))

        run(duration, body, completion=done)

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
    def _pinned_ids(self, all_notes) -> list[str]:
        """Stored pins with stale ids (deleted notes) pruned and persisted."""
        stored = self._prefs.pinned_note_ids
        pruned = prune_pinned_ids(stored, [note.id for note in all_notes])
        if pruned != stored:
            self._prefs.pinned_note_ids = pruned
        return pruned

    @objc.python_method
    def rename_project_inline(self, project_id: str, name: str) -> None:
        """Commit an inline (double-click) project rename.

        Reuses the same store call as the context-menu Rename Project, so the
        project UUID is unchanged, notes stay inside it, unsafe filesystem
        characters are sanitised, and duplicate names get a unique folder.
        """
        cleaned = str(name).strip()
        if not cleaned:
            return
        self._autosave.flush()
        try:
            self._store.rename_project(project_id, cleaned)
        except (InvalidProjectError, ProjectNotFoundError, StorageError, OSError) as exc:
            self._alert("Could not rename project", str(exc))
        self._apply_filter()  # refreshes the header, counts, and note tags

    @objc.python_method
    def _record_recent_color(self, entry: str) -> None:
        """Persist the applied colour and refresh the palette's recents."""
        self._editor.set_color_recents(self._prefs.record_recent_color(entry))

    @objc.python_method
    def _on_pin_filter_changed(self, pinned_only: bool) -> None:
        self._pinned_only = bool(pinned_only)
        self._apply_filter()

    @objc.IBAction
    def togglePinNote_(self, sender):  # noqa: N802
        note_id = self._represented_string(sender) or self._current_id
        if note_id is None:
            return
        pinned = self._prefs.pinned_note_ids
        if note_id in pinned:
            pinned = [item for item in pinned if item != note_id]
        else:
            pinned = [*pinned, note_id]
        self._prefs.pinned_note_ids = pinned
        self._apply_filter()

    @objc.python_method
    def _pin_menu_item(self, note):
        pinned = note.id in set(self._prefs.pinned_note_ids)
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Unpin Note" if pinned else "Pin Note", "togglePinNote:", ""
        )
        item.setTarget_(self)
        item.setRepresentedObject_(note.id)
        return item

    @objc.python_method
    def _note_context_menu(self, note):
        menu = NSMenu.alloc().initWithTitle_("Note")
        menu.addItem_(self._pin_menu_item(note))
        menu.addItem_(NSMenuItem.separatorItem())
        share = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Share Note…", "shareNote:", ""
        )
        share.setTarget_(self)
        menu.addItem_(share)
        menu.addItem_(NSMenuItem.separatorItem())
        menu.addItem_(self._move_to_project_item(note))
        if note.project_id is not None:
            remove = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Remove from Project", "removeNoteFromProject:", ""
            )
            remove.setTarget_(self)
            remove.setRepresentedObject_(note.id)
            menu.addItem_(remove)
        menu.addItem_(NSMenuItem.separatorItem())
        # Deletes the whole selection when the right-clicked note is part of a
        # multi-selection; the table's menuForEvent_ has already ensured a note
        # outside the selection is selected on its own first.
        selected = self._note_list.selected_note_ids()
        count = len(selected) if note.id in selected and len(selected) > 1 else 1
        delete = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"Delete {count} Notes…" if count > 1 else "Delete Note…",
            "deleteNote:",
            "",
        )
        delete.setTarget_(self)
        menu.addItem_(delete)
        return menu

    @objc.IBAction
    def moveNoteToProject_(self, sender):  # noqa: N802
        payload = self._represented_string(sender)
        if payload is None or "|" not in payload:
            return
        note_id, project_id = payload.split("|", 1)
        try:
            self._move_note_to_project_internal(
                note_id,
                project_id,
                register_undo=True,
            )
        except (NoteNotFoundError, ProjectNotFoundError, StorageError, OSError) as exc:
            self._alert("Could not move note", str(exc))
            self._apply_filter()

    @objc.IBAction
    def removeNoteFromProject_(self, sender):  # noqa: N802
        note_id = self._represented_string(sender) or self._current_id
        if note_id is None:
            return
        try:
            self._move_note_to_project_internal(
                note_id,
                None,
                register_undo=True,
            )
        except (NoteNotFoundError, StorageError, OSError) as exc:
            self._alert("Could not remove note from project", str(exc))
            self._apply_filter()

    @objc.python_method
    def _on_note_drop(self, note_id: str, project_id: str | None) -> bool:
        try:
            return self._move_note_to_project_internal(
                note_id,
                project_id,
                register_undo=True,
            )
        except (
            NoteNotFoundError,
            ProjectNotFoundError,
            StorageError,
            OSError,
        ) as exc:
            self._alert("Could not move note", str(exc))
            self._apply_filter()
            return False

    @objc.python_method
    def _move_note_to_project_internal(
        self,
        note_id: str,
        project_id: str | None,
        *,
        register_undo: bool,
    ) -> bool:
        """Flush, validate stable IDs, move atomically, then refresh selection."""
        self._autosave.flush()
        note = self._store.load_note(note_id)
        if project_id is not None:
            self._store.load_project(project_id)
        source_project_id = note.project_id
        if source_project_id == project_id:
            return False
        moved = self._store.move_note_to_project(note_id, project_id)
        self._autosave.reset()
        self._current_id = moved.id
        self._prefs.last_note_id = moved.id
        self._project_id = project_id or UNFILED_PROJECT_ID
        self._expanded_project_id = project_id
        self._category = ALL_NOTES
        self._query = ""
        self._sidebar.clear_search()
        self._prefs.selected_project_id = self._project_id
        self._prefs.last_category = ALL_NOTES
        self._apply_filter()
        if register_undo:
            source = source_project_id or UNFILED_PROJECT_ID
            self._register_controller_undo(
                "restoreNoteProject:",
                f"{moved.id}|{source}",
                "Move Note",
            )
        return True

    def restoreNoteProject_(self, payload):  # noqa: N802
        raw = str(payload)
        if "|" not in raw:
            return
        note_id, project_id = raw.split("|", 1)
        target = None if project_id == UNFILED_PROJECT_ID else project_id
        try:
            self._move_note_to_project_internal(
                note_id,
                target,
                register_undo=True,
            )
        except (
            NoteNotFoundError,
            ProjectNotFoundError,
            StorageError,
            OSError,
        ) as exc:
            self._alert("Could not undo note move", str(exc))

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
        menu.addItem_(self._pin_menu_item(note))
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
            ("Share Note…", "shareNote:"),
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
            search_previews=self._search_previews,
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
        # A right-clicked note already extends the selection when it is part of
        # it, so the menu's Delete acts on the whole selection in that case.
        selected = self._note_list.selected_note_ids()
        if len(selected) > 1:
            self._request_delete_selection()
            return
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
        self._forget_pins([note.id])
        if self._prefs.last_note_id == note.id:
            self._prefs.last_note_id = None
        self._current_id = None
        self._apply_filter()

    @objc.python_method
    def _request_delete_selection(self) -> None:
        """Delete every selected note through the safe Trash path, with one
        confirmation. A single-note selection keeps the existing singular flow.
        """
        selected_ids = self._note_list.selected_note_ids()
        if len(selected_ids) <= 1:
            self.deleteNote_(None)
            return
        self._autosave.flush()
        confirmation = delete_confirmation(len(selected_ids))
        alert = NSAlert.alloc().init()
        alert.setMessageText_(confirmation.title)
        alert.setInformativeText_(confirmation.message)
        alert.addButtonWithTitle_(confirmation.cancel_button)  # default = safe
        remove = alert.addButtonWithTitle_(confirmation.confirm_button)
        if hasattr(remove, "setHasDestructiveAction_"):
            remove.setHasDestructiveAction_(True)
        if alert.runModal() != NSAlertSecondButtonReturn:
            return  # Cancel changes nothing
        self._perform_bulk_delete(selected_ids)

    @objc.python_method
    def _perform_bulk_delete(self, selected_ids: list[str]) -> None:
        """Delete confirmed notes through the safe path; preserve any that fail."""
        self._speech.stop()
        pre_delete = list(self._displayed)
        removed: list[str] = []
        failures: list[str] = []
        for note_id in selected_ids:
            try:
                self._store.delete_note(note_id)  # macOS Trash, never permanent
                removed.append(note_id)
            except NoteNotFoundError:
                # Already gone on disk — treat as removed so it leaves the UI.
                removed.append(note_id)
            except (StorageError, OSError) as exc:
                failures.append(f"{note_id}: {exc}")

        self._forget_pins(removed)
        removed_set = set(removed)
        if self._current_id in removed_set:
            self._current_id = None
        if self._prefs.last_note_id in removed_set:
            self._prefs.last_note_id = None
        # Select the nearest surviving visible note where practical.
        survivor = select_after_bulk_delete(pre_delete, removed_set)
        if survivor is not None:
            self._current_id = survivor
        self._note_list.select_note_id(survivor, notify=False)
        self._apply_filter()  # counts, sidebar, Pinned all refresh here

        if failures:
            # Everything not successfully removed is preserved and reported.
            self._alert(
                "Some notes could not be removed",
                f"{len(removed)} removed, {len(failures)} kept.\n\n"
                + "\n".join(failures),
            )

    @objc.python_method
    def _forget_pins(self, note_ids) -> None:
        """Drop deleted UUIDs from pinned preferences; stale ids are harmless."""
        gone = set(note_ids)
        if not gone:
            return
        pinned = self._prefs.pinned_note_ids
        remaining = [pid for pid in pinned if pid not in gone]
        if remaining != pinned:
            self._prefs.pinned_note_ids = remaining

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
            "shareNote:",
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
        if name == "shareProject:":
            project_id = self._represented_string(item)
            if project_id is not None:
                return any(
                    project.id == project_id
                    for project in self._projects()
                )
            return "project" in share_menu_options(
                note_selected=self._current_id is not None,
                project_selected=self._project_id not in (
                    None,
                    UNFILED_PROJECT_ID,
                ),
            )
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
            # Search may immediately select a different result. Persist the
            # active live editor first so unsaved text cannot be displaced.
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
        self._share_exports.cleanup_expired()

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
