# Changelog

All notable changes to this project are documented here. Versions follow [Semantic Versioning](https://semver.org/).

## [0.3.0] - 2026-11-19

### Added
- **Sessions:** `session start/heartbeat/end` and `sessions`; interrupted-session detection (`sessions.stale_after`); resume by agent session id.
- **Watcher:** `watch start/stop/status/run` — portable polling daemon with debounce, rate limit, branch-change triggers, ignore patterns, file bound, graceful stop, crash detection, and detection of changes made while it was not running. One process per project.
- **Recovery report:** `recover --format markdown` handoff (project, objective, invariants, state, decisions, unfinished tasks, next action, Git drift, uncommitted/untracked files, interrupted sessions). JSON gains the same fields.
- **Scope guardian:** `scope show/check/approve`, `park`; gitignore-style protected paths in `SCOPE.md`; time-limited, logged approvals; built-in protection for checkpoints and identity.
- **Registry:** `projects list/add/alias/forget/prune`, `@alias` directories, duplicate-identity detection; parent-directory project discovery.
- **Integrations:** `integrate claude|codex|opencode|gemini|cursor|windsurf|agents-md`, marked blocks that never touch user content, Claude Code hooks (`hook claude …`). Claude Code integration verified end-to-end with 2.1.328.
- **Reconciliation:** `diff`, `restore` (with safety checkpoint), `import-checkpoint` (verified).
- **Security:** credential scanning (checkpoints refuse high-confidence findings), `security.private_permissions`.
- **CLI:** `config`, `doctor` checks, `completion bash|zsh|powershell`, `uninstall`, `--version`, `--format text`, `--verbose`, consistent exit codes (1 check failed, 2 usage, 3 internal).
- **Installers:** `--version` pinning (tags, branches, commits), `--agent none`, `--yes`, interactive confirmation, staged upgrades, skill upgrades only when unmodified, install manifest, validation, `--uninstall`. Experimental `install.ps1` for Windows.
- Tests for the 12 roadmap failure scenarios; installer tests; release workflow.

### Changed
- `SCOPE.md` template gains "Protected paths" and "Approved scope changes" sections.

## [0.2.0] - 2026-11-19

### Added
- Atomic checkpoint publishing, OS-level locking, verified recovery-point selection, retention (`--keep`, `prune`, `retention.keep`), manifest format v2 with v1 compatibility, project identity fingerprinting, corruption and merge-conflict detection.

## [0.1.0]

- Initial memory protocol, templates, core engine, Linux/macOS installer.
