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

> **Status:** Phase 5.1, the clean block-editor redesign, is implemented on
> `feature/notion-editor` and ready for review. Phase 6 packaging has not
> started: there is no final `.app`, `.icns`, `.dmg`, signing, notarization,
> release, or landing page yet.

## What is implemented

- Native three-column macOS window: sidebar, collapsible note list, editor.
- Clear themed selected-note treatment that remains visible while writing.
- Blank new-note flow with an unsaved `Untitled` placeholder and continuous
  title-to-body keyboard transition.
- Native block editor for Text, Heading 1–3, To-do, Bulleted list, Numbered
  list, Quote, Divider, Link, Image, File, and optional Transcript.
- Native `+` block menu, Option-insert-above, block conversion, and a stable
  Move Up / Move Down reorder menu.
- Bold, italic, underline, link, curated text colors, and curated highlights,
  with keyboard shortcuts and a contextual formatting toolbar.
- Debounced atomic autosave, native undo/redo, search, categories, restored
  selection, Copy Note, Open File, Reveal in Finder, Delete to Trash, and
  Speak Selection.
- Stable UUID note identity independent of title/filename.
- Safe title-derived filenames such as `my-business-plan.md`, with collision
  suffixes and legacy-note migration.
- Managed local images/files under `Attachments/<stable-note-id>/`, including
  native image previews, file type/size, Open/Reveal, and conservative orphan
  tracking.
- Transcript chunks kept separate from editable prose and shown only when
  content exists or a Transcript block is explicitly inserted.
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
./.venv/bin/python -m compileall -q stormpad tests
./.venv/bin/python -m stormpad --self-check
```

The test suite is headless and uses temporary directories. Native `--smoke`
and visual launches require an active macOS display session.

## Local storage

```text
~/Documents/StormPad/
├── Notes/
│   └── my-business-plan.md
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

Switch from **View ▸ Theme**. Theme and collapsed-note-list state persist.

## Screenshots

Sanitized Phase 5.1 fixtures and reproducible capture commands are documented
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
  models.py / storage.py     note model, envelope, identity, atomic file I/O
  session.py                 CRUD and transcript integration seam
  preferences.py / theme.py  persisted state and three complete palettes
  views/block_editor.py      native writing page, gutter and formatting
  views/note_list.py         selected rows and collapsible panel
```

See [docs/architecture.md](docs/architecture.md) for selection, undo, autosave,
transcript, and migration details.

## Scope and roadmap

StormPad remains a standalone local-first notepad. This phase does not add
recording, live transcription, AI writing, cloud storage, collaboration,
arbitrary embeds, databases, or publishing.

- **Phase 5.1 (current):** clean native block editor and storage migration.
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
