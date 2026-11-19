# Architecture

SessionGuardian has three layers, kept separate so the core never depends on a vendor:

```text
 agents (Claude Code, Codex, OpenCode, Cursor, …)
   │  instructions (CLAUDE.md / AGENTS.md / rules)  +  lifecycle hooks where supported
   ▼
 CLI contract: session-guardian <command>   (JSON on stdout, documented exit codes)
   ▼
 core engine: core/session_guardian.py      (Python 3.9+, standard library, one file)
   ▼
 project memory: <project>/.session-guardian/   ·   global registry: <data home>/registry.json
```

## Core engine

A single file so it can be installed, vendored, or run directly (`python3 core/session_guardian.py …`). Sections:

| Area | Responsibility |
|---|---|
| Primitives | `atomic_write` (temp file + fsync + `os.replace` + directory fsync), `create_new` (hard-link based create-if-absent, never overwrites), `write_durable`. |
| Locking | `file_lock`: `fcntl.flock` on POSIX, `msvcrt.locking` on Windows. The OS releases the lock when the holder dies, so there is no stale-lock recovery to get wrong. `project_lock` guards memory and checkpoints; `.watch.lock` guarantees one watcher per project; `.registry.lock` guards the registry. |
| Checkpoints | Staging directory → files written once and hashed from the same bytes → manifest → fsync → single `rename` publish → `LATEST`. Retention prunes only *valid* checkpoints by renaming them to `.trash-*` before deletion. |
| Verification | Manifest format version, allowed file names, sizes, SHA-256, unlisted files, project identity. v1 manifests are normalised in memory, never rewritten. |
| Inspection | Corruption (empty, non-UTF-8, NUL), merge-conflict markers, credential scan, identity fingerprint (Git root commits), remnants of interrupted operations. |
| Sessions | One JSON record per session in `sessions/`. State is derived: `ended`, `active` (seen within `sessions.stale_after`), or `interrupted`. Agent session ids make `SessionStart` on resume/compaction idempotent. |
| Recovery | Selects the newest valid checkpoint, compares memory and Git with it (branch, HEAD, commits since, uncommitted and untracked files), extracts unfinished tasks and the next action, and renders a Markdown handoff. Memory excerpts are framed as data and their headings demoted so they cannot impersonate report sections. |
| Scope | Parses `SCOPE.md` sections; gitignore-style protected globs plus built-in protection of checkpoints and identity; time-limited approvals logged in `SCOPE.md`; append-only parking lot in `NEXT_STEPS.md`. |
| Watcher | Portable polling (`os.scandir`, bounded by `watch.max_files`) of the tree, memory files and Git state. Debounce + rate limit; branch/HEAD changes bypass the rate limit. Stores a tree digest so changes made while it was not running are detected at start. Graceful stop via a stop file (works on every OS) or signals. |
| Registry | `registry.json` in the data home (`$SESSION_GUARDIAN_DATA`, else `$XDG_DATA_HOME/session-guardian` or `%LOCALAPPDATA%\session-guardian`). Keyed by path; detects duplicate identities. Registry failures never fail project operations. |
| Integrations | Marked blocks (`<!-- session-guardian:begin/end -->`) in instruction files; only the block is ever modified. Claude Code hooks are merged into `.claude/settings.json` additively and removed precisely. |

## Data flow: a Claude Code session

1. `SessionStart` → `hook claude SessionStart` → `session start` (or resume by agent session id) → `recover` → Markdown report on stdout, which Claude Code adds to the context.
2. `UserPromptSubmit` → heartbeat (keeps the session `active`).
3. `PreToolUse` (Edit/Write/MultiEdit/NotebookEdit) → `scope check` → exit 2 with a reason when the path is protected, which blocks the tool call.
4. `PreCompact` → checkpoint before context is compacted.
5. `SessionEnd` → checkpoint and close the session. If it never fires (terminal closed, crash), the session becomes `interrupted` once stale and is reported by the next `recover`.

Hooks never fail the agent: any error other than a scope violation exits 0 with a message on stderr.

## Failure model

| Failure | Effect | Recovery |
|---|---|---|
| Process killed mid-checkpoint | Staging directory left behind; no new recovery point | Ignored by readers; removed by the next checkpoint |
| Process killed holding a lock | OS releases the lock | Nothing to do |
| Power loss after publish | Checkpoint durable on POSIX (file + directory fsync). Windows has no directory fsync | Verification detects anything incomplete |
| Corrupted checkpoint | Skipped by recovery, reported by audit | `recover` uses the previous valid one |
| Merge conflict in memory | Reported by audit | `diff` / `restore` against a checkpoint, or resolve by hand |
| Memory copied between repos | Identity mismatch / duplicate identity reported | Delete `identity.json` in the copy and run `init` |
| Watcher killed | Checkpoints intact; `watch status` reports it | `watch start`; changes made meanwhile are detected |
