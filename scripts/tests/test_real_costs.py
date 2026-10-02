"""A0 real costs (docs/plans/2026-09-28-methodology-improvement-plan.md §2) -- scripts/real_costs.py, and its
two integration points in scripts/backtest-methods.py: `simulate(..., cost_profile=...)` and
`walk(..., Tm=...)`'s `OPTS["flat_before_rollover"]` fund-cell rule.

Four things this file has to prove, per the dispatch:
  * spread lookup by UTC hour (median/p90, and the daily-break-hour fallback);
  * swap nights, including the triple-swap day and a hold that crosses the FTMO server's US-dates DST edge;
  * flatten-before-rollover exits at the right bar and NEVER at a later one (CLAUDE.md §8 point-in-time);
  * leaving `cost_profile`/`flat_before_rollover` unset reproduces the PRE-A0 `simulate()` formula exactly
    (`2 * fee_pct / dist`), so every existing caller's output is unchanged (plan §1.6 "live safety").

Code review 2026-09-29, fix round 1 (critical, F1): `mt5_time.UsDatesFixedOffsetZone` had no `fromutc()`, so
Python's default (wall-clock-guessing) implementation ran instead -- and it guesses wrong near a US DST edge,
because `dt` arrives with UTC digits and only `tzinfo` swapped to the zone, which the default algorithm reads
AS IF it were already local. Repro: 2026-03-08 06:00-08:00Z round-tripped through `.astimezone(ftmo_zone)`
came back one hour late and jumped by TWO hours instead of one. `real_costs.crosses_rollover`/`nights_held`
call exactly this path (`.astimezone(zone)` on a stored UTC bar time), so the bug reached every swap/flatten
decision near a US transition. `FromUtcIsExactAcrossDstTransitions` below is the adversarial regression test;
`mt5_time.py`'s own `fromutc()` docstring carries the fix's reasoning.
"""
import datetime
import importlib.util
import os
import sys
import unittest
import unittest.mock
import zoneinfo

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import real_costs as RC  # noqa: E402
import mt5_time as MT    # noqa: E402

FTMO = "ftmo_demo_2026_09"
PROVIDER = "mt5_bridge_ftmo"
UTC = datetime.timezone.utc


