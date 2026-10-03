"""scripts/research/edge_f6.py on hand-built bars with the REAL FTMO server clock (no history, no outcome).

Covers the server-day boundary and the two weeks a year when US and EU daylight saving disagree (condition (b) of the F6
pre-registration). Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_edge_f6
"""
import datetime
import importlib.util
import os
import sys
import unittest
import zoneinfo

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import real_costs as RC  # noqa: E402

spec = importlib.util.spec_from_file_location("edge_f6", os.path.join(ROOT, "scripts", "research", "edge_f6.py"))
F = importlib.util.module_from_spec(spec)
spec.loader.exec_module(F)
EC = F.EC
UTC = datetime.timezone.utc
NY, BERLIN = zoneinfo.ZoneInfo("America/New_York"), zoneinfo.ZoneInfo("Europe/Berlin")
ZONE = RC.server_zone("mt5_bridge_ftmo")[1]
SELLOFF = datetime.date(2023, 3, 16)            # a Thursday inside the US-DST-only weeks (2023-03-12 .. 03-26)


def candles(first=datetime.date(2023, 1, 30), last=datetime.date(2023, 4, 7)):
    """5m bars around the clock except the 17:00-18:00 New York break and the weekend; prices move only inside the New York
    cash session (a varying daily move, and -3 % on SELLOFF)."""
    out, p = [], 100.0
    t = datetime.datetime(first.year, first.month, first.day, tzinfo=UTC)
    end = datetime.datetime(last.year, last.month, last.day, tzinfo=UTC)
    k = 0
    while t < end:
        ny = t.astimezone(NY)
        wd, m = ny.weekday(), ny.hour * 60 + ny.minute
        closed = (17 * 60 <= m < 18 * 60) or wd == 5 or (wd == 4 and m >= 17 * 60) or (wd == 6 and m < 18 * 60)
        if not closed:
            o = p
            if F.SESSION_OPEN <= m < F.SESSION_CLOSE:
                move = -0.03 if ny.date() == SELLOFF else 0.004 * (((ny.toordinal() % 5) - 2) / 2)
                p = p * (1 + move / 78)
            out.append({"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "open": o, "high": max(o, p) + 0.01,
                        "low": min(o, p) - 0.01, "close": p})
            k += 1
        t += datetime.timedelta(minutes=5)
    return out


def series(c=None):
    return EC.Series("US500", c or candles(), ZONE, end=F.END)


class Clock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = series()
        cls.evs = F.events(cls.s)

    def test_server_day_is_17_to_17_new_york(self):
        rows = self.s.day_rows[datetime.date(2023, 3, 2)]
        self.assertEqual(self.s.dt[rows[0]].astimezone(NY).strftime("%m-%d %H:%M"), "03-01 18:00")
        self.assertEqual(self.s.dt[rows[-1]].astimezone(NY).strftime("%m-%d %H:%M"), "03-02 16:55")

    def test_complete_sessions_and_the_selloff_z(self):
        z = F.session_z(self.s)
        sess = F.sessions(self.s)
        prev = sorted(d for d in sess if d < SELLOFF)[-F.SD_SESSIONS:]
        import statistics
        want = sess[SELLOFF][0] / statistics.stdev(sess[d][0] for d in prev)      # previous sessions only
        self.assertAlmostEqual(z[SELLOFF][0], want)
        self.assertAlmostEqual(sess[SELLOFF][0], (1 - 0.03 / 78) ** 78 - 1)
        self.assertLess(z[SELLOFF][0], -5.0)

    def _ev(self, session_day, window):
        return next(e for e in self.evs if e["session_day"] == session_day and e["window"] == window)

    def test_entry_and_exits_stay_inside_the_next_server_day(self):
        for e in self.evs:
            self.assertEqual(self.s.sday[e["entry_i"]], e["day"])
            self.assertEqual(self.s.sday[e["exit_i"]], e["day"])
            self.assertGreater(e["day"], e["session_day"])
            self.assertGreater(e["entry_i"], e["i"])                      # entry after the trigger bar

    def test_us_dst_only_weeks_move_the_berlin_exit_to_04_new_york(self):
        normal, async_ = datetime.date(2023, 3, 2), SELLOFF
        for day, ny_close in ((normal, "03:00"), (async_, "04:00"), (datetime.date(2023, 3, 30), "03:00")):
            e = self._ev(day, "W1_berlin_0900")
            self.assertEqual((self.s.dt[e["exit_i"]] + F.BAR).astimezone(NY).strftime("%H:%M"), ny_close, day)
            self.assertEqual((self.s.dt[e["exit_i"]] + F.BAR).astimezone(BERLIN).strftime("%H:%M"), "09:00")
            self.assertEqual(self.s.dt[e["entry_i"]].astimezone(NY).strftime("%H:%M"), "19:00")
            w2 = self._ev(day, "W2_newyork_0930")
            self.assertEqual((self.s.dt[w2["exit_i"]] + F.BAR).astimezone(NY).strftime("%H:%M"), "09:30")

    def test_a_friday_session_enters_on_sunday_evening(self):
        e = self._ev(datetime.date(2023, 3, 3), "W2_newyork_0930")
        t = self.s.dt[e["entry_i"]].astimezone(NY)
        self.assertEqual((t.strftime("%a %H:%M"), e["day"]), ("Sun 19:00", datetime.date(2023, 3, 6)))

    def test_truncating_the_future_never_changes_a_past_event(self):
        """The generic leakage probe applied to this detector: every event whose EXIT is before the cut is found, identical,
        on the truncated series."""
        c = candles()
        full = {(e["session_day"], e["window"]): (e["entry_i"], e["exit_i"], round(e["z"], 12)) for e in self.evs}
        for cut in (len(c) // 2, len(c) // 2 + 137, len(c) - 300):
            part = series(c[:cut])
            got = {(e["session_day"], e["window"]): (e["entry_i"], e["exit_i"], round(e["z"], 12)) for e in F.events(part)}
            want = {k: v for k, v in full.items() if v[1] < cut}
            self.assertEqual({k: v for k, v in got.items() if v[1] < cut}, want)

    def test_family_sizes_are_fixed(self):
        self.assertEqual(len(F.family_tests("F6")), 12)
        self.assertEqual(len(F.family_tests("F7")), 4)


if __name__ == "__main__":
    unittest.main()
