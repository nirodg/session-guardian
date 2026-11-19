import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

CORE = Path(__file__).resolve().parents[1] / "core" / "session_guardian.py"
spec = importlib.util.spec_from_file_location("session_guardian", CORE)
sg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sg)

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_init_creates_memory_and_is_non_destructive(self):
        sg.init(self.root)
        scope = self.root / ".session-guardian" / "SCOPE.md"
        scope.write_text("# My custom scope\n")
        sg.init(self.root)
        self.assertEqual(scope.read_text(), "# My custom scope\n")
        self.assertTrue((self.root / ".session-guardian" / "identity.json").is_file())

    def test_checkpoint_is_manifested_and_auditable(self):
        sg.init(self.root)
        sg.snapshot(self.root)
        checkpoints = sg.list_checkpoints(self.root)
        self.assertEqual(len(checkpoints), 1)
        manifest = json.loads((checkpoints[0] / "manifest.json").read_text())
        self.assertEqual(manifest["format_version"], sg.FORMAT_VERSION)
        self.assertTrue(manifest["files"])
        self.assertEqual(sg.audit(self.root), 0)

    def test_audit_detects_checkpoint_tampering(self):
        sg.init(self.root)
        sg.snapshot(self.root)
        cp = sg.list_checkpoints(self.root)[0]
        (cp / "PROJECT.md").write_text("tampered")
        self.assertEqual(sg.audit(self.root), 1)

    def test_repeated_checkpoint_does_not_overwrite(self):
        sg.init(self.root)
        sg.snapshot(self.root)
        # Use a distinct timestamp to ensure independent recovery points.
        import time
        time.sleep(1.05)
        sg.snapshot(self.root)
        self.assertEqual(len(sg.list_checkpoints(self.root)), 2)

if __name__ == "__main__":
    unittest.main()
