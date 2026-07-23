# StormPad PRD


**Product Name:** StormPad  
**Tagline:** A local-first notepad for capturing ideas as they happen.  
**Project Type:** Standalone native macOS app prototype  
**Version:** V1 PRD with V2 and final product roadmap  
**Status:** Planning / product definition  
**Proposed Local Project Path:** `/Users/mattferre/web/APP/stormpad`  
**Future Relationship:** Separate public GitHub project first, future premium Session Notes layer for WisperFlow.


---


## 1. Product Overview


StormPad is a standalone native macOS notepad designed for fast idea capture, private local writing, and future voice-driven session notes.


It is structurally inspired by the simplicity of Apple Notes: sidebar, note list, editor, search, autosave. Visually and philosophically, StormPad should feel more modern, local-first, and builder-focused. Notes are saved as Markdown files directly on the user’s Mac. There is no cloud sync, no account system, no telemetry, no analytics, and no external AI dependency in V1.


StormPad starts as a typing-first local notepad. The architecture should be clean enough that WisperFlow can later append live transcript chunks into StormPad-style notes during a premium Session Notes mode.


The guiding idea:


Apple Notes structure + modern dark native macOS design + local Markdown files + future voice-first capture.


---


## 2. Name and Positioning


### Name


StormPad


### Tagline


A local-first notepad for capturing ideas as they happen.


### Positioning


StormPad is a modern local-first notes app for people who want to capture thoughts, drafts, ideas, and future voice transcripts without being locked into cloud services.


It should feel fast, calm, private, and focused. It is not trying to replace Notion, Obsidian, Craft, or a full productivity suite in V1. The product should stay small enough to build well, while laying a strong foundation for future voice-session features.


### One-Line Pitch


StormPad is a private macOS notepad that saves your ideas locally as Markdown and is designed to become a voice-first session notes companion.


---


## 3. Target Users


### Primary User


The primary user is a Mac-based builder, creator, or freelancer who wants a fast local space to capture ideas without cloud friction.


### Early Users


- People who want a cleaner Apple Notes alternative.
- Builders capturing product ideas.
- Freelancers writing quick notes and client thoughts.
- Creators drafting scripts, hooks, thumbnails, and concepts.
- Students or professionals taking private local notes.
- Privacy-conscious Mac users.
- WisperFlow users who eventually want long-form voice notes.


---


## 4. Core Use Cases


### Use Case 1 — Quick Idea Capture


The user opens StormPad, creates a note, writes an idea, and trusts that it autosaves locally.


### Use Case 2 — Local Markdown Notes


The user wants notes stored as normal `.md` files that can be opened, backed up, edited, moved, or versioned outside the app.


### Use Case 3 — Project Brainstorming


The user creates a note for a project idea and adds messy thoughts, lists, references, and future actions.


### Use Case 4 — Session Notes Prototype


The user clicks “Append Test Transcript” to simulate a future WisperFlow transcript block being inserted into the note.


### Use Case 5 — Finder-Friendly Notes


The user can reveal the real Markdown file in Finder and open it in any text or Markdown editor.


### Use Case 6 — Future Voice Capture


In a later version, WisperFlow can create or open a StormPad-style note and append transcript chunks while the user speaks.


---


## 5. V1 Product Scope


V1 should be practical, small, and public-GitHub ready.


### V1 Must-Have Features


- Native macOS window.
- Left notes sidebar.
- Main editor area.
- Create new note.
- Rename note.
- Autosave while typing.
- Save notes as local Markdown files.
- Reload notes when the app restarts.
- Delete note with confirmation.
- Search notes.
- Open note file.
- Reveal note in Finder.
- Append fake transcript block button for future WisperFlow testing.
- Timestamped transcript blocks.
- Clean README.
- MIT license.
- `.gitignore`.
- Basic tests for storage and session logic.


### V1 Nice-to-Have Features


Only include these if they do not make V1 too large:


- Word count.
- Character count.
- Autosave status: `Saving…` / `Saved`.
- Keyboard shortcut: `Cmd+N` for new note.
- Keyboard shortcut: `Cmd+F` for search.
- Keyboard shortcut: `Cmd+S` for force save.
- Empty states.
- Persist last selected note.


