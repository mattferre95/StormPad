"""Application entry point.

In Phase 1 this is a runnable placeholder so the package imports and
``scripts/run.sh`` works without AppKit. The real NSApplication lifecycle,
main menu (Cmd+N/F/S/O), and View -> Theme menu arrive in Phase 3.
"""

from __future__ import annotations

import sys

from . import __app_name__, __tagline__, __version__


def main(argv: list[str] | None = None) -> int:
    """Launch StormPad.

    Phase 1 placeholder: prints scaffold info and exits cleanly. Phase 3
    replaces this with the AppKit application lifecycle and main window.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    print(f"{__app_name__} {__version__} — {__tagline__}")
    print("Phase 1 scaffold. The native macOS UI arrives in Phase 3.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
