"""AppKit adapter for :mod:`stormpad.motion`.

The only place Reduce Motion is read and the only place ``NSAnimationContext``
is driven. Views ask for a duration from the shared policy and hand their
changes to :func:`run`; nothing here decides *whether* to animate.

All animations are ease-in-out with no bounce, are interruptible, and always
land in the correct final state — a duration of ``0`` (Reduce Motion, or an
initial build) applies the change immediately through the same code path.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from AppKit import NSAnimationContext
from Quartz import CAMediaTimingFunction, kCAMediaTimingFunctionEaseInEaseOut

from ..motion import Motion, MotionPolicy

__all__ = ["Motion", "MotionPolicy", "anim", "can_animate", "current_policy", "run"]

_TRUTHY = {"1", "true", "yes", "on"}


def reduce_motion_enabled() -> bool:
    """Whether macOS Reduce Motion is on (``STORMPAD_REDUCE_MOTION`` overrides).

    The environment override exists so the reduced path can be exercised on a
    machine where the accessibility setting is off.
    """
    override = os.environ.get("STORMPAD_REDUCE_MOTION")
    if override is not None:
        return override.strip().lower() in _TRUTHY
    try:
        from AppKit import NSWorkspace

        workspace = NSWorkspace.sharedWorkspace()
        if hasattr(workspace, "accessibilityDisplayShouldReduceMotion"):
            return bool(workspace.accessibilityDisplayShouldReduceMotion())
    except (ImportError, AttributeError, TypeError):  # pragma: no cover - defensive
        return False
    return False


def current_policy() -> MotionPolicy:
    """The live motion policy. Read per transition so toggling it takes effect."""
    return MotionPolicy(enabled=not reduce_motion_enabled())


def can_animate(view) -> bool:
    """False for a view that is not in a visible window.

    Prevents animating a hidden or closed window, and keeps the initial build
    (and ``--smoke``, which never enters the event loop) on the immediate path.
    """
    if view is None:
        return False
    window = view.window()
    return window is not None and bool(window.isVisible())


def anim(view, animated: bool):
    """The animator proxy when animating, otherwise the view itself."""
    return view.animator() if animated else view


def run(
    duration: float,
    body: Callable[[bool], None],
    *,
    completion: Callable[[], None] | None = None,
) -> None:
    """Apply ``body`` over ``duration`` seconds, ease-in-out, no bounce.

    ``body(animated)`` receives whether it is inside an animation group and is
    expected to route its changes through :func:`anim`. When ``duration`` is
    zero or negative the change (and any completion) is applied synchronously,
    so the final state is identical either way.
    """
    if duration <= 0.0:
        body(False)
        if completion is not None:
            completion()
        return

    def group(context):
        context.setDuration_(duration)
        context.setTimingFunction_(
            CAMediaTimingFunction.functionWithName_(kCAMediaTimingFunctionEaseInEaseOut)
        )
        context.setAllowsImplicitAnimation_(True)
        body(True)

    NSAnimationContext.runAnimationGroup_completionHandler_(group, completion)
