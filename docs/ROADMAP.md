# SessionGuardian — Remaining Tasks & Implementation Roadmap

**Vision:** The ultimate agent-agnostic session persistence, recovery, and scope-protection system for AI-assisted software development.

**Repository:** https://github.com/nirodg/session-guardian

**Core principle:** Never lose context. Never lose direction.

Status legend: `[x]` implemented and tested · `[~]` partially implemented (see note) · `[ ]` not started.

---

## 1. Core Engine Hardening

**Priority: CRITICAL** — *in progress*

The core engine must become the reliable foundation independent of any AI agent.

- [x] Review and validate existing Python core implementation.
- [x] Implement robust atomic checkpoint operations. *(staging directory + single rename publish)*
- [x] Add checkpoint versioning and migration support. *(manifest v2; v1 read in place; newer formats rejected with upgrade hint)*
- [x] Implement checkpoint rotation and configurable retention. *(`--keep`, `prune`, `config.json` `retention.keep`; off by default)*
- [x] Add recovery-point selection and validation. *(newest valid checkpoint; `recover --checkpoint ID`)*
- [x] Implement crash-safe writes and filesystem locking. *(fsync + atomic rename; `flock` / `msvcrt.locking`)*
- [x] Detect corrupted, incomplete, or inconsistent memory.
- [~] Add memory conflict detection and reconciliation. *Detection done (merge-conflict markers, memory changed since checkpoint). Reconciliation not implemented.*
- [x] Implement project fingerprinting and identity verification. *(project_id in manifests; Git root-commit fingerprint)*
- [x] Add comprehensive unit and integration tests. *(35 tests, including real process kills while locked and mid-checkpoint)*
- [ ] Verify cross-platform behavior on Linux, macOS and Windows. *Verified locally on Linux with Python 3.9, 3.11, 3.12. macOS and Windows not yet run: GitHub Actions jobs are not starting (account billing lock).*

**Acceptance criteria:**
- No checkpoint operation can silently corrupt existing memory.
- Interrupted writes cannot replace the last valid checkpoint.
- Recovery can identify the latest valid recovery point.
- Existing project memory is never silently overwritten.

## 2. Automatic Session Watcher

**Priority: CRITICAL**

Build an independent background process that monitors project activity and maintains durable session state without relying on an AI agent.

- [ ] Implement lightweight background daemon.
- [ ] Monitor configured project directories.
- [ ] Detect relevant file changes.
- [ ] Detect Git branch and working-tree changes.
- [ ] Implement configurable checkpoint intervals.
- [ ] Implement debouncing to avoid excessive writes.
- [ ] Add automatic checkpoint triggers.
- [ ] Implement process lifecycle management.
- [ ] Support graceful shutdown.
- [ ] Recover from unexpected daemon termination.
- [ ] Implement resource-efficient monitoring.
- [ ] Provide configurable exclusions and ignore patterns.

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
- [ ] Native skill installation.
- [ ] Startup recovery instructions.
- [ ] Session checkpoint integration.
- [ ] Context compaction handling where supported.
- [ ] Scope enforcement.

### Claude Code
- [ ] Native skill installation.
- [ ] Lifecycle hooks where supported.
- [ ] Session recovery.
- [ ] Automatic checkpoint triggers.
- [ ] Scope enforcement.

### OpenCode
- [ ] Native skill installation.
- [ ] Plugin or event integration.
- [ ] Session lifecycle handling.
- [ ] Recovery and checkpoint support.

### Other agents
- [ ] Cursor.
- [ ] Windsurf.
- [ ] Gemini CLI.
- [ ] Generic AGENTS.md-compatible agents.
- [ ] Documented integration SDK for third-party agents.

**Acceptance criteria:**
- Different agents can share the same project memory.
- Switching agents does not require memory conversion.
- Integrations never overwrite existing user instructions.
- Unsupported lifecycle capabilities are clearly documented.

## 4. Session Recovery System

**Priority: HIGH**

Build a deterministic recovery workflow.

