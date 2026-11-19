#!/usr/bin/env bash
# Install a pre-push hook that runs the local CI on exactly what is being pushed.
# Never overwrites an existing hook that SessionGuardian did not create.
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
hook="$(git -C "$repo" rev-parse --git-path hooks)/pre-push"
[[ "$hook" = /* ]] || hook="$repo/$hook"
marker="# session-guardian local-ci hook"
if [[ -e "$hook" ]] && ! grep -q "$marker" "$hook"; then
  echo "A different pre-push hook already exists at $hook; not overwriting it." >&2
  echo "Add this line to it instead: \"$repo/ci/local-ci.sh\" --committed" >&2
  exit 1
fi
cat > "$hook" <<HOOK
#!/usr/bin/env bash
$marker
# Skip once with: git push --no-verify
exec "$repo/ci/local-ci.sh" --committed \${SG_CI_ARGS:-}
HOOK
chmod +x "$hook"
echo "Installed $hook. Pushes now run ci/local-ci.sh --committed (skip once with --no-verify)."
echo "To also publish a GitHub commit status: export SG_CI_ARGS=--publish-status"
