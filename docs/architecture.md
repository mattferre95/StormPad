# StormPad architecture

## Principles

- StormPad is a native Python 3.12 + PyObjC/AppKit application. It does not use
  a web view, HTML contenteditable, React, Electron, or browser JavaScript.
- Markdown files are the source of truth. AppKit renders and edits a semantic
  model; it does not replace the local files with a database.
- Domain, storage, search, preferences, block conversion, and attachment
  policies remain AppKit-free and are tested headlessly.
- Views consume semantic tokens from `theme.py`; semantic inline colors are
  stored as token names so changing theme never changes note content.
- User data is changed only by an explicit create/edit/action. Loading a legacy
  file does not rewrite or rename it.

## Phase 5.1.2 stabilized editor and local Projects

### Representation and selection

`blocks.py` defines `Block`, `InlineRun`, and `InlineMark`. Required block types
are text, Heading 1–3, to-do, bullet, numbered list, quote, divider, link,
image, file, and transcript. Unknown fenced Markdown is represented as a
protected raw block so it is not silently discarded.

`views/block_editor.py` owns one rich native `NSTextView` for body blocks. A
paragraph-level attributed-string key identifies each block and carries
to-do/indent/target/collapse metadata. Native attributed runs carry bold,
italic, underline, link, and semantic color/highlight keys. The active
paragraph is the block selection; the normal `NSTextView` range is the inline
selection.

The title remains a native `NSTextField` in the model, but its typography and
keyboard transitions make it the visual first block of the page. Return from
the title focuses the first body paragraph; Up at the start of the body returns
to the title. The placeholder `Untitled` is never saved as content. Editor-wide
Cmd+A selects the visual title and the entire body, and one Delete clears both
plus Transcript UI state as one undoable/autosaved mutation. Managed attachment
files are preserved.

### Block interaction and undo

`GutterHoverView` is a dedicated transparent pointer tracker outside the text
column. Pure `BlockGutterLayout` helpers model the text inset, gutter width,
visible block rectangle, scroll offset, hit region, and control rectangles.
Only the `+` appears beside the hovered semantic block. It remains left of the
92-point text inset with explicit clearance, follows scrolling, and hides when
the pointer leaves the block area. There is no block drag handle, drop target,
insertion indicator, or Move Up/Down UI. The hover preference may hide `+`, but
native Format commands remain available.

`+` captures the body selection before opening its retained native menu. When
text is selected, paragraph commands convert every intersecting paragraph in
place and preserve the exact text/runs without inserting a duplicate. A
collapsed selection converts a compatible empty text paragraph or inserts one
structural block below the active paragraph (above with Option). Format ▸ Block
Type uses the same selection-aware path. The caret or selection is restored and
the mutation participates in native undo and autosave.

Text typing uses the standard `NSTextView` undo manager. Structural and
formatting operations snapshot the affected attributed content and register
inverse operations with that same manager. All mutations call the existing
body-edit callback and therefore share the autosave path.

### Markdown conversion

`block_parser.py` converts `Note.body` to semantic blocks and
`block_serializer.py` writes deterministic, human-readable Markdown:

- standard Markdown for headings, bold, italic, lists, to-dos, quotes,
  dividers, links, images, and files;
- `<u>` for underline;
- allow-listed `<span data-stormpad-color="…">` and
  `<span data-stormpad-highlight="…">` for curated semantic colors;
- `<!-- stormpad:transcript collapsed="…">` for the optional transcript-block
  placement/state marker.

No Markdown or HTML is executed. Unsupported color values are treated as plain
content, output is escaped, and only the curated token set is serialized.
Supported `<u>` and semantic `<span>` tags may begin a normal paragraph; the
parser distinguishes them from unsupported raw HTML so leading formatting
survives relaunch.

The selection toolbar uses standard native controls. Its text/highlight color
menus pair semantic swatches with visible labels. `Clear` removes a text-color
mark and restores the current theme foreground; `Clear / Transparent` removes
highlight markup and native background color. Mixed selections report mixed
state. Standard `NSMenuItem` surfaces preserve keyboard menu access, selection
checks, and predictable AppKit drawing.

### Autosave

`AutosaveController` still owns the 0.4-second debounce. Title, body,
formatting, block, attachment, and transcript-state changes all enter the same
callback. Switching notes, closing, and quitting flush pending edits. The save
callback captures the stable note ID and refuses to apply stale editor content
to a newly selected note.

The note is atomically written to its current path before a title-derived
rename is attempted. If the rename fails, the valid, newly saved old file
remains in place and the UI reports the failure.

## Stable identity and filename migration

Every new note receives one UUID, stored as `ID: <uuid>` in Markdown metadata.
Identity is independent of title and path. `NoteStore` resolves notes by the
stored ID, and selection preferences store that ID.

A legacy file without `ID` receives a deterministic UUIDv5 derived from its
existing absolute path. This is an in-memory migration only: opening the file
does not rewrite it. Its next real save persists the UUID. The legacy stem is
temporarily retained as a lookup alias so an existing last-note preference can
still resolve during migration.

