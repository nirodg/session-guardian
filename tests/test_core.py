import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

CORE = Path(__file__).resolve().parents[1] / "core" / "session_guardian.py"
spec = importlib.util.spec_from_file_location("session_guardian", CORE)
sg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sg)

HAS_GIT = shutil.which("git") is not None


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.md = self.root / ".session-guardian"

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)

    def git_repo(self):
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Test")
        (self.root / "README").write_text("x")
        self.git("add", "README")
        self.git("commit", "-q", "-m", "root")


class InitTests(Base):
    def test_init_creates_memory_and_is_non_destructive(self):
        sg.init(self.root)
        scope = self.md / "SCOPE.md"
        scope.write_text("# My custom scope\n")
        ident_before = (self.md / "identity.json").read_text()
        out = sg.init(self.root)
        self.assertEqual(scope.read_text(), "# My custom scope\n")
        self.assertEqual((self.md / "identity.json").read_text(), ident_before)
        self.assertEqual(out["created"], [])

    def test_init_ignores_runtime_files(self):
        sg.init(self.root)
        body = (self.md / ".gitignore").read_text()
        self.assertIn(".lock", body)
        self.assertIn("checkpoints/.staging-*", body)

    def test_create_new_never_overwrites(self):
        p = self.root / "f.md"
        self.assertTrue(sg.create_new(p, b"one"))
        self.assertFalse(sg.create_new(p, b"two"))
        self.assertEqual(p.read_bytes(), b"one")
        self.assertEqual(list(self.root.glob(".*.tmp")), [])

    @unittest.skipUnless(HAS_GIT, "git not installed")
    def test_init_records_git_fingerprint_and_upgrades_old_identity(self):
        self.git_repo()
        self.md.mkdir()
        (self.md / "identity.json").write_text(json.dumps({"format_version": 1, "project_id": "abc", "created_at": "x"}))
        out = sg.init(self.root)
        ident = json.loads((self.md / "identity.json").read_text())
        self.assertEqual(ident["project_id"], "abc")  # preserved
        self.assertEqual(len(ident["fingerprint"]["git_root_commits"]), 1)
        self.assertTrue(out["upgraded"])


class CheckpointTests(Base):
    def setUp(self):
        super().setUp()
        sg.init(self.root)

    def test_checkpoint_is_manifested_and_auditable(self):
        sg.snapshot(self.root)
        checkpoints = sg.list_checkpoints(self.root)
        self.assertEqual(len(checkpoints), 1)
        manifest = json.loads((checkpoints[0] / "manifest.json").read_text())
        self.assertEqual(manifest["format_version"], sg.FORMAT_VERSION)
        self.assertEqual(len(manifest["files"]), len(sg.MEMORY_FILES))
        self.assertEqual(manifest["project_id"], json.loads((self.md / "identity.json").read_text())["project_id"])
        self.assertTrue(sg.audit(self.root)["ok"])

    def test_checkpoints_in_same_second_are_distinct(self):
        for _ in range(3):
            sg.snapshot(self.root)
        self.assertEqual(len(sg.list_checkpoints(self.root)), 3)

    def test_latest_points_at_newest(self):
        sg.snapshot(self.root)
        out = sg.snapshot(self.root)
        self.assertEqual((self.md / "LATEST").read_text().strip(), out["id"])
        self.assertEqual(sg.list_checkpoints(self.root)[0].name, out["id"])

    def test_interrupted_checkpoint_leaves_previous_state_intact(self):
        first = sg.snapshot(self.root)["id"]
        latest_before = (self.md / "LATEST").read_text()
        calls = {"n": 0}
        real = sg.write_durable

        def flaky(path, data):
            calls["n"] += 1
            if calls["n"] == 3:
                raise OSError("disk full")
            return real(path, data)

        with mock.patch.object(sg, "write_durable", flaky):
            with self.assertRaises(OSError):
                sg.snapshot(self.root)
        self.assertEqual([p.name for p in sg.list_checkpoints(self.root)], [first])
        self.assertEqual((self.md / "LATEST").read_text(), latest_before)
        self.assertEqual([p.name for p in (self.md / "checkpoints").iterdir()], [first])

    def test_crash_remnants_are_ignored_and_cleaned(self):
        # Simulate a process killed after writing a staging manifest but before publishing.
        staging = self.md / "checkpoints" / ".staging-20990101T000000_000000Z-dead"
        staging.mkdir()
        (staging / "manifest.json").write_text("{}")
        (self.md / ".PROJECT.md.abc.tmp").write_text("partial")
        self.assertEqual(sg.list_checkpoints(self.root), [])
        self.assertTrue(any("remnant" in w for w in sg.audit(self.root)["warnings"]))
        out = sg.snapshot(self.root)
        self.assertFalse(staging.exists())
        self.assertFalse((self.md / ".PROJECT.md.abc.tmp").exists())
        self.assertEqual(len(out["cleaned_remnants"]), 2)

    def test_checkpoint_requires_init(self):
        other = Path(tempfile.mkdtemp())
        try:
            with self.assertRaises(sg.GuardianError):
                sg.snapshot(other)
        finally:
            shutil.rmtree(other)


