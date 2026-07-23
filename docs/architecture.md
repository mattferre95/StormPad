# StormPad architecture

## Principles

- **UI is separate from storage.** All non-UI logic imports without AppKit and
  is unit-tested headlessly.
- **Markdown files are the source of truth.** The app is a window over a folder
  of `.md` files under `~/Documents/StormPad/Notes/`.
- **Semantic theming.** Colors live only in `theme.py` as semantic tokens; view
  code never references color literals.
- **Small, focused modules.** No giant controller/view files.

## Layers

### Pure (AppKit-free, testable)

| Module | Responsibility |
| --- | --- |
| `errors.py` | Domain/storage exception hierarchy (input errors vs. storage failures). |
| `paths.py` | Canonical app/notes directories; injectable override; explicit folder creation (no import-time side effects). |
| `models.py` | `Note` / `TranscriptBlock`, categories, tz-aware timestamps, transcript-timestamp normalization. |
| `storage.py` | Deterministic Markdown serialize; lenient parse; slug + stable filenames with collision handling; atomic writes; read/list. |
| `session.py` | `NoteStore`: CRUD, `append_transcript_block(note_id, text, timestamp)`, `append_test_transcript`; injectable clock and delete strategy. |
| `search.py` | Case-insensitive Unicode search over title/body/transcript + independent category filter; match spans for highlighting. |
| `preferences.py` | Persisted theme + last-open note/category over an injectable backend (dict in tests, NSUserDefaults in the app), with safe fallbacks. |
| `theme.py` | Storm Blue / Light / Deep Dark semantic token sets (Phase 5). |

### Key seams (for testing and Phase 3/4)

- `NoteStore(notes_dir=..., clock=..., delete_strategy=...)` — tests inject a
  temp dir, a fake clock, and a recording delete strategy; Phase 4 injects a
  "move to macOS Trash" strategy.
- `PreferencesBackend` protocol (`get`/`set`/`delete`) — `InMemoryBackend` in
  tests; an `NSUserDefaults` adapter in Phase 3.

### Write-path vs. read-path validation

User-facing APIs (model construction, `create_note`, `update_category`,
preferences setters) validate strictly and raise. Parsing files off disk is
**lenient**: malformed metadata falls back to safe defaults so a note's body is
never lost.

### AppKit (UI)

| Module | Responsibility |
| --- | --- |
| `app.py` | NSApplication lifecycle, main menu (Cmd+N/F/S/O), View → Theme menu. |
| `window.py` | Main window (native chrome) + three-column split controller. |
| `views/sidebar.py` | Logo, tagline, search, Library categories, privacy panel. |
| `views/note_list.py` | Note rows, selected/empty/search states. |
| `views/editor.py` | Serif title field + premium `NSTextView` writing surface + save status. |
| `views/toolbar.py` | New Note, Copy Note, Append Transcript, Open File, Reveal, Delete. |
| `views/transcript.py` | Timestamped transcript card + Append Test Transcript. |
| `views/empty_state.py` | Empty / no-selection / no-results states. |
| `views/controls.py` | Shared themed controls reading from theme tokens. |

## Note Markdown format

See PRD §12. A note has a title (`# ...`), `Created` / `Updated` / `Category`
metadata, a `## Notes` body, and an optional `## Transcript` section of
`[hh:mm:ss]`-timestamped blocks. Renaming updates the in-file title only;
filenames stay stable in V1.

## Future WisperFlow boundary

`session.py` exposes the clean seam (`create_note`, `save_note`,
`append_transcript_block`, `reveal_note_in_finder`) that a future WisperFlow
Session Notes feature can reuse without coupling the apps. No WisperFlow code
exists in V1.
