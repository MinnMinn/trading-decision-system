"""scripts/research/pit_trend.py on hand-built bars (no history, no outcome).

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_pit_trend
(docs/plans/2026-10-04-edge-cx-ftmo-crypto-preregistration.md §1; the OIL and VC drafts of 2026-10-04)
"""
import datetime
import importlib.util
import math
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


PT = _load("pit_trend", "scripts/research/pit_trend.py")
UTC = datetime.timezone.utc
D0 = datetime.date(2021, 1, 4)


def day_bars(d, closes, first_slot=0, wiggle=0.0):
    """5m candles on UTC day d starting at slot `first_slot` (minutes / 5); open = previous close."""
    out, prev = [], closes[0]
    for k, c in enumerate(closes):
        t = datetime.datetime(d.year, d.month, d.day, tzinfo=UTC) + datetime.timedelta(minutes=5 * (first_slot + k))
        o = prev
        out.append({"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "open": o, "high": max(o, c) + wiggle,
                    "low": min(o, c) - wiggle, "close": c})
        prev = c
    return out


def flat_history(n_days, start=D0, base=100.0, bars=288, step=0.001):
    """n_days of complete days with a small zig-zag (a non-zero sigma) and a slow uptrend (MOM20 > 0)."""
    out, px = [], base
    for k in range(n_days):
        d = start + datetime.timedelta(days=k)
        closes = [px * (1 + step * (1 if j % 2 else -1)) for j in range(bars - 1)] + [px * 1.001]
        out += day_bars(d, closes)
        px *= 1.001
    return out


class Constants(unittest.TestCase):
    def test_parameters_are_f3_f4_own(self):
        F3 = _load("edge_f3", "scripts/research/edge_f3.py")
        F4 = _load("edge_f4", "scripts/research/edge_f4.py")
        self.assertEqual(PT.MOM_DAYS, F3.MOM_DAYS)
        self.assertEqual(PT.VB_K, F4.VB_K)
        self.assertEqual(PT.VOL_DAYS, F3.EC.VOL_DAYS)


class Qualifying(unittest.TestCase):
    def test_threshold_counts_distinct_on_grid_bars(self):
        c = day_bars(D0, [100.0] * 230)
        b = PT.Bars("X", c, UTC)
        self.assertIn(D0, PT.qualifying(b, 230))
        self.assertNotIn(D0, PT.qualifying(b, 231))

    def test_off_grid_bars_do_not_count(self):
        c = day_bars(D0, [100.0] * 230)
        c[5]["time"] = c[5]["time"][:-3] + "07Z"           # second 7: off the grid
        b = PT.Bars("X", c, UTC)
        self.assertNotIn(D0, PT.qualifying(b, 230))


class Context(unittest.TestCase):
    def test_eligibility_needs_21_qualifying_days_and_a_qualifying_previous_day(self):
        b = PT.Bars("X", flat_history(23), UTC)
        ctx = PT.context(b, 230)
        days = list(b.day_rows)
        self.assertNotIn(days[20], ctx)                   # only 20 qualifying days before it
        self.assertIn(days[21], ctx)
        self.assertGreater(ctx[days[21]]["mom"], 0)

    def test_calendar_rule_rejects_after_a_missing_day_trading_rule_accepts(self):
        c = flat_history(30)
        gap = (D0 + datetime.timedelta(days=25)).isoformat()
        c = [x for x in c if not x["time"].startswith(gap)]
        b = PT.Bars("X", c, UTC)
        d26 = D0 + datetime.timedelta(days=26)
        self.assertNotIn(d26, PT.context(b, 230, "calendar"))
        self.assertIn(d26, PT.context(b, 230, "trading"))

    def test_own_day_bar_count_is_not_consulted(self):
        c = flat_history(25)
        last = (D0 + datetime.timedelta(days=24)).isoformat()
        short = [x for x in c if not x["time"].startswith(last)] + day_bars(D0 + datetime.timedelta(days=24), [130.0] * 10)
        b = PT.Bars("X", short, UTC)
        self.assertIn(D0 + datetime.timedelta(days=24), PT.context(b, 230))

    def test_sigma_uses_previous_days_only(self):
        c = flat_history(30)
        b1 = PT.Bars("X", c, UTC)
        d = D0 + datetime.timedelta(days=25)
        later = [x for x in c if x["time"] < (d + datetime.timedelta(days=1)).isoformat()]
        b2 = PT.Bars("X", later, UTC)
        self.assertEqual(PT.context(b1, 230)[d]["sigma"], PT.context(b2, 230)[d]["sigma"])


