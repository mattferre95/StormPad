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
- **Latest commit:** _see `git log -1` — Phase 1 scaffold commit_
- **Git status:** clean after the Phase 1 commit (supplied ZIPs, the raw PRD
  `.txt`, and the root logo original are git-ignored; cleaned copies are
  committed).
- **Phase complete:** Phase 1 (repository scaffold).

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
- `docs/architecture.md`
- `stormpad/__init__.py`, `__main__.py`, `app.py`, `paths.py` and stub modules
  `window.py`, `models.py`, `storage.py`, `session.py`, `search.py`,
  `preferences.py`, `theme.py`
- `stormpad/views/` — `__init__.py` + stubs: `sidebar.py`, `note_list.py`,
  `editor.py`, `toolbar.py`, `transcript.py`, `empty_state.py`, `controls.py`
- `scripts/run.sh`, `test.sh`, `format.sh`, `generate_icons.py`
- `tests/test_smoke.py`
- `assets/Stormpad_logo.png` (byte-identical copy of the untouched original)

## Features completed

- Public-GitHub-ready scaffold: package skeleton, packaging, license, ignore
  rules, scripts, README, PRD, handoff.
- `paths` resolves the canonical `~/Documents/StormPad/Notes/`.
- Runnable placeholder `main()` + `python -m stormpad`.
- Smoke tests pass; package imports without AppKit.

## Features remaining

- **Phase 2** — models, storage (Markdown serialize/parse, CRUD, stable
  filenames, atomic writes), session (incl. `append_transcript_block`),
  search, preferences persistence; full unit tests.
- **Phase 3** — native window + three columns, create/select/edit, autosave,
  search, categories, reload-on-restart.
- **Phase 4** — Copy Note, Append Test Transcript, Open File, Reveal in Finder,
  delete-with-confirm, save status, error handling, safe shutdown.
- **Phase 5** — visual fidelity, three themes from the token tables, View →
  Theme switcher + persistence, logo, states, resize behavior.
- **Phase 6** — icon generation, optional `.app` packaging, repo audit, docs.

## Known issues

- None functional. UI modules are documented stubs pending Phase 3.

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

Begin **Phase 2**: implement `models.py` and `storage.py` with the Markdown
format from PRD §12 (TDD), then `session.py` (`append_transcript_block`),
`search.py`, and `preferences.py`, with `tests/` covering each. Keep everything
AppKit-free and testable headlessly. **Stop for review at the end of Phase 2.**

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
