import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from _support import REPO

BASH = shutil.which("bash")


@unittest.skipUnless(BASH and os.name != "nt", "install.sh targets Linux/macOS")
class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.env = dict(os.environ, HOME=str(self.home), SESSION_GUARDIAN_DATA=str(self.home / "data"),
                        PATH=os.environ.get("PATH", ""))
        for k in ("SESSION_GUARDIAN_HOME", "SESSION_GUARDIAN_BIN", "SESSION_GUARDIAN_SOURCE", "XDG_DATA_HOME"):
            self.env.pop(k, None)
        self.root = self.home / ".local/share/session-guardian"
        self.bin = self.home / ".local/bin/session-guardian"

    def tearDown(self):
        self.tmp.cleanup()

    def install(self, *args, check=True):
        p = subprocess.run([BASH, str(REPO / "install.sh"), "--source", str(REPO), "--yes", *args],
                           env=self.env, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        if check:
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p

    def sg(self, *args):
        return subprocess.run([str(self.bin), *args], env=self.env, capture_output=True, text=True)

    def test_fresh_install_runs_and_validates(self):
        out = self.install("--agent", "generic").stdout
        self.assertIn("installed", out)
        self.assertEqual(json.loads(self.sg("doctor").stdout)["checks"]["installation"]["managed_install"], True)
        self.assertTrue((self.home / ".agents/skills/session-guardian/SKILL.md").is_file())
        manifest = json.loads((self.root / "install-manifest.json").read_text())
        self.assertEqual(manifest["ref"], "main")
        self.assertEqual(len(manifest["skills"]), 1)

    def test_reinstall_is_idempotent(self):
        self.install("--agent", "generic")
        first = (self.root / "core/session_guardian.py").read_bytes()
        out = self.install("--agent", "generic").stdout
        self.assertIn("Skill up to date", out)
        self.assertEqual((self.root / "core/session_guardian.py").read_bytes(), first)
        self.assertFalse(list(self.root.glob("*.old")))
        self.assertFalse((self.root / ".install-staging").exists())

    def test_upgrade_replaces_unmodified_skill_but_preserves_edited(self):
        (self.home / ".claude/skills").mkdir(parents=True)
        (self.home / ".codex/skills").mkdir(parents=True)
        self.install()  # auto detects both
        claude = self.home / ".claude/skills/session-guardian/SKILL.md"
        codex = self.home / ".codex/skills/session-guardian/SKILL.md"
        self.assertTrue(claude.is_file() and codex.is_file())
        # Simulate an older release we installed (record its hash) vs a user-edited copy.
        old = b"old release skill\n"
        claude.write_bytes(old)
        m = json.loads((self.root / "install-manifest.json").read_text())
        for s in m["skills"]:
            if "claude" in s["path"]:
                s["sha256"] = hashlib.sha256(old).hexdigest()
        (self.root / "install-manifest.json").write_text(json.dumps(m))
        codex.write_text("my edits\n")
        out = self.install().stdout
        self.assertIn("Upgraded skill", out)
        self.assertEqual(claude.read_bytes(), (REPO / "skills/session-guardian/SKILL.md").read_bytes())
        self.assertEqual(codex.read_text(), "my edits\n")

    def test_foreign_skill_and_wrapper_are_never_overwritten(self):
        skill = self.home / ".agents/skills/session-guardian/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("someone else's skill\n")
        self.bin.parent.mkdir(parents=True)
        self.bin.write_text("#!/bin/sh\necho mine\n")
        p = self.install("--agent", "generic")
        self.assertEqual(skill.read_text(), "someone else's skill\n")
        self.assertEqual(self.bin.read_text(), "#!/bin/sh\necho mine\n")
        self.assertIn("Not overwriting", p.stderr)

    def test_agent_none_installs_core_only(self):
        self.install("--agent", "none")
        self.assertFalse((self.home / ".agents").exists())
        self.assertEqual(self.sg("--version").returncode, 0)

    def test_init_flag_and_uninstall_preserve_project_memory(self):
        project = self.home / "proj"
        project.mkdir()
        subprocess.run([BASH, str(REPO / "install.sh"), "--source", str(REPO), "--yes", "--agent", "generic", "--init"],
                       env=self.env, cwd=project, check=True, capture_output=True)
        self.assertTrue((project / ".session-guardian/SCOPE.md").is_file())
        p = subprocess.run([BASH, str(REPO / "install.sh"), "--uninstall"], env=self.env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertFalse(self.bin.exists())
        self.assertFalse((self.root / "core").exists())
        self.assertFalse((self.home / ".agents/skills/session-guardian").exists())
        self.assertTrue((project / ".session-guardian/SCOPE.md").is_file())

    def test_uninstall_keeps_modified_skill(self):
        self.install("--agent", "generic")
        skill = self.home / ".agents/skills/session-guardian/SKILL.md"
        skill.write_text("edited\n")
        subprocess.run([BASH, str(REPO / "install.sh"), "--uninstall"], env=self.env, check=True, capture_output=True)
        self.assertEqual(skill.read_text(), "edited\n")

    def test_rejects_bad_options_and_invalid_source(self):
        self.assertEqual(self.install("--agent", "nope", check=False).returncode, 2)
        bad = self.home / "bad"
        bad.mkdir()
        p = subprocess.run([BASH, str(REPO / "install.sh"), "--source", str(bad), "--yes"], env=self.env, capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("Invalid package", p.stderr)

    def test_version_pin_from_git(self):
        if not shutil.which("git"):
            self.skipTest("git not installed")
        # Install a pinned commit from a local clone (no network).
        head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        env = dict(self.env, SESSION_GUARDIAN_REPO=str(REPO))
        p = subprocess.run([BASH, str(REPO / "install.sh"), "--yes", "--agent", "none", "--version", head], env=env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(json.loads((self.root / "install-manifest.json").read_text())["ref"], head)


if __name__ == "__main__":
    unittest.main()