class IntegrityTests(Base):
    def setUp(self):
        super().setUp()
        sg.init(self.root)
        sg.snapshot(self.root)
        self.cp = sg.list_checkpoints(self.root)[0]

    def test_audit_detects_checkpoint_tampering(self):
        (self.cp / "PROJECT.md").write_text("tampered")
        self.assertFalse(sg.audit(self.root)["ok"])

    def test_manifest_path_traversal_is_rejected(self):
        m = json.loads((self.cp / "manifest.json").read_text())
        m["files"].append({"file": "../identity.json", "sha256": "0", "size": 0})
        (self.cp / "manifest.json").write_text(json.dumps(m))
        v = sg.verify_checkpoint(self.cp)
        self.assertFalse(v["ok"])
        self.assertIn("unexpected file", v["problems"][0])

    def test_unlisted_file_is_reported(self):
        (self.cp / "extra.md").write_text("x")
        self.assertFalse(sg.verify_checkpoint(self.cp)["ok"])

    def test_future_format_is_rejected_with_upgrade_hint(self):
        m = json.loads((self.cp / "manifest.json").read_text())
        m["format_version"] = sg.FORMAT_VERSION + 1
        (self.cp / "manifest.json").write_text(json.dumps(m))
        v = sg.verify_checkpoint(self.cp)
        self.assertFalse(v["ok"])
        self.assertIn("newer SessionGuardian", v["problems"][0])

    def test_v1_manifest_is_still_verifiable(self):
        v1 = self.md / "checkpoints" / "20200101T000000Z"
        v1.mkdir()
        data = b"# Project\n"
        (v1 / "PROJECT.md").write_bytes(data)
        (v1 / "manifest.json").write_text(json.dumps({"format_version": 1, "created_at": "2020", "project": "x", "git": {}, "files": [{"file": "PROJECT.md", "sha256": sg.sha256_bytes(data), "size": len(data)}]}))
        v = sg.verify_checkpoint(v1)
        self.assertTrue(v["ok"], v["problems"])
        self.assertEqual(v["manifest"]["id"], "20200101T000000Z")
        # v1 names sort correctly against v2 names.
        self.assertEqual(sg.list_checkpoints(self.root)[-1].name, "20200101T000000Z")

    def test_checkpoint_from_other_project_is_flagged(self):
        m = json.loads((self.cp / "manifest.json").read_text())
        m["project_id"] = "someone-else"
        (self.cp / "manifest.json").write_text(json.dumps(m))
        audit = sg.audit(self.root)
        self.assertFalse(audit["ok"])
        self.assertTrue(any("different project" in p for p in audit["problems"]))

    def test_conflict_markers_and_corruption_detected(self):
        (self.md / "DECISIONS.md").write_text("# D\n<<<<<<< HEAD\na\n=======\nb\n>>>>>>> branch\n")
        (self.md / "SCOPE.md").write_bytes(b"\xff\xfe\x00bad")
        problems = sg.audit(self.root)["problems"]
        self.assertTrue(any("merge conflict" in p and "DECISIONS" in p for p in problems))
        self.assertTrue(any("UTF-8" in p and "SCOPE" in p for p in problems))

    def test_setext_heading_is_not_a_conflict(self):
        self.assertFalse(sg.find_conflict_markers("Title\n=======\n"))

    def test_invalid_identity_is_reported(self):
        (self.md / "identity.json").write_text("{not json")
        self.assertTrue(any("identity.json" in p for p in sg.audit(self.root)["problems"]))

    @unittest.skipUnless(HAS_GIT, "git not installed")
    def test_memory_copied_from_other_repository_is_flagged(self):
        self.git_repo()
        ident = json.loads((self.md / "identity.json").read_text())
        ident["fingerprint"] = {"git_root_commits": ["0" * 40]}
        (self.md / "identity.json").write_text(json.dumps(ident))
        self.assertTrue(any("different Git repository" in p for p in sg.audit(self.root)["problems"]))


