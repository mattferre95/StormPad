# Storage and Markdown format

StormPad stores user data locally. Markdown remains the note source of truth;
managed attachments are ordinary files next to the notes directory.

## Layout

```text
~/Documents/StormPad/
├── Notes/
│   ├── my-business-plan.md
│   ├── my-business-plan-2.md
│   └── Projects/
│       └── build/
│           ├── .stormpad-project.json
│           └── editor-plan.md
└── Attachments/
    └── 6a774f94-09f6-44f1-9e08-41fc0ddde477/
        ├── moodboard.png
        ├── brief.pdf
        └── .orphans.json
```

Tests and development launches can replace `Notes/` with
`STORMPAD_NOTES_DIR`; its sibling `Attachments/` directory follows
automatically.

## Note envelope

```markdown
# My Business Plan

Created: 2026-07-23 14:30:00+02:00
Updated: 2026-07-23 15:05:00+02:00
Category: Sessions
ID: 6a774f94-09f6-44f1-9e08-41fc0ddde477
Transcript-Block: collapsed

## Notes

## Direction

A **focused** plan with <u>clear ownership</u>.

- [x] Define the first release

![Moodboard](../Attachments/6a774f94-09f6-44f1-9e08-41fc0ddde477/moodboard.png)

<!-- stormpad:transcript collapsed="true" -->

## Transcript

[00:00:04]
We should launch the first version in September.
```

`Filename-Mode` is normally omitted/treated as `title`; an explicit manual
rename stores `manual`. `Transcript-Block` is `expanded`, `collapsed`, or
`hidden`, and it plus `## Transcript` are absent when an ordinary note has no
transcript block or content. `hidden` preserves existing transcript chunks
without placing a Transcript container in the body. Unknown metadata fields
before `## Notes` are preserved across a StormPad save.

`Project-ID` is present while a note lives in a valid project. The real folder
location remains authoritative; this metadata provides a stable relationship
that does not depend on the folder slug.

## Projects

Each project directory contains `.stormpad-project.json` with a stable UUID,
display name, created date, and updated date. Folder names are safe slugs;
duplicate names receive `-2`, `-3`, and so on. Renaming changes the folder and
metadata while preserving the project UUID, note UUIDs, and attachment
directories.

Moving a note into or out of a project moves its Markdown file, resolves
filename collisions, and rewrites only managed relative attachment references
for the new depth. Search and note loading scan root notes plus project folders.
Malformed or future project metadata never makes contained Markdown disappear;
such notes remain visible as unfiled/unknown-project content.

Drag payloads never provide filesystem paths. StormPad resolves the private
pasteboard's stable note/project UUIDs against this current layout, flushes
pending edits, verifies the source, chooses an unused destination, and performs
the filesystem move before updating visible membership. A same-project drop is
a no-op. If the move fails, the previous Markdown path, content, project
membership, and stable attachment directory remain valid.

Deleting an empty project sends its folder through the configured Trash
strategy. A populated project cannot be deleted implicitly: the supported path
moves every note to Unfiled first, collision-safely, then trashes the empty
project folder.

## Block syntax

| Block or mark | Stored form |
| --- | --- |
| Heading 1–3 | `#`, `##`, `###` |
| To-do | `- [ ]` / `- [x]` |
| Bullet / number | `- item` / `1. item` |
| Quote / divider | `> quote` / `---` |
| Link | `[label](target)` |
| Image | `![alt](relative/path)` |
| Managed file | `[filename](relative/path)` |
| Bold / italic | `**bold**` / `*italic*` |
| Underline | `<u>text</u>` |
| Text color | `<span data-stormpad-color="blue">text</span>` |
| Highlight | `<span data-stormpad-highlight="yellow">text</span>` |
| Transcript placement | `<!-- stormpad:transcript collapsed="false" -->` |
| Toggle List | `<!-- stormpad:toggle collapsed="false" -->` + `- summary` |
| Toggle Heading 1-3 | `<!-- stormpad:toggle … -->` + `#`, `##`, `###` |
| Image width / alignment | `<!-- stormpad:image width="640" alignment="center" -->` |

Allowed semantic color names are `default`, `gray`, `blue`, `cyan`, `green`,
`yellow`, `orange`, `red`, and `purple`. Arbitrary style/script content is
never generated or executed.

## Bundled starter note

StormPad ships one read-only starter template inside the application bundle at
`stormpad/resources/welcome_note.md`. It is an ordinary note document without
`ID` or timestamps, so identity belongs to the copy that lands in the user's
workspace rather than to the shipped resource.

The first time StormPad initializes a genuinely new workspace it parses that
template with the production parser and writes one note, `Welcome to StormPad`,
into `Notes/` through the normal storage layer. From then on the note is
indistinguishable from any other: editable, renameable, movable, pinnable, and
permanently deletable. The bundle is never read again.

A workspace counts as new only while `Notes/` does not exist yet, so the check
runs before the directory is created. An established workspace is recognized
even when the user has since deleted every note, and never receives the starter
note retroactively.

Installation is recorded once in the durable
`starter_template_installed_v1` preference, written only after the note is
successfully on disk. The marker is never keyed on a title, so renaming,
moving, or deleting the note does not bring it back, and a relaunch, update, or
reinstall cannot duplicate it. A failed write rolls the empty notes directory
back and leaves the marker unset, so the next launch retries instead of
silently skipping the note.

## Image width and alignment

An image block may carry one metadata comment, the same convention transcripts
and toggles use:

```markdown
<!-- stormpad:image width="640" alignment="center" -->
![Alt text](../Attachments/<note-id>/photo.png)
```