---


## 6. V1 Non-Goals


Do not include the following in V1:


- Speech recording.
- Whisper transcription.
- Global hotkeys.
- System audio capture.
- Speaker labels.
- AI summaries.
- Cloud sync.
- Accounts.
- Payments.
- Telemetry.
- Analytics.
- Clipboard paste automation.
- WisperFlow integration code.
- Background menu bar behavior.


V1 is only the standalone local notes prototype.


---


## 7. UX Flow


### First Launch


1. User launches StormPad.
2. App creates the default notes folder if missing.
3. App opens the main window.
4. If no notes exist, user sees an empty state.
5. User clicks “New Note.”
6. A Markdown file is created.
7. The note appears in the sidebar.
8. The editor becomes active.


### Creating a Note


1. User clicks `New Note`.
2. App creates a new Markdown file.
3. Default title is `Untitled Note`.
4. File is saved immediately.
5. User can rename the note.
6. Autosave updates the file as the user types.


### Editing a Note


1. User selects a note from the sidebar.
2. Main editor loads the note content.
3. User edits the title or body.
4. Changes autosave after a short debounce.
5. UI shows save status.


### Searching Notes


1. User types into the search field.
2. Sidebar filters notes by title and body preview.
3. Search results update quickly.
4. Clearing search restores the full list.


### Appending a Test Transcript


1. User clicks `Append Test Transcript`.
2. App appends a timestamped block to the current note.
3. Editor updates immediately.
4. Markdown file saves.


### Opening or Revealing a Note


- `Open File` opens the Markdown file with the default macOS app.
- `Reveal in Finder` opens Finder and selects the file.


### Deleting a Note


1. User selects a note.
2. User clicks delete.
3. Confirmation dialog appears.
4. If confirmed, the note is deleted or moved to Trash.
5. Sidebar updates.


---


## 8. Information Architecture


StormPad V1 uses one main window with two primary zones:


```text
┌───────────────────────────────────────────────┐
│ Toolbar / Header                              │
├───────────────┬───────────────────────────────┤
│ Notes Sidebar │ Editor                        │
│               │                               │
│ Search        │ Title                         │
│ Note List     │ Autosave Status               │
│ New Note      │ Markdown/Text Editor          │
│               │                               │
└───────────────┴───────────────────────────────┘
```


### Sidebar


The sidebar contains:


- Search field.
- Note list.
- Note title.
- Updated timestamp.
- Optional short preview.
- New Note button.


### Editor


The editor contains:


- Editable title.
- Autosave status.
- Main text area.
- Action buttons:
  - Append Test Transcript.
  - Open File.
  - Reveal in Finder.
  - Delete.


---


## 9. UI Layout Requirements


### Main Window


- Native macOS window.
- Minimum size around `900 x 620`.
- Default size around `1100 x 720`.
- Sidebar width around `260`.
- Editor takes remaining width.
- Native macOS feel, not a web app.


### Sidebar Requirements


- Clear selected note state.
- Search field at top.
- Notes sorted by most recently updated.
- Empty state if no notes exist.
- Search empty state if no results.


### Editor Requirements


- Large readable writing area.
- Clean note title field.
- Autosave indicator.
- Comfortable line height.
- Markdown stored plainly.
- Text editing should feel native and responsive.


### Empty States


No notes:


```text
Capture your first storm.
Create a local note to start writing.
[New Note]
```


No selected note:


```text
Select a note or create a new one.
```


No search results:


```text
No notes found.
```


---


## 10. Visual Design Direction


StormPad should be structurally familiar like Apple Notes, but visually original.


### Design Keywords


- Native.
- Fast.
- Calm.
- Premium.
- Local.
- Focused.
- Dark blue.
- Minimal.
- Writer-friendly.


### Palette


```text
#0A1128 — Night navy
#0B1DFF — Deep blue
#0A84FF — Electric blue
#00C7FF — Cyan
#73E8FF — Soft aqua
```


### Visual Rules


