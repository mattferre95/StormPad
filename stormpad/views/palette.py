"""Resolve semantic :class:`~stormpad.theme.Theme` tokens to AppKit values.

The single place hex strings become ``NSColor`` and where fonts / SF Symbols /
gradients are produced. View code asks the palette for semantic names
(``palette.accent``, ``palette.selected_glow``) and never for literals.

Token access is dynamic: ``palette.<token>`` returns the token's ``NSColor``
(or the raw float for numeric tokens). A few legacy names are aliased so older
view code keeps working.
"""

from __future__ import annotations

from AppKit import (
    NSColor,
    NSFont,
    NSFontWeightMedium,
    NSFontWeightRegular,
    NSFontWeightSemibold,
    NSImage,
    NSImageSymbolConfiguration,
    NSImageSymbolScaleMedium,
)

from ..theme import Theme

_DESIGN_SERIF = 1  # NSFontDescriptorSystemDesignSerif

# Legacy token names -> current names (keeps pre-Phase-5 view code working).
_ALIASES = {
    "toolbar_background": "header_background",
    "input_background": "search_background",
    "danger": "destructive",
}


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


def _weight(name: str) -> float:
    return {
        "regular": NSFontWeightRegular,
        "medium": NSFontWeightMedium,
        "semibold": NSFontWeightSemibold,
    }.get(name, NSFontWeightRegular)


def symbol_image(name: str, *, size: float = 13.0, weight: str = "regular"):
    """Return a template SF Symbol NSImage (tint via contentTintColor), or None."""
    if not hasattr(NSImage, "imageWithSystemSymbolName_accessibilityDescription_"):
        return None  # pragma: no cover
    image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, None)
    if image is None:
        return None
    config = NSImageSymbolConfiguration.configurationWithPointSize_weight_scale_(
        size, _weight(weight), NSImageSymbolScaleMedium
    )
    configured = image.imageWithSymbolConfiguration_(config)
    result = configured if configured is not None else image
    result.setTemplate_(True)
    return result


class Palette:
    """Semantic NSColors + fonts + effects derived from a :class:`Theme`."""

    def __init__(self, theme: Theme) -> None:
        self.theme = theme

    def __getattr__(self, name: str):
        # Only reached when normal attribute lookup fails (i.e. token names).
        theme = object.__getattribute__(self, "theme")
        real = _ALIASES.get(name, name)
        if hasattr(theme, real):
            value = getattr(theme, real)
            if isinstance(value, str) and value.startswith("#"):
                return color_from_hex(value)
            return value
        raise AttributeError(name)

    # -- effects -------------------------------------------------------------

    def color(self, token: str, alpha: float = 1.0) -> NSColor:
        """Return a token color with an explicit alpha."""
        real = _ALIASES.get(token, token)
        return color_from_hex(getattr(self.theme, real), alpha)

    def window_gradient(self) -> tuple[NSColor, NSColor]:
        return (
            color_from_hex(self.theme.gradient_top),
            color_from_hex(self.theme.gradient_bottom),
        )

    def glow(self) -> NSColor | None:
        """Radial background glow color at its theme opacity, or None if off."""
        if self.theme.glow_opacity <= 0.0:
            return None
        return color_from_hex(self.theme.glow_color, self.theme.glow_opacity)

    def selection_glow(self, alpha: float = 0.5) -> NSColor | None:
        if self.theme.selected_shadow_opacity <= 0.0:
            return None
        return color_from_hex(self.theme.selected_glow, alpha)
