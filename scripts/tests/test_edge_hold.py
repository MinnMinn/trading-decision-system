"""scripts/research/edge_hold.py on hand-built bars (no history, no outcome).

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_edge_hold
"""
import datetime
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("edge_hold", os.path.join(ROOT, "scripts", "research", "edge_hold.py"))
H = importlib.util.module_from_spec(spec)
spec.loader.exec_module(H)
EC = H.EC
UTC = datetime.timezone.utc


def series(n_days=8, short_day=None):
    t0 = datetime.datetime(2020, 1, 6, tzinfo=UTC)
    out = []
    for d in range(n_days):
        nb = 10 if d == short_day else 60
        for b in range(nb):
            t = t0 + datetime.timedelta(days=d, minutes=5 * b)
            px = 100.0 + d
            out.append({"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "open": px, "high": px + 0.1, "low": px - 0.1, "close": px})
    return EC.Series("XAUUSD", out, UTC, end="9999-12-31T00:00:00Z")


class Hold(unittest.TestCase):
    def test_family(self):
        self.assertEqual(len(H.FAMILY), 9)

    def test_forward_ends_skip_sparse_days(self):
        s = series(short_day=3)
        ends = H.forward_ends(s)
        d2 = sorted(s.day_rows)[2]
        self.assertEqual([s.sday[x] for x in ends[d2]], [sorted(s.day_rows)[k] for k in (4, 5, 6)])   # day 3 is sparse
        self.assertTrue(all(x == s.day_rows[s.sday[x]][-1] for x in ends[d2]))

    def test_increment_starts_at_the_entry_days_close(self):
        s = series()
        eod = H.F3._eod(s)
        ends = H.forward_ends(s)
        ev = EC._ev(s, 5, 1)
        a0, x = H.increment(s, ev, 2, ends, eod)
        self.assertEqual(a0, s.day_rows[s.sday[5]][-1])
        self.assertEqual(s.sday[x], s.sday[5] + datetime.timedelta(days=2))
        last_bar = EC._ev(s, s.day_rows[s.sday[0]][-1], 1)
        self.assertIsNone(H.increment(s, last_bar, 1, ends, eod))        # entry would be the next day: not this rule's trade


if __name__ == "__main__":
    unittest.main()
