"""scripts/research/edge_f4.py on HAND-BUILT bars only (no real history, no outcome).

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_edge_f4
"""
import datetime
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("edge_f4", os.path.join(ROOT, "scripts", "research", "edge_f4.py"))
F4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(F4)
EC = F4.EC
UTC = datetime.timezone.utc


def series(days, start=datetime.date(2020, 1, 6), weekdays_only=False):
    """days: list of per-day bar lists [(o, h, l, c), ...]; one 5m bar each, from 00:00 of consecutive (week)days."""
    out, d = [], start
    for bars in days:
        while weekdays_only and d.weekday() >= 5:
            d += datetime.timedelta(days=1)
        t0 = datetime.datetime(d.year, d.month, d.day, tzinfo=UTC)
        for b, (o, h, l, c) in enumerate(bars):
            t = t0 + datetime.timedelta(minutes=5 * b)
            out.append({"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "open": o, "high": h, "low": l, "close": c})
        d += datetime.timedelta(days=1)
    return EC.Series("XAUUSD", out, UTC, end="9999-12-31T00:00:00Z")


def flat(px, n=60, w=0.1):
    return [(px, px + w, px - w, px)] * n


class Family(unittest.TestCase):
    def test_size_and_allowlist(self):
        self.assertEqual(len(F4.FAMILY), 8 + 3 + 8 + 8 + 6 + 8)
        self.assertEqual(len(set(F4.FAMILY)), len(F4.FAMILY))
        self.assertTrue({k[0] for k in F4.FAMILY} <= set(F4.DETECTORS) == set(F4.HYPOTHESES))
        self.assertTrue(all(s in F4.INDICES for h, s in F4.FAMILY if h == "G7_turn_of_month_long"))


class TSMOM(unittest.TestCase):
    def test_signal_before_entry_and_exit_next_day(self):
        s = series([flat(100 + k) for k in range(70)])
        evs = F4.ev_tsmom(s)
        self.assertTrue(evs and all(e["side"] == 1 for e in evs))
        e = evs[0]
        self.assertLess(e["i"], e["entry_i"])
        self.assertEqual(s.sday[e["i"]], s.sday[e["entry_i"]])                       # signal + entry on day d
        self.assertEqual(s.sday[e["exit_i"]], s.sday[e["entry_i"]] + datetime.timedelta(days=1))
        self.assertEqual(e["exit_i"], s.day_rows[s.sday[e["exit_i"]]][-1])

    def test_signal_ignores_the_entry_day_close(self):
        """Changing day d's LAST bar (the entry bar) must not change day d's signal."""
        base = [flat(100 + k) for k in range(70)]
        a = F4.ev_tsmom(series(base))
        base[65] = base[65][:-1] + [(165, 165, 1, 1)]
        b = F4.ev_tsmom(series(base))
        sa = {x["entry_i"]: x["side"] for x in a}
        sb = {x["entry_i"]: x["side"] for x in b}
        self.assertEqual(sa, sb)


class Breakouts(unittest.TestCase):
    def test_prev_week_levels_use_earlier_weeks_only(self):
        days = [flat(100)] * 7 + [flat(100)] * 2 + [flat(100) + [(100, 200, 100, 200)] + flat(100)]  # a spike on Wed of week 2
        s = series(days)
        lv = F4.prev_week_levels(s)
        wk2 = [d for d in s.day_rows if d.isocalendar()[1] == s.sday[0].isocalendar()[1] + 1]
        self.assertTrue(all(lv[d][0] < 101 for d in wk2))          # week 2 sees week 1 only, never its own spike

    def test_prev_week_breakout_needs_trend(self):
        rising = [flat(100 + k) for k in range(30)]
        last = flat(129, 10) + [(129, 140, 129, 140)] + flat(140, 10)
        s = series(rising + [last])
        evs = F4.ev_prev_week(s)
        self.assertTrue(evs and all(e["side"] == 1 for e in evs))          # with the trend: longs only
        lv = F4.prev_week_levels(s)
        for e in evs:                                                        # the FIRST close above the previous week's high
            rows = s.day_rows[s.sday[e["i"]]]
            self.assertGreater(s.C[e["i"]], lv[s.sday[e["i"]]][0])
            self.assertTrue(all(s.C[j] <= lv[s.sday[e["i"]]][0] for j in rows if j < e["i"]))

    def test_nr7_breakout_both_ways(self):
        days = [flat(100, w=1.0)] * 6 + [flat(100, w=0.2)] + [flat(100, 5) + [(100, 100, 99, 99)] + flat(99, 5)]
        s = series(days)
        evs = F4.ev_nr7(s)
        self.assertEqual([e["side"] for e in evs], [-1])
        self.assertEqual(s.sday[evs[0]["i"]], s.sday[-1])

    def test_no_nr7_when_yesterday_not_narrowest(self):
        days = [flat(100, w=0.2)] * 6 + [flat(100, w=1.0)] + [flat(100, 5) + [(100, 100, 98, 98)] + flat(98, 5)]
        self.assertEqual(F4.ev_nr7(series(days)), [])

    def test_vol_breakout_threshold_from_open_and_yesterday_range(self):
        days = [flat(100, w=1.0)] * 3 + [[(100, 100.5, 99.9, 100.5), (100.5, 101.2, 100.4, 101.1)] + flat(101.1, 5)]
        s = series(days)                                   # yesterday's range 2.0 -> threshold 100 + 1.0
        evs = F4.ev_vol_breakout(s)
        self.assertEqual(len(evs), 1)
        self.assertEqual((evs[0]["side"], s.C[evs[0]["i"]]), (1, 101.1))

    def test_signal_on_the_last_bar_is_not_an_event(self):
        days = [flat(100, w=1.0)] * 3 + [flat(100, 5) + [(100, 110, 100, 110)]]
        self.assertEqual(F4.ev_vol_breakout(series(days)), [])


class TurnOfMonth(unittest.TestCase):
    def test_last_and_first_three_weekdays(self):
        s = series([flat(100, 10)] * 50, start=datetime.date(2020, 1, 1), weekdays_only=True)
        tom = sorted(F4.tom_days(s))
        jan, feb = [d for d in tom if d.month == 1], [d for d in tom if d.month == 2]
        self.assertEqual(jan[-1], datetime.date(2020, 1, 31))
        self.assertEqual(feb[:3], [datetime.date(2020, 2, 3), datetime.date(2020, 2, 4), datetime.date(2020, 2, 5)])
        self.assertNotIn(datetime.date(2020, 2, 6), tom)
        self.assertNotIn(datetime.date(2020, 1, 30), tom)

    def test_long_from_the_first_bar_known_before_the_open(self):
        s = series([flat(100, 10)] * 50, start=datetime.date(2020, 1, 1), weekdays_only=True)
        evs = F4.ev_tom(s)
        self.assertTrue(evs and all(e["side"] == 1 for e in evs))
        for e in evs:
            self.assertEqual(e["entry_i"], s.day_rows[s.sday[e["entry_i"]]][0])
            self.assertLess(s.sday[e["i"]], s.sday[e["entry_i"]])


if __name__ == "__main__":
    unittest.main()
