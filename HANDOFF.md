# StormPad — HANDOFF

Living handoff document. Updated after every phase. Intended for any agent or
human (including a later Codex session) continuing this work.

## Final Delivery Requirements (HARD REQUIREMENT — Phase 6)

When all phases are complete, StormPad **must** ship as:

- A real standalone `StormPad.app`.
- Double-clickable from Finder and Applications (no Terminal, no
  `scripts/run.sh` required by the end user).
- Official `Stormpad_logo.png` used as the macOS app icon.
- Correct `.icns` generation.
- Correct bundle name, identifier, version, and `Info.plist`.
- Self-contained packaged dependencies.
- No dependency on the source folder or the development `.venv`.
- Reproducible build and install scripts.
- Installed and tested from `/Applications/StormPad.app`.
- A final downloadable `.dmg` supporting the normal drag-to-Applications flow.

This is **not** built in Phase 3. It is preserved here as a hard requirement to
be delivered in Phase 6 (packaging & public readiness).

## Product summary

StormPad is a native macOS (Python 3.12 + PyObjC/AppKit) local-first notepad.
Notes are plain Markdown files in `~/Documents/StormPad/Notes/` (the source of
truth). Apple Notes-like structure (sidebar → note list → editor), original
premium visual identity, three themes. No cloud, accounts, telemetry, AI, or
voice in V1. See `PRD.md` for full scope and `docs/design/` notes for the
design handoff.

## Current state

- **Branch:** `main`
- **Latest commit:** _see `git log -1` — Phase 5 visual fidelity / themes commit_
- **Git status:** clean after the Phase 5 commit (supplied ZIPs, the raw PRD
  `.txt`, and the root logo original are git-ignored; cleaned copies are
  committed; no dev/test notes or screenshots committed — tests use `tmp_path`,
  manual runs use a temp dir via `STORMPAD_NOTES_DIR`).
- **Phase complete:** Phase 5 (visual fidelity, three complete themes, live
  theme switching; 134 tests passing, all headless).

## Setup / run / test commands

```bash
./scripts/run.sh      # create .venv (first run), install, launch
./scripts/test.sh     # create .venv[dev] (first run), run pytest
./scripts/format.sh   # ruff format + lint --fix
```

Manual: `python3.12 -m venv .venv && source .venv/bin/activate && pip install -e '.[dev]'`.

## Architecture overview

Non-UI logic is AppKit-free and headlessly testable. Modules: `paths`,
`models`, `storage`, `session`, `search`, `preferences`, `theme` (pure);
`app`, `window`, `views/*` (AppKit). See `docs/architecture.md`.

## Files created / changed (Phase 1)

- `.gitignore`, `LICENSE` (MIT), `pyproject.toml`
- `README.md`, `PRD.md` (cleaned from supplied source), `HANDOFF.md`
- `docs/architecture.md`, `docs/design/README.md`
- `stormpad/__init__.py`, `__main__.py`, `app.py`, `paths.py` and stub modules
  `window.py`, `models.py`, `storage.py`, `session.py`, `search.py`,
  `preferences.py`, `theme.py`
- `stormpad/views/` — `__init__.py` + stubs: `sidebar.py`, `note_list.py`,
  `editor.py`, `toolbar.py`, `transcript.py`, `empty_state.py`, `controls.py`
- `scripts/run.sh`, `test.sh`, `format.sh`, `generate_icons.py`
- `assets/Stormpad_logo.png` (byte-identical copy of the untouched original)

## Files created / changed (Phase 2)

- `stormpad/errors.py` — new: domain/storage exception hierarchy.
- `stormpad/models.py` — Note + TranscriptBlock, categories, timestamp helpers.
- `stormpad/paths.py` — injectable override, `ensure_notes_dir`, no import-time
  side effects.
- `stormpad/storage.py` — deterministic serialize / lenient parse, slug +
  stable filenames, collision handling, atomic writes, read/list.
- `stormpad/session.py` — `NoteStore` (CRUD, `append_transcript_block`,
  `append_test_transcript`, injectable clock + delete strategy).
- `stormpad/search.py` — title/body/transcript search + independent category
  filter, match spans for highlighting.
- `stormpad/preferences.py` — injectable backend, theme/last-note/last-category
  with safe fallbacks; `InMemoryBackend` for tests.
- `tests/` — replaced `test_smoke.py` with `test_models.py`, `test_paths.py`,
  `test_storage.py`, `test_session.py`, `test_search.py`, `test_preferences.py`
  (81 tests, all `tmp_path`-based).

## Files created / changed (Phase 3)

- `stormpad/app.py` — real NSApplication lifecycle, delegate (reopen/terminate
  flush), full main menu (Cmd+N/S/W/F + Edit), View→Theme submenu; `--smoke`
  and `--self-check` runtime checks; benign CGColor warning silenced at runtime.
