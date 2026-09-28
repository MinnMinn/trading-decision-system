"""scripts/diagnose-methods.py -- the read-only development-window method diagnosis.

Two properties matter and both are attacked here:
  1. The instrumentation changes nothing: the trades an instrumented scan returns are IDENTICAL to a plain
     `bt.scan()` under the same PIT cutoff, for both methods, on a real slice. Config C is used because it
     exercises every wrapped function (htf gate + breakeven management).
     Speed: `bt.limit_bars(N)` cannot be used here -- it keeps the file's most recent N bars, which are all
     after the development cutoff, so the PIT cutoff would then leave nothing. An EARLIER cutoff is used
     instead (XAUUSD 4H through 2006: ~3.8k bars), which is still development data and still a real scan.
  2. The outcome summary is right, on synthetic trades whose answer is known by construction.
"""
import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
_spec = importlib.util.spec_from_file_location("diagnose_methods", os.path.join(ROOT, "scripts", "diagnose-methods.py"))
dm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dm)

SLICE = ("XAUUSD", "4H", "C", "2007-01-01T00:00:00Z")


def _t(side="long", outcome="loss", R=-1.0, Rp=3.0, mfe=0.5, mae=-1.0, bars=5, et="2020-01-01T00:00:00Z",
       xt="2020-01-02T00:00:00Z"):
    return dict(symbol="X", tf="1H", side=side, outcome=outcome, R=R, R_planned=Rp, mfe=mfe, mae=mae,
                bars_held=bars, entry_time=et, exit_time=xt, entry=100.0, stop=99.0, target=103.0)


class OutcomeSummary(unittest.TestCase):
    H = 10

    def test_exit_types(self):
        self.assertEqual(dm.exit_type(_t(), self.H), "stop")
        self.assertEqual(dm.exit_type(_t(outcome="win", R=3.0), self.H), "target")
        self.assertEqual(dm.exit_type(_t(outcome="breakeven", R=0.0), self.H), "breakeven_stop")
        self.assertEqual(dm.exit_type(_t(outcome="timeout", R=0.4, bars=10), self.H), "time_stop")
        self.assertEqual(dm.exit_type(_t(outcome="timeout", R=0.4, bars=3), self.H), "truncated_at_cutoff")
        same = _t(mfe=0.0, bars=1, xt="2020-01-01T00:00:00Z")
        self.assertEqual(dm.exit_type(same, self.H), "same_bar_fill_and_stop")

    def test_summary_numbers(self):
        trades = [
            _t(mfe=1.2),                                   # loser that first went +1.2R
            _t(mfe=3.5, Rp=3.0),                           # loser whose MFE passed the planned target's R
            _t(mfe=0.2, side="short"),
            _t(outcome="win", R=3.0, mfe=3.0, mae=-0.3),
            _t(outcome="breakeven", R=0.0, mfe=1.1, mae=-0.2, side="short"),
            _t(outcome="timeout", R=0.5, mfe=0.9, mae=-0.4, bars=10, Rp=1.5),
        ]
        s = dm.summarize_outcomes(trades, self.H, min_rr=2.0)
        self.assertEqual(s["n"], 6)
        self.assertEqual(s["exit_types"], {"stop": 3, "target": 1, "breakeven_stop": 1, "time_stop": 1})
        self.assertAlmostEqual(s["mean_R"], round((-3 + 3 + 0 + 0.5) / 6, 3))
        self.assertAlmostEqual(s["median_R"], -0.5)          # sorted: -1,-1,-1,0,0.5,3 -> (-1+0)/2
        self.assertAlmostEqual(s["win_rate"], round(2 / 6, 3))
        self.assertEqual(s["losers"], 3)
        self.assertEqual(s["losers_with_mfe_ge_1R"], 2)
        self.assertEqual(s["losers_with_mfe_ge_planned_R"], 1)
        self.assertEqual(s["non_winners_with_mfe_ge_1R"], 3)  # the two losers + the breakeven
        self.assertEqual(s["by_side"]["long"]["n"], 4)
        self.assertEqual(s["by_side"]["short"]["n"], 2)
        self.assertAlmostEqual(s["by_side"]["short"]["mean_R"], -0.5)
        self.assertAlmostEqual(s["share_R_planned_below_floor"], round(1 / 6, 3))
        self.assertEqual(s["bars_held"]["median"], 5)

    def test_empty(self):
        self.assertEqual(dm.summarize_outcomes([], self.H), {"n": 0})

    def test_reached_is_cumulative(self):
        st = ("a", "b", "c")
        self.assertEqual(dm._reached({"a": 2, "c": 1}, st), {"a": 3, "b": 1, "c": 1})


class CutoffGuard(unittest.TestCase):
    def test_refuses_cutoff_inside_validation(self):
        with self.assertRaises(ValueError):
            dm._check_cutoff("2024-03-01T00:00:01Z")
        with self.assertRaises(ValueError):
            dm._check_cutoff("2025-01-01T00:00:00Z")
        dm._check_cutoff(dm.DEV_CUTOFF)          # the boundary itself is allowed (exclusive end of dev)


class InstrumentationChangesNothing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sr = dm.load_sr()

    def _check(self, method):
        sym, tf, cfg, cut = SLICE
        bt = self.sr.bt
        originals = (bt.walk, bt.fvg_fill, bt.htf_bias_gate, bt._fires_from, bt._wyckoff_candidates,
                     bt.ict_setups_live, bt.lr.read_at, bt.lr.ict_scan.setup_candidate, bt.W.detect_accumulations)
        plain = dm.plain_scan(self.sr, sym, tf, method, cfg, cut)["trades"][method]
        res, probe = dm.instrumented_scan(self.sr, sym, tf, method, cfg, cut)
        instr = res["trades"][method]
        self.assertGreater(len(plain), 0, "slice must book at least one trade or equality proves little")
        self.assertEqual(plain, instr)
        # wrappers removed again
        self.assertEqual(originals, (bt.walk, bt.fvg_fill, bt.htf_bias_gate, bt._fires_from, bt._wyckoff_candidates,
                                     bt.ict_setups_live, bt.lr.read_at, bt.lr.ict_scan.setup_candidate,
                                     bt.W.detect_accumulations))
        self.assertTrue(res["last"] < cut)
        summ = probe.summary(True) if method == "ICT" else probe.summary(instr, True)
        self.assertEqual(summ["consistency"], {}, "an inferred stage disagrees with an observed one")
        return summ, instr

    def test_ict(self):
        summ, trades = self._check("ICT")
        self.assertEqual(summ["unique_setups_reaching"]["booked"], len(trades))

    def test_wyckoff_book(self):
        summ, trades = self._check("WYCKOFF-BOOK")
        self.assertEqual(sum(summ["booked_by_leg"].values()), len(trades))
        self.assertEqual(summ["walk_calls"].get("trade", 0), len(trades))


if __name__ == "__main__":
    unittest.main()
