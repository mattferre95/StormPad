# StormPad — handoff

Living continuation document for the native macOS StormPad project.

## Current status

Phase 5.1.5 (motion, Project icons, bottom-left profile menu, Notes `+`) is
complete locally on `feature/notion-editor`. Phase 6 has **not** started.

- **Project:** `/Users/mattferre/web/APP/Stormpad`
- **Phase 5.1.5 starting point:** `7c7f6b2`
  (`feat: colour palette, block-edit control, project tags and inline rename`)
- **Remote activity:** none; nothing was pushed or published
- **Packaging/signing/notarization/release:** not started
- **WisperFlow:** untouched

## Phase 5.1.5 motion, Project icons, and the local profile menu

Animation is decided in exactly one place. `stormpad/motion.py` is a pure policy
(five transition kinds, one duration table, one reduced table, plus an
interruption token); `stormpad/views/motion.py` is the only module that reads
macOS Reduce Motion and the only one that drives `NSAnimationContext`. No view
holds a timing literal, and a duration of `0` runs the identical code path
synchronously — so Reduce Motion, the initial build, and `--smoke` all land in
the final state immediately.

- The notes panel animates its divider with the editor column following in the
  same group. Thickness clamps are relaxed for the journey and rewritten
  verbatim on completion from `notes_panel_geometry`, so interrupted and rapid
  repeated toggles still end at the exact final widths and stay resizable.
- Selecting a sidebar row no longer tears down and rebuilds every row. The
  navigation tree rebuilds only when the projects, their icons, or the collapsed
  state actually change; otherwise counts and the selected surface update in
  place, which is what removed the abrupt selection flash.
- Projects carry an optional `icon` (`symbol:<curated name>` or `emoji:<glyph>`)
  in their existing metadata JSON. It is presentation only — identity, folder,
  name, notes, order, and rename are all unaffected — and any unknown value
  normalises back to the default folder.
- The bottom-left row shows the macOS display name (falling back to
  `StormPad User`) over `Local workspace`, and opens a native menu built from a
  declarative spec whose Appearance items reuse the View menu's `selectTheme:`.
- The Notes header `+` calls the same `newNote_` as Cmd+N, File → New Note, and
  New Note in Project, so no creation path can drift.

## Phase 5.1.4 critical regression repair

The user-approved Share Note path remains unchanged. The repair is limited to
Return handling, sidebar hit-testing, and the reusable main-window lifecycle.

- Return now performs the native selection replacement first, then derives any
  block continuation from the post-edit `NSTextStorage`. It no longer rebuilds
  from a pre-Return semantic snapshot that can omit marked or just-typed text.
  The structural operation has one safe undo/redo snapshot.
- Project, Unfiled, All Notes, and category rows now convert AppKit's
  superview-space `hitTest:` point into row-local coordinates. The navigation
  document fills a tall `NSClipView`, so visible rows and their actual
  hit-test/drag surfaces coincide.
- The controller-owned `NSWindow` is not released on close. Because StormPad
  remains running after its last window closes, Dock reopen can show that same
  valid window.
- The native smoke sends real `NSEvent` key-downs through the title field
  editor and body first responder. It covers title Return, rapid/pending-save
  Return, repeated Return, selection replacement, inline formatting, accented
  Unicode/emoji, list continuation/exit, undo/redo, save/reload, row
  hit-testing, and closing/reopening the same window.

The clean verification remains 273 tests plus Ruff, compileall, imports, three
themes, self-check, isolated smoke, and expanded native interaction smoke. A
sanitized inspected fixture is in `docs/screenshots/phase-5-1-4/`.

Do not package, sign, notarize, publish, push, create a release, or start Phase 6
until the user completes the hands-on review and explicitly approves it.

## Phase 5.1.3 inspection and baseline

The worktree was clean on `feature/notion-editor` at `e298315`; expected
ancestors `ae51ce1` and `07c3cc4` were present. Before production edits, the
existing direct project click behavior and absence of note/project drag
pasteboard writers were reproduced with disposable AppKit introspection.

The requested baseline passed: 258 tests, Ruff, compileall, headless imports,
AppKit imports, all three themes, self-check, isolated native smoke, and native
interaction smoke.

## Phase 5.1.3 implementation

### Native note and project sharing

- A compact native share-symbol button sits in the top-right editor header
  beside Note Info and is visible/enabled with a selected note. Tooltip and
  accessibility label are both “Share Note”.
- The button, File ▸ Share Note…, Note ▸ Share Note…, Note Info, and the note
  context menu share one action. It flushes autosave, reloads the stable-ID
  note, generates a readable collision-safe TXT outside Notes, and passes its
  file URL to `NSSharingServicePicker`.
