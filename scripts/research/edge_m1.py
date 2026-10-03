#!/usr/bin/env python3
"""Edge family M1: month-end pension-rebalancing pressure on index CFDs (FTMO 1D server-day bars).
Pre-registration: docs/plans/2026-10-03-edge-m1-month-end-preregistration.md (committed BEFORE any read of M1 outcomes).
Each read ONCE, in order, each in its own commit:

    python3 scripts/research/edge_m1.py dry-run --out <json>          # outcome-blind: bar / gap / event COUNTS only
    python3 scripts/research/edge_m1.py run --read discovery    --out docs/audits/2026-10-03-edge-m1-discovery.json
    python3 scripts/research/edge_m1.py run --read confirmation --after <discovery json>   --out ...
    python3 scripts/research/edge_m1.py run --read exposed      --after <confirmation json> --out ...

A read computes outcome rows ONLY for the episode months of its own period (pre-registration §5); a read refuses to overwrite
an existing output (each read runs ONCE). Signal (§3): T(m) = the last NYSE business day of month m; for t in {T-4 .. T}:
R_E = US500 close(t) / close(T(m-1)) - 1, R_B = -8.5 (y(t-1) - y(T(m-1))) / 100 with y = FRED DGS10, y(t-1) = the latest value
the H.15 had POSTED by t (Board business days, see BoardCalendar), S = 0.6 (1 + R_E) / (0.6 (1 + R_E) + 0.4 (1 + R_B)) - 0.6,
position s = -sign(S). US members hold s over the NEXT NYSE business day's server day (open -> close), non-US members over the
2nd weekday server day after t (the source's one-day lag, counted in the non-US markets' own server days).
Test (§4): per member / basket, OLS r = c + gamma s on the week-4 return days, CR1 by episode month, H1 gamma > 0 one-sided;
net gate mean(s r) - one round-trip spread > 0; BH m = 5, q = 0.10. Diagnostics (§6) are outside the family.

Server day = 17:00 -> 17:00 New York (FTMO-Demo clock: scripts/real_costs.py server_zone("mt5_bridge_ftmo"), New York + 7 h
in every week). A 1D bar's `time` is the server-day START (00:00 server = 17:00 New York the previous calendar date) in UTC; its
server date is `time.astimezone(server zone).date()` -- the same mapping as edge_census.Series.sday (tested). Read-only on repo
data; nothing here touches the live path or any account."""
import argparse
import bisect
import collections
import datetime
import hashlib
import importlib.util
import json
import math
import os
import statistics
import zoneinfo

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


EC = _load("edge_census", "scripts/research/edge_census.py")        # also puts scripts/ on sys.path
import history_store as HS  # noqa: E402
import instruments as INS  # noqa: E402
import real_costs as RC  # noqa: E402

PREREG = "docs/plans/2026-10-03-edge-m1-month-end-preregistration.md"
SCRIPT = "scripts/research/edge_m1.py"
HIST_ROOT = EC.HIST_ROOT                                            # data/history/ftmo
FRED_PATH = os.path.join(ROOT, "data", "history", "fred", "DGS10.json")
PROVIDER = EC.PROVIDER                                              # mt5_bridge_ftmo
UTC = datetime.timezone.utc
END = "9999-12-31T00:00:00Z"
DAY = datetime.timedelta(days=1)
SIGNAL_SYMBOL = "US500"
US_NAMES = ("US500", "US30", "USTEC")            # §4 T1..T4: selected BY NAME from instruments.execution("cfd")
NON_US_NAMES = ("DE40", "FRA40", "AUS200")       # §4 T5
#: §3 lag: US = the 1st NYSE business day after t; non-US = the 2nd weekday (Mon-Fri server day) after t.
LAG = {"US": ("nyse_business_days", 1), "NON_US": ("weekday_server_days", 2)}
W_EQ, W_BOND, DURATION = 0.6, 0.4, 8.5
WEEK4_DAYS = 5                                   # T-4 .. T (the source's Dummy5Days)
FDR_Q, BH_M, CONFIRM_P, EXPOSED_P = 0.10, 5, 0.05, 0.10
READS = ("discovery", "confirmation", "exposed")
EPISODES = {"discovery": ("2018-01", "2021-08"), "confirmation": ("2021-09", "2024-02"), "exposed": ("2024-03", "2026-08")}
STOP_K, SD_DAYS, RISK = 2.0, 20, 0.01            # §6 owner sizing
CRISIS_SHARE = 0.20                              # §6 "crisis months": top fifth of the span's months by US500 day-SD
CRISIS_MIN_DAYS = 10                             # a month counts only with >= 10 sd-eligible US500 days inside the span
MIN_INTRADAY_1H_BARS = 4                         # fewer 1H bars on a server day = D1-filled history (cost hours only)
#: Server-clock hours of the 1D open / close legs when a day has no intraday 1H history: 01:00 server (18:00 New York, the
#: first 1H bar after the daily break) and 23:00 server (16:00 New York, the last 1H bar before 17:00 New York). The modal
#: (first, last) server hours of every member's intraday days equal these in every DST regime (QA: SessionHours.mode,
#: load_context refuses otherwise; outcome-blind dry run 2026-10-03).
FALLBACK_SERVER_HOURS = (1, 23)
#: research-ledger docs/architecture/research-ledger.json oos.periods id "cfd-development-pre-2024-03": development data is
#: everything before this date; later return days are disclosed per read (meta.return_days_after_dev_cutoff).
DEV_CUTOFF = (datetime.date(2024, 3, 1), "cfd-development-pre-2024-03")
CAL_YEARS = (2016, 2027)