- Do not visually copy Apple Notes.
- Use Apple Notes only as structural inspiration.
- Prefer dark navy surfaces.
- Use cyan and blue accents sparingly.
- Keep text highly readable.
- Avoid excessive glow.
- Avoid web-style cards if they do not feel native.
- Keep controls calm and macOS-like.


### Suggested Look


- Dark navy app background.
- Slightly lighter sidebar.
- Main editor in a soft rounded surface.
- Cyan selected-note accent.
- Small blue autosave indicator.
- Subtle glow only in active/focused states.
- SF Symbols where appropriate.


---


## 11. Local File / Storage Model


### Default Storage Folder


```text
~/Documents/StormPad/Notes/
```


The app should create this folder automatically on first launch.


### File Type


```text
.md
```


### File Naming


Use a safe slug based on the note creation timestamp and title.


Example:


```text
2026-07-23-1430-untitled-note.md
```


### Rename Behavior


For V1, keep filenames stable. When the user renames a note, update the Markdown title and metadata, but do not rename the underlying file automatically. This avoids broken references and reduces edge cases.


### Source of Truth


Markdown files are the source of truth.


An optional lightweight index may be used later for faster search:


```text
~/Documents/StormPad/index.json
```


But V1 should remain understandable and portable.


---


## 12. Markdown File Format


Each note is a readable Markdown file.


### Sample Note


```md
# Untitled Note


Created: YYYY-MM-DD HH:mm
Updated: YYYY-MM-DD HH:mm


## Notes


Typed notes go here.


## Transcript


[00:00:04]
Future transcript block goes here.
```


### Transcript Block Format


```md
[00:04:12]
This is a transcript chunk from a future WisperFlow session.
```


The format should be simple enough that future WisperFlow code can append to it without needing to understand the full UI.


---


## 13. Future WisperFlow Integration Concept


StormPad should be built separately first. Later, WisperFlow may reuse its storage and note-session concepts for a premium feature called Session Notes.


### Future WisperFlow Session Flow


```text
Double-press Right Option in WisperFlow
→ Start Session Notes
→ Create a StormPad-style Markdown note
→ Record microphone audio in chunks
→ Transcribe chunks locally
→ Append transcript blocks live
→ Save locally
→ Reveal or open final note
```


### Future Integration Boundary


StormPad should have clean concepts that can later be reused:


- `Note`
- `NoteStorage`
- `create_note(title)`
- `save_note(note)`
- `append_transcript_block(note_id, text, timestamp)`
- `reveal_note_in_finder(note_id)`


### Example Future API


```python
session = create_note(title="Meeting Notes")
append_transcript_block(session.id, text="The idea is to build the V1 smaller.", timestamp="00:04:12")
save_note(session)
```


V1 should not implement WisperFlow integration, but the storage and session modules should be clean enough to support it later.


---


## 14. Technical Architecture


### Preferred Stack


```text
Python 3.12
PyObjC / AppKit
Native macOS window
Local Markdown files
pytest for tests
ruff or black for formatting
```


### Not Allowed


```text
Electron
React
Next.js
Webviews
Cloud APIs
Analytics SDKs
Account systems
External AI APIs
```


### Core Modules


- `app.py` — app entrypoint.
- `window.py` — main window/controller.
- `sidebar.py` — sidebar and note list UI.
- `editor.py` — editor UI.
- `models.py` — note data structures.
- `storage.py` — Markdown file read/write.
- `paths.py` — app paths and directory creation.
- `theme.py` — colors, fonts, spacing constants.
- `session.py` — note/session operations.
- `utils.py` — small helpers if needed.


### Architecture Principles


- Keep UI separate from storage.
- Keep file operations testable without launching the app.
- Keep note/session logic pure where practical.
- Avoid large files.
- Avoid hidden side effects.
- Avoid unnecessary global state.
- Make the repo understandable for public GitHub visitors.


---


## 15. Suggested Folder Structure


```text
stormpad/
  stormpad/
    __init__.py
    app.py
    window.py
    sidebar.py
    editor.py
    session.py
    storage.py
    models.py
    paths.py
    theme.py
    utils.py


  assets/
    README.md


  scripts/
    run.sh
    test.sh
    format.sh


  tests/
    test_storage.py
    test_session.py
    test_paths.py


  README.md
  PRD.md
  LICENSE
  pyproject.toml
  .gitignore
```