- Project context menus add Share Project…. A sanitized, atomic,
  collision-safe ZIP contains README.txt, Markdown/TXT note copies, and only
  referenced attachments with rewritten links.
- UUID/project metadata, `.stormpad-project.json`, preferences, caches,
  orphaned attachments, hidden UI state, and local absolute paths are excluded.
  Original notes/projects are unchanged.
- StormPad never selects a service, recipient, upload, or public link. Recent
  exports stay available to the chosen service; only manager-owned artifacts
  older than 24 hours are removed on launch/quit.

### Direct project-row ordering

- The full normal row surface—folder, name, count, and empty background—is the
  drag source. There is no handle or permanent drag indicator.
- A five-point threshold preserves ordinary selection clicks. During drag the
  row lifts subtly, a themed insertion line follows valid project positions,
  accessibility announcements describe the position, and near-edge
  autoscrolling is attempted.
- Private UUID-only pasteboard payloads are validated. Projects remain flat:
  dropping on another project means reorder, never nesting. All Notes,
  Unfiled, headers, Categories, and external applications reject project
  movement.
- Custom UUID order persists in Preferences without renaming/moving project
  folders, survives relaunch, and participates in native undo/redo. Context
  menus expose Move Project Up/Down as keyboard-accessible alternatives.

### Note dragging between Projects and Unfiled

- Native note-list rows are whole-row drag sources with no drag icon.
- Project and Unfiled rows accept validated private note UUID payloads; All
  Notes and unrelated sidebar regions reject them.
- Before movement, pending edits flush and current note/project UUIDs are
  resolved through the model. The collision-safe filesystem move succeeds
  before selection, search, counts, visible lists, and preferences refresh.
- Stable note UUID, attachment directory, content, and title are preserved.
  Managed attachment links retarget for the new note depth. Same-project drops
  are no-ops; failed moves preserve the prior valid source. Undo returns the
  note to its previous Project or Unfiled and redo reapplies the move.

### Verification evidence

- The expanded headless suite passes 273 tests.
- Ruff, compileall, headless/AppKit imports, all themes, self-check, native
  smoke, and the expanded native interaction smoke pass.
- The native smoke creates Build, StormPad, and WisperFlow only inside a
  temporary library; reorders Build, relaunches, moves a note
  Unfiled → StormPad → Build → Unfiled, checks stable UUID/attachments and
  undo/redo, prepares note/project shares, and inspects TXT/ZIP contents.
- Sanitized, visually inspected screenshots live in
  `docs/screenshots/phase-5-1-3/`, including the real native Share picker and
  drop feedback in Storm Blue, Light, and Deep Dark.

External Finder drag-to-export is deliberately deferred: an external project
drag returns no operation, so the managed project folder can never be moved out
of the library. Block dragging remains absent. Transcript polish remains
deferred.

## Phase 5.1.2 historical inspection and reproduction

The repository was clean on `feature/notion-editor`. The Phase 5.1.1 baseline
had 233 passing tests; Ruff, compile/import checks, all three theme objects,
`--self-check`, isolated `--smoke`, and the native interaction smoke were green.

Two native regressions were reproduced before production edits:

- Selecting `Alpha` and choosing Heading 1 produced three blocks:
  `Text("Alpha")`, an empty Heading 1, and `Text("Beta")`.
- Cmd+A in the body selected only the body range while the title remained
  outside the selection.

The cause was command routing that retained a hovered/caret block index without
retaining the real body selection, plus a title implemented as a separate
AppKit field with no editor-wide selection coordinator.

## Phase 5.1.2 implementation

### Selection-aware block conversion

The real `NSTextView` selection now wins over hover state for paragraph-level
block commands.

- Text, Heading 1–3, To-do, Bulleted list, Numbered list, and Quote convert the
  intersecting paragraph or paragraphs in place.
- Exact attributed text and inline runs are preserved.
- Conversion never inserts a duplicate or blank block.
- The selection is restored after conversion.
- One command creates one native undo step and enters the normal autosave path.
- A collapsed selection retains the existing empty-block conversion / insert
  below behavior; Option still inserts above.
- The gutter exposes only `+`. No secondary block control is shown.

### Editor-wide Cmd+A and Delete

Cmd+A in the title or body selects the visual note content: title plus the full
body. The body uses its real full range and the title shows a native selection
background.

One Delete/Backspace after that selection:

- clears the saved title and leaves the visual `Untitled` placeholder;
- replaces the body with one clean empty Text block;
- clears Transcript UI state;
- preserves managed attachment files and stable attachment UUID directories;
- registers one undo snapshot covering title, attributed body, selection, and
  Transcript state;
- participates in redo, autosave, and reload.

Ordinary partial selection/deletion remains native, including selections that
cross paragraph boundaries.

