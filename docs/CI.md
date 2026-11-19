# Continuous integration without paid GitHub Actions

GitHub Actions is configured (`.github/workflows/`) but currently cannot run on this account. CI runs on free alternatives instead:

| Platform | Where | Cost | Status |
|---|---|---|---|
| Linux, Python 3.9–3.13, installer smoke test | Your machine, Docker (`ci/local-ci.sh`) | Free | Working |
| Windows (Python 3.9, 3.12, `install.ps1`), macOS | AppVeyor open-source plan (`appveyor.yml`) | Free for public repos (1 concurrent job) | Configured; needs enabling and a first run |
| Everything above | GitHub Actions | Free for public repos once the account lock is cleared | Blocked |

## Local CI (Linux)

Requires Docker. Each Python version runs in parallel in a clean container: non-root user, no network, read-only source.

```bash
ci/local-ci.sh                        # working tree, all versions (~40 s once images are cached)
ci/local-ci.sh --committed            # exactly HEAD, i.e. what you would push
ci/local-ci.sh --versions "3.9 3.13" --no-smoke
```

Logs land in `.ci-logs/` (ignored by Git). The exit code is non-zero if any job fails.

**Run it on every push:**

```bash
ci/install-git-hook.sh                # installs .git/hooks/pre-push (never replaces a foreign hook)
git push --no-verify                  # skip once
```

**Show results on GitHub:** `--publish-status` (with `--committed`) sets a `local-ci/linux` commit status through the GitHub API using your `gh` login. Commit statuses do not use Actions, so they work even while Actions is locked. Enable it for the hook with `export SG_CI_ARGS=--publish-status`.

## AppVeyor (Windows and macOS)

1. Sign in at https://ci.appveyor.com with GitHub and add `nirodg/session-guardian`. The open-source plan applies to public repositories.
2. Pushes and pull requests then build `appveyor.yml`: the full suite on Windows (Python 3.9 and 3.12) and macOS, plus install → use → uninstall smoke tests with `install.ps1` and `install.sh`.
3. AppVeyor reports its own commit status on GitHub.

The configuration has not run yet. Expect to adjust image names or Python paths on the first build.

## Self-hosting Windows

macOS cannot be self-hosted on non-Apple hardware. Windows can run in a local VM (VirtualBox or libvirt with a Windows evaluation image) as a self-hosted AppVeyor or GitLab runner if AppVeyor's queue is too slow. This is not set up.

## Unblocking GitHub Actions

Actions on public repositories is free, and community reports say a billing lock blocks self-hosted runners too. The lock usually comes from a failed payment authorization. A GitHub Support ticket can often clear it without paying.
