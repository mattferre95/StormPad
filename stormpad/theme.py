"""Semantic theme tokens for StormPad — the single source of truth for color.

Pure and AppKit-free: a :class:`Theme` is a complete set of named color tokens
(hex strings) plus a few numeric decorative parameters. View code references
*semantic names* through :class:`~stormpad.views.palette.Palette`; it never uses
color literals.

Three first-class themes, transcribed/derived from the supplied design handoff
token tables:

- **Storm Blue** (Signature, default) — night navy, electric blue/cyan accents,
  restrained radial glow.
- **Light** — cool off-white canvas, frosted white panels, restrained blue.
- **Deep Dark** (Focus) — near-black zinc surfaces, monochrome accents, no glow.

Every field is required, so a theme cannot be constructed with a missing token.
Effects that do not apply to a theme are expressed as transparent/zero rather
than branched in view code (e.g. ``glow_opacity = 0.0`` for Light/Deep Dark).
"""

from __future__ import annotations

from dataclasses import dataclass

# Stable theme ids (must match stormpad.preferences).
STORM_BLUE = "storm_blue"
LIGHT = "light"
DEEP_DARK = "deep_dark"

# Menu / switcher order.
THEME_ORDER: tuple[str, ...] = (STORM_BLUE, LIGHT, DEEP_DARK)


@dataclass(frozen=True)
class Theme:
    """A complete semantic token set. Colors are ``#RRGGBB`` hex strings."""

    id: str
    name: str
    is_dark: bool

    # -- Window & structure --
    app_background: str
    header_background: str
    sidebar_background: str
    note_list_background: str
    editor_background: str
    elevated_surface: str
    secondary_surface: str
    divider: str
    separator: str
    border: str
    strong_border: str

    # -- Text --
    text_primary: str
    text_secondary: str
    text_muted: str
    text_inverse: str
    editor_text: str
    title_text: str
    timestamp_text: str
    placeholder_text: str

    # -- Interaction --
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_strong: str  # cyan highlight
    focus_ring: str
    hover_background: str
    selected_background: str
    selected_border: str
    selected_glow: str
    disabled_background: str
    disabled_text: str

    # -- Components --
    search_background: str
    search_border: str
    toolbar_button_background: str
    toolbar_button_hover: str
    transcript_background: str
    transcript_border: str
    privacy_background: str
    privacy_border: str
    pill_background: str
    success: str
    success_background: str
    warning: str
    warning_background: str
    destructive: str
    destructive_background: str

    # -- Block editor --
    gutter_background: str
    gutter_border: str
    formatting_background: str
    formatting_border: str
    quote_border: str
    attachment_background: str
    attachment_border: str
    divider_line: str

    # -- Semantic inline colors (stored by token name, rendered per theme) --
    inline_gray: str
    inline_blue: str
    inline_cyan: str
    inline_green: str
    inline_yellow: str
    inline_orange: str
    inline_red: str
    inline_purple: str
    inline_brown: str
    inline_pink: str

    # -- Decorative (numeric) --
    gradient_top: str
    gradient_bottom: str
    glow_color: str
    glow_opacity: float
    panel_shadow_opacity: float
    selected_shadow_opacity: float