- `stormpad/window.py` — `MainController`: native window (transparent titlebar,
  full-size content view, real traffic lights), three-column
  `NSSplitViewController`, header + New Note button; owns store/prefs/autosave
  and all selection/search/category state.
- `stormpad/theme.py` — `Theme` dataclass + functional **Storm Blue** tokens;
  Light/Deep Dark stubs (same shape); `get_theme`/`all_themes`.
- `stormpad/uihelpers.py` — new pure helpers: `preview_text`, `word_count`,
  `format_relative`, `choose_selected_note`, `default_new_category`,
  `SaveStatus`, `AutosaveController` (injectable scheduler).
- `stormpad/defaults.py` — new `UserDefaultsBackend` (NSUserDefaults adapter).
- `stormpad/views/` — implemented `palette.py` (new), `layout.py` (new),
  `controls.py`, `sidebar.py`, `note_list.py`, `editor.py`, `transcript.py`,
  `empty_state.py`.
- `tests/test_uihelpers.py` — new (21 tests) for the pure helpers + controller
  save/selection/delete logic.

## Files created / changed (Phase 4)

- `stormpad/speech.py` — new: `SpeechController` + `AVSpeechBackend` +
  `SpeechUnavailableError` (injectable backend; AVFoundation confined here).
- `stormpad/window.py` — action toolbar (Copy/Append/Open/Reveal/Delete + New
  Note) with enabled-state; actions `copyNote:`/`appendTranscript:`/`openFile:`/
  `revealInFinder:`/`deleteNote:`/`speakSelection:`/`stopSpeaking:`;
  `validateMenuItem_`; `trash_file` delete strategy wired into `make_store`;
  speech-stop hooks on switch/delete/close/quit; `cleanup()`.
- `stormpad/views/editor.py` — `selected_body_text`, `flash_status` ("Copied"),
  and `textView:menu:forEvent:atIndex:` to augment (not replace) the native
  context menu with Speak/Stop.
- `stormpad/app.py` — File menu (Copy Note, Append Test Transcript, Open File
  ⌘O, Reveal, Delete) and Edit▸Speech submenu; terminate now calls `cleanup()`.
- `stormpad/uihelpers.py` — `copy_text`, `next_selection_after_delete`,
  `is_speakable`.
- `pyproject.toml` — added `pyobjc-framework-AVFoundation` dependency.
- `tests/test_speech.py` (new) + extended `test_uihelpers.py` (copy/next/
  speakable/external-deletion) → 121 tests total.

## Files created / changed (Phase 5)

- `stormpad/theme.py` — complete ~50-token `Theme` dataclass; three first-class
  themes (Storm Blue / Light / Deep Dark) with real handoff values + decorative
  params (gradient/glow/shadow); `menu_state`, `THEME_ORDER`, `all_themes`.
- `stormpad/views/palette.py` — dynamic token→`NSColor` resolution (with legacy
  aliases), fonts, `window_gradient`/`glow`/`selection_glow`, and `symbol_image`
  (SF Symbols).
- `stormpad/window.py` — split into `_build_window` + `_install_content` (used
  for **live theme rebuild**); `selectTheme_` (persist + rebuild + restore
  editor selection/focus); per-theme window `NSAppearance`; gradient root; SF
  Symbol pill/icon toolbar with tooltips/disabled/destructive; theme checkmarks
  via `validateMenuItem_`+`menu_state`; `STORMPAD_THEME` dev hook.
- `stormpad/views/{sidebar,note_list,editor,transcript,controls}.py` — SF Symbol
  library icons + selected pill/border + hover + shield footer (sidebar);
  themed selection with border/glow + category chip (note list); status &
  filename pills, transcript-append target, selection/focus preservation
  (editor); redesigned transcript card w/ icon header + readiness + in-card
  Append button (transcript); `GradientView`, `rounded_view`, `icon_view`
  (controls).
- `stormpad/app.py` — theme menu items wired to `selectTheme:` with
  `representedObject`.
- `stormpad/uihelpers.py` — `status_style` (pure save-status → token mapping).
- `tests/test_theme.py` (new, 13) → 134 tests total.

## Features completed

- Public-GitHub-ready scaffold: package skeleton, packaging, license, ignore
  rules, scripts, README, PRD, handoff.
- **Full headless foundation (Phase 2):** Note model with categories &
  tz-aware timestamps; deterministic Markdown serialization + lenient parsing;
  stable slug filenames with collision handling; atomic writes; full CRUD;
  transcript append API + test-transcript helper; case-insensitive Unicode
  search with category filtering; injectable preferences with safe fallbacks.
