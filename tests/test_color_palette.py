"""Targeted tests for the redesigned colour palette.

Covers the palette vocabulary/order, recently-used state, human names used for
tooltips/accessibility, and that Clear / Transparent removes the colour rather
than serialising a fake transparent token.
"""

from __future__ import annotations

from stormpad.block_serializer import serialize_blocks
from stormpad.blocks import COLOR_TOKENS, Block, BlockType, InlineMark, InlineRun, MarkType
from stormpad.preferences import RECENT_COLOR_LIMIT, InMemoryBackend, Preferences
from stormpad.views.color_palette import PALETTE_ORDER, color_display_name

# -- palette vocabulary --------------------------------------------------------


def test_palette_order_matches_requested_swatches():
    assert PALETTE_ORDER == (
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


def test_every_palette_token_is_serialisable():
    for token in PALETTE_ORDER:
        assert token in COLOR_TOKENS


def test_existing_tokens_are_preserved_for_compatibility():
    """Older notes using these tokens must still round-trip."""
    for legacy in ("default", "gray", "blue", "cyan", "green", "yellow", "orange", "red", "purple"):
        assert legacy in COLOR_TOKENS


def test_display_names_for_tooltips():
    assert color_display_name("default", "text") == "Default"
    assert color_display_name("default", "highlight") == "Clear / Transparent"
    assert color_display_name("brown", "text") == "Brown"
    assert color_display_name("pink", "highlight") == "Pink"


# -- recently used -------------------------------------------------------------


def test_recent_colors_default_empty():
    assert Preferences().recent_colors == []


def test_recording_a_colour_puts_it_first():
    prefs = Preferences(InMemoryBackend())
    prefs.record_recent_color("text:red")
    prefs.record_recent_color("highlight:yellow")
    assert prefs.recent_colors == ["highlight:yellow", "text:red"]


def test_recording_an_existing_colour_moves_it_to_front_without_duplicating():
    prefs = Preferences(InMemoryBackend())
    for entry in ("text:red", "text:blue", "text:red"):
        prefs.record_recent_color(entry)
    assert prefs.recent_colors == ["text:red", "text:blue"]


def test_recents_stay_small():
    prefs = Preferences(InMemoryBackend())
    for token in ("red", "blue", "green", "yellow", "orange", "pink"):
        prefs.record_recent_color(f"text:{token}")
    assert len(prefs.recent_colors) == RECENT_COLOR_LIMIT
    assert prefs.recent_colors[0] == "text:pink"  # most recent first


def test_recents_persist_through_backend():
    backend = InMemoryBackend()
    Preferences(backend).record_recent_color("highlight:green")
    assert Preferences(backend).recent_colors == ["highlight:green"]


def test_invalid_recent_payloads_fall_back_safely():
    assert Preferences(InMemoryBackend({"recent_colors": "not-json"})).recent_colors == []
    assert Preferences(InMemoryBackend({"recent_colors": '{"a":1}'})).recent_colors == []
    # Entries without a "mode:token" shape are dropped.
    backend = InMemoryBackend({"recent_colors": '["text:red", "junk", 7]'})
    assert Preferences(backend).recent_colors == ["text:red"]
    prefs = Preferences(InMemoryBackend())
    prefs.record_recent_color("nonsense")
    assert prefs.recent_colors == []


# -- clear / transparent -------------------------------------------------------


def _run(text: str, mark: InlineMark | None) -> Block:
    return Block(kind=BlockType.TEXT, runs=[InlineRun(text=text, marks=[mark] if mark else [])])


def test_applied_colour_serialises_a_token():
    block = _run("hello", InlineMark(MarkType.TEXT_COLOR, "red"))
    assert 'data-stormpad-color="red"' in serialize_blocks([block])


def test_clear_text_colour_writes_no_token():
    """Clear removes the attribute; it must not serialise a fake token."""
    cleared = _run("hello", InlineMark(MarkType.TEXT_COLOR, "default"))
    output = serialize_blocks([cleared])
    assert "data-stormpad-color" not in output
    assert "default" not in output
    assert "hello" in output


def test_clear_highlight_writes_no_token():
    cleared = _run("hello", InlineMark(MarkType.HIGHLIGHT, "default"))
    output = serialize_blocks([cleared])
    assert "data-stormpad-highlight" not in output
    assert "hello" in output


def test_new_brown_and_pink_tokens_serialise():
    for token in ("brown", "pink"):
        block = _run("x", InlineMark(MarkType.TEXT_COLOR, token))
        assert f'data-stormpad-color="{token}"' in serialize_blocks([block])
