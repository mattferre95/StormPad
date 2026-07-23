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

Allowed semantic color names are `default`, `gray`, `blue`, `cyan`, `green`,
`yellow`, `orange`, `red`, and `purple`. Arbitrary style/script content is
never generated or executed.

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
