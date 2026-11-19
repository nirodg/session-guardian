import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest import mock

from _support import CORE, HAS_GIT, Base, sg


class SessionTests(Base):
    def setUp(self):
        super().setUp()
        sg.init(self.root)

    def test_lifecycle(self):
        s = sg.session_start(self.root, agent="claude", agent_session_id="abc")["session"]
        self.assertEqual(sg.list_sessions(self.root)[0]["state"], "active")
        sg.session_heartbeat(self.root, agent="claude", agent_session_id="abc")
        sg.session_end(self.root, agent="claude", agent_session_id="abc", reason="logout")
        rec = sg.list_sessions(self.root)[0]
        self.assertEqual((rec["id"], rec["state"], rec["end_reason"]), (s["id"], "ended", "logout"))

    def test_resume_reuses_open_session(self):
        a = sg.session_start(self.root, agent="claude", agent_session_id="abc")
        b = sg.session_start(self.root, agent="claude", agent_session_id="abc")
        self.assertTrue(b["resumed"])
        self.assertEqual(a["session"]["id"], b["session"]["id"])
        self.assertEqual(len(sg.list_sessions(self.root)), 1)

    def test_concurrent_sessions_are_independent(self):
        sg.session_start(self.root, agent="claude", agent_session_id="one")
        sg.session_start(self.root, agent="codex", agent_session_id="two")
        sg.session_end(self.root, agent="codex", agent_session_id="two")
        states = {s["agent"]: s["state"] for s in sg.list_sessions(self.root)}
        self.assertEqual(states, {"claude": "active", "codex": "ended"})

    def test_stale_session_is_interrupted(self):
        sg.session_start(self.root, agent="claude", agent_session_id="abc")
        later = sg.utcnow() + dt.timedelta(hours=2)
        with mock.patch.object(sg, "utcnow", return_value=later):
            self.assertEqual(sg.list_sessions(self.root)[0]["state"], "interrupted")
            report = sg.recover(self.root)
        self.assertEqual(len(report["interrupted_sessions"]), 1)

    def test_end_without_match_is_an_error(self):
        with self.assertRaises(sg.GuardianError):
            sg.session_end(self.root, agent_session_id="missing")

    def test_old_ended_sessions_expire(self):
        sg.session_start(self.root, agent="a", agent_session_id="old")
        sg.session_end(self.root, agent="a", agent_session_id="old")
        future = sg.utcnow() + dt.timedelta(days=31)
        with mock.patch.object(sg, "utcnow", return_value=future):
            sg.session_start(self.root, agent="a", agent_session_id="new")
        self.assertEqual([s["agent_session_id"] for s in sg.list_sessions(self.root)], ["new"])


class WatcherUnitTests(Base):
    """Drive ProjectWatch with a synthetic clock: deterministic and fast."""

    def setUp(self):
        super().setUp()
        sg.init(self.root)
        self.w = sg.ProjectWatch(self.root, {"interval": 1, "debounce": 5, "min_checkpoint_interval": 60})
        self.w.start(0.0)

    def touch(self, name, text="x"):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        # Make mtime differences visible on filesystems with coarse timestamps.
        st = p.stat()
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))

    def test_no_change_no_checkpoint(self):
        self.assertIsNone(self.w.tick(100.0))
        self.assertEqual(sg.list_checkpoints(self.root), [])

    def test_debounce_then_checkpoint_with_activity(self):
        self.touch("src/app.py")
        self.assertIsNone(self.w.tick(1.0))  # change seen, still within debounce
        self.assertIsNone(self.w.tick(3.0))
        out = self.w.tick(7.0)
        self.assertIsNotNone(out)
        m = json.loads((sg.list_checkpoints(self.root)[0] / "manifest.json").read_text())
        self.assertEqual(m["activity"]["trigger"], "watcher")
        self.assertIn("src/app.py", m["activity"]["changed_paths"])

    def test_continuous_edits_postpone_checkpoint(self):
        for t in (1.0, 3.0, 5.0, 7.0):
            self.touch("a.txt", str(t))
            self.assertIsNone(self.w.tick(t))
        self.assertIsNotNone(self.w.tick(13.0))

    def test_min_interval_limits_checkpoint_rate(self):
        self.touch("a.txt", "1")
        self.w.tick(1.0)
        self.assertIsNotNone(self.w.tick(10.0))
        self.touch("a.txt", "2")
        self.w.tick(11.0)
        self.assertIsNone(self.w.tick(20.0))  # debounced, but within min interval
        self.assertIsNotNone(self.w.tick(71.0))
        self.assertEqual(len(sg.list_checkpoints(self.root)), 2)

    def test_ignored_paths(self):
        self.touch("node_modules/x.js")
        self.touch("build/out.o")
        self.w.tick(1.0)
        self.assertIsNone(self.w.tick(10.0))

    def test_memory_edit_triggers(self):
        self.touch(".session-guardian/CURRENT_STATE.md", "# State\nnew\n")
        self.w.tick(1.0)
        out = self.w.tick(10.0)
        self.assertIsNotNone(out)

    def test_watcher_checkpoint_does_not_retrigger_itself(self):
        self.touch("a.txt")
        self.w.tick(1.0)
        self.assertIsNotNone(self.w.tick(10.0))
        self.assertIsNone(self.w.tick(100.0))
        self.assertIsNone(self.w.tick(200.0))
        self.assertEqual(len(sg.list_checkpoints(self.root)), 1)

    def test_max_files_truncates(self):
        w = sg.ProjectWatch(self.root, {"max_files": 3})
        for i in range(10):
            (self.root / f"f{i}").write_text("x")
        tree = w.scan()
        self.assertTrue(w.truncated)
        self.assertLessEqual(len([k for k in tree if not k.startswith(".session-guardian")]), 3)

    def test_shutdown_flushes_pending(self):
        self.touch("a.txt")
        self.w.tick(1.0)
        self.w.stop(2.0)
        m = json.loads((sg.list_checkpoints(self.root)[0] / "manifest.json").read_text())
        self.assertEqual(m["activity"]["trigger"], "watcher-shutdown")
        self.assertEqual(json.loads((self.md / "watch.json").read_text())["status"], "stopped")

    def test_changes_while_not_running_are_detected(self):
        self.w.stop(1.0)
        self.touch("offline.txt")
        w2 = sg.ProjectWatch(self.root, {"debounce": 0, "min_checkpoint_interval": 0})
        w2.start(0.0)
        self.assertTrue(w2.urgent)
        self.assertIsNotNone(w2.tick(1.0))

    def test_crash_is_detected_on_restart(self):
        # Simulate a crash: state says running, but nobody holds the lock.
        w2 = sg.ProjectWatch(self.root)
        w2.start(0.0)
        self.assertTrue(w2.recovered_from_crash)

    def test_secret_block_is_logged_not_fatal(self):
        (self.md / "CURRENT_STATE.md").write_text("key AKIAABCDEFGHIJKLMNOP\n")
        self.w.tick(1.0)
        self.assertIsNone(self.w.tick(10.0))
        self.assertEqual(sg.list_checkpoints(self.root), [])

    @unittest.skipUnless(HAS_GIT, "git not installed")
    def test_branch_change_bypasses_min_interval(self):
        self.git_repo()
        w = sg.ProjectWatch(self.root, {"debounce": 1, "min_checkpoint_interval": 3600})
        w.start(0.0)
        self.touch("a.txt")
        w.tick(1.0)
        self.assertIsNotNone(w.tick(3.0))
        self.git("checkout", "-q", "-b", "feature")
        w.tick(4.0)
        out = w.tick(6.0)
        self.assertIsNotNone(out)
        m = json.loads((sg.list_checkpoints(self.root)[0] / "manifest.json").read_text())
        self.assertIn("branch changed", m["activity"]["reason"])


