"""Resolve semantic :class:`~stormpad.theme.Theme` tokens to ``NSColor``.

The single place hex strings become AppKit colors. View code asks the palette
for semantic colors (``palette.accent``) and fonts, never for literals.
"""

from __future__ import annotations

from AppKit import NSColor, NSFont

from ..theme import Theme

# NSFontDescriptorSystemDesign* constants (not always exported by PyObjC name).
_DESIGN_SERIF = 1  # NSFontDescriptorSystemDesignSerif


def color_from_hex(hex_str: str, alpha: float = 1.0) -> NSColor:
    """Build a calibrated ``NSColor`` from ``#RRGGBB``."""
    value = hex_str.lstrip("#")
    r = int(value[0:2], 16) / 255.0
    g = int(value[2:4], 16) / 255.0
    b = int(value[4:6], 16) / 255.0
    return NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, alpha)


def serif_font(size: float, weight: float = 0.0) -> NSFont:
    """Return the native serif system font (New York) at ``size``."""
    base = NSFont.systemFontOfSize_(size)
    descriptor = base.fontDescriptor().fontDescriptorWithDesign_(_DESIGN_SERIF)
    if descriptor is not None:
        serif = NSFont.fontWithDescriptor_size_(descriptor, size)
        if serif is not None:
            return serif
    return base  # pragma: no cover - fallback if serif design unavailable


def mono_font(size: float) -> NSFont:
    """Return a monospaced font (SF Mono / Menlo) at ``size``."""
    font = NSFont.monospacedSystemFontOfSize_weight_(size, 0.0)
    return font if font is not None else NSFont.fontWithName_size_("Menlo", size)


class Palette:
    """Semantic NSColors + fonts derived from a :class:`Theme`."""

    def __init__(self, theme: Theme) -> None:
        self.theme = theme

    # Surfaces
    @property
    def app_background(self) -> NSColor:
        return color_from_hex(self.theme.app_background)

    @property
    def toolbar_background(self) -> NSColor:
        return color_from_hex(self.theme.toolbar_background)

    @property
    def sidebar_background(self) -> NSColor:
        return color_from_hex(self.theme.sidebar_background)

    @property
    def note_list_background(self) -> NSColor:
        return color_from_hex(self.theme.note_list_background)

    @property
    def editor_background(self) -> NSColor:
        return color_from_hex(self.theme.editor_background)

    @property
    def elevated_surface(self) -> NSColor:
        return color_from_hex(self.theme.elevated_surface)

    @property
    def selected_background(self) -> NSColor:
        return color_from_hex(self.theme.selected_background)

    @property
    def hover_background(self) -> NSColor:
        return color_from_hex(self.theme.hover_background)

    @property
    def input_background(self) -> NSColor:
        return color_from_hex(self.theme.input_background)

    @property
    def transcript_background(self) -> NSColor:
        return color_from_hex(self.theme.transcript_background)

    # Lines
    @property
    def border(self) -> NSColor:
        return color_from_hex(self.theme.border)

    @property
    def separator(self) -> NSColor:
        return color_from_hex(self.theme.separator)

    # Text
    @property
    def text_primary(self) -> NSColor:
        return color_from_hex(self.theme.text_primary)

    @property
    def text_secondary(self) -> NSColor:
        return color_from_hex(self.theme.text_secondary)

    @property
    def text_muted(self) -> NSColor:
        return color_from_hex(self.theme.text_muted)

    # Accents / status
    @property
    def accent(self) -> NSColor:
        return color_from_hex(self.theme.accent)

    @property
    def accent_strong(self) -> NSColor:
        return color_from_hex(self.theme.accent_strong)

    @property
    def success(self) -> NSColor:
        return color_from_hex(self.theme.success)

    @property
    def danger(self) -> NSColor:
        return color_from_hex(self.theme.danger)