- `paths` resolves the canonical `~/Documents/StormPad/Notes/` and creates it
  only on explicit request.
- **Functional native UI (Phase 3):** real macOS window (native chrome/traffic
  lights) + three-column split (sidebar 248 / list 326 / editor); brand header
  with the official logo; search field; category nav (All/Ideas/Sessions/Drafts)
  with live counts and persisted selection; note list with themed selection,
  preview, timestamp, category tag; premium serif `NSTextView` editor with title
  field, created/updated/word-count/filename metadata and real save status;
  read-only transcript section; create (Cmd+N)/select/edit; debounced autosave
  (0.4s, atomic writes, flush on switch/close/quit); search (title/body/
  transcript) with result count; empty / no-selection / no-results states;
  reload + selection/category restoration on relaunch; Storm Blue theme via
  semantic tokens; `NSUserDefaults` prefs adapter.
- **Actions & reliability (Phase 4):** Copy Note (user-visible text only, via
  `copy_text`), Append Test Transcript (live re-render), Open File
  (`NSWorkspace openURL:`), Reveal in Finder (`activateFileViewerSelectingURLs:`),
  Delete with confirmation → **macOS Trash** (`NSFileManager trashItemAtURL:` via
  the injectable delete seam; note kept in UI if Trash fails), native
  **Speak Selection / Stop Speaking** (AVSpeechSynthesizer) in the editor
  context menu and Edit▸Speech, full menu/button validation, external-deletion
  handling, and speech-stop + flush on switch/delete/close/quit.
- **Visual fidelity & themes (Phase 5):** complete semantic token architecture;
  three first-class themes (Storm Blue signature / Light / Deep Dark focus);
  **live View▸Theme switching** (no relaunch) with checkmarks and persistence;
  per-theme window appearance (native traffic lights/cursor/scrollbars); gradient
  background + restrained selection glow (Storm Blue only); SF Symbol pill/icon
  toolbar; polished sidebar (icons, selected pill, hover, shield footer), note
  list (themed selection + category chip), editor (status/filename pills, serif
  typography), transcript card, and empty/search states.
- 134 unit tests pass without AppKit; ruff clean; all three themes launch
  cleanly with an empty console (verified via real launches + `--smoke`).

## Features remaining

- **Phase 6** — icon generation (`.icns` from the official logo), `.app`
  packaging, `.dmg` creation, install/test from `/Applications`, repo audit,
  final docs. See **Final Delivery Requirements** at the top.

## Design comparison (vs. supplied handoff)

**Matched closely:** three-column proportions; sidebar brand block (official
logo + wordmark + tagline), search, library rows with icons/counts/selected
pill, local-first footer; note-list rows (title / 2-line preview / timestamp /
category chip) with themed selection (cyan glow in Storm Blue, soft blue in
Light, quiet zinc in Deep Dark); editor title/metadata/save-status; transcript
card (icon header, readiness indicator, monospace timestamps, Append action);
empty/search/no-results states; all three palettes; save-status pills.

**Native adaptations (AppKit differs from the static mockup):** real macOS
window chrome + real traffic lights instead of the mockup's floating rounded
card and fake lights; per-theme `NSAppearance` drives native controls; window
background is a subtle vertical gradient (native `CAGradientLayer`) rather than
the mockup's layered radial glows; the transcript Append button uses a solid
themed border (CALayer has no native dashed border); fonts are SF Pro / New
York / SF Mono (no bundled Inter / Newsreader / JetBrains Mono).

**Remaining gaps (honest):** not pixel-perfect — micro-spacing, exact glow
radii, and some hover treatments are approximations. Hover is implemented on
sidebar rows; note-row/toolbar hover relies on native defaults. Search-result
title/body **highlighting is deferred** (match metadata is produced by
`search.py` but not yet rendered in-list; see gap below). This was not
verified against the mockup pixel-by-pixel — no display capture was available.

## Known issues / limitations

- **Search highlighting deferred:** result rows show the "N notes matching …"
  header and correct ordering, but per-match title/body highlighting is not yet
  drawn. The `SearchResult.matches` spans are available for a later pass.
- **Autosave & external deletion:** while a note is open, autosave re-persists
  it (atomic write); if the file was deleted externally *mid-edit*, the next
  autosave recreates it (deliberate — never silently discard in-progress edits).
  Open/Reveal/Delete and note-switch/load detect a missing file and recover.
- Autosave does not reorder the list while typing (refreshes on switch / filter).
- Transcript block text is a single paragraph (no internal blank lines).
- **Speech** uses the system default voice; no voice picker/rate/highlighting.
- **Screenshots** could not be captured in the build session (no display access
  for `screencapture`); all three themes launch and run with an empty console.
  See `docs/screenshots/README.md` for reproducible capture commands.

