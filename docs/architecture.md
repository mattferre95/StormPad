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
| `app.py` | NSApplication lifecycle, delegate, main menu (Cmd+N/S/W/F + Edit), View → Theme menu. |
| `window.py` | `MainController`: native window (transparent titlebar, full-size content, real traffic lights) + three-column `NSSplitViewController`; owns store/prefs/autosave/selection/search state. |
| `defaults.py` | `UserDefaultsBackend` — NSUserDefaults adapter for the `PreferencesBackend` protocol. |
| `uihelpers.py` | **Pure** controller helpers: preview text, word count, relative time, selection restoration, default category, `AutosaveController`. |
| `views/palette.py` | Resolves semantic `Theme` tokens → `NSColor`/fonts. |
| `views/layout.py` | Tiny Auto Layout helpers (pin edges, size). |
| `views/sidebar.py` | Logo, tagline, search, Library categories + counts, privacy panel. |
| `views/note_list.py` | `NSTableView` note rows (themed selection) + empty/search headers. |
| `views/editor.py` | Serif title field + premium `NSTextView` body + metadata/save status + transcript section. |
| `views/transcript.py` | Read-only timestamped transcript card (Append wired in Phase 4). |
| `views/empty_state.py` | Empty / no-selection / no-results states. |
| `views/controls.py` | Shared themed control builders (labels, flipped/solid views). |

### UI layer (Phase 3)

**View hierarchy.** `MainController` builds an `NSWindow` (transparent titlebar
+ full-size content view + real traffic lights) whose content is a header bar
(New Note button) above an `NSSplitViewController` with three items — `Sidebar`,
`NoteList`, and an editor column that stacks `Editor` and `EmptyState`. Split
divider positions and the window frame persist via AppKit autosave names.

**Theming.** Colors live only in `theme.py` (semantic hex tokens). `Palette`
turns them into `NSColor`s; every view reads semantic names. Storm Blue is
functional; Light/Deep Dark are token stubs for Phase 5.

**Lifecycle.** `app.py` builds `NSApplication`, a delegate (reopen shows the
window; terminate flushes pending edits), and the main menu. `python -m stormpad`
runs it; `--self-check` and `--smoke` are display-independent runtime checks.

**Autosave.** Editing marks the pure `AutosaveController` dirty and (re)starts a
0.4s debounce backed by `NSTimer`. Firing (or an explicit flush on note switch /
window close / quit) saves via the Phase 2 atomic write. Save status
(`Saving…`/`Saved locally`/`Save failed`) reflects real state; the note list is
not reordered mid-typing.

**Search / category.** The sidebar search field and category rows feed
`search.search_notes` / `filter_by_category`; results drive the list header,
count, selection, and empty/results states. Category selection persists.

**Preferences.** `Preferences` (domain, AppKit-free) runs over
`UserDefaultsBackend`; theme, last note, and last category are restored on
launch (selection falls back to the newest note, then the empty state).

### Actions & speech (Phase 4)

Actions live on `MainController` and are exposed on both the header toolbar and
the File/Edit menus, validated by `validateMenuItem_` (and button enable/alpha):

- **Copy Note** → `uihelpers.copy_text(note)` (title + body + transcript;
  excludes path/Created/Updated/Category/ids/headers) to the general pasteboard.
- **Append Test Transcript** → `NoteStore.append_test_transcript`; re-renders the
  transcript section and refreshes the list, selection stable.
- **Open File** → `NSWorkspace.openURL:` (default app); **Reveal** →
  `activateFileViewerSelectingURLs:`.
- **Delete** → confirmation `NSAlert` (Cancel is default/safe) → `NoteStore`'s
  injected `trash_file` strategy (`NSFileManager trashItemAtURL:`); the note is
  removed from the UI only after Trash succeeds, then the next note is selected.
- Pending edits are flushed before Open/Reveal and on note-switch/close/quit;
  a missing file is detected on these paths and recovered via a clear alert.

**Speech** is isolated in `stormpad/speech.py`. `SpeechController` owns one
backend (`AVSpeechBackend`, wrapping a strongly-retained `AVSpeechSynthesizer`
from the top-level `AVFoundation` module), validates the selection, stops any
current utterance before starting a new one, and is cleaned up on note switch /
active-note delete / window close / quit. The editor augments — not replaces —
the native `NSTextView` context menu via `textView:menu:forEvent:atIndex:`. The
controller logic is unit-tested with an injected fake backend (no real audio).

### Theming (Phase 5)

`theme.py` is the single source of truth: a frozen `Theme` dataclass of ~50
semantic tokens (hex strings) plus numeric decorative params (gradient/glow/
shadow). Three first-class themes — **Storm Blue** (default), **Light**, **Deep
Dark** — carry real handoff values. Because every field is required, a theme
cannot be constructed with a missing token.

`views/palette.py` resolves tokens to AppKit values dynamically (`palette.<token>`
→ `NSColor`; numeric tokens pass through; a few legacy names are aliased) and
provides fonts (SF Pro / New York / SF Mono), `window_gradient()`, `glow()`,
`selection_glow()`, and `symbol_image()` (SF Symbols). **View code references
semantic names only — never color literals.**

**Live switching:** the window is built once; its content tree is built by
`_install_content()`. `selectTheme:` flushes edits, captures the editor's
selection + first-responder state, persists the `theme` preference, swaps the
`Palette`, calls `_install_content()` again (a full rebuild → no stale colors),
re-applies the filter (reloading the current note into the fresh editor), then
restores the editor selection/focus. Each rebuild sets a per-theme
`NSAppearance` (`darkAqua`/`aqua`) so native traffic lights, cursor, selection,
and scrollbars match. Menu checkmarks are driven by `validateMenuItem_` +
`theme.menu_state`. Storm Blue is the only theme with decorative glow
(`glow_opacity`/`selected_shadow_opacity`).

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
