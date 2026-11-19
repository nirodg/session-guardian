#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/nirodg/session-guardian.git"
REF="${SESSION_GUARDIAN_VERSION:-main}"
ROOT="${SESSION_GUARDIAN_HOME:-$HOME/.local/share/session-guardian}"
BIN="${SESSION_GUARDIAN_BIN:-$HOME/.local/bin}"
AGENT="auto"
INIT=0
while (($#)); do
  case "$1" in
    --agent) AGENT="${2:?missing agent}"; shift 2 ;;
    --init) INIT=1; shift ;;
    -h|--help) echo "Usage: install.sh [--agent auto|codex|claude|opencode|generic] [--init]"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

command -v git >/dev/null || { echo "Git is required for installation." >&2; exit 1; }
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
git clone --depth 1 --branch "$REF" "$REPO_URL" "$tmp/repo" >/dev/null 2>&1 || { echo "Could not download SessionGuardian ($REF)." >&2; exit 1; }
src="$tmp/repo"
[[ -f "$src/skills/session-guardian/SKILL.md" ]] || { echo "Invalid package: skill missing." >&2; exit 1; }

mkdir -p "$ROOT/skills/session-guardian" "$ROOT/templates" "$BIN"
install -m 0644 "$src/skills/session-guardian/SKILL.md" "$ROOT/skills/session-guardian/SKILL.md"
cp -R "$src/templates/." "$ROOT/templates/"
cat > "$ROOT/session-guardian" <<'CLI'
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cmd="${1:-help}"; shift || true
case "$cmd" in
  init)
    target="${1:-.}"
    mkdir -p "$target/.session-guardian/checkpoints"
    for name in PROJECT SCOPE ARCHITECTURE DECISIONS CURRENT_STATE SESSION_LOG NEXT_STEPS; do
      file="$target/.session-guardian/$name.md"
      if [[ ! -e "$file" ]]; then cp "$ROOT/templates/$name.md" "$file"; fi
    done
    echo "Initialized .session-guardian (existing files preserved)."
    ;;
  status)
    target="${1:-.}"
    if [[ -d "$target/.session-guardian" ]]; then find "$target/.session-guardian" -maxdepth 2 -type f -print | sort; else echo "No memory found. Run session-guardian init."; fi
    git -C "$target" status --short --branch 2>/dev/null || true
    ;;
  checkpoint)
    target="${1:-.}"; dir="$target/.session-guardian"
    [[ -d "$dir" ]] || { echo "No memory found. Run session-guardian init."; exit 1; }
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    mkdir -p "$dir/checkpoints"
    {
      echo "# Checkpoint $stamp"; echo; echo "- Created (UTC): $stamp"
      echo "- Working directory: $(pwd)"
      echo "- Git status:"; git -C "$target" status --short --branch 2>/dev/null || true
      for f in PROJECT SCOPE CURRENT_STATE NEXT_STEPS; do echo; echo "## $f"; cat "$dir/$f.md"; done
    } > "$dir/checkpoints/$stamp.md"
    echo "Saved $dir/checkpoints/$stamp.md"
    ;;
  recover)
    echo "Read repository instructions and .session-guardian/*.md."
    echo "Inspect Git status, recent commits and source. Reconcile stale memory."
    echo "Report objective, scope, verified state, blockers and exact next action."
    ;;
  doctor)
    echo "Installation: $ROOT"
    echo "Skill: $ROOT/skills/session-guardian/SKILL.md"
    ;;
  help|--help|-h) echo "Usage: session-guardian {init [dir]|status [dir]|checkpoint [dir]|recover|doctor}" ;;
  *) echo "Unknown command: $cmd" >&2; exit 2 ;;
esac
CLI
chmod 0755 "$ROOT/session-guardian"
cat > "$BIN/session-guardian" <<EOF
#!/usr/bin/env bash
exec "$ROOT/session-guardian" "\$@"
EOF
chmod 0755 "$BIN/session-guardian"

install_skill() {
  local destination="$1"
  if [[ -e "$destination/SKILL.md" ]]; then
    echo "Preserving existing skill at $destination/SKILL.md"
  else
    mkdir -p "$destination"
    cp "$ROOT/skills/session-guardian/SKILL.md" "$destination/SKILL.md"
    echo "Installed skill at $destination"
  fi
}
case "$AGENT" in
  auto)
    # Install only into agent directories that already exist; generic is always available.
    found=0
    for d in "$HOME/.agents/skills" "$HOME/.codex/skills" "$HOME/.claude/skills" "$HOME/.config/opencode/skills"; do
      if [[ -d "$d" ]]; then install_skill "$d/session-guardian"; found=1; fi
    done
    if (( ! found )); then install_skill "$HOME/.agents/skills/session-guardian"; fi
    ;;
  codex) install_skill "$HOME/.codex/skills/session-guardian" ;;
  claude) install_skill "$HOME/.claude/skills/session-guardian" ;;
  opencode) install_skill "$HOME/.config/opencode/skills/session-guardian" ;;
  generic) install_skill "$HOME/.agents/skills/session-guardian" ;;
  *) echo "Unknown agent: $AGENT" >&2; exit 2 ;;
esac
if (( INIT )); then "$ROOT/session-guardian" init .; fi
echo "SessionGuardian installed. Ensure $BIN is on PATH; then run: session-guardian init"
