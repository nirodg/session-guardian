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

command -v git >/dev/null || { echo "Git is required." >&2; exit 1; }
command -v python3 >/dev/null || { echo "Python 3.9+ is required." >&2; exit 1; }
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,9) else 1)' || { echo "Python 3.9+ is required." >&2; exit 1; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
git clone --depth 1 --branch "$REF" "$REPO_URL" "$tmp/repo" >/dev/null 2>&1 || { echo "Could not download SessionGuardian ($REF)." >&2; exit 1; }
src="$tmp/repo"
[[ -f "$src/skills/session-guardian/SKILL.md" && -f "$src/core/session_guardian.py" ]] || { echo "Invalid package: core or skill missing." >&2; exit 1; }

mkdir -p "$ROOT/skills/session-guardian" "$ROOT/core" "$ROOT/templates" "$BIN"
install -m 0644 "$src/skills/session-guardian/SKILL.md" "$ROOT/skills/session-guardian/SKILL.md"
install -m 0644 "$src/core/session_guardian.py" "$ROOT/core/session_guardian.py"
cp -R "$src/templates/." "$ROOT/templates/"

cat > "$ROOT/session-guardian" <<EOF
#!/usr/bin/env bash
exec python3 "$ROOT/core/session_guardian.py" "\$@"
EOF
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
echo "SessionGuardian installed. Ensure $BIN is on PATH."
echo "Start with: session-guardian init"
