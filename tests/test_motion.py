"""Targeted tests for the centralised motion policy and collapse end states.

Covers the duration helper, Reduce Motion behaviour, the interruption guard that
keeps animations landing in the correct final state, and the notes-panel
geometry that a collapse or expand animates towards.
"""

from __future__ import annotations

import pytest

from stormpad.motion import (
    DURATIONS,
    REDUCED_DURATIONS,
    AnimationToken,
    Motion,
    MotionPolicy,
)
from stormpad.uihelpers import notes_panel_geometry

# -- duration helper -----------------------------------------------------------


def test_every_transition_kind_has_a_duration():
    for kind in Motion:
        assert kind in DURATIONS
        assert kind in REDUCED_DURATIONS


@pytest.mark.parametrize(
    ("kind", "low", "high"),
    [
        (Motion.FAST, 0.09, 0.12),  # hover controls
        (Motion.SELECTION, 0.10, 0.14),  # selected surface
        (Motion.LIST, 0.14, 0.18),  # note list
        (Motion.POPOVER, 0.13, 0.17),  # menus / palettes / inline rename
        (Motion.PANEL, 0.18, 0.22),  # notes panel collapse
    ],
)
def test_durations_are_restrained(kind, low, high):
    """Calm and quick — never a long, flashy web-style transition."""
    assert low <= MotionPolicy(enabled=True).duration(kind) <= high


def test_durations_come_from_one_place():
    """No view may invent its own timing; the policy is the only source."""
    policy = MotionPolicy(enabled=True)
    assert {kind: policy.duration(kind) for kind in Motion} == DURATIONS


def test_animates_reflects_duration():
    policy = MotionPolicy(enabled=True)
    assert all(policy.animates(kind) for kind in Motion)


# -- Reduce Motion -------------------------------------------------------------


def test_reduce_motion_removes_sliding_and_zooming():
    reduced = MotionPolicy(enabled=False)
    assert reduced.duration(Motion.PANEL) == 0.0  # no panel slide
    assert reduced.duration(Motion.SELECTION) == 0.0
    assert reduced.duration(Motion.POPOVER) == 0.0
    assert reduced.duration(Motion.FAST) == 0.0
    assert not reduced.moves


def test_reduce_motion_keeps_at_most_a_very_short_fade():
    reduced = MotionPolicy(enabled=False)
    for kind in Motion:
        assert reduced.duration(kind) <= 0.08
        assert reduced.duration(kind) <= MotionPolicy(enabled=True).duration(kind)


def test_reduce_motion_never_makes_a_duration_negative():
    for kind in Motion:
        assert MotionPolicy(enabled=False).duration(kind) >= 0.0


def test_motion_enabled_allows_geometry_to_move():
    assert MotionPolicy(enabled=True).moves


# -- interruption guard --------------------------------------------------------


def test_only_the_newest_animation_writes_the_final_state():
    token = AnimationToken()
    first = token.begin()
    second = token.begin()
    assert not token.is_current(first)  # interrupted animation stands down
    assert token.is_current(second)


def test_cancel_invalidates_outstanding_animations():
    token = AnimationToken()
    outstanding = token.begin()
    token.cancel()  # e.g. the window closed
    assert not token.is_current(outstanding)


# -- collapse / expand final state ---------------------------------------------

_SIDEBAR = 248.0
_LIST = 326.0


def _geometry(collapsed: bool):
    return notes_panel_geometry(
        collapsed, sidebar_width=_SIDEBAR, expanded_width=_LIST
    )


def test_expanded_panel_keeps_its_resizable_range():
    geometry = _geometry(False)
    assert geometry.width == _LIST
    assert (geometry.minimum, geometry.maximum) == (260.0, 440.0)
    assert geometry.divider_position == _SIDEBAR + _LIST


def test_collapsed_panel_is_pinned_to_the_compact_tab():
    geometry = _geometry(True)
    assert geometry.width == 46.0
    assert geometry.minimum == geometry.maximum == 46.0
    assert geometry.divider_position == _SIDEBAR + 46.0


def test_collapse_then_expand_restores_the_original_widths():
    """The animation's end state must be identical to where it started."""
    before = _geometry(False)
    _geometry(True)
    assert _geometry(False) == before


def test_geometry_is_pure_and_repeatable():
    assert _geometry(True) == _geometry(True)
    assert _geometry(True) != _geometry(False)