Safe title commits produce lowercase, Unicode-friendly kebab filenames.
Reserved punctuation is removed, whitespace is normalized, an empty result
uses `untitled-note.md`, and collisions use `-2`, `-3`, and so on. Existing
files are not mass-renamed; a title filename is adopted on the next committed
title/save.

Note Info exposes the filename and current full path without adding permanent
metadata to the writing canvas. An explicit manual rename is sanitized and
collision-safe, keeps `.md`, preserves the UUID and attachment directory, and
sets `Filename-Mode: manual`; later title saves no longer overwrite that manual
choice. A failed move restores both the previous path and filename mode.

## Attachments

`attachments.py` stores managed local copies at:

```text
~/Documents/StormPad/
├── Notes/
│   ├── <unfiled-title-slug>.md
│   └── Projects/<project-slug>/<filed-title-slug>.md
└── Attachments/<stable-note-id>/<sanitized-filename>
```

An import copies to a temporary file inside the managed directory and then
atomically moves it into place. Duplicate names receive numeric suffixes.
Markdown stores paths relative to each note, and project moves retarget those
references without moving the stable-ID attachment directory. Image blocks use
native `NSTextAttachment` previews; file blocks show a native compact line with
filename, type, and size and open through `NSWorkspace` on double-click.
Context actions reveal or remove the block.

Removing a block records its path in `.orphans.json` and does not delete the
underlying file. Deleting a note stages the note and its stable-ID attachment
directory together before passing the bundle to the configured Trash strategy;
failure rolls both back.

## Transcript

Timestamped transcript chunks remain in `Note.transcript`, separate from
editable body prose. The optional transcript marker only records block
visibility and collapse state. The editor renders a semantically themed native
container inside the note flow. Its heading/collapse control and empty-state
`Append Test Transcript` action remain interactive while its multiline
timestamp/text rows are protected read-only attributed content. Context actions
can collapse/expand, append test data, remove chunks, or remove its marker;
inverse chunk operations register with the editor undo manager. Further
Transcript polish is deferred beyond Phase 5.1.2.

A Transcript appears only when chunks exist, the user inserts the block, or
Development ▸ Append Test Transcript is invoked. Removing/hiding the marker
does not discard legacy chunks. Body search continues to include
`Note.transcript`.

No recording, live transcription, or WisperFlow integration exists in this
phase.

## Local Projects, note actions, TXT export, menus, and Settings

Projects are real filesystem folders under `Notes/Projects/`, with one hidden
`.stormpad-project.json` identity record in each folder. Notes remain ordinary
Markdown and gain the known `Project-ID` metadata key while filed. `NoteStore`
creates, loads, renames, and deletes projects; creates notes directly inside a
project; and moves notes into or out of projects with collision-safe filenames.
Project folder renames preserve project and note UUIDs. Managed attachment
references are retargeted relative to the note's new folder while the stable
attachment UUID and files remain unchanged.

The sidebar exposes All Notes, Unfiled, and a collapsible Projects section above
Categories. Project rows show folder icons and live counts. Project and note
context menus provide create, rename, reveal, delete, move-to-project, and
remove-from-project actions. Deleting a non-empty project never deletes its
notes by default: the native confirmation path moves them to Unfiled first.
Unknown legacy metadata is preserved, and root-level notes remain visible.

The upper-right Note Info menu and the Note menu share the same current-note
actions. Project, filename, path, dates, category, and word count are read from
the selected stable-ID note after pending edits are flushed. Open, Reveal,
Rename, Export, Settings, Move to Project, Remove from Project, and Delete
operate on that current path.

`exporter.py` is AppKit-free. It converts every semantic block and transcript
chunk into readable UTF-8 text, strips Markdown/StormPad inline markup and
storage metadata, renders to-dos as `[ ]`/`[x]`, and never writes back to the
note. `window.py` wraps it in one native `NSSavePanel` and an atomic destination
write.

`app.py` constructs complete StormPad, File, Edit, Note, Format, View, Window,
Help, and Development menus. Validation reflects selection, current block and
inline formatting, panel state, theme, and enabled actions.

`views/settings.py` owns one reusable window. Appearance changes theme
immediately, Editor controls the persisted Add Block hover preference, and
Storage shows the StormPad root/Notes/Attachments paths with separate Reveal
actions.

## Phase 5.1.3 native sharing and sidebar dragging

### One sharing path

The top-right `square.and.arrow.up` button, File ▸ Share Note…, Note ▸ Share
Note…, Note Info, and note context menu all call the same controller action.
Pending edits are flushed, the current note is reloaded by stable UUID, and
`ShareExportManager` writes a human-readable TXT outside the Notes library.
`NSSharingServicePicker` receives only the resulting file URL. StormPad does
not pick a service, recipient, cloud destination, or public link.

Project row context menus call the same manager with a stable project UUID.
The manager stages a sanitized project tree and atomically replaces a
collision-safe ZIP. It includes a local-export README, readable TXT and
sanitized Markdown per note, and only referenced managed attachments.
Attachment links are rewritten for the ZIP layout; identity metadata, project
metadata files, preferences, caches, orphaned attachments, and absolute local
paths are omitted. The originals are never rewritten.

