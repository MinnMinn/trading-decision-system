"""scripts/research/prereg_guard.py in temporary git repositories (no market data, no outcome).

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_prereg_guard
(the VC, OIL and CAL drafts of 2026-10-04: docs/plans/2026-10-04-*-preregistration-DRAFT.md)
"""
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


G = _load("prereg_guard", "scripts/research/prereg_guard.py")
VC_DRAFT = "docs/plans/2026-10-04-vc-volatility-condition-preregistration-DRAFT.md"
VC_SEALED = "docs/plans/2026-10-04-vc-volatility-condition-preregistration.md"


def git(root, *args):
    subprocess.run(["git", "-C", root, *args], check=True, capture_output=True, text=True)


class Repo(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        git(self.root, "init", "-q")
        git(self.root, "config", "user.email", "t@example.invalid")
        git(self.root, "config", "user.name", "t")
        git(self.root, "config", "commit.gpgsign", "false")
        git(self.root, "config", "core.excludesFile", os.devnull)        # a user's global ignore must not hide docs/

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, rel, text):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        return p

    def commit(self, *rels):
        git(self.root, "add", "-f", *rels)
        git(self.root, "commit", "-q", "-m", "x")


class Sealed(Repo):
    def test_the_vc_draft_committed_unchanged_under_the_sealed_name_is_refused(self):
        """The reviewer's probe (2026-10-04): the draft's own instructions contain the words 'Status: SEALED'."""
        with open(os.path.join(ROOT, VC_DRAFT), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("Status: SEALED", text)
        self.write(VC_SEALED, text)
        self.commit(VC_SEALED)
        with self.assertRaises(SystemExit):
            G.require_sealed(self.root, VC_SEALED, "[VC-P1]")

    def test_exact_line_passes_and_returns_the_text(self):
        text = "# x [VC-P1]\n\nStatus: SEALED\n\nbody\n"
        self.write(VC_SEALED, text)
        self.commit(VC_SEALED)
        self.assertEqual(G.require_sealed(self.root, VC_SEALED, "[VC-P1]"), text)

    def test_draft_line_tag_name_and_cleanliness(self):
        with self.assertRaises(SystemExit):
            G.check_sealed_text("[VC-P1]\nStatus: SEALED\nStatus: DRAFT. Not sealed.\n", "x", "[VC-P1]")
        with self.assertRaises(SystemExit):
            G.check_sealed_text("Status: SEALED\n", "x", "[VC-P1]")
        with self.assertRaises(SystemExit):
            G.check_sealed_text("[VC-P1] the line 'Status: SEALED' goes here\n", "x", "[VC-P1]")
        with self.assertRaises(SystemExit):
            G.require_sealed(self.root, VC_DRAFT, "[VC-P1]")
        self.write(VC_SEALED, "[VC-P1]\nStatus: SEALED\n")
        with self.assertRaises(SystemExit):
            G.require_sealed(self.root, VC_SEALED, "[VC-P1]")                    # untracked
        self.commit(VC_SEALED)
        self.write(VC_SEALED, "[VC-P1]\nStatus: SEALED\nedited\n")
        with self.assertRaises(SystemExit):
            G.require_sealed(self.root, VC_SEALED, "[VC-P1]")                    # uncommitted change


class Fingerprint(Repo):
    def test_manifest_roundtrip_and_change_after_seal(self):
        self.write("scripts/research/a.py", "A = 1\n")
        self.write("scripts/tests/test_a.py", "T = 1\n")
        code = ("scripts/research/a.py", "scripts/tests/test_a.py")
        text = "[X]\nStatus: SEALED\n\n" + "\n".join(G.manifest_lines(self.root, code)) + "\n"
        man = G.require_fingerprint(self.root, text, code)
        self.assertEqual(set(man), set(code))
        self.write("scripts/research/a.py", "A = 2\n")                          # edited (and maybe committed) later
        with self.assertRaises(SystemExit):
            G.require_fingerprint(self.root, text, code)

    def test_a_needed_file_missing_from_the_manifest_is_refused(self):
        self.write("scripts/research/a.py", "A = 1\n")
        self.write("scripts/research/b.py", "B = 1\n")
        text = "\n".join(G.manifest_lines(self.root, ["scripts/research/a.py"]))
        with self.assertRaises(SystemExit):
            G.require_fingerprint(self.root, text, ["scripts/research/a.py", "scripts/research/b.py"])

    def test_duplicate_or_malformed_lines(self):
        line = G.manifest_lines(ROOT, ["scripts/research/prereg_guard.py"])[0]
        with self.assertRaises(SystemExit):
            G.manifest(line + "\n" + line + "\n")
        self.assertEqual(G.manifest("code-sha256 abc scripts/x.py\n"), {})            # not 64 hex: not a manifest line

    def test_trace_sees_spec_loaded_modules_and_config_files(self):
        self.write("scripts/research/listed.py", "X = 1\n")
        self.write("scripts/research/hidden.py", "Y = 2\n")
        self.write("docs/architecture/conf.json", "{}\n")
        self.write("data/history/ftmo/bars.json", "[]\n")
        G.trace_start(self.root)
        for name in ("listed", "hidden"):
            spec = importlib.util.spec_from_file_location(name, os.path.join(self.root, "scripts/research", name + ".py"))
            spec.loader.exec_module(importlib.util.module_from_spec(spec))
        open(os.path.join(self.root, "docs/architecture/conf.json")).close()
        open(os.path.join(self.root, "data/history/ftmo/bars.json")).close()
        self.assertEqual(G.executed_code(), {"scripts/research/listed.py", "scripts/research/hidden.py"})
        with self.assertRaises(SystemExit):
            G.require_covered(["scripts/research/listed.py"])
        G.require_covered(["scripts/research/listed.py", "scripts/research/hidden.py"])
        self.assertEqual(list(G.opened_files(self.root)), ["docs/architecture/conf.json"])
        G.trace_start(self.root)                                              # a new trace starts empty
        self.assertEqual(G.executed_code(), set())


class Overwrite(unittest.TestCase):
    def test_refuse_overwrite(self):
        with tempfile.NamedTemporaryFile() as fh:
            with self.assertRaises(SystemExit):
                G.refuse_overwrite(fh.name)
        G.refuse_overwrite(os.path.join(tempfile.gettempdir(), "does-not-exist-prereg-guard.json"))


if __name__ == "__main__":
    unittest.main()
