# SessionGuardian — Remaining Tasks & Implementation Roadmap

**Vision:** The ultimate agent-agnostic session persistence, recovery, and scope-protection system for AI-assisted software development.

**Repository:** https://github.com/nirodg/session-guardian

**Core principle:** Never lose context. Never lose direction.

Status legend: `[x]` implemented and tested · `[~]` partially implemented (see note) · `[ ]` not started.

---

## 1. Core Engine Hardening

**Priority: CRITICAL** — *done except Windows/macOS verification*

The core engine must become the reliable foundation independent of any AI agent.

- [x] Review and validate existing Python core implementation.
- [x] Implement robust atomic checkpoint operations. *(staging directory + single rename publish)*
- [x] Add checkpoint versioning and migration support. *(manifest v2; v1 read in place; newer formats rejected with upgrade hint)*
- [x] Implement checkpoint rotation and configurable retention. *(`--keep`, `prune`, `config.json` `retention.keep`; off by default)*
- [x] Add recovery-point selection and validation. *(newest valid checkpoint; `recover --checkpoint ID`)*
- [x] Implement crash-safe writes and filesystem locking. *(fsync + atomic rename; `flock` / `msvcrt.locking`)*
- [x] Detect corrupted, incomplete, or inconsistent memory.
- [x] Add memory conflict detection and reconciliation. *(merge-conflict markers, drift since checkpoint; `diff`, `restore` with safety checkpoint, `import-checkpoint`. Semantic merging of conflicting content stays manual.)*
- [x] Implement project fingerprinting and identity verification. *(project_id in manifests; Git root-commit fingerprint)*
- [x] Add comprehensive unit and integration tests. *(see `tests/`; includes real process kills while locked and mid-checkpoint)*
- [ ] Verify cross-platform behavior on Linux, macOS and Windows. *Verified locally on Linux with Python 3.9, 3.11, 3.12. macOS and Windows not yet run: GitHub Actions jobs are not starting (account billing lock).*

**Acceptance criteria:**
- No checkpoint operation can silently corrupt existing memory.
- Interrupted writes cannot replace the last valid checkpoint.
- Recovery can identify the latest valid recovery point.
- Existing project memory is never silently overwritten.

## 2. Automatic Session Watcher

**Priority: CRITICAL**

Build an independent background process that monitors project activity and maintains durable session state without relying on an AI agent.

- [x] Implement lightweight background daemon. *(`watch start` / `watch run`; stdlib polling)*
- [x] Monitor configured project directories. *(explicit directories or `--all` registered projects)*
- [x] Detect relevant file changes.
- [x] Detect Git branch and working-tree changes.
- [x] Implement configurable checkpoint intervals.
- [x] Implement debouncing to avoid excessive writes.
- [x] Add automatic checkpoint triggers. *(activity settles, branch/HEAD change, shutdown, changes while stopped)*
- [x] Implement process lifecycle management. *(start/stop/status, one watcher per project via OS lock)*
- [x] Support graceful shutdown. *(stop file + signals; final checkpoint)*
- [~] Recover from unexpected daemon termination. *Detected and reported; offline changes caught on restart. Automatic restart needs a service manager — examples in docs/WATCHER.md, untested.*
- [x] Implement resource-efficient monitoring. *(bounded scan, configurable interval; no native FS events yet)*
- [x] Provide configurable exclusions and ignore patterns.

**Important:** File monitoring does not automatically capture an AI conversation. The watcher must preserve filesystem and project state, while agent integrations provide semantic session context.

**Acceptance criteria:**
- The watcher operates independently of the AI agent.
- Multiple projects can be monitored simultaneously.
- Unexpected termination does not destroy existing checkpoints.
- CPU, memory and disk usage remain minimal.

## 3. Agent Integrations

**Priority: HIGH**

Provide native integrations while maintaining a vendor-independent core.

### OpenAI Codex
- [x] Native skill installation. *(installer: `~/.codex/skills`)*
- [x] Startup recovery instructions. *(`integrate codex` → AGENTS.md block)*
- [~] Session checkpoint integration. *Instruction-based plus `watch`; no Codex hooks wired.*
- [ ] Context compaction handling where supported.
- [~] Scope enforcement. *Advisory (`scope check`); not blocking.*

### Claude Code
- [x] Native skill installation.
- [x] Lifecycle hooks where supported. *(verified end-to-end with Claude Code 2.1.328: SessionStart, PreToolUse, SessionEnd; PreCompact payload-tested)*
- [x] Session recovery. *(report injected at SessionStart)*
- [x] Automatic checkpoint triggers. *(PreCompact, SessionEnd)*
- [x] Scope enforcement. *(PreToolUse blocks protected paths)*

