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
| `paths.py` | Canonical app/notes directories; folder creation. |
| `models.py` | `Note` data structures. |
| `storage.py` | Markdown serialize/parse; note file CRUD; stable slug filenames; atomic writes. |
| `session.py` | Note/session operations; `append_transcript_block(note_id, text, timestamp)`. |
| `search.py` | Title + body filtering and match metadata for highlighting. |
| `preferences.py` | Persisted theme + last-open note over an injectable backend (dict in tests, NSUserDefaults in the app). |
| `theme.py` | Storm Blue / Light / Deep Dark semantic token sets. |

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
