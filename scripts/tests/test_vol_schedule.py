"""scripts/research/vol_schedule.py: phase-specific challenge and the funded-stage replay on hand-built trades (no history).

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_vol_schedule
"""
import datetime
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("vol_schedule", os.path.join(ROOT, "scripts", "research", "vol_schedule.py"))
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)
UTC = datetime.timezone.utc
T0 = datetime.datetime(2024, 1, 1, tzinfo=UTC)          # a Monday


def daily(R, n, start=T0, c="X"):
    """One trade per weekday, entry 10:00, exit 12:00, result R (in units of the 1 % risk)."""
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            e = d.replace(hour=10)
            x = d.replace(hour=12)
            out.append({"entry": e, "exit": x, "entry_day": e.date().isoformat(), "exit_day": x.date().isoformat(),
                        "R": R if not callable(R) else R(len(out)), "mae": min(0.0, R if not callable(R) else R(len(out))), "c": c})
        d += datetime.timedelta(days=1)
    return out


class Challenge(unittest.TestCase):
    def test_phase_two_runs_on_its_own_trade_list(self):
        p = V.pol("realised")
        t1 = daily(2.0, 300)                              # +2 % a day: P1 (+10 %) on day 5
        t2 = daily(0.0, 300)                              # flat: P2 never passes
        self.assertIsNone(V.challenge2(t1, t2, T0, p)["funded_at"])
        t2 = daily(1.0, 300)                              # +1 % a day: P2 (+5 %) passes
        c = V.challenge2(t1, t2, T0, p)
        self.assertIsNotNone(c["funded_at"])
        self.assertEqual(c["attempts"], 1)

    def test_a_fail_costs_a_new_attempt_inside_the_horizon(self):
        p = V.pol("realised")
        bad = daily(lambda k: -6.0 if k == 0 else 2.0, 300)    # a -6 % first day fails P1 on the daily limit
        c = V.challenge2(bad, daily(1.0, 300), T0, p, retry_horizon=V.HORIZON_DAYS, end=T0 + datetime.timedelta(days=V.HORIZON_DAYS))
        self.assertEqual(c["attempts"], 2)
        self.assertTrue(c["first_fail"])
        self.assertIsNotNone(c["funded_at"])


class Funded(unittest.TestCase):
    def test_monthly_payout_is_the_split_of_the_profit_and_resets(self):
        p = V.pol("realised")
        tr = daily(0.5, 200)                              # +0.5 % a day
        paid, breached = V.funded_stage(tr, T0, T0 + datetime.timedelta(days=61), p)
        self.assertFalse(breached)
        # two payouts (day 30, day 60); each month ~ 21-22 weekdays x 0.5 % (dd3 never throttles above 97 %)
        self.assertGreater(paid, 2 * V.SPLIT * 0.10)
        self.assertLess(paid, 2 * V.SPLIT * 0.12)

    def test_a_breach_ends_the_account(self):
        p = V.pol("realised")
        tr = daily(lambda k: -6.0 if k == 3 else 0.5, 200)
        paid, breached = V.funded_stage(tr, T0, T0 + datetime.timedelta(days=120), p)
        self.assertTrue(breached)
        self.assertEqual(paid, 0.0)


if __name__ == "__main__":
    unittest.main()