# --- Storm Blue (Signature, default) -----------------------------------------
STORM_BLUE_THEME = Theme(
    id=STORM_BLUE,
    name="Storm Blue",
    is_dark=True,
    app_background="#0A1128",
    header_background="#0C1734",
    sidebar_background="#0C1631",
    note_list_background="#0A1228",
    editor_background="#0A1128",
    elevated_surface="#13234A",
    secondary_surface="#0F1D3E",
    divider="#152340",
    separator="#122038",
    border="#1A2E52",
    strong_border="#24406E",
    text_primary="#EAF4FB",
    text_secondary="#9FB6CC",
    text_muted="#5F7A94",
    text_inverse="#05060F",
    editor_text="#E6F0F9",
    title_text="#F2F9FE",
    timestamp_text="#00C7FF",
    placeholder_text="#4F6880",
    accent="#0A84FF",
    accent_hover="#2A96FF",
    accent_pressed="#0B1DFF",
    accent_strong="#00C7FF",
    focus_ring="#00C7FF",
    hover_background="#101E40",
    selected_background="#123A66",
    selected_border="#00C7FF",
    selected_glow="#00C7FF",
    disabled_background="#0E1730",
    disabled_text="#3A5170",
    search_background="#080D1C",
    search_border="#1E3358",
    toolbar_button_background="#13234A",
    toolbar_button_hover="#1A2E58",
    transcript_background="#101F42",
    transcript_border="#1C3B63",
    privacy_background="#080E20",
    privacy_border="#18294B",
    pill_background="#0E1D3E",
    success="#4ADE9A",
    success_background="#13372A",
    warning="#F5C542",
    warning_background="#3A2F12",
    destructive="#FF8080",
    destructive_background="#3A1620",
    gutter_background="#13234A",
    gutter_border="#24406E",
    formatting_background="#13234A",
    formatting_border="#24406E",
    quote_border="#00C7FF",
    attachment_background="#101F42",
    attachment_border="#1C3B63",
    divider_line="#24406E",
    inline_gray="#9FB6CC",
    inline_blue="#60A5FA",
    inline_cyan="#22D3EE",
    inline_green="#4ADE80",
    inline_yellow="#FACC15",
    inline_orange="#FB923C",
    inline_red="#F87171",
    inline_purple="#C084FC",
    inline_brown="#C89F7B",
    inline_pink="#F472B6",
    gradient_top="#12224F",
    gradient_bottom="#0A1128",
    glow_color="#12224F",
    glow_opacity=0.55,
    panel_shadow_opacity=0.45,
    selected_shadow_opacity=0.40,
)

# --- Light --------------------------------------------------------------------
LIGHT_THEME = Theme(
    id=LIGHT,
    name="Light",
    is_dark=False,
    app_background="#F7FAFF",
    header_background="#FFFFFF",
    sidebar_background="#F1F5FD",
    note_list_background="#FBFCFF",
    editor_background="#FFFFFF",
    elevated_surface="#F4F9FF",
    secondary_surface="#EEF3FC",
    divider="#EEF2FB",
    separator="#EDF1FA",
    border="#E2E8F5",
    strong_border="#CBD6EC",
    text_primary="#0A1128",
    text_secondary="#475569",
    text_muted="#94A3B8",
    text_inverse="#FFFFFF",
    editor_text="#1E293B",
    title_text="#0A1128",
    timestamp_text="#0284C7",
    placeholder_text="#94A3B8",
    accent="#2563EB",
    accent_hover="#1D4ED8",
    accent_pressed="#1E40AF",
    accent_strong="#00AEEF",
    focus_ring="#2563EB",
    hover_background="#EEF3FC",
    selected_background="#E4EDFF",
    selected_border="#2563EB",
    selected_glow="#2563EB",
    disabled_background="#F1F5FD",
    disabled_text="#B6C2D6",
    search_background="#FFFFFF",
    search_border="#E2E8F5",
    toolbar_button_background="#FFFFFF",
    toolbar_button_hover="#EEF3FC",
    transcript_background="#F4F9FF",
    transcript_border="#D5E6F5",
    privacy_background="#FFFFFF",
    privacy_border="#E2E8F5",
    pill_background="#F1F5FD",
    success="#059669",
    success_background="#DCFCE7",
    warning="#B45309",
    warning_background="#FEF3C7",
    destructive="#DC2626",
    destructive_background="#FEE2E2",
    gutter_background="#FFFFFF",
    gutter_border="#CBD6EC",
    formatting_background="#FFFFFF",
    formatting_border="#CBD6EC",
    quote_border="#2563EB",
    attachment_background="#F4F9FF",
    attachment_border="#D5E6F5",
    divider_line="#CBD6EC",
    inline_gray="#64748B",
    inline_blue="#2563EB",
    inline_cyan="#0891B2",
    inline_green="#16A34A",
    inline_yellow="#A16207",
    inline_orange="#EA580C",
    inline_red="#DC2626",
    inline_purple="#9333EA",
    inline_brown="#92400E",
    inline_pink="#DB2777",
    gradient_top="#EAF1FF",
    gradient_bottom="#F7FAFF",
    glow_color="#EAF1FF",
    glow_opacity=0.0,
    panel_shadow_opacity=0.10,
    selected_shadow_opacity=0.0,
)

