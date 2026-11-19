#!/usr/bin/env python3
"""SessionGuardian deterministic local core. Python 3.9+, standard library only."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

MEMORY = ("PROJECT", "SCOPE", "ARCHITECTURE", "DECISIONS", "CURRENT_STATE", "SESSION_LOG", "NEXT_STEPS")
FORMAT_VERSION = 1

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        try:
            dfd = os.open(str(path.parent), os.O_RDONLY)
            try: os.fsync(dfd)
            finally: os.close(dfd)
        except OSError:
            pass
    except BaseException:
        try: os.unlink(tmp)
        except OSError: pass
        raise

def git_info(root: Path):
    def run(args):
        try:
            p = subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True, timeout=5)
            return p.stdout.strip() if p.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            return None
    return {"branch": run(["branch", "--show-current"]), "status": run(["status", "--short"]), "head": run(["rev-parse", "HEAD"])}

def memory_dir(root: Path) -> Path:
    return root / ".session-guardian"

def init(root: Path):
    root = root.resolve()
    md = memory_dir(root)
    (md / "checkpoints").mkdir(parents=True, exist_ok=True)
    templates = Path(__file__).resolve().parent.parent / "templates"
    created = []
    for name in MEMORY:
        dest = md / (name + ".md")
        if dest.exists():
            continue
        src = templates / (name + ".md")
        body = src.read_bytes() if src.exists() else f"# {name.replace('_', ' ').title()}\n\nUNKNOWN\n".encode()
        atomic_write(dest, body)
        created.append(dest.name)
    meta = md / "identity.json"
    if not meta.exists():
        atomic_write(meta, (json.dumps({"format_version": FORMAT_VERSION, "project_id": str(uuid.uuid4()), "created_at": now()}, indent=2) + "\n").encode())
        created.append(meta.name)
    print(json.dumps({"project": str(root), "memory_dir": str(md), "created": created, "preserved_existing": True}, indent=2))

def snapshot(root: Path):
    md = memory_dir(root)
    if not md.is_dir():
        raise SystemExit("No .session-guardian directory. Run: session-guardian init")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = md / "checkpoints" / stamp
    target.mkdir(parents=True, exist_ok=False)
    entries = []
    try:
        for name in MEMORY:
            src = md / (name + ".md")
            if src.is_file():
                dest = target / src.name
                shutil.copyfile(src, dest)
                entries.append({"file": src.name, "sha256": digest(dest), "size": dest.stat().st_size})
        git = git_info(root)
        manifest = {"format_version": FORMAT_VERSION, "created_at": now(), "project": str(root.resolve()), "git": git, "files": entries}
        atomic_write(target / "manifest.json", (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode())
        atomic_write(md / "LATEST", (stamp + "\n").encode())
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        raise
    print(json.dumps({"checkpoint": str(target), "files": len(entries), "git": git}, indent=2))

def list_checkpoints(root: Path):
    base = memory_dir(root) / "checkpoints"
    if not base.is_dir(): return []
    return sorted((p for p in base.iterdir() if p.is_dir() and (p / "manifest.json").is_file()), key=lambda p: p.name, reverse=True)

def audit(root: Path):
    md = memory_dir(root)
    problems = []
    for name in MEMORY:
        p = md / (name + ".md")
        if not p.is_file(): problems.append("missing: " + p.name)
        elif p.stat().st_size == 0: problems.append("empty: " + p.name)
    checkpoints = []
    for cp in list_checkpoints(root):
        try:
            m = json.loads((cp / "manifest.json").read_text())
            for item in m.get("files", []):
                p = cp / item["file"]
                if not p.is_file() or digest(p) != item["sha256"]:
                    problems.append(f"checkpoint integrity failure: {cp.name}/{item['file']}")
            checkpoints.append(cp.name)
        except Exception as e:
            problems.append(f"invalid manifest: {cp.name}: {e}")
    result = {"ok": not problems, "problems": problems, "checkpoints": checkpoints, "git": git_info(root)}
    print(json.dumps(result, indent=2))
    return 0 if not problems else 1

def recover(root: Path):
    md = memory_dir(root)
    if not md.is_dir(): raise SystemExit("No .session-guardian directory. Run: session-guardian init")
    cps = list_checkpoints(root)
    result = {"project": str(root.resolve()), "memory_files": [n + ".md" for n in MEMORY if (md / (n + ".md")).is_file()], "latest_checkpoint": str(cps[0]) if cps else None, "git": git_info(root), "instruction": "Read repository agent instructions and memory files. Verify claims against source and Git. Do not restore or overwrite working files automatically."}
    print(json.dumps(result, indent=2))

def main():
    ap = argparse.ArgumentParser(prog="session-guardian", description="Persistent project memory and checkpoint core")
    sub = ap.add_subparsers(dest="command", required=True)
    for cmd in ("init", "status", "checkpoint", "recover", "audit", "doctor"):
        p = sub.add_parser(cmd)
        p.add_argument("directory", nargs="?", default=".")
    args = ap.parse_args()
    root = Path(args.directory).expanduser().resolve()
    if args.command == "init": init(root)
    elif args.command == "checkpoint": snapshot(root)
    elif args.command == "recover": recover(root)
    elif args.command == "audit": raise SystemExit(audit(root))
    elif args.command == "status":
        md = memory_dir(root)
        print(json.dumps({"project": str(root), "initialized": md.is_dir(), "memory_files": sorted(p.name for p in md.glob("*.md")) if md.is_dir() else [], "checkpoints": [p.name for p in list_checkpoints(root)], "git": git_info(root)}, indent=2))
    elif args.command == "doctor":
        print(json.dumps({"python": sys.version.split()[0], "python_supported": sys.version_info >= (3, 9), "core": str(Path(__file__).resolve()), "platform": sys.platform}, indent=2))

if __name__ == "__main__":
    main()
