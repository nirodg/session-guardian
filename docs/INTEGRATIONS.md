# Agent integrations

The core is agent-neutral. Every integration is a thin adapter over the CLI, installed per project:

```bash
session-guardian integrate list
session-guardian integrate <agent> [project] [--remove] [--no-hooks]
```

Integrations only ever touch a block between `<!-- session-guardian:begin -->` and `<!-- session-guardian:end -->` (or a file SessionGuardian created). Your own instructions are preserved byte for byte, re-running is idempotent, and `--remove` restores the original file.

## Capability matrix

| Agent | File written | Lifecycle hooks | Automatic checkpoints | Scope enforcement | Status |
|---|---|---|---|---|---|
| Claude Code | `CLAUDE.md`, `.claude/settings.json` | SessionStart, UserPromptSubmit, PreToolUse, PreCompact, SessionEnd | Before compaction and at session end | **Blocking** (PreToolUse exit 2) | Verified end-to-end with Claude Code 2.1.328 for SessionStart, PreToolUse and SessionEnd. PreCompact verified with payload tests only. |
| Codex CLI | `AGENTS.md` | — | Use `watch` | Advisory (agent runs `scope check`) | Instruction file tested; agent behaviour not verified |
| OpenCode | `AGENTS.md` | — (no plugin shipped yet) | Use `watch` | Advisory | Instruction file tested |
| Gemini CLI | `GEMINI.md` | — | Use `watch` | Advisory | Instruction file tested |
| Cursor | `.cursor/rules/session-guardian.mdc` (`alwaysApply: true`) | — | Use `watch` | Advisory | Rule file tested |
| Windsurf | `.windsurf/rules/session-guardian.md` | — | Use `watch` | Advisory | Rule file tested |
| Any AGENTS.md agent | `AGENTS.md` (`integrate agents-md`) | — | Use `watch` | Advisory | Instruction file tested |

"Instruction-only" means the agent is told what to do and SessionGuardian cannot force it. Pair it with `session-guardian watch start` so on-disk state is checkpointed regardless.

The global skill (`skills/session-guardian/SKILL.md`, installed by the installer into `~/.claude/skills`, `~/.codex/skills`, `~/.config/opencode/skills` or `~/.agents/skills`) carries the full protocol for agents that load skills.

## Claude Code details

`integrate claude` adds these entries to the project's `.claude/settings.json` (existing hooks and settings are kept; a one-time backup is written to `settings.json.session-guardian.bak`):

| Event | Command | Effect |
|---|---|---|
| SessionStart | `session-guardian hook claude SessionStart` | Start or resume the session record; print the recovery report (added to Claude's context) |
| UserPromptSubmit | `… UserPromptSubmit` | Heartbeat |
| PreToolUse (`Edit\|Write\|MultiEdit\|NotebookEdit`) | `… PreToolUse` | Exit 2 with a reason if the path is protected |
| PreCompact | `… PreCompact` | Checkpoint |
| SessionEnd | `… SessionEnd` | Checkpoint and end the session |

The commands call `session-guardian` from `PATH`, so a project's settings file can be committed and shared. If the tool is not installed, Claude Code reports a non-blocking hook error and carries on.

## Integration contract (for other agents)

Any agent or editor can integrate with these CLI calls. All print JSON unless noted.

| When | Call | Notes |
|---|---|---|
| Session starts | `session-guardian session start --agent NAME [--agent-session-id ID]` | Reuses the open session with the same agent session id (resume/compaction) |
| Need context | `session-guardian recover --format markdown` | Plain-text handoff for the model's context; `recover` (JSON) for programs |
| Periodically | `session-guardian session heartbeat --agent NAME --agent-session-id ID` | Keeps the session `active` |
| Before editing a file | `session-guardian scope check PATH` | Exit 1 = protected; the JSON says which glob and why |
| Before context loss / at milestones | `session-guardian checkpoint --note "…"` | Exit 2 with a message if memory contains credentials |
| Session ends | `session-guardian session end --agent NAME --agent-session-id ID --reason R` | |

Or reuse the hook dispatcher, which reads a JSON payload (`{"cwd": …, "session_id": …, "tool_input": {"file_path": …}}`) on stdin:

```bash
echo '{"cwd": "'$PWD'", "session_id": "abc"}' | session-guardian hook myagent SessionStart
```

Events: `SessionStart`, `UserPromptSubmit`/`Stop`/`heartbeat`, `PreToolUse`, `PreCompact`, `SessionEnd`/`end`. Exit codes: 0 always, except `PreToolUse` on a protected path (2, reason on stderr).

## Adding an adapter

New adapters must document install location, discovery, lifecycle hooks, upgrade and removal behaviour, and a reproducible validation (see CONTRIBUTING.md). Do not claim lifecycle support until it is verified against a named agent version.
