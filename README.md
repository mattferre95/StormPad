<div align="center">

<img src="assets/Stormpad_logo.png" alt="StormPad logo" width="120" height="120" />

# StormPad

**A calm, local-first macOS notepad for capturing ideas as they happen.**

</div>

---

StormPad is a native Python + AppKit application with a focused, block-oriented
writing canvas. Notes stay as human-readable Markdown on your Mac; attachments
are copied into local managed folders. There are no accounts, cloud sync,
telemetry, external AI services, or web views.

> **Status:** Phase 5.1.4 critical editor, navigation, dragging, and lifecycle
> repairs are implemented locally on `feature/notion-editor` and ready for
> hands-on review. Phase 6 packaging has
> not started: there is no final `.app`, `.icns`, `.dmg`, signing,
> notarization, release, or landing page yet.

## What is implemented

- Native three-column macOS window: sidebar, collapsible note list, editor.
- Clear themed selected-note treatment that remains visible while writing.
- Blank new-note flow with an unsaved `Untitled` placeholder and continuous
  title-to-body keyboard transition. A `+` in the Notes header, Cmd+N, File →
  New Note, and New Note in Project all run the same creation command, so the
  note lands in the selected Project (or Unfiled) with the title focused.
- Native block editor for Text, Heading 1–3, To-do, Bulleted list, Numbered
  list, Quote, Divider, Link, Image, File, and optional Transcript.
- One pointer-following `+` in a dedicated non-overlapping gutter. Block drag
  controls, drop targets, insertion indicators, and Move Up/Down UI are absent.
- Selection-aware block commands convert one or many selected paragraphs in
  place; collapsed-caret commands retain insertion behavior.
- Editor-wide Cmd+A/Delete clears title, body, attachment references, and
  Transcript presentation as one undoable action without deleting the note or
  managed attachment files.
- Bold, italic, underline, link, curated text colors, and curated highlights,
  with keyboard shortcuts plus explicit Clear and Clear / Transparent semantic
  swatches.
- Local filesystem-backed Projects alongside categories, with All Notes and
  Unfiled filters, note counts, safe note movement, and project-aware creation.
- Optional Project icons — a curated SF Symbol or a single emoji — chosen from a
  compact native picker, persisted with the project and never affecting its
  identity, folder, or notes.
- A compact bottom-left local workspace row opening Settings, Appearance,
  Reveal StormPad Folder, About, and Quit. StormPad has no accounts, so it shows
  no sign-in, upgrade, subscription, or sync affordance.
- Restrained native motion — collapsing the notes panel, changing the selected
  surface, reloading the note list, and revealing hover controls — with every
  duration coming from one policy that honours macOS Reduce Motion.
- A compact top-right native Share button plus File and Note menu commands.
  Notes share as readable temporary TXT files through
  `NSSharingServicePicker`; projects share as sanitized local ZIP packages.
- Direct whole-row project reordering with persisted custom order, insertion
  feedback, undo/redo, and context-menu Move Up/Down alternatives.
- Direct whole-row note dragging from the middle list onto Projects or
  Unfiled, preserving stable identity, attachments, selection, and rollback
  safety. All Notes is intentionally not a destination.
- Debounced atomic autosave, native undo/redo, search, categories, restored
  selection, Copy Note, Open File, Reveal in Finder, Delete to Trash, and
  Speak Selection.
- Stable UUID note identity independent of title/filename.
- Safe title-derived filenames such as `my-business-plan.md`, with collision
  suffixes, legacy-note migration, and an explicit sanitized manual rename
  mode available from Note Info.
- Managed local images/files under `Attachments/<stable-note-id>/`, including
  native image previews, file type/size, Open/Reveal, and conservative orphan
  tracking.
- A protected native Transcript container with empty/populated states,
  collapse/expand, timestamped read-only rows, contextual test append/chunk
  actions, search, undo, and persistence.
- Note Info with current filename/path/dates/category/word count and native
  open/reveal/rename/export/settings actions.
- Deterministic plain-text export through a native save panel.
- Complete native application menus and a reusable Settings window for theme,
  the Add Block hover control, and local storage locations.
- Storm Blue, Light, and Deep Dark themes with live switching.

## Run

Requires macOS and Python 3.12.

```bash
./scripts/run.sh
```

The script creates a local `.venv` on first run, installs the project, and
launches the native development app.

