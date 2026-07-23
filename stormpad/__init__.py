"""StormPad — a local-first notepad for capturing ideas as they happen.

Native macOS (PyObjC/AppKit) app that stores notes as plain Markdown files
under ``~/Documents/StormPad/Notes/``. Markdown files are the source of truth.

The package is organized so that all non-UI logic (models, storage, paths,
session, search, preferences, theme tokens) imports without AppKit and can be
unit-tested headlessly. Only the ``app``, ``window`` and ``views`` modules
touch AppKit.
"""

__version__ = "0.1.0"
__app_name__ = "StormPad"
__tagline__ = "A local-first notepad for capturing ideas as they happen."

__all__ = ["__version__", "__app_name__", "__tagline__"]