RESOLVED_AMBIGUITIES = [
    "Return days (§3): US = the 1st NYSE business day after t; non-US = the 2nd WEEKDAY (Mon-Fri server day) after t, i.e. "
    "'the server day after that' counted in the non-US markets' own server days, so the non-US lag is two sessions in every "
    "week (an NYSE-only holiday such as Memorial Day or Thanksgiving is a normal European / Australian session, not a skipped "
    "day). A missing member bar on that day is a missing day, never filled or shifted. The pre-registration's 'T-2 .. T+2 "
    "(non-US)' holds in NYSE-day terms except across an NYSE-only holiday; a CFD bar on an NYSE holiday is never a US return "
    "day. (Fix round 2026-10-03, before any read: NYSE counting held 31/264 discovery non-US decisions 3+ sessions.)",
    "y(t-1) (§3) = DGS10 at the latest NYSE business day d < t that has a value AND whose H.15 posting day is <= t: the H.15 "
    "is 'posted daily Monday through Friday at 4:15pm' and 'not posted on holidays or in the event that the Board is closed' "
    "(federalreserve.gov/releases/h15, release of 2026-10-02, which holds data through 2026-10-01), so the value for d is "
    "posted at 16:15 ET on the next Board business day after d (BoardCalendar) and is usable at a decision at t's close "
    "(17:00 New York) only when that day is <= t. On an NYSE day the Board is closed (Columbus, Veterans, Juneteenth 2021, "
    "a Saturday New Year observed on Dec 31, Board closures) y(t-1) is therefore the value one day older. y(T(m-1)) = DGS10 "
    "at the latest NYSE business day ON OR before T(m-1) with a value (posted weeks before every t; asserted). Values dated "
    "on non-NYSE days are ignored. DGS10.json's `_pit` header ('published ~16:15 ET that day') is wrong and is NOT used.",
    "A member's episode m counts only when the member's first 1D bar is on or before T(m-1) (its history covers the episode); "
    "this is what gives §5's 'US30 / AUS200 from 2019-03' (their first bar is server day 2019-02-08, a partial day).",
    "Baskets (T1, T5): on each return day, the equal-weight mean of the members that have a bar that day (return and cost).",
    "T1 is the decision test; T2-T4 carry their own BH / threshold verdicts for the record but decide nothing; T5 is promoted "
    "only by passing all three reads itself.",
    "Entry / exit hours for the spread (§4 'half at the entry UTC hour, half at the exit UTC hour'): the SERVER-clock hours of "
    "the server day's FIRST and LAST 1H bar (the 1D open is the first quote after the daily break, its close the last quote "
    "before 17:00 New York) when the day has >= 4 1H bars; otherwise (the D1-filled early 1H history: one bar per day, "
    "US500 / USTEC / FRA40 to 2021-01, DE40 to 2021-05; or no 1H bar) the server-clock constants 01:00 / 23:00 "
    "(FALLBACK_SERVER_HOURS), which equal every member's modal intraday hours in every DST regime (QA, refused otherwise) -- "
    "no later-era data enters the cost hours. Cost hours only: the return always comes from the 1D bar. The true UTC hours "
    "are written to each row for audit.",
    "Cost-table hour frame: the spread table (ExportSymbolSpec.mq5) buckets every M15 bar by `TimeToStruct(r[k].time - "
    "offset)` with offset = the server-GMT offset AT EXPORT (`_server_utc_offset_sec_now` = 10800 s, 2026-09-28) -- its "
    "header: 'the hour buckets use the CURRENT server-GMT offset ... (a DST shift moves a bucket by one hour -- disclosed, not "
    "corrected here)'. So table 'UTC hour' h holds SERVER hour (h + 3) mod 24 all year (US500 / DE40 bucket 21 = server "
    "00:00, the daily break, n = 0). A leg at server hour H is priced at bucket (H - offset) mod 24 (TableCosts), i.e. "
    "(22, 20) for 01:00 / 23:00 in winter and summer alike, NOT at its true UTC hour (which would read server 02:00 / 00:00 "
    "in US standard time). A leg whose bucket has no recorded bars is priced at the symbol's overall spread "
    "(real_costs.spread_price 'overall_fallback'): counted per row (cost_fallback), per test and per member, never silent.",
    "CR1 for the OLS slope = Cameron-Miller sandwich with G/(G-1) x (N-1)/(N-K), K = 2, Student-t with G-1 df (edge_census.cr1 "
    "on the influence values supplies the G/(G-1) part).",
    "Falsification (§6): non-week-4 NYSE business days of the same month m with the same weekday as a week-4 day (t - 7k, "
    "k >= 1), with the same S(t) formula and month-to-date base T(m-1), held as in §3 -- and a placebo row of group g is "
    "kept only when its return day is BEFORE T-4 of month m (return_day(t, g) < week4[0]), so no placebo return lands in "
    "the month-end window it is meant to exclude (T-5 / T-6 hold over T-4 / T-3). Dropped rows are counted in `skipped`.",
    "First-business-day reversal (§6, descriptive): the source's Sec. 4 rule 'on the first business day of a new month the "
    "modified Calendar signal is set to sign(Calendar Signal_-4)': position +sign(S(T-4)) decided at T+1, held over the next "
    "server day as in §3 (US: T+2; non-US: the 2nd weekday after T+1).",
    "Return days T-3 .. T-1 only (§6): rows whose return day lies in [T-3, T-1] (dates, so a non-US return day on an "
    "NYSE-only holiday inside that range counts).",
    "Owner sizing (§6): a stop hit when the day's adverse excursion from the open reaches the stop, filled AT the stop (a 1D "
    "bar cannot show a gap through it). The trailing 20-server-day SD uses WEEKDAY bars only, and for US members not NYSE "
    "holidays (stub CFD sessions that would shrink the SD); non-US exchange holidays are not modelled (no calendar).",
    "Data quality: weekend-dated 1D bars (DE40: 20 Sunday-dated bars 2018-01-07 .. 2018-05-27, when its Monday open is not "
    "the first quote after the weekend) are FLAGGED, not excluded: meta.data_quality_flags lists the read's affected episodes "
    "and their row counts; any exclusion is a pre-registration decision for the lead.",
    "Crisis months (§6): the months of the read's return-day span whose US500 SD of server-day open->close returns (sd-eligible "
    "days inside the span only) is in the top fifth (rounded up), counting only months with >= 10 such days (the span's "
    "partial edge months, 1-4 days, cannot be ranked by noise).",
    "1H clock QA (flagged, not corrected): the US500, USTEC and FRA40 1H files hold a whole session one hour early "
    "((00:00, 22:00) server) on 2021-01-20 .. 2021-03-26, while US30 (same session, same broker) holds (01:00, 23:00) on the "
    "same days -- most likely a one-hour label shift in that 1H segment (outcome-blind dry run 2026-10-03). Those days are "
    "priced at their 1H hours as the rule above says (the 00:00 entry leg lands in the empty break bucket and is counted as an "
    "overall fallback); each read counts them per member (cost_hours_shifted_minus_1h_rows). Re-pricing them at the "
    "server-clock constant would be a pre-registered data-quality rule for the lead to decide. The same counter also counts "
    "AUS200's 84 (00:00, 22:00) days of 2025-11 .. 2026-03 (its Australian-summer regime, where such sessions are common: "
    "not this defect; AUS200's table has no empty bucket).",
    "1D bars whose server day had not ended at the file's _exported_at_utc are dropped as incomplete (counted).",
    "Period edges: §5 assigns rows by EPISODE month, so a read's return days run past its last episode month (discovery to "
    "2021-09-03, confirmation to 2024-03-05). The confirmation read's return days on/after 2024-03-01 lie in the ledger's "
    "oos_exposed period cfd-prop-search-2024-03-2025-03, outside 'cfd-development-pre-2024-03': each read writes them to "
    "meta.return_days_after_dev_cutoff and its exact return-day span to meta.return_day_span.",
    "Snapshot: a confirmation / exposed read records whether each member's 1D / 1H / cost-spec digest and DGS10's digest equal "
    "the prior read's (meta.snapshot_matches_prior); a mismatch is recorded and printed, not refused (a re-export that only "
    "appends later bars changes the digest).",
]


def _sign(x):
    return (x > 0) - (x < 0)


def _parse(iso):
    return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))


def server_date(iso, zone):
    """Server date of a bar time (UTC ISO): `time.astimezone(zone).date()`, the edge_census.Series.sday mapping.
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §2."""
    return _parse(iso).astimezone(zone).date()


def server_day_end_utc(d, zone):
    """The instant server day `d` ends: 00:00 server time on d + 1 (= 17:00 New York on d).
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §2."""
    n = d + DAY
    return datetime.datetime(n.year, n.month, n.day, tzinfo=zone).astimezone(UTC)


# ------------------------------------------------------------------------------------------------ NYSE calendar (§2)
#: The two special closures inside the window (ICE / NYSE press releases): national days of mourning.
SPECIAL_CLOSURES = {datetime.date(2018, 12, 5): "national day of mourning, President George H. W. Bush",
                    datetime.date(2025, 1, 9): "national day of mourning, President Jimmy Carter"}
JUNETEENTH_FROM = 2022


def easter(y):
    """Gregorian Easter Sunday (anonymous / Meeus-Jones-Butcher algorithm); Good Friday = Easter - 2 days.
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §2."""
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    ll = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ll) // 451
    month = (h + ll - 7 * m + 114) // 31
    day = (h + ll - 7 * m + 114) % 31 + 1
    return datetime.date(y, month, day)


def _nth_weekday(y, m, wd, n):
    d = datetime.date(y, m, 1)
    return d + datetime.timedelta(days=(wd - d.weekday()) % 7 + 7 * (n - 1))


def _last_weekday(y, m, wd):
    d = datetime.date(y + (m == 12), m % 12 + 1, 1) - DAY
    return d - datetime.timedelta(days=(d.weekday() - wd) % 7)


def _observed(d, saturday_to_friday=True):
    if d.weekday() == 5:
        return d - DAY if saturday_to_friday else None
    if d.weekday() == 6:
        return d + DAY
    return d


def nyse_holidays(y):
    """{date: name} of NYSE full-day closures in year y, rule-based (§2).

    Observance follows NYSE Rule 7.2 (Holidays): "When a holiday observed by the Exchange falls on a Saturday, the Exchange
    will not be open for business on the preceding Friday and when any holiday observed by the Exchange falls on a Sunday, the
    Exchange will not be open for business on the succeeding Monday, unless unusual business conditions exist, such as the
    ending of a monthly or yearly accounting period." (NYSE Guide, Rule 7.2, adopted 2015-12-30, NYSE-2015-67.) The
    accounting-period exception is why a SATURDAY New Year's Day is NOT observed on the preceding Friday (December 31 ends the
    yearly accounting period): nyse.com/markets/hours-calendars, "Because the holiday falls on Saturday, January 1, 2028, no
    New Year's Day holiday is observed"; e.g. 2021-12-31 was a trading day. No other observed holiday can put its Friday at a
    month end (fixed-date holidays: Jan 1, Jun 19, Jul 4, Dec 25). Juneteenth from 2022 (first observed 2022-06-20).
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §2."""
    out = {}

    def add(d, name):
        if d is not None:
            out[d] = name

    add(_observed(datetime.date(y, 1, 1), saturday_to_friday=False), "New Year's Day")
    add(_nth_weekday(y, 1, 0, 3), "Martin Luther King Jr. Day")
    add(_nth_weekday(y, 2, 0, 3), "Washington's Birthday")
    add(easter(y) - 2 * DAY, "Good Friday")
    add(_last_weekday(y, 5, 0), "Memorial Day")
    if y >= JUNETEENTH_FROM:
        add(_observed(datetime.date(y, 6, 19)), "Juneteenth National Independence Day")
    add(_observed(datetime.date(y, 7, 4)), "Independence Day")
    add(_nth_weekday(y, 9, 0, 1), "Labor Day")
    add(_nth_weekday(y, 11, 3, 4), "Thanksgiving Day")
    add(_observed(datetime.date(y, 12, 25)), "Christmas Day")
    for d, name in SPECIAL_CLOSURES.items():
        if d.year == y:
            add(d, name)
    return out


class NyseCalendar:
    """NYSE business days for CAL_YEARS (weekdays minus nyse_holidays). Published in advance, so point-in-time.
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §2-§3."""

    def __init__(self, first_year=CAL_YEARS[0], last_year=CAL_YEARS[1]):
        self.lo, self.hi = datetime.date(first_year, 1, 1), datetime.date(last_year, 12, 31)
        self.holidays = {}
        for y in range(first_year, last_year + 1):
            self.holidays.update(nyse_holidays(y))
        self.days, d = [], self.lo
        while d <= self.hi:
            if d.weekday() < 5 and d not in self.holidays:
                self.days.append(d)
            d += DAY
        self._set = set(self.days)

    def in_range(self, d):
        return self.lo <= d <= self.hi

    def is_open(self, d):
        if not self.in_range(d):
            raise ValueError(f"{d} outside the NYSE calendar {self.lo}..{self.hi}")
        return d in self._set

    def next(self, d, k=1):                                   # the k-th NYSE business day strictly after d
        j = bisect.bisect_right(self.days, d) + k - 1
        if not self.in_range(d) or j >= len(self.days):
            raise ValueError(f"{d} + {k} NYSE days is outside the calendar")
        return self.days[j]

    def prev(self, d):                                        # the latest NYSE business day strictly before d
        j = bisect.bisect_left(self.days, d) - 1
        if not self.in_range(d) or j < 0:
            raise ValueError(f"no NYSE day before {d} in the calendar")
        return self.days[j]

    def month_days(self, y, m):
        a = bisect.bisect_left(self.days, datetime.date(y, m, 1))
        b = bisect.bisect_left(self.days, datetime.date(y + (m == 12), m % 12 + 1, 1))
        return self.days[a:b]

    def last(self, y, m):                                     # T(m): the last NYSE business day of month m
        return self.month_days(y, m)[-1]

    def week4(self, y, m):                                    # T-4 .. T of month m (the source's Dummy5Days)
        return self.month_days(y, m)[-WEEK4_DAYS:]


