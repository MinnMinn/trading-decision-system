"""C3 (red-team 2026-10-02): `OPTS["fx_gap_fill"]` -- gap-aware stop fills in `walk()` and in the same-bar fill-and-stop booking.

v1 (key off, the default) fills a stop at EXACTLY the stop price even when the bar OPENS beyond it. With the key on, a stop (the
planned stop or the breakeven stop) fills at the WORSE of the stop and the bar open when the open is beyond the stop (long
min(stop, open), short max(stop, open)); targets and limit entries still fill at their own price (no price improvement); the
realised R comes from the actual fill on the PLANNED risk, so R_planned / min_rr admission are untouched.

Every series here is hand-built: no real history, no R / expectancy of any evaluation.

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_gap_fill
"""
import importlib.util
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def _bt():
    spec = importlib.util.spec_from_file_location("bt_gap_fill", os.path.join(ROOT, "scripts", "backtest-methods.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Base(unittest.TestCase):
    def setUp(self):
        self.bt = _bt()

    def tearDown(self):
        self.bt.reset_opts()

    def opts(self, **kw):
        self.bt.OPTS = dict(self.bt._OPTS_BASE, **kw)

    def walk(self, side, entry, stop, target, bars, gap, **kw):
        """bars = [(open, high, low, close), ...]; the walk starts at bar 0."""
        self.opts(fx_gap_fill=gap, **kw)
        O, H, L, C = ([b[i] for b in bars] for i in range(4))
        return self.bt.walk(side, entry, stop, target, H, L, C, 0, len(bars), O_=O)


class Registered(_Base):
    def test_key_is_off_by_default_in_the_baseline_and_live_never_sets_it(self):
        self.assertIs(self.bt._OPTS_BASE["fx_gap_fill"], False)
        self.assertIs(self.bt.OPTS["fx_gap_fill"], False)
        src = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        self.assertNotIn("fx_gap_fill", src)


class StopGapLong(_Base):
    # long: entry 100, stop 98 (r = 2), target 106 (rp = 3)
    def test_a_bar_opening_below_the_stop_fills_at_the_open(self):
        bars = [(96.0, 97.0, 95.0, 96.5)]
        on = self.walk("long", 100.0, 98.0, 106.0, bars, True)
        self.assertEqual((on["outcome"], on["R"], on["exit"], on["R_planned"]), ("loss", -2.0, 0, 3.0))
        off = self.walk("long", 100.0, 98.0, 106.0, bars, False)
        self.assertEqual((off["outcome"], off["R"]), ("loss", -1.0))                # v1: filled at the stop

    def test_an_open_exactly_at_the_stop_fills_at_the_stop_in_both_modes(self):
        bars = [(98.0, 99.0, 97.0, 97.5)]
        on = self.walk("long", 100.0, 98.0, 106.0, bars, True)
        off = self.walk("long", 100.0, 98.0, 106.0, bars, False)
        self.assertEqual(on, off)
        self.assertEqual(on["R"], -1.0)

    def test_no_gap_is_identical_in_both_modes(self):
        bars = [(99.0, 99.5, 97.5, 98.0)]
        self.assertEqual(self.walk("long", 100.0, 98.0, 106.0, bars, True), self.walk("long", 100.0, 98.0, 106.0, bars, False))

    def test_a_bar_that_touches_both_stop_and_target_is_still_a_stop_first(self):
        bars = [(99.0, 107.0, 97.0, 100.0)]                                        # opened inside the stop: no gap
        on = self.walk("long", 100.0, 98.0, 106.0, bars, True)
        self.assertEqual((on["outcome"], on["R"]), ("loss", -1.0))

    def test_a_bar_that_gaps_down_through_the_stop_even_when_it_also_reaches_the_target(self):
        bars = [(96.0, 107.0, 95.0, 100.0)]                                        # opens below the stop, rallies through target
        on = self.walk("long", 100.0, 98.0, 106.0, bars, True)
        self.assertEqual((on["outcome"], on["R"]), ("loss", -2.0))                 # stop first, filled at the open

    def test_a_gap_through_the_target_still_fills_at_the_target_price(self):
        bars = [(108.0, 109.0, 107.0, 108.5)]
        for gap in (True, False):
            w = self.walk("long", 100.0, 98.0, 106.0, bars, gap)
            self.assertEqual((w["outcome"], w["R"]), ("win", 3.0))                 # no price improvement

    def test_the_bar_before_the_gap_does_not_change_the_walk(self):
        bars = [(100.5, 101.0, 99.0, 100.2), (96.0, 97.0, 95.0, 96.0)]
        w = self.walk("long", 100.0, 98.0, 106.0, bars, True)
        self.assertEqual((w["R"], w["exit"], w["bars_held"]), (-2.0, 1, 2))


class StopGapShort(_Base):
    # short: entry 100, stop 102 (r = 2), target 94 (rp = 3)
    def test_a_bar_opening_above_the_stop_fills_at_the_open(self):
        bars = [(104.0, 105.0, 103.0, 104.5)]
        on = self.walk("short", 100.0, 102.0, 94.0, bars, True)
        self.assertEqual((on["outcome"], on["R"]), ("loss", -2.0))
        off = self.walk("short", 100.0, 102.0, 94.0, bars, False)
        self.assertEqual(off["R"], -1.0)

    def test_an_open_exactly_at_the_stop_and_no_gap(self):
        for bars in ([(102.0, 103.0, 101.0, 102.5)], [(101.0, 102.5, 100.5, 101.5)]):
            self.assertEqual(self.walk("short", 100.0, 102.0, 94.0, bars, True),
                             self.walk("short", 100.0, 102.0, 94.0, bars, False))

    def test_a_gap_through_the_short_target_still_fills_at_the_target(self):
        bars = [(92.0, 93.0, 91.0, 92.5)]
        w = self.walk("short", 100.0, 102.0, 94.0, bars, True)
        self.assertEqual((w["outcome"], w["R"]), ("win", 3.0))


class TrailedStop(_Base):
    def test_a_gap_through_the_breakeven_stop_fills_at_the_open_and_is_a_loss(self):
        # long, mgmt "be": bar 0 reaches +1R (102) without touching the stop -> stop moves to entry (100); bar 1 opens at 99
        bars = [(100.5, 102.5, 100.2, 102.0), (99.0, 99.5, 98.5, 99.0)]
        on = self.walk("long", 100.0, 98.0, 106.0, bars, True, mgmt="be")
        self.assertEqual((on["outcome"], on["R"], on["exit"]), ("loss", -0.5, 1))   # (99 - 100) / planned risk 2
        off = self.walk("long", 100.0, 98.0, 106.0, bars, False, mgmt="be")
        self.assertEqual((off["outcome"], off["R"]), ("breakeven", 0.0))            # v1: filled at the breakeven stop

    def test_breakeven_stop_hit_without_a_gap_is_still_a_breakeven(self):
        bars = [(100.5, 102.5, 100.2, 102.0), (101.0, 101.5, 99.5, 100.0)]
        for gap in (True, False):
            w = self.walk("long", 100.0, 98.0, 106.0, bars, gap, mgmt="be")
            self.assertEqual((w["outcome"], w["R"]), ("breakeven", 0.0))

    def test_short_breakeven_gap(self):
        bars = [(99.5, 99.8, 97.5, 98.0), (101.0, 101.5, 100.5, 101.0)]             # +1R at 98 -> stop to 100; bar 1 opens at 101
        on = self.walk("short", 100.0, 102.0, 94.0, bars, True, mgmt="be")
        self.assertEqual((on["outcome"], on["R"]), ("loss", -0.5))


class Guards(_Base):
    def test_the_key_without_opens_refuses_instead_of_filling_at_the_stop(self):
        self.opts(fx_gap_fill=True)
        with self.assertRaises(ValueError):
            self.bt.walk("long", 100.0, 98.0, 106.0, [97.0], [95.0], [96.0], 0, 1)

    def test_a_caller_that_passes_nothing_gets_v1(self):
        self.opts(fx_gap_fill=False)
        w = self.bt.walk("long", 100.0, 98.0, 106.0, [97.0], [95.0], [96.0], 0, 1)
        self.assertEqual(w["R"], -1.0)

    def test_planned_risk_is_unchanged(self):
        bars = [(96.0, 97.0, 95.0, 96.5)]
        self.assertEqual(self.walk("long", 100.0, 98.0, 106.0, bars, True)["R_planned"],
                         self.walk("long", 100.0, 98.0, 106.0, bars, False)["R_planned"])


class SameBarFillAndStop(_Base):
    def test_helper_values(self):
        g = self.bt.gap_stop_R
        self.assertEqual(g("long", 100.0, 98.0, 97.0), -1.5)
        self.assertIsNone(g("long", 100.0, 98.0, 98.0))
        self.assertIsNone(g("long", 100.0, 98.0, 99.0))
        self.assertEqual(g("short", 100.0, 102.0, 104.0), -2.0)
        self.assertIsNone(g("short", 100.0, 102.0, 102.0))
        self.assertIsNone(g("long", 100.0, 100.0, 90.0))                             # no valid risk

    def _ict(self, open_fill_bar, gap):
        """`_ict_trade` on hand-built bars: the limit at 100 (a long) and the stop at 98 are both reached on bar 4."""
        self.opts(fx_gap_fill=gap)
        n = 8
        Tm = [f"2024-01-01T00:{m:02d}:00Z" for m in range(0, 8 * 5, 5)][:n]
        H = [101.0] * n
        L = [101.0] * n
        L[4] = 95.0                                   # bar 4 trades through the limit AND the stop
        O = [101.0] * n
        O[4] = open_fill_bar
        x = types.SimpleNamespace(sym="XAUUSD", tf="5m", c=[], Tm=Tm, H=H, L=L, C=[101.0] * n, O=O, n=n,
                                  idx_of_time={Tm[1]: 1}, hz=10, b7_kz=False, K=5, methods=None)
        su = {"side": "long", "entry": 100.0, "stop": 98.0, "target": 106.0, "entry_models": {"fill": 99.0},
              "mss": {"time": Tm[1]}, "sweep": {"time": Tm[0]}, "R": 3.0}
        return self.bt._ict_trade(x, 3, su)

    def test_ict_same_bar_fill_and_stop_obeys_the_gap_rule(self):
        t_off = self._ict(96.0, False)
        t_on = self._ict(96.0, True)
        self.assertEqual((t_off["outcome"], t_off["R"], t_off["mae"]), ("loss", -1.0, -1.0))
        self.assertEqual((t_on["outcome"], t_on["R"], t_on["mae"]), ("loss", -2.0, -2.0))     # limit 100, stop leg at the 96 open
        self.assertEqual(t_on["R_planned"], 3.0)
        self.assertEqual(t_on["entry"], 100.0)                                                # the limit filled at its own price

    def test_ict_same_bar_fill_and_stop_without_a_gap_is_v1(self):
        self.assertEqual(self._ict(100.5, True), self._ict(100.5, False))
        self.assertEqual(self._ict(98.0, True)["R"], -1.0)


if __name__ == "__main__":
    unittest.main()
