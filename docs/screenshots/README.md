# Sanitized screenshots

Repository screenshots must use generated fixtures in a temporary directory,
never real notes or imported personal files.

## Phase 5.1.1 capture status

The following native captures were launched against isolated `/tmp` libraries
and visually inspected on 2026-07-23. They are ephemeral verification artifacts,
not committed public assets.

| State | Inspected capture |
| --- | --- |
| Storm Blue gutter, headings, lists, populated Transcript | `/tmp/stormpad-phase511-gutter-headings-lists.png` |
| Complete working block menu | `/tmp/stormpad-phase511-block-menu.png` |
| Native drag insertion line | `/tmp/stormpad-phase511-drag-insertion.png` |
| Empty Transcript and append action | `/tmp/stormpad-phase511-transcript-empty.png` |
| Contextual semantic color swatches | `/tmp/stormpad-phase511-color-swatches.png` |
| Note Info filename/path/actions | `/tmp/stormpad-phase511-note-info.png` |
| Native TXT export panel | `/tmp/stormpad-phase511-txt-export-panel.png` |
| Settings Appearance/Editor/Storage | `/tmp/stormpad-phase511-settings-appearance.png` |
| Collapsed Notes tab | `/tmp/stormpad-phase511-collapsed-notes.png` |
| Light theme | `/tmp/stormpad-phase511-theme-light.png` |
| Deep Dark theme | `/tmp/stormpad-phase511-theme-deep-dark.png` |

The Storm Blue capture also proves that gutter controls end before the
92-point text inset, the drag handle does not cover characters, and heading,
to-do, numbered, quote, divider, inline color/underline, and populated
Transcript surfaces coexist. Light and Deep Dark were captured separately.

## Reproducible fixtures

Use separate preference suites as well as temporary note roots. This prevents a
development capture from reading or changing the normal StormPad selection,
theme, or collapsed-panel state.

```bash
mkdir -p /tmp/stormpad-phase511-populated/Notes
export STORMPAD_DEMO_NOTES=/tmp/stormpad-phase511-populated/Notes
export STORMPAD_DEFAULTS_SUITE=com.stormpad.StormPad.ScreenshotFixture

./.venv/bin/python - "$STORMPAD_DEMO_NOTES" <<'PY'
import sys
from pathlib import Path
from stormpad import models
from stormpad.session import NoteStore

store = NoteStore(Path(sys.argv[1]))
note = store.create_note("September launch plan", models.SESSIONS)
note.body = (
    "## Direction\n\n"
    "A **focused** launch with <u>clear ownership</u> and "
    '<span data-stormpad-color="cyan">calm momentum</span>.\n\n'
    "- [x] Define the first release\n\n"
    "- [ ] Capture the final screenshots\n\n"
    "1. Confirm the release path\n\n"
    "> Keep the writing experience quiet and local-first.\n\n"
    "---\n\n"
    '<!-- stormpad:transcript collapsed="false" -->'
)
note.transcript_visible = True
store.save_note(note)
store.append_transcript_block(
    note.id, "We should launch the first version in September.", 4
)
store.append_transcript_block(
    note.id,
    "The landing page should link directly to the GitHub release.",
    17,
)
PY
```

Create a second library with a visible Transcript marker and no chunks for the
empty-state capture.

## Launch states

```bash
# Hover gutter / Storm Blue / populated Transcript.
STORMPAD_NOTES_DIR="$STORMPAD_DEMO_NOTES" \
STORMPAD_DEFAULTS_SUITE=com.stormpad.StormPad.ScreenshotFixture \
STORMPAD_THEME=storm_blue \
STORMPAD_FOCUS_EDITOR=1 \
STORMPAD_EDITOR_SELECTION=0,0 \
STORMPAD_HOVER_BLOCK=0 \
./.venv/bin/python -m stormpad

# Block menu.
STORMPAD_NOTES_DIR="$STORMPAD_DEMO_NOTES" \
STORMPAD_DEFAULTS_SUITE=com.stormpad.StormPad.ScreenshotMenu \
STORMPAD_FOCUS_EDITOR=1 \
STORMPAD_EDITOR_SELECTION=0,0 \
STORMPAD_SHOW_BLOCK_MENU=1 \
./.venv/bin/python -m stormpad

# Formatting swatches.
STORMPAD_NOTES_DIR="$STORMPAD_DEMO_NOTES" \
STORMPAD_DEFAULTS_SUITE=com.stormpad.StormPad.ScreenshotColors \
STORMPAD_FOCUS_EDITOR=1 \
STORMPAD_EDITOR_SELECTION=12,7 \
STORMPAD_SHOW_COLOR_MENU=text \
./.venv/bin/python -m stormpad

# Deterministic insertion line, Note Info, Settings, or TXT panel.
STORMPAD_DRAG_INSERTION=2 ./.venv/bin/python -m stormpad
STORMPAD_SHOW_NOTE_INFO=1 ./.venv/bin/python -m stormpad
STORMPAD_SHOW_SETTINGS=1 ./.venv/bin/python -m stormpad
STORMPAD_SHOW_EXPORT=1 ./.venv/bin/python -m stormpad

# Panel and theme variants.
STORMPAD_COLLAPSE_NOTES=1 ./.venv/bin/python -m stormpad
STORMPAD_THEME=light ./.venv/bin/python -m stormpad
STORMPAD_THEME=deep_dark ./.venv/bin/python -m stormpad
```

Always include `STORMPAD_NOTES_DIR` and `STORMPAD_DEFAULTS_SUITE` from the
fixture setup in the abbreviated commands above.

## Capture command

Use the macOS screenshot helper and inspect every output before reporting it:

```bash
python3 /Users/mattferre/.codex/skills/screenshot/scripts/take_screenshot.py \
  --app Python --window-name StormPad --mode temp
```

Transient native menus are separate transparent windows. Capture the complete
sanitized application region so the menu retains its editor context.

## Development hooks

These hooks are deterministic capture/test setup only and are inert in normal
launches:

- `STORMPAD_NOTES_DIR`
- `STORMPAD_DEFAULTS_SUITE`
- `STORMPAD_INITIAL_QUERY`
- `STORMPAD_THEME`
- `STORMPAD_FOCUS_EDITOR`
- `STORMPAD_EDITOR_SELECTION`
- `STORMPAD_HOVER_BLOCK`
- `STORMPAD_SHOW_BLOCK_MENU`
- `STORMPAD_SHOW_COLOR_MENU`
- `STORMPAD_DRAG_INSERTION`
- `STORMPAD_SHOW_NOTE_INFO`
- `STORMPAD_SHOW_SETTINGS`
- `STORMPAD_SHOW_EXPORT`
- `STORMPAD_COLLAPSE_NOTES`
- `python -m stormpad --smoke`