def history_then(day_closes, n_hist=25):
    c = flat_history(n_hist)
    d = D0 + datetime.timedelta(days=n_hist)
    return c + day_bars(d, day_closes), d


class Detection(unittest.TestCase):
    def test_h7_long_first_close_above_previous_high_enters_next_open(self):
        c, d = history_then([110.0] * 5 + [140.0] + [141.0] * 20)
        b = PT.Bars("X", c, UTC)
        ctx = PT.context(b, 230)
        ev = PT.ev_h7(b, ctx)
        e = [x for x in ev if x["day"] == d]
        self.assertEqual(len(e), 1)
        self.assertEqual(e[0]["side"], 1)
        self.assertEqual(b.sday[e[0]["i"]], d)
        self.assertEqual(e[0]["entry_i"], e[0]["i"] + 1)
        self.assertGreater(b.C[e[0]["i"]], ctx[d]["prev_high"])

    def test_h7_ignores_a_break_against_momentum(self):
        c, d = history_then([102.45] * 5 + [50.0] * 20)     # inside the previous range, then a break DOWN (MOM20 > 0)
        b = PT.Bars("X", c, UTC)
        self.assertEqual([x for x in PT.ev_h7(b, PT.context(b, 230)) if x["day"] == d], [])

    def test_g9_short_side_and_drop_when_signal_is_the_last_bar(self):
        c, d = history_then([110.0] * 5 + [90.0] * 3)
        b = PT.Bars("X", c, UTC)
        ctx = PT.context(b, 230)
        ev = [x for x in PT.ev_g9(b, ctx) if x["day"] == d]
        self.assertEqual(ev[0]["side"], -1)
        c2, d2 = history_then([110.0] * 5 + [90.0])
        b2 = PT.Bars("X", c2, UTC)
        self.assertEqual([x for x in PT.ev_g9(b2, PT.context(b2, 230)) if x["day"] == d2], [])

    def test_truncation_probe_event_and_inputs_unchanged(self):
        c, d = history_then([110.0] * 5 + [140.0] + [141.0 + k for k in range(30)])
        b = PT.Bars("X", c, UTC)
        ctx = PT.context(b, 230)
        for rule in PT.RULES:
            full = [x for x in PT.DETECTORS[rule](b, ctx) if x["day"] == d]
            if not full:
                continue
            cut = [x for x in c if x["time"] <= b.T[full[0]["i"] + 1]]   # keep the entry bar's open only
            bt = PT.Bars("X", cut, UTC)
            ctx_t = PT.context(bt, 230)
            tr = [x for x in PT.DETECTORS[rule](bt, ctx_t) if x["day"] == d]
            self.assertEqual(len(tr), 1)
            self.assertEqual((tr[0]["i"], tr[0]["side"]), (full[0]["i"], full[0]["side"]))
            for key in ("mom", "sigma", "prev_range", "prev_high", "prev_low", "open"):
                self.assertEqual(ctx_t[d][key], ctx[d][key])


class Outcomes(unittest.TestCase):
    def test_outcome_eod_close_and_scale(self):
        c, d = history_then([110.0] * 5 + [140.0] + [141.0] * 10 + [150.0])
        b = PT.Bars("X", c, UTC)
        ctx = PT.context(b, 230)
        ev = [x for x in PT.ev_h7(b, ctx) if x["day"] == d][0]
        o = PT.outcome(b, ev, ctx)
        self.assertAlmostEqual(o["r"], 150.0 / b.O[ev["entry_i"]] - 1)
        self.assertEqual(o["nb"], PT.exit_index(b, ev) - ev["entry_i"] + 1)
        self.assertAlmostEqual(o["scale"], ctx[d]["sigma"] * math.sqrt(o["nb"]))
        self.assertFalse(o["costed"])

    def test_stop_trade_stops_and_fills_at_open_beyond(self):
        c, d = history_then([110.0] * 5 + [140.0] + [141.0] * 3 + [60.0] + [61.0] * 5)
        crash = [x for x in c if x["close"] == 60.0][0]
        crash.update(open=60.0, high=60.5)                  # the bar OPENS beyond the stop
        b = PT.Bars("X", c, UTC)
        ctx = PT.context(b, 230)
        ev = [x for x in PT.ev_h7(b, ctx) if x["day"] == d][0]
        t = PT.stop_trade(b, ev, ctx, 1.4)
        self.assertEqual(t["exit"], "stop")
        self.assertLess(t["R_gross"], -1.0)                 # a gap through the stop fills at the open
        self.assertEqual(t["R_gross"], t["R_net"])

    def test_stop_trade_cost_lowers_r(self):
        c, d = history_then([110.0] * 5 + [140.0] + [141.0] * 10)
        b = PT.Bars("X", c, UTC)
        ctx = PT.context(b, 230)
        ev = [x for x in PT.ev_h7(b, ctx) if x["day"] == d][0]
        t = PT.stop_trade(b, ev, ctx, 1.4, cost=lambda a, z, s: 0.001)
        self.assertAlmostEqual(t["R_gross"] - t["R_net"], t["cost_R"])
        self.assertGreater(t["cost_R"], 0)

    def test_placebo_table_and_excess(self):
        c, d = history_then([110.0] * 5 + [140.0] + [141.0] * 10)
        b = PT.Bars("X", c, UTC)
        ctx = PT.context(b, 230)
        plc = PT.placebo_table(b, ctx, [d])
        ev = [x for x in PT.ev_h7(b, ctx) if x["day"] == d][0]
        rows, missing = PT.with_excess([PT.outcome(b, ev, ctx)], plc)
        self.assertEqual(missing, 0)
        self.assertAlmostEqual(rows[0]["excess"], 0.0)       # one day: the placebo IS the event's own return


