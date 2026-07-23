# StormPad — handoff

Living continuation document for the native macOS StormPad project.

## Current status

Phase 5.1.1 interaction stabilization is complete on
`feature/notion-editor`. Phase 6 has **not** started.

- **Project:** `/Users/mattferre/web/APP/Stormpad`
- **Base:** `02c1513` (`main`, Phase 5)
- **Earlier Phase 5.1 commits:**
  - `c8f2e6c` — stable IDs and Markdown block foundation
  - `6825afe` — native clean block editor
  - `896b70f` — migration, storage, and review documentation
- **Phase 5.1.1 commits:**
  - `9cd7020` — `fix: stabilize native block editor interactions`
  - `84d9a30` — `feat: add note actions export settings and menus`
  - the documentation checkpoint follows these commits
- **Remote activity:** none; nothing was pushed or published
- **Packaging/signing/notarization/release:** not started

Do not package, sign, notarize, publish, push, create a release, or start the
landing page until the user completes the hands-on review and explicitly
requests Phase 6.

## Initial inspection and baseline

The repository was clean on `feature/notion-editor`. The reported three Phase
5.1 commits were present in the expected order. The initial test suite had 188
passing tests; Ruff, compile/import checks, all three theme objects,
`--self-check`, `--smoke`, and the baseline native launch were green.

Before production edits, `HANDOFF.md`, `README.md`, `PRD.md`,
`docs/architecture.md`, `docs/storage.md`, screenshot instructions, relevant
AppKit/storage/transcript/attachment/formatting code, and Phase 5.1 tests were
read completely.

### Root causes

- The body text column began at x=92 while the old `+` control occupied
  approximately x=86…114, making overlap geometrically inevitable.
- Gutter visibility and command routing followed the focused/caret block rather
  than the pointer-hovered block.
- The secondary control implemented Move Up/Move Down instead of native drag.
- Block menu actions inferred the current caret/event after the menu opened
  instead of retaining the hovered semantic index, so commands could target the
  wrong paragraph or appear inert.
- Empty structural Markdown such as `#`, `1.`, or `>` was not parsed back as
  its semantic block, so inserting an empty type degraded after reload.
- A paragraph beginning with supported StormPad `<u>`/semantic-color markup was
  classified as raw HTML, losing semantic inline runs after reload.
- Transcript insertion reused ordinary text-flow presentation instead of a
  dedicated protected native container.
- The contextual custom-view swatch grid triggered an AppKit/PyObjC drawing
  lifecycle exception. It was replaced with stable standard native menu items
  whose visible content is the semantic swatch icon.

## Phase 5.1.1 implementation

### Pointer-following block gutter

`GutterHoverView` tracks the pointer in a dedicated transparent gutter outside
the writing column. Pure helpers model text inset, gutter width, block rect,
scroll offset, hit region, and control rects.

- `+` and the unobtrusive drag target appear only beside the hovered block.
- Both end before the 92-point text inset with explicit clearance.
- They hide outside editable/insertable block regions and when the hover
  preference is off.
- Their canvas position accounts for the scroll view offset.
- The old Move Up/Move Down button/menu is gone.
- Accessibility labels are `Add Block` and `Drag Block`.

### Functional block commands

The retained native menu captures the hovered index and Option state. Each
command applies exactly once through the pure `apply_block_command` operation,
converts a compatible empty text block in place, otherwise inserts below
(above with Option), restores the caret/focus, registers undo, and enters the
normal autosave path.

Proven semantic types:

- Text
- Heading 1
- Heading 2
- Heading 3
- To-do
- Bulleted list
- Numbered list
- Quote
- Divider
- Link
- Image
- File
- Transcript

Parser/serializer tests cover empty and populated forms, insertion/conversion,
no duplicates, Markdown round trips, and relaunch storage. Leading underline
and color/highlight markup now remains a normal formatted paragraph.

### Native Transcript block

Transcript is a distinct protected multiline attributed container in the note
flow, not a bullet or ordinary prose block.

- Header with collapse/expand state.
- `No transcript yet` and `Append Test Transcript` empty state.
- Timestamped read-only rows when populated.
- Context actions for collapse/expand, test append, move/remove chunks,
  move/remove the block.
- Chunk operations participate in native undo.
- Chunks remain in `Note.transcript`, separate from editable body prose.
- Search includes transcript content.
- Removing the marker uses `Transcript-Block: hidden` and does not destroy
  existing transcript data.
- Ordinary notes stay transcript-free unless inserted or legacy content exists.
- Recording/live transcription/WisperFlow integration was not added.

### Native block drag reordering

`BlockDragButton` starts an AppKit dragging session with a private pasteboard
type. The editor is a native move destination, calculates an insertion boundary,
and renders a semantic-theme insertion line. The title is outside the drag
source/destination model and cannot be moved into the body.

