# SessionGuardian

<p align="center">
<img src="assets/cover.png" alt="SessionGuardian — Never lose context. Never lose direction." width="100%">
</p>

<p align="center">
  <strong>Never lose context. Never lose direction.</strong><br>
  Agent-agnostic project memory, session recovery, and scope protection.
</p>

SessionGuardian gives AI coding agents a durable, repository-local source of truth for project goals, scope, architecture, decisions, current state, and next actions. Memory is plain Markdown in `.session-guardian/`; a single-file, standard-library Python engine handles crash-safe checkpoints, verified recovery, session tracking, a background watcher, and scope enforcement.

> **Core principle:** the conversation is temporary; the project's memory belongs to the project. The agent is replaceable.

## Install

### macOS / Linux

```bash
curl -fsSL https://raw.githubusercontent.com/nirodg/session-guardian/main/install.sh | bash
```

Inspect first, pin a version, or pick an agent:

```bash
curl -fsSLO https://raw.githubusercontent.com/nirodg/session-guardian/main/install.sh
less install.sh
bash install.sh --version <tag-or-commit> --agent claude   # agent: auto | codex | claude | opencode | generic | none
```

### Windows (experimental)

```powershell
irm https://raw.githubusercontent.com/nirodg/session-guardian/main/install.ps1 -OutFile install.ps1
.\install.ps1 -AddToPath
```

`install.ps1` mirrors `install.sh` but has **not yet been validated on Windows**; it runs in the `windows-latest` CI job. The core engine supports Windows (it uses `msvcrt` locking), but that path has also only been exercised in CI so far.

Requirements: Python 3.9+, Git (for downloads and Git-aware features). Installers are idempotent: re-running upgrades in place, never overwrites a skill you edited or a file it did not create, and never touches project memory. Uninstall with `bash install.sh --uninstall` or `.\install.ps1 -Uninstall`.

## Quick start

```bash
cd my-project
session-guardian init                 # create .session-guardian/ (never overwrites)
session-guardian integrate claude     # or codex, opencode, gemini, cursor, windsurf, agents-md
session-guardian watch start          # optional: background checkpoints on activity
```

Fill in `SCOPE.md` (objective, invariants, protected paths) and `PROJECT.md`. From then on:

- A fresh session runs `session-guardian recover --format markdown` (Claude Code does this automatically via hooks) and gets a handoff report: what the project is, the active objective, what must not change, decisions, current state, unfinished tasks, the next action, Git drift, and interrupted sessions.
- Agents update memory after milestones and run `session-guardian checkpoint`.
- Edits to protected paths are flagged by `session-guardian scope check` (and blocked outright in Claude Code).

## Commands

| Command | Purpose |
|---|---|
| `init [dir] [--alias NAME]` | Create memory templates without overwriting; record identity; register the project. |
| `status [dir]` | Memory files, checkpoints, sessions, watcher, Git state. |
| `checkpoint [dir] [--keep N] [--note TEXT]` | Atomically publish a verified snapshot. Refuses if memory appears to contain credentials (`--allow-secrets` to override). |
| `recover [dir] [--checkpoint ID] [--format markdown]` | Select the newest valid checkpoint and produce the recovery report. Read-only. |
| `audit [dir]` | Verify memory, identity, secrets, merge-conflict markers and every checkpoint. Exit 1 on problems. |
| `diff [dir] [--checkpoint ID] [FILE…]` | Unified diff of memory against a checkpoint. |
| `restore FILE… --checkpoint ID` / `--all` | Explicitly restore memory files; a safety checkpoint of the current content is taken first. |
| `prune [dir] --keep N` | Delete the oldest valid checkpoints beyond N. |
| `import-checkpoint SRC [dir]` | Verify an external checkpoint and add it as a recovery point. |
| `session start/heartbeat/end` · `sessions` | Record and list agent sessions (active, interrupted, ended). |
| `watch start/stop/status/run [dirs…] [--all]` | Background watcher; one process per project. |
| `scope show` · `scope check PATH… [--git]` · `scope approve TEXT [--path GLOB]` | Scope guardian. `check` exits 1 on protected paths. |
| `park "idea"` | Record an out-of-scope idea in the parking lot instead of implementing it. |
| `projects [list/add/alias/forget/prune]` | Global registry of projects; `@alias` works wherever a directory is accepted. |
| `config list/get/set/unset KEY [VALUE]` | Per-project configuration (validated). |
| `integrate AGENT [dir] [--remove]` · `integrate list` | Install agent instructions and (Claude Code) lifecycle hooks. |
| `hook AGENT EVENT` | Lifecycle hook entry point; reads the event payload on stdin. |
| `doctor` · `completion bash/zsh/powershell` · `uninstall` · `--version` | Diagnostics and tooling. |

Commands search parent directories for `.session-guardian/`, so they work from any subdirectory. Output is JSON by default (`--format text` for humans); usage errors exit 2, unexpected errors exit 3 with a one-line message (`--verbose` for details).

## Memory layout