class WatcherProcessTests(Base):
    """Real background processes: start, detect a change, stop gracefully, survive a kill."""

    def wait_for(self, cond, timeout=15.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if cond():
                return True
            time.sleep(0.1)
        return False

    def test_start_change_stop(self):
        sg.init(self.root)
        out = sg.watch_start([self.root], {"interval": 0.2, "debounce": 0.3, "min_checkpoint_interval": 0})
        self.assertTrue(out["results"][0]["started"], out)
        try:
            self.assertTrue(sg.watch_status([self.root])["watchers"][0]["running"])
            again = sg.watch_start([self.root])
            self.assertFalse(again["results"][0]["started"])  # one watcher per project
            (self.root / "work.txt").write_text("hello")
            self.assertTrue(self.wait_for(lambda: len(sg.list_checkpoints(self.root)) >= 1), (self.md / "watch.log").read_text())
        finally:
            stopped = sg.watch_stop([self.root], timeout=15)
        self.assertTrue(stopped["results"][0]["stopped"])
        self.assertEqual(json.loads((self.md / "watch.json").read_text())["status"], "stopped")

    def test_killed_watcher_keeps_checkpoints_and_restarts(self):
        sg.init(self.root)
        sg.snapshot(self.root)
        before = [p.name for p in sg.list_checkpoints(self.root)]
        proc = subprocess.Popen([sys.executable, str(CORE), "watch", "run", str(self.root), "--interval", "0.2"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            def running():
                try:
                    return json.loads((self.md / "watch.json").read_text()).get("status") == "running"
                except (OSError, ValueError):
                    return False
            self.assertTrue(self.wait_for(running))
        finally:
            proc.kill()
            proc.wait()
        self.assertEqual([p.name for p in sg.list_checkpoints(self.root)][-len(before):], before)
        st = sg.watch_status([self.root])["watchers"][0]
        self.assertFalse(st["running"])
        self.assertIn("unexpectedly", st["note"])
        self.assertTrue(sg.audit(self.root)["ok"])
        out = sg.watch_run([self.root], once=True)
        self.assertIn(str(self.root), out["watched"])

    def test_multiple_projects_are_isolated(self):
        other = Path(self.tmp.name) / "other"
        other.mkdir()
        sg.init(self.root)
        sg.init(other)
        out = sg.watch_start([self.root, other], {"interval": 0.2, "debounce": 0.2, "min_checkpoint_interval": 0})
        try:
            self.assertTrue(all(r["started"] for r in out["results"]), out)
            sg.watch_stop([other], timeout=15)  # stopping one leaves the other running
            self.assertTrue(sg.watch_status([self.root])["watchers"][0]["running"])
            (self.root / "a.txt").write_text("x")
            self.assertTrue(self.wait_for(lambda: len(sg.list_checkpoints(self.root)) >= 1))
            self.assertEqual(sg.list_checkpoints(other), [])
        finally:
            sg.watch_stop([self.root, other], timeout=15)


if __name__ == "__main__":
    unittest.main()
