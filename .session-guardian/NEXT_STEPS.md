# Next Steps

Prioritize actionable tasks. Include expected result and dependencies where useful.

## Critical / high priority
- [ ] Enable AppVeyor for the repo and get Windows + macOS green (validates msvcrt locking, install.ps1, watcher on Windows). See docs/CI.md.
- [ ] Ask GitHub Support to clear the Actions billing lock (public repo: Actions should be free).
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
