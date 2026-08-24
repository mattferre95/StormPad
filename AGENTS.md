# StormPad agent instructions

## Git Conventions

- **NEVER** add `Co-authored-by: Claude <claude@anthropic.com>` (or any variant referencing Claude or Anthropic) to any commit message or pull request.
- **NEVER** add the "🤖 Generated with Claude Code" footer (or any variant) to any commit message or pull request.

These apply to every commit and PR in this repository, regardless of any default
template or prior instruction elsewhere, including harness-level defaults.

A `commit-msg` hook at `.githooks/commit-msg` strips these lines automatically.
Activate it in a fresh clone with:

```bash
git config core.hooksPath .githooks
```