class RecoveryTests(Base):
    def setUp(self):
        super().setUp()
        sg.init(self.root)

    def test_recover_selects_newest_valid_checkpoint(self):
        good = sg.snapshot(self.root)["id"]
        bad = sg.snapshot(self.root)["id"]
        (self.md / "checkpoints" / bad / "SCOPE.md").write_text("corrupt")
        out = sg.recover(self.root)
        self.assertEqual(out["recovery_point"]["id"], good)
        self.assertTrue(out["latest_checkpoint"].endswith(good))
        audit = sg.audit(self.root)
        self.assertEqual(audit["checkpoints"], [bad, good])
        self.assertEqual(audit["invalid_checkpoints"], [bad])
        self.assertEqual(out["skipped_invalid_checkpoints"][0]["id"], bad)

    def test_recover_with_no_checkpoints(self):
        out = sg.recover(self.root)
        self.assertIsNone(out["recovery_point"])

    def test_recover_reports_memory_changed_since_checkpoint(self):
        sg.snapshot(self.root)
        (self.md / "CURRENT_STATE.md").write_text("# New state\n")
        self.assertEqual(sg.recover(self.root)["memory_changed_since_checkpoint"], ["CURRENT_STATE.md"])

    def test_recover_explicit_checkpoint_must_be_valid(self):
        cp = sg.snapshot(self.root)["id"]
        self.assertEqual(sg.recover(self.root, checkpoint=cp)["recovery_point"]["id"], cp)
        (self.md / "checkpoints" / cp / "PROJECT.md").write_text("corrupt")
        with self.assertRaises(sg.GuardianError):
            sg.recover(self.root, checkpoint=cp)
        with self.assertRaises(sg.GuardianError):
            sg.recover(self.root, checkpoint="nope")

    def test_recover_never_modifies_memory(self):
        sg.snapshot(self.root)
        (self.md / "PROJECT.md").write_text("# Edited after checkpoint\n")
        sg.recover(self.root)
        self.assertEqual((self.md / "PROJECT.md").read_text(), "# Edited after checkpoint\n")


class RetentionTests(Base):
    def setUp(self):
        super().setUp()
        sg.init(self.root)

    def test_keep_prunes_oldest_valid_only(self):
        ids = [sg.snapshot(self.root)["id"] for _ in range(4)]
        (self.md / "checkpoints" / ids[0] / "PROJECT.md").write_text("corrupt")  # invalid: kept for inspection
        out = sg.snapshot(self.root, keep=2)
        remaining = [p.name for p in sg.list_checkpoints(self.root)]
        self.assertEqual(remaining, [out["id"], ids[3], ids[0]])
        self.assertEqual(sorted(out["pruned"]), sorted(ids[1:3]))

    def test_default_is_unlimited(self):
        for _ in range(4):
            sg.snapshot(self.root)
        self.assertEqual(len(sg.list_checkpoints(self.root)), 4)

    def test_config_retention(self):
        (self.md / "config.json").write_text(json.dumps({"retention": {"keep": 1}}))
        sg.snapshot(self.root)
        last = sg.snapshot(self.root)["id"]
        self.assertEqual([p.name for p in sg.list_checkpoints(self.root)], [last])

    def test_invalid_config_is_an_error(self):
        (self.md / "config.json").write_text(json.dumps({"retention": {"keep": -1}}))
        with self.assertRaises(sg.GuardianError):
            sg.snapshot(self.root)

    def test_prune_command(self):
        for _ in range(3):
            sg.snapshot(self.root)
        self.assertEqual(len(sg.prune(self.root, 1)["pruned"]), 2)
        with self.assertRaises(sg.GuardianError):
            sg.prune(self.root, 0)