# --- Deep Dark (Focus) --------------------------------------------------------
DEEP_DARK_THEME = Theme(
    id=DEEP_DARK,
    name="Deep Dark",
    is_dark=True,
    app_background="#0A0A0B",
    header_background="#161618",
    sidebar_background="#141416",
    note_list_background="#121214",
    editor_background="#0A0A0B",
    elevated_surface="#18181B",
    secondary_surface="#141416",
    divider="#1E1E20",
    separator="#1B1B1D",
    border="#2A2A2E",
    strong_border="#3A3A40",
    text_primary="#F4F4F5",
    text_secondary="#A1A1AA",
    text_muted="#71717A",
    text_inverse="#0A0A0B",
    editor_text="#E9E9EC",
    title_text="#FAFAFA",
    timestamp_text="#D4D4D8",
    placeholder_text="#52525B",
    accent="#D4D4D8",
    accent_hover="#E4E4E7",
    accent_pressed="#A1A1AA",
    accent_strong="#E4E4E7",
    focus_ring="#A1A1AA",
    hover_background="#161618",
    selected_background="#232326",
    selected_border="#3F3F46",
    selected_glow="#000000",
    disabled_background="#161618",
    disabled_text="#3F3F46",
    search_background="#0A0A0B",
    search_border="#2A2A2E",
    toolbar_button_background="#18181B",
    toolbar_button_hover="#232326",
    transcript_background="#161618",
    transcript_border="#2A2A2E",
    privacy_background="#0F0F10",
    privacy_border="#242427",
    pill_background="#18181B",
    success="#86EFAC",
    success_background="#14301F",
    warning="#FBBF24",
    warning_background="#332611",
    destructive="#F87171",
    destructive_background="#341A1A",
    gutter_background="#18181B",
    gutter_border="#3A3A40",
    formatting_background="#18181B",
    formatting_border="#3A3A40",
    quote_border="#A1A1AA",
    attachment_background="#161618",
    attachment_border="#2A2A2E",
    divider_line="#3F3F46",
    inline_gray="#A1A1AA",
    inline_blue="#93C5FD",
    inline_cyan="#67E8F9",
    inline_green="#86EFAC",
    inline_yellow="#FDE047",
    inline_orange="#FDBA74",
    inline_red="#FCA5A5",
    inline_purple="#D8B4FE",
    inline_brown="#D6B08C",
    inline_pink="#F9A8D4",
    gradient_top="#161618",
    gradient_bottom="#0A0A0B",
    glow_color="#000000",
    glow_opacity=0.0,
    panel_shadow_opacity=0.55,
    selected_shadow_opacity=0.0,
)

_THEMES: dict[str, Theme] = {
    STORM_BLUE: STORM_BLUE_THEME,
    LIGHT: LIGHT_THEME,
    DEEP_DARK: DEEP_DARK_THEME,
}

DEFAULT_THEME_ID = STORM_BLUE
# All three themes are now first-class / functional.
FUNCTIONAL_THEME_IDS: tuple[str, ...] = THEME_ORDER


def get_theme(theme_id: str | None) -> Theme:
    """Return the theme for ``theme_id``, falling back to the default."""
    return _THEMES.get(theme_id or "", STORM_BLUE_THEME)


def all_themes() -> dict[str, Theme]:
    """Return every theme keyed by id (ordered Storm Blue, Light, Deep Dark)."""
    return {tid: _THEMES[tid] for tid in THEME_ORDER}


def menu_state(item_theme_id: str, current_theme_id: str) -> int:
    """NSMenuItem state (1 = on / checkmark) for a theme item. Pure helper."""
    return 1 if item_theme_id == current_theme_id else 0
