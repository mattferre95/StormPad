"""Semantic theme tokens for StormPad.

Pure and AppKit-free: a :class:`Theme` is just named hex color strings. The UI
layer resolves these to ``NSColor`` (see ``stormpad/views/palette.py``), so view
code references *semantic names* (``theme.accent``) and never color literals.

Phase 3 ships a functional **Storm Blue** theme (the default). Light and Deep
Dark are stubbed with the same token shape and get their real values, plus live
switching, in Phase 5. Values are transcribed/derived from the supplied design
handoff token tables.
"""

from __future__ import annotations

from dataclasses import dataclass

# Stable theme ids (must match stormpad.preferences).
STORM_BLUE = "storm_blue"
LIGHT = "light"
DEEP_DARK = "deep_dark"


@dataclass(frozen=True)
class Theme:
    """A complete set of semantic color tokens (hex strings, ``#RRGGBB``)."""

    id: str
    name: str
    is_dark: bool

    # Surfaces
    app_background: str
    toolbar_background: str
    sidebar_background: str
    note_list_background: str
    editor_background: str
    elevated_surface: str
    selected_background: str
    hover_background: str
    input_background: str
    transcript_background: str

    # Lines
    border: str
    separator: str

    # Text
    text_primary: str
    text_secondary: str
    text_muted: str

    # Accents / status
    accent: str
    accent_strong: str
    success: str
    danger: str


# --- Storm Blue (Signature, default) -----------------------------------------
# Derived from the handoff Storm Blue token table (navy surfaces, cyan/blue
# accents). Translucent design values are flattened to solid colors suitable for
# native views.
STORM_BLUE_THEME = Theme(
    id=STORM_BLUE,
    name="Storm Blue",
    is_dark=True,
    app_background="#0A1128",
    toolbar_background="#0C1734",
    sidebar_background="#0C1631",
    note_list_background="#0A1228",
    editor_background="#0A1128",
    elevated_surface="#13234A",
    selected_background="#123A66",
    hover_background="#101E40",
    input_background="#080D1C",
    transcript_background="#101F42",
    border="#1A2E52",
    separator="#152340",
    text_primary="#EAF4FB",
    text_secondary="#9FB6CC",
    text_muted="#5F7A94",
    accent="#0A84FF",
    accent_strong="#00C7FF",
    success="#4ADE9A",
    danger="#FF8080",
)

# --- Light / Deep Dark (Phase 5 stubs; token shape only) ----------------------
# Placeholder values keep the app coherent if selected, but these are NOT the
# finished themes. Real values + live switching land in Phase 5.
_LIGHT_THEME = Theme(
    id=LIGHT,
    name="Light",
    is_dark=False,
    app_background="#F7FAFF",
    toolbar_background="#FFFFFF",
    sidebar_background="#F1F5FD",
    note_list_background="#FFFFFF",
    editor_background="#FFFFFF",
    elevated_surface="#F4F9FF",
    selected_background="#E4EDFF",
    hover_background="#EEF3FC",
    input_background="#FFFFFF",
    transcript_background="#F4F9FF",
    border="#E2E8F5",
    separator="#EEF2FB",
    text_primary="#0A1128",
    text_secondary="#475569",
    text_muted="#94A3B8",
    accent="#2563EB",
    accent_strong="#00AEEF",
    success="#059669",
    danger="#DC2626",
)

_DEEP_DARK_THEME = Theme(
    id=DEEP_DARK,
    name="Deep Dark",
    is_dark=True,
    app_background="#0A0A0B",
    toolbar_background="#161618",
    sidebar_background="#141416",
    note_list_background="#121214",
    editor_background="#0A0A0B",
    elevated_surface="#18181B",
    selected_background="#232326",
    hover_background="#141416",
    input_background="#0A0A0B",
    transcript_background="#161618",
    border="#2A2A2E",
    separator="#1E1E20",
    text_primary="#F4F4F5",
    text_secondary="#A1A1AA",
    text_muted="#52525B",
    accent="#D4D4D8",
    accent_strong="#E4E4E7",
    success="#A1A1AA",
    danger="#F87171",
)

_THEMES: dict[str, Theme] = {
    STORM_BLUE: STORM_BLUE_THEME,
    LIGHT: _LIGHT_THEME,
    DEEP_DARK: _DEEP_DARK_THEME,
}

DEFAULT_THEME_ID = STORM_BLUE

# Themes considered visually complete/functional in the current phase.
FUNCTIONAL_THEME_IDS: tuple[str, ...] = (STORM_BLUE,)


def get_theme(theme_id: str | None) -> Theme:
    """Return the theme for ``theme_id``, falling back to the default."""
    return _THEMES.get(theme_id or "", STORM_BLUE_THEME)


def all_themes() -> dict[str, Theme]:
    """Return every theme keyed by id (ordered Storm Blue, Light, Deep Dark)."""
    return dict(_THEMES)
