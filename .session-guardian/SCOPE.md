# Scope and Constraints

## Active objective
Complete and verify the roadmap in docs/ROADMAP.md, starting with cross-platform validation (macOS, Windows) once CI can run.

## In scope
- Core engine (core/session_guardian.py), installers, agent adapters, docs, tests.
- Items listed in docs/ROADMAP.md.

## Explicitly out of scope
- Capturing conversations, terminal scrollback or editor buffers.
- Third-party runtime dependencies in the core.
- Vendor-specific behaviour inside the core (it belongs in adapters).

## Invariants / non-negotiables
- Preserve user data and uncommitted changes.
- Do not add unrelated features or dependencies.
- Core stays one standard-library Python file supporting Python 3.9+.
- Never silently overwrite memory; installers never overwrite files they did not create.
- Backwards compatibility of memory files, manifests (v1 readable) and JSON output keys.
- Never claim an integration works until tested against a named agent version.
- Never store secrets in memory.

## Protected paths
Paths agents must not modify without explicit user approval: one gitignore-style glob per bullet, in backticks.
`session-guardian scope check` and agent hooks enforce this list.
- `LICENSE` — licensing changes need the maintainer
- `assets/` — approved artwork only

## Approval required
Record changes to this scope only after explicit user approval (`session-guardian scope approve "<what and why>"`).

## Approved scope changes
