#!/usr/bin/env python3
"""SessionGuardian deterministic local core. Python 3.9+, standard library only.

Guarantees provided by this module (see README "Core engine guarantees"):

* Checkpoints are built in a hidden staging directory and published with a single
  atomic directory rename. An interrupted checkpoint never appears as a recovery
  point and never replaces an earlier one.
* Every mutating operation holds an OS-level lock on ``.session-guardian/.lock``.
  The OS releases the lock if the process dies, so a crash cannot leave a stuck lock.
* Memory files are never overwritten. ``init`` only creates files that are missing.
* Recovery selects the newest checkpoint that passes full integrity verification.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

MEMORY = ("PROJECT", "SCOPE", "ARCHITECTURE", "DECISIONS", "CURRENT_STATE", "SESSION_LOG", "NEXT_STEPS")
MEMORY_FILES = tuple(n + ".md" for n in MEMORY)
FORMAT_VERSION = 2  # manifest format written by this version
SUPPORTED_MANIFEST_VERSIONS = (1, 2)  # formats this version can read and verify
IDENTITY_VERSION = 1
LOCK_NAME = ".lock"
CONFIG_NAME = "config.json"
STAGING_PREFIX = ".staging-"
TRASH_PREFIX = ".trash-"
DEFAULT_LOCK_TIMEOUT = 30.0
GITIGNORE_BODY = "# SessionGuardian runtime files\n.lock\ncheckpoints/.staging-*\ncheckpoints/.trash-*\n"


class GuardianError(Exception):
    """A user-facing error. The CLI prints the message and exits with status 2."""


class LockTimeout(GuardianError):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fsync_dir(path: Path) -> None:
    """Persist directory entries (renames/creations). Not supported on Windows; ignored there."""
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def write_durable(path: Path, data: bytes) -> None:
    """Write a new file and fsync it. Opened for writing, so fsync also works on Windows."""
    with path.open("wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def atomic_write(path: Path, data: bytes) -> None:
    """Replace ``path`` atomically: readers see either the old or the new content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        fsync_dir(path.parent)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def create_new(path: Path, data: bytes) -> bool:
    """Atomically create ``path`` only if it does not exist. Never overwrites. Returns True if created."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.link(tmp, path)  # fails if path exists: no window in which existing content is replaced
            created = True
        except FileExistsError:
            created = False
        except OSError:
            # Filesystem without hard links (e.g. FAT): exclusive create, then copy the content in.
            try:
                with path.open("xb") as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
                created = True
            except FileExistsError:
                created = False
        if created:
            fsync_dir(path.parent)
        return created
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp)


# --------------------------------------------------------------------------- locking

@contextlib.contextmanager
def project_lock(md: Path, timeout: float = DEFAULT_LOCK_TIMEOUT):
    """Exclusive inter-process lock. Released by the OS if the holder crashes."""
    md.mkdir(parents=True, exist_ok=True)
    f = open(md / LOCK_NAME, "a+b")
    try:
        if os.name == "nt":
            import msvcrt

            def try_lock():
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)

            def unlock():
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            def try_lock():
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

            def unlock():
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            try:
                try_lock()
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise LockTimeout(f"Another SessionGuardian process holds {md / LOCK_NAME}; gave up after {timeout:g}s.")
                time.sleep(0.05)
        try:
            yield
        finally:
            with contextlib.suppress(OSError):
                unlock()
    finally:
        f.close()


# --------------------------------------------------------------------------- project state

def run_git(root: Path, *args: str):
    try:
        p = subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True, timeout=5)
        return p.stdout.strip() if p.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def git_info(root: Path):
    return {"branch": run_git(root, "branch", "--show-current"), "status": run_git(root, "status", "--short"), "head": run_git(root, "rev-parse", "HEAD")}


def git_root_commits(root: Path):
    out = run_git(root, "rev-list", "--max-parents=0", "HEAD")
    return sorted(out.split()) if out else []


def memory_dir(root: Path) -> Path:
    return root / ".session-guardian"


def checkpoints_dir(root: Path) -> Path:
    return memory_dir(root) / "checkpoints"


def require_initialized(root: Path) -> Path:
    md = memory_dir(root)
    if not md.is_dir():
        raise GuardianError("No .session-guardian directory. Run: session-guardian init")
    return md


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_identity(root: Path):
    """Return (identity dict or None, problem string or None)."""
    p = memory_dir(root) / "identity.json"
    if not p.is_file():
        return None, "missing: identity.json"
    try:
        ident = load_json(p)
    except (OSError, ValueError) as e:
        return None, f"invalid identity.json: {e}"
    if not isinstance(ident, dict) or not isinstance(ident.get("project_id"), str):
        return None, "invalid identity.json: project_id missing"
    return ident, None


def read_config(root: Path) -> dict:
    p = memory_dir(root) / CONFIG_NAME
    if not p.is_file():
        return {}
    try:
        cfg = load_json(p)
    except (OSError, ValueError) as e:
        raise GuardianError(f"Invalid {p}: {e}")
    if not isinstance(cfg, dict):
        raise GuardianError(f"Invalid {p}: expected a JSON object")
    return cfg


def retention_from_config(root: Path):
    keep = read_config(root).get("retention", {}).get("keep")
    if keep is None:
        return None
    if not isinstance(keep, int) or isinstance(keep, bool) or keep < 0:
        raise GuardianError("config.json retention.keep must be a non-negative integer (0 = unlimited)")
    return keep


# --------------------------------------------------------------------------- init

def init(root: Path) -> dict:
    root = root.resolve()
    md = memory_dir(root)
    md.mkdir(parents=True, exist_ok=True)
    with project_lock(md):
        (md / "checkpoints").mkdir(exist_ok=True)
        templates = Path(__file__).resolve().parent.parent / "templates"
        created, upgraded = [], []
        for name in MEMORY:
            src = templates / (name + ".md")
            body = src.read_bytes() if src.is_file() else f"# {name.replace('_', ' ').title()}\n\nUNKNOWN\n".encode()
            if create_new(md / (name + ".md"), body):
                created.append(name + ".md")
        if create_new(md / ".gitignore", GITIGNORE_BODY.encode()):
            created.append(".gitignore")
        roots = git_root_commits(root)
        ident_path = md / "identity.json"
        fresh = {"format_version": IDENTITY_VERSION, "project_id": str(uuid.uuid4()), "created_at": now(), "fingerprint": {"git_root_commits": roots}}
        if create_new(ident_path, (json.dumps(fresh, indent=2) + "\n").encode()):
            created.append("identity.json")
        else:
            # Additive, non-destructive upgrade: record a fingerprint if one was never stored.
            ident, problem = read_identity(root)
            if ident is not None and roots and not ident.get("fingerprint", {}).get("git_root_commits"):
                ident.setdefault("fingerprint", {})["git_root_commits"] = roots
                atomic_write(ident_path, (json.dumps(ident, indent=2) + "\n").encode())
                upgraded.append("identity.json: added git fingerprint")
    return {"project": str(root), "memory_dir": str(md), "created": created, "upgraded": upgraded, "preserved_existing": True}


# --------------------------------------------------------------------------- checkpoints

def new_checkpoint_id(base: Path) -> str:
    t = dt.datetime.now(dt.timezone.utc)
    stamp = t.strftime("%Y%m%dT%H%M%S") + "_" + t.strftime("%f") + "Z"
    candidate, n = stamp, 1
    while (base / candidate).exists():
        candidate, n = f"{stamp}-{n}", n + 1
    return candidate


def checkpoint_sort_key(p: Path):
    # Both v1 names (YYYYMMDDTHHMMSSZ) and v2 names (YYYYMMDDTHHMMSS_ffffffZ) start with the second.
    return (p.name[:15], p.name)


def list_checkpoints(root: Path):
    """Published checkpoints (directories containing manifest.json), newest first. Not verified."""
    base = checkpoints_dir(root)
    if not base.is_dir():
        return []
    cps = [p for p in base.iterdir() if p.is_dir() and not p.name.startswith(".") and (p / "manifest.json").is_file()]
    return sorted(cps, key=checkpoint_sort_key, reverse=True)


def cleanup_remnants(root: Path) -> list:
    """Remove leftovers of interrupted operations. Caller must hold the project lock."""
    removed = []
    base = checkpoints_dir(root)
    if base.is_dir():
        for p in base.iterdir():
            if p.is_dir() and p.name.startswith((STAGING_PREFIX, TRASH_PREFIX)):
                shutil.rmtree(p, ignore_errors=True)
                removed.append("checkpoints/" + p.name)
    md = memory_dir(root)
    for p in md.glob(".*.tmp"):
        if p.is_file():
            with contextlib.suppress(OSError):
                p.unlink()
                removed.append(p.name)
    return removed


def snapshot(root: Path, keep=None, lock_timeout: float = DEFAULT_LOCK_TIMEOUT) -> dict:
    root = root.resolve()
    md = require_initialized(root)
    with project_lock(md, lock_timeout):
        cleaned = cleanup_remnants(root)
        base = checkpoints_dir(root)
        base.mkdir(exist_ok=True)
        ident, _ = read_identity(root)
        cp_id = new_checkpoint_id(base)
        staging = base / (STAGING_PREFIX + cp_id + "-" + uuid.uuid4().hex[:8])
        staging.mkdir()
        target = base / cp_id
        try:
            entries, missing = [], []
            for name in MEMORY_FILES:
                src = md / name
                if not src.is_file():
                    missing.append(name)
                    continue
                data = src.read_bytes()  # read once: the hash describes exactly the bytes stored
                write_durable(staging / name, data)
                entries.append({"file": name, "sha256": sha256_bytes(data), "size": len(data)})
            git = git_info(root)
            manifest = {
                "format_version": FORMAT_VERSION,
                "id": cp_id,
                "created_at": now(),
                "project": str(root),
                "project_id": ident["project_id"] if ident else None,
                "git": git,
                "files": entries,
                "missing": missing,
            }
            write_durable(staging / "manifest.json", (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode())
            fsync_dir(staging)
            os.rename(str(staging), str(target))  # the single publish step
            fsync_dir(base)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        atomic_write(md / "LATEST", (cp_id + "\n").encode())
        if keep is None:
            keep = retention_from_config(root)
        pruned = prune_locked(root, keep) if keep else []
    return {"checkpoint": str(target), "id": cp_id, "files": len(entries), "missing": missing, "git": git, "pruned": pruned, "cleaned_remnants": cleaned}


def prune_locked(root: Path, keep: int) -> list:
    """Delete the oldest *valid* checkpoints beyond ``keep``. Invalid checkpoints are kept for inspection."""
    if keep < 1:
        return []
    ident, _ = read_identity(root)
    pid = ident["project_id"] if ident else None
    valid = [cp for cp in list_checkpoints(root) if verify_checkpoint(cp, pid)["ok"]]
    removed = []
    for cp in valid[keep:]:
        trash = cp.parent / (TRASH_PREFIX + cp.name + "-" + uuid.uuid4().hex[:8])
        os.rename(str(cp), str(trash))  # atomic un-publish, then delete
        shutil.rmtree(trash, ignore_errors=True)
        removed.append(cp.name)
    if removed:
        fsync_dir(checkpoints_dir(root))
    return removed


def prune(root: Path, keep: int, lock_timeout: float = DEFAULT_LOCK_TIMEOUT) -> dict:
    root = root.resolve()
    md = require_initialized(root)
    if keep < 1:
        raise GuardianError("--keep must be at least 1")
    with project_lock(md, lock_timeout):
        cleaned = cleanup_remnants(root)
        removed = prune_locked(root, keep)
    return {"pruned": removed, "kept": keep, "cleaned_remnants": cleaned}


def upgrade_manifest(m: dict, cp: Path) -> dict:
    """Normalize an older manifest to the current in-memory shape. Stored files are never rewritten,
    because they are integrity records."""
    m = dict(m)
    if m.get("format_version") == 1:
        m.setdefault("id", cp.name)
        m.setdefault("project_id", None)
        m.setdefault("missing", [])
    return m


def verify_checkpoint(cp: Path, project_id=None) -> dict:
    problems = []
    try:
        m = load_json(cp / "manifest.json")
    except (OSError, ValueError) as e:
        return {"id": cp.name, "ok": False, "problems": [f"invalid manifest: {e}"], "manifest": None}
    if not isinstance(m, dict):
        return {"id": cp.name, "ok": False, "problems": ["invalid manifest: not an object"], "manifest": None}
    version = m.get("format_version")
    if version not in SUPPORTED_MANIFEST_VERSIONS:
        newer = isinstance(version, int) and version > FORMAT_VERSION
        hint = " (written by a newer SessionGuardian; upgrade to read it)" if newer else ""
        return {"id": cp.name, "ok": False, "problems": [f"unsupported manifest format_version {version!r}{hint}"], "manifest": None}
    m = upgrade_manifest(m, cp)
    files = m.get("files")
    if not isinstance(files, list):
        return {"id": cp.name, "ok": False, "problems": ["invalid manifest: files is not a list"], "manifest": None}
    listed = set()
    for item in files:
        name = item.get("file") if isinstance(item, dict) else None
        if name not in MEMORY_FILES:  # also rejects path traversal such as "../x"
            problems.append(f"manifest lists unexpected file {name!r}")
            continue
        listed.add(name)
        p = cp / name
        if not p.is_file():
            problems.append(f"missing file: {name}")
        elif "size" in item and p.stat().st_size != item["size"]:
            problems.append(f"size mismatch: {name}")
        elif digest(p) != item.get("sha256"):
            problems.append(f"hash mismatch: {name}")
    for p in cp.iterdir():
        if p.name != "manifest.json" and p.name not in listed:
            problems.append(f"unlisted file: {p.name}")
    if project_id and m.get("project_id") and m["project_id"] != project_id:
        problems.append("belongs to a different project (project_id mismatch)")
    return {"id": cp.name, "ok": not problems, "problems": problems, "manifest": m}


# --------------------------------------------------------------------------- inspection

def find_conflict_markers(text: str) -> bool:
    lines = text.splitlines()
    return any(l.startswith("<<<<<<< ") or l == "<<<<<<<" for l in lines) and any(l.startswith(">>>>>>> ") or l == ">>>>>>>" for l in lines)


def memory_problems(root: Path):
    md = memory_dir(root)
    problems, warnings = [], []
    for name in MEMORY_FILES:
        p = md / name
        if not p.is_file():
            problems.append("missing: " + name)
            continue
        data = p.read_bytes()
        if not data.strip():
            problems.append("empty: " + name)
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            problems.append("not valid UTF-8 (possible corruption): " + name)
            continue
        if "\x00" in text:
            problems.append("contains NUL bytes (possible corruption): " + name)
        if find_conflict_markers(text):
            problems.append("unresolved merge conflict markers: " + name)
    for p in sorted(md.glob(".*.tmp")):
        warnings.append(f"interrupted write remnant: {p.name} (removed on next checkpoint)")
    base = checkpoints_dir(root)
    if base.is_dir():
        for p in sorted(base.iterdir()):
            if p.name.startswith((STAGING_PREFIX, TRASH_PREFIX)):
                warnings.append(f"interrupted checkpoint remnant: checkpoints/{p.name} (removed on next checkpoint)")
            elif p.is_dir() and not p.name.startswith(".") and not (p / "manifest.json").is_file():
                warnings.append(f"checkpoint directory without manifest ignored: checkpoints/{p.name}")
    return problems, warnings


def identity_problems(root: Path, ident):
    problems = []
    recorded = (ident or {}).get("fingerprint", {}).get("git_root_commits") or []
    current = git_root_commits(root)
    if recorded and current and not set(recorded) & set(current):
        problems.append("identity mismatch: memory was created for a different Git repository (root commits differ)")
    return problems


def changed_since(root: Path, verified: dict) -> list:
    if not verified or not verified.get("manifest"):
        return []
    md = memory_dir(root)
    recorded = {i["file"]: i["sha256"] for i in verified["manifest"]["files"]}
    changed = []
    for name in MEMORY_FILES:
        p = md / name
        now_hash = digest(p) if p.is_file() else None
        if now_hash != recorded.get(name):
            changed.append(name)
    return changed


def audit(root: Path, lock_timeout: float = DEFAULT_LOCK_TIMEOUT) -> dict:
    root = root.resolve()
    md = require_initialized(root)
    with project_lock(md, lock_timeout):
        problems, warnings = memory_problems(root)
        ident, ident_problem = read_identity(root)
        if ident_problem:
            problems.append(ident_problem)
        problems += identity_problems(root, ident)
        pid = ident["project_id"] if ident else None
        checkpoints, invalid = [], []
        for cp in list_checkpoints(root):
            v = verify_checkpoint(cp, pid)
            checkpoints.append(v["id"])
            if not v["ok"]:
                invalid.append(v["id"])
            problems += [f"checkpoint {v['id']}: {p}" for p in v["problems"]]
        latest = md / "LATEST"
        if latest.is_file():
            name = latest.read_text(encoding="utf-8").strip()
            if name and not (checkpoints_dir(root) / name / "manifest.json").is_file():
                warnings.append(f"LATEST points to missing checkpoint {name!r}")
    return {"ok": not problems, "problems": problems, "warnings": warnings, "checkpoints": checkpoints, "invalid_checkpoints": invalid, "git": git_info(root)}


def select_recovery_point(root: Path, checkpoint=None):
    """Return (verified checkpoint or None, skipped list). Newest valid wins unless one is requested."""
    ident, _ = read_identity(root)
    pid = ident["project_id"] if ident else None
    cps = list_checkpoints(root)
    if checkpoint:
        match = [cp for cp in cps if cp.name == checkpoint]
        if not match:
            raise GuardianError(f"No checkpoint named {checkpoint!r}")
        v = verify_checkpoint(match[0], pid)
        if not v["ok"]:
            raise GuardianError(f"Checkpoint {checkpoint} failed verification: " + "; ".join(v["problems"]))
        return v, []
    skipped = []
    for cp in cps:
        v = verify_checkpoint(cp, pid)
        if v["ok"]:
            return v, skipped
        skipped.append({"id": v["id"], "problems": v["problems"]})
    return None, skipped


def recover(root: Path, checkpoint=None, lock_timeout: float = DEFAULT_LOCK_TIMEOUT) -> dict:
    root = root.resolve()
    md = require_initialized(root)
    with project_lock(md, lock_timeout):
        chosen, skipped = select_recovery_point(root, checkpoint)
        git_now = git_info(root)
        result = {
            "project": str(root),
            "memory_files": [n for n in MEMORY_FILES if (md / n).is_file()],
            "latest_checkpoint": None,  # kept for compatibility: path of the selected valid checkpoint
            "recovery_point": None,
            "skipped_invalid_checkpoints": skipped,
            "memory_changed_since_checkpoint": changed_since(root, chosen),
            "git": git_now,
            "instruction": "Read repository agent instructions and memory files. Verify claims against source and Git. Do not restore or overwrite working files automatically.",
        }
        if chosen:
            m = chosen["manifest"]
            then = m.get("git") or {}
            result["latest_checkpoint"] = str(checkpoints_dir(root) / chosen["id"])
            result["recovery_point"] = {
                "id": chosen["id"],
                "path": str(checkpoints_dir(root) / chosen["id"]),
                "created_at": m.get("created_at"),
                "format_version": m.get("format_version"),
                "git_at_checkpoint": then,
                "head_changed": bool(then.get("head")) and then.get("head") != git_now.get("head"),
                "branch_changed": bool(then.get("branch")) and then.get("branch") != git_now.get("branch"),
            }
    return result


def status(root: Path) -> dict:
    root = root.resolve()
    md = memory_dir(root)
    return {
        "project": str(root),
        "initialized": md.is_dir(),
        "memory_files": sorted(p.name for p in md.glob("*.md")) if md.is_dir() else [],
        "checkpoints": [p.name for p in list_checkpoints(root)],
        "git": git_info(root),
    }


def doctor() -> dict:
    return {"python": sys.version.split()[0], "python_supported": sys.version_info >= (3, 9), "core": str(Path(__file__).resolve()), "platform": sys.platform, "manifest_format": FORMAT_VERSION, "readable_manifest_formats": list(SUPPORTED_MANIFEST_VERSIONS)}


# --------------------------------------------------------------------------- CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="session-guardian", description="Persistent project memory and checkpoint core")
    sub = ap.add_subparsers(dest="command", required=True)
    parsers = {}
    for cmd in ("init", "status", "checkpoint", "recover", "audit", "prune", "doctor"):
        p = sub.add_parser(cmd)
        if cmd != "doctor":
            p.add_argument("directory", nargs="?", default=".")
        if cmd in ("checkpoint", "recover", "audit", "prune"):
            p.add_argument("--lock-timeout", type=float, default=DEFAULT_LOCK_TIMEOUT, help="seconds to wait for another SessionGuardian process")
        parsers[cmd] = p
    parsers["checkpoint"].add_argument("--keep", type=int, default=None, help="after checkpointing, keep only the N newest valid checkpoints (overrides config retention.keep; 0 = unlimited)")
    parsers["prune"].add_argument("--keep", type=int, required=True, help="keep the N newest valid checkpoints")
    parsers["recover"].add_argument("--checkpoint", default=None, help="verify and select this checkpoint id instead of the newest valid one")
    args = ap.parse_args(argv)
    root = Path(getattr(args, "directory", ".")).expanduser().resolve()
    code = 0
    try:
        if args.command == "init":
            out = init(root)
        elif args.command == "checkpoint":
            if args.keep is not None and args.keep < 0:
                raise GuardianError("--keep must be non-negative")
            out = snapshot(root, keep=args.keep, lock_timeout=args.lock_timeout)
        elif args.command == "recover":
            out = recover(root, checkpoint=args.checkpoint, lock_timeout=args.lock_timeout)
        elif args.command == "audit":
            out = audit(root, lock_timeout=args.lock_timeout)
            code = 0 if out["ok"] else 1
        elif args.command == "prune":
            out = prune(root, args.keep, lock_timeout=args.lock_timeout)
        elif args.command == "status":
            out = status(root)
        else:
            out = doctor()
    except GuardianError as e:
        print(f"session-guardian: {e}", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
