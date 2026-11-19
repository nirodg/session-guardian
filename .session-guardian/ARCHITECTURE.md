# Architecture

Document only verified facts. Full description: docs/ARCHITECTURE.md.

## System overview
Agents → (instruction blocks / Claude Code hooks) → CLI `session-guardian` → single-file core `core/session_guardian.py` → per-project `.session-guardian/` + global registry in the data home.

## Components and responsibilities
- core/session_guardian.py: checkpoints, verification, locking, sessions, watcher, scope, recovery report, registry, integrations, CLI.
- install.sh (tested) / install.ps1 (experimental, CI only): installation, upgrades, uninstall.
- skills/session-guardian/SKILL.md: agent protocol.
- templates/: initial memory files.

## Data and control flows
See docs/ARCHITECTURE.md "Data flow: a Claude Code session" and "Failure model".

## External services / integrations
Git (optional, subprocess). Claude Code hooks via .claude/settings.json. No network access at runtime.

## Build, test, deployment
`python -m unittest discover -s tests -v`. CI: .github/workflows/tests.yml (Linux/macOS/Windows × Python 3.9/3.12, installer smoke tests). Release: tag `v<version>` → .github/workflows/release.yml.
