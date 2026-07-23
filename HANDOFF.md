# StormPad — handoff

Living continuation document for the native macOS StormPad project.

## Hard Phase 6 delivery requirements

Phase 6 has **not** started. After Phase 5.1 is manually reviewed, final
delivery still requires:

- a standalone, double-clickable `StormPad.app`;
- the official `assets/Stormpad_logo.png` converted into a correct `.icns`;
- correct bundle name, identifier, version, and `Info.plist`;
- self-contained dependencies with no source-folder or development-`.venv`
  dependency;
- reproducible build/install scripts;
- installation and testing from `/Applications/StormPad.app`;
- a drag-to-Applications `StormPad.dmg`;
- later, a GitHub Release asset and mattferre.com showcase/download link.

Do not package, sign, notarize, publish, push, create a release, or build the
landing page before the Phase 5.1 review is complete and the user requests
Phase 6.

## Repository state

- **Project:** `/Users/mattferre/web/APP/Stormpad`
- **Branch:** `feature/notion-editor`
- **Base:** `02c1513` (`main`, Phase 5)
- **Phase 5.1 implementation commits:**
  - `c8f2e6c` — `Phase 5.1: add stable IDs and Markdown block foundation`
  - `6825afe` — `Phase 5.1: build native clean block editor`
  - the current documentation/handoff checkpoint follows those commits
- **Expected working tree at handoff:** clean
- **Remote activity:** none; nothing was pushed or published
- **Packaging status:** not started

Initial inspection confirmed the expected Phase 1–5 history
(`fae719f` → `b20ff31` → `498e8ff` → `eeacc97` → `02c1513`) and a clean
`main`. The verified baseline was 134 tests, Ruff clean, compile/import checks
clean, `--smoke` successful with display permission, and a real isolated native
launch.

## Phase 5.1 result

The dashboard-like editor was replaced with a calm page-style native block
editor while preserving local Markdown, autosave, search, categories, actions,
speech, and all three themes.

### Architecture

The body is one rich native `NSTextView`. Paragraph attributes carry block
semantics; attributed runs carry inline semantics. The title is a native
`NSTextField` styled and keyboard-connected as the visual first block. This is
AppKit-only: no web view, HTML contenteditable, browser JavaScript, React, or
Electron.

Pure modules keep the model testable:

- `blocks.py` — block/inline types and structural operations;
- `block_parser.py` / `block_serializer.py` — safe deterministic Markdown;
- `attachments.py` — managed local copies and orphan policy;
- `storage.py` — note envelope, identity migration, atomic write and filename
  commit;
- `session.py` — stable-ID CRUD, transcript seam, note+attachment deletion.

The active paragraph is the block selection and the standard `NSTextView` range
is the inline selection. Native typing undo remains intact. Structural and
formatting operations register attributed-string snapshots with the same undo
manager.

See `docs/architecture.md` and `docs/storage.md`.

### Selected note and collapsible list

The selected row uses a themed filled background, border, stronger title,
left-side accent indicator, and restrained Storm Blue glow. Regular table
selection keeps it visible while the editor has focus. Light uses soft
gray-blue; Deep Dark uses quiet zinc.

The middle note-list panel collapses to a 46-point vertical native tab and the
editor receives the freed width. Collapse state is stored by `Preferences`,
survives relaunch, and is reapplied after theme rebuilds.

### Clean new-note and writing canvas

- No filename, word count, Created/Updated row, permanent “Saved locally” pill,
  transcript card, or heavy editor border occupies the normal canvas.
- Saving/Saved is a subtle transient top-right message; failures remain visible.
- Metadata is available through Note ▸ Note Info, Open File, and Reveal in
  Finder.
- Native scroll views use autohiding overlay indicators.
- A pristine note displays only the unsaved `Untitled` title placeholder.
- Command-N focuses the title. Return enters the first text block; Up from the
  first body position returns to the title.

### Stable IDs and filenames

New notes receive one UUID stored as `ID: <uuid>`. Identity and persisted
selection no longer depend on the path. Legacy files without `ID` receive a
deterministic UUIDv5 in memory and retain their old stem as a temporary lookup
alias. Merely opening them does not rewrite, rename, or schedule an autosave;
the next actual edit persists the ID.

A safe title commit first atomically writes the current file, then moves it to
a collision-free lowercase Unicode-friendly kebab name. Empty/unsafe titles
fall back to `untitled-note.md`; collisions append `-2`, `-3`, and so on. The
model path changes only after the move succeeds. A failed move leaves the
newly saved old file and its in-memory path intact.

