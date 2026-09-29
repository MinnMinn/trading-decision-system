"""The fund-setup harness (docs/plans/2026-09-28-methodology-improvement-plan.md §1.4) -- adversarial tests.

Research integrity is the product: a no-edge strategy must NOT pass at N = 205 while a large true edge must; V
values chosen on a training fold must never see the test fold (the test fold's data is POISONED to prove it); the
lower bound must use pooled TEST trades only; a fold with 29 trades is "insufficient"; one huge trade cannot carry a
result; the run refuses without the ledger declaration; nothing is dropped after results are seen; a run with zero
passes says so. All data is synthetic -- no real history is evaluated here (that is Batch 3).

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_fund_search
"""
import copy
import datetime
import importlib.util
import io
import json
import math
import os
import random
import shutil
import sys
import tempfile
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


SYMS = ["XAUUSD", "XAGUSD", "US500", "US30", "USTEC", "DE40", "FRA40"]
DEV_START = "2020-03-01T00:00:00Z"


def gen(start, end, n, mean, sd, seed, symbols=SYMS, extra=None):
    """n trades evenly spread over [start, end), R ~ N(mean, sd), ADX random in [10, 40]."""
    rng = random.Random(seed)
    a, b = FS.ts(start), FS.ts(end)
    span = (b - a) / n
    out = []
    for i in range(n):
        t = a + span * (i + 0.5)
        tr = {"entry_time": FS.iso(t), "exit_time": FS.iso(t + datetime.timedelta(hours=2)),
              "net_R": rng.gauss(mean, sd), "symbol": symbols[i % len(symbols)], "adx14": rng.uniform(10, 40)}
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


def _seed(values):
    return hash(json.dumps(values, sort_keys=True)) & 0xFFFF   # only used inside one process


class SynthEngine:
    """trades_for(values) over the development span; every distinct V assignment draws its OWN sample."""

    def __init__(self, mean=0.0, sd=1.0, per_year=150, prop=None, mean_by=None, symbols=SYMS, salt=0):
        self.salt = salt
        self.mean, self.sd, self.per_year, self.symbols = mean, sd, per_year, symbols
        self.prop = prop if prop is not None else {"ftmo": 0.9, "the5ers": 0.9}
        self.mean_by = mean_by or (lambda values: mean)
        self.calls = []

    def trades_for(self, values):
        self.calls.append(dict(values))
        years = 4
        return gen(DEV_START, FS.DEV_CUTOFF, self.per_year * years, self.mean_by(values), self.sd,
                   seed=f"{self.salt}:" + json.dumps(values, sort_keys=True), symbols=self.symbols)

    def prop_pass(self, pooled):
        return dict(self.prop)

    def admission_stats(self, values, fold=None):
        rows = [{"entry_time": t["entry_time"], "R_planned": 3.0 + (i % 5) * 0.1, "fee_R": 0.05 * (i % 7)}
                for i, t in enumerate(self.trades_for(values))]
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

    def test_neighbours_numeric_sorted_categorical_listed(self):
        self.assertEqual(FS.neighbours([12, 8, 16], 12), [(-1, 8), (+1, 16)])
        self.assertEqual(FS.neighbours([12, 8, 16], 8), [(+1, 12)])
        self.assertEqual(FS.neighbours(["IOFED", "CE", "Fill"], "CE"), [(-1, "IOFED"), (+1, "Fill")])
        self.assertEqual(FS.neighbours([False, True], False), [(+1, True)])


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

        res = FS.nested_walk_forward(grid, FS.CountingSource(trades_for), folds)
        self.assertEqual([r["chosen"]["a"] for r in res], ["y", "y"])
        # ... and the selected values are unchanged when the test fold's data is replaced by garbage
        def clean(values):
            tr = trades_for(values)
            for t in FS.test_window(tr, last):
                t["net_R"] = -7.0
            return tr
        res2 = FS.nested_walk_forward(grid, FS.CountingSource(clean), folds)
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

        res = FS.nested_walk_forward(grid, FS.CountingSource(trades_for), folds)
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
        res = FS.nested_walk_forward(grid, src, folds)
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
        res = FS.nested_walk_forward(grid, FS.CountingSource(same), folds)
        self.assertTrue(all(r["changed"] == [] for r in res))         # ties keep the baseline
        sparse = lambda values: gen(DEV_START, FS.DEV_CUTOFF, 6, 3.0, 0.1, json.dumps(values, sort_keys=True))
        res = FS.nested_walk_forward(grid, FS.CountingSource(sparse), folds)
        self.assertTrue(all(r["changed"] == [] for r in res))         # < MIN_TRAIN_TRADES: not eligible

    def test_every_distinct_run_is_counted(self):
        grid = grid_two_items()
        folds = FS.make_folds(DEV_START)
        src = FS.CountingSource(lambda v: gen(DEV_START, FS.DEV_CUTOFF, 300, 0.0, 1.0, json.dumps(v, sort_keys=True)))
        FS.nested_walk_forward(grid, src, folds)
        self.assertGreaterEqual(src.runs, 1 + 2 + 1)                  # baseline + non-baseline a (2) + b (1)


