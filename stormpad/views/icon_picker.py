"""Compact native picker for a Project icon.

Follows the colour palette's pattern: a small fixed-size view hosted in an
``NSMenu`` custom item, so it appears beside its source control and never
resizes after opening. Each button carries its canonical icon value as its
identifier, which the controller reads back.

SF Symbols only — StormPad is native, so there are no vector icon packs — plus a
single-emoji option and a reset to the default folder.
"""

from __future__ import annotations

from AppKit import NSButton, NSFont, NSImageOnly
from Foundation import NSMakeRect

from ..icons import (
    DEFAULT_PROJECT_SYMBOL,
    EMOJI_PREFIX,
    PROJECT_SYMBOLS,
    SUGGESTED_EMOJI,
    SYMBOL_PREFIX,
    normalize_project_icon,
)
from .controls import flipped_view, label
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


def _cell_button(*, palette, identifier: str, selected: bool, target, action: str) -> NSButton:
    button = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, _CELL, _CELL))
    button.setBordered_(False)
    button.setWantsLayer_(True)
    button.layer().setCornerRadius_(6.0)
    if selected:
        button.layer().setBorderWidth_(2.0)
        button.layer().setBorderColor_(palette.accent_strong.CGColor())
    button.setIdentifier_(identifier)
    button.setTarget_(target)
    button.setAction_(action)
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


def _text_row(*, palette, title: str, identifier: str, target, action: str) -> NSButton:
    button = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, PANEL_WIDTH - _PAD * 2, _ROW_H))
    button.setBordered_(False)
    button.setTitle_(title)
    button.setFont_(NSFont.systemFontOfSize_(12))
    button.setContentTintColor_(palette.text_secondary)
    button.setAlignment_(0)  # NSTextAlignmentLeft
    button.setIdentifier_(identifier)
    button.setTarget_(target)
    button.setAction_(action)
    button.setAccessibilityLabel_(title)
    return button


def build_icon_picker_view(
    palette,
    *,
    current: str | None,
    target,
    action: str = "setProjectIcon:",
):
    """Build the fixed-size icon picker panel and return its view."""
    selected = normalize_project_icon(current)

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
                selected=canonical is not None and canonical == selected,
                target=target,
                action=action,
                **kwargs,
            )
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
            target=target,
            action=action,
        )
        row.setFrame_(NSMakeRect(_PAD, y, PANEL_WIDTH - _PAD * 2, _ROW_H))
        view.addSubview_(row)
        y += _ROW_H + _GAP

    return view
