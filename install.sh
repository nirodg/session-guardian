#!/usr/bin/env bash
# SessionGuardian installer for Linux and macOS.
# Safe to re-run: upgrades in place, never overwrites modified skills or foreign files,
# never touches project memory.
set -euo pipefail

REPO_URL="${SESSION_GUARDIAN_REPO:-https://github.com/nirodg/session-guardian.git}"
REF="${SESSION_GUARDIAN_VERSION:-main}"
ROOT="${SESSION_GUARDIAN_HOME:-$HOME/.local/share/session-guardian}"
BIN="${SESSION_GUARDIAN_BIN:-$HOME/.local/bin}"
SOURCE="${SESSION_GUARDIAN_SOURCE:-}"
AGENT="auto"
INIT=0
YES=0
UNINSTALL=0
MARKER="# SessionGuardian wrapper"

usage() {
  cat <<'EOF'
Usage: install.sh [options]

  --agent NAME     auto (default), codex, claude, opencode, generic, or none (core only)
  --version REF    Git tag, branch or commit to install (default: main; env SESSION_GUARDIAN_VERSION)
  --init           run `session-guardian init` in the current directory afterwards
  --yes            non-interactive: do not prompt
  --uninstall      remove the installed tool (project memory is never removed)
  --source DIR     install from a local checkout instead of downloading
  -h, --help       show this help

Environment: SESSION_GUARDIAN_HOME (install dir), SESSION_GUARDIAN_BIN (wrapper dir),
SESSION_GUARDIAN_REPO (Git URL), SESSION_GUARDIAN_SOURCE (local checkout).
EOF
}

while (($#)); do
  case "$1" in
    --agent) AGENT="${2:?missing agent}"; shift 2 ;;
    --version) REF="${2:?missing version}"; shift 2 ;;
    --source) SOURCE="${2:?missing directory}"; shift 2 ;;
    --init) INIT=1; shift ;;
    --yes|-y|--non-interactive) YES=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$AGENT" in auto|codex|claude|opencode|generic|none) ;; *) echo "Unknown agent: $AGENT" >&2; exit 2 ;; esac

command -v python3 >/dev/null || { echo "Python 3.9+ is required." >&2; exit 1; }
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,9) else 1)' || { echo "Python 3.9+ is required." >&2; exit 1; }

if (( UNINSTALL )); then
  [[ -x "$ROOT/session-guardian" ]] || { echo "SessionGuardian is not installed in $ROOT." >&2; exit 1; }
  "$ROOT/session-guardian" uninstall --yes
  for w in "$BIN/session-guardian" "$ROOT/session-guardian"; do
    if [[ -f "$w" ]] && grep -q "$MARKER" "$w"; then rm -f "$w"; fi
  done
  rmdir "$ROOT" 2>/dev/null || true
  echo "SessionGuardian uninstalled. Project memory (.session-guardian/) was not touched."
  exit 0
fi

