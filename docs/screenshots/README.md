# Sanitized screenshots

Repository screenshots must use generated fixtures in a temporary directory,
never real notes or imported personal files.

## Phase 5.1 capture status

A native Storm Blue active-canvas screenshot was captured and visually
inspected on 2026-07-23:

```text
/var/folders/z4/lznm_6tn1l3dc4sf7wm25d100000gn/T/codex-shot-2026-07-23_19-54-43.png
```

It verifies the clear selected-note state, clean title/body page, headings,
inline formatting, to-dos, quote, divider, and managed native image preview.
It is an ephemeral inspection artifact, not a committed public asset.

The complete screenshot matrix still needs recapture after the final gutter
coordinate adjustment: blank note, active canvas, block menu, formatting
toolbar, image/file, transcript, collapsed note list, Storm Blue, Light, and
Deep Dark. Do not describe those states as visually verified until their
captures have been inspected.

## Reproducible fixture

```bash
export STORMPAD_DEMO_ROOT="$(mktemp -d)"
export STORMPAD_DEMO_NOTES="$STORMPAD_DEMO_ROOT/Notes"

./.venv/bin/python - "$STORMPAD_DEMO_NOTES" <<'PY'
import sys
from pathlib import Path
from stormpad import models
from stormpad.attachments import import_attachment, relative_markdown_path
from stormpad.session import NoteStore

notes = Path(sys.argv[1])
store = NoteStore(notes)
note = store.create_note("Product launch plan", models.SESSIONS)
store.update_body(
    note.id,
    "## Direction\n\n"
    "A **focused** plan with <u>clear ownership</u> and "
    '<span data-stormpad-color="cyan">calm momentum</span>.\n\n'
    "- [x] Define the first release\n\n"
    "- [ ] Capture sanitized screenshots\n\n"
    "> Keep the writing experience quiet and local-first.\n\n"
    "---",
)
store.append_transcript_block(note.id, "Confirm the local launch plan.", 4)
PY
```

Add only generated/non-personal attachment fixtures if an image or file state
is needed. The app copies them under the temporary root's sibling
`Attachments/` directory.

## Launch states

```bash
# Active Storm Blue canvas, cursor in first block.
STORMPAD_NOTES_DIR="$STORMPAD_DEMO_NOTES" \
STORMPAD_THEME=storm_blue \
STORMPAD_FOCUS_EDITOR=1 \
STORMPAD_EDITOR_SELECTION=0,0 \
./.venv/bin/python -m stormpad

# Block insertion menu.
STORMPAD_NOTES_DIR="$STORMPAD_DEMO_NOTES" \
STORMPAD_THEME=storm_blue \
STORMPAD_FOCUS_EDITOR=1 \
STORMPAD_EDITOR_SELECTION=0,0 \
STORMPAD_SHOW_BLOCK_MENU=1 \
./.venv/bin/python -m stormpad

# Formatting toolbar (adjust range to fixture text).
STORMPAD_NOTES_DIR="$STORMPAD_DEMO_NOTES" \
STORMPAD_THEME=storm_blue \
STORMPAD_FOCUS_EDITOR=1 \
STORMPAD_EDITOR_SELECTION=12,7 \
./.venv/bin/python -m stormpad

# Theme variants.
STORMPAD_NOTES_DIR="$STORMPAD_DEMO_NOTES" STORMPAD_THEME=light \
./.venv/bin/python -m stormpad
STORMPAD_NOTES_DIR="$STORMPAD_DEMO_NOTES" STORMPAD_THEME=deep_dark \
./.venv/bin/python -m stormpad

# Truly blank library/new-note state.
STORMPAD_NOTES_DIR="$(mktemp -d)/Notes" ./.venv/bin/python -m stormpad
```

The collapse state is a real preference. Toggle it with the header/sidebar
control, quit, and relaunch the same state to verify persistence. Restore it
after capture if this is a normal development profile.

## Capture command

Use the macOS screenshot skill/helper when available, or the normal
Command-Shift-4 then Space workflow. Save public images in this directory with
descriptive names only after visual inspection, for example:

```text
active-storm-blue.png
active-light.png
active-deep-dark.png
block-menu.png
formatting-toolbar.png
collapsed-notes.png
```

Dev hooks are limited to deterministic capture/setup:

- `STORMPAD_NOTES_DIR`
- `STORMPAD_INITIAL_QUERY`
- `STORMPAD_THEME`
- `STORMPAD_FOCUS_EDITOR`
- `STORMPAD_EDITOR_SELECTION`
- `STORMPAD_SHOW_BLOCK_MENU`
- `python -m stormpad --smoke`
