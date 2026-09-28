"""docs/plans/2026-09-27-prop-setup-search-preregistration.md -- the pre-registered prop-challenge search.

Research integrity is the product: a pre-registered candidate list that could silently change after the
first evaluation, a pass/fail count that does not survive a restart, or a report that hides the losers would
each defeat the whole point of pre-registration. These tests attack exactly those properties, plus the
load-time point-in-time seam (CLAUDE.md §8) the search depends on to keep the validation window honestly
unseen until the moment it is judged.

Kept fast per this task's own instruction: synthetic data and monkeypatched I/O throughout, except for two
places that are only meaningful against the real engine -- the PIT seam's byte-identity claim (a real scan,
kept small with `bt.limit_bars`) and one true end-to-end multiprocessing smoke test (a SKIP-path candidate,
which returns before any scan runs).
"""
import concurrent.futures
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import experiment as X


def _bt():
    spec = importlib.util.spec_from_file_location("bt", os.path.join(ROOT, "scripts", "backtest-methods.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ps():
    spec = importlib.util.spec_from_file_location("ps", os.path.join(ROOT, "scripts", "prop-search.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def bar(t, close=100.0, **over):
    d = {"time": t, "open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 10.0}
    d.update(over)
    return d


# ============================================================================================== PIT seam
# CLAUDE.md §8: the load-time cutoff scripts/backtest-methods.py `pit_cutoff()` adds, driving prop-search's
# validation-window truncation.


class SeamOffIsByteIdentical(unittest.TestCase):
    """Task requirement: "Default off; when off, behaviour and output are byte-identical to today (prove
    with a test that compares a small scan with and without the seam unset)." Compares the seam's default
    state (never touched) against explicitly resetting it to None -- the two must be indistinguishable,
    because a caller that merely imports the module and never calls pit_cutoff() must see today's behaviour
    exactly."""

    def test_a_small_real_scan_is_identical_left_default_vs_explicitly_reset(self):
        bt1 = _bt()
        bt1.limit_bars(400)                      # keep the scan small and fast
        r1 = bt1.scan("BTCUSDT", "1H", only=("ICT",))

        bt2 = _bt()
        bt2.limit_bars(400)
        bt2.pit_cutoff(None)                      # explicit no-op -- must change nothing
        r2 = bt2.scan("BTCUSDT", "1H", only=("ICT",))

        self.assertEqual(r1["trades"]["ICT"], r2["trades"]["ICT"])
        self.assertEqual(r1["bars"], r2["bars"])
        self.assertEqual(r1["first"], r2["first"])
        self.assertEqual(r1["last"], r2["last"])

    def test_pit_cutoff_defaults_to_none(self):
        bt = _bt()
        self.assertIsNone(bt._PIT_CUTOFF)


class PitCutoffFiltersAtLoadTime(unittest.TestCase):
    """`load()`'s own logic (bars trim, PIT trim, quality assessment) run for real against synthetic candles
    injected below `_read_history` -- the file-existence check itself uses a REAL (symbol, timeframe) so
    `load()` proceeds past it, but the bytes it reads are ours."""

    def setUp(self):
        self.bt = _bt()
        self._orig_read_history = self.bt._read_history

    def _inject(self, candles):
        self.bt._read_history = lambda p: {"candles": candles, "_source": "synthetic-pit-test"}

    def test_a_spike_after_the_cutoff_does_not_change_what_load_returns(self):
        """A synthetic 'spike' bar placed after the cutoff must not even be visible to the engine -- the
        strongest form of 'must not change any decision': the decision-maker never sees it at all."""
        pre = [bar(f"2026-01-01T{h:02d}:00:00Z", close=100.0) for h in range(10)]
        cutoff = self.bt._N.available_time(pre[-1], "1H").isoformat().replace("+00:00", "Z")
        quiet_tail = [bar(f"2026-01-01T{h:02d}:00:00Z", close=100.0) for h in range(10, 14)]
        spike_tail = [bar(f"2026-01-01T{h:02d}:00:00Z", close=100000.0) for h in range(10, 14)]

        self._inject(pre + quiet_tail)
        self.bt.pit_cutoff(cutoff)
        quiet_result, _ = self.bt.load("BTCUSDT", "1H")

        self.bt._LOAD_CACHE.clear()
        self._inject(pre + spike_tail)
        self.bt.pit_cutoff(cutoff)
        spike_result, _ = self.bt.load("BTCUSDT", "1H")

        self.assertEqual(quiet_result, spike_result,
                         "a candle whose availability is after the cutoff must be invisible to load(), "
                         "spike or not")
        self.assertEqual(len(quiet_result), 10, "only the pre-cutoff bars should survive")

    def test_a_bar_that_opens_before_and_closes_after_the_cutoff_is_excluded(self):
        """1H bar opening 09:00 is AVAILABLE at 10:00 (open + one period). A cutoff at 09:30 sits strictly
        inside that bar's lifetime: it opened before the cutoff but has not yet closed -- its high/low/close
        are not knowable at 09:30, so it must be excluded, not merely truncated in value."""
        rows = [bar("2026-01-01T08:00:00Z"), bar("2026-01-01T09:00:00Z")]
        self._inject(rows)
        self.bt.pit_cutoff("2026-01-01T09:30:00Z")   # inside the 09:00-10:00 bar's lifetime
        result, _ = self.bt.load("BTCUSDT", "1H")
        self.assertEqual([r["time"] for r in result], ["2026-01-01T08:00:00Z"],
                         "the bar that has not yet closed at the cutoff must be excluded")

    def test_available_exactly_at_the_cutoff_is_admissible(self):
        """Boundary convention matches pit.py: available_time == cutoff is ADMITTED."""
        rows = [bar("2026-01-01T08:00:00Z")]
        self._inject(rows)
        self.bt.pit_cutoff("2026-01-01T09:00:00Z")   # exactly this bar's available_time
        result, _ = self.bt.load("BTCUSDT", "1H")
        self.assertEqual(len(result), 1)

    def test_lifting_the_cutoff_restores_every_bar(self):
        # 5 bars opening 00:00..04:00; available_time = open + 1H, so bar[0] (avail 01:00) is the only one
        # <= a 01:30 cutoff -- bar[1] (avail 02:00) is not.
        rows = [bar(f"2026-01-01T{h:02d}:00:00Z") for h in range(5)]
        self._inject(rows)
        self.bt.pit_cutoff("2026-01-01T01:30:00Z")
        self.assertEqual(len(self.bt.load("BTCUSDT", "1H")[0]), 1)
        self.bt._LOAD_CACHE.clear()
        self.bt.pit_cutoff(None)
        self.assertEqual(len(self.bt.load("BTCUSDT", "1H")[0]), 5)


# ============================================================================================ candidate space


class CandidateSpaceDeterminismAndImmutability(unittest.TestCase):
    def test_build_candidate_space_is_deterministic(self):
        ps = _ps()
        a = ps.build_candidate_space()
        b = ps.build_candidate_space()
        self.assertEqual(a, b)

    def test_every_candidate_id_is_unique(self):
        ps = _ps()
        ids = [c["id"] for c in ps.build_candidate_space()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_candidate_space_covers_methods_x_configs_x_timeframes_x_groups(self):
        ps = _ps()
        candidates = ps.build_candidate_space()
        methods = {c["method"] for c in candidates}
        configs = {c["config"] for c in candidates}
        tfs = {c["timeframe"] for c in candidates}
        groups = {(c["group_kind"], c["group_id"]) for c in candidates}
        self.assertEqual(tfs, set(ps.TIMEFRAMES))
        self.assertEqual(configs, {"A", "B", "C"})
        self.assertTrue(methods <= {"ICT", "WYCKOFF-BOOK"})
        # Independently computed from the same registries build_candidate_space() reads, not derived from
        # `candidates` itself -- a self-referential check would pass even if the cross product were wrong.
        n_instruments = len(ps._I.analysis("cfd"))
        n_asset_classes = len(ps._asset_class_groups())
        self.assertEqual(len(groups), n_instruments + n_asset_classes)
        self.assertEqual(len(candidates), len(methods) * len(configs) * len(tfs) * len(groups))

    def test_pooled_asset_class_groups_include_every_member_instrument(self):
        ps = _ps()
        candidates = ps.build_candidate_space()
        pooled = {c["group_id"]: c["symbols"] for c in candidates if c["group_kind"] == "asset_class"}
        self.assertIn("metals", pooled)
        self.assertIn("XAUUSD", pooled["metals"])
        self.assertIn("XAGUSD", pooled["metals"])

    def test_plan_writes_a_hash_that_matches_its_own_candidates(self):
        ps = _ps()
        d = tempfile.mkdtemp()
        try:
            ps.EXPERIMENT_DIR = d
            ps.PLAN_PATH = os.path.join(d, "plan.json")
            payload = ps.cmd_plan()
            self.assertEqual(payload["plan_hash"], ps._hash_candidates(payload["candidates"]))
            self.assertEqual(payload["candidate_count"], len(payload["candidates"]))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_plan_is_a_no_op_when_rerun_unchanged(self):
        ps = _ps()
        d = tempfile.mkdtemp()
        try:
            ps.EXPERIMENT_DIR = d
            ps.PLAN_PATH = os.path.join(d, "plan.json")
            first = ps.cmd_plan()
            mtime1 = os.path.getmtime(ps.PLAN_PATH)
            second = ps.cmd_plan()
            self.assertEqual(first["plan_hash"], second["plan_hash"])
            self.assertEqual(os.path.getmtime(ps.PLAN_PATH), mtime1, "an unchanged plan must not be rewritten")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_plan_refuses_to_silently_change_a_committed_plan(self):
        ps = _ps()
        d = tempfile.mkdtemp()
        try:
            ps.EXPERIMENT_DIR = d
            ps.PLAN_PATH = os.path.join(d, "plan.json")
            ps.cmd_plan()
            # Simulate a drifted candidate space (e.g. the registry changed) by monkeypatching the builder.
            ps.build_candidate_space = lambda: [{"id": "SOMETHING-ELSE", "method": "ICT", "config": "A",
                                                 "timeframe": "1H", "group_kind": "instrument",
                                                 "group_id": "X", "symbols": ["X"]}]
            with self.assertRaises(SystemExit) as cm:
                ps.cmd_plan()
            self.assertIn("refusing to change the committed plan", str(cm.exception))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_load_plan_refuses_a_plan_that_no_longer_matches_the_registry(self):
        ps = _ps()
        d = tempfile.mkdtemp()
        try:
            ps.EXPERIMENT_DIR = d
            ps.PLAN_PATH = os.path.join(d, "plan.json")
            ps.cmd_plan()
            ps.build_candidate_space = lambda: [{"id": "DRIFTED", "method": "ICT", "config": "A",
                                                 "timeframe": "1H", "group_kind": "instrument",
                                                 "group_id": "X", "symbols": ["X"]}]
            with self.assertRaises(SystemExit) as cm:
                ps.load_plan()
            self.assertIn("no longer matches", str(cm.exception))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_load_plan_refuses_when_no_plan_exists(self):
        ps = _ps()
        d = tempfile.mkdtemp()
        try:
            ps.EXPERIMENT_DIR = d
            ps.PLAN_PATH = os.path.join(d, "plan.json")
            with self.assertRaises(SystemExit):
                ps.load_plan()
        finally:
            shutil.rmtree(d, ignore_errors=True)


# ============================================================================================ window split


class WindowSplitByEntryTime(unittest.TestCase):
    def test_development_is_strictly_before_validation_start(self):
        ps = _ps()
        trades = [{"entry_time": "2024-02-29T23:59:59Z"}, {"entry_time": ps.VALIDATION_START}]
        dev, val = ps.split_windows(trades)
        self.assertEqual(len(dev), 1)
        self.assertEqual(dev[0]["entry_time"], "2024-02-29T23:59:59Z")
        self.assertEqual(len(val), 1)
        self.assertEqual(val[0]["entry_time"], ps.VALIDATION_START)

    def test_validation_excludes_the_end_boundary(self):
        ps = _ps()
        trades = [{"entry_time": ps.VALIDATION_END}, {"entry_time": "2025-02-28T23:59:59Z"}]
        dev, val = ps.split_windows(trades)
        self.assertEqual(dev, [])
        self.assertEqual(len(val), 1)
        self.assertEqual(val[0]["entry_time"], "2025-02-28T23:59:59Z")

    def test_a_trade_after_validation_end_is_in_neither_window(self):
        ps = _ps()
        dev, val = ps.split_windows([{"entry_time": "2025-06-01T00:00:00Z"}])
        self.assertEqual(dev, [])
        self.assertEqual(val, [])


# ============================================================================================ pass rule


class ExpectancyLowerBound(unittest.TestCase):
    def test_all_positive_trades_give_a_positive_lower_bound(self):
        ps = _ps()
        r = ps.expectancy_lower_bound([1.0, 1.2, 0.8, 1.5, 0.9], iterations=500)
        self.assertGreater(r["value"], 0)
        self.assertEqual(r["sample"], 5)

    def test_below_the_floor_is_unavailable(self):
        ps = _ps()
        r = ps.expectancy_lower_bound([1.0, 1.0, 1.0, 1.0])  # n=4 < EXPECTANCY_MIN_N=5
        self.assertIn("unavailable", r)

    def test_a_mixed_population_can_have_a_non_positive_lower_bound(self):
        ps = _ps()
        r = ps.expectancy_lower_bound([2.0, -1.0, -1.0, -1.0, -1.0, 0.1], iterations=500)
        self.assertLessEqual(r["value"], 0)

    def test_is_reproducible_for_a_fixed_seed(self):
        ps = _ps()
        rs = [1.0, -0.5, 2.0, -1.0, 0.3, 0.7]
        a = ps.expectancy_lower_bound(rs, seed=42, iterations=300)
        b = ps.expectancy_lower_bound(rs, seed=42, iterations=300)
        self.assertEqual(a["value"], b["value"])


class EvaluatePass(unittest.TestCase):
    def _metrics(self, prob):
        return {"prop_pass_probability": {"value": prob}}

    def test_both_funds_above_threshold_with_enough_days_and_positive_expectancy_passes(self):
        ps = _ps()
        m = {"ftmo-challenge-phase1": self._metrics(0.75), "the5ers-high-stakes-step1": self._metrics(0.80)}
        passed, detail = ps.evaluate_pass(m, trading_days=10, expectancy_lb={"value": 0.05})
        self.assertTrue(passed, detail)

    def test_one_fund_below_threshold_fails(self):
        ps = _ps()
        m = {"ftmo-challenge-phase1": self._metrics(0.69), "the5ers-high-stakes-step1": self._metrics(0.90)}
        passed, detail = ps.evaluate_pass(m, trading_days=10, expectancy_lb={"value": 0.05})
        self.assertFalse(passed)
        self.assertFalse(detail["ftmo-challenge-phase1"]["meets_threshold"])

    def test_below_min_trading_days_for_ftmo_fails_even_with_good_probabilities(self):
        ps = _ps()
        m = {"ftmo-challenge-phase1": self._metrics(0.95), "the5ers-high-stakes-step1": self._metrics(0.95)}
        passed, detail = ps.evaluate_pass(m, trading_days=3, expectancy_lb={"value": 1.0})
        self.assertFalse(passed, "FTMO needs 4 trading days; 3 must fail")
        self.assertFalse(detail["ftmo-challenge-phase1"]["meets_min_trading_days"])
        self.assertTrue(detail["the5ers-high-stakes-step1"]["meets_min_trading_days"], "The5ers only needs 3")

    def test_non_positive_expectancy_lower_bound_fails_even_with_good_probabilities(self):
        ps = _ps()
        m = {"ftmo-challenge-phase1": self._metrics(0.95), "the5ers-high-stakes-step1": self._metrics(0.95)}
        passed, detail = ps.evaluate_pass(m, trading_days=10, expectancy_lb={"value": 0.0})
        self.assertFalse(passed)
        self.assertFalse(detail["expectancy_positive"])

    def test_unavailable_expectancy_lower_bound_fails_closed(self):
        ps = _ps()
        m = {"ftmo-challenge-phase1": self._metrics(0.95), "the5ers-high-stakes-step1": self._metrics(0.95)}
        passed, detail = ps.evaluate_pass(m, trading_days=10, expectancy_lb={"unavailable": "n too small"})
        self.assertFalse(passed)

    def test_unavailable_prop_pass_probability_fails_closed(self):
        ps = _ps()
        m = {"ftmo-challenge-phase1": {"prop_pass_probability": {"unavailable": "n too small"}},
             "the5ers-high-stakes-step1": self._metrics(0.95)}
        passed, detail = ps.evaluate_pass(m, trading_days=10, expectancy_lb={"value": 1.0})
        self.assertFalse(passed)
        self.assertFalse(detail["ftmo-challenge-phase1"]["meets_threshold"])


# ============================================================================================ budget / resume


def _fake_evaluate(candidate, sr=None, *, passed=False, skip=None):
    """A cheap stand-in for `_evaluate_candidate` that still produces a REAL sealed §42 record (so `X.write`/
    `X.load`'s hash check is exercised faithfully) without running the engine at all."""
    if skip:
        return {"skip": skip}
    r = X.Record(hypothesis=f"hypothesis for {candidate['id']}", motivation="test fixture",
                parent_trading_system_version=X.unavailable("test fixture"),
                candidate_version=f"v:{candidate['id']}", experiment_id=candidate["id"])
    metrics = {"validation": {"passed": passed, "trading_days_observed": 10,
                              "expectancy_lower_bound": {"value": 0.1}, "pass_detail": {}, "n_trades": 10},
              "development": {}}
    filler = {f: X.unavailable("test fixture") for f in X.ORDER if f not in r._v}
    filler["metrics"] = metrics
    filler["parameters"] = {"method": candidate["method"], "config": candidate["config"],
                            "timeframe": candidate["timeframe"], "group_kind": candidate["group_kind"],
                            "group_id": candidate["group_id"]}
    for k, v in filler.items():
        r.set(k, v)
    return {"record": dict(r.seal())}


def _candidates(n, prefix="C"):
    return [{"id": f"{prefix}{i}", "method": "ICT", "config": "A", "timeframe": "1H",
            "group_kind": "instrument", "group_id": f"{prefix}{i}", "symbols": [f"{prefix}{i}"]}
           for i in range(n)]


class BudgetAndResume(unittest.TestCase):
    def setUp(self):
        self.ps = _ps()
        self.d = tempfile.mkdtemp()
        self.ps.EXPERIMENT_DIR = self.d
        self.ps.PLAN_PATH = os.path.join(self.d, "plan.json")
        self.ps.RECORDS_DIR = os.path.join(self.d, "records")
        self.ps.SKIPPED_PATH = os.path.join(self.d, "skipped.json")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _set_plan(self, candidates):
        plan = {"candidates": candidates, "plan_hash": "fixture", "candidate_count": len(candidates)}
        self.ps.load_plan = lambda: plan
        return plan

    def test_stops_at_the_budget_and_a_restart_evaluates_nothing_more(self):
        ps = self.ps
        self._set_plan(_candidates(10))
        ps.BUDGET_MAX = 3
        ps.TARGET_PASSES = 100
        ps._evaluate_candidate = lambda c, sr=None: _fake_evaluate(c, passed=False)
        ps.cmd_run(workers=1)
        self.assertEqual(len(os.listdir(ps.RECORDS_DIR)), 3)

        calls = []
        real = ps._evaluate_candidate
        ps._evaluate_candidate = lambda c, sr=None: (calls.append(c["id"]) or _fake_evaluate(c, passed=False))
        ps.cmd_run(workers=1)
        self.assertEqual(calls, [], "budget already spent -- a restart must evaluate nothing more")
        self.assertEqual(len(os.listdir(ps.RECORDS_DIR)), 3)

    def test_stops_at_the_target_pass_count_even_with_budget_remaining(self):
        ps = self.ps
        self._set_plan(_candidates(10))
        ps.BUDGET_MAX = 100
        ps.TARGET_PASSES = 2
        ps._evaluate_candidate = lambda c, sr=None: _fake_evaluate(c, passed=True)
        ps.cmd_run(workers=1)
        recs = [X.load(f[:-5], store=ps.RECORDS_DIR) for f in os.listdir(ps.RECORDS_DIR)]
        self.assertEqual(len(recs), 2, "must stop the moment the 2nd pass is recorded, not run the other 8")
        self.assertTrue(all(r["metrics"]["validation"]["passed"] for r in recs))

    def test_resume_skips_already_recorded_ids(self):
        ps = self.ps
        candidates = _candidates(3)
        self._set_plan(candidates)
        ps.BUDGET_MAX = 100
        ps.TARGET_PASSES = 100
        os.makedirs(ps.RECORDS_DIR, exist_ok=True)
        pre = _fake_evaluate(candidates[0], passed=False)["record"]
        X.write(types.MappingProxyType(pre), store=ps.RECORDS_DIR)

        calls = []
        def spy(c, sr=None):
            calls.append(c["id"])
            return _fake_evaluate(c, passed=False)
        ps._evaluate_candidate = spy
        ps.cmd_run(workers=1)
        self.assertNotIn("C0", calls, "C0 was already recorded and must not be re-evaluated")
        self.assertEqual(set(calls), {"C1", "C2"})
        self.assertEqual(len(os.listdir(ps.RECORDS_DIR)), 3)

    def test_only_restricts_the_run_to_named_candidate_ids(self):
        ps = self.ps
        self._set_plan(_candidates(5))
        ps.BUDGET_MAX = 100
        ps.TARGET_PASSES = 100
        calls = []
        ps._evaluate_candidate = lambda c, sr=None: (calls.append(c["id"]) or _fake_evaluate(c, passed=False))
        ps.cmd_run(only=["C2", "C4"], workers=1)
        self.assertEqual(sorted(calls), ["C2", "C4"])

    def test_skipped_candidates_do_not_count_against_the_budget(self):
        ps = self.ps
        self._set_plan(_candidates(3))
        ps.BUDGET_MAX = 100
        ps.TARGET_PASSES = 100
        ps._evaluate_candidate = lambda c, sr=None: _fake_evaluate(c, skip=f"no history for {c['id']}")
        ps.cmd_run(workers=1)
        self.assertFalse(os.path.isdir(ps.RECORDS_DIR) and os.listdir(ps.RECORDS_DIR))
        skipped = json.load(open(ps.SKIPPED_PATH, encoding="utf-8"))
        self.assertEqual({s["id"] for s in skipped}, {"C0", "C1", "C2"})

    def test_a_tampered_record_stops_the_search_rather_than_being_silently_skipped(self):
        ps = self.ps
        candidates = _candidates(2)
        self._set_plan(candidates)
        os.makedirs(ps.RECORDS_DIR, exist_ok=True)
        rec = _fake_evaluate(candidates[0], passed=False)["record"]
        path = X.write(types.MappingProxyType(rec), store=ps.RECORDS_DIR)
        d = json.load(open(path, encoding="utf-8"))
        d["hypothesis"] = "tampered"
        json.dump(d, open(path, "w", encoding="utf-8"))
        with self.assertRaises(X.Tampered):
            ps.cmd_run(workers=1)


# ============================================================================================ report


class ReportIncludesFailures(unittest.TestCase):
    def setUp(self):
        self.ps = _ps()
        self.d = tempfile.mkdtemp()
        self.ps.EXPERIMENT_DIR = self.d
        self.ps.PLAN_PATH = os.path.join(self.d, "plan.json")
        self.ps.RECORDS_DIR = os.path.join(self.d, "records")
        self.ps.SKIPPED_PATH = os.path.join(self.d, "skipped.json")
        self.ps.REPORT_PATH = os.path.join(self.d, "report.md")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_report_lists_passing_and_failing_candidates_and_the_budget_spent(self):
        ps = self.ps
        candidates = _candidates(3)
        plan = {"candidates": candidates, "plan_hash": "fixture", "candidate_count": len(candidates)}
        ps.load_plan = lambda: plan
        os.makedirs(ps.RECORDS_DIR, exist_ok=True)
        for c, passed in zip(candidates, (True, False, False)):
            rec = _fake_evaluate(c, passed=passed)["record"]
            X.write(types.MappingProxyType(rec), store=ps.RECORDS_DIR)
        md = ps.cmd_report()
        self.assertIn("C0", md)
        self.assertIn("C1", md)
        self.assertIn("C2", md)
        self.assertIn("1 / 5", md.replace("**", ""))   # 1 pass found against the default target
        self.assertIn("3 / 200", md.replace("**", ""))  # budget spent against the default budget

    def test_report_says_so_plainly_when_nothing_passed(self):
        ps = self.ps
        candidates = _candidates(2)
        plan = {"candidates": candidates, "plan_hash": "fixture", "candidate_count": len(candidates)}
        ps.load_plan = lambda: plan
        os.makedirs(ps.RECORDS_DIR, exist_ok=True)
        for c in candidates:
            rec = _fake_evaluate(c, passed=False)["record"]
            X.write(types.MappingProxyType(rec), store=ps.RECORDS_DIR)
        md = ps.cmd_report()
        self.assertIn("None of the 2 evaluated candidates passed", md)

    def test_report_lists_skipped_candidates_with_their_reason(self):
        ps = self.ps
        plan = {"candidates": [], "plan_hash": "fixture", "candidate_count": 0}
        ps.load_plan = lambda: plan
        os.makedirs(ps.EXPERIMENT_DIR, exist_ok=True)
        json.dump([{"id": "NOHIST-1H-XYZ", "reason": "no history before validation start"}],
                 open(ps.SKIPPED_PATH, "w", encoding="utf-8"))
        md = ps.cmd_report()
        self.assertIn("NOHIST-1H-XYZ", md)
        self.assertIn("no history before validation start", md)


# =========================================================================================== parallel workers
#
# Real OS-process spawn (isolated_pool.IsolatedExecutor) requires the calling module to be reconstructible in
# the child by NAME -- true when `scripts/prop-search.py` is invoked as `__main__` (exactly how
# scripts/stability-report.py's own `_worker_scan` already relies on this, and scripts/tests/
# test_isolated_pool.py covers the pool mechanics directly), but NOT true when this test loads the file under
# an artificial importlib module name ("ps") -- pickling `_evaluate_candidate` for a spawned child then fails
# with "No module named 'ps'", a test-harness limitation rather than anything about the code under test. So
# this exercises `cmd_run`'s OWN orchestration logic (chunking, `as_completed`, budget/pass bookkeeping) under
# the `workers > 1` branch with an in-process fake executor standing in for IsolatedExecutor, and leaves the
# real spawn mechanics to isolated_pool.py's own test suite.


class _FakeExecutor:
    """`submit()` runs `fn(*args)` synchronously, in this process, wrapped in a real `concurrent.futures.
    Future` -- same call shape `cmd_run` uses either way (`ex.submit(...)`, `concurrent.futures.
    as_completed(futs)`), no spawn, no pickling."""

    def __init__(self, max_workers):
        self.max_workers = max_workers

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def submit(self, fn, *args):
        fut = concurrent.futures.Future()
        try:
            fut.set_result(fn(*args))
        except BaseException as exc:   # noqa: BLE001 -- report exactly like a real crashed worker would
            fut.set_exception(exc)
        return fut


class ParallelWorkersRouteThroughTheSameOrchestration(unittest.TestCase):
    def test_workers_greater_than_one_still_respects_the_budget(self):
        ps = _ps()
        d = tempfile.mkdtemp()
        try:
            ps.EXPERIMENT_DIR = d
            ps.PLAN_PATH = os.path.join(d, "plan.json")
            ps.RECORDS_DIR = os.path.join(d, "records")
            ps.SKIPPED_PATH = os.path.join(d, "skipped.json")
            candidates = _candidates(6)
            plan = {"candidates": candidates, "plan_hash": "fixture", "candidate_count": len(candidates)}
            ps.load_plan = lambda: plan
            ps.BUDGET_MAX = 4
            ps.TARGET_PASSES = 100
            ps._evaluate_candidate = lambda c, sr=None: _fake_evaluate(c, passed=False)
            ps._pool.IsolatedExecutor = _FakeExecutor
            ps.cmd_run(workers=3)
            self.assertEqual(len(os.listdir(ps.RECORDS_DIR)), 4)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_workers_greater_than_one_skips_a_candidate_without_writing_a_record(self):
        ps = _ps()
        d = tempfile.mkdtemp()
        try:
            ps.EXPERIMENT_DIR = d
            ps.PLAN_PATH = os.path.join(d, "plan.json")
            ps.RECORDS_DIR = os.path.join(d, "records")
            ps.SKIPPED_PATH = os.path.join(d, "skipped.json")
            candidates = _candidates(2)
            plan = {"candidates": candidates, "plan_hash": "fixture", "candidate_count": len(candidates)}
            ps.load_plan = lambda: plan
            ps._evaluate_candidate = lambda c, sr=None: _fake_evaluate(c, skip=f"no history for {c['id']}")
            ps._pool.IsolatedExecutor = _FakeExecutor
            ps.cmd_run(workers=2)
            self.assertFalse(os.path.isdir(ps.RECORDS_DIR) and os.listdir(ps.RECORDS_DIR))
            skipped = json.load(open(ps.SKIPPED_PATH, encoding="utf-8"))
            self.assertEqual({s["id"] for s in skipped}, {"C0", "C1"})
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
