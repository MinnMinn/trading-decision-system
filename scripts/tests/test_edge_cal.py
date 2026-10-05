"""scripts/research/edge_cal.py on hand-built bars and calendars (no history, no outcome).

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_edge_cal
(docs/plans/2026-10-04-cal-us-index-calendar-preregistration-DRAFT.md [CAL-P1])
"""
import datetime
import importlib.util
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


C = _load("edge_cal", "scripts/research/edge_cal.py")
import real_costs as RC  # noqa: E402  (edge_cal put scripts/ on sys.path)

Z = RC.server_zone("mt5_bridge_ftmo")[1]
UTC = datetime.timezone.utc
CAL = C.M1.NyseCalendar()
FAKE_FOMC = {datetime.date(2019, 3, 20): (14, 0), datetime.date(2019, 6, 19): (14, 0), datetime.date(2019, 9, 18): (14, 0),
             datetime.date(2019, 12, 11): (14, 0)}            # synthetic dates for the test, NOT a sourced calendar


def candles(start, end, drift_days, drift=0.005, clock=(12, 50)):
    """Server-day 5m bars 01:05-23:45 server time on weekdays; a zig-zag around a flat price, plus `drift` accrued
    linearly from the day's first bar to the bar opening at `clock` New York on `drift_days`."""
    out, d, px = [], start, 100.0
    while d <= end:
        if d.weekday() < 5:
            slots = [datetime.datetime(d.year, d.month, d.day, 1, 5, tzinfo=Z) + datetime.timedelta(minutes=5 * k)
                     for k in range(272)]
            utc = [t.astimezone(UTC) for t in slots]
            ny = [t.astimezone(C.NY) for t in utc]
            stop = next((k for k, t in enumerate(ny) if t.date() == d and (t.hour, t.minute) == clock), None)
            prev = px
            for k, t in enumerate(utc):
                base = px * (1 + (drift * min(k, stop) / stop if (d in drift_days and stop) else 0.0))
                c = base * (1 + 0.0005 * (1 if k % 2 else -1))
                out.append({"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "open": prev, "high": max(prev, c),
                            "low": min(prev, c), "close": c})
                prev = c
        d += datetime.timedelta(days=1)
    return out


def series(drift_days, clock=(12, 50)):
    EC = C.EC
    c = candles(datetime.date(2018, 10, 1), datetime.date(2019, 12, 31), drift_days, clock=clock)
    return EC.Series("US500", c, Z, end="9999-12-31T00:00:00Z", sigma_every_day=True)


class Calendars(unittest.TestCase):
    def test_pre_holidays(self):
        ph = C.pre_holidays(CAL, 2019, 2019)
        for d in (datetime.date(2019, 7, 3), datetime.date(2019, 11, 27), datetime.date(2019, 12, 24),
                  datetime.date(2019, 4, 18), datetime.date(2019, 5, 24)):
            self.assertIn(d, ph)
        ph18 = C.pre_holidays(CAL, 2018, 2018)
        self.assertNotIn(datetime.date(2018, 12, 4), ph18)       # 2018-12-05 is a special closure, not a holiday

    def test_m1_read_days(self):
        m1 = C.m1_read_days(CAL)
        self.assertIn(datetime.date(2019, 5, 28), m1)            # the day after T-4 (2019-05-24) of May 2019
        self.assertIn(datetime.date(2019, 6, 4), m1)             # reversal: decided 2019-06-03, held the next NYSE day
        self.assertIn(datetime.date(2019, 5, 22), m1)            # placebo t = 2019-05-21 (Tue 05-28 minus 7), held 05-22
        self.assertNotIn(datetime.date(2019, 5, 24), m1)         # placebo return day not before T-4 (05-24): not kept
        self.assertNotIn(datetime.date(2023, 5, 25), m1)         # M1 confirmation never ran
        self.assertTrue(all(datetime.date(2018, 1, 1) <= d <= datetime.date(2021, 9, 30) for d in m1))

    def test_read_days_take_g7_days_from_the_series_itself(self):
        s = series(set())
        drop = C.read_days(s, CAL)
        tom = C.F4.tom_days(s)
        self.assertTrue(tom)
        self.assertTrue(all(drop[d] == "g7_turn_of_month" for d in tom))
        self.assertIn(datetime.date(2019, 5, 31), drop)          # last weekday with bars of May 2019
        self.assertIn(datetime.date(2019, 7, 3), drop)           # 3rd weekday of July 2019: pre-holiday AND G7-read
        self.assertEqual(drop[datetime.date(2019, 5, 28)], "m1_discovery")

    def test_exit_clock(self):
        self.assertEqual(C.exit_clock("pre_fomc", (14, 0)), (13, 50))
        self.assertEqual(C.exit_clock("pre_fomc", (14, 15)), (14, 5))
        self.assertEqual(C.exit_clock("pre_holiday"), (12, 50))

    def test_load_fomc(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "f.json")
            json.dump({"events": [{"date": "2019-03-20", "release_et": "14:00", "scheduled": True}]}, open(p, "w"))
            with self.assertRaises(SystemExit):
                C.load_fomc(p)                                  # unsourced
            json.dump({"_source": ["x"], "_retrieved_utc": "y",
                       "events": [{"date": "2019-03-20", "release_et": "14:00", "scheduled": True},
                                  {"date": "2020-03-15", "release_et": "17:00", "scheduled": False},
                                  {"date": "2020-03-18", "release_et": "14:00", "scheduled": True, "cancelled": True}]},
                      open(p, "w"))
            self.assertEqual(C.load_fomc(p), {datetime.date(2019, 3, 20): (14, 0)})
            json.dump({"_source": ["x"], "_retrieved_utc": "y",
                       "events": [{"date": "2019-03-20", "release_et": "14:00", "scheduled": True}] * 2}, open(p, "w"))
            with self.assertRaises(SystemExit):
                C.load_fomc(p)