`width` is the displayed point width; it is presentation only and never
resamples or rewrites the source file. `alignment` is `left`, `center`, or
`right`, positioning the image within the editor content column. StormPad stores
no coordinates: a note is a flowing document, not a canvas.

`left` is the default and is never written, so an existing image note is
byte-identical after being opened and saved unchanged. A missing, unknown, or
malformed `alignment` falls back to `left`; a malformed `width` falls back to the
natural size. In every failure case the `![...](...)` line and its attachment
path are preserved, so bad metadata can cost formatting but never the image.

Pasted image data is copied into the note's own attachment directory through the
normal attachment layer, which sanitizes the filename, writes atomically, and
never overwrites an existing file. Raw clipboard bitmaps are encoded as PNG to
keep transparency; local files are copied byte-for-byte. Remote URLs are never
fetched, and no temporary pasteboard path is ever written into the Markdown.

Image selection, selection borders, and resize handles are view state only and
appear nowhere in the file.

## Collapsible toggles

Toggle List and Toggle Heading 1-3 are ordinary blocks preceded by one metadata
comment, following the same convention as `stormpad:image`:

```markdown
<!-- stormpad:toggle collapsed="true" -->
- Launch checklist

  - Finalize homepage

  - Build the DMG

Normal paragraph outside the toggle

<!-- stormpad:toggle collapsed="false" -->
## Product direction
```

The line beneath the comment decides the kind: a bullet becomes a Toggle List,
and `#`, `##`, or `###` become Toggle Heading 1, 2, or 3. `collapsed` is the
existing `Block.collapsed` property and accepts only `true` or `false`.

**Collapsing hides nothing from the file.** A collapsed toggle still serializes
every block it owns, so search, export, sharing, Copy Note, and autosave all see
the complete note. Collapse is applied in the editor with layout-only
mechanisms (a clear temporary attribute plus a zero-height line fragment), and
the full document always remains in the text storage that saving reads from.

Ownership follows the existing structure rather than a stored child list:

- A **Toggle List** owns the following blocks indented deeper than itself and
  stops at the first block whose indent is equal or shallower. Only blocks that
  carry indent (to-dos, bullets, numbered items, and nested toggles) can be
  children; a plain paragraph cannot, because four leading spaces already means
  preserved raw text.
- A **Toggle Heading** owns everything until the next heading of the same or
  higher level, counting normal and toggle headings alike, so a section runs to
  the end of the note when nothing bounds it.

Unknown or malformed toggle metadata is preserved as raw text and the line below
it parses as an ordinary bullet or heading, so a bad marker degrades to fully
visible content and never hides or drops anything. Notes without toggle metadata
parse exactly as before.

## IDs and migration

- New notes receive one UUID at creation.
- Renaming a title or file never changes that UUID.
- Legacy notes without `ID` receive a deterministic in-memory UUID. Opening
  them alone does not modify the file.
- The next actual save writes the ID and preserves unknown metadata.
- A legacy filename stem remains a temporary lookup alias so older persisted
  selection values continue to resolve.

## Filenames

Titles commit to lowercase, Unicode-friendly kebab names. Unsafe punctuation is
removed, repeated whitespace/dashes are collapsed, and an empty title becomes
`untitled-note.md`. Collisions append `-2`, `-3`, and so on.

StormPad first atomically saves the current path, then moves that valid file to
the new unused path. If the move fails, the old path and saved content remain
valid and the in-memory path is not changed.

`Rename Filename…` is an explicit secondary workflow. Input is sanitized,
`.md` is preserved, collisions receive numeric suffixes, the stable UUID and
attachment directory do not change, and `Filename-Mode: manual` prevents a
later title save from silently replacing the chosen filename. Rename failure
restores the previous file and mode.

## Attachments and deletion

Imports are copied into `Attachments/<stable-note-id>/` through a same-directory
temporary file. Markdown stores relative paths, so note filename changes do not
affect attachments; project movement retargets those relative references
without moving the attachment directory.

Removing an image/file block does not delete the managed file; StormPad records
the relative path in `.orphans.json` for a future conservative cleanup tool.
Deleting a note stages its Markdown file and attachment directory together and
moves that bundle to macOS Trash. A staging/Trash failure rolls the data back.

## Plain-text export

TXT export is a separate atomic UTF-8 file and never changes the Markdown note.
It includes the title, readable block text, `[ ]`/`[x]` to-dos, list/quote/link
content, image alt text, attached filenames, and timestamped transcript chunks.
It omits the metadata envelope, UUID, `Filename-Mode`, transcript UI state,
StormPad color/underline markup, and managed attachment directory details.

## Temporary native sharing

Share Note uses the same readable text conversion but writes to a
collision-safe filename such as `my-business-plan.txt` in the system temporary
cache under `StormPad/ShareExports`. It never writes into Notes, changes the
Markdown source, or enters search.

Share Project creates an atomic collision-safe ZIP with this public layout:

```text
Project Name/
├── README.txt
├── Notes/
│   ├── first-note.md
│   └── first-note.txt
└── Attachments/
    └── first-note/
        └── referenced-file.pdf
```

The Markdown copy has internal identity metadata and absolute paths removed,
and managed attachment links are rewritten to the ZIP layout. Only attachments
referenced by included notes are copied. `.stormpad-project.json`, preferences,
caches, orphan records/files, unrelated project files, and hidden UI state are
excluded. The original project tree is unchanged.

StormPad gives the temporary TXT or ZIP file URL to the native macOS sharing
picker and does not upload or send it automatically. On launch and quit,
StormPad removes only its own share artifacts older than 24 hours; recent files
remain available long enough for a user-selected service to consume them.
