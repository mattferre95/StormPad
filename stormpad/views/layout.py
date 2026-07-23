"""Tiny Auto Layout helpers.

Keep view construction readable and make the layout robust under window resize
(no manual frame math). All helpers assume constraint-based layout.
"""

from __future__ import annotations

from AppKit import NSLayoutConstraint, NSView


def add(parent: NSView, child: NSView) -> NSView:
    """Add ``child`` to ``parent`` for Auto Layout and return it."""
    child.setTranslatesAutoresizingMaskIntoConstraints_(False)
    parent.addSubview_(child)
    return child


def _activate(constraints: list) -> None:
    NSLayoutConstraint.activateConstraints_(constraints)


def pin_edges(
    child: NSView,
    parent: NSView,
    *,
    top: float | None = 0.0,
    leading: float | None = 0.0,
    trailing: float | None = 0.0,
    bottom: float | None = 0.0,
) -> None:
    """Pin ``child`` to ``parent`` edges with per-edge insets (None to skip)."""
    constraints = []
    if top is not None:
        constraints.append(
            child.topAnchor().constraintEqualToAnchor_constant_(parent.topAnchor(), top)
        )
    if leading is not None:
        constraints.append(
            child.leadingAnchor().constraintEqualToAnchor_constant_(parent.leadingAnchor(), leading)
        )
    if trailing is not None:
        constraints.append(
            child.trailingAnchor().constraintEqualToAnchor_constant_(
                parent.trailingAnchor(), -trailing
            )
        )
    if bottom is not None:
        constraints.append(
            child.bottomAnchor().constraintEqualToAnchor_constant_(parent.bottomAnchor(), -bottom)
        )
    _activate(constraints)


def set_height(view: NSView, height: float) -> None:
    _activate([view.heightAnchor().constraintEqualToConstant_(height)])


def set_width(view: NSView, width: float) -> None:
    _activate([view.widthAnchor().constraintEqualToConstant_(width)])
