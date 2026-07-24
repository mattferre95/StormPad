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
    NSFont,
    NSImage,
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
from Foundation import NSMakeRect, NSPointInRect

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
from .layout import add, pin_edges, set_height, set_width
from .motion import anim, can_animate, current_policy, run
from .palette import Palette, symbol_image
from .profile import build_profile_row

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
        # Double-click on a project name starts inline renaming; a drag never
        # begins from it because the editable field takes over the row.
        if (
            event is not None
            and self.drag_kind == "project"
            and int(event.clickCount()) >= 2
            and not self._drag_started
        ):
            self._mouse_down_point = None
            self.begin_inline_rename()
            return
        if not self._drag_started and self.on_select is not None:
            self.on_select(self.key)
        self._mouse_down_point = None
        self._drag_started = False

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
        if (
            not self._selected
            and not self._drop_target
            and not self._drag_lifted
            and self._palette is not None
        ):
            self.setBackgroundColor_(self._palette.hover_background)

    def mouseExited_(self, event):  # noqa: N802
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
        menu = NSMenu.alloc().initWithTitle_("Project")
        for title, action in (
            ("Rename Project…", "renameProject:"),
            ("Choose Icon…", "chooseProjectIcon:"),
            ("New Note in Project", "newNoteInProject:"),
            ("Share Project…", "shareProject:"),
            ("Reveal Project Folder in Finder", "revealProject:"),
            ("Move Project Up", "moveProjectUp:"),
            ("Move Project Down", "moveProjectDown:"),
            ("Delete Project…", "deleteProject:"),
        ):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                title, action, ""
            )
            item.setTarget_(self.action_target)
            item.setRepresentedObject_(self.key)
            menu.addItem_(item)
            if action in ("revealProject:", "moveProjectDown:"):
                menu.addItem_(NSMenuItem.separatorItem())
        return menu

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
            else NSColor.clearColor()
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
        self._name.setTextColor_(
            palette.text_primary if selected else palette.text_secondary
        )
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
        self._project_action_target = project_action_target
        self._on_reorder_project = on_reorder_project
        self._on_move_note = on_move_note
        self._projects: list[Project] = []
        self._counts: dict[str, int] = {}
        self._rows: dict[str, SidebarRow] = {}
        self._active_category = ALL_NOTES
        self._active_project_id: str | None = None
        self._projects_collapsed = False
        self._pending_drop = None
        self._last_announcement = ""
        self._nav_signature = None
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
        pin_edges(search, self.view, top=104, leading=14, trailing=14, bottom=None)
        set_height(search, 30)

        nav_scroll = add(self.view, NSScrollView.alloc().init())
        nav_scroll.setDrawsBackground_(False)
        nav_scroll.setBorderType_(NSNoBorder)
        nav_scroll.setHasVerticalScroller_(True)
        nav_scroll.setAutohidesScrollers_(True)
        pin_edges(nav_scroll, self.view, top=144, leading=8, trailing=8, bottom=140)
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
            glyph = label(
                project_icon_payload(icon),
                NSFont.systemFontOfSize_(14),
                self.palette.text_primary,
            )
            glyph.setAlignment_(1)  # centred
            return glyph, False
        name = project_icon_payload(icon) if icon else symbol
        image = symbol_image(name, size=13) or symbol_image(
            DEFAULT_PROJECT_SYMBOL, size=13
        )
        return icon_view(image, self.palette.text_muted), True

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
        row.drag_owner = self
        row.drag_kind = drag_kind
        row.drag_source_index = source_index
        row.setFrame_(NSMakeRect(2, y, 216, 34))
        row.setWantsLayer_(True)
        row.layer().setCornerRadius_(8.0)
        parent.addSubview_(row)

        icon_view_, is_symbol = self._row_icon(symbol, icon)
        # An emoji needs a slightly taller box than a template symbol so its
        # descender is never clipped; both stay optically on the same baseline.
        icon_view_.setFrame_(
            NSMakeRect(12, 9, 17, 16) if is_symbol else NSMakeRect(11, 7, 19, 21)
        )
        row.addSubview_(icon_view_)
        row._icon_is_symbol = is_symbol
        name = label(
            title,
            NSFont.systemFontOfSize_(13.5),
            self.palette.text_secondary,
        )
        name.setFrame_(NSMakeRect(38, 7, 132, 20))
        row.addSubview_(name)
        count = label(
            str(self._counts.get(key, 0)),
            NSFont.systemFontOfSize_(11.5),
            self.palette.text_muted,
        )
        count.setAlignment_(2)
        count.setFrame_(NSMakeRect(174, 7, 30, 20))
        row.addSubview_(count)
        row._icon = icon_view_
        row._name = name
        row._count = count
        if drag_kind == "project":
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
        for key, row in self._rows.items():
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

    def _navigation_signature(self, projects: list[Project], collapsed: bool):
        """What actually requires rebuilding the navigation tree."""
        return (
            tuple((project.id, project.name, project.icon) for project in projects),
            bool(collapsed),
        )

    def set_navigation(
        self,
        projects: list[Project],
        counts: dict[str, int],
        *,
        category: str,
        project_id: str | None,
        collapsed: bool,
    ) -> None:
        signature = self._navigation_signature(projects, collapsed)
        self._projects = list(projects)
        self._counts = dict(counts)
        self._active_category = category
        self._active_project_id = project_id
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
            row._count.setStringValue_(str(counts.get(key, 0)))

    def search_string(self) -> str:
        return str(self.search_field.stringValue())

    def clear_search(self) -> None:
        self.search_field.setStringValue_("")
