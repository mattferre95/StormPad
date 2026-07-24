"""Bottom-left local profile row and its menu.

A compact, discoverable access point for Settings, Appearance, the StormPad
folder, About, and Quit — in the shape people expect from the bottom of a
sidebar. StormPad has no accounts, so this deliberately shows only a local
workspace label: no sign-in, upgrade, subscription, sync, or online profile.

The menu is built from the declarative spec in :mod:`stormpad.uihelpers`, so its
Appearance items route through the same ``selectTheme:`` action as the View menu.
"""

from __future__ import annotations

import objc
from AppKit import (
    NSFont,
    NSImageScaleProportionallyUpOrDown,
    NSImageView,
    NSMenu,
    NSMenuItem,
)
from Foundation import NSMakePoint, NSMakeRect, NSPointInRect

from ..motion import Motion
from ..uihelpers import (
    PROFILE_SUBTITLE,
    MenuEntry,
    TransientMenuState,
    profile_display_name,
    profile_menu_spec,
)
from .controls import FlippedView, label
from .layout import add, pin_edges, set_height, set_width
from .motion import anim, can_animate, current_policy, run
from .palette import menu_icon, symbol_image


def macos_display_name() -> str:
    """The macOS display name, or the neutral fallback if unavailable."""
    try:
        from Foundation import NSFullUserName

        return profile_display_name(str(NSFullUserName()))
    except (ImportError, AttributeError, TypeError):  # pragma: no cover - defensive
        return profile_display_name(None)


def build_profile_menu(spec: tuple[MenuEntry, ...], target, palette=None) -> NSMenu:
    """Realise a declarative menu spec as a native ``NSMenu``.

    Items with an explicit target are routed to the controller; ``About`` and
    ``Quit`` intentionally keep a nil target so they travel the standard
    responder chain like every other macOS app. When a ``palette`` is supplied,
    each row gets its accent-tinted SF Symbol (Quit stays neutral, never red)
    and its ⌘ shortcut hint, matching the menu reference within native AppKit.
    """
    menu = NSMenu.alloc().initWithTitle_("StormPad")
    responder_chain_actions = {"orderFrontStandardAboutPanel:", "terminate:"}
    for entry in spec:
        if entry.is_separator:
            menu.addItem_(NSMenuItem.separatorItem())
            continue
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            entry.title, entry.action or None, entry.key or ""
        )
        if entry.action and entry.action not in responder_chain_actions:
            item.setTarget_(target)
        if entry.represented is not None:
            item.setRepresentedObject_(entry.represented)
        if palette is not None and entry.icon:
            # Quit is deliberately neutral (never red or accent); everything else
            # carries the theme accent so icons read as one aligned column.
            tint = palette.text_muted if entry.action == "terminate:" else palette.accent_strong
            image = menu_icon(entry.icon, tint)
            if image is not None:
                item.setImage_(image)
        if entry.submenu:
            item.setSubmenu_(build_profile_menu(entry.submenu, target, palette))
        menu.addItem_(item)
    return menu