def _bt():
    """A fresh module instance, matching test_backtesting.py's own convention: backtest-methods.py runs
    top-level config reads at import time, so every test that mutates its module-global OPTS gets an
    isolated copy rather than fighting other test files over one cached `sys.modules` entry."""
    spec = importlib.util.spec_from_file_location("bt_real_costs", os.path.join(ROOT, "scripts", "backtest-methods.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class SpreadLookupByHour(unittest.TestCase):
    def test_hour_with_recorded_bars_uses_that_hours_median(self):
        d = RC.spec(FTMO, "XAUUSD")
        row = next(r for r in d["recorded_spread_m15"]["by_utc_hour"] if r["h"] == 14)
        price, note = RC.spread_price(FTMO, "XAUUSD", 14, stat="median")
        self.assertEqual(note, "hour")
        self.assertAlmostEqual(price, row["median"] * d["point"])

    def test_p90_stat_reads_the_p90_column(self):
        d = RC.spec(FTMO, "XAUUSD")
        row = next(r for r in d["recorded_spread_m15"]["by_utc_hour"] if r["h"] == 14)
        price, _ = RC.spread_price(FTMO, "XAUUSD", 14, stat="p90")
        self.assertAlmostEqual(price, row["p90"] * d["point"])

    def test_an_hour_with_no_recorded_bars_falls_back_to_the_overall_figure_and_flags_it(self):
        # XAUUSD's FTMO-Demo export records n=0 at UTC hour 21 (the broker's daily break) -- see
        # data/history/costs/ftmo/symbolspec.XAUUSD.json.
        d = RC.spec(FTMO, "XAUUSD")
        row = next(r for r in d["recorded_spread_m15"]["by_utc_hour"] if r["h"] == 21)
        self.assertEqual(row["n"], 0)
        price, note = RC.spread_price(FTMO, "XAUUSD", 21, stat="median")
        self.assertEqual(note, "overall_fallback")
        self.assertAlmostEqual(price, d["recorded_spread_m15"]["median_points"] * d["point"])

    def test_an_unmapped_symbol_refuses_rather_than_guessing(self):
        with self.assertRaises(RC.CostRefused):
            RC.spread_price(FTMO, "NOSUCHSYMBOL", 12)

    def test_an_unknown_profile_refuses(self):
        with self.assertRaises(RC.CostRefused):
            RC.spread_price("not_a_real_profile", "XAUUSD", 12)


class SwapNightsAndTripleDay(unittest.TestCase):
    def test_one_ordinary_night_charges_the_bare_swap_once(self):
        # 2024-01-01 (Mon) -> 2024-01-02 (Tue): one night, not the FTMO XAUUSD triple day (Wed, MQL5 dow 3).
        d = RC.spec(FTMO, "XAUUSD")
        signed, nights, note = RC.swap_price(FTMO, "XAUUSD", "long", "2024-01-01T10:00:00Z", "2024-01-02T10:00:00Z")
        self.assertEqual(nights, 1)
        self.assertEqual(note, "swap_mode_points")
        self.assertAlmostEqual(signed, d["swap_long"] * d["point"])

    def test_the_wednesday_rollover_is_tripled(self):
        # 2024-01-03 is a Wednesday; MQL5 dow (Sun=0..Sat=6) for Wednesday is 3, matching XAUUSD's own
        # swap_rollover3days=3 (data/history/costs/ftmo/symbolspec.XAUUSD.json).
        d = RC.spec(FTMO, "XAUUSD")
        self.assertEqual(d["swap_rollover3days"], 3)
        signed, nights, _ = RC.swap_price(FTMO, "XAUUSD", "long", "2024-01-03T10:00:00Z", "2024-01-04T10:00:00Z")
        self.assertEqual(nights, 1)
        self.assertAlmostEqual(signed, d["swap_long"] * d["point"] * 3)

    def test_short_side_uses_swap_short(self):
        d = RC.spec(FTMO, "XAUUSD")
        signed, nights, _ = RC.swap_price(FTMO, "XAUUSD", "short", "2024-01-01T10:00:00Z", "2024-01-02T10:00:00Z")
        self.assertEqual(nights, 1)
        self.assertAlmostEqual(signed, d["swap_short"] * d["point"])

    def test_a_hold_spanning_the_ftmo_us_dates_dst_edge_still_counts_one_night_per_calendar_day(self):
        # 2024-03-10 is the US "spring forward" Sunday; FTMO-Demo's server_timezone_convention
        # (us_dst_dates_fixed_offset, docs/audits/2026-09-29-ftmo-server-timezone.md) jumps its own offset on
        # this date. A position opened the Friday before and closed the Monday after must still resolve to
        # exactly 3 calendar nights (Fri->Sat, Sat->Sun, Sun->Mon) despite the mid-span offset change -- this
        # is the same zone conversion mt5_time.py already gets right, reused rather than re-derived (§58).
        nights = RC.nights_held("2024-03-08T10:00:00Z", "2024-03-11T10:00:00Z", PROVIDER)
        self.assertEqual(len(nights), 3)

    def test_an_invalid_side_refuses(self):
        with self.assertRaises(RC.CostRefused):
            RC.swap_price(FTMO, "XAUUSD", "sideways", "2024-01-01T10:00:00Z", "2024-01-02T10:00:00Z")

    def test_every_ftmo_export_declares_swap_mode_points(self):
        # A0's re-pricing task (plan §2/§6 items 3/7) reads FTMO-Demo only, and every FTMO export recorded so
        # far IS swap_mode 1 (data/history/costs/ftmo/symbol-map.json's own note) -- pinned so a future export
        # in a different mode is caught here first, not by a silent wrong number downstream.
        profile = RC.PROFILES[FTMO]
        # Owner 2026-10-01 (symbol universe): these nine are MAPPED in symbol-map.json (so `fund-search.py plan --check-data`
        # can name the file it is waiting for) but their symbolspec.<RAW>.json is exported by the owner LATER. Only while the
        # file is absent are they skipped; the moment it exists it is held to swap_mode 1 like every other export. Every
        # other mapped symbol must have its spec, as before.
        pending = {"XPTUSD", "XPDUSD", "UK100", "EU50", "JP225", "HK50", "US2000", "SPN35", "N25"}
        for sym in dict(RC._reverse_symbol_map(profile["symbol_map"])):
            with self.subTest(symbol=sym):
                if sym in pending and not os.path.exists(RC.spec_path(FTMO, sym)):
                    continue
                self.assertEqual(RC.spec(FTMO, sym)["swap_mode"], 1)

    def test_the_pending_new_universe_symbols_are_mapped_to_their_cash_spec_file_names(self):
        expect = {"UK100": "symbolspec.UK100.cash.json", "EU50": "symbolspec.EU50.cash.json",
                  "JP225": "symbolspec.JP225.cash.json", "HK50": "symbolspec.HK50.cash.json",
                  "US2000": "symbolspec.US2000.cash.json", "SPN35": "symbolspec.SPN35.cash.json",
                  "N25": "symbolspec.N25.cash.json", "XPTUSD": "symbolspec.XPTUSD.json", "XPDUSD": "symbolspec.XPDUSD.json"}
        for sym, fname in expect.items():
            self.assertEqual(os.path.basename(RC.spec_path(FTMO, sym)), fname)
        for sym in expect:
            if not os.path.exists(RC.spec_path(FTMO, sym)):
                with self.assertRaises(RC.CostRefused, msg=sym):   # an absent spec is refused, never defaulted or borrowed
                    RC.spec(FTMO, sym)

    def test_a_non_points_swap_mode_refuses_rather_than_being_priced_wrong(self):
        # MetaQuotes-Demo's own indices are NOT all swap_mode 1 (measured: US500=2 CURRENCY_SYMBOL, FRA40=0
        # DISABLED, AUS200/DE40/US30/USTEC=3 CURRENCY_MARGIN -- data/history/costs/symbolspec.*.json). This is
        # exactly the case the guard exists for: refuse rather than apply the POINTS formula to a spec that
        # does not mean what it says.
        metaquotes = "metaquotes_demo_2026_09"
        for sym in ("US500", "FRA40", "AUS200"):
            with self.subTest(symbol=sym):
                self.assertNotEqual(RC.spec(metaquotes, sym)["swap_mode"], 1)
                with self.assertRaises(RC.CostRefused):
                    RC.swap_price(metaquotes, sym, "long", "2024-01-01T10:00:00Z", "2024-01-02T10:00:00Z")


class CommissionIsNeverGuessed(unittest.TestCase):
    def test_commission_is_always_zero_and_carries_the_specs_own_status(self):
        d = RC.spec(FTMO, "XAUUSD")
        commission_R, state = RC.commission_r(FTMO, "XAUUSD")
        self.assertEqual(commission_R, 0.0)
        self.assertEqual(state, d["commission"]["status"])
        self.assertEqual(state, "no_deals")


class CostRIntegration(unittest.TestCase):
    def test_cost_r_combines_spread_and_swap_into_total_R(self):
        entry, stop = 2000.0, 1990.0
        r = RC.cost_r(entry, stop, "2024-01-01T10:00:00Z", "2024-01-01T12:00:00Z", "XAUUSD", "long", FTMO)
        self.assertAlmostEqual(r["total_R"], r["spread_R"] + r["swap_R"] + r["commission_R"])
        self.assertEqual(r["nights_held"], 0)
        self.assertGreater(r["spread_R"], 0)   # a same-day round trip still pays the spread

    def test_a_zero_stop_distance_refuses(self):
        with self.assertRaises(RC.CostRefused):
            RC.cost_r(2000.0, 2000.0, "2024-01-01T10:00:00Z", "2024-01-01T12:00:00Z", "XAUUSD", "long", FTMO)


class RolloverProviderIsRequired(unittest.TestCase):
    """Code review 2026-09-29, fix round 1 (minor, item 3): `rollover_provider=None` must refuse as
    `CostRefused`, not surface whatever unguided exception `mt5_time`/`providers` happens to raise for a
    `None` id -- `OPTS["flat_before_rollover"]`/`OPTS["rollover_provider"]` are meant to be set together
    (`main()` refuses the CLI combination that would split them), but `server_zone` is the one place that
    actually enforces it for every caller (a test, a future direct `real_costs` caller)."""

    def test_server_zone_none_refuses(self):
        with self.assertRaises(RC.CostRefused) as cm:
            RC.server_zone(None)
        self.assertIn("rollover_provider", str(cm.exception))

    def test_crosses_rollover_none_refuses(self):
        with self.assertRaises(RC.CostRefused):
            RC.crosses_rollover("2024-01-01T21:45:00Z", "2024-01-01T22:15:00Z", None)

    def test_nights_held_none_refuses(self):
        with self.assertRaises(RC.CostRefused):
            RC.nights_held("2024-01-01T10:00:00Z", "2024-01-03T10:00:00Z", None)

    def test_walk_with_the_flag_on_and_no_provider_refuses_cleanly(self):
        bt = _bt()
        try:
            bt.OPTS.update(flat_before_rollover=True, rollover_provider=None)
            H = L = C = [100.0] * 8
            Tm = [f"2024-01-01T21:{m:02d}:00Z" for m in (0, 15, 30, 45)] + \
                 [f"2024-01-01T22:{m:02d}:00Z" for m in (0, 15, 30, 45)]
            with self.assertRaises(RC.CostRefused):
                bt.walk("long", 99.0, 90.0, 200.0, H, L, C, 0, len(C), Tm=Tm)
        finally:
            bt.reset_opts()


class FromUtcIsExactAcrossDstTransitions(unittest.TestCase):
    """Code review 2026-09-29, fix round 1 (critical, item 1): `UsDatesFixedOffsetZone.fromutc()` -- the path
    every `.astimezone(zone)` call on a UTC-aware datetime routes through, and therefore the path
    `real_costs.crosses_rollover`/`nights_held` actually use on stored (UTC) bar times.

    Ground truth for "when does the US transition happen, in UTC" is the real `America/New_York` zoneinfo
    object's own `.dst()` flip -- bisected to the minute, not hardcoded as "2am local" (which is today's US
    rule but not a rule this test should assume). `fromutc()` must flip our synthetic zone's offset at
    EXACTLY that UTC instant, regardless of the zone's own std/dst magnitude."""

    _NY = zoneinfo.ZoneInfo("America/New_York")

    def _true_ny_transition(self, lo, hi):
        """Bisect (to the minute) the UTC instant NY's own `dst()` state flips between `lo` and `hi`."""
        lo_dst = lo.astimezone(self._NY).dst()
        while hi - lo > datetime.timedelta(minutes=1):
            mid = lo + (hi - lo) // 2
            if mid.astimezone(self._NY).dst() == lo_dst:
                lo = mid
            else:
                hi = mid
        return hi

    def _assert_offset_flips_exactly_at(self, zone, true_instant, window=datetime.timedelta(hours=2)):
        """Minute-by-minute walk across `true_instant +/- window`: the zone's own UTC offset (via
        `.astimezone(zone).utcoffset()`, i.e. through `fromutc()`) must change at exactly one minute in the
        walk, and that minute must be `true_instant`."""
        t = true_instant - window
        end = true_instant + window
        prev = t.astimezone(zone).utcoffset()
        flips = []
        t += datetime.timedelta(minutes=1)
        while t <= end:
            off = t.astimezone(zone).utcoffset()
            if off != prev:
                flips.append(t)
            prev = off
            t += datetime.timedelta(minutes=1)
        self.assertEqual(flips, [true_instant],
                         f"zone flipped at {flips}, expected exactly one flip at {true_instant}")

    def test_march_and_november_transitions_two_years_ftmo_magnitude(self):
        # FTMO-Demo's own declared magnitude (std=+02:00, dst=+03:00, docs/architecture/providers.json
        # mt5_bridge_ftmo) -- the exact zone real_costs.py prices against.
        zone = MT.UsDatesFixedOffsetZone(datetime.timedelta(hours=2), datetime.timedelta(hours=3))
        for year in (2025, 2026):
            march = self._true_ny_transition(datetime.datetime(year, 1, 1, tzinfo=UTC),
                                             datetime.datetime(year, 4, 1, tzinfo=UTC))
            november = self._true_ny_transition(datetime.datetime(year, 10, 1, tzinfo=UTC),
                                                 datetime.datetime(year, 12, 1, tzinfo=UTC))
            with self.subTest(year=year, transition="march"):
                self._assert_offset_flips_exactly_at(zone, march)
            with self.subTest(year=year, transition="november"):
                self._assert_offset_flips_exactly_at(zone, november)

    def test_a_different_magnitude_is_not_incidental_to_02_03(self):
        # +01:00/+02:00 -- a different pair of offsets than FTMO's, on the SAME (real) NY transition dates,
        # proving the fix reads the transition off NY's own calendar rather than off a std/dst-specific
        # shortcut that happened to work for +02/+03.
        zone = MT.UsDatesFixedOffsetZone(datetime.timedelta(hours=1), datetime.timedelta(hours=2))
        march = self._true_ny_transition(datetime.datetime(2026, 1, 1, tzinfo=UTC),
                                         datetime.datetime(2026, 4, 1, tzinfo=UTC))
        self._assert_offset_flips_exactly_at(zone, march)

    def test_crosses_rollover_changes_only_at_true_local_midnight_near_the_march_transition(self):
        """(b) of the adversarial ask: a minute-by-minute walk of `real_costs.crosses_rollover` across the
        2026-03-08 US transition must fire at every true server-local midnight in the window and NOWHERE
        else -- the old bug's one-hour-late, two-hour jump could plausibly have shifted, duplicated or
        dropped a midnight boundary near the transition; this catches any of those."""
        _, zone = RC.server_zone(PROVIDER)
        start = datetime.datetime(2026, 3, 7, 0, 0, tzinfo=UTC)
        end = datetime.datetime(2026, 3, 9, 0, 0, tzinfo=UTC)
        step = datetime.timedelta(minutes=1)

        # Ground truth: every minute boundary where the zone's own local DATE changes.
        t = start
        prev_date = t.astimezone(zone).date()
        true_boundaries = set()
        t += step
        while t <= end:
            d = t.astimezone(zone).date()
            if d != prev_date:
                true_boundaries.add(t)
            prev_date = d
            t += step

        self.assertEqual(len(true_boundaries), 2, f"expected exactly 2 midnights in a 2-day window, got "
                         f"{sorted(true_boundaries)}")

        t = start
        while t < end:
            nxt = t + step
            got = RC.crosses_rollover(t.isoformat().replace("+00:00", "Z"),
                                      nxt.isoformat().replace("+00:00", "Z"), PROVIDER)
            expected = nxt in true_boundaries
            self.assertEqual(got, expected, f"crosses_rollover({t.isoformat()}, {nxt.isoformat()}) = {got}, "
                             f"expected {expected}")
            t = nxt


class FlattenBeforeRollover(unittest.TestCase):
    """`walk(..., Tm=...)` with OPTS["flat_before_rollover"]/OPTS["rollover_provider"] set."""

    def setUp(self):
        self.bt = _bt()

    def tearDown(self):
        self.bt.reset_opts()

    def _series(self):
        # 15-minute bars, flat price, from 2024-01-01T21:00Z. FTMO server local midnight in this (winter,
        # std +02:00) window is 22:00Z -- so the bar closing 21:45Z is the last one closing before rollover,
        # and the bar at 22:00Z is the first one closing at/after it.
        times = [f"2024-01-01T21:{m:02d}:00Z" for m in (0, 15, 30, 45)] + \
                [f"2024-01-01T22:{m:02d}:00Z" for m in (0, 15, 30, 45)] + \
                [f"2024-01-01T23:{m:02d}:00Z" for m in (0, 15, 30, 45)]
        H = [100.0] * len(times)
        L = [100.0] * len(times)
        C = [100.0] * len(times)
        return H, L, C, times

    def test_flattens_at_the_last_bar_closing_before_rollover(self):
        H, L, C, Tm = self._series()
        self.bt.OPTS.update(flat_before_rollover=True, rollover_provider=PROVIDER)
        # entry=99, stop=90 (far away), target=200 (far away): price sits flat at 100 the whole series, so
        # neither stop nor target ever fires -- the ONLY way this returns is the flatten rule or the ordinary
        # end-of-horizon timeout, and the flatten rule must win because it is earlier.
        w = self.bt.walk("long", 99.0, 90.0, 200.0, H, L, C, 0, len(C), Tm=Tm)
        self.assertEqual(w["outcome"], "rollover_flat")
        self.assertEqual(Tm[w["exit"]], "2024-01-01T21:45:00Z")

    def test_a_fill_on_the_last_bar_before_rollover_is_flat_at_once_not_carried_across(self):
        """Fund-search finding (real history, B-RAID on): the walk starts at fill_bar + 1, so the boundary between the
        fill bar and the first walked bar was never asked. Fill bar = the 21:45 bar (last before rollover), first
        walked bar = 22:00 (after it)."""
        H, L, C, Tm = self._series()
        fill = Tm.index("2024-01-01T21:45:00Z")
        self.bt.OPTS.update(flat_before_rollover=True, rollover_provider=PROVIDER)
        w = self.bt.walk("long", 99.0, 90.0, 200.0, H, L, C, fill + 1, len(C), Tm=Tm)
        self.assertEqual(w["outcome"], "rollover_flat")
        self.assertEqual(w["exit"], fill)                          # flat at the fill bar's own close
        self.assertEqual(w["bars_held"], 0)

    def test_a_data_gap_spanning_rollover_right_after_the_fill_is_flat_too(self):
        H, L, C, Tm = self._series()
        # drop the 22:00-22:45 bars: 21:45 is followed directly by 23:00 (a hole across the rollover)
        keep = [i for i, t in enumerate(Tm) if not ("T22:" in t)]
        H, L, C, Tm = ([x[i] for i in keep] for x in (H, L, C, Tm))
        self.bt.OPTS.update(flat_before_rollover=True, rollover_provider=PROVIDER)
        fill = Tm.index("2024-01-01T21:45:00Z")
        w = self.bt.walk("long", 99.0, 90.0, 200.0, H, L, C, fill + 1, len(C), Tm=Tm)
        self.assertEqual((w["outcome"], w["exit"]), ("rollover_flat", fill))

    def test_no_new_flatten_without_the_flag_or_when_the_fill_is_not_at_the_boundary(self):
        H, L, C, Tm = self._series()
        fill = Tm.index("2024-01-01T21:45:00Z")
        self.bt.OPTS.update(flat_before_rollover=False, rollover_provider=PROVIDER)
        off = self.bt.walk("long", 99.0, 90.0, 200.0, H, L, C, fill + 1, len(C), Tm=Tm)
        self.assertEqual(off["outcome"], "timeout")                # v1: unchanged
        self.bt.OPTS.update(flat_before_rollover=True, rollover_provider=PROVIDER)
        early = self.bt.walk("long", 99.0, 90.0, 200.0, H, L, C, 1, len(C), Tm=Tm)
        self.assertEqual(Tm[early["exit"]], "2024-01-01T21:45:00Z")   # the existing rule, still the first flatten

    def test_never_flattens_at_or_after_the_bar_that_closes_at_rollover(self):
        H, L, C, Tm = self._series()
        self.bt.OPTS.update(flat_before_rollover=True, rollover_provider=PROVIDER)
        w = self.bt.walk("long", 99.0, 90.0, 200.0, H, L, C, 0, len(C), Tm=Tm)
        self.assertLess(Tm[w["exit"]], "2024-01-01T22:00:00Z")

    def test_the_flatten_bars_own_close_price_decides_R_not_a_later_bar(self):
        H, L, C, Tm = self._series()
        # A dramatic move on the bar AFTER the flatten point -- if the engine peeked ahead, R would reflect
        # this instead of the flat 100.0 close at the flatten bar (CLAUDE.md §8: no future information).
        idx = Tm.index("2024-01-01T22:00:00Z")
        C[idx] = 500.0; H[idx] = 500.0
        self.bt.OPTS.update(flat_before_rollover=True, rollover_provider=PROVIDER)
        entry = 99.0
        w = self.bt.walk("long", entry, 90.0, 200.0, H, L, C, 0, len(C), Tm=Tm)
        self.assertEqual(w["outcome"], "rollover_flat")
        expected_R = (100.0 - entry) / (entry - 90.0)
        self.assertAlmostEqual(w["R"], expected_R)

    def test_default_off_never_flattens(self):
        H, L, C, Tm = self._series()
        # OPTS left at baseline (reset_opts in setUp/tearDown is not enough on its own here -- this asserts
        # the DEFAULT, so no OPTS.update at all).
        self.bt.reset_opts()
        w = self.bt.walk("long", 99.0, 90.0, 200.0, H, L, C, 0, len(C), Tm=Tm)
        self.assertEqual(w["outcome"], "timeout")

    def test_passing_no_Tm_never_flattens_even_with_the_flag_on(self):
        # Every pre-A0 caller passes no Tm -- OPTS["flat_before_rollover"] being left True by some other
        # test/config must not matter without the timestamps to check against.
        H, L, C, _Tm = self._series()
        self.bt.OPTS.update(flat_before_rollover=True, rollover_provider=PROVIDER)
        w = self.bt.walk("long", 99.0, 90.0, 200.0, H, L, C, 0, len(C))
        self.assertEqual(w["outcome"], "timeout")


class DefaultCostProfileIsByteIdenticalToPreA0(unittest.TestCase):
    """`simulate(..., cost_profile=None)` (the default) must compute `fee_R` with the EXACT pre-A0 formula."""

    def setUp(self):
        self.bt = _bt()

    def tearDown(self):
        self.bt.reset_opts()

    def _one_trade(self):
        return [{"symbol": "BTCUSDT", "side": "long", "entry": 100.0, "stop": 99.0, "target": 103.0,
                 "entry_time": "2024-01-01T00:00:00Z", "exit_time": "2024-01-01T01:00:00Z",
                 "R": 3.0, "R_planned": 3.0, "event": "e1"}]

    def test_no_entry_order_type_no_cost_profile_matches_the_flat_formula(self):
        fee = 0.05 / 100
        eq, curve, taken = self.bt.simulate(self._one_trade(), fee)
        dist = abs(100.0 - 99.0) / 100.0
        expected_fee_R = 2 * fee / dist
        self.assertEqual(len(taken), 1)
        self.assertAlmostEqual(taken[0]["net_R"], 3.0 - expected_fee_R, places=9)

    def test_cost_profile_none_is_the_same_as_omitting_the_keyword_entirely(self):
        fee = 0.05 / 100
        eq1, _, taken1 = self.bt.simulate(self._one_trade(), fee)
        eq2, _, taken2 = self.bt.simulate(self._one_trade(), fee, cost_profile=None)
        self.assertEqual(eq1, eq2)
        self.assertAlmostEqual(taken1[0]["net_R"], taken2[0]["net_R"], places=12)

    def test_cost_profile_set_changes_the_result(self):
        # Sanity check that the new path is actually reachable and does something different from the flat
        # formula -- XAUUSD is declared under the ftmo profile; BTCUSDT (crypto) is not, so this uses XAUUSD.
        fee = 0.05 / 100
        trades = [{"symbol": "XAUUSD", "side": "long", "entry": 2000.0, "stop": 1990.0, "target": 2030.0,
                   "entry_time": "2024-01-01T10:00:00Z", "exit_time": "2024-01-01T12:00:00Z",
                   "R": 3.0, "R_planned": 3.0, "event": "e1"}]
        eq_flat, _, taken_flat = self.bt.simulate([dict(t) for t in trades], fee)
        eq_real, _, taken_real = self.bt.simulate([dict(t) for t in trades], fee, cost_profile=FTMO)
        self.assertNotAlmostEqual(taken_flat[0]["net_R"], taken_real[0]["net_R"], places=6)

    def test_cost_profile_refuses_for_a_symbol_it_has_no_export_for(self):
        fee = 0.05 / 100
        trades = [{"symbol": "BTCUSDT", "side": "long", "entry": 100.0, "stop": 99.0, "target": 103.0,
                   "entry_time": "2024-01-01T00:00:00Z", "exit_time": "2024-01-01T01:00:00Z",
                   "R": 3.0, "R_planned": 3.0, "event": "e1"}]
        with self.assertRaises(RC.CostRefused):
            self.bt.simulate(trades, fee, cost_profile=FTMO)


REL = "ftmo_demo_2026_09_relspread"


class RelativeSpreadProfile(unittest.TestCase):
    """C2 (red-team 2026-10-02): the recorded spreads are absolute price units from 2022-07..2026-09; the relative
    profile scales them by entry / price_ref (median M15 close over EXACTLY the recording window). The absolute profile
    stays byte-identical. Every number here is a COST, never an outcome."""

    # XAUUSD's spec window in server time is 2022.07.06 08:00 .. 2026.09.28 18:15; the FTMO server is UTC+3 on both dates
    # (US DST dates fixed offset: summer), so the UTC bar-open labels are 05:00 and 15:15.
    WIN = ("2022-07-06T05:00:00Z", "2026-09-28T15:15:00Z")

    def test_the_window_is_the_specs_recording_window_in_utc(self):
        self.assertEqual(RC.price_ref_window(REL, "XAUUSD"), self.WIN)

    def test_price_ref_equals_the_median_close_over_exactly_that_window_and_is_reproducible(self):
        import gzip
        import json
        import statistics
        d = os.path.join(ROOT, "data", "history", "ftmo", "ohlcv.XAUUSD.15m")
        closes = []
        for y in range(2022, 2027):
            with gzip.open(os.path.join(d, f"{y}.json.gz"), "rt", encoding="utf-8") as fh:
                closes += [c["close"] for c in json.load(fh)["candles"] if self.WIN[0] <= c["time"] <= self.WIN[1]]
        # the window holds exactly the 100,000 M15 bars the spec says it recorded
        self.assertEqual(len(closes), RC.spec(REL, "XAUUSD")["recorded_spread_m15"]["bars"])
        want = statistics.median(closes)
        self.assertEqual(RC.price_ref(REL, "XAUUSD"), want)
        RC._price_ref_cached.cache_clear()
        self.assertEqual(RC.price_ref(REL, "XAUUSD"), want)                 # deterministic across a cold cache
        self.assertEqual(RC.price_ref_info(REL, "XAUUSD")["n_bars"], len(closes))

    def test_window_bounds_are_inclusive_and_bars_outside_are_excluded(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            rows = [("2022-07-06T04:45:00Z", 1.0), (self.WIN[0], 10.0), ("2024-01-01T00:00:00Z", 20.0),
                    (self.WIN[1], 30.0), ("2026-09-28T15:30:00Z", 1000.0)]
            doc = {"symbol": "XAUUSD", "timeframe": "15m",
                   "candles": [{"time": t, "open": c, "high": c, "low": c, "close": c, "volume": 1.0} for t, c in rows]}
            with open(os.path.join(tmp, "ohlcv.XAUUSD.15m.json"), "w", encoding="utf-8") as fh:
                json.dump(doc, fh)
            prof = dict(RC.PROFILES[REL], price_ref_history_dir=tmp)
            with unittest.mock.patch.dict(RC.PROFILES, {"rel_tmp": prof}):
                info = RC.price_ref_info("rel_tmp", "XAUUSD")
        self.assertEqual((info["price_ref"], info["n_bars"]), (20.0, 3))
        self.assertEqual((info["first_bar"], info["last_bar"]), self.WIN)

    def test_missing_history_refuses_rather_than_guessing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            with unittest.mock.patch.dict(RC.PROFILES, {"rel_tmp": dict(RC.PROFILES[REL], price_ref_history_dir=tmp)}):
                with self.assertRaises(RC.CostRefused):
                    RC.price_ref("rel_tmp", "XAUUSD")

    def test_an_absolute_profile_has_no_price_ref(self):
        with self.assertRaises(RC.CostRefused):
            RC.price_ref(FTMO, "XAUUSD")
        self.assertEqual(RC.spread_scaling(FTMO), "absolute")
        self.assertEqual(RC.spread_scaling(REL), "relative_price_ref")

    def test_at_the_recording_window_price_level_relative_equals_absolute(self):
        for sym in ("XAUUSD", "US500", "XAGUSD"):
            pr = RC.price_ref(REL, sym)
            for stat in ("median", "p90"):
                a = RC.cost_r(pr, pr * 0.999, "2023-03-07T09:00:00Z", "2023-03-07T13:00:00Z", sym, "long", FTMO, spread_stat=stat)
                r = RC.cost_r(pr, pr * 0.999, "2023-03-07T09:00:00Z", "2023-03-07T13:00:00Z", sym, "long", REL, spread_stat=stat)
                self.assertAlmostEqual(r["spread_R"], a["spread_R"], places=10, msg=(sym, stat))
                self.assertAlmostEqual(r["spread_scale"], 1.0, places=12)
                self.assertEqual(r["swap_R"], a["swap_R"])                      # swap is not rescaled

    def test_a_2012_like_price_level_gets_a_proportionally_smaller_spread(self):
        pr = RC.price_ref(REL, "XAUUSD")
        t_in, t_out = "2012-03-07T09:00:00Z", "2012-03-07T13:00:00Z"
        base = RC.cost_r(pr, pr - 5.0, t_in, t_out, "XAUUSD", "long", REL)["spread_R"]
        early = RC.cost_r(pr / 2.5, pr / 2.5 - 5.0, t_in, t_out, "XAUUSD", "long", REL)["spread_R"]
        self.assertAlmostEqual(early, base / 2.5, places=10)       # same $5 stop, price 2.5x lower -> spread 2.5x smaller
        # the same PERCENT stop: relative spread_R is price-level invariant, the absolute one is overstated 2.5x
        e_abs = RC.cost_r(pr / 2.5, pr / 2.5 * 0.998, t_in, t_out, "XAUUSD", "long", FTMO)["spread_R"]
        e_rel = RC.cost_r(pr / 2.5, pr / 2.5 * 0.998, t_in, t_out, "XAUUSD", "long", REL)["spread_R"]
        l_rel = RC.cost_r(pr, pr * 0.998, t_in, t_out, "XAUUSD", "long", REL)["spread_R"]
        self.assertAlmostEqual(e_rel, l_rel, places=10)
        self.assertGreater(e_abs / e_rel, 2.4)

    def test_absolute_profile_is_byte_identical_to_the_pre_c2_formula(self):
        r = RC.cost_r(2000.0, 1995.0, "2023-03-07T09:00:00Z", "2023-03-09T21:00:00Z", "XAUUSD", "long", FTMO)
        self.assertNotIn("spread_scale", r)
        spread_entry, _ = RC.spread_price(FTMO, "XAUUSD", 9)
        spread_exit, _ = RC.spread_price(FTMO, "XAUUSD", 21)
        self.assertEqual(r["spread_R"], ((spread_entry / 2 + spread_exit / 2) / 2000.0) / (abs(2000.0 - 1995.0) / 2000.0))

    def test_snapshot_pins_price_ref_values_and_provenance_only_for_the_relative_profile(self):
        snap = RC.profile_snapshot(REL, ["XAUUSD", "US500"])
        self.assertEqual(snap["spread_scaling"], "relative_price_ref")
        self.assertEqual(snap["price_ref"], {"US500": RC.price_ref(REL, "US500"), "XAUUSD": RC.price_ref(REL, "XAUUSD")})
        self.assertEqual(len(snap["price_ref_provenance_sha256"]), 64)
        self.assertEqual(snap, RC.profile_snapshot(REL, ["US500", "XAUUSD"]))      # order-independent
        absolute = RC.profile_snapshot(FTMO, ["XAUUSD"])
        self.assertNotIn("price_ref", absolute)
        self.assertEqual(set(absolute), {"profile", "server", "provider", "source_files_sha256"})

    def test_mean_spread_r_helper_prices_only_valid_trades(self):
        pr = RC.price_ref(REL, "XAUUSD")
        mk = lambda e, st: {"symbol": "XAUUSD", "side": "long", "entry": e, "stop": st,
                            "entry_time": "2023-03-07T09:00:00Z", "exit_time": "2023-03-07T13:00:00Z"}
        trades = [mk(pr, pr - 5.0), mk(pr, pr - 10.0), mk(pr, pr)]                  # the last has no stop distance
        out = RC.mean_spread_r(trades, REL)
        a = RC.cost_r(pr, pr - 5.0, "2023-03-07T09:00:00Z", "2023-03-07T13:00:00Z", "XAUUSD", "long", REL)["spread_R"]
        b = RC.cost_r(pr, pr - 10.0, "2023-03-07T09:00:00Z", "2023-03-07T13:00:00Z", "XAUUSD", "long", REL)["spread_R"]
        self.assertEqual(out["n"], 2)
        self.assertAlmostEqual(out["mean_spread_R"], (a + b) / 2, places=12)
        self.assertEqual(RC.mean_spread_r([], REL), {"n": 0, "mean_spread_R": None})


class RolloverOptionSeparatesScanCacheEntries(unittest.TestCase):
    """flat_before_rollover changes trades inside scan()/walk(), so two scans that differ only in it must never
    share a scan-cache key (scripts/stability-report.py _SCAN_RELEVANT_KEYS)."""

    def test_keys_differ_and_default_matches_an_overlay_without_the_option(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("sr_rc", os.path.join(ROOT, "scripts", "stability-report.py"))
        sr = importlib.util.module_from_spec(spec); spec.loader.exec_module(sr)
        ov = sr.config_opts(sr.CONFIGS["A"], ict_target="range")
        k_default = sr._scan_cache_key("XAUUSD", "15m", ov, ("ict",))
        k_off = sr._scan_cache_key("XAUUSD", "15m", dict(ov, flat_before_rollover=False, rollover_provider=None), ("ict",))
        k_on = sr._scan_cache_key("XAUUSD", "15m", dict(ov, flat_before_rollover=True, rollover_provider="mt5_bridge_ftmo"), ("ict",))
        self.assertEqual(k_default, k_off)
        self.assertNotEqual(k_off, k_on)


if __name__ == "__main__":
    unittest.main()
