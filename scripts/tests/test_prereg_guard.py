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


class ReadOnce(Repo):
    """Review item 18 (2026-10-04): refuse_overwrite alone let a second run of a read write to another path."""
    OUT = "docs/audits/2026-11-02-edge-vc-xau-holdout.json"

    def test_the_output_name_is_fixed_per_read(self):
        G.require_read_once(self.root, self.OUT, "vc", "xau-holdout")
        for bad in ("docs/audits/edge-vc-xau-holdout.json", "docs/audits/2026-11-02-edge-vc-crypto.json",
                    "tmp/2026-11-02-edge-vc-xau-holdout.json", "docs/audits/2026-11-02-edge-vc-xau-holdout.json.bak",
                    "docs/audits/sub/2026-11-02-edge-vc-xau-holdout.json"):
            with self.assertRaises(SystemExit):
                G.require_read_once(self.root, bad, "vc", "xau-holdout")

    def test_a_second_run_to_another_path_is_refused_while_the_first_is_on_disk(self):
        self.write("docs/audits/2026-11-01-edge-vc-xau-holdout.json", "{}\n")          # untracked first run
        with self.assertRaises(SystemExit) as cm:
            G.require_read_once(self.root, self.OUT, "vc", "xau-holdout")
        self.assertIn("2026-11-01-edge-vc-xau-holdout.json", str(cm.exception))
        G.require_read_once(self.root, "docs/audits/2026-11-02-edge-vc-crypto.json", "vc", "crypto")   # another read
        G.require_read_once(self.root, "docs/audits/2026-11-02-edge-oil-xau-holdout.json", "oil", "xau-holdout")

    def test_a_read_ever_committed_is_refused_even_after_deletion(self):
        first = "docs/audits/2026-11-01-edge-vc-xau-holdout.json"
        self.write(first, "{}\n")
        self.commit(first)
        git(self.root, "rm", "-q", first)
        git(self.root, "commit", "-q", "-m", "drop")
        self.assertFalse(os.path.exists(os.path.join(self.root, first)))
        with self.assertRaises(SystemExit) as cm:
            G.require_read_once(self.root, self.OUT, "vc", "xau-holdout")
        self.assertIn("committed before", str(cm.exception))

    def test_a_read_committed_on_another_branch_is_refused(self):
        self.write("README", "x\n")
        self.commit("README")
        git(self.root, "checkout", "-q", "-b", "side")
        first = "docs/audits/2026-11-01-edge-vc-xau-holdout.json"
        self.write(first, "{}\n")
        self.commit(first)
        git(self.root, "checkout", "-q", "-")
        self.assertFalse(os.path.exists(os.path.join(self.root, first)))
        with self.assertRaises(SystemExit):
            G.require_read_once(self.root, self.OUT, "vc", "xau-holdout")

    def test_outside_a_git_repository_it_cannot_verify_and_refuses(self):
        plain = tempfile.mkdtemp()
        try:
            with self.assertRaises(SystemExit) as cm:
                G.require_read_once(plain, self.OUT, "vc", "xau-holdout")
            self.assertIn("cannot check the git history", str(cm.exception))
        finally:
            shutil.rmtree(plain, ignore_errors=True)


