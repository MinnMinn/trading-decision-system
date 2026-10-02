"""Report-only obligations of the sealed fund search (pre-registration section C): the PLACEBO benchmark (item 6), the per-year /
fold table and the data DISCLOSURE header. Synthetic data only: random-walk bars written to a temp history root, hand-built trades;
no R / expectancy of any real evaluation is read (the one real-data check reads FIRST-BAR LABELS and the export bar count only).

Report-only means: no check, margin, verdict or Holm step may read any of it (`test_*_changes_no_verdict`).

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_fund_search_report_obligations
"""
import bisect
import datetime
import gzip
import importlib.util
import json
import os
import random
import shutil
import sys
import tempfile
import types
import unittest
import unittest.mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "tests"))
import fund_stats as FS
import real_costs
import test_fund_search as TFS          # SynthEngine, grid_two_items, TEST_AXES, gen: the same stubs the report tests use

REAL_ARCH = os.path.join(ROOT, "docs", "architecture")


def _fs():
    spec = importlib.util.spec_from_file_location("fund_search_mod_ro", os.path.join(ROOT, "scripts", "fund-search.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _walk_candles(start, end, seed, minutes=15, skip_hour=None, p0=2000.0, sd=1.6):
    """A random walk (no drift) of `minutes` bars from `start` (inclusive) to `end` (exclusive); bars of `skip_hour` (UTC) are absent."""
    rng = random.Random(seed)
    t, stop = FS.ts(start), FS.ts(end)
    step = datetime.timedelta(minutes=minutes)
    price, out = p0, []
    while t < stop:
        if t.hour != skip_hour:
            o = price
            c = o + rng.gauss(0.0, sd)
            hi = max(o, c) + abs(rng.gauss(0.0, sd * 0.4))
            lo = min(o, c) - abs(rng.gauss(0.0, sd * 0.4))
            out.append({"time": FS.iso(t), "open": round(o, 2), "high": round(hi, 2), "low": round(lo, 2),
                        "close": round(c, 2), "volume": 10})
            price = c
        t += step
    return out


def fake_placebo(fold_results, grid, key):
    """A stub engine's `placebo_trades`: placebo 0.0 R for every real trade, one skipped per fold."""
    return [{"test_start": fr["fold"]["test_start"], "real": [t["net_R"] for t in fr["test_trades"]],
             "placebo": [0.0] * len(fr["test_trades"]), "skipped": {"min_rr": 1}} for fr in fold_results]


# =============================================================================================== pure statistics
class PlaceboStatistics(unittest.TestCase):
    def test_the_seed_is_stable_and_depends_on_every_part(self):
        a = FS.stable_seed("s", "k", 1)
        self.assertEqual(a, FS.stable_seed("s", "k", 1))
        self.assertNotEqual(a, FS.stable_seed("s", "k", 2))
        self.assertNotEqual(a, FS.stable_seed("s", "j", 1))
        self.assertEqual(FS.stable_seed("x"), 0x2d711642b726b044)        # pinned: a change of the hash recipe is a visible event

    def test_hour_buckets(self):
        trades = [{"entry_time": f"2022-01-03T{h:02d}:30:00Z"} for h in (0, 5, 6, 11, 12, 17, 18, 23, 23, 3)]
        self.assertEqual([FS.hour_bucket(t["entry_time"]) for t in trades], [0, 0, 1, 1, 2, 2, 3, 3, 3, 0])
        self.assertEqual(FS.hour_bucket_shares(trades), [0.3, 0.2, 0.2, 0.3])
        self.assertIsNone(FS.hour_bucket_shares([]))

    def test_fold_year_row_values(self):
        trades = [{"entry_time": "2022-01-03T01:00:00Z", "net_R": 1.0, "R_planned": 4.0},
                  {"entry_time": "2022-01-03T13:00:00Z", "net_R": -1.0, "R_planned": 2.0},
                  {"entry_time": "2022-01-03T14:00:00Z", "net_R": 0.5, "R_planned": 5.0},
                  {"entry_time": "2022-01-03T20:00:00Z", "net_R": 0.0, "R_planned": None}]
        stress = [dict(t, net_R=t["net_R"] - 0.1) for t in trades]
        row = FS.fold_year_row("2022-03-01T00:00:00Z", trades, mean_spread_r=0.05, spread_r_each=[0.2, 0.2, 0.5, 0.3],
                               stress_trades=stress)
        self.assertEqual(row["n_trades"], 4)
        self.assertAlmostEqual(row["mean_net_R"], 0.125)
        self.assertAlmostEqual(row["mean_stress_R"], 0.025)
        self.assertEqual(row["mean_spread_R"], 0.05)
        self.assertEqual(row["hour_share"], [0.25, 0.0, 0.5, 0.25])
        self.assertEqual(row["cost_regime_n"], 3)                          # the trade without R_planned is not in the mean
        self.assertAlmostEqual(row["cost_regime_ratio"], (0.2 / 4 + 0.2 / 2 + 0.5 / 5) / 3)
        empty = FS.fold_year_row("x", [])
        self.assertEqual((empty["n_trades"], empty["mean_net_R"], empty["hour_share"]), (0, None, None))

    def test_bootstrap_is_deterministic_and_separates_a_real_difference(self):
        rng = random.Random(1)
        same = [{"n_real": 100, "sum_real": rng.gauss(0, 8), "n_pl": 100, "sum_pl": rng.gauss(0, 8)} for _ in range(8)]
        a, b = FS.block_bootstrap(same, "k"), FS.block_bootstrap(same, "k")
        self.assertEqual(a, b)
        self.assertNotEqual(a, FS.block_bootstrap(same, "other-key"))
        self.assertLess(a["diff"][0], 0.0)
        self.assertGreater(a["diff"][1], 0.0)                                   # no difference: the interval straddles 0
        planted = [{"n_real": 100, "sum_real": 60.0 + i, "n_pl": 100, "sum_pl": -5.0 + i} for i in range(8)]
        c = FS.block_bootstrap(planted, "k")
        self.assertGreater(c["diff"][0], 0.5)                                   # a +0.65 R/trade difference excludes 0
        self.assertIsNone(FS.block_bootstrap(planted[:1], "k"))                 # one block: no interval

    def test_summary_pools_the_folds(self):
        rows = [{"test_start": "2022-03-01T00:00:00Z", "real": [1.0, 3.0], "placebo": [0.0], "skipped": {"min_rr": 1}},
                {"test_start": "2023-03-01T00:00:00Z", "real": [-1.0], "placebo": [-1.0, 1.0], "skipped": {"min_rr": 2, "zero_risk": 1}}]
        s = FS.placebo_summary(rows, "k")
        self.assertEqual(s["pooled"]["n_real"], 3)
        self.assertEqual(s["pooled"]["n_placebo"], 3)
        self.assertAlmostEqual(s["pooled"]["mean_real"], 1.0)
        self.assertAlmostEqual(s["pooled"]["mean_placebo"], 0.0)
        self.assertAlmostEqual(s["pooled"]["diff"], 1.0)
        self.assertEqual(s["skipped"], {"min_rr": 3, "zero_risk": 1})
        self.assertEqual(s["skipped_total"], 4)
        self.assertEqual(s["seed"], FS.PLACEBO_SEED)
        self.assertTrue(s["report_only"])


# ===================================================================================== the engine placebo (real BtEngine)
class _PlaceboEngineBase(unittest.TestCase):
    """The REAL BtEngine on a temp history root of a synthetic XAUUSD 15m random walk; no scan is run, the 'real' trades are built by hand."""

    DEV_START = "2018-03-01T00:00:00Z"          # 4 test folds (2020-03 .. 2024-03)
    SKIP_HOUR = 3                                # the synthetic market is shut 03:00-03:59 UTC

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="placebo-")
        cls.env = os.environ.get("BT_HISTORY_ROOT")
        hist = os.path.join(cls.tmp, "hist")
        os.makedirs(hist)
        cls.candles = _walk_candles("2018-01-01T00:00:00Z", "2024-02-29T00:00:00Z", seed=7, skip_hour=cls.SKIP_HOUR)
        with open(os.path.join(hist, "ohlcv.XAUUSD.15m.json"), "w", encoding="utf-8") as fh:
            json.dump({"symbol": "XAUUSD", "timeframe": "15m", "_source": "synthetic", "candles": cls.candles}, fh)
        os.environ["BT_HISTORY_ROOT"] = hist
        cls.fs = _fs()
        grids, _ = cls.fs.load_grids(REAL_ARCH)
        cls.grid = grids["ict"].runnable()
        cls.engine = cls.fs.BtEngine(cls.grid, "ICT", "15m", ["XAUUSD"], workers=1)
        cls.folds = FS.make_folds(cls.DEV_START)
        cls.ser = cls.fs.PlaceboSeries(cls.engine.bt.load("XAUUSD", "15m")[0])

    @classmethod
    def tearDownClass(cls):
        if cls.env is None:
            os.environ.pop("BT_HISTORY_ROOT", None)
        else:
            os.environ["BT_HISTORY_ROOT"] = cls.env
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # -- helpers
    def overlay(self):
        return self.fs.build_overlay(self.grid, self.grid.baseline())

    def make_real(self, fold, rng, informed=False, n=100, dist=8.0, rp=3.0):
        """Hand-built 'real' test trades: entry at a random bar of the fold, walked and priced by the SAME functions as the placebo.
        `informed` chooses the side by LOOKING AHEAD (24 bars): a planted edge no honest strategy has."""
        import real_costs as RC
        out = []
        lo = bisect.bisect_left(self.ser.Tm, fold["test_start"])
        hi = bisect.bisect_left(self.ser.Tm, fold["test_end"]) - 300
        sim = self.fs.simulate_time_opts(self.engine.bt, self.overlay())
        with self.fs.bt_opts(self.engine.bt, self.overlay()) as opts:
            hz = self.fs.placebo_horizon(self.engine.bt, "ICT", "15m", opts, self.ser.n)
            while len(out) < n:
                b = rng.randrange(lo, hi)
                if informed:
                    side = "long" if self.ser.C[b + 24] > self.ser.O[b] else "short"
                else:
                    side = "long" if rng.random() < 0.5 else "short"
                pt, why = self.fs.placebo_trade(self.engine.bt, self.ser, "XAUUSD", b, side, dist, rp, hz, sim["min_rr"],
                                                bool(sim.get("fx_admission_entry_cost")), RC)
                if pt is None:
                    continue
                out.append(dict(pt, tf="15m", event=f"XAUUSD-{side}-ict-{b}"))
        return out

    def fold_results(self, per_fold):
        return [{"fold": f, "chosen": self.grid.baseline(), "test_trades": tr} for f, tr in zip(self.folds, per_fold)]


class PlaceboConstruction(_PlaceboEngineBase):
    def test_the_series_has_no_bar_in_the_shut_hour_and_the_window_bisect_is_exact(self):
        f = self.folds[0]
        c = self.ser.candidates(10, f["test_start"], f["test_end"])
        self.assertTrue(c)
        self.assertTrue(all(f["test_start"] <= self.ser.Tm[i] < f["test_end"] and self.ser.Tm[i][11:13] == "10" for i in c))
        self.assertEqual(self.ser.candidates(self.SKIP_HOUR, f["test_start"], f["test_end"]), [])
        # every bar of that hour inside the window, none outside it
        want = [i for i, t in enumerate(self.ser.Tm) if t[11:13] == "10" and f["test_start"] <= t < f["test_end"]]
        self.assertEqual(c, [i for i in want if i + 1 < self.ser.n])
        self.assertNotIn(self.ser.n - 1, self.ser.candidates(23, "2024-02-01T00:00:00Z", "2024-03-01T00:00:00Z"))   # no bar to walk

    def test_same_stop_distance_r_planned_hour_symbol_fold_and_both_sides(self):
        rng = random.Random(3)
        real = self.make_real(self.folds[1], rng, n=150, dist=9.5, rp=3.2)
        import real_costs as RC
        sim = self.fs.simulate_time_opts(self.engine.bt, self.overlay())
        sides, n_ok = set(), 0
        with self.fs.bt_opts(self.engine.bt, self.overlay()) as opts:
            hz = self.fs.placebo_horizon(self.engine.bt, "ICT", "15m", opts, self.ser.n)
            for r in real:
                pt, why = self.fs.placebo_for_trade(self.engine.bt, self.ser, r, self.folds[1], "k", hz, sim["min_rr"], True, RC)
                if pt is None:
                    self.assertIn(why, ("min_rr", "walk_cut_by_series_end", "zero_risk"))
                    continue
                n_ok += 1
                sides.add(pt["side"])
                self.assertAlmostEqual(abs(pt["entry"] - pt["stop"]), 9.5, places=6)               # same stop distance (price)
                self.assertAlmostEqual(pt["R_planned"], 3.2, places=6)                              # same R_planned
                self.assertAlmostEqual(abs(pt["target"] - pt["entry"]), 3.2 * 9.5, places=6)
                self.assertEqual(pt["entry_time"][11:13], r["entry_time"][11:13])                   # same UTC hour-of-day
                self.assertEqual(pt["symbol"], r["symbol"])
                self.assertTrue(self.folds[1]["test_start"] <= pt["entry_time"] < self.folds[1]["test_end"])   # same fold
                self.assertEqual(pt["entry"], self.ser.O[self.ser.Tm.index(pt["entry_time"])])      # entry = the bar's open
                self.assertEqual(pt["stop"] < pt["entry"], pt["side"] == "long")
        self.assertGreater(n_ok, 100)
        self.assertEqual(sides, {"long", "short"})

    def test_the_side_is_drawn_50_50_whatever_the_real_trades_side_is(self):
        import real_costs as RC
        rng = random.Random(4)
        longs = [dict(r, side="long") for r in self.make_real(self.folds[2], rng, n=200)]
        sim = self.fs.simulate_time_opts(self.engine.bt, self.overlay())
        sides = []
        with self.fs.bt_opts(self.engine.bt, self.overlay()) as opts:
            hz = self.fs.placebo_horizon(self.engine.bt, "ICT", "15m", opts, self.ser.n)
            for r in longs:
                pt, _ = self.fs.placebo_for_trade(self.engine.bt, self.ser, r, self.folds[2], "k", hz, sim["min_rr"], True, RC)
                if pt:
                    sides.append(pt["side"])
        self.assertGreater(len(sides), 150)
        share_long = sides.count("long") / len(sides)
        self.assertTrue(0.38 < share_long < 0.62, share_long)           # binomial se about 0.037 at n=180

    def test_the_draw_is_deterministic_independent_of_order_and_depends_on_the_candidate_key(self):
        rng = random.Random(5)
        per = [self.make_real(f, rng, n=40) for f in self.folds]
        fr = self.fold_results(per)
        first = self.engine.placebo_trades(fr, self.grid, "cellA|ICT")
        self.assertEqual(first, self.engine.placebo_trades(fr, self.grid, "cellA|ICT"))                   # same seed: same trades
        other = self.engine.placebo_trades(fr, self.grid, "cellB|WYCKOFF-BOOK")                            # another candidate in between
        self.assertNotEqual(first, other)
        self.assertEqual(first, self.engine.placebo_trades(fr, self.grid, "cellA|ICT"))                   # unaffected by it
        # fold order and trade order do not change any fold's placebo: each real trade carries its own seed
        rev = self.engine.placebo_trades(list(reversed([dict(x, test_trades=list(reversed(x["test_trades"]))) for x in fr])),
                                         self.grid, "cellA|ICT")
        by = {r["test_start"]: r for r in first}
        for r in rev:
            self.assertEqual(sorted(r["placebo"]), sorted(by[r["test_start"]]["placebo"]))
            self.assertEqual(r["skipped"], by[r["test_start"]]["skipped"])

    def test_a_trade_with_no_bar_in_its_hour_is_skipped_and_counted_not_redrawn(self):
        rng = random.Random(9)
        real = self.make_real(self.folds[0], rng, n=5)
        shut = dict(real[0], entry_time=real[0]["entry_time"][:11] + "03:15:00Z")
        res = self.engine.placebo_trades(self.fold_results([real[1:] + [shut]] + [[] for _ in self.folds[1:]]), self.grid, "k")
        self.assertEqual(res[0]["skipped"].get("no_bar_in_hour"), 1)
        self.assertEqual(len(res[0]["placebo"]) + sum(res[0]["skipped"].values()), 5)
        no_rp = dict(real[0], R_planned=None)
        self.assertEqual(self.fs.placebo_for_trade(self.engine.bt, self.ser, no_rp, self.folds[0], "k", 96, 2.5, True,
                                                   real_costs)[1], "no_R_planned")

    def test_an_outcome_cut_by_the_end_of_the_series_is_skipped(self):
        import real_costs as RC
        n = self.ser.n
        with self.fs.bt_opts(self.engine.bt, self.overlay()):
            pt, why = self.fs.placebo_trade(self.engine.bt, self.ser, "XAUUSD", n - 5, "long", 8.0, 3.0, 96, 2.5, True, RC)
        self.assertIsNone(pt)
        self.assertEqual(why, "walk_cut_by_series_end")

    def test_min_rr_admission_refuses_like_simulate(self):
        import real_costs as RC
        with self.fs.bt_opts(self.engine.bt, self.overlay()):
            # R_planned 1.0 can never clear the floor 2.5 once costs are subtracted
            pt, why = self.fs.placebo_trade(self.engine.bt, self.ser, "XAUUSD", 1000, "long", 8.0, 1.0, 96, 2.5, True, RC)
        self.assertEqual((pt, why), (None, "min_rr"))

    def test_the_walk_is_the_engines_walk_gap_fill_flat_before_rollover_and_time_stop(self):
        """The placebo trade equals walk() + cost_r run by hand on the same bar and side: nothing re-implemented."""
        import real_costs as RC
        bt, ser = self.engine.bt, self.ser
        with self.fs.bt_opts(bt, self.overlay()) as opts:
            self.assertTrue(opts["fx_gap_fill"] and opts["flat_before_rollover"])
            b, side = 5000, "short"
            pt, why = self.fs.placebo_trade(bt, ser, "XAUUSD", b, side, 7.0, 3.0, 96, 2.5, True, RC)
            self.assertIsNone(why)
            entry = ser.O[b]
            w = bt.walk(side, entry, entry + 7.0, entry - 21.0, ser.H, ser.L, ser.C, b + 1, 96, Tm=ser.Tm, O_=ser.O)
            fee = RC.cost_r(entry, entry + 7.0, ser.Tm[b], ser.Tm[w["exit"]], "XAUUSD", side, self.fs.COST_PROFILE)["total_R"]
            self.assertEqual(pt["net_R"], round(w["R"] - fee, 3))
            self.assertEqual(pt["exit_time"], ser.Tm[w["exit"]])
        self.assertIsNot(bt.OPTS.get("fx_gap_fill"), None)

    def test_the_module_opts_are_restored(self):
        before = self.engine.bt.OPTS
        with self.fs.bt_opts(self.engine.bt, self.overlay()):
            self.assertIsNot(self.engine.bt.OPTS, before)
        self.assertIs(self.engine.bt.OPTS, before)


class PlaceboStatisticalSanity(_PlaceboEngineBase):
    def _summary(self, informed, seed):
        rng = random.Random(seed)
        per = [self.make_real(f, rng, informed=informed, n=120) for f in self.folds]
        rows = self.engine.placebo_trades(self.fold_results(per), self.grid, "sanity|ICT")
        return FS.placebo_summary(rows, "sanity|ICT")

    def test_a_zero_edge_candidate_has_a_placebo_close_to_it(self):
        covered = 0
        for seed in (11, 12, 13):                        # independent draws of both the 'real' and the placebo entries
            s = self._summary(False, seed)
            p = s["pooled"]
            self.assertEqual(p["n_real"], 480)
            self.assertGreater(p["n_placebo"], 400)
            # both are random entries on the same walk: the difference is noise (se about 0.1 R per 480 trades)
            self.assertLess(abs(p["diff"]), 0.3)
            lo, hi = s["bootstrap"]["diff"]
            covered += lo <= 0.0 <= hi
        self.assertGreaterEqual(covered, 2)              # a 4-block bootstrap is rough: 0 lies inside the interval in most draws

    def test_a_planted_edge_beats_the_placebo(self):
        s = self._summary(True, 11)                      # entries chosen by looking 24 bars ahead
        p = s["pooled"]
        self.assertGreater(p["mean_real"], p["mean_placebo"] + 0.5)
        self.assertGreater(s["bootstrap"]["diff"][0], 0.0)       # the whole interval is above 0


# ===================================================================== report-only: nothing reads it, the table values
class ReportOnlyNoVerdict(unittest.TestCase):
    """evaluate_with_engine on the synthetic stub engines the report tests use; the new keys are removed and the rest compared."""

    class _Engine(TFS.SynthEngine):
        def __init__(self, with_report_hooks, placebo=None, **kw):
            super().__init__(**kw)
            self.hooks, self.placebo = with_report_hooks, placebo
            self.method = "ICT"

        def trades_for(self, values):
            return [dict(t, R_planned=4.0, entry=2000.0, stop=1990.0, side="long") for t in super().trades_for(values)]

        def __getattribute__(self, name):
            if name == "spread_r_each" and not object.__getattribute__(self, "hooks"):
                raise AttributeError(name)
            if name == "placebo_trades" and object.__getattribute__(self, "placebo") is None:
                raise AttributeError(name)
            return super().__getattribute__(name)

        def mean_spread_r(self, trades):
            return 0.05

        def spread_r_each(self, trades):
            return [0.05] * len(trades)

        def placebo_trades(self, fold_results, grid, key):
            return self.placebo(fold_results, grid, key)

    def _eval(self, engine, mean=0.4):
        cell = {"id": "5m-indices", "timeframe": "5m", "symbols": TFS.SYMS, "development_start": TFS.LONG_START}
        return _fs().evaluate_with_engine(engine, TFS.grid_two_items(), cell, 6, axes=TFS.TEST_AXES)

    def test_the_placebo_and_the_tables_change_no_verdict_check_or_figure(self):
        plain = self._eval(self._Engine(False, mean=0.4))
        full = self._eval(self._Engine(True, placebo=fake_placebo, mean=0.4))
        self.assertEqual(plain["placebo"] if "placebo" in plain else None, None)
        self.assertEqual(full["placebo"]["status"], "OK")
        strip = lambda r: {k: v for k, v in r.items() if k not in ("placebo", "fold_year_report")}
        self.assertEqual(strip(plain), strip(full))
        self.assertEqual(FS.verdict_from(plain["checks"]), FS.verdict_from(full["checks"]))
        self.assertEqual(plain["verdict"], full["verdict"])
        self.assertEqual(plain["failed_checks"], full["failed_checks"])
        self.assertEqual(plain["margins"], full["margins"])

    def test_a_placebo_better_than_the_candidate_still_changes_nothing(self):
        def better(fold_results, grid, key):
            return [{"test_start": fr["fold"]["test_start"], "real": [t["net_R"] for t in fr["test_trades"]],
                     "placebo": [5.0] * len(fr["test_trades"]), "skipped": {}} for fr in fold_results]
        a = self._eval(self._Engine(True, placebo=fake_placebo, mean=0.4))
        b = self._eval(self._Engine(True, placebo=better, mean=0.4))
        self.assertLess(b["placebo"]["pooled"]["diff"], 0.0)
        self.assertEqual(a["verdict"], b["verdict"])
        self.assertEqual(a["checks"], b["checks"])

    def test_a_failing_placebo_is_recorded_not_raised_and_changes_nothing(self):
        def boom(fold_results, grid, key):
            raise RuntimeError("synthetic placebo failure")
        ok = self._eval(self._Engine(True, placebo=fake_placebo, mean=0.4))
        bad = self._eval(self._Engine(True, placebo=boom, mean=0.4))
        self.assertEqual(bad["placebo"]["status"], "ERROR")
        self.assertIn("synthetic placebo failure", bad["placebo"]["error"])
        self.assertEqual(ok["checks"], bad["checks"])
        self.assertEqual(ok["verdict"], bad["verdict"])

    def test_per_year_table_values(self):
        eng = self._Engine(True, placebo=fake_placebo, mean=0.4)
        res = self._eval(eng)
        fy = res["fold_year_report"]
        self.assertTrue(fy["report_only"])
        self.assertEqual(len(fy["rows"]), len(res["folds_geometry"]))
        self.assertEqual(fy["hour_buckets_utc"], [[0, 6], [6, 12], [12, 18], [18, 24]])
        old = {f["test_start"]: f for f in res["fold_cost_report"]}               # the existing table is untouched
        for row in fy["rows"]:
            o = old[row["test_start"]]
            self.assertEqual((row["n_trades"], row["mean_net_R"]), (o["n_trades"], o["mean_net_R"]))
            self.assertEqual(row["mean_spread_R"], 0.05)
            self.assertAlmostEqual(row["mean_stress_R"], row["mean_net_R"] - eng.stress_cost)     # the stub's stress re-pricing
            self.assertAlmostEqual(sum(row["hour_share"]), 1.0)
            self.assertAlmostEqual(row["cost_regime_ratio"], 0.05 / 4.0)
        # hour shares against a direct count of the fold's test trades
        fold = res["folds_geometry"][-1]
        trades = [t for t in eng.trades_for(res["folds"][-1]["chosen"])
                  if fold["test_start"] <= t["entry_time"] < fold["test_end"]]
        want = [sum(1 for t in trades if a <= int(t["entry_time"][11:13]) < b) / len(trades) for a, b in FS.HOUR_BUCKETS]
        for x, y in zip(fy["rows"][-1]["hour_share"], want):
            self.assertAlmostEqual(x, y)


# ====================================================================================================== disclosure
class Disclosure(unittest.TestCase):
    def _split_series(self, root, sym, tf, first, bars, export_bars, years):
        d = os.path.join(root, f"ohlcv.{sym}.{tf}")
        os.makedirs(d)
        with open(os.path.join(d, "index.json"), "w", encoding="utf-8") as fh:
            json.dump({"symbol": sym, "timeframe": tf, "_bars": export_bars, "_exported_at_utc": "2026-09-28T17:03:41Z",
                       "_format": "split-gz-year-v1", "years": years, "first": first, "last": "2026-09-28T17:03:00Z"}, fh)

    def test_stored_series_facts_read_the_index_and_the_cap_note_prints_both_metals(self):
        fs = _fs()
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self._split_series(tmp, "XAUUSD", "1m", "2012-06-14T17:46:00Z", 5, 5_000_000, [2012])
        self._split_series(tmp, "XAGUSD", "1m", "2012-05-03T05:38:00Z", 5, 5_000_000, [2012])
        f = fs.stored_series_facts("XAUUSD", "1m", root=tmp)
        self.assertEqual((f["first"], f["export_bars"], f["shape"]), ("2012-06-14T17:46:00Z", 5_000_000, "split"))
        self.assertIsNone(fs.stored_series_facts("NOPE", "1m", root=tmp))
        plan = {"cells": [{"id": "1m-metals", "timeframe": "1m", "asset_class": "metals", "symbols": ["XAUUSD", "XAGUSD"],
                           "development_start": "2012-05-03T05:38:00Z", "span_source": "from data",
                           "symbol_first_bar": {"XAUUSD": "2012-06-14T17:46:00Z", "XAGUSD": "2012-05-03T05:38:00Z"}}]}
        rec = {"parameters": {"cell": "1m-metals"},
               "dataset_snapshot": {"series": [{"symbol": "XAUUSD", "timeframe": "1m", "bars": 123, "first_open": "2012-06-14T17:46:00Z"}]}}
        md = "\n".join(fs.disclosure_lines(plan, [rec], facts=lambda s, t: fs.stored_series_facts(s, t, root=tmp), density={}))
        self.assertIn("capped at 5,000,000 bars", md)
        self.assertIn("XAUUSD first bar 2012-06-14T17:46:00Z", md)
        self.assertIn("XAGUSD first bar 2012-05-03T05:38:00Z", md)
        self.assertIn("| 1m-metals | XAUUSD | 1m | 2012-06-14T17:46:00Z | 5000000 | 2012-06-14T17:46:00Z | 123 |", md)
        self.assertIn("| 1m-metals | XAGUSD | 1m | 2012-05-03T05:38:00Z | 5000000 | n/a | n/a |", md)     # no record: n/a, not invented
        self.assertIn("earliest-symbol first bar 2012-05-03T05:38:00Z (XAGUSD)", md)

    def test_no_cap_note_when_the_series_is_not_at_the_cap(self):
        fs = _fs()
        plan = {"cells": [{"id": "1m-metals", "timeframe": "1m", "asset_class": "metals", "symbols": ["XAUUSD"],
                           "development_start": "2013-01-01T00:00:00Z", "span_source": "from data", "symbol_first_bar": {}}]}
        md = "\n".join(fs.disclosure_lines(plan, [], facts=lambda s, t: {"first": "2013-01-01T00:00:00Z", "export_bars": 4_999_999}))
        self.assertNotIn("1m metals export cap:", md)

    def test_the_real_stored_1m_metals_first_bars_match_the_first_part_files(self):
        """Disclosure numbers vs the stored series: the first bar of the index is the first candle of the first year part, and the
        export is at the cap (labels and counts only; no price is used)."""
        fs = _fs()
        for sym in ("XAUUSD", "XAGUSD"):
            d = os.path.join(ROOT, "data", "history", "ftmo", f"ohlcv.{sym}.1m")
            if not os.path.isdir(d):
                raise AssertionError(f"{d} is missing: this check needs the FTMO history")
            f = fs.stored_series_facts(sym, "1m", root=os.path.join(ROOT, "data", "history", "ftmo"))
            ix = json.load(open(os.path.join(d, "index.json")))
            with gzip.open(os.path.join(d, f"{min(ix['years'])}.json.gz"), "rt", encoding="utf-8") as fh:
                first = json.load(fh)["candles"][0]["time"]
            self.assertEqual(f["first"], first)
            self.assertEqual(f["export_bars"], fs.EXPORT_BAR_CAP)
        xau = fs.stored_series_facts("XAUUSD", "1m", root=os.path.join(ROOT, "data", "history", "ftmo"))["first"]
        xag = fs.stored_series_facts("XAGUSD", "1m", root=os.path.join(ROOT, "data", "history", "ftmo"))["first"]
        self.assertNotEqual(xau, xag)                                 # the two metals start on different dates: both are printed

    def test_sparse_summary_from_the_density_census(self):
        fs = _fs()
        dens = fs.load_density()
        self.assertIsNotNone(dens, "docs/audits/2026-10-02-dev-start-density.json is committed")
        s = fs.sparse_summary(dens, "US500", "1m")
        self.assertEqual(s["first_bar"], dens["US500|1m"]["first_bar"])
        self.assertEqual(s["bars_per_year"][2017], dens["US500|1m"]["months"]["2017-12"])
        self.assertTrue(all(n < 1000 for n in s["bars_per_year"].values()))             # sparse before 2021
        self.assertEqual(s["first_dense_month"], "2021-09")                           # the census finding
        self.assertEqual(fs.sparse_summary(dens, "US30", "1m")["first_dense_month"], "2019-02")
        self.assertIsNone(fs.sparse_summary(dens, "NOPE", "1m"))
        self.assertIsNone(fs.load_density("/nonexistent/density.json"))

    def test_the_indices_cell_prints_the_sparse_note_and_a_missing_census_is_said(self):
        fs = _fs()
        plan = {"cells": [{"id": "1m-indices", "timeframe": "1m", "asset_class": "indices", "symbols": ["US500", "US30"],
                           "development_start": "2020-03-01T00:00:00Z", "span_source": "declared",
                           "symbol_first_bar": {"US500": "2017-12-28T22:00:00Z", "US30": "2019-02-08T12:25:00Z"}}]}
        md = "\n".join(fs.disclosure_lines(plan, [], facts=lambda s, t: None, density=fs.load_density()))
        self.assertIn("Sparse 1m data, US500", md)
        self.assertIn("first month with >= 10,000 bars: 2021-09", md)
        self.assertIn("Sparse 1m data, US30", md)
        with unittest.mock.patch.object(fs, "load_density", lambda path=None: None):
            md2 = "\n".join(fs.disclosure_lines(plan, [], facts=lambda s, t: None))
        self.assertIn("density census json is not present", md2)


# ======================================================================================================== the report
class ReportShowsIt(TFS._Tmp):
    """cmd_report on stored records: the NOT IMPLEMENTED line is gone, the placebo and the tables are printed, the verdicts are unchanged."""

    def _write(self, plan, placebo, mean=0.6):
        grids, paths = self.fs.load_grids(TFS.FIXTURES)
        os.makedirs(self.records, exist_ok=True)
        for c in plan["candidates"][:2]:
            cell = dict(next(x for x in plan["cells"] if x["id"] == c["cell"]), development_start=TFS.LONG_START)
            eng = ReportOnlyNoVerdict._Engine(True, placebo=placebo, mean=mean, symbols=cell["symbols"])
            res = self.fs.evaluate_with_engine(eng, TFS.grid_two_items(), cell, c["family_size"], axes={"a": TFS.TEST_AXES["a"]})
            rec = self.fs.build_record(c, plan["plan_hash"], grids[c["method"]], paths[c["method"]], res,
                                       {"snapshot_id": "t", "series": []}, cell)
            TFS.X.write(types.MappingProxyType(dict(rec)), store=self.records)

    def test_the_report_prints_the_placebo_the_table_the_build_and_the_disclosure(self):
        self.fs.cmd_plan(grid_dir=TFS.FIXTURES)
        plan = json.load(open(self.fs.PLAN_PATH))
        self._write(plan, fake_placebo)
        md = self.fs.cmd_report()
        self.assertNotIn("NOT IMPLEMENTED", md)
        self.assertRegex(md, r"_Build: git `[0-9a-f]{12}`")
        self.assertRegex(md, r"\*\*Placebo \(section C item 6, REPORT-ONLY; build `[0-9a-f]{12}`\):\*\* implemented")
        self.assertIn("REPORT-ONLY: a PASS requires nothing from this", md)
        self.assertIn(FS.PLACEBO_SEED, md)
        self.assertIn("Bootstrap over", md)
        self.assertIn("Per test fold (REPORT-ONLY", md)
        self.assertIn("cost regime ratio", md)
        self.assertIn("## Data disclosure", md)

    def test_an_old_record_without_placebo_says_so_and_the_verdicts_do_not_move(self):
        self.fs.cmd_plan(grid_dir=TFS.FIXTURES)
        plan = json.load(open(self.fs.PLAN_PATH))
        self._write(plan, fake_placebo)
        md_with = self.fs.cmd_report()
        recs = [TFS.X.load(f[:-5], store=self.records) for f in sorted(os.listdir(self.records)) if f.endswith(".json")]
        v_with = {r["experiment_id"]: FS.verdict_from(r["metrics"]["evaluation"]["checks"]) for r in recs}
        shutil.rmtree(self.records)
        self._write(plan, None)                                              # engines without a placebo
        md_without = self.fs.cmd_report()
        recs = [TFS.X.load(f[:-5], store=self.records) for f in sorted(os.listdir(self.records)) if f.endswith(".json")]
        v_without = {r["experiment_id"]: FS.verdict_from(r["metrics"]["evaluation"]["checks"]) for r in recs}
        self.assertEqual(v_with, v_without)
        self.assertIn("Placebo: no figure in this record", md_without)
        self.assertNotIn("Placebo: no figure in this record", md_with)
        pick = lambda md: [ln for ln in md.splitlines() if ln.startswith("| ") and "rejected" in ln]
        self.assertEqual(pick(md_with), pick(md_without))                      # the Holm table is the same


if __name__ == "__main__":
    unittest.main()
