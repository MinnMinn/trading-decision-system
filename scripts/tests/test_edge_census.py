"""scripts/research/edge_census.py: statistics and event detectors on HAND-BUILT bars only (no real history, no outcome).

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_edge_census
"""
import datetime
import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def _ec():
    spec = importlib.util.spec_from_file_location("edge_census", os.path.join(ROOT, "scripts", "research", "edge_census.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


EC = _ec()
UTC = datetime.timezone.utc


def bars(start, ohlc, step_min=5):
    t0 = datetime.datetime.fromisoformat(start).replace(tzinfo=UTC)
    return [{"time": (t0 + datetime.timedelta(minutes=step_min * k)).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "open": o, "high": h, "low": l, "close": c} for k, (o, h, l, c) in enumerate(ohlc)]


def series(candles):
    return EC.Series("XAUUSD", candles, UTC)        # UTC as the "server" zone keeps the tests readable


class Stats(unittest.TestCase):
    def test_t_survival_matches_known_quantiles(self):
        self.assertAlmostEqual(EC.t_sf(1.959964, 10 ** 6), 0.025, places=4)
        self.assertAlmostEqual(EC.t_sf(2.228139, 10), 0.025, places=5)      # t_{0.975, 10}
        self.assertAlmostEqual(EC.t_sf(-2.228139, 10), 0.975, places=5)

    def test_cr1_collapses_to_the_cluster_sums(self):
        mu, se, df = EC.cr1([1.0, 1.0, -1.0, -1.0], ["a", "a", "b", "b"])
        self.assertEqual((mu, df), (0.0, 1))
        self.assertAlmostEqual(se, (2 / 1 * (2 ** 2 + 2 ** 2)) ** 0.5 / 4)
        self.assertIsNone(EC.cr1([1.0, 2.0], ["a", "a"])[1])

    def test_bh(self):
        self.assertEqual(EC.bh([0.001, 0.02, 0.04, 0.5], 0.10), {0, 1, 2})
        self.assertEqual(EC.bh([0.2, 0.3], 0.10), set())

    def test_family_is_fixed(self):
        self.assertEqual(len(EC.FAMILY), 6 * 2 * 3 + 3 + 1)
        self.assertEqual(len(set(EC.FAMILY)), len(EC.FAMILY))


class Detectors(unittest.TestCase):
    def _two_days(self, day2):
        """Day 1: a flat 100-102 range over 288 bars; day 2 as given, padded flat to 288 bars."""
        d1 = [(101.0, 102.0, 100.0, 101.0)] * 288
        d2 = day2 + [(101.0, 101.5, 100.5, 101.0)] * (288 - len(day2))
        return series(bars("2023-03-06T00:00:00", d1 + d2))

    def test_prev_day_sweep_reclaim_signals_on_the_close_and_enters_next_open(self):
        s = self._two_days([(101.0, 101.5, 100.5, 101.0)] * 10 + [(101.5, 102.6, 101.4, 101.8)])
        evs = EC.ev_prev_day(s, "sweep")
        self.assertEqual(len(evs), 1)
        ev = evs[0]
        self.assertEqual((ev["side"], ev["i"], ev["entry_i"]), (-1, 288 + 10, 288 + 11))

    def test_acceptance_is_a_close_beyond(self):
        s = self._two_days([(101.0, 101.5, 100.5, 101.0)] * 5 + [(101.5, 102.8, 101.4, 102.5)])
        evs = EC.ev_prev_day(s, "accept")
        self.assertEqual([(e["side"], e["i"]) for e in evs], [(+1, 288 + 5)])

    def test_no_event_uses_a_future_bar(self):
        """Truncating the series after the signal bar must not change the detected signal."""
        day2 = [(101.0, 101.5, 100.5, 101.0)] * 10 + [(101.5, 102.6, 101.4, 101.8)]
        full = self._two_days(day2)
        cut = series(bars("2023-03-06T00:00:00", [(101.0, 102.0, 100.0, 101.0)] * 288 + day2))
        self.assertEqual([e["i"] for e in EC.ev_prev_day(full, "sweep")], [e["i"] for e in EC.ev_prev_day(cut, "sweep")])

    def test_fvg_fills_at_the_edge_after_the_gap_exists(self):
        flat = [(100.0, 100.4, 99.6, 100.0)] * 30
        seq = flat + [(100.0, 100.2, 99.9, 100.1),           # m-1: high 100.2
                      (100.1, 102.0, 100.1, 101.9),          # m: displacement up
                      (101.9, 102.5, 101.0, 102.3),          # m+1: low 101.0 > 100.2 -> gap [100.2, 101.0]
                      (102.3, 102.4, 101.5, 101.6),
                      (101.6, 101.7, 100.8, 101.2)]          # touches 101.0
        day1 = [(100.0, 100.4, 99.6, 100.0)] * 288          # a dense previous day (PIT density gate)
        s = series(bars("2023-03-05T00:00:00", day1 + seq + [(101.2, 101.3, 101.1, 101.2)] * 200))
        evs = EC.ev_fvg(s)
        self.assertEqual(len(evs), 1)
        self.assertEqual((evs[0]["side"], evs[0]["entry_i"], evs[0]["entry_px"]), (+1, 288 + 34, 101.0))


class Outcomes(unittest.TestCase):
    def test_rollover_crossing_is_skipped(self):
        s = series(bars("2023-03-06T23:30:00", [(100.0, 100.5, 99.5, 100.0)] * 20))

        class C:
            def round_trip(self, a, b, stat="median"):
                return 0.0
        s._vol = {d: 0.001 for d in s.sday}
        o, why = EC.outcome(s, {"i": 2, "entry_i": 3, "entry_px": None, "fixed_exit": None, "side": 1}, 6, C())
        self.assertIsNone(o)
        self.assertEqual(why, "crosses_rollover")


if __name__ == "__main__":
    unittest.main()
