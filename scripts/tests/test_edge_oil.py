"""scripts/research/edge_oil.py on hand-built bars (no history, no outcome).

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_edge_oil
(docs/plans/2026-10-04-oil-trend-transfer-preregistration-DRAFT.md [OIL-P1])
"""
import datetime
import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


O = _load("edge_oil", "scripts/research/edge_oil.py")
PT = O.PT
UTC = datetime.timezone.utc


def weekday_candles(n_days, start=datetime.date(2022, 1, 3), first_slot=37, bars=249):
    """A 5-day market: weekday sessions of `bars` 5m bars from slot `first_slot` (03:05), slow uptrend, zig-zag."""
    out, px, d, k = [], 100.0, start, 0
    while k < n_days:
        if d.weekday() < 5:
            step = 0.0004 if (k // 7) % 2 else 0.0001
            prev = px * (1 - step)
            for j in range(bars):
                c = px * (1 + step * (1 if j % 2 else -1))
                t = datetime.datetime(d.year, d.month, d.day, tzinfo=UTC) + datetime.timedelta(minutes=5 * (first_slot + j))
                out.append({"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "open": prev, "high": max(prev, c),
                            "low": min(prev, c), "close": c})
                prev = c
            px *= 1.001
            k += 1
        d += datetime.timedelta(days=1)
    return out


class Windows(unittest.TestCase):
    def test_split_date_is_where_60_percent_have_elapsed(self):
        days = [datetime.date(2020, 1, 1) + datetime.timedelta(days=k) for k in range(100)]
        self.assertEqual(O.split_date({"A": days}, dev_end=datetime.date(2030, 1, 1)), days[60])

    def test_split_is_pooled_and_ignores_days_after_dev_end(self):
        a = [datetime.date(2020, 1, 1) + datetime.timedelta(days=k) for k in range(100)]
        b = [datetime.date(2020, 1, 1) + datetime.timedelta(days=50 + k) for k in range(100)]
        d = O.split_date({"A": a, "B": b}, dev_end=datetime.date(2020, 4, 30))
        pooled = sorted(x for x in a + b if x < datetime.date(2020, 4, 30))
        self.assertGreaterEqual(sum(1 for x in pooled if x < d), 0.6 * len(pooled))
        self.assertLess(sum(1 for x in pooled if x < d - datetime.timedelta(days=1)), 0.6 * len(pooled))

    def test_membership_needs_250_days_on_both_sides(self):
        d_star = datetime.date(2022, 1, 1)
        a = [d_star - datetime.timedelta(days=k) for k in range(1, 251)] + \
            [d_star + datetime.timedelta(days=k) for k in range(250)]
        b = a[:249] + a[250:]
        self.assertEqual(O.members({"A": a, "B": b}, d_star, dev_end=datetime.date(2030, 1, 1)), ["A"])

    def test_windows_are_contiguous(self):
        d_star, end = datetime.date(2021, 6, 1), datetime.date(2026, 9, 30)
        self.assertEqual(O.window("discovery", d_star, end)[1], O.window("confirmation", d_star, end)[0])
        self.assertEqual(O.window("confirmation", d_star, end)[1], O.window("exposed", d_star, end)[0])
        self.assertEqual(O.window("exposed", d_star, end)[1], end + datetime.timedelta(days=1))

    def test_min_bars_from_the_session(self):
        e = {"sessions_trade": [{"dow": k, "windows": [["03:05", "23:50"]] if 1 <= k <= 5 else []} for k in range(7)]}
        self.assertEqual(O.min_bars_for(e), 199)            # floor(0.8 x 249)


class DryRun(unittest.TestCase):
    def test_counts_only(self):
        b = PT.Bars("UKOIL", weekday_candles(60), UTC)
        out = O.dry_symbol(b, 199)
        self.assertGreater(len(out["qualifying_days"]), 50)
        self.assertGreater(len(out["events"]["H7"]) + len(out["events"]["G9"]), 0)
        self.assertFalse(set(out) & {"r", "R", "R_net", "R_gross", "net_bp", "excess", "rows"})   # no return field
        s = O.dry_summary({"UKOIL": out}, datetime.date(2022, 6, 30))
        self.assertIn("windows", s["symbols"]["UKOIL"])
        self.assertIsNotNone(s["symbols"]["UKOIL"]["S"])
        self.assertLessEqual(len(s["symbols"]["UKOIL"]["largest_overnight_gaps_daily_sd"]), 20)

    def test_monday_uses_friday_as_previous_day(self):
        b = PT.Bars("UKOIL", weekday_candles(40), UTC)
        ctx = PT.context(b, 199, O.PREV_RULE)
        mondays = [d for d in ctx if d.weekday() == 0]
        self.assertTrue(mondays)
        self.assertTrue(all(ctx[d]["prev_day"].weekday() == 4 for d in mondays))


class Screen(unittest.TestCase):
    def test_k_against_s(self):
        spec = {"symbol": "UKOIL.cash", "point": 0.001, "_server_utc_offset_sec_now": 10800,
                "recorded_spread_m15": {"median_points": 30, "p90_points": 60,
                                        "by_utc_hour": [{"h": h, "n": 9, "median": 30, "p90": 60} for h in range(24)]}}
        sc = PT.SpecCost(spec, 70.0, 0.00002, UTC)
        rel = 30 * 0.001 / 70.0
        S = 0.02
        out = O.screen_symbol(sc, S, 23 * 60 + 45)
        self.assertAlmostEqual(out["K"], rel + 2 * 0.00002)
        self.assertAlmostEqual(out["limit"], 0.5 * 0.05 * S)
        self.assertEqual(out["admitted"], out["K"] <= out["limit"])
        self.assertFalse(O.screen_symbol(sc, None, 0)["admitted"])


def _s(n, p, net, p90=1.0):
    return {"n": n, "p_one_sided": p, "net_bp": net, "net_bp_p90": p90}


class Verdicts(unittest.TestCase):
    def test_discovery_bh_and_net(self):
        v = O.verdicts("discovery", {"T1": _s(100, 0.01, 2.0), "T2": _s(100, 0.04, -1.0)})
        self.assertTrue(v["T1"]["advances"])
        self.assertFalse(v["T2"]["advances"])               # BH-rejected but net < 0
        self.assertTrue(v["T2"]["bh_rejected"])

    def test_confirmation_needs_p90_and_closes_failed_tests(self):
        prior = {"T1": {"advances": True}, "T2": {"advances": False}}
        v = O.verdicts("confirmation", {"T1": _s(50, 0.01, 2.0, -0.5), "T2": {"n": 0}}, prior)
        self.assertFalse(v["T1"]["advances"])
        self.assertTrue(v["T2"]["closed_before_this_read"])
        v2 = O.verdicts("confirmation", {"T1": _s(50, 0.01, 2.0, 0.5), "T2": {"n": 0}}, prior)
        self.assertTrue(v2["T1"]["advances"])

    def test_exposed_gate(self):
        prior = {"T1": {"advances": True}, "T2": {"advances": True}}
        v = O.verdicts("exposed", {"T1": _s(50, 0.09, 0.1), "T2": _s(50, 0.11, 3.0)}, prior)
        self.assertEqual((v["T1"]["advances"], v["T2"]["advances"]), (True, False))


class Read(unittest.TestCase):
    def test_rows_stay_inside_the_window_and_retired_rules_are_not_computed(self):
        b = PT.Bars("UKOIL", weekday_candles(80), UTC)
        ctx = PT.context(b, 199, O.PREV_RULE)
        days = sorted(ctx)
        lo, hi = days[10], days[40]
        rows, missing = O.read_rows(b, ctx, lo, hi, lambda a, z, s: 0.0002, rules=("G9",))
        self.assertEqual(set(rows), {"G9"})
        self.assertTrue(rows["G9"])
        self.assertTrue(all(lo.isoformat() <= r["date"] < hi.isoformat() for r in rows["G9"]))
        self.assertTrue(all(abs(r["cost"] - 0.0002) < 1e-15 and "excess" in r for r in rows["G9"]))
        rep = O.by_symbol_year(rows)
        self.assertIn("UKOIL|2022", rep["G9"])
        EC = O._ec()
        s = EC.summarise(rows["G9"])
        self.assertEqual(s["n"], len(rows["G9"]))

    def test_owner_sizing_report(self):
        b = PT.Bars("UKOIL", weekday_candles(60), UTC)
        ctx = PT.context(b, 199, O.PREV_RULE)
        out = O.owner_sizing(b, ctx, min(ctx), max(ctx), lambda a, z, s: 0.0, 2)
        self.assertEqual(set(out), {"1.4", "2.0"})
        self.assertEqual(out["1.4"]["risk_pct_each"], 0.5)


class Guard(unittest.TestCase):
    def test_prereg_constant_is_the_sealed_name_and_draft_exists(self):
        self.assertFalse(O.PREREG.endswith("-DRAFT.md"))
        self.assertTrue(os.path.exists(os.path.join(ROOT, O.PREREG.replace(".md", "-DRAFT.md"))))
        with self.assertRaises(SystemExit):
            O.G.require_sealed(ROOT, O.PREREG.replace(".md", "-DRAFT.md"), O.TAG)

    def test_draft_text_does_not_pass_the_sealed_check(self):
        with open(os.path.join(ROOT, O.PREREG.replace(".md", "-DRAFT.md")), encoding="utf-8") as fh:
            text = fh.read()
        with self.assertRaises(SystemExit):
            O.G.check_sealed_text(text, O.PREREG, O.TAG)

    def test_code_files_exist(self):
        self.assertEqual(len(O.CODE), len(set(O.CODE)))
        for p in O.CODE:
            self.assertTrue(os.path.exists(os.path.join(ROOT, p)), p)

    def test_code_lists_every_module_a_read_loads(self):
        """Every repository module an OIL read loads (fresh, under the trace) is in CODE."""
        O.G.trace_start(ROOT)
        O._load("edge_census", "scripts/research/edge_census.py")
        O._zone()
        import history_store  # noqa: F401
        import real_costs  # noqa: F401
        O.G.require_covered(O.CODE)
        loaded = set()
        for m in list(sys.modules.values()):
            f = getattr(m, "__file__", None)
            if not f:
                continue
            rel = os.path.relpath(os.path.abspath(f), ROOT).replace(os.sep, "/")
            if rel.startswith("scripts/") and not rel.startswith("scripts/tests/") and rel.endswith(".py"):
                loaded.add(rel)
        self.assertEqual(sorted(loaded - set(O.CODE)), [])


if __name__ == "__main__":
    unittest.main()
