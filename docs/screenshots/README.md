# Screenshots

Screenshots for the README live here. They are generated from the running app
against a **temporary** notes directory (never your real notes), so they are
reproducible and safe to commit.

## Reproducible capture

Seed a temp folder and launch the app pointed at it via the `STORMPAD_NOTES_DIR`
dev hook, then capture the window:

```bash
# 1. Seed a temporary notes directory with demo fixtures.
export SP_DEMO="$(mktemp -d)/Notes"
./.venv/bin/python - "$SP_DEMO" <<'PY'
import sys
from stormpad.session import NoteStore
from stormpad import models
s = NoteStore(sys.argv[1])
n = s.create_note("App idea — voice session notes", models.SESSIONS)
s.update_body(n.id, "StormPad should feel like the fastest place to put a thought.")
s.append_transcript_block(n.id, "This is a captured thought.", 4)
s.append_transcript_block(n.id, "Chunks append in order.", 11)
s.create_note("Client website brainstorm", models.IDEAS)
s.create_note("Video concepts", models.DRAFTS)
PY

# 2a. Active-note state.
STORMPAD_NOTES_DIR="$SP_DEMO" ./scripts/run.sh
# 2b. Search state (boots into a query):
STORMPAD_NOTES_DIR="$SP_DEMO" STORMPAD_INITIAL_QUERY=voice ./scripts/run.sh
# 2c. Empty state (point at a fresh empty dir):
STORMPAD_NOTES_DIR="$(mktemp -d)/Notes" ./scripts/run.sh
```

Then capture the front window (⌘⇧4 then Space, or `screencapture -o -w`) and
save as `active.png`, `search.png`, `empty.png` here.

## Dev/test hooks used above

- `STORMPAD_NOTES_DIR` — point the app at any notes directory (keeps demos out
  of `~/Documents/StormPad/Notes`).
- `STORMPAD_INITIAL_QUERY` — boot into a search state.
- `python -m stormpad --smoke` — build the UI and print introspected state
  without entering the event loop (useful when no display is available).

> Note: screenshots were not captured in the original Phase 3 build session
> because that session had no display access for `screencapture`. The app itself
> launches and runs; regenerate the images with the commands above.
