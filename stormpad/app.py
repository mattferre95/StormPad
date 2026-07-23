"""Application entry point: NSApplication lifecycle, menus, delegate.

Builds the real AppKit application, the main menu (with Cmd+N/S/F/W and the
standard Edit shortcuts), and one StormPad window backed by a :class:`NoteStore`.
Launches via ``scripts/run.sh`` or ``python -m stormpad``. Packaging the final
``.app`` is Phase 6.
"""

from __future__ import annotations

import sys

from . import __app_name__, __version__


def _build_menu(app, controller) -> None:
    from AppKit import NSMenu, NSMenuItem

    from .theme import FUNCTIONAL_THEME_IDS, STORM_BLUE, all_themes

    main_menu = NSMenu.alloc().init()

    def add_menu(title):
        item = NSMenuItem.alloc().init()
        menu = NSMenu.alloc().initWithTitle_(title)
        item.setSubmenu_(menu)
        main_menu.addItem_(item)
        return menu

    def add_item(menu, title, action, key, target=None, modifier=None):
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key)
        if target is not None:
            item.setTarget_(target)
        if modifier is not None:
            item.setKeyEquivalentModifierMask_(modifier)
        menu.addItem_(item)
        return item

    # App menu.
    app_menu = add_menu(__app_name__)
    add_item(app_menu, f"About {__app_name__}", "orderFrontStandardAboutPanel:", "")
    app_menu.addItem_(NSMenuItem.separatorItem())
    add_item(app_menu, f"Hide {__app_name__}", "hide:", "h")
    add_item(app_menu, "Hide Others", "hideOtherApplications:", "h").setKeyEquivalentModifierMask_(
        (1 << 19) | (1 << 20)  # Command | Option
    )
    app_menu.addItem_(NSMenuItem.separatorItem())
    add_item(app_menu, f"Quit {__app_name__}", "terminate:", "q")

    # File menu.
    file_menu = add_menu("File")
    add_item(file_menu, "New Note", "newNote:", "n", target=controller)
    add_item(file_menu, "Save", "saveNote:", "s", target=controller)
    file_menu.addItem_(NSMenuItem.separatorItem())
    add_item(file_menu, "Copy Note", "copyNote:", "", target=controller)
    add_item(file_menu, "Append Test Transcript", "appendTranscript:", "", target=controller)
    file_menu.addItem_(NSMenuItem.separatorItem())
    add_item(file_menu, "Open File", "openFile:", "o", target=controller)
    add_item(file_menu, "Reveal in Finder", "revealInFinder:", "", target=controller)
    file_menu.addItem_(NSMenuItem.separatorItem())
    add_item(file_menu, "Delete Note", "deleteNote:", "", target=controller)
    file_menu.addItem_(NSMenuItem.separatorItem())
    add_item(file_menu, "Close Window", "performClose:", "w")

    # Edit menu (standard responder actions + StormPad speech).
    edit_menu = add_menu("Edit")
    add_item(edit_menu, "Undo", "undo:", "z")
    add_item(edit_menu, "Redo", "redo:", "Z")
    edit_menu.addItem_(NSMenuItem.separatorItem())
    add_item(edit_menu, "Cut", "cut:", "x")
    add_item(edit_menu, "Copy", "copy:", "c")
    add_item(edit_menu, "Paste", "paste:", "v")
    add_item(edit_menu, "Select All", "selectAll:", "a")
    edit_menu.addItem_(NSMenuItem.separatorItem())
    speech_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Speech", None, "")
    speech_menu = NSMenu.alloc().initWithTitle_("Speech")
    speech_item.setSubmenu_(speech_menu)
    add_item(speech_menu, "Speak Selection", "speakSelection:", "", target=controller)
    add_item(speech_menu, "Stop Speaking", "stopSpeaking:", "", target=controller)
    edit_menu.addItem_(speech_item)

    # View menu.
    view_menu = add_menu("View")
    add_item(view_menu, "Focus Search", "focusSearch:", "f", target=controller)
    view_menu.addItem_(NSMenuItem.separatorItem())
    theme_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Theme", None, "")
    theme_menu = NSMenu.alloc().initWithTitle_("Theme")
    theme_item.setSubmenu_(theme_menu)
    for theme_id, theme in all_themes().items():
        entry = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(theme.name, None, "")
        entry.setEnabled_(theme_id in FUNCTIONAL_THEME_IDS)  # Light/Deep Dark: Phase 5
        if theme_id == STORM_BLUE:
            entry.setState_(1)  # on
        theme_menu.addItem_(entry)
    view_menu.addItem_(theme_item)

    app.setMainMenu_(main_menu)


class AppDelegate:
    """Lightweight delegate object (created via PyObjC class below)."""


def main(argv: list[str] | None = None) -> int:
    """Launch StormPad."""
    argv = list(sys.argv[1:] if argv is None else argv)

    # Self-check mode: build objects without running the event loop (used by
    # the headless smoke check). Does not open a visible app.
    if "--self-check" in argv:
        print(f"{__app_name__} {__version__} self-check OK")
        return 0

    import warnings

    import objc
    from AppKit import (
        NSApplication,
        NSApplicationActivationPolicyRegular,
    )
    from Foundation import NSObject

    from .window import MainController, make_store

    # Silence the benign CGColorRef pointer-wrapping warning emitted when we set
    # layer colors (the colors apply correctly; PyObjC just notes the opaque
    # pointer). Runtime-only — library imports and tests are unaffected.
    warnings.filterwarnings("ignore", category=objc.ObjCPointerWarning)

    class _Delegate(NSObject):
        def applicationDidFinishLaunching_(self, notification):  # noqa: N802
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

        def applicationShouldTerminateAfterLastWindowClosed_(self, app):  # noqa: N802
            return False

        def applicationShouldHandleReopen_hasVisibleWindows_(self, app, flag):  # noqa: N802
            if not flag and self.controller is not None:
                self.controller.show()
            return True

        def applicationShouldTerminate_(self, app):  # noqa: N802
            if self.controller is not None:
                self.controller.cleanup()  # stop speech + flush pending edits
            return 1  # NSTerminateNow

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)

    controller = MainController.alloc().initWithStore_(make_store())
    delegate = _Delegate.alloc().init()
    delegate.controller = controller
    app.setDelegate_(delegate)
    _build_menu(app, controller)

    # Smoke mode: build the real UI at runtime, print introspected state, and
    # exit without entering the event loop (display-independent runtime check).
    if "--smoke" in argv:
        print(controller.smoke_summary())
        return 0

    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
