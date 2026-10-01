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
        years = 10
        return gen(LONG_START, FS.DEV_CUTOFF, self.per_year * years, self.mean_by(values), self.sd,
                   seed=f"{self.salt}:" + json.dumps(values, sort_keys=True), symbols=self.symbols)

    def prop_pass(self, pooled):
        return dict(self.prop)

    def rollover_edge_stats(self, values, fold=None):
        return _fs().rollover_edge_stats([t["entry_time"] for t in self.trades_for(values)][:7], fold)

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
    def _run(self, engine, n=205):
        fs = _fs()
        cell = {"id": "5m-indices", "timeframe": "5m", "symbols": SYMS, "development_start": LONG_START}
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
        self.assertEqual(p["cell_count"], 6)                               # owner 2026-10-01: the 30m cells are removed
        self.assertEqual(p["n_by_method"], {"ict": 41 * 6, "wyckoff": 16 * 6})
        self.assertAlmostEqual(p["confidence_by_method"]["ict"], 1 - 0.10 / (41 * 6))
        self.assertEqual(p["candidate_count"], 12)
        self.assertNotIn("AUS200", json.dumps(p["cells"]))                # plan §6 item 8
        self.assertEqual({c["timeframe"] for c in p["cells"]}, {"1m", "5m", "15m"})

    def test_a_cell_without_development_history_is_excluded_and_a_symbol_is_listed_not_forgotten(self):
        for s in ("US500", "US30", "USTEC", "DE40", "FRA40"):
            self.first[(s, "1m")] = "2024-06-01T00:00:00Z"               # indices 1m start AFTER the cutoff
        self.first[("XAGUSD", "5m")] = "2025-01-01T00:00:00Z"
        p = self.plan()
        self.assertEqual(p["cell_count"], 5)
        self.assertEqual([e["id"] for e in p["excluded_cells"]], ["1m-indices"])
        c5 = next(c for c in p["cells"] if c["id"] == "5m-metals")
        self.assertEqual(c5["symbols"], ["XAUUSD"])
        self.assertIn("XAGUSD", c5["symbols_without_development"])         # m excludes it, but it is disclosed
        self.assertEqual(p["n_by_method"]["ict"], 41 * 5)

    def test_dry_run_prints_n_and_confidence_and_writes_nothing(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.fs.cmd_plan(dry_run=True, grid_dir=FIXTURES)
        out = buf.getvalue()
        self.assertIn("N 246", out)
        self.assertIn("1 - 0.1/246", out)
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
        cell = dict(cell, development_start=LONG_START)
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
        self.assertIn("**246**", md)
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
            fs.checked_simulate(bt, self._trades(), 0.0, overlay=fs.fixed_opts())
        self.assertIn("never lose trades silently", str(cm.exception))
        fs.neutralise_ruin(bt)
        taken = fs.checked_simulate(bt, self._trades(), 0.0, overlay=fs.fixed_opts())[2]
        self.assertEqual(len(taken), 6)

    def test_post_ruin_trades_fail_loud_even_without_a_ruin_stamp(self):
        fs = _fs()
        bt = mock.Mock()
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
            self.assertIn("declared, not runnable, counted in N: ['B-EX']", buf.getvalue())
            self.assertIn("N 246", buf.getvalue())                          # still counted in N
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

    def test_the_committed_cells_file_declares_exactly_six_cells_and_no_30m(self):
        spec, path, sha = self.fs.load_cells_file(REAL_ARCH)
        self.assertEqual([c["id"] for c in spec["cells"]],
                         ["1m-metals", "1m-indices", "5m-metals", "5m-indices", "15m-metals", "15m-indices"])
        self.assertFalse(any("30m" in c["id"] or c["timeframe"] == "30m" for c in spec["cells"]))
        self.assertEqual([r["id"] for r in spec["removed_cells"]], ["30m-metals", "30m-indices"])
        self.assertEqual(sha, hashlib.sha256(open(path, "rb").read()).hexdigest())
        p = self.fs.build_plan(REAL_ARCH, first_bar=self._first_bar)
        self.assertEqual(p["cell_count"], 6)
        self.assertEqual(p["candidate_count"], 12)
        self.assertFalse(any(c["timeframe"] == "30m" for c in p["candidates"]))
        self.assertEqual(p["n_by_method"], {"ict": 29 * 6, "wyckoff": 16 * 6})
        self.assertEqual(p["cells_file"]["sha256"], sha)

    def test_the_committed_cells_keep_their_original_data_start_and_the_fold_counts_the_owner_listed(self):
        p = self.fs.build_plan(REAL_ARCH, first_bar=self._first_bar)
        self.assertEqual(self._folds(p), {"1m-metals": 9, "1m-indices": 4, "5m-metals": 17, "5m-indices": 4,
                                          "15m-metals": 17, "15m-indices": 4})
        self.assertTrue(all(c["dev_start_override"] is None and c["span_source"] == "from data" for c in p["cells"]))

    def test_the_fixture_cells_file_has_the_same_six_cells(self):
        self.assertEqual([c["id"] for c in self.plan()["cells"]],
                         [c["id"] for c in self.fs.load_cells_file(REAL_ARCH)[0]["cells"]])

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


@unittest.skipUnless(os.path.isdir(os.path.join(ROOT, "data", "history", "ftmo", "ohlcv.XAUUSD.15m")),
                     "data/history/ftmo is not present")
class EngineDevStart(unittest.TestCase):
    """BtEngine(dev_start=...): no trade before dev_start exists, and what is left equals the full-series run."""

    @classmethod
    def setUpClass(cls):
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


class AdoptedFKeys(unittest.TestCase):
    """Owner adoption 2026-09-30 (docs/plans/2026-09-30-owner-decisions.md): the nine F items are ON in every cell."""

    @classmethod
    def setUpClass(cls):
        cls.fs = _fs()

    def test_the_nine_keys_are_in_every_overlay_and_are_engine_keys_that_default_off(self):
        bt = self.fs._load_bt()
        self.assertEqual(len(self.fs.ADOPTED_F_KEYS), 10)              # nine F items + O1 fx_admission_entry_cost
        self.assertIn("fx_admission_entry_cost", self.fs.ADOPTED_F_KEYS)
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
                    "cells_file": {"sha256": "c" * 8, "warmup_days": 14}}
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


if __name__ == "__main__":
    unittest.main()