### Clear formatting

Text Color and Highlight menus now include visible reset labels:

- `Clear` removes semantic text-color markup and restores the active theme's
  semantic foreground.
- `Clear / Transparent` removes semantic highlight markup and native
  background color.
- Mixed selections report a mixed state instead of pretending one token owns
  the whole selection.
- Clearing is undoable/redoable and removed marks do not serialize as empty
  StormPad spans.

### Filesystem-backed Projects

Projects are real local folders:

```text
Notes/
├── <unfiled-note>.md
└── Projects/
    └── <project-slug>/
        ├── .stormpad-project.json
        └── <filed-note>.md
```

Each project has a stable UUID in its hidden JSON metadata record. Filed notes
remain ordinary Markdown and store a known `Project-ID` metadata key. Root-level
legacy notes remain visible as Unfiled; recursive scanning ignores project
metadata files and preserves unknown note metadata.

Implemented storage/session behavior:

- create a project with sanitized, collision-safe folder naming;
- rename a project while preserving project and note UUIDs;
- create a note directly inside a project;
- move a note into a project or back to Unfiled with collision-safe filenames;
- preserve stable note UUIDs and managed attachment files during moves;
- retarget managed relative attachment references for the note's new depth;
- delete an empty project through the injected Trash/delete strategy;
- refuse direct deletion of a populated project unless notes are explicitly
  moved to Unfiled first.

The sidebar now contains Library (`All Notes`, `Unfiled`), a collapsible
Projects section with folder icons and live counts, then Categories. Selecting a
project filters the middle list. Project context actions provide New Note,
Rename, Reveal, and Delete. Note and Note Info menus provide Move to Project and
Remove from Project.

The populated-project delete dialog defaults to preserving notes by moving them
to Unfiled; there is no delete-notes default.

### Transcript boundary

Transcript remains separate from editable body prose and participates in the
full-note clear snapshot. Exposed Move Up/Move Down controls were removed.
Further Transcript polish is explicitly deferred beyond Phase 5.1.2.
Recording, live transcription, and WisperFlow integration were not added.

## Files changed in Phase 5.1.2

New:

- `tests/test_projects.py`

Updated:

- `HANDOFF.md`
- `README.md`
- `docs/architecture.md`
- `docs/screenshots/README.md`
- `docs/storage.md`
- `scripts/native_interaction_smoke.py`
- `stormpad/app.py`
- `stormpad/blocks.py`
- `stormpad/errors.py`
- `stormpad/models.py`
- `stormpad/preferences.py`
- `stormpad/search.py`
- `stormpad/session.py`
- `stormpad/storage.py`
- `stormpad/uihelpers.py`
- `stormpad/views/block_editor.py`
- `stormpad/views/note_list.py`
- `stormpad/views/settings.py`
- `stormpad/views/sidebar.py`
- `stormpad/window.py`
- `tests/test_blocks.py`
- `tests/test_preferences.py`
- `tests/test_search.py`
- `tests/test_uihelpers.py`

## Automated verification

The final suite contains 258 tests:

```text
./scripts/test.sh -q
258 passed

./.venv/bin/ruff check .
All checks passed!

./.venv/bin/python -m compileall -q stormpad scripts tests
passed

headless imports
passed

AppKit imports
passed

all three theme objects
passed

./.venv/bin/python -m stormpad --self-check
StormPad 0.1.0 self-check OK

isolated ./.venv/bin/python -m stormpad --smoke
SMOKE OK

./.venv/bin/python scripts/native_interaction_smoke.py
NATIVE INTERACTION SMOKE OK: menus, swatches, settings, selection conversion,
full-note delete, projects, transcript, undo, redo, autosave, reload
```

Coverage includes single- and multi-paragraph conversion, exact inline-run
preservation, no duplicate blocks, UTF-16 selection mapping, partial
multi-paragraph deletion, full-note clear/undo/redo/autosave/reload, mixed and
clear colors, project metadata/folder lifecycle, filtering, safe moves,
collision policy, legacy visibility, attachment-reference retargeting, and
populated-project deletion safety.

## Manual and visual verification

Native interaction smoke exercised actual AppKit actions against a disposable
library. Separate sanitized native windows were captured and visually inspected
for:

- Projects sidebar, selected project, counts, and filtered note list;
- selected text converted to Heading 2 in place;
- visual title-plus-body full-note selection;
- clean blank editor after one Delete;
- visible `Clear` and `Clear / Transparent` color-menu actions;
- Create Project dialog and Move to Project menu;
- plus-only gutter outside the text column.

The standard macOS screenshot helper could not be used without persistent
Screen Recording permission. The safer fallback was StormPad's development-only
AppKit capture hook, which renders only this process's own windows. No personal
library or other application was captured.

