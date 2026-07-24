# Contributing to StormPad

Thank you for helping improve StormPad. Contributions should preserve its
native macOS experience, local-first storage model, and privacy guarantees.

## Requirements

- macOS
- Python 3.12
- Git

StormPad is a native AppKit application built with PyObjC. Native interface
behavior should remain in the AppKit layer, while storage and model logic should
remain independently testable.

## Local setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m stormpad
```

You can also use:

```bash
./scripts/run.sh
```

## Pull requests

- Keep each pull request focused on one problem or cohesive change.
- Explain user-visible behavior and storage implications.
- Add or update focused tests when behavior changes.
- Preserve the native AppKit and PyObjC architecture.
- Do not include generated release artifacts.
- Do not include personal notes, attachments, screenshots, paths, or logs.
- Use sanitized temporary fixtures for screenshots and UI checks.

Accounts, telemetry, advertising, cloud storage, cloud sync, and external
service dependencies require prior project discussion. Do not introduce them
incidentally.

## Checks

Run before opening a pull request:

```bash
python -m pytest
python -m ruff check .
python -m compileall -q stormpad scripts tests
```

When a change affects AppKit behavior, also launch the application and verify
the relevant native flow manually. Use the existing isolated smoke tools when
appropriate.
