# Contributing

Help make AI coding sessions recoverable and focused.

**Principles:** agent-neutral core; portable Markdown memory; standard library only; safe, idempotent installation; never overwrite user instructions or memory; evidence over assumptions; scope protection without blocking explicit user direction.

## Workflow

1. Read `AGENTS.md`, `README.md`, `skills/session-guardian/SKILL.md` and `docs/ARCHITECTURE.md`.
2. Pick one roadmap item (`docs/ROADMAP.md`) or issue. Keep the change focused; no unrelated refactors.
3. Add tests for every behaviour change: `python -m unittest discover -s tests -v`, and before pushing `ci/local-ci.sh --committed` (clean containers, Python 3.9–3.13; see docs/CI.md). Tests must not touch the real home directory (import `tests/_support.py`).
4. Update documentation and the changelog.
5. Preserve backwards compatibility of memory files, manifests and JSON output keys unless the change is explicitly approved.

**Definition of done:** implemented, tested, documented and verified. Never claim an integration works until it has been tested against a named agent version.

## New agent adapters

Document install location, discovery, lifecycle hooks, upgrade and removal behaviour, and a reproducible validation. Unsupported lifecycle capabilities must be stated plainly in `docs/INTEGRATIONS.md`.

Exclude credentials and private project data from issues, pull requests and test fixtures.
