# Storage and Markdown format

StormPad stores user data locally. Markdown remains the note source of truth;
managed attachments are ordinary files next to the notes directory.

## Layout

```text
~/Documents/StormPad/
├── Notes/
│   ├── my-business-plan.md
│   └── my-business-plan-2.md
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
affect attachments.

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
