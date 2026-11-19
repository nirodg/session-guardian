# Architecture and Product Decisions

Record dated decisions, context, rationale, alternatives, consequences, and status. Do not silently reverse accepted decisions.

## Decisions
- 2026-11-19 — Keep the core a single standard-library file. Rationale: copyable, vendorable, no install step. Alternative: package with modules (rejected for now: complicates installers). Status: accepted.
- 2026-11-19 — Use OS file locks (flock / msvcrt.locking) instead of PID lock files. Rationale: released by the OS on crash, no stale-lock heuristics. Status: accepted.
- 2026-11-19 — Publish checkpoints by staging directory + single rename; verify before use; prune only valid checkpoints. Status: accepted.
- 2026-11-19 — Retention off by default. Rationale: never delete user data unless asked. Status: accepted.
- 2026-11-19 — Watcher uses portable polling, not native FS events. Rationale: stdlib-only, identical behaviour on every OS. Trade-off: CPU proportional to file count (bounded by watch.max_files). Status: accepted.
- 2026-11-19 — Scope protection is path-based and deterministic; blocking only where the agent offers a pre-tool hook (Claude Code). Semantic contradiction detection stays in the agent protocol. Status: accepted.
- 2026-11-19 — Integrations write only marked blocks or files they own; Claude hooks merged additively. Status: accepted.
- 2026-11-19 — JSON output stays the default for backwards compatibility; `--format text` and `recover --format markdown` added. Status: accepted.
