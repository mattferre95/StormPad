# Design source

The visual implementation follows a Claude Design handoff supplied for this
project (two `.zip` bundles). Those archives are **local build references** and
are intentionally **not committed** to this repository (see `.gitignore`).

## What the handoff specifies

- **Base app design** — one macOS window, three columns (sidebar 248px → note
  list 326px → editor), in three states: empty, active note, search.
- **Theme system** — one layout, three production themes defined as complete
  semantic token tables:
  - **Storm Blue / Signature** (default) — night navy, cyan/blue accents, glow.
  - **Light** — cool-gray canvas, frosted white panels, restrained blue.
  - **Deep Dark / Focus** — near-black monochrome, no colored glow.

The token tables are transcribed into `stormpad/theme.py` during Phase 5.

## Agreed native adaptations

See `HANDOFF.md` → "Design fidelity gaps": premium native `NSTextView` editor
(no visible Markdown / no WYSIWYG / no preview in V1), real native window
chrome and traffic lights, native fonts (SF Pro / New York / SF Mono), and the
canonical `~/Documents/StormPad/Notes/` storage path.
