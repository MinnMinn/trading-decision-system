"""scripts/research/edge_followup.py on HAND-BUILT bars only (no real history, no outcome).

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_edge_followup
"""
import datetime
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("edge_followup", os.path.join(ROOT, "scripts", "research", "edge_followup.py"))
EF = importlib.util.module_from_spec(spec)
spec.loader.exec_module(EF)
EC = EF.EC
UTC = datetime.timezone.utc


def bars(start, ohlc):
    t0 = datetime.datetime.fromisoformat(start).replace(tzinfo=UTC)
    return [{"time": (t0 + datetime.timedelta(minutes=5 * k)).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "open": o, "high": h, "low": l, "close": c} for k, (o, h, l, c) in enumerate(ohlc)]


class Costs0:
    def round_trip(self, a, b, stat="median"):
        return 0.0


class FollowUp(unittest.TestCase):
    def setUp(self):
        d1 = [(101.0, 102.0, 100.0, 101.0)] * 288
        d2 = ([(101.0, 101.5, 100.5, 101.0)] * 10 + [(101.5, 102.6, 101.4, 101.8)]
              + [(101.8, 103.0, 101.7, 102.9)] * 277)
        self.s = EC.Series("XAUUSD", bars("2024-03-04T00:00:00", d1 + d2), UTC, end="9999-12-31T00:00:00Z")
        self.s._vol = {d: 0.001 for d in self.s.sday}

    def test_family_and_directions_are_fixed(self):
        self.assertEqual(len(EF.FAMILY), 3 * 5 * 3)
        self.assertEqual(EF.DIRECTION, {"E1_prev_day_sweep_reclaim": -1, "E2_prev_day_acceptance": -1, "E5_fvg_retrace": 1})
        self.assertNotIn("XAGUSD", EF.SYMBOLS)

    def test_eod_exit_is_the_last_bar_of_the_entry_server_day(self):
        eod = EF._eod_index(self.s)
        evs = EC.ev_prev_day(self.s, "sweep")
        rows, _ = EF.window_rows(self.s, evs, "eod", Costs0(), "2024-03-01T00:00:00Z", "9999-12-31T00:00:00Z", eod)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["exit_i"], 2 * 288 - 1)
        self.assertEqual(rows[0]["entry_i"], 288 + 11)

    def test_window_excludes_events_before_its_start(self):
        eod = EF._eod_index(self.s)
        evs = EC.ev_prev_day(self.s, "sweep")
        rows, _ = EF.window_rows(self.s, evs, 24, Costs0(), "2024-03-06T00:00:00Z", "9999-12-31T00:00:00Z", eod)
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
