"""Sidebar navigation for library, Projects, categories, and local privacy."""

from __future__ import annotations

from collections.abc import Callable

import objc
from AppKit import (
    NSAccessibilityAnnouncementKey,
    NSAccessibilityAnnouncementRequestedNotification,
    NSAccessibilityPostNotificationWithUserInfo,
    NSAccessibilityPriorityKey,
    NSAccessibilityPriorityMedium,
    NSButton,
    NSColor,
    NSDraggingContextOutsideApplication,
    NSDraggingItem,
    NSDragOperationMove,
    NSDragOperationNone,
    NSEvent,
    NSFont,
    NSFontAttributeName,
    NSImage,
    NSImageAlignCenter,
    NSImageOnly,
    NSImageScaleProportionallyUpOrDown,
    NSImageView,
    NSMenu,
    NSMenuItem,
    NSNoBorder,
    NSPasteboardItem,
    NSScrollView,
    NSSearchField,
    NSTextField,
    NSTrackingActiveInKeyWindow,
    NSTrackingArea,
    NSTrackingInVisibleRect,
    NSTrackingMouseEnteredAndExited,
    NSViewHeightSizable,
    NSViewWidthSizable,
)
from Foundation import NSAttributedString, NSMakeRect, NSPointInRect, NSTimer

from ..dragdrop import (
    NOTE_PASTEBOARD_TYPE,
    PROJECT_PASTEBOARD_TYPE,
    decode_drag_payload,
    drag_threshold_exceeded,
    encode_drag_payload,
    insertion_index_for_row,
)
from ..icons import (
    DEFAULT_PROJECT_SYMBOL,
    project_icon_kind,
    project_icon_payload,
)
from ..models import ALL_NOTES, CATEGORIES, UNFILED, UNFILED_PROJECT_ID, Project
from ..motion import Motion
from .controls import FlippedView, flipped_view, icon_view, label, rounded_view, solid_view
from .layout import MAIN_COLUMN_TOP_INSET, add, pin_edges, set_height, set_width
from .motion import anim, can_animate, current_policy, run
from .palette import Palette, menu_icon, symbol_image
from .profile import build_profile_row


def _destructive_menu_title(title: str, palette):
    """A restrained red menu title (label only, never a full-row fill)."""
    from AppKit import NSFont, NSFontAttributeName, NSForegroundColorAttributeName
    from Foundation import NSAttributedString

    return NSAttributedString.alloc().initWithString_attributes_(
        title,
        {
            NSForegroundColorAttributeName: palette.destructive,
            NSFontAttributeName: NSFont.systemFontOfSize_(13.0),
        },
    )


# A stable square container for every Project icon. The 24pt box leaves enough
# room for Apple Color Emoji's taller glyph bounds while remaining centred in
# the 34pt row. Symbols and emoji deliberately use separate rendering metrics.
_ROW_ICON_BOX = NSMakeRect(10, 5, 24, 24)
_ROW_SYMBOL_POINT = 15.0
_ROW_EMOJI_POINT = 16.0
_ROW_LABEL_X = 40.0

_ICONS = {
    ALL_NOTES: "square.grid.2x2",
    UNFILED: "tray",
    "Ideas": "lightbulb",
    "Sessions": "waveform",
    "Drafts": "pencil.line",
}
_TRACKING_OPTS = (
    NSTrackingMouseEnteredAndExited
    | NSTrackingActiveInKeyWindow
    | NSTrackingInVisibleRect
)


def project_click_action(click_count: int) -> str:
    """Resolve AppKit click counts without letting a double-click toggle twice."""
    return "rename" if int(click_count) >= 2 else "select"


def project_row_hit_region(x: float, y: float) -> str:
    """Classify a Project-row click without conflating icon and name actions."""
    point = (float(x), float(y))
    if NSPointInRect(point, _ROW_ICON_BOX):
        return "icon"
    if NSPointInRect(point, NSMakeRect(_ROW_LABEL_X, 7, 84, 20)):
        return "name"
    if NSPointInRect(point, NSMakeRect(150, 4, 26, 26)):
        return "write"
    if NSPointInRect(point, NSMakeRect(180, 4, 26, 26)):
        return "ellipsis"
    return "row"


def nested_note_selection_states(
    note_ids: list[str] | tuple[str, ...],
    active_note_id: str | None,
) -> dict[str, bool]:
    """Nested note shortcuts are single-active navigation, never a range."""
    return {note_id: note_id == active_note_id for note_id in note_ids}


def toggled_project_expansion(
    active_project_id: str | None,
    expanded_project_id: str | None,
    clicked_project_id: str,
) -> str | None:
    """Select-and-expand a new Project, or fold the selected Project in place."""
    if clicked_project_id != active_project_id:
        return clicked_project_id
    return None if expanded_project_id == clicked_project_id else clicked_project_id


class ProjectRowActionButton(NSButton):
    """Restrained icon button that brightens slightly on hover."""

    def initWithFrame_(self, frame):  # noqa: N802
        self = objc.super(ProjectRowActionButton, self).initWithFrame_(frame)
        if self is None:
            return None
        area = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
            NSMakeRect(0, 0, 0, 0), _TRACKING_OPTS, self, None
        )
        self.addTrackingArea_(area)
        self.setAlphaValue_(0.78)
        return self

    def mouseEntered_(self, event):  # noqa: N802
        self.setAlphaValue_(1.0)

    def mouseExited_(self, event):  # noqa: N802
        self.setAlphaValue_(0.78)