class ProfileRow(FlippedView):
    """Clickable local-workspace row that presents the StormPad menu."""

    def initWithPalette_(self, palette):  # noqa: N802
        self = objc.super(ProfileRow, self).init()
        if self is None:
            return None
        self._palette = palette
        self._menu_state = TransientMenuState()
        self.menu_target = None
        self.themes: list[tuple[str, str]] = []
        return self

    @objc.python_method
    def menu_is_open(self) -> bool:
        return self._menu_state.is_open

    def hitTest_(self, point):  # noqa: N802
        # Treat the composed avatar/labels/chevron and the empty area as one
        # native menu target. AppKit supplies the point in the *superview's*
        # coordinate space; comparing it directly against local bounds rejected
        # every click (the row is not at its superview's origin), which is why
        # the row appeared dead. Convert first, matching SidebarRow.
        local = self.convertPoint_fromView_(point, self.superview())
        return self if NSPointInRect(local, self.bounds()) else None

    def mouseDown_(self, event):  # noqa: N802
        self._present_menu(event)

    def rightMouseDown_(self, event):  # noqa: N802
        self._present_menu(event)

    @objc.python_method
    def _present_menu(self, event) -> None:
        # A click while the menu is up is the dismissal, not a new request.
        if not self._menu_state.accepts_clicks or self.menu_target is None:
            return
        menu = build_profile_menu(
            profile_menu_spec(self.themes), self.menu_target, self._palette
        )
        self._menu_state.opened()
        self._apply_surface(pressed=True)
        try:
            # Anchor the menu's last item at the row's top-left so it reveals
            # upward, out of the sidebar's bottom edge. AppKit keeps it on
            # screen, and menu tracking is modal — it returns once dismissed by
            # an outside click or Escape.
            last = menu.numberOfItems() - 1
            menu.popUpMenuPositioningItem_atLocation_inView_(
                menu.itemAtIndex_(last) if last >= 0 else None,
                NSMakePoint(0.0, 0.0),
                self,
            )
        finally:
            # Always restored, so a dismissed menu can never leave the sidebar
            # swallowing clicks.
            self._menu_state.closed()
            self._apply_surface(pressed=False)

    def mouseUp_(self, event):  # noqa: N802
        # Consumed by menu tracking; nothing to do, but the row must not fall
        # through to a selection.
        return

    @objc.python_method
    def _apply_surface(self, *, pressed: bool) -> None:
        policy = current_policy()
        duration = policy.duration(Motion.FAST) if can_animate(self) else 0.0
        color = self._palette.hover_background if pressed else self._palette.elevated_surface

        def body(animated: bool) -> None:
            anim(self, animated).setAlphaValue_(0.85 if pressed else 1.0)
            self.setBackgroundColor_(color)

        run(duration, body)


def build_profile_row(
    palette,
    logo_image,
    *,
    menu_target,
    themes: list[tuple[str, str]],
) -> ProfileRow:
    """Build the compact local-workspace row for the sidebar footer."""
    row = ProfileRow.alloc().initWithPalette_(palette)
    row.setWantsLayer_(True)
    row.setBackgroundColor_(palette.elevated_surface)
    row.layer().setCornerRadius_(10.0)
    row.layer().setBorderWidth_(1.0)
    row.layer().setBorderColor_(palette.border.CGColor())
    row.menu_target = menu_target
    row.themes = list(themes)

    avatar = add(row, NSImageView.alloc().init())
    if logo_image is not None:
        avatar.setImage_(logo_image)
    avatar.setImageScaling_(NSImageScaleProportionallyUpOrDown)
    avatar.setWantsLayer_(True)
    if avatar.layer() is not None:
        avatar.layer().setCornerRadius_(13.0)  # circular
        avatar.layer().setMasksToBounds_(True)
    pin_edges(avatar, row, top=9, leading=9, trailing=None, bottom=None)
    set_width(avatar, 26)
    set_height(avatar, 26)

    name = add(
        row,
        label(macos_display_name(), NSFont.boldSystemFontOfSize_(12), palette.text_primary),
    )
    pin_edges(name, row, top=8, leading=43, trailing=26, bottom=None)
    subtitle = add(
        row,
        label(PROFILE_SUBTITLE, NSFont.systemFontOfSize_(10.5), palette.text_muted),
    )
    pin_edges(subtitle, row, top=24, leading=43, trailing=26, bottom=None)

    chevron = add(row, NSImageView.alloc().init())
    chevron.setImage_(symbol_image("chevron.up.chevron.down", size=9, weight="semibold"))
    chevron.setContentTintColor_(palette.text_muted)
    pin_edges(chevron, row, top=None, leading=None, trailing=10, bottom=None)
    chevron.centerYAnchor().constraintEqualToAnchor_(row.centerYAnchor()).setActive_(True)
    set_width(chevron, 12)
    set_height(chevron, 16)

    row.setAccessibilityLabel_(
        f"{macos_display_name()}, {PROFILE_SUBTITLE}. Opens StormPad settings menu."
    )
    row.setToolTip_("Settings, Appearance, and StormPad folder")
    row.setFrame_(NSMakeRect(0, 0, 220, 44))
    return row