```text
.session-guardian/
  PROJECT.md  SCOPE.md  ARCHITECTURE.md  DECISIONS.md     # project memory (commit these)
  CURRENT_STATE.md  SESSION_LOG.md  NEXT_STEPS.md
  identity.json        # project_id + Git root-commit fingerprint
  config.json          # optional settings
  .gitignore           # ignores the machine-local files below
  LATEST               # id of the newest checkpoint
  checkpoints/<YYYYMMDDTHHMMSS_ffffffZ>/manifest.json + *.md
  sessions/            # machine-local session records
  watch.json watch.log # machine-local watcher state
  .lock .watch.lock    # OS-level locks
```

Memory is plain Markdown: inspectable, editable, portable, and easy to version with Git. Whether to commit `checkpoints/` is your choice; the default `.gitignore` only excludes machine-local runtime files. **Never store secrets in memory.**

## Guarantees

- **Atomic checkpoints.** Built in `checkpoints/.staging-*`, published with one directory rename. A crash, kill or full disk mid-checkpoint never produces a visible checkpoint and never replaces an earlier one; leftovers are cleaned by the next checkpoint.
- **Consistent hashes.** Each file is read once; the stored bytes and the recorded SHA-256 come from the same read and are fsynced before publishing.
- **Locking.** Mutating commands hold an OS lock (`flock` / `msvcrt.locking`) that the OS releases if the holder dies — no stale locks after crashes.
- **Never silently overwrite memory.** `init` uses exclusive creates; `park` and `scope approve` only append; `restore` takes a safety checkpoint first; `recover` is read-only.
- **Verified recovery.** Manifest format, allowed file names (no path traversal), sizes, hashes, unlisted files and project identity are checked; recovery picks the newest checkpoint that passes.
- **Corruption, conflict and contamination detection.** Missing/empty/non-UTF-8 files, merge-conflict markers, credentials, foreign checkpoints, memory copied from another repository, duplicate identities across projects.
- **Versioned formats.** Manifest v2; v1 is still read; newer formats are rejected with an upgrade hint rather than misread.

## Configuration

`session-guardian config list` shows every key with its meaning. Highlights:

| Key | Default | Meaning |
|---|---|---|
| `retention.keep` | `0` (unlimited) | Keep only the N newest valid checkpoints. Invalid ones are never pruned. |
| `watch.interval` / `watch.debounce` / `watch.min_checkpoint_interval` | 5 / 10 / 300 s | Poll rate, quiet period before a checkpoint, and rate limit (branch changes bypass the limit). |
| `watch.ignore` / `watch.max_files` | common build dirs / 20000 | Watcher exclusions and scan bound. |
| `sessions.stale_after` | 1800 s | A session not seen for this long is reported as interrupted. |
| `security.block_secrets` | `true` | Refuse checkpoints when high-confidence credentials are detected. |
| `security.private_permissions` | `false` | `0700`/`0600` permissions on memory and checkpoints (POSIX). |

## Agent support

| Agent | Integration | Lifecycle hooks | Verified |
|---|---|---|---|
| Claude Code | `CLAUDE.md` block + `.claude/settings.json` hooks | SessionStart (recovery report injected), UserPromptSubmit (heartbeat), PreToolUse (blocks protected paths), PreCompact (checkpoint), SessionEnd (checkpoint + end) | End-to-end with Claude Code 2.1.328 (SessionStart, PreToolUse, SessionEnd); PreCompact unit-tested only |
| Codex, OpenCode, generic | `AGENTS.md` block | None — instruction-only | File installation tested; agent compliance depends on the model |
| Gemini CLI | `GEMINI.md` block | None | File installation tested |
| Cursor / Windsurf | `.cursor/rules/…mdc` / `.windsurf/rules/…md` | None | File installation tested |

Instruction-only agents get automatic checkpoints from `session-guardian watch`. See [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md) for the hook contract and how to integrate another agent.

## Important limitations

SessionGuardian is not a process recorder. It recovers only what was persisted: memory files written by agents, checkpoints, session records, and Git state. It does not capture conversations, terminal scrollback, editor buffers, or agent internals; a forced kill or power loss loses uncheckpointed reasoning and unsaved buffers. The watcher preserves filesystem and Git state; semantic context comes from agents keeping memory files accurate.

Scope protection is a guardrail, not a security boundary: an agent with shell access can run `scope approve` itself or edit `SCOPE.md`. Approvals are logged in `SCOPE.md` so this is auditable. The repository's actual code and Git state outrank stale memory. SessionGuardian never restores or overwrites working files automatically.

More: [architecture](docs/ARCHITECTURE.md) · [recovery guide](docs/RECOVERY.md) · [watcher](docs/WATCHER.md) · [integrations](docs/INTEGRATIONS.md) · [roadmap](docs/ROADMAP.md) · [changelog](CHANGELOG.md)

## Development

```bash
python -m unittest discover -s tests -v
```

Standard library only. The suite (128 tests) covers the core, sessions, watcher (real background processes), scope, recovery, registry, integrations, Claude hook payloads, the installer, and the 12 failure scenarios from the roadmap. CI runs Linux, macOS and Windows on Python 3.9 and 3.12, plus installer smoke tests on each OS.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Security issues: [SECURITY.md](SECURITY.md).

## License

MIT — see [LICENSE](LICENSE).
