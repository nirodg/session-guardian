# Next Steps

Prioritize actionable tasks. Include expected result and dependencies where useful.

## Critical / high priority
- [ ] Resolve the GitHub Actions billing lock and get the CI matrix green on macOS and Windows (validates msvcrt locking, install.ps1, watcher on Windows).
- [ ] Tag v0.3.0 once CI is green (release workflow runs on the tag).

## Normal priority
- [ ] OpenCode plugin integration, validated against a named OpenCode version.
- [ ] Codex lifecycle integration (compaction / session hooks) if Codex exposes them.
- [ ] Animated terminal demos for the README.
- [ ] Verify PreCompact end-to-end in Claude Code.
- [ ] Test the watcher service examples (systemd, launchd, Task Scheduler).

## Out of scope / parking lot
- Ideas to revisit only with user approval.
- Native filesystem events (inotify/FSEvents/ReadDirectoryChangesW) for the watcher — needs dependencies or per-OS code.
