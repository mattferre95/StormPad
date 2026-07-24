"""Compact visual colour palette for the floating formatting panel.

Native AppKit only. Builds a small panel with three sections — Recently used,
Text color, Background color — laid out as square swatches. Swatch buttons carry
the existing ``"mode:token"`` payload, so they reuse the editor's established
``chooseColor:`` action and its Markdown behaviour (``default`` removes the
semantic attribute rather than writing a transparent token).

Colour names live in tooltips and accessibility labels rather than beside every
swatch, keeping the panel compact.
"""

from __future__ import annotations

from AppKit import (
    NSBezierPath,
    NSButton,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSImage,
    NSImageOnly,
)
from Foundation import NSMakePoint, NSMakeRect, NSMakeSize, NSString

from .controls import flipped_view, label

# Swatch order shown in both grids (five per row).
PALETTE_ORDER: tuple[str, ...] = (
    "default",
    "gray",
    "brown",
    "orange",
    "yellow",
    "green",
    "blue",
    "purple",
    "pink",
    "red",
)

_SWATCH = 24.0
_GAP = 6.0
_COLUMNS = 5
_PAD = 14.0
_HEADING_H = 15.0
_SECTION_GAP = 10.0

PANEL_WIDTH = _PAD * 2 + _COLUMNS * _SWATCH + (_COLUMNS - 1) * _GAP


def color_display_name(token: str, mode: str) -> str:
    """Human name for a token, used in tooltips and accessibility labels."""
    if token == "default":
        return "Default" if mode == "text" else "Clear / Transparent"
    return token.replace("_", " ").title()


def swatch_image(
    color: NSColor,
    *,
    mode: str,
    token: str,
    selected: bool,
    border: NSColor,
    accent: NSColor,
    muted: NSColor,
    surface: NSColor,
) -> NSImage:
    """A square, slightly rounded swatch.

    Text swatches show an ``A`` in the target colour; background swatches show
    the fill itself. ``default`` is drawn empty with a diagonal slash so Clear /
    Transparent is recognisable.
    """
    image = NSImage.alloc().initWithSize_(NSMakeSize(_SWATCH, _SWATCH))
    image.lockFocus()
    rect = NSMakeRect(1.5, 1.5, _SWATCH - 3.0, _SWATCH - 3.0)
    path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(rect, 5.0, 5.0)

    is_clear = token == "default"
    if mode == "highlight":
        (surface if is_clear else color).setFill()
    else:
        surface.setFill()
    path.fill()

    if is_clear:
        slash = NSBezierPath.bezierPath()
        slash.moveToPoint_(NSMakePoint(5.0, 5.0))
        slash.lineToPoint_(NSMakePoint(_SWATCH - 5.0, _SWATCH - 5.0))
        slash.setLineWidth_(1.5)
        muted.setStroke()
        slash.stroke()
    elif mode == "text":
        glyph = NSString.stringWithString_("A")
        attrs = {
            NSFontAttributeName: NSFont.boldSystemFontOfSize_(13.0),
            NSForegroundColorAttributeName: color,
        }
        size = glyph.sizeWithAttributes_(attrs)
        origin = NSMakePoint(
            (_SWATCH - float(size.width)) / 2.0,
            (_SWATCH - float(size.height)) / 2.0,
        )
        glyph.drawAtPoint_withAttributes_(origin, attrs)

    (accent if selected else border).setStroke()
    path.setLineWidth_(2.0 if selected else 1.0)
    path.stroke()
    image.unlockFocus()
    return image


def _swatch_button(
    *,
    palette,
    mode: str,
    token: str,
    selected: bool,
    target,
    action: str,
) -> NSButton:
    button = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, _SWATCH, _SWATCH))
    button.setBordered_(False)
    button.setImagePosition_(NSImageOnly)
    color = (
        palette.editor_text
        if token == "default"
        else palette.color(f"inline_{token}", 1.0 if mode == "text" else 0.85)
    )
    button.setImage_(
        swatch_image(
            color,
            mode=mode,
            token=token,
            selected=selected,
            border=palette.formatting_border,
            accent=palette.accent_strong,
            muted=palette.text_muted,
            surface=palette.formatting_background,
        )
    )
    button.setTarget_(target)
    button.setAction_(action)
    button.setIdentifier_(f"{mode}:{token}")
    name = color_display_name(token, mode)
    kind = "Text" if mode == "text" else "Background"
    button.setToolTip_(f"{kind} color: {name}")
    button.setAccessibilityLabel_(f"{kind} color: {name}")
    return button


def _heading(text: str, palette):
    return label(text.upper(), NSFont.boldSystemFontOfSize_(9.5), palette.text_muted)


def build_color_palette_view(
    palette,
    *,
    recents: list[str],
    selected_text: str,
    selected_highlight: str,
    target,
    action: str = "chooseColor:",
):
    """Build the compact palette panel and return its view."""
    sections: list[tuple[str, list[tuple[str, str]]]] = []
    trimmed = [entry for entry in (recents or []) if ":" in entry][:_COLUMNS]
    if trimmed:
        pairs = []
        for entry in trimmed:
            mode, _, token = entry.partition(":")
            if mode in {"text", "highlight"} and token:
                pairs.append((mode, token))
        if pairs:
            sections.append(("Recently used", pairs))
    sections.append(("Text color", [("text", token) for token in PALETTE_ORDER]))
    sections.append(("Background color", [("highlight", token) for token in PALETTE_ORDER]))

    # Measure.
    height = _PAD
    for _, pairs in sections:
        rows = max(1, (len(pairs) + _COLUMNS - 1) // _COLUMNS)
        height += _HEADING_H + 4.0 + rows * _SWATCH + (rows - 1) * _GAP + _SECTION_GAP
    height = height - _SECTION_GAP + _PAD

    view = flipped_view()
    view.setFrame_(NSMakeRect(0, 0, PANEL_WIDTH, height))
    view.setBackgroundColor_(palette.formatting_background)

    y = _PAD
    for title, pairs in sections:
        head = _heading(title, palette)
        head.setFrame_(NSMakeRect(_PAD, y, PANEL_WIDTH - _PAD * 2, _HEADING_H))
        view.addSubview_(head)
        y += _HEADING_H + 4.0
        for index, (mode, token) in enumerate(pairs):
            column = index % _COLUMNS
            row = index // _COLUMNS
            chosen = selected_text if mode == "text" else selected_highlight
            button = _swatch_button(
                palette=palette,
                mode=mode,
                token=token,
                selected=token == chosen,
                target=target,
                action=action,
            )
            button.setFrame_(
                NSMakeRect(
                    _PAD + column * (_SWATCH + _GAP),
                    y + row * (_SWATCH + _GAP),
                    _SWATCH,
                    _SWATCH,
                )
            )
            view.addSubview_(button)
        rows = max(1, (len(pairs) + _COLUMNS - 1) // _COLUMNS)
        y += rows * _SWATCH + (rows - 1) * _GAP + _SECTION_GAP
    return view
