"""scripts/repo_paths.py -- the shared, never-raises replacement for the ~28 `os.path.relpath(p, ROOT)` call
sites that used to crash on a cross-drive path (Windows, `TMP` on a different drive from the repo checkout;
see this module's own docstring for the three test files that reproduced it: test_experiment, test_journal,
test_system_ranking)."""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from repo_paths import repo_rel


class InsideTheRepo(unittest.TestCase):
    def test_a_path_under_root_is_a_posix_relative_path(self):
        p = os.path.join(ROOT, "docs", "architecture", "latency-model.json")
        self.assertEqual(repo_rel(p, ROOT), "docs/architecture/latency-model.json")

    def test_the_result_uses_forward_slashes_even_when_the_input_used_os_sep(self):
        p = ROOT + os.sep + "scripts" + os.sep + "repo_paths.py"
        self.assertEqual(repo_rel(p, ROOT), "scripts/repo_paths.py")
        self.assertNotIn("\\", repo_rel(p, ROOT))

    def test_root_itself_is_a_single_dot(self):
        # os.path.relpath(ROOT, ROOT) == "." -- repo_rel must not treat "." as a "startswith .." escape.
        self.assertEqual(repo_rel(ROOT, ROOT), ".")

    def test_a_relative_input_path_is_accepted_too(self):
        cwd = os.getcwd()
        try:
            os.chdir(ROOT)
            self.assertEqual(repo_rel(os.path.join("scripts", "repo_paths.py"), ROOT), "scripts/repo_paths.py")
        finally:
            os.chdir(cwd)


class OutsideTheRepo(unittest.TestCase):
    def test_a_sibling_directory_of_root_is_an_absolute_posix_path(self):
        # tempfile.mkdtemp() is same-drive-but-outside-the-tree on every CI box this runs on -- the ".."-walk
        # case, not the cross-drive one, and repo_rel must refuse the ".."-walk exactly like the cross-drive
        # case, not return "../../whatever".
        outside = tempfile.mkdtemp(prefix="repo-paths-outside-")
        try:
            p = os.path.join(outside, "some-file.json")
            rel = os.path.relpath(p, ROOT)
            self.assertTrue(rel.startswith(".."), "test fixture assumption: mkdtemp() landed inside ROOT")
            got = repo_rel(p, ROOT)
            self.assertFalse(got.startswith(".."), got)
            self.assertEqual(got, p.replace(os.sep, "/"))
            self.assertTrue(os.path.isabs(got.replace("/", os.sep)) or got[1:3] == ":/", got)
        finally:
            os.rmdir(outside)

    @unittest.skipUnless(sys.platform == "win32" and os.path.isdir("D:\\"), "no D: drive on this machine")
    def test_a_path_on_a_different_drive_never_raises_and_is_absolute(self):
        # The actual defect: os.path.relpath(p, ROOT) raises ValueError here (Windows, cross-drive). This is
        # the reproduction for test_experiment/test_journal/test_system_ranking's TMP=D:/... failures.
        with self.assertRaises(ValueError):
            os.path.relpath("D:\\tmp-tests\\whatever.json", ROOT)
        got = repo_rel("D:\\tmp-tests\\whatever.json", ROOT)
        self.assertEqual(got, "D:/tmp-tests/whatever.json")


if __name__ == "__main__":
    unittest.main(verbosity=2)