---


## 16. Public GitHub Quality Checklist


StormPad should be public-ready from day one.


### Required Repo Files


- `README.md`
- `PRD.md`
- `LICENSE`
- `.gitignore`
- `pyproject.toml`
- `scripts/run.sh`
- `scripts/test.sh`
- `scripts/format.sh`


### README Requirements


The README should include:


- Product name.
- Tagline.
- Short description.
- Screenshot placeholder.
- Features.
- V1 scope.
- Non-goals.
- Installation.
- Run instructions.
- Test instructions.
- Architecture overview.
- Privacy statement.
- Roadmap.
- License.


### `.gitignore` Must Exclude


```text
.venv/
__pycache__/
*.pyc
.DS_Store
dist/
build/
*.egg-info/
logs/
*.log
.env
.env.*
.pytest_cache/
.ruff_cache/
```


### Public Safety Requirements


Do not commit:


- API keys.
- Personal notes.
- Logs.
- Local configs with private paths, unless documented as examples.
- `.venv`.
- Build artifacts.
- Generated cache files.
- Private screenshots.
- WisperFlow private project files unless intentionally cleaned and copied.


---


## 17. Privacy and Security Requirements


StormPad V1 must be privacy-friendly by design.


### Privacy Rules


- Notes stay local on the user’s Mac.
- No cloud sync.
- No accounts.
- No telemetry.
- No analytics.
- No crash reporting SDKs.
- No external AI APIs.
- No background network calls.


### Security Rules


- Do not request unnecessary macOS permissions.
- Do not require Accessibility.
- Do not require Input Monitoring.
- Do not require Microphone.
- Do not require Screen Recording.
- Do not modify files outside the StormPad notes folder unless the user chooses an explicit file action.


### README Privacy Statement


```text
StormPad stores notes locally on your Mac. V1 does not use cloud sync, accounts, analytics, telemetry, AI APIs, or network services.
```


---


## 18. Accessibility Requirements


StormPad should be readable, navigable, and comfortable to use.


### V1 Accessibility Requirements


- Text contrast must be high enough on dark backgrounds.
- Main actions must have visible labels.
- Keyboard navigation should work where practical.
- Editor should support normal macOS text behavior.
- Search field should be accessible.
- Buttons should have clear names.
- Selected note state should be visually obvious.
- Destructive actions must not rely on color only.


### Suggested Keyboard Shortcuts


```text
Cmd+N — New Note
Cmd+F — Search
Cmd+S — Force Save
Cmd+O — Open File
Esc — Clear search or cancel modal
```


---


## 19. Edge Cases


StormPad should handle:


- Notes folder does not exist.
- Notes folder cannot be created.
- Markdown file is deleted outside the app.
- Markdown file is renamed outside the app.
- Markdown file is edited outside the app.
- Empty note title.
- Duplicate note titles.
- Very long note.
- Special characters in title.
- No notes exist.
- Search returns no results.
- User tries to delete the current note.
- File open fails.
- Reveal in Finder fails.
- Autosave fails.
- App quits during autosave.
- Corrupted or malformed Markdown metadata.
- Storage path contains spaces or non-English characters.


V1 does not need perfect handling for every edge case, but it should fail clearly and avoid data loss.


---


## 20. Acceptance Criteria


StormPad V1 is complete when:


- `scripts/run.sh` launches the app.
- App creates `~/Documents/StormPad/Notes/` if missing.
- User can create a new note.
- New note appears in the sidebar.
- User can rename the note.
- User can type in the editor.
- Editor autosaves to a Markdown file.
- App reloads existing notes on restart.
- Search filters notes.
- User can append a fake timestamped transcript block.
- User can open the Markdown file.
- User can reveal the Markdown file in Finder.
- User can delete a note after confirmation.
- No WisperFlow files are touched.
- No microphone, hotkey, paste, or transcription logic exists in V1.
- Repo is safe to publish on GitHub.
- README explains purpose, setup, privacy stance, and roadmap.
- Basic tests pass for storage/session logic.