class ProjectEmojiView(NSImageView):
    """Draw one full-colour Apple emoji centred without text-cell clipping."""

    def initWithGlyph_(self, glyph):  # noqa: N802
        self = objc.super(ProjectEmojiView, self).init()
        if self is None:
            return None
        self._glyph = str(glyph)
        self._emoji_font = (
            NSFont.fontWithName_size_("Apple Color Emoji", _ROW_EMOJI_POINT)
            or NSFont.systemFontOfSize_(_ROW_EMOJI_POINT)
        )
        return self

    def drawRect_(self, rect):  # noqa: N802
        text = NSAttributedString.alloc().initWithString_attributes_(
            self._glyph,
            {NSFontAttributeName: self._emoji_font},
        )
        size = text.size()
        bounds = self.bounds()
        x = max(0.0, (float(bounds.size.width) - float(size.width)) / 2.0)
        y = max(0.0, (float(bounds.size.height) - float(size.height)) / 2.0)
        text.drawAtPoint_((x, y))


class SidebarRow(FlippedView):
    """Clickable native row with semantic selected and hover states."""

    def initWithKey_(self, key):  # noqa: N802
        self = objc.super(SidebarRow, self).init()
        if self is None:
            return None
        self.key = str(key)
        self._selected = False
        self._emphasized = False
        self._surface_applied = False
        self._icon_is_symbol = True
        self._drop_target = False
        self._drag_lifted = False
        self._drag_started = False
        self._mouse_down_point: tuple[float, float] | None = None
        self._single_click_timer = None
        self._hovered = False
        self._is_child_shortcut = False
        self._action_controls: list[NSButton] = []
        self._palette: Palette | None = None
        self.on_select: Callable[[str], None] | None = None
        self.action_target = None
        self.rename_target = None
        self._renaming = False
        self._rename_field = None
        self._original_name = ""
        self.drag_owner = None
        self.drag_kind: str | None = None
        self.drag_source_index = 0
        area = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
            NSMakeRect(0, 0, 0, 0), _TRACKING_OPTS, self, None
        )
        self.addTrackingArea_(area)
        return self

    def mouseDown_(self, event):  # noqa: N802
        if event is None:
            if self.on_select is not None:
                self.on_select(self.key)
            return
        if self._renaming:
            return
        point = self.convertPoint_fromView_(event.locationInWindow(), None)
        self._mouse_down_point = (float(point.x), float(point.y))
        self._drag_started = False

    def representedObject(self):  # noqa: N802
        """Let existing Project actions resolve this row's exact UUID."""
        return self.key

    def hitTest_(self, point):  # noqa: N802
        """Make icon, label, count, and empty background one draggable surface."""
        # While inline-renaming, defer to subviews so the editable field gets
        # the clicks instead of the row swallowing them.
        if self._renaming:
            return objc.super(SidebarRow, self).hitTest_(point)
        # AppKit supplies hitTest: points in the receiver's superview
        # coordinates. Comparing that directly with local bounds rejected
        # every row whose y-origin was below the first 34 points.
        local = self.convertPoint_fromView_(point, self.superview())
        for control in self._action_controls:
            if NSPointInRect(local, control.frame()):
                return control
        return self if NSPointInRect(local, self.bounds()) else None

    def mouseDragged_(self, event):  # noqa: N802
        if (
            self._renaming
            or self.drag_kind != "project"
            or self.drag_owner is None
            or self._mouse_down_point is None
            or self._drag_started
        ):
            return
        point = self.convertPoint_fromView_(event.locationInWindow(), None)
        if not drag_threshold_exceeded(
            self._mouse_down_point,
            (float(point.x), float(point.y)),
        ):
            return
        self._drag_started = bool(self.drag_owner.start_project_drag(self, event))

    def mouseUp_(self, event):  # noqa: N802
        if self._renaming:
            return
        if not self._drag_started and self.on_select is not None:
            if event is None or self.drag_kind != "project":
                self.on_select(self.key)
            elif project_click_action(event.clickCount()) == "rename":
                self._cancel_single_click()
                point = self.convertPoint_fromView_(event.locationInWindow(), None)
                region = project_row_hit_region(float(point.x), float(point.y))
                if region == "icon" and self.action_target is not None:
                    self.action_target.chooseProjectIcon_(self)
                elif region == "name":
                    self.begin_inline_rename()
            else:
                # Wait through AppKit's double-click interval. This prevents
                # the first half of a rename gesture from folding the Project.
                self._schedule_single_click()
        self._mouse_down_point = None
        self._drag_started = False

    @objc.python_method
    def _cancel_single_click(self) -> None:
        timer = self._single_click_timer
        self._single_click_timer = None
        if timer is not None:
            timer.invalidate()

    @objc.python_method
    def _schedule_single_click(self) -> None:
        self._cancel_single_click()
        delay = float(NSEvent.doubleClickInterval())

        def fire(_timer):
            self._single_click_timer = None
            if not self._renaming and self.on_select is not None:
                self.on_select(self.key)

        self._single_click_timer = (
            NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                delay, False, fire
            )
        )

    # -- inline rename -------------------------------------------------------

    @objc.python_method
    def begin_inline_rename(self):
        """Swap the name label for an editable field, in place."""
        if self._renaming or self.drag_kind != "project":
            return
        self._renaming = True
        self._original_name = str(self._name.stringValue())
        frame = self._name.frame()
        field = NSTextField.alloc().initWithFrame_(frame)
        field.setStringValue_(self._original_name)
        field.setFont_(self._name.font())
        field.setBezeled_(True)
        field.setBezelStyle_(0)  # square bezel
        field.setEditable_(True)
        field.setSelectable_(True)
        field.setDrawsBackground_(True)
        field.setDelegate_(self)
        field.setAccessibilityLabel_("Project name")
        self._name.setHidden_(True)
        self.addSubview_(field)
        self._rename_field = field
        # Fade the field in so label → editable field reads as one control
        # changing state rather than two views swapping.
        self._fade_rename_field(field, appearing=True)
        window = self.window()
        if window is not None:
            window.makeFirstResponder_(field)
            field.currentEditor() and field.currentEditor().selectAll_(None)

    @objc.python_method
    def _fade_rename_field(self, field, *, appearing: bool) -> None:
        duration = (
            current_policy().duration(Motion.POPOVER) if can_animate(self) else 0.0
        )
        if duration <= 0.0:
            field.setAlphaValue_(1.0 if appearing else 0.0)
            return
        field.setAlphaValue_(0.0 if appearing else 1.0)
        run(
            duration,
            lambda animated: anim(field, animated).setAlphaValue_(
                1.0 if appearing else 0.0
            ),
        )

    @objc.python_method
    def _end_inline_rename(self, commit: bool):
        field = self._rename_field
        if field is None:
            return
        value = str(field.stringValue()) if commit else ""
        self._rename_field = None
        self._renaming = False
        field.setDelegate_(None)
        # Remove synchronously: the field must never linger as an invisible
        # first-responder overlay, and the row is about to be rebuilt anyway.
        field.removeFromSuperview()
        self._name.setHidden_(False)
        window = self.window()
        if window is not None:
            window.makeFirstResponder_(None)
        if not commit:
            return
        cleaned = value.strip()
        # An empty name is never accepted; the store handles sanitising unsafe
        # filesystem characters and de-duplicating names.
        if not cleaned or cleaned == self._original_name:
            return
        if self.rename_target is not None:
            self.rename_target.rename_project_inline(self.key, cleaned)

    def control_textView_doCommandBySelector_(self, control, view, selector):  # noqa: N802
        name = str(selector)
        if name == "insertNewline:":
            self._end_inline_rename(True)
            return True
        if name == "cancelOperation:":
            self._end_inline_rename(False)
            return True
        return False

    def controlTextDidEndEditing_(self, notification):  # noqa: N802
        # Clicking away commits, matching normal macOS field behaviour.
        if self._renaming:
            self._end_inline_rename(True)

    def mouseEntered_(self, event):  # noqa: N802
        self._hovered = True
        if self._is_child_shortcut:
            if not self._selected and self._palette is not None:
                self._name.setTextColor_(self._palette.text_primary)
            return
        self._apply_surface()

    def mouseExited_(self, event):  # noqa: N802
        self._hovered = False
        if self._is_child_shortcut:
            if self._palette is not None:
                self._apply_selection_text(self._selected, self._palette)
            return
        self._apply_surface()

    def rightMouseDown_(self, event):  # noqa: N802
        if self.action_target is None or self.key in {
            ALL_NOTES,
            UNFILED_PROJECT_ID,
            *CATEGORIES,
        }:
            objc.super(SidebarRow, self).rightMouseDown_(event)
            return
        menu = self.project_context_menu()
        NSMenu.popUpContextMenu_withEvent_forView_(menu, event, self)

    def project_context_menu(self):
        palette = self._palette
        menu = NSMenu.alloc().initWithTitle_("Project")
        # Four groups matching the menu reference: edit · share/locate · reorder
        # · destructive. Each row carries its accent-tinted SF Symbol; Delete is
        # the sole restrained-destructive row.
        for title, action, symbol in (
            ("Rename Project…", "renameProject:", "pencil"),
            ("Choose Icon…", "chooseProjectIcon:", "face.smiling"),
            ("New Note in Project", "newNoteInProject:", "doc.badge.plus"),
            ("Share Project…", "shareProject:", "square.and.arrow.up"),
            ("Reveal Project Folder in Finder", "revealProject:", "folder"),
            ("Move Project Up", "moveProjectUp:", "arrow.up"),
            ("Move Project Down", "moveProjectDown:", "arrow.down"),
            ("Delete Project…", "deleteProject:", "trash"),
        ):
            destructive = action == "deleteProject:"
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                title, action, ""
            )
            item.setTarget_(self.action_target)
            item.setRepresentedObject_(self.key)
            if palette is not None:
                tint = palette.destructive if destructive else palette.accent_strong
                image = menu_icon(symbol, tint)
                if image is not None:
                    item.setImage_(image)
                if destructive:
                    # Restrained: red label at rest (matching the Light/Deep Dark
                    # reference), never a loud full-row fill.
                    item.setAttributedTitle_(_destructive_menu_title(title, palette))
            menu.addItem_(item)
            if action in ("newNoteInProject:", "revealProject:", "moveProjectDown:"):
                menu.addItem_(NSMenuItem.separatorItem())
        return menu

    def showProjectMenu_(self, sender):  # noqa: N802
        menu = self.project_context_menu()
        menu.popUpMenuPositioningItem_atLocation_inView_(
            None, (0.0, 0.0), sender
        )

    def _apply_surface(self) -> None:
        if self._palette is None:
            return
        emphasized = self._selected or self._drop_target or self._drag_lifted
        # Only an actual change animates. A freshly built row (or a repeated
        # call) applies its surface immediately, so nothing flashes on rebuild.
        changed = self._surface_applied and emphasized != self._emphasized
        self._emphasized = emphasized
        self._surface_applied = True
        duration = (
            current_policy().duration(Motion.SELECTION)
            if changed and can_animate(self)
            else 0.0
        )
        # Inside an animation group with implicit animation allowed, these layer
        # colour changes interpolate; outside one they apply immediately.
        run(duration, lambda _animated: self._paint_surface(emphasized))

    @objc.python_method
    def _paint_surface(self, emphasized: bool) -> None:
        palette = self._palette
        self.setBackgroundColor_(
            palette.selected_background
            if emphasized
            else (
                palette.hover_background
                if self._hovered and not self._is_child_shortcut
                else NSColor.clearColor()
            )
        )
        layer = self.layer()
        layer.setBorderWidth_(1.5 if self._drop_target else (1.0 if emphasized else 0.0))
        layer.setBorderColor_(
            palette.accent_strong.CGColor()
            if self._drop_target
            else (
                palette.selected_border.CGColor()
                if emphasized
                else NSColor.clearColor().CGColor()
            )
        )
        # Drag lift is a grab feedback, never an animated transition.
        self.layer().setShadowOpacity_(0.2 if self._drag_lifted else 0.0)
        self.layer().setShadowRadius_(7.0 if self._drag_lifted else 0.0)
        self.layer().setShadowOffset_((0.0, -2.0))

    def set_drop_target(self, active: bool) -> None:
        self._drop_target = bool(active)
        self._apply_surface()

    def set_drag_lifted(self, active: bool) -> None:
        self._drag_lifted = bool(active)
        self._apply_surface()

    def set_selected(self, selected: bool, palette: Palette) -> None:
        self._selected = bool(selected)
        self._palette = palette
        self._apply_surface()
        self._apply_selection_text(selected, palette)

    def set_child_selected(self, selected: bool, palette: Palette) -> None:
        """Synchronously reset and repaint a single-active child shortcut."""
        self._selected = bool(selected)
        self._palette = palette
        self._drop_target = False
        self._drag_lifted = False
        self._drag_started = False
        self._hovered = False
        self._emphasized = self._selected
        self._surface_applied = True
        layer = self.layer()
        layer.removeAllAnimations()
        self._paint_surface(self._selected)
        # A previous implicit selection transition can otherwise remain in the
        # presentation layer after the model layer has already become clear.
        layer.removeAllAnimations()
        self._apply_selection_text(selected, palette)

    @objc.python_method
    def _apply_selection_text(self, selected: bool, palette: Palette) -> None:
        self._name.setTextColor_(
            palette.text_primary if selected else palette.text_secondary
        )
        if self._count is not None:
            self._count.setTextColor_(
                palette.text_secondary if selected else palette.text_muted
            )
        # An emoji icon is a text label, not a tintable template image — it keeps
        # its own colours.
        if self._icon_is_symbol:
            self._icon.setContentTintColor_(
                palette.accent_strong if selected else palette.text_muted
            )

    def draggingSession_sourceOperationMaskForDraggingContext_(  # noqa: N802
        self, session, context
    ):
        if context == NSDraggingContextOutsideApplication:
            return NSDragOperationNone
        return NSDragOperationMove

    def ignoreModifierKeysForDraggingSession_(self, session):  # noqa: N802
        return True

    def draggingSession_willBeginAtPoint_(self, session, point):  # noqa: N802
        self.set_drag_lifted(True)

    def draggingSession_endedAtPoint_operation_(  # noqa: N802
        self, session, point, operation
    ):
        self.set_drag_lifted(False)
        if self.drag_owner is not None:
            self.drag_owner.clear_drag_feedback()

    def draggingEntered_(self, sender):  # noqa: N802
        if self.drag_owner is None:
            return NSDragOperationNone
        return self.drag_owner.update_drag(self, sender)

    def draggingUpdated_(self, sender):  # noqa: N802
        return self.draggingEntered_(sender)

    def draggingExited_(self, sender):  # noqa: N802
        if self.drag_owner is not None:
            self.drag_owner.clear_drag_feedback()

    def performDragOperation_(self, sender):  # noqa: N802
        if self.drag_owner is None:
            return False
        return bool(self.drag_owner.perform_drop(self, sender))

    def concludeDragOperation_(self, sender):  # noqa: N802
        if self.drag_owner is not None:
            self.drag_owner.clear_drag_feedback()


