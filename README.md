# SessionGuardian

<p align="center">
  <strong>Never lose context. Never lose direction.</strong><br>
  Agent-agnostic project memory, session recovery, and scope protection.
</p>

SessionGuardian gives AI coding agents a durable, repository-local source of truth for project goals, scope, architecture, decisions, current state, and next actions. Its core protocol is plain Markdown; its deterministic local engine handles initialization, atomic checkpointing, and integrity verification.

> **Core principle:** the conversation is temporary; the project's memory belongs to the project.

## Install

### macOS / Linux

```bash
curl -fsSL https://raw.githubusercontent.com/nirodg/session-guardian/main/install.sh | bash
```

Prefer to inspect before executing?

```bash
curl -fsSLO https://raw.githubusercontent.com/nirodg/session-guardian/main/install.sh
less install.sh
bash install.sh
```

Choose an adapter explicitly:

```bash
curl -fsSL https://raw.githubusercontent.com/nirodg/session-guardian/main/install.sh | bash -s -- --agent codex
```

The installer currently targets Codex, Claude Code, OpenCode, and a generic skills directory. Auto mode installs only into recognized agent skill directories already present; otherwise it installs the generic skill. Python 3.9+ and Git are required.

## Quick start

From the project you want to protect:

```bash
session-guardian init
session-guardian status
```

At the beginning of a fresh agent session, ask it to **recover context**. Before ending or switching agents, ask it to **checkpoint**.

## Core commands

- `session-guardian init [directory]` — create project memory templates without overwriting existing files.
- `session-guardian status [directory]` — show memory files, checkpoints, and Git state.
- `session-guardian checkpoint [directory]` — create a timestamped snapshot with SHA-256 manifest and Git metadata.
- `session-guardian recover [directory]` — identify available recovery context; never rolls back working files.
- `session-guardian audit [directory]` — verify required memory files and checkpoint integrity.
- `session-guardian doctor` — inspect Python and core installation.

## Memory layout

```text
.session-guardian/
  identity.json
  PROJECT.md
  SCOPE.md
  ARCHITECTURE.md
  DECISIONS.md
  CURRENT_STATE.md
  SESSION_LOG.md
  NEXT_STEPS.md
  LATEST
  checkpoints/
    <timestamp>/
      manifest.json
      *.md
```

Memory is plain Markdown: inspectable, editable, portable, and easy to version with Git. Never store secrets, credentials, private keys, or sensitive personal data in memory files.

## What it protects

- **Persistent project memory** — goals, scope, architecture, decisions, verified state, and next steps.
- **Session recovery** — actionable handoff for a fresh agent instance.
- **Scope integrity** — out-of-scope ideas are parked, not silently implemented.
- **Reality verification** — reconcile memory against source code, Git state, and test results.
- **Checkpoint integrity** — atomic file replacement and SHA-256 verification of stored snapshots.
- **Multi-agent continuity** — one portable memory format across supported agents.

## Important limitations

SessionGuardian is not a magical process recorder. It can recover only information that was persisted. A hard power loss or forced process kill can lose unsaved editor buffers and uncheckpointed reasoning. The current core snapshots memory files; it does not capture terminal scrollback, editor buffers, or live agent internals. Lifecycle hooks and automatic checkpointing remain future work and must be validated per agent and version.

The repository's actual code and Git state outrank stale memory. SessionGuardian never restores or overwrites working files automatically.

## Development

Run the standard-library test suite:

```bash
python -m unittest discover -s tests -v
```

CI is configured for Linux, macOS, and Windows across Python 3.9 and 3.12.

## Roadmap

- [x] Agent-neutral memory protocol and core skill
- [x] Memory templates and non-destructive initialization
- [x] Python standard-library core engine
- [x] Atomic checkpoint snapshots and SHA-256 integrity audit
- [x] Linux/macOS installer
- [x] Initial cross-platform CI matrix
- [ ] Run and fix the CI matrix; validate installer on clean machines
- [ ] Native agent lifecycle hooks and automatic checkpoints
- [ ] Windows-native installer and polished agent adapters
- [ ] Multi-project registry and session discovery
- [ ] Crash-resilient background checkpoint service

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). New adapters must document installation paths, discovery behavior, lifecycle hooks, upgrades, and reproducible validation.

## License

MIT — see [LICENSE](LICENSE).