# ------------------------------------------------------------------------------------------------ Board calendar (H.15, §2-§3)
#: Weekdays that are NOT federal holidays on which no H.15 was posted (the Board was closed), 2016-01-01 .. 2026-10-02, from
#: the ALFRED release-date list of the H.15 (release id 18, https://alfred.stlouisfed.org/release/downloaddates?rid=18,
#: fetched 2026-10-03). Checked against board_holidays(): every other weekday in that span has a release and no federal
#: holiday has one (the one weekend-dated release, Saturday 2019-01-19, is ignored: it changes no NYSE decision day).
BOARD_CLOSURES = {datetime.date(2016, 1, 25): "no H.15 release (ALFRED)", datetime.date(2016, 1, 26): "no H.15 release (ALFRED)",
                  datetime.date(2017, 1, 20): "no H.15 release (ALFRED)", datetime.date(2018, 3, 2): "no H.15 release (ALFRED)",
                  datetime.date(2018, 12, 5): "no H.15 release (ALFRED); national day of mourning, President George H. W. Bush",
                  datetime.date(2018, 12, 24): "no H.15 release (ALFRED)", datetime.date(2019, 1, 14): "no H.15 release (ALFRED)",
                  datetime.date(2019, 2, 20): "no H.15 release (ALFRED)", datetime.date(2020, 12, 24): "no H.15 release (ALFRED)",
                  datetime.date(2021, 1, 20): "no H.15 release (ALFRED)", datetime.date(2024, 12, 24): "no H.15 release (ALFRED)",
                  datetime.date(2025, 1, 9): "no H.15 release (ALFRED); national day of mourning, President Jimmy Carter"}
FED_JUNETEENTH_FROM = 2021


def board_holidays(y):
    """{date: name} of the Federal Reserve Board's holidays in year y: the federal holidays (5 U.S.C. 6103: New Year, MLK,
    Washington's Birthday, Memorial, Juneteenth from 2021, Independence, Labor, Columbus, Veterans, Thanksgiving, Christmas)
    with the Board's observance -- a Saturday holiday is observed on the preceding Friday (a Saturday New Year on Dec 31 of
    the year before), a Sunday holiday on the following Monday -- plus BOARD_CLOSURES. Verified against the ALFRED H.15
    release dates (BOARD_CLOSURES comment). Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §2."""
    out = {}

    def add(d, name):
        out[d] = name
    for yy, name, d in ((y, "New Year's Day", datetime.date(y, 1, 1)), (y + 1, "New Year's Day", datetime.date(y + 1, 1, 1)),
                        (y, "Juneteenth", datetime.date(y, 6, 19) if y >= FED_JUNETEENTH_FROM else None),
                        (y, "Independence Day", datetime.date(y, 7, 4)), (y, "Veterans Day", datetime.date(y, 11, 11)),
                        (y, "Christmas Day", datetime.date(y, 12, 25))):
        if d is None:
            continue
        o = d - DAY if d.weekday() == 5 else d + DAY if d.weekday() == 6 else d
        if o.year == y:
            add(o, name)
    add(_nth_weekday(y, 1, 0, 3), "Martin Luther King Jr. Day")
    add(_nth_weekday(y, 2, 0, 3), "Washington's Birthday")
    add(_last_weekday(y, 5, 0), "Memorial Day")
    add(_nth_weekday(y, 9, 0, 1), "Labor Day")
    add(_nth_weekday(y, 10, 0, 2), "Columbus Day")
    add(_nth_weekday(y, 11, 3, 4), "Thanksgiving Day")
    for d, name in BOARD_CLOSURES.items():
        if d.year == y:
            add(d, name)
    return out


class BoardCalendar:
    """Federal Reserve Board business days for CAL_YEARS (weekdays minus board_holidays): the days the H.15 is posted (16:15
    ET). `posting_day(d)` = the first Board business day STRICTLY after value date d = when DGS10's value for d became public.
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §2-§3."""

    def __init__(self, first_year=CAL_YEARS[0], last_year=CAL_YEARS[1]):
        self.lo, self.hi = datetime.date(first_year, 1, 1), datetime.date(last_year, 12, 31)
        self.holidays = {}
        for y in range(first_year, last_year + 1):
            self.holidays.update(board_holidays(y))
        self.days, d = [], self.lo
        while d <= self.hi:
            if d.weekday() < 5 and d not in self.holidays:
                self.days.append(d)
            d += DAY
        self._set = set(self.days)

    def is_open(self, d):
        if not self.lo <= d <= self.hi:
            raise ValueError(f"{d} outside the Board calendar {self.lo}..{self.hi}")
        return d in self._set

    def posting_day(self, d):
        j = bisect.bisect_right(self.days, d)
        if not self.lo <= d <= self.hi or j >= len(self.days):
            raise ValueError(f"no Board business day after {d} in the calendar")
        return self.days[j]


def _ym(ep):
    y, m = ep.split("-")
    return int(y), int(m)


def _prev_month(y, m):
    return (y - 1, 12) if m == 1 else (y, m - 1)


def month_range(a, b):
    """Episode months a .. b inclusive, as 'YYYY-MM'. Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §5."""
    y, m = _ym(a)
    out = []
    while f"{y:04d}-{m:02d}" <= b:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def episode_read(ep):
    """The read whose episode months contain `ep`, or None. Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §5."""
    for r, (a, b) in EPISODES.items():
        if a <= ep <= b:
            return r
    return None


# ------------------------------------------------------------------------------------------------ data (§2)
class Daily:
    """One symbol's FTMO 1D server-day bars keyed by SERVER DATE. A server day with two bars is ambiguous and dropped (never
    one picked); a bar whose server day had not ended at `exported_at` is incomplete and dropped; a bar time that is not server
    midnight is counted (data QA). A missing bar is a missing day, never filled. `sd_exclude` = server dates that are not
    full sessions for this member (its exchange's holidays, e.g. the NYSE holidays for a US member): they and every
    weekend-dated bar are left out of the trailing SD (sd_days), never out of the returns.
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §2-§3, §6."""

    def __init__(self, sym, candles, zone, exported_at=None, sd_exclude=()):
        self.sym = sym
        self.sd_exclude = frozenset(sd_exclude)
        self.qa = collections.Counter()
        cut = _parse(exported_at) if exported_at else None
        by_day = collections.defaultdict(list)
        for b in candles:
            loc = _parse(b["time"]).astimezone(zone)
            if (loc.hour, loc.minute, loc.second) != (0, 0, 0):
                self.qa["bar_time_not_server_midnight"] += 1
            by_day[loc.date()].append(b)
        self.bars, self.time = {}, {}
        for d, bs in by_day.items():
            if len(bs) != 1:
                self.qa["duplicate_server_day_dropped"] += 1
                continue
            if cut is not None and server_day_end_utc(d, zone) > cut:
                self.qa["incomplete_at_export_dropped"] += 1
                continue
            b = bs[0]
            self.bars[d] = (b["open"], b["high"], b["low"], b["close"])
            self.time[d] = b["time"]
        self.days = sorted(self.bars)
        self.weekend_days = [d for d in self.days if d.weekday() >= 5]
        if self.weekend_days:
            self.qa["weekend_dated_bars"] = len(self.weekend_days)
        self.sd_days = [d for d in self.days if d.weekday() < 5 and d not in self.sd_exclude]

    def close(self, d):
        b = self.bars.get(d)
        return b[3] if b else None

    def oc_return(self, d):
        o, _h, _l, c = self.bars[d]
        return c / o - 1.0

    def trailing_sd(self, d, n=SD_DAYS):
        """SD of the open -> close returns of the n sd-eligible server days (weekday bars, not in sd_exclude) STRICTLY before
        d (known at d's open), or None. Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §6."""
        k = bisect.bisect_left(self.sd_days, d)
        if k < n:
            return None
        return statistics.stdev(self.oc_return(x) for x in self.sd_days[k - n:k])