The share cache defaults to the system temporary directory under
`StormPad/ShareExports`, never under Notes. Manager-owned artifacts older than
24 hours are removed on launch and quit. Current exports remain long enough for
the user-selected native service to read them.

### UUID-only internal dragging

`dragdrop.py` defines private project and note pasteboard types. Payloads
contain a validated UUID, semantic kind, source project UUID/Unfiled, and source
index; paths are never accepted from the pasteboard. Every drop resolves the
UUID through the current `NoteStore`/project model and rejects missing,
deleted, stale, malformed, or unsupported payloads.

Custom project `SidebarRow` views make the icon, name, count, and empty row
background one drag surface. A five-point threshold separates selection from
dragging. Internal project drops only compute a new flat order—dropping on a
project never nests it—and persist UUID order in Preferences without renaming
folders. The UI shows a lifted row, insertion line, accessibility announcement,
and near-edge autoscroll. Undo/redo and context-menu Move Project Up/Down use
the same pure reorder operation.

The middle `NSTableView` supplies native whole-row note dragging. Project and
Unfiled rows are note destinations; All Notes, Categories, and the Projects
header reject drops. Before a move, the controller flushes autosave and reloads
the note/project by UUID. `NoteStore` performs the collision-safe filesystem
move first, retargets managed attachment links, and only then refreshes
selection, filters, search, counts, current paths, and preferences. The stable
note UUID and attachment directory do not change. A failure leaves the prior
file/content/membership valid; same-project drops are no-ops. Undo moves the
note to its previous project or Unfiled location.

Dragging an exported project ZIP to Finder is deliberately deferred. External
dragging returns no operation so StormPad can never move a managed project
folder out of its library. Block dragging inside the editor remains out of
scope.

## Layers

### AppKit-free

| Module | Responsibility |
| --- | --- |
| `models.py` | Note/project/transcript structures, categories, timestamps, stable-ID state. |
| `storage.py` | Note/project parsing/serialization, atomic writes, slugging, safe rename, legacy migration. |
| `sharing.py` | Temporary readable note shares and atomic sanitized project ZIP packages. |
| `dragdrop.py` | Private UUID drag payload validation and pure project reorder helpers. |
| `blocks.py` | Semantic blocks/inline marks and pure structural operations. |
| `block_parser.py` | Supported Markdown → semantic blocks. |
| `block_serializer.py` | Semantic blocks → safe deterministic Markdown. |
| `attachments.py` | Managed paths, atomic imports, collision policy, orphan manifest. |
| `session.py` | Note/project CRUD, filing moves, transcript seam, note+attachment deletion policy. |
| `exporter.py` | Semantic note → readable atomic UTF-8 TXT export. |
| `paths.py` | Canonical/injectable local paths; no import-time creation. |
| `search.py` | Unicode title/body/transcript search and category/project filtering. |
| `preferences.py` | Theme, note/project selection, project order/collapse, note-list collapse, and Add Block preference. |
| `theme.py` | Complete Storm Blue, Light, and Deep Dark semantic tokens. |
| `uihelpers.py` | Pure previews, selection rules, autosave, and block UI-state helpers. |

### AppKit

| Module | Responsibility |
| --- | --- |
| `app.py` | Application lifecycle and complete native application menu bar. |
| `window.py` | Window/split controller, autosave, project/note actions, validation, theme rebuild, Note Info/TXT. |
| `defaults.py` | `NSUserDefaults` adapter for the preferences protocol. |
| `views/block_editor.py` | Native title/body page, blocks, formatting toolbar, gutter, attachment rendering. |
| `views/editor.py` | Compatibility re-export of the block editor. |
| `views/note_list.py` | Themed persistent selection and collapsible middle column. |
| `views/settings.py` | Reusable themed Settings window and storage reveal actions. |
| `views/sidebar.py` | Search, Library, filesystem Projects, categories, counts, branding, privacy indicator. |
| `views/palette.py` | Theme token → AppKit color/font/symbol resolution. |
| `speech.py` | Isolated AVSpeechSynthesizer wrapper and lifecycle. |

## Theme switching and note-list collapse

Theme changes flush pending edits, rebuild the AppKit view tree from a new
palette, reload the stable selected note, and restore body selection/focus.
The middle note-list panel stores its collapsed state through `Preferences`.
Expanded width is preserved by the split view; collapsed width is a 46-point
tab that cannot cover the editor. The left-facing collapse arrow stays in the
expanded header and the right-facing expand arrow stays near the top of the
collapsed tab.

## Compatibility

Phase 1–5 files with `# Title`, metadata, `## Notes`, and optional
`## Transcript` continue to load. Existing body content becomes blocks and
transcript chunks remain separate. Root-level notes stay visible as Unfiled;
project folders are discovered recursively. Unknown metadata is preserved. No
file is renamed, assigned an on-disk ID/project, or otherwise migrated merely
by being opened.

See [storage.md](storage.md) for the exact on-disk format and migration rules.
