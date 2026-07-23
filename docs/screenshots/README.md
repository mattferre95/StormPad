# Sanitized screenshots

Repository screenshots must use generated fixtures in a temporary directory,
never real notes or imported personal files.

## Phase 5.1.4 capture status

`phase-5-1-4/enter-navigation-repaired.png` and
`phase-5-1-4/native-window-repaired.png` use the disposable fixture at
`/tmp/stormpad-phase514-fixture.t4wIic/Notes`. Both were visually inspected on
2026-07-24 and show the selected Alpha project plus the preserved
`My Project Plan`, `First line`, and `Café 🚀` content after the native Return
matrix. The first uses StormPad's app-owned capture hook; the second is a
window-ID-only system capture after Screen Recording preflight succeeded.

## Phase 5.1.3 capture status

The following committed captures use the disposable fixture at
`/tmp/stormpad-phase513-fixture.SxaznD/Notes` and isolated defaults suites.
Every image was visually inspected on 2026-07-23.

| State | Sanitized capture |
| --- | --- |
| Top-right Share button | `phase-5-1-3/share-button.png` |
| Native macOS Share sheet with a temporary TXT | `phase-5-1-3/native-share-sheet.png` |
| Selected Build project and its context menu | `phase-5-1-3/share-project-menu-1.png`, `share-project-menu-2.png` |
| Lifted Build row and below-last insertion line | `phase-5-1-3/project-drag-insertion.png` |
| Note over highlighted StormPad drop target (Storm Blue) | `phase-5-1-3/note-over-project.png` |
| Note moved into StormPad, with counts updated | `phase-5-1-3/note-moved-into-project.png` |
| Persisted StormPad, WisperFlow, Build order after relaunch | `phase-5-1-3/project-order-after-relaunch.png` |
| Light drop target | `phase-5-1-3/drop-state-light.png` |
| Deep Dark drop target | `phase-5-1-3/drop-state-deep-dark.png` |

The native Share picker was captured from the disposable Python-hosted
StormPad process after the exact process was activated. No service or recipient
was selected. The app-owned renderer captured the other states so it could not
include other applications or desktop content. Screen Recording permission
preflight succeeded for the native picker capture.

The fixture used projects named Build, StormPad, and WisperFlow. “WisperFlow”
is only a disposable folder name in the fixture; no WisperFlow repository or
application data was read or changed.

## Phase 5.1.2 capture status

The following native captures were launched against the isolated fixture at
`/tmp/stormpad-phase512-fixture.K46iZF/Notes` and visually inspected on
2026-07-23. They are ephemeral verification artifacts, not committed public
assets.

| State | Inspected capture |
| --- | --- |
| Projects sidebar with Build selected and filtered notes | `/tmp/stormpad-phase512-projects-selected.png` |
| Existing selected paragraph converted to Heading 2 in place | `/tmp/stormpad-phase512-selection-heading.png` |
| Editor-wide title and body selection | `/tmp/stormpad-phase512-full-note-selection-1.png` |
| One Delete leaves a clean blank note | `/tmp/stormpad-phase512-delete-blank.png` |
| Visible `Clear` text-color command | `/tmp/stormpad-phase512-clear-text-color-2.png` |
| Visible `Clear / Transparent` highlight command | `/tmp/stormpad-phase512-transparent-highlight-2.png` |
| Native Create Project dialog | `/tmp/stormpad-phase512-create-project-dialog-2.png` |
| Move to Project menu with Build target | `/tmp/stormpad-phase512-move-to-project-menu-2.png` |
| Plus-only non-overlapping block gutter | `/tmp/stormpad-phase512-plus-only-gutter.png` |

The captures prove that Projects are visually distinct from Categories, project
selection filters the middle list, text selection converts in place, full-note
selection includes title and body, Delete leaves a coherent blank editor, color
reset actions have visible labels, and the gutter exposes only `+`. There is no
block drag handle, drop target, insertion indicator, or Move Up/Down UI.

## Phase 5.1.2 capture method and privacy boundary

The standard macOS screenshot helper required persistent Screen Recording
permission, which was not granted during the Phase 5.1.2 run. That verification therefore
used StormPad's development-only `STORMPAD_CAPTURE_PATH` hook. It caches PNGs
from this process's own `NSWindow` objects and cannot capture other apps, the
desktop, or personal note libraries. Transient menus and dialogs may be emitted
as a second numbered file because AppKit owns them as separate windows.

The main-window and menu/dialog images listed above were each opened and
visually inspected. A tiny field-editor artifact produced during one full-note
selection capture (`/tmp/stormpad-phase512-full-note-selection-2.png`) is not a
verification artifact and should not be used.

## Reproducible fixture pattern

Use a fresh temporary note root and a separate defaults suite:

```bash
export STORMPAD_DEMO_NOTES=/tmp/stormpad-phase512-fixture/Notes
export STORMPAD_DEFAULTS_SUITE=com.stormpad.StormPad.Phase512Fixture
mkdir -p "$STORMPAD_DEMO_NOTES"
```

Create notes and projects through `NoteStore`, then launch with both values on
every command. For example:

```bash
STORMPAD_NOTES_DIR="$STORMPAD_DEMO_NOTES" \
STORMPAD_DEFAULTS_SUITE="$STORMPAD_DEFAULTS_SUITE" \
STORMPAD_SELECT_PROJECT=Build \
STORMPAD_CAPTURE_PATH=/tmp/stormpad-phase512-projects-selected.png \
STORMPAD_CAPTURE_AND_QUIT=1 \
./.venv/bin/python -m stormpad
```

To exercise editor-wide selection or project surfaces, add one of:

```text
STORMPAD_SELECT_NOTE=<stable-note-id>
STORMPAD_SELECT_ALL_NOTE=1
STORMPAD_DELETE_ALL_NOTE=1
STORMPAD_CREATE_PROJECT_DIALOG=1
STORMPAD_SHOW_MOVE_PROJECT_MENU=1
STORMPAD_HOVER_BLOCK=<zero-based-index>
STORMPAD_SHOW_COLOR_MENU=text
STORMPAD_SHOW_COLOR_MENU=highlight
```

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
- `STORMPAD_SELECT_PROJECT`
- `STORMPAD_SELECT_NOTE`
- `STORMPAD_SELECT_ALL_NOTE`
- `STORMPAD_DELETE_ALL_NOTE`
- `STORMPAD_CREATE_PROJECT_DIALOG`
- `STORMPAD_SHOW_MOVE_PROJECT_MENU`
- `STORMPAD_SHOW_NOTE_INFO`
- `STORMPAD_SHOW_SETTINGS`
- `STORMPAD_SHOW_EXPORT`
- `STORMPAD_SHOW_SHARE_NOTE`
- `STORMPAD_SHARE_DELAY`
- `STORMPAD_SHOW_SHARE_PROJECT`
- `STORMPAD_SHOW_PROJECT_CONTEXT`
- `STORMPAD_DRAG_PROJECT`
- `STORMPAD_PROJECT_INSERTION_INDEX`
- `STORMPAD_DRAG_NOTE_OVER`
- `STORMPAD_COLLAPSE_NOTES`
- `STORMPAD_CAPTURE_PATH`
- `STORMPAD_CAPTURE_AND_QUIT`
- `python -m stormpad --smoke`