class Sidebar:
    """Own the sidebar tree and rebuildable project navigation."""

    def __init__(
        self,
        palette: Palette,
        logo_image,
        *,
        on_category: Callable[[str], None],
        on_project: Callable[[str | None], None],
        on_note: Callable[[str], None],
        search_delegate,
        project_action_target,
        on_reorder_project,
        on_move_note,
        themes: list[tuple[str, str]] | None = None,
    ) -> None:
        self.palette = palette
        self._themes = list(themes or ())
        self.view = solid_view(palette.sidebar_background)
        self._on_category = on_category
        self._on_project = on_project
        self._on_note = on_note
        self._project_action_target = project_action_target
        self._on_reorder_project = on_reorder_project
        self._on_move_note = on_move_note
        self._projects: list[Project] = []
        self._notes: list = []
        self._counts: dict[str, int] = {}
        self._rows: dict[str, SidebarRow] = {}
        self._note_rows: dict[str, SidebarRow] = {}
        self._active_category = ALL_NOTES
        self._active_project_id: str | None = None
        self._expanded_project_id: str | None = None
        self._active_note_id: str | None = None
        self._projects_collapsed = False
        self._pending_drop = None
        self._last_announcement = ""
        self._nav_signature = None
        self.search_field = self._build(logo_image, search_delegate)

    def _build(self, logo_image, search_delegate) -> NSSearchField:
        p = self.palette
        header = add(self.view, flipped_view())
        pin_edges(
            header,
            self.view,
            top=MAIN_COLUMN_TOP_INSET,
            leading=16,
            trailing=14,
            bottom=None,
        )
        set_height(header, 40)

        logo = add(header, NSImageView.alloc().init())
        if logo_image is not None:
            logo.setImage_(logo_image)
        logo.setImageScaling_(NSImageScaleProportionallyUpOrDown)
        pin_edges(logo, header, top=2, leading=0, trailing=None, bottom=None)
        set_width(logo, 34)
        set_height(logo, 34)

        name = add(
            header,
            label("StormPad", NSFont.boldSystemFontOfSize_(16), p.text_primary),
        )
        pin_edges(name, header, top=0, leading=46, trailing=0, bottom=None)
        tagline = add(
            header,
            label(
                "Capture ideas as they happen",
                NSFont.systemFontOfSize_(10.5),
                p.text_muted,
            ),
        )
        pin_edges(tagline, header, top=20, leading=46, trailing=0, bottom=None)

        search = add(self.view, NSSearchField.alloc().init())
        search.setDelegate_(search_delegate)
        search.setPlaceholderString_("Search notes")
        search.setFont_(NSFont.systemFontOfSize_(13))
        search.setSendsSearchStringImmediately_(True)
        search.setSendsWholeSearchString_(False)
        pin_edges(
            search,
            self.view,
            top=MAIN_COLUMN_TOP_INSET + 52,
            leading=14,
            trailing=14,
            bottom=None,
        )
        set_height(search, 30)

        nav_scroll = add(self.view, NSScrollView.alloc().init())
        nav_scroll.setDrawsBackground_(False)
        nav_scroll.setBorderType_(NSNoBorder)
        nav_scroll.setHasVerticalScroller_(True)
        nav_scroll.setAutohidesScrollers_(True)
        pin_edges(
            nav_scroll,
            self.view,
            top=MAIN_COLUMN_TOP_INSET + 92,
            leading=8,
            trailing=8,
            bottom=140,
        )
        self._nav_scroll = nav_scroll
        self._rebuild_navigation()

        # Bottom-left local workspace row (Settings / Appearance / folder).
        profile = add(
            self.view,
            build_profile_row(
                p,
                logo_image,
                menu_target=self._project_action_target,
                themes=self._themes,
            ),
        )
        pin_edges(profile, self.view, top=None, leading=14, trailing=14, bottom=12)
        set_height(profile, 44)
        self.profile_row = profile

        footer = add(
            self.view,
            rounded_view(
                p.privacy_background,
                10.0,
                border_color=p.privacy_border,
                border_width=1.0,
            ),
        )
        pin_edges(footer, self.view, top=None, leading=14, trailing=14, bottom=66)
        set_height(footer, 52)
        shield = add(
            footer,
            icon_view(symbol_image("checkmark.shield", size=15), p.accent_strong),
        )
        pin_edges(shield, footer, top=17, leading=12, trailing=None, bottom=None)
        set_width(shield, 20)
        set_height(shield, 18)
        f_title = add(
            footer,
            label(
                "Local-first & private",
                NSFont.boldSystemFontOfSize_(12),
                p.text_secondary,
            ),
        )
        pin_edges(f_title, footer, top=10, leading=40, trailing=12, bottom=None)
        f_sub = add(
            footer,
            label(
                "Everything stays on this Mac",
                NSFont.systemFontOfSize_(10.5),
                p.text_muted,
            ),
        )
        pin_edges(f_sub, footer, top=28, leading=40, trailing=12, bottom=None)
        return search

    def _row_icon(self, symbol: str, icon: str | None):
        """The row's leading glyph: an emoji label, or a tintable SF Symbol.

        An unknown or unavailable symbol falls back to the default folder, so a
        stale stored icon can never leave a Project row blank.
        """
        if project_icon_kind(icon) == "emoji":
            return (
                ProjectEmojiView.alloc().initWithGlyph_(project_icon_payload(icon)),
                False,
            )
        name = project_icon_payload(icon) if icon else symbol
        image = symbol_image(name, size=_ROW_SYMBOL_POINT) or symbol_image(
            DEFAULT_PROJECT_SYMBOL, size=_ROW_SYMBOL_POINT
        )
        view = icon_view(image, self.palette.text_muted)
        # Fit the symbol inside the fixed box preserving its aspect ratio (SF
        # Symbols are vector-backed, so proportional scaling stays crisp) and
        # centre it, so a folder that is naturally wider than tall is fully
        # visible instead of being clipped by a too-tight frame.
        view.setImageScaling_(NSImageScaleProportionallyUpOrDown)
        view.setImageAlignment_(NSImageAlignCenter)
        return view, True

    def _make_row(
        self,
        parent,
        *,
        key: str,
        title: str,
        symbol: str,
        y: float,
        on_select,
        drag_kind: str | None = None,
        source_index: int = 0,
        icon: str | None = None,
    ) -> SidebarRow:
        row = SidebarRow.alloc().initWithKey_(key)
        row.on_select = on_select
        row.action_target = self._project_action_target
        row.rename_target = self._project_action_target
        # Available immediately so a right-click context menu can tint its icons
        # even before the row's first set_selected pass.
        row._palette = self.palette
        row.drag_owner = self
        row.drag_kind = drag_kind
        row.drag_source_index = source_index
        row.setFrame_(NSMakeRect(2, y, 216, 34))
        row.setWantsLayer_(True)
        row.layer().setCornerRadius_(8.0)
        parent.addSubview_(row)

        icon_view_, is_symbol = self._row_icon(symbol, icon)
        # One fixed, vertically-centred container for symbol and emoji alike, so
        # the glyph geometry never shifts between icon types or row states.
        icon_view_.setFrame_(_ROW_ICON_BOX)
        row.addSubview_(icon_view_)
        row._icon_is_symbol = is_symbol
        name = label(
            title,
            NSFont.systemFontOfSize_(13.5),
            self.palette.text_secondary,
        )
        name_width = 84 if drag_kind == "project" else 128
        name.setFrame_(NSMakeRect(_ROW_LABEL_X, 7, name_width, 20))
        row.addSubview_(name)
        count = label(
            str(self._counts.get(key, 0)),
            NSFont.systemFontOfSize_(11.5),
            self.palette.text_muted,
        )
        count.setAlignment_(2)
        count.setFrame_(
            NSMakeRect(124, 7, 22, 20)
            if drag_kind == "project"
            else NSMakeRect(174, 7, 30, 20)
        )
        row.addSubview_(count)
        row._icon = icon_view_
        row._name = name
        row._count = count
        if drag_kind == "project":
            write = ProjectRowActionButton.alloc().initWithFrame_(
                NSMakeRect(150, 4, 26, 26)
            )
            write.setBordered_(False)
            write.setImagePosition_(NSImageOnly)
            write.setImage_(
                symbol_image("square.and.pencil", size=11.5, weight="medium")
            )
            write.setContentTintColor_(self.palette.text_muted)
            write.setTarget_(self._project_action_target)
            write.setAction_("newNoteInProject:")
            write.setRepresentedObject_(key)
            write.setToolTip_("New Note in Project")
            write.setAccessibilityLabel_("New Note in Project")
            row.addSubview_(write)

            more = ProjectRowActionButton.alloc().initWithFrame_(
                NSMakeRect(180, 4, 26, 26)
            )
            more.setBordered_(False)
            more.setImagePosition_(NSImageOnly)
            more.setImage_(symbol_image("ellipsis", size=12, weight="semibold"))
            more.setContentTintColor_(self.palette.text_muted)
            more.setTarget_(row)
            more.setAction_("showProjectMenu:")
            more.setToolTip_("Project menu")
            more.setAccessibilityLabel_("Project menu")
            row.addSubview_(more)
            row._action_controls = [write, more]
            row.registerForDraggedTypes_(
                [PROJECT_PASTEBOARD_TYPE, NOTE_PASTEBOARD_TYPE]
            )
            row.setAccessibilityLabel_(
                f"Project {title}, drag source and note drop target"
            )
        elif key == UNFILED_PROJECT_ID:
            row.registerForDraggedTypes_([NOTE_PASTEBOARD_TYPE])
            row.setAccessibilityLabel_(
                "Unfiled notes, note drop target"
            )
        else:
            row.setAccessibilityLabel_(title)
        self._rows[key] = row
        return row

    def _make_note_row(self, parent, note, y: float) -> SidebarRow:
        """Build a compact child shortcut with no Project drag/menu surface."""
        row = SidebarRow.alloc().initWithKey_(note.id)
        row.on_select = self._on_note
        row.action_target = None
        row.rename_target = None
        row.drag_owner = self
        row.drag_kind = None
        row._is_child_shortcut = True
        row._parent_project_id = note.project_id
        row._palette = self.palette
        row.setFrame_(NSMakeRect(16, y, 202, 30))
        row.setWantsLayer_(True)
        row.layer().setCornerRadius_(7.0)
        row.layer().removeAllAnimations()
        row.setBackgroundColor_(NSColor.clearColor())
        row.layer().setBorderWidth_(0.0)
        row.layer().setBorderColor_(NSColor.clearColor().CGColor())
        parent.addSubview_(row)

        name = label(
            note.title or "Untitled Note",
            NSFont.systemFontOfSize_(12.5),
            self.palette.text_secondary,
        )
        name.setFrame_(NSMakeRect(30, 5, 160, 20))
        row.addSubview_(name)
        row._icon = None
        row._icon_is_symbol = False
        row._name = name
        row._count = None
        row.registerForDraggedTypes_(
            [PROJECT_PASTEBOARD_TYPE, NOTE_PASTEBOARD_TYPE]
        )
        row.setAccessibilityLabel_(f"Open note {note.title or 'Untitled Note'}")
        self._rows[note.id] = row
        self._note_rows[note.id] = row
        return row

    def _rebuild_navigation(self) -> None:
        p = self.palette
        nav = FlippedView.alloc().init()
        nav.setFrame_(NSMakeRect(0, 0, 220, 400))
        # Fill a tall clip view as well as a short one. A shorter document view
        # is bottom-aligned by NSClipView, which visually places rows near the
        # top but leaves their apparent area outside the document hit-test
        # region. That made project/library rows intermittently unclickable.
        nav.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        self._rows = {}
        self._note_rows = {}
        y = 4.0

        library = label("LIBRARY", NSFont.systemFontOfSize_(10.5), p.text_muted)
        library.setFrame_(NSMakeRect(12, y, 190, 16))
        nav.addSubview_(library)
        y += 22
        self._make_row(
            nav,
            key=ALL_NOTES,
            title=ALL_NOTES,
            symbol=_ICONS[ALL_NOTES],
            y=y,
            on_select=lambda _key: self._on_project(None),
        )
        y += 38
        self._make_row(
            nav,
            key=UNFILED_PROJECT_ID,
            title=UNFILED,
            symbol=_ICONS[UNFILED],
            y=y,
            on_select=self._on_project,
        )
        y += 46

        disclosure = NSButton.alloc().initWithFrame_(NSMakeRect(4, y - 4, 24, 24))
        disclosure.setBordered_(False)
        disclosure.setImagePosition_(NSImageOnly)
        disclosure.setImage_(
            symbol_image(
                "chevron.right" if self._projects_collapsed else "chevron.down",
                size=9,
                weight="semibold",
            )
        )
        disclosure.setTarget_(self._project_action_target)
        disclosure.setAction_("toggleProjectsSection:")
        disclosure.setAccessibilityLabel_(
            "Expand Projects"
            if self._projects_collapsed
            else "Collapse Projects"
        )
        nav.addSubview_(disclosure)
        projects_heading = label(
            "PROJECTS", NSFont.systemFontOfSize_(10.5), p.text_muted
        )
        projects_heading.setFrame_(NSMakeRect(28, y, 130, 16))
        nav.addSubview_(projects_heading)
        create = NSButton.alloc().initWithFrame_(NSMakeRect(184, y - 5, 26, 26))
        create.setBordered_(False)
        create.setImagePosition_(NSImageOnly)
        create.setImage_(symbol_image("plus", size=11, weight="semibold"))
        create.setContentTintColor_(p.text_muted)
        create.setTarget_(self._project_action_target)
        create.setAction_("createProject:")
        create.setToolTip_("Create Project")
        create.setAccessibilityLabel_("Create Project")
        nav.addSubview_(create)
        y += 24

        if not self._projects_collapsed:
            for index, project in enumerate(self._projects):
                self._make_row(
                    nav,
                    key=project.id,
                    title=project.name,
                    symbol=DEFAULT_PROJECT_SYMBOL,
                    y=y,
                    on_select=self._on_project,
                    drag_kind="project",
                    source_index=index,
                    icon=project.icon,
                )
                y += 38
                if project.id == self._expanded_project_id:
                    for note in self._notes:
                        if note.project_id == project.id:
                            self._make_note_row(nav, note, y)
                            y += 32

        insertion = solid_view(p.accent_strong)
        insertion.setFrame_(NSMakeRect(8, y, 202, 2))
        insertion.setHidden_(True)
        insertion.setAccessibilityLabel_("Project reorder insertion position")
        nav.addSubview_(insertion)
        self._insertion_line = insertion

        y += 8
        categories = label(
            "CATEGORIES", NSFont.systemFontOfSize_(10.5), p.text_muted
        )
        categories.setFrame_(NSMakeRect(12, y, 190, 16))
        nav.addSubview_(categories)
        y += 22
        for category in CATEGORIES:
            self._make_row(
                nav,
                key=category,
                title=category,
                symbol=_ICONS[category],
                y=y,
                on_select=self._on_category,
            )
            y += 38
        viewport_height = float(self._nav_scroll.contentSize().height)
        nav.setFrameSize_((220, max(y + 8, viewport_height, 300)))
        self._nav_scroll.setDocumentView_(nav)
        self._nav = nav
        self._apply_selection()

    def _snapshot(self, row: SidebarRow):
        bounds = row.bounds()
        representation = row.bitmapImageRepForCachingDisplayInRect_(bounds)
        if representation is None:
            return None
        row.cacheDisplayInRect_toBitmapImageRep_(bounds, representation)
        image = NSImage.alloc().initWithSize_(bounds.size)
        image.addRepresentation_(representation)
        return image

    def start_project_drag(self, row: SidebarRow, event) -> bool:
        project_ids = [project.id for project in self._projects]
        if row.key not in project_ids:
            return False
        raw = encode_drag_payload(
            "project",
            row.key,
            source_project_id=None,
            source_index=project_ids.index(row.key),
        )
        writer = NSPasteboardItem.alloc().init()
        writer.setString_forType_(raw, PROJECT_PASTEBOARD_TYPE)
        dragging_item = NSDraggingItem.alloc().initWithPasteboardWriter_(writer)
        snapshot = self._snapshot(row) or symbol_image("folder", size=20)
        dragging_item.setDraggingFrame_contents_(row.bounds(), snapshot)
        row.beginDraggingSessionWithItems_event_source_(
            [dragging_item],
            event,
            row,
        )
        return True

    def _payload(self, sender):
        pasteboard = sender.draggingPasteboard()
        project_raw = pasteboard.stringForType_(PROJECT_PASTEBOARD_TYPE)
        if project_raw is not None:
            return decode_drag_payload(project_raw, expected_kind="project")
        note_raw = pasteboard.stringForType_(NOTE_PASTEBOARD_TYPE)
        if note_raw is not None:
            return decode_drag_payload(note_raw, expected_kind="note")
        return None

    def _announce(self, message: str) -> None:
        if not message or message == self._last_announcement:
            return
        self._last_announcement = message
        try:
            NSAccessibilityPostNotificationWithUserInfo(
                self.view,
                NSAccessibilityAnnouncementRequestedNotification,
                {
                    NSAccessibilityAnnouncementKey: message,
                    NSAccessibilityPriorityKey: NSAccessibilityPriorityMedium,
                },
            )
        except (AttributeError, TypeError):
            pass

    def _autoscroll(self, sender) -> None:
        point = self._nav.convertPoint_fromView_(sender.draggingLocation(), None)
        clip = self._nav_scroll.contentView()
        visible = clip.bounds()
        y = float(visible.origin.y)
        height = float(visible.size.height)
        target = y
        if float(point.y) < y + 24.0:
            target = max(0.0, y - 20.0)
        elif float(point.y) > y + height - 24.0:
            maximum = max(0.0, float(self._nav.frame().size.height) - height)
            target = min(maximum, y + 20.0)
        if target != y:
            clip.scrollToPoint_((0.0, target))
            self._nav_scroll.reflectScrolledClipView_(clip)

    def update_drag(self, row: SidebarRow, sender):
        self.clear_drag_feedback(reset_announcement=False)
        payload = self._payload(sender)
        if payload is None:
            return NSDragOperationNone
        parent_project_id = getattr(row, "_parent_project_id", None)
        if parent_project_id is not None:
            parent_row = self._rows.get(parent_project_id)
            if parent_row is None:
                return NSDragOperationNone
            row = parent_row
        project_ids = [project.id for project in self._projects]
        point = row.convertPoint_fromView_(sender.draggingLocation(), None)
        if payload.kind == "project":
            if row.key not in project_ids or payload.stable_id not in project_ids:
                return NSDragOperationNone
            row_index = project_ids.index(row.key)
            insertion = insertion_index_for_row(
                row_index,
                float(point.y),
                float(row.bounds().size.height),
            )
            line_y = (
                float(row.frame().origin.y)
                if insertion == row_index
                else float(row.frame().origin.y + row.frame().size.height)
            )
            self._insertion_line.setFrame_(NSMakeRect(8, line_y - 1, 202, 2))
            self._insertion_line.setHidden_(False)
            self._insertion_line.setAccessibilityLabel_(
                f"Insert project at position {insertion + 1}"
            )
            self._pending_drop = (payload, insertion, None)
            self._announce(f"Move project to position {insertion + 1}")
        elif payload.kind == "note":
            if row.key == UNFILED_PROJECT_ID:
                target = None
            elif row.key in project_ids:
                target = row.key
            else:
                return NSDragOperationNone
            row.set_drop_target(True)
            self._pending_drop = (payload, None, target)
            target_name = UNFILED if target is None else str(row._name.stringValue())
            self._announce(f"Move note to {target_name}")
        else:
            return NSDragOperationNone
        self._autoscroll(sender)
        return NSDragOperationMove

    def perform_drop(self, row: SidebarRow, sender) -> bool:
        if self.update_drag(row, sender) != NSDragOperationMove:
            self.clear_drag_feedback()
            return False
        payload, insertion, target = self._pending_drop
        try:
            if payload.kind == "project":
                return bool(self._on_reorder_project(payload.stable_id, insertion))
            return bool(self._on_move_note(payload.stable_id, target))
        finally:
            self.clear_drag_feedback()

    def clear_drag_feedback(self, *, reset_announcement: bool = True) -> None:
        line = getattr(self, "_insertion_line", None)
        if line is not None:
            line.setHidden_(True)
        for row in self._rows.values():
            row.set_drop_target(False)
        self._pending_drop = None
        if reset_announcement:
            self._last_announcement = ""

    def show_project_drag_preview(
        self,
        source_project_id: str,
        insertion_index: int,
    ) -> None:
        """Deterministic sanitized screenshot hook; inert in normal launches."""
        project_ids = [project.id for project in self._projects]
        if source_project_id not in project_ids:
            return
        self.clear_drag_feedback()
        source = self._rows[source_project_id]
        source.set_drag_lifted(True)
        insertion = min(max(int(insertion_index), 0), len(project_ids))
        if insertion == len(project_ids):
            anchor = self._rows[project_ids[-1]]
            line_y = float(anchor.frame().origin.y + anchor.frame().size.height)
        else:
            anchor = self._rows[project_ids[insertion]]
            line_y = float(anchor.frame().origin.y)
        self._insertion_line.setFrame_(NSMakeRect(8, line_y - 1, 202, 2))
        self._insertion_line.setHidden_(False)

    def show_note_drop_preview(self, project_id: str | None) -> None:
        """Deterministic sanitized screenshot hook; inert in normal launches."""
        key = UNFILED_PROJECT_ID if project_id is None else project_id
        row = self._rows.get(key)
        if row is None:
            return
        self.clear_drag_feedback()
        row.set_drop_target(True)

    def _apply_selection(self) -> None:
        child_states = nested_note_selection_states(
            tuple(self._note_rows),
            self._active_note_id,
        )
        for key, row in self._rows.items():
            if key in self._note_rows:
                row.set_child_selected(child_states[key], self.palette)
                continue
            else:
                selected = (
                    key == self._active_project_id
                    if self._active_project_id is not None
                    else (
                        key == self._active_category
                        if self._active_category in CATEGORIES
                        else key == ALL_NOTES
                    )
                )
            row.set_selected(selected, self.palette)

    def _navigation_signature(
        self,
        projects: list[Project],
        notes: list,
        expanded_project_id: str | None,
        collapsed: bool,
    ):
        """What actually requires rebuilding the navigation tree."""
        return (
            tuple((project.id, project.name, project.icon) for project in projects),
            expanded_project_id,
            tuple(
                (note.id, note.title)
                for note in notes
                if note.project_id == expanded_project_id
            ),
            bool(collapsed),
        )

    def set_navigation(
        self,
        projects: list[Project],
        notes: list,
        counts: dict[str, int],
        *,
        category: str,
        project_id: str | None,
        expanded_project_id: str | None,
        note_id: str | None,
        collapsed: bool,
    ) -> None:
        signature = self._navigation_signature(
            projects, notes, expanded_project_id, collapsed
        )
        self._projects = list(projects)
        self._notes = list(notes)
        self._counts = dict(counts)
        self._active_category = category
        self._active_project_id = project_id
        self._expanded_project_id = expanded_project_id
        self._active_note_id = note_id
        self._projects_collapsed = bool(collapsed)
        # Selecting a different row used to tear down and rebuild every row,
        # which is what made selection change abruptly. When only the selection
        # (or a count) moved, update in place so the surface can transition.
        if signature == self._nav_signature and self._rows:
            self.set_counts(self._counts)
            self._apply_selection()
            return
        self._nav_signature = signature
        self._rebuild_navigation()

    def set_active_category(self, category: str) -> None:
        self._active_category = category
        self._active_project_id = None
        self._apply_selection()

    def set_counts(self, counts: dict[str, int]) -> None:
        self._counts = dict(counts)
        for key, row in self._rows.items():
            if row._count is not None:
                row._count.setStringValue_(str(counts.get(key, 0)))

    def set_active_note_id(self, note_id: str | None) -> None:
        self._active_note_id = note_id
        self._apply_selection()

    def update_note_title(self, note_id: str, title: str) -> None:
        row = self._note_rows.get(note_id)
        if row is not None:
            row._name.setStringValue_(title or "Untitled Note")

    def search_string(self) -> str:
        return str(self.search_field.stringValue())

    def clear_search(self) -> None:
        self.search_field.setStringValue_("")
