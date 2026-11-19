# SessionGuardian

**Never lose context. Never lose direction.**

SessionGuardian is an agent-agnostic project memory and session recovery system for AI-assisted software development. It gives coding agents a durable, repository-local source of truth for project goals, scope, architecture, decisions, current state, and next actions.

It is designed for Codex, Claude Code, OpenCode, and other agents that can read Markdown instructions or skills.

> **Core principle:** the agent's conversation is temporary; the project's memory belongs to the project.

## Why

AI coding sessions end unexpectedly: terminals close, agents crash, context windows compact, and developers switch tools. SessionGuardian makes recovery a deliberate engineering workflow rather than a guess based on chat history.

It also protects focus. Agents must identify out-of-scope ideas, record them separately, and keep working on the agreed objective.

## Install

### macOS / Linux

```bash
curl -fsSL https://raw.githubusercontent.com/nirodg/session-guardian/main/install.sh | bash
```

Or inspect the installer first:

```bash
curl -fsSLO https://raw.githubusercontent.com/nirodg/session-guardian/main/install.sh
less install.sh
bash install.sh
```

### Windows PowerShell

```powershell
irm https://raw.githubusercontent.com/nirodg/session-guardian/main/install.ps1 | iex
```

The installer detects supported agents, installs the shared skill/instructions, and can initialize the current project. It does not require a GitHub account at runtime.

## Quick start

From the repository you want to protect:

```bash
session-guardian init
session-guardian status
```

In your coding agent, ask it to **recover context**. Before ending a session, ask it to **checkpoint**. The skill also instructs agents to update durable memory after meaningful milestones and decisions.

## What it protects

- **Project memory:** goals, scope, architecture, decisions, verified state, and next steps.
- **Session recovery:** a compact, actionable handoff for a fresh agent instance.
- **Scope integrity:** explicit in-scope and out-of-scope boundaries.
- **Reality checks:** compare memory with Git state and the actual repository before resuming.
- **Multi-agent continuity:** portable Markdown memory that is not owned by one vendor.
- **Safe operation:** preserve user changes; never silently discard work or overwrite instructions.

## Memory layout

```text
.session-guardian/
  PROJECT.md
  SCOPE.md
  ARCHITECTURE.md
  DECISIONS.md
  CURRENT_STATE.md
  SESSION_LOG.md
  NEXT_STEPS.md
  checkpoints/
```

All project memory is plain Markdown and can be reviewed, edited, backed up, or committed with Git. Do not store secrets, credentials, private keys, or sensitive personal data in memory files.

## Design guarantees and limits

SessionGuardian is a recovery protocol and agent skill, not a magical process recorder. It can recover only information that was persisted. A hard power loss or forced process kill can destroy work that was never saved or checkpointed. Agent-specific hooks and lifecycle integrations can improve automatic checkpointing, but support varies by agent and version.

The source code and working tree are authoritative over stale memory. SessionGuardian never claims a task is complete without verification.

## Commands

The installer provides a lightweight local helper:

- `session-guardian init` — create project memory templates.
- `session-guardian status` — show memory files and Git working-tree state.
- `session-guardian checkpoint` — create a timestamped checkpoint from current memory.
- `session-guardian recover` — print the recovery checklist.
- `session-guardian doctor` — inspect installation and agent integrations.

The coding agent performs the semantic work of reading, reconciling, and updating project context.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Contributions for additional agent adapters, lifecycle hooks, tests, and platform support are welcome.

## License

MIT. See [LICENSE](LICENSE).