class SealTime(Repo):
    """Review (2026-10-04, fix round): the forward reads trusted a --seal-date typed on the command line."""

    def commit_at(self, stamp, *rels):
        env = dict(os.environ, GIT_COMMITTER_DATE=stamp, GIT_AUTHOR_DATE=stamp)
        subprocess.run(["git", "-C", self.root, "add", "-f", *rels], check=True, capture_output=True, env=env)
        subprocess.run(["git", "-C", self.root, "commit", "-q", "-m", "x"], check=True, capture_output=True, env=env)

    def test_the_seal_instant_is_the_commit_that_added_the_text(self):
        import datetime
        utc3 = datetime.timezone(datetime.timedelta(hours=3))
        self.write(VC_SEALED, "[VC-P1]\nStatus: SEALED\n")
        self.commit_at("2026-10-05T23:30:00+03:00", VC_SEALED)
        self.assertEqual(G.seal_time(self.root, VC_SEALED), datetime.datetime(2026, 10, 5, 23, 30, tzinfo=utc3))
        self.assertEqual(G.first_forward_day(self.root, VC_SEALED, utc3), datetime.date(2026, 10, 6))
        # the same instant seen from a zone where it is already the next day
        utc8 = datetime.timezone(datetime.timedelta(hours=8))
        self.assertEqual(G.first_forward_day(self.root, VC_SEALED, utc8), datetime.date(2026, 10, 7))
        self.write(VC_SEALED, "[VC-P1]\nStatus: SEALED\namended\n")              # an amendment does not move it
        self.commit_at("2026-12-01T10:00:00+03:00", VC_SEALED)
        self.assertEqual(G.first_forward_day(self.root, VC_SEALED, utc3), datetime.date(2026, 10, 6))

    def test_no_commit_means_no_seal(self):
        self.write(VC_SEALED, "[VC-P1]\nStatus: SEALED\n")                          # on disk, never committed
        with self.assertRaises(SystemExit):
            G.seal_time(self.root, VC_SEALED)


class ReadJson(Repo):
    """An earlier read's JSON is used only when its name, commit state, tag and read match (VC --xau, OIL --after)."""
    GOLD = "docs/audits/2026-11-02-edge-vc-xau-holdout.json"

    def put(self, rel, meta, commit=True):
        import json
        self.write(rel, json.dumps({"meta": meta, "primary": {"x": 1}}))
        if commit:
            self.commit(rel)

    def test_a_committed_read_with_its_tag_and_read_passes(self):
        self.put(self.GOLD, {"tag": "[VC-P1]", "read": "xau-holdout"})
        self.assertEqual(G.require_read_json(self.root, self.GOLD, "vc", "xau-holdout", "[VC-P1]")["primary"], {"x": 1})

    def test_wrong_name_tag_read_or_commit_state_is_refused(self):
        other = "docs/audits/2026-11-02-edge-vc-crypto.json"
        self.put(other, {"tag": "[VC-P1]", "read": "xau-holdout"})
        with self.assertRaises(SystemExit):
            G.require_read_json(self.root, other, "vc", "xau-holdout", "[VC-P1]")          # another read's name
        self.put(self.GOLD, {"tag": "[CX-P1]", "read": "xau-holdout"})
        with self.assertRaises(SystemExit):
            G.require_read_json(self.root, self.GOLD, "vc", "xau-holdout", "[VC-P1]")     # another family's tag
        self.put(self.GOLD, {"tag": "[VC-P1]", "read": "forward"})
        with self.assertRaises(SystemExit):
            G.require_read_json(self.root, self.GOLD, "vc", "xau-holdout", "[VC-P1]")     # another read
        self.put(self.GOLD, {"tag": "[VC-P1]", "read": "xau-holdout"}, commit=False)
        with self.assertRaises(SystemExit):
            G.require_read_json(self.root, self.GOLD, "vc", "xau-holdout", "[VC-P1]")     # edited after its commit


class CandlesDigest(unittest.TestCase):
    def test_canonical_and_order_sensitive(self):
        a = {"time": "2026-10-05T00:00:00Z", "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "tick_volume": 7}
        b = {"time": "2026-10-05T00:05:00Z", "open": 1.5, "high": 2.5, "low": 1.0, "close": 2.0}
        d = G.candles_digest([a, b])
        self.assertEqual(len(d), 64)
        self.assertEqual(d, G.candles_digest([dict(a, tick_volume=99), b]))       # only time / OHLC count
        self.assertNotEqual(d, G.candles_digest([b, a]))
        self.assertNotEqual(d, G.candles_digest([dict(a, close=1.6), b]))


if __name__ == "__main__":
    unittest.main()
