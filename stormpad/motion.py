"""Centralised motion policy — the single place animation is decided.

Every animated transition in StormPad asks this module for its duration, so no
view hardcodes a timing literal and macOS "Reduce Motion" is honoured in exactly
one place rather than being re-checked across unrelated views.

Pure and AppKit-free: :mod:`stormpad.views.motion` supplies the AppKit adapter
(where Reduce Motion is actually read and where ``NSAnimationContext`` runs).

The visual direction is Things 3 calmness and Linear speed: short, ease-in-out,
never bouncing, and always clarifying where something moved.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Motion(StrEnum):
    """The kinds of transition StormPad animates."""

    FAST = "fast"  # hover-revealed contextual controls
    SELECTION = "selection"  # a selected surface changing colour
    LIST = "list"  # the note list's content changing
    POPOVER = "popover"  # menus, palettes, inline rename
    PANEL = "panel"  # the notes panel collapsing / expanding


# Deliberate, restrained timings in seconds.
DURATIONS: dict[Motion, float] = {
    Motion.FAST: 0.10,  # 90-120ms
    Motion.SELECTION: 0.12,  # 100-140ms
    Motion.LIST: 0.16,  # 140-180ms
    Motion.POPOVER: 0.15,  # 130-170ms
    Motion.PANEL: 0.20,  # 180-220ms
}

# With Reduce Motion enabled nothing slides, zooms, or springs. A single very
# short fade survives so list changes do not strobe; everything else becomes an
# immediate state change.
REDUCED_DURATIONS: dict[Motion, float] = {
    Motion.FAST: 0.0,
    Motion.SELECTION: 0.0,
    Motion.LIST: 0.06,
    Motion.POPOVER: 0.0,
    Motion.PANEL: 0.0,
}


@dataclass(frozen=True)
class MotionPolicy:
    """Resolves a transition kind to a duration.

    ``enabled`` is False when macOS Reduce Motion is on. Callers never branch on
    Reduce Motion themselves — they ask for a duration and treat ``0.0`` as
    "apply the final state immediately".
    """

    enabled: bool = True

    def duration(self, kind: Motion) -> float:
        table = DURATIONS if self.enabled else REDUCED_DURATIONS
        return table[Motion(kind)]

    def animates(self, kind: Motion) -> bool:
        """True when this transition has any duration at all."""
        return self.duration(kind) > 0.0

    @property
    def moves(self) -> bool:
        """True when geometry (sliding panels) may animate rather than jump."""
        return self.enabled


class AnimationToken:
    """Interruption guard for animations with completion handlers.

    Each animation takes a token before it starts; its completion handler only
    applies deferred work when the token is still the newest one. A transition
    interrupted by a newer one therefore never fights it, and the newest
    transition is always the one that writes the final state.
    """

    def __init__(self) -> None:
        self._value = 0

    def begin(self) -> int:
        self._value += 1
        return self._value

    def is_current(self, token: int) -> bool:
        return token == self._value

    def cancel(self) -> None:
        """Invalidate every outstanding token (e.g. the window closed)."""
        self._value += 1
