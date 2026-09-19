"""CLAUDE.md §41 stages 1-4 + §42 (docs/plans/2026-09-18-close-feature-gaps.md §0.10) --
`scripts/improve-loop.py`: baseline -> cluster LOSSES -> declared candidates -> one sealed experiment.Record
per candidate -> ranked report.

Three things these tests are built to prove:

1. **The script never invents a candidate.** Every run it makes is one declared in
   `docs/architecture/improve-candidates.json`; a cluster whose key fields match none of them is reported as
   having none (§41: "No candidate is invented at runtime").
2. **Every experiment record is complete and PENDING.** `experiment.Record.seal()` already refuses an
   incomplete record; these tests confirm the SCRIPT supplies every §42 field for a real run, and that the
   decision starts (and, since nothing here calls `experiment.decide`, stays) `PENDING`.
3. **The script never writes the registries it is meant to inform.** A grep of its own source for the three
   write targets must find them only in comments / read paths (§41: "AI must NEVER silently rewrite the
   production Trading System").

Uses a short REAL slice (`--bars`, scripts/backtest-methods.py limit_bars()) so the ICT live scanner -- the
slow part of a full-history run -- stays under the ~60s budget these tests are asked to keep.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import experiment as X

SCRIPT = os.path.join(ROOT, "scripts", "improve-loop.py")
SRC = open(SCRIPT, encoding="utf-8").read()

# A short REAL slice that carries several ICT/Wyckoff loss clusters, with min-size lowered to 2 so the test
# does not need a larger, slower slice to reach the production default of 3.
#
# This used to be ICT on one symbol with a pinned session name ("25,000 BTCUSDT bars carry 2 asia-session
# losses", found empirically). That pinning broke on 2026-09-19 when the ICT scanner gained the deck's first
# liquidity type (Old Highs & Lows, knowledge/ict/core-a.md §2.7): the setup population shifted and the asia
# cluster stopped existing. Two things changed as a result.
#
# 1. The fixture moved to WYCKOFF-BOOK, which is both RICHER and ~4x FASTER here (baseline n=56 in ~24 s,
#    six clusters, four declared candidates matched -- against ICT's n=4 in ~90 s with one cluster and no
#    match). ICT's cost is its per-bar live scanner; WYCKOFF-BOOK detects structures once per series.
# 2. WHICH session clusters is a property of the history in the slice, not of the script, so nothing below
#    asserts a session name any more. The invariants are derived from the run's own --json output.
FAST_ARGS = ["--market", "crypto", "--tf", "15m", "--symbols", "BTCUSDT,ETHUSDT,SOLUSDT",
            "--method", "WYCKOFF-BOOK", "--bars", "60000", "--min-size", "2"]


def _run(store, extra=(), out=None, js=None):
    cmd = [sys.executable, SCRIPT, *FAST_ARGS, "--store", store]
    if out:
        cmd += ["--out", out]
    if js:
        cmd += ["--json", js]
    cmd += list(extra)
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=180)


class NeverWritesTheGovernedRegistries(unittest.TestCase):
    def test_source_never_writes_pilot_top20_methods_or_trading_systems(self):
        # Every occurrence of the three filenames must be in a comment, a docstring, or a read-side string --
        # never the target of an open(..., "w") / write() call on the SAME line.
        forbidden = ("pilot-top20.json", "methods.json", "trading-systems.json")
        for line_no, line in enumerate(SRC.splitlines(), start=1):
            for name in forbidden:
                if name in line:
                    self.assertNotRegex(line, r'open\([^)]*"w"',
                                        f"line {line_no} opens a file containing {name!r} for writing: {line!r}")
                    self.assertNotIn(".write(", line, f"line {line_no} calls .write() near {name!r}: {line!r}")


class RunsEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = tempfile.mkdtemp(prefix="improve-loop-test-")
        # Reports go OUTSIDE the experiment store. The store holds sealed §42 records and the tests below read
        # it with `os.listdir(...).endswith(".json")`; a report.json sitting in there is picked up as a record
        # and fails experiment.load()'s tamper check, which is a confusing way to learn you put a file in the
        # wrong place.
        cls.outdir = tempfile.mkdtemp(prefix="improve-loop-out-")
        cls.out = os.path.join(cls.outdir, "report.md")
        cls.js = os.path.join(cls.outdir, "report.json")
        cls.proc = _run(cls.store, out=cls.out, js=cls.js)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.store, ignore_errors=True)
        shutil.rmtree(cls.outdir, ignore_errors=True)

    def test_it_exits_zero(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr[-4000:])

    def test_it_writes_a_report(self):
        self.assertTrue(os.path.exists(self.out))
        text = open(self.out, encoding="utf-8").read()
        self.assertIn("Con người quyết định", text)      # the §41 stage 11 "human decides" sentence

    def test_it_writes_at_least_one_pending_experiment_record(self):
        records = [f for f in os.listdir(self.store) if f.endswith(".json")]
        self.assertGreaterEqual(len(records), 1, self.proc.stdout)
        rec = X.load(records[0][:-5], store=self.store)
        self.assertEqual(rec["decision"]["decision"], "PENDING")

    def test_every_seven_and_forty_two_field_is_present_and_sealed(self):
        # experiment.Record.seal() already refuses an incomplete record, so a record on disk having loaded
        # (hash re-checked by X.load) proves completeness. This test additionally names the fields, so a
        # future field this script forgot to `.set()` fails loudly here rather than only inside seal().
        records = [f for f in os.listdir(self.store) if f.endswith(".json")]
        rec = X.load(records[0][:-5], store=self.store)
        import experiment as X_
        for fid in X_.ORDER:
            self.assertIn(fid, rec, f"missing §42 field {fid!r}")

    def test_the_slice_actually_produced_a_cluster(self):
        """Guard against the whole class passing vacuously: if the slice carries no repeated-failure cluster,
        the two invariants below have nothing to bind on and the run proves nothing."""
        d = json.load(open(self.js, encoding="utf-8"))
        self.assertGreaterEqual(len(d["clusters"]["clusters"]), 1,
                                f"no loss cluster in the fixture slice; widen --bars or --symbols. "
                                f"stdout:\n{self.proc.stdout[-2000:]}")

    def test_every_cluster_is_either_matched_to_a_declared_candidate_or_reported_as_unmatched(self):
        """§41's actual promise: "No candidate is invented at runtime". So for every cluster the run found,
        exactly one of two things must be true -- a candidate DECLARED in improve-candidates.json ran against
        it, or the report names it as having none. Nothing is quietly dropped, and nothing is made up.

        Derived from the run rather than pinned to a session name, because which session clusters is a
        property of the history in the slice, not of the script (see the FAST_ARGS note)."""
        d = json.load(open(self.js, encoding="utf-8"))
        declared = json.load(open(os.path.join(ROOT, "docs", "architecture", "improve-candidates.json"),
                                  encoding="utf-8"))["candidates"]
        text = open(self.out, encoding="utf-8").read()
        ran = {c["candidate_id"] for c in d["candidates"]}
        for c in d["clusters"]["clusters"]:
            keyed = [(f, v) for f, v in c["key"].items()
                     if v is not None and f in declared and str(v) in declared[f]]
            if keyed:
                field, value = keyed[0]
                self.assertTrue(any(f"{field}={value}" in r for r in ran),
                                f"cluster {c['key']} matches declared candidate {field}={value} but no "
                                f"candidate ran for it; ran={sorted(ran)}")
            else:
                self.assertIn("Không có ứng viên khai báo", text,
                              "a cluster with no declared candidate must be reported as such, not dropped")

    def test_a_cluster_with_no_declared_candidate_is_named_in_the_report(self):
        """The other half of §41's promise, exercised directly rather than by hunting for a slice of history
        that happens to contain an unmatched cluster. `_report` is the function that decides whether an
        unmatched cluster is visible or silently dropped, so it is the thing worth testing."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("il_report", SCRIPT)
        il = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(il)
        unmatched = [{"key": {"method": "ICT", "session": "off", "vol_type": None, "via": None},
                      "n": 4, "states": {"LOSS": 4}}]
        args = type("A", (), {"market": "crypto", "tf": "15m", "objective": "expectancy", "min_size": 2,
                              "bars": None, "account": None, "trader": None, "fee_pct": 0.05,
                              "min_trades": 20})()
        md = il._report(args, "run-1", "ICT", ["BTCUSDT"], "2026-01-01", "2026-02-01",
                        {"n": 0, "expectancy": None}, [], [],
                        {"clusters": [], "min_size": 2, "grouped_by": list(il.BY_FIELDS), "singletons": 0},
                        [], unmatched)
        self.assertIn("Không có ứng viên khai báo", md)
        self.assertIn("'off'", md, "the unmatched cluster's own key must be printed, not just a heading")

    def test_a_candidate_that_could_not_run_is_reported_instead_of_crashing_the_report(self):
        """Found 2026-09-19: two declared candidates overrode `ict_disp`, an OPTS key removed that day
        (finding 11). `_apply_override` correctly refused them and recorded {"candidate_id", "error"} rows --
        and then `_report` indexed row["n"] on those rows and killed the whole run with a KeyError, hiding
        WHICH candidate was broken behind a traceback. The registry entries are gone; this keeps the report
        honest for the next one."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("il_report2", SCRIPT)
        il = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(il)
        args = type("A", (), {"market": "crypto", "tf": "15m", "objective": "expectancy", "min_size": 2,
                              "bars": None, "account": None, "trader": None, "fee_pct": 0.05,
                              "min_trades": 20})()
        md = il._report(args, "run-1", "ICT", ["BTCUSDT"], "2026-01-01", "2026-02-01",
                        {"n": 0, "expectancy": None}, [], [],
                        {"clusters": [], "min_size": 2, "grouped_by": list(il.BY_FIELDS), "singletons": 0},
                        [{"candidate_id": "session=asia", "error": "override key 'ict_disp' is not an OPTS key"}],
                        [])
        self.assertIn("KHÔNG CHẠY ĐƯỢC", md)
        self.assertIn("ict_disp", md)

    def test_no_declared_candidate_overrides_a_key_the_engine_no_longer_has(self):
        """The registry is data, and data can name a key that has been deleted. Catch it here rather than in
        a five-minute end-to-end run (finding 11 removed `ict_disp`, `ict_pd` and `std_origin` from OPTS)."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("il_keys", SCRIPT)
        il = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(il)
        declared = json.load(open(os.path.join(ROOT, "docs", "architecture", "improve-candidates.json"),
                                  encoding="utf-8"))["candidates"]
        for field, vals in declared.items():
            for value, spec_ in vals.items():
                for key in spec_["override"]:
                    if key == "sessions":
                        continue
                    self.assertIn(key, il.bt.OPTS,
                                  f"candidate {field}={value} overrides {key!r}, which is not an OPTS key")

    def test_no_candidate_ran_that_the_registry_does_not_declare(self):
        d = json.load(open(self.js, encoding="utf-8"))
        declared = json.load(open(os.path.join(ROOT, "docs", "architecture", "improve-candidates.json"),
                                  encoding="utf-8"))["candidates"]
        allowed = {f"{f}={v}" for f, vals in declared.items() for v in vals}
        for c in d["candidates"]:
            self.assertIn(c["candidate_id"], allowed,
                          f"{c['candidate_id']} is not declared in improve-candidates.json (§41)")


