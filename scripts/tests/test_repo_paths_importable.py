"""Every script that imports repo_paths must be loadable by PATH from any sys.path.

2026-09-27 regression: scripts/automation.py gained `from repo_paths import repo_rel` without putting scripts/ on
sys.path. `scripts/scan-loop.sh` loads it with spec_from_file_location from a heredoc, the import failed inside
an `except Exception: pass`, the SCANWIN_* settings stayed unset, and every scan style was skipped from
2026-09-27T05:46Z on (data/live/scan-loop.log) -- the live chart froze with nothing failing loud.
"""
import os, re, subprocess, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS = os.path.join(ROOT, "scripts")


class RepoPathsImportable(unittest.TestCase):
    def test_every_importer_puts_scripts_on_sys_path_first(self):
        bad = []
        for name in sorted(os.listdir(SCRIPTS)):
            if not name.endswith(".py"):
                continue
            src = open(os.path.join(SCRIPTS, name), encoding="utf-8").read()
            m = re.search(r"^(from repo_paths import|import repo_paths)", src, re.M)
            if m and "sys.path.insert" not in src[:m.start()]:
                bad.append(name)
        self.assertEqual(bad, [], "import repo_paths only after sys.path.insert(0, <scripts dir>)")

    def test_scan_loop_gate_loads_automation_from_the_repo_root(self):
        # The same load scan-loop.sh does, in a fresh interpreter whose sys.path has no scripts/ entry.
        code = ("import importlib.util; s = importlib.util.spec_from_file_location('automation', 'scripts/automation.py'); "
                "m = importlib.util.module_from_spec(s); s.loader.exec_module(m); print(sorted(m.SCAN_WINDOW))")
        r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=120,
                           env=dict(os.environ, PYTHONPATH=""))
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertIn("15m", r.stdout)


if __name__ == "__main__":
    unittest.main()
