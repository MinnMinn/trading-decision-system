"""Planned-risk admission (pre-registration item 12; docs/audits/2026-10-01-zero-risk.md).

A candidate trade whose planned risk |entry - stop| is zero (the ICT B-EX=fill entry model puts the FVG's far edge ON the
stop whenever the first candle of the gap is a flat bar at the extreme), wrong-side, below one tick, or not a finite
price has no position size. `backtest-methods.planned_risk_refusal` is the ONE rule; simulate() refuses such a candidate
at admission (counted `SIM_LAST["refused"]["zero_risk"]`), before any pricing, instead of letting `real_costs.cost_r`
raise (`CostRefused: stop distance is zero`) or the flat-fee path divide by zero.

No R / expectancy of any real evaluation is computed here: every trade is a hand-built dict.
"""
import hashlib
import importlib.util
import json
import math
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import real_costs as RC  # noqa: E402

FTMO = "ftmo_demo_2026_09"


def _bt():
    spec = importlib.util.spec_from_file_location("bt_zr", os.path.join(ROOT, "scripts", "backtest-methods.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _trade(i, entry=2000.0, stop=1998.0, side="long", sym="XAUUSD", r_planned=6.0, **extra):
    """A distinct hand-built trade per `i` (own hour on 2024-01-10, one hour long, same server day)."""
    t = {"symbol": sym, "side": side, "entry": entry, "stop": stop, "target": entry + 6 * (entry - stop),
         "entry_time": f"2024-01-10T{8 + 2 * i:02d}:00:00Z", "exit_time": f"2024-01-10T{9 + 2 * i:02d}:00:00Z",
         "R": r_planned, "R_planned": r_planned, "event": f"e{i}", "outcome": "win"}
    t.update(extra)
    return t


class PlannedRiskRefusal(unittest.TestCase):
    """The shared function: every refusal cause, and what it must NOT refuse."""

    @classmethod
    def setUpClass(cls):
        cls.bt = _bt()
        cls.f = staticmethod(cls.bt.planned_risk_refusal)

    def test_valid_orders_pass_both_sides_with_and_without_a_tick(self):
        for tick in (None, 0.01):
            self.assertIsNone(self.f("long", 2000.0, 1999.0, tick))
            self.assertIsNone(self.f("short", 2000.0, 2001.0, tick))

    def test_zero_risk_is_refused_long_and_short(self):
        for side in ("long", "short"):
            for tick in (None, 0.01):
                self.assertEqual(self.f(side, 4053.5, 4053.5, tick), "zero")

    def test_negative_risk_the_stop_on_the_profit_side_is_refused(self):
        self.assertEqual(self.f("long", 2000.0, 2000.5, None), "wrong_side")
        self.assertEqual(self.f("short", 2000.0, 1999.5, None), "wrong_side")

    def test_below_one_tick_is_refused_only_when_a_tick_is_known(self):
        self.assertEqual(self.f("long", 2000.0, 1999.995, 0.01), "sub_tick")
        self.assertEqual(self.f("short", 2000.0, 2000.004, 0.01), "sub_tick")
        self.assertIsNone(self.f("long", 2000.0, 1999.995, None))        # no tick: only "> 0" can be asked

    def test_exactly_one_tick_is_admitted_despite_float_noise(self):
        # 2000.01 - 2000.00 == 0.009999999999990905: one tick of 0.01, but a hair "below" it in floating point
        self.assertLess(2000.01 - 2000.00, 0.01)
        self.assertIsNone(self.f("long", 2000.01, 2000.00, 0.01))
        self.assertIsNone(self.f("short", 2000.00, 2000.01, 0.01))
        self.assertIsNone(self.f("long", 4053.6, 4053.59, 0.01))
        self.assertIsNone(self.f("long", 1.2346, 1.2345, 0.0001))

    def test_slack_boundary_decisions(self):
        """Documented decisions at the edge of `risk < tick * (1 - RISK_TICK_REL_TOL)` (tol = 1e-6):
          * risk == tick                 -> ADMITTED (a one-tick stop is placeable);
          * risk == tick * (1 - 1e-6)    -> ADMITTED (the comparison is strict `<`: the boundary itself is the slack's
                                            last admitted value, so float noise on a one-tick stop can never refuse it);
          * risk == tick * (1 - 2e-6)    -> REFUSED `sub_tick` (beyond the slack: a genuinely smaller stop)."""
        factor = {0.0: 1.0, 1e-6: 1 - 1e-6, 2e-6: 1 - 2e-6}
        for side in ("long", "short"):
            for rel, want in ((0.0, None), (1e-6, None), (2e-6, "sub_tick")):
                entry = 1.0
                for guess in (1.999999, 1.9999995, 1.9999990000000001, 1.5):     # a risk r = stop - entry, exact (Sterbenz)
                    r = guess - entry
                    # a tick with tick * (1 - rel) == r bit for bit, found by stepping the float neighbours of r / factor
                    tick = r / factor[rel]
                    for _ in range(64):
                        if tick * factor[rel] == r:
                            break
                        tick = math.nextafter(tick, math.inf if tick * factor[rel] < r else -math.inf)
                    if tick * factor[rel] == r:
                        break
                else:
                    self.fail("no exact boundary tick found")
                # long: entry = 1.0 + r, stop = 1.0 (risk = entry - stop = r exactly); short: entry = 1.0, stop = 1.0 + r
                e, st = (1.0 + r, 1.0) if side == "long" else (1.0, 1.0 + r)
                risk = (e - st) if side == "long" else (st - e)
                self.assertEqual(risk, tick * factor[rel], (side, rel))
                self.assertEqual(self.f(side, e, st, tick), want, (side, rel))

    def test_nan_inf_none_and_non_numbers_are_refused_not_raised(self):
        for bad in (float("nan"), float("inf"), float("-inf"), None, "abc", [], {}):
            self.assertEqual(self.f("long", 2000.0, bad, 0.01), "invalid_price", bad)
            self.assertEqual(self.f("long", bad, 1999.0, 0.01), "invalid_price", bad)
        self.assertEqual(self.f("long", 0.0, -1.0, None), "invalid_price")       # entry must be a positive price
        self.assertEqual(self.f("long", -5.0, -6.0, None), "invalid_price")
        self.assertEqual(self.f("sideways", 2000.0, 1999.0, None), "invalid_price")
        self.assertEqual(self.f(None, 2000.0, 1999.0, None), "invalid_price")

    def test_numeric_strings_and_ints_are_read_as_numbers(self):
        self.assertIsNone(self.f("long", 2000, 1999, None))
        self.assertEqual(self.f("long", "2000", "2000", None), "zero")

    def test_every_returned_cause_is_a_declared_one(self):
        for args in (("long", 1.0, 1.0), ("long", 1.0, 2.0), ("long", float("nan"), 1.0)):
            self.assertIn(self.f(*args), self.bt.ZERO_RISK_CAUSES)
        self.assertEqual(self.bt.ZERO_RISK_REASON, "zero_risk")

    def test_the_tick_comes_from_the_cost_spec(self):
        self.assertEqual(RC.tick_size(FTMO, "XAUUSD"), 0.01)
        self.assertEqual(RC.tick_size(FTMO, "XAGUSD"), 0.001)
        self.assertEqual(RC.tick_size(FTMO, "US500"), 0.01)
        with mock.patch.object(RC, "spec", return_value={"tick_size": 0}):
            with self.assertRaises(RC.CostRefused):
                RC.tick_size(FTMO, "XAUUSD")
        with mock.patch.object(RC, "spec", return_value={}):
            with self.assertRaises(RC.CostRefused):
                RC.tick_size(FTMO, "XAUUSD")


class SimulateRefusesZeroRisk(unittest.TestCase):
    def setUp(self):
        self.bt = _bt()
        self.bt.RUIN_FRAC = 0.0

    def tearDown(self):
        self.bt.reset_opts()

    def _sha(self, taken):
        return hashlib.sha256(json.dumps(taken, sort_keys=True).encode()).hexdigest()

    def _mixed(self):
        zero = _trade(1, entry=4053.5, stop=4053.5, r_planned=None)          # the shape the scan produced: R_planned None
        return [_trade(0), zero, _trade(2, side="short", entry=2000.0, stop=2002.0),
                _trade(3, entry=2000.0, stop=1999.999), _trade(4, entry=2000.0, stop=float("nan"))]

    def test_a_zero_risk_trade_no_longer_aborts_with_real_costs(self):
        trades = self._mixed()
        with self.assertRaises(RC.CostRefused):                                # what the unguarded engine did
            RC.cost_r(trades[1]["entry"], trades[1]["stop"], trades[1]["entry_time"], trades[1]["exit_time"],
                      "XAUUSD", "long", FTMO)
        _eq, _curve, taken = self.bt.simulate(trades, 0.0, cost_profile=FTMO)   # does NOT raise
        self.assertEqual([t["event"] for t in taken], ["e0", "e2"])
        refused = self.bt.SIM_LAST["refused"]
        self.assertEqual(refused["zero_risk"], 3)                              # zero, sub-tick (0.001 < 0.01), NaN
        self.assertEqual(self.bt.SIM_LAST["zero_risk_by_cause"],
                         {"zero": 1, "wrong_side": 0, "sub_tick": 1, "invalid_price": 1})
        self.assertEqual((refused["news"], refused["session"]), (0, 0))

    def test_a_zero_risk_trade_no_longer_aborts_on_the_flat_fee_path(self):
        trades = [_trade(0, sym="BTCUSDT"), _trade(1, sym="BTCUSDT", entry=2000.0, stop=2000.0, r_planned=None)]
        _eq, _curve, taken = self.bt.simulate(trades, 0.0005)
        self.assertEqual([t["event"] for t in taken], ["e0"])
        self.assertEqual(self.bt.SIM_LAST["refused"]["zero_risk"], 1)

    def test_a_wrong_side_stop_is_refused_and_counted(self):
        trades = [_trade(0), _trade(1, entry=2000.0, stop=2001.0, r_planned=None)]
        _eq, _curve, taken = self.bt.simulate(trades, 0.0, cost_profile=FTMO)
        self.assertEqual([t["event"] for t in taken], ["e0"])
        self.assertEqual(self.bt.SIM_LAST["zero_risk_by_cause"]["wrong_side"], 1)

    def test_the_refusal_is_exactly_the_removal_of_those_trades(self):
        """BEFORE (the engine without the rule, fed only the trades that have a valid stop) == AFTER (with the rule, fed
        everything): same taken list byte for byte; nothing but the zero-risk trades is gone."""
        trades = self._mixed()
        valid_only = [t for t in trades if self.bt.planned_risk_refusal(t["side"], t["entry"], t["stop"], 0.01) is None]
        self.assertEqual(len(valid_only), 2)
        before = self.bt.simulate(valid_only, 0.0, cost_profile=FTMO)
        self.assertEqual(self.bt.SIM_LAST["refused"]["zero_risk"], 0)
        after = self.bt.simulate(trades, 0.0, cost_profile=FTMO)
        self.assertEqual(self._sha(after[2]), self._sha(before[2]))
        self.assertEqual(self._sha(after[1]), self._sha(before[1]))
        self.assertEqual(after[0], before[0])

    def test_a_refused_trade_does_not_block_the_next_trade_of_its_symbol(self):
        """It was never entered: it must not occupy the one-position-per-symbol slot."""
        zero = _trade(0, entry=2000.0, stop=2000.0, r_planned=None, exit_time="2024-01-10T20:00:00Z")
        nxt = _trade(1)                                       # enters 10:00, inside the zero-risk trade's window
        _eq, _curve, taken = self.bt.simulate([zero, nxt], 0.0, cost_profile=FTMO)
        self.assertEqual([t["event"] for t in taken], ["e1"])

    def test_valid_trades_alone_are_untouched_and_count_zero(self):
        trades = [_trade(0), _trade(1, side="short", entry=2000.0, stop=2002.0), _trade(2, entry=2000.0, stop=1999.99)]
        self.bt.simulate(trades, 0.0, cost_profile=FTMO)
        self.assertEqual(self.bt.SIM_LAST["refused"]["zero_risk"], 0)
        self.assertEqual(sum(self.bt.SIM_LAST["zero_risk_by_cause"].values()), 0)

    def test_non_vacuity_without_the_rule_the_same_input_aborts(self):
        """Mutation of the guard: with `planned_risk_refusal` neutralised the zero-risk candidate reaches the pricing and
        the run raises (real costs) / divides by zero (flat fee). The tests above pass only because of the rule."""
        self.bt.planned_risk_refusal = lambda *a, **k: None
        with self.assertRaises(RC.CostRefused):
            self.bt.simulate(self._mixed(), 0.0, cost_profile=FTMO)
        with self.assertRaises(ZeroDivisionError):
            self.bt.simulate([_trade(1, sym="BTCUSDT", entry=2000.0, stop=2000.0, r_planned=None)], 0.0005)


class IctProducerSide(unittest.TestCase):
    """Root cause pinned on the PRODUCER (scripts/ict-scan.py setup_candidate): under B-EX=fill the entry is the FVG's far
    edge (a long's `f["lo"]` = the HIGH of the gap's first candle) and the stop is the lowest low of [reference bar ..
    MSS bar]. When the gap's first candle IS a flat (H == L) bar at that extreme -- the real US500 1m case, 2023-03-07
    06:54Z, V=1 -- the two are the same number. iofed / ce put the entry strictly inside the gap, so they cannot."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("ict_scan_zr", os.path.join(ROOT, "scripts", "ict-scan.py"))
        cls.ict = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.ict)

    def _inputs(self):
        def bar(i, o, h, l, c):
            return {"time": f"2023-03-07T06:{50 + i:02d}:00Z", "open": o, "high": h, "low": l, "close": c, "volume": 1}
        c = [bar(0, 101.0, 101.5, 100.8, 101.0), bar(1, 101.0, 101.2, 100.6, 100.7),
             bar(2, 100.0, 100.0, 100.0, 100.0),                     # the flat sweep bar: H == L == the extreme low
             bar(3, 100.1, 100.9, 100.0, 100.8),                     # gap centre
             bar(4, 100.8, 101.4, 100.5, 101.3)]                     # MSS bar: L[4] > H[2] -> bull FVG lo=100.0 hi=100.5
        m = {"i": 4, "type": "bull", "level": 101.0, "disp": True, "origin": 100.0, "ext": 100.0, "ext_i": 2,
             "leg_lo": 2, "leg_hi": 4, "vol_mult": None, "cisd": None}
        fvg = {"type": "bull", "i": 3, "lo": 100.0, "hi": 100.5, "ce": 100.25, "mitigated": False, "inverted_at": None}
        a = {"mss": [m], "pools": [], "pct": 0.2, "dr_source": "t", "lo": 99.0, "hi": 110.0, "unswept": [],
             "fvgs_all": [fvg]}
        return a, c

    def _su(self, ex, **extra):
        a, c = self._inputs()
        opts = {"fx_braid_optional": True, "fx_b2a_fvg_in_leg": True, "fx_b_ex": ex}
        opts.update(extra)
        return self.ict.setup_candidate(a, c, 12, opts=opts)

    def test_fill_puts_the_entry_on_the_stop(self):
        su = self._su("fill")
        self.assertTrue(su["complete"])
        self.assertEqual((su["entry"], su["stop"]), (100.0, 100.0))
        self.assertIsNone(su["R"])                                     # risk 0 -> no planned R
        self.assertEqual(_bt().planned_risk_refusal(su["side"], su["entry"], su["stop"], 0.01), "zero")

    def test_iofed_and_ce_keep_a_positive_risk_on_the_same_bars(self):
        for ex in ("iofed", "ce"):
            su = self._su(ex)
            self.assertGreater(su["entry"], su["stop"], ex)
            self.assertIsNone(_bt().planned_risk_refusal(su["side"], su["entry"], su["stop"], 0.01), ex)

    def test_a_stop_buffer_moves_the_stop_off_the_entry(self):
        su = self._su("fill", fx_b_buf="0.1atr")
        self.assertGreater(su["entry"], su["stop"])


if __name__ == "__main__":
    unittest.main()