class RejectsAnUndeclaredOverrideKey(unittest.TestCase):
    def test_apply_override_refuses_a_key_that_is_neither_sessions_nor_an_opts_key(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("il_test", SCRIPT)
        il = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(il)
        with self.assertRaises(ValueError):
            il._apply_override({"min_rr": 3.0}, None, {"not_a_real_key": True})


class LoadCandidatesValidates(unittest.TestCase):
    def test_the_live_registry_loads(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("il_test2", SCRIPT)
        il = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(il)
        table = il._load_candidates()
        self.assertIn("session", table)
        self.assertIn("asia", table["session"])


if __name__ == "__main__":
    unittest.main()


class CandidateRowsCanBeRankedByPropPass(unittest.TestCase):
    """User decision 2026-09-19: the loop exists to find the candidate that PASSES the challenge most often,
    so every candidate row must carry the §39 keys ranking.py sorts those objectives on."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location("il_rank", SCRIPT)
        cls.IL = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.IL)

    def test_ranking_keys_are_copied_unchanged_from_the_perf_block(self):
        stats = {"n": 20, "perf": {"expectancy": 0.3, "max_drawdown": 0.12, "time_in_drawdown": 0.4,
                                   "prop_pass_probability": {"value": 0.21, "low_confidence": True},
                                   "account_failure_probability": {"value": 0.62},
                                   "sortino": 0.9, "sharpe": 0.7}}
        keys = self.IL._ranking_keys(stats, {"ruin": None, "failed_by": None})
        self.assertEqual(keys["prop_pass_probability"], stats["perf"]["prop_pass_probability"])
        self.assertEqual(keys["max_drawdown"], 0.12)
        self.assertIsNone(keys["ruin"])

    def test_an_unavailable_marker_is_carried_through_not_zeroed(self):
        marker = {"unavailable": "no account", "owner": "§39"}
        keys = self.IL._ranking_keys({"n": 5, "perf": {"prop_pass_probability": marker}}, {"ruin": None})
        self.assertEqual(keys["prop_pass_probability"], marker)

    def test_rows_with_these_keys_actually_sort_under_the_prop_pass_objective(self):
        import ranking as R
        rows = [{"id": "a", "prop_pass_probability": {"value": 0.10}},
                {"id": "b", "prop_pass_probability": {"value": 0.44}},
                {"id": "c", "prop_pass_probability": {"unavailable": "n too small"}}]
        ranked = R.rank(rows, objective_id="prop_pass_rate")["ranked"]
        self.assertEqual(ranked[0]["row"]["id"], "b")          # highest pass rate first
        self.assertEqual(ranked[-1]["row"]["id"], "c")         # unmeasurable sorts last, never wins
