"""Empty-state overlays for the editor column.

Three modes: no notes at all (with a create button), no note selected, and no
search results. Shown instead of a blank editor so controls are never left
unexplained.
"""

from __future__ import annotations

from AppKit import (
    NSButton,
    NSColor,
    NSFont,
    NSImageScaleProportionallyUpOrDown,
    NSImageView,
    NSTextAlignmentCenter,
)

from .controls import flipped_view, label, solid_view
from .layout import add, pin_edges, set_height, set_width
from .palette import Palette, serif_font

NO_NOTES = "no_notes"
NO_SELECTION = "no_selection"
NO_RESULTS = "no_results"


class EmptyState:
    """A centered empty-state panel with switchable messaging."""

    def __init__(self, palette: Palette, logo_image, *, create_target, create_action: str) -> None:
        self.palette = palette
        self.view = solid_view(palette.editor_background)

        box = add(self.view, flipped_view())
        box.centerXAnchor().constraintEqualToAnchor_(self.view.centerXAnchor()).setActive_(True)
        box.centerYAnchor().constraintEqualToAnchor_(self.view.centerYAnchor()).setActive_(True)
        set_width(box, 420)
        set_height(box, 260)

        logo = add(box, NSImageView.alloc().init())
        if logo_image is not None:
            logo.setImage_(logo_image)
        logo.setImageScaling_(NSImageScaleProportionallyUpOrDown)
        logo.setWantsLayer_(True)
        if logo.layer() is not None:
            logo.layer().setCornerRadius_(18.0)
            logo.layer().setMasksToBounds_(True)
        logo.centerXAnchor().constraintEqualToAnchor_(box.centerXAnchor()).setActive_(True)
        pin_edges(logo, box, top=0, leading=None, trailing=None, bottom=None)
        set_width(logo, 72)
        set_height(logo, 72)

        self._title = self._centered(
            "A quiet place to think", serif_font(26.0), palette.text_primary
        )
        add(box, self._title)
        pin_edges(self._title, box, top=90, leading=0, trailing=0, bottom=None)

        self._subtitle = self._centered(
            "Create your first note and start writing.\n"
            "Everything is saved locally as Markdown.",
            NSFont.systemFontOfSize_(13.5),
            palette.text_secondary,
            multiline=True,
        )
        add(box, self._subtitle)
        pin_edges(self._subtitle, box, top=128, leading=0, trailing=0, bottom=None)
        set_height(self._subtitle, 44)

        button = NSButton.alloc().init()
        button.setTitle_("Create your first note")
        button.setBordered_(False)
        button.setWantsLayer_(True)
        button.setFont_(NSFont.boldSystemFontOfSize_(13.5))
        button.setContentTintColor_(NSColor.whiteColor())
        button.layer().setBackgroundColor_(palette.accent.CGColor())
        button.layer().setCornerRadius_(10.0)
        button.setTarget_(create_target)
        button.setAction_(create_action)
        add(box, button)
        button.centerXAnchor().constraintEqualToAnchor_(box.centerXAnchor()).setActive_(True)
        pin_edges(button, box, top=188, leading=None, trailing=None, bottom=None)
        set_width(button, 210)
        set_height(button, 40)
        self._button = button

    def _centered(self, text, font, color, *, multiline=False):
        field = label(text, font, color, multiline=multiline)
        field.setAlignment_(NSTextAlignmentCenter)
        return field

    def set_mode(self, mode: str) -> None:
        if mode == NO_NOTES:
            self._title.setStringValue_("A quiet place to think")
            self._subtitle.setStringValue_(
                "Create your first note and start writing.\n"
                "Everything is saved locally as Markdown."
            )
            self._button.setHidden_(False)
        elif mode == NO_RESULTS:
            self._title.setStringValue_("No notes found")
            self._subtitle.setStringValue_("Try a different search, or clear it to see all notes.")
            self._button.setHidden_(True)
        else:  # NO_SELECTION
            self._title.setStringValue_("Select a note")
            self._subtitle.setStringValue_("Choose a note from the list, or create a new one.")
            self._button.setHidden_(True)
        self.view.setHidden_(False)

    def hide(self) -> None:
        self.view.setHidden_(True)