class Costs(unittest.TestCase):
    def spec(self):
        return {"symbol": "X", "point": 0.01, "_server_utc_offset_sec_now": 10800,
                "recorded_spread_m15": {"median_points": 10, "p90_points": 30, "first_bar_server": "2024.01.01 00:00",
                                        "last_bar_server": "2024.01.02 00:00",
                                        "by_utc_hour": [{"h": h, "n": 5, "median": 4, "p90": 8} for h in range(23)]}}

    def test_bucket_is_server_hour_minus_export_offset(self):
        z = datetime.timezone(datetime.timedelta(hours=3))
        sc = PT.SpecCost(self.spec(), 100.0, 0.0002, z)
        t = datetime.datetime(2024, 1, 1, 10, 0, tzinfo=UTC)         # 13:00 server -> bucket 10
        self.assertEqual(sc.bucket(t), 10)
        self.assertAlmostEqual(sc.leg(t), 0.5 * 4 * 0.01 / 100.0 + 0.0002)
        self.assertAlmostEqual(sc(t, t), 2 * sc.leg(t))

    def test_missing_bucket_falls_back_and_is_counted(self):
        sc = PT.SpecCost(self.spec(), 100.0, 0.0, UTC)
        t = datetime.datetime(2024, 1, 1, 23, 0, tzinfo=UTC)         # bucket (23 - 3) % 24 = 20: present
        sc.leg(t)
        self.assertEqual(sc.fallbacks, 0)
        t2 = datetime.datetime(2024, 1, 1, 2, 0, tzinfo=UTC)         # bucket 23: absent -> overall median
        self.assertAlmostEqual(sc.spread_rel(sc.bucket(t2)), 10 * 0.01 / 100.0)
        self.assertEqual(sc.fallbacks, 1)

    def test_refuses_without_commission_or_whole_hour_offset(self):
        with self.assertRaises(ValueError):
            PT.SpecCost(self.spec(), 100.0, None, UTC)
        bad = dict(self.spec(), _server_utc_offset_sec_now=5000)
        with self.assertRaises(ValueError):
            PT.SpecCost(bad, 100.0, 0.0, UTC)

    def test_price_ref_is_the_window_median(self):
        z = datetime.timezone(datetime.timedelta(hours=3))
        m15 = [{"time": "2023-12-31T21:00:00Z", "close": 1.0}, {"time": "2024-01-01T00:00:00Z", "close": 3.0},
               {"time": "2024-01-01T12:00:00Z", "close": 5.0}, {"time": "2024-01-02T22:00:00Z", "close": 99.0}]
        self.assertEqual(PT.price_ref(m15, self.spec(), z), 3.0)


class Sessions(unittest.TestCase):
    def test_session_bars(self):
        s = [{"dow": 0, "windows": []}] + [{"dow": k, "windows": [["03:05", "23:50"]]} for k in range(1, 6)] + \
            [{"dow": 6, "windows": []}]
        self.assertEqual(PT.session_bars(s), 249)
        s[2]["windows"] = [["01:05", "23:50"]]
        with self.assertRaises(ValueError):
            PT.session_bars(s)


if __name__ == "__main__":
    unittest.main()