- [ ] Detect interrupted sessions.
- [x] Identify the last valid checkpoint.
- [~] Compare checkpoint state against current Git state. *HEAD and branch drift reported; no working-tree diff yet.*
- [ ] Detect unfinished tasks.
- [ ] Detect potentially unsaved or untracked work.
- [ ] Generate a recovery report.
- [ ] Generate an actionable next-step handoff.
- [ ] Support recovery from another AI agent.
- [ ] Support manual recovery without an AI agent.

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

- [ ] Define explicit project scope.
- [ ] Define architectural invariants.
- [ ] Track approved scope changes.
- [ ] Detect proposed out-of-scope modifications.
- [ ] Maintain a separate parking lot for unrelated ideas.
- [ ] Detect contradictions between instructions and project decisions.
- [ ] Require user approval for consequential scope changes.
- [ ] Audit implementation against the active objective.

**Acceptance criteria:**
- Unrelated ideas are recorded but not implemented.
- Existing architectural decisions are respected.
- Explicit user instructions can change scope.
- Agents can explain why a proposed action is outside scope.

## 6. Multi-Project and Multi-Session Management

**Priority: HIGH**

Support developers working across numerous projects and terminal sessions.

- [ ] Implement global project registry.
- [ ] Detect project roots.
- [ ] Associate sessions with projects.
- [ ] Support multiple simultaneous sessions per project.
- [ ] Identify active and interrupted sessions.
- [~] Prevent cross-project memory contamination. *Checkpoints from another project and memory copied from another Git repository are flagged by `audit`.*
- [ ] Provide project/session listing commands.
- [ ] Support configurable project aliases.

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

- [ ] Consistent command output.
- [ ] Human-readable and JSON output.
- [ ] Useful error messages.
- [ ] Configuration management.
- [ ] Logging and diagnostic mode.
- [ ] Shell completion.
- [ ] Version and update management.
- [ ] No unnecessary dependencies.

## 8. Universal Installer

**Priority: MEDIUM**

One-command installation should remain a defining feature.

- [ ] Linux installer.
- [ ] macOS installer.
- [ ] Windows PowerShell installer.
- [ ] Automatic agent detection.
- [ ] Interactive and non-interactive installation.
- [ ] Safe upgrades.
- [ ] Installation validation.
- [ ] Clean uninstall.
- [ ] Version pinning.
- [ ] Installation tests.

Target installation:

```bash
curl -fsSL https://raw.githubusercontent.com/nirodg/session-guardian/main/install.sh | bash
```

## 9. Security and Reliability

**Priority: HIGH**

- [ ] Protect memory files from accidental corruption.
- [ ] Never persist credentials or secrets.
- [ ] Add configurable memory permissions.
- [x] Prevent unsafe concurrent writes. *(core operations are serialized by the project lock)*
- [~] Validate imported checkpoints. *Manifests are validated (format, file names, hashes, project id); there is no import command yet.*
- [ ] Protect against malicious repository instructions.
- [ ] Add recovery and backup documentation.
- [x] Test interrupted writes and process termination.
- [ ] Establish security reporting procedures.

## 10. Documentation and Open Source Adoption

**Priority: MEDIUM**

- [x] Publish the correct project hero image.
- [ ] Improve README presentation.
- [ ] Add architecture documentation.
- [ ] Add installation guides for every supported agent.
- [ ] Add animated terminal demonstrations.
- [ ] Add real-world recovery examples.
- [ ] Add contribution guidelines.
- [ ] Add GitHub issue and PR templates.
- [ ] Add release workflow and versioning.
- [x] Publish a roadmap and changelog. *(roadmap published; changelog pending)*

## 11. Testing Strategy

**Priority: CRITICAL**

Create reproducible scenarios covering:

1. Normal session shutdown.
2. Unexpected terminal closure.
3. AI agent crash.
4. Machine restart.
5. Context window exhaustion.
6. Switching between AI agents.
7. Concurrent sessions.
8. Multiple projects.
9. Corrupted checkpoint. *(covered)*
10. Conflicting project memory. *(covered: merge-conflict markers, foreign project checkpoints)*
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
