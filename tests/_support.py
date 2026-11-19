"""Shared test helpers. Importing this module isolates SessionGuardian's global state (registry)."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
CORE = REPO / "core" / "session_guardian.py"
# Never touch the real user registry from tests.
DATA = tempfile.mkdtemp(prefix="sg-test-data-")
os.environ["SESSION_GUARDIAN_DATA"] = DATA

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

    def git(self, *args, cwd=None):
        return subprocess.run(["git", "-C", str(cwd or self.root), *args], check=True, capture_output=True, text=True).stdout

    def git_repo(self, root=None):
        root = root or self.root
        self.git("init", "-q", cwd=root)
        self.git("config", "user.email", "test@example.invalid", cwd=root)
        self.git("config", "user.name", "Test", cwd=root)
        self.git("config", "commit.gpgsign", "false", cwd=root)
        (root / "README").write_text("x")
        self.git("add", "README", cwd=root)
        self.git("commit", "-q", "-m", "root", cwd=root)

    def run_cli(self, *args, stdin=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            if stdin is not None:
                import sys
                old = sys.stdin
                sys.stdin = io.StringIO(stdin)
                try:
                    code = sg.main(list(args))
                finally:
                    sys.stdin = old
            else:
                code = sg.main(list(args))
        return code, out.getvalue(), err.getvalue()
