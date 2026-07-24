"""Compact native picker for a Project icon.

Follows the colour palette's pattern: a small fixed-size view hosted in an
``NSMenu`` custom item, so it appears beside its source control and never
resizes after opening. Each button carries its canonical icon value as its
identifier, which the controller reads back.

SF Symbols only — StormPad is native, so there are no vector icon packs — plus a
single-emoji option and a reset to the default folder.
"""

from __future__ import annotations

import objc
from AppKit import NSButton, NSColor, NSFont, NSImageOnly
from Foundation import NSMakeRect

from ..icons import (
    DEFAULT_PROJECT_SYMBOL,
    EMOJI_PREFIX,
    PROJECT_SYMBOLS,
    SUGGESTED_EMOJI,
    SYMBOL_PREFIX,
    normalize_project_icon,
    project_icon_payload,
)
from .controls import flipped_view, icon_view, label
from .palette import symbol_image

_CELL = 28.0
_GAP = 4.0
_COLUMNS = 7
_PAD = 12.0
_HEADING_H = 15.0
_SECTION_GAP = 10.0
_ROW_H = 24.0

PANEL_WIDTH = _PAD * 2 + _COLUMNS * _CELL + (_COLUMNS - 1) * _GAP

# Reset is a distinct value so it can be told apart from "no change".
CLEAR_IDENTIFIER = "__default__"
CUSTOM_EMOJI_IDENTIFIER = "__emoji__"


