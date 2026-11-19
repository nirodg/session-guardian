"""Roadmap section 11: one reproducible integration test per failure scenario."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest import mock

from _support import CORE, HAS_GIT, Base, sg

HOLD_LOCK = """
import importlib.util, sys, time
from pathlib import Path
spec = importlib.util.spec_from_file_location("sg", sys.argv[1])
sg = importlib.util.module_from_spec(spec); spec.loader.exec_module(sg)
sg.session_start(Path(sys.argv[2]), agent="crashy", agent_session_id="c-1")
with sg.project_lock(Path(sys.argv[2]) / ".session-guardian"):
    print("locked", flush=True)
    time.sleep(60)
"""

CHECKPOINT_LOOP = """
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("sg", sys.argv[1])
sg = importlib.util.module_from_spec(spec); spec.loader.exec_module(sg)
for _ in range(int(sys.argv[3])):
    sg.snapshot(Path(sys.argv[2]))
"""


def tree_hash(path: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(path.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(path)).encode() + p.read_bytes())
    return h.hexdigest()


class Scenarios(Base):
    def claude(self, event, **extra):
        payload = dict({"session_id": "claude-1", "cwd": str(self.root), "hook_event_name": event}, **extra)
        return sg.hook("claude", event, payload)

    def later(self, hours=2):
        return mock.patch.object(sg, "utcnow", return_value=sg.utcnow() + dt.timedelta(hours=hours))

    def test_01_normal_session_shutdown(self):
        sg.init(self.root)
        self.claude("SessionStart", source="startup")
        (self.root / ".session-guardian/CURRENT_STATE.md").write_text("# Current State\n\n- Completed: parser\n")
        self.claude("SessionEnd", reason="logout")
        r = sg.recover(self.root)
        self.assertEqual(r["interrupted_sessions"], [])
        self.assertEqual(r["memory_changed_since_checkpoint"], [])
        self.assertEqual(r["recovery_point"]["activity"]["trigger"], "claude-session-end")

    def test_02_unexpected_terminal_closure(self):
        sg.init(self.root)
        self.claude("SessionStart")
        sg.snapshot(self.root)  # last persisted state before the terminal disappears; SessionEnd never fires
        with self.later():
            r = sg.recover(self.root)
            md = sg.recovery_markdown(self.root, r)
        self.assertEqual(len(r["interrupted_sessions"]), 1)
        self.assertIsNotNone(r["recovery_point"])
        self.assertIn("Interrupted session", md)

    def test_03_agent_crash_while_holding_lock(self):
        sg.init(self.root)
        child = subprocess.Popen([sys.executable, "-c", HOLD_LOCK, str(CORE), str(self.root)], stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), "locked")
        finally:
            child.kill()
            child.wait()
            child.stdout.close()
        out = self.claude("SessionStart")  # next agent starts immediately: no stuck lock
        self.assertIn("recovery report", out.stdout)
        with self.later():
            agents = {s["agent"]: s["state"] for s in sg.list_sessions(self.root)}
        self.assertEqual(agents["crashy"], "interrupted")

    def test_04_machine_restart(self):
        sg.init(self.root)
        good = sg.snapshot(self.root)["id"]
        md = self.root / ".session-guardian"
        # State a power loss can leave: half-built checkpoint, temp file, watcher that was "running".
        (md / "checkpoints/.staging-20990101T000000_000000Z-dead").mkdir()
        (md / ".SCOPE.md.x1.tmp").write_text("partial")
        (md / "watch.json").write_text(json.dumps({"status": "running", "pid": 999999}))
        audit = sg.audit(self.root)
        self.assertTrue(audit["ok"], audit)
        self.assertEqual(len([w for w in audit["warnings"] if "remnant" in w]), 2)
        self.assertIn("unexpectedly", sg.watch_status([self.root])["watchers"][0]["note"])
        self.assertEqual(sg.recover(self.root)["recovery_point"]["id"], good)
        sg.snapshot(self.root)
        self.assertEqual([w for w in sg.audit(self.root)["warnings"] if "remnant" in w], [])

    def test_05_context_window_exhaustion(self):
        sg.init(self.root)
        (self.root / ".session-guardian/SCOPE.md").write_text("# Scope\n\n## Active objective\nMigrate auth to OAuth\n")
        self.claude("SessionStart")
        self.claude("PreCompact", trigger="auto")
        after = self.claude("SessionStart", source="compact")  # context was compacted; memory is re-injected
        self.assertIn("Migrate auth to OAuth", after.stdout)
        triggers = [json.loads((c / "manifest.json").read_text())["activity"]["trigger"] for c in sg.list_checkpoints(self.root)]
        self.assertIn("claude-precompact", triggers)
        self.assertEqual(len(sg.list_sessions(self.root)), 1)  # same session resumed, not duplicated

    def test_06_switching_agents(self):
        sg.init(self.root)
        sg.integrate(self.root, "claude")
        sg.integrate(self.root, "codex")
        self.claude("SessionStart")
        (self.root / ".session-guardian/NEXT_STEPS.md").write_text("# Next\n\n- [ ] Wire the exporter\n")
        self.claude("SessionEnd")
        # Codex has no hooks: it follows AGENTS.md and calls the CLI directly.
        code, out, _ = self.run_cli("session", "start", str(self.root), "--agent", "codex")
        self.assertEqual(code, 0)
        code, report, _ = self.run_cli("recover", str(self.root), "--format", "markdown")
        self.assertIn("- [ ] Wire the exporter", report)
        self.assertIn("session-guardian recover", (self.root / "AGENTS.md").read_text())
        self.assertIn("session-guardian recover", (self.root / "CLAUDE.md").read_text())

    def test_07_concurrent_sessions(self):
        sg.init(self.root)
        procs = [subprocess.Popen([sys.executable, "-c", CHECKPOINT_LOOP, str(CORE), str(self.root), "5"]) for _ in range(3)]
        for p in procs:
            self.assertEqual(p.wait(timeout=120), 0)
        self.assertEqual(len(sg.list_checkpoints(self.root)), 15)
        self.assertTrue(sg.audit(self.root)["ok"])
        sg.session_start(self.root, agent="claude", agent_session_id="a")
        sg.session_start(self.root, agent="codex", agent_session_id="b")
        self.assertEqual(len(sg.recover(self.root)["active_sessions"]), 2)

    def test_08_multiple_projects(self):
        a, b = self.root / "a", self.root / "b"
        a.mkdir()
        b.mkdir()
        sg.init(a, alias="proj-a")
        sg.init(b, alias="proj-b")
        before = tree_hash(b / ".session-guardian")
        sg.snapshot(a)
        sg.park(a, "idea for A only")
        sg.session_start(a, agent="claude", agent_session_id="x")
        self.assertEqual(tree_hash(b / ".session-guardian"), before)
        listed = {p["alias"]: p for p in sg.projects_list()["projects"]}
        self.assertEqual((listed["proj-a"]["checkpoints"], listed["proj-b"]["checkpoints"]), (1, 0))
        self.assertNotEqual(sg.project_id(a), sg.project_id(b))

    def test_09_corrupted_checkpoint(self):
        sg.init(self.root)
        good = sg.snapshot(self.root)["id"]
        bad = sg.snapshot(self.root)["id"]
        (self.root / ".session-guardian/checkpoints" / bad / "manifest.json").write_text("{truncated")
        self.assertFalse(sg.audit(self.root)["ok"])
        r = sg.recover(self.root)
        self.assertEqual(r["recovery_point"]["id"], good)
        self.assertEqual(r["skipped_invalid_checkpoints"][0]["id"], bad)

    @unittest.skipUnless(HAS_GIT, "git not installed")
    def test_10_conflicting_project_memory(self):
        self.git_repo()
        sg.init(self.root)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "memory")
        cp = sg.snapshot(self.root)["id"]
        state = ".session-guardian/CURRENT_STATE.md"
        self.git("checkout", "-q", "-b", "other")
        (self.root / state).write_text("# Current State\n\nfrom branch other\n")
        self.git("commit", "-q", "-am", "other")
        self.git("checkout", "-q", "-")
        (self.root / state).write_text("# Current State\n\nfrom main\n")
        self.git("commit", "-q", "-am", "main")
        subprocess.run(["git", "-C", str(self.root), "merge", "other"], capture_output=True)
        audit = sg.audit(self.root)
        self.assertTrue(any("merge conflict" in p for p in audit["problems"]))
        self.assertIn("from branch other", sg.diff_cmd(self.root, checkpoint=cp).stdout)
        sg.restore_cmd(self.root, cp, ["CURRENT_STATE.md"])
        self.assertFalse(any("merge conflict" in p for p in sg.audit(self.root)["problems"]))

    @unittest.skipUnless(HAS_GIT, "git not installed")
    def test_11_git_branch_changes(self):
        self.git_repo()
        sg.init(self.root)
        sg.snapshot(self.root)
        self.git("checkout", "-q", "-b", "experiment")
        r = sg.recover(self.root)
        self.assertTrue(r["recovery_point"]["branch_changed"])
        self.assertIn("Branch changed", sg.recovery_markdown(self.root, r))

    def test_12_out_of_scope_implementation_attempt(self):
        sg.init(self.root)
        scope = self.root / ".session-guardian/SCOPE.md"
        scope.write_text(scope.read_text().replace("## Protected paths\n", "## Protected paths\n- `billing/` — finance owns this\n"))
        target = str(self.root / "billing/rates.py")
        blocked = self.claude("PreToolUse", tool_name="Write", tool_input={"file_path": target})
        self.assertEqual(blocked.code, 2)
        self.assertIn("billing/", blocked.stderr)
        sg.park(self.root, "Refactor billing rates")  # the idea is recorded, not implemented
        self.assertIn("Refactor billing rates", "\n".join(sg.scope_show(self.root)["parking_lot"]))
        sg.scope_approve(self.root, "User approved rate fix for INC-7", ["billing/"], hours=1)
        self.assertEqual(self.claude("PreToolUse", tool_name="Write", tool_input={"file_path": target}).code, 0)
        self.assertIn("INC-7", scope.read_text())


if __name__ == "__main__":
    unittest.main()
