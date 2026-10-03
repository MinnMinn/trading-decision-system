"""scripts/research/edge_amd.py on HAND-BUILT bars only (no real history, no outcome). Winter dates: New York = UTC-5,
London = UTC, server (Europe/Athens) = UTC+2, so Asia = 01:00-05:00Z, London = 08:00-11:00Z, NY open 13:30Z, NY exit 21:00Z.

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_edge_amd
"""
import datetime
import importlib.util
import os
import unittest
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("edge_amd", os.path.join(ROOT, "scripts", "research", "edge_amd.py"))
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)
EC = A.EC
SERVER = ZoneInfo("Europe/Athens")
UTC = datetime.timezone.utc


def build(last_day_price):
    """Three flat dense server days, then a fourth whose price at UTC time t is last_day_price(t) (a float or (o,h,l,c))."""
    start = datetime.datetime(2022, 1, 9, 22, 0, tzinfo=UTC)          # server midnight, Monday 2022-01-10 server date
    bars = []
    for d in range(4):
        for b in range(288):
            t = start + datetime.timedelta(days=d, minutes=5 * b)
            if d < 3:
                px = 100.0 + (0.05 if b % 2 else -0.05)
                o, h, l, c = px, px + 0.1, px - 0.1, px
            else:
                v = last_day_price(t)
                o, h, l, c = v if isinstance(v, tuple) else (v, v + 0.05, v - 0.05, v)
            bars.append({"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "open": o, "high": h, "low": l, "close": c})
    return EC.Series("XAUUSD", bars, SERVER, end="9999-12-31T00:00:00Z")


def at(t, h, m=0):
    return t.hour == h and t.minute == m


def day_of(s):
    return datetime.date(2022, 1, 13)                                  # the NY date of the fourth server day


def london_reversal_up(t):
    if at(t, 8, 0):
        return 99.9                                                     # the London open
    if 8 <= t.hour < 9:
        return 99.0                                                     # London sweeps the Asia low (99.95)
    if t.hour >= 9 and (t.hour, t.minute) < (13, 30):
        return 100.0                                                    # back above the London open, Asia high (100.05) intact
    return 100.0 if t.hour < 8 else 101.0


class Profiles(unittest.TestCase):
    def test_london_reversal_long_into_new_york(self):
        s = build(london_reversal_up)
        days = A.ny_days(s)
        v = days[day_of(s)]
        self.assertEqual(A.classify(s, v), "reversal_up")
        evs = [e for e in A.ev_amd1(s, days) if s.sday[e["i"]] == s.sday[-1]]
        self.assertEqual(len(evs), 1)
        e = evs[0]
        self.assertEqual(e["side"], 1)
        self.assertEqual(s.dt[e["entry_i"]].strftime("%H:%M"), "13:30")    # 08:30 New York
        self.assertEqual(s.dt[e["fixed_exit"]].strftime("%H:%M"), "20:55")  # last bar before 16:00 New York
        self.assertLess(e["i"], e["entry_i"])

    def test_expansion_is_never_traded(self):
        s = build(lambda t: 98.0 if t.hour >= 8 else 100.0)            # London breaks the Asia low and stays below
        days = A.ny_days(s)
        self.assertEqual(A.classify(s, days[day_of(s)]), "expansion")
        last = s.sday[-1]
        self.assertFalse([e for e in A.ev_amd1(s, days) + A.ev_amd2(s, days) if s.sday[e["i"]] == last])

    def test_ny_reversal_after_london_consolidation(self):
        def f(t):
            if at(t, 14, 0):
                return (100.0, 101.0, 99.95, 99.98)                    # NY sweeps the Asia+London high, closes back inside
            return 100.0
        s = build(f)
        days = A.ny_days(s)
        self.assertEqual(A.classify(s, days[day_of(s)]), "consolidation")
        evs = [e for e in A.ev_amd2(s, days) if s.sday[e["i"]] == s.sday[-1]]
        self.assertEqual([(e["side"], s.dt[e["i"]].strftime("%H:%M")) for e in evs], [(-1, "14:00")])

    def test_po3_open_needs_the_larger_excursion_against_the_close(self):
        def f(t):
            if t.hour == 3:
                return 99.0                                             # manipulation 1.0 below the open (100.0)
            if 5 <= t.hour and (t.hour, t.minute) < (13, 30):
                return 100.3                                            # back above the open, smaller excursion above
            return 100.0
        s = build(f)
        evs = [e for e in A.ev_amd3(s) if s.sday[e["i"]] == s.sday[-1]]
        self.assertEqual([e["side"] for e in evs], [1])

    def test_family(self):
        self.assertEqual(len(A.FAMILY), 3 * 8)
        self.assertEqual(set(A.DETECTORS), set(A.RULES))


if __name__ == "__main__":
    unittest.main()
