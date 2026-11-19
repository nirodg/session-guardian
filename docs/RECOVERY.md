# Recovery guide

## What a fresh session gets

```bash
session-guardian recover --format markdown
```

The report answers, from memory plus live verification:

| Question | Source |
|---|---|
| What is the project? | `PROJECT.md` |
| What objective is active, what must not change? | `SCOPE.md` (objective, invariants, protected paths) |
| What is implemented? | `CURRENT_STATE.md`, commits since the checkpoint |
| What was decided? | `DECISIONS.md` |
| What is unfinished, what next? | unchecked `- [ ]` items in `NEXT_STEPS.md`; the first one is the next action |
| What might be lost or unsaved? | interrupted sessions, uncommitted and untracked files, memory changed since the checkpoint |
| Did the world move? | branch and HEAD changes since the checkpoint, rewritten history |

The JSON form (`recover` without `--format`) carries the same data for programs.

## Examples

**The terminal closed mid-task.** The session never ended, so after `sessions.stale_after` it is listed as *interrupted*. The report shows it, the last valid checkpoint, and any uncommitted files. Review the uncommitted files before continuing: they are the unrecorded work.

**Switching from Claude Code to Codex.** No conversion: both read the same `.session-guardian/`. Run `session-guardian integrate codex` once; Codex then reads the instructions in `AGENTS.md` and runs `recover`.

**The newest checkpoint is corrupt.** `recover` skips it, says why, and uses the previous valid one. `audit` exits 1 and names the problem.

**A merge left conflict markers in `CURRENT_STATE.md`.** `audit` reports it. Compare with `session-guardian diff CURRENT_STATE.md`, then resolve by hand or run `session-guardian restore CURRENT_STATE.md --checkpoint <id>`. Restore takes a safety checkpoint first, so nothing is lost.

**You are on a different branch than the checkpoint.** The report flags *Branch changed* and lists commits since the checkpoint (or notes rewritten history). Memory may describe the other branch; verify before acting.

## Manual recovery without any agent

Everything is plain files:

1. Read `.session-guardian/*.md`, or `session-guardian recover --format markdown | less`.
2. `session-guardian audit` to check integrity.
3. Checkpoints are directories: `ls .session-guardian/checkpoints/`; each has the memory files and a `manifest.json` with SHA-256 hashes and Git state. `sha256sum` reproduces the hashes.
4. To roll memory back: `session-guardian restore --all --checkpoint <id>`, or copy files out of a checkpoint directory yourself.

## Backups

- Commit the memory files with your project; that is the simplest off-machine backup.
- Checkpoints are self-verifying directories. Copy them anywhere; bring one back with `session-guardian import-checkpoint <dir>`, which verifies it (including that it belongs to this project) before adding it.
- Retention is off by default. If you enable `retention.keep`, older valid checkpoints are deleted; invalid ones are kept for inspection.

SessionGuardian never restores or overwrites working files (your source code); it only manages memory and checkpoints.
