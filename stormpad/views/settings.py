"""Reusable native Settings window for theme, editor, and storage preferences."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import objc
from AppKit import (
    NSAppearance,
    NSAppearanceNameAqua,
    NSAppearanceNameDarkAqua,
    NSAttributedString,
    NSBackingStoreBuffered,
    NSButton,
    NSControlStateValueOn,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSPopUpButton,
    NSSwitchButton,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSMakeRect, NSObject

from ..theme import all_themes
from .controls import label, solid_view
from .palette import Palette


class SettingsController(NSObject):
    """One reusable Settings window whose content follows the active theme."""

    def initWithOnTheme_onBlockControls_onReveal_(  # noqa: N802
        self, on_theme, on_block_controls, on_reveal
    ):
        self = objc.super(SettingsController, self).init()
        if self is None:
            return None
        self._on_theme: Callable[[str], None] = on_theme
        self._on_block_controls: Callable[[bool], None] = on_block_controls
        self._on_reveal: Callable[[str], None] = on_reveal
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 560, 470),
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
            NSBackingStoreBuffered,
            False,
        )
        self._window.setTitle_("StormPad Settings")
        self._window.setReleasedWhenClosed_(False)
        self._window.center()
        self._theme_id = ""
        self._show_controls = True
        self._notes_path = Path()
        return self

    @objc.python_method
    def show(
        self,
        palette: Palette,
        *,
        theme_id: str,
        show_controls: bool,
        notes_path: Path,
    ) -> None:
        self._theme_id = theme_id
        self._show_controls = bool(show_controls)
        self._notes_path = Path(notes_path)
        self._window.setAppearance_(
            NSAppearance.appearanceNamed_(
                NSAppearanceNameDarkAqua
                if palette.theme.is_dark
                else NSAppearanceNameAqua
            )
        )
        self._build_content(palette)
        self._window.makeKeyAndOrderFront_(None)

    @objc.python_method
    def _build_content(self, palette: Palette) -> None:
        content = solid_view(palette.editor_background)
        content.setFrame_(NSMakeRect(0, 0, 560, 470))

        title = label(
            "Settings", NSFont.boldSystemFontOfSize_(24), palette.title_text
        )
        title.setFrame_(NSMakeRect(28, 24, 504, 34))
        content.addSubview_(title)

        theme_label = label(
            "Appearance", NSFont.boldSystemFontOfSize_(13), palette.text_primary
        )
        theme_label.setFrame_(NSMakeRect(28, 78, 150, 22))
        content.addSubview_(theme_label)
        theme_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(240, 74, 292, 30), False
        )
        for theme_id, theme in all_themes().items():
            theme_popup.addItemWithTitle_(theme.name)
            theme_popup.lastItem().setRepresentedObject_(theme_id)
        selected = next(
            (
                index
                for index, theme_id in enumerate(all_themes())
                if theme_id == self._theme_id
            ),
            0,
        )
        theme_popup.selectItemAtIndex_(selected)
        theme_popup.setTarget_(self)
        theme_popup.setAction_("chooseTheme:")
        theme_popup.setAccessibilityLabel_("Theme")
        content.addSubview_(theme_popup)
        self._theme_popup = theme_popup

        editor_heading = label(
            "Editor", NSFont.boldSystemFontOfSize_(13), palette.text_primary
        )
        editor_heading.setFrame_(NSMakeRect(28, 132, 150, 22))
        content.addSubview_(editor_heading)
        controls = NSButton.alloc().initWithFrame_(NSMakeRect(236, 126, 296, 32))
        controls.setButtonType_(NSSwitchButton)
        controls.setAttributedTitle_(
            NSAttributedString.alloc().initWithString_attributes_(
                "Show Add Block on hover",
                {
                    NSFontAttributeName: NSFont.systemFontOfSize_(13),
                    NSForegroundColorAttributeName: palette.text_primary,
                },
            )
        )
        controls.setState_(NSControlStateValueOn if self._show_controls else 0)
        controls.setTarget_(self)
        controls.setAction_("toggleBlockControls:")
        controls.setContentTintColor_(palette.accent)
        controls.setAccessibilityLabel_("Show Add Block on hover")
        content.addSubview_(controls)
        self._controls_checkbox = controls

        storage_heading = label(
            "Storage", NSFont.boldSystemFontOfSize_(13), palette.text_primary
        )
        storage_heading.setFrame_(NSMakeRect(28, 194, 150, 22))
        content.addSubview_(storage_heading)
        root = self._notes_path.parent
        folders = (
            ("StormPad root", root, "Reveal StormPad Folder"),
            ("Notes", self._notes_path, "Reveal Notes Folder"),
            ("Attachments", root / "Attachments", "Reveal Attachments Folder"),
        )
        for index, (name, path, action_title) in enumerate(folders):
            y = 224 + index * 52
            name_label = label(
                name, NSFont.systemFontOfSize_(11.5), palette.text_muted
            )
            name_label.setFrame_(NSMakeRect(28, y, 106, 20))
            content.addSubview_(name_label)
            path_label = label(
                str(path), NSFont.systemFontOfSize_(11.5), palette.text_secondary
            )
            path_label.setSelectable_(True)
            path_label.setToolTip_(str(path))
            path_label.setAccessibilityLabel_(f"{name} path")
            path_label.setFrame_(NSMakeRect(134, y, 200, 20))
            content.addSubview_(path_label)
            reveal = NSButton.alloc().initWithFrame_(
                NSMakeRect(342, y - 5, 190, 28)
            )
            reveal.setTitle_(action_title)
            reveal.setTag_(index)
            reveal.setTarget_(self)
            reveal.setAction_("revealStorage:")
            reveal.setAccessibilityLabel_(action_title)
            content.addSubview_(reveal)

        detail = label(
            "Notes remain local Markdown files; exports are separate plain-text copies.",
            NSFont.systemFontOfSize_(11.5),
            palette.text_muted,
            multiline=True,
        )
        detail.setFrame_(NSMakeRect(28, 410, 504, 36))
        content.addSubview_(detail)
        self._window.setContentView_(content)

    @objc.IBAction
    def chooseTheme_(self, sender):  # noqa: N802
        theme_id = sender.selectedItem().representedObject()
        if theme_id is not None:
            self._on_theme(str(theme_id))

    @objc.IBAction
    def toggleBlockControls_(self, sender):  # noqa: N802
        self._on_block_controls(int(sender.state()) == int(NSControlStateValueOn))

    @objc.IBAction
    def revealStorage_(self, sender):  # noqa: N802
        kind = ("root", "notes", "attachments")[int(sender.tag())]
        self._on_reveal(kind)
