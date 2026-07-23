# StormPad — HANDOFF

Living handoff document. Updated after every phase. Intended for any agent or
human (including a later Codex session) continuing this work.

## Product summary

StormPad is a native macOS (Python 3.12 + PyObjC/AppKit) local-first notepad.
Notes are plain Markdown files in `~/Documents/StormPad/Notes/` (the source of
truth). Apple Notes-like structure (sidebar → note list → editor), original
premium visual identity, three themes. No cloud, accounts, telemetry, AI, or
voice in V1. See `PRD.md` for full scope and `docs/design/` notes for the
design handoff.

## Current state

- **Branch:** `main`
- **Latest commit:** _see `git log -1` — Phase 2 domain/storage commit_
- **Git status:** clean after the Phase 2 commit (supplied ZIPs, the raw PRD
  `.txt`, and the root logo original are git-ignored; cleaned copies are
  committed; no test-generated notes committed — tests use `tmp_path`).
- **Phase complete:** Phase 2 (domain, storage, session, search, preferences —
  fully headless, 81 tests passing).

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
- Runnable placeholder `main()` + `python -m stormpad` (UI still Phase 3).
- 81 unit tests pass without AppKit; ruff clean.

## Features remaining

- **Phase 3** — native window + three columns, create/select/edit, autosave,
  search, categories, reload-on-restart.
- **Phase 4** — Copy Note, Append Test Transcript, Open File, Reveal in Finder,
  delete-with-confirm, save status, error handling, safe shutdown.
- **Phase 5** — visual fidelity, three themes from the token tables, View →
  Theme switcher + persistence, logo, states, resize behavior.
- **Phase 6** — icon generation, optional `.app` packaging, repo audit, docs.

## Known issues

- None functional. UI modules (`app`, `window`, `views/*`) are documented
  stubs pending Phase 3; `theme.py` holds tokens only from Phase 5.
- Transcript block text is treated as a single paragraph (no internal blank
  lines) — sufficient for V1's timestamped chunks.

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

Token tables for all three themes are captured from the design handoff and
will be transcribed into `theme.py` in Phase 5. Storm Blue is the default.

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

Begin **Phase 3** (native UI): NSApplication lifecycle + main menu (Cmd+N/F/S/O)
in `app.py`; a native window with transparent titlebar / full-size content view
and real traffic lights hosting a three-column `NSSplitView` in `window.py`;
then `views/sidebar.py`, `views/note_list.py`, `views/editor.py` wired to a
`NoteStore`. Deliver create/select/edit, debounced autosave, search, categories,
and reload-on-restart. Consume the Phase 2 API — do not reimplement storage in
the UI. **Stop for review at the end of Phase 3.**

Phase 3 will add an `NSUserDefaults`-backed `PreferencesBackend` implementing
the `get/set/delete` protocol from `preferences.py`.

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
