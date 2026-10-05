"""scripts/research/edge_m1.py on HAND-BUILT bars with the REAL FTMO server clock and the rule-based NYSE calendar (no real
history, no outcome). Pre-registration: docs/plans/2026-10-03-edge-m1-month-end-preregistration.md.

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_edge_m1
"""
import datetime
import importlib.util
import json
import math
import os
import statistics
import sys
import tempfile
import unittest
import zoneinfo

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import instruments as INS  # noqa: E402
import real_costs as RC  # noqa: E402

spec = importlib.util.spec_from_file_location("edge_m1", os.path.join(ROOT, "scripts", "research", "edge_m1.py"))
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
EC = M.EC
UTC = datetime.timezone.utc
NY = zoneinfo.ZoneInfo("America/New_York")
ZONE = RC.server_zone("mt5_bridge_ftmo")[1]
CAL = M.NyseCalendar()
BOARD = M.BoardCalendar()
D = datetime.date
DAY = datetime.timedelta(days=1)


# ------------------------------------------------------------------------------------------------ hand-built data
def candle(d, o, h, lo, c):
    """A 1D bar stamped like the FTMO export: the server-day start (00:00 server) in UTC."""
    t = datetime.datetime(d.year, d.month, d.day, tzinfo=ZONE).astimezone(UTC)
    return {"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "open": o, "high": h, "low": lo, "close": c}


def path(days, seed):
    """Deterministic prices (no randomness): gap a_k at the open, move b_k to the close."""
    out, p = [], 100.0
    for k, d in enumerate(days):
        a = (((k * 7 + seed) % 13) - 6) / 4000.0
        b = (((k * 11 + 3 * seed) % 17) - 8) / 1500.0
        o = p * (1 + a)
        c = o * (1 + b)
        out.append(candle(d, o, max(o, c) * 1.003, min(o, c) * 0.997, c))
        p = c
    return out


def yield_rows(days, nulls=(), extra=()):
    rows = [{"date": str(d), "value": None if d in nulls else round(2.0 + 0.5 * math.sin(k / 9.0), 4)}
            for k, d in enumerate(days)]
    return sorted(rows + [{"date": str(d), "value": v} for d, v in extra], key=lambda r: r["date"])


def fake_costs(base=1e-4):
    """An edge_census.Costs with a hand-set hourly table (its own round_trip is the code under test)."""
    c = EC.Costs.__new__(EC.Costs)
    c.ref = 1.0
    c.med = {h: base * (1 + h / 100.0) for h in range(24)}
    c.p90 = {h: 2.0 * c.med[h] for h in range(24)}
    return c


def table_costs(fallback_buckets=()):
    """The FTMO table frame (export offset UTC+3) over the hand-set table; `fallback_buckets` have no recorded bar."""
    notes = {(st, h): "overall_fallback" if h in fallback_buckets else "hour" for st in M.TableCosts.STATS for h in range(24)}
    return M.TableCosts(fake_costs(), 3, notes)


def stamp(t):
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def hourly_bars(days, thin_until=None, server_hours=(1, 8, 15, 23)):
    """1H bar TIMES (no prices) on each server day: a D1-filled day (d <= thin_until) has ONE bar at server 00:00, an intraday
    day one bar at each of `server_hours` (server clock)."""
    out = []
    for d in days:
        hs = (0,) if thin_until is not None and d <= thin_until else server_hours
        out += [{"time": stamp(datetime.datetime(d.year, d.month, d.day, h, tzinfo=ZONE))} for h in hs]
    return out


LATE = {"US30": D(2019, 2, 8), "AUS200": D(2019, 2, 8)}           # the real first server day of both (§2)


def context(first=D(2017, 12, 1), last=D(2021, 9, 30), poison_from=None, drop=(), price=None, thin_until=D(2018, 12, 31)):
    """US members trade NYSE days; non-US members every weekday (their sessions do not stop on NYSE-only holidays). Cost
    hours come from SessionHours over hand-built 1H times (D1-filled to `thin_until`), costs from the table frame."""
    nyse = [d for d in CAL.days if first <= d <= last]
    weekdays = [first + k * DAY for k in range((last - first).days + 1) if (first + k * DAY).weekday() < 5]
    mem = M.members()
    daily, hours, costs, raw = {}, {}, {}, {}
    for k, sym in enumerate(mem["US"] + mem["NON_US"]):
        base = nyse if sym in mem["US"] else weekdays
        ds = [d for d in base if d >= LATE.get(sym, first) and (sym, d) not in drop]
        cs = path(ds, seed=k)
        for c, d in zip(cs, ds):
            if poison_from is not None and d >= poison_from:
                c["open"] = 0.0                             # any return computed on these days raises ZeroDivisionError
            if price == "none":
                c.update(open=None, high=None, low=None, close=None)
        h1 = hourly_bars(ds, thin_until)
        daily[sym] = M.Daily(sym, cs, ZONE, sd_exclude=CAL.holidays if sym in mem["US"] else ())
        hours[sym] = M.SessionHours(h1, ZONE, zoneinfo.ZoneInfo(EC.OPEN_LOCAL[sym][0]))
        costs[sym] = table_costs()
        raw[sym] = (cs, h1)
    ys = yield_rows(nyse)
    return {"cal": CAL, "members": mem, "daily": daily, "hours": hours, "costs": costs, "yields": M.Yields(ys, CAL),
            "raw": raw, "yield_rows": ys}


# ------------------------------------------------------------------------------------------------ §2 NYSE calendar
class NyseCalendar(unittest.TestCase):
    def test_known_closures(self):
        closed = {D(2019, 4, 19): "Good Friday", D(2022, 6, 20): "Juneteenth Sunday -> Monday",
                  D(2021, 12, 24): "Christmas Saturday -> Friday", D(2023, 1, 2): "New Year Sunday -> Monday",
                  D(2020, 7, 3): "Independence Saturday -> Friday", D(2021, 7, 5): "Independence Sunday -> Monday",
                  D(2027, 6, 18): "Juneteenth Saturday -> Friday", D(2026, 7, 3): "Independence Saturday -> Friday",
                  D(2018, 12, 5): "special closure (Bush)", D(2025, 1, 9): "special closure (Carter)",
                  D(2019, 1, 21): "MLK", D(2020, 2, 17): "Washington's Birthday", D(2024, 5, 27): "Memorial",
                  D(2025, 9, 1): "Labor", D(2023, 11, 23): "Thanksgiving", D(2024, 3, 29): "Good Friday"}
        for d, why in closed.items():
            self.assertFalse(CAL.is_open(d), f"{d} {why}")

    def test_known_openings(self):
        # 2021-12-31: New Year 2022 fell on a SATURDAY and NYSE does NOT close the preceding Friday (NYSE Rule 7.2's
        # end-of-yearly-accounting-period exception; nyse.com/markets/hours-calendars: "Because the holiday falls on Saturday,
        # January 1, 2028, no New Year's Day holiday is observed"). 2021-06-18: Juneteenth not observed before 2022.
        for d in (D(2021, 12, 31), D(2027, 12, 31), D(2021, 6, 18), D(2023, 11, 24), D(2018, 12, 24), D(2018, 12, 6)):
            self.assertTrue(CAL.is_open(d), d)

    def test_easter(self):
        for y, e in ((2018, D(2018, 4, 1)), (2019, D(2019, 4, 21)), (2024, D(2024, 3, 31)), (2025, D(2025, 4, 20))):
            self.assertEqual(M.easter(y), e)

    def test_business_days_per_year(self):
        want = {2018: 251, 2019: 252, 2020: 253, 2021: 252, 2022: 251, 2023: 250, 2024: 252, 2025: 250}
        self.assertEqual({y: sum(1 for d in CAL.days if d.year == y) for y in want}, want)

    def test_last_day_and_week4(self):
        self.assertEqual(CAL.last(2018, 3), D(2018, 3, 29))                      # Good Friday 2018-03-30
        self.assertEqual(CAL.week4(2018, 3), [D(2018, 3, 23), D(2018, 3, 26), D(2018, 3, 27), D(2018, 3, 28),
                                              D(2018, 3, 29)])
        self.assertEqual(CAL.week4(2018, 12), [D(2018, 12, 24), D(2018, 12, 26), D(2018, 12, 27), D(2018, 12, 28),
                                               D(2018, 12, 31)])
        self.assertEqual(CAL.last(2021, 12), D(2021, 12, 31))
        self.assertEqual(CAL.last(2022, 12), D(2022, 12, 30))
        self.assertEqual(CAL.last(2024, 3), D(2024, 3, 28))
        self.assertEqual(CAL.next(D(2018, 3, 29)), D(2018, 4, 2))
        self.assertEqual(CAL.prev(D(2018, 4, 2)), D(2018, 3, 29))

    def test_return_days_are_T_minus_3_to_T_plus_1_us_and_the_2nd_weekday_non_us(self):
        w4 = CAL.week4(2018, 3)                                                   # Thu 2018-03-29 = T (Good Friday 03-30)
        self.assertEqual([M.return_day(CAL, t, "US") for t in w4],
                         [D(2018, 3, 26), D(2018, 3, 27), D(2018, 3, 28), D(2018, 3, 29), D(2018, 4, 2)])
        # non-US: the 2nd weekday server day after t -- Good Friday is a weekday (a member without a bar there has a missing
        # day, never a shifted one)
        self.assertEqual([M.return_day(CAL, t, "NON_US") for t in w4],
                         [D(2018, 3, 27), D(2018, 3, 28), D(2018, 3, 29), D(2018, 3, 30), D(2018, 4, 2)])

    def test_the_non_us_lag_is_two_sessions_across_nyse_only_holidays(self):
        """Review 2026-10-03: NYSE counting held a non-US position 3+ European sessions after the signal across Memorial Day /
        Thanksgiving; the weekday count holds it over the 2nd session every week."""
        cases = {D(2018, 5, 24): D(2018, 5, 28), D(2018, 5, 25): D(2018, 5, 29),          # Memorial Day Mon 2018-05-28
                 D(2021, 11, 24): D(2021, 11, 26), D(2021, 11, 26): D(2021, 11, 30),      # Thanksgiving Thu 2021-11-25
                 D(2019, 3, 22): D(2019, 3, 26)}                                          # Fri -> Tue over a weekend
        for t, d in cases.items():
            self.assertEqual(M.return_day(CAL, t, "NON_US"), d, t)
        self.assertEqual(CAL.next(D(2018, 5, 25), 2), D(2018, 5, 30))                    # what NYSE counting would give
        self.assertEqual(M.return_day(CAL, D(2018, 5, 25), "US"), D(2018, 5, 29))

    def test_episode_months(self):
        self.assertEqual([len(M.month_range(*M.EPISODES[r])) for r in M.READS], [44, 30, 30])
        self.assertEqual((M.episode_read("2021-08"), M.episode_read("2021-09"), M.episode_read("2024-03"),
                          M.episode_read("2026-09")), ("discovery", "confirmation", "exposed", None))


# ------------------------------------------------------------------------------------------------ §2 server clock
class ServerClock(unittest.TestCase):
    def test_real_header_bar_times_map_to_the_server_date(self):
        # First / last US500 1D bar and the first US30 1D bar of the FTMO export headers (index.json "first" / "last").
        self.assertEqual(M.server_date("2017-12-28T22:00:00Z", ZONE), D(2017, 12, 29))      # winter: server = UTC + 2
        self.assertEqual(M.server_date("2026-09-27T21:00:00Z", ZONE), D(2026, 9, 28))       # summer: server = UTC + 3
        self.assertEqual(M.server_date("2019-02-07T22:00:00Z", ZONE), D(2019, 2, 8))

    def test_server_day_is_17_to_17_new_york_across_dst(self):
        d = D(2023, 2, 20)
        while d <= D(2023, 11, 20):
            start = datetime.datetime(d.year, d.month, d.day, tzinfo=ZONE)
            prev = d - datetime.timedelta(days=1)
            self.assertEqual(start, datetime.datetime(prev.year, prev.month, prev.day, 17, 0, tzinfo=NY), d)
            self.assertEqual(M.server_day_end_utc(d, ZONE), datetime.datetime(d.year, d.month, d.day, 17, 0, tzinfo=NY))
            d += datetime.timedelta(days=1)

    def test_same_mapping_as_edge_census_series(self):
        days = [d for d in CAL.days if D(2023, 3, 1) <= d <= D(2023, 11, 15)]
        cs = path(days, 3)
        s = EC.Series("US500", cs, ZONE, end=M.END)
        self.assertEqual(s.sday, [M.server_date(c["time"], ZONE) for c in cs])
        self.assertEqual(M.Daily("US500", cs, ZONE).days, s.sday)
        self.assertEqual(M.Daily("US500", cs, ZONE).days, days)

    def test_incomplete_duplicate_and_off_midnight_bars(self):
        cs = [candle(D(2026, 9, 24), 1, 1, 1, 1), candle(D(2026, 9, 25), 1, 1, 1, 1), candle(D(2026, 9, 28), 1, 1, 1, 1)]
        dl = M.Daily("US500", cs, ZONE, exported_at="2026-09-28T17:03:54Z")         # the real US500 1D export instant
        self.assertEqual(dl.days, [D(2026, 9, 24), D(2026, 9, 25)])
        self.assertEqual(dl.qa["incomplete_at_export_dropped"], 1)
        dup = cs[:2] + [dict(cs[1], time="2026-09-25T09:00:00Z")]                   # same server day, not midnight
        dl = M.Daily("US500", dup, ZONE)
        self.assertEqual(dl.days, [D(2026, 9, 24)])                                  # never one picked
        self.assertEqual((dl.qa["duplicate_server_day_dropped"], dl.qa["bar_time_not_server_midnight"]), (1, 1))

    @staticmethod
    def hourly(first_utc, n):
        return [{"time": stamp(first_utc + datetime.timedelta(hours=k))} for k in range(n)]

    def test_session_hours_are_server_clock_hours_with_a_server_clock_fallback(self):
        winter = self.hourly(datetime.datetime(2023, 3, 1, 23, tzinfo=UTC), 23)     # 18:00 NY .. 16:00 NY bar (server UTC+2)
        summer = self.hourly(datetime.datetime(2023, 3, 15, 22, tzinfo=UTC), 23)    # US DST (server UTC+3), Europe not yet
        thin = [{"time": "2023-03-06T22:00:00Z"}, {"time": "2023-03-16T21:00:00Z"}]  # D1-filled: one bar at server 00:00
        h = M.SessionHours(list(reversed(winter + summer + thin)), ZONE, NY)        # order-free (min / max instant)
        at = lambda s: datetime.datetime.fromisoformat(s).replace(tzinfo=UTC)      # noqa: E731
        # the SAME server hours (01:00 / 23:00) in winter and summer; the true UTC instants differ by one hour
        self.assertEqual(h.get(D(2023, 3, 2)), (1, 23, "1h", at("2023-03-01T23:00"), at("2023-03-02T21:00")))
        self.assertEqual(h.get(D(2023, 3, 16)), (1, 23, "1h", at("2023-03-15T22:00"), at("2023-03-16T20:00")))
        self.assertEqual(h.thin_days, {D(2023, 3, 7), D(2023, 3, 17)})
        self.assertEqual(h.get(D(2023, 3, 7)), (1, 23, "server_clock_constant", at("2023-03-06T23:00"), at("2023-03-07T21:00")))
        self.assertEqual(h.get(D(2023, 3, 17)), (1, 23, "server_clock_constant", at("2023-03-16T22:00"), at("2023-03-17T20:00")))
        self.assertEqual(h.get(D(2023, 4, 5))[:3], (1, 23, "server_clock_constant_no_1h"))
        self.assertTrue(h.modes_match_constant())
        self.assertEqual(h.mode, {(2, -5): (1, 23), (3, -4): (1, 23)})
        hb = M.SessionHours(winter + summer + thin, ZONE, zoneinfo.ZoneInfo("Europe/Berlin"))
        self.assertEqual((hb.regime(D(2023, 3, 16)), hb.regime(D(2023, 4, 5))), ((3, 1), (3, 2)))
        self.assertEqual(hb.get(D(2023, 3, 17))[:3], (1, 23, "server_clock_constant"))  # regime-free: no later-era modes

    def test_the_modal_hours_qa_catches_a_session_off_the_constant(self):
        off = self.hourly(datetime.datetime(2023, 3, 1, 22, tzinfo=UTC), 23)       # server 00:00 .. 22:00
        h = M.SessionHours(off, ZONE, NY)
        self.assertEqual((h.get(D(2023, 3, 2))[:3], h.off_constant_days), ((0, 22, "1h"), 1))
        self.assertFalse(h.modes_match_constant())
        self.assertEqual(h.shifted_minus_1h_days, [D(2023, 3, 2)])               # a whole session one hour early: flagged


# ------------------------------------------------------------------------------------------------ §4 cost-table hour frame
class CostFrame(unittest.TestCase):
    """Review 2026-10-03 (major): the spread table buckets SERVER hour - 3 (the export-time offset) all year; a winter day
    looked up by its true UTC hours read server 02:00 / 00:00 (the empty daily-break bucket -> silent overall fallback)."""
    WINTER_T, WINTER_D = D(2023, 1, 9), D(2023, 1, 10)
    SUMMER_T, SUMMER_D = D(2023, 7, 10), D(2023, 7, 11)

    @staticmethod
    def _hours(*first_utc):
        bars = []
        for f in first_utc:
            bars += ServerClock.hourly(f, 23)
        return M.SessionHours(bars, ZONE, NY)

    def _rows(self, costs, hours, cases):
        bars = []
        for t, d in cases:
            bars += [candle(CAL.last(*M._prev_month(t.year, t.month)), 100, 100, 100, 100), candle(d, 100.0, 101, 99, 100.5)]
        dl = M.Daily("US500", sorted(bars, key=lambda c: c["time"]), ZONE)
        sigs = [{"episode": f"{t:%Y-%m}", "t": t, "T": CAL.last(t.year, t.month), "missing": [], "s": 1,
                 "T_prev": CAL.last(*M._prev_month(t.year, t.month))} for t, _d in cases]
        out = []
        for sg in sigs:
            rows, _ = M.member_rows(M.episode_read(sg["episode"]), CAL, [sg], dl, "US", hours, costs)
            out += rows
        return out

    def test_winter_and_summer_days_are_priced_at_the_same_table_buckets(self):
        hours = self._hours(datetime.datetime(2023, 1, 9, 23, tzinfo=UTC), datetime.datetime(2023, 7, 10, 22, tzinfo=UTC))
        c = table_costs(fallback_buckets={21})
        rows = self._rows(c, hours, [(self.WINTER_T, self.WINTER_D), (self.SUMMER_T, self.SUMMER_D)])
        self.assertEqual([r["d"] for r in rows], [self.WINTER_D, self.SUMMER_D])
        for r in rows:
            self.assertEqual((r["entry_hour_server"], r["exit_hour_server"]), (1, 23))
            self.assertEqual((r["cost_bucket_in"], r["cost_bucket_out"]), (22, 20))
            self.assertAlmostEqual(r["cost"], c.costs.round_trip(22, 20))
            self.assertAlmostEqual(r["cost90"], c.costs.round_trip(22, 20, "p90"))
            self.assertEqual((r["cost_fallback"], r["cost_hours_source"]), ([], "1h"))
        self.assertEqual([(r["entry_hour_utc"], r["exit_hour_utc"]) for r in rows], [(23, 21), (22, 20)])   # audit: true UTC

    def test_a_leg_in_an_unrecorded_bucket_is_counted_never_silent(self):
        hours = self._hours(datetime.datetime(2023, 1, 9, 22, tzinfo=UTC))           # first bar server 00:00 (the break)
        rows = self._rows(table_costs(fallback_buckets={21}), hours, [(self.WINTER_T, self.WINTER_D)])
        self.assertEqual((rows[0]["cost_bucket_in"], rows[0]["cost_bucket_out"]), (21, 19))
        self.assertEqual(rows[0]["cost_fallback"], ["median:in", "p90:in"])
        self.assertEqual(M.test_stats(rows)["cost_fallback_rows"], 1)
        b = M.basket_rows([rows, [dict(rows[0], symbol="USTEC", cost_fallback=[])]])
        self.assertEqual(b[0]["cost_fallback"], ["US500:median:in", "US500:p90:in"])

    def test_the_real_us500_table(self):
        """The REAL FTMO cost table (edge_census.Costs + the symbolspec export; a cost model, no outcome): offset UTC+3,
        bucket 21 (= server 00:00, the daily break) has no recorded bar, and a January and a July day are both priced at
        buckets (22, 20) with no fallback -- where the true-UTC winter exit hour 21 would have hit the fallback."""
        tc = M.TableCosts.load("US500")
        self.assertEqual(tc.offset, 3)
        self.assertEqual(tc.fallback_buckets(), [21])
        hours = self._hours(datetime.datetime(2023, 1, 9, 23, tzinfo=UTC), datetime.datetime(2023, 7, 10, 22, tzinfo=UTC))
        for d in (self.WINTER_D, self.SUMMER_D):
            h = hours.get(d)
            self.assertEqual((tc.bucket(h[0]), tc.bucket(h[1])), (22, 20), d)
            self.assertEqual(tc.fallback_legs(h[0], h[1]), [], d)
            self.assertEqual(tc.round_trip(h[0], h[1]), tc.costs.round_trip(22, 20))
        self.assertEqual(tc.notes[("median", hours.get(self.WINTER_D)[4].hour)], "overall_fallback")   # the old lookup


# ------------------------------------------------------------------------------------------------ §2-§3 H.15 / Board calendar
class BoardCalendar(unittest.TestCase):
    def test_board_closures(self):
        closed = {D(2019, 10, 14): "Columbus", D(2019, 11, 11): "Veterans", D(2018, 11, 12): "Veterans Sunday -> Monday",
                  D(2023, 11, 10): "Veterans Saturday -> Friday", D(2021, 6, 18): "Juneteenth 2021 Saturday -> Friday",
                  D(2021, 12, 31): "New Year 2022 Saturday -> Friday (NYSE open)", D(2018, 12, 24): "no H.15 (ALFRED)",
                  D(2018, 12, 5): "mourning", D(2025, 1, 9): "mourning", D(2021, 1, 20): "no H.15 (ALFRED)"}
        for d, why in closed.items():
            self.assertFalse(BOARD.is_open(d), f"{d} {why}")
        for d in (D(2019, 4, 19), D(2019, 12, 24), D(2025, 12, 24), D(2025, 12, 26), D(2021, 6, 17), D(2022, 6, 17)):
            self.assertTrue(BOARD.is_open(d), d)                                   # Good Friday / Dec 24 2019 / Dec 2025
        self.assertTrue(CAL.is_open(D(2019, 10, 14)) and CAL.is_open(D(2021, 12, 31)))

    def test_the_lag_is_the_latest_value_posted_by_t(self):
        """Review 2026-10-03: the H.15 is 'not posted on holidays or in the event that the Board is closed', so on an NYSE day
        the Board is closed y(t-1) had NOT been posted at t's decision."""
        days = [d for d in CAL.days if D(2018, 10, 1) <= d <= D(2022, 1, 31)]
        y = M.Yields(yield_rows(days), CAL)
        want = {D(2019, 10, 14): D(2019, 10, 10), D(2019, 10, 11): D(2019, 10, 10),
                D(2019, 10, 15): D(2019, 10, 14),       # a value dated on the Board holiday is posted with 10-11's on 10-15
                D(2019, 11, 11): D(2019, 11, 7), D(2021, 12, 31): D(2021, 12, 29), D(2018, 12, 24): D(2018, 12, 20),
                D(2018, 12, 26): D(2018, 12, 24),       # 12-21 and 12-24 (bond market open) both posted on 12-26
                D(2019, 12, 24): D(2019, 12, 23), D(2021, 6, 18): D(2021, 6, 16)}
        for t, d in want.items():
            self.assertEqual(y.available_at(t)[0], d, t)
        # the real file has no DGS10 value on Columbus Day (bond market closed): then t + 1 reads the Friday value
        y2 = M.Yields(yield_rows(days, nulls={D(2019, 10, 14)}), CAL)
        self.assertEqual((y2.available_at(D(2019, 10, 14))[0], y2.available_at(D(2019, 10, 15))[0]),
                         (D(2019, 10, 10), D(2019, 10, 11)))
        us = M.Daily("US500", [candle(d, 100, 100, 100, 100) for d in days], ZONE)
        sg = M.signal_at(CAL, us, y, "2019-10", D(2019, 10, 14))                   # a falsification day of 2019-10
        self.assertEqual((sg["y_lag_date"], sg["y_base_date"], sg["missing"]), (D(2019, 10, 10), D(2019, 9, 30), []))


# ------------------------------------------------------------------------------------------------ §3 signal
class Signal(unittest.TestCase):
    EP, T_PREV, T = "2019-03", D(2019, 2, 28), D(2019, 3, 25)

    def _us500(self, base=100.0, at_t=102.0):
        return M.Daily("US500", [candle(self.T_PREV, base, base, base, base), candle(self.T, at_t, at_t, at_t, at_t)], ZONE)

    def _yields(self, **kw):
        vals = {D(2019, 2, 27): 1.95, self.T_PREV: 2.00, D(2019, 3, 21): 2.05, D(2019, 3, 22): 2.10, self.T: 9.99}
        vals.update(kw.pop("vals", {}))
        rows = [{"date": str(d), "value": v} for d, v in sorted(vals.items())]
        return M.Yields(rows, CAL)

    def test_formula_by_hand(self):
        self.assertEqual(CAL.last(2019, 2), self.T_PREV)
        self.assertIn(self.T, CAL.week4(2019, 3))
        sg = M.signal_at(CAL, self._us500(), self._yields(), self.EP, self.T)
        r_e, r_b = 0.02, -8.5 * (2.10 - 2.00) / 100
        want = 0.6 * (1 + r_e) / (0.6 * (1 + r_e) + 0.4 * (1 + r_b)) - 0.6
        self.assertAlmostEqual(sg["R_E"], r_e)
        self.assertAlmostEqual(sg["R_B"], r_b)
        self.assertAlmostEqual(sg["S"], want)
        self.assertEqual((sg["s"], sg["s_eq"]), (-1, -1))                 # stocks beat bonds -> sell equities
        self.assertAlmostEqual(sg["S_eq"], 0.6 * 1.02 / (0.6 * 1.02 + 0.4) - 0.6)
        self.assertEqual((sg["y_lag_date"], sg["y_base_date"]), (D(2019, 3, 22), self.T_PREV))

    def test_yield_is_lagged_one_nyse_day(self):
        a = M.signal_at(CAL, self._us500(), self._yields(), self.EP, self.T)
        b = M.signal_at(CAL, self._us500(), self._yields(vals={self.T: -5.0}), self.EP, self.T)
        self.assertEqual(a["S"], b["S"])                                   # y(t) itself is never read
        c = M.signal_at(CAL, self._us500(), self._yields(vals={D(2019, 3, 22): 2.20}), self.EP, self.T)
        self.assertNotEqual(a["S"], c["S"])

    def test_yield_nulls_fall_back_to_the_previous_nyse_day_with_a_value(self):
        sg = M.signal_at(CAL, self._us500(), self._yields(vals={D(2019, 3, 22): None, self.T_PREV: None}), self.EP, self.T)
        self.assertEqual((sg["y_lag_date"], sg["y_base_date"]), (D(2019, 3, 21), D(2019, 2, 27)))
        self.assertAlmostEqual(sg["R_B"], -8.5 * (2.05 - 1.95) / 100)

    def test_yield_on_a_non_nyse_day_is_ignored(self):
        y = M.Yields([{"date": "2019-02-15", "value": 2.0}, {"date": "2019-02-18", "value": 7.0}], CAL)   # Presidents' Day
        self.assertEqual(y.asof(D(2019, 2, 19)), (D(2019, 2, 15), 2.0))
        self.assertEqual(y.qa["value_on_non_nyse_day_ignored"], 1)

    def test_bonds_beat_stocks_buys_equities(self):
        sg = M.signal_at(CAL, self._us500(at_t=99.0), self._yields(vals={D(2019, 3, 22): 1.80}), self.EP, self.T)
        self.assertLess(sg["S"], 0)
        self.assertEqual(sg["s"], 1)

    def test_a_missing_bar_is_a_missing_signal(self):
        us = M.Daily("US500", [candle(self.T_PREV, 100, 100, 100, 100)], ZONE)
        sg = M.signal_at(CAL, us, self._yields(), self.EP, self.T)
        self.assertEqual((sg["missing"], sg["s"]), (["no_us500_bar_t"], None))
        us = M.Daily("US500", [candle(self.T, 100, 100, 100, 100)], ZONE)
        self.assertEqual(M.signal_at(CAL, us, self._yields(), self.EP, self.T)["missing"], ["no_us500_bar_base"])


# ------------------------------------------------------------------------------------------------ §3 events
class Events(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = context(last=D(2019, 6, 28))

    def _sigs(self, eps):
        return [sg for ep in eps for sg in M.signals(CAL, self.ctx["daily"]["US500"], self.ctx["yields"], ep)]

    def test_return_days_per_group(self):
        sigs = self._sigs(["2018-03"])
        us, _ = M.events(CAL, sigs, self.ctx["daily"]["USTEC"], "US")
        nus, _ = M.events(CAL, sigs, self.ctx["daily"]["DE40"], "NON_US")
        self.assertEqual([e["d"] for e in us], [D(2018, 3, 26), D(2018, 3, 27), D(2018, 3, 28), D(2018, 3, 29),
                                                D(2018, 4, 2)])
        self.assertEqual([e["d"] for e in nus], [D(2018, 3, 27), D(2018, 3, 28), D(2018, 3, 29), D(2018, 3, 30),
                                                 D(2018, 4, 2)])
        self.assertEqual([e["s"] for e in us], [sg["s"] for sg in sigs])
        self.assertTrue(all(e["d"] > e["t"] for e in us + nus))

    def test_a_missing_member_bar_is_a_missing_day_never_filled(self):
        ctx = context(last=D(2018, 4, 30), drop={("USTEC", D(2018, 3, 28))})
        sigs = [sg for sg in M.signals(CAL, ctx["daily"]["US500"], ctx["yields"], "2018-03")]
        evs, skip = M.events(CAL, sigs, ctx["daily"]["USTEC"], "US")
        self.assertNotIn(D(2018, 3, 28), [e["d"] for e in evs])
        self.assertEqual((len(evs), skip["no_bar_on_return_day"]), (4, 1))

    def test_member_history_must_cover_the_episode_base(self):
        sigs = self._sigs(["2019-01", "2019-02", "2019-03"])
        evs, skip = M.events(CAL, sigs, self.ctx["daily"]["US30"], "US")
        self.assertEqual({e["episode"] for e in evs}, {"2019-03"})          # §5: US30 / AUS200 from 2019-03
        self.assertEqual(skip["member_history_starts_after_base"], 10)

    def test_basket_is_the_equal_weight_of_the_members_with_a_bar(self):
        a = [{"episode": "e", "t": 1, "T": 2, "d": D(2019, 3, 26), "s": 1, "r": 0.01, "cost": 1e-4, "cost90": 2e-4,
              "symbol": "US500"}]
        b = [dict(a[0], r=0.03, cost=3e-4, cost90=4e-4, symbol="USTEC"), dict(a[0], d=D(2019, 3, 27), r=0.02, symbol="USTEC")]
        out = M.basket_rows([a, b])
        self.assertEqual(len(out), 2)
        self.assertAlmostEqual(out[0]["r"], 0.02)
        self.assertAlmostEqual(out[0]["cost"], 2e-4)
        self.assertEqual(out[0]["members"], ["US500", "USTEC"])
        self.assertAlmostEqual(out[1]["r"], 0.02)                            # one member that day: its own return


# ------------------------------------------------------------------------------------------------ §4 statistics and verdicts
class Statistics(unittest.TestCase):
    X = [1, -1, 1, 1, -1, -1, 1, -1, 1, -1, 1, 1]
    Y = [0.004, -0.002, 0.001, 0.006, 0.000, -0.003, 0.002, 0.001, 0.005, -0.004, -0.001, 0.003]
    G = ["a", "a", "a", "b", "b", "b", "c", "c", "d", "d", "e", "e"]

    def test_ols_cr1_matches_the_direct_sandwich(self):
        x, y, g = [float(v) for v in self.X], self.Y, self.G
        n, k = len(y), 2
        sx, sxx = sum(x), sum(v * v for v in x)
        det = n * sxx - sx * sx
        inv = [[sxx / det, -sx / det], [-sx / det, n / det]]
        b1 = (n * sum(a * b for a, b in zip(x, y)) - sx * sum(y)) / det
        b0 = (sum(y) - b1 * sx) / n
        u = [b - b0 - b1 * a for a, b in zip(x, y)]
        meat = [[0.0, 0.0], [0.0, 0.0]]
        for c in set(g):
            s0 = sum(e for e, cc in zip(u, g) if cc == c)
            s1 = sum(a * e for a, e, cc in zip(x, u, g) if cc == c)
            meat = [[meat[0][0] + s0 * s0, meat[0][1] + s0 * s1], [meat[1][0] + s1 * s0, meat[1][1] + s1 * s1]]
        mm = lambda p, q: [[sum(p[i][m] * q[m][j] for m in range(2)) for j in range(2)] for i in range(2)]  # noqa: E731
        V = mm(mm(inv, meat), inv)
        G = len(set(g))
        f = G / (G - 1) * (n - 1) / (n - k)
        o = M.ols_cr1(y, x, g)
        self.assertAlmostEqual(o["gamma"], b1, places=12)
        self.assertAlmostEqual(o["intercept"], b0, places=12)
        self.assertAlmostEqual(o["se_gamma"], math.sqrt(f * V[1][1]), places=12)
        self.assertAlmostEqual(o["se_intercept"], math.sqrt(f * V[0][0]), places=12)
        self.assertEqual(o["df"], G - 1)
        self.assertAlmostEqual(o["p_one_sided"], EC.t_sf(b1 / math.sqrt(f * V[1][1]), G - 1), places=12)

    def test_the_calendar_drift_lands_in_the_intercept_not_in_gamma(self):
        o = M.ols_cr1([0.0010] * len(self.X), [float(v) for v in self.X], self.G)
        self.assertAlmostEqual(o["gamma"], 0.0, places=15)
        self.assertAlmostEqual(o["intercept"], 0.0010, places=15)

    def test_a_planted_slope_is_recovered(self):
        x = [float(v) for v in self.X] * 3
        y = [0.0005 + 0.002 * a + e for a, e in zip(x, [v / 100 for v in self.Y] * 3)]   # small noise (not x-orthogonal)
        g = [f"{c}{k // 12}" for k, c in enumerate(self.G * 3)]
        o = M.ols_cr1(y, x, g)
        self.assertAlmostEqual(o["gamma"], 0.002, delta=2e-4)
        self.assertLess(o["p_one_sided"], 0.01)

    def test_constant_position_has_no_gamma(self):
        self.assertNotIn("gamma", M.ols_cr1([0.1, 0.2, 0.3], [1.0, 1.0, 1.0], ["a", "b", "c"]))

    def _stats(self, p, net, net90=1.0):
        return {"n": 50, "p_one_sided": p, "net_bp": net, "net_bp_p90": net90}

    def test_discovery_bh_m5_and_the_net_gate(self):
        st = {"T1": self._stats(0.001, 2.0), "T2": self._stats(0.03, 1.0), "T3": self._stats(0.5, 1.0),
              "T4": self._stats(0.02, -1.0), "T5": self._stats(0.9, 1.0)}
        v = M.verdicts("discovery", st)
        # BH m = 5, q = 0.10: sorted p 0.001, 0.02, 0.03, 0.5, 0.9 vs 0.02, 0.04, 0.06, 0.08, 0.10 -> three rejected
        self.assertEqual({i: x["bh_rejected"] for i, x in v.items()},
                         {"T1": True, "T2": True, "T3": False, "T4": True, "T5": False})
        self.assertEqual({i: x["candidate"] for i, x in v.items()},
                         {"T1": True, "T2": True, "T3": False, "T4": False, "T5": False})
        with self.assertRaises(AssertionError):
            M.verdicts("discovery", {"T1": self._stats(0.01, 1.0)})

    def test_confirmation_and_exposed_thresholds(self):
        prior = {"tests": [{"id": i, "verdict": {"bh_rejected": True, "candidate": c}}
                           for i, c in (("T1", True), ("T2", True), ("T3", True), ("T4", False), ("T5", True))]}
        st = {"T1": self._stats(0.04, 1.0, 0.5), "T2": self._stats(0.06, 1.0), "T3": self._stats(0.01, 1.0, -0.1),
              "T4": self._stats(0.001, 5.0), "T5": {"n": 0}}
        v = M.verdicts("confirmation", st, prior)
        self.assertEqual({i: x["confirmed"] for i, x in v.items()},
                         {"T1": True, "T2": False, "T3": False, "T4": False, "T5": False})
        prior2 = {"tests": [{"id": i, "verdict": x} for i, x in v.items()]}
        st2 = {"T1": self._stats(0.09, 0.1, -9.0), "T2": self._stats(0.01, 1.0), "T3": self._stats(0.01, 1.0),
               "T4": self._stats(0.01, 1.0), "T5": self._stats(0.01, 1.0)}
        v2 = M.verdicts("exposed", st2, prior2)
        self.assertEqual({i: x["survives"] for i, x in v2.items()},
                         {"T1": True, "T2": False, "T3": False, "T4": False, "T5": False})   # exposed: no p90 gate

    def test_family_and_members_come_from_the_cfd_allowlist(self):
        mem = M.members()
        cfd = INS.execution("cfd")
        self.assertEqual(mem, {"US": ["US500", "US30", "USTEC"], "NON_US": ["DE40", "FRA40", "AUS200"]})
        self.assertTrue(set(mem["US"] + mem["NON_US"]) <= set(cfd))
        fam = M.family(mem)
        self.assertEqual([f[0] for f in fam], ["T1", "T2", "T3", "T4", "T5"])
        self.assertEqual(len(fam), M.BH_M)
        self.assertEqual(fam[0][4], "decision test")
        real = M.INS.execution
        try:
            M.INS.execution = lambda market=None: [s for s in real(market) if s != "AUS200"]
            with self.assertRaises(SystemExit):
                M.members()
        finally:
            M.INS.execution = real


# ------------------------------------------------------------------------------------------------ §5 reads
class Reads(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = context(last=D(2024, 3, 28), poison_from=None)
        cls.disc = M.compute_read("discovery", cls.ctx)

    def test_discovery_touches_only_its_own_episode_months(self):
        """Every bar from 2021-09-07 on has open = 0: any return computed there would raise. Episode 2021-08's last outcome
        day is its non-US reversal day T+3 = 2021-09-03, which belongs to DISCOVERY (§5 reads are by episode month)."""
        ctx = context(last=D(2021, 9, 30), poison_from=D(2021, 9, 7))
        res = M.compute_read("discovery", ctx)
        t = {x["id"]: x["discovery"] for x in res["tests"]}
        self.assertEqual((t["T1"]["n"], t["T2"]["n"], t["T3"]["n"], t["T4"]["n"], t["T5"]["n"]), (220, 220, 150, 220, 220))
        self.assertEqual((t["T1"]["episodes"], t["T3"]["episodes"]), (44, 30))
        self.assertEqual((t["T1"]["first_day"], t["T1"]["last_day"]), ("2018-01-26", "2021-09-01"))
        self.assertEqual((t["T5"]["first_day"], t["T5"]["last_day"]), ("2018-01-29", "2021-09-02"))
        rev = res["diagnostics"]["first_business_day_reversal_descriptive"]
        self.assertEqual((rev["T1"]["n"], rev["T5"]["n"], rev["T5"]["last_day"]), (44, 44, "2021-09-03"))
        with self.assertRaises(ZeroDivisionError):                          # the poison is live
            M.compute_read("confirmation", ctx, prior=res)

    def test_result_shape_and_decision(self):
        res = self.disc
        self.assertEqual([x["id"] for x in res["tests"]], ["T1", "T2", "T3", "T4", "T5"])
        for x in res["tests"]:
            self.assertEqual(set(x["verdict"]), {"bh_rejected", "candidate"})
            for k in ("gamma_bp", "p_one_sided", "net_bp", "net_bp_p90", "intercept_bp"):
                self.assertIn(k, x["discovery"])
        self.assertEqual(res["decision"]["decision_test"], "T1")
        self.assertEqual(set(res["diagnostics"]), {"equity_only_signal", "falsification_non_week4_same_weekday",
                                                   "first_business_day_reversal_descriptive", "return_days_T-3_to_T-1_only",
                                                   "owner_sizing", "corr_with_fvg_book_v3"})
        d = res["diagnostics"]
        self.assertEqual(d["return_days_T-3_to_T-1_only"]["T1"]["n"], 44 * 3)
        # non-US: T-2, T-1 -- plus Thanksgiving 2020-11-26 (a European session inside [T-3 = 11-24, T-1 = 11-27], the
        # 2nd weekday after T-3); its T-2 decision (11-25) then returns on T-1 (11-27)
        self.assertEqual(d["return_days_T-3_to_T-1_only"]["T5"]["n"], 44 * 2 + 1)
        self.assertEqual(d["owner_sizing"]["T2"]["n"] + d["owner_sizing"]["T2"]["skipped_no_sd_history"], 220)
        self.assertEqual(d["equity_only_signal"]["T1"]["n"], 220)
        self.assertGreater(d["falsification_non_week4_same_weekday"]["T1"]["n"], 220)
        meta = res["meta"]
        self.assertEqual(meta["return_day_span"]["main"], ["2018-01-26", "2021-09-02"])
        self.assertEqual(meta["return_day_span"]["reversal"], ["2018-02-02", "2021-09-03"])
        self.assertEqual(meta["return_days_after_dev_cutoff"]["days"], {})
        self.assertEqual(meta["cost_bucket_frame"]["DE40"]["export_server_utc_offset_hours"], 3)
        self.assertEqual(meta["lag"], {"US": ["nyse_business_days", 1], "NON_US": ["weekday_server_days", 2]})
        # cost hours: D1-filled to 2018-12 -> server-clock constant, then the 1H bars; both at buckets (22, 20)
        # 12 episodes of 2018 x 5 US return days, minus 2018-12's T+1 = 2019-01-02 (intraday era): 59 constant, 161 1h
        self.assertEqual(res["cost_hours_source"]["US500"], {"server_clock_constant": 59, "1h": 161})
        self.assertEqual(res["cost_fallback_rows"]["main"], {s: 0 for s in M.members()["US"] + M.members()["NON_US"]})
        self.assertTrue(all(x["discovery"]["cost_fallback_rows"] == 0 for x in res["tests"]))
        self.assertEqual(set(res["cost_hours_shifted_minus_1h_rows"].values()), {0})
        self.assertTrue(any(k.startswith("falsification|") and k.endswith("|placebo_return_day_in_week4")
                            for k in res["skipped"]))
        json.dumps(res, default=str)

    def test_confirmation_stops_before_the_exposed_bars_and_discloses_the_post_cutoff_days(self):
        """Every bar from 2024-03-06 on has open = 0. CONFIRMATION's last outcome days are episode 2024-02's T+2 (non-US,
        2024-03-04) and its reversal T+3 (2024-03-05) -- after the ledger's 2024-03-01 development cutoff, so disclosed."""
        ctx = context(last=D(2024, 3, 28), poison_from=D(2024, 3, 6))
        conf = M.compute_read("confirmation", ctx, prior=self.disc)
        t = {x["id"]: x["confirmation"] for x in conf["tests"]}
        self.assertEqual((t["T1"]["last_day"], t["T5"]["last_day"]), ("2024-03-01", "2024-03-04"))
        rev = conf["diagnostics"]["first_business_day_reversal_descriptive"]
        self.assertEqual((rev["T1"]["last_day"], rev["T5"]["last_day"]), ("2024-03-04", "2024-03-05"))
        late = conf["meta"]["return_days_after_dev_cutoff"]
        self.assertEqual((late["cutoff"], late["ledger_period"]), ("2024-03-01", "cfd-development-pre-2024-03"))
        self.assertEqual(late["days"]["main"]["T1"], ["2024-03-01"])
        self.assertEqual(late["days"]["main"]["T5"], ["2024-03-01", "2024-03-04"])
        self.assertEqual(late["days"]["reversal"]["T5"], ["2024-03-05"])
        self.assertNotIn("falsification", late["days"])
        self.assertEqual(conf["meta"]["return_day_span"]["main"][1], "2024-03-04")
        with self.assertRaises(ZeroDivisionError):                          # the poison is live
            M.compute_read("exposed", ctx, prior=conf)

    def test_confirmation_and_exposed_chain_on_the_previous_json(self):
        conf = M.compute_read("confirmation", self.ctx, prior=self.disc)
        for x in conf["tests"]:
            self.assertIn("confirmed", x["verdict"])
            self.assertEqual(x["confirmation"]["episodes"], 30)
            self.assertGreaterEqual(x["confirmation"]["first_day"], "2021-09-24")
        prev = {x["id"]: x["verdict"]["candidate"] for x in self.disc["tests"]}
        self.assertEqual({x["id"]: x["verdict"]["candidate"] for x in conf["tests"]}, prev)
        with self.assertRaises(SystemExit):
            M.compute_read("exposed", self.ctx, prior=self.disc)              # exposed needs the CONFIRMATION json
        with self.assertRaises(SystemExit):
            M.compute_read("confirmation", self.ctx, prior=None)

    def test_run_refuses_out_of_order_before_loading_any_data(self):
        real = M.load_context
        M.load_context = lambda: (_ for _ in ()).throw(AssertionError("data loaded"))
        try:
            with tempfile.TemporaryDirectory() as tmp:
                out = os.path.join(tmp, "x.json")
                with self.assertRaises(SystemExit):
                    M.run("confirmation", out, None)
                bad = os.path.join(tmp, "prior.json")
                for meta in ({"read": "discovery", "script": "scripts/research/edge_f6.py", "preregistration": M.PREREG},
                             {"read": "confirmation", "script": M.SCRIPT, "preregistration": M.PREREG}):
                    with open(bad, "w") as fh:
                        json.dump({"meta": meta, "tests": []}, fh)
                    with self.assertRaises(SystemExit):
                        M.run("confirmation", out, bad)
                self.assertFalse(os.path.exists(out))
                with open(out, "w") as fh:                                       # a read that already ran
                    fh.write("{}")
                with self.assertRaises(SystemExit) as cm:
                    M.run("discovery", out, None)
                self.assertIn("run ONCE", str(cm.exception))
                with open(out) as fh:
                    self.assertEqual(fh.read(), "{}")                            # untouched
        finally:
            M.load_context = real

    def test_snapshot_matches_prior(self):
        cur = {"US500": {"1D": {"sha256": "a"}, "1H": {"sha256": "b"}, "cost_spec": {"sha256": "c"}},
               "DGS10": {"file_sha256": "y"}, "cost_profile": {}}
        same = json.loads(json.dumps(cur))
        self.assertEqual(M.snapshot_matches_prior(same, cur),
                         {"US500/1D": True, "US500/1H": True, "US500/cost_spec": True, "DGS10": True})
        moved = json.loads(json.dumps(cur))
        moved["US500"]["1D"]["sha256"], moved["DGS10"]["file_sha256"] = "z", "w"
        del moved["US500"]["cost_spec"]
        self.assertEqual(M.snapshot_matches_prior(moved, cur),
                         {"US500/1D": False, "US500/1H": True, "US500/cost_spec": None, "DGS10": False})


# ------------------------------------------------------------------------------------------------ point-in-time
class PointInTime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.days = [d for d in CAL.days if D(2018, 10, 1) <= d <= D(2019, 12, 31)]
        cls.cs = path(cls.days, 5)
        cls.rows = yield_rows(cls.days, nulls={D(2019, 3, 22), D(2019, 5, 31), D(2019, 9, 26)})
        cls.eps = M.month_range("2018-11", "2019-11")

    def _decisions(self, cs, rows):
        us, y = M.Daily("US500", cs, ZONE), M.Yields(rows, CAL)
        out = {}
        for ep in self.eps:
            for sg in M.signals(CAL, us, y, ep):
                if sg["s"] is not None:
                    out[(ep, sg["t"])] = (sg["s"], sg["s_eq"], round(sg["S"], 15), sg["y_lag_date"], sg["y_base_date"])
        return out

    def test_truncating_the_future_never_changes_a_past_decision(self):
        """The generic leakage probe applied to the signal: every decision dated on or before the cut is found, identical, on
        bars and yields truncated at the cut."""
        full = self._decisions(self.cs, self.rows)
        self.assertGreater(len(full), 60)
        self.assertEqual({v[0] for v in full.values()}, {-1, 1})              # both positions occur
        for cut in (D(2019, 1, 31), D(2019, 3, 26), D(2019, 6, 27), D(2019, 9, 30)):
            cs = [c for c, d in zip(self.cs, self.days) if d <= cut]
            rows = [r for r in self.rows if r["date"] <= str(cut)]
            got = self._decisions(cs, rows)
            want = {k: v for k, v in full.items() if k[1] <= cut}
            self.assertEqual({k: v for k, v in got.items() if k[1] <= cut}, want)

    def test_each_decision_needs_only_bars_to_t_and_yields_before_t(self):
        full = self._decisions(self.cs, self.rows)
        for (ep, t), v in list(full.items())[::4]:
            cs = [c for c, d in zip(self.cs, self.days) if d <= t]
            rows = [r for r in self.rows if r["date"] < str(t)]               # not even y(t), published 16:15 ET on t
            sg = M.signal_at(CAL, M.Daily("US500", cs, ZONE), M.Yields(rows, CAL), ep, t)
            self.assertEqual((sg["s"], sg["s_eq"], round(sg["S"], 15), sg["y_lag_date"], sg["y_base_date"]), v)

    def test_the_entry_instant_is_after_the_decision_close(self):
        """The priced entry (the first 1H bar of the return day, or the server-clock 01:00 on a D1-filled day) is after the
        decision close (end of server day t), and the exit inside the return day -- for main, reversal and placebo rows."""
        ctx = context(last=D(2019, 12, 31))                                    # D1-filled 1H to 2018-12, intraday after
        seen = set()
        for ep in self.eps:
            sigs = M.signals(CAL, ctx["daily"]["US500"], ctx["yields"], ep)
            ts = [sg["t"] for sg in sigs] + [sg["t"] for sg in M.reversal_signals(CAL, sigs)]
            ts += M.placebo_days(CAL, *M._ym(ep))
            for t in ts:
                for g, sym in (("US", "US500"), ("NON_US", "DE40")):
                    d = M.return_day(CAL, t, g)
                    h = ctx["hours"][sym].get(d)
                    seen.add(h[2])
                    self.assertGreater(h[3], M.server_day_end_utc(t, ZONE), (t, g))
                    self.assertLess(h[4], M.server_day_end_utc(d, ZONE), (t, g))
                    self.assertGreaterEqual(h[3], M.server_day_end_utc(d - DAY, ZONE), (t, g))
        self.assertEqual(seen, {"1h", "server_clock_constant"})

    def test_truncating_the_future_never_changes_an_outcome_row(self):
        """Row-level leakage probe: each outcome row (position, return, cost, cost hours / buckets) is rebuilt, identical,
        from bars cut at its return day d (1D and 1H, every member) and yields cut before its decision day t."""
        ctx = context(last=D(2019, 4, 30))
        raw, ys = ctx["raw"], ctx["yield_rows"]
        sigs = [sg for ep in M.month_range("2018-09", "2019-03")
                for sg in M.signals(CAL, ctx["daily"]["US500"], ctx["yields"], ep)]
        checked = set()
        for g, syms in (("US", ("US500", "USTEC")), ("NON_US", ("DE40", "FRA40"))):
            for sym in syms:
                rows, _ = M.member_rows("discovery", CAL, sigs, ctx["daily"][sym], g, ctx["hours"][sym], ctx["costs"][sym])
                self.assertGreater(len(rows), 10)
                for row in rows[::3]:
                    d, t = row["d"], row["t"]
                    cut = lambda bars: [b for b in bars if M.server_date(b["time"], ZONE) <= d]  # noqa: E731
                    us = M.Daily("US500", cut(raw["US500"][0]), ZONE)
                    dl = M.Daily(sym, cut(raw[sym][0]), ZONE, sd_exclude=ctx["daily"][sym].sd_exclude)
                    hr = M.SessionHours(cut(raw[sym][1]), ZONE, ctx["hours"][sym].local)
                    y = M.Yields([r for r in ys if r["date"] < str(t)], CAL)
                    sg = [s for s in M.signals(CAL, us, y, row["episode"]) if s["t"] == t]
                    got, _ = M.member_rows("discovery", CAL, sg, dl, g, hr, ctx["costs"][sym])
                    self.assertEqual(got, [row], (sym, t))
                    self.assertEqual(dl.trailing_sd(d), ctx["daily"][sym].trailing_sd(d))
                    checked.add(row["cost_hours_source"])
        self.assertEqual(checked, {"1h", "server_clock_constant"})

    def test_owner_sizing_sd_uses_only_earlier_days(self):
        full = M.Daily("US500", self.cs, ZONE)
        for k in (25, 60, 200):
            d = self.days[k]
            part = M.Daily("US500", self.cs[:k], ZONE)                          # every bar from d on removed
            self.assertEqual(full.trailing_sd(d), part.trailing_sd(d))
        self.assertIsNone(full.trailing_sd(self.days[19]))
        self.assertIsNotNone(full.trailing_sd(self.days[20]))


# ------------------------------------------------------------------------------------------------ §6 diagnostics
class Diagnostics(unittest.TestCase):
    def test_falsification_days_have_a_week4_weekday_and_lie_outside_week4(self):
        self.assertEqual(M.placebo_days(CAL, 2019, 3), [d for d in CAL.month_days(2019, 3) if d < D(2019, 3, 25)])
        # Nov 2019: week 4 = Fri 22, Mon 25, Tue 26, Wed 27, Fri 29 (Thanksgiving Thu 28) -> no Thursday is a placebo day
        got = M.placebo_days(CAL, 2019, 11)
        self.assertEqual([d.day for d in got], [1, 4, 5, 6, 8, 11, 12, 13, 15, 18, 19, 20])
        self.assertTrue(all(d.weekday() != 3 for d in got))

    def test_reversal_is_decided_at_T_plus_1_against_the_T_minus_4_position(self):
        ctx = context(last=D(2018, 5, 31))
        sigs = M.signals(CAL, ctx["daily"]["US500"], ctx["yields"], "2018-03")
        rv = M.reversal_signals(CAL, sigs)
        self.assertEqual(len(rv), 1)
        self.assertEqual((rv[0]["t"], rv[0]["s"]), (D(2018, 4, 2), -sigs[0]["s"]))
        self.assertEqual((M.return_day(CAL, rv[0]["t"], "US"), M.return_day(CAL, rv[0]["t"], "NON_US")),
                         (D(2018, 4, 3), D(2018, 4, 4)))

    def test_owner_sizing_stop_hit_and_time_exit(self):
        days = [d for d in CAL.days if D(2019, 1, 2) <= d <= D(2019, 2, 28)]
        cs = [candle(d, 100.0, 100.5, 99.5, 100.0 + (0.5 if k % 2 else -0.5)) for k, d in enumerate(days)]
        d_hit, d_time = days[25], days[26]
        cs[25] = candle(d_hit, 100.0, 100.2, 90.0, 95.0)                      # long: low far beyond the stop
        cs[26] = candle(d_time, 100.0, 100.2, 99.9, 100.1)                    # long: no stop, +0.1 %
        dl = {"US500": M.Daily("US500", cs, ZONE)}
        stop = 2.0 * dl["US500"].trailing_sd(d_hit)
        rows = [{"symbol": "US500", "d": d_hit, "s": 1, "r": -0.05, "cost": 1e-4},
                {"symbol": "US500", "d": d_time, "s": 1, "r": 0.001, "cost": 1e-4}]
        o = M.owner_sizing(rows, dl)
        stop2 = 2.0 * dl["US500"].trailing_sd(d_time)
        self.assertEqual((o["n"], o["stop_hits"]), (2, 1))
        self.assertAlmostEqual(o["mean_R_net"], ((-stop - 1e-4) / stop + (0.001 - 1e-4) / stop2) / 2)
        self.assertAlmostEqual(o["net_pnl_pct_total"], 1.0 * ((-stop - 1e-4) / stop + (0.001 - 1e-4) / stop2))

    def test_a_placebo_row_never_returns_inside_the_month_end_window(self):
        """Review 2026-10-03: T-5 / T-6 placebo days held over T-4 / T-3 leaked month-end flow into the falsification."""
        ctx = context(last=D(2019, 4, 30))
        plc = [M.signal_at(CAL, ctx["daily"]["US500"], ctx["yields"], "2019-03", t) for t in M.placebo_days(CAL, 2019, 3)]
        w4 = CAL.week4(2019, 3)                                                    # Mon 03-25 .. Fri 03-29
        us, sk_us = M.events(CAL, plc, ctx["daily"]["USTEC"], "US", keep=M.placebo_keep)
        nus, sk_nus = M.events(CAL, plc, ctx["daily"]["DE40"], "NON_US", keep=M.placebo_keep)
        self.assertTrue(all(e["d"] < w4[0] for e in us + nus))
        self.assertEqual(sk_us["placebo_return_day_in_week4"], 1)                 # Fri 03-22 -> Mon 03-25 (T-4)
        self.assertEqual(sk_nus["placebo_return_day_in_week4"], 2)                # Thu 03-21, Fri 03-22 -> 03-25, 03-26
        self.assertEqual((len(us), len(nus)), (len(plc) - 1, len(plc) - 2))

    def test_owner_sizing_short_side_stop(self):
        days = [d for d in CAL.days if D(2019, 1, 2) <= d <= D(2019, 2, 28)]
        cs = [candle(d, 100.0, 100.5, 99.5, 100.0 + (0.5 if k % 2 else -0.5)) for k, d in enumerate(days)]
        d_hit = days[25]
        cs[25] = candle(d_hit, 100.0, 110.0, 99.8, 104.0)                     # short: high far beyond the stop
        dl = {"US500": M.Daily("US500", cs, ZONE)}
        stop = 2.0 * dl["US500"].trailing_sd(d_hit)
        self.assertGreaterEqual(0.10, stop)
        o = M.owner_sizing([{"symbol": "US500", "d": d_hit, "s": -1, "r": 0.04, "cost": 1e-4}], dl)
        self.assertEqual((o["n"], o["stop_hits"]), (1, 1))
        self.assertAlmostEqual(o["mean_R_net"], (-stop - 1e-4) / stop)

    def test_the_trailing_sd_skips_weekend_and_us_holiday_stub_bars(self):
        days = [d for d in CAL.days if D(2019, 1, 2) <= d <= D(2019, 3, 29)]
        base = [candle(d, 100.0, 101, 99, 100.0 + (0.4 if k % 3 else -0.6)) for k, d in enumerate(days)]
        stubs = [candle(D(2019, 1, 21), 100.0, 130, 70, 120.0),                  # MLK (NYSE closed): a stub session
                 candle(D(2019, 2, 10), 100.0, 130, 70, 80.0)]                    # a Sunday-dated bar
        a = M.Daily("US500", base, ZONE, sd_exclude=CAL.holidays)
        b = M.Daily("US500", sorted(base + stubs, key=lambda c: c["time"]), ZONE, sd_exclude=CAL.holidays)
        self.assertEqual(b.qa["weekend_dated_bars"], 1)
        self.assertEqual(b.sd_days, a.sd_days)
        for d in (D(2019, 2, 12), D(2019, 3, 1), D(2019, 3, 29)):
            self.assertEqual(b.trailing_sd(d), a.trailing_sd(d))
        c = M.Daily("US500", sorted(base + stubs, key=lambda c: c["time"]), ZONE)   # no holiday list: MLK stub counts
        self.assertNotEqual(c.trailing_sd(D(2019, 2, 12)), a.trailing_sd(D(2019, 2, 12)))

    def test_weekend_dated_bars_are_flagged_not_dropped(self):
        days = [d for d in CAL.days if D(2018, 1, 2) <= d <= D(2018, 6, 29)]
        cs = sorted(path(days, 2) + [candle(D(2018, 1, 7), 1, 1, 1, 1), candle(D(2018, 5, 27), 1, 1, 1, 1)],
                    key=lambda c: c["time"])
        dl = M.Daily("DE40", cs, ZONE)
        main = {"DE40": [{"episode": "2018-02"}, {"episode": "2018-06"}]}
        f = M.weekend_bar_flags({"DE40": dl, "US500": M.Daily("US500", path(days, 1), ZONE)},
                                M.month_range("2018-01", "2018-06"), main)
        self.assertEqual(set(f), {"DE40"})
        self.assertEqual((f["DE40"]["weekend_dated_1d_bars"], f["DE40"]["first"], f["DE40"]["last"]),
                         (2, "2018-01-07", "2018-05-27"))
        self.assertEqual(f["DE40"]["episodes_flagged_in_read"], M.month_range("2018-01", "2018-05"))
        self.assertEqual(f["DE40"]["main_rows_in_flagged_episodes"], 1)
        self.assertIn(D(2018, 1, 7), dl.bars)                                      # flagged, not dropped

    def test_crisis_months_ignore_a_partial_edge_month(self):
        """Review 2026-10-03: a 2-day edge month of the span must not take a crisis slot by noise."""
        days = [d for d in CAL.days if D(2019, 1, 2) <= d <= D(2019, 7, 31)]
        edge = {D(2019, 2, 27), D(2019, 2, 28), D(2019, 7, 1), D(2019, 7, 2)}
        cs = [candle(d, 100.0, 101, 99, (150.0 if k % 2 else 60.0) if d in edge else
                     100.0 * (1 + (0.03 if d.month == 3 and k % 2 else 0.001 * (k % 3)))) for k, d in enumerate(days)]
        dl = M.Daily("US500", cs, ZONE)
        # span 02-27 .. 07-02: Feb and Jul hold 2 huge days each; only Mar..Jun (>= 10 days) are ranked: ceil(0.2 x 4) = 1
        self.assertEqual(M.crisis_months(dl, D(2019, 2, 27), D(2019, 7, 2)), ["2019-03"])
        by_m = {}
        for d in dl.sd_days:
            if D(2019, 2, 27) <= d <= D(2019, 7, 2):
                by_m.setdefault(d.month, []).append(d)
        self.assertEqual((len(by_m[2]), len(by_m[7])), (2, 2))
        self.assertGreater(min(statistics.stdev(dl.oc_return(d) for d in by_m[m]) for m in (2, 7)),
                           statistics.stdev(dl.oc_return(d) for d in by_m[3]))      # they WOULD win without the rule

    def test_crisis_months_use_only_days_inside_the_span(self):
        days = [d for d in CAL.days if D(2019, 1, 2) <= d <= D(2019, 6, 28)]
        cs = [candle(d, 100.0, 101, 99, 100.0 * (1 + (0.03 if d.month == 3 and k % 2 else 0.001 * (k % 3)))) for k, d in
              enumerate(days)]
        cs = [dict(c, open=0.0) if d > D(2019, 5, 15) else c for c, d in zip(cs, days)]   # poison after the span
        dl = M.Daily("US500", cs, ZONE)
        self.assertEqual(M.crisis_months(dl, D(2019, 1, 2), D(2019, 5, 15)), ["2019-03"])


    def test_book_correlation_stays_inside_the_span_and_its_crisis_months(self):
        days = [d for d in CAL.days if D(2019, 1, 2) <= d <= D(2019, 6, 28)]
        cs = [candle(d, 100.0, 101, 99, 100.0 * (1 + (0.03 if d.month == 3 and k % 2 else 0.001 * (k % 3)))) for k, d in
              enumerate(days)]
        us = M.Daily("US500", cs, ZONE)
        rows = [{"d": d, "s": 1 if k % 2 else -1, "r": 0.001 * (k % 5 - 2), "cost": 1e-4}
                for k, d in enumerate(days) if D(2019, 1, 10) <= d <= D(2019, 5, 15)]
        seen = []

        def corr(a, b):
            seen.append((dict(a), dict(b)))
            return 0.5
        book = {str(d): 1.0 for d in days}
        out = M.book_correlation(rows, (book, corr), us)
        self.assertEqual((out["span"], out["crisis_months"]), (["2019-01-10", "2019-05-15"], ["2019-03"]))
        (m_all, b_all), (m_cr, b_cr) = seen
        self.assertEqual((min(b_all), max(b_all)), ("2019-01-10", "2019-05-15"))       # the book is cut to the span
        self.assertTrue(all(d[:7] == "2019-03" for d in list(m_cr) + list(b_cr)))
        self.assertAlmostEqual(m_all["2019-01-10"], rows[0]["s"] * rows[0]["r"] - 1e-4)
        self.assertIsNone(M.book_correlation(rows, None, us))


# ------------------------------------------------------------------------------------------------ dry run
class DryRun(unittest.TestCase):
    def test_dry_run_reads_no_price_and_no_yield_value(self):
        ctx = context(last=D(2026, 9, 25), price="none")
        ctx["yields"].values = [None] * len(ctx["yields"].values)            # any yield arithmetic raises
        res = M.dry_run(ctx)
        json.dumps(res, default=str)
        disc = res["reads"]["discovery"]
        self.assertEqual(disc["episodes"], ["2018-01", "2021-08", 44])
        self.assertEqual((disc["week4_signal_days"], disc["signal_days_with_all_inputs"]), (220, 220))
        self.assertEqual({s: m["events"] for s, m in disc["members"].items()},
                         {"US500": 220, "US30": 150, "USTEC": 220, "DE40": 220, "FRA40": 220, "AUS200": 150})
        self.assertEqual(res["reads"]["exposed"]["members"]["US500"]["events"], 150)
        self.assertEqual(disc["yield_base_dated_before_T_prev"], 0)
        self.assertEqual(disc["members"]["US500"]["return_days_by_cost_buckets"], {"22-20": 220})
        self.assertEqual(disc["members"]["US500"]["return_days_with_cost_fallback"], 0)
        self.assertEqual(disc["members"]["US500"]["reversal_events"], 44)
        self.assertGreater(disc["members"]["DE40"]["main_and_reversal_events_whose_day_differs_from_the_2nd_nyse_day"], 0)
        self.assertGreater(disc["members"]["DE40"]["falsification_dropped_return_day_in_week4"], 0)
        # week-4 NYSE days with the Board closed (no H.15 that day) in 2018-01 .. 2021-08: Dec 24 of 2018 and 2020
        self.assertEqual(disc["signal_days_where_board_rule_takes_an_older_yield"], ["2018-12-24", "2020-12-24"])
        self.assertIn("2019-10-14", res["nyse_days_board_closed_in_window"])
        self.assertEqual(res["members"]["US500"]["intraday_modes_match_constant"], True)
        self.assertEqual(res["members"]["US500"]["constant_hour_buckets"], [22, 20])
        forbidden = {"r", "gamma_bp", "net_bp", "gross_bp", "excess", "win_rate_net", "mean_R_net", "S", "s", "R_E", "R_B"}

        def keys(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    yield k
                    yield from keys(v)
            elif isinstance(o, list):
                for v in o:
                    yield from keys(v)
        self.assertFalse(forbidden & set(keys(res)))
        with self.assertRaises(TypeError):                                    # the poison is live
            M.compute_read("discovery", ctx)


class BoardCalendarMatchesTheCommittedH15Dates(unittest.TestCase):
    """data/history/fred/h15-release-dates.json (ALFRED, committed 2026-10-04): every weekday H.15 release date from
    2016-01-01 to the list's end is a Board business day of edge_m1.BoardCalendar, and every Board business day in that span
    is a release date -- the verification the implementer ran, made reproducible."""

    def test_calendar_equals_the_release_dates(self):
        import datetime as _dt
        import json as _json
        path = os.path.join(ROOT, "data", "history", "fred", "h15-release-dates.json")
        rel = {_dt.date.fromisoformat(x) for x in _json.load(open(path))["dates"]}
        lo, hi = _dt.date(2016, 1, 1), max(rel)
        cal = M.BoardCalendar()
        want = {d for d in rel if lo <= d <= hi and d.weekday() < 5}
        got = {d for d in cal.days if lo <= d <= hi}
        self.assertEqual(sorted(got - want)[:5], [])
        self.assertEqual(sorted(want - got)[:5], [])


if __name__ == "__main__":
    unittest.main()
