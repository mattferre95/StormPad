<div align="center">

<img src="assets/Stormpad_logo.png" alt="StormPad logo" width="120" height="120" />

# StormPad

**A local-first notepad for capturing ideas as they happen.**

</div>

---

StormPad is a native macOS notepad for fast idea capture and private, local
writing. It borrows the familiar structure of Apple Notes — sidebar, note list,
editor, search, autosave — but is visually its own thing: modern, calm,
premium, and local-first. Your notes are saved as plain **Markdown files** on
your Mac. No cloud sync, no accounts, no telemetry, no external AI.

> **Status:** V1 in active development. The local-first **core** — Markdown
> storage, notes, categories, transcript blocks, search, and preferences — is
> implemented and unit-tested (headless). The native macOS **UI** is being
> built next; `./scripts/run.sh` currently launches a placeholder. This README
> describes the V1 scope. Voice/session-notes features are a later phase (see
> Roadmap).

## Screenshots

_Screenshots land during Phase 5 (visual fidelity)._

| Storm Blue (default) | Light | Deep Dark / Focus |
| --- | --- | --- |
| _placeholder_ | _placeholder_ | _placeholder_ |

## Features

- Native macOS window with a three-column layout: **sidebar → note list → editor**
- Create, rename, and edit notes
- Debounced **autosave** with a live save-status indicator
- Notes stored as plain **Markdown** — the source of truth
- Reloads your notes on restart
- **Search** across note titles and body text, with a results state
- Categories: **All Notes · Ideas · Sessions · Drafts**
- Selected-note, empty, and search-results states
- **Delete** with confirmation
- **Open File** and **Reveal in Finder**
- **Copy Note**
- **Append Test Transcript** — timestamped transcript blocks (a clean seam for
  future voice sessions; no voice code in V1)
- A **local-first & private** indicator
- Three complete themes with a **View → Theme** switcher that persists

## Themes

| Theme | Feel |
| --- | --- |
| **Storm Blue / Signature** (default) | Night-navy surfaces, electric-blue & cyan accents, subtle glow |
| **Light** | Clean cool-gray canvas, frosted white panels, restrained blue accents |
| **Deep Dark / Focus** | Near-black monochrome, no colored glow, tuned for long focused writing |

## Local-first

StormPad reads and writes plain `.md` files in a folder you own. The app is a
quiet, beautiful window over that folder — nothing leaves your Mac. Because the
files are ordinary Markdown, you can back them up, edit them in any other
editor, move them, or put them under version control.

## V1 scope

The full product definition lives in [PRD.md](PRD.md). V1 is deliberately
small: a clean, reliable, local-first notepad foundation.

### Non-goals (V1)

No speech recording, Whisper transcription, global hotkeys, WisperFlow
integration, system-audio capture, speaker labels, AI summaries, cloud sync,
accounts, payments, telemetry, or analytics. V1 is the standalone local
notepad only.

## Requirements

- macOS
- Python 3.12
- [PyObjC](https://pyobjc.readthedocs.io/) (installed automatically into a
  local virtual environment by the scripts below)

## Installation & run

```bash
./scripts/run.sh
```

On first run this creates a local `.venv`, installs StormPad and its runtime
dependencies, and launches the app.

Prefer manual setup?

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python -m stormpad
```

## Tests

```bash
./scripts/test.sh
```

Non-UI logic (models, storage, paths, session, search, preferences) is unit
tested with `pytest` and runs headlessly — no app launch required.

Formatting & lint:

```bash
./scripts/format.sh
```

## Storage location

```
~/Documents/StormPad/Notes/
```

The app creates this folder on first launch (never on import; tests use a
temporary directory and never touch your real Documents). Markdown files are
the source of truth. Renaming a note updates the title inside the Markdown
file; the underlying filename stays stable in V1.

Each note is a plain, human-readable Markdown file:

```markdown
# App idea — voice session notes

Created: 2026-07-23 16:47:06+02:00
Updated: 2026-07-23 16:47:06+02:00
Category: Sessions

## Notes

Capture before it evaporates.
Local-first, plain Markdown.

## Transcript

[00:00:04]
This is a captured thought.

[00:00:11]
Chunks append in order.
```

Filenames are stable, slugged, and timestamped (e.g.
`2026-07-23-1647-app-idea-voice-session-notes.md`).

## Architecture

Non-UI logic is fully decoupled from AppKit so it stays testable.

```
stormpad/
  app.py          entry point / NSApplication lifecycle & menus
  window.py       main window + three-column split controller
  models.py       Note data structures
  storage.py      Markdown serialization + note file CRUD
  paths.py        app paths & directory creation
  session.py      note/session operations (create, save, append transcript)
  search.py       title + body search / filtering
  preferences.py  persisted theme & last-open note
  theme.py        semantic theme tokens (Storm Blue / Light / Deep Dark)
  views/          sidebar, note_list, editor, toolbar, transcript, empty_state, controls
assets/           official logo + generated icons
scripts/          run.sh · test.sh · format.sh · generate_icons.py
tests/            headless unit tests
```

See [docs/architecture.md](docs/architecture.md) for detail.

## Privacy

> StormPad stores notes locally on your Mac. V1 does not use cloud sync,
> accounts, analytics, telemetry, external AI APIs, or network services.

## Roadmap

- **V1** — standalone local-first Markdown notepad _(current)_
- **V2** — WisperFlow **Session Notes**: long-form local dictation appends
  timestamped transcript blocks into StormPad-style notes
- **Later** — folders/tags, Markdown preview, export, local intelligence
  (all local-first)

### Relationship to WisperFlow

StormPad is built as a **separate, standalone** project first. Its `Note` /
storage / session concepts are designed so WisperFlow can later reuse them for
a premium Session Notes feature — without coupling the two apps. No WisperFlow
code ships in V1.

## Contributing

Issues and PRs are welcome. Please keep changes within the V1 scope and the
local-first, no-network principle. Run `./scripts/format.sh` and
`./scripts/test.sh` before opening a PR.

## License

[MIT](LICENSE) © 2026 StormPad contributors
