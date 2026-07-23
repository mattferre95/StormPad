"""Sidebar navigation for library, Projects, categories, and local privacy."""

from __future__ import annotations

from collections.abc import Callable

import objc
from AppKit import (
    NSButton,
    NSColor,
    NSFont,
    NSImageOnly,
    NSImageScaleProportionallyUpOrDown,
    NSImageView,
    NSMenu,
    NSMenuItem,
    NSNoBorder,
    NSScrollView,
    NSSearchField,
    NSTrackingActiveInKeyWindow,
    NSTrackingArea,
    NSTrackingInVisibleRect,
    NSTrackingMouseEnteredAndExited,
    NSViewWidthSizable,
)
from Foundation import NSMakeRect

from ..models import ALL_NOTES, CATEGORIES, UNFILED, UNFILED_PROJECT_ID, Project
from .controls import FlippedView, flipped_view, icon_view, label, rounded_view, solid_view
from .layout import add, pin_edges, set_height, set_width
from .palette import Palette, symbol_image

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
        self._palette: Palette | None = None
        self.on_select: Callable[[str], None] | None = None
        self.action_target = None
        area = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
            NSMakeRect(0, 0, 0, 0), _TRACKING_OPTS, self, None
        )
        self.addTrackingArea_(area)
        return self

    def mouseDown_(self, event):  # noqa: N802
        if self.on_select is not None:
            self.on_select(self.key)

    def mouseEntered_(self, event):  # noqa: N802
        if not self._selected and self._palette is not None:
            self.setBackgroundColor_(self._palette.hover_background)

    def mouseExited_(self, event):  # noqa: N802
        if not self._selected:
            self.setBackgroundColor_(NSColor.clearColor())

    def rightMouseDown_(self, event):  # noqa: N802
        if self.action_target is None or self.key in {
            ALL_NOTES,
            UNFILED_PROJECT_ID,
            *CATEGORIES,
        }:
            objc.super(SidebarRow, self).rightMouseDown_(event)
            return
        menu = NSMenu.alloc().initWithTitle_("Project")
        for title, action in (
            ("Rename Project…", "renameProject:"),
            ("New Note in Project", "newNoteInProject:"),
            ("Reveal Project Folder in Finder", "revealProject:"),
            ("Delete Project…", "deleteProject:"),
        ):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                title, action, ""
            )
            item.setTarget_(self.action_target)
            item.setRepresentedObject_(self.key)
            menu.addItem_(item)
            if action == "revealProject:":
                menu.addItem_(NSMenuItem.separatorItem())
        NSMenu.popUpContextMenu_withEvent_forView_(menu, event, self)

    def set_selected(self, selected: bool, palette: Palette) -> None:
        self._selected = bool(selected)
        self._palette = palette
        self.setBackgroundColor_(
            palette.selected_background if selected else NSColor.clearColor()
        )
        self.layer().setBorderWidth_(1.0 if selected else 0.0)
        self.layer().setBorderColor_(
            palette.selected_border.CGColor()
            if selected
            else NSColor.clearColor().CGColor()
        )
        self._name.setTextColor_(
            palette.text_primary if selected else palette.text_secondary
        )
        self._count.setTextColor_(
            palette.text_secondary if selected else palette.text_muted
        )
        self._icon.setContentTintColor_(
            palette.accent_strong if selected else palette.text_muted
        )


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
    ) -> None:
        self.palette = palette
        self.view = solid_view(palette.sidebar_background)
        self._on_category = on_category
        self._on_project = on_project
        self._project_action_target = project_action_target
        self._projects: list[Project] = []
        self._counts: dict[str, int] = {}
        self._rows: dict[str, SidebarRow] = {}
        self._active_category = ALL_NOTES
        self._active_project_id: str | None = None
        self._projects_collapsed = False
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
        pin_edges(nav_scroll, self.view, top=144, leading=8, trailing=8, bottom=82)
        self._nav_scroll = nav_scroll
        self._rebuild_navigation()

        footer = add(
            self.view,
            rounded_view(
                p.privacy_background,
                10.0,
                border_color=p.privacy_border,
                border_width=1.0,
            ),
        )
        pin_edges(footer, self.view, top=None, leading=14, trailing=14, bottom=16)
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

    def _make_row(
        self,
        parent,
        *,
        key: str,
        title: str,
        symbol: str,
        y: float,
        on_select,
    ) -> SidebarRow:
        row = SidebarRow.alloc().initWithKey_(key)
        row.on_select = on_select
        row.action_target = self._project_action_target
        row.setFrame_(NSMakeRect(2, y, 216, 34))
        row.setWantsLayer_(True)
        row.layer().setCornerRadius_(8.0)
        parent.addSubview_(row)

        icon = icon_view(symbol_image(symbol, size=13), self.palette.text_muted)
        icon.setFrame_(NSMakeRect(12, 9, 17, 16))
        row.addSubview_(icon)
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
        row._icon = icon
        row._name = name
        row._count = count
        self._rows[key] = row
        return row

    def _rebuild_navigation(self) -> None:
        p = self.palette
        nav = FlippedView.alloc().init()
        nav.setFrame_(NSMakeRect(0, 0, 220, 400))
        nav.setAutoresizingMask_(NSViewWidthSizable)
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
            for project in self._projects:
                self._make_row(
                    nav,
                    key=project.id,
                    title=project.name,
                    symbol="folder",
                    y=y,
                    on_select=self._on_project,
                )
                y += 38

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
        nav.setFrameSize_((220, max(y + 8, 300)))
        self._nav_scroll.setDocumentView_(nav)
        self._nav = nav
        self._apply_selection()

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

    def set_navigation(
        self,
        projects: list[Project],
        counts: dict[str, int],
        *,
        category: str,
        project_id: str | None,
        collapsed: bool,
    ) -> None:
        self._projects = list(projects)
        self._counts = dict(counts)
        self._active_category = category
        self._active_project_id = project_id
        self._projects_collapsed = bool(collapsed)
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