---


## 21. V2 Scope — WisperFlow Session Notes Integration


V2 turns StormPad from a standalone notepad prototype into the foundation for WisperFlow’s premium Session Notes feature.


### V2 Product Goal


Allow WisperFlow to create and append to StormPad-style notes during long-form local dictation sessions.


### V2 User Experience


```text
Double-press Right Option in WisperFlow
→ Start Session Notes
→ StormPad-style note is created
→ User speaks naturally
→ WisperFlow records microphone audio in chunks
→ Local Whisper transcribes each chunk
→ Transcript blocks append live into the note
→ Double-press Right Option again to stop
→ Final Markdown file is revealed or opened
```


### V2 Features


- WisperFlow starts a Session Notes mode.
- Double-press Right Option toggles session start/stop.
- Mic-only long-form recording.
- Chunked transcription.
- Silence-based segmentation.
- Append transcript blocks live to a local Markdown note.
- Show session duration.
- Show recording/transcribing status.
- Pause/resume session.
- Stop session safely.
- Open or reveal finished note.
- Keep normal hold-to-dictate unchanged.
- No system audio capture yet.
- No speaker labels yet.
- No AI summaries yet.


### V2 Technical Notes


V2 should not record one giant audio file and transcribe only at the end. It should use rolling chunks to keep memory stable and make the note update live.


Preferred flow:


```text
capture audio
→ detect silence or segment boundary
→ close chunk
→ transcribe chunk
→ append to note
→ free audio memory
```


### V2 Non-Goals


- Zoom/Meet system audio capture.
- Speaker diarization.
- AI summaries.
- Cloud upload.
- Team collaboration.
- Accounts or billing.


---


## 22. Final Product Vision


The final version of StormPad can become a local-first capture workspace for typed notes, voice notes, and session transcripts.


The final product should still protect the original principle:


Local-first. Private. Fast. No unnecessary cloud dependency.


### Final Product Pillars


1. **Fast Capture** — open quickly, write instantly, append voice thoughts naturally.
2. **Local Ownership** — Markdown files live on the user’s Mac.
3. **Voice-First Sessions** — long-form dictation and session recording become a core strength.
4. **Beautiful Native UX** — premium macOS design without Electron bloat.
5. **Composable with WisperFlow** — WisperFlow can create and update notes without tightly coupling the apps.


### Full Feature Set — Final Phase


#### Notes Core


- Local Markdown notes.
- Sidebar and search.
- Folders or collections.
- Tags.
- Pinned notes.
- Favorites.
- Recent notes.
- Markdown preview mode.
- Export `.md`, `.txt`, and `.pdf`.
- Import existing Markdown files.
- File watching for external edits.


#### Capture Features


- Typed notes.
- Append transcript blocks.
- Quick capture window.
- Menu bar quick note.
- Global quick note shortcut, if user grants permission.
- Session templates.
- Meeting notes template.
- Brainstorm template.
- Daily log template.


#### WisperFlow / Voice Features


- WisperFlow Session Notes mode.
- Double-press hotkey to start/stop long session.
- Mic-only recording.
- Chunked transcription.
- Live note appending.
- Pause/resume.
- Local audio retention setting.
- Option to discard raw audio after transcription.
- Local-only transcript cleanup.
- Session duration indicator.
- Session recovery if app quits mid-session.


#### Advanced Voice Features


These should come after the core experience is stable:


- System audio capture for Zoom/Meet-style sessions.
- Speaker diarization, if feasible locally.
- Multiple audio source selection.
- Audio level monitor.
- Noise/silence handling settings.
- Long meeting stability testing.


#### Local Intelligence Features


Only after V1 and V2 are stable:


- Local summary generation.
- Local action item extraction.
- Local decision extraction.
- Local title suggestions.
- Local cleanup/rewrite options.
- Local semantic search.
- Local embeddings stored on device.


#### Privacy and Control Features


- Clear storage folder preference.
- Export all notes.
- Delete all app data.
- No cloud by default.
- Optional future sync only if explicitly designed.
- Clear privacy screen in app.
- No telemetry unless user explicitly opts in.


#### Premium Feature Possibilities


