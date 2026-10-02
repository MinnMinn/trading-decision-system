"""The fund-setup harness (docs/plans/2026-09-28-methodology-improvement-plan.md §1.4) -- adversarial tests.

Research integrity is the product: a no-edge strategy must NOT pass at N = 205 while a large true edge must; V
values chosen on a training fold must never see the test fold (the test fold's data is POISONED to prove it); the
lower bound must use pooled TEST trades only; a fold with 29 trades is "insufficient"; one huge trade cannot carry a
result; the run refuses without the ledger declaration; nothing is dropped after results are seen; a run with zero
passes says so. All data is synthetic -- no real history is evaluated here (that is Batch 3).

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_fund_search
"""
import contextlib
import copy
import datetime
import hashlib
import importlib.util
import io
import json
import math
import os
import random
import shutil
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import fund_stats as FS
import experiment as X

FIXTURES = os.path.join(ROOT, "scripts", "tests", "fixtures")


def _fs():
    spec = importlib.util.spec_from_file_location("fund_search_mod", os.path.join(ROOT, "scripts", "fund-search.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_REAL_FIRST_BAR = _fs()._first_bar
_REAL_DEV_BARS = {tf: dict(rows) for tf, rows in _fs().DEV_BARS.items()}      # the committed table, before any test patches it
SYMS = ["XAUUSD", "XAGUSD", "US500", "US30", "USTEC", "DE40", "FRA40"]
DEV_START = "2020-03-01T00:00:00Z"
LONG_START = "2014-03-01T00:00:00Z"   # ten development years: enough quarters/half-years for the block bounds


def gen(start, end, n, mean, sd, seed, symbols=SYMS, extra=None):
    """n trades evenly spread over [start, end), R ~ N(mean, sd), ADX random in [10, 40]."""
    rng = random.Random(seed)
    a, b = FS.ts(start), FS.ts(end)
    span = (b - a) / n
    out = []
    for i in range(n):
        t = a + span * (i + 0.5)
        tr = {"entry_time": FS.iso(t), "exit_time": FS.iso(t + datetime.timedelta(hours=2)),
              "net_R": rng.gauss(mean, sd), "symbol": symbols[i % len(symbols)], "adx14_d1": rng.uniform(10, 40)}
        if extra:
            tr.update(extra)
        out.append(tr)
    return out


def grid_two_items():
    return FS.Grid({"method": "ICT", "items": [
        {"id": "a", "key": "fx_a", "existing_opts_key": None, "values": ["x", "y", "z"], "joint_group": None,
         "source": "t", "implemented": True},
        {"id": "b", "key": "fx_b", "existing_opts_key": None, "values": [0, 1], "joint_group": None,
         "source": "t", "implemented": True}]})


#: The synthetic grid's ordinal table (the REAL table is FS.PERTURBATION_AXES, tested separately): item "a" is ordinal
#: x < y < z, item "b" ordinal 0 < 1.
TEST_AXES = {"a": [{"component": "a", "part": None, "order": ["x", "y", "z"]}],
             "b": [{"component": "b", "part": None, "order": [0, 1]}]}


def _seed(values):
    return hash(json.dumps(values, sort_keys=True)) & 0xFFFF   # only used inside one process


class SynthEngine:
    """trades_for(values) over the development span; every distinct V assignment draws its OWN sample."""

    def __init__(self, mean=0.0, sd=1.0, per_year=150, prop=None, mean_by=None, symbols=SYMS, salt=0,
                 stress_cost=0.02, prop_shifted=None):
        self.salt = salt
        self.stress_cost = stress_cost                 # R charged by the stress re-pricing (p90 spread + commission margin)
        self.prop_shifted = prop_shifted               # per-fund prop pass once R is shifted down (None = same as `prop`)
        self.shifts = []
        self.mean, self.sd, self.per_year, self.symbols = mean, sd, per_year, symbols
        self.prop = prop if prop is not None else {"ftmo": 0.9, "the5ers": 0.9}
        self.mean_by = mean_by or (lambda values: mean)
        self.calls = []

    def trades_for(self, values):
        self.calls.append(dict(values))
        years = 10
        return gen(LONG_START, FS.DEV_CUTOFF, self.per_year * years, self.mean_by(values), self.sd,
                   seed=f"{self.salt}:" + json.dumps(values, sort_keys=True), symbols=self.symbols)

    def prop_pass(self, pooled, r_shift=0.0, weekdays=None):
        self.shifts.append(r_shift)
        if r_shift and self.prop_shifted is not None:
            return dict(self.prop_shifted)
        return dict(self.prop)

    def stress_trades(self, pooled):
        return [dict(t, net_R=t["net_R"] - self.stress_cost) for t in pooled]

    def rollover_edge_stats(self, values, fold=None):
        return _fs().rollover_edge_stats([t["entry_time"] for t in self.trades_for(values)][:7], fold)

    def admission_stats(self, values, fold=None):
        rows = [{"entry_time": t["entry_time"], "R_planned": 3.0 + (i % 5) * 0.1, "fee_R": 0.05 * (i % 7)}
                for i, t in enumerate(self.trades_for(values))]
        # item 12: every 11th candidate has no valid stop distance (a counted `zero_risk` row, no R_planned / fee_R)
        rows = [{"entry_time": r["entry_time"], "zero_risk": "zero"} if i % 11 == 0 else r for i, r in enumerate(rows)]
        return _fs().admission_stats(rows, 3.0, fold)


# ==================================================================================== statistics primitives
class TQuantile(unittest.TestCase):
    def test_known_values(self):
        self.assertAlmostEqual(FS.t_quantile(0.975, 10), 2.22814, places=3)
        self.assertAlmostEqual(FS.t_quantile(0.95, 29), 1.69913, places=3)
        self.assertAlmostEqual(FS.t_quantile(0.9995, 30), 3.6460, places=2)
        self.assertAlmostEqual(FS.t_quantile(0.99, 1), 31.8205, places=2)

    def test_tail_precision_at_n_205(self):
        # 1 - 0.10/205: the tail the plan's N = 205 asks for must resolve, and exceed the plain 90% quantile
        c = FS.n_adjusted_confidence(205)
        self.assertAlmostEqual(c, 1 - 0.10 / 205)
        self.assertGreater(FS.t_quantile(c, 300), 3.3)
        self.assertGreater(FS.t_quantile(c, 300), FS.t_quantile(0.90, 300))

    def test_bad_inputs_refused(self):
        with self.assertRaises(ValueError):
            FS.n_adjusted_confidence(0)
        with self.assertRaises(ValueError):
            FS.t_quantile(0.4, 10)


class LowerBound(unittest.TestCase):
    def test_n_below_two_has_no_bound(self):
        self.assertIsNone(FS.lower_bound([1.0], 0.9)["value"])
        self.assertIsNone(FS.lower_bound([], 0.9)["value"])

    def test_bound_is_below_mean_and_grows_stricter_with_n(self):
        rs = [0.5, -0.3, 0.9, 0.1, 0.7, -0.2, 0.4, 0.6] * 10
        lo_n = FS.lower_bound(rs, FS.n_adjusted_confidence(1))["value"]
        hi_n = FS.lower_bound(rs, FS.n_adjusted_confidence(205))["value"]
        self.assertLess(hi_n, lo_n)
        self.assertLess(lo_n, sum(rs) / len(rs))

    def test_n_adjustment_is_what_rejects_a_lucky_sample(self):
        rs = [1.0 if i % 2 == 0 else -0.76 for i in range(300)]        # mean +0.12, sd ~ 0.88
        self.assertGreater(FS.lower_bound(rs, FS.n_adjusted_confidence(1))["value"], 0)
        self.assertLess(FS.lower_bound(rs, FS.n_adjusted_confidence(205))["value"], 0)


class GridArithmetic(unittest.TestCase):
    def test_fixture_grids_reproduce_the_plans_n(self):
        ict = FS.load_grid(os.path.join(FIXTURES, "v-grid-ict.json"))
        wy = FS.load_grid(os.path.join(FIXTURES, "v-grid-wyckoff.json"))
        self.assertEqual(FS.n_per_method(ict), 41)     # plan §3: 1 + 39 + 1
        self.assertEqual(FS.n_per_method(wy), 16)      # plan §3: 1 + 14 + 1
        self.assertEqual(FS.n_per_method(ict) * 5, 205)
        self.assertEqual(FS.n_per_method(wy) * 5, 80)

    def test_joint_group_is_one_factor_with_product_candidates(self):
        ict = FS.load_grid(os.path.join(FIXTURES, "v-grid-ict.json"))
        exit_group = next(g for g in ict.groups if g["group"] == "B-EXIT")
        self.assertEqual(len(exit_group["candidates"]), 3 * 4 * 2 - 1)

    def test_malformed_grid_refused(self):
        with self.assertRaises(FS.GridError):
            FS.Grid({"method": "ICT", "items": []})
        with self.assertRaises(FS.GridError):
            FS.Grid({"method": "ICT", "items": [{"id": "a", "key": "k", "values": ["only"]}]})
        it = {"id": "a", "key": "k", "values": [1, 2]}
        with self.assertRaises(FS.GridError):
            FS.Grid({"method": "ICT", "items": [it, dict(it)]})

    def test_the_old_numeric_sort_neighbours_are_gone_the_axis_table_is_the_only_definition_of_a_step(self):
        self.assertFalse(hasattr(FS, "neighbours"))
        self.assertFalse(hasattr(FS, "value_axis"))
        self.assertTrue(FS.PERTURBATION_AXES)


class FoldGeometry(unittest.TestCase):
    def test_folds_end_at_the_development_cutoff_and_tile(self):
        folds = FS.make_folds(DEV_START)
        self.assertEqual(len(folds), 2)
        self.assertEqual(folds[-1]["test_end"], FS.DEV_CUTOFF)
        self.assertEqual(folds[0]["test_end"], folds[1]["test_start"])
        first_train_days = (FS.ts(folds[0]["test_start"]) - FS.ts(DEV_START)).days
        self.assertGreaterEqual(first_train_days, FS.MIN_TRAIN_DAYS)

    def test_too_short_a_history_has_no_folds(self):
        self.assertEqual(FS.make_folds("2023-06-01T00:00:00Z"), [])

    def test_train_window_purges_a_trade_still_open_at_the_test_start(self):
        fold = FS.make_folds(DEV_START)[-1]
        ts0 = FS.ts(fold["test_start"])
        crossing = {"entry_time": FS.iso(ts0 - datetime.timedelta(hours=1)),
                    "exit_time": FS.iso(ts0 + datetime.timedelta(hours=3)), "net_R": 99.0, "symbol": "XAUUSD"}
        early = {"entry_time": FS.iso(ts0 - datetime.timedelta(days=3)),
                 "exit_time": FS.iso(ts0 - datetime.timedelta(days=3) + datetime.timedelta(hours=2)),
                 "net_R": 1.0, "symbol": "XAUUSD"}
        self.assertEqual(FS.train_window([crossing, early], fold), [early])
        self.assertEqual(FS.test_window([crossing, early], fold), [])       # entered BEFORE the fold: not test either


class AdxIndicator(unittest.TestCase):
    def test_trend_is_high_and_range_is_low(self):
        n = 120
        up = FS.adx14([10 + i + 0.5 for i in range(n)], [10 + i - 0.5 for i in range(n)], [10 + i for i in range(n)])
        rng = random.Random(1)
        cl = [100 + rng.uniform(-0.2, 0.2) * (-1) ** i for i in range(n)]
        flat = FS.adx14([c + 0.3 for c in cl], [c - 0.3 for c in cl], cl)
        self.assertIsNone(up[2 * FS.ADX_PERIOD - 2])
        self.assertIsNotNone(up[2 * FS.ADX_PERIOD - 1])
        self.assertGreater(up[-1], 80)
        self.assertLess(flat[-1], 30)

    def test_lookup_uses_only_a_bar_that_opened_before_the_entry(self):
        candles = [{"time": FS.iso(datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
                                   + datetime.timedelta(minutes=5 * i)),
                    "high": 10 + i + .5, "low": 10 + i - .5, "close": 10 + i} for i in range(80)]
        idx = FS.adx_index(candles)
        entry = candles[60]["time"]                              # exactly at bar 60's open
        self.assertEqual(FS.adx_before(idx, entry), idx[1][59])  # bar 59, never bar 60 (PIT)
        self.assertIsNone(FS.adx_before(idx, candles[0]["time"]))


# ========================================================================================= nested walk-forward
class NestedWalkForward(unittest.TestCase):
    def test_selection_never_sees_the_test_fold_poison(self):
        """Value z is terrible everywhere EXCEPT inside the LAST fold's test window, where it is a fantasy. If the
        selection could see that window it would pick z. It must pick y (a real, visible-in-training edge)."""
        grid = grid_two_items()
        folds = FS.make_folds(DEV_START)
        last = folds[-1]

        def trades_for(values):
            seed = json.dumps(values, sort_keys=True)
            mean = 0.3 if values["a"] == "y" else 0.0
            tr = gen(DEV_START, FS.DEV_CUTOFF, 600, mean if values["a"] != "z" else -0.5, 0.5, seed)
            if values["a"] == "z":
                for t in tr:
                    if last["test_start"] <= t["entry_time"] < last["test_end"]:
                        t["net_R"] = 50.0                       # POISON: only the last test fold
            return tr

        # the poison is real: peeking at everything would make z look far better than y
        z_all = trades_for(grid.full({"a": "z"}))
        y_all = trades_for(grid.full({"a": "y"}))
        self.assertGreater(sum(t["net_R"] for t in z_all), sum(t["net_R"] for t in y_all))

        res = FS.nested_walk_forward(grid, FS.CountingSource(trades_for), folds, FS.bar_delta("5m"))
        self.assertEqual([r["chosen"]["a"] for r in res], ["y", "y"])
        # ... and the selected values are unchanged when the test fold's data is replaced by garbage
        def clean(values):
            tr = trades_for(values)
            for t in FS.test_window(tr, last):
                t["net_R"] = -7.0
            return tr
        res2 = FS.nested_walk_forward(grid, FS.CountingSource(clean), folds, FS.bar_delta("5m"))
        self.assertEqual([r["chosen"] for r in res], [r["chosen"] for r in res2])

    def test_each_test_fold_is_scored_with_the_values_chosen_on_its_own_training_fold(self):
        grid = grid_two_items()
        folds = FS.make_folds(DEV_START)

        def trades_for(values):
            # value y is good only BEFORE the last fold's training ends; at fold 0 it is good, later it flips
            mean = 0.0
            if values["a"] == "y":
                mean = 0.4
            return gen(DEV_START, FS.DEV_CUTOFF, 600, mean, 0.5, json.dumps(values, sort_keys=True))

        res = FS.nested_walk_forward(grid, FS.CountingSource(trades_for), folds, FS.bar_delta("5m"))
        for r in res:
            for t in r["test_trades"]:
                self.assertTrue(r["fold"]["test_start"] <= t["entry_time"] < r["fold"]["test_end"])
        # test trades of fold i came from trades_for(chosen_i), not from any other assignment
        expect = FS.test_window(trades_for(res[0]["chosen"]), folds[0])
        self.assertEqual(res[0]["test_trades"], expect)

    def test_lower_bound_uses_only_pooled_test_fold_trades(self):
        """Training trades are +5 R each; test trades are noise around 0. A bound over ALL trades would be hugely
        positive. The cell must be judged on the test trades alone."""
        grid = grid_two_items()
        folds = FS.make_folds(DEV_START)

        def trades_for(values):
            tr = gen(DEV_START, FS.DEV_CUTOFF, 600, 0.0, 1.0, json.dumps(values, sort_keys=True))
            for t in tr:
                if not any(f["test_start"] <= t["entry_time"] < f["test_end"] for f in folds):
                    t["net_R"] = 5.0
            return tr

        src = FS.CountingSource(trades_for)
        res = FS.nested_walk_forward(grid, src, folds, FS.bar_delta("5m"))
        pooled = FS.pooled_test_trades(res)
        self.assertTrue(pooled)
        for t in pooled:
            self.assertTrue(any(f["test_start"] <= t["entry_time"] < f["test_end"] for f in folds))
        ev = FS.evaluate_cell(res, FS.perturbation_trade_sets(grid, src, res), SYMS, 205,
                              {"f1": 0.9, "f2": 0.9})
        self.assertAlmostEqual(ev["pooled"]["mean_R"], sum(t["net_R"] for t in pooled) / len(pooled))
        self.assertEqual(ev["checks"]["lower_bound_positive"]["bound"]["n"], len(pooled))
        self.assertFalse(ev["checks"]["lower_bound_positive"]["ok"])
        self.assertEqual(ev["verdict"], FS.FAIL)

    def test_selection_needs_a_strictly_better_eligible_value(self):
        grid = grid_two_items()
        folds = FS.make_folds(DEV_START)
        same = lambda values: gen(DEV_START, FS.DEV_CUTOFF, 600, 0.2, 0.5, "same")   # every value identical
        res = FS.nested_walk_forward(grid, FS.CountingSource(same), folds, FS.bar_delta("5m"))
        self.assertTrue(all(r["changed"] == [] for r in res))         # ties keep the baseline
        sparse = lambda values: gen(DEV_START, FS.DEV_CUTOFF, 6, 3.0, 0.1, json.dumps(values, sort_keys=True))
        res = FS.nested_walk_forward(grid, FS.CountingSource(sparse), folds, FS.bar_delta("5m"))
        self.assertTrue(all(r["changed"] == [] for r in res))         # < MIN_TRAIN_TRADES: not eligible

    def test_every_distinct_run_is_counted(self):
        grid = grid_two_items()
        folds = FS.make_folds(DEV_START)
        src = FS.CountingSource(lambda v: gen(DEV_START, FS.DEV_CUTOFF, 300, 0.0, 1.0, json.dumps(v, sort_keys=True)))
        FS.nested_walk_forward(grid, src, folds, FS.bar_delta("5m"))
        self.assertGreaterEqual(src.runs, 1 + 2 + 1)                  # baseline + non-baseline a (2) + b (1)


# ============================================================================ the pass / fail decision, end to end
class EndToEndVerdicts(unittest.TestCase):
    FAMILY = 6          # the six candidate procedures: the floor confidence is 1 - 0.10/6 for EVERY candidate

    def _run(self, engine, n=None):
        fs = _fs()
        cell = {"id": "5m-indices", "timeframe": "5m", "symbols": SYMS, "development_start": LONG_START}
        return fs.evaluate_with_engine(engine, grid_two_items(), cell, n or self.FAMILY, axes=TEST_AXES)

    def test_no_edge_strategy_does_not_pass_at_the_floor(self):
        # many independent seeds: an edge-less strategy must never sneak through the strict gate
        for salt in range(6):
            ev = self._run(SynthEngine(mean=0.0, sd=1.0, salt=salt))
            self.assertNotEqual(ev["verdict"], FS.PASS)
            self.assertIn("lower_bound_positive", ev["failed_checks"])

    def test_large_true_edge_passes_at_the_floor(self):
        ev = self._run(SynthEngine(mean=0.6, sd=1.0))
        self.assertEqual(ev["verdict"], FS.PASS, ev["failed_checks"])
        self.assertEqual(ev["failed_checks"], [])
        self.assertAlmostEqual(ev["confidence"], 1 - 0.10 / 6)
        self.assertEqual(ev["family_size"], 6)
        self.assertGreater(ev["runs_evaluated"], 4)
        pr = ev["primary"]
        self.assertTrue(pr["floor_ok"])
        self.assertEqual(sorted(pr["p_values"]), sorted(FS.PRIMARY_COMPONENTS))
        self.assertAlmostEqual(pr["p_robust"], max(pr["p_values"].values()))
        self.assertLess(pr["p_robust"], 0.10 / 6)               # floor pass <=> p_robust below Holm's strictest step

    def test_a_failing_candidate_reports_every_reason_not_just_the_first(self):
        ev = self._run(SynthEngine(mean=-0.2, sd=1.0, prop={"f": 0.1}, prop_shifted={"f": 0.1}))
        for k in ("lower_bound_positive", "stability", "regime_split", "perturbation", "prop_pass_probability",
                  "stress"):
            self.assertIn(k, ev["failed_checks"])

    def test_a_positive_edge_passes_the_stress_gate_and_reports_the_stressed_bound(self):
        ev = self._run(SynthEngine(mean=0.6, stress_cost=0.05))
        st = ev["checks"]["stress"]
        self.assertTrue(st["ok"])
        self.assertAlmostEqual(st["mean_R_stressed"], ev["pooled"]["mean_R"] - 0.05, places=9)
        self.assertIsNotNone(st["stressed_primary_bound"])            # reported, not gated

    def test_an_edge_that_disappears_under_p90_plus_commission_fails_the_stress_gate_only(self):
        # edge +0.6 R, the stress re-pricing costs 0.9 R: every other gate passes, the stress gate does not
        ev = self._run(SynthEngine(mean=0.6, sd=0.6, stress_cost=0.9))
        self.assertEqual(ev["failed_checks"], ["stress"])
        self.assertEqual(ev["verdict"], FS.FAIL)
        self.assertLess(ev["checks"]["stress"]["mean_R_stressed"], 0)

    def test_stress_gates_on_the_mean_only_not_on_its_bound(self):
        # a positive stressed mean passes the gate even when its (reported) bound is below 0
        ev = self._run(SynthEngine(mean=0.6, sd=1.0, stress_cost=0.55))
        st = ev["checks"]["stress"]
        self.assertTrue(st["ok"])
        self.assertLess(st["stressed_primary_bound"], 0)

    def test_an_engine_without_stress_pricing_fails_closed(self):
        class NoStress(SynthEngine):
            stress_trades = None
        ev = self._run(NoStress(mean=0.6))
        self.assertFalse(ev["checks"]["stress"]["ok"])
        self.assertEqual(ev["verdict"], FS.FAIL)

    def test_the_shifted_prop_pass_is_report_only_computed_with_mean_minus_bound_and_gates_nothing(self):
        eng = SynthEngine(mean=0.6, prop={"f": 0.9}, prop_shifted={"f": 0.5})
        ev = self._run(eng)
        sh = ev["report_only"]["prop_pass_shifted"]
        pr = ev["primary"]
        self.assertNotIn("prop_pass_shifted", ev["checks"])             # owner decision 2026-10-02: not a check
        self.assertAlmostEqual(sh["shift_R"], pr["mean"] - pr["primary_bound"], places=12)
        self.assertGreater(sh["shift_R"], 0)
        self.assertTrue(sh["report_only"])
        self.assertEqual(eng.shifts[0], 0.0)                            # the unshifted gate is evaluated, first
        self.assertAlmostEqual(eng.shifts[1], sh["shift_R"], places=12)  # the shifted figure is still computed
        self.assertTrue(ev["checks"]["prop_pass_probability"]["ok"])
        self.assertFalse(sh["ok"])                                      # it would have failed ...
        self.assertEqual(ev["failed_checks"], [])                       # ... and it fails nothing
        self.assertEqual(ev["verdict"], FS.PASS)

    def test_the_unshifted_prop_pass_still_gates_when_the_shifted_one_is_fine(self):
        ev = self._run(SynthEngine(mean=0.6, prop={"f": 0.5}, prop_shifted={"f": 0.9}))
        self.assertEqual(ev["failed_checks"], ["prop_pass_probability"])
        self.assertEqual(ev["verdict"], FS.FAIL)

    def test_required_checks_are_exactly_the_final_conjunction_and_exclude_the_shifted_prop_pass(self):
        self.assertEqual(FS.REQUIRED_CHECKS, ("folds_sufficient", "lower_bound_positive", "stability", "frequency",
                                              "regime_split", "perturbation", "prop_pass_probability", "stress",
                                              "min_trading_days"))
        self.assertNotIn("prop_pass_shifted", FS.REQUIRED_CHECKS)
        self.assertEqual(FS.REPORT_ONLY_CHECKS, ("prop_pass_shifted",))
        self.assertIn("REPORT-ONLY", FS.VERDICT_PRECEDENCE)
        self.assertIn("REPORT-ONLY", FS.PROP_SHIFT_DEFINITION)

    def test_a_record_lacking_the_shifted_check_still_passes_and_one_lacking_the_unshifted_prop_check_fails_closed(self):
        ev = self._run(SynthEngine(mean=0.6))
        checks = copy.deepcopy(ev["checks"])
        self.assertNotIn("prop_pass_shifted", checks)
        self.assertEqual(FS.verdict_from(checks), FS.PASS)
        old = dict(checks, prop_pass_shifted={"ok": False})             # an older record carrying a failing shifted check
        self.assertEqual(FS.verdict_from(old), FS.PASS)                 # is not gated by it
        del checks["prop_pass_probability"]
        self.assertEqual(FS.verdict_from(checks), FS.FAIL)

    def test_mutation_making_the_shifted_check_required_again_is_caught(self):
        ev = self._run(SynthEngine(mean=0.6, prop={"f": 0.9}, prop_shifted={"f": 0.5}))
        checks = dict(ev["checks"], prop_pass_shifted=ev["report_only"]["prop_pass_shifted"])
        self.assertEqual(FS.verdict_from(checks), FS.PASS)
        with mock.patch.object(FS, "REQUIRED_CHECKS", FS.REQUIRED_CHECKS + ("prop_pass_shifted",)):
            self.assertEqual(FS.verdict_from(checks), FS.FAIL)          # the mutation flips the verdict ...
            self.assertNotEqual(FS.REQUIRED_CHECKS, ("folds_sufficient", "lower_bound_positive", "stability", "frequency",
                                                     "regime_split", "perturbation", "prop_pass_probability", "stress",
                                                     "min_trading_days"))    # ... and the pinned-tuple test would fail

    def test_no_shift_without_a_bound_is_reported_as_not_computable(self):
        r = FS.check_prop_pass_shifted({"f": 0.99}, None)
        self.assertFalse(r["ok"])
        self.assertTrue(r["report_only"])

    def test_every_check_has_a_margin_row_and_a_pass_lists_them_all(self):
        ev = self._run(SynthEngine(mean=0.6))
        names = {m["check"] for m in ev["margins"]}
        self.assertEqual(names, set(FS.REQUIRED_CHECKS))
        self.assertTrue(all(m["ok"] for m in ev["margins"]))
        bad = self._run(SynthEngine(mean=0.0, salt=1))
        lb = next(m for m in bad["margins"] if m["check"] == "lower_bound_positive")
        self.assertFalse(lb["ok"])
        self.assertLess(lb["margin"], 0)

    def test_a_record_lacking_a_required_check_cannot_read_as_a_pass(self):
        ev = self._run(SynthEngine(mean=0.6))
        checks = dict(ev["checks"])
        del checks["stress"]
        self.assertEqual(FS.verdict_from(checks), FS.FAIL)
        self.assertEqual(FS.verdict_from(ev["checks"]), FS.PASS)

    def test_the_primary_bound_alone_failing_is_a_fail_when_every_other_check_is_ok(self):
        """Holm never loosens the verdict: the floor test is one of the conjuncts, so ONLY lower_bound_positive.ok = False
        (a candidate Holm might still reject at rank >= 2) is a FAIL."""
        ev = self._run(SynthEngine(mean=0.6))
        checks = copy.deepcopy(ev["checks"])
        self.assertEqual(FS.verdict_from(checks), FS.PASS)
        checks["lower_bound_positive"]["ok"] = False
        self.assertTrue(all(c["ok"] for k, c in checks.items() if k != "lower_bound_positive"))
        self.assertEqual(FS.verdict_from(checks), FS.FAIL)

    def test_a_record_without_folds_sufficient_fails_closed_instead_of_raising(self):
        ev = self._run(SynthEngine(mean=0.6))
        checks = {k: v for k, v in ev["checks"].items() if k != "folds_sufficient"}
        verdict = FS.verdict_from(checks)                      # no KeyError
        self.assertNotEqual(verdict, FS.PASS)
        self.assertEqual(verdict, FS.INSUFFICIENT)             # a missing sufficiency check is treated as NOT ok
        self.assertEqual(FS.verdict_from({}), FS.INSUFFICIENT)
        self.assertNotEqual(FS.verdict_from(dict(ev["checks"], folds_sufficient={})), FS.PASS)

    def test_fold_cost_report_and_chosen_value_stability_per_component(self):
        ev = self._run(SynthEngine(mean=0.6))
        self.assertEqual(len(ev["fold_cost_report"]), len(ev["folds"]))
        self.assertTrue(all(f["n_trades"] >= 30 for f in ev["fold_cost_report"]))
        self.assertTrue(all(f["mean_spread_R"] is None for f in ev["fold_cost_report"]))     # SynthEngine offers none
        self.assertEqual(sorted(ev["component_stability"]), ["a.a", "b.b"])

    def test_prop_pass_below_threshold_or_missing_fails(self):
        self.assertEqual(self._run(SynthEngine(mean=0.6, prop={"a": 0.69, "b": 0.99}))["verdict"], FS.FAIL)
        self.assertEqual(self._run(SynthEngine(mean=0.6, prop={"a": None, "b": 0.99}))["verdict"], FS.FAIL)
        self.assertEqual(self._run(SynthEngine(mean=0.6, prop={}))["verdict"], FS.FAIL)

    def test_perturbation_that_collapses_the_edge_fails_the_cell(self):
        # the edge exists only at the value the folds choose; one grid step away it is gone
        def mean_by(values):
            return 0.7 if values["a"] == "y" and values["b"] == 0 else (0.0 if values["a"] != "y" else 0.4)
        ev = self._run(SynthEngine(mean_by=mean_by))
        pert = ev["checks"]["perturbation"]
        self.assertFalse(pert["ok"])
        self.assertTrue(any(not r["ok"] for r in pert["rows"]))
        self.assertNotEqual(ev["verdict"], FS.PASS)


class MinTradingDays(unittest.TestCase):
    """Owner 2026-10-02: FTMO's minimum trading days (profile `ftmo-challenge-phase1`: 4, flagged for verification) is an explicit
    PASS condition: per test fold, distinct UTC ENTRY days >= the declared minimum. Synthetic trades only."""
    FTMO, FIVERS = "ftmo-challenge-phase1", "the5ers-high-stakes-step1"

    def _folds(self, days_per_fold, trades_per_day=1):
        """Fold results whose test trades are entered on exactly `days_per_fold[i]` distinct UTC days of fold i (several
        trades on one day count once)."""
        out = []
        for f, nd in zip(FS.make_folds(LONG_START), days_per_fold):
            t0 = FS.ts(f["test_start"])
            trades = [{"entry_time": FS.iso(t0 + datetime.timedelta(days=3 * d, hours=1, minutes=k)), "net_R": 0.3, "symbol": "XAUUSD"}
                      for d in range(nd) for k in range(trades_per_day)]
            out.append({"fold": f, "chosen": {}, "changed": [], "test_trades": trades})
        return out

    def test_three_distinct_entry_days_fail_and_four_pass(self):
        req = {self.FTMO: 4, self.FIVERS: None}
        three = FS.check_min_trading_days(self._folds([3, 3]), req)
        self.assertFalse(three["ok"])
        self.assertEqual((three["fewest_entry_days"], three["required"], three["margin"]), (3, 4, -1))
        four = FS.check_min_trading_days(self._folds([4, 4]), req)
        self.assertTrue(four["ok"])
        self.assertEqual(four["margin"], 0)
        self.assertIn("2026-10-02", FS.MIN_TRADING_DAYS_DEFINITION)

    def test_many_trades_on_one_day_count_as_one_day(self):
        chk = FS.check_min_trading_days(self._folds([3, 3], trades_per_day=40), {self.FTMO: 4})
        self.assertEqual([x["entry_days"] for x in chk["folds"]], [3, 3])
        self.assertFalse(chk["ok"])

    def test_it_is_judged_per_fold_not_pooled(self):
        chk = FS.check_min_trading_days(self._folds([9, 3, 9]), {self.FTMO: 4})
        self.assertFalse(chk["ok"])                                   # 21 pooled days, but one fold has 3
        self.assertEqual([x["ok"] for x in chk["folds"]], [True, False, True])
        self.assertEqual(chk["fewest_entry_days"], 3)

    def test_a_trade_outside_its_folds_window_is_not_counted(self):
        folds = self._folds([3, 3])
        late = FS.ts(folds[0]["fold"]["test_end"]) + datetime.timedelta(days=1)
        folds[0]["test_trades"].append({"entry_time": FS.iso(late), "net_R": 0.1, "symbol": "XAUUSD"})
        self.assertEqual(FS.check_min_trading_days(folds, {self.FTMO: 4})["folds"][0]["entry_days"], 3)

    def test_a_fund_without_the_field_is_not_checked(self):
        chk = FS.check_min_trading_days(self._folds([1, 1]), {self.FIVERS: None})
        self.assertTrue(chk["ok"])
        self.assertEqual(chk["funds"][self.FIVERS], {"required": None, "checked": False, "ok": True})
        chk = FS.check_min_trading_days(self._folds([4, 4]), {self.FTMO: 4, self.FIVERS: None})
        self.assertTrue(chk["funds"][self.FTMO]["checked"] and not chk["funds"][self.FIVERS]["checked"])

    def test_unreadable_or_malformed_requirements_fail_closed(self):
        folds = self._folds([50, 50])
        for bad in (None, {}, {self.FTMO: 0}, {self.FTMO: "4"}, {self.FTMO: True}, {self.FTMO: 4.0}):
            chk = FS.check_min_trading_days(folds, bad)
            self.assertFalse(chk["ok"], bad)
            self.assertIn("fail closed", chk["reason"])
        self.assertFalse(FS.check_min_trading_days([], {self.FTMO: 4})["ok"])
        broken = self._folds([5, 5])
        broken[1]["test_trades"][0]["entry_time"] = "not a time"
        self.assertFalse(FS.check_min_trading_days(broken, {self.FTMO: 4})["ok"])
        del broken[1]["test_trades"][0]["entry_time"]
        self.assertFalse(FS.check_min_trading_days(broken, {self.FTMO: 4})["ok"])

    def test_the_harness_reads_the_declared_minimum_from_the_profiles(self):
        fs = _fs()
        self.assertEqual(fs.min_trading_days_required(), {self.FTMO: 4, self.FIVERS: None})
        cfg = fs.min_trading_days_config()
        self.assertEqual(cfg["declared_by_fund"], {self.FTMO: 4, self.FIVERS: None})
        self.assertEqual(cfg["source_profile_ids"], [self.FTMO])
        self.assertIn("flagged for verification", cfg["profile_note_flagged_for_verification"][self.FTMO])
        self.assertEqual(cfg["definition"], FS.MIN_TRADING_DAYS_DEFINITION)

    def test_an_unreadable_profile_fails_closed_end_to_end(self):
        fs = _fs()
        ps = fs._prop_search()
        with mock.patch.object(ps._AP, "get", side_effect=KeyError("profile file unreadable")):
            self.assertIsNone(fs.min_trading_days_required())
            self.assertIsNone(fs.min_trading_days_config()["declared_by_fund"])
        with mock.patch.object(fs, "min_trading_days_required", return_value=None):
            cell = {"id": "5m-indices", "timeframe": "5m", "symbols": SYMS, "development_start": LONG_START}
            ev = fs.evaluate_with_engine(SynthEngine(mean=0.6), grid_two_items(), cell, 6, axes=TEST_AXES)
        self.assertEqual(ev["failed_checks"], ["min_trading_days"])
        self.assertEqual(ev["verdict"], FS.FAIL)

    def _evaluate(self, required):
        fs = _fs()
        cell = {"id": "5m-indices", "timeframe": "5m", "symbols": SYMS, "development_start": LONG_START}
        with mock.patch.object(fs, "min_trading_days_required", return_value=required):
            return fs.evaluate_with_engine(SynthEngine(mean=0.6), grid_two_items(), cell, 6, axes=TEST_AXES)

    def test_the_verdict_fails_when_only_this_check_fails(self):
        ok = self._evaluate({self.FTMO: 4, self.FIVERS: None})
        self.assertEqual(ok["verdict"], FS.PASS)
        self.assertTrue(ok["checks"]["min_trading_days"]["ok"])
        self.assertEqual([m for m in ok["margins"] if m["check"] == "min_trading_days"][0]["unit"], "days")
        fewest = ok["checks"]["min_trading_days"]["fewest_entry_days"]
        bad = self._evaluate({self.FTMO: fewest + 1, self.FIVERS: None})      # one more day than the sparsest fold has
        self.assertEqual(bad["failed_checks"], ["min_trading_days"])
        self.assertEqual(bad["verdict"], FS.FAIL)
        row = [m for m in bad["margins"] if m["check"] == "min_trading_days"][0]
        self.assertEqual((row["margin"], row["ok"]), (-1, False))
        self.assertEqual(len(bad["checks"]["min_trading_days"]["folds"]), len(bad["folds"]))   # the value per fold is recorded

    def test_mutation_the_verdict_test_bites_when_the_check_is_neutralised(self):
        """Remove the check from the conjunction (its result forced ok) and the only-this-check-fails verdict flips to PASS."""
        fewest = self._evaluate({self.FTMO: 4})["checks"]["min_trading_days"]["fewest_entry_days"]
        with mock.patch.object(FS, "check_min_trading_days", return_value={"ok": True}):
            mutated = self._evaluate({self.FTMO: fewest + 1})
        self.assertEqual(mutated["verdict"], FS.PASS)                   # what the mutation does ...
        self.assertEqual(self._evaluate({self.FTMO: fewest + 1})["verdict"], FS.FAIL)    # ... and the real code refuses

    def test_it_is_a_required_check_and_a_record_without_it_cannot_pass(self):
        self.assertIn("min_trading_days", FS.REQUIRED_CHECKS)
        self.assertEqual(len(FS.REQUIRED_CHECKS), 9)
        ev = self._evaluate({self.FTMO: 4})
        checks = copy.deepcopy(ev["checks"])
        self.assertEqual(FS.verdict_from(checks), FS.PASS)
        del checks["min_trading_days"]
        self.assertEqual(FS.verdict_from(checks), FS.FAIL)             # absent -> fails closed
        self.assertEqual(FS.verdict_from(dict(ev["checks"], min_trading_days={"ok": False})), FS.FAIL)
        self.assertIn("minimum trading days", FS.VERDICT_PRECEDENCE)

    def test_evaluate_cell_without_the_requirement_fails_closed(self):
        ev = FS.evaluate_cell(self._folds([60, 60]), [], SYMS, 6, {"f": 0.9})
        self.assertFalse(ev["checks"]["min_trading_days"]["ok"])
        self.assertIn("min_trading_days", ev["failed_checks"])


class Sufficiency(unittest.TestCase):
    def _folds(self, counts):
        out = []
        base = FS.make_folds(DEV_START)
        for f, n in zip(base, counts):
            out.append({"fold": f, "chosen": {}, "changed": [],
                        "test_trades": gen(f["test_start"], f["test_end"], n, 0.5, 0.3, "s")})
        return out

    def test_a_fold_with_29_trades_is_insufficient(self):
        chk = FS.check_fold_sufficiency(self._folds([40, 29]))
        self.assertFalse(chk["ok"])
        ev = FS.evaluate_cell(self._folds([40, 29]), [], SYMS, 205, {"f": 0.9})
        self.assertEqual(ev["verdict"], FS.INSUFFICIENT)

    def test_exactly_30_trades_is_sufficient(self):
        self.assertTrue(FS.check_fold_sufficiency(self._folds([30, 30]))["ok"])

    def test_fewer_than_two_folds_is_insufficient(self):
        self.assertEqual(FS.evaluate_cell(self._folds([200]), [], SYMS, 205, {"f": 0.9})["verdict"], FS.INSUFFICIENT)
        self.assertEqual(FS.evaluate_cell([], [], SYMS, 205, {"f": 0.9})["verdict"], FS.INSUFFICIENT)


class Stability(unittest.TestCase):
    def test_one_trade_carrying_more_than_a_quarter_of_net_r_fails(self):
        trades = gen(DEV_START, FS.DEV_CUTOFF, 60, 0.05, 0.02, "st")
        trades[3]["net_R"] = 40.0                                     # one lottery ticket
        chk = FS.check_stability(trades, SYMS)
        self.assertGreater(chk["largest_trade_share"], 0.25)
        self.assertFalse(chk["share_ok"])
        self.assertFalse(chk["ok"])

    def test_exactly_a_quarter_is_allowed_and_a_hair_over_is_not(self):
        def mk(big):
            base = gen(DEV_START, FS.DEV_CUTOFF, 6, 1.0, 0.0, "q", symbols=SYMS[:1])
            base[0]["net_R"] = big
            return base
        # 5 trades of 1.0 + one of x: share = x / (5 + x) ; x = 5/3 -> exactly 0.25
        self.assertTrue(FS.check_stability(mk(5 / 3 - 1e-9), SYMS[:1])["share_ok"])
        self.assertFalse(FS.check_stability(mk(5 / 3 + 1e-3), SYMS[:1])["share_ok"])

    def test_a_non_positive_total_never_passes(self):
        trades = gen(DEV_START, FS.DEV_CUTOFF, 60, -0.1, 0.05, "neg")
        self.assertFalse(FS.check_stability(trades, SYMS)["ok"])

    def test_symbol_rule_is_ceil_two_thirds_of_m(self):
        self.assertEqual(FS.check_stability(gen(DEV_START, FS.DEV_CUTOFF, 70, 0.3, 0.1, "m"), SYMS)["required_symbols"], 5)
        self.assertEqual(math.ceil(2 * 2 / 3), 2)
        self.assertEqual(math.ceil(2 * 5 / 3), 4)

        def by_symbol(positive):
            tr = []
            for i, s in enumerate(SYMS):
                tr += [{"entry_time": "2022-01-01T00:00:00Z", "exit_time": "2022-01-01T01:00:00Z", "symbol": s,
                        "net_R": (0.5 if i < positive else -0.5)} for _ in range(10)]
            return tr
        self.assertFalse(FS.check_stability(by_symbol(4), SYMS)["symbols_ok"])
        self.assertTrue(FS.check_stability(by_symbol(5), SYMS)["symbols_ok"])

    def test_a_symbol_with_no_test_trades_counts_against_never_dropped(self):
        tr = gen(DEV_START, FS.DEV_CUTOFF, 60, 0.3, 0.1, "m", symbols=SYMS[:4])       # only 4 of 7 symbols trade
        chk = FS.check_stability(tr, SYMS)
        self.assertEqual(chk["m_symbols"], 7)
        self.assertEqual(chk["per_symbol"]["FRA40"]["n"], 0)
        self.assertFalse(chk["symbols_ok"])


class Frequency(unittest.TestCase):
    def _fold(self, gaps_ok):
        f = FS.make_folds(DEV_START)[0]
        n = 60 if gaps_ok else 4
        return {"fold": f, "chosen": {}, "changed": [], "test_trades": gen(f["test_start"], f["test_end"], n, 0.5, 0.1, "f")}

    def test_gap_over_30_days_fails_and_inside_passes(self):
        good, bad = self._fold(True), self._fold(False)
        self.assertLessEqual(FS.max_gap_days(good["test_trades"], good["fold"]["test_start"], good["fold"]["test_end"]), 30)
        self.assertGreater(FS.max_gap_days(bad["test_trades"], bad["fold"]["test_start"], bad["fold"]["test_end"]), 30)

    def test_needs_ninety_percent_of_folds(self):
        good, bad = self._fold(True), self._fold(False)
        self.assertTrue(FS.check_frequency([good] * 10)["ok"])
        self.assertTrue(FS.check_frequency([good] * 9 + [bad])["ok"])       # 90 % is enough
        self.assertFalse(FS.check_frequency([good] * 8 + [bad] * 2)["ok"])
        self.assertFalse(FS.check_frequency([])["ok"])

    def test_window_edges_count_as_gaps(self):
        f = FS.make_folds(DEV_START)[0]
        one = [{"entry_time": f["test_start"], "exit_time": f["test_start"], "net_R": 1, "symbol": "X"}]
        self.assertGreater(FS.max_gap_days(one, f["test_start"], f["test_end"]), 300)     # nothing for 364 days


class Regime(unittest.TestCase):
    def _t(self, adx, r):
        return {"entry_time": "2022-01-01T00:00:00Z", "exit_time": "2022-01-01T01:00:00Z", "symbol": "X",
                "net_R": r, "adx14_d1": adx}

    def test_edge_only_in_one_regime_fails(self):
        trades = [self._t(10 + i % 5, 0.9) for i in range(40)] + [self._t(30 + i % 5, -0.4) for i in range(40)]
        self.assertFalse(FS.check_regime_split(trades)["ok"])

    def test_edge_in_both_halves_passes(self):
        trades = [self._t(10 + i % 5, 0.5) for i in range(40)] + [self._t(30 + i % 5, 0.3) for i in range(40)]
        self.assertTrue(FS.check_regime_split(trades)["ok"])

    def test_a_missing_adx_cannot_be_split_and_fails(self):
        trades = [self._t(20, 0.5) for _ in range(10)] + [self._t(None, 0.5)]
        chk = FS.check_regime_split(trades)
        self.assertFalse(chk["ok"])
        self.assertIn("ADX", chk["reason"])

    def test_both_halves_negative_is_not_a_pass(self):
        trades = [self._t(10 + i % 5, -0.5) for i in range(20)] + [self._t(30 + i % 5, -0.3) for i in range(20)]
        self.assertFalse(FS.check_regime_split(trades)["ok"])

    def _split(self, n_low, n_high, r=0.5):
        """n_low trades at one tied ADX (the median) and n_high above it, every trade net R = r."""
        return [self._t(20.0, r) for _ in range(n_low)] + [self._t(50.0, r) for _ in range(n_high)]

    def test_ties_at_the_median_cannot_leave_a_tiny_half_that_still_passes(self):
        # reproduced by the review: [10, 20, 20, 20, 50], all net R +0.5 -> low n = 4, high n = 1 was "ok"
        trades = [self._t(a, 0.5) for a in (10, 20, 20, 20, 50)]
        chk = FS.check_regime_split(trades)
        self.assertEqual((chk["low"]["n"], chk["high"]["n"]), (4, 1))
        self.assertFalse(chk["ok"])
        self.assertIn("regime halves unbalanced", chk["reason"])
        self.assertAlmostEqual(chk["smaller_half_share"], 0.2)

    def test_a_balanced_split_passes_and_carries_no_reason(self):
        trades = [self._t(10 + i, 0.4) for i in range(8)]
        chk = FS.check_regime_split(trades)
        self.assertTrue(chk["ok"])
        self.assertNotIn("reason", chk)
        self.assertEqual(chk["min_half_share"], 0.25)

    def test_each_half_needs_at_least_25_percent_exactly_at_the_boundary(self):
        self.assertEqual(FS.REGIME_MIN_HALF_SHARE, 0.25)
        for n_low, n_high, ok in ((6, 2, True),      # 2/8 = 25 % exactly: passes
                                  (9, 3, True),      # 3/12 = 25 %
                                  (10, 2, False),    # 2/12 = 16.7 %
                                  (7, 2, False),     # 2/9 = 22.2 %
                                  (75, 25, True), (76, 24, False), (3, 1, True), (4, 1, False)):
            chk = FS.check_regime_split(self._split(n_low, n_high))
            self.assertEqual(chk["ok"], ok, (n_low, n_high))
            self.assertEqual("reason" in chk, not ok, (n_low, n_high))

    def test_balance_does_not_replace_the_sign_requirement(self):
        trades = self._split(10, 10)
        trades[-1] = dict(trades[-1], net_R=-50.0)                 # a balanced split whose high half is negative on average
        self.assertFalse(FS.check_regime_split(trades)["ok"])
        self.assertNotIn("regime halves unbalanced", FS.check_regime_split(trades).get("reason", ""))

    def test_the_balance_rule_is_in_the_pinned_definition_and_the_margins(self):
        self.assertIn("25 %", FS.REGIME_SPLIT_DEFINITION)
        self.assertIn("regime halves unbalanced", FS.REGIME_SPLIT_DEFINITION)
        chk = FS.check_regime_split(self._split(4, 1))
        rows = FS.check_margins({"regime_split": chk})
        row = next(r for r in rows if r["measure"].startswith("smaller half's share"))
        self.assertFalse(row["ok"])
        self.assertAlmostEqual(row["margin"], 0.2 - 0.25)


class VolumeKindAndPerSymbol(unittest.TestCase):
    def test_wyckoff_results_are_split_by_volume_kind_with_the_limitation_labelled(self):
        tr = gen(DEV_START, FS.DEV_CUTOFF, 40, 0.3, 0.2, "v", extra={"volume_kind": "tick"})
        tr += gen(DEV_START, FS.DEV_CUTOFF, 40, 0.0, 0.2, "w", extra={"volume_kind": "traded"})
        out = FS.split_by_volume_kind(tr, 0.99)
        self.assertEqual(out["tick"]["n"], 40)
        self.assertEqual(out["traded"]["n"], 40)
        self.assertIn("NOT real traded volume", out["_limitation"])
        self.assertIsNone(FS.split_by_volume_kind(gen(DEV_START, FS.DEV_CUTOFF, 5, 0, 1, "n"), 0.99))


# ==================================================================================== orchestration (fund-search)
class _Tmp(unittest.TestCase):
    """A scratch copy of the ledger + a scratch experiment dir, patched into a fresh fund-search module."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.fs = _fs()
        self.ledger = os.path.join(self.tmp, "research-ledger.json")
        shutil.copy(os.path.join(ROOT, "docs", "architecture", "research-ledger.json"), self.ledger)
        # The real ledger carries the REAL declaration (since c4ea722); these tests exercise declare/run from scratch, so the
        # copy starts without it (and without superseded ones) -- the real file is never touched.
        led = json.load(open(self.ledger))
        for k in ("fund_search", "fund_search_superseded"):
            led.pop(k, None)
        json.dump(led, open(self.ledger, "w"), indent=1)
        self.exp = os.path.join(self.tmp, "exp")
        self.records = os.path.join(self.exp, "records")
        os.makedirs(self.exp)
        patches = [mock.patch.object(self.fs, "EXPERIMENT_DIR", self.exp),
                   mock.patch.object(self.fs, "PLAN_PATH", os.path.join(self.exp, "plan.json")),
                   mock.patch.object(self.fs, "RECORDS_DIR", self.records),
                   mock.patch.object(self.fs, "REPORT_PATH", os.path.join(self.tmp, "report.md")),
                   mock.patch.object(self.fs, "GRID_DIR", FIXTURES),
                   mock.patch.object(self.fs.RL, "PATH", self.ledger),
                   mock.patch.object(self.fs, "_first_bar", self._first_bar),
                   # the readiness gate (build_plan) needs a real-cost spec per symbol; the fixture plan has none on disk
                   mock.patch.object(self.fs, "_spec_present", lambda sym: (True, f"synthetic/{sym}")),
                   # the real scoped dirty check reads THIS checkout (dirty while developing); its own tests use a temp repo
                   mock.patch.object(self.fs, "scoped_dirty", lambda root=None: [])]
        # the SYNTHETIC cell fixtures name symbols with no DEV_BARS row (the real declared cells all have one: see
        # test_every_symbol_of_every_declared_cell_has_a_dev_bars_row, which reads the unpatched table `_REAL_DEV_BARS`)
        for tf, bars in (("1m", 800000), ("5m", 160000), ("15m", 60000)):
            patches.append(mock.patch.dict(self.fs.DEV_BARS[tf], {sy: bars for sy in self.fs.FUND_SYMBOLS
                                                                   if sy not in self.fs.DEV_BARS[tf]}))
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.first = {}

    def _first_bar(self, sym, tf):
        return self.first.get((sym, tf), "2018-01-01T00:00:00Z")

    def plan(self):
        return self.fs.build_plan(FIXTURES)


class PlanAndDryRun(_Tmp):
    def test_cells_n_and_confidence(self):
        p = self.plan()
        self.assertEqual(p["cell_count"], 6)                               # owner 2026-10-01: the 30m cells are removed
        self.assertEqual(p["family"]["size"], 12)                           # family A: 6 declared cells x 2 methods
        self.assertAlmostEqual(p["family"]["floor_confidence"], 1 - 0.10 / 12)
        self.assertEqual(p["grids"]["ict"]["n_per_cell"], 41)               # grid values are disclosed, not in the family
        self.assertEqual(p["candidate_count"], 12)
        # plan §6 item 8 dropped AUS200 (no data); owner 2026-10-01 (symbol universe) puts it back in the 5m and 15m indices cells only
        self.assertEqual([c["id"] for c in p["cells"] if "AUS200" in c["symbols"]], ["5m-indices", "15m-indices"])
        self.assertEqual({c["timeframe"] for c in p["cells"]}, {"1m", "5m", "15m"})

    def test_a_cell_without_development_history_is_excluded_and_a_symbol_is_listed_not_forgotten(self):
        for s in ("US500", "US30", "USTEC", "DE40", "FRA40"):
            self.first[(s, "1m")] = "2024-06-01T00:00:00Z"               # indices 1m start AFTER the cutoff
        self.first[("XAGUSD", "5m")] = "2025-01-01T00:00:00Z"
        p = self.plan()
        self.assertEqual(p["cell_count"], 5)
        self.assertEqual([e["id"] for e in p["excluded_cells"]], ["1m-indices"])
        c5 = next(c for c in p["cells"] if c["id"] == "5m-metals")
        self.assertEqual(c5["symbols"], ["XAUUSD", "XPTUSD", "XPDUSD"])
        self.assertIn("XAGUSD", c5["symbols_without_development"])         # m excludes it, but it is disclosed
        self.assertEqual(p["family"]["size"], 12)                          # counted on the DECLARED cells: the excluded one still counts
        self.assertEqual(p["candidate_count"], 10)

    def test_dry_run_prints_n_and_confidence_and_writes_nothing(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.fs.cmd_plan(dry_run=True, grid_dir=FIXTURES)
        out = buf.getvalue()
        self.assertIn("12 candidate procedures", out)
        self.assertIn("1 - 0.1/12 = 0.991667", out)
        self.assertIn("NOTHING is evaluated", out)
        self.assertFalse(os.path.exists(self.fs.PLAN_PATH))
        self.assertFalse(os.path.exists(self.records))

    def test_committed_plan_cannot_be_silently_changed(self):
        self.fs.cmd_plan(grid_dir=FIXTURES)
        self.first[("XAUUSD", "1m")] = "2025-01-01T00:00:00Z"            # the data view changes
        with self.assertRaises(SystemExit) as cm:
            self.fs.cmd_plan(grid_dir=FIXTURES)
        self.assertIn("refusing to change the committed plan", str(cm.exception))

    def test_missing_grid_is_refused_not_guessed(self):
        with self.assertRaises(SystemExit) as cm:
            self.fs.build_plan(self.tmp)
        self.assertIn("grid file missing", str(cm.exception))


class FixedRules(_Tmp):
    def test_a_grid_item_cannot_unfix_flat_before_rollover(self):
        g = FS.Grid({"method": "ICT", "items": [
            {"id": "x", "key": "fx_x", "existing_opts_key": "flat_before_rollover", "values": [True, False]}]})
        with self.assertRaises(SystemExit) as cm:
            self.fs.validate_grid(g)
        self.assertIn("FIXED", str(cm.exception))

    def test_fixed_overlay_is_on_and_uses_the_real_cost_profile(self):
        o = self.fs.fixed_opts()
        self.assertTrue(o["flat_before_rollover"])
        self.assertEqual(o["rollover_provider"], "mt5_bridge_ftmo")
        self.assertEqual(self.fs.COST_PROFILE, "ftmo_demo_2026_09_relspread")          # C2: relative spread (red-team 2026-10-02)
        self.assertEqual(self.fs.COST_PROFILE_ABSOLUTE, "ftmo_demo_2026_09")           # comparison baseline only

    def test_cost_profile_pin_carries_the_price_refs_and_their_provenance_hash(self):
        import real_costs as RC
        pin = self.fs.cost_profile_pin(["XAUUSD", "US500", "XAUUSD"])
        self.assertEqual(pin["profile"], "ftmo_demo_2026_09_relspread")
        self.assertEqual(pin["spread_scaling"], "relative_price_ref")
        self.assertEqual(pin["price_ref"], {"US500": RC.price_ref(self.fs.COST_PROFILE, "US500"),
                                            "XAUUSD": RC.price_ref(self.fs.COST_PROFILE, "XAUUSD")})
        self.assertEqual(len(pin["price_ref_provenance_sha256"]), 64)

    def test_plan_and_declaration_config_pin_the_cost_profile_and_price_refs(self):
        plan = self.fs.build_plan(grid_dir=FIXTURES, first_bar=lambda s, t: "2010-01-01T00:00:00Z")
        self.assertEqual(plan["cost_profile"], "ftmo_demo_2026_09_relspread")
        syms = sorted({s for c in plan["cells"] for s in c["symbols"]})
        self.assertEqual(sorted(plan["cost_profile_pin"]["price_ref"]), syms)
        cfg = self.fs.evaluation_config(plan)
        self.assertEqual((cfg["cost_profile"], cfg["cost_profile_pin"]), (plan["cost_profile"], plan["cost_profile_pin"]))
        pin = dict(plan["cost_profile_pin"], price_ref_provenance_sha256="0" * 64)         # a changed history = a changed plan
        with mock.patch.object(self.fs, "cost_profile_pin", return_value=pin):
            self.assertNotEqual(self.fs.build_plan(grid_dir=FIXTURES, first_bar=lambda s, t: "2010-01-01T00:00:00Z")
                                ["plan_hash"], plan["plan_hash"])

    def test_scope_is_the_17_pinned_symbols(self):
        """The universe cells may draw from (owner 2026-10-01): the original 7 + XPTUSD XPDUSD + UK100 EU50 JP225 HK50 AUS200
        US2000 SPN35 N25. XCUUSD, DXY (no pre-cutoff history) and all FX are not in it."""
        self.assertEqual(self.fs.FUND_SYMBOLS, ("XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD", "US500", "US30", "USTEC", "DE40", "FRA40",
                                                "UK100", "EU50", "JP225", "HK50", "AUS200", "US2000", "SPN35", "N25"))


class _Helpers(_Tmp):
    def _plan_file(self):
        self.fs.cmd_plan(grid_dir=FIXTURES)
        return json.load(open(self.fs.PLAN_PATH))

    def _fake_out(self, c, plan_hash, mean=0.0):
        grids, paths = self.fs.load_grids(FIXTURES)
        plan = json.load(open(self.fs.PLAN_PATH))
        cell = next(x for x in plan["cells"] if x["id"] == c["cell"])
        cell = dict(cell, development_start=LONG_START)
        eng = SynthEngine(mean=mean, symbols=cell["symbols"])     # every symbol of the (5/13/28-symbol) cell trades
        grid = grid_two_items()
        res = self.fs.evaluate_with_engine(eng, grid, cell, c["family_size"], axes=TEST_AXES)
        snap = {"snapshot_id": "t", "series": []}
        return {"record": dict(self.fs.build_record(c, plan_hash, grids[c["method"]], paths[c["method"]], res, snap, cell))}


class LedgerDeclaration(_Helpers):
    def test_run_refuses_without_the_ledger_declaration(self):
        plan = self._plan_file()
        with mock.patch.object(self.fs, "_evaluate_candidate") as ev:
            with self.assertRaises(SystemExit) as cm:
                self.fs.cmd_run("5m-metals", grid_dir=FIXTURES)
        self.assertIn("no `fund_search` declaration", str(cm.exception))
        ev.assert_not_called()                                            # nothing was evaluated
        self.assertFalse(os.path.isdir(self.records) and os.listdir(self.records))
        self.assertIsInstance(plan, dict)

    def test_run_refuses_a_declaration_that_does_not_match_the_plan(self):
        self._plan_file()
        self.fs.cmd_declare()
        data = json.load(open(self.ledger))
        data["fund_search"]["cell_count"] = 3
        json.dump(data, open(self.ledger, "w"))
        with mock.patch.object(self.fs, "_evaluate_candidate") as ev:
            with self.assertRaises(SystemExit) as cm:
                self.fs.cmd_run("5m-metals", grid_dir=FIXTURES)
        self.assertIn("does not match", str(cm.exception))
        ev.assert_not_called()

    def test_declare_records_the_cell_count_and_leaves_every_period_untouched(self):
        self._plan_file()
        before = json.load(open(self.ledger))
        self.fs.cmd_declare()
        after = json.load(open(self.ledger))
        self.assertEqual(after["fund_search"]["cell_count"], 6)
        self.assertEqual(after["oos"], before["oos"])                     # no window / period changed
        self.assertEqual(after["budget"], before["budget"])

    def test_declare_refuses_once_records_exist(self):
        self._plan_file()
        os.makedirs(self.records)
        open(os.path.join(self.records, "x.json"), "w").write("{}")
        with self.assertRaises(SystemExit) as cm:
            self.fs.cmd_declare()
        self.assertIn("BEFORE any evaluation", str(cm.exception))

    def test_a_different_declaration_needs_supersede_and_keeps_the_old_one(self):
        """D-redeclare (2026-10-02): replacing a declaration is a recorded ledger event, never an edit."""
        self._plan_file()
        self.fs.cmd_declare()
        data = json.load(open(self.ledger))
        data["fund_search"]["plan_hash"] = "old-hash"
        json.dump(data, open(self.ledger, "w"))
        with self.assertRaises(SystemExit) as cm:
            self.fs.cmd_declare()
        self.assertIn("--supersede", str(cm.exception))
        self.fs.cmd_declare(supersede="engine fix D3")
        after = json.load(open(self.ledger))
        old = after["fund_search_superseded"][-1]
        self.assertEqual((old["plan_hash"], old["superseded_reason"]), ("old-hash", "engine fix D3"))
        self.assertEqual(after["fund_search"]["supersedes_plan_hash"], "old-hash")
        self.assertNotEqual(after["fund_search"]["plan_hash"], "old-hash")

    def test_supersede_is_refused_once_records_exist(self):
        self._plan_file()
        self.fs.cmd_declare()
        os.makedirs(self.records)
        open(os.path.join(self.records, "x.json"), "w").write("{}")
        with self.assertRaises(SystemExit) as cm:
            self.fs.cmd_declare(supersede="too late")
        self.assertIn("BEFORE any evaluation", str(cm.exception))

    def test_declared_run_proceeds_only_past_the_gate(self):
        self._plan_file()
        self.fs.cmd_declare()
        calls = []
        with mock.patch.object(self.fs, "_evaluate_candidate", side_effect=lambda c, h, g=None: calls.append(c["id"]) or
                               self._fake_out(c, h)):
            self.fs.cmd_run("5m-metals", grid_dir=FIXTURES)
        self.assertEqual(sorted(calls), ["ict-5m-metals", "wyckoff-5m-metals"])
        self.assertEqual(sorted(os.listdir(self.records)), ["ict-5m-metals.json", "wyckoff-5m-metals.json"])



class RunAndReport(_Helpers):
    def setUp(self):
        super().setUp()
        self._plan_file()
        self.fs.cmd_declare()

    def _run(self, cell, mean=0.0, only_fail=None):
        def fake(c, h, g=None):
            if only_fail and c["id"] == only_fail:
                raise RuntimeError("boom")
            return self._fake_out(c, h, mean)
        with mock.patch.object(self.fs, "_evaluate_candidate", side_effect=fake):
            self.fs.cmd_run(cell, grid_dir=FIXTURES)

    def test_record_is_a_sealed_complete_experiment_record(self):
        self._run("5m-metals")
        rec = X.load("ict-5m-metals", store=self.records)
        for fid in ("dataset_snapshot", "configuration_snapshot", "metrics", "random_seed", "test_periods"):
            self.assertIn(fid, rec)
        self.assertEqual(rec["risk_configuration"]["flat_before_rollover"], True)
        self.assertIn("UNKNOWN", rec["risk_configuration"]["commission_note"])
        self.assertIn("no_deals", json.dumps(rec["risk_configuration"]["commission_status_by_symbol"]))

    def test_resume_skips_recorded_candidates(self):
        self._run("5m-metals")
        with mock.patch.object(self.fs, "_evaluate_candidate") as ev:
            self.fs.cmd_run("5m-metals", grid_dir=FIXTURES)
        ev.assert_not_called()

    def test_an_exception_fails_loud_and_is_never_recorded_as_a_fail(self):
        with self.assertRaises(RuntimeError) as cm:
            self._run("5m-metals", only_fail="wyckoff-5m-metals")
        self.assertIn("FAILING LOUD", str(cm.exception))
        self.assertEqual(os.listdir(self.records), ["ict-5m-metals.json"])   # the sibling that finished is kept

    def test_zero_pass_report_says_so_and_lists_every_candidate_including_fails(self):
        for cell in ("5m-metals", "15m-metals"):
            self._run(cell, mean=0.0)
        md = self.fs.cmd_report(grid_dir=FIXTURES)
        self.assertIn("Zero passes", md)
        self.assertIn("evaluated: **4**", md)
        for cid in ("ict-5m-metals", "wyckoff-5m-metals", "ict-15m-metals", "wyckoff-15m-metals"):
            self.assertIn(cid, md)
        self.assertIn("NOT RUN: **8**", md)                                   # the rest of the plan is disclosed
        self.assertIn("Incomplete", md)
        self.assertIn("**12 candidate procedures**", md)                       # family A: cells x methods, not grid values
        self.assertIn("NOT folded into the family", md)

    def test_a_report_with_no_records_says_zero_results(self):
        md = self.fs.cmd_report(grid_dir=FIXTURES)
        self.assertIn("No candidate has been evaluated yet", md)

    def test_a_passing_candidate_is_reported_as_a_pass(self):
        self._run("5m-metals", mean=0.6)
        md = self.fs.cmd_report(grid_dir=FIXTURES)
        self.assertIn("evaluated candidates passed", md)
        self.assertNotIn("Zero passes", md)

    def test_verdict_is_rederived_from_stored_checks_not_a_stored_flag(self):
        self._run("5m-metals", mean=0.0)
        rec = X.load("ict-5m-metals", store=self.records)
        ev = rec["metrics"]["evaluation"]
        self.assertEqual(FS.verdict_from(ev["checks"]), ev["verdict"])

    def test_no_symbol_may_be_dropped_after_the_plan(self):
        self._run("5m-metals")
        plan = json.load(open(self.fs.PLAN_PATH))
        rec = copy.deepcopy(dict(X.load("ict-5m-metals", store=self.records)))
        rec["parameters"] = dict(rec["parameters"], symbols_evaluated=["XAUUSD"])   # XAGUSD quietly dropped
        with self.assertRaises(self.fs.RecordMismatch) as cm:
            self.fs.validate_record(rec, plan)
        self.assertIn("no symbol may be added or dropped", str(cm.exception))

    def test_a_record_from_another_plan_is_refused(self):
        self._run("5m-metals")
        plan = json.load(open(self.fs.PLAN_PATH))
        rec = copy.deepcopy(dict(X.load("ict-5m-metals", store=self.records)))
        rec["parameters"] = dict(rec["parameters"], plan_hash="deadbeef" * 8)
        with self.assertRaises(self.fs.RecordMismatch):
            self.fs.validate_record(rec, plan)

    def test_unimplemented_grid_items_refuse_the_run(self):
        bad = os.path.join(self.tmp, "grids")
        shutil.copytree(FIXTURES, bad)
        p = os.path.join(bad, "v-grid-ict.json")
        d = json.load(open(p))
        d["items"][0]["implemented"] = False
        json.dump(d, open(p, "w"))
        with self.assertRaises(SystemExit):
            self.fs.cmd_run("5m-metals", grid_dir=bad)   # plan hash mismatch or unimplemented: refused either way


class EngineAdapter(_Tmp):
    def test_engine_refuses_keys_the_engine_does_not_know(self):
        fake_bt = mock.Mock()
        fake_bt._OPTS_BASE = {"mgmt": "none"}
        g = FS.Grid({"method": "ICT", "items": [
            {"id": "x", "key": "fx_not_in_engine", "existing_opts_key": None, "values": [False, True],
             "implemented": True}]})
        with self.assertRaises(SystemExit) as cm:
            self.fs.BtEngine(g, "ICT", "5m", ["XAUUSD"], bt=fake_bt)
        self.assertIn("not implemented in the engine", str(cm.exception))


# ================================================================================== fix round 1 (statistical review)
def clustered_trades(seed, days=100, per=4, rho=0.8):
    """Zero-edge trades, `per` same-day trades with correlation rho (reviewer scenario (a))."""
    rng = random.Random(seed)
    out, d0 = [], datetime.datetime(2022, 3, 1, tzinfo=datetime.timezone.utc)
    for d in range(days):
        z = rng.gauss(0, 1)
        for k in range(per):
            t = d0 + datetime.timedelta(days=d, hours=8 + k)
            out.append({"entry_time": FS.iso(t), "exit_time": FS.iso(t + datetime.timedelta(hours=1)),
                        "net_R": math.sqrt(rho) * z + math.sqrt(1 - rho) * rng.gauss(0, 1), "symbol": "XAUUSD"})
    return out


def regime_trades(seed, days=360, sd_reg=0.35):
    """Zero-edge trades with a persistent 30-day regime effect (reviewer scenario (b))."""
    rng = random.Random(seed)
    out, d0, eff = [], datetime.datetime(2022, 3, 1, tzinfo=datetime.timezone.utc), 0.0
    for d in range(days):
        if d % 30 == 0:
            eff = rng.gauss(0, sd_reg)
        t = d0 + datetime.timedelta(days=d, hours=8)
        out.append({"entry_time": FS.iso(t), "exit_time": FS.iso(t + datetime.timedelta(hours=1)),
                    "net_R": eff + rng.gauss(0, 1), "symbol": "XAUUSD"})
    return out


class BlockRobustBound(unittest.TestCase):
    CONF = FS.n_adjusted_confidence(205)

    def test_same_day_clustered_zero_edge_passes_iid_but_not_the_robust_bound(self):
        tr = clustered_trades(1)                                       # fixed seed: iid t-bound alone PASSES
        lb = FS.robust_lower_bound(tr, self.CONF)
        self.assertGreater(lb["iid"], 0)                               # the reviewer's false positive
        self.assertLessEqual(lb["block_date"], 0)
        self.assertTrue(lb["value"] is None or lb["value"] <= 0)         # None = fail closed (< 2 quarters)
        self.assertFalse(FS.check_lower_bound(tr, self.CONF)["ok"])

    def test_regime_persistence_zero_edge_is_stopped_by_the_30_day_block_bound(self):
        tr = regime_trades(1)
        lb = FS.robust_lower_bound(tr, self.CONF)
        self.assertGreater(lb["iid"], 0)
        self.assertLessEqual(lb["block_30d"], 0)
        self.assertFalse(FS.check_lower_bound(tr, self.CONF)["ok"])

    def test_min_can_only_lower_the_bound(self):
        for seed in range(25):
            tr = clustered_trades(seed, days=40) if seed % 2 else regime_trades(seed, days=200)
            lb = FS.robust_lower_bound(tr, self.CONF)
            if lb["value"] is None:                                       # fail closed: nothing to compare
                continue
            for k in ("iid", "block_date", "block_30d", "block_quarter", "block_half"):
                self.assertLessEqual(lb["value"], lb[k] + 1e-12)

    def test_fewer_than_two_blocks_fails_closed(self):
        one_day = clustered_trades(3, days=1)
        self.assertIsNone(FS.robust_lower_bound(one_day, self.CONF)["value"])
        self.assertFalse(FS.check_lower_bound(one_day, self.CONF)["ok"])

    def test_perturbation_check_uses_the_robust_bound(self):
        tr = clustered_trades(1)
        chk = FS.check_perturbation([{"item": "a", "direction": 1, "trades": tr}], self.CONF)
        self.assertFalse(chk["ok"])                                    # iid alone would have passed it

    def test_true_edge_still_passes_the_robust_bound(self):
        tr = gen(DEV_START, FS.DEV_CUTOFF, 600, 0.6, 1.0, "edge")
        self.assertTrue(FS.check_lower_bound(tr, self.CONF)["ok"])


class PropPassStatus(unittest.TestCase):
    def test_unavailable_is_distinct_from_below_threshold_and_both_block(self):
        c = FS.check_prop_pass({"a": {"value": None, "reason": "no profit target"}, "b": 0.5, "c": 0.9})
        self.assertEqual(c["funds"]["a"]["status"], "unavailable")
        self.assertEqual(c["funds"]["a"]["reason"], "no profit target")
        self.assertEqual(c["funds"]["b"]["status"], "below_threshold")
        self.assertEqual(c["funds"]["c"]["status"], "ok")
        self.assertFalse(c["ok"])
        self.assertFalse(FS.check_prop_pass({"a": None, "b": 0.9})["ok"])

    def test_low_confidence_needs_the_spread_minimum_to_clear_too(self):
        low = {"value": 0.9, "low_confidence": True, "spread_min": 0.55}
        self.assertFalse(FS.check_prop_pass({"a": low})["ok"])
        self.assertEqual(FS.check_prop_pass({"a": low})["funds"]["a"]["status"],
                         "low_confidence_spread_below_threshold")
        self.assertFalse(FS.check_prop_pass({"a": dict(low, spread_min=None)})["ok"])
        self.assertTrue(FS.check_prop_pass({"a": dict(low, spread_min=0.70)})["ok"])
        self.assertTrue(FS.check_prop_pass({"a": {"value": 0.9, "low_confidence": False}})["ok"])

    def test_metric_entry_conversion(self):
        fs = _fs()
        self.assertEqual(fs.prop_row_from_metric({"value": 0.8, "low_confidence": True,
                                                  "spread": {"prop_pass_probability": [0.6, 0.9]}}),
                         {"value": 0.8, "low_confidence": True, "spread_min": 0.6, "risk_per_trade": None,
                          "horizon_unit": None, "observed_weekdays": None})
        r = fs.prop_row_from_metric({"unavailable": "no profit_target", "owner": "x"})
        self.assertIsNone(r["value"])
        self.assertEqual(r["reason"], "no profit_target")


class SimulateGuards(unittest.TestCase):
    def _trades(self, n=6):
        d0 = datetime.datetime(2022, 3, 1, tzinfo=datetime.timezone.utc)
        return [{"symbol": "XAUUSD", "side": "long", "entry": 100.0, "stop": 99.0, "R": -1.0, "R_planned": 99,
                 "entry_time": FS.iso(d0 + datetime.timedelta(hours=2 * i)),
                 "exit_time": FS.iso(d0 + datetime.timedelta(hours=2 * i + 1)), "outcome": "loss"} for i in range(n)]

    def test_ruin_is_neutralised_on_the_harness_own_instance_only(self):
        fs = _fs()
        a, b = fs._load_bt(), fs._load_bt()
        default = a.RUIN_FRAC
        fs.neutralise_ruin(a)
        self.assertEqual(a.RUIN_FRAC, 0.0)
        self.assertEqual(b.RUIN_FRAC, default)                          # v1 untouched everywhere else

    def test_a_ruin_stop_fails_loud_and_neutralising_it_keeps_every_trade(self):
        fs = _fs()
        bt = fs._load_bt()
        bt.RUIN_FRAC = 0.9999                                            # ruin after the first loss
        with self.assertRaises(RuntimeError) as cm:
            fs.checked_simulate(bt, self._trades(), 0.0, overlay=fs.fixed_opts())
        self.assertIn("never lose trades silently", str(cm.exception))
        fs.neutralise_ruin(bt)
        taken = fs.checked_simulate(bt, self._trades(), 0.0, overlay=fs.fixed_opts())[2]
        self.assertEqual(len(taken), 6)

    def test_post_ruin_trades_fail_loud_even_without_a_ruin_stamp(self):
        fs = _fs()
        bt = mock.Mock()
        bt._OPTS_BASE = {"min_rr": 2.5, "fx_b_exit": "-2.0|H|floor"}     # the simulate-time context is built from it (C1)
        bt.simulate.return_value = (1.0, [], [])
        bt.SIM_LAST = {"post_ruin": [{"symbol": "X"}], "ruin": None}
        with self.assertRaises(RuntimeError):
            fs.checked_simulate(bt, [], 0.0, overlay=fs.fixed_opts())

    PROV = "mt5_bridge_ftmo"     # FTMO-Demo server = UTC+2 in winter: server midnight is 22:00Z

    def test_a_last_bar_of_the_server_day_wyckoff_entry_does_not_trip(self):
        fs = _fs()
        # entry label = OPEN of the last bar of the server day (21:55Z = 23:55 server); the first walked bar
        # opens at 22:00Z = 00:00 server and the trade is stopped in it -- legitimate, nothing held overnight
        legit = {"symbol": "X", "entry_time": "2022-01-10T21:55:00Z", "exit_time": "2022-01-10T22:00:00Z"}
        fs.assert_no_rollover_crossing([legit], self.PROV, "5m")
        # the OLD label-to-label comparison false-trips on exactly this trade
        import real_costs as RC
        self.assertTrue(RC.crosses_rollover(legit["entry_time"], legit["exit_time"], self.PROV))

    def test_a_genuinely_overnight_held_trade_trips(self):
        fs = _fs()
        held = {"symbol": "X", "entry_time": "2022-01-10T10:00:00Z", "exit_time": "2022-01-11T03:00:00Z"}
        with self.assertRaises(RuntimeError) as cm:
            fs.assert_no_rollover_crossing([held], self.PROV, "5m")
        self.assertIn("cross the server rollover", str(cm.exception))
        flat = {"symbol": "X", "entry_time": "2022-01-10T19:00:00Z", "exit_time": "2022-01-10T21:30:00Z"}
        fs.assert_no_rollover_crossing([flat], self.PROV, "5m")

    def test_an_exit_on_the_entry_bar_itself_has_no_walked_span_to_cross(self):
        fs = _fs()
        t = {"symbol": "X", "entry_time": "2022-01-10T21:55:00Z", "exit_time": "2022-01-10T21:55:00Z"}
        fs.assert_no_rollover_crossing([t], self.PROV, "5m")

    def test_entries_on_the_last_bar_of_a_server_day_are_counted_not_raised(self):
        fs = _fs()
        taken = [{"symbol": "X", "entry_time": "2022-01-10T21:55:00Z", "exit_time": "2022-01-10T22:00:00Z"},
                 {"symbol": "X", "entry_time": "2022-01-10T10:00:00Z", "exit_time": "2022-01-10T11:00:00Z"}]
        times = fs.last_bar_entry_times(taken, "5m", self.PROV)
        self.assertEqual(times, ["2022-01-10T21:55:00Z"])
        self.assertEqual(fs.rollover_edge_stats(times)["entries_on_last_bar_of_server_day"], 1)
        fold = {"test_start": "2022-02-01T00:00:00Z", "test_end": "2022-03-01T00:00:00Z"}
        self.assertEqual(fs.rollover_edge_stats(times, fold)["entries_on_last_bar_of_server_day"], 0)


class AllowListAndOverlay(_Tmp):
    def _g(self, key, existing=None):
        return FS.Grid({"method": "ICT", "items": [
            {"id": "x", "key": key, "existing_opts_key": existing, "values": [1, 2]}]})

    def test_only_fx_keys_and_the_listed_existing_keys_are_allowed(self):
        self.fs.validate_grid(self._g("fx_ok"))
        self.fs.validate_grid(self._g("fx_mgmt", "mgmt"))
        for bad in ("min_rr", "methods", "entry", "sides"):
            with self.assertRaises(SystemExit):
                self.fs.validate_grid(self._g("fx_x", bad))
        with self.assertRaises(SystemExit):
            self.fs.validate_grid(self._g("plain_key"))

    def test_overlay_carries_only_declared_keys_plus_the_fixed_rules(self):
        g = self._g("fx_ok")
        o = self.fs.build_overlay(g, {"x": 2})
        self.assertEqual(set(o), {"fx_ok", "flat_before_rollover", "rollover_provider"} | set(self.fs.ADOPTED_F_KEYS))
        with self.assertRaises(SystemExit):
            self.fs.build_overlay(g, {"x": 2, "min_rr": 0})


class AdmissionDisclosure(_Tmp):
    def test_admission_stats_counts_refusals_and_near_floor_margins(self):
        rows = [{"entry_time": "2022-06-01T00:00:00Z", "R_planned": 3.10, "fee_R": 0.2},   # margin -0.10 refused
                {"entry_time": "2022-06-02T00:00:00Z", "R_planned": 3.30, "fee_R": 0.1},   # +0.20 near, admitted
                {"entry_time": "2022-06-03T00:00:00Z", "R_planned": 6.00, "fee_R": 0.1}]   # far above
        st = self.fs.admission_stats(rows, 3.0)
        self.assertEqual(st["candidates"], 3)
        self.assertEqual(st["refused_min_rr"], 1)
        self.assertEqual(st["near_floor_n"], 2)
        self.assertEqual(st["near_floor_refused"], 1)
        self.assertAlmostEqual(st["near_floor_margin_min"], -0.10)
        fold = {"test_start": "2022-06-02T00:00:00Z", "test_end": "2022-06-04T00:00:00Z"}
        self.assertEqual(self.fs.admission_stats(rows, 3.0, fold)["candidates"], 2)

    def test_result_and_report_carry_the_admission_counts_and_the_limitation(self):
        cell = {"id": "5m-metals", "timeframe": "5m", "symbols": SYMS, "development_start": LONG_START}
        res = self.fs.evaluate_with_engine(SynthEngine(mean=0.0), grid_two_items(), cell, 205)
        adm = res["admission"]
        self.assertEqual(len(adm["by_fold_chosen"]), len(FS.make_folds(LONG_START)))
        self.assertIn("EXIT-hour spread", adm["limitation"])
        self.assertIn("O1 DECIDED", adm["limitation"])
        self.assertTrue(adm["by_value_set"])


class ZeroRiskDisclosure(_Tmp):
    """Item 12: the admission disclosure carries the zero_risk refusals, per fold and per value set."""

    def test_admission_stats_counts_zero_risk_rows_and_keeps_them_out_of_the_min_rr_margins(self):
        rows = [{"entry_time": "2022-06-01T00:00:00Z", "R_planned": 3.10, "fee_R": 0.2},   # margin -0.10 refused (min_rr)
                {"entry_time": "2022-06-02T00:00:00Z", "zero_risk": "zero"},
                {"entry_time": "2022-06-03T00:00:00Z", "zero_risk": "sub_tick"},
                {"entry_time": "2022-06-03T06:00:00Z", "R_planned": 6.00, "fee_R": 0.1}]
        st = self.fs.admission_stats(rows, 3.0)
        self.assertEqual((st["candidates"], st["refused_zero_risk"], st["refused_min_rr"]), (4, 2, 1))
        self.assertEqual(st["near_floor_n"], 1)                       # only the two risk-valid rows have a margin
        fold = {"test_start": "2022-06-02T00:00:00Z", "test_end": "2022-06-03T00:00:00Z"}
        f = self.fs.admission_stats(rows, 3.0, fold)
        self.assertEqual((f["candidates"], f["refused_zero_risk"], f["refused_min_rr"]), (1, 1, 0))
        none = self.fs.admission_stats(rows[:1] + rows[3:], 3.0)
        self.assertEqual(none["refused_zero_risk"], 0)                # a value set with none: 0, every other figure as before

    def test_result_carries_zero_risk_per_fold_and_per_value_set(self):
        cell = {"id": "5m-metals", "timeframe": "5m", "symbols": SYMS, "development_start": LONG_START}
        res = self.fs.evaluate_with_engine(SynthEngine(mean=0.0), grid_two_items(), cell, 205)
        adm = res["admission"]
        self.assertTrue(all("refused_zero_risk" in f for f in adm["by_fold_chosen"]))
        self.assertGreater(sum(f["refused_zero_risk"] for f in adm["by_fold_chosen"]), 0)
        self.assertTrue(all(v["refused_zero_risk"] > 0 for v in adm["by_value_set"].values()))


class Disclosures(_Helpers):
    def setUp(self):
        super().setUp()
        self._plan_file()

    def test_declaration_pins_code_shas_grid_hashes_and_the_evaluation_config(self):
        self.fs.cmd_declare()
        d = json.load(open(self.ledger))["fund_search"]
        for f in ("scripts/fund_stats.py", "scripts/fund-search.py", "scripts/prop-search.py"):
            self.assertIn(f, d["code"])
            self.assertIsInstance(d["code"][f]["dirty"], bool)
            self.assertRegex(d["code"][f]["git_sha"] or "", r"^[0-9a-f]{40}$")
        cfg = d["evaluation_config"]
        self.assertEqual(cfg["stability_fraction"], [2, 3])
        self.assertEqual(cfg["spread_stat"], "median")
        self.assertEqual(cfg["live_parity_sizing"], {"trades_for": False, "prop_pass": True})
        self.assertEqual(cfg["prop_horizon_days"], 120)
        mtd = cfg["min_trading_days"]                                    # owner 2026-10-02: the pinned definition
        self.assertEqual(mtd["declared_by_fund"], {"ftmo-challenge-phase1": 4, "the5ers-high-stakes-step1": None})
        self.assertEqual(mtd["source_profile_ids"], ["ftmo-challenge-phase1"])
        self.assertEqual(mtd["definition"], FS.MIN_TRADING_DAYS_DEFINITION)
        self.assertIn("flagged for verification", mtd["profile_note_flagged_for_verification"]["ftmo-challenge-phase1"])
        self.assertIn("insufficient", cfg["verdict_precedence"])
        self.assertEqual(set(cfg["grid_sha256"]), {"ict", "wyckoff"})
        self.assertTrue(all(len(h) == 64 for h in cfg["grid_sha256"].values()))

    def test_report_flags_mixed_code_versions_and_a_dirty_tree(self):
        self.fs.cmd_declare()
        with mock.patch.object(X, "code_version", return_value={"commit": "a" * 40, "dirty": False}):
            self._run_cell("5m-metals")
        with mock.patch.object(X, "code_version", return_value={"commit": "b" * 40, "dirty": True}):
            self._run_cell("15m-metals")
        md = self.fs.cmd_report()
        self.assertIn("WARNING: records sealed under different code versions", md)
        self.assertIn("dirty=True", md)

    def test_report_is_quiet_when_every_record_shares_one_clean_code_version(self):
        self.fs.cmd_declare()
        with mock.patch.object(X, "code_version", return_value={"commit": "a" * 40, "dirty": False}):
            self._run_cell("5m-metals")
        self.assertNotIn("WARNING: records sealed", self.fs.cmd_report())

    def _run_cell(self, cell):
        with mock.patch.object(self.fs, "_evaluate_candidate",
                               side_effect=lambda c, h, g=None: self._fake_out(c, h)):
            self.fs.cmd_run(cell, grid_dir=FIXTURES)

    def test_report_states_folds_frequency_arithmetic_pass_meaning_stability_and_regime(self):
        self.fs.cmd_declare()
        self._run_cell("5m-metals")
        md = self.fs.cmd_report()
        self.assertIn("Folds per cell and the frequency-rule arithmetic", md)
        self.assertIn("What a PASS certifies", md)
        self.assertIn("SELECTION PROCEDURE", md)
        self.assertIn("FINAL fold", md)
        self.assertIn("Chosen-value stability across folds", md)
        self.assertIn("MEDIAN of the pooled TEST trades", md)                 # S6, stated as a definition
        self.assertIn("min_rr admission", md)
        self.assertIn("planned-risk admission (item 12", md)               # the zero_risk refusals are in the report line
        self.assertRegex(md, r"refused as zero_risk \[[0-9, ]+\] of candidates")
        self.assertIn("prop_pass_probability: ", md)

    def test_fold_counts_and_frequency_arithmetic_per_cell(self):
        self.assertEqual(FS.fold_arithmetic(17), {"n_folds": 17, "folds_required_within_gap": 16,
                                                  "folds_allowed_to_fail": 1, "max_gap_days": 30,
                                                  "required_share": 0.9})
        self.assertEqual(FS.fold_arithmetic(4)["folds_required_within_gap"], 4)
        self.assertEqual(FS.fold_arithmetic(4)["folds_allowed_to_fail"], 0)
        self.assertEqual(FS.fold_arithmetic(10)["folds_required_within_gap"], 9)
        p = self.plan()
        for c in p["cells"]:
            self.assertEqual(c["n_folds"], len(FS.make_folds(c["development_start"])))
            self.assertIn("frequency_rule", c)

    def test_dry_run_prints_folds_and_the_frequency_rule(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.fs.cmd_plan(dry_run=True, grid_dir=FIXTURES)
        self.assertRegex(buf.getvalue(), r"folds \d+ \(frequency rule: >= \d+ of \d+ folds")

    def test_chosen_value_stability_counts_changes_between_folds(self):
        res = [{"chosen": {"a": "x", "b": 0}}, {"chosen": {"a": "y", "b": 0}}, {"chosen": {"a": "x", "b": 0}}]
        st = FS.chosen_value_stability(res)
        self.assertEqual(st["a"]["changes"], 2)
        self.assertEqual(st["a"]["transitions"], 2)
        self.assertEqual(st["b"]["changes"], 0)


class RecordsPersistAsTheyComplete(_Helpers):
    def test_the_first_record_is_on_disk_before_the_second_candidate_starts(self):
        self._plan_file()
        self.fs.cmd_declare()
        seen = {}

        def fake(c, h, g=None):
            seen[c["id"]] = sorted(os.listdir(self.records)) if os.path.isdir(self.records) else []
            return self._fake_out(c, h)
        with mock.patch.object(self.fs, "_evaluate_candidate", side_effect=fake):
            self.fs.cmd_run("5m-metals", grid_dir=FIXTURES)
        self.assertEqual(seen["ict-5m-metals"], [])
        self.assertEqual(seen["wyckoff-5m-metals"], ["ict-5m-metals.json"])


class WorkflowHardening(unittest.TestCase):
    def test_no_expression_is_interpolated_into_a_shell_script_and_workers_is_validated(self):
        lines = open(os.path.join(ROOT, ".github", "workflows", "fund-search.yml")).read().splitlines()
        in_run, run_indent = False, 0
        for ln in lines:
            ind = len(ln) - len(ln.lstrip())
            if in_run and ln.strip() and ind <= run_indent:
                in_run = False
            if in_run:
                self.assertNotIn("${{", ln, "expression interpolated into a shell script: " + ln)
            if ln.strip().startswith("run:"):
                in_run, run_indent = True, ind
        text = "\n".join(lines)
        self.assertIn("INPUT_WORKERS: ${{ inputs.workers }}", text)
        self.assertIn("*[!0-9]*", text)                                       # integer validation
        self.assertNotIn("workflow_dispatch:\n    inputs:\n      workers:\n        description: x", "x")


# ==================================================================================== fix round 2
def persistent_trades(seed, days=720, rho=0.7, sd=0.40, blk=30):
    """Zero-edge trades whose regime effect is AR(1) across `blk`-day blocks (reviewer persistence scenario)."""
    rng = random.Random(seed)
    eff_rng = random.Random(seed * 7 + 1)
    eff = eff_rng.gauss(0, sd)
    out, d0 = [], datetime.datetime(2022, 3, 1, tzinfo=datetime.timezone.utc)
    for d in range(days):
        if d % blk == 0 and d > 0:
            eff = rho * eff + math.sqrt(1 - rho * rho) * sd * eff_rng.gauss(0, 1)
        t = d0 + datetime.timedelta(days=d, hours=8)
        out.append({"entry_time": FS.iso(t), "exit_time": FS.iso(t + datetime.timedelta(hours=1)),
                    "net_R": eff + rng.gauss(0, 1), "symbol": "XAUUSD"})
    return out


def old_three_bound(lb):
    """The round-1 bound: min(iid, UTC date, 30-day window)."""
    return min(lb["iid"], lb["block_date"], lb["block_30d"])


class QuarterAndHalfYearBounds(unittest.TestCase):
    CONF = FS.n_adjusted_confidence(205)

    def test_ar1_persistence_over_30_day_blocks_is_rejected_by_the_new_min(self):
        tr = persistent_trades(1)
        lb = FS.robust_lower_bound(tr, self.CONF)
        self.assertGreater(old_three_bound(lb), 0)                        # the round-1 bound PASSED this
        self.assertLessEqual(lb["value"], 0)
        self.assertFalse(FS.check_lower_bound(tr, self.CONF)["ok"])

    def test_180_day_persistence_is_rejected_by_the_new_min(self):
        tr = persistent_trades(1, rho=0.0, blk=180)
        lb = FS.robust_lower_bound(tr, self.CONF)
        self.assertGreater(old_three_bound(lb), 0)
        self.assertLessEqual(min(lb["block_quarter"], lb["block_half"]), 0)
        self.assertFalse(FS.check_lower_bound(tr, self.CONF)["ok"])

    def test_the_perturbation_check_uses_the_same_five_way_min(self):
        tr = persistent_trades(1, rho=0.0, blk=180)
        chk = FS.check_perturbation([{"item": "a", "direction": 1, "trades": tr}], self.CONF)
        self.assertFalse(chk["ok"])

    def test_the_min_never_exceeds_any_component_and_fewer_than_two_quarters_fail_closed(self):
        for seed in range(12):
            lb = FS.robust_lower_bound(persistent_trades(seed, days=400), self.CONF)
            for k in ("iid", "block_date", "block_30d", "block_quarter", "block_half"):
                self.assertLessEqual(lb["value"], lb[k] + 1e-12)
        one_quarter = gen("2022-01-05T00:00:00Z", "2022-03-20T00:00:00Z", 200, 1.0, 0.1, "q")
        lb = FS.robust_lower_bound(one_quarter, self.CONF)
        self.assertEqual(lb["blocks_quarter"], 1)
        self.assertIsNone(lb["value"])                                    # G < 2 => no bound => fail closed
        self.assertFalse(FS.check_lower_bound(one_quarter, self.CONF)["ok"])

    def test_a_genuine_iid_edge_of_point_three_at_n_600_still_passes(self):
        tr = gen("2018-03-01T00:00:00Z", FS.DEV_CUTOFF, 600, 0.30, 1.0, "iid-edge-0")
        lb = FS.robust_lower_bound(tr, self.CONF)
        self.assertGreater(lb["value"], 0)
        self.assertTrue(FS.check_lower_bound(tr, self.CONF)["ok"])


class ReportWording(_Helpers):
    def test_result_carries_the_rollover_edge_counts_and_report_states_o8_and_the_power_price(self):
        cell = {"id": "5m-metals", "timeframe": "5m", "symbols": SYMS, "development_start": LONG_START}
        res = self.fs.evaluate_with_engine(SynthEngine(), grid_two_items(), cell, 205)
        edge = res["rollover_edge"]
        self.assertEqual(len(edge["by_fold_chosen"]), len(FS.make_folds(LONG_START)))
        self.assertIn("O8", edge["note"])
        self._plan_file()
        self.fs.cmd_declare()
        with mock.patch.object(self.fs, "_evaluate_candidate",
                               side_effect=lambda c, h, g=None: self._fake_out(c, h)):
            self.fs.cmd_run("5m-metals", grid_dir=FIXTURES)
        md = self.fs.cmd_report()
        self.assertIn("Entries on the last bar of a server day", md)
        self.assertIn("DISCLOSED PRICE", md)
        self.assertIn("calendar quarter and by half-year", md)
        self.assertNotIn("perturbation check back it", md)              # the cap/perturbation do NOT back the bound
        self.assertIn("not backed by the single-trade cap", md)


class PurgeMargin(unittest.TestCase):
    def test_a_trade_ending_within_one_bar_of_the_test_start_is_purged(self):
        fold = FS.make_folds(DEV_START)[-1]
        t0 = FS.ts(fold["test_start"])
        mk = lambda mins: {"entry_time": FS.iso(t0 - datetime.timedelta(days=1)),
                           "exit_time": FS.iso(t0 - datetime.timedelta(minutes=mins)), "net_R": 1.0, "symbol": "X"}
        inside, outside = mk(2), mk(6)
        self.assertEqual(FS.train_window([inside, outside], fold), [inside, outside])          # old rule (no margin)
        self.assertEqual(FS.train_window([inside, outside], fold, FS.bar_delta("5m")), [outside])
        self.assertEqual(FS.train_window([mk(5)], fold, FS.bar_delta("5m")), [])                  # exactly one bar: not <
        self.assertEqual(FS.train_window([mk(20)], fold, FS.bar_delta("30m")), [])

    def test_unknown_timeframe_is_refused_not_guessed(self):
        with self.assertRaises(ValueError):
            FS.bar_delta("7m")

    def test_evaluate_with_engine_passes_the_cells_bar_as_the_margin(self):
        fs = _fs()
        cell = {"id": "15m-metals", "timeframe": "15m", "symbols": SYMS, "development_start": LONG_START}
        with mock.patch.object(FS, "nested_walk_forward", wraps=FS.nested_walk_forward) as spy:
            fs.evaluate_with_engine(SynthEngine(), grid_two_items(), cell, 205)
        self.assertEqual(spy.call_args[0][3], datetime.timedelta(minutes=15))


class Embargo(unittest.TestCase):
    """O2 (owner-approved 2026-09-30): training additionally requires exit_label < test_start - embargo, embargo =
    2 x H bars of the cell's timeframe (H = the engine's own P[tf]["H"])."""

    @classmethod
    def setUpClass(cls):
        cls.fs = _fs()

    def test_embargo_excludes_a_training_trade_exiting_inside_the_window_and_keeps_one_just_before(self):
        fold = FS.make_folds(DEV_START)[-1]
        t0 = FS.ts(fold["test_start"])
        emb = datetime.timedelta(minutes=5 * 240)
        mk = lambda d: {"entry_time": FS.iso(t0 - datetime.timedelta(days=30)), "exit_time": FS.iso(t0 - d),
                        "net_R": 1.0, "symbol": "X"}
        inside = mk(emb - datetime.timedelta(minutes=5))       # clears the one-bar purge, inside the embargo
        exactly = mk(emb)                                       # exactly at the boundary: strict <, excluded
        before = mk(emb + datetime.timedelta(minutes=5))
        bar = FS.bar_delta("5m")
        self.assertEqual(FS.train_window([inside, exactly, before], fold, bar), [inside, exactly, before])  # purge alone
        self.assertEqual(FS.train_window([inside, exactly, before], fold, bar, emb), [before])
        self.assertEqual(FS.train_window([inside, before], fold, bar, datetime.timedelta(0)), [inside, before])

    def test_embargo_is_two_h_bars_from_the_engines_own_p_table_for_every_fund_timeframe(self):
        bt = self.fs._load_bt()
        self.assertEqual(self.fs.FUND_TIMEFRAMES, ("1m", "5m", "15m"))        # 30m removed, owner 2026-10-01
        for tf in self.fs.FUND_TIMEFRAMES:
            self.assertEqual(self.fs.embargo_for(tf, bt),
                             datetime.timedelta(minutes=2 * bt.P[tf]["H"] * FS.TF_MINUTES[tf]), tf)
        # follows the engine table, not a copy of it
        fake = types.SimpleNamespace(P={"5m": {"H": 7}})
        self.assertEqual(self.fs.embargo_for("5m", fake), datetime.timedelta(minutes=70))

    def test_the_embargo_covers_the_largest_finite_time_stop_of_the_declared_v_grid(self):
        # the ICT grid's finite time stops are H, 1.5H, 2H (v-grid-ict.json B-EXIT "time_stop"); 2H == the embargo
        with open(os.path.join(ROOT, "docs", "architecture", "v-grid-ict.json"), encoding="utf-8") as fh:
            ts_item = next(it for it in json.load(fh)["items"] if it["id"] == "B-EXIT")
        ts_labels = {v.split("|")[1] for v in ts_item["values"]}
        self.assertEqual(ts_labels, {"H", "1.5H", "2H", "none"})
        finite = [float(x[:-1] or 1) for x in ts_labels if x != "none"]
        self.assertEqual(max(finite), self.fs.EMBARGO_H_MULTIPLE)

    def test_evaluate_with_engine_passes_two_h_bars_as_the_embargo(self):
        cell = {"id": "15m-metals", "timeframe": "15m", "symbols": SYMS, "development_start": LONG_START}
        bt = self.fs._load_bt()
        with mock.patch.object(FS, "nested_walk_forward", wraps=FS.nested_walk_forward) as spy:
            self.fs.evaluate_with_engine(SynthEngine(), grid_two_items(), cell, 205)
        self.assertEqual(spy.call_args[1]["embargo"], datetime.timedelta(minutes=2 * bt.P["15m"]["H"] * 15))
        self.assertEqual(spy.call_args[0][3], datetime.timedelta(minutes=15))           # the purge margin is unchanged

    def test_plan_and_declaration_config_record_the_embargo(self):
        plan = self.fs.build_plan(grid_dir=FIXTURES, first_bar=lambda s, t: "2010-01-01T00:00:00Z")
        bt = self.fs._load_bt()
        want = {tf: 2 * bt.P[tf]["H"] * FS.TF_MINUTES[tf] for tf in self.fs.FUND_TIMEFRAMES}
        self.assertEqual(plan["embargo"]["minutes_by_timeframe"], want)
        self.assertEqual(plan["embargo"]["h_multiple"], 2)
        self.assertEqual(self.fs.evaluation_config(plan)["embargo"], plan["embargo"])
        h1 = plan["plan_hash"]
        with mock.patch.object(self.fs, "EMBARGO_H_MULTIPLE", 3):
            self.assertNotEqual(self.fs.build_plan(grid_dir=FIXTURES,
                                                   first_bar=lambda s, t: "2010-01-01T00:00:00Z")["plan_hash"], h1)


class DeclarationEnforcement(_Helpers):
    def setUp(self):
        super().setUp()
        self._plan_file()
        self.fs.cmd_declare()

    def _run(self, **kw):
        with mock.patch.object(self.fs, "_evaluate_candidate",
                               side_effect=lambda c, h, g=None: self._fake_out(c, h)) as ev:
            try:
                self.fs.cmd_run("5m-metals", grid_dir=FIXTURES, **kw)
            finally:
                self.ev = ev

    def test_fingerprint_covers_the_engine_files_and_they_all_exist(self):
        for f in ("scripts/backtest-methods.py", "scripts/real_costs.py", "scripts/performance.py",
                  "scripts/mt5_time.py", "scripts/ict-scan.py", "scripts/wyckoff_rules.py", "scripts/live_rules.py"):
            self.assertIn(f, self.fs.FINGERPRINT_FILES)
            self.assertTrue(os.path.exists(os.path.join(ROOT, f)), f)
        d = json.load(open(self.ledger))["fund_search"]["code"]
        self.assertEqual(set(d), set(self.fs.FINGERPRINT_FILES))

    def test_an_unchanged_tree_runs(self):
        self._run()
        self.assertEqual(self.ev.call_count, 2)

    def test_code_drift_refuses_with_a_clear_message_and_evaluates_nothing(self):
        real = self.fs.code_fingerprint

        def drifted(files=self.fs.FINGERPRINT_FILES):
            out = real(files)
            out["scripts/backtest-methods.py"] = {"git_sha": "f" * 40, "dirty": False}
            return out
        with mock.patch.object(self.fs, "code_fingerprint", drifted):
            with self.assertRaises(SystemExit) as cm:
                self._run()
        self.assertIn("scripts/backtest-methods.py", str(cm.exception))
        self.assertIn("--allow-drift", str(cm.exception))
        self.assertNotEqual(str(cm.exception), "0")
        self.ev.assert_not_called()
        self.assertFalse(os.path.isdir(self.records) and os.listdir(self.records))

    def test_a_dirty_file_now_is_drift_too(self):
        real = self.fs.code_fingerprint

        def dirty(files=self.fs.FINGERPRINT_FILES):
            out = real(files)
            out["scripts/fund_stats.py"] = dict(out["scripts/fund_stats.py"], dirty=not out["scripts/fund_stats.py"]["dirty"])
            return out
        with mock.patch.object(self.fs, "code_fingerprint", dirty):
            with self.assertRaises(SystemExit):
                self._run()

    def test_evaluation_config_drift_refuses(self):
        with mock.patch.object(FS, "STABILITY_FRACTION", (3, 4)):
            with self.assertRaises(SystemExit) as cm:
                self._run()
        self.assertIn("stability_fraction", str(cm.exception))
        self.ev.assert_not_called()

    def test_allow_drift_proceeds_stamps_every_record_and_the_report_header_says_so(self):
        with mock.patch.object(FS, "STABILITY_FRACTION", (3, 4)):
            self._run(allow_drift=True)
            self.assertEqual(self.ev.call_count, 2)
            for cid in ("ict-5m-metals", "wyckoff-5m-metals"):
                rec = X.load(cid, store=self.records)
                self.assertTrue(rec["parameters"]["drifted"])
                self.assertTrue(any("stability_fraction" in d for d in rec["parameters"]["drift"]))
        self.assertNotIn(self.fs.DRIFT_ENV, os.environ)                    # the stamp does not leak
        with mock.patch.object(FS, "STABILITY_FRACTION", (3, 4)):
            md = self.fs.cmd_report()
        self.assertIn("WARNING: DRIFTED RECORDS", md.splitlines()[2])

    def test_undrifted_records_are_not_stamped(self):
        self._run()
        rec = X.load("ict-5m-metals", store=self.records)
        self.assertFalse(rec["parameters"]["drifted"])
        self.assertNotIn("DRIFTED RECORDS", self.fs.cmd_report())


def _git_repo(tmp):
    """A throw-away git repo shaped like the pinned layout (scripts/, docs/architecture/, data/history/..., config/)."""
    import subprocess
    repo = os.path.join(tmp, "repo")
    files = {"scripts/a.py": "x = 1\n", "docs/architecture/analysis-params.json": "{}\n",
             "docs/architecture/research-ledger.json": "{\"v\": 1}\n", "data/history/costs/ftmo/symbolspec.X.json": "{}\n",
             "data/history/ftmo/ohlcv.X.5m.json": "[]\n", "config/env.example": "A=1\n", "README.md": "r\n"}
    for rel, txt in files.items():
        p = os.path.join(repo, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write(txt)

    def g(*a):
        # no global excludes: a developer's `docs/*` rule must not hide the fixture's docs/architecture
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.excludesFile=/dev/null", *a],
                       cwd=repo, check=True, capture_output=True)
    g("init", "-q")
    g("add", "-A")
    g("commit", "-q", "-m", "init")
    return repo, g


class PinningAndDirtyTree(_Tmp):
    """2026-10-02 red-team I5: tree-hash pins, the scoped dirty-tree refusal, the python/platform NOTE."""

    def setUp(self):
        super().setUp()
        self.repo, self.g = _git_repo(self.tmp)
        self.real = _fs()        # unpatched module: the real scoped_dirty / tree_pins on the temp repo

    def _write(self, rel, txt):
        open(os.path.join(self.repo, rel), "w").write(txt)

    def test_fingerprint_lists_every_engine_import_and_every_file_exists(self):
        for m in ("history_store", "normalized", "pit", "quality", "research_validity", "account_profile", "trading_env",
                  "instruments", "event_risk", "isolated_pool", "experiment"):
            self.assertIn(f"scripts/{m}.py", self.fs.FINGERPRINT_FILES)
        for f in self.fs.FINGERPRINT_FILES:
            self.assertTrue(os.path.exists(os.path.join(ROOT, f)), f)
        self.assertEqual(len(set(self.fs.FINGERPRINT_FILES)), len(self.fs.FINGERPRINT_FILES))

    def test_the_scoped_dirty_check_ignores_config_and_other_paths(self):
        self.assertEqual(self.real.scoped_dirty(self.repo), [])
        self._write("config/env.example", "A=2\n")                              # ` M config/env.example`
        os.makedirs(os.path.join(self.repo, ".claude", "worktrees"))
        self._write(".claude/worktrees/w.txt", "x")                            # `?? .claude/worktrees/`
        self._write("README.md", "changed\n")
        self.assertEqual(self.real.scoped_dirty(self.repo), [])
        self.assertEqual(self.real.check_clean_tree(False, root=self.repo), [])

    def test_a_modified_tracked_file_or_an_untracked_file_in_scope_refuses(self):
        cases = (("scripts/a.py", "x = 2\n"),
                 ("docs/architecture/analysis-params.json", "{\"min_rr\": 1}\n"),
                 ("data/history/ftmo/ohlcv.X.5m.json", "[1]\n"),
                 ("scripts/new_untracked.py", "y = 1\n"),
                 ("docs/architecture/new_untracked.json", "{}\n"),      # also when a global ignore rule (docs/*) hides it
                 ("data/history/costs/ftmo/new.json", "{}\n"))
        for rel, txt in cases:
            with self.subTest(rel):
                self.g("checkout", "-q", "--", ".")
                self.g("clean", "-qfd")
                self.assertEqual(self.real.scoped_dirty(self.repo), [])         # non-vacuous: clean first ...
                self._write(rel, txt)
                with self.assertRaises(self.real.DirtyTreeRefused) as cm:      # ... refuses after the mutation
                    self.real.check_clean_tree(False, root=self.repo)
                self.assertIn(os.path.basename(rel), str(cm.exception))
                self.assertIn("--allow-dirty", str(cm.exception))

    def _commit_gitignore(self, text):
        self._write(".gitignore", text)
        self.g("add", "-A")
        self.g("commit", "-q", "-m", "gitignore")

    def test_a_zero_byte_lock_file_ignored_by_the_repos_own_gitignore_does_not_block(self):
        lock = "docs/architecture/automation-config.json.lock"
        self._commit_gitignore(lock + "\n")
        self.assertEqual(self.real.scoped_dirty(self.repo), [])
        self._write(lock, "")                                                      # scripts/automation.py's 0-byte lock
        self.assertEqual(self.real.scoped_dirty(self.repo), [])
        self.assertEqual(self.real.check_clean_tree(False, root=self.repo), [])

    def test_a_stray_lock_that_the_repo_does_not_ignore_still_blocks(self):
        self._commit_gitignore("docs/architecture/automation-config.json.lock\n")
        for rel in ("scripts/stray.lock", "docs/architecture/other.lock", "data/history/ftmo/x.lock"):
            with self.subTest(rel):
                self._write(rel, "")
                dirty = self.real.scoped_dirty(self.repo)
                self.assertEqual(dirty, ["?? " + rel])
                with self.assertRaises(self.real.DirtyTreeRefused):
                    self.real.check_clean_tree(False, root=self.repo)
                os.remove(os.path.join(self.repo, rel))
        self.assertEqual(self.real.scoped_dirty(self.repo), [])

    def test_a_lock_hidden_only_by_a_local_exclude_not_the_repos_gitignore_still_blocks(self):
        lock = "docs/architecture/automation-config.json.lock"
        with open(os.path.join(self.repo, ".git", "info", "exclude"), "a") as fh:
            fh.write(lock + "\n")                                                  # a developer-local rule, not the repo's
        self._write(lock, "")
        self.assertEqual(self.real.scoped_dirty(self.repo), ["?? " + lock])

    def test_a_tracked_lock_file_that_changes_blocks_and_only_lock_files_are_exempt(self):
        self._write("scripts/tracked.lock", "a\n")
        self.g("add", "-A")
        self.g("commit", "-q", "-m", "tracked lock")
        self._commit_gitignore("scripts/tracked.lock\nscripts/ignored_other.json\n")   # ignored AND tracked
        self.assertEqual(self.real.scoped_dirty(self.repo), [])
        self._write("scripts/tracked.lock", "b\n")
        self.assertEqual(len(self.real.scoped_dirty(self.repo)), 1)                      # a tracked change is reported
        self._write("scripts/ignored_other.json", "{}\n")                                # ignored, not a .lock: still listed
        self.assertIn("?? scripts/ignored_other.json", self.real.scoped_dirty(self.repo))

    def test_skip_worktree_and_assume_unchanged_files_in_scope_block(self):
        for flag, undo, tag in (("--skip-worktree", "--no-skip-worktree", "S"), ("--assume-unchanged", "--no-assume-unchanged", "h")):
            with self.subTest(flag):
                self.assertEqual(self.real.scoped_dirty(self.repo), [])                  # clean first
                self.g("update-index", flag, "scripts/a.py")
                self._write("scripts/a.py", "x = 99\n")                                  # `git status` no longer shows this edit
                dirty = self.real.scoped_dirty(self.repo)
                self.assertEqual(dirty, [f"hidden-change-flag[{tag}] scripts/a.py"])
                with self.assertRaises(self.real.DirtyTreeRefused) as cm:
                    self.real.check_clean_tree(False, root=self.repo)
                self.assertIn("scripts/a.py", str(cm.exception))
                self.g("update-index", undo, "scripts/a.py")
                self.g("checkout", "-q", "--", "scripts/a.py")
        self.assertEqual(self.real.scoped_dirty(self.repo), [])

    def test_a_skip_worktree_file_outside_the_scope_does_not_block(self):
        self.g("update-index", "--skip-worktree", "config/env.example")
        self._write("config/env.example", "A=3\n")
        self.assertEqual(self.real.scoped_dirty(self.repo), [])

    def test_allow_dirty_is_loud_and_returns_the_lines(self):
        self._write("scripts/a.py", "x = 2\n")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            got = self.real.check_clean_tree(True, root=self.repo)
        self.assertEqual(len(got), 1)
        self.assertIn("scripts/a.py", got[0])
        self.assertIn("WARNING: --allow-dirty", err.getvalue())

    def test_the_committed_plan_discloses_the_same_prior_counts_as_the_code(self):
        plan = json.load(open(os.path.join(ROOT, "docs", "experiments", "fund-search", "plan.json")))
        self.assertEqual(plan["prior_counts_disclosed"], self.fs.PRIOR_COUNTS)
        self.assertEqual(self.fs.PRIOR_COUNTS["prop_search_records"], 180)
        self.assertEqual(self.fs.PRIOR_COUNTS["diagnosis_slices"], 30)

    def test_git_unavailable_is_not_clean(self):
        real = _fs()                                  # a module with the REAL scoped_dirty (setUp patches self.fs's)
        with mock.patch.object(real, "_git", return_value=None):
            with self.assertRaises(real.DirtyTreeRefused):
                real.check_clean_tree(False)

    def test_tree_pins_move_with_each_pinned_tree_and_ignore_the_ledger(self):
        base = self.real.tree_pins(self.repo)
        self.assertTrue(all(base.values()), base)

        def commit_change(rel, txt):
            self._write(rel, txt)
            self.g("add", "-A")
            self.g("commit", "-q", "-m", "change " + rel)
            return self.real.tree_pins(self.repo)
        cur = base
        for rel, moved in (("scripts/a.py", "scripts"), ("docs/architecture/analysis-params.json", "docs/architecture"),
                           ("data/history/costs/ftmo/symbolspec.X.json", "data/history/costs/ftmo"),
                           ("data/history/ftmo/ohlcv.X.5m.json", "data/history/ftmo")):
            with self.subTest(rel):
                new = commit_change(rel, "{\"changed\": \"" + rel + "\"}\n")
                self.assertEqual({k for k in new if new[k] != cur[k]}, {moved})   # exactly that pin, no other
                cur = new
        new = commit_change(self.real.LEDGER_REL, "{\"v\": 2, \"fund_search\": {}}\n")   # the declaration lives here
        self.assertEqual(new, cur)

    def test_the_tree_pin_is_a_real_git_tree_hash_and_works_in_a_shallow_clone(self):
        import subprocess
        pins = self.real.tree_pins(self.repo)
        self.assertEqual(pins["scripts"], subprocess.run(["git", "-C", self.repo, "rev-parse", "HEAD:scripts"],
                                                         capture_output=True, text=True).stdout.strip())
        self._write("scripts/a.py", "x = 3\n")
        self.g("add", "-A")
        self.g("commit", "-q", "-m", "second")                                 # two commits so --depth 1 is truly shallow
        shallow = os.path.join(self.tmp, "shallow")
        subprocess.run(["git", "clone", "-q", "--depth", "1", "file://" + self.repo, shallow], check=True,
                       capture_output=True)
        self.assertEqual(subprocess.run(["git", "-C", shallow, "rev-parse", "--is-shallow-repository"],
                                        capture_output=True, text=True).stdout.strip(), "true")
        self.assertEqual(self.real.tree_pins(shallow), self.real.tree_pins(self.repo))

    def _declared(self):
        self.fs.cmd_plan(grid_dir=FIXTURES)
        self.fs.cmd_declare()
        return json.load(open(self.ledger))["fund_search"]

    def test_the_declaration_records_pins_head_python_and_platform(self):
        decl = self._declared()
        self.assertEqual(set(decl["repo_pins"]["trees"]), set(self.fs.PINNED_TREES))
        self.assertTrue(all(decl["repo_pins"]["trees"].values()))
        self.assertEqual(len(decl["repo_pins"]["head"]), 40)
        self.assertEqual(decl["runtime"]["python"], sys.version.split()[0])
        self.assertTrue(decl["runtime"]["platform"])
        self.assertNotIn("allow_dirty", decl)

    def test_a_changed_pinned_tree_is_drift_and_run_refuses(self):
        decl = self._declared()
        plan = self.fs.load_plan(FIXTURES)
        self.assertEqual([d for d in self.fs.detect_drift(decl, plan) if d.startswith("tree ")], [])
        real = self.fs.tree_pins
        for path in self.fs.PINNED_TREES:                                      # each of the four, one at a time
            with self.subTest(path):
                with mock.patch.object(self.fs, "tree_pins", lambda root=None, p=path: dict(real(root), **{p: "e" * 40})):
                    drift = self.fs.detect_drift(decl, plan)
                    self.assertTrue(any(d.startswith(f"tree {path}:") for d in drift), drift)
                    with mock.patch.object(self.fs, "_evaluate_candidate") as ev:
                        with self.assertRaises(self.fs.DeclarationDrift) as cm:
                            self.fs.cmd_run("5m-metals", grid_dir=FIXTURES)
                    self.assertIn(f"tree {path}", str(cm.exception))
                    ev.assert_not_called()

    def test_a_declaration_without_pins_is_drift(self):
        decl = dict(self._declared())
        decl.pop("repo_pins")
        self.assertTrue(any("repo_pins" in d for d in self.fs.detect_drift(decl, self.fs.load_plan(FIXTURES))))

    def test_a_different_python_or_platform_is_a_note_not_a_refusal(self):
        decl = dict(self._declared(), runtime={"python": "3.12.1", "implementation": "CPython",
                                               "platform": "Linux-6.8-x86_64", "machine": "x86_64"})
        plan = self.fs.load_plan(FIXTURES)
        self.assertEqual([d for d in self.fs.detect_drift(decl, plan) if "runtime" in d], [])
        notes = self.fs.drift_notes(decl)
        self.assertTrue(any("runtime python: declared '3.12.1'" in n and "not a refusal" in n for n in notes), notes)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual([d for d in self.fs.check_drift(decl, plan) if "runtime" in d], [])   # does not raise
        self.assertIn("NOTE (not a refusal): runtime python", err.getvalue())
        self.assertEqual(self.fs.drift_notes(self._declared_again()), [])      # same interpreter: no note

    def _declared_again(self):
        return json.load(open(self.ledger))["fund_search"]

    def test_declare_and_run_and_scan_refuse_a_dirty_pinned_tree(self):
        self.fs.cmd_plan(grid_dir=FIXTURES)
        dirty = ["M scripts/fund_stats.py", "?? data/history/ftmo/new.json"]
        with mock.patch.object(self.fs, "scoped_dirty", lambda root=None: dirty):
            with self.assertRaises(self.fs.DirtyTreeRefused) as cm:
                self.fs.cmd_declare()
            self.assertIn("scripts/fund_stats.py", str(cm.exception))
            self.assertNotIn("fund_search", json.load(open(self.ledger)))      # nothing was written
            with mock.patch.object(self.fs, "_evaluate_candidate") as ev:
                with self.assertRaises(self.fs.DirtyTreeRefused):
                    self.fs.cmd_run("5m-metals", grid_dir=FIXTURES)
            ev.assert_not_called()
            with self.assertRaises(self.fs.DirtyTreeRefused):
                self.fs.cmd_scan("5m-metals", "XAUUSD", "ict", os.path.join(tempfile.gettempdir(), "b21-never"),
                                 grid_dir=FIXTURES)

    def test_allow_dirty_declares_with_the_dirty_list_and_stamps_every_record(self):
        self.fs.cmd_plan(grid_dir=FIXTURES)
        dirty = ["M scripts/fund_stats.py"]
        helper = _Helpers("run")
        helper.fs, helper.tmp = self.fs, self.tmp
        err = io.StringIO()
        with mock.patch.object(self.fs, "scoped_dirty", lambda root=None: dirty), contextlib.redirect_stderr(err):
            self.fs.cmd_declare(allow_dirty=True)
            decl = json.load(open(self.ledger))["fund_search"]
            self.assertEqual(decl["allow_dirty"], dirty)
            with mock.patch.object(self.fs, "_evaluate_candidate",
                                   side_effect=lambda c, h, g=None: helper._fake_out(c, h)):
                self.fs.cmd_run("5m-metals", grid_dir=FIXTURES, allow_dirty=True)
        self.assertIn("WARNING: --allow-dirty", err.getvalue())
        rec = X.load("ict-5m-metals", store=self.records)
        self.assertTrue(rec["parameters"]["drifted"])
        self.assertTrue(any("--allow-dirty" in d for d in rec["parameters"]["drift"]))


class MergeTimeGuards(_Helpers):
    def _bad_grid_dir(self):
        bad = os.path.join(self.tmp, "grids")
        shutil.copytree(FIXTURES, bad)
        p = os.path.join(bad, "v-grid-ict.json")
        d = json.load(open(p))
        d["items"][0]["implemented"] = False
        json.dump(d, open(p, "w"))
        return bad

    def test_an_unimplemented_item_is_counted_in_n_but_never_evaluated(self):
        """Declared-but-unimplemented items (real grids: B4, W4b) stay in N (stricter) and are excluded from selection
        and from the engine's grid; `run` no longer refuses the whole cell because of them."""
        bad = self._bad_grid_dir()
        with mock.patch.object(self.fs, "GRID_DIR", bad):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.fs.cmd_plan(dry_run=True)
            self.assertIn("declared, not runnable: ['B-EX']", buf.getvalue())
            self.assertIn("N per cell 41", buf.getvalue())                  # the grid size is still disclosed on the FULL grid
        full = FS.load_grid(os.path.join(bad, "v-grid-ict.json"))
        run = full.runnable()
        self.assertEqual(full.unimplemented, ["B-EX"])
        self.assertNotIn("B-EX", run.by_id)                                # not evaluated
        self.assertEqual(run.unimplemented, [])
        self.assertLess(FS.n_per_method(run), FS.n_per_method(full))       # N is only ever taken on the FULL grid
        self.fs.assert_grid_runnable(full)                                 # does not raise

    def test_a_fully_implemented_grid_is_its_own_runnable_grid(self):
        g = FS.load_grid(os.path.join(FIXTURES, "v-grid-ict.json"))
        self.assertIs(g.runnable(), g)

    def test_a_grid_that_can_drop_the_time_stop_needs_flat_before_rollover(self):
        ict = FS.load_grid(os.path.join(FIXTURES, "v-grid-ict.json"))
        self.assertTrue(self.fs.grid_has_no_time_stop_value(ict))            # B-EXIT-H has "none"
        mgmt_only = FS.Grid({"method": "ICT", "items": [
            {"id": "B-MGMT", "key": "fx_m", "existing_opts_key": "mgmt", "values": ["none", "be"]}]})
        self.assertFalse(self.fs.grid_has_no_time_stop_value(mgmt_only))     # breakeven "none" is not a time stop
        self.fs.assert_grid_runnable(ict)
        unfixed = lambda: {"flat_before_rollover": False, "rollover_provider": "mt5_bridge_ftmo"}
        with mock.patch.object(self.fs, "fixed_opts", unfixed):
            with self.assertRaises(SystemExit):
                self.fs.assert_grid_runnable(ict)
            with self.assertRaises(SystemExit):
                self.fs.build_overlay(ict, ict.baseline())

    def test_checked_simulate_refuses_an_overlay_without_flat_before_rollover(self):
        bt = mock.Mock()
        bt._OPTS_BASE = {"min_rr": 2.5, "fx_b_exit": "-2.0|H|floor"}     # the simulate-time context is built from it (C1)
        bt.simulate.return_value = (1.0, [], [])
        bt.SIM_LAST = {}
        with self.assertRaises(SystemExit):
            self.fs.checked_simulate(bt, [], 0.0, overlay={"flat_before_rollover": False})
        with self.assertRaises(SystemExit):
            self.fs.checked_simulate(bt, [], 0.0, overlay={})
        bt.simulate.assert_not_called()
        self.fs.checked_simulate(bt, [], 0.0, overlay=self.fs.fixed_opts())
        bt.simulate.assert_called_once()

    def test_a_v_value_nobody_declared_is_refused_before_any_scan(self):
        g = grid_two_items()
        g.by_id["a"]["key"] = "fx_a"
        with self.assertRaises(SystemExit) as cm:
            self.fs.build_overlay(g, {"a": "bogus", "b": 0})
        self.assertIn("does not declare", str(cm.exception))
        bt = mock.Mock()
        bt._OPTS_BASE = {"fx_a": None, "fx_b": None}
        eng = object.__new__(self.fs.BtEngine)
        eng.grid, eng.method, eng.tf, eng.symbols, eng.bt = g, "ICT", "5m", ["XAUUSD"], bt
        with self.assertRaises(SystemExit):
            eng.trades_for({"a": "bogus", "b": 0})
        bt.scan.assert_not_called()


# ============================================================================ declared cells + per-cell history spans
REAL_ARCH = os.path.join(ROOT, "docs", "architecture")


def _grid_dir_with_cells(tmp, mutate=None):
    """A private copy of the fixture grid dir whose cells file `mutate(spec)` may change."""
    gd = tempfile.mkdtemp(prefix="cells-", dir=tmp)
    for f in os.listdir(FIXTURES):
        if f.endswith(".json"):
            shutil.copy(os.path.join(FIXTURES, f), gd)
    if mutate:
        p = os.path.join(gd, "fund-search-cells.json")
        spec = json.load(open(p))
        mutate(spec)
        json.dump(spec, open(p, "w"), indent=1)
    return gd


class DeclaredCells(_Tmp):
    """docs/architecture/fund-search-cells.json: the cell list and each cell's history start are a pinned part of the plan."""

    REAL_FIRST = {("XAUUSD", "1m"): "2012-06-14T17:46:00Z", ("XAGUSD", "1m"): "2012-05-03T05:38:00Z",
                  ("XAUUSD", "5m"): "2004-06-11T04:15:00Z", ("XAGUSD", "5m"): "2008-11-07T21:10:00Z",
                  ("XAUUSD", "15m"): "2004-06-11T04:15:00Z", ("XAGUSD", "15m"): "2008-11-07T21:00:00Z"}

    def _first_bar(self, sym, tf):        # real first bars for the metals, the real indices start for the rest
        return self.REAL_FIRST.get((sym, tf), "2017-12-27T23:00:00Z")

    def _folds(self, p):
        return {c["id"]: c["n_folds"] for c in p["cells"]}

    def test_the_committed_cells_file_declares_exactly_three_cells_and_records_the_removed_ones(self):
        """Owner 2026-10-01 (cell selection, e_min <= 2 x e_star, primary pooling variant): three cells."""
        spec, path, sha = self.fs.load_cells_file(REAL_ARCH)
        self.assertEqual([c["id"] for c in spec["cells"]], ["1m-metals", "1m-indices", "5m-metals"])
        self.assertFalse(any(c["timeframe"] in ("15m", "30m") for c in spec["cells"]))
        removed = {r["id"]: r for r in spec["removed_cells"]}
        self.assertEqual(list(removed), ["30m-metals", "30m-indices", "5m-indices", "15m-metals", "15m-indices"])
        for r in removed.values():                         # every removal carries its reason, reference and decision
            self.assertTrue(r["reason"].strip() and r["decision"].strip())
            self.assertTrue(os.path.exists(os.path.join(ROOT, r["reference"])), r["reference"])
        self.assertIn("3.76", removed["5m-indices"]["reason"])
        self.assertIn("2.23", removed["15m-metals"]["reason"])
        self.assertIn("insufficient-fold", removed["15m-metals"]["reason"])
        self.assertIn("prior_counts_disclosed", removed["15m-metals"]["reason"])    # a re-add is a later, separate round
        self.assertIn("6.21", removed["15m-indices"]["reason"])
        self.assertIn("4.73", removed["30m-metals"]["reason"])
        self.assertEqual(sha, hashlib.sha256(open(path, "rb").read()).hexdigest())
        p = self.fs.build_plan(REAL_ARCH, first_bar=self._first_bar)
        self.assertEqual(p["cell_count"], 3)
        self.assertEqual(p["candidate_count"], 6)
        self.assertFalse(any(c["timeframe"] in ("15m", "30m") for c in p["candidates"]))
        self.assertEqual([r["id"] for r in p["cells_file"]["removed_cells"]], list(removed))
        self.assertEqual(p["family"]["size"], 6)                              # family A (2026-10-02): 3 cells x 2 methods
        self.assertAlmostEqual(p["family"]["floor_confidence"], 0.983333, places=6)
        self.assertEqual((p["grids"]["ict"]["n_per_cell"], p["grids"]["wyckoff"]["n_per_cell"]), (29, 16))   # disclosed only
        self.assertNotIn("n_by_method", p)                                    # the per-method N 87 / 48 is replaced
        self.assertEqual(p["cells_file"]["sha256"], sha)

    def test_the_committed_cells_carry_the_dev_starts_decided_by_the_availability_rule(self):
        """docs/audits/2026-10-02-dev-start-decision.md: 1m-metals keeps its data start (9 folds); 1m-indices starts
        2020-03-01 (2 folds); 5m-metals starts 2015-01-07 (7 folds)."""
        p = self.fs.build_plan(REAL_ARCH, first_bar=self._first_bar)
        self.assertEqual(self._folds(p), {"1m-metals": 9, "1m-indices": 2, "5m-metals": 7})
        by = {c["id"]: c for c in p["cells"]}
        self.assertEqual({k: v["dev_start_override"] for k, v in by.items()},
                         {"1m-metals": None, "1m-indices": "2020-03-01T00:00:00Z", "5m-metals": "2015-01-07T00:00:00Z"})
        self.assertEqual({k: v["span_source"] for k, v in by.items()},
                         {"1m-metals": "from data", "1m-indices": "declared", "5m-metals": "declared"})

    def test_the_fixture_is_a_six_cell_superset_of_the_committed_three_cells(self):
        """The fixture is test-local (wide cell list for late-start / override / shard tests); the three committed cells
        appear in it unchanged in id and symbols, and the plan built from it has all six."""
        real = {c["id"]: c["symbols"] for c in self.fs.load_cells_file(REAL_ARCH)[0]["cells"]}
        fix = {c["id"]: c["symbols"] for c in self.fs.load_cells_file(FIXTURES)[0]["cells"]}
        self.assertEqual(len(fix), 6)
        self.assertEqual({k: fix[k] for k in real}, real)
        self.assertEqual([c["id"] for c in self.plan()["cells"]], list(fix))
        self.assertGreater(len(fix["5m-indices"]), 5)               # a wide per-cell symbol list stays exercised

    def test_a_dev_start_override_changes_the_fold_counts(self):
        def mutate(spec):
            for c in spec["cells"]:
                c["dev_start"] = {"1m-metals": "2018-03-01T00:00:00Z", "1m-indices": "2020-03-01T00:00:00Z",
                                  "5m-metals": "2008-03-01T00:00:00Z"}.get(c["id"])
        gd = _grid_dir_with_cells(self.tmp, mutate)
        p = self.fs.build_plan(gd, first_bar=self._first_bar)
        self.assertEqual(self._folds(p), {"1m-metals": 4, "1m-indices": 2, "5m-metals": 14, "5m-indices": 4,
                                          "15m-metals": 17, "15m-indices": 4})
        c = next(x for x in p["cells"] if x["id"] == "5m-metals")
        self.assertEqual((c["development_start"], c["dev_start_override"], c["span_source"]),
                         ("2008-03-01T00:00:00Z", "2008-03-01T00:00:00Z", "declared"))
        self.assertEqual(c["symbol_first_bar"]["XAGUSD"], "2008-11-07T21:10:00Z")      # a later symbol is disclosed
        self.assertEqual(p["cells_file"]["sha256"], hashlib.sha256(
            open(os.path.join(gd, "fund-search-cells.json"), "rb").read()).hexdigest())
        self.assertEqual(self.fs.evaluation_config(p)["dev_start_by_cell"]["5m-metals"], "2008-03-01T00:00:00Z")
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.fs.cmd_plan(dry_run=True, grid_dir=gd)
        self.assertIn("folds 14", buf.getvalue())
        self.assertIn("(declared)", buf.getvalue())

    def test_a_declared_start_before_any_symbols_data_is_refused(self):
        gd = _grid_dir_with_cells(self.tmp, lambda spec: spec["cells"][2].update(dev_start="2001-03-01T00:00:00Z"))
        with self.assertRaises(SystemExit) as cm:
            self.fs.build_plan(gd, first_bar=self._first_bar)
        self.assertIn("before the first bar its data has", str(cm.exception))

    def test_a_declared_start_that_yields_fewer_than_min_test_folds_is_refused(self):
        # folds end at the cutoff 2024-03-01, 365 days each, after >= 730 training days: 2020-03-01 is the first start with 2
        ok = _grid_dir_with_cells(self.tmp, lambda spec: spec["cells"][2].update(dev_start="2020-03-01T00:00:00Z"))
        self.assertEqual(self._folds(self.fs.build_plan(ok, first_bar=self._first_bar))["5m-metals"], 2)
        gd = _grid_dir_with_cells(self.tmp, lambda spec: spec["cells"][2].update(dev_start="2021-03-01T00:00:00Z"))
        with self.assertRaises(SystemExit) as cm:
            self.fs.build_plan(gd, first_bar=self._first_bar)
        self.assertIn("MIN_TEST_FOLDS", str(cm.exception))
        self.assertIn("5m-metals", str(cm.exception))

    def test_a_malformed_cells_file_is_refused_not_repaired(self):
        bad = [lambda s: s["cells"][0].update(timeframe="30m", id="30m-metals"),
               lambda s: s["cells"][0].update(dev_start="2018-03-01"),
               lambda s: s["cells"][0].update(dev_start="2024-03-01T00:00:00Z"),       # not before the cutoff
               lambda s: s["cells"][0].update(rationale=" "),
               lambda s: s["cells"][0].update(symbols=["US500"]),                       # an index in a metals cell
               lambda s: s["cells"][0].update(unexpected=1),
               lambda s: s["cells"].append(dict(s["cells"][0])),                        # duplicate id
               lambda s: s.update(warmup_days=0),
               lambda s: s.update(cells=[])]
        for i, m in enumerate(bad):
            gd = _grid_dir_with_cells(self.tmp, m)
            with self.assertRaises(SystemExit, msg=f"mutation {i}"):
                self.fs.load_cells_file(gd)
        empty = tempfile.mkdtemp(dir=self.tmp)
        with self.assertRaises(SystemExit) as cm:
            self.fs.load_cells_file(empty)
        self.assertIn("cells file missing", str(cm.exception))

    def test_the_cells_file_hash_is_in_the_plan_core_so_a_changed_file_changes_plan_hash(self):
        gd = _grid_dir_with_cells(self.tmp)
        h0 = self.fs.build_plan(gd, first_bar=self._first_bar)["plan_hash"]
        self.assertEqual(h0, self.fs.build_plan(gd, first_bar=self._first_bar)["plan_hash"])       # deterministic
        p = os.path.join(gd, "fund-search-cells.json")
        spec = json.load(open(p))
        spec["cells"][0]["rationale"] += " (edited)"
        json.dump(spec, open(p, "w"))
        self.assertNotEqual(self.fs.build_plan(gd, first_bar=self._first_bar)["plan_hash"], h0)

    def test_an_edit_touching_no_cell_field_still_changes_plan_hash(self):
        gd = _grid_dir_with_cells(self.tmp)
        p0 = self.fs.build_plan(gd, first_bar=self._first_bar)
        p = os.path.join(gd, "fund-search-cells.json")
        for mutate in (lambda s: s.update(_why=s["_why"] + " x"), lambda s: s.update(_source="elsewhere")):
            spec = json.load(open(p))
            mutate(spec)
            json.dump(spec, open(p, "w"))
            p1 = self.fs.build_plan(gd, first_bar=self._first_bar)
            self.assertEqual(p1["cells"], p0["cells"])                       # no cell field moved ...
            self.assertNotEqual(p1["plan_hash"], p0["plan_hash"])            # ... yet the hash did
            shutil.copy(os.path.join(FIXTURES, "fund-search-cells.json"), p)
        with open(p, "a") as fh:                                              # whitespace only
            fh.write("\n \n")
        self.assertNotEqual(self.fs.build_plan(gd, first_bar=self._first_bar)["plan_hash"], p0["plan_hash"])

    def test_the_plan_core_carries_the_cells_file_sha256(self):
        gd = _grid_dir_with_cells(self.tmp)
        plan = self.fs.build_plan(gd, first_bar=self._first_bar)
        want = hashlib.sha256(open(os.path.join(gd, "fund-search-cells.json"), "rb").read()).hexdigest()
        self.assertEqual(plan["cells_file"]["sha256"], want)
        core = {k: v for k, v in plan.items() if k in ("cells", "cells_file", "excluded_cells", "grids", "candidates",
                                                       "family", "cost_profile", "cost_profile_pin", "dev_cutoff",
                                                       "adopted_f_keys", "perturbation_axes",
                                                       "embargo", "constants")}
        self.assertEqual(self.fs._hash(core), plan["plan_hash"])            # cells_file is inside what is hashed
        core.pop("cells_file")
        self.assertNotEqual(self.fs._hash(core), plan["plan_hash"])

    def test_the_declaration_pins_the_cells_file_and_run_refuses_a_mutated_one(self):
        gd = _grid_dir_with_cells(self.tmp)
        with mock.patch.object(self.fs, "GRID_DIR", gd):
            self.fs.cmd_plan(grid_dir=gd)
            self.fs.cmd_declare()
            decl = json.load(open(self.ledger))["fund_search"]
            want = hashlib.sha256(open(os.path.join(gd, "fund-search-cells.json"), "rb").read()).hexdigest()
            self.assertEqual(decl["evaluation_config"]["cells_sha256"], want)
            self.assertEqual(decl["cells"], [c["id"] for c in self.plan_of(gd)["cells"]])
            p = os.path.join(gd, "fund-search-cells.json")
            spec = json.load(open(p))
            spec["cells"][0]["rationale"] += " (edited after declare)"
            json.dump(spec, open(p, "w"))
            with mock.patch.object(self.fs, "_evaluate_candidate") as ev:
                with self.assertRaises(SystemExit) as cm:
                    self.fs.cmd_run("5m-metals", grid_dir=gd)
            self.assertIn("no longer matches the recomputed cell space", str(cm.exception))
            ev.assert_not_called()
            # the drift detector names the pinned hash too (a declaration made by an older plan, same plan_hash)
            plan = self.plan_of(gd)
            self.assertIn("cells_sha256", " ".join(self.fs.detect_drift(
                dict(decl, evaluation_config=dict(decl["evaluation_config"], cells_sha256="0" * 64)), plan)))

    def test_a_scan_refuses_a_mutated_cells_file_too(self):
        gd = _grid_dir_with_cells(self.tmp)
        with mock.patch.object(self.fs, "GRID_DIR", gd):
            self.fs.cmd_plan(grid_dir=gd)
            self.fs.cmd_declare()
            p = os.path.join(gd, "fund-search-cells.json")
            spec = json.load(open(p))
            spec["warmup_days"] = 15
            json.dump(spec, open(p, "w"))
            with self.assertRaises(SystemExit) as cm:
                self.fs.cmd_scan("5m-metals", "XAUUSD", "ict", os.path.join(tempfile.gettempdir(), "b11-never"),
                                 grid_dir=gd)
            self.assertIn("no longer matches", str(cm.exception))

    def plan_of(self, gd):
        return self.fs.build_plan(gd, first_bar=self._first_bar)

    def test_list_cells_and_the_shard_matrix_follow_the_declared_cells_and_carry_no_30m(self):
        gd = _grid_dir_with_cells(self.tmp)
        with mock.patch.object(self.fs, "GRID_DIR", gd):
            self.fs.cmd_plan(grid_dir=gd)
            out = io.StringIO()
            with redirect_stdout(out):
                self.fs.main(["list-cells"])
                self.fs.main(["list-scan-shards"])
                self.fs.main(["list-scan-shards", "--explain"])
            lines = out.getvalue().splitlines()
            cells = json.loads(lines[0])
            self.assertEqual([c["cell"] for c in cells], ["1m-metals", "1m-indices", "5m-metals", "5m-indices",
                                                          "15m-metals", "15m-indices"])
            rows = json.loads(lines[1])
            self.assertTrue(rows)
            self.assertEqual({r["cell"] for r in rows}, {c["cell"] for c in cells})
            self.assertFalse([r for r in rows if "30m" in r["cell"] or "30m" in r["name"]])
            self.assertFalse([ln for ln in lines[2:] if ln.startswith("30m")])

    def test_shard_sizing_scales_bars_only_for_a_declared_later_start(self):
        cell = {"timeframe": "5m", "dev_start_override": None, "symbol_first_bar": {"XAUUSD": "2004-06-11T04:15:00Z"}}
        self.assertEqual(self.fs.cell_bars(cell, "XAUUSD"), self.fs.DEV_BARS["5m"]["XAUUSD"])
        later = dict(cell, dev_start_override="2014-03-01T00:00:00Z")
        half = self.fs.cell_bars(later, "XAUUSD")
        self.assertLess(half, self.fs.DEV_BARS["5m"]["XAUUSD"])
        self.assertGreater(half, 0)
        no_later_symbol = dict(later, symbol_first_bar={"XAUUSD": "2015-01-01T00:00:00Z"})     # starts after the override
        self.assertEqual(self.fs.cell_bars(no_later_symbol, "XAUUSD"), self.fs.DEV_BARS["5m"]["XAUUSD"])

    def test_a_measured_span_row_wins_over_the_time_scaled_estimate(self):
        cell = {"timeframe": "1m", "dev_start_override": "2020-03-01T00:00:00Z",
                "symbol_first_bar": {"US30": "2017-12-27T23:00:00Z"}}
        self.assertEqual(self.fs.cell_bars(cell, "US30"), self.fs.SPAN_BARS[("1m", "US30", "2020-03-01T00:00:00Z")])
        scaled = dict(cell, dev_start_override="2020-03-02T00:00:00Z")          # no measured row for this start: the estimate
        self.assertLess(self.fs.cell_bars(scaled, "US30"), self.fs.cell_bars(cell, "US30"))   # sparse history: it UNDER-counts

    def test_every_declared_later_start_has_a_measured_span_row_that_fits_the_audit_table(self):
        """Real cells file: each (timeframe, symbol, declared start) has a SPAN_BARS row (the estimate is never used for the
        real plan), and a cut series never has MORE bars than the whole development span plus the warm-up of the cut."""
        spec = self.fs.load_cells_file(os.path.join(ROOT, "docs", "architecture"))[0]
        later = [c for c in spec["cells"] if c["dev_start"]]
        self.assertEqual({c["id"] for c in later}, {"1m-indices", "5m-metals"})
        for c in later:
            for sym in c["symbols"]:
                key = (c["timeframe"], sym, c["dev_start"])
                self.assertIn(key, self.fs.SPAN_BARS, f"no measured bars for {key}")
                self.assertLessEqual(self.fs.SPAN_BARS[key], _REAL_DEV_BARS[c["timeframe"]][sym])
                self.assertGreater(self.fs.SPAN_BARS[key], 0.3 * _REAL_DEV_BARS[c["timeframe"]][sym])

    def test_wave2_set_count_is_the_measured_affine_fit_with_its_margin(self):
        fs = self.fs
        for method, (n2, n7) in {"ict": (29, 69), "wyckoff": (16, 50)}.items():
            # the two measured points (2026-10-02, real folds of 1m-indices and 5m-metals) are covered by the estimate ...
            self.assertGreaterEqual(fs.wave2_set_count(method, 2), n2)
            self.assertGreaterEqual(fs.wave2_set_count(method, 7), n7)
            # ... by no more than the stated margin plus rounding, and it grows with the folds
            self.assertLessEqual(fs.wave2_set_count(method, 2), 1.15 * n2 + 1)
            self.assertLessEqual(fs.wave2_set_count(method, 7), 1.15 * n7 + 1)
            self.assertLess(fs.wave2_set_count(method, 2), fs.wave2_set_count(method, 9))
        self.assertEqual(fs.WAVE2_SAFETY_MARGIN, 1.10)


class SeriesStartSeam(unittest.TestCase):
    """bt.series_start / load(): the declared start cuts ONE (symbol, timeframe) series, nothing else."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="series-start-")
        cls.env = os.environ.get("BT_HISTORY_ROOT")
        t0 = datetime.datetime(2022, 1, 3, tzinfo=datetime.timezone.utc)
        for tf, minutes in (("5m", 5), ("1H", 60)):
            cs = []
            for i in range(3000 if tf == "5m" else 300):
                t = t0 + datetime.timedelta(minutes=minutes * i)
                cs.append({"time": FS.iso(t), "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1})
            json.dump({"symbol": "XAUUSD", "timeframe": tf, "_source": "synthetic", "candles": cs},
                      open(os.path.join(cls.tmp, f"ohlcv.XAUUSD.{tf}.json"), "w"))
        os.environ["BT_HISTORY_ROOT"] = cls.tmp
        spec = importlib.util.spec_from_file_location("bt_seam", os.path.join(ROOT, "scripts", "backtest-methods.py"))
        cls.bt = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.bt)
        cls.bt.HISTORY_ROOT = cls.tmp

    @classmethod
    def tearDownClass(cls):
        if cls.env is None:
            os.environ.pop("BT_HISTORY_ROOT", None)
        else:
            os.environ["BT_HISTORY_ROOT"] = cls.env
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def tearDown(self):
        self.bt._SERIES_START.clear()

    def test_default_is_every_bar(self):
        self.assertEqual(len(self.bt.load("XAUUSD", "5m")[0]), 3000)

    def test_the_cut_keeps_lead_bars_before_the_start_and_everything_after(self):
        full = self.bt.load("XAUUSD", "5m")[0]
        start = full[1000]["time"]
        self.bt.series_start("XAUUSD", "5m", start, 360)
        cut = self.bt.load("XAUUSD", "5m")[0]
        self.assertEqual(cut, full[640:])
        self.bt.series_start("XAUUSD", "5m", start, 5000)            # more lead than bars: clamps at the series start
        self.assertEqual(self.bt.load("XAUUSD", "5m")[0], full)

    def test_a_higher_timeframe_series_keeps_its_full_history(self):
        self.bt.series_start("XAUUSD", "5m", self.bt.load("XAUUSD", "5m")[0][2000]["time"], 0)
        self.assertEqual(len(self.bt.load("XAUUSD", "1H")[0]), 300)

    def test_lifting_the_cut_restores_every_bar(self):
        self.bt.series_start("XAUUSD", "5m", self.bt.load("XAUUSD", "5m")[0][2000]["time"], 0)
        self.bt.series_start("XAUUSD", "5m", None)
        self.assertEqual(len(self.bt.load("XAUUSD", "5m")[0]), 3000)

    def test_the_cut_composes_with_the_pit_cutoff(self):
        full = self.bt.load("XAUUSD", "5m")[0]
        self.bt.pit_cutoff(full[2500]["time"])
        try:
            self.bt.series_start("XAUUSD", "5m", full[1000]["time"], 0)
            cut = self.bt.load("XAUUSD", "5m")[0]
            self.assertEqual(cut[0]["time"], full[1000]["time"])
            self.assertLessEqual(cut[-1]["time"], full[2500]["time"])      # PIT cut applied first, never undone
        finally:
            self.bt.pit_cutoff(None)

    def test_scan_many_hands_the_start_to_its_spawned_workers(self):
        import scan_many as SM
        captured = {}

        class Boom(Exception):
            pass

        def fake_submit(self_, fn, spec):
            captured.update(spec)
            raise Boom

        self.bt.series_start("XAUUSD", "5m", "2022-01-05T00:00:00Z", 12)
        with mock.patch.object(SM._pool.IsolatedExecutor, "submit", fake_submit), \
                mock.patch.object(SM, "clamp_workers", return_value=2), \
                mock.patch.object(SM, "MIN_CHUNK_BARS", 100):
            with self.assertRaises(Boom):
                SM.scan_many(self.bt, "XAUUSD", "5m", "ICT", [{}], workers=2, chunks=2, min_chunk_bars=100)
        self.assertEqual(captured["series_start"], {("XAUUSD", "5m"): ("2022-01-05T00:00:00Z", 12)})


class EngineDevStart(unittest.TestCase):
    """BtEngine(dev_start=...): no trade before dev_start exists, and what is left equals the full-series run."""

    @classmethod
    def setUpClass(cls):
        d = os.path.join(ROOT, "data", "history", "ftmo", "ohlcv.XAUUSD.15m")
        if not os.path.isdir(d):               # never a silent skip: this proof must run wherever the data should be
            raise AssertionError(f"{d} is missing: EngineDevStart (the dev_start equivalence proof) needs the FTMO history; "
                                 f"run it in a checkout that has data/history/ftmo")
        cls.tmp = tempfile.mkdtemp(prefix="dev-start-")
        cls.env = os.environ.get("BT_HISTORY_ROOT")
        cls.hist = os.path.join(cls.tmp, "hist")
        cls.first, _ = _write_slice_root(cls.hist, "XAUUSD", "15m", 40000)
        os.environ["BT_HISTORY_ROOT"] = cls.hist
        cls.fs = _fs()
        grids, _ = cls.fs.load_grids(REAL_ARCH)
        cls.grids = grids
        cls.dev_start = FS.iso(FS.ts(cls.first) + datetime.timedelta(days=120))

    @classmethod
    def tearDownClass(cls):
        if cls.env is None:
            os.environ.pop("BT_HISTORY_ROOT", None)
        else:
            os.environ["BT_HISTORY_ROOT"] = cls.env
        shutil.rmtree(cls.tmp, ignore_errors=True)

    START_DEPENDENT = ("exit", "pnl")     # exit = bar INDEX into the loaded (cut) series; pnl = $ on an account compounding from the run's first trade

    def _sha(self, trades):
        rows = [{k: v for k, v in t.items() if k not in self.START_DEPENDENT} for t in trades]
        return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()

    def _both(self, method, runner):
        grid = self.grids[method].runnable()
        full_engine = self.fs.BtEngine(grid, runner, "15m", ["XAUUSD"], workers=1)
        cut_engine = self.fs.BtEngine(grid, runner, "15m", ["XAUUSD"], workers=1, dev_start=self.dev_start, warmup_days=14)
        return (full_engine, full_engine.trades_for(grid.baseline()), cut_engine, cut_engine.trades_for(grid.baseline()))

    def test_ict_no_trade_before_dev_start_and_the_rest_equals_the_full_run(self):
        fe, full, ce, cut = self._both("ict", "ICT")
        ds = FS.ts(self.dev_start)
        self.assertGreater(len(cut), 0, "the slice must produce trades for this check to bite")
        self.assertTrue(all(FS.ts(t["entry_time"]) >= ds for t in cut))
        self.assertGreater(ce._series["XAUUSD"]["first_open"], fe._series["XAUUSD"]["first_open"])   # data really cut
        self.assertLess(ce._series["XAUUSD"]["bars"], fe._series["XAUUSD"]["bars"])
        self.assertTrue(any(FS.ts(t["entry_time"]) < ds for t in full), "the full run has pre-start trades to drop")
        want = [t for t in full if FS.ts(t["entry_time"]) >= ds]
        self.assertEqual(self._sha(cut), self._sha(want))
        self.assertEqual(ce.span["dev_start"], self.dev_start)
        self.assertTrue(all(FS.ts(r["entry_time"]) >= ds for r in ce._admission[FS.CountingSource._key(ce.grid.baseline())]))

    def test_wyckoff_no_trade_before_dev_start_and_the_rest_equals_the_full_run(self):
        fe, full, ce, cut = self._both("wyckoff", "WYCKOFF-BOOK")
        ds = FS.ts(self.dev_start)
        self.assertGreater(len(cut), 0, "the slice must produce trades for this check to bite")
        self.assertTrue(any(FS.ts(t["entry_time"]) < ds for t in full), "the full run has pre-start trades to drop")
        self.assertTrue(all(FS.ts(t["entry_time"]) >= ds for t in cut))
        want = [t for t in full if FS.ts(t["entry_time"]) >= ds]
        self.assertEqual(self._sha(cut), self._sha(want))

    def test_dev_start_without_warmup_is_refused_and_no_dev_start_is_a_noop(self):
        grid = self.grids["ict"].runnable()
        with self.assertRaises(ValueError):
            self.fs.BtEngine(grid, "ICT", "15m", ["XAUUSD"], dev_start=self.dev_start)
        e = self.fs.BtEngine(grid, "ICT", "15m", ["XAUUSD"], workers=1)
        self.assertIsNone(e.span)
        self.assertIsNone(e.dataset_snapshot()["series"][0]["_series_start"])

    def test_the_snapshot_names_the_declared_start(self):
        grid = self.grids["ict"].runnable()
        e = self.fs.BtEngine(grid, "ICT", "15m", ["XAUUSD"], workers=1, dev_start=self.dev_start, warmup_days=14)
        row = e.dataset_snapshot()["series"][0]
        self.assertEqual(row["_series_start"]["dev_start"], self.dev_start)
        self.assertEqual(row["_series_start"]["warmup_days"], 14)
        self.assertEqual(row["first_open"] < self.dev_start, True)                       # warm-up bars precede the start


class ZeroRiskHarnessEngine(unittest.TestCase):
    """Item 12 on the REAL BtEngine.trades_for path (real simulate(), real cost profile, real XAUUSD slice): a value set whose
    raw scan holds a zero-risk trade (the ICT B-EX=fill `entry == stop` record) used to abort in `real_costs.cost_r`
    (`CostRefused: stop distance is zero`). It must now complete, refuse that candidate with a counted `zero_risk`
    admission row, and leave every other trade exactly as it was. The raw scan is seeded by hand (what `scan_many` would
    hand over), so no engine R / expectancy of any real evaluation is involved."""

    @classmethod
    def setUpClass(cls):
        d = os.path.join(ROOT, "data", "history", "ftmo", "ohlcv.XAUUSD.15m")
        if not os.path.isdir(d):               # never a silent skip: this proof must run wherever the data should be
            raise AssertionError(f"{d} is missing: ZeroRiskHarnessEngine needs the FTMO history")
        cls.tmp = tempfile.mkdtemp(prefix="zero-risk-")
        cls.env = os.environ.get("BT_HISTORY_ROOT")
        hist = os.path.join(cls.tmp, "hist")
        _write_slice_root(hist, "XAUUSD", "15m", 3000)
        os.environ["BT_HISTORY_ROOT"] = hist
        cls.fs = _fs()
        grids, _ = cls.fs.load_grids(REAL_ARCH)
        cls.grid = grids["ict"].runnable()

    @classmethod
    def tearDownClass(cls):
        if cls.env is None:
            os.environ.pop("BT_HISTORY_ROOT", None)
        else:
            os.environ["BT_HISTORY_ROOT"] = cls.env
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _t(self, i, entry, stop, side="long", **extra):
        base = datetime.datetime(2023, 6, 6, 8, tzinfo=datetime.timezone.utc) + datetime.timedelta(hours=2 * i)
        rp = abs(entry - stop) and 6.0
        t = {"symbol": "XAUUSD", "tf": "15m", "side": side, "entry": entry, "stop": stop, "target": entry + 6 * (entry - stop),
             "entry_time": FS.iso(base), "exit_time": FS.iso(base + datetime.timedelta(hours=1)), "outcome": "win",
             "R": 6.0, "R_planned": rp or None, "event": f"XAUUSD-{side}-ict-s{i}-m{i}"}
        t.update(extra)
        return t

    def _engine(self, raw):
        eng = self.fs.BtEngine(self.grid, "ICT", "15m", ["XAUUSD"], workers=1)
        eng._raw[FS.CountingSource._key(self.grid.baseline())] = list(raw)
        return eng

    def _raw(self):
        return [self._t(0, 2000.0, 1998.0), self._t(1, 4053.5, 4053.5), self._t(2, 2000.0, 2002.0, side="short")]

    def test_a_value_set_with_a_zero_risk_trade_no_longer_aborts_and_records_the_refusal(self):
        raw = self._raw()
        import real_costs as RC
        with self.assertRaises(RC.CostRefused):
            RC.cost_r(raw[1]["entry"], raw[1]["stop"], raw[1]["entry_time"], raw[1]["exit_time"], "XAUUSD", "long",
                      self.fs.COST_PROFILE)                           # what the harness did before: it aborted here
        eng = self._engine(raw)
        taken = eng.trades_for(self.grid.baseline())                  # does NOT raise
        self.assertEqual([t["event"] for t in taken], [raw[0]["event"], raw[2]["event"]])
        st = eng.admission_stats(self.grid.baseline())
        self.assertEqual((st["candidates"], st["refused_zero_risk"], st["refused_min_rr"]), (3, 1, 0))
        rows = eng._admission[FS.CountingSource._key(self.grid.baseline())]
        self.assertEqual([r.get("zero_risk") for r in rows], [None, "zero", None])
        self.assertEqual(eng.bt.SIM_LAST["refused"]["zero_risk"], 1)  # simulate() and the harness count the same candidates
        fold = {"test_start": raw[1]["entry_time"], "test_end": FS.iso(FS.ts(raw[1]["entry_time"]) + datetime.timedelta(hours=1))}
        self.assertEqual(eng.admission_stats(self.grid.baseline(), fold)["refused_zero_risk"], 1)
        other = {"test_start": raw[2]["entry_time"], "test_end": FS.iso(FS.ts(raw[2]["entry_time"]) + datetime.timedelta(hours=1))}
        self.assertEqual(eng.admission_stats(self.grid.baseline(), other)["refused_zero_risk"], 0)

    def test_the_other_trades_are_exactly_what_they_are_without_the_zero_risk_one(self):
        with_zero = self._engine(self._raw()).trades_for(self.grid.baseline())
        without = self._engine([t for i, t in enumerate(self._raw()) if i != 1]).trades_for(self.grid.baseline())
        self.assertEqual(json.dumps(with_zero, sort_keys=True), json.dumps(without, sort_keys=True))

    def test_a_set_without_a_zero_risk_trade_reports_zero_refusals(self):
        eng = self._engine([t for i, t in enumerate(self._raw()) if i != 1])
        eng.trades_for(self.grid.baseline())
        st = eng.admission_stats(self.grid.baseline())
        self.assertEqual((st["candidates"], st["refused_zero_risk"]), (2, 0))

    def test_harness_and_simulate_disagreement_fails_loud(self):
        eng = self._engine(self._raw())
        real, calls = eng.bt.planned_risk_refusal, {"n": 0}

        def harness_says_zero_simulate_says_real(*a, **k):            # the harness' 3 row calls come first, then simulate's
            calls["n"] += 1
            return "zero" if calls["n"] <= 3 else real(*a, **k)
        eng.bt.planned_risk_refusal = harness_says_zero_simulate_says_real
        with self.assertRaises(RuntimeError) as cm:
            eng.trades_for(self.grid.baseline())
        self.assertIn("planned-risk admission disagrees", str(cm.exception))


class AdoptedFKeys(unittest.TestCase):
    """Owner adoption 2026-09-30 (docs/plans/2026-09-30-owner-decisions.md): the nine F items are ON in every cell."""

    @classmethod
    def setUpClass(cls):
        cls.fs = _fs()

    def test_the_nine_keys_are_in_every_overlay_and_are_engine_keys_that_default_off(self):
        bt = self.fs._load_bt()
        self.assertEqual(len(self.fs.ADOPTED_F_KEYS), 12)              # nine F items + O1 fx_admission_entry_cost + C3 fx_gap_fill + D3 fx_fvg_formed_start
        self.assertIn("fx_fvg_formed_start", self.fs.ADOPTED_F_KEYS)
        self.assertIn("fx_admission_entry_cost", self.fs.ADOPTED_F_KEYS)
        self.assertIn("fx_gap_fill", self.fs.ADOPTED_F_KEYS)
        fixed = self.fs.fixed_opts()
        for k in self.fs.ADOPTED_F_KEYS:
            self.assertIn(k, bt._OPTS_BASE, k)
            self.assertIs(bt._OPTS_BASE[k], False, f"{k}: engine default must stay v1 (off)")
            self.assertIs(fixed[k], True, k)

    def test_a_grid_item_can_never_set_an_adopted_key(self):
        for k in self.fs.ADOPTED_F_KEYS:
            g = FS.Grid({"method": "ICT", "items": [{"id": "X", "key": k, "values": [False, True]}]})
            with self.assertRaises(SystemExit):
                self.fs.validate_grid(g)

    def test_the_adopted_set_is_part_of_the_plan_hash_and_the_declaration_config(self):
        plan = self.fs.build_plan(grid_dir=FIXTURES, first_bar=lambda s, t: "2010-01-01T00:00:00Z")
        self.assertEqual(plan["adopted_f_keys"], list(self.fs.ADOPTED_F_KEYS))
        self.assertEqual(self.fs.evaluation_config(plan)["adopted_f_keys"], list(self.fs.ADOPTED_F_KEYS))


# ============================================================================ Actions scan shards + scan cache
class ShardLayout(_Helpers):
    """`list-scan-shards`: a pure function of the plan and the declared grids (data availability, never a result)."""

    def test_every_wave_of_every_symbol_is_covered_by_disjoint_contiguous_slices(self):
        self._plan_file()
        plan = self.fs.load_plan()
        rows = self.fs.shard_plan(plan)
        groups = {}
        for r in rows:
            groups.setdefault((r["cell"], r["method"], r["symbol"], r["wave"]), []).append(r)
        for rs in groups.values():
            n = int(rs[0]["slice"].split("/")[1])
            self.assertEqual(sorted(int(r["slice"].split("/")[0]) for r in rs), list(range(n)))
            self.assertTrue(all(r["slice"].endswith(f"/{n}") for r in rs))
            self.assertGreater(sum(r["sets"] for r in rs), 0)
        self.assertEqual({r["cell"] for r in rows}, {c["id"] for c in plan["cells"]})
        self.assertEqual(len({r["name"] for r in rows}), len(rows), "shard names (artifact names) must be unique")
        self.assertEqual(json.loads(json.dumps(rows)), rows)
        for c in plan["cells"]:      # exactly the plan's symbols of the cell: none added, none dropped
            self.assertEqual({r["symbol"] for r in rows if r["cell"] == c["id"]}, set(c["symbols"]))

    def test_slices_partition_the_wave_exactly_in_order(self):
        for n in (0, 1, 5, 39, 99, 187):
            for k in (1, 2, 3, 7, 17):
                items = list(range(n))
                parts = [self.fs.take_slice(items, i, k) for i in range(k)]
                self.assertEqual([x for p in parts for x in p], items)

    def test_heavy_cells_are_sliced_and_no_shard_is_modelled_over_the_timeout(self):
        self._plan_file()
        rows = self.fs.shard_plan(self.fs.load_plan())
        heavy = [r for r in rows if r["cell"] == "1m-metals" and r["method"] == "ict" and r["wave"] == 1]
        self.assertGreater(len(heavy), 2)                     # more than one shard per symbol (2 symbols)
        self.assertFalse(any(r["over_timeout"] for r in rows))
        self.assertLessEqual(max(r["est_min"] for r in rows), self.fs.SHARD_MODEL["job_timeout_min"])

    def test_no_shard_is_over_the_cap_at_the_slow_runner_factor(self):
        """The layout is made for the slow-runner assumption (factor 3.0): NO shard may be modelled above the cap there
        -- asserted from the model's own numbers, not from a stored expectation."""
        m = self.fs.SHARD_MODEL
        self.assertEqual(m["layout_factor"], 3.0)
        self.assertEqual(m["budget_s"], 300 * 60)
        self._plan_file()
        plan = self.fs.load_plan()
        rows = self.fs.shard_plan(plan)
        cap_min = m["budget_s"] / 60
        self.assertFalse(any(r["over_cap"] for r in rows))
        self.assertLessEqual(max(r["est_min"] for r in rows), cap_min)
        self.assertLessEqual(max(r["est_min_by_factor"]["3"] for r in rows), cap_min)
        self.assertEqual([r["est_min"] for r in rows], [r["est_min_by_factor"]["3"] for r in rows])
        # recomputed independently of the rows: the model's own function, slice by slice, at factor 3.0
        grids, _ = self.fs.load_grids()
        bt = self.fs._load_bt()
        by_cell = {c["id"]: c for c in plan["cells"]}
        for r in rows[:: max(1, len(rows) // 40)]:                       # a spread of 40 shards, every cell/method/wave
            cell = by_cell[r["cell"]]
            g = grids[r["method"]].runnable()
            info = self.fs.wave1_group_info(g, r["method"], cell, cell["symbols"][0], bt)
            i, n = self.fs.parse_slice(r["slice"])
            total = len(info) if r["wave"] == 1 else self.fs.wave2_set_count(r["method"], cell["n_folds"])
            lo, hi = self.fs.slice_bounds(total, i, n)
            groups = self.fs._slice_groups(r["method"], r["wave"], info, lo, hi, cell["timeframe"])
            secs = self.fs.shard_seconds(r["wave"], cell, r["method"], r["symbol"], groups, hi - lo, 3.0, n_wave1=len(info))
            self.assertAlmostEqual(secs / 60, r["est_min"], delta=1.0)
            self.assertLessEqual(secs, m["budget_s"])

    def test_the_layout_follows_the_factor_and_the_model_scales_with_it(self):
        self._plan_file()
        plan = self.fs.load_plan()
        fast, slow = self.fs.shard_plan(plan, factor=1.0), self.fs.shard_plan(plan, factor=3.0)
        self.assertLessEqual(len(fast), len(slow))                       # a slower runner never needs fewer shards
        self.assertFalse(any(r["over_cap"] for r in fast))
        m = self.fs.SHARD_MODEL
        for r in slow:
            e = r["est_min_by_factor"]
            self.assertLessEqual(e["1"], e["2"])
            self.assertLessEqual(e["2"], e["3"])
        # the compute scales exactly with the factor, `job_fixed_s` does not
        cell = next(c for c in plan["cells"] if c["id"] == "5m-metals")
        a = self.fs.shard_seconds(1, cell, "ict", "XAUUSD", [1.0, 1.0], 27, 1.0)
        b = self.fs.shard_seconds(1, cell, "ict", "XAUUSD", [1.0, 1.0], 27, 2.0)
        self.assertAlmostEqual(b - m["job_fixed_s"], 2 * (a - m["job_fixed_s"]), places=6)
        # more bars, more value sets and more groups never cost less
        small = dict(cell, timeframe="15m")
        self.assertLess(self.fs.shard_seconds(1, small, "ict", "XAUUSD", [1.0], 5, 1.0),
                        self.fs.shard_seconds(1, cell, "ict", "XAUUSD", [1.0], 5, 1.0))
        self.assertLess(self.fs.shard_seconds(1, cell, "ict", "XAUUSD", [1.0], 5, 1.0),
                        self.fs.shard_seconds(1, cell, "ict", "XAUUSD", [1.0], 27, 1.0))
        self.assertLess(self.fs.shard_seconds(1, cell, "wyckoff", "XAUUSD", [1.0], 5, 1.0),
                        self.fs.shard_seconds(1, cell, "wyckoff", "XAUUSD", [1.0, 1.0, 1.0], 5, 1.0))

    def test_the_sets_of_every_wave_are_partitioned_exactly_by_the_slices(self):
        self._plan_file()
        plan = self.fs.load_plan()
        rows = self.fs.shard_plan(plan)
        grids, _ = self.fs.load_grids()
        for cell in plan["cells"]:
            for method in self.fs.METHODS:
                g = grids[method].runnable()
                want = {1: 1 + sum(len(x["candidates"]) for x in g.groups),
                        2: self.fs.wave2_set_count(method, cell["n_folds"])}
                for sym in cell["symbols"]:
                    for wave in (1, 2):
                        rs = [r for r in rows if (r["cell"], r["method"], r["symbol"], r["wave"]) == (cell["id"], method, sym, wave)]
                        self.assertEqual(sum(r["sets"] for r in rs), want[wave], (cell["id"], method, sym, wave))
                        self.assertTrue(all(r["sets"] >= 1 and r["groups"] >= 1 for r in rs))

    def test_wave2_group_estimate_is_capped_and_never_below_one(self):
        for method in ("ict", "wyckoff"):
            cap = self.fs.SHARD_MODEL["max_groups"][method]
            prev = 0
            for k in (1, 2, 5, 17, 99, 400):
                g = self.fs.wave2_groups_in_slice(method, k)
                self.assertTrue(1 <= g <= min(k, cap))
                self.assertGreaterEqual(g, prev)
                prev = g
        self.assertEqual(self.fs.wave2_groups_in_slice("ict", 400), 2)       # ICT has only B-POOL to vary

    def test_the_model_says_which_constants_are_measured_and_which_assumed(self):
        m = self.fs.SHARD_MODEL
        listed = list(m["measured"]) + list(m["assumed"])
        self.assertEqual(len(listed), len(set(listed)))                   # no constant is both
        self.assertEqual(set(listed), set(m) - {"measured", "assumed"})   # and none is unlabelled
        self.assertIn("docs/audits/2026-10-01-shard-calibration.md", self.fs.SHARD_MODEL_LABEL)
        self.assertTrue(os.path.exists(os.path.join(ROOT, "docs", "audits", "2026-10-01-shard-calibration.md")))
        self._plan_file()
        text = self.fs.format_shard_table(self.fs.shard_plan(self.fs.load_plan()))
        self.assertIn("MEASURED", text)
        self.assertIn("ASSUMED", text)

    def test_the_real_declared_plan_lays_out_without_an_over_cap_shard(self):
        """The REAL committed cells file + grids + the committed DEV_BARS rows (no fixture cells): a DEV_BARS or constant
        edit cannot shift the layout silently. Pins the shard count at the layout factor 3.0 (hosted-runner benchmark of 2026-10-01)."""
        arch = os.path.join(ROOT, "docs", "architecture")
        first = _REAL_FIRST_BAR
        with mock.patch.dict(os.environ, {"BT_HISTORY_ROOT": os.path.join(ROOT, "data", "history", "ftmo")}):
            plan = self.fs.build_plan(arch, first_bar=first)
        self.assertEqual([c["id"] for c in plan["cells"]], ["1m-metals", "1m-indices", "5m-metals"])
        for c in plan["cells"]:
            for sym in c["symbols"]:
                self.assertIn(sym, _REAL_DEV_BARS[c["timeframe"]])
        rows = self.fs.shard_plan(plan, arch)
        self.assertEqual(self.fs.SHARD_MODEL["layout_factor"], 3.0)
        self.assertFalse([r["name"] for r in rows if r["over_cap"]])
        self.assertLessEqual(max(r["est_min"] for r in rows), self.fs.SHARD_MODEL["budget_s"] / 60)
        self.assertEqual(len(rows), 284)
        waves = (sum(1 for r in rows if r["wave"] == 1), sum(1 for r in rows if r["wave"] == 2))
        self.assertEqual(waves, (62, 222))
        self.assertLessEqual(max(waves), 256, "a GitHub Actions matrix may hold at most 256 jobs")
        # the declared later starts are laid out from the MEASURED bars of the cut series (warm-up included), not from
        # DEV_BARS scaled by time: the real cells file, no monkeypatch
        by_cell = {c["id"]: c for c in plan["cells"]}
        self.assertEqual({r["bars"] for r in rows if r["cell"] == "1m-indices" and r["symbol"] == "US30"}, {1418201})
        self.assertEqual({r["bars"] for r in rows if r["cell"] == "5m-metals" and r["symbol"] == "XAUUSD"}, {645119})
        self.assertEqual({r["bars"] for r in rows if r["cell"] == "1m-metals" and r["symbol"] == "XAUUSD"},
                         {_REAL_DEV_BARS["1m"]["XAUUSD"]})
        self.assertIsNotNone(by_cell["1m-indices"]["dev_start_override"])

    def test_the_wave2_tripwire_fires_only_beyond_ten_percent(self):
        w = self.fs.wave2_size_warning
        self.assertIsNone(w("1m-metals", "ict", "XAUUSD", 10, 110, 102))
        self.assertIsNone(w("1m-metals", "ict", "XAUUSD", 10, 112, 102))        # +9.8 %
        msg = w("1m-metals", "ict", "XAUUSD", 10, 204, 102)                      # twice the estimate
        self.assertTrue(msg.startswith("WARNING:"))
        self.assertIn("--slice I/20", msg)
        self.assertIn("1m-metals/ict/XAUUSD", msg)

    def test_the_runner_benchmark_status_never_refuses_and_says_what_is_missing(self):
        fs = self.fs
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        with mock.patch.object(fs, "RUNNER_BENCHMARK_PATH", os.path.join(tmp, "none.json")):
            st = fs.runner_benchmark_status()
        self.assertFalse(st["recorded"])
        self.assertIsNone(st["sha256"])
        self.assertIn("ASSUMPTION", st["note"])
        path = os.path.join(tmp, "bench.json")
        # the layout factor is DERIVED from the measured per-job factors: worst job rounded up to 0.25
        for worst, ok in ((fs.SHARD_MODEL["layout_factor"] - 0.1, True), (1.2, False)):
            json.dump({"all_ok": True, "layout_factor": 2.25,
                       "factors": [{"job": "a", "status": "OK", "factor": 1.5}, {"job": "b", "status": "OK", "factor": worst}]},
                      open(path, "w"))
            with mock.patch.object(fs, "RUNNER_BENCHMARK_PATH", path):
                st = fs.runner_benchmark_status()
            self.assertEqual(st["recorded"], ok)
            self.assertEqual(len(st["sha256"]), 64)

    def test_the_benchmark_workflow_is_manual_read_only_and_secret_free(self):
        text = open(os.path.join(ROOT, ".github", "workflows", "fund-search-benchmark.yml")).read()
        for needle in ("workflow_dispatch:", "contents: read", "runner_benchmark.py", "RUNNER_TEMP", "upload-artifact"):
            self.assertIn(needle, text)
        for bad in ("secrets.", "\n  push:", "pull_request", "contents: write"):
            self.assertNotIn(bad, text)
        self.assertTrue(os.path.exists(os.path.join(ROOT, "scripts", "research", "runner_benchmark.py")))

    def test_every_symbol_of_every_declared_cell_has_a_dev_bars_row(self):
        """No synthetic rows: the committed cells file against the committed DEV_BARS table."""
        cells = self.fs.load_cells_file(os.path.join(ROOT, "docs", "architecture"))[0]["cells"]
        self.assertTrue(cells)
        for c in cells:
            for sym in c["symbols"]:
                self.assertIn(sym, _REAL_DEV_BARS[c["timeframe"]], f"DEV_BARS lacks {sym} {c['timeframe']} (cell {c['id']})")

    def test_a_series_without_a_dev_bars_row_is_refused_by_name(self):
        cell = {"timeframe": "15m", "dev_start_override": None}
        with self.assertRaises(SystemExit) as cm:
            self.fs.cell_bars(cell, "NOSUCH")
        self.assertIn("DEV_BARS has no row for NOSUCH 15m", str(cm.exception))

    def test_summary_reports_every_factor_with_the_same_layout(self):
        self._plan_file()
        plan = self.fs.load_plan()
        rows = self.fs.shard_plan(plan)
        summ = self.fs.shard_summary(plan, rows)
        self.assertEqual(list(summ), ["1", "2", "3"])
        self.assertEqual({v["shards"] for v in summ.values()}, {len(rows)})
        self.assertLess(summ["1"]["runner_hours"], summ["2"]["runner_hours"])
        self.assertLess(summ["2"]["runner_hours"], summ["3"]["runner_hours"])
        self.assertLessEqual(summ["3"]["longest_shard_min"], self.fs.SHARD_MODEL["budget_s"] / 60)
        self.assertGreater(summ["3"]["critical_path_min"], summ["3"]["longest_wave2_min"])
        self.assertAlmostEqual(sum(v["runner_hours"] for v in summ["2"]["by_cell_method"].values()),
                               summ["2"]["runner_hours"], delta=0.8)       # per-(cell, method) rounding to 0.1 h

    def test_the_slice_argument_is_validated(self):
        self.assertEqual(self.fs.parse_slice("2/5"), (2, 5))
        for bad in ("5/5", "-1/3", "a/b", "1", "0/0", "1/2/3"):
            with self.assertRaises(SystemExit):
                self.fs.parse_slice(bad)

    def test_list_scan_shards_prints_valid_json(self):
        self._plan_file()
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {}), redirect_stdout(buf):
            self.fs.main(["list-scan-shards", "--wave", "2"])
        rows = json.loads(buf.getvalue())
        self.assertTrue(rows and all(r["wave"] == 2 for r in rows))
        for r in rows:                                    # a CI matrix entry: scalars only (no nested object)
            self.assertFalse(any(isinstance(v, (dict, list)) for v in r.values()), r)
            self.assertLessEqual(r["est_min_f3"], self.fs.SHARD_MODEL["budget_s"] / 60)
            self.assertLessEqual(r["est_min_f1"], r["est_min_f2"])
            self.assertLessEqual(r["est_min_f2"], r["est_min_f3"])
            self.assertFalse(r["over_cap"])

    def test_the_workflow_uses_these_shards_within_the_cap(self):
        text = open(os.path.join(ROOT, ".github", "workflows", "fund-search.yml")).read()
        for needle in ("list-scan-shards --wave 1", "list-scan-shards --wave 2", "--scan-cache", "fund-scan-",
                       "BT_HISTORY_ROOT", "fetch-depth: 0", "workflow_dispatch:", "contents: read",
                       "--require-complete-scan-cache", "overwrite: true", "error-unmatch"):
            self.assertIn(needle, text)
        for ln in text.splitlines():
            if ln.strip().startswith("timeout-minutes:"):
                self.assertLessEqual(int(ln.split(":")[1]), 355)
        self.assertNotIn("\n  push:", text)
        self.assertNotIn("pull_request", text)


def _write_slice_root(out_root, sym, tf, n_bars, end="2024-03-01T00:00:00Z"):
    """A temp history root holding `sym` on every timeframe, cut to the span of the last `n_bars` bars of `tf` before `end`."""
    import history_store as HS
    ftmo = os.path.join(ROOT, "data", "history", "ftmo")
    doc, _ = HS.read_doc(sym, tf, root=ftmo)
    cs = [c for c in doc["candles"] if c["time"] < end][-n_bars:]
    start, stop = cs[0]["time"], cs[-1]["time"]
    os.makedirs(out_root, exist_ok=True)
    for t in ("1m", "5m", "15m", "30m", "1H", "4H", "1D", "1W"):
        d, _ = HS.read_doc(sym, t, root=ftmo)
        if d is None:
            continue
        sub = dict((k, v) for k, v in d.items() if k not in ("candles", "years"))
        sub["candles"] = [c for c in d["candles"] if start <= c["time"] <= stop]
        with open(os.path.join(out_root, f"ohlcv.{sym}.{t}.json"), "w", encoding="utf-8") as fh:
            json.dump(sub, fh)
    return start, stop


class ShardGroupModel(unittest.TestCase):
    """The data-free detection-group keys the shard model uses (`wave1_group_info`) are what `scan_many` REALLY groups the
    wave-1 value sets by: real scans of the harness's own engine over a real 7,000-bar 5m slice, the groups
    captured from scan_many's own `_assemble` call. If this fails, the model's per-group / per-extra-set split is wrong."""

    TF, SYM = "5m", "US500"

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(os.path.join(ROOT, "data", "history", "ftmo", f"ohlcv.{cls.SYM}.{cls.TF}")):
            raise unittest.SkipTest("data/history/ftmo is not present")
        cls.tmp = tempfile.mkdtemp(prefix="shard-groups-")
        cls.env = os.environ.get("BT_HISTORY_ROOT")
        hist = os.path.join(cls.tmp, "hist")
        cls.start, _stop = _write_slice_root(hist, cls.SYM, cls.TF, 7000)
        os.environ["BT_HISTORY_ROOT"] = hist
        cls.fs = _fs()
        cls.grids, _ = cls.fs.load_grids()
        cls.cell = {"id": "t", "development_start": "2012-05-03T05:38:00Z", "timeframe": cls.TF, "symbols": [cls.SYM],
                    "asset_class": "indices", "n_folds": 2}

    @classmethod
    def tearDownClass(cls):
        if cls.env is None:
            os.environ.pop("BT_HISTORY_ROOT", None)
        else:
            os.environ["BT_HISTORY_ROOT"] = cls.env
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _real_groups(self, method):
        fs = self.fs
        grid = self.grids[method].runnable()
        eng = fs.BtEngine(grid, fs.METHODS[method], self.TF, [self.SYM], workers=1)
        sets = fs.wave1_values(eng, grid, self.cell)
        seen = []
        real = fs.SM._assemble

        def spy(bt, sym, tf, meth, src, S, groups, results, n_overlays):
            seen.append([list(m) for m in groups.values()])
            return real(bt, sym, tf, meth, src, S, groups, results, n_overlays)

        with mock.patch.object(fs.SM, "_assemble", spy):
            eng.scan_symbol(self.SYM, sets)
        self.assertEqual(len(seen), 1)
        return grid, len(sets), seen[0]

    def _model_groups(self, grid, method):
        info = self.fs.wave1_group_info(grid, method, self.cell, self.SYM)
        by = {}
        for i, (gid, _win) in enumerate(info):
            by.setdefault(gid, []).append(i)
        return info, sorted(by.values())

    def test_ict_wave1_groups_match_scan_many(self):
        grid, n, real = self._real_groups("ict")
        info, model = self._model_groups(grid, "ict")
        self.assertEqual(len(info), n)
        self.assertEqual(sorted(real), model)
        self.assertEqual(len(model), 2)                    # B-POOL off / on: the only analysis-affecting item of the grid
        self.assertEqual(sorted(len(g) for g in model), [1, n - 1])

    def test_wyckoff_wave1_groups_and_windows_match_scan_many(self):
        grid, n, real = self._real_groups("wyckoff")
        info, model = self._model_groups(grid, "wyckoff")
        self.assertEqual(len(info), n)
        self.assertEqual(sorted(real), model)
        self.assertGreater(len(model), 5)                  # W6 / W4a / W-TW each open their own detection group
        wins = {win for _gid, win in info}
        self.assertEqual(wins, {300, 600})                 # the W6 = 600 window is told apart (it costs more)


class _ScanCacheBase:
    """Shared fixture of the scan-cache tests: the REAL BtEngine over real 5m slices (`SYMS`), a reference cache built
    the way the workflow builds it (wave 1 in two slices per symbol, then wave 2), and a cache-less reference run.

    The slice is far too short for the selection to choose reliably, so `select_values` is wrapped: it still runs for
    real (and reads the held wave-1 trades) but its answer is forced to "the last candidate of every factor".
      FORCE = "always": forced from the very first (empty-trade) wave-1 probe on, so the forced combined set is ALSO a
        wave-1 set (5 + 1 sets in wave 1).
      FORCE = "held": forced only once the baseline holds training trades, i.e. only after wave 1 is held -- like a real
        selection, whose combined set is NOT a wave-1 set (wave 1 = exactly baseline + candidates)."""

    SYMS, TF, CELL = ("US500",), "5m", "t-indices"
    SYM = SYMS[0]
    FORCE = "always"

    @classmethod
    def setUpClass(cls):
        if not all(os.path.isdir(os.path.join(ROOT, "data", "history", "ftmo", f"ohlcv.{s}.{cls.TF}")) for s in cls.SYMS):
            raise unittest.SkipTest("data/history/ftmo is not present")
        cls.tmp = tempfile.mkdtemp(prefix="scan-cache-")
        cls.env = os.environ.get("BT_HISTORY_ROOT")
        hist = os.path.join(cls.tmp, "hist")
        starts = [_write_slice_root(hist, s, cls.TF, 7000)[0] for s in cls.SYMS]
        cls.start = min(starts, key=FS.ts)
        os.environ["BT_HISTORY_ROOT"] = hist
        cls.fs = _fs()
        real = json.load(open(os.path.join(ROOT, "docs", "architecture", "v-grid-ict.json")))
        keep = ("B-POOL", "B-PD", "B6", "B-MGMT")
        cls.grid = FS.Grid({"method": "ICT", "items": [i for i in real["items"] if i["id"] in keep]})
        a = FS.ts(cls.start)
        d = datetime.timedelta(days=8)
        cls.folds = [{"index": k, "train_start": cls.start, "test_start": FS.iso(a + d * (k + 1)),
                      "test_end": FS.iso(a + d * (k + 2))} for k in range(2)]
        cls.cell = {"id": cls.CELL, "timeframe": cls.TF, "symbols": list(cls.SYMS), "development_start": cls.start,
                    "asset_class": "indices", "n_folds": 2}
        cls.plan = {"plan_hash": "p" * 16, "cells": [cls.cell], "cell_count": 1,
                    "candidates": [{"id": "ict-" + cls.CELL, "method": "ict", "runner_method": "ICT", "cell": cls.CELL,
                                    "timeframe": cls.TF, "symbols": list(cls.SYMS)}],
                    "embargo": {"h_multiple": 2}, "grids": {"ict": {"sha256": "g" * 8}},
                    "cells_file": {"sha256": "c" * 8, "warmup_days": 14},
                    "cost_profile": cls.fs.COST_PROFILE, "cost_profile_pin": {},
                    "family": {"size": 6, "alpha": 0.10, "floor_confidence": 1 - 0.10 / 6}}
        try:
            with cls._patched():
                cls.plain_engine = cls._engine()
                cls.plain = cls.fs.evaluate_with_engine(cls.plain_engine, cls.grid, cls.cell, 205)
                # the reference cache, built the way the workflow does: wave 1 in two slices, then wave 2
                cls.cache = os.path.join(cls.tmp, "cache")
                w1 = [(cls._cmd_scan(1, cls.cache, "0/2", symbol=sym), cls._cmd_scan(1, cls.cache, "1/2", symbol=sym))
                      for sym in cls.SYMS]
                cls.w1_files = set(os.listdir(cls.cache))
                cls.w1 = w1[0]
                cls.n1 = w1[0][0]["wave_sets"]
                cls.w2 = {"written": sum(cls._cmd_scan(2, cls.cache, "0/1", cache=[cls.cache], symbol=sym)["written"]
                                         for sym in cls.SYMS)}
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        if cls.env is None:
            os.environ.pop("BT_HISTORY_ROOT", None)
        else:
            os.environ["BT_HISTORY_ROOT"] = cls.env
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    @contextlib.contextmanager
    def _patched(cls):
        real_select = FS.select_values

        def forced(grid, train_trades_for):
            _chosen, scores = real_select(grid, train_trades_for)     # the real selection runs (and reads held trades)
            if cls.FORCE == "held" and not scores[0]["n_train"]:
                return _chosen, scores                                # nothing held yet (a wave-1 probe): real answer
            chosen = grid.baseline()
            for g in grid.groups:
                chosen.update(g["candidates"][-1])
            return chosen, scores

        with mock.patch.object(FS, "make_folds", side_effect=lambda *a, **k: [dict(f) for f in cls.folds]), \
                mock.patch.object(cls.fs, "scoped_dirty", lambda root=None: []), \
                mock.patch.object(FS, "MIN_TRAIN_TRADES", 1), mock.patch.object(FS, "select_values", forced):
            yield

    @classmethod
    def _engine(cls):
        return cls.fs.BtEngine(cls.grid, "ICT", cls.TF, list(cls.SYMS), workers=1)

    @classmethod
    def _cmd_scan(cls, wave, out, slice_spec="0/1", cache=(), symbol=None):
        with mock.patch.object(cls.fs, "load_plan", return_value=cls.plan), \
                mock.patch.object(cls.fs, "require_declaration", return_value={}), \
                mock.patch.object(cls.fs, "check_drift", return_value=[]), \
                mock.patch.object(cls.fs, "load_grids", return_value=({"ict": cls.grid, "wyckoff": cls.grid}, {})), \
                redirect_stdout(io.StringIO()):
            return cls.fs.cmd_scan(cls.CELL, symbol or cls.SYM, "ict", out, workers=1, wave=wave, slice_spec=slice_spec,
                                   scan_cache_dirs=list(cache))

    def setUp(self):
        self.out = os.path.join(tempfile.mkdtemp(prefix="scan-out-"), "cache")
        self.addCleanup(shutil.rmtree, os.path.dirname(self.out), ignore_errors=True)
        shutil.copytree(self.cache, self.out)                    # a private, mutable copy of the reference cache
        p = self._patched()
        p.__enter__()
        self.addCleanup(p.__exit__, None, None, None)

    def _load(self, stamp=None, directory=None, engine=None):
        return (engine or self._engine()).load_scan_cache(stamp or self.fs.scan_cache_stamp(self.plan),
                                                          [directory or self.out], self.CELL)

    def _first_with_trades(self):
        for name in sorted(os.listdir(self.out)):
            f = os.path.join(self.out, name)
            e = json.load(open(f))
            if e["trades"]:
                return f, e
        self.fail("the slice must produce trades for this check to bite")


class ScanCache(_ScanCacheBase, unittest.TestCase):
    """One symbol, FORCE = "always": refusal matrix, determinism, partial caches, slices."""

    def test_the_reference_cache_is_complete_and_wave_2_is_not_vacuous(self):
        # 4 items = baseline + 4 candidates, plus the forced combined set the wave-1 probe also asks for (see the class docstring)
        self.assertEqual(self.n1, 6)
        self.assertEqual(self.w1[0]["written"] + self.w1[1]["written"], self.n1)
        self.assertGreater(self.w2["written"], 0)
        self.assertEqual(len(self.w1_files), self.n1)
        self.assertEqual(len(os.listdir(self.cache)), self.n1 + self.w2["written"])

    def test_cache_run_is_byte_identical_to_no_cache_run(self):
        cached = self._engine()
        full, n = self._load(engine=cached)
        self.assertEqual(n, self.n1 + self.w2["written"])
        with mock.patch.object(self.fs.SM, "scan_many", side_effect=AssertionError("scanned on demand")), \
                mock.patch.object(cached.bt, "scan", side_effect=AssertionError("scanned on demand")):
            res = self.fs.evaluate_with_engine(cached, self.grid, self.cell, 205)
        self.assertEqual(json.dumps(res, sort_keys=True, default=repr), json.dumps(self.plain, sort_keys=True, default=repr))
        self.assertEqual(res["runs_evaluated"], self.plain["runs_evaluated"])
        self.assertGreater(res["runs_evaluated"], self.n1)                 # wave-2 sets were scored too
        self.assertEqual(set(cached._done), set(self.plain_engine._done))
        for k, v in self.plain_engine._done.items():                       # trades: types, key order, float text
            self.assertEqual(repr(cached._done[k]), repr(v))
            self.assertEqual(cached._admission[k], self.plain_engine._admission[k])
            self.assertEqual(cached._edge[k], self.plain_engine._edge[k])

    def test_entries_are_deterministic_bytes(self):
        other = os.path.join(os.path.dirname(self.out), "again")
        self._cmd_scan(1, other, "0/1")
        self.assertEqual(sorted(os.listdir(other)), sorted(self.w1_files))
        for f in self.w1_files:
            self.assertEqual(open(os.path.join(self.cache, f), "rb").read(), open(os.path.join(other, f), "rb").read())

    def test_a_rerun_of_a_shard_does_not_rescan(self):
        with mock.patch.object(self.fs.SM, "scan_many", side_effect=AssertionError("rescanned")):
            again = self._cmd_scan(1, self.out, "0/1")
        self.assertEqual((again["written"], again["skipped"]), (0, self.n1))

    def test_a_partial_cache_scans_only_what_is_missing_and_changes_nothing(self):
        for f in sorted(os.listdir(self.out))[:3]:
            os.remove(os.path.join(self.out, f))
        eng = self._engine()
        self._load(engine=eng)
        res = self.fs.evaluate_with_engine(eng, self.grid, self.cell, 205)
        self.assertEqual(json.dumps(res, sort_keys=True, default=repr), json.dumps(self.plain, sort_keys=True, default=repr))

    def test_a_value_set_cached_for_only_some_symbols_is_scanned_for_the_rest(self):
        """A value set with only ONE of the engine's symbols cached stays partial: prefetch scans just the missing symbol
        and the pooled raw list is in engine symbol order, exactly as if both had been scanned."""
        eng = object.__new__(self.fs.BtEngine)
        eng.grid, eng.method, eng.tf, eng.symbols, eng.workers, eng.bt = self.grid, "ICT", self.TF, ["AAA", "BBB"], 1, None
        eng._raw, eng._done, eng._part = {}, {}, {}
        v = self.grid.baseline()
        key = FS.CountingSource._key(v)
        eng._part[key] = {"BBB": [{"symbol": "BBB", "n": 1}]}
        calls = []

        def fake_scan_many(bt, sym, tf, method, overlays, workers=1):
            calls.append((sym, len(overlays)))
            return [{"trades": {"ICT": [{"symbol": sym, "n": 0}]}} for _ in overlays]

        with mock.patch.object(self.fs.SM, "scan_many", side_effect=fake_scan_many):
            eng.prefetch([v])
        self.assertEqual(calls, [("AAA", 1)])                      # BBB came from the cache
        self.assertEqual(eng._raw[key], [{"symbol": "AAA", "n": 0}, {"symbol": "BBB", "n": 1}])
        self.assertNotIn(key, eng._part)

    def test_a_different_code_version_is_refused(self):
        stamp = self.fs.scan_cache_stamp(self.plan)
        stamp["code"]["scripts/fund-search.py"] = {"git_sha": "0" * 40, "dirty": False}
        with self.assertRaises(self.fs.ScanCacheRefused) as cm:
            self._load(stamp)
        self.assertIn("code.scripts/fund-search.py", str(cm.exception))
        stamp = self.fs.scan_cache_stamp(self.plan)
        stamp["code_sha256"]["scripts/fund_stats.py"] = "f" * 64
        with self.assertRaises(self.fs.ScanCacheRefused):
            self._load(stamp)

    def test_a_cache_from_other_code_config_or_data_trees_is_refused(self):
        stamp = self.fs.scan_cache_stamp(self.plan)
        self.assertEqual(set(stamp["repo_trees"]), set(self.fs.PINNED_TREES))
        self.assertTrue(stamp["repo_head"])
        self.assertEqual(stamp["scoped_dirty"], [])
        self._load(stamp)                                                       # non-vacuous: the unmutated stamp loads
        for key, bad in (("repo_head", "0" * 40),
                         ("repo_trees", dict(stamp["repo_trees"], **{"docs/architecture": "1" * 40})),
                         ("repo_trees", dict(stamp["repo_trees"], **{"data/history/ftmo": "2" * 40})),
                         ("repo_trees", dict(stamp["repo_trees"], scripts="3" * 40)),
                         ("scoped_dirty", ["M scripts/ict-scan.py"])):
            with self.subTest(key=key, bad=str(bad)[:40]):
                with self.assertRaises(self.fs.ScanCacheRefused) as cm:
                    self._load(dict(stamp, **{key: bad}))
                self.assertIn(key, str(cm.exception))

    def test_a_different_plan_or_evaluation_setting_is_refused(self):
        stamp = self.fs.scan_cache_stamp(self.plan)
        stamp["plan_hash"] = "q" * 16
        with self.assertRaises(self.fs.ScanCacheRefused) as cm:
            self._load(stamp)
        self.assertIn("plan_hash", str(cm.exception))
        stamp = self.fs.scan_cache_stamp(self.plan)
        stamp["evaluation_config"]["embargo"] = {"h_multiple": 3}
        with self.assertRaises(self.fs.ScanCacheRefused) as cm:
            self._load(stamp)
        self.assertIn("evaluation_config", str(cm.exception))

    def test_a_foreign_entry_of_another_cell_still_refuses(self):
        """A cache directory is homogeneous or it is wrong: an entry of another cell made by other code still refuses."""
        f = os.path.join(self.out, sorted(os.listdir(self.out))[0])
        e = json.load(open(f))
        e["scope"]["cell"] = "some-other-cell"
        e["stamp"]["plan_hash"] = "z" * 16
        e["key"] = self.fs.scan_cache_key(e["stamp"], e["scope"])
        json.dump(e, open(os.path.join(self.out, e["key"] + ".json"), "w"))
        with self.assertRaises(self.fs.ScanCacheRefused):
            self._load()

    def test_an_entry_of_another_cell_made_by_the_same_code_is_ignored_not_used(self):
        f = os.path.join(self.out, sorted(os.listdir(self.out))[0])
        e = json.load(open(f))
        e["scope"]["cell"] = "some-other-cell"
        e["key"] = self.fs.scan_cache_key(e["stamp"], e["scope"])
        json.dump(e, open(os.path.join(self.out, e["key"] + ".json"), "w"))
        os.remove(f)
        full, n = self._load()
        self.assertEqual(n, self.n1 + self.w2["written"] - 1)          # the moved entry was not loaded for this cell

    def test_history_that_differs_from_what_the_shard_scanned_is_refused(self):
        eng = self._engine()
        eng._series[self.SYM] = dict(eng._series[self.SYM], bars=eng._series[self.SYM]["bars"] + 1)
        with self.assertRaises(self.fs.ScanCacheRefused) as cm:
            self._load(engine=eng)
        self.assertIn("history differs", str(cm.exception))
        eng = self._engine()                                     # same bars, first and last bar; one bar's CONTENT differs
        eng._series[self.SYM] = dict(eng._series[self.SYM], sha256="0" * 64)
        with self.assertRaises(self.fs.ScanCacheRefused):
            self._load(engine=eng)

    def test_an_edited_file_is_refused(self):
        f, e = self._first_with_trades()
        e["trades"][0]["R"] = 12345.0                                  # edit a trade, leave every hash alone
        json.dump(e, open(f, "w"))
        with self.assertRaises(self.fs.ScanCacheRefused) as cm:
            self._load()
        self.assertIn("sha256", str(cm.exception))

    def test_dropping_a_trade_and_fixing_the_count_is_still_refused(self):
        f, e = self._first_with_trades()
        e["trades"].pop()
        e["n_trades"] = len(e["trades"])
        json.dump(e, open(f, "w"))
        with self.assertRaises(self.fs.ScanCacheRefused):
            self._load()

    def test_a_torn_or_partial_file_is_refused(self):
        f = os.path.join(self.out, sorted(os.listdir(self.out))[0])
        raw = open(f, "rb").read()
        open(f, "wb").write(raw[: len(raw) // 2])                      # cut mid-file
        with self.assertRaises(self.fs.ScanCacheRefused) as cm:
            self._load()
        self.assertIn("partial", str(cm.exception))
        open(f, "w").write(json.dumps({"format": 1, "key": "x"}))      # valid JSON, structurally incomplete
        with self.assertRaises(self.fs.ScanCacheRefused) as cm:
            self._load()
        self.assertIn("not a complete entry", str(cm.exception))

    def test_a_renamed_file_is_refused_and_a_leftover_tmp_is_never_read(self):
        f = os.path.join(self.out, sorted(os.listdir(self.out))[0])
        open(os.path.join(self.out, "half-written.json.tmp"), "w").write("{")      # interrupted atomic write: ignored
        self._load()
        os.rename(f, os.path.join(self.out, "renamed.json"))
        with self.assertRaises(self.fs.ScanCacheRefused) as cm:
            self._load()
        self.assertIn("renamed", str(cm.exception))

    def test_a_missing_cache_directory_is_refused(self):
        with self.assertRaises(self.fs.ScanCacheRefused):
            self._load(directory=os.path.join(self.out, "nope"))

    def test_wave_2_refuses_an_incomplete_wave_1_and_a_missing_cache(self):
        os.remove(os.path.join(self.out, sorted(self.w1_files)[0]))
        with self.assertRaises(SystemExit) as cm:
            self._cmd_scan(2, os.path.join(os.path.dirname(self.out), "w2"), "0/1", cache=[self.out])
        self.assertIn("incomplete", str(cm.exception))
        with self.assertRaises(SystemExit) as cm:
            self._cmd_scan(2, os.path.join(os.path.dirname(self.out), "w2"), "0/1")
        self.assertIn("--scan-cache", str(cm.exception))

    def test_wave_2_slices_partition_the_wave_and_together_equal_the_unsliced_wave(self):
        a, b = os.path.join(os.path.dirname(self.out), "s0"), os.path.join(os.path.dirname(self.out), "s1")
        r0 = self._cmd_scan(2, a, "0/2", cache=[self.out])          # self.out ALSO holds every wave-2 entry: must not matter
        r1 = self._cmd_scan(2, b, "1/2", cache=[self.out])
        self.assertEqual(r0["wave_sets"], r1["wave_sets"])
        self.assertEqual(r0["slice_sets"] + r1["slice_sets"], r0["wave_sets"])
        got = set(os.listdir(a)) | set(os.listdir(b))
        self.assertEqual(got, set(os.listdir(self.cache)) - self.w1_files)
        self.assertFalse(set(os.listdir(a)) & set(os.listdir(b)))

    def test_scan_refuses_an_output_inside_the_checkout_and_a_symbol_outside_the_cell(self):
        inside = os.path.join(ROOT, "scan-out-must-not-exist")
        with self.assertRaises(SystemExit) as cm:
            self._cmd_scan(1, inside, "0/1")
        self.assertIn("inside the checkout", str(cm.exception))
        self.assertFalse(os.path.exists(inside))
        with mock.patch.object(self.fs, "load_plan", return_value=self.plan), \
                mock.patch.object(self.fs, "require_declaration", return_value={}), \
                mock.patch.object(self.fs, "check_drift", return_value=[]):
            with self.assertRaises(SystemExit) as cm:
                self.fs.cmd_scan(self.CELL, "XAUUSD", "ict", self.out)
        self.assertIn("not a symbol of cell", str(cm.exception))

    def test_scan_refuses_without_the_ledger_declaration(self):
        other = os.path.join(os.path.dirname(self.out), "nodecl")
        with mock.patch.object(self.fs, "load_plan", return_value=self.plan), \
                mock.patch.object(self.fs, "require_declaration", side_effect=self.fs.LedgerDeclarationMissing("no")):
            with self.assertRaises(SystemExit):
                self.fs.cmd_scan(self.CELL, self.SYM, "ict", other)
        self.assertFalse(os.path.exists(other))

    def test_entries_that_do_not_survive_json_are_never_written(self):
        scope = self.fs.scan_cache_scope(self.CELL, "ICT", self.TF, self.SYM, "k", {"bars": 1})
        with self.assertRaises(self.fs.ScanCacheRefused):
            self.fs.write_scan_entry(os.path.join(os.path.dirname(self.out), "bad"), self.fs.scan_cache_stamp(self.plan),
                                     scope, [{"a": (1, 2)}])           # a tuple would come back a list
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(self.out), "bad")))



class ScanCacheHeldSelection(_ScanCacheBase, unittest.TestCase):
    """C1 regression: a fold's combined set that is NOT a wave-1 set (as with every real selection that changes >= 2
    factors) must not make `scan --wave 2` refuse a complete wave 1. The choice is forced only once trades are held."""

    FORCE = "held"

    def test_wave_1_is_exactly_baseline_plus_candidates_and_wave_2_has_the_combined_set(self):
        self.assertEqual(self.n1, 5)                          # 1 baseline + 4 single-factor candidates, no combined set
        self.assertGreater(self.w2["written"], 0, "the held-trades selection must have asked for wave-2 sets")

    def test_wave_2_is_accepted_on_a_complete_wave_1_and_refused_when_one_wave_1_set_is_absent(self):
        # the reference cache itself was built by an accepted wave-2 scan (setUpClass); now knock out one wave-1 entry
        w1_only = os.path.join(os.path.dirname(self.out), "w1only")
        os.makedirs(w1_only)
        for f in self.w1_files:
            shutil.copy(os.path.join(self.cache, f), w1_only)
        again = self._cmd_scan(2, os.path.join(os.path.dirname(self.out), "w2ok"), "0/1", cache=[w1_only])
        self.assertEqual(again["written"], self.w2["written"])
        os.remove(os.path.join(w1_only, sorted(self.w1_files)[0]))
        with self.assertRaises(SystemExit) as cm:
            self._cmd_scan(2, os.path.join(os.path.dirname(self.out), "w2bad"), "0/1", cache=[w1_only])
        self.assertIn("incomplete", str(cm.exception))

    def test_cache_run_equals_no_cache_run_and_the_record_provenance_is_stamped(self):
        cached = self._engine()
        self._load(engine=cached)
        cached.no_scan = True                                  # --require-complete-scan-cache
        with mock.patch.object(cached.bt, "scan", side_effect=AssertionError("scanned on demand")):
            res = self.fs.evaluate_with_engine(cached, self.grid, self.cell, 205)
        self.assertEqual(json.dumps(res, sort_keys=True, default=repr), json.dumps(self.plain, sort_keys=True, default=repr))
        info = cached.scan_cache_info
        self.assertEqual(info["entries"], self.n1 + self.w2["written"])
        self.assertEqual(len(info["sha256_of_sorted_entry_keys"]), 64)

    def test_require_complete_fails_loud_instead_of_scanning_on_demand(self):
        for f in sorted(os.listdir(self.out))[:2]:
            os.remove(os.path.join(self.out, f))
        eng = self._engine()
        self._load(engine=eng)
        eng.no_scan = True
        with self.assertRaises(self.fs.ScanCacheRefused) as cm:
            self.fs.evaluate_with_engine(eng, self.grid, self.cell, 205)
        self.assertIn("--require-complete-scan-cache", str(cm.exception))


class ScanCacheTwoSymbols(_ScanCacheBase, unittest.TestCase):
    """Two symbols end to end: per-symbol wave-1 shards, per-symbol wave-2 shards from the POOLED wave 1, then a
    cache-fed evaluation that equals the cache-less one (symbol pooling order included)."""

    SYMS = ("US500", "US30")
    SYM = SYMS[0]
    FORCE = "held"

    def test_each_symbol_has_its_own_entries_and_the_pooled_run_is_identical(self):
        entries = [json.load(open(os.path.join(self.cache, f))) for f in os.listdir(self.cache)]
        self.assertEqual({e["scope"]["symbol"] for e in entries}, set(self.SYMS))
        self.assertEqual({e["scope"]["series"]["sha256"] for e in entries if e["scope"]["symbol"] == "US500"}.__len__(), 1)
        cached = self._engine()
        self._load(engine=cached)
        cached.no_scan = True
        res = self.fs.evaluate_with_engine(cached, self.grid, self.cell, 205)
        self.assertEqual(json.dumps(res, sort_keys=True, default=repr), json.dumps(self.plain, sort_keys=True, default=repr))
        self.assertEqual(res["runs_evaluated"], self.plain["runs_evaluated"])
        for k, v in self.plain_engine._done.items():
            self.assertEqual(repr(cached._done[k]), repr(v))

    def test_wave_2_of_one_symbol_needs_the_other_symbols_wave_1(self):
        only_us500 = os.path.join(os.path.dirname(self.out), "only500")
        os.makedirs(only_us500)
        for f in self.w1_files:
            if json.load(open(os.path.join(self.cache, f)))["scope"]["symbol"] == "US500":
                shutil.copy(os.path.join(self.cache, f), only_us500)
        with self.assertRaises(SystemExit) as cm:
            self._cmd_scan(2, os.path.join(os.path.dirname(self.out), "w2"), "0/1", cache=[only_us500], symbol="US500")
        self.assertIn("incomplete", str(cm.exception))

class ScanCacheRunPlumbing(_Helpers):
    """`run --scan-cache` reaches `_evaluate_candidate` only when given (the 3-argument shape is otherwise unchanged)."""

    def setUp(self):
        super().setUp()
        self._plan_file()
        self.fs.cmd_declare()

    def test_without_the_flag_the_candidate_call_is_unchanged(self):
        seen = []
        with mock.patch.object(self.fs, "_evaluate_candidate",
                               side_effect=lambda *a, **k: seen.append((len(a), tuple(sorted(k)))) or self._fake_out(a[0], a[1])):
            self.fs.cmd_run("5m-metals", grid_dir=FIXTURES)
        self.assertEqual(set(seen), {(3, ())})

    def test_with_the_flag_the_directories_are_passed_through(self):
        seen = []
        with mock.patch.object(self.fs, "_evaluate_candidate",
                               side_effect=lambda *a, **k: seen.append(k) or self._fake_out(a[0], a[1])):
            self.fs.cmd_run("5m-metals", grid_dir=FIXTURES, scan_cache_dirs=["/x/y"])
        self.assertEqual([k["scan_cache_dirs"] for k in seen], [["/x/y"], ["/x/y"]])

    def test_require_complete_needs_a_cache_and_is_passed_through(self):
        with self.assertRaises(SystemExit):
            self.fs.cmd_run("5m-metals", grid_dir=FIXTURES, require_complete_scan_cache=True)
        seen = []
        with mock.patch.object(self.fs, "_evaluate_candidate",
                               side_effect=lambda *a, **k: seen.append(k) or self._fake_out(a[0], a[1])):
            self.fs.cmd_run("5m-metals", grid_dir=FIXTURES, scan_cache_dirs=["/x"], require_complete_scan_cache=True)
        self.assertTrue(all(k["require_complete_scan_cache"] for k in seen) and seen)

    def test_a_missing_candidate_is_a_clear_error_not_a_stopiteration(self):
        plan = self._plan_file()
        plan = dict(plan, candidates=[c for c in plan["candidates"] if c["cell"] != "5m-metals"])
        with mock.patch.object(self.fs, "load_plan", return_value=plan), \
                mock.patch.object(self.fs, "require_declaration", return_value={}), \
                mock.patch.object(self.fs, "check_drift", return_value=[]):
            with self.assertRaises(SystemExit) as cm:
                self.fs.cmd_scan("5m-metals", "XAUUSD", "ict", os.path.join(self.tmp, "o"))
        self.assertIn("no candidate", str(cm.exception))

    def test_the_cli_accepts_a_repeatable_scan_cache_flag(self):
        with mock.patch.object(self.fs, "cmd_run") as run, mock.patch.dict(os.environ, {}):
            self.fs.main(["run", "--cell", "5m-metals", "--workers", "1", "--scan-cache", "/a", "--scan-cache", "/b"])
        self.assertEqual(run.call_args.kwargs["scan_cache_dirs"], ["/a", "/b"])


class SymbolUniverse(_Tmp):
    """Owner 2026-10-01 (symbol universe + cell selection): per-cell symbol lists, three declared cells, N 87 / 48, parked
    symbols, late-starting symbols. The 13-symbol / 15m behaviour is exercised on the six-cell test fixture (FIXTURES)."""

    METALS4 = ["XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD"]
    INDICES13 = ["US500", "US30", "USTEC", "DE40", "FRA40", "UK100", "EU50", "JP225", "HK50", "AUS200", "US2000", "SPN35", "N25"]

    def _by_id(self, arch):
        return {c["id"]: c for c in self.fs.load_cells_file(arch)[0]["cells"]}

    PARKED = {"UK100", "EU50", "JP225", "HK50", "AUS200", "US2000", "SPN35", "N25"}

    def test_the_committed_cells_are_the_three_cells_with_the_decided_symbol_lists(self):
        cells = self._by_id(REAL_ARCH)
        self.assertEqual(list(cells), ["1m-metals", "1m-indices", "5m-metals"])
        self.assertEqual(cells["1m-metals"]["symbols"], ["XAUUSD", "XAGUSD"])                      # the 1m cells are unchanged
        self.assertEqual(cells["1m-indices"]["symbols"], ["US500", "US30", "USTEC", "DE40", "FRA40"])
        self.assertEqual(cells["5m-metals"]["symbols"], self.METALS4)
        every = {s for c in cells.values() for s in c["symbols"]}
        # FUND_SYMBOLS is a PINNED superset: the nine used symbols are in it, the eight parked ones are in it but in no cell
        self.assertTrue(every < set(self.fs.FUND_SYMBOLS))
        self.assertEqual(set(self.fs.FUND_SYMBOLS) - every, self.PARKED)
        # excluded: no pre-cutoff history (XCUUSD, DXY), cross-quoted metals, FX (no fx class), parked classes
        self.assertTrue({"XCUUSD", "DXY", "XAUEUR", "XAUAUD", "XAGEUR", "XAGAUD", "EURUSD", "USDJPY", "BTCUSD", "UKOIL",
                         "USOIL"}.isdisjoint(every))
        self.assertEqual({k: c["dev_start"] for k, c in cells.items()},                # availability rule, 2026-10-02
                         {"1m-metals": None, "1m-indices": "2020-03-01T00:00:00Z", "5m-metals": "2015-01-07T00:00:00Z"})
        self.assertEqual({c["asset_class"] for c in cells.values()}, {"metals", "indices"})

    def test_the_fixture_keeps_the_per_cell_symbol_lists_and_draws_on_the_whole_pinned_universe(self):
        real, fix = self._by_id(REAL_ARCH), self._by_id(FIXTURES)
        self.assertEqual({k: fix[k]["symbols"] for k in real}, {k: v["symbols"] for k, v in real.items()})
        self.assertEqual(fix["5m-indices"]["symbols"], self.INDICES13)
        self.assertEqual(fix["15m-metals"]["symbols"], self.METALS4)
        self.assertEqual({s for c in fix.values() for s in c["symbols"]}, set(self.fs.FUND_SYMBOLS))

    def test_parked_symbols_are_unused_but_stay_registered_and_nothing_in_the_plan_needs_them(self):
        """The eight symbols of the removed cells stay in the registry (research-only) and in FUND_SYMBOLS, no declared cell
        uses them, and the plan / readiness gate ignore them: missing data or specs for them is not a failure."""
        import instruments as I
        used = {s for c in self._by_id(REAL_ARCH).values() for s in c["symbols"]}
        for sy in self.PARKED:
            self.assertIn(sy, self.fs.FUND_SYMBOLS)
            self.assertIn(sy, I.analysis("cfd"))
            self.assertNotIn(sy, used)
        first = lambda s, t: (None if s in self.PARKED else
                              "2004-06-11T04:15:00Z" if s in ("XAUUSD", "XAGUSD") else "2017-12-27T23:00:00Z")
        rep = self.fs.data_readiness(self.fs.load_cells_file(REAL_ARCH)[0], first, lambda s: (s not in self.PARKED, "x"))
        self.assertTrue(rep["ready"] and rep["complete"])
        p = self.fs.build_plan(REAL_ARCH, first_bar=first)
        self.assertEqual(p["cell_count"], 3)
        self.assertFalse(self.PARKED & {s for c in p["cells"] for s in c["symbols"]})

    def test_every_new_symbol_is_a_research_only_registry_symbol_of_its_cells_class_and_never_orderable(self):
        import instruments as I
        for c in self.fs.load_cells_file(REAL_ARCH)[0]["cells"]:
            for sy in c["symbols"]:
                self.assertIn(sy, I.analysis("cfd"))
                self.assertEqual(I.display(sy)["asset_class"], c["asset_class"])
        orig = {"XAUUSD", "XAGUSD", "US500", "US30", "USTEC", "DE40", "FRA40"}
        new = set(self.fs.FUND_SYMBOLS) - orig - {"AUS200"}
        self.assertEqual(new, {"XPTUSD", "XPDUSD", "UK100", "EU50", "JP225", "HK50", "US2000", "SPN35", "N25"})
        self.assertEqual(set(I.research_only("cfd")), new)
        for sy in new:
            self.assertNotIn(sy, I.execution("cfd"))
            self.assertNotIn(sy, I.backtested("cfd"))
        # execution / backtested are exactly what they were before the 2026-10-01 symbol universe (f5eb338)
        self.assertEqual(I.execution("cfd"), ["XAUUSD", "XAGUSD", "US500", "US30", "USTEC", "DE40", "FRA40", "AUS200"])
        self.assertEqual(I.backtested("cfd"), ["XAUUSD"])
        # AUS200 was on the registry before (and is one of prop-search's 180 candidates): it is NOT research-only
        self.assertNotIn("AUS200", I.research_only("cfd"))

    def test_n_and_confidence_of_the_declared_cells_need_no_data(self):
        spec, path, sha = self.fs.load_cells_file(REAL_ARCH)
        line = self.fs.declared_n_line(spec, sha, REAL_ARCH)
        self.assertIn("declared cells: 3", line)
        self.assertIn("family = 6 candidate procedures (3 cells x 2 methods)", line)
        self.assertIn("floor confidence 1 - 0.1/6 = 0.983333", line)
        self.assertIn("ict 29 per cell, wyckoff 16 per cell", line)           # disclosed, not in the family
        self.assertNotIn("N 87", line)
        self.assertIn(sha, line)

    def test_a_symbol_outside_the_universe_or_of_another_class_or_an_fx_cell_is_refused(self):
        def cell(spec, cid):
            return next(c for c in spec["cells"] if c["id"] == cid)
        bad = [lambda s: cell(s, "5m-metals")["symbols"].append("XCUUSD"),        # no pre-cutoff history: dropped
               lambda s: cell(s, "5m-indices")["symbols"].append("DXY"),          # dropped
               lambda s: cell(s, "5m-metals")["symbols"].append("EURUSD"),        # no fx class
               lambda s: cell(s, "5m-metals")["symbols"].append("XAUEUR"),
               lambda s: cell(s, "5m-metals")["symbols"].append("UK100"),         # an index in a metals cell
               lambda s: cell(s, "5m-indices")["symbols"].append("XPTUSD"),       # a metal in an indices cell
               lambda s: cell(s, "5m-indices")["symbols"].append("BTCUSD"),
               lambda s: s["cells"].append(dict(cell(s, "5m-indices"), id="5m-fx", asset_class="fx", symbols=["EURUSD"]))]
        for i, m in enumerate(bad):
            with self.assertRaises(SystemExit, msg=f"mutation {i}"):
                self.fs.load_cells_file(_grid_dir_with_cells(self.tmp, m))
        self.assertEqual(self.fs.ASSET_CLASSES, ("metals", "indices"))

    # ---- late-starting symbols: first bars from the owner's export (server first dates, coordinator message 2026-10-01)
    LATE = {"UK100": "2017-12-28T00:00:00Z", "JP225": "2017-12-28T00:00:00Z", "EU50": "2017-12-29T00:00:00Z",
            "US2000": "2018-01-23T00:00:00Z", "HK50": "2018-12-17T01:00:00Z", "AUS200": "2019-02-08T22:00:00Z",
            "SPN35": "2020-11-09T08:00:00Z", "N25": "2020-11-12T08:00:00Z"}

    def _late_first_bar(self, sym, tf):
        return self.LATE.get(sym, "2017-12-27T23:00:00Z")

    def test_late_symbols_stay_in_m_are_disclosed_and_do_not_move_the_folds(self):
        p = self.fs.build_plan(FIXTURES, first_bar=self._late_first_bar)         # the 13-symbol cells live in the fixture
        for cid in ("5m-indices", "15m-indices"):
            c = next(x for x in p["cells"] if x["id"] == cid)
            self.assertEqual(c["symbols"], self.INDICES13)                # every symbol with data before the cutoff is in m
            self.assertEqual(c["symbols_without_development"], {})
            self.assertEqual(c["development_start"], "2017-12-27T23:00:00Z")   # the EARLIEST symbol sets the cell's start ...
            self.assertEqual(c["n_folds"], len(FS.make_folds("2017-12-27T23:00:00Z")))   # ... and so the folds
            for sy, fb in self.LATE.items():
                self.assertEqual(c["symbol_first_bar"][sy], fb)           # disclosed, never invented earlier
            self.assertEqual(c["span_source"], "from data")
        self.assertEqual(p["family"]["size"], 12)                            # fixture cells: 6 x 2; more symbols add nothing

    def test_every_late_symbol_has_bars_in_every_test_fold_and_only_spn35_and_n25_miss_the_start_of_the_first(self):
        """The owner's concern: a symbol with data in only the last folds. The fold geometry (dates only) says no symbol
        of the 13 is absent from a test fold; SPN35 and N25 (first bars Nov 2020) have no data for the first ~8 months
        of fold 0 and none in any training window before fold 0, so fold 0's training trades come from the other 11."""
        folds = FS.make_folds("2017-12-27T23:00:00Z")
        self.assertEqual(len(folds), 4)
        for sy, fb in self.LATE.items():
            for f in folds:
                self.assertLess(FS.ts(fb), FS.ts(f["test_end"]), f"{sy} has no bar by the end of fold {f['index']}")
            partial = [f["index"] for f in folds if FS.ts(fb) > FS.ts(f["test_start"])]
            self.assertEqual(partial, [0] if sy in ("SPN35", "N25") else [], sy)
            before_fold0 = (FS.ts(folds[0]["test_start"]) - FS.ts(fb)).days
            if sy in ("SPN35", "N25"):
                self.assertLess(before_fold0, 0)                       # no pre-fold-0 history at all
            else:
                self.assertGreater(before_fold0, 365)                  # at least a year of training history

    def test_xpt_and_xpd_have_no_data_in_the_first_seven_test_folds_of_the_17_fold_metals_cells_yet_count_in_m(self):
        """5m-metals / 15m-metals: folds follow XAUUSD (2004-06-11, 17 folds). XPTUSD and XPDUSD start 2015-01-07: no bar in
        test folds 0-6, 2 months of fold 7, all of folds 8-16. They stay in m (= 4, so ceil(2m/3) = 3 symbols must be positive)
        and contribute test trades only to folds 7-16; nothing is invented for the earlier folds."""
        first = {("XAUUSD", "5m"): "2004-06-11T04:15:00Z", ("XAGUSD", "5m"): "2008-11-07T21:10:00Z",
                 ("XAUUSD", "15m"): "2004-06-11T04:15:00Z", ("XAGUSD", "15m"): "2008-11-07T21:00:00Z"}
        fb = lambda s, t: first.get((s, t), "2015-01-07T00:00:00Z" if s in ("XPTUSD", "XPDUSD") else "2017-12-27T23:00:00Z")
        p = self.fs.build_plan(FIXTURES, first_bar=fb)
        for cid in ("5m-metals", "15m-metals"):
            c = next(x for x in p["cells"] if x["id"] == cid)
            self.assertEqual(c["symbols"], self.METALS4)
            self.assertEqual(c["n_folds"], 17)
            self.assertEqual(c["development_start"], "2004-06-11T04:15:00Z")
        folds = FS.make_folds("2004-06-11T04:15:00Z")
        kinds = ["none" if FS.ts("2015-01-07T00:00:00Z") >= FS.ts(f["test_end"]) else
                 ("part" if FS.ts("2015-01-07T00:00:00Z") > FS.ts(f["test_start"]) else "full") for f in folds]
        self.assertEqual(kinds, ["none"] * 7 + ["part"] + ["full"] * 9)
        self.assertEqual(FS.check_stability([], self.METALS4)["required_symbols"], 3)

    def test_a_symbol_first_bar_not_before_the_cutoff_is_left_out_of_m_and_disclosed(self):
        late = dict(self.LATE, N25="2024-06-01T00:00:00Z")
        p = self.fs.build_plan(FIXTURES, first_bar=lambda s, t: late.get(s, "2017-12-27T23:00:00Z"))
        c = next(x for x in p["cells"] if x["id"] == "15m-indices")
        self.assertNotIn("N25", c["symbols"])
        self.assertEqual(len(c["symbols"]), 12)
        self.assertIn("N25", c["symbols_without_development"])

    def test_stability_denominator_is_ceil_two_thirds_of_m_and_a_symbol_without_trades_is_not_positive(self):
        for m, need in ((2, 2), (4, 3), (5, 4), (12, 8), (13, 9)):
            syms = [f"S{i}" for i in range(m)]
            trades = [{"symbol": s, "net_R": 1.0, "entry_time": "2020-01-01T00:00:00Z"} for s in syms]
            r = FS.check_stability(trades, syms)
            self.assertEqual((r["m_symbols"], r["required_symbols"]), (m, need))
        syms = [f"S{i}" for i in range(13)]
        # 9 symbols with positive trades, 4 without a trade (or negative): exactly enough; one fewer fails
        trades = [{"symbol": s, "net_R": 1.0, "entry_time": "2023-01-01T00:00:00Z"} for s in syms[:9]]
        r = FS.check_stability(trades, syms)
        self.assertEqual((r["positive_symbols"], r["required_symbols"]), (9, 9))
        self.assertTrue(r["symbols_ok"])
        r8 = FS.check_stability(trades[:8], syms)
        self.assertFalse(r8["symbols_ok"])                                 # a silent symbol never counts as positive
        self.assertIsNone(r8["per_symbol"]["S12"]["mean_R"])
        # a late symbol with a handful of trades whose mean is <= 0 is one of the (up to) 4 that may fail, not excluded
        neg = trades + [{"symbol": "S9", "net_R": -0.5, "entry_time": "2023-06-01T00:00:00Z"}]
        self.assertEqual(FS.check_stability(neg, syms)["positive_symbols"], 9)


class DataReadiness(_Tmp):
    """Missing history / real-cost specs fail LOUD with a per-cell table (no stack trace, exit 1); complete data exits 0."""

    NEW = ("XPTUSD", "XPDUSD", "UK100", "EU50", "JP225", "HK50", "US2000", "SPN35", "N25")     # no history, no spec yet

    def _have(self, absent=(), partial=None, late=None):
        partial = partial or {}
        late = late or {}

        def first_bar(sym, tf):
            if sym in absent or tf in partial.get(sym, ()):
                return None
            return late.get(sym, "2017-12-27T23:00:00Z")
        return first_bar

    def _check(self, first_bar, spec_present=lambda s: (True, "x"), arch=FIXTURES):
        """Readiness over the six-cell test fixture by default (it keeps the 13-symbol and 15m cells); arch=REAL_ARCH for the plan."""
        out = io.StringIO()
        rc = self.fs.check_data(arch, first_bar, spec_present, out=out)
        return rc, out.getvalue()

    def test_complete_data_exits_zero_and_says_ready(self):
        rc, txt = self._check(self._have(), arch=REAL_ARCH)
        self.assertEqual(rc, 0)
        self.assertIn("READY: every declared cell", txt)
        self.assertNotIn("NOT READY", txt)
        for cid in ("1m-metals", "1m-indices", "5m-metals"):
            self.assertRegex(txt, rf"{cid}\s+\d+\s+\d+\s+0\s+0\s+0\s+yes\s+yes")
        self.assertIn("declared cells: 3", txt)
        self.assertIn("family = 6 candidate procedures", txt)
        self.assertIn("ict 29 per cell, wyckoff 16 per cell", txt)
        rc, txt = self._check(self._have())                      # the fixture: six cells, its own grids
        self.assertEqual(rc, 0)
        self.assertIn("family = 12 candidate procedures", txt)
        self.assertIn("ict 41 per cell", txt)

    def test_absent_data_exits_nonzero_with_a_table_naming_the_cells_symbols_and_specs(self):
        # today's state: the 9 new symbols have neither history nor spec; AUS200 has a spec but no history
        absent = set(self.NEW) | {"AUS200"}
        rc, txt = self._check(self._have(absent=absent), lambda s: (s not in self.NEW, f"symbolspec.{s}.json"))
        self.assertEqual(rc, 1)
        self.assertIn("NOT READY", txt)
        for cid in ("5m-metals", "5m-indices", "15m-metals", "15m-indices"):
            self.assertRegex(txt, rf"{cid}\s+\d+\s+\d+\s+\d+\s+0\s+\d+\s+yes\s+NO")
        self.assertRegex(txt, r"1m-metals\s+2\s+2\s+0\s+0\s+0\s+yes\s+yes")              # the unchanged 1m cells are ready
        self.assertRegex(txt, r"1m-indices\s+5\s+5\s+0\s+0\s+0\s+yes\s+yes")
        # declared vs effective m: today 5m-indices declares 13 but only the 5 symbols with history count
        self.assertRegex(txt, r"5m-indices\s+13\s+5\s+8\s+0\s+7\s+yes\s+NO")
        self.assertRegex(txt, r"5m-metals\s+4\s+2\s+2\s+0\s+2\s+yes\s+NO")
        self.assertIn("no history at all and no real-cost spec (2): XPTUSD, XPDUSD", txt)
        self.assertIn("no history at all and no real-cost spec (7): UK100, EU50, JP225, HK50, US2000, SPN35, N25", txt)
        self.assertIn("no history at all (1): AUS200", txt)

    def test_a_missing_spec_alone_or_a_missing_context_timeframe_alone_is_flagged(self):
        rc, txt = self._check(self._have(), lambda s: (s != "HK50", "x"))
        self.assertEqual(rc, 1)
        self.assertIn("no real-cost spec (1): HK50", txt)
        rc, txt = self._check(self._have(partial={"US2000": ("1W", "4H")}))     # US2000 1W is being re-exported
        self.assertEqual(rc, 1)
        self.assertIn("incomplete history: US2000 lacks 4H, 1W", txt)

    def test_a_symbol_starting_after_the_cutoff_is_a_note_not_a_failure_but_a_cell_with_none_is(self):
        rc, txt = self._check(self._have(late={"N25": "2024-06-01T00:00:00Z"}))
        self.assertEqual(rc, 0)
        rep = self.fs.data_readiness(self.fs.load_cells_file(FIXTURES)[0], self._have(late={"N25": "2024-06-01T00:00:00Z"}),
                                     lambda s: (True, "x"))
        c = next(x for x in rep["cells"] if x["id"] == "5m-indices")
        self.assertEqual((len(c["symbols"]), c["m_effective"]), (13, 12))       # declared 13, effective m 12
        self.assertRegex(txt, r"5m-indices\s+13\s+12\s+")
        idx = set(SymbolUniverse.INDICES13)
        every_index_late = self._have(late={s: "2024-06-01T00:00:00Z" for s in idx})
        rc, txt = self._check(every_index_late)
        self.assertEqual(rc, 1)
        self.assertIn("the cell would be dropped from the plan (the family size still counts it)", txt)
        # ... but it does not block planning: plan section 6 item 7 drops such a cell from N by data availability
        with mock.patch.object(self.fs, "_first_bar", every_index_late):
            p = self.fs.build_plan(FIXTURES)
        self.assertEqual([e["id"] for e in p["excluded_cells"]], ["1m-indices", "5m-indices", "15m-indices"])
        self.assertEqual(p["family"]["size"], 12)                           # the family counts the DECLARED cells, dropped ones included
        # the committed three-cell plan: the same late indices drop its one indices cell (1m-indices) from N
        # (5m-metals declares dev_start 2015-01-07 since 2026-10-02: its metals need a first bar at or before it)
        real_late = lambda s, t: "2004-06-11T04:15:00Z" if s in ("XAUUSD", "XAGUSD") else every_index_late(s, t)
        rc, txt = self._check(real_late, arch=REAL_ARCH)
        self.assertEqual(rc, 1)
        with mock.patch.object(self.fs, "_first_bar", real_late):
            p = self.fs.build_plan(REAL_ARCH)
        self.assertEqual([e["id"] for e in p["excluded_cells"]], ["1m-indices"])
        self.assertEqual(p["family"]["size"], 6)

    def test_plan_dry_run_and_every_data_command_refuse_with_the_table_not_a_stack_trace(self):
        gd = REAL_ARCH
        with mock.patch.object(self.fs, "_first_bar", lambda s, t: None):
            for call in (lambda: self.fs.cmd_plan(dry_run=True, grid_dir=gd),
                         lambda: self.fs.cmd_plan(grid_dir=gd),
                         lambda: self.fs.build_plan(gd)):
                with self.assertRaises(self.fs.DataNotReady) as cm:
                    call()
                self.assertIsInstance(cm.exception, SystemExit)          # a message and an exit status
                self.assertIn("DATA READINESS", str(cm.exception))
                self.assertIn("5m-metals", str(cm.exception))
            self.assertFalse(os.path.exists(self.fs.PLAN_PATH))          # nothing was written
            with self.assertRaises(SystemExit):
                self.fs.load_plan(gd)

    def test_the_cli_check_data_flag_returns_the_exit_status(self):
        with mock.patch.object(self.fs, "_first_bar", self._have()), redirect_stdout(io.StringIO()):
            self.assertEqual(self.fs.main(["plan", "--check-data", "--grid-dir", REAL_ARCH]), 0)
        with mock.patch.object(self.fs, "_first_bar", self._have(absent=set(SymbolUniverse.PARKED))), redirect_stdout(io.StringIO()):
            self.assertEqual(self.fs.main(["plan", "--check-data", "--grid-dir", REAL_ARCH]), 0)     # parked: ignored
        with mock.patch.object(self.fs, "_first_bar", self._have(absent={"XPTUSD"})), redirect_stdout(io.StringIO()):
            self.assertEqual(self.fs.main(["plan", "--check-data", "--grid-dir", REAL_ARCH]), 1)     # a used symbol: refused
        with mock.patch.object(self.fs, "_first_bar", self._have(absent={"UK100"})), redirect_stdout(io.StringIO()):
            self.assertEqual(self.fs.main(["plan", "--check-data", "--grid-dir", FIXTURES]), 1)      # used by a fixture cell

    def test_the_real_cost_spec_probe_follows_the_symbol_map(self):
        import real_costs as RC
        self.assertTrue(RC.spec_path(self.fs.COST_PROFILE, "UK100").endswith("symbolspec.UK100.cash.json"))
        self.assertTrue(RC.spec_path(self.fs.COST_PROFILE, "AUS200").endswith("symbolspec.AUS200.cash.json"))
        self.assertTrue(RC.spec_path(self.fs.COST_PROFILE, "XPTUSD").endswith("symbolspec.XPTUSD.json"))
        self.assertTrue(os.path.exists(RC.spec_path(self.fs.COST_PROFILE, "AUS200")))     # the one new-universe spec on disk


# ===================================================================== the sealed statistics (branch b20-stats-sealed)
FLOOR = 1 - 0.10 / 6


def _iid(seed, n, mean, sd=1.0, years=6):
    """n trades spread over `years` development years (so the quarter / half-year blocks have clusters)."""
    return gen("2018-03-01T00:00:00Z", FS.iso(FS.ts("2018-03-01T00:00:00Z") + datetime.timedelta(days=365 * years)), n, mean, sd,
               seed, symbols=["XAUUSD"])


class FamilyA(unittest.TestCase):
    """Pre-registration 0.2 / A2: the family is the six candidate procedures; floor 1 - 0.10/6; p = max of five p-values."""

    def test_n_adjusted_confidence_keeps_its_semantics_with_the_new_family_size(self):
        self.assertAlmostEqual(FS.n_adjusted_confidence(6), 1 - 0.10 / 6)
        self.assertAlmostEqual(FS.n_adjusted_confidence(6), 0.983333, places=6)
        self.assertEqual(FS.FAMILY_ALPHA, 0.10)
        for bad in (0, -1, 2.5, "6"):
            with self.assertRaises(ValueError):
                FS.n_adjusted_confidence(bad)

    def test_the_floor_is_looser_than_the_old_per_method_levels(self):
        # 0.98333 replaces 0.998851 (ICT, N = 87) and 0.997917 (Wyckoff, N = 48): the t quantile is smaller
        self.assertLess(FS.t_quantile(FLOOR, 100), FS.t_quantile(FS.n_adjusted_confidence(87), 100))

    def test_p_robust_is_the_max_of_the_five_and_the_bound_is_the_min(self):
        for seed in range(8):
            lb = FS.robust_lower_bound(_iid(seed, 400, 0.12), FLOOR)
            self.assertEqual(sorted(lb["p_values"]), sorted(FS.PRIMARY_COMPONENTS))
            self.assertAlmostEqual(lb["p_robust"], max(lb["p_values"].values()))
            self.assertAlmostEqual(lb["value"], min(lb["iid"], lb["block_date"], lb["block_30d"], lb["block_quarter"],
                                                    lb["block_half"]))

    def test_a_bound_above_zero_at_the_floor_is_exactly_p_robust_below_one_sixth_of_alpha(self):
        crossings = 0
        for seed in range(60):
            lb = FS.robust_lower_bound(_iid(seed, 300, 0.10 + 0.002 * seed), FLOOR)
            self.assertEqual(lb["value"] > 0, lb["p_robust"] < 0.10 / 6, (seed, lb["value"], lb["p_robust"]))
            crossings += lb["value"] > 0
        self.assertTrue(0 < crossings < 60)                         # the sweep really straddles the threshold

    def test_each_p_matches_its_own_bound(self):
        lb = FS.robust_lower_bound(_iid(3, 500, 0.15), FLOOR)
        for k in FS.PRIMARY_COMPONENTS:
            c = lb["components"][k]
            self.assertEqual(c["value"] > 0, lb["p_values"][k] < 0.10 / 6, k)

    def test_degenerate_samples_fail_closed(self):
        self.assertIsNone(FS.one_sided_p(0.1, None, None))
        self.assertEqual(FS.one_sided_p(0.1, 0.0, 5), 0.0)
        self.assertEqual(FS.one_sided_p(0.0, 0.0, 5), 1.0)
        self.assertEqual(FS.one_sided_p(-0.1, 0.0, 5), 1.0)
        self.assertAlmostEqual(FS.one_sided_p(0.0, 1.0, 10), 0.5)
        self.assertGreater(FS.one_sided_p(-2.0, 1.0, 10), 0.5)
        one_day = [{"entry_time": "2022-01-03T08:00:00Z", "exit_time": "2022-01-03T09:00:00Z", "net_R": 1.0, "symbol": "X"}] * 5
        lb = FS.robust_lower_bound(one_day, FLOOR)
        self.assertIsNone(lb["value"])                             # a single block has no CR1 bound
        self.assertIsNone(lb["p_robust"])

    def test_holm_stepdown_arithmetic(self):
        rows = FS.holm_stepdown({"a": 0.001, "b": 0.01, "c": 0.02, "d": 0.2, "e": 0.9, "f": 1.0}, 6)
        self.assertEqual([r["id"] for r in rows], ["a", "b", "c", "d", "e", "f"])
        self.assertEqual([round(r["threshold"], 6) for r in rows], [round(0.10 / (6 - k + 1), 6) for k in range(1, 7)])
        self.assertEqual([r["reject"] for r in rows], [True, True, True, False, False, False])

    def test_holm_stops_at_the_first_failure_even_if_a_later_p_is_small_enough(self):
        rows = FS.holm_stepdown({"a": 0.001, "b": 0.5, "c": 0.5001}, 3, alpha=0.10)
        self.assertEqual([r["reject"] for r in rows], [True, False, False])
        rows = FS.holm_stepdown({"a": 0.04, "b": 0.0001}, 2, alpha=0.10)       # sorted ascending; 0.04 <= 0.10/1
        self.assertEqual([(r["id"], r["reject"]) for r in rows], [("b", True), ("a", True)])

    def test_not_run_and_not_computable_candidates_count_in_the_family(self):
        # 2 of 6 given: the denominators are still 6, 5, ...; the missing four rank last with p = 1
        rows = FS.holm_stepdown({"a": 0.016, "b": None}, 6)
        self.assertAlmostEqual(rows[0]["threshold"], 0.10 / 6)
        self.assertTrue(rows[0]["reject"])                          # 0.016 <= 0.016667
        self.assertAlmostEqual(rows[1]["threshold"], 0.10 / 5)
        self.assertFalse(rows[1]["reject"])
        self.assertIsNone(rows[1]["p"])
        rows = FS.holm_stepdown({"a": 0.017}, 6)
        self.assertFalse(rows[0]["reject"])                         # fewer entries must not shrink the family
        with self.assertRaises(ValueError):
            FS.holm_stepdown({str(i): 0.5 for i in range(7)}, 6)

    def test_a_floor_pass_is_always_holm_rejected_but_holm_can_also_reject_a_floor_failure(self):
        for p in (0.0, 1e-9, 0.10 / 6 - 1e-9):                     # a floor pass, whatever the others are
            for others in ({}, {"z": 0.5}, {"y": 0.02, "z": 0.7}):
                rows = {r["id"]: r for r in FS.holm_stepdown(dict(others, cand=p), 6)}
                self.assertTrue(rows["cand"]["reject"], (p, others))
        # the other direction is NOT true, which is why the verdict does not rest on Holm alone:
        rows = {r["id"]: r for r in FS.holm_stepdown({"a": 0.001, "b": 0.018}, 6)}
        self.assertTrue(rows["b"]["reject"])
        self.assertGreater(0.018, 0.10 / 6)                         # b FAILS the floor

    def test_edge_interval_and_minimum_detectable_edge(self):
        iv = FS.edge_interval(0.10, 0.04, 11, FLOOR)
        tc, tp = FS.t_quantile(FLOOR, 11), FS.t_quantile(0.80, 11)
        self.assertAlmostEqual(iv["lower"], 0.10 - tc * 0.04)
        self.assertAlmostEqual(iv["upper"], 0.10 + tc * 0.04)
        self.assertAlmostEqual(iv["mde"], (tc + tp) * 0.04)
        self.assertGreater(iv["mde"], iv["upper"] - 0.10)           # the MDE is wider than the confidence half-width
        self.assertIsNone(FS.edge_interval(0.1, None, 5, FLOOR))
        self.assertIsNone(FS.edge_interval(0.1, 0.1, 0, FLOOR))

    def test_primary_summary_names_the_binding_half_year_bound_and_the_smallest_when_it_differs(self):
        ps = FS.primary_summary(_iid(5, 500, 0.2), FLOOR)
        half = ps["components"]["half"]
        self.assertEqual(ps["binding_half_year"]["df"], half["df"])
        self.assertAlmostEqual(ps["binding_half_year"]["se"], half["se"])
        self.assertAlmostEqual(ps["binding_half_year"]["lower"], half["value"])
        self.assertEqual(ps["floor_ok"], ps["primary_bound"] > 0)
        if ps["numerically_smallest"] != "half":
            self.assertIsNotNone(ps["smallest_bound_interval"])
        else:
            self.assertIsNone(ps["smallest_bound_interval"])
        none = FS.primary_summary([], FLOOR)
        self.assertFalse(none["floor_ok"])
        self.assertIsNone(none["binding_half_year"])

    def test_the_family_text_is_pinned_and_says_the_verdict_never_rests_on_holm_alone(self):
        self.assertIn("6", FS.FAMILY_DEFINITION)
        self.assertIn("never a PASS", FS.FAMILY_DEFINITION)
        self.assertIn("stress gate", FS.VERDICT_PRECEDENCE)
        self.assertIn("never turns a failing candidate into a pass", FS.VERDICT_PRECEDENCE)


class OrdinalPerturbation(unittest.TestCase):
    """Pre-registration A5 (replaced 2026-10-02): ordinal components only, one at a time; categorical items reported."""

    @classmethod
    def setUpClass(cls):
        cls.ict = FS.load_grid(os.path.join(ROOT, "docs", "architecture", "v-grid-ict.json")).runnable()
        cls.wy = FS.load_grid(os.path.join(ROOT, "docs", "architecture", "v-grid-wyckoff.json")).runnable()

    @staticmethod
    def _moves(grid, item, comp_name, current):
        comp = next(c for c in FS.PERTURBATION_AXES[item] if c["component"] == comp_name)
        return FS.component_neighbours(grid, item, comp, current)

    def test_the_axis_table_agrees_with_the_real_grids(self):
        for grid in (self.ict, self.wy):
            for item_id, comps in FS.PERTURBATION_AXES.items():
                if item_id not in grid.by_id:
                    continue
                for comp in comps:
                    for v in grid.by_id[item_id]["values"]:
                        if item_id == "W4a" and v == grid.by_id[item_id]["values"][0]:
                            self.assertEqual(FS.component_neighbours(grid, item_id, comp, v), [])   # the v1-typed baseline
                            continue
                        self.assertIn(FS._split_value(v, comp["part"]), comp["order"], (item_id, comp["component"], v))
                        for _d, new in FS.component_neighbours(grid, item_id, comp, v):      # raises if undeclared
                            self.assertIn(new, grid.by_id[item_id]["values"])
        # every axis item exists in one of the grids, and the orders are the pre-registered ones
        names = {i for g in (self.ict, self.wy) for i in g.by_id}
        self.assertTrue(set(FS.PERTURBATION_AXES) <= names | {"W4a"})
        self.assertEqual(FS.PERTURBATION_AXES["B-EX"][0]["order"], ["iofed", "ce", "fill"])
        self.assertEqual(FS.PERTURBATION_AXES["B-BUF"][0]["order"], ["0", "0.1atr", "0.25atr"])
        self.assertEqual([c["order"] for c in FS.PERTURBATION_AXES["B-EXIT"]],
                         [["-2.0", "-2.25", "-2.5"], ["H", "1.5H", "2H", "none"]])
        self.assertEqual([c["order"] for c in FS.PERTURBATION_AXES["B-LB"]], [["8", "12", "16"], ["K", "2K"]])
        self.assertEqual(FS.PERTURBATION_AXES["W6"][0]["order"], [300, 600])
        self.assertEqual([c["order"] for c in FS.PERTURBATION_AXES["W-TW"]], [[8, 12, 20], [2, 3]])
        self.assertEqual(FS.PERTURBATION_AXES["W4a"][0]["order"], [3, 4])

    def test_the_categorical_items_are_exactly_the_pre_registered_ones(self):
        ict_cat = {i for i in self.ict.by_id if i not in FS.PERTURBATION_AXES}
        wy_cat = {i for i in self.wy.by_id if i not in FS.PERTURBATION_AXES}
        self.assertEqual(ict_cat, {"B-PD", "B-POOL", "B6", "B3", "B-MGMT", "B7"})       # B4 is declared, not runnable
        self.assertEqual(wy_cat, {"W-STOP", "W-SPT", "W-MGMT", "W-TOUCH"})              # W4b likewise

    def test_one_component_moves_at_a_time_and_the_others_stay(self):
        g = self.ict
        self.assertEqual(self._moves(g, "B-EXIT", "target", "-2.25|1.5H|floor"),
                         [(-1, "-2.0|1.5H|floor"), (+1, "-2.5|1.5H|floor")])
        self.assertEqual(self._moves(g, "B-EXIT", "time_stop", "-2.25|1.5H|floor"),
                         [(-1, "-2.25|H|floor"), (+1, "-2.25|2H|floor")])
        self.assertEqual(self._moves(g, "B-EXIT", "target", "-2.0|H|floor"), [(+1, "-2.25|H|floor")])        # edge
        self.assertEqual(self._moves(g, "B-EXIT", "time_stop", "-2.5|none|floor"), [(-1, "-2.5|2H|floor")])  # edge
        self.assertEqual(self._moves(g, "B-LB", "lookback", "12|K"), [(-1, "8|K"), (+1, "16|K")])
        self.assertEqual(self._moves(g, "B-LB", "expiry", "12|K"), [(+1, "12|2K")])
        self.assertEqual(self._moves(g, "B-LB", "expiry", "12|2K"), [(-1, "12|K")])
        self.assertEqual(self._moves(g, "B-EX", "entry_model", "ce"), [(-1, "iofed"), (+1, "fill")])
        self.assertEqual(self._moves(g, "B-BUF", "stop_buffer", "0"), [(+1, "0.1atr")])
        w = self.wy
        self.assertEqual(self._moves(w, "W-TW", "test_window", [12, 3]), [(-1, [8, 3]), (+1, [20, 3])])
        self.assertEqual(self._moves(w, "W-TW", "phase_b_swings", [12, 2]), [(+1, [12, 3])])
        self.assertEqual(self._moves(w, "W6", "structure_window", 300), [(+1, 600)])
        self.assertEqual(self._moves(w, "W6", "structure_window", 600), [(-1, 300)])

    def test_w4a_is_only_perturbed_between_the_explicit_counts_3_and_4(self):
        w = self.wy
        self.assertEqual(self._moves(w, "W4a", "linger_closes", 2), [])                  # the v1-typed baseline: not ordinal
        self.assertEqual(self._moves(w, "W4a", "linger_closes", 3), [(+1, 4)])
        self.assertEqual(self._moves(w, "W4a", "linger_closes", 4), [(-1, 3)])

    def test_an_axis_that_disagrees_with_the_grid_fails_loud(self):
        g = FS.Grid({"method": "ICT", "items": [{"id": "B-EX", "key": "k", "values": ["iofed", "fill"]}]})
        comp = FS.PERTURBATION_AXES["B-EX"][0]
        with self.assertRaises(FS.GridError):
            FS.component_neighbours(g, "B-EX", comp, "iofed")          # the next step on the order, 'ce', is not declared

    def _folds_with(self, grid, overrides_by_fold):
        folds = FS.make_folds(LONG_START)
        out = []
        for fold, ov in zip(folds, overrides_by_fold):
            out.append({"fold": fold, "chosen": grid.full(ov), "changed": [], "test_trades": []})
        return out

    def test_sets_pool_the_moved_values_per_component_and_direction_and_record_the_skips(self):
        g = self.wy
        asked = []

        def trades_for(values):
            asked.append(json.dumps(values, sort_keys=True))
            return gen(LONG_START, FS.DEV_CUTOFF, 400, 0.3, 0.5, json.dumps(values, sort_keys=True), symbols=["XAUUSD"])
        res = self._folds_with(g, [{"W4a": 2, "W6": 300, "W-TW": [12, 2]}, {"W4a": 3, "W6": 600, "W-TW": [8, 3]}])
        sets = FS.perturbation_trade_sets(g, trades_for, res)
        keys = {(s["item"], s["component"], s["direction"]): s for s in sets}
        self.assertEqual(sorted(keys), sorted([("W-TW", "phase_b_swings", -1), ("W-TW", "phase_b_swings", +1),
                                               ("W-TW", "test_window", -1), ("W-TW", "test_window", +1),
                                               ("W4a", "linger_closes", +1), ("W6", "structure_window", -1),
                                               ("W6", "structure_window", +1)]))
        self.assertEqual(keys[("W6", "structure_window", +1)]["folds"], 1)               # only fold 0 chose 300
        self.assertEqual(keys[("W6", "structure_window", -1)]["folds"], 1)               # only fold 1 chose 600
        self.assertEqual(keys[("W4a", "linger_closes", +1)]["folds"], 1)                 # fold 1 (3 -> 4); fold 0 chose 2
        self.assertNotIn(("W4a", "linger_closes", -1), keys)
        self.assertEqual(keys[("W-TW", "test_window", +1)]["folds"], 2)                  # 12 -> 20 and 8 -> 12
        self.assertTrue(all(s["kind"] == "ordinal" for s in sets))
        skips = FS.perturbation_skips(g, res)
        self.assertEqual([(s["item"], s["component"], s["chosen"]) for s in skips], [("W4a", "linger_closes", 2)])
        # nothing but ONE component moved in any requested set: compare against the fold's chosen values
        base_keys = {json.dumps(r["chosen"], sort_keys=True) for r in res}
        for k in asked:
            v = json.loads(k)
            if k in base_keys:
                continue
            diffs = [i for r in res for i in v if v[i] != r["chosen"][i]]
            self.assertTrue(any(sum(1 for i in v if v[i] != r["chosen"][i]) == 1 for r in res), (k, diffs))

    def test_categorical_flips_are_value_a_to_value_b_per_fold_choice_and_never_ordinal_items(self):
        g = self.ict
        res = self._folds_with(g, [{"B-PD": "r15", "B7": "all_hours"}, {"B-PD": "r13", "B7": "all_hours"}])
        flips = FS.categorical_flip_sets(g, lambda v: [], res)
        got = {(f["item"], f["from"], f["to"]): f["folds"] for f in flips}
        self.assertEqual(got[("B-PD", "r15", "r13")], 1)
        self.assertEqual(got[("B-PD", "r13", "r15")], 1)
        self.assertEqual(got[("B7", "all_hours", "killzone")], 2)
        self.assertFalse(any(f["item"] in FS.PERTURBATION_AXES for f in flips))
        self.assertTrue(all(f["kind"] == "categorical" for f in flips))
        rep = FS.categorical_report([dict(f, trades=_iid(1, 60, 0.2)) for f in flips[:2]], FLOOR)
        self.assertEqual(sorted(rep[0]), ["folds", "from", "item", "lower_bound", "mean_R", "n", "to"])

    def test_a_neighbour_must_have_a_positive_mean_and_a_positive_bound(self):
        good = _iid(1, 400, 0.4)
        meh = _iid(2, 400, 0.12)                       # positive mean, bound below 0 at the floor
        bad = _iid(3, 400, -0.1)

        def row(tr):
            return {"item": "a", "component": "a", "direction": 1, "folds": 3, "trades": tr}
        self.assertTrue(FS.check_perturbation([row(good)], FLOOR)["ok"])
        r = FS.check_perturbation([row(meh)], FLOOR)
        self.assertFalse(r["ok"])
        self.assertGreater(r["rows"][0]["mean_R"], 0)
        self.assertLessEqual(r["rows"][0]["lower_bound"], 0)
        self.assertFalse(FS.check_perturbation([row(bad)], FLOOR)["ok"])
        self.assertFalse(FS.check_perturbation([row(good), row(bad)], FLOOR)["ok"])      # every neighbour must pass
        self.assertFalse(FS.check_perturbation([], FLOOR)["ok"])

    def test_the_gate_is_at_the_floor_confidence_not_at_a_looser_level(self):
        tr = _iid(7, 300, 0.11)
        lo90 = FS.robust_lower_bound(tr, 0.90)["value"]
        lo_floor = FS.robust_lower_bound(tr, FLOOR)["value"]
        self.assertLess(lo_floor, lo90)
        got = FS.check_perturbation([{"item": "a", "component": "a", "direction": 1, "folds": 1, "trades": tr}], FLOOR)
        self.assertEqual(got["rows"][0]["lower_bound"], lo_floor)

    def test_component_stability_lists_the_chosen_component_per_fold(self):
        g = self.ict
        res = self._folds_with(g, [{"B-EXIT": "-2.0|H|floor"}, {"B-EXIT": "-2.0|2H|floor"}, {"B-EXIT": "-2.5|2H|floor"}])
        cs = FS.component_stability(g, res)
        self.assertEqual(cs["B-EXIT.target"]["values_by_fold"], ["-2.0", "-2.0", "-2.5"])
        self.assertEqual((cs["B-EXIT.target"]["changes"], cs["B-EXIT.time_stop"]["changes"]), (1, 1))
        self.assertIn("B-EX.entry_model", cs)

    def test_the_axes_are_part_of_the_plan_core_and_the_declaration_pin(self):
        fs = _fs()
        plan = fs.build_plan(REAL_ARCH, first_bar=lambda s, t: "2010-01-01T00:00:00Z")
        self.assertEqual(plan["perturbation_axes"], FS.PERTURBATION_AXES)
        cfg = fs.evaluation_config(plan)
        self.assertEqual(cfg["perturbation"]["axes"], FS.PERTURBATION_AXES)
        self.assertEqual(cfg["perturbation"]["definition"], FS.PERTURBATION_DEFINITION)
        self.assertEqual(cfg["stress"]["commission_fraction"], 0.00003)
        self.assertEqual(cfg["stress"]["spread_stat"], "p90")
        self.assertEqual(cfg["family"], plan["family"])
        self.assertEqual(cfg["regime_split"], FS.REGIME_SPLIT_DEFINITION)
        self.assertEqual(cfg["verdict_precedence"], FS.VERDICT_PRECEDENCE)
        self.assertEqual(cfg["prop_shift"], FS.PROP_SHIFT_DEFINITION)
        changed = json.loads(json.dumps(FS.PERTURBATION_AXES))
        changed["W6"][0]["order"] = [600, 300]
        with mock.patch.object(FS, "PERTURBATION_AXES", changed):
            self.assertNotEqual(fs.build_plan(REAL_ARCH, first_bar=lambda s, t: "2010-01-01T00:00:00Z")["plan_hash"],
                                plan["plan_hash"])


def _d1_candles(opens, base=2000.0):
    """D1 candles with a mild deterministic trend + noise; `opens` are ISO open labels."""
    rng = random.Random(11)
    out, px = [], base
    for o in opens:
        step = rng.uniform(-6, 9)
        out.append({"time": o, "open": px, "high": px + abs(step) + 4, "low": px - abs(step) - 4, "close": px + step,
                    "volume": 1.0})
        px += step
    return out


def _daily_opens(start, n, hour=22):
    t0 = FS.ts(start).replace(hour=hour)
    return [FS.iso(t0 + datetime.timedelta(days=i)) for i in range(n)]


class D1Regime(unittest.TestCase):
    """Pre-registration A7: the D1 ADX(14) of the last D1 bar whose CLOSE is at or before the entry time."""

    def setUp(self):
        self.candles = _d1_candles(_daily_opens("2022-01-03T00:00:00Z", 80))
        self.idx = FS.d1_adx_index(self.candles)
        self.vals = FS.adx14([c["high"] for c in self.candles], [c["low"] for c in self.candles],
                             [c["close"] for c in self.candles])

    def test_a_bar_is_complete_at_open_plus_24h_and_not_a_second_earlier(self):
        i = 50                                                          # a bar with a computed ADX
        self.assertIsNotNone(self.vals[i])
        close = FS.ts(self.candles[i]["time"]) + datetime.timedelta(days=1)
        at = FS.iso(close)
        before = FS.iso(close - datetime.timedelta(seconds=1))
        self.assertEqual(FS.d1_adx_at(self.idx, at), self.vals[i])                    # bar boundary: closed AT the entry
        self.assertEqual(FS.d1_adx_at(self.idx, before), self.vals[i - 1])             # one second earlier: still forming
        self.assertNotEqual(self.vals[i], self.vals[i - 1])

    def test_the_entry_days_own_forming_bar_is_never_read(self):
        i = 55
        opened = self.candles[i]["time"]                                # the instant the entry day's bar OPENS
        for delta in (0, 1, 3600, 12 * 3600, 24 * 3600 - 1):
            at = FS.iso(FS.ts(opened) + datetime.timedelta(seconds=delta))
            self.assertEqual(FS.d1_adx_at(self.idx, at), self.vals[i - 1], delta)

    def test_the_old_decision_timeframe_rule_would_have_read_the_forming_bar(self):
        # why the replacement exists: `adx_before` (last bar that OPENED strictly before the entry) is right for a 15m bar and a
        # one-day look-ahead for D1 -- the bar that opened an hour earlier is still forming
        i = 55
        entry = FS.iso(FS.ts(self.candles[i]["time"]) + datetime.timedelta(hours=1))
        old = FS.adx_before(FS.adx_index(self.candles), entry)
        self.assertEqual(old, self.vals[i])
        self.assertEqual(FS.d1_adx_at(self.idx, entry), self.vals[i - 1])

    def test_no_value_before_the_first_close_or_during_warm_up(self):
        first_close = FS.ts(self.candles[0]["time"]) + datetime.timedelta(days=1)
        self.assertIsNone(FS.d1_adx_at(self.idx, FS.iso(first_close - datetime.timedelta(seconds=1))))
        self.assertIsNone(FS.d1_adx_at(self.idx, FS.iso(first_close)))               # closed, but ADX(14) needs 2 x 14 bars
        warm = FS.ts(self.candles[26]["time"]) + datetime.timedelta(days=1)
        self.assertIsNone(FS.d1_adx_at(self.idx, FS.iso(warm)))
        self.assertIsNotNone(FS.d1_adx_at(self.idx, FS.iso(warm + datetime.timedelta(days=1))))

    def test_a_trade_with_no_d1_value_fails_the_regime_check(self):
        mk = lambda a, r: {"entry_time": "2022-01-01T00:00:00Z", "exit_time": "2022-01-01T01:00:00Z", "symbol": "X",
                           "net_R": r, "adx14_d1": a}
        trades = [mk(10 + i % 5, 0.5) for i in range(20)] + [mk(30 + i % 5, 0.4) for i in range(20)]
        self.assertTrue(FS.check_regime_split(trades)["ok"])
        chk = FS.check_regime_split(trades + [mk(None, 0.5)])
        self.assertFalse(chk["ok"])
        self.assertIn("no completed D1 bar", chk["reason"])
        # the decision-timeframe ADX is NOT a substitute: a trade carrying only `adx14` has no D1 value
        only_tf = [{"entry_time": "2022-01-01T00:00:00Z", "exit_time": "2022-01-01T01:00:00Z", "symbol": "X", "net_R": 0.5,
                    "adx14": 20.0} for _ in range(10)]
        self.assertFalse(FS.check_regime_split(only_tf)["ok"])

    def test_the_median_split_uses_the_d1_value_and_needs_both_halves_positive(self):
        mk = lambda a, r, tf_adx: {"entry_time": "2022-01-01T00:00:00Z", "exit_time": "2022-01-01T01:00:00Z", "symbol": "X",
                                   "net_R": r, "adx14_d1": a, "adx14": tf_adx}
        # the D1 ADX separates winners from losers; the decision-timeframe ADX (reporting) is constant and would not
        trades = [mk(12, 0.9, 25.0) for _ in range(30)] + [mk(35, -0.3, 25.0) for _ in range(30)]
        chk = FS.check_regime_split(trades)
        self.assertFalse(chk["ok"])
        self.assertEqual((chk["low"]["n"], chk["high"]["n"]), (30, 30))
        self.assertAlmostEqual(chk["median_adx14_d1"], (12 + 35) / 2)
        self.assertGreater(chk["low"]["mean_R"], 0)
        self.assertLess(chk["high"]["mean_R"], 0)

    def test_the_value_is_point_in_time(self):
        # bar i's ADX is identical on the series truncated right after bar i: no later bar can change it
        for i in (30, 45, 60):
            trunc = FS.d1_adx_index(self.candles[:i + 1])
            at = FS.iso(FS.ts(self.candles[i]["time"]) + datetime.timedelta(days=1))
            self.assertEqual(FS.d1_adx_at(trunc, at), FS.d1_adx_at(self.idx, at))

    def test_close_convention_dst_weekend_and_last_bar(self):
        # 25 h day (fall back): the next bar opens 25 h later, so the close is the next open, NOT open + 24 h
        a, b, c = "2023-10-28T21:00:00Z", "2023-10-29T21:00:00Z", "2023-10-30T22:00:00Z"
        cs = [{"time": t, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 1} for t in (a, b, c)]
        closes, _ = FS.d1_adx_index(cs)
        self.assertEqual([FS.iso(x) for x in closes], [b, c, "2023-10-31T22:00:00Z"])
        # 23 h bar / weekend: never EARLIER than open + 24 h
        w = [{"time": t, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 1}
             for t in ("2023-03-24T22:00:00Z", "2023-03-26T21:00:00Z")]       # Friday bar, then the Sunday-evening bar (47 h)
        closes, _ = FS.d1_adx_index(w)
        self.assertEqual(FS.iso(closes[0]), "2023-03-26T21:00:00Z")
        self.assertGreaterEqual(closes[0], FS.ts(w[0]["time"]) + FS.D1_BAR)
        self.assertEqual(FS.iso(closes[1]), "2023-03-27T21:00:00Z")           # the last bar: open + 24 h

    def test_the_real_d1_series_follow_the_documented_open_label_convention(self):
        """Counts of label hours and gaps only (no price, no R): every real FTMO D1 label is the broker's server midnight in UTC
        (21:00Z or 22:00Z), gaps are 24 h except weekend / DST / holiday ones, and no D1 close precedes its own open label + 24 h."""
        import history_store as HS
        root = os.path.join(ROOT, "data", "history", "ftmo")
        doc, _ = HS.read_doc("XAUUSD", "1D", root=root)
        cs = [c for c in doc["candles"] if "2022-01-01" <= c["time"] < "2024-03-01"]
        self.assertGreater(len(cs), 400)
        self.assertEqual({FS.ts(c["time"]).hour for c in cs}, {21, 22})
        gaps = {round((FS.ts(b["time"]) - FS.ts(a["time"])).total_seconds() / 3600) for a, b in zip(cs, cs[1:])}
        self.assertTrue({24, 25, 23}.intersection(gaps) and gaps <= {23, 24, 25, 47, 48, 49, 71, 72, 73, 95, 96, 97})
        closes, _ = FS.d1_adx_index(cs)
        self.assertTrue(all(c >= FS.ts(k["time"]) + FS.D1_BAR for c, k in zip(closes, cs)))
        self.assertEqual(closes, sorted(closes))                    # monotone, so the bisect lookup is valid


class StressArithmetic(unittest.TestCase):
    """Pre-registration A8a: gross R - p90 cost - 0.00003 * entry / |entry - stop|."""

    def test_the_commission_margin_is_a_fraction_of_notional_charged_in_r(self):
        self.assertAlmostEqual(FS.stress_commission_r(2000.0, 1998.0), 0.00003 * 2000 / 2)
        self.assertAlmostEqual(FS.stress_commission_r(100.0, 101.0), 0.003)
        self.assertAlmostEqual(FS.stress_commission_r(50.0, 49.5), 0.00003 * 50 / 0.5)
        # a tighter stop makes the same margin cost more R: it is a fraction of NOTIONAL, not of risk
        self.assertGreater(FS.stress_commission_r(2000.0, 1999.0), FS.stress_commission_r(2000.0, 1990.0))
        # not computable: a result the gate fails on, never a raise
        for e, s in ((0.0, 1.0), (100.0, 100.0), (-1.0, -2.0), (float("nan"), 1.0), (100.0, float("inf")), (None, 1.0)):
            self.assertIsNone(FS.stress_commission_r(e, s), (e, s))
            self.assertIsNone(FS.stressed_net_r(1.0, 0.1, e, s), (e, s))
        self.assertEqual(FS.STRESS_COMMISSION_FRACTION, 0.00003)
        self.assertEqual(FS.STRESS_SPREAD_STAT, "p90")

    def test_stressed_net_r_subtracts_cost_and_margin(self):
        self.assertAlmostEqual(FS.stressed_net_r(1.5, 0.2, 2000.0, 1998.0), 1.5 - 0.2 - 0.03)

    def test_the_gate_is_on_the_stressed_mean_and_fails_closed(self):
        win = [{"entry_time": "2022-01-03T08:00:00Z", "exit_time": "2022-01-03T09:00:00Z", "net_R": r, "symbol": "X"}
               for r in (0.2, 0.1, 0.3, 0.15)]
        self.assertTrue(FS.check_stress(win, FLOOR)["ok"])
        lose = [dict(t, net_R=t["net_R"] - 0.3) for t in win]
        chk = FS.check_stress(lose, FLOOR)
        self.assertFalse(chk["ok"])
        self.assertLess(chk["mean_R_stressed"], 0)
        self.assertFalse(FS.check_stress(None, FLOOR)["ok"])
        self.assertFalse(FS.check_stress([], FLOOR)["ok"])
        # a not-computable trade (net_R None) fails the gate even when every other trade is a big winner
        broken = win + [dict(win[0], net_R=None)]
        chk = FS.check_stress(broken, FLOOR)
        self.assertFalse(chk["ok"])
        self.assertIn("not computable", chk["reason"])
        self.assertEqual(FS.prop_shift_r({"value": 0.1, "mean": 0.25}), 0.15)
        self.assertIsNone(FS.prop_shift_r({"value": None, "mean": 0.25}))


class _RealSliceEngine(unittest.TestCase):
    """The REAL BtEngine on a temp history root cut from the committed FTMO XAUUSD series (all timeframes, one span): no
    scan is run, the raw trades are seeded by hand, so no engine R of any real evaluation is involved."""

    SPAN_TF, SPAN_BARS = "1D", 400

    @classmethod
    def setUpClass(cls):
        d = os.path.join(ROOT, "data", "history", "ftmo", "ohlcv.XAUUSD.1D")
        if not os.path.isdir(d):
            raise AssertionError(f"{d} is missing: these tests need the FTMO history")
        cls.tmp = tempfile.mkdtemp(prefix="stats-sealed-")
        cls.env = os.environ.get("BT_HISTORY_ROOT")
        hist = os.path.join(cls.tmp, "hist")
        cls.span = _write_slice_root(hist, "XAUUSD", cls.SPAN_TF, cls.SPAN_BARS)
        os.environ["BT_HISTORY_ROOT"] = hist
        cls.fs = _fs()
        grids, _ = cls.fs.load_grids(REAL_ARCH)
        cls.grid = grids["ict"].runnable()

    @classmethod
    def tearDownClass(cls):
        if cls.env is None:
            os.environ.pop("BT_HISTORY_ROOT", None)
        else:
            os.environ["BT_HISTORY_ROOT"] = cls.env
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _t(self, i, entry, stop, side="long", day="2023-09-12", R=2.0):
        base = datetime.datetime.fromisoformat(day + "T08:00:00+00:00") + datetime.timedelta(hours=3 * i)
        return {"symbol": "XAUUSD", "tf": "15m", "side": side, "entry": entry, "stop": stop, "target": entry + 6 * (entry - stop),
                "entry_time": FS.iso(base), "exit_time": FS.iso(base + datetime.timedelta(hours=1)), "outcome": "win",
                "R": R, "R_planned": 6.0, "event": f"XAUUSD-{side}-ict-s{i}-m{i}"}

    def _engine(self, raw):
        eng = self.fs.BtEngine(self.grid, "ICT", "15m", ["XAUUSD"], workers=1)
        eng._raw[FS.CountingSource._key(self.grid.baseline())] = list(raw)
        return eng


class RegimeOnTheEngine(_RealSliceEngine):
    def test_the_trade_carries_the_d1_adx_of_the_last_completed_bar_and_keeps_the_tf_adx_for_reporting(self):
        eng = self._engine([self._t(0, 1900.0, 1898.0), self._t(1, 1900.0, 1902.0, side="short")])
        taken = eng.trades_for(self.grid.baseline())
        self.assertEqual(len(taken), 2)
        d1, _ = eng.bt.load("XAUUSD", "1D")
        idx = FS.d1_adx_index(d1)
        for t in taken:
            self.assertIn("adx14", t)                                    # decision timeframe: reporting only
            want = FS.d1_adx_at(idx, t["entry_time"])
            self.assertEqual(t["adx14_d1"], want)
            self.assertIsNotNone(want)
        # a different day reads a different completed bar
        late = self._engine([self._t(0, 1900.0, 1898.0, day="2023-12-12")]).trades_for(self.grid.baseline())
        self.assertNotEqual(late[0]["adx14_d1"], taken[0]["adx14_d1"])

    def test_the_snapshot_records_the_d1_series_the_regime_split_reads(self):
        snap = self._engine([]).dataset_snapshot()
        rs = snap["regime_series"]
        self.assertEqual([r["symbol"] for r in rs], ["XAUUSD"])
        self.assertEqual(rs[0]["timeframe"], "1D")
        self.assertGreater(rs[0]["bars"], 100)
        self.assertEqual(len(rs[0]["sha256"]), 64)
        self.assertLess(rs[0]["last_open"], FS.DEV_CUTOFF)                # PIT-truncated like every series

    def test_a_trade_before_any_completed_d1_bar_has_no_value(self):
        early = self._engine([self._t(0, 1900.0, 1898.0, day="2021-01-12")])         # before the temp series starts
        taken = early.trades_for(self.grid.baseline())
        self.assertTrue(all(t["adx14_d1"] is None for t in taken))


class StressAndShiftOnTheEngine(_RealSliceEngine):
    def test_stress_trades_reprice_the_same_admitted_trades_at_p90_plus_the_commission_margin(self):
        import real_costs as RC
        eng = self._engine([self._t(0, 1900.0, 1898.0), self._t(1, 1900.0, 1902.0, side="short"),
                            self._t(2, 1950.0, 1949.0, R=-1.0)])
        taken = eng.trades_for(self.grid.baseline())
        stressed = eng.stress_trades(taken)
        self.assertEqual([t["event"] for t in stressed], [t["event"] for t in taken])         # no trade added or removed
        self.assertEqual([t["entry_time"] for t in stressed], [t["entry_time"] for t in taken])
        for s, t in zip(stressed, taken):
            med = RC.cost_r(t["entry"], t["stop"], t["entry_time"], t["exit_time"], t["symbol"], t["side"], self.fs.COST_PROFILE)
            p90 = RC.cost_r(t["entry"], t["stop"], t["entry_time"], t["exit_time"], t["symbol"], t["side"], self.fs.COST_PROFILE,
                            spread_stat="p90")
            self.assertGreater(p90["spread_R"], med["spread_R"])                           # p90 spread is wider
            margin = 0.00003 * t["entry"] / abs(t["entry"] - t["stop"])
            self.assertAlmostEqual(s["net_R"], t["R"] - p90["total_R"] - margin, places=12)
            self.assertAlmostEqual(s["net_R_median"], t["net_R"])
            self.assertLess(s["net_R"], t["net_R"])                                        # stress only ever costs more
            self.assertEqual(p90["spread_stat"], "p90")
            self.assertIn("spread_scale", p90)                                            # price-scaled (relative-spread profile)

    def test_a_not_computable_stress_margin_makes_the_engine_offer_nothing_and_the_gate_fails(self):
        eng = self._engine([self._t(0, 1900.0, 1898.0), self._t(1, 1900.0, 1902.0, side="short")])
        taken = eng.trades_for(self.grid.baseline())
        with mock.patch.object(FS, "stressed_net_r", return_value=None):
            self.assertIsNone(eng.stress_trades(taken))            # no raise: fail closed
        self.assertFalse(FS.check_stress(None, FLOOR)["ok"])

    def test_a_trade_that_only_just_wins_loses_under_stress(self):
        import real_costs as RC
        t0 = self._t(0, 1900.0, 1899.0, R=0.0)
        eng = self._engine([dict(t0, R=0.0)])
        taken = eng.trades_for(self.grid.baseline())
        self.assertEqual(len(taken), 1)
        p90 = RC.cost_r(1900.0, 1899.0, t0["entry_time"], t0["exit_time"], "XAUUSD", "long", self.fs.COST_PROFILE, "p90")
        med = RC.cost_r(1900.0, 1899.0, t0["entry_time"], t0["exit_time"], "XAUUSD", "long", self.fs.COST_PROFILE)
        edge = med["total_R"] + 0.5 * (p90["total_R"] - med["total_R"])        # an R that clears the median cost, not the p90 one
        taken = [dict(taken[0], R=edge, net_R=edge - med["total_R"])]
        self.assertGreater(taken[0]["net_R"], 0)
        self.assertLess(eng.stress_trades(taken)[0]["net_R"], 0)

    def test_prop_pass_default_is_the_unshifted_gate_and_a_shift_subtracts_from_every_admitted_trade(self):
        raw = [self._t(i, 1900.0 + i, 1898.0 + i, day="2023-09-12") for i in range(4)]
        eng = self._engine(raw)
        taken = eng.trades_for(self.grid.baseline())
        ps = self.fs._prop_search()
        seen = []

        def fake_metrics(trades, **kw):
            seen.append([t["net_R"] for t in trades])
            return {"prop_pass_probability": {"value": 0.8, "spread": {}}}
        with mock.patch.object(ps._perf, "metrics", fake_metrics):
            plain = eng.prop_pass(taken)
            explicit = eng.prop_pass(taken, r_shift=0.0)
            shifted = eng.prop_pass(taken, r_shift=0.15)
        n_funds = len(ps.FUNDS)
        self.assertEqual(len(seen), 3 * n_funds)
        base, zero, sh = seen[:n_funds][0], seen[n_funds:2 * n_funds][0], seen[2 * n_funds:][0]
        self.assertEqual(base, zero)                                        # r_shift=0.0 IS the default, byte for byte
        self.assertEqual(plain, explicit)
        self.assertEqual(len(sh), len(base))                                # the admitted list is unchanged by the shift
        for a, b in zip(base, sh):
            self.assertAlmostEqual(b, a - 0.15, places=12)
        self.assertEqual(shifted, plain)                                    # (the stub returns a constant)


class CommittedPlanIsCurrent(unittest.TestCase):
    """C1 (review 2026-10-02): `declare` / `run` refuse a stale `docs/experiments/fund-search/plan.json` (`load_plan`), but until
    now nothing in the suite did, so a cells file / grid / engine-pin edit after the plan was committed only failed at `declare`.
    This test recomputes the plan on the REAL cells file, grids and data and compares its hash with the committed one."""

    def test_the_committed_plan_hash_equals_build_plan_on_the_real_inputs(self):
        fs = _fs()                                   # unpatched: PLAN_PATH is the committed file, GRID_DIR the real grids
        if not os.path.exists(fs.PLAN_PATH):
            self.skipTest(f"LOUD SKIP: {fs.PLAN_PATH} is absent (deleted before `plan`?). Recreate it with `python3 -W ignore "
                          f"scripts/fund-search.py plan` and `git add -f` it; this test asserts it again once it exists.")
        committed = json.load(open(fs.PLAN_PATH, encoding="utf-8"))
        with mock.patch.dict(os.environ, {"BT_HISTORY_ROOT": os.path.join(ROOT, "data", "history", "ftmo")}):
            fresh = fs.build_plan()
        self.assertEqual(
            fresh["plan_hash"], committed["plan_hash"],
            f"STALE PLAN: {fs.PLAN_PATH} has plan_hash {committed['plan_hash'][:12]} but the real cells file, grids, cost pins "
            f"and data now give {fresh['plan_hash'][:12]}. Delete the file, run `python3 -W ignore scripts/fund-search.py plan`, "
            f"`git add -f` it, after the LAST change to the plan core.")


class ReportAndLedger(_Tmp):
    """The family, Holm, section C and the statements in the report; the declaration records the family."""

    def _plan(self):
        self.fs.cmd_plan(grid_dir=FIXTURES)
        return json.load(open(self.fs.PLAN_PATH))

    def _records(self, plan, means):
        grids, paths = self.fs.load_grids(FIXTURES)
        os.makedirs(self.records, exist_ok=True)
        for c, mean in zip(plan["candidates"], means):
            cell = dict(next(x for x in plan["cells"] if x["id"] == c["cell"]), development_start=LONG_START)
            eng = SynthEngine(mean=mean, symbols=cell["symbols"])
            # "a" is ordinal and "b" categorical here, so the report has both an ordinal table and categorical flips
            res = self.fs.evaluate_with_engine(eng, grid_two_items(), cell, c["family_size"], axes={"a": TEST_AXES["a"]})
            rec = self.fs.build_record(c, plan["plan_hash"], grids[c["method"]], paths[c["method"]], res,
                                       {"snapshot_id": "t", "series": []}, cell)
            X.write(types.MappingProxyType(dict(rec)), store=self.records)
        return plan

    def test_1m_indices_short_span_label_is_in_the_statements_only_when_the_cell_is_planned(self):
        self.assertIn("2022-03..2024-03", self.fs.INDICES_SHORT_SPAN_LABEL)
        self.assertIn("2022-24 behaviour", self.fs.INDICES_SHORT_SPAN_LABEL)
        base = {"cells": [{"id": "1m-indices", "symbols": ["US500"], "development_start": "2020-03-01"}],
                "cells_file": {"removed_cells": []}, "dev_cutoff": "2024-03-01T00:00:00Z", "prior_counts_disclosed": {}}
        self.assertIn(self.fs.INDICES_SHORT_SPAN_LABEL, "\n".join(self.fs.report_statement_lines(base, [])))
        other = dict(base, cells=[{"id": "5m-metals", "symbols": ["XAUUSD"], "development_start": None}])
        self.assertNotIn(self.fs.INDICES_SHORT_SPAN_LABEL, "\n".join(self.fs.report_statement_lines(other, [])))

    def test_plan_core_family_and_dry_run(self):
        plan = self._plan()
        fam = plan["family"]
        self.assertEqual(fam["size"], plan["cell_count"] * 2)
        self.assertAlmostEqual(fam["floor_confidence"], 1 - 0.10 / fam["size"])
        self.assertEqual(fam["members"], [f"{m}-{c['id']}" for c in json.load(open(os.path.join(FIXTURES, "fund-search-cells.json")))["cells"]
                                          for m in ("ict", "wyckoff")])
        self.assertNotIn("n_by_method", plan)
        self.assertNotIn("confidence_by_method", plan)
        for c in plan["candidates"]:
            self.assertEqual((c["family_size"], c["floor_confidence"]), (fam["size"], fam["floor_confidence"]))
            self.assertNotIn("n_comparisons", c)
        out = self.fs.format_dry_run(plan)
        self.assertIn(f"{fam['size']} candidate procedures", out)
        self.assertIn(f"1 - 0.1/{fam['size']} = {fam['floor_confidence']:.6f}", out)
        self.assertIn("Holm", out)
        self.assertNotIn("one-sided confidence 1 - 0.1/87", out)
        self.assertIn("grid values disclosed, NOT in the family", out)

    def test_the_family_counts_declared_cells_not_the_ones_that_survived_the_data_gate(self):
        for s in ("US500", "US30", "USTEC", "DE40", "FRA40"):
            self.first[(s, "1m")] = "2024-06-01T00:00:00Z"                  # the indices 1m cell has no development history
        plan = self.fs.build_plan(FIXTURES)
        self.assertEqual(plan["family"]["size"], len(json.load(open(os.path.join(FIXTURES, "fund-search-cells.json")))["cells"]) * 2)
        self.assertGreater(plan["family"]["size"], plan["candidate_count"])

    def test_declaration_records_the_family_and_run_refuses_when_it_differs(self):
        plan = self._plan()
        with mock.patch.object(self.fs, "check_clean_tree", lambda allow_dirty=False, root=None: []):
            decl = self.fs.cmd_declare(allow_dirty=True)
        self.assertEqual((decl["family_size"], decl["floor_confidence"]), (plan["family"]["size"], plan["family"]["floor_confidence"]))
        self.assertEqual(decl["family_members"], plan["family"]["members"])
        self.assertNotIn("n_by_method", decl)
        self.assertEqual(decl["cell_count"], plan["cell_count"])                 # cell_count keeps its meaning
        self.assertEqual(decl["evaluation_config"]["family"], plan["family"])
        self.assertEqual(self.fs.require_declaration(plan)["family_size"], plan["family"]["size"])
        data = json.load(open(self.ledger))
        data["fund_search"]["family_size"] = 205
        json.dump(data, open(self.ledger, "w"))
        with self.assertRaises(SystemExit):
            self.fs.require_declaration(plan)

    def test_report_applies_holm_over_the_whole_family_and_states_the_report_only_placebo(self):
        plan = self._records(self._plan(), [0.6, 0.0, 0.6])                   # 3 of the planned candidates are evaluated
        md = self.fs.cmd_report()
        fam = plan["family"]
        self.assertIn(f"Holm step-down over the family of {fam['size']}", md)
        rows = [ln for ln in md.splitlines() if ln.startswith("| ") and "rejected" in ln]
        self.assertEqual(len(rows), fam["size"])                              # one row per PLANNED candidate, NOT RUN included
        self.assertTrue(any("NOT RUN" in ln and "not rejected" in ln and "counts as 1" in ln for ln in rows))
        self.assertNotIn("NOT IMPLEMENTED", md)                               # b28: the placebo is implemented (report-only)
        self.assertIn("a PASS requires nothing from it", md)
        self.assertRegex(md, r"\*\*Build:\*\* git `[0-9a-f]{12}`")
        self.assertIn("Minimum detectable edge", md)
        self.assertIn("Upper confidence bound on the edge", md)
        self.assertIn("Every check, with its margin", md)
        self.assertIn("Fold by fold", md)
        self.assertIn("Stability of the chosen values per perturbation component (changes between consecutive folds): a.a", md)
        self.assertIn("Categorical flips (REPORTED, never gated)", md)
        self.assertIn("Stress gate", md)
        self.assertIn("prop_pass_probability with R shifted down by", md)
        self.assertIn("REPORT-ONLY, not a gate (owner decision 2026-10-02)", md)
        self.assertIn("NOMINATION for a separately pre-registered forward demo", md)
        self.assertIn("Placebo: no figure in this record", md)               # these stub engines offer no placebo: said, not omitted
        self.assertIn("NOT folded into the family", md)
        self.assertNotIn("PROPOSED, NOT DECIDED", md)
        self.assertIn("highest primary bound at the floor confidence", md)

    def test_a_floor_pass_is_confirmed_by_holm_and_counted_and_a_floor_failure_never_is(self):
        plan = self._records(self._plan(), [0.6, 0.0])
        md = self.fs.cmd_report()
        self.assertIn("**1 of 2 evaluated candidates passed:**", md)
        self.assertIn(plan["candidates"][0]["id"], md.split("candidates passed:**")[1].splitlines()[0])
        self.assertNotIn(plan["candidates"][1]["id"], md.split("candidates passed:**")[1].splitlines()[0])
        self.assertIn("A candidate that fails the floor is never reported as a pass", md)

    def test_holm_rescue_of_a_floor_failure_is_not_a_pass_through_cmd_report(self):
        """Candidate A: tiny p, floor pass. Candidate B: every other check ok, but p between the floor 0.10/6 and Holm's
        rank-2 threshold 0.10/5, i.e. Holm rejects it at rank 2 while it FAILS the floor. cmd_report must NOT pass B and must
        list it under 'would reject, but the floor fails (NOT a pass)'."""
        plan = self._plan()
        size = plan["family"]["size"]                                       # the fixture family (12); the real one is 6
        floor_p, rank2_p = 0.10 / size, 0.10 / (size - 1)                    # real family: 0.01667 and 0.02
        p_b = (floor_p + rank2_p) / 2                                       # above the floor, below Holm's rank-2 threshold
        self.assertTrue(floor_p < p_b < rank2_p)
        grids, paths = self.fs.load_grids(FIXTURES)
        os.makedirs(self.records, exist_ok=True)
        for c, p_target in zip(plan["candidates"][:2], (1e-9, p_b)):
            cell = dict(next(x for x in plan["cells"] if x["id"] == c["cell"]), development_start=LONG_START)
            eng = SynthEngine(mean=0.6, symbols=cell["symbols"])
            res = self.fs.evaluate_with_engine(eng, grid_two_items(), cell, c["family_size"], axes={"a": TEST_AXES["a"]})
            self.assertEqual(res["verdict"], FS.PASS)                          # every check ok before the tamper
            if p_target == p_b:                                                  # B: only the floor test fails, p sits at p_b
                res["primary"]["p_robust"] = p_b
                res["checks"]["lower_bound_positive"]["ok"] = False
                res["verdict"] = FS.FAIL
                res["failed_checks"] = ["lower_bound_positive"]
            else:
                res["primary"]["p_robust"] = p_target
            rec = self.fs.build_record(c, plan["plan_hash"], grids[c["method"]], paths[c["method"]], res,
                                       {"snapshot_id": "t", "series": []}, cell)
            X.write(types.MappingProxyType(dict(rec)), store=self.records)
        a_id, b_id = plan["candidates"][0]["id"], plan["candidates"][1]["id"]
        md = self.fs.cmd_report()
        holm_rows = {ln.split("|")[2].strip(): ln for ln in md.splitlines() if ln.startswith("| ") and "rejected" in ln}
        self.assertIn("| rejected |", holm_rows[a_id])
        self.assertIn("| rejected |", holm_rows[b_id])                            # Holm DOES reject B at rank 2 ...
        passed_line = next(ln for ln in md.splitlines() if "evaluated candidates passed:**" in ln)
        self.assertIn(a_id, passed_line)
        self.assertNotIn(b_id, passed_line)                                      # ... and B is still NOT a pass
        self.assertIn("**1 of 2 evaluated candidates passed:**", md)
        holm_only_line = next(ln for ln in md.splitlines() if "Holm would reject, but the floor fails (NOT a pass)" in ln)
        self.assertIn(b_id, holm_only_line)
        self.assertNotIn(a_id, holm_only_line)

    def test_holm_only_rejections_are_listed_but_do_not_pass(self):
        plan = self._plan()
        by = plan["candidates"][:2]
        # two evaluated candidates whose p_robust sit between the floor and Holm's rank-2 threshold: p = 0.001 and 0.018
        recs = {}
        for c, p in zip(by, (0.001, 0.018)):
            fake = {"experiment_id": c["id"], "parameters": {"plan_hash": plan["plan_hash"], "symbols_evaluated": c["symbols"]},
                    "metrics": {"evaluation": {"checks": {k: {"ok": True} for k in FS.REQUIRED_CHECKS}, "primary": {"p_robust": p}}}}
            fake["metrics"]["evaluation"]["checks"]["lower_bound_positive"] = {"ok": p < 0.10 / plan["family"]["size"]}
            recs[c["id"]] = fake
        verdicts = {cid: FS.verdict_from(r["metrics"]["evaluation"]["checks"]) for cid, r in recs.items()}
        holm = {r["id"]: r for r in FS.holm_stepdown({cid: r["metrics"]["evaluation"]["primary"]["p_robust"] for cid, r in recs.items()},
                                                    plan["family"]["size"])}
        lines = self.fs.report_holm_lines(plan["candidates"], {k: v for k, v in verdicts.items()}, holm, plan["family"],
                                          [by[1]["id"]], [])
        txt = "\n".join(lines)
        self.assertIn("Holm would reject, but the floor fails (NOT a pass)", txt)
        self.assertIn(by[1]["id"], txt)


if __name__ == "__main__":
    unittest.main()
