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
- **Latest commit:** _see `git log -1` — Phase 4 actions/speech commit_
- **Git status:** clean after the Phase 4 commit (supplied ZIPs, the raw PRD
  `.txt`, and the root logo original are git-ignored; cleaned copies are
  committed; no dev/test notes committed — tests use `tmp_path`, manual runs use
  a temp dir via `STORMPAD_NOTES_DIR`).
- **Phase complete:** Phase 4 (actions, reliability, and native Speak Selection;
  121 tests passing, all headless).

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
- 121 unit tests pass without AppKit; ruff clean; app launches cleanly with an
  empty console (verified via a real launch + `--smoke` introspection).

## Features remaining

- **Phase 5** — visual fidelity, three themes from the token tables, View →
  Theme switcher + persistence, logo, states, resize behavior.
- **Phase 6** — icon generation, optional `.app` packaging, repo audit, docs.

## Known issues / Phase-5 fidelity gaps

- **Visual polish is intentionally deferred to Phase 5:** no gradients, glow,
  rounded window-card look, hover states, or exact spacing/typography of the
  mockup yet. Storm Blue is functional-but-flat; Light and Deep Dark are token
  stubs (disabled in the Theme menu) and **not** yet real themes. Live theme
  switching is Phase 5. The action toolbar uses plain buttons (Phase-4 minimal
  styling), not the designed pill/icon toolbar.
- Transcript remains **read-only text**; the in-card "Append Test Transcript"
  button is decorative — the wired action lives in the toolbar/File menu.
- **Autosave & external deletion:** while a note is open, autosave re-persists
  the current note (atomic write). If its file was deleted externally *mid-edit*,
  the next autosave recreates it — a deliberate choice to never silently discard
  the user's in-progress edits. Open/Reveal/Delete and note-switch/load **do**
  detect a missing file and recover with a clear alert. Continuous filesystem
  watching is still out of scope.
- Autosave does not reorder the list while typing (order refreshes on note
  switch / filter change) — deliberate, to avoid the row jumping under the cursor.
- Transcript block text is treated as a single paragraph (no internal blank
  lines) — sufficient for V1's timestamped chunks.
- **Speech:** uses the current system default voice; no voice picker, rate, or
  word-highlighting (intentionally out of scope). Menu items validate via
  `validateMenuItem_` when a menu opens (pull-based), so state is correct on open.
- **Screenshots:** could not be captured in the build session (no display access
  for `screencapture`); the app launches and runs. See
  `docs/screenshots/README.md` for the one-line reproducible capture commands.

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

`theme.py` defines the semantic token shape and a **functional Storm Blue**
theme (default), consumed everywhere via `views/palette.py` (no literals in view
code). Light and Deep Dark are placeholder stubs of the same shape, disabled in
the View→Theme menu. Real Light/Deep Dark values + live switching land in
Phase 5 from the captured handoff token tables.

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

Begin **Phase 5** (visual fidelity & themes): transcribe the full handoff token
tables into `theme.py` for **Light** and **Deep Dark**, add **live theme
switching** (View▸Theme actions that rebuild/re-color the UI and persist via the
existing `theme` preference), and raise Storm Blue to design fidelity — gradients
/glow/rounded surfaces, hover + selection states, exact spacing/typography, the
designed pill/icon action toolbar, transcript card, and empty/search polish.
Keep the Phase 2 storage and Phase 3/4 behavior intact. **Stop for review at the
end of Phase 5.** (Packaging `.app`/`.dmg` remains Phase 6 — see Final Delivery
Requirements at the top.)

Dev/test hooks available: `STORMPAD_NOTES_DIR` (temp notes dir),
`STORMPAD_INITIAL_QUERY` (boot into a search state), `python -m stormpad --smoke`
(build the UI and print introspected state without the event loop).

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