def _rows(count: int) -> int:
    return max(1, (count + _COLUMNS - 1) // _COLUMNS)


def _grid_height(count: int) -> float:
    rows = _rows(count)
    return rows * _CELL + (rows - 1) * _GAP


def _heading(text: str, palette):
    return label(text.upper(), NSFont.boldSystemFontOfSize_(9.5), palette.text_muted)


def picker_selected_identifier(current: str | None) -> str:
    """Map persisted/invalid values onto exactly one visible picker choice."""
    selected = normalize_project_icon(current)
    if selected is None:
        return CLEAR_IDENTIFIER
    if selected.startswith(EMOJI_PREFIX):
        glyph = project_icon_payload(selected)
        if glyph not in SUGGESTED_EMOJI:
            return CUSTOM_EMOJI_IDENTIFIER
    return selected


def picker_selection_flags(identifiers, selected_identifier: str) -> tuple[bool, ...]:
    """Exactly one peer is selected for a valid picker identifier."""
    return tuple(
        str(identifier) == str(selected_identifier)
        for identifier in identifiers
    )


def icon_picker_click_behavior(
    click_count: int,
    action_already_dispatched: bool,
) -> tuple[bool, bool]:
    """Return ``(dispatch_selection, close_picker)`` for this click."""
    if int(click_count) >= 2:
        return (not action_already_dispatched, True)
    return (True, False)


class IconPickerButton(NSButton):
    """Update the one-of-many visual selection before dispatching the action."""

    def mouseDown_(self, event):  # noqa: N802
        peers = getattr(self, "stormpad_picker_peers", ())
        palette = getattr(self, "stormpad_picker_palette", None)
        if palette is not None:
            flags = picker_selection_flags(
                (peer.identifier() for peer in peers),
                str(self.identifier()),
            )
            for peer, selected in zip(peers, flags, strict=True):
                _apply_selected_state(
                    peer,
                    selected,
                    palette,
                )
        dispatch, close = icon_picker_click_behavior(
            int(event.clickCount()),
            bool(getattr(self, "stormpad_action_dispatched", False)),
        )
        if dispatch:
            objc.super(IconPickerButton, self).mouseDown_(event)
            self.stormpad_action_dispatched = True
        if close:
            target = self.target()
            if target is not None and hasattr(target, "closeProjectIconPicker_"):
                target.closeProjectIconPicker_(self)
            else:
                item = self.enclosingMenuItem()
                menu = item.menu() if item is not None else None
                if menu is not None:
                    menu.cancelTracking()


def _apply_selected_state(button, selected: bool, palette) -> None:
    button.setWantsLayer_(True)
    button.layer().setCornerRadius_(6.0)
    button.layer().setBorderWidth_(2.0 if selected else 0.0)
    button.layer().setBorderColor_(
        (
            palette.accent_strong
            if selected
            else NSColor.clearColor()
        ).CGColor()
    )
    button.layer().setBackgroundColor_(
        (
            palette.selected_background
            if selected
            else NSColor.clearColor()
        ).CGColor()
    )
    badge = getattr(button, "stormpad_selection_badge", None)
    if badge is not None:
        badge.setHidden_(not selected)
    original_title = getattr(button, "stormpad_original_title", None)
    if original_title is not None:
        button.setTitle_(f"✓  {original_title}" if selected else original_title)
    button.setAccessibilityValue_("Selected" if selected else "Not selected")


def _cell_button(*, palette, identifier: str, selected: bool, target, action: str) -> NSButton:
    button = IconPickerButton.alloc().initWithFrame_(NSMakeRect(0, 0, _CELL, _CELL))
    button.setBordered_(False)
    button.setIdentifier_(identifier)
    button.setTarget_(target)
    button.setAction_(action)
    badge = icon_view(
        symbol_image("checkmark.circle.fill", size=9, weight="semibold"),
        palette.accent_strong,
    )
    badge.setFrame_(NSMakeRect(16, 1, 11, 11))
    button.addSubview_(badge)
    button.stormpad_selection_badge = badge
    _apply_selected_state(button, selected, palette)
    return button


def _symbol_cell(*, palette, name: str, selected: bool, target, action: str) -> NSButton:
    button = _cell_button(
        palette=palette,
        identifier=f"{SYMBOL_PREFIX}{name}",
        selected=selected,
        target=target,
        action=action,
    )
    # A symbol missing on this macOS falls back to the folder rather than
    # rendering an empty cell.
    image = symbol_image(name, size=14) or symbol_image(DEFAULT_PROJECT_SYMBOL, size=14)
    if image is not None:
        button.setImage_(image)
        button.setImagePosition_(NSImageOnly)
    button.setContentTintColor_(palette.text_secondary)
    readable = name.replace(".", " ")
    button.setToolTip_(readable)
    button.setAccessibilityLabel_(f"Project icon {readable}")
    return button


def _emoji_cell(*, palette, glyph: str, selected: bool, target, action: str) -> NSButton:
    button = _cell_button(
        palette=palette,
        identifier=f"{EMOJI_PREFIX}{glyph}",
        selected=selected,
        target=target,
        action=action,
    )
    button.setTitle_(glyph)
    button.setFont_(NSFont.systemFontOfSize_(15))
    button.setToolTip_(f"Project icon {glyph}")
    button.setAccessibilityLabel_(f"Project icon {glyph}")
    return button


def _text_row(
    *,
    palette,
    title: str,
    identifier: str,
    selected: bool,
    target,
    action: str,
) -> NSButton:
    button = IconPickerButton.alloc().initWithFrame_(
        NSMakeRect(0, 0, PANEL_WIDTH - _PAD * 2, _ROW_H)
    )
    button.setBordered_(False)
    button.setTitle_(title)
    button.setFont_(NSFont.systemFontOfSize_(12))
    button.setContentTintColor_(palette.text_secondary)
    button.setAlignment_(0)  # NSTextAlignmentLeft
    button.setIdentifier_(identifier)
    button.setTarget_(target)
    button.setAction_(action)
    button.setAccessibilityLabel_(title)
    button.stormpad_original_title = title
    _apply_selected_state(button, selected, palette)
    return button


def build_icon_picker_view(
    palette,
    *,
    current: str | None,
    target,
    action: str = "setProjectIcon:",
):
    """Build the fixed-size icon picker panel and return its view."""
    selected_identifier = picker_selected_identifier(current)
    picker_buttons: list[NSButton] = []

    height = _PAD
    height += _HEADING_H + 4.0 + _grid_height(len(PROJECT_SYMBOLS)) + _SECTION_GAP
    height += _HEADING_H + 4.0 + _grid_height(len(SUGGESTED_EMOJI)) + _SECTION_GAP
    height += _ROW_H * 2 + _GAP + _PAD

    view = flipped_view()
    view.setFrame_(NSMakeRect(0, 0, PANEL_WIDTH, height))
    view.setBackgroundColor_(palette.formatting_background)

    y = _PAD
    for title, values, builder in (
        ("Icons", PROJECT_SYMBOLS, _symbol_cell),
        ("Emoji", SUGGESTED_EMOJI, _emoji_cell),
    ):
        head = _heading(title, palette)
        head.setFrame_(NSMakeRect(_PAD, y, PANEL_WIDTH - _PAD * 2, _HEADING_H))
        view.addSubview_(head)
        y += _HEADING_H + 4.0
        for index, value in enumerate(values):
            canonical = normalize_project_icon(value)
            kwargs = {"name": value} if builder is _symbol_cell else {"glyph": value}
            button = builder(
                palette=palette,
                selected=canonical is not None and canonical == selected_identifier,
                target=target,
                action=action,
                **kwargs,
            )
            picker_buttons.append(button)
            button.setFrame_(
                NSMakeRect(
                    _PAD + (index % _COLUMNS) * (_CELL + _GAP),
                    y + (index // _COLUMNS) * (_CELL + _GAP),
                    _CELL,
                    _CELL,
                )
            )
            view.addSubview_(button)
        y += _grid_height(len(values)) + _SECTION_GAP

    for title, identifier in (
        ("Choose Emoji…", CUSTOM_EMOJI_IDENTIFIER),
        ("Use Default Folder", CLEAR_IDENTIFIER),
    ):
        row = _text_row(
            palette=palette,
            title=title,
            identifier=identifier,
            selected=identifier == selected_identifier,
            target=target,
            action=action,
        )
        picker_buttons.append(row)
        row.setFrame_(NSMakeRect(_PAD, y, PANEL_WIDTH - _PAD * 2, _ROW_H))
        view.addSubview_(row)
        y += _ROW_H + _GAP

    for button in picker_buttons:
        button.stormpad_picker_peers = picker_buttons
        button.stormpad_picker_palette = palette
    view.stormpad_selected_identifier = selected_identifier
    return view