`reorder_blocks` preserves the complete payload: type, text, inline marks,
to-do checked state, indent, target/alt attachment references, raw payload, and
Transcript state. The native action path is undoable, autosaves, and survives
reload.

### Collapsed Notes tab

The expanded header has a left-facing collapse arrow. The narrow 46-point tab
has a right-facing expand arrow near the top at the corresponding header
height. It no longer centers vertically or covers editor content. Preference
and split-width persistence remain intact. Accessibility labels are
`Collapse Notes` and `Expand Notes`.

### Filename and Note Info

The writing canvas remains free of a permanent filename pill. The upper-right
`Open Note Info` control opens a native menu with filename, current full path,
created/updated dates, category, word count, Rename, Export, Reveal, Open,
Settings, and Delete actions.

Title commits remain the primary lowercase safe kebab naming flow. Explicit
manual rename sanitizes input, preserves `.md`, resolves collisions, does not
change the stable UUID or attachment directory, and stores
`Filename-Mode: manual` so a later title save does not silently overwrite it.
Rename failure restores the previous file/path/mode.

### Plain-text export

File and Note Info expose `Export as TXT…` through one native `NSSavePanel`.
`exporter.py` atomically writes a separate UTF-8 file containing title,
readable headings/body/lists/to-dos/quotes/links/image alt/file names, and
timestamped transcript chunks.

It excludes the Markdown metadata envelope, stable UUID, filename/transcript UI
state, StormPad color and underline markup, attachment directory internals, and
other serialization details. Export never modifies the note or Markdown file.

### Formatting swatches

The contextual text/highlight menus show nine icon-only semantic swatches:
Default, Gray, Blue, Cyan, Green, Yellow, Orange, Red, and Purple. The selected
swatch has a strong semantic outline and native checkmark; Default has a reset
slash. Color names remain available through tooltips/accessibility labels.

No unrestricted color picker was added. Bold, italic, underline, link,
Cmd+B/I/U/K, allow-list validation, relaunch persistence, and theme-aware
semantic rendering remain intact.

### Native menus and Settings

The menu bar now contains complete StormPad, File, Edit, Note, Format, View,
Window, Help, and Development menus. Validation reflects note selection,
current block type, inline selection/formatting, current theme, and Notes-panel
state.

One reusable `StormPad Settings` window is available from Cmd+, and Note Info.
It provides:

- Appearance: immediate persisted Storm Blue, Light, or Deep Dark.
- Editor: persisted `Show block controls on hover`; native menus remain the
  insertion alternative.
- Storage: StormPad root, Notes, and Attachments paths plus explicit Reveal
  actions for each.

There are no accounts, sync, telemetry, analytics, AI, or WisperFlow settings.

## Files changed in Phase 5.1.1

New:

- `scripts/native_interaction_smoke.py`
- `stormpad/exporter.py`
- `stormpad/views/settings.py`
- `tests/test_exporter.py`

Updated:

- `HANDOFF.md`
- `README.md`
- `docs/architecture.md`
- `docs/screenshots/README.md`
- `docs/storage.md`
- `stormpad/app.py`
- `stormpad/block_parser.py`
- `stormpad/blocks.py`
- `stormpad/models.py`
- `stormpad/preferences.py`
- `stormpad/session.py`
- `stormpad/storage.py`
- `stormpad/uihelpers.py`
- `stormpad/views/block_editor.py`
- `stormpad/views/note_list.py`
- `stormpad/window.py`
- `tests/test_attachments.py`
- `tests/test_blocks.py`
- `tests/test_models.py`
- `tests/test_preferences.py`
- `tests/test_session.py`
- `tests/test_storage.py`
- `tests/test_uihelpers.py`

## Final automated verification

```text
./scripts/test.sh -q
233 passed

./.venv/bin/ruff check .
All checks passed!

python -m compileall -q stormpad scripts tests
passed

headless imports
passed

AppKit imports
passed

all three theme objects
passed

python -m stormpad --self-check
StormPad 0.1.0 self-check OK

isolated python -m stormpad --smoke
SMOKE OK

python scripts/native_interaction_smoke.py
NATIVE INTERACTION SMOKE OK: menus, swatches, settings, insert, drag,
transcript, undo, redo, autosave, reload
```

The 233 tests cover gutter geometry/hit/scroll state; all block commands and
round trips; full-payload reorder; Transcript absent/empty/legacy/append/
collapse/search/export behavior; filename sanitization/collision/failure and
attachment stability; deterministic TXT output; preferences; menu/UI helpers;
autosave stale-selection safety; and themes.

## Manual and visual verification

Completed with temporary sanitized note libraries and isolated
`NSUserDefaults` suites:

- native launch, self-check, and UI construction without final tracebacks;
- pre-edit default-library smoke loaded the existing notes read-only;
- dedicated gutter, headings/lists, populated and empty Transcript;
- complete native block menu;
- native insertion indicator;
- contextual swatches after repairing the custom-menu crash;
- Note Info and native TXT save panel;
- expanded Light-theme Settings with all paths/actions;
- collapsed Notes tab near the top;
- Storm Blue, Light, and Deep Dark editor surfaces;
- generated `/tmp/stormpad-phase511-export.txt` manually inspected for readable
  content/timestamps and absence of metadata/internal markup.

The native interaction driver exercised actual AppKit action methods for menu
construction/validation, inline formatting/swatches, block insert, drag drop,
Transcript append/move/remove, undo/redo, autosave, and reload.

### Screenshot locations

- `/tmp/stormpad-phase511-gutter-headings-lists.png`
- `/tmp/stormpad-phase511-block-menu.png`
- `/tmp/stormpad-phase511-drag-insertion.png`
- `/tmp/stormpad-phase511-transcript-empty.png`
- `/tmp/stormpad-phase511-color-swatches.png`
- `/tmp/stormpad-phase511-note-info.png`
- `/tmp/stormpad-phase511-txt-export-panel.png`
- `/tmp/stormpad-phase511-settings-appearance.png`
- `/tmp/stormpad-phase511-collapsed-notes.png`
- `/tmp/stormpad-phase511-theme-light.png`
- `/tmp/stormpad-phase511-theme-deep-dark.png`

See `docs/screenshots/README.md` for fixture/hook commands.

## Known limitations and hands-on review boundary

- Edge auto-scroll during a drag is not implemented. Ordinary vertical native
  dragging/reordering is implemented.
- The AppKit drag source/drop destination and insertion indicator were
  exercised programmatically and visually, but a freehand physical mouse drag
  of every practical block type still needs user review.
- Deterministic hover rendering and pure pointer/scroll geometry were tested and
  inspected; freehand pointer-leave and a long-note scroll should still be
  confirmed by the user.
- Open/Reveal routes, speech selectors, Copy Note, and Delete-to-Trash
  preservation remain wired and covered by existing tests, but final Finder,
  audible speech, and destructive Trash interactions were intentionally not
  invoked during the sanitized screenshot pass.
- Theme/collapse/hover preferences are tested for persistence. Final hands-on
  Cmd+, quit/relaunch, and physical collapsed-panel relaunch remain recommended.
- Search results are correct, including Transcript text, but per-match in-row
  highlighting remains deferred.
- Speech still uses the system voice and has no voice/rate picker.

## Exact recommended hands-on retest

Use a disposable temporary `STORMPAD_NOTES_DIR` and isolated
`STORMPAD_DEFAULTS_SUITE`:

1. Launch, confirm the existing/disposable library loads, and open a long note.
2. Hover an empty block, paragraph, heading, and list; confirm `+`/drag controls
   follow the pointer, never overlap text, disappear on leave, and stay aligned
   after scrolling.
3. Insert all 13 block types; verify empty conversion, below insertion, Option
   insertion above, caret focus, undo/redo, and one block per click.
4. Quit/relaunch and verify type/order/format persistence.
5. Insert an empty Transcript, append twice, search its text, collapse/expand,
   move/remove a chunk, undo, hide/remove the block, and verify data survives.
6. Physically drag text, heading, list, checked to-do, link, image, file, and
   Transcript blocks; verify insertion line, undo, relaunch order, and stable
   attachment references.
7. Open Note Info; compare filename/path to Finder. Perform a disposable manual
   rename, change the title, and verify the manual filename and UUID remain.
8. Export TXT from File and Note Info; inspect title, all blocks, link targets,
   attachment names, and transcript timestamps; confirm no metadata/UUID/
   StormPad markup/path internals and no Markdown modification.
9. Select text; test Cmd+B/I/U/K, text and highlight swatches, Default reset,
   selected outlines, undo, and relaunch.
10. Open Settings with Cmd+, switch all themes, toggle hover controls, use all
    three Reveal actions, close/reopen Settings, quit/relaunch, and verify
    persistence without duplicate windows.
11. Collapse Notes, verify the arrow remains near the top, resize, quit/relaunch,
    expand, and confirm the editor was never covered.
12. Verify search, Copy Note, Open File, Reveal, Speak/Stop, and Delete to Trash
    on disposable data while watching the console for tracebacks.

If this review passes, approve Phase 5.1.1 and only then request Phase 6.

## Guardrails

- Keep Markdown and local managed files as the source of truth.
- Do not mass-rewrite notes merely by opening them.
- Do not touch `/Users/mattferre/web/APP/wisperflow_`.
- Do not add cloud, accounts, analytics, telemetry, AI, recording, or
  speculative scope.
- Do not alter the official logo source.
- Do not push, create a remote, package, sign, notarize, publish, or release
  without an explicit next-phase request.

WisperFlow was untouched. No file under
`/Users/mattferre/web/APP/wisperflow_` was read, modified, moved, or copied.
