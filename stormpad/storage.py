"""Markdown serialization and note file CRUD.

Markdown files are the source of truth. Pure, AppKit-free so it is fully
unit-testable. Implemented in Phase 2.
"""

from __future__ import annotations

# TODO(phase-2): serialize/parse the note Markdown format (PRD §12), stable
# slug filenames, atomic writes, create/read/update/delete, and category
# handling. Renaming updates the in-file title only — filenames stay stable.
