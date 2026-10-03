"""D4 / D5 (docs/audits/2026-10-02-strategic-diagnosis.md §2 #4, #5).

D4: `performance.metrics(observed_weekdays=W)` adds the weekdays with no trade as EMPTY day blocks, so the prop bootstrap's
horizon counts calendar weekdays, not days that had a trade (v1, kept when W is None). The trading-day objective counts only
non-empty days.
D5: `performance.metrics(risk=r)` runs the probabilities at r (never above the account ceiling); `fund_stats.prop_risk` picks
r from the trade frequency alone.

Hand-built trade lists only: no real history, no evaluation.

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_prop_weekdays_risk
"""
import datetime
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import account_profile as AP   # noqa: E402
import fund_stats as FS        # noqa: E402
import performance as PF       # noqa: E402

FTMO = AP.get("ftmo-challenge-phase1")


def _trades(n, r, start="2023-01-02"):
    d0 = datetime.date.fromisoformat(start)
    out, d = [], d0
    while len(out) < n:
        if d.weekday() < 5:
            out.append({"net_R": r, "R": r, "entry_time": f"{d.isoformat()}T10:00:00Z"})
        d += datetime.timedelta(days=1)
    return out


def _pp(trades, **kw):
    return PF.metrics(trades, account=FTMO, horizon=120, iterations=400, **kw)["prop_pass_probability"]


class WeekdayHorizon(unittest.TestCase):
    def test_none_is_the_v1_reading(self):
        t = _trades(40, 0.3) + _trades(40, -1.0, "2023-06-01")
        self.assertEqual(_pp(t)["value"], _pp(t, observed_weekdays=None)["value"])
        self.assertEqual(_pp(t)["horizon_unit"], "days")

    def test_a_sparse_winner_no_longer_passes_on_calendar_time(self):
        """6 trades in a 261-weekday year, every one +2.5R: v1 replays 120 TRADE days (300R) and passes ~always; in 120
        weekdays the expected 2.8 trades (~7 %) rarely reach +10 %."""
        t = _trades(6, 2.5)
        self.assertGreater(_pp(t)["value"], 0.95)
        cal = _pp(t, observed_weekdays=261)
        self.assertLess(cal["value"], 0.35)
        self.assertEqual(cal["horizon_unit"], "weekdays")
        self.assertEqual((cal["observed_weekdays"], cal["observed_trade_days"]), (261, 6))

    def test_dense_population_is_barely_changed(self):
        t = _trades(250, 0.4)          # a trade every weekday: no empty day to add
        self.assertAlmostEqual(_pp(t)["value"], _pp(t, observed_weekdays=250)["value"], places=6)

    def test_refuses_fewer_weekdays_than_trade_days(self):
        with self.assertRaises(ValueError):
            _pp(_trades(10, 0.5), observed_weekdays=9)

    def test_min_trading_days_counts_only_days_with_a_trade(self):
        """One +11R day among ten, a 6-day horizon, FTMO's four-day objective. A flat TRADED day (0R) counts toward the
        four days, an EMPTY weekday does not: with empty days the target needs four winning draws in six (~0)."""
        fail = {"max_total_drawdown": 0.9}
        kw = dict(risk=0.01, horizon_days=6, iterations=2000, seed=1, ruin_level=0.1, failure=fail, profit_target=0.10,
                  min_days=4)
        _, _, flat = PF._bootstrap_days([[11.0]] + [[0.0]] * 9, **kw)
        _, _, empty = PF._bootstrap_days([[11.0]] + [[]] * 9, **kw)
        self.assertGreater(flat, 0.3)
        self.assertLess(empty, 0.01)


class RiskOverride(unittest.TestCase):
    def test_risk_is_used_and_recorded(self):
        t = _trades(200, 0.1) + _trades(200, -0.1, "2023-11-01")
        r = _pp(t, risk=0.005)
        self.assertEqual(r["risk_per_trade"], 0.005)

    def test_risk_above_the_ceiling_is_refused(self):
        with self.assertRaises(ValueError):
            _pp(_trades(20, 0.5), risk=0.02)


class FrequencyRule(unittest.TestCase):
    def test_grid_choice_follows_frequency(self):
        wd, h = 261, 120
        self.assertEqual(FS.prop_risk(12, wd, h, 0.10, 0.01), 0.01)      # sparse: the ceiling
        self.assertEqual(FS.prop_risk(250, wd, h, 0.10, 0.01), 0.01)     # ~1/day: N=115 -> 0.01 (0.10/(0.005*0.1)=200 > 115)
        self.assertEqual(FS.prop_risk(780, wd, h, 0.10, 0.01), 0.005)    # ~3/day: N=359 -> 0.005
        self.assertEqual(FS.prop_risk(1785, wd, h, 0.10, 0.01), 0.0025)  # ~7/day: N=821 -> 0.0025

    def test_never_above_the_ceiling(self):
        self.assertEqual(FS.prop_risk(5, 261, 120, 0.10, 0.004), 0.0025)
        self.assertEqual(FS.prop_risk(0, 261, 120, 0.10, 0.01), 0.01)

    def test_test_weekdays_counts_mon_to_fri_in_the_union(self):
        folds = [{"test_start": "2023-01-02T00:00:00Z", "test_end": "2023-01-09T00:00:00Z"},     # Mon..Sun: 5
                 {"test_start": "2023-01-06T00:00:00Z", "test_end": "2023-01-11T00:00:00Z"}]     # overlap Fri; +Mon,Tue
        self.assertEqual(FS.test_weekdays(folds), 7)


if __name__ == "__main__":
    unittest.main()