Ephemeral inspected files:

- `/tmp/stormpad-phase512-projects-selected.png`
- `/tmp/stormpad-phase512-selection-heading.png`
- `/tmp/stormpad-phase512-full-note-selection-1.png`
- `/tmp/stormpad-phase512-delete-blank.png`
- `/tmp/stormpad-phase512-clear-text-color-2.png`
- `/tmp/stormpad-phase512-transparent-highlight-2.png`
- `/tmp/stormpad-phase512-create-project-dialog-2.png`
- `/tmp/stormpad-phase512-move-to-project-menu-2.png`
- `/tmp/stormpad-phase512-plus-only-gutter.png`

See `docs/screenshots/README.md` for the privacy boundary, fixture pattern, and
deterministic hooks.

## Known limitations and review boundary

- App-owned cached-window capture can render a transient field-editor helper or
  omit decorative text from a native alert. The relevant main/menu/dialog
  windows were inspected; this is a capture limitation, not a storage failure.
- Finder Reveal and final Trash behavior remain wired and headlessly covered,
  but destructive physical Trash interaction was intentionally not invoked
  during the sanitized pass.
- The project model is one level under `Notes/Projects/`; nested project
  hierarchies are not part of Phase 5.1.3.
- External project dragging to Finder as a promised ZIP is deferred. Internal
  reordering is the only accepted project drag operation.
- Search is correct across root/project notes and Transcript text, but
  per-match in-row highlighting remains deferred.
- Further Transcript editing/presentation polish remains deferred.
- Speech still uses the system voice and has no voice/rate picker.

## Phase 5.1.3 recommended hands-on retest

Use a disposable library. Confirm the Share button opens the native picker for
a readable TXT, project Share produces the documented sanitized ZIP, and
neither action sends or uploads automatically. Grab any normal point on project
rows to reorder above/below several projects, verify clicks still select, then
quit/relaunch and confirm order. Drag one note Unfiled → Project A → Project B
→ Unfiled; confirm UUID, attachment opening, Open File/Reveal paths, search,
counts, selection, collisions, undo/redo, and relaunch. Repeat drop-target
feedback in all three themes and exercise Move Project Up/Down plus Move to
Project/Remove from Project without dragging.

## Phase 5.1.2 regression retest

Use a disposable `STORMPAD_NOTES_DIR` and isolated
`STORMPAD_DEFAULTS_SUITE`:

1. Select text inside each paragraph type and choose Text, Heading 1–3, To-do,
   Bulleted list, Numbered list, and Quote; verify in-place conversion, exact
   text/format preservation, selection, undo/redo, autosave, and relaunch.
2. Select across two or more paragraphs and repeat conversion; verify every
   intersecting paragraph changes once and no blank/duplicate block appears.
3. Confirm the gutter contains only `+`, stays outside text, follows hover and
   scrolling, and has no block drag or Move Up/Down surface.
4. Cmd+A from title and body, then Delete; verify title/body/Transcript clear,
   one clean body block, undo/redo, autosave/relaunch, and attachment files
   remain present.
5. Partially select across paragraph boundaries and Delete; verify normal native
   editing and undo.
6. Apply multiple text/highlight colors, inspect mixed state, Clear each kind,
   undo/redo, and verify Markdown contains no empty semantic spans.
7. Create and rename two disposable projects, create notes directly inside,
   select projects in the sidebar, and verify counts/filtering.
8. Move notes between projects and Unfiled, including a collision and a managed
   image/file note; verify UUIDs, files, preview/open, autosave, and relaunch.
9. Delete an empty project, then a populated project; verify the latter offers
   moving notes to Unfiled and never defaults to deleting notes.
10. Use project/note Reveal actions and compare the project shown in Note Info
    with the filesystem.

If this review passes, approve Phase 5.1.3 and only then request Phase 6.

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



# CREDIT-EFFICIENT DEVELOPMENT RULE

For all future StormPad work, keep scope strictly limited to the exact feedback points provided by the user.

Do not automatically:

- inspect the entire repository
- run the full test suite
- run exhaustive manual verification
- capture large screenshot matrices
- relaunch repeatedly
- test unrelated features
- refactor adjacent systems
- perform broad regression passes
- verify every historical requirement

Instead:

1. Inspect only the files directly related to the reported issue.
2. Reproduce only the specific bug or behavior mentioned.
3. Make the smallest safe fix.
4. Run only targeted tests for the changed behavior.
5. Report what was changed and what was not tested.
6. Stop after the requested feedback points are addressed.

Only perform full verification, broad regression testing, extensive screenshots, or whole-app audits when the user explicitly asks for them.

Weekly model credits are limited, so avoid unnecessary exploration and repeated validation.
