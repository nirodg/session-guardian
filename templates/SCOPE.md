# Scope and Constraints

## Active objective
UNKNOWN

## In scope
- UNKNOWN

## Explicitly out of scope
- UNKNOWN

## Invariants / non-negotiables
- Preserve user data and uncommitted changes.
- Do not add unrelated features or dependencies.
- UNKNOWN

## Protected paths
Paths agents must not modify without explicit user approval: one gitignore-style glob per bullet, in backticks.
`session-guardian scope check` and agent hooks enforce this list. For example, the bullet
"- `migrations/` — schema changes need review" protects that directory and everything in it.

## Approval required
Record changes to this scope only after explicit user approval (`session-guardian scope approve "<what and why>"`).

## Approved scope changes
