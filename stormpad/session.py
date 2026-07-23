"""Note/session operations layer.

Coordinates the in-memory note collection with the storage layer and exposes
the clean, reusable API the PRD calls for (create_note, save_note,
append_transcript_block, ...). Pure, AppKit-free. Implemented in Phase 2.
"""

from __future__ import annotations

# TODO(phase-2): NoteStore with create/save/rename/delete and
# append_transcript_block(note_id, text, timestamp) — the V2 WisperFlow
# integration boundary (PRD §13). No WisperFlow code here in V1.
