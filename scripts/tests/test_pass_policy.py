"""scripts/research/pass_policy.py on hand-built trades (no history).

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_pass_policy
"""
import datetime
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("pass_policy", os.path.join(ROOT, "scripts", "research", "pass_policy.py"))
PP = importlib.util.module_from_spec(spec)
spec.loader.exec_module(PP)
UTC = datetime.timezone.utc
POL = dict(book="x", risk=0.01, throttle="none", day_stop=None)
D0 = datetime.datetime(2022, 1, 3, 10, tzinfo=UTC)              # a Monday


def tr(day, R, hour=10, hold_h=2, c="a"):
    e = D0 + datetime.timedelta(days=day, hours=hour - 10)
    x = e + datetime.timedelta(hours=hold_h)
    return {"entry": e, "exit": x, "entry_day": e.date().isoformat(), "exit_day": x.date().isoformat(), "R": R, "c": c}


class Phase(unittest.TestCase):
    def test_pass_needs_target_and_four_trading_days(self):
        trades = [tr(0, 5.0), tr(1, 5.0), tr(2, 0.0), tr(3, 0.0), tr(4, 0.0)]
        o, end, _ = PP.run_phase(trades, 0, D0, 0.10, POL)
        self.assertEqual(o, "pass")
        self.assertEqual(end, trades[3]["exit"])                 # +10 % after day 2, but only the 4th traded day passes

    def test_daily_loss_fails(self):
        o, end, _ = PP.run_phase([tr(0, -3.0, hour=10), tr(0, -3.0, hour=11)], 0, D0, 0.10, POL)
        self.assertEqual((o, end.hour), ("fail", 13))

    def test_day_stop_blocks_the_next_entry_only_that_day(self):
        trades = [tr(0, -2.5, hour=9, hold_h=1), tr(0, -3.0, hour=11), tr(1, 1.0)]
        o, _e, _k = PP.run_phase(trades, 0, D0 - datetime.timedelta(hours=2), 0.10, dict(POL, day_stop=0.02))
        self.assertEqual(o, "open")                               # without the stop the day would reach -5.5 % and fail
        o2, _e2, _k2 = PP.run_phase(trades, 0, D0 - datetime.timedelta(hours=2), 0.10, POL)
        self.assertEqual(o2, "fail")

    def test_throttle_and_ceiling(self):
        self.assertEqual(PP.throttle_mult("dd3", 0.99), 1.0)
        self.assertEqual(PP.throttle_mult("dd3", 0.95), 0.5)
        self.assertEqual(PP.throttle_mult("dd3", 0.93), 0.25)
        trades = [tr(d, 10.0) for d in range(6)]
        o, end, _ = PP.run_phase(trades, 0, D0, 0.10, dict(POL, risk=0.05))   # 5 % asked, clamped to the 1 % ceiling
        self.assertEqual((o, end), ("pass", trades[3]["exit"]))
        self.assertTrue(all(r <= PP.CEILING for r in PP.RISKS))


class Challenge(unittest.TestCase):
    def test_p2_starts_after_p1_and_counts_calendar_days(self):
        trades = [tr(d, 4.0) for d in range(0, 20)]
        r = PP.challenge(trades, D0, POL)
        self.assertEqual(r["attempts"], 1)
        self.assertFalse(r["first_fail"])
        self.assertGreater(r["funded_days"], 4)

    def test_retry_restarts_after_a_fail(self):
        trades = [tr(0, -6.0), tr(1, -6.0)] + [tr(d, 4.0) for d in range(3, 30)]
        self.assertIsNone(PP.challenge(trades, D0, POL)["funded_days"])
        r = PP.challenge(trades, D0, POL, retry_horizon=122)
        self.assertEqual(r["attempts"], 2)
        self.assertTrue(r["first_fail"])
        self.assertIsNotNone(r["funded_days"])


class Bootstrap(unittest.TestCase):
    def test_paths_keep_time_of_day_and_holding_time(self):
        trades = [tr(d, 1.0, hour=10 + d % 3) for d in range(0, 40) if (D0 + datetime.timedelta(days=d)).weekday() < 5]
        for base, path in PP.bootstrap_paths(trades, 3, 30, 5, 1):
            self.assertTrue(path)
            for t in path:
                self.assertIn(t["entry"].hour, (10, 11, 12))
                self.assertEqual(t["exit"] - t["entry"], datetime.timedelta(hours=2))
                self.assertLess(t["entry"].weekday(), 5)

    def test_haircut_shifts_each_component_mean(self):
        raw = {"a": [{"entry_time": "2022-01-03T10:00:00Z", "exit_time": "2022-01-03T12:00:00Z", "server_day": "2022-01-03",
                      "R": r} for r in (1.0, 0.0)]}
        self.assertEqual([t["R"] for t in PP.prepare(raw, ["a"], 0.5)], [0.75, -0.25])


if __name__ == "__main__":
    unittest.main()
