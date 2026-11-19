#!/usr/bin/env bash
# Free, self-hosted CI for SessionGuardian: runs the test suite in clean Docker
# containers (one per Python version, in parallel) plus an installer smoke test.
#
#   ci/local-ci.sh                     # test the working tree on all versions
#   ci/local-ci.sh --committed         # test exactly HEAD (what you would push)
#   ci/local-ci.sh --versions "3.9 3.13"
#   ci/local-ci.sh --committed --publish-status   # also set a commit status on GitHub (needs gh auth)
#
# Covers Linux only. Windows and macOS run on AppVeyor (appveyor.yml).
set -euo pipefail

VERSIONS="3.9 3.10 3.11 3.12 3.13"
COMMITTED=0
PUBLISH=0
SMOKE=1
while (($#)); do
  case "$1" in
    --versions) VERSIONS="${2:?}"; shift 2 ;;
    --committed) COMMITTED=1; shift ;;
    --publish-status) PUBLISH=1; shift ;;
    --no-smoke) SMOKE=0; shift ;;
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

repo="$(cd "$(dirname "$0")/.." && pwd)"
command -v docker >/dev/null || { echo "Docker is required." >&2; exit 1; }
logs="${CI_LOG_DIR:-$repo/.ci-logs}"
rm -rf "$logs"; mkdir -p "$logs"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

if (( COMMITTED )); then
  sha="$(git -C "$repo" rev-parse HEAD)"
  git -C "$repo" archive --format=tar HEAD | tar -x -C "$work"
  # The installer's version-pin test clones the repository, so ship the history too.
  git clone --quiet --no-local "$repo" "$work/.git-src" && mv "$work/.git-src/.git" "$work/.git" && rm -rf "$work/.git-src"
  src="$work"
  label="HEAD ${sha:0:12}"
else
  sha="$(git -C "$repo" rev-parse HEAD 2>/dev/null || echo unknown)"
  src="$repo"
  label="working tree"
  [[ -z "$(git -C "$repo" status --porcelain 2>/dev/null)" ]] || label="working tree (uncommitted changes)"
fi
chmod -R a+rX "$src"

status() {  # status state description
  (( PUBLISH )) || return 0
  if (( ! COMMITTED )); then echo "--publish-status requires --committed" >&2; return 0; fi
  gh api --silent -X POST "repos/{owner}/{repo}/statuses/$sha" \
    -f state="$1" -f context="local-ci/linux" -f description="$2" >/dev/null 2>&1 \
    || echo "warning: could not publish commit status" >&2
}

echo "Local CI: $label"
status pending "Running on $(hostname)"

echo "Building images (cached after the first run)…"
for v in $VERSIONS; do
  docker build -q --build-arg "PY=$v" -t "sg-ci:py$v" "$repo/ci" >/dev/null &
done
wait

run_tests() {  # run_tests version
  docker run --rm --network none -v "$src:/src:ro" "sg-ci:py$1" \
    bash -c 'cp -r /src ~/repo && cd ~/repo && python -m unittest discover -s tests' >"$logs/py$1.log" 2>&1
}
run_smoke() {
  docker run --rm --network none -v "$src:/src:ro" "sg-ci:py3.12" bash -euc '
    cp -r /src ~/repo && cd ~/repo
    bash install.sh --source . --yes --agent generic
    export PATH="$HOME/.local/bin:$PATH"
    session-guardian doctor >/dev/null
    mkdir ~/proj && cd ~/proj && git init -q
    session-guardian init >/dev/null
    session-guardian checkpoint >/dev/null
    session-guardian audit >/dev/null
    session-guardian recover --format markdown | head -1
    session-guardian watch start --interval 0.5 >/dev/null
    session-guardian watch stop >/dev/null
    bash ~/repo/install.sh --uninstall
    test ! -e ~/.local/bin/session-guardian
    test ! -e ~/.local/share/session-guardian/core
    test -f ~/proj/.session-guardian/SCOPE.md
    echo "smoke: all checks passed"
  ' >"$logs/install-smoke.log" 2>&1
}

start=$SECONDS
declare -A pids
for v in $VERSIONS; do run_tests "$v" & pids["py$v"]=$!; done
(( SMOKE )) && { run_smoke & pids["install-smoke"]=$!; }

failed=0
printf '\n%-16s %s\n' JOB RESULT
for job in $(printf '%s\n' "${!pids[@]}" | sort -V); do
  if wait "${pids[$job]}"; then
    printf '%-16s %s\n' "$job" "ok   $(grep -Eo '^Ran [0-9]+ tests' "$logs/$job.log" || true)"
  else
    printf '%-16s %s\n' "$job" "FAIL (see $logs/$job.log)"
    failed=1
  fi
done
echo "Finished in $((SECONDS - start))s. Logs: $logs"

if (( failed )); then
  status failure "Linux tests failed"
  exit 1
fi
status success "Linux: Python ${VERSIONS// /, } + installer"
