"""Targeted tests for the bottom-left local profile row.

Covers the display-name fallback, the menu's command routing (especially that
Appearance reuses the same theme action as the View menu), the absence of any
account/cloud affordance, and the menu-open state that must always clean up so
the sidebar keeps accepting clicks.
"""

from __future__ import annotations

from stormpad.preferences import DEEP_DARK, LIGHT, STORM_BLUE, THEMES
from stormpad.theme import all_themes
from stormpad.uihelpers import (
    PROFILE_FALLBACK_NAME,
    PROFILE_SUBTITLE,
    TransientMenuState,
    profile_display_name,
    profile_menu_spec,
)


def _themes() -> list[tuple[str, str]]:
    return [(theme_id, theme.name) for theme_id, theme in all_themes().items()]


def _flat(spec) -> list:
    entries = []
    for entry in spec:
        entries.append(entry)
        entries.extend(entry.submenu)
    return entries


# -- display name --------------------------------------------------------------


def test_macos_display_name_is_used_when_available():
    assert profile_display_name("Ada Lovelace") == "Ada Lovelace"


def test_missing_or_unusable_names_fall_back():
    for value in (None, "", "   ", "\t\n", 42, object()):
        assert profile_display_name(value) == PROFILE_FALLBACK_NAME


def test_whitespace_is_normalised():
    assert profile_display_name("  Ada   Lovelace \n") == "Ada Lovelace"


def test_secondary_text_describes_a_local_workspace():
    assert PROFILE_SUBTITLE == "Local workspace"


# -- command routing -----------------------------------------------------------


def test_settings_routes_to_the_existing_settings_action():
    spec = profile_menu_spec(_themes())
    settings = next(e for e in spec if e.title == "Settings…")
    assert settings.action == "showSettings:"


def test_appearance_lists_every_theme_through_the_shared_theme_action():
    """Same action as the View menu, so the two routes cannot drift apart."""
    appearance = next(e for e in profile_menu_spec(_themes()) if e.title == "Appearance")
    assert [entry.represented for entry in appearance.submenu] == list(THEMES)
    assert {entry.action for entry in appearance.submenu} == {"selectTheme:"}
    assert [entry.title for entry in appearance.submenu] == [
        all_themes()[theme_id].name for theme_id in (STORM_BLUE, LIGHT, DEEP_DARK)
    ]


def test_folder_about_and_quit_are_present():
    actions = {e.title: e.action for e in profile_menu_spec(_themes())}
    assert actions["Reveal StormPad Folder"] == "revealStormPadFolder:"
    assert actions["About StormPad"] == "orderFrontStandardAboutPanel:"
    assert actions["Quit StormPad"] == "terminate:"


def test_every_non_separator_entry_acts_or_opens_a_submenu():
    for entry in profile_menu_spec(_themes()):
        if entry.is_separator:
            continue
        assert entry.action or entry.submenu


def test_every_top_level_row_carries_an_icon():
    """The menu reference gives every workspace row a leading SF Symbol."""
    for entry in profile_menu_spec(_themes()):
        if entry.is_separator:
            continue
        assert entry.icon  # non-empty SF Symbol name


def test_settings_and_quit_expose_keyboard_shortcuts():
    spec = profile_menu_spec(_themes())
    keys = {e.title: e.key for e in spec if not e.is_separator}
    assert keys["Settings…"] == ","  # ⌘,
    assert keys["Quit StormPad"] == "q"  # ⌘Q


def test_theme_rows_have_no_icon_reserving_the_checkmark_column():
    appearance = next(e for e in profile_menu_spec(_themes()) if e.title == "Appearance")
    assert all(not entry.icon for entry in appearance.submenu)


def test_no_account_subscription_or_cloud_affordances():
    """StormPad has no accounts; the row must not imply otherwise."""
    banned = (
        "upgrade",
        "log out",
        "logout",
        "sign in",
        "sign up",
        "profile",
        "subscription",
        "subscribe",
        "billing",
        "plan",
        "sync",
        "cloud",
        "account",
    )
    titles = [e.title.lower() for e in _flat(profile_menu_spec(_themes())) if e.title]
    for title in titles:
        assert not any(word in title for word in banned), title


# -- menu state cleanup --------------------------------------------------------


def test_a_fresh_row_accepts_clicks():
    state = TransientMenuState()
    assert not state.is_open
    assert state.accepts_clicks


def test_an_open_menu_swallows_the_dismissing_click():
    state = TransientMenuState()
    state.opened()
    assert state.is_open
    assert not state.accepts_clicks


def test_closing_restores_sidebar_clicks():
    state = TransientMenuState()
    state.opened()
    state.closed()
    assert not state.is_open
    assert state.accepts_clicks


def test_repeated_open_close_cycles_leave_no_residue():
    state = TransientMenuState()
    for _ in range(5):
        state.opened()
        state.closed()
    assert state.accepts_clicks