Manual setup:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python -m stormpad
```

## Verify

```bash
./scripts/test.sh
./.venv/bin/ruff check .
./.venv/bin/python -m compileall -q stormpad scripts tests
./.venv/bin/python -m stormpad --self-check
./.venv/bin/python -m stormpad --smoke
./.venv/bin/python scripts/native_interaction_smoke.py
```

The test suite is headless and uses temporary directories. Native `--smoke`
and visual launches require an active macOS display session.

## Unsigned local packaging

The initial Phase 6A package requires macOS 13 or later, Apple Silicon, and an
arm64 Python 3.12 environment. Development continues to launch with
`./scripts/run.sh`; release packaging uses a separate pinned environment:

```bash
python3.12 -m venv .release-venv
./.release-venv/bin/python -m pip install -r requirements-release.txt
STORMPAD_RELEASE_PYTHON=.release-venv/bin/python ./scripts/build_app.sh
./.release-venv/bin/python scripts/verify_package.py
./scripts/build_dmg.sh
```

The generated review artifacts are:

```text
dist/StormPad.app
dist/StormPad-0.1.0.dmg
```

These artifacts are unsigned and not notarized. They are for local review and
are not ready for public distribution. This first package supports arm64 only;
it does not claim Intel support. Packaging does not move or copy user notes:
they remain in `~/Documents/StormPad/`.

## Local storage

```text
~/Documents/StormPad/
├── Notes/
│   ├── my-business-plan.md
│   └── Projects/
│       └── build/
│           ├── .stormpad-project.json
│           └── editor-plan.md
└── Attachments/
    └── <stable-note-id>/
        ├── moodboard.png
        └── brief.pdf
```

A note starts with a title and metadata envelope, followed by the Markdown body:

```markdown
# My Business Plan

Created: 2026-07-23 14:30:00+02:00
Updated: 2026-07-23 15:05:00+02:00
Category: Ideas
ID: 6a774f94-09f6-44f1-9e08-41fc0ddde477

## Notes

## Direction

A **focused** plan with <u>clear ownership</u>.

- [x] Define the first release
```

Standard Markdown is used where possible. Underline and curated semantic colors
use a small allow-listed StormPad HTML representation; Markdown/HTML is never
executed. See [docs/storage.md](docs/storage.md) for the exact format,
attachment policy, filename behavior, and legacy migration.

## Themes

| Theme | Character |
| --- | --- |
| **Storm Blue** | Night navy, restrained electric blue/cyan, subtle selection glow. |
| **Light** | Cool white canvas with soft gray-blue selection. |
| **Deep Dark** | Near-black zinc surfaces for quiet focus. |

Switch from **View ▸ Theme** or **StormPad ▸ Settings…**. Theme, selected
project, project ordering/collapse, collapsed-note-list state, and the
hover-control preference persist.

## Screenshots

Sanitized Phase 5.1.3 and 5.1.4 fixtures and reproducible capture commands are documented
in [docs/screenshots/README.md](docs/screenshots/README.md). Do not capture real
personal notes for repository screenshots.

## Architecture

The AppKit layer renders a semantic block model backed by one rich
`NSTextView`; storage/parser/session code remains AppKit-free:

```text
stormpad/
  app.py                     application lifecycle and native menus
  window.py                  window, actions, autosave and selection controller
  blocks.py                  semantic blocks and inline marks
  block_parser.py            Markdown to blocks
  block_serializer.py        blocks to deterministic safe Markdown
  attachments.py             local managed attachment policy
  models.py / storage.py     notes, projects, identity, atomic local file I/O
  session.py                 CRUD, movement, deletion safety, transcript seam
  preferences.py / theme.py  persisted state and three complete palettes
  exporter.py                deterministic readable TXT output
  sharing.py                 temporary note TXT and sanitized project ZIP shares
  dragdrop.py                private UUID payloads and pure reorder helpers
  views/block_editor.py      native writing page, gutter and formatting
  views/note_list.py         selected rows and collapsible panel
  views/settings.py          reusable native Settings window
```

See [docs/architecture.md](docs/architecture.md) for selection, undo, autosave,
transcript, and migration details.

## Scope and roadmap

StormPad remains a standalone local-first notepad. This phase does not add
recording, live transcription, AI writing, cloud storage, collaboration,
arbitrary embeds, databases, or publishing.

- **Phase 5.1.4 (current):** data-safe native Return handling, trustworthy
  sidebar hit-testing/drag surfaces, and close/reopen lifecycle repair.
- **Phase 6 (next, after manual review):** generate the official `.icns`, build
  a standalone `StormPad.app`, install-test it from `/Applications`, and create
  a drag-to-Applications `.dmg`.
- **Future:** a GitHub Release asset linked from a mattferre.com StormPad page.
- **Later V2 direction:** WisperFlow Session Notes may call the existing local
  transcript seam. WisperFlow is a separate project and was not touched here.

## Privacy

Everything stays on this Mac. StormPad has no network service, account,
analytics, telemetry, or external AI dependency.

## License

[MIT](LICENSE) © 2026 StormPad contributors