interactive=0
if (( ! YES )) && [[ -r /dev/tty ]] && [[ -t 1 ]]; then interactive=1; fi
confirm() {  # confirm "question" -> 0 for yes
  (( interactive )) || return 0
  local reply
  printf '%s [Y/n] ' "$1" > /dev/tty
  read -r reply < /dev/tty || reply=""
  [[ -z "$reply" || "$reply" =~ ^[Yy] ]]
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
if [[ -n "$SOURCE" ]]; then
  src="$(cd "$SOURCE" && pwd)"
else
  command -v git >/dev/null || { echo "Git is required." >&2; exit 1; }
  if ! git clone --quiet --depth 1 --branch "$REF" "$REPO_URL" "$tmp/repo" 2>/dev/null; then
    # A commit SHA cannot be cloned with --branch; fetch it explicitly.
    rm -rf "$tmp/repo"
    git init --quiet "$tmp/repo" && git -C "$tmp/repo" remote add origin "$REPO_URL" \
      && git -C "$tmp/repo" fetch --quiet --depth 1 origin "$REF" && git -C "$tmp/repo" checkout --quiet FETCH_HEAD \
      || { echo "Could not download SessionGuardian ($REF) from $REPO_URL." >&2; exit 1; }
  fi
  src="$tmp/repo"
fi
for f in core/session_guardian.py skills/session-guardian/SKILL.md templates/SCOPE.md; do
  [[ -f "$src/$f" ]] || { echo "Invalid package: $f missing." >&2; exit 1; }
done
python3 "$src/core/session_guardian.py" doctor >/dev/null 2>&1 || { echo "Invalid package: core does not run." >&2; exit 1; }
version="$(python3 "$src/core/session_guardian.py" --version 2>/dev/null || echo "session-guardian $REF")"

# ---- stage, then swap each component into place (an interrupted upgrade leaves the old or new copy, never a mix)
mkdir -p "$ROOT" "$BIN"
stage="$ROOT/.install-staging"
rm -rf "$stage"
mkdir -p "$stage/core" "$stage/skills/session-guardian" "$stage/templates"
cp "$src/core/session_guardian.py" "$stage/core/session_guardian.py"
cp "$src/skills/session-guardian/SKILL.md" "$stage/skills/session-guardian/SKILL.md"
cp -R "$src/templates/." "$stage/templates/"
chmod 0644 "$stage/core/session_guardian.py" "$stage/skills/session-guardian/SKILL.md"
for component in core skills templates; do
  rm -rf "$ROOT/$component.old"
  if [[ -e "$ROOT/$component" ]]; then mv "$ROOT/$component" "$ROOT/$component.old"; fi
  mv "$stage/$component" "$ROOT/$component"
  rm -rf "$ROOT/$component.old"
done
rm -rf "$stage"

write_wrapper() {  # write_wrapper path command
  local path="$1" target="$2"
  if [[ -e "$path" ]] && ! grep -q "$MARKER" "$path"; then
    echo "Not overwriting $path: it was not created by SessionGuardian." >&2
    return 1
  fi
  printf '#!/usr/bin/env bash\n%s\nexec %s "$@"\n' "$MARKER" "$target" > "$path.tmp"
  chmod 0755 "$path.tmp"
  mv "$path.tmp" "$path"
}
write_wrapper "$ROOT/session-guardian" "python3 \"$ROOT/core/session_guardian.py\""
bin_ok=1
write_wrapper "$BIN/session-guardian" "\"$ROOT/session-guardian\"" || bin_ok=0

# ---- skills: upgrade only copies that are unmodified since we installed them
previous="$ROOT/install-manifest.json"
sha() { python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$1"; }
recorded_sha() {  # recorded_sha skill_dir
  [[ -f "$previous" ]] || return 0
  python3 - "$previous" "$1" <<'PY'
import json, sys
try:
    m = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
for s in m.get("skills", []):
    if s.get("path") == sys.argv[2]:
        print(s.get("sha256", ""))
PY
}
installed_skills=()
install_skill() {
  local destination="$1" file="$1/SKILL.md"
  if [[ -e "$file" ]]; then
    local current recorded
    current="$(sha "$file")"
    recorded="$(recorded_sha "$destination")"
    if [[ "$current" == "$(sha "$ROOT/skills/session-guardian/SKILL.md")" ]]; then
      echo "Skill up to date at $destination"
    elif [[ -n "$recorded" && "$current" == "$recorded" ]]; then
      cp "$ROOT/skills/session-guardian/SKILL.md" "$file"
      echo "Upgraded skill at $destination"
    else
      echo "Preserving existing skill at $file (modified or not installed by SessionGuardian)"
      return 0
    fi
  else
    mkdir -p "$destination"
    cp "$ROOT/skills/session-guardian/SKILL.md" "$file"
    echo "Installed skill at $destination"
  fi
  installed_skills+=("$destination")
}
targets=()
case "$AGENT" in
  auto)
    for d in "$HOME/.agents/skills" "$HOME/.codex/skills" "$HOME/.claude/skills" "$HOME/.config/opencode/skills"; do
      [[ -d "$d" ]] && targets+=("$d/session-guardian")
    done
    (( ${#targets[@]} )) || targets+=("$HOME/.agents/skills/session-guardian")
    ;;
  codex) targets+=("$HOME/.codex/skills/session-guardian") ;;
  claude) targets+=("$HOME/.claude/skills/session-guardian") ;;
  opencode) targets+=("$HOME/.config/opencode/skills/session-guardian") ;;
  generic) targets+=("$HOME/.agents/skills/session-guardian") ;;
  none) ;;
esac
if (( ${#targets[@]} )); then
  if (( interactive )); then
    echo "The SessionGuardian skill will be installed into:"
    printf '  %s\n' "${targets[@]}"
  fi
  if confirm "Install the agent skill there?"; then
    for t in "${targets[@]}"; do install_skill "$t"; done
  fi
fi
# Keep skills recorded by a previous install that this run did not touch, so uninstall can still find them.
python3 - "$ROOT" "$BIN" "$REF" "$version" "$previous" "${installed_skills[@]+"${installed_skills[@]}"}" <<'PY'
import datetime, hashlib, json, os, sys
root, bin_dir, ref, version, previous, *skills = sys.argv[1:]
def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()
entries = {}
try:
    for s in json.load(open(previous)).get("skills", []):
        if os.path.isfile(os.path.join(s["path"], "SKILL.md")):
            entries[s["path"]] = s
except Exception:
    pass
for d in skills:
    entries[d] = {"path": d, "sha256": sha(os.path.join(d, "SKILL.md"))}
files = [os.path.join(root, n) for n in ("core", "skills", "templates", "session-guardian")]
wrapper = os.path.join(bin_dir, "session-guardian")
if os.path.isfile(wrapper) and "# SessionGuardian wrapper" in open(wrapper).read():
    files.append(wrapper)
manifest = {"format_version": 1, "version": version.split()[-1], "ref": ref, "installed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "root": root, "files": files, "skills": sorted(entries.values(), key=lambda s: s["path"])}
tmp = previous + ".tmp"
with open(tmp, "w") as f:
    json.dump(manifest, f, indent=2)
os.replace(tmp, previous)
PY

# ---- validate
if ! "$ROOT/session-guardian" doctor > "$tmp/doctor.json" 2>&1; then
  echo "Installation validation failed:" >&2
  cat "$tmp/doctor.json" >&2
  exit 1
fi
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d.get("python_supported") else 1)' "$tmp/doctor.json" \
  || { echo "Installation validation failed: unsupported Python." >&2; exit 1; }

echo "SessionGuardian $version installed in $ROOT."
if (( bin_ok )); then
  case ":$PATH:" in
    *":$BIN:"*) ;;
    *) echo "Add $BIN to PATH to use 'session-guardian' (e.g. export PATH=\"$BIN:\$PATH\")." ;;
  esac
else
  echo "Use $ROOT/session-guardian directly, or remove the conflicting $BIN/session-guardian."
fi
if (( INIT )); then "$ROOT/session-guardian" init .; fi
echo "Next: cd into a project and run 'session-guardian init', then 'session-guardian integrate <agent>'."
