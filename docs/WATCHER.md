# Session watcher

`session-guardian watch` keeps durable project state without relying on an agent. It polls the project tree, the memory files and Git, and writes a checkpoint (with an `activity` record: trigger, reason, changed paths) once activity settles.

```bash
session-guardian watch start            # detached background process for this project
session-guardian watch start --all      # every registered project (one process each)
session-guardian watch status
session-guardian watch stop             # graceful: final checkpoint if anything is pending
session-guardian watch run              # foreground (for service managers)
session-guardian watch run --once       # checkpoint if anything changed since the last run, then exit (cron)
```

Behaviour:

- **Debounce:** a checkpoint is written only after `watch.debounce` seconds without further changes.
- **Rate limit:** at most one checkpoint per `watch.min_checkpoint_interval`, except branch switches and new commits, which checkpoint as soon as the debounce passes.
- **Exclusions:** `watch.ignore` (glob patterns matched against names and relative paths). `.session-guardian/` is ignored except the memory files themselves, so the watcher never triggers itself.
- **Bound:** at most `watch.max_files` files are scanned; a warning is logged if the limit is reached.
- **One watcher per project**, enforced by an OS lock. Stopping one project's watcher never affects another.
- **Crash safety:** killing the watcher cannot damage checkpoints. On the next start it notices the unclean shutdown and checks for changes made while it was not running.
- Logs go to `.session-guardian/watch.log` (rotated at 1 MB).

What it does **not** do: capture conversations or editor buffers. Agents still need to write meaning into memory files; the watcher makes sure what is on disk gets checkpointed.

## Start on login

The watcher is a plain foreground process under `watch run`, so any service manager can supervise it.

**systemd (Linux, user service)** — `~/.config/systemd/user/session-guardian@.service`:

```ini
[Unit]
Description=SessionGuardian watcher for %I

[Service]
ExecStart=%h/.local/bin/session-guardian watch run %I
Restart=on-failure

[Install]
WantedBy=default.target
```

`systemctl --user enable --now "session-guardian@$(systemd-escape -p ~/code/my-project).service"`

**launchd (macOS)** — `~/Library/LaunchAgents/dev.session-guardian.my-project.plist` with `ProgramArguments` = `session-guardian watch run /path/to/project`, `RunAtLoad` and `KeepAlive` = true; load with `launchctl load`.

**Windows Task Scheduler** — a task triggered "At log on" running `session-guardian.cmd watch run C:\path\to\project`.

These service definitions are examples; they have not been tested as part of the test suite.