### Blocks and keyboard behavior

Implemented blocks:

- Text
- Heading 1, Heading 2, Heading 3
- To-do
- Bulleted list
- Numbered list
- Quote
- Divider
- Link
- Image
- File
- Transcript

`+` opens a native insertion menu. It converts the current empty paragraph,
inserts below by default, and supports Option-insert-above. The handle exposes
undoable Move Up / Move Down. Return continues compatible blocks, empty lists
and to-dos exit to Text, Backspace converts an empty non-text block, and
Tab/Shift-Tab changes supported-list indentation. Cocoa ranges account for
UTF-16 so emoji/non-BMP text does not shift later block boundaries.

### Inline formatting

Bold, italic, underline, link, curated text color, and curated highlight are
implemented as semantic attributed runs. Commands B/I/U/K route through native
menus. A contextual native toolbar appears for a non-empty selection and hides
when selection/focus collapses.

The stored palette is `default`, `gray`, `blue`, `cyan`, `green`, `yellow`,
`orange`, `red`, and `purple`. Theme changes rerender tokens but do not mutate
Markdown.

### Markdown

Standard Markdown is used for headings, emphasis, lists, to-dos, quote,
divider, link, image, and file. Underline uses `<u>`. Curated colors use
allow-listed `data-stormpad-color` / `data-stormpad-highlight` spans. Transcript
placement/collapse uses a StormPad HTML comment. Markdown/HTML is never
executed; output is escaped and unsafe color tokens are rejected.

Unknown metadata is preserved. Existing Phase 1–5 title/Notes/Transcript files
continue to load without an open-time rewrite.

### Attachments

Managed copies live at:

```text
~/Documents/StormPad/Attachments/<stable-note-id>/
```

Imports are copied atomically, names are sanitized/collision-safe, and Markdown
stores relative links from `Notes/`. Title/file rename therefore cannot break
an attachment. Native images are aspect-constrained previews. File blocks show
an icon, filename, type, and size; double-click opens through `NSWorkspace`.
Context actions reveal or remove the block.

Removing a block records an orphan candidate in `.orphans.json` and does not
risk deleting the managed file. Delete stages the note and its attachment
directory together before the configured Trash strategy; failures roll back.

### Transcript

Transcript chunks remain separate `Note.transcript` data. Ordinary blank notes,
including Sessions, have no transcript block. Existing chunks, explicit block
insertion, or Development ▸ Append Test Transcript make it appear. The editor
renders timestamps/chunks as protected read-only content and persists
collapsed/expanded state.

No recording, live transcription, audio capture, or WisperFlow integration was
implemented.

### Autosave, actions, themes, accessibility

All editor mutations reuse the existing 0.4-second debounce. Note switch,
close, and quit flush pending work; stale callbacks cannot write into a newly
selected note. Theme switching flushes, rebuilds, then restores stable
selection/focus without mutating content.

Copy Note, Open File, Reveal in Finder, Delete to Trash, Speak/Stop, search, and
categories remain available through native menus/context actions. The primary
toolbar now contains only collapse/expand, Note Info, and New Note. Append Test
Transcript moved to Development.

New controls have labels/tooltips and comfortable targets. Theme tokens cover
the gutter, formatting controls, selection, transcript, attachments, quote,
divider, title placeholder, and collapsed tab across Storm Blue, Light, and
Deep Dark.

## Files changed in Phase 5.1

New:

- `stormpad/blocks.py`
- `stormpad/block_parser.py`
- `stormpad/block_serializer.py`
- `stormpad/attachments.py`
- `stormpad/views/block_editor.py`
- `tests/test_blocks.py`
- `tests/test_attachments.py`
- `docs/storage.md`

Updated:

- `stormpad/app.py`
- `stormpad/errors.py`
- `stormpad/models.py`
- `stormpad/paths.py`
- `stormpad/preferences.py`
- `stormpad/session.py`
- `stormpad/storage.py`
- `stormpad/theme.py`
- `stormpad/uihelpers.py`
- `stormpad/views/editor.py`
- `stormpad/views/note_list.py`
- `stormpad/window.py`
- `tests/test_preferences.py`
- `tests/test_session.py`
- `tests/test_storage.py`
- `tests/test_uihelpers.py`
- `README.md`
- `PRD.md`
- `docs/architecture.md`
- `docs/screenshots/README.md`
- `HANDOFF.md`