### OpenCode
- [x] Native skill installation.
- [ ] Plugin or event integration. *Not shipped: needs validation against OpenCode's plugin API.*
- [ ] Session lifecycle handling.
- [~] Recovery and checkpoint support. *Instruction-based (AGENTS.md) plus `watch`.*

### Other agents
- [x] Cursor. *(rule file; instruction-only)*
- [x] Windsurf. *(rule file; instruction-only)*
- [x] Gemini CLI. *(GEMINI.md block; instruction-only)*
- [x] Generic AGENTS.md-compatible agents.
- [x] Documented integration SDK for third-party agents. *(docs/INTEGRATIONS.md: CLI contract + generic hook dispatcher)*

**Acceptance criteria:**
- Different agents can share the same project memory.
- Switching agents does not require memory conversion.
- Integrations never overwrite existing user instructions.
- Unsupported lifecycle capabilities are clearly documented.

## 4. Session Recovery System

**Priority: HIGH**

Build a deterministic recovery workflow.

- [x] Detect interrupted sessions.
- [x] Identify the last valid checkpoint.
- [x] Compare checkpoint state against current Git state. *(branch, HEAD, commits since, rewritten history)*
- [x] Detect unfinished tasks. *(unchecked items in NEXT_STEPS.md)*
- [x] Detect potentially unsaved or untracked work. *(uncommitted/untracked files, memory changed since checkpoint; editor buffers are out of reach)*
- [x] Generate a recovery report. *(`recover --format markdown`)*
- [x] Generate an actionable next-step handoff.
- [x] Support recovery from another AI agent. *(scenario test 06)*
- [x] Support manual recovery without an AI agent. *(docs/RECOVERY.md)*

**Acceptance criteria:**

A fresh agent must be able to reconstruct:
- What the project is.
- What objective is currently active.
- What has already been implemented.
- What decisions have been made.
- What must not be changed.
- What remains unfinished.
- What the next action should be.

## 5. Scope Guardian

**Priority: HIGH**

Prevent AI agents from drifting away from the agreed objective.

- [x] Define explicit project scope. *(SCOPE.md sections; `scope show`)*
- [x] Define architectural invariants.
- [x] Track approved scope changes. *(`scope approve`, logged in SCOPE.md)*
- [x] Detect proposed out-of-scope modifications. *(protected path globs: `scope check`, Claude PreToolUse)*
- [x] Maintain a separate parking lot for unrelated ideas. *(`park`)*
- [~] Detect contradictions between instructions and project decisions. *Agent protocol only (SKILL.md); no deterministic detection — this needs semantic judgement.*
- [x] Require user approval for consequential scope changes. *(blocking in Claude Code; advisory elsewhere)*
- [~] Audit implementation against the active objective. *Path-level (`scope check --git`); semantic review is left to the agent.*

**Acceptance criteria:**
- Unrelated ideas are recorded but not implemented.
- Existing architectural decisions are respected.
- Explicit user instructions can change scope.
- Agents can explain why a proposed action is outside scope.

## 6. Multi-Project and Multi-Session Management

**Priority: HIGH**

Support developers working across numerous projects and terminal sessions.

- [x] Implement global project registry.
- [x] Detect project roots. *(parent-directory search)*
- [x] Associate sessions with projects.
- [x] Support multiple simultaneous sessions per project.
- [x] Identify active and interrupted sessions.
- [x] Prevent cross-project memory contamination. *(foreign checkpoints, copied memory, duplicate identities flagged; per-project locks)*
- [x] Provide project/session listing commands.
- [x] Support configurable project aliases.

**Target workflow:**

A developer has ten terminal tabs open, each working on a different project. Closing one terminal must not affect the other nine projects or their memory.

## 7. CLI and Developer Experience

**Priority: MEDIUM**

Build a polished command-line interface.

Commands:

```bash
session-guardian init
session-guardian status
session-guardian projects
session-guardian sessions
session-guardian checkpoint
session-guardian recover
session-guardian audit
session-guardian doctor
session-guardian config
session-guardian uninstall
```

- [x] Consistent command output.
- [x] Human-readable and JSON output. *(`--format text`, recovery Markdown)*
- [x] Useful error messages.
- [x] Configuration management. *(`config`)*
- [x] Logging and diagnostic mode. *(`--verbose`, `SESSION_GUARDIAN_DEBUG`, watcher log)*
- [x] Shell completion. *(bash, zsh, PowerShell)*
- [x] Version and update management. *(`--version`; update = re-run installer, optionally pinned)*
- [x] No unnecessary dependencies. *(standard library only)*