# ============================================================================ the pass / fail decision, end to end
class EndToEndVerdicts(unittest.TestCase):
    def _run(self, engine, n=205):
        fs = _fs()
        cell = {"id": "5m-indices", "symbols": SYMS, "development_start": DEV_START}
        return fs.evaluate_with_engine(engine, grid_two_items(), cell, n)

    def test_no_edge_strategy_does_not_pass_at_n_205(self):
        # many independent seeds: an edge-less strategy must never sneak through the strict gate
        for salt in range(6):
            ev = self._run(SynthEngine(mean=0.0, sd=1.0, salt=salt))
            self.assertNotEqual(ev["verdict"], FS.PASS)
            self.assertIn("lower_bound_positive", ev["failed_checks"])

    def test_large_true_edge_passes_at_n_205(self):
        ev = self._run(SynthEngine(mean=0.6, sd=1.0))
        self.assertEqual(ev["verdict"], FS.PASS, ev["failed_checks"])
        self.assertEqual(ev["failed_checks"], [])
        self.assertAlmostEqual(ev["confidence"], 1 - 0.10 / 205)
        self.assertGreater(ev["runs_evaluated"], 4)

    def test_a_failing_candidate_reports_every_reason_not_just_the_first(self):
        ev = self._run(SynthEngine(mean=-0.2, sd=1.0, prop={"f": 0.1}))
        for k in ("lower_bound_positive", "stability", "regime_split", "perturbation", "prop_pass_probability"):
            self.assertIn(k, ev["failed_checks"])

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
                "net_R": r, "adx14": adx}

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
        self.exp = os.path.join(self.tmp, "exp")
        self.records = os.path.join(self.exp, "records")
        os.makedirs(self.exp)
        patches = [mock.patch.object(self.fs, "EXPERIMENT_DIR", self.exp),
                   mock.patch.object(self.fs, "PLAN_PATH", os.path.join(self.exp, "plan.json")),
                   mock.patch.object(self.fs, "RECORDS_DIR", self.records),
                   mock.patch.object(self.fs, "REPORT_PATH", os.path.join(self.tmp, "report.md")),
                   mock.patch.object(self.fs, "GRID_DIR", FIXTURES),
                   mock.patch.object(self.fs.RL, "PATH", self.ledger),
                   mock.patch.object(self.fs, "_first_bar", self._first_bar)]
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
        self.assertEqual(p["cell_count"], 8)
        self.assertEqual(p["n_by_method"], {"ict": 41 * 8, "wyckoff": 16 * 8})
        self.assertAlmostEqual(p["confidence_by_method"]["ict"], 1 - 0.10 / (41 * 8))
        self.assertEqual(p["candidate_count"], 16)
        self.assertNotIn("AUS200", json.dumps(p["cells"]))                # plan §6 item 8
        self.assertEqual({c["timeframe"] for c in p["cells"]}, {"1m", "5m", "15m", "30m"})

    def test_a_cell_without_development_history_is_excluded_and_a_symbol_is_listed_not_forgotten(self):
        for s in ("US500", "US30", "USTEC", "DE40", "FRA40"):
            self.first[(s, "1m")] = "2024-06-01T00:00:00Z"               # indices 1m start AFTER the cutoff
        self.first[("XAGUSD", "5m")] = "2025-01-01T00:00:00Z"
        p = self.plan()
        self.assertEqual(p["cell_count"], 7)
        self.assertEqual([e["id"] for e in p["excluded_cells"]], ["1m-indices"])
        c5 = next(c for c in p["cells"] if c["id"] == "5m-metals")
        self.assertEqual(c5["symbols"], ["XAUUSD"])
        self.assertIn("XAGUSD", c5["symbols_without_development"])         # m excludes it, but it is disclosed
        self.assertEqual(p["n_by_method"]["ict"], 41 * 7)

    def test_dry_run_prints_n_and_confidence_and_writes_nothing(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.fs.cmd_plan(dry_run=True, grid_dir=FIXTURES)
        out = buf.getvalue()
        self.assertIn("N 328", out)
        self.assertIn("1 - 0.1/328", out)
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
        self.assertEqual(self.fs.COST_PROFILE, "ftmo_demo_2026_09")

    def test_scope_is_the_seven_symbols(self):
        self.assertEqual(self.fs.FUND_SYMBOLS, ("XAUUSD", "XAGUSD", "US500", "US30", "USTEC", "DE40", "FRA40"))


class _Helpers(_Tmp):
    def _plan_file(self):
        self.fs.cmd_plan(grid_dir=FIXTURES)
        return json.load(open(self.fs.PLAN_PATH))

    def _fake_out(self, c, plan_hash, mean=0.0):
        grids, paths = self.fs.load_grids(FIXTURES)
        plan = json.load(open(self.fs.PLAN_PATH))
        cell = next(x for x in plan["cells"] if x["id"] == c["cell"])
        cell = dict(cell, development_start=DEV_START)
        eng = SynthEngine(mean=mean)
        grid = grid_two_items()
        res = self.fs.evaluate_with_engine(eng, grid, cell, c["n_comparisons"])
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
        self.assertEqual(after["fund_search"]["cell_count"], 8)
        self.assertEqual(after["oos"], before["oos"])                     # no window / period changed
        self.assertEqual(after["budget"], before["budget"])

    def test_declare_refuses_once_records_exist(self):
        self._plan_file()
        os.makedirs(self.records)
        open(os.path.join(self.records, "x.json"), "w").write("{}")
        with self.assertRaises(SystemExit) as cm:
            self.fs.cmd_declare()
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
        self.assertIn("NOT RUN: **12**", md)                                  # the rest of the plan is disclosed
        self.assertIn("Incomplete", md)
        self.assertIn("N 328".replace("N 328", "**328**"), md)
        self.assertIn("NOT folded into N", md)

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
        self.assertLessEqual(lb["value"], 0)
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
            self.assertLessEqual(lb["value"], lb["iid"] + 1e-12)
            self.assertLessEqual(lb["value"], lb["block_date"] + 1e-12)
            self.assertLessEqual(lb["value"], lb["block_30d"] + 1e-12)

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
                         {"value": 0.8, "low_confidence": True, "spread_min": 0.6})
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
            fs.checked_simulate(bt, self._trades(), 0.0)
        self.assertIn("never lose trades silently", str(cm.exception))
        fs.neutralise_ruin(bt)
        taken = fs.checked_simulate(bt, self._trades(), 0.0)[2]
        self.assertEqual(len(taken), 6)

    def test_post_ruin_trades_fail_loud_even_without_a_ruin_stamp(self):
        fs = _fs()
        bt = mock.Mock()
        bt.simulate.return_value = (1.0, [], [])
        bt.SIM_LAST = {"post_ruin": [{"symbol": "X"}], "ruin": None}
        with self.assertRaises(RuntimeError):
            fs.checked_simulate(bt, [], 0.0)

    def test_a_trade_held_over_the_server_rollover_fails_loud(self):
        fs = _fs()
        prov = "mt5_bridge_ftmo"
        held = {"symbol": "X", "entry_time": "2022-01-10T20:00:00Z", "exit_time": "2022-01-10T23:00:00Z"}
        flat = {"symbol": "X", "entry_time": "2022-01-10T19:00:00Z", "exit_time": "2022-01-10T21:30:00Z"}
        fs.assert_no_rollover_crossing([flat], prov)
        with self.assertRaises(RuntimeError):
            fs.assert_no_rollover_crossing([flat, held], prov)


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
        self.assertEqual(set(o), {"fx_ok", "flat_before_rollover", "rollover_provider"})
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
        cell = {"id": "5m-metals", "symbols": SYMS, "development_start": DEV_START}
        res = self.fs.evaluate_with_engine(SynthEngine(mean=0.0), grid_two_items(), cell, 205)
        adm = res["admission"]
        self.assertEqual(len(adm["by_fold_chosen"]), 2)
        self.assertIn("EXIT-hour spread", adm["limitation"])
        self.assertIn("OPEN owner item", adm["limitation"])
        self.assertTrue(adm["by_value_set"])


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


if __name__ == "__main__":
    unittest.main()