## Automated verification

Final available checks:

```text
./scripts/test.sh
188 passed

./.venv/bin/ruff check .
All checks passed

python -m compileall -q stormpad tests
passed

headless imports
passed

all three theme objects
passed

AppKit module imports
passed

python -m stormpad --self-check
StormPad 0.1.0 self-check OK
```

Tests cover stable ID creation/migration, legacy aliases, filenames and
collisions/failure rollback, all blocks and inline formats, unsafe color/HTML
handling, attachments and rename stability, transcript visibility/collapse,
preferences, selected-row/title/block-menu/formatting UI helpers, autosave
stale-selection safety, and all theme token sets.

## Manual/visual verification

Completed against isolated temporary notes:

- baseline native app launch and `--smoke`;
- populated Phase 5.1 native launch with no console traceback;
- visibly strong selected note while the body held focus;
- clean canvas with heading, bold/underline/color, to-dos, quote, divider, and
  managed image preview;
- attachment copy remained managed rather than source-path dependent;
- a crash caused by an invalid custom selection rect was diagnosed from the
  macOS crash report and fixed; the subsequent app remained stable.

Inspected sanitized screenshot:

```text
/var/folders/z4/lznm_6tn1l3dc4sf7wm25d100000gn/T/codex-shot-2026-07-23_19-54-43.png
```

The final layout-offset change for the active-block gutter was made after the
last successful capture. A subsequent native relaunch request was blocked by
the execution environment's approval/usage limit, so that last adjustment and
the remaining screenshot matrix were **not** visually re-verified. Do not claim
otherwise.

## Known limitations / review items

- Block reordering uses the documented Move Up / Move Down menu fallback, not
  true drag-and-drop.
- The gutter follows the active block while the body is focused; proximity-only
  pointer hover is not implemented.
- The compact file presentation is an attributed native line rather than a
  separate rounded card view.
- Attributed to-do and transcript content is keyboard/screen-reader ordered,
  but the to-do glyph is not a separate native accessibility element.
- Search results are correct but per-match in-row highlighting remains deferred.
- The final gutter scroll/coordinate adjustment, blank-note screen, collapsed
  relaunch, contextual formatting toolbar, block menu, transcript collapse,
  and Light/Deep Dark Phase 5.1 screens still require hands-on visual review.
- Speech uses the system voice and has no voice/rate picker.
- If a file is deleted externally while unsaved edits are active, autosave
  recreates it rather than discarding the user's edits.

## Exact next task

**Do not start Phase 6 yet.** First run the remaining Phase 5.1 manual review
against a fresh temporary `STORMPAD_NOTES_DIR`:

1. verify the final gutter position at the first block and after scrolling;
2. create a blank note, title/body transition, commit/rename it twice, and
   relaunch to confirm stable selection;
3. collapse/relaunch/expand the note-list panel;
4. insert/reorder every block and exercise every inline format/shortcut;
5. import image/file, delete the original source, Open/Reveal, and verify Trash
   bundling on a disposable note;
6. insert/append/collapse Transcript and verify normal notes remain clean;
7. switch and inspect all three themes;
8. verify Copy Note, Speak Selection, pending-edit quit, and an empty console;
9. capture/inspect the sanitized screenshot matrix in
   `docs/screenshots/README.md`.

If that review passes, approve Phase 5.1 and only then begin Phase 6 using the
hard delivery requirements at the top.

## Development hooks

- `STORMPAD_NOTES_DIR` — isolated notes directory
- `STORMPAD_INITIAL_QUERY` — launch into search
- `STORMPAD_THEME` — force initial development theme
- `STORMPAD_FOCUS_EDITOR` — focus body after launch
- `STORMPAD_EDITOR_SELECTION=location,length` — deterministic selection
- `STORMPAD_SHOW_BLOCK_MENU=1` — open the insertion menu for capture
- `python -m stormpad --smoke` — build the real UI without event loop

## Guardrails

- Do not touch `/Users/mattferre/web/APP/wisperflow_`.
- Do not add cloud, AI, accounts, telemetry, or speculative scope.
- Do not alter the official logo source.
- Keep Markdown and local managed files as the source of truth.
- Do not push, create a remote, package, publish, or release without an explicit
  next-phase request.

## WisperFlow statement

WisperFlow was untouched. No file under
`/Users/mattferre/web/APP/wisperflow_` was read, modified, moved, or copied.