## Speech architecture (Phase 4)

`stormpad/speech.py` isolates text-to-speech. `SpeechController` owns one
backend and enforces validation + "new speech stops previous" + cleanup;
`AVSpeechBackend` wraps a single strongly-retained `AVSpeechSynthesizer`.
Verified imports (PyObjC 12.x): `AVSpeechSynthesizer`, `AVSpeechUtterance`,
`AVSpeechBoundaryImmediate` (== 0) all from the top-level **`AVFoundation`**
module (dependency `pyobjc-framework-AVFoundation`). Tests inject a fake backend
— no real audio. Speech stops on note switch, delete of the active note, window
close, and app quit.

## Design fidelity gaps (agreed)

- **Editor:** V1 uses a premium native `NSTextView` writing surface (readable
  prose, New York serif, no visible Markdown during ordinary writing) with safe
  Markdown serialization underneath — not a rendered/WYSIWYG Markdown view and
  no preview mode. The Transcript component below the body is preserved.
- **Window chrome:** real native macOS window + real traffic lights
  (transparent titlebar / full-size content view), matching the design *inside*
  the native window rather than recreating the mockup's fake floating card and
  fake traffic lights.
- **Fonts:** native SF Pro (UI) / New York (editor titles & body) / SF Mono or
  Menlo (timestamps, filenames). No bundled web fonts (design used Inter /
  Newsreader / JetBrains Mono).
- **Storage path:** `~/Documents/StormPad/Notes/` everywhere; the mockups'
  `~/StormPad/...` strings are treated as presentation copy to be corrected.

## Theme status

**All three themes are complete and first-class.** `theme.py` holds ~50 semantic
tokens per theme; `views/palette.py` resolves them to `NSColor`/fonts/SF Symbols
(no literals in view code). **Live switching** via View▸Theme rebuilds the whole
content tree (`_install_content`) so no stale colors remain, sets a per-theme
`NSAppearance`, preserves editor selection/focus, and persists the choice
(`theme` preference; invalid → Storm Blue). Storm Blue is the default and the
only theme with decorative glow.

## Packaging status

Not started (Phase 6). `scripts/generate_icons.py` documents the reproducible
`sips` + `iconutil` workflow from the untouched source logo; it is a stub until
Phase 6.

## Public-repository audit status

- Supplied ZIPs, raw PRD `.txt`, and root logo original are git-ignored; only
  cleaned copies are committed. No secrets, `.venv`, caches, or build
  artifacts committed.
- **Open item to confirm before publishing:** `PRD.md` preserves the source
  document faithfully, which includes one machine-specific absolute path
  (`Proposed Local Project Path`). Decide whether to genericize it before the
  repo goes public.

## Exact next recommended task

Begin **Phase 6** (packaging & public readiness), per the Final Delivery
Requirements at the top: generate `.icns` from the untouched official logo via a
reproducible `scripts/generate_icons.py` (`sips` + `iconutil`); build a
standalone, double-clickable `StormPad.app` with a correct `Info.plist` (bundle
name / identifier / version) and self-contained dependencies (no source-folder
or `.venv` dependency; e.g. py2app or an embedded venv); install and test from
`/Applications/StormPad.app`; produce a drag-to-Applications `.dmg`; add
reproducible build/install scripts; then a final repo audit and doc pass. Do not
push/publish. **Stop for review at the end of Phase 6.**

### Future distribution direction (do NOT build yet)

```
mattferre.com StormPad showcase
→ Download for macOS
→ GitHub Release asset: StormPad.dmg
→ Open DMG
→ Drag StormPad to Applications
→ Launch StormPad.app
```

The landing page (mattferre.com showcase) and GitHub Release are **future**
work — record the direction, build nothing in Phase 5/6 beyond the local
`.app`/`.dmg`.

Dev/test hooks: `STORMPAD_NOTES_DIR` (temp notes dir), `STORMPAD_INITIAL_QUERY`
(boot into a search state), `STORMPAD_THEME` (force initial theme),
`python -m stormpad --smoke` (build the UI + print introspected state without the
event loop).

## Guardrails (for any continuing agent)

- Do **not** touch `/Users/mattferre/web/APP/wisperflow_` — separate project.
- No voice, AI, cloud, accounts, telemetry, analytics, or speculative features.
- Do not invent design; follow the handoff and the agreed fidelity gaps above.
- Do not modify the official logo; keep the original source untouched.
- Markdown files remain the source of truth.
- Do not push or create a remote. Commit each stable phase locally only.
- Update this file after every phase.

## WisperFlow statement

**WisperFlow was not touched.** No files under `/Users/mattferre/web/APP/wisperflow_`
were read, modified, moved, or copied. StormPad is an entirely separate project.
