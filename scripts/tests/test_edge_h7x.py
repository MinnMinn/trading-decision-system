"""scripts/research/edge_h7x.py on HAND-BUILT bars only (no real history, no outcome on market data).
Pre-registration: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_edge_h7x
"""
import ast
import contextlib
import datetime
import gzip
import io
import importlib.util
import json
import math
import os
import random
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "tests"))
spec = importlib.util.spec_from_file_location("edge_h7x", os.path.join(ROOT, "scripts", "research", "edge_h7x.py"))
H = importlib.util.module_from_spec(spec)
spec.loader.exec_module(H)
import instruments as I  # noqa: E402
import test_detector_leakage_probe as PROBE  # noqa: E402  (its walk/check only; its TestCase is not collected here)

EC, F3, F4 = H.EC, H.F3, H.F4
UTC = datetime.timezone.utc
DAY = datetime.timedelta(days=1)
PREREG = "docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md"
START = datetime.date(2021, 5, 1)                       # a DISCOVERY date (a Saturday: the market is 7-day)
D22 = START + datetime.timedelta(days=22)               # the first day with 21 complete days AND a non-zero MOM20


def candles(days, start=START):
    """days: [{slot: (o, h, l, c)}, ...] on consecutive UTC dates; a missing slot is a missing bar.
    [prereg: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    out = []
    for k, bars in enumerate(days):
        d = start + datetime.timedelta(days=k)
        t0 = datetime.datetime(d.year, d.month, d.day, tzinfo=UTC)
        for sl in sorted(bars):
            o, h, l, c = bars[sl]
            out.append({"time": (t0 + sl * H.BAR).strftime("%Y-%m-%dT%H:%M:%SZ"), "open": o, "high": h, "low": l, "close": c})
    return out


def day(px, drop=(), at=None):
    """288 bars zig-zagging +/- 0.05 around px, high px + 0.25, low px - 0.25 (range 0.5; last close px + 0.05; first open
    px + 0.05); `drop` = missing slots, `at` = {slot: (o, h, l, c)} overrides.
    [prereg: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    bars = {}
    for sl in range(288):
        if sl in drop:
            continue
        z = 0.05 if sl % 2 else -0.05
        bars[sl] = (px - z, px + 0.25, px - 0.25, px + z)
    bars.update(at or {})
    return bars


def trend(last=101.0, d22=None, more=(), start=START):
    """Days 0..20 at 100, day 21 at `last` (so MOM20 on day 22 has the sign of last - 100), day 22 = `d22`, then `more`.
    [prereg: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    return H.series("BTCUSDT", candles([day(100.0)] * 21 + [day(last)] + [d22 or day(last)] + list(more), start=start))


def idx(s, d, sl):
    return next(i for i in s.day_rows[d] if H.slot(s, i) == sl)


def walk(seed=11, days=60, start=datetime.date(2021, 6, 1), holes=None):
    """24/7 random walk with a few missing bars and outages (days 5, 9, 17, 33 incomplete; day 33 loses its close).
    [prereg: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    holes = {5: {17}, 9: set(range(100, 130)), 17: {200, 201}, 33: set(range(250, 288))} if holes is None else holes
    rng = random.Random(seed)
    out, p = [], 30000.0
    t0 = datetime.datetime(start.year, start.month, start.day, tzinfo=UTC)
    for k in range(days * 288):
        o = p
        p = o * (1 + rng.gauss(0, 0.002))
        dd, sl = divmod(k, 288)
        if sl in holes.get(dd, ()):
            continue
        w = abs(rng.gauss(0, 0.0005)) * o
        out.append({"time": (t0 + k * H.BAR).strftime("%Y-%m-%dT%H:%M:%SZ"), "open": o, "high": max(o, p) + w,
                    "low": min(o, p) - w, "close": p})
    return out


def stamps(start, days, rate=0.0, hours=(0, 8, 16), at=None, iv=8):
    """Hand-built funding settlements [(time, rate, interval_hours)] at `hours` UTC on `days` dates from `start`; `at` =
    {datetime: rate} overrides.
    [prereg amendment [H7x-A1]: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    out = []
    for k in range(days):
        d = start + datetime.timedelta(days=k)
        for h in hours:
            t = datetime.datetime(d.year, d.month, d.day, h, tzinfo=UTC)
            out.append((t, (at or {}).get(t, rate), iv))
    return out


def funding_for(s, rate=0.0, at=None):
    """An 8-hourly funding table covering series `s` (one day either side).
    [prereg amendment [H7x-A1]: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    return H.Funding(stamps(s.sday[0] - DAY, (s.sday[-1] - s.sday[0]).days + 3, rate, at=at))


def at(d, h, m=0):
    return datetime.datetime(d.year, d.month, d.day, h, m, tzinfo=UTC)


def ev_key(e):
    return (e["rule"], e["i"], e["side"], e["entry_i"], e["slot"])


class Registration(unittest.TestCase):
    def test_parameters_are_golds_and_costs_are_preregistered(self):
        self.assertEqual((H.MOM_DAYS, F3.MOM_DAYS, H.VOL_DAYS), (20, 20, 20))
        self.assertEqual((H.VB_K, F4.VB_K), (0.5, 0.5))
        self.assertAlmostEqual(H.COST_RT, 0.0012)
        self.assertAlmostEqual(H.COST_STRESS, 0.0014)
        self.assertEqual((H.BARS_PER_DAY, H.EXIT_SLOT), (288, 287))
        self.assertEqual(H.PERIODS, {"discovery": ("2017-08-17", "2021-07-18"), "confirmation": ("2021-07-19", "2024-02-29"),
                                     "exposed": ("2024-03-01", "2026-09-30")})
        self.assertEqual(H.TESTS, (("T1", "H7x"), ("T2", "G9x")))
        self.assertEqual((H.FDR_Q, H.CONFIRM_P, H.EXPOSED_P), (0.10, 0.05, 0.10))
        self.assertEqual(H.BOOK_V3, ("H7_XAUUSD_eod", "G9_XAUUSD_eod"))
        self.assertEqual(H.SWITCH_DAY, datetime.date(2020, 1, 1))
        self.assertIn("entry_time <= tau < exit_time", H._meta("dry-run")["costs"]["funding"])

    def test_symbols_come_from_instruments_never_a_literal(self):
        self.assertEqual(H.symbols(), I.backtested("crypto"))
        src = open(os.path.join(ROOT, "scripts", "research", "edge_h7x.py")).read()
        for sym in I.backtested("crypto"):
            self.assertNotIn(sym, src)

    def test_every_docstring_cites_the_preregistration(self):
        for rel in ("scripts/research/edge_h7x.py", "scripts/tests/test_edge_h7x.py"):
            tree = ast.parse(open(os.path.join(ROOT, rel)).read())
            for n in ast.walk(tree):
                if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)):
                    doc = ast.get_docstring(n)
                    if doc is not None:
                        self.assertIn(PREREG, doc, f"{rel}: {getattr(n, 'name', '<module>')}")

    def test_period_boundaries(self):
        D = datetime.date
        self.assertIsNone(H.day_period(D(2017, 8, 16)))
        self.assertEqual(H.day_period(D(2017, 8, 17)), "discovery")
        self.assertEqual(H.day_period(D(2021, 7, 18)), "discovery")
        self.assertEqual(H.day_period(D(2021, 7, 19)), "confirmation")
        self.assertEqual(H.day_period(D(2024, 2, 29)), "confirmation")
        self.assertEqual(H.day_period(D(2024, 3, 1)), "exposed")
        self.assertEqual(H.day_period(D(2026, 9, 30)), "exposed")
        self.assertIsNone(H.day_period(D(2026, 10, 1)))


class Data(unittest.TestCase):
    def _c(self, t, o):
        return {"time": t, "open": o, "high": o, "low": o, "close": o, "volume": 1.0}

    def test_spot_before_2020_perp_from_2020_deduplicated(self):
        spot = [self._c("2019-12-31T23:50:00Z", 1), self._c("2019-12-31T23:55:00Z", 2), self._c("2020-01-01T00:00:00Z", 3)]
        perp = [self._c("2019-12-31T23:55:00Z", 20), self._c("2020-01-01T00:00:00Z", 30), self._c("2020-01-01T00:05:00Z", 40),
                self._c("2020-01-01T00:05:00Z", 41)]
        out, dup = H.merge_candles(spot, perp)
        self.assertEqual([(c["time"][11:16], c["open"]) for c in out],
                         [("23:50", 1), ("23:55", 2), ("00:00", 30), ("00:05", 40)])
        self.assertEqual(dup, 1)
        self.assertEqual(set(out[0]), {"time", "open", "high", "low", "close"})

    def test_load_reads_both_roots_and_records_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            for root, rows in (("spot", [self._c("2019-12-31T23:55:00Z", 2)]), ("perp", [self._c("2020-01-01T00:00:00Z", 3)])):
                os.makedirs(os.path.join(tmp, root))
                json.dump({"symbol": "X", "timeframe": "5m", "_source": root, "candles": rows},
                          open(os.path.join(tmp, root, "ohlcv.X.5m.json"), "w"))
            c, prov = H.load_candles("X", spot_root=os.path.join(tmp, "spot"), perp_root=os.path.join(tmp, "perp"))
        self.assertEqual([x["open"] for x in c], [2, 3])
        self.assertEqual((prov["spot"]["bars_used"], prov["perp"]["bars_used"], prov["bars"]), (1, 1, 2))
        self.assertEqual(len(prov["perp"]["sha256"]), 64)

    def test_load_funding_sorts_deduplicates_and_records_provenance_without_rates(self):
        rows = [{"time": "2020-01-01T08:00:00Z", "interval_hours": 8, "rate": 2e-4},
                {"time": "2020-01-01T00:00:00Z", "interval_hours": 8, "rate": 1e-4},
                {"time": "2020-01-01T08:00:00Z", "interval_hours": 8, "rate": 9e-4},
                {"time": "2020-01-01T10:00:00Z", "interval_hours": 2, "rate": 3e-4}]
        with tempfile.TemporaryDirectory() as tmp:
            with gzip.open(os.path.join(tmp, "funding.X.json.gz"), "wt") as fh:
                json.dump({"symbol": "X", "_source": "test", "rows": rows}, fh)
            f, prov = H.load_funding("X", root=tmp)
            empty, eprov = H.load_funding("Y", root=tmp)
        self.assertEqual([t.hour for t in f.t], [0, 8, 10])
        self.assertEqual(f.rate, [1e-4, 2e-4, 3e-4])                      # the first 08:00 row is kept
        self.assertEqual((prov["rows"], prov["duplicates_dropped"], prov["gaps"], len(prov["sha256"])), (4, 1, 0, 64))
        self.assertFalse({"rate", "rates"} & set(prov))
        self.assertEqual((empty.t, eprov["rows"], eprov["sha256"]), ([], 0, None))

    def test_server_day_ending_a_utc_day_carries_its_date(self):
        zone = H.RC.server_zone(EC.PROVIDER)[1]
        for d in (datetime.date(2024, 1, 15), datetime.date(2024, 7, 15)):
            self.assertEqual(H.server_day_ending(d), d.isoformat())
            boundary = 22 if d.month == 1 else 21                        # 17:00 New York in UTC (EST / EDT)
            after = datetime.datetime(d.year, d.month, d.day, boundary, 0, tzinfo=UTC).astimezone(zone).date()
            self.assertEqual(after, d + datetime.timedelta(days=1))       # the next server day starts that evening


class Context(unittest.TestCase):
    def test_eligibility_needs_a_complete_previous_day_and_21_complete_days(self):
        s = trend()
        ctx = H.day_context(s)
        self.assertNotIn(START + datetime.timedelta(days=20), ctx)        # only 20 complete days before it
        self.assertIn(START + datetime.timedelta(days=21), ctx)
        self.assertIn(D22, ctx)
        self.assertEqual(ctx[START + datetime.timedelta(days=21)]["mom_sign"], 0)
        self.assertEqual(ctx[D22]["mom_sign"], 1)
        self.assertEqual((ctx[D22]["prev_high"], ctx[D22]["prev_low"]), (101.25, 100.75))
        self.assertAlmostEqual(ctx[D22]["open"], 101.05)
        self.assertAlmostEqual(ctx[D22]["mom"], 101.05 / 100.05 - 1)
        self.assertEqual(ctx[D22]["lookback_from"], START + datetime.timedelta(days=1))

    def test_mom20_counts_complete_days_skipping_incomplete_ones(self):
        px = [100.0 + k for k in range(23)]
        full = H.day_context(H.series("BTCUSDT", candles([day(p) for p in px])))
        holed = H.day_context(H.series("BTCUSDT", candles([day(p, drop={10} if k == 5 else ()) for k, p in enumerate(px)])))
        self.assertAlmostEqual(full[D22]["mom"], (px[21] + 0.05) / (px[1] + 0.05) - 1)
        self.assertAlmostEqual(holed[D22]["mom"], (px[21] + 0.05) / (px[0] + 0.05) - 1)   # day 5 skipped: 21st = day 0
        self.assertNotIn(START + datetime.timedelta(days=21), holed)                     # 20 complete days only

    def test_a_days_own_bars_never_decide_its_eligibility(self):
        full = trend(more=[day(101.0)])
        cut = trend(d22=day(101.0, drop=set(range(200, 288))), more=[day(101.0)])
        a, b = H.day_context(full), H.day_context(cut)
        self.assertEqual(a[D22], b[D22])                                  # D's missing afternoon changes nothing about D
        self.assertNotIn(D22 + datetime.timedelta(days=1), b)             # but the NEXT day has an incomplete D-1

    def test_sigma_is_the_rms_of_the_previous_20_complete_days(self):
        px = [100.0 + 0.5 * k for k in range(23)]
        s = H.series("BTCUSDT", candles([day(p) for p in px]))
        ms = []
        for p in px[2:22]:
            r = math.log((p + 0.05) / (p - 0.05))
            ms.append(r * r)                                              # every within-day 5m return is +/- r
        self.assertAlmostEqual(H.day_context(s)[D22]["sigma"], math.sqrt(sum(ms) / 20), places=12)

    def test_a_day_with_an_off_grid_bar_is_not_complete(self):
        bars = candles([day(100.0)] * 21 + [day(101.0)] * 3)
        k = next(j for j, b in enumerate(bars) if b["time"] == f"{D22.isoformat()}T04:10:00Z")
        bars[k] = dict(bars[k], time=f"{D22.isoformat()}T04:10:14Z")       # 288 bars, one shifted by 14 s
        s = H.series("BTCUSDT", bars)
        self.assertEqual(len(s.day_rows[D22]), 288)
        self.assertNotIn(D22, H._complete_days(s))
        ctx = H.day_context(s)
        self.assertIn(D22, ctx)                                           # D's own bars never decide D
        self.assertNotIn(D22 + DAY, ctx)                                  # but D+1 has an incomplete D-1
        c = H.dry_counts(s)["periods"]["discovery"]
        self.assertEqual((c["off_grid_bars"], c["off_grid_bars_in_eligible_days"], c["incomplete_days"]), (1, 1, 1))

    def test_a_duplicated_slot_is_not_complete(self):
        bars = candles([day(100.0)] * 21 + [day(101.0)] * 2)
        k = next(j for j, b in enumerate(bars) if b["time"] == f"{(D22 - DAY).isoformat()}T04:10:00Z")
        bars[k] = dict(bars[k], time=f"{(D22 - DAY).isoformat()}T04:05:00Z")   # 288 rows, 287 distinct slots
        self.assertNotIn(D22, H.day_context(H.series("BTCUSDT", bars)))

    def test_the_venue_switch_day_is_not_eligible(self):
        """Spot through 2019-12-31 + perp from 2020-01-01: no event on 2020-01-01 (its previous high / low are spot), the
        next day is eligible and counted as a mixed-venue lookback.
        [prereg amendment [H7x-A1]: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
        start = H.SWITCH_DAY - datetime.timedelta(days=22)
        big = (101.0, 101.9, 100.9, 101.8)                                # above the switch day's own high (101.6)
        days = [day(100.0)] * 21 + [day(101.0)] + [day(101.0, at={100: Rules.BREAK_UP})] + [day(101.0, at={100: big})]
        bars = candles(days, start=start)
        spot = [b for b in bars if b["time"] < H.PERP_FROM] + [dict(b, open=999.0) for b in bars if b["time"] >= H.PERP_FROM]
        perp = [b for b in bars if b["time"] >= H.PERP_FROM]
        merged, dup = H.merge_candles(spot, perp)
        self.assertEqual((merged, dup), (bars, 0))                        # spot bars on/after the switch are never used
        s = H.series("BTCUSDT", merged)
        ctx, excluded = H._context(s)
        self.assertEqual(excluded, {H.SWITCH_DAY: "venue_switch_day"})
        self.assertNotIn(H.SWITCH_DAY, ctx)
        evs = H.events(s, ctx)
        self.assertEqual([e["day"] for r in H.RULES for e in evs[r]], [H.SWITCH_DAY + DAY] * 2)
        c = H.dry_counts(s)["periods"]["discovery"]
        self.assertEqual((c["venue_switch_day"], c["venue_mixed_lookback_days"]), (1, 1))
        later = trend(d22=day(101.0, at={100: Rules.BREAK_UP}), start=start + DAY)       # the same day pattern, one day on
        self.assertEqual(len(H.ev_h7x(later)), 1)


class Rules(unittest.TestCase):
    BREAK_UP = (101.0, 101.6, 100.9, 101.5)

    def test_h7x_long_on_the_first_close_above_the_previous_high_with_up_momentum(self):
        s = trend(d22=day(101.0, at={100: self.BREAK_UP, 150: self.BREAK_UP}))
        evs = H.ev_h7x(s)
        self.assertEqual(len(evs), 1)
        e = evs[0]
        self.assertEqual((e["day"], e["side"], e["i"], e["entry_i"], e["slot"]),
                         (D22, 1, idx(s, D22, 100), idx(s, D22, 101), 101))

    def test_h7x_ignores_a_break_against_momentum_g9x_takes_either_side(self):
        s = trend(d22=day(101.0, at={100: (101.0, 101.0, 100.4, 100.5)}))
        self.assertEqual(H.ev_h7x(s), [])
        g = H.ev_g9x(s)
        self.assertEqual([(e["side"], e["slot"]) for e in g], [(-1, 101)])   # 100.5 < open 101.05 - 0.5 x 0.5

    def test_h7x_short_with_down_momentum(self):
        s = trend(last=99.0, d22=day(99.0, at={100: (99.0, 99.1, 98.4, 98.5)}))
        self.assertEqual([(e["side"], e["slot"]) for e in H.ev_h7x(s)], [(-1, 101)])

    def test_no_h7x_on_a_zero_momentum_day(self):
        s = trend(last=100.0, d22=day(100.0, at={100: (100.0, 100.6, 99.9, 100.5)}))
        self.assertEqual(H.ev_h7x(s), [])

    def test_g9x_threshold_is_open_plus_minus_half_the_previous_range(self):
        s = trend(d22=day(101.0, at={60: (101.0, 101.3, 101.0, 101.29), 61: (101.0, 101.4, 101.0, 101.31)}))
        self.assertEqual([(e["side"], e["i"]) for e in H.ev_g9x(s)], [(1, idx(s, D22, 61))])   # 101.05 + 0.25 = 101.30

    def test_an_entry_at_or_after_2355_is_not_an_event(self):
        for sl, want in ((286, []), (285, [286])):
            s = trend(d22=day(101.0, at={sl: self.BREAK_UP}))
            for det in (H.ev_h7x, H.ev_g9x):
                self.assertEqual([e["slot"] for e in det(s)], want, (sl, det.__name__))

    def test_the_entry_is_the_next_available_bar_of_the_day(self):
        s = trend(d22=day(101.0, drop={101, 102, 103}, at={100: self.BREAK_UP}))
        self.assertEqual([e["slot"] for e in H.ev_h7x(s)], [104])
        s = trend(d22=day(101.0, drop=set(range(281, 287)), at={280: self.BREAK_UP}))
        self.assertEqual(H.ev_h7x(s), [])                                 # the next bar opens at 23:55

    def test_missing_bars_after_the_signal_exit_at_the_last_available_open(self):
        for drop, last in ((set(), 287), ({287}, 286), (set(range(200, 288)), 199)):
            s = trend(d22=day(101.0, drop=drop, at={100: self.BREAK_UP}))
            e = H.ev_h7x(s)[0]
            self.assertEqual(H.slot(s, H.exit_index(s, e)), last)
        s = trend(d22=day(101.0, drop=set(range(102, 288)), at={100: self.BREAK_UP}))
        e = H.ev_h7x(s)[0]                                                # entry bar = the day's last available bar
        self.assertIsNone(H.exit_index(s, e))
        self.assertEqual(H.outcome(s, e, 0.001, funding_for(s)), (None, "no_exit_bar"))

    def test_an_exit_before_2355_is_counted_and_flagged(self):
        s = trend(d22=day(101.0, drop={287}, at={100: self.BREAK_UP}))
        c = H.dry_counts(s, funding_for(s))["periods"]["discovery"]
        self.assertEqual(c["exit_not_2355"], {"H7x": 1, "G9x": 1})
        self.assertEqual(c["placebo_days_last_bar_not_2355"], 1)
        _, skipped = H.symbol_rows(s, "discovery", funding=funding_for(s))
        self.assertEqual((skipped["H7x|flag:exit_not_2355"], skipped["G9x|flag:exit_not_2355"]), (1, 1))
        ok = trend(d22=day(101.0, at={100: self.BREAK_UP}))
        c = H.dry_counts(ok, funding_for(ok))["periods"]["discovery"]
        self.assertEqual((c["exit_not_2355"], c["placebo_days_last_bar_not_2355"]), ({"H7x": 0, "G9x": 0}, 0))


class Funding(unittest.TestCase):
    """Realized funding on perp-era trades: side x rate for every settlement entry_time <= tau < exit_time.
    [prereg amendment [H7x-A1]: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    RATES = {at(D22, 0): 5e-4, at(D22, 8): 1e-4, at(D22, 16): 2e-4, at(D22 + DAY, 0): 7e-4}

    def _trade(self, signal_slot, table=None, start=START):
        s = trend(d22=day(101.0, at={signal_slot: Rules.BREAK_UP}), start=start)
        e = H.ev_h7x(s)[0]
        f = funding_for(s, at=self.RATES) if table is None else table
        return s, e, f

    def test_a_long_from_0300_pays_0800_and_1600_never_the_next_midnight(self):
        s, e, f = self._trade(35)                                         # entry 03:00
        self.assertEqual(s.T[e["entry_i"]][11:16], "03:00")
        o, why = H.outcome(s, e, 0.001, f)
        self.assertIsNone(why)
        self.assertAlmostEqual(o["funding"], 3e-4)
        self.assertEqual(o["funding_stamps"], 2)
        self.assertAlmostEqual(o["cost"], H.COST_RT + 3e-4)
        self.assertAlmostEqual(o["cost90"], H.COST_STRESS + 3e-4)
        short, _ = H.outcome(s, dict(e, side=-1), 0.001, f)
        self.assertAlmostEqual(short["funding"], -3e-4)                    # a short RECEIVES a positive rate
        self.assertAlmostEqual(short["cost"], H.COST_RT - 3e-4)

    def test_settlement_boundaries(self):
        for signal, entry, paid, n in ((95, "08:00", 3e-4, 2), (96, "08:05", 2e-4, 1), (192, "16:05", 0.0, 0)):
            s, e, f = self._trade(signal)
            o, _ = H.outcome(s, e, 0.001, f)
            self.assertEqual(s.T[e["entry_i"]][11:16], entry)
            self.assertAlmostEqual(o["funding"], paid, msg=entry)
            self.assertEqual(o["funding_stamps"], n, entry)

    def test_a_spot_era_trade_pays_no_funding(self):
        s, e, _ = self._trade(35, start=datetime.date(2019, 6, 1))
        self.assertLess(s.T[e["entry_i"]], H.PERP_FROM)
        for table in (None, funding_for(s, rate=1e-3)):
            o, why = H.outcome(s, e, 0.001, table)
            self.assertIsNone(why)
            self.assertEqual((o["funding"], o["funding_stamps"], o["cost"], o["cost90"]), (0.0, 0, H.COST_RT, H.COST_STRESS))

    def test_a_two_hour_interval_day_charges_every_settlement_in_the_window(self):
        s = trend(d22=day(101.0, at={35: Rules.BREAK_UP}))
        rows = stamps(START - DAY, 23, 0.0) + stamps(D22, 1, 1e-5, hours=range(0, 24, 2), iv=2) + stamps(D22 + DAY, 2, 0.0)
        f = H.Funding(rows)
        self.assertEqual(f.gaps, [])
        o, _ = H.outcome(s, H.ev_h7x(s)[0], 0.001, f)
        self.assertEqual(o["funding_stamps"], 10)                          # 04:00, 06:00, ..., 22:00
        self.assertAlmostEqual(o["funding"], 1e-4)

    def test_a_window_without_funding_coverage_is_never_charged_zero(self):
        s, e, f = self._trade(35)
        short = H.Funding([x for x in stamps(START - DAY, 24, 0.0) if x[0] <= at(D22, 8)])   # ends 16:00 (08:00 + 8 h)
        holed = H.Funding([x for x in stamps(START - DAY, 26, 0.0) if x[0] != at(D22, 8)])
        self.assertEqual(len(holed.gaps), 1)
        for table in (None, short, holed):
            self.assertEqual(H.outcome(s, e, 0.001, table), (None, "no_funding_coverage"))
        with self.assertRaises(ValueError):
            H.owner_trade(s, e, H.exit_index(s, e))
        c = H.dry_counts(s, short)["periods"]["discovery"]
        self.assertEqual(c["funding_uncovered_events"]["H7x"], 1)
        self.assertEqual(H.dry_counts(s, f)["periods"]["discovery"]["funding_stamps_crossed"]["H7x"],
                         {"0": 0, "1": 0, "2": 1, "3+": 0})

    def test_owner_sizing_pays_funding_up_to_its_stop_fill(self):
        stop = 100.75                                                     # day 21's low
        cases = (({120: (101.0, 101.0, 100.5, 100.9)}, 1e-4, stop),      # touch inside the 10:00 bar: 08:00 paid
                 ({96: (100.5, 100.6, 100.4, 100.5)}, 0.0, 100.5),       # gap through at the 08:00 open: 08:00 not paid
                 ({96: (101.0, 101.0, 100.5, 100.9)}, 1e-4, stop))       # touch inside the 08:00 bar: 08:00 paid
        for bars, paid, fill in cases:
            s = trend(d22=day(101.1, at={**bars, 35: Rules.BREAK_UP}))
            e = H.ev_h7x(s)[0]
            o = H.owner_trade(s, e, H.exit_index(s, e), H.COST_RT, funding_for(s, at=self.RATES))
            px = s.O[e["entry_i"]]
            self.assertTrue(o["stop"])
            self.assertAlmostEqual(o["funding"], paid, msg=str(bars))
            self.assertAlmostEqual(o["R"], (fill - px - (H.COST_RT + paid) * px) / (px - stop))


class Outcomes(unittest.TestCase):
    def test_return_cost_and_scale(self):
        s = trend(d22=day(101.0, at={100: Rules.BREAK_UP}))
        e = H.ev_h7x(s)[0]
        sig = H.day_context(s)[D22]["sigma"]
        o, why = H.outcome(s, e, sig, funding_for(s))
        x = idx(s, D22, 287)
        self.assertIsNone(why)
        self.assertEqual((o["exit_i"], o["nb"], o["date"]), (x, 287 - 101, D22.isoformat()))
        self.assertAlmostEqual(o["r"], s.O[x] / s.O[e["entry_i"]] - 1)
        self.assertAlmostEqual(o["scale"], sig * math.sqrt(186))
        self.assertEqual((o["cost"], o["cost90"], o["funding"]), (H.COST_RT, H.COST_STRESS, 0.0))
        short = dict(e, side=-1)
        self.assertAlmostEqual(H.outcome(s, short, sig, funding_for(s))[0]["r"], -o["r"])

    def test_placebo_is_matched_on_period_slot_weekday_and_momentum_sign(self):
        s = H.series("BTCUSDT", walk(days=75))
        ctx = H.day_context(s)
        f = funding_for(s, rate=1e-4)
        for read in ("discovery", "confirmation"):
            plc, comp, aux = H.placebo_tables(s, ctx, read, f)
            brute, bcomp, bfund = {}, {}, {}
            for d, c in ctx.items():
                if H.day_period(d) != read:
                    continue
                rows = s.day_rows[d]
                for j in rows[:-1]:
                    r = s.O[rows[-1]] / s.O[j] - 1
                    brute.setdefault((H.slot(s, j), d.weekday(), c["mom_sign"]), []).append(r)
                    if c["mom_sign"]:
                        bcomp.setdefault(H.slot(s, j), []).append(c["mom_sign"] * r)
                        n = sum(1 for t in f.t if s.dt[j] <= t < s.dt[rows[-1]])
                        bfund.setdefault(H.slot(s, j), []).append(c["mom_sign"] * 1e-4 * n)
            self.assertTrue(brute)
            self.assertEqual(set(plc), set(brute))
            for k, v in brute.items():
                self.assertAlmostEqual(plc[k], sum(v) / len(v), places=14)
                self.assertEqual(aux["cells"][k][1], len(v))
            for k, v in bcomp.items():
                self.assertAlmostEqual(comp[k], sum(v) / len(v), places=14)
                self.assertAlmostEqual(aux["comparator_funding"][k], sum(bfund[k]) / len(bfund[k]), places=14)
            self.assertEqual(aux["comparator_days_without_funding"], 0)

    def test_a_read_computes_rows_for_its_own_period_only_and_signs_the_placebo(self):
        s = H.series("BTCUSDT", walk(days=75))
        seen = set()
        for read in ("discovery", "confirmation", "exposed"):
            rows, skipped = H.symbol_rows(s, read, funding=funding_for(s))
            for rule in H.RULES:
                for r in rows[rule]:
                    self.assertEqual(H.day_period(datetime.date.fromisoformat(r["date"])), read)
                    self.assertAlmostEqual(r["excess"], r["r"] - r["side"] * r["placebo"])
                    self.assertEqual(r["comparator_r"] is None, rule == "G9x")
                    seen.add((read, rule))
        self.assertTrue({("discovery", "H7x"), ("discovery", "G9x"), ("confirmation", "H7x"), ("confirmation", "G9x")} <= seen)
        self.assertFalse(any(k[0] == "exposed" for k in seen))

    def test_the_leave_own_day_out_placebo_is_the_mean_over_the_other_days(self):
        s = H.series("BTCUSDT", walk(days=75))
        ctx = H.day_context(s)
        cells = {}
        for d, c in ctx.items():
            if H.day_period(d) != "discovery":
                continue
            rows = s.day_rows[d]
            for j in rows[:-1]:
                cells.setdefault((H.slot(s, j), d.weekday(), c["mom_sign"]), {})[d.isoformat()] = s.O[rows[-1]] / s.O[j] - 1
        rows, _ = H.symbol_rows(s, "discovery", ctx, funding_for(s))
        checked = singles = 0
        for rule in H.RULES:
            for r in rows[rule]:
                others = [v for d, v in cells[(r["slot"], r["weekday"], r["mom_sign"])].items() if d != r["date"]]
                if not others:
                    self.assertIsNone(r["placebo_loo"])
                    self.assertIsNone(r["excess_loo"])
                    singles += 1
                    continue
                self.assertAlmostEqual(r["placebo_loo"], sum(others) / len(others), places=12)
                self.assertAlmostEqual(r["excess_loo"], r["r"] - r["side"] * r["placebo_loo"], places=14)
                checked += 1
        self.assertGreater(checked, 5)
        summ = H.loo_summary(rows["H7x"])
        self.assertEqual((summ["n"] + summ["dropped_single_day_cell"], summ["report_only"]), (len(rows["H7x"]), True))


class OwnerSizing(unittest.TestCase):
    def _trade(self, at, cost=0.0):
        bars = {100: Rules.BREAK_UP}
        bars.update(at)
        s = trend(d22=day(101.1, at=bars))                                # lows 100.85 stay above the stop (100.75)
        e = H.ev_h7x(s)[0]
        return s, e, H.owner_trade(s, e, H.exit_index(s, e), cost, funding_for(s))

    def test_stop_at_the_previous_low_costs_one_r(self):
        s, e, o = self._trade({150: (101.0, 101.0, 100.5, 100.9)})
        self.assertTrue(o["stop"])
        self.assertAlmostEqual(o["R"], -1.0)                               # exit AT the stop, 100.75
        self.assertAlmostEqual(o["stop_bp"], (s.O[e["entry_i"]] - 100.75) / s.O[e["entry_i"]] * 1e4)

    def test_a_gap_through_the_stop_fills_at_the_open(self):
        s, e, o = self._trade({150: (100.5, 100.6, 100.4, 100.5)})
        px = s.O[e["entry_i"]]
        self.assertAlmostEqual(o["R"], (100.5 - px) / (px - 100.75))
        self.assertLess(o["R"], H.GAP_THROUGH_R)

    def test_time_exit_and_cost_in_r(self):
        s, e, o = self._trade({}, cost=H.COST_RT)
        px, x = s.O[e["entry_i"]], H.exit_index(s, e)
        self.assertFalse(o["stop"])
        self.assertAlmostEqual(o["R"], (s.O[x] - px - H.COST_RT * px) / (px - 100.75))

    def test_the_exit_bar_itself_is_never_checked_for_the_stop(self):
        s, e, o = self._trade({287: (101.1, 101.2, 100.5, 101.15)}, cost=H.COST_RT)    # only the 23:55 bar pierces
        px, x = s.O[e["entry_i"]], H.exit_index(s, e)
        self.assertEqual(H.slot(s, x), 287)
        self.assertFalse(o["stop"])
        self.assertAlmostEqual(o["R"], (s.O[x] - px - H.COST_RT * px) / (px - 100.75))

    def test_an_entry_beyond_the_stop_is_unsizable(self):
        s = trend(d22=day(95.0, at={100: (95.0, 95.6, 95.0, 95.5)}))      # G9x long far below the previous low
        e = H.ev_g9x(s)[0]
        self.assertEqual(e["side"], 1)
        self.assertIsNone(H.owner_trade(s, e, H.exit_index(s, e), H.COST_RT, funding_for(s)))
        summ = H.owner_summary([{"owner": None, "symbol": "X", "date": "d", "side": 1}])
        self.assertEqual((summ["n"], summ["unsizable_entry_beyond_stop"]), (0, 1))


class Diagnostics(unittest.TestCase):
    def test_corr_with_book_ignores_book_days_outside_the_read(self):
        BS = H._load("book_sim", "scripts/research/book_sim.py")
        rows = [{"date": "2021-06-25", "owner": {"R": 1.0}}, {"date": "2021-06-28", "owner": {"R": 0.3}},
                {"date": "2021-07-02", "owner": {"R": -0.5}}]
        book = {"2021-06-25": 0.5, "2021-06-30": 0.2, "2021-07-02": -1.0}
        a = H.corr_with_book(rows, book, BS.corr, "discovery")
        b = H.corr_with_book(rows, dict(book, **{"2021-07-21": 5.0, "2017-08-01": -3.0}), BS.corr, "discovery")
        self.assertEqual(a, b)
        self.assertEqual(a["book_days"], 3)
        self.assertIsNotNone(a["corr_daily_R"])

    def test_comparator_difference_is_h7x_minus_comparator(self):
        base = {"cost": H.COST_RT, "funding": 0.0, "comparator_funding": 0.0}
        rows = [dict(base, r=0.003, comparator_r=0.001, date="2021-06-01"),
                dict(base, r=0.001, comparator_r=0.002, date="2021-06-02")]
        c = H.comparator_summary(rows)
        self.assertAlmostEqual(c["h7x_minus_comparator_bp"], 5.0)
        self.assertAlmostEqual(c["h7x_minus_comparator_net_bp"], 5.0)
        rows[0].update(funding=1e-4, cost=H.COST_RT + 1e-4, comparator_funding=-1e-4)
        c = H.comparator_summary(rows)
        self.assertAlmostEqual(c["h7x_minus_comparator_bp"], 5.0)                        # gross: funding-free
        self.assertAlmostEqual(c["h7x_minus_comparator_net_bp"], 5.0 - 1.0)              # (1 bp + 1 bp) / 2 rows
        self.assertAlmostEqual(c["comparator_net_bp"], 15.0 - 12.0 + 0.5)
        self.assertTrue(c["report_only"])

    def test_result_label(self):
        t = [{"test": "T1", "verdict": {"candidate": False}}, {"test": "T2", "verdict": {"candidate": True}}]
        self.assertEqual(H.result_label("discovery", t[:1]), "not found at this power")
        self.assertEqual(H.result_label("discovery", t), "candidate: T2")
        self.assertEqual(H.result_label("exposed", [{"test": "T1", "verdict": {"confirmed": True, "survives": False}}]),
                         "not found at this power")


class Verdicts(unittest.TestCase):
    def _tests(self, read, rows):
        return [{"test": n, "rule": r, read: d} for (n, r), d in zip(H.TESTS, rows)]

    def test_discovery_bh_m2_and_positive_net(self):
        t = H.verdicts("discovery", self._tests("discovery", [{"n": 9, "p_one_sided": 0.04, "net_bp": 5.0},
                                                              {"n": 9, "p_one_sided": 0.5, "net_bp": 3.0}]))
        self.assertEqual([x["verdict"] for x in t], [{"bh_rejected": True, "candidate": True},
                                                     {"bh_rejected": False, "candidate": False}])
        t = H.verdicts("discovery", self._tests("discovery", [{"n": 9, "p_one_sided": 0.04, "net_bp": -1.0},
                                                              {"n": 9, "p_one_sided": 0.06, "net_bp": 1.0}]))
        self.assertEqual([x["verdict"] for x in t], [{"bh_rejected": True, "candidate": False},
                                                     {"bh_rejected": True, "candidate": True}])

    def test_confirmation_and_exposed_chain_on_the_previous_verdict(self):
        prior = {"tests": [{"test": "T1", "verdict": {"bh_rejected": True, "candidate": True}},
                           {"test": "T2", "verdict": {"bh_rejected": False, "candidate": False}}]}
        ok = {"n": 9, "p_one_sided": 0.03, "net_bp": 2.0, "net_bp_2x_slippage": 1.0}
        t = H.verdicts("confirmation", self._tests("confirmation", [ok, ok]), prior)
        self.assertEqual([x["verdict"]["confirmed"] for x in t], [True, False])
        t = H.verdicts("confirmation", self._tests("confirmation", [dict(ok, net_bp_2x_slippage=-0.1), ok]), prior)
        self.assertFalse(t[0]["verdict"]["confirmed"])
        prior2 = {"tests": [{"test": "T1", "verdict": {"candidate": True, "confirmed": True}},
                            {"test": "T2", "verdict": {"candidate": False, "confirmed": False}}]}
        t = H.verdicts("exposed", self._tests("exposed", [{"n": 9, "p_one_sided": 0.08, "net_bp": 1.0}] * 2), prior2)
        self.assertEqual([x["verdict"]["survives"] for x in t], [True, False])


def fake_loader(days=75, start=datetime.date(2021, 6, 1)):
    """Hand-built 5m bars per symbol (a different seed each) standing in for the Binance history.
    [prereg: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    seeds = {sym: 100 + k for k, sym in enumerate(H.symbols())}
    return lambda sym: (walk(seed=seeds[sym], days=days, start=start), {"bars": None, "synthetic": True})


def fake_funding(days=80, start=datetime.date(2021, 5, 31), rate=1e-4):
    """Hand-built 8-hourly settlements standing in for funding.{SYM}.json.gz.
    [prereg amendment [H7x-A1]: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    return lambda sym: (H.Funding(stamps(start, days, rate)), {"rows": days * 3, "synthetic": True})


def boom(sym):
    raise AssertionError("data was loaded before the read order was checked")


class FakeGit:
    """Stands in for `git -C ROOT ...` in the registration-guard tests (no real git state is read or changed).
    [prereg §2: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""

    def __init__(self, untracked=(), dirty=(), history=False, ancestor=True):
        self.untracked, self.dirty, self.history, self.ancestor = set(untracked), set(dirty), history, ancestor

    def __call__(self, *args):
        if args[0] == "ls-files":
            return (1 if args[-1] in self.untracked else 0), ""
        if args[0] == "status":
            return 0, (f" M {args[-1]}\n" if args[-1] in self.dirty else "")
        if args[0] == "log":
            return 0, ("0123abcd\n" if self.history else "")
        if args[0] == "merge-base":
            return (0 if self.ancestor else 1), ""
        if args[0] == "rev-parse":
            return 0, "f" * 40 + "\n"
        raise AssertionError(args)


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        quiet = contextlib.redirect_stdout(io.StringIO())                 # the CLI's progress lines
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)
        BS = H._load("book_sim", "scripts/research/book_sim.py")
        self.book = ({"2021-06-25": 0.5, "2021-07-02": -1.0, "2021-07-21": 1.0, "2021-08-02": -0.5}, BS.corr)

    def p(self, name):
        return os.path.join(self.tmp.name, name)

    def guarded(self, git, prereg="... " + H.PREREG_AMENDMENT + " ..."):
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(H, "_git", git))
        stack.enter_context(mock.patch.object(H, "_prereg_text", lambda: prereg))
        self.addCleanup(stack.close)
        return stack

    def test_out_of_order_reads_refuse_before_touching_data(self):
        with self.assertRaises(SystemExit):
            H.run("confirmation", self.p("c.json"), None, loader=boom, book=self.book)
        json.dump({"meta": {"script": H.SCRIPT, "read": "discovery"}, "tests": []}, open(self.p("d.json"), "w"))
        with self.assertRaises(SystemExit):
            H.run("exposed", self.p("x.json"), self.p("d.json"), loader=boom, book=self.book)
        json.dump({"meta": {"script": "scripts/research/edge_f6.py", "read": "discovery"}}, open(self.p("f6.json"), "w"))
        with self.assertRaises(SystemExit):
            H.run("confirmation", self.p("c.json"), self.p("f6.json"), loader=boom, book=self.book)
        open(self.p("exists.json"), "w").write("{}")
        with self.assertRaises(SystemExit):
            H.run("discovery", self.p("exists.json"), loader=boom, book=self.book, require_clean=False)

    def test_the_guard_refuses_uncommitted_or_dirty_code_before_touching_data(self):
        out = os.path.join(H.ROOT, H.CANONICAL_OUT.format(read="discovery"))
        self.assertFalse(os.path.exists(out))
        for git in (FakeGit(untracked={H.SCRIPT}), FakeGit(dirty={H.PREREG}), FakeGit(dirty={"scripts/research/book_sim.py"}),
                    FakeGit(untracked={H.TESTS_FILE})):
            with self.guarded(git), self.assertRaises(SystemExit):
                H.run("discovery", out, loader=boom, book=self.book, funding_loader=boom)
        self.assertFalse(os.path.exists(out))

    def test_the_guard_refuses_a_non_canonical_or_already_read_out_path(self):
        with self.guarded(FakeGit()), self.assertRaises(SystemExit):
            H.run("discovery", self.p("d.json"), loader=boom, book=self.book, funding_loader=boom)
        out = os.path.join(H.ROOT, H.CANONICAL_OUT.format(read="discovery"))
        with self.guarded(FakeGit(history=True)), self.assertRaises(SystemExit):
            H.run("discovery", out, loader=boom, book=self.book, funding_loader=boom)
        with self.guarded(FakeGit(), prereg="no amendment tag"), self.assertRaises(SystemExit):
            H.run("discovery", out, loader=boom, book=self.book, funding_loader=boom)
        with self.guarded(FakeGit()):
            got = H._require_registration("discovery", out)
        self.assertEqual(set(got["committed_sha256"]), set(H.COMMITTED))
        self.assertIn(H.SCRIPT, H.COMMITTED)
        self.assertIn(H.PREREG, H.COMMITTED)

    def test_the_guard_ties_the_previous_read_to_history_and_registration(self):
        with self.guarded(FakeGit()):
            meta = json.loads(json.dumps(dict(H._meta("read", "discovery"), guarded=True), default=str))
        good = {"meta": meta, "tests": []}
        cases = ((dict(meta, guarded=False), FakeGit()), (meta, FakeGit(ancestor=False)),
                 (dict(meta, parameters=dict(meta["parameters"], vb_k=0.6)), FakeGit()),
                 (dict(meta, costs=dict(meta["costs"], funding="none")), FakeGit()),
                 (dict(meta, preregistration_sha256="0" * 64), FakeGit()),
                 (meta, FakeGit(dirty={"docs/audits/2026-10-03-edge-h7x-discovery.json"})))
        for m, git in cases:
            json.dump({"meta": m, "tests": []}, open(self.p("d.json"), "w"))
            with self.guarded(git), mock.patch.object(H, "_rel", lambda p: "docs/audits/2026-10-03-edge-h7x-discovery.json"):
                with self.assertRaises(SystemExit):
                    H._check_order("confirmation", self.p("d.json"))
        json.dump(good, open(self.p("d.json"), "w"))
        with self.guarded(FakeGit()):
            with self.assertRaises(SystemExit):                            # a temp file is outside the repository
                H._check_order("confirmation", self.p("d.json"))
            with mock.patch.object(H, "_rel", lambda p: "docs/audits/2026-10-03-edge-h7x-discovery.json"):
                self.assertEqual(H._check_order("confirmation", self.p("d.json")), good)

    def test_three_reads_chain_on_synthetic_bars(self):
        ld, fl = fake_loader(), fake_funding()
        d = H.run("discovery", self.p("d.json"), loader=ld, book=self.book, funding_loader=fl, require_clean=False)
        self.assertEqual([t["test"] for t in d["tests"]], ["T1", "T2"])
        self.assertTrue(all(t["discovery"]["n"] > 0 and "net_bp_2x_slippage" in t["discovery"] for t in d["tests"]))
        self.assertEqual(set(d["per_symbol"]["H7x"]), set(H.symbols()))
        self.assertTrue(all(v["report_only"] and "loo_placebo" in v for v in d["per_symbol"]["H7x"].values()))
        self.assertIn("mom20_comparator", d["diagnostics"]["H7x"])
        self.assertTrue(d["diagnostics"]["H7x"]["mom20_comparator"]["report_only"])
        self.assertIn("corr_daily_R", d["diagnostics"]["G9x"]["corr_with_fvg_book_v3"])
        self.assertEqual(d["family"]["bh_m"], 2)
        self.assertIn(d["result_label"], ("not found at this power", "candidate: T1", "candidate: T2", "candidate: T1, T2"))
        saved = json.load(open(self.p("d.json")))
        for t in d["tests"]:
            rows = saved["rows"][t["rule"]]
            self.assertEqual(len(rows), t["discovery"]["n"])
            self.assertTrue(set(H.ROW_FIELDS) | {"owner"} <= set(rows[0]))
            self.assertAlmostEqual(sum(r["funding"] for r in rows) / len(rows) * 1e4, t["discovery"]["funding_bp"])
            self.assertTrue(any(r["funding"] for r in rows) and any(r["funding_stamps"] == 2 for r in rows))
            self.assertTrue(all(abs(r["funding"]) == 1e-4 * r["funding_stamps"] for r in rows))
        self.assertEqual(saved["meta"]["guarded"], False)
        c = H.run("confirmation", self.p("c.json"), self.p("d.json"), loader=ld, book=self.book, funding_loader=fl,
                  require_clean=False)
        self.assertTrue(all("confirmed" in t["verdict"] and t["confirmation"]["n"] > 0 for t in c["tests"]))
        self.assertTrue(all("discovery" not in t for t in c["tests"]))         # a read carries its own period only
        self.assertEqual(c["meta"]["after"]["script_changed_since"], False)
        x = H.run("exposed", self.p("x.json"), self.p("c.json"), loader=ld, book=self.book, funding_loader=fl,
                  require_clean=False)
        self.assertTrue(all(t["exposed"]["n"] == 0 and t["verdict"]["survives"] is False for t in x["tests"]))
        self.assertEqual(x["result_label"], "not found at this power")

    def test_a_read_refuses_missing_funding_or_off_grid_bars_in_eligible_days(self):
        empty = lambda sym: (H.Funding([]), {"rows": 0})                   # noqa: E731
        with self.assertRaises(SystemExit):
            H.run("discovery", self.p("d.json"), loader=fake_loader(), book=self.book, funding_loader=empty,
                  require_clean=False)
        bars = walk(seed=100, days=75)
        k = next(j for j, b in enumerate(bars) if b["time"] == "2021-07-10T04:10:00Z")       # an eligible day (D-1 complete)
        bars[k] = dict(bars[k], time="2021-07-10T04:10:14Z")
        with self.assertRaises(SystemExit):
            H.run("discovery", self.p("d2.json"), loader=lambda sym: (bars, {}), book=self.book,
                  funding_loader=fake_funding(), require_clean=False)
        self.assertFalse(os.path.exists(self.p("d.json")) or os.path.exists(self.p("d2.json")))

    def test_dry_run_is_outcome_blind(self):
        saved = {k: getattr(H, k) for k in ("outcome", "placebo_tables", "owner_trade", "symbol_rows", "summarise",
                                            "funding_paid", "loo_summary", "comparator_summary")}

        def refuse(*a, **k):
            raise AssertionError("the dry run touched an outcome function")
        try:
            for k in saved:
                setattr(H, k, refuse)
            res = H.dry_run(self.p("dry.json"), loader=fake_loader(), funding_loader=fake_funding())
        finally:
            for k, v in saved.items():
                setattr(H, k, v)
        forbidden = {"r", "excess", "placebo", "net_bp", "gross_bp", "R", "mean_R", "excess_z", "p_one_sided",
                     "win_rate_net", "corr_daily_R", "comparator_r", "funding", "funding_bp", "rate", "cost", "cost90",
                     "placebo_loo", "excess_loo", "comparator_funding"}

        def keys(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    yield k
                    yield from keys(v)
            elif isinstance(o, list):
                for v in o:
                    yield from keys(v)
        dry = json.load(open(self.p("dry.json")))
        self.assertFalse(forbidden & set(keys({k: v for k, v in dry.items() if k != "meta"})))   # meta: registered text
        per = res["symbols"][H.symbols()[0]]["periods"]
        self.assertTrue(per["discovery"]["events"]["H7x"] > 0 and per["confirmation"]["events"]["G9x"] > 0)
        self.assertEqual(per["discovery"]["incomplete_days"], 4)            # days 5, 9, 17, 33 of the walk
        self.assertEqual(sum(per["discovery"]["funding_stamps_crossed"]["H7x"].values())
                         + per["discovery"]["events_without_exit_bar"]["H7x"], per["discovery"]["events"]["H7x"])
        self.assertEqual(sum(res["pooled_events"]["discovery"].values()),
                         sum(res["symbols"][s]["periods"]["discovery"]["events"][r] for s in H.symbols() for r in H.RULES))


class DryCounts(unittest.TestCase):
    def test_a_day_without_any_bar_is_absent_and_makes_the_next_ineligible(self):
        s = H.series("BTCUSDT", walk(holes={40: set(range(288))}))       # 2021-07-11 missing entirely
        c = H.dry_counts(s)["periods"]["discovery"]
        self.assertEqual((c["absent_days"], c["incomplete_days"], c["days_with_bars"]), (1, 0, 47))
        self.assertEqual((c["gaps"]["missing_5m_slots"], c["gaps"]["gap_runs"]), (288, 1))
        self.assertNotIn(datetime.date(2021, 7, 12), H.day_context(s))


class PointInTime(unittest.TestCase):
    """Truncating the future must never change a past decision (the pattern of test_detector_leakage_probe.py and
    test_edge_f6.py), with NO completeness exemption: the cut day must agree too.
    [prereg §1: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""

    @staticmethod
    def _keys(evs, cut):
        return {ev_key(e) for e in evs if e["entry_i"] < cut}

    def _cuts(self, s, full):
        cuts = [e["entry_i"] + 1 for rule in H.RULES for e in full[rule][2:40:9]]       # just after an entry, mid-day
        cuts += [s.day_rows[d][0] for d in list(s.day_rows)[30::11]]                  # day boundaries
        return cuts + [len(s.C) // 2 + 37, len(s.C) - 150]

    def test_truncating_the_future_never_changes_a_past_event(self):
        bars = walk()
        s = H.series("BTCUSDT", bars)
        full, fctx = H.events(s), H.day_context(s)
        self.assertTrue(all(len(full[r]) > 10 for r in H.RULES))
        for cut in self._cuts(s, full):
            part = H.series("BTCUSDT", bars[:cut])
            pev, pctx = H.events(part), H.day_context(part)
            for rule in H.RULES:
                self.assertEqual(self._keys(pev[rule], cut), self._keys(full[rule], cut), (rule, cut))
            self.assertEqual(pctx, {d: fctx[d] for d in part.day_rows if d in fctx}, cut)

    def test_a_reads_rows_never_depend_on_bars_after_its_period(self):
        """Every outcome row of a read (returns, placebo, LOO placebo, comparator, funding, owner sizing) is identical when
        every bar after the read's last day is cut.
        [prereg §2: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
        for read, start in (("discovery", datetime.date(2021, 6, 1)), ("confirmation", datetime.date(2024, 1, 15))):
            bars = walk(days=75, start=start)
            nxt = (datetime.date.fromisoformat(H.PERIODS[read][1]) + DAY).isoformat()
            cut = next(k for k, b in enumerate(bars) if b["time"] >= nxt)
            full = H.series("BTCUSDT", bars)
            f = funding_for(full, rate=1e-4)
            a, _ = H.symbol_rows(full, read, funding=f)
            b, _ = H.symbol_rows(H.series("BTCUSDT", bars[:cut]), read, funding=f)
            self.assertTrue(all(len(a[r]) > 3 for r in H.RULES), read)
            self.assertEqual(a, b, read)

    def test_the_check_catches_a_same_day_completeness_filter(self):
        """Negative control: F3/F4's research semantics (keep an event only if its OWN day turns out complete) must FAIL
        the truncation check, which is why their detectors are not reused here.
        [prereg §1: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
        bars = walk()
        leaky = lambda s: [e for e in H.ev_h7x(s) if len(s.day_rows[e["day"]]) >= H.BARS_PER_DAY]  # noqa: E731
        s = H.series("BTCUSDT", bars)
        full = leaky(s)
        cut = full[5]["entry_i"] + 1
        self.assertNotEqual(self._keys(leaky(H.series("BTCUSDT", bars[:cut])), cut), self._keys(full, cut))

    def test_the_shared_leakage_probe_passes_strictly(self):
        """The shared probe's own random walk and check (scripts/tests/test_detector_leakage_probe.py), with no
        KNOWN_COMPLETENESS exemption for either rule, under the names the shared registry would use (H7x:<DETECTORS key>).
        [prereg §1: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
        bars = PROBE.walk()
        n = len(bars)
        for k, det in H.DETECTORS.items():
            name = f"H7x:{k}"
            self.assertNotIn(name, PROBE.KNOWN_COMPLETENESS)
            s_full = PROBE.SERIES("BTCUSDT", bars)
            evs = det(s_full)
            self.assertTrue(evs, name)
            for cut in (n // 3 + 101, n // 2 + 37, 2 * n // 3 + 200, n - 150, 288 * 50, evs[len(evs) // 2]["entry_i"] + 1):
                with self.subTest(detector=name, cut=cut):
                    PROBE.check(self, name, s_full, PROBE.entries(evs, cut),
                                PROBE.entries(det(PROBE.SERIES("BTCUSDT", bars[:cut])), cut), cut)


if __name__ == "__main__":
    unittest.main()
