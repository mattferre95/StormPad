"""Tests for the semantic theme architecture (pure, no AppKit)."""

from __future__ import annotations

import re
from dataclasses import fields

import pytest

from stormpad import theme
from stormpad.theme import (
    DEEP_DARK,
    LIGHT,
    STORM_BLUE,
    THEME_ORDER,
    Theme,
    all_themes,
    get_theme,
    menu_state,
)
from stormpad.uihelpers import SaveStatus, status_style

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
# Fields that are not colors.
_NON_COLOR = {
    "id",
    "name",
    "is_dark",
    "glow_opacity",
    "panel_shadow_opacity",
    "selected_shadow_opacity",
}


def _color_fields() -> list[str]:
    return [f.name for f in fields(Theme) if f.name not in _NON_COLOR]


def test_three_themes_registered_in_order():
    assert THEME_ORDER == (STORM_BLUE, LIGHT, DEEP_DARK)
    assert list(all_themes().keys()) == list(THEME_ORDER)


def test_every_theme_has_valid_hex_for_all_color_tokens():
    color_fields = _color_fields()
    for theme_id, t in all_themes().items():
        for name in color_fields:
            value = getattr(t, name)
            assert _HEX.match(value), f"{theme_id}.{name} = {value!r} is not #RRGGBB"


def test_no_missing_tokens_between_themes():
    # Every theme is the same dataclass, so all share the identical token set.
    token_sets = {frozenset(f.name for f in fields(type(t))) for t in all_themes().values()}
    assert len(token_sets) == 1


def test_theme_id_mapping_and_flags():
    assert get_theme(STORM_BLUE).id == STORM_BLUE
    assert get_theme(LIGHT).is_dark is False
    assert get_theme(DEEP_DARK).is_dark is True
    assert get_theme(STORM_BLUE).is_dark is True


def test_invalid_theme_falls_back_to_storm_blue():
    assert get_theme("bogus").id == STORM_BLUE
    assert get_theme(None).id == STORM_BLUE
    assert get_theme("").id == STORM_BLUE


def test_light_and_deep_dark_are_not_aliases_of_storm_blue():
    storm = get_theme(STORM_BLUE)
    light = get_theme(LIGHT)
    dark = get_theme(DEEP_DARK)
    # Distinct foundations and accents — not naive recolors.
    assert light.app_background != storm.app_background
    assert dark.app_background != storm.app_background
    assert light.app_background != dark.app_background
    assert light.accent != storm.accent
    assert dark.accent != storm.accent
    assert light.is_dark != storm.is_dark
    # Light is genuinely light; the others are dark.
    assert light.is_dark is False and storm.is_dark and dark.is_dark


def test_glow_only_on_storm_blue():
    assert get_theme(STORM_BLUE).glow_opacity > 0
    assert get_theme(LIGHT).glow_opacity == 0.0
    assert get_theme(DEEP_DARK).glow_opacity == 0.0


def test_menu_state():
    assert menu_state(STORM_BLUE, STORM_BLUE) == 1
    assert menu_state(LIGHT, STORM_BLUE) == 0


def test_color_parsing_pure():
    # A minimal, AppKit-free RGB parse of a token proves the hex is well-formed.
    hex_value = get_theme(STORM_BLUE).accent_strong.lstrip("#")
    r, g, b = (int(hex_value[i : i + 2], 16) for i in (0, 2, 4))
    assert (r, g, b) == (0x00, 0xC7, 0xFF)


@pytest.mark.parametrize(
    "status,text_token,bg_token",
    [
        (SaveStatus.SAVED, "success", "success_background"),
        (SaveStatus.SAVING, "text_muted", "pill_background"),
        (SaveStatus.FAILED, "destructive", "destructive_background"),
    ],
)
def test_status_style_mapping(status, text_token, bg_token):
    color, background, symbol = status_style(status)
    assert color == text_token
    assert background == bg_token
    assert symbol  # a non-empty SF Symbol name
    # The token names must exist on every theme.
    for t in all_themes().values():
        assert hasattr(t, color) and hasattr(t, background)


def test_theme_module_has_default():
    assert theme.DEFAULT_THEME_ID == STORM_BLUE