HOLDER = """
import importlib.util, sys, time
from pathlib import Path
spec = importlib.util.spec_from_file_location("sg", sys.argv[1])
sg = importlib.util.module_from_spec(spec); spec.loader.exec_module(sg)
with sg.project_lock(Path(sys.argv[2])):
    print("locked", flush=True)
    time.sleep(60)
"""


SLOW_CHECKPOINT = """
import importlib.util, sys, time
from pathlib import Path
spec = importlib.util.spec_from_file_location("sg", sys.argv[1])
sg = importlib.util.module_from_spec(spec); spec.loader.exec_module(sg)
real = sg.write_durable
def slow(path, data):
    real(path, data)
    if path.name == "SCOPE.md":
        print("mid-checkpoint", flush=True)
        time.sleep(60)
sg.write_durable = slow
sg.snapshot(Path(sys.argv[2]))
"""


class LockTests(Base):
    def test_process_killed_mid_checkpoint_cannot_replace_last_valid(self):
        sg.init(self.root)
        first = sg.snapshot(self.root)["id"]
        latest_before = (self.md / "LATEST").read_text()
        child = subprocess.Popen([sys.executable, "-c", SLOW_CHECKPOINT, str(CORE), str(self.root)], stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), "mid-checkpoint")
        finally:
            child.kill()
            child.wait()
            child.stdout.close()
        self.assertEqual([p.name for p in sg.list_checkpoints(self.root)], [first])
        self.assertEqual((self.md / "LATEST").read_text(), latest_before)
        self.assertEqual(sg.recover(self.root)["recovery_point"]["id"], first)
        self.assertTrue(sg.audit(self.root)["ok"])  # remnant is only a warning
        sg.snapshot(self.root)  # cleans the remnant and succeeds
        self.assertEqual(len(sg.list_checkpoints(self.root)), 2)
        self.assertFalse(any(p.name.startswith(".staging-") for p in (self.md / "checkpoints").iterdir()))

    def test_lock_excludes_other_process_and_is_released_on_crash(self):
        sg.init(self.root)
        child = subprocess.Popen([sys.executable, "-c", HOLDER, str(CORE), str(self.md)], stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), "locked")
            with self.assertRaises(sg.LockTimeout):
                sg.snapshot(self.root, lock_timeout=0.2)
            self.assertEqual(sg.list_checkpoints(self.root), [])
        finally:
            child.kill()  # simulate a crash while holding the lock
            child.wait()
            child.stdout.close()
        sg.snapshot(self.root, lock_timeout=5)
        self.assertEqual(len(sg.list_checkpoints(self.root)), 1)


class CliTests(Base):
    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = sg.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_cli_round_trip(self):
        d = str(self.root)
        self.assertEqual(self.run_cli("init", d)[0], 0)
        code, out, _ = self.run_cli("checkpoint", d, "--keep", "3")
        self.assertEqual(code, 0)
        self.assertIn("id", json.loads(out))
        self.assertEqual(self.run_cli("audit", d)[0], 0)
        self.assertIsNotNone(json.loads(self.run_cli("recover", d)[1])["recovery_point"])
        self.assertEqual(self.run_cli("prune", d, "--keep", "1")[0], 0)
        self.assertEqual(json.loads(self.run_cli("doctor")[1])["manifest_format"], sg.FORMAT_VERSION)

    def test_cli_errors_are_clean(self):
        code, _, err = self.run_cli("checkpoint", str(self.root))
        self.assertEqual(code, 2)
        self.assertIn("session-guardian init", err)

    def test_audit_exit_code(self):
        d = str(self.root)
        self.run_cli("init", d)
        (self.md / "PROJECT.md").write_text("")
        self.assertEqual(self.run_cli("audit", d)[0], 1)


if __name__ == "__main__":
    unittest.main()