class Rows(unittest.TestCase):
    def test_pre_holiday_drift_is_found_as_excess(self):
        ph = {d: None for d in C.pre_holidays(CAL, 2019, 2019)}
        s = series(set(ph))
        rows, skipped = C.event_rows(s, CAL, ph, "pre_holiday", set(ph), None, end_day=datetime.date(2019, 12, 31))
        self.assertGreaterEqual(len(rows), 7)
        for r in rows:
            self.assertAlmostEqual(r["excess"], 0.005, delta=0.0015)
            t = datetime.datetime.fromisoformat(r["exit_time"].replace("Z", "+00:00")).astimezone(C.NY)
            self.assertEqual((t.date().isoformat(), t.hour, t.minute), (r["date"], 12, 50))
        st = C.EC.summarise(rows)
        self.assertLess(st["p_one_sided"], 0.01)

    def test_no_drift_no_excess(self):
        ph = {d: None for d in C.pre_holidays(CAL, 2019, 2019)}
        s = series(set())
        rows, _ = C.event_rows(s, CAL, ph, "pre_holiday", set(ph), None, end_day=datetime.date(2019, 12, 31))
        self.assertTrue(rows)
        self.assertTrue(all(abs(r["excess"]) < 0.0015 for r in rows))

    def test_fomc_window_exits_before_the_release(self):
        s = series(set(FAKE_FOMC), clock=(13, 50))
        rows, _ = C.event_rows(s, CAL, FAKE_FOMC, "pre_fomc", set(FAKE_FOMC), None, end_day=datetime.date(2019, 12, 31))
        self.assertEqual(len(rows), 4)
        for r in rows:
            t = datetime.datetime.fromisoformat(r["exit_time"].replace("Z", "+00:00")).astimezone(C.NY)
            self.assertEqual((t.hour, t.minute), (13, 50))
            self.assertAlmostEqual(r["excess"], 0.005, delta=0.0015)

    def test_read_days_are_skipped_untouched_and_kept_out_of_the_null(self):
        ph = {d: None for d in C.pre_holidays(CAL, 2019, 2019)}
        s = series(set(ph))
        g7 = {d: r for d, r in C.read_days(s, CAL).items() if r == "g7_turn_of_month"}
        rows, skipped = C.event_rows(s, CAL, ph, "pre_holiday", set(ph), None, end_day=datetime.date(2019, 12, 31),
                                     drop=g7)
        self.assertNotIn("2019-07-03", {r["date"] for r in rows})
        self.assertGreaterEqual(skipped["read_day:g7_turn_of_month"], 1)
        self.assertTrue(rows)
        for r in rows:
            self.assertAlmostEqual(r["excess"], 0.005, delta=0.0015)

    def test_m1_read_days_leave_2019_without_a_weekday_null(self):
        """M1's discovery read covers ~93 % of the NYSE days of 2018-01 -> 2021-08: with those days out of the null, a
        (year, weekday) cell of 2019 is thinner than MIN_NULL_DAYS, so no 2019 event yields a row (history read only)."""
        ph = {d: None for d in C.pre_holidays(CAL, 2019, 2019)}
        s = series(set(ph))
        rows, skipped = C.event_rows(s, CAL, ph, "pre_holiday", set(ph), None, end_day=datetime.date(2019, 12, 31),
                                     drop=C.read_days(s, CAL))
        self.assertEqual(rows, [])
        self.assertGreaterEqual(skipped["read_day:g7_turn_of_month"] + skipped["read_day:m1_discovery"], 1)
        self.assertGreaterEqual(skipped["thin_null"], 1)

    def test_forward_rows_and_null_start_at_the_seal(self):
        ph = {d: None for d in C.pre_holidays(CAL, 2019, 2019)}
        s = series(set(ph))
        seal = datetime.date(2019, 6, 1)
        rows, skipped = C.event_rows(s, CAL, ph, "pre_holiday", set(ph), None, end_day=datetime.date(2019, 12, 31),
                                     start_day=seal)
        self.assertTrue(rows)
        self.assertTrue(all(r["date"] >= "2019-06-01" for r in rows))
        self.assertGreaterEqual(skipped["outside_span"], 3)       # Jan / Feb / Apr / May 2019 pre-holidays

    def test_the_null_is_weekday_matched(self):
        """Review item 14: a Friday effect alone (drift on EVERY Friday, none for being pre-holiday) must not show as a
        pre-holiday excess on the Friday pre-holidays. The all-weekday null (report-only) would credit it."""
        fridays = {d for d in CAL.days if d.weekday() == 4 and d.year == 2019}
        ph = {d: None for d in C.pre_holidays(CAL, 2019, 2019)}
        s = series(fridays)
        rows, _ = C.event_rows(s, CAL, ph, "pre_holiday", set(ph), None, end_day=datetime.date(2019, 12, 31))
        fri = [r for r in rows if r["weekday"] == 4]
        self.assertGreaterEqual(len(fri), 3)                      # MLK, Presidents', Memorial, Labor Day eves
        for r in fri:
            self.assertAlmostEqual(r["excess"], 0.0, delta=0.0015)
            self.assertGreater(r["excess_all_days"], 0.0025)       # the all-weekday null: ~0.005 x 4/5
        for r in rows:
            if r["weekday"] != 4:
                self.assertAlmostEqual(r["excess"], 0.0, delta=0.0015)

    def test_a_thin_weekday_null_skips_the_event(self):
        ph = {d: None for d in C.pre_holidays(CAL, 2019, 2019)}
        s = series(set(ph))
        seal = datetime.date(2019, 11, 15)                         # ~6 same-weekday days left in 2019
        rows, skipped = C.event_rows(s, CAL, ph, "pre_holiday", set(ph), None, end_day=datetime.date(2019, 12, 31),
                                     start_day=seal)
        self.assertEqual(rows, [])
        self.assertGreaterEqual(skipped["thin_null"], 2)           # 11-27 (Wed) and 12-24 (Tue)
        self.assertNotIn("no_placebo", skipped)

    def test_a_read_writes_only_its_one_output_name(self):
        """Review item 18: a forward read to another path is refused before the seal is even checked."""
        with tempfile.TemporaryDirectory() as tmp:
            argv = sys.argv
            sys.argv = ["edge_cal.py", "run", "--read", "forward", "--out", os.path.join(tmp, "x.json")]
            try:
                with self.assertRaises(SystemExit) as cm:
                    C.main()
            finally:
                sys.argv = argv
            self.assertIn("edge-cal-forward.json", str(cm.exception))

    def test_the_forward_window_takes_no_typed_date(self):
        """Review (2026-10-04, fix round): an earlier --seal-date let pre-seal days into a FRESH window, and an --end past
        the data made the read 'due' on calendar dates whose events then dropped as no_window. Both flags are gone: the
        start comes from the seal commit (prereg_guard.first_forward_day), the end from the data (`last_full_day`)."""
        for flag in (["--seal-date", "2026-01-01"], ["--end", "2031-12-31"]):
            with tempfile.TemporaryDirectory() as tmp:
                argv = sys.argv
                sys.argv = ["edge_cal.py", "run", "--read", "forward", "--out",
                            os.path.join(tmp, "2031-12-31-edge-cal-forward.json")] + flag
                try:
                    with self.assertRaises(SystemExit) as cm:
                        C.main()
                finally:
                    sys.argv = argv
                self.assertEqual(cm.exception.code, 2)                  # argparse: unrecognized argument

    def test_last_full_day_is_the_day_before_the_last_bars_server_day(self):
        c = candles(datetime.date(2019, 7, 1), datetime.date(2019, 7, 3), set())
        self.assertEqual(C.last_full_day(c, Z), datetime.date(2019, 7, 2))
        cut = [x for x in c if x["time"] < "2019-07-03T12:00:00Z"]          # the export stops mid-session on 07-03
        self.assertEqual(C.last_full_day(cut, Z), datetime.date(2019, 7, 2))
        self.assertEqual(C.last_full_day(list(reversed(c)), Z), datetime.date(2019, 7, 2))
        self.assertIsNone(C.last_full_day([], Z))

    def test_forward_due(self):
        seal = datetime.date(2026, 10, 10)
        few = {"pre_holiday": set(range(39)), "pre_fomc": set(range(50))}
        self.assertFalse(C.forward_due(few, seal, datetime.date(2031, 10, 9)))
        self.assertTrue(C.forward_due(few, seal, datetime.date(2031, 10, 10)))
        self.assertTrue(C.forward_due({"pre_holiday": set(range(40)), "pre_fomc": set(range(40))}, seal, seal))

    def test_window_needs_a_dense_previous_day(self):
        s = series(set())
        d = datetime.date(2019, 7, 3)
        rows = s.day_rows[d]
        s.prev_dense[rows[0]] = False
        self.assertIsNone(C.day_window(s, d, (12, 50)))