If StormPad becomes part of a paid WisperFlow product:


- Unlimited Session Notes.
- Long-form transcription sessions.
- Voice note history.
- Local summaries.
- Action items.
- Search across transcripts.
- Export formats.
- Custom templates.
- System audio capture, if technically and legally scoped.


---


## 23. Build Phases


### Phase 0 — Planning


Deliverables:


- Final PRD.
- V1 scope lock.
- V2 roadmap.
- Final folder structure.
- Final acceptance criteria.


No code.


### Phase 1 — Project Scaffold


Deliverables:


- Clean project folder.
- `pyproject.toml`.
- `.gitignore`.
- `README.md`.
- `LICENSE`.
- Basic package structure.
- Run/test scripts.


Acceptance:


- Repo is structurally safe for public GitHub.
- No personal or private files included.


### Phase 2 — Storage Layer


Deliverables:


- Notes folder creation.
- Markdown file creation.
- Read/write notes.
- Rename note title.
- Delete note.
- Append transcript block.
- Basic tests.


Acceptance:


- Storage tests pass without launching UI.


### Phase 3 — Native UI


Deliverables:


- Native macOS window.
- Sidebar.
- Editor.
- New Note.
- Search.
- Autosave.
- Save status.


Acceptance:


- User can create, edit, save, and reload notes.


### Phase 4 — File Actions


Deliverables:


- Open File.
- Reveal in Finder.
- Delete confirmation.
- Error handling.


Acceptance:


- File actions work safely.


### Phase 5 — Visual Polish and Public Repo Prep


Deliverables:


- Visual polish.
- README update.
- Screenshot placeholder.
- Roadmap.
- Privacy statement.
- Final tests.


Acceptance:


- Project is ready to upload to public GitHub.


### Phase 6 — V2 WisperFlow Integration Planning


Deliverables:


- Integration design document.
- Session Notes API design.
- Double-press hotkey plan.
- Chunked transcription plan.
- Failure recovery plan.


Acceptance:


- WisperFlow integration is planned without risking the stable dictation pipeline.


---


## 24. Final V1 Principle


StormPad V1 should be small, beautiful, local, and reliable.


Do not overbuild.


The goal is not to create a full notes platform immediately. The goal is to create a clean local-first notepad foundation that feels good enough to become WisperFlow’s premium Session Notes experience later.


---


## 25. Design Handoff and Brand Assets


### Official Logo
The current official StormPad logo is the white S / lightning mark inset into an electric blue gradient square. This logo should be treated as the temporary source of truth for branding during V1 implementation.


Official logo preview:


  



### Provided Design Handoff
A StormPad macOS design handoff has now been provided. The implementation should use that design as the visual source of truth rather than inventing a new layout from scratch.


Provided assets:
- `StormPad macOS design-handoff.zip` — main macOS app design handoff.
- `StormPad macOS design-handoff_themes.zip` — theme exploration / theme handoff.
- `Stormpad_logo.png` — current official logo asset.


### Theme System
StormPad now has three visual theme directions to choose from. V1 should either ship one selected theme first or keep theme support architected cleanly enough to add the others later.


1. **Storm Blue / Signature** — the current primary identity: dark navy surfaces, electric blue and cyan accents, subtle glow, selected notes with cyan emphasis, and premium local-first feel.
2. **Light** — a clean bright variant with off-white backgrounds, white/frosted panels, dark readable text, soft blue selection states, and minimal local-first polish.
3. **Deep Dark / Focus** — a calmer near-black navy writing mode with reduced glow, high-contrast editor text, quieter selected states, and a more focused long-writing feel.


### Design Implementation Rules
- Keep the Apple Notes-like structure: sidebar, note list, editor, search, save status, and note actions.
- Do not visually clone Apple Notes; use the provided StormPad design language as the reference.
- Keep the design native macOS and avoid a web-app feel.
- Use the official logo in the app icon, README, window/sidebar branding, and future GitHub assets unless replaced by a later finalized brand system.
- Treat theme tokens as code-level constants in `theme.py` so colors can be swapped cleanly.
- Do not add cloud/account/paywall UI to the V1 design.