class SessionHours:
    """The SERVER-clock hours in which a server day's 1D open (first quote after the daily break) and close (last quote
    before 17:00 New York) print, for the cost (§4: half the hourly spread at the entry hour, half at the exit hour). Times
    only -- no price is read.

    `get(d)` -> (entry server hour, exit server hour, source, entry instant UTC, exit instant UTC): source "1h" = the first
    and last 1H bar of the day, when it has >= MIN_INTRADAY_1H_BARS of them; otherwise FALLBACK_SERVER_HOURS (01:00 / 23:00
    server) with source "server_clock_constant" (a D1-filled day: the FTMO 1H history holds ONE bar per server day early on,
    US500 / USTEC / FRA40 until 2021-01, DE40 until 2021-05) or "server_clock_constant_no_1h" (no 1H bar). The constants are
    the server clock's own session (New York + 7 h: 18:00 / 16:00 New York), so no later-era data sets an earlier day's cost
    hours. `mode` = the modal (first, last) server hours of the intraday days per (server, exchange-local) UTC-offset regime,
    kept as QA only (`modes_match_constant`). The entry / exit instants are the bar OPEN times (the 1D open quote lies in the
    entry hour). Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §4."""

    def __init__(self, candles_1h, zone, local_zone):
        self.zone, self.local = zone, local_zone
        per = collections.defaultdict(list)
        for b in candles_1h:
            t = _parse(b["time"])
            per[t.astimezone(zone).date()].append(t)
        self.actual = {d: (min(ts), max(ts)) for d, ts in per.items() if len(ts) >= MIN_INTRADAY_1H_BARS}
        self.thin_days = {d for d, ts in per.items() if len(ts) < MIN_INTRADAY_1H_BARS}
        modes = collections.defaultdict(collections.Counter)
        self.off_constant_days = 0
        shifted = tuple((x - 1) % 24 for x in FALLBACK_SERVER_HOURS)
        self.shifted_minus_1h_days = []                       # QA: a whole session one hour early, (00:00, 22:00) server
        for d, (a, b) in sorted(self.actual.items()):
            h = (a.astimezone(zone).hour, b.astimezone(zone).hour)
            modes[self.regime(d)][h] += 1
            self.off_constant_days += h != FALLBACK_SERVER_HOURS
            if h == shifted:
                self.shifted_minus_1h_days.append(d)
        self.mode = {k: sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] for k, c in modes.items()}

    def regime(self, d):
        """(server, exchange-local) UTC offsets in hours at 12:00 UTC of server date d.
        Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §4."""
        noon = datetime.datetime(d.year, d.month, d.day, 12, tzinfo=UTC)
        return (int(noon.astimezone(self.zone).utcoffset().total_seconds() // 3600),
                int(noon.astimezone(self.local).utcoffset().total_seconds() // 3600))

    def modes_match_constant(self):
        return all(m == FALLBACK_SERVER_HOURS for m in self.mode.values())

    def at(self, d, server_hour):
        """The UTC instant of `server_hour`:00 server time on server date d.
        Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §4."""
        return datetime.datetime(d.year, d.month, d.day, server_hour, tzinfo=self.zone).astimezone(UTC)

    def get(self, d):
        if d in self.actual:
            a, b = self.actual[d]
            return (a.astimezone(self.zone).hour, b.astimezone(self.zone).hour, "1h", a.astimezone(UTC), b.astimezone(UTC))
        h_in, h_out = FALLBACK_SERVER_HOURS
        src = "server_clock_constant" if d in self.thin_days else "server_clock_constant_no_1h"
        return (h_in, h_out, src, self.at(d, h_in), self.at(d, h_out))


class TableCosts:
    """One member's round-trip relative spread (edge_census.Costs, profile EC.COST_PROFILE) priced in the spread TABLE's own
    hour frame. ExportSymbolSpec.mq5 buckets every recorded M15 bar by `TimeToStruct(r[k].time - offset)`, offset = the
    server-GMT offset AT EXPORT (`_server_utc_offset_sec_now`), so bucket h holds server hour (h + offset) mod 24 in every DST
    regime; a leg at server hour H is priced at bucket (H - offset) mod 24. `notes[(stat, bucket)]` is
    real_costs.spread_price's note ("hour" | "overall_fallback"); `fallback_legs` names the legs priced at the symbol's
    overall spread because their bucket has no recorded bar.
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §2 (spreads), §4 (net gate)."""
    STATS = ("median", "p90")

    def __init__(self, costs, offset_hours, notes=None):
        self.costs, self.offset = costs, offset_hours
        self.notes = notes if notes is not None else {(st, h): "hour" for st in self.STATS for h in range(24)}

    @classmethod
    def load(cls, sym, costs=None):
        """The real table of `sym`; refuses an offset that is not a whole number of hours (never guessed).
        Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §2."""
        sp = RC.spec(EC.COST_PROFILE, sym)
        off = sp.get("_server_utc_offset_sec_now")
        if not isinstance(off, int) or isinstance(off, bool) or off % 3600:
            raise SystemExit(f"{sym}: cost spec _server_utc_offset_sec_now {off!r} is not a whole number of hours; refusing")
        notes = {(st, h): RC.spread_price(EC.COST_PROFILE, sym, h, st)[1] for st in cls.STATS for h in range(24)}
        return cls(EC.Costs(sym) if costs is None else costs, off // 3600, notes)

    def bucket(self, server_hour):
        return (server_hour - self.offset) % 24

    def round_trip(self, srv_in, srv_out, stat="median"):
        return self.costs.round_trip(self.bucket(srv_in), self.bucket(srv_out), stat)

    def fallback_legs(self, srv_in, srv_out):
        return [f"{st}:{leg}" for st in self.STATS for leg, h in (("in", srv_in), ("out", srv_out))
                if self.notes[(st, self.bucket(h))] != "hour"]

    def fallback_buckets(self):
        return sorted({h for (_st, h), note in self.notes.items() if note != "hour"})


class Yields:
    """FRED DGS10 (percent) on NYSE business days that have a value; nulls stay missing, never filled; values dated on a
    non-NYSE day are ignored. Revisions are not tracked (the vintage is the file's fetch time). `posted[k]` = the H.15
    posting day of value k (BoardCalendar.posting_day): `available_at(t)` returns only values posted by t.
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §2-§3."""

    def __init__(self, rows, cal, board=None):
        self.board = board if board is not None else BoardCalendar()
        self.qa = collections.Counter(rows=len(rows))
        pts = []
        for r in rows:
            d = datetime.date.fromisoformat(r["date"])
            if r.get("value") is None:
                self.qa["null"] += 1
                continue
            if not cal.in_range(d):
                continue
            if not cal.is_open(d):
                self.qa["value_on_non_nyse_day_ignored"] += 1
                continue
            pts.append((d, float(r["value"])))
        pts.sort()
        self.dates = [d for d, _ in pts]
        self.values = [v for _, v in pts]
        self.posted = [self.board.posting_day(d) for d in self.dates]          # non-decreasing in d

    def asof(self, d):                     # (date, value) at the latest NYSE business day <= d with a value, or None
        k = bisect.bisect_right(self.dates, d)
        return (self.dates[k - 1], self.values[k - 1]) if k else None

    def available_at(self, t):
        """(date, value) of the latest value whose H.15 posting day (16:15 ET) is on or before NYSE day t -- usable at t's
        close -- or None. Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §2-§3."""
        k = bisect.bisect_right(self.posted, t)
        return (self.dates[k - 1], self.values[k - 1]) if k else None


def members():
    """{"US": [...], "NON_US": [...]}: the six names §4 selects, taken FROM the CFD execution allowlist
    (scripts/instruments.py execution("cfd")); refuses when one is not on it.
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §4."""
    cfd = INS.execution("cfd")
    missing = [n for n in US_NAMES + NON_US_NAMES if n not in cfd]
    if missing:
        raise SystemExit(f"M1 members {missing} are not on instruments.execution('cfd') {cfd}; refusing to substitute")
    return {"US": [s for s in cfd if s in US_NAMES], "NON_US": [s for s in cfd if s in NON_US_NAMES]}


def family(mem):
    """The five tests (§4), in BH order: (id, name, group, members, role).
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §4."""
    us, nus = mem["US"], mem["NON_US"]
    role_m = "member test (in the BH family; decides nothing)"
    return [("T1", "US basket", "US", tuple(us), "decision test"),
            ("T2", "US500", "US", ("US500",), role_m), ("T3", "US30", "US", ("US30",), role_m),
            ("T4", "USTEC", "US", ("USTEC",), role_m),
            ("T5", "non-US basket", "NON_US", tuple(nus), "promoted only by passing all three reads itself")]


# ------------------------------------------------------------------------------------------------ signal (§3)
def calendar_signal(r_e, r_b):
    """S = 0.6 (1 + R_E) / (0.6 (1 + R_E) + 0.4 (1 + R_B)) - 0.6 (the source's 'w - 60 %').
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §3."""
    a = W_EQ * (1.0 + r_e)
    return a / (a + W_BOND * (1.0 + r_b)) - W_EQ


def signal_at(cal, us500, yields, episode, t, values=True):
    """The decision at the close of NYSE day t for episode month m: inputs US500 close(t), close(T(m-1)), y(t-1) and
    y(T(m-1)) -- all available at t's close (y(t-1) = the latest DGS10 value the H.15 had posted by t: Yields.available_at).
    values=False reports only WHICH inputs exist (the outcome-blind dry run never reads a price or yield value).
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §3."""
    y, m = _ym(episode)
    T, tp = cal.last(y, m), cal.last(*_prev_month(y, m))
    yl, yb = yields.available_at(t), yields.asof(tp)
    base_posted = yb is not None and yields.board.posting_day(yb[0]) <= t
    miss = [k for k, ok in (("no_us500_bar_t", t in us500.bars), ("no_us500_bar_base", tp in us500.bars),
                            ("no_yield_lag", yl is not None), ("no_yield_base", yb is not None),
                            ("yield_base_not_posted", yb is None or base_posted)) if not ok]
    sg = {"episode": episode, "t": t, "T": T, "T_prev": tp, "y_lag_date": yl[0] if yl else None,
          "y_base_date": yb[0] if yb else None, "missing": miss, "s": None, "s_eq": None}
    if yl is not None:
        assert yl[0] < t and tp < t, "point-in-time: a decision at t reads nothing dated t or later except close(t)"
        assert yields.board.posting_day(yl[0]) <= t, "point-in-time: y(t-1) must have been posted by t"
    if miss or not values:
        return sg
    r_e = us500.close(t) / us500.close(tp) - 1.0
    r_b = -DURATION * (yl[1] - yb[1]) / 100.0
    s_full, s_eq = calendar_signal(r_e, r_b), calendar_signal(r_e, 0.0)
    sg.update(R_E=r_e, R_B=r_b, S=s_full, s=-_sign(s_full), S_eq=s_eq, s_eq=-_sign(s_eq))
    return sg


def signals(cal, us500, yields, episode, values=True):
    """signal_at for each week-4 day T-4 .. T of the episode month.
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §3."""
    return [signal_at(cal, us500, yields, episode, t, values) for t in cal.week4(*_ym(episode))]


def placebo_days(cal, y, m):
    """§6 falsification days: NON-week-4 NYSE days of month m with the same weekday as a week-4 day (t - 7k, k >= 1).
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §6."""
    w4 = cal.week4(y, m)
    days = set(cal.month_days(y, m))
    out = set()
    for t in w4:
        x = t - 7 * DAY
        while (x.year, x.month) == (y, m):
            if x in days and x not in w4:
                out.add(x)
            x -= 7 * DAY
    return sorted(out)


def reversal_signals(cal, sigs):
    """§6 first-business-day reversal (descriptive), the source's Sec. 4 rule: decided at T+1 (first NYSE day of month m+1),
    position +sign(S(T-4)) = -s(T-4).
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §6."""
    out = []
    for sg in sigs:
        if sg["t"] == cal.week4(*_ym(sg["episode"]))[0]:
            s = None if sg["s"] is None else -sg["s"]
            out.append(dict(sg, t=cal.next(sg["T"]), s=s, s_eq=None))
    return out


# ------------------------------------------------------------------------------------------------ events and outcomes (§3-§4)
def return_day(cal, t, group):
    """The server day the position decided at t is held over: the NEXT NYSE business day (US); the 2nd weekday server day
    after t (non-US: 'the server day after that', counted in the non-US markets' own Mon-Fri server days).
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §3."""
    kind, k = LAG[group]
    if kind == "nyse_business_days":
        return cal.next(t, k)
    d = t
    while k:
        d += DAY
        k -= d.weekday() < 5
    return d


def placebo_keep(cal, sg, group):
    """§6 falsification: a placebo row of `group` is kept only when its return day is BEFORE T-4 of the episode month (never
    inside the month-end window it is meant to exclude).
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §6."""
    return return_day(cal, sg["t"], group) < cal.week4(*_ym(sg["episode"]))[0]


def events(cal, sigs, daily, group, key="s", blind=False, keep=None):
    """([event], skip counts) for one member: a decided signal with a nonzero position, the member's history covering the
    episode's base day T(m-1), and the member's 1D bar on the return day (missing bar = missing day, never filled).
    blind=True (dry run) skips the position checks, which need values. keep(cal, sg, group) -> False drops the signal for
    this group (the falsification filter), counted as 'placebo_return_day_in_week4'.
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §3, §5."""
    out, skip = [], collections.Counter()
    for sg in sigs:
        if sg["missing"]:
            skip["no_signal_inputs"] += 1
            continue
        if keep is not None and not keep(cal, sg, group):
            skip["placebo_return_day_in_week4"] += 1
            continue
        if not blind:
            if sg.get(key) is None:
                skip["no_signal"] += 1
                continue
            if sg[key] == 0:
                skip["S_zero_no_trade"] += 1
                continue
        if not daily.days or daily.days[0] > sg["T_prev"]:
            skip["member_history_starts_after_base"] += 1
            continue
        d = return_day(cal, sg["t"], group)
        assert d > sg["t"]
        if d not in daily.bars:
            skip["no_bar_on_return_day"] += 1
            continue
        out.append({"episode": sg["episode"], "t": sg["t"], "T": sg["T"], "d": d, "s": None if blind else sg[key],
                    "symbol": daily.sym})
    return out, skip


def member_rows(read, cal, sigs, daily, group, hours, costs, key="s", keep=None):
    """(outcome rows, skip counts) of ONE read for one member: the open -> close return of each event's server day and one
    round trip of relative spread -- half the median / p90 spread of the table bucket of the entry leg's SERVER hour, half
    of the exit leg's (TableCosts: bucket = (server hour - export offset) mod 24). Each row carries the server and true UTC
    hours, the buckets and the legs priced at the overall fallback. Only events whose episode month is in `read` get a return.
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §4-§5."""
    evs, skip = events(cal, [sg for sg in sigs if episode_read(sg["episode"]) == read], daily, group, key, keep=keep)
    rows = []
    for ev in evs:
        h = hours.get(ev["d"])
        if h is None:
            skip["no_cost_hours"] += 1
            continue
        srv_in, srv_out, src, at_in, at_out = h
        rows.append(dict(ev, r=daily.oc_return(ev["d"]), cost=costs.round_trip(srv_in, srv_out),
                         cost90=costs.round_trip(srv_in, srv_out, "p90"), entry_hour_server=srv_in, exit_hour_server=srv_out,
                         entry_hour_utc=at_in.hour, exit_hour_utc=at_out.hour, cost_bucket_in=costs.bucket(srv_in),
                         cost_bucket_out=costs.bucket(srv_out), cost_fallback=costs.fallback_legs(srv_in, srv_out),
                         cost_hours_source=src))
    return rows, skip


def basket_rows(per_member):
    """Equal weight of the members with a bar on each return day (return and cost); s is shared by construction.
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §4."""
    by_d = collections.defaultdict(list)
    for rows in per_member:
        for r in rows:
            by_d[r["d"]].append(r)
    out = []
    for d in sorted(by_d):
        rs = by_d[d]
        if len({(r["s"], r["episode"]) for r in rs}) != 1:
            raise AssertionError(f"basket day {d}: members disagree on the position / episode")
        k = len(rs)
        out.append({"episode": rs[0]["episode"], "t": rs[0]["t"], "T": rs[0]["T"], "d": d, "s": rs[0]["s"],
                    "r": sum(r["r"] for r in rs) / k, "cost": sum(r["cost"] for r in rs) / k,
                    "cost90": sum(r["cost90"] for r in rs) / k, "members": sorted(r["symbol"] for r in rs),
                    "cost_fallback": sorted(f"{r['symbol']}:{leg}" for r in rs for leg in r.get("cost_fallback", ()))})
    return out


# ------------------------------------------------------------------------------------------------ statistics (§4)
def ols_cr1(y, x, clusters):
    """OLS y = c + gamma x + e with CR1 cluster-robust SEs: (X'X)^-1 (sum_g X_g' u_g u_g' X_g) (X'X)^-1 x G/(G-1) x
    (N-1)/(N-K), K = 2 (Cameron & Miller 2015), Student-t with G-1 df; one-sided p for gamma > 0. edge_census.cr1 applied to
    each observation's influence (n x its row of (X'X)^-1 X' x its residual) gives the G/(G-1) sandwich; (N-1)/(N-2) on top.
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §4."""
    n = len(y)
    out = {"n": n, "clusters": len(set(clusters))}
    if n < 3:
        return out
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((v - mx) ** 2 for v in x)
    if sxx <= 0:
        return out                                        # one-sided position only: gamma not identified
    g = sum((a - mx) * (b - my) for a, b in zip(x, y)) / sxx
    c = my - g * mx
    u = [b - c - g * a for a, b in zip(x, y)]
    adj = math.sqrt((n - 1) / (n - 2))
    _m, se_g, df = EC.cr1([g + n * (a - mx) * e / sxx for a, e in zip(x, u)], clusters)
    _m, se_c, _df = EC.cr1([c + (1.0 - n * mx * (a - mx) / sxx) * e for a, e in zip(x, u)], clusters)
    se_g = se_g * adj if se_g else None
    se_c = se_c * adj if se_c else None
    t = g / se_g if se_g else None
    out.update(gamma=g, intercept=c, se_gamma=se_g, se_intercept=se_c, t_gamma=t, df=df,
               p_one_sided=EC.t_sf(t, df) if t is not None else None)
    return out


def test_stats(rows):
    """Per-test statistics: the OLS slope (H1) and the net gate (mean(s r) - one round trip, median and p90 spread) via
    edge_census.summarise on signed rows (clusters = episode months).
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §4."""
    if not rows:
        return {"n": 0}
    o = ols_cr1([r["r"] for r in rows], [float(r["s"]) for r in rows], [r["episode"] for r in rows])
    net = EC.summarise([{"r": r["s"] * r["r"], "excess": r["s"] * r["r"], "scale": 1.0, "cost": r["cost"],
                         "cost90": r["cost90"], "date": r["episode"]} for r in rows], +1)
    bp = lambda v: None if v is None else v * 1e4  # noqa: E731
    return {"n": len(rows), "episodes": o["clusters"], "first_day": str(min(r["d"] for r in rows)),
            "last_day": str(max(r["d"] for r in rows)), "long_share": sum(r["s"] > 0 for r in rows) / len(rows),
            "gamma_bp": bp(o.get("gamma")), "se_gamma_bp": bp(o.get("se_gamma")), "t_gamma": o.get("t_gamma"),
            "df": o.get("df"), "p_one_sided": o.get("p_one_sided"), "intercept_bp": bp(o.get("intercept")),
            "se_intercept_bp": bp(o.get("se_intercept")), "gross_bp": net["gross_bp"], "net_bp": net["net_bp"],
            "net_bp_p90": net["net_bp_p90"], "cost_bp": net["cost_bp"], "t_net": net["t_net"],
            "p_net_one_sided": net["p_net_one_sided"], "win_rate_net": net["win_rate_net"],
            "cost_fallback_rows": sum(1 for r in rows if r.get("cost_fallback"))}


def verdicts(read, stats, prior=None):
    """{test id: verdict}. DISCOVERY: BH (m = 5, q = 0.10) on the one-sided gamma p, CANDIDATE iff rejected and net > 0.
    CONFIRMATION: a candidate with p < 0.05, net > 0 and net > 0 at the p90 spread. EXPOSED: a confirmed test with p < 0.10
    and net > 0. A test without a p (n = 0, < 2 clusters, constant position) fails.
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §4-§5."""
    ids = list(stats)
    p = {i: (stats[i].get("p_one_sided") if stats[i].get("n") and stats[i].get("p_one_sided") is not None else None)
         for i in ids}
    if read == "discovery":
        if len(ids) != BH_M:
            raise AssertionError(f"BH family must have m = {BH_M} tests, got {len(ids)}")
        rej = EC.bh([1.0 if p[i] is None else p[i] for i in ids], FDR_Q)
        return {i: {"bh_rejected": k in rej, "candidate": bool(k in rej and p[i] is not None and stats[i]["net_bp"] > 0)}
                for k, i in enumerate(ids)}
    prev = {t["id"]: t["verdict"] for t in prior["tests"]}
    out = {}
    for i in ids:
        s = stats[i]
        if read == "confirmation":
            ok = (prev[i]["candidate"] and p[i] is not None and p[i] < CONFIRM_P and s["net_bp"] > 0 and s["net_bp_p90"] > 0)
            out[i] = dict(prev[i], confirmed=bool(ok))
        else:
            ok = prev[i].get("confirmed") and p[i] is not None and p[i] < EXPOSED_P and s["net_bp"] > 0
            out[i] = dict(prev[i], survives=bool(ok))
    return out


def check_prior(read, prior):
    """Refuse a read out of order: confirmation needs the discovery JSON, exposed the confirmation JSON (of THIS script).
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §5."""
    if read not in READS:
        raise SystemExit(f"unknown read {read}")
    if read == "discovery":
        return
    need = READS[READS.index(read) - 1]
    meta = (prior or {}).get("meta") or {}
    if prior is None or meta.get("read") != need or meta.get("script") != SCRIPT or meta.get("preregistration") != PREREG:
        raise SystemExit(f"--read {read} needs --after <the {need} json written by {SCRIPT}>")


# ------------------------------------------------------------------------------------------------ diagnostics (§6)
def owner_sizing(rows, daily):
    """§6 owner sizing: stop = 2.0 x the trailing 20-server-day SD of open -> close returns (strictly earlier days: PIT),
    size = 1 % / stop; a stop hit when the adverse excursion from the open reaches the stop, filled at the stop. R = (signed
    return or -stop, minus the round trip) / stop; P&L % of the account = 1 % x R.
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §6."""
    trades, no_sd = [], 0
    for r in rows:
        dl = daily[r["symbol"]]
        sd = dl.trailing_sd(r["d"])
        if not sd:
            no_sd += 1
            continue
        stop = STOP_K * sd
        o, h, lo, _c = dl.bars[r["d"]]
        adverse = (o - lo) / o if r["s"] > 0 else (h - o) / o
        hit = adverse >= stop
        big_r = ((-stop if hit else r["s"] * r["r"]) - r["cost"]) / stop
        trades.append((hit, big_r))
    if not trades:
        return {"n": 0, "skipped_no_sd_history": no_sd}
    n = len(trades)
    return {"n": n, "skipped_no_sd_history": no_sd, "stop_hits": sum(h for h, _ in trades),
            "stop_hit_rate": sum(h for h, _ in trades) / n, "mean_R_net": sum(x for _, x in trades) / n,
            "net_pnl_pct_total": sum(RISK * 100 * x for _, x in trades), "net_pnl_pct_mean": RISK * 100 * sum(x for _, x in trades) / n}


def crisis_months(us500, lo, hi):
    """Months of [lo, hi] whose US500 SD of server-day open -> close returns (sd-eligible days inside [lo, hi] only, so no
    later read's bar is touched) is in the top CRISIS_SHARE of the span's months with >= CRISIS_MIN_DAYS such days, rounded
    up (a partial edge month of the span is never ranked).
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §6."""
    by_m = collections.defaultdict(list)
    for d in us500.sd_days:
        if lo <= d <= hi:
            by_m[f"{d:%Y-%m}"].append(us500.oc_return(d))
    sds = {m: statistics.stdev(v) for m, v in by_m.items() if len(v) >= CRISIS_MIN_DAYS}
    k = math.ceil(CRISIS_SHARE * len(sds))
    return sorted(sorted(sds, key=lambda m: (-sds[m], m))[:k])


def book_correlation(rows, book, us500):
    """§6 daily P&L correlation of a test's net (s r - round trip, per return day) with fvg-book v3 (H7 + G9 XAUUSD daily R,
    scripts/research/book_sim.py), over the read's return-day span and over its crisis months only.
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §6."""
    if not rows or book is None:
        return None
    bd, corr = book
    mine = collections.defaultdict(float)
    for r in rows:
        mine[str(r["d"])] += r["s"] * r["r"] - r["cost"]
    lo, hi = min(r["d"] for r in rows), max(r["d"] for r in rows)
    b = {d: v for d, v in bd.items() if str(lo) <= d <= str(hi)}
    cm = set(crisis_months(us500, lo, hi))
    pick = lambda mp: {d: v for d, v in mp.items() if d[:7] in cm}  # noqa: E731
    return {"span": [str(lo), str(hi)], "corr_all_days": corr(dict(mine), b), "crisis_months": sorted(cm),
            "corr_crisis_months": corr(pick(mine), pick(b)), "m1_days": len(mine), "book_days": len(b)}


def _book_v3_daily():
    """fvg-book v3 = H7 + G9 XAUUSD (owner 2026-10-03), the same components as edge_f6's 'h7_g9'.
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §6."""
    bs = _load("book_sim", "scripts/research/book_sim.py")
    comps = ["H7_XAUUSD_eod", "G9_XAUUSD_eod"]
    return bs.daily_r([t for c in comps for t in bs.trades(*bs.COMPONENTS[c])]), bs.corr


# ------------------------------------------------------------------------------------------------ one read
def compute_read(read, ctx, prior=None):
    """The whole read on a loaded context (real data in `run`, hand-built bars in the tests): family tests, verdicts and the
    §6 diagnostics, every outcome row from the read's own episode months only.
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §3-§6."""
    check_prior(read, prior)
    cal, mem, daily, yields = ctx["cal"], ctx["members"], ctx["daily"], ctx["yields"]
    us500 = daily[SIGNAL_SYMBOL]
    eps = month_range(*EPISODES[read])
    groups = {"US": mem["US"], "NON_US": mem["NON_US"]}
    fam = family(mem)
    skipped = collections.Counter()
    by_tag = {}                                               # tag -> {sym: member rows}

    def rows_for(sig_list, tag, key="s", keep=None):
        per = {}
        for g, syms in groups.items():
            for sym in syms:
                rs, sk = member_rows(read, cal, sig_list, daily[sym], g, ctx["hours"][sym], ctx["costs"][sym], key, keep)
                per[sym] = rs
                for k, v in sk.items():
                    skipped[f"{tag}|{sym}|{k}"] += v
        by_tag[tag] = per
        return per

    def by_test(per):
        return {tid: (per[syms[0]] if len(syms) == 1 else basket_rows([per[s] for s in syms]))
                for tid, _n, _g, syms, _r in fam}

    sigs = [sg for ep in eps for sg in signals(cal, us500, yields, ep)]
    for sg in sigs:
        for m in sg["missing"]:
            skipped[f"signal|{m}"] += 1
    main = rows_for(sigs, "main")
    rows = by_test(main)
    stats = {tid: test_stats(rows[tid]) for tid in rows}
    v = verdicts(read, stats, prior)
    tests = [{"id": tid, "name": name, "group": g, "members": list(syms), "role": role, read: stats[tid], "verdict": v[tid]}
             for tid, name, g, syms, role in fam]
    key = {"discovery": "candidate", "confirmation": "confirmed", "exposed": "survives"}[read]
    decision = {"decision_test": "T1", "T1": v["T1"][key], "T5_own_promotion": v["T5"][key],
                "T2_T4_record_only": {i: v[i][key] for i in ("T2", "T3", "T4")}, "criterion": key}

    diag = {}
    eq = by_test(rows_for(sigs, "equity_only", "s_eq"))
    diag["equity_only_signal"] = {tid: test_stats(r) for tid, r in eq.items()}
    plc = [signal_at(cal, us500, yields, ep, t) for ep in eps for t in placebo_days(cal, *_ym(ep))]
    fz = by_test(rows_for(plc, "falsification", keep=placebo_keep))
    diag["falsification_non_week4_same_weekday"] = {tid: test_stats(r) for tid, r in fz.items()}
    rv = by_test(rows_for(reversal_signals(cal, sigs), "reversal"))
    diag["first_business_day_reversal_descriptive"] = {tid: test_stats(r) for tid, r in rv.items()}
    w4 = {ep: cal.week4(*_ym(ep)) for ep in eps}
    in_t3_t1 = lambda r: w4[r["episode"]][1] <= r["d"] <= w4[r["episode"]][3]  # noqa: E731
    diag["return_days_T-3_to_T-1_only"] = {tid: test_stats([r for r in rs if in_t3_t1(r)]) for tid, rs in rows.items()}
    diag["owner_sizing"] = {tid: owner_sizing([r for s in syms for r in main[s]], daily) for tid, _n, _g, syms, _r in fam}
    diag["corr_with_fvg_book_v3"] = {tid: book_correlation(rows[tid], ctx.get("book"), us500) for tid in ("T1", "T5")}
    every = {tag: [r for rs in per.values() for r in rs] for tag, per in by_tag.items()}
    span = {tag: [str(min(r["d"] for r in rs)), str(max(r["d"] for r in rs))] for tag, rs in every.items() if rs}
    late = {tag: {tid: sorted({str(r["d"]) for r in rs if r["d"] >= DEV_CUTOFF[0]})
                  for tid, rs in by_test(by_tag[tag]).items() if any(r["d"] >= DEV_CUTOFF[0] for r in rs)}
            for tag in by_tag}
    meta = {"script": SCRIPT, "read": read, "preregistration": PREREG, "episodes": [eps[0], eps[-1], len(eps)],
            "members": mem, "signal_symbol": SIGNAL_SYMBOL, "lag": {g: list(v) for g, v in LAG.items()},
            "weights": [W_EQ, W_BOND], "duration": DURATION, "fdr_q": FDR_Q, "bh_m": BH_M, "confirm_p": CONFIRM_P,
            "exposed_p": EXPOSED_P, "cost_profile": EC.COST_PROFILE,
            "cost_bucket_frame": {sym: {"export_server_utc_offset_hours": ctx["costs"][sym].offset,
                                        "bucket": "(server hour - export offset) mod 24",
                                        "fallback_server_hours": list(FALLBACK_SERVER_HOURS),
                                        "overall_fallback_buckets": ctx["costs"][sym].fallback_buckets()}
                                  for sym in mem["US"] + mem["NON_US"]},
            "return_day_span": span,
            "return_days_after_dev_cutoff": {"cutoff": str(DEV_CUTOFF[0]), "ledger_period": DEV_CUTOFF[1],
                                             "days": {tag: v for tag, v in late.items() if v}},
            "data_quality_flags": weekend_bar_flags(daily, eps, main),
            "resolved_ambiguities": RESOLVED_AMBIGUITIES}
    return {"meta": meta, "tests": tests, "decision": decision, "diagnostics": diag, "skipped": dict(sorted(skipped.items())),
            "cost_hours_source": {sym: dict(collections.Counter(r["cost_hours_source"] for r in rs)) for sym, rs in main.items()},
            "cost_fallback_rows": {tag: {sym: sum(1 for r in rs if r["cost_fallback"]) for sym, rs in per.items()}
                                   for tag, per in by_tag.items()},
            "cost_hours_shifted_minus_1h_rows": {sym: len({r["d"] for r in rs} & set(ctx["hours"][sym].shifted_minus_1h_days))
                                                 for sym, rs in main.items()}}


def weekend_bar_flags(daily, eps, main):
    """Data-quality flags (not exclusions): per member with weekend-dated 1D bars, their count and span, the read's episode
    months between the first and last such bar's months, and how many main rows those episodes hold.
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §2-§3."""
    out = {}
    for sym, dl in daily.items():
        wk = dl.weekend_days
        if not wk:
            continue
        a, b = f"{wk[0]:%Y-%m}", f"{wk[-1]:%Y-%m}"
        flagged = [ep for ep in eps if a <= ep <= b]
        out[sym] = {"weekend_dated_1d_bars": len(wk), "first": str(wk[0]), "last": str(wk[-1]),
                    "episodes_flagged_in_read": flagged,
                    "main_rows_in_flagged_episodes": sum(1 for r in main.get(sym, ()) if r["episode"] in flagged),
                    "note": "weekend-dated server-day bars: the next weekday's 1D open may not be the first quote after the "
                            "weekend; flagged, not excluded"}
    return out


# ------------------------------------------------------------------------------------------------ loading
def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_context():
    """Real data: 1D and 1H FTMO bars of the six members, their costs (in the table's bucket frame), DGS10, the NYSE and
    Board calendars, and provenance (§10 dataset snapshot: per-series sha256 digests, the cost specs and the cost profile
    snapshot). Refuses a series whose server clock differs from the provider's, and a member whose modal intraday server
    hours are not FALLBACK_SERVER_HOURS (the constant would then be wrong).
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §2."""
    zone_name, zone = RC.server_zone(PROVIDER)
    cal = NyseCalendar()
    mem = members()
    daily, hours, costs, prov = {}, {}, {}, {}
    for sym in mem["US"] + mem["NON_US"]:
        doc, path = HS.read_doc(sym, "1D", root=HIST_ROOT)
        doc_h, path_h = HS.read_doc(sym, "1H", root=HIST_ROOT)
        if doc is None or doc_h is None:
            raise SystemExit(f"no 1D / 1H history for {sym} under {HIST_ROOT}")
        for d in (doc, doc_h):
            if d.get("_server_timezone") != zone_name:
                raise SystemExit(f"{sym}: series clock {d.get('_server_timezone')!r} != provider clock {zone_name!r}")
        daily[sym] = Daily(sym, doc["candles"], zone, doc.get("_exported_at_utc"),
                           sd_exclude=cal.holidays if sym in mem["US"] else ())
        hours[sym] = SessionHours(doc_h["candles"], zone, zoneinfo.ZoneInfo(EC.OPEN_LOCAL[sym][0]))
        if not hours[sym].modes_match_constant():
            raise SystemExit(f"{sym}: modal intraday server hours {hours[sym].mode} != {FALLBACK_SERVER_HOURS}; refusing "
                             "the server-clock constant for D1-filled days")
        costs[sym] = TableCosts.load(sym)
        prov[sym] = {tf: {"path": os.path.relpath(p, ROOT), "sha256": HS.digest(sym, tf, root=HIST_ROOT),
                          "server": dd.get("_server"), "exported_at_utc": dd.get("_exported_at_utc"),
                          "first": dd.get("first"), "last": dd.get("last")}
                     for tf, dd, p in (("1D", doc, path), ("1H", doc_h, path_h))}
        sp_path = RC.spec_path(EC.COST_PROFILE, sym)
        sp = RC.spec(EC.COST_PROFILE, sym)
        prov[sym]["cost_spec"] = {"path": os.path.relpath(sp_path, ROOT), "sha256": _sha256(sp_path),
                                  "_exported_at_utc": sp.get("_exported_at_utc"),
                                  "_server_utc_offset_sec_now": sp.get("_server_utc_offset_sec_now"),
                                  "overall_fallback_buckets": costs[sym].fallback_buckets()}
    prov["cost_profile"] = RC.profile_snapshot(EC.COST_PROFILE, mem["US"] + mem["NON_US"])
    with open(FRED_PATH, encoding="utf-8") as fh:
        fred = json.load(fh)
    prov["DGS10"] = dict({k: fred.get(k) for k in ("series", "_source", "_sha256_of_download", "_fetched_at_utc", "_pit")},
                         path=os.path.relpath(FRED_PATH, ROOT), file_sha256=_sha256(FRED_PATH),
                         pit_rule_used="Yields.available_at (H.15 posting day <= t), not the header's _pit")
    return {"cal": cal, "members": mem, "daily": daily, "hours": hours, "costs": costs, "yields": Yields(fred["rows"], cal),
            "provenance": prov, "server_zone": zone_name}


def snapshot_matches_prior(prior_prov, prov):
    """{series: bool}: whether each member's 1D / 1H / cost-spec digest and DGS10's file digest equal the prior read's
    (None when the prior JSON did not record that series).
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §5."""
    prior_prov = prior_prov or {}
    out = {}
    for sym, p in prov.items():
        if sym in ("DGS10", "cost_profile"):
            continue
        for part in ("1D", "1H", "cost_spec"):
            old = ((prior_prov.get(sym) or {}).get(part) or {}).get("sha256")
            out[f"{sym}/{part}"] = None if old is None else old == p[part]["sha256"]
    old = (prior_prov.get("DGS10") or {}).get("file_sha256")
    out["DGS10"] = None if old is None else old == prov["DGS10"]["file_sha256"]
    return out


def run(read, out_path, after=None):
    """One pre-registered read on the real data, written to `out_path`. Refuses an existing `out_path` (each read runs
    ONCE) and an out-of-order read, both before any data is loaded.
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §5."""
    if os.path.exists(out_path):
        raise SystemExit(f"{out_path} exists: each read is run ONCE (pre-registration §5); refusing to overwrite")
    prior = None
    if after:
        with open(after, encoding="utf-8") as fh:
            prior = json.load(fh)
    check_prior(read, prior)                                  # before any data is loaded
    ctx = load_context()
    ctx["book"] = _book_v3_daily()
    res = compute_read(read, ctx, prior)
    res["meta"].update(provenance=ctx["provenance"], server_zone=ctx["server_zone"],
                       script_sha256=_sha256(os.path.join(ROOT, SCRIPT)),
                       preregistration_sha256=_sha256(os.path.join(ROOT, PREREG)),
                       member_qa={s: dict(d.qa) for s, d in ctx["daily"].items()}, dgs10_qa=dict(ctx["yields"].qa),
                       cost_hours_qa={s: {"server_modes": {str(k): list(v) for k, v in h.mode.items()},
                                          "intraday_days_off_constant_hours": h.off_constant_days,
                                          "shifted_minus_1h_days": len(h.shifted_minus_1h_days),
                                          "shifted_minus_1h_span": [str(h.shifted_minus_1h_days[0]),
                                                                    str(h.shifted_minus_1h_days[-1])]
                                          if h.shifted_minus_1h_days else None}
                                      for s, h in ctx["hours"].items()})
    if prior is not None:
        pm = prior["meta"]
        snap = snapshot_matches_prior(pm.get("provenance"), ctx["provenance"])
        res["meta"].update(after={"path": after, "sha256": _sha256(after), "script_sha256": pm.get("script_sha256"),
                                  "script_changed_since": pm.get("script_sha256") != res["meta"]["script_sha256"]},
                           snapshot_matches_prior=snap)
        changed = sorted(k for k, v in snap.items() if v is False)
        if changed:
            print(f"WARNING: data snapshot differs from the prior read for {changed} (recorded in meta.snapshot_matches_prior)")
    with open(out_path, "x", encoding="utf-8") as fh:        # "x": never overwrite, even on a race with the check above
        json.dump(res, fh, indent=1, default=str)
    f = lambda v, p=2: "n/a" if v is None else f"{v:+.{p}f}"  # noqa: E731
    for t in res["tests"]:
        d = t[read]
        print(f"{t['id']} {t['name']:14s} n {d.get('n', 0):4d} G {d.get('episodes', 0):3d} gamma {f(d.get('gamma_bp'))} bp "
              f"p1 {f(d.get('p_one_sided'), 4)} net {f(d.get('net_bp'))} bp p90 {f(d.get('net_bp_p90'))} bp | {t['verdict']}")
    print(f"decision: {res['decision']}")
    print(f"wrote {out_path}")


# ------------------------------------------------------------------------------------------------ dry run (outcome-blind)
def dry_run(ctx):
    """Outcome-blind counts: per member bar counts, spans, gap counts, data-QA counters, cost-hour QA (server-clock modes,
    table buckets with no recorded bar); DGS10 coverage; NYSE / Board days; per read and member the episode / signal-day /
    event counts, cost-fallback counts, the non-US weekday-lag days and the falsification filter. Reads NO price and NO
    yield VALUE (signal_at values=False, events blind=True): no return, P&L, excess or win rate exists here.
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §2, §5."""
    cal, mem, daily, hours, yields = ctx["cal"], ctx["members"], ctx["daily"], ctx["hours"], ctx["yields"]
    costs = ctx["costs"]
    us500 = daily[SIGNAL_SYMBOL]
    groups = {"US": mem["US"], "NON_US": mem["NON_US"]}
    win = (datetime.date(2017, 12, 1), datetime.date(2026, 9, 30))
    out = {"meta": {"script": SCRIPT, "mode": "dry-run (outcome-blind: counts only)", "preregistration": PREREG,
                    "members": mem, "resolved_ambiguities": RESOLVED_AMBIGUITIES},
           "nyse_business_days_per_year": {y: sum(1 for d in cal.days if d.year == y) for y in range(2017, 2027)},
           "nyse_holidays_in_window": {str(d): n for d, n in sorted(cal.holidays.items()) if win[0] <= d <= win[1]},
           "nyse_days_board_closed_in_window": {str(d): n for d, n in sorted(yields.board.holidays.items())
                                                if win[0] <= d <= win[1] and cal.is_open(d)},
           "members": {}, "dgs10": {}, "reads": {}}
    for sym, dl in daily.items():
        days = dl.days
        span = [d for d in cal.days if days[0] <= d <= days[-1]]
        h = hours[sym]
        out["members"][sym] = {"bars_1d": len(days), "first_server_day": str(days[0]), "last_server_day": str(days[-1]),
                               "qa": dict(dl.qa), "weekend_bars": len(dl.weekend_days),
                               "weekend_bar_span": ([str(dl.weekend_days[0]), str(dl.weekend_days[-1])]
                                                    if dl.weekend_days else None),
                               "bars_on_nyse_holidays": sum(1 for d in days if d.weekday() < 5 and not cal.is_open(d)),
                               "nyse_days_without_bar": sum(1 for d in span if d not in dl.bars),
                               "sd_eligible_bars": len(dl.sd_days),
                               "server_days_with_intraday_1h": len(h.actual),
                               "server_days_with_d1_filled_1h": len(h.thin_days),
                               "last_d1_filled_1h_day": str(max(h.thin_days)) if h.thin_days else None,
                               "intraday_server_hour_modes_by_regime": {str(k): list(v) for k, v in h.mode.items()},
                               "intraday_modes_match_constant": h.modes_match_constant(),
                               "intraday_days_off_constant_hours": h.off_constant_days,
                               "intraday_days_shifted_minus_1h": len(h.shifted_minus_1h_days),
                               "intraday_days_shifted_minus_1h_span": [str(h.shifted_minus_1h_days[0]),
                                                                       str(h.shifted_minus_1h_days[-1])]
                               if h.shifted_minus_1h_days else None,
                               "cost_export_offset_hours": costs[sym].offset,
                               "cost_buckets_overall_fallback": costs[sym].fallback_buckets(),
                               "constant_hour_buckets": [costs[sym].bucket(x) for x in FALLBACK_SERVER_HOURS]}
    lo = datetime.date(2017, 12, 1)
    needed = [d for d in cal.days if lo <= d <= (yields.dates[-1] if yields.dates else lo)]
    have = set(yields.dates)
    out["dgs10"] = {"qa": dict(yields.qa), "first_value_date": str(yields.dates[0]) if yields.dates else None,
                    "last_value_date": str(yields.dates[-1]) if yields.dates else None,
                    "nyse_days_since_2017_12_without_value": sum(1 for d in needed if d not in have)}
    for read in READS:
        eps = month_range(*EPISODES[read])
        sigs = [sg for ep in eps for sg in signals(cal, us500, yields, ep, values=False)]
        lag_gap = collections.Counter()
        for sg in sigs:
            if sg["y_lag_date"] is not None:
                lag_gap[sum(1 for d in cal.days if sg["y_lag_date"] < d < sg["t"])] += 1
        missing = collections.Counter(m for sg in sigs for m in sg["missing"])
        older = [str(sg["t"]) for sg in sigs if sg["y_lag_date"] is not None
                 and (yields.asof(cal.prev(sg["t"])) or (None,))[0] != sg["y_lag_date"]]
        rd = {"episodes": [eps[0], eps[-1], len(eps)], "week4_signal_days": len(sigs),
              "signal_days_with_all_inputs": sum(1 for sg in sigs if not sg["missing"]),
              "signal_input_missing": dict(missing),
              "yield_lag_nyse_days_between_value_and_t": {str(k): v for k, v in sorted(lag_gap.items())},
              "signal_days_where_board_rule_takes_an_older_yield": older,
              "yield_base_dated_before_T_prev": sum(1 for sg in sigs if sg["y_base_date"] not in (None, sg["T_prev"])),
              "members": {}, "basket_days": {}, "falsification": {}}
        rev = reversal_signals(cal, sigs)
        plc = [signal_at(cal, us500, yields, ep, t, values=False) for ep in eps for t in placebo_days(cal, *_ym(ep))]
        for g, syms in groups.items():
            union, f_union = set(), set()
            for sym in syms:
                evs, sk = events(cal, sigs, daily[sym], g, blind=True)
                rvs, _ = events(cal, rev, daily[sym], g, blind=True)
                fz, fsk = events(cal, plc, daily[sym], g, blind=True, keep=placebo_keep)
                union |= {e["d"] for e in evs}
                f_union |= {e["d"] for e in fz}
                hs = [hours[sym].get(e["d"]) for e in evs]
                m = {"events": len(evs), "episodes_with_events": len({e["episode"] for e in evs}),
                     "return_days_by_cost_hours_source": dict(collections.Counter(x[2] for x in hs)),
                     "return_days_by_cost_buckets": {f"{a}-{b}": n for (a, b), n in sorted(collections.Counter(
                         (costs[sym].bucket(x[0]), costs[sym].bucket(x[1])) for x in hs).items())},
                     "return_days_with_cost_fallback": sum(1 for x in hs if costs[sym].fallback_legs(x[0], x[1])),
                     "reversal_events": len(rvs), "falsification_events": len(fz),
                     "falsification_dropped_return_day_in_week4": fsk["placebo_return_day_in_week4"],
                     "skipped": dict(sk)}
                if g == "NON_US":
                    m["main_and_reversal_events_whose_day_differs_from_the_2nd_nyse_day"] = sum(
                        1 for e in evs + rvs if e["d"] != cal.next(e["t"], 2))
                rd["members"][sym] = m
            rd["basket_days"][g] = len(union)
            rd["falsification"][g] = {"basket_days": len(f_union)}
        rd["falsification_signal_days_with_all_inputs"] = sum(1 for sg in plc if not sg["missing"])
        out["reads"][read] = rd
    return out


def dry_run_cli(out_path):
    """`dry-run --out <json>`: load the real data and write the outcome-blind counts.
    Pre-registration docs/plans/2026-10-03-edge-m1-month-end-preregistration.md §2, §5."""
    ctx = load_context()
    res = dry_run(ctx)
    res["meta"].update(provenance=ctx["provenance"], server_zone=ctx["server_zone"])
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, default=str)
    for read, rd in res["reads"].items():
        print(f"{read:12s} episodes {rd['episodes'][2]:3d} signal days {rd['signal_days_with_all_inputs']:4d}/"
              f"{rd['week4_signal_days']:4d} events " + " ".join(f"{s} {m['events']}" for s, m in rd["members"].items()))
    print(f"wrote {out_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--read", required=True, choices=READS)
    r.add_argument("--out", required=True)
    r.add_argument("--after")
    d = sub.add_parser("dry-run")
    d.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.read, a.out, a.after)
    else:
        dry_run_cli(a.out)


if __name__ == "__main__":
    main()