class Verdicts(unittest.TestCase):
    def test_bh_and_net(self):
        t = {"T1": {"n": 70, "p_one_sided": 0.02, "net_bp": 5.0}, "T2": {"n": 80, "p_one_sided": 0.3, "net_bp": 9.0}}
        v = C.verdicts(t)
        self.assertTrue(v["T1"]["candidate"])
        self.assertFalse(v["T2"]["candidate"])
        v2 = C.verdicts({"T1": {"n": 0}, "T2": {"n": 80, "p_one_sided": 0.04, "net_bp": 1.0}})
        self.assertTrue(v2["T2"]["candidate"])                   # T1 not run enters with p = 1: 0.04 <= 0.10 x 1 / 2
        v3 = C.verdicts({"T1": {"n": 0}, "T2": {"n": 80, "p_one_sided": 0.06, "net_bp": 1.0}})
        self.assertFalse(v3["T2"]["candidate"])


class Guard(unittest.TestCase):
    def test_prereg_constant_is_the_sealed_name_and_draft_exists(self):
        self.assertFalse(C.PREREG.endswith("-DRAFT.md"))
        self.assertTrue(os.path.exists(os.path.join(ROOT, C.PREREG.replace(".md", "-DRAFT.md"))))
        with self.assertRaises(SystemExit):
            C.G.require_sealed(ROOT, C.PREREG.replace(".md", "-DRAFT.md"), C.TAG)

    def test_draft_text_does_not_pass_the_sealed_check(self):
        with open(os.path.join(ROOT, C.PREREG.replace(".md", "-DRAFT.md")), encoding="utf-8") as fh:
            text = fh.read()
        with self.assertRaises(SystemExit):
            C.G.check_sealed_text(text, C.PREREG, C.TAG)

    def test_history_read_is_refused_without_the_owner_override(self):
        self.assertFalse(C.HISTORICAL_READ)
        with tempfile.TemporaryDirectory() as tmp:
            argv = sys.argv
            sys.argv = ["edge_cal.py", "run", "--read", "history", "--out", os.path.join(tmp, "x.json")]
            try:
                with self.assertRaises(SystemExit) as cm:
                    C.main()
            finally:
                sys.argv = argv
            self.assertIn("forward-only", str(cm.exception))
            self.assertFalse(os.path.exists(os.path.join(tmp, "x.json")))

    def test_code_files_exist(self):
        self.assertEqual(len(C.CODE), len(set(C.CODE)))
        for p in C.CODE:
            self.assertTrue(os.path.exists(os.path.join(ROOT, p)), p)

    def test_code_lists_every_module_a_read_loads(self):
        """Every repository module a CAL read loads (fresh, under the trace) is in CODE."""
        C.G.trace_start(ROOT)
        C._load("edge_m1", "scripts/research/edge_m1.py")
        C._load("edge_f4", "scripts/research/edge_f4.py")
        C.G.require_covered(C.CODE)
        loaded = set()
        for m in list(sys.modules.values()):
            f = getattr(m, "__file__", None)
            if not f:
                continue
            rel = os.path.relpath(os.path.abspath(f), ROOT).replace(os.sep, "/")
            if rel.startswith("scripts/") and not rel.startswith("scripts/tests/") and rel.endswith(".py"):
                loaded.add(rel)
        self.assertEqual(sorted(loaded - set(C.CODE)), [])


if __name__ == "__main__":
    unittest.main()
