"""Config-write integrity. A second writer (the applier cron) is coming, and today's read-modify-write is
neither atomic nor locked, and silently replaces an unreadable config with permissive defaults.
Rules CFG-01, CFG-02, CFG-05, CFG-06, CFG-07 in docs/security/2026-09-12-method-panel.md."""
import json, os, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AUTO = os.path.join(ROOT, "scripts", "automation.py")
CONFIG = os.path.join(ROOT, "docs", "architecture", "automation-config.json")


class ConfigIntegrity(unittest.TestCase):
    def setUp(self):
        self.backup = tempfile.NamedTemporaryFile(delete=False).name
        shutil.copy(CONFIG, self.backup)

    def tearDown(self):
        shutil.copy(self.backup, CONFIG); os.unlink(self.backup)

    def run_auto(self, *args):
        return subprocess.run([sys.executable, AUTO, *args], capture_output=True, text=True)

    def test_unreadable_config_is_never_overwritten(self):
        """CFG-02: a corrupt file must stop the write, not be replaced by permissive DEFAULTS."""
        open(CONFIG, "w").write("{ this is not json")
        r = self.run_auto("dimension", "heatmap", "off", "--market", "crypto")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("unreadable", (r.stdout + r.stderr).lower())
        self.assertEqual(open(CONFIG).read(), "{ this is not json",
                         "the corrupt file was overwritten -- CFG-02 violated")

    def test_audit_strings_are_sanitised(self):
        """CFG-05: newlines and ANSI in an audit string must not forge a second history row."""
        r = self.run_auto("dimension", "heatmap", "off", "--market", "crypto",
                          "--reason", "line one\nline two\x1b[31mred\x1b[0m")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        row = json.load(open(CONFIG, encoding="utf-8"))["history"][-1]
        self.assertNotIn("\n", row["detail"] or "")
        self.assertNotIn("\x1b", row["detail"] or "")

    def test_write_is_atomic_no_partial_file(self):
        """CFG-01: os.replace, so a reader never sees a truncated file."""
        src = open(AUTO, encoding="utf-8").read()
        self.assertIn("os.replace", src)
        self.assertIn("flock", src)

    def test_evicted_history_rows_are_archived(self):
        """CFG-07: the 200-row ring must not be a silent shredder once a cron writes to it."""
        src = open(AUTO, encoding="utf-8").read()
        self.assertIn("history-archive", src)


if __name__ == "__main__":
    unittest.main()