## 8. Universal Installer

**Priority: MEDIUM**

One-command installation should remain a defining feature.

- [x] Linux installer.
- [~] macOS installer. *Same script; macOS run pending CI.*
- [~] Windows PowerShell installer. *Written (`install.ps1`), not yet run on Windows; CI job added.*
- [x] Automatic agent detection.
- [x] Interactive and non-interactive installation.
- [x] Safe upgrades.
- [x] Installation validation.
- [x] Clean uninstall.
- [x] Version pinning.
- [x] Installation tests. *(install.sh; install.ps1 via CI only)*

Target installation:

```bash
curl -fsSL https://raw.githubusercontent.com/nirodg/session-guardian/main/install.sh | bash
```

## 9. Security and Reliability

**Priority: HIGH**

- [x] Protect memory files from accidental corruption.
- [x] Never persist credentials or secrets. *(pattern-based detection; checkpoint refuses high-confidence findings)*
- [x] Add configurable memory permissions.
- [x] Prevent unsafe concurrent writes. *(core operations are serialized by the project lock)*
- [x] Validate imported checkpoints. *(`import-checkpoint`)*
- [~] Protect against malicious repository instructions. *Report frames memory as data and demotes headings; agents must still treat repo content as untrusted.*
- [x] Add recovery and backup documentation.
- [x] Test interrupted writes and process termination.
- [x] Establish security reporting procedures.

## 10. Documentation and Open Source Adoption

**Priority: MEDIUM**

- [x] Publish the correct project hero image.
- [x] Improve README presentation.
- [x] Add architecture documentation.
- [x] Add installation guides for every supported agent. *(README + docs/INTEGRATIONS.md)*
- [ ] Add animated terminal demonstrations. *Needs recording tooling and review of the result.*
- [x] Add real-world recovery examples. *(docs/RECOVERY.md)*
- [x] Add contribution guidelines.
- [x] Add GitHub issue and PR templates.
- [~] Add release workflow and versioning. *Workflow added (tag `v*` → tests → release); not yet run.*
- [x] Publish a roadmap and changelog.

## 11. Testing Strategy

**Priority: CRITICAL** — *done*

Create reproducible scenarios covering:

All 12 are automated in `tests/test_scenarios.py` (`test_01` … `test_12`). Machine restart is simulated by recreating the on-disk state a power loss leaves behind.

1. Normal session shutdown.
2. Unexpected terminal closure.
3. AI agent crash.
4. Machine restart.
5. Context window exhaustion.
6. Switching between AI agents.
7. Concurrent sessions.
8. Multiple projects.
9. Corrupted checkpoint.
10. Conflicting project memory.
11. Git branch changes.
12. Out-of-scope implementation attempts.

Every scenario must have an automated or reproducible integration test.

---

# Implementation Order

| Phase | Deliverable | Priority |
|---|---|---|
| 1 | Core engine hardening | Critical |
| 2 | Automatic Session Watcher | Critical |
| 3 | Crash-safe persistence | Critical |
| 4 | Agent lifecycle integrations | High |
| 5 | Session recovery | High |
| 6 | Scope Guardian | High |
| 7 | Multi-project registry | High |
| 8 | Universal CLI and installers | Medium |
| 9 | Security and cross-platform validation | High |
| 10 | Documentation and community launch | Medium |

# Development Rules

All AI agents contributing to this repository MUST follow these rules:

1. Read `AGENTS.md` and the SessionGuardian core skill before making changes.
2. Work exclusively on the currently approved task.
3. Do not introduce unrelated features or refactoring.
4. Do not duplicate existing functionality.
5. Inspect existing implementations before creating new ones.
6. Add tests for every meaningful behavior change.
7. Update documentation when functionality changes.
8. Never claim completion without verification.
9. Update project memory after meaningful milestones.
10. Preserve backwards compatibility unless explicitly approved otherwise.

Every task must have:
- A clearly defined objective.
- Implementation requirements.
- Acceptance criteria.
- Tests.
- Documented limitations.

**Definition of Done:** Implemented, tested, documented, and verified.

---

# Final Product Vision

SessionGuardian should become a universal persistence and continuity layer for AI-assisted development.

It should not matter whether a developer uses Codex, Claude, OpenCode, Cursor, or an entirely different agent.

The project remains the source of truth.

The agent is replaceable.

The context is persistent.

The scope is protected.

**Never lose context. Never lose direction.**
