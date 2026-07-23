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

## Phase 5.1 block editor

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
to the title. The placeholder `Untitled` is never saved as content.

### Block interaction and undo

The native gutter follows the active line using the layout manager plus the
scroll view's visible offset. It is shown while the body is active and hidden
when focus leaves. `+` opens one native insertion menu. Option-insert places a
block above; an empty paragraph is converted in place. The handle intentionally
uses a native Move Up / Move Down menu rather than custom drag reordering; this
is the stable Phase 5.1 fallback.

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

## Attachments

`attachments.py` stores managed local copies at:

```text
~/Documents/StormPad/
├── Notes/<title-slug>.md
└── Attachments/<stable-note-id>/<sanitized-filename>
```

An import copies to a temporary file inside the managed directory and then
atomically moves it into place. Duplicate names receive numeric suffixes.
Markdown stores paths relative to `Notes/`, so renaming a note does not break
links. Image blocks use native `NSTextAttachment` previews; file blocks show a
native compact line with filename, type, and size and open through
`NSWorkspace` on double-click. Context actions reveal or remove the block.

Removing a block records its path in `.orphans.json` and does not delete the
underlying file. Deleting a note stages the note and its stable-ID attachment
directory together before passing the bundle to the configured Trash strategy;
failure rolls both back.

## Transcript

Timestamped transcript chunks remain in `Note.transcript`, separate from
editable body prose. The optional transcript marker only records block
visibility and collapse state. The editor renders transcript timestamps/text as
protected content. A transcript appears only when chunks exist, the user
inserts the block, or Development ▸ Append Test Transcript is invoked.

No recording, live transcription, or WisperFlow integration exists in this
phase.

## Layers

### AppKit-free

| Module | Responsibility |
| --- | --- |
| `models.py` | Note/transcript structures, categories, timestamps, stable-ID state. |
| `storage.py` | Note Markdown parsing/serialization, atomic writes, slugging, safe rename, legacy migration. |
| `blocks.py` | Semantic blocks/inline marks and pure structural operations. |
| `block_parser.py` | Supported Markdown → semantic blocks. |
| `block_serializer.py` | Semantic blocks → safe deterministic Markdown. |
| `attachments.py` | Managed paths, atomic imports, collision policy, orphan manifest. |
| `session.py` | `NoteStore` CRUD, transcript seam, note+attachment deletion policy. |
| `paths.py` | Canonical/injectable local paths; no import-time creation. |
| `search.py` | Unicode title/body/transcript search and category filtering. |
| `preferences.py` | Theme, selection, category, and note-list-collapse preferences. |
| `theme.py` | Complete Storm Blue, Light, and Deep Dark semantic tokens. |
| `uihelpers.py` | Pure previews, selection rules, autosave, and block UI-state helpers. |

### AppKit

| Module | Responsibility |
| --- | --- |
| `app.py` | Application lifecycle and native File/Edit/Note/Format/View/Development menus. |
| `window.py` | Window/split controller, autosave wiring, actions, theme rebuild, Note Info. |
| `defaults.py` | `NSUserDefaults` adapter for the preferences protocol. |
| `views/block_editor.py` | Native title/body page, blocks, formatting toolbar, gutter, attachment rendering. |
| `views/editor.py` | Compatibility re-export of the block editor. |
| `views/note_list.py` | Themed persistent selection and collapsible middle column. |
| `views/sidebar.py` | Search, categories, counts, branding, privacy indicator. |
| `views/palette.py` | Theme token → AppKit color/font/symbol resolution. |
| `speech.py` | Isolated AVSpeechSynthesizer wrapper and lifecycle. |

## Theme switching and note-list collapse

Theme changes flush pending edits, rebuild the AppKit view tree from a new
palette, reload the stable selected note, and restore body selection/focus.
The middle note-list panel stores its collapsed state through `Preferences`.
Expanded width is preserved by the split view; collapsed width is a 46-point
tab that cannot cover the editor.

## Compatibility

Phase 1–5 files with `# Title`, metadata, `## Notes`, and optional
`## Transcript` continue to load. Existing body content becomes blocks and
transcript chunks remain separate. Unknown metadata is preserved. No file is
renamed, assigned an on-disk ID, or otherwise migrated merely by being opened.

See [storage.md](storage.md) for the exact on-disk format and migration rules.
