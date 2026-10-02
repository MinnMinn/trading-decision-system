"""scripts/research/edge_f3.py on HAND-BUILT bars only (no real history, no outcome).

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_edge_f3
"""
import datetime
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("edge_f3", os.path.join(ROOT, "scripts", "research", "edge_f3.py"))
F3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(F3)
EC = F3.EC
UTC = datetime.timezone.utc


def days_series(closes, bars_per_day=50):
    t0 = datetime.datetime(2020, 1, 6, tzinfo=UTC)
    out = []
    for d, c in enumerate(closes):
        for b in range(bars_per_day):
            t = t0 + datetime.timedelta(days=d, minutes=5 * b)
            out.append({"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "open": c, "high": c + 0.1, "low": c - 0.1, "close": c})
    return EC.Series("XAUUSD", out, UTC, end="9999-12-31T00:00:00Z")


class F3Tests(unittest.TestCase):
    def test_family(self):
        self.assertEqual(len(F3.FAMILY), 5 * (1 + 1 + 2 + 1 + 1))
        self.assertNotIn("XAGUSD", F3.SYMBOLS)

    def test_daily_momentum_uses_previous_days_only(self):
        s = days_series([100 + k for k in range(30)])
        evs = F3.ev_daily(s, "mom")
        self.assertTrue(evs and all(e["side"] == 1 for e in evs))
        first = evs[0]
        self.assertEqual(s.sday[first["entry_i"]], s.sday[first["i"]] + datetime.timedelta(days=1))

    def test_shock_reversal_trades_against_the_shock(self):
        closes = [100.0 + (0.1 if k % 2 else -0.1) for k in range(25)] + [110.0, 110.0]
        evs = F3.ev_daily(s := days_series(closes), "shock")
        self.assertEqual([e["side"] for e in evs], [-1])
        self.assertEqual(s.sday[evs[0]["entry_i"]], s.sday[s.day_rows[next(reversed(list(s.day_rows)))][0]])


if __name__ == "__main__":
    unittest.main()
