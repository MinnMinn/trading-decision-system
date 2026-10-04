"""scripts/research/edge_vc.py on hand-built series and trades (no history, no outcome).

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_edge_vc
(docs/plans/2026-10-04-vc-volatility-condition-preregistration-DRAFT.md [VC-P1])
"""
import datetime
import importlib.util
import math
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


V = _load("edge_vc", "scripts/research/edge_vc.py")
UTC = datetime.timezone.utc


def weekdays(start, n):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += datetime.timedelta(days=1)
    return out


def sigma_pattern(days, flat=130):
    """1.0 for `flat` days, then alternating 2.0 / 0.5: HIGH and LOW days once the history exists."""
    return {d: (1.0 if k < flat else (2.0 if k % 2 else 0.5)) for k, d in enumerate(days)}


def fake_series(days, sig, hour=10):
    """One bar per day at `hour`:00 UTC (the series shape book_rows / forward_rows read)."""
    s = types.SimpleNamespace()
    s.T = [f"{d.isoformat()}T{hour:02d}:00:00Z" for d in days]
    s.dt = [datetime.datetime(d.year, d.month, d.day, hour, tzinfo=UTC) for d in days]
    s.sday = list(days)
    s.day_rows = {d: [i] for i, d in enumerate(days)}
    s.dense_days = list(days)
    s._vol = dict(sig)
    return s


def fake_trades(days, vr_high, r_high=0.5, r_low=-0.1, k=1.4, sig=None, hour=10):
    """book_sim.trades-shaped rows; both sides on both halves."""
    out = []
    for n, d in enumerate(days):
        if d not in vr_high:
            continue
        noise = ((n * 7919) % 13 - 6) / 20.0
        r = (r_high if vr_high[d] else r_low) + noise
        out.append({"symbol": "XAUUSD", "entry_time": f"{d.isoformat()}T{hour:02d}:00:00Z", "R": r - 0.01, "cost_R": 0.01,
                    "stop_bp": 1e4 * k * (sig[d] if sig else 1.0) * 6.0, "side": 1 if n % 3 else -1, "exit": "time"})
    return out


def split_rows(r_true, r_false, n=400, key="high", side=lambda k: 1 if k % 3 else -1):
    out = []
    for k in range(n):
        noise = ((k * 7919) % 13 - 6) / 20.0
        h = bool(k % 2)
        out.append({"day": f"d{k}", key: h, "side": side(k), "R_gross": (r_true if h else r_false) + noise, "R_net": 0.0})
    return out


class Condition(unittest.TestCase):
    def test_vr_needs_125_previous_days_and_uses_the_median(self):
        days = weekdays(datetime.date(2016, 1, 4), 200)
        sig = {d: 1.0 for d in days}
        sig[days[150]] = 3.0
        vr = V.vr_by_day(sig)
        self.assertNotIn(days[124], vr)
        self.assertIn(days[125], vr)
        self.assertAlmostEqual(vr[days[150]], 3.0)

    def test_vr_is_point_in_time(self):
        days = weekdays(datetime.date(2016, 1, 4), 220)
        sig = sigma_pattern(days)
        a = V.vr_by_day(sig)
        sig2 = dict(sig)
        for d in days[180:]:
            sig2[d] = 50.0
        b = V.vr_by_day(sig2)
        for d in days[:180]:
            self.assertEqual(a.get(d), b.get(d))

    def test_label_high_iff_vr_above_one(self):
        rows, missing = V.label([{"day": "2020-01-01"}, {"day": "2020-01-02"}, {"day": "2020-01-03"}],
                                {datetime.date(2020, 1, 1): 1.0, datetime.date(2020, 1, 2): 1.01})
        self.assertEqual([r["high"] for r in rows], [False, True])
        self.assertEqual(missing, 1)

    def test_long_hold_is_an_earlier_entry_slot_than_the_component_median(self):
        rows = [{"component": "H7_XAUUSD_eod", "entry_slot": s} for s in (60, 120, 600, 900)] + \
               [{"component": "G9_XAUUSD_eod", "entry_slot": s} for s in (300, 310)]
        med = V.mark_hold(rows)
        self.assertEqual(med, {"H7_XAUUSD_eod": 360, "G9_XAUUSD_eod": 305})
        self.assertEqual([r["long_hold"] for r in rows], [True, True, False, False, True, False])

    def test_recorded_medians_are_used_not_recomputed(self):
        rows = [{"component": "H7_XAUUSD_eod", "entry_slot": s} for s in (60, 120, 600, 900)]
        V.mark_hold(rows, {"H7_XAUUSD_eod": 30})
        self.assertFalse(any(r["long_hold"] for r in rows))


class Statistics(unittest.TestCase):
    def test_a_real_gradient_is_detected(self):
        t = V.split_test(split_rows(0.3, 0.0))
        self.assertGreater(t["diff"], 0.25)
        self.assertLess(t["p_one_sided"], 0.001)

    def test_no_gradient_is_not(self):
        t = V.split_test(split_rows(0.1, 0.1))
        self.assertGreater(t["p_one_sided"], 0.05)

    def test_rows_on_one_day_are_one_cluster(self):
        r = split_rows(0.3, 0.0)
        a = V.split_test(r)
        b = V.split_test(r + [dict(x) for x in r])
        self.assertAlmostEqual(a["se"], b["se"])
        self.assertEqual(a["df"], b["df"])

    def test_needs_both_sides_in_both_halves(self):
        t = V.split_test(split_rows(0.3, 0.0, side=lambda k: 1))
        self.assertIsNone(t["diff"])
        self.assertEqual(t["p_one_sided"], 1.0)
        self.assertGreater(t["pooled_report_only"]["diff"], 0.25)

    def test_constant_drift_does_not_pass_t1b(self):
        """R under a constant drift: side x c x sqrt(bars left). Early entries of the majority (long) side earn more R with
        no conditional effect; the side-balanced statistic must not reject, the pooled one (report-only) would."""
        rows = []
        for k in range(1200):
            side = -1 if k % 4 == 0 else 1                       # 75 % long, as in a gold bull market
            nb = 20 + (k * 37) % 250                             # bars from entry to the end of the day
            noise = ((k * 7919) % 13 - 6) / 20.0
            rows.append({"component": "H7_XAUUSD_eod", "day": f"d{k}", "side": side, "entry_slot": 1440 - 5 * nb,
                         "R_gross": side * 0.02 * math.sqrt(nb) + noise, "R_net": 0.0})
        V.mark_hold(rows)
        t = V.split_test(rows, key="long_hold")
        self.assertGreater(t["pooled_report_only"]["diff"] / t["pooled_report_only"]["se"], 3.0)
        self.assertAlmostEqual(t["diff"], 0.0, delta=0.05)
        self.assertGreater(t["p_one_sided"], 0.05)

    def test_shared_days_are_handled_jointly(self):
        """Two symbols per day, one in each half, hit by the same day shock: the shock cancels in the difference, so the
        joint SE must be far below the naive sum of the halves' SEs (the earlier formula)."""
        rows = []
        for k in range(300):
            shock = ((k * 7919) % 101 - 50) / 25.0
            tiny = ((k * 31) % 7 - 3) / 100.0
            side = 1 if k % 3 else -1
            rows.append({"day": f"d{k}", "high": True, "side": side, "R_gross": shock + 0.1 + tiny, "R_net": 0.0})
            rows.append({"day": f"d{k}", "high": False, "side": side, "R_gross": shock - tiny, "R_net": 0.0})
        t = V.split_test(rows)
        self.assertEqual(t["shared_days"], 300)
        naive = []
        for h in (True, False):
            rs = [r for r in rows if r["high"] == h]
            m = sum(r["R_gross"] for r in rs) / len(rs)
            naive.append(math.sqrt(len(rs) / (len(rs) - 1) * sum((r["R_gross"] - m) ** 2 for r in rs)) / len(rs))
        self.assertLess(t["se"], 0.2 * math.sqrt(naive[0] ** 2 + naive[1] ** 2))
        self.assertLess(t["p_one_sided"], 0.001)

    def test_holm(self):
        self.assertEqual(V.holm([0.01, 0.04], 0.05), [True, True])
        self.assertEqual(V.holm([0.03, 0.04], 0.05), [False, False])
        self.assertEqual(V.holm([0.04, 0.001], 0.05), [True, True])
        self.assertEqual(V.secondary_verdict(0.02, None)["T2_silver"], True)
        self.assertEqual(V.secondary_verdict(0.03, None)["T2_silver"], False)


class Holdout(unittest.TestCase):
    def setUp(self):
        self.days = weekdays(datetime.date(2017, 1, 2), 330)            # crosses 2018-01-01
        self.sig = sigma_pattern(self.days)
        vr = V.vr_by_day(self.sig)
        self.high = {d: v > 1 for d, v in vr.items()}
        self.s = fake_series(self.days, self.sig)

    def read(self, r_high=0.5, r_low=-0.1):
        return V.gold_read(1.4, trades_fn=lambda *a, **k: fake_trades(self.days, self.high, r_high, r_low, sig=self.sig),
                           series_fn=lambda sym: self.s, zone=UTC)

    def test_window_constants(self):
        self.assertEqual(V.HOLDOUT_WINDOWS, {"A": datetime.date(2018, 1, 1), "B": datetime.date(2008, 12, 10)})
        self.assertIn(V.HOLDOUT, V.HOLDOUT_WINDOWS)
        self.assertEqual(V.HOLDOUT_END, V.HOLDOUT_WINDOWS[V.HOLDOUT])
        self.assertEqual(V.PA_SPAN_START, datetime.date(2008, 12, 10))

    def test_only_entries_before_the_holdout_end_and_vr_by_entry_day(self):
        rows, counts = V.holdout_rows("H7_XAUUSD_eod", 1.4, trades_fn=lambda *a, **k: fake_trades(self.days, self.high, sig=self.sig),
                                      series_fn=lambda sym: self.s, zone=UTC)
        self.assertTrue(rows)
        self.assertTrue(all(r["day"] < V.HOLDOUT_END for r in rows))
        self.assertTrue(all(r["high"] == self.high[r["day"]] for r in rows))
        self.assertTrue(all(abs(r["R_gross"] - r["R_net"] - 0.01) < 1e-12 for r in rows))
        self.assertTrue(all(r["entry_slot"] == 600 and r["nb_planned"] == 1 for r in rows))

    def test_gold_read_passes_on_a_gradient_and_fails_without(self):
        good = self.read()
        self.assertTrue(good["T1_verdict"]["T1a_volatility"])
        self.assertFalse(good["T1_verdict"]["T1b_hold_length"])      # every entry at one slot: no early half
        self.assertEqual(good["hold_medians"]["H7_XAUUSD_eod"], 600)
        flat = self.read(0.1, 0.1)
        self.assertFalse(flat["T1_verdict"]["T1a_volatility"])
        self.assertIn("stop_quartiles", good["diagnostics"]["gold"])
        self.assertIn("report_only_before_pa_span", good)            # window A reports window B's span

    def test_high_half_must_be_net_positive(self):
        neg = self.read(-0.2, -0.8)
        self.assertLess(neg["T1a_gold_volatility"]["p_one_sided"], 0.05)
        self.assertFalse(neg["T1_verdict"]["T1a_volatility"])

    def test_hold_length_split_is_its_own_test(self):
        rows = []
        for k in range(400):
            noise = ((k * 7919) % 13 - 6) / 20.0
            early = bool(k % 2)
            rows.append({"component": "H7_XAUUSD_eod", "day": f"d{k}", "high": bool((k // 2) % 2),
                         "side": 1 if (k // 4) % 3 else -1, "entry_slot": 120 if early else 1200,
                         "R_gross": (0.3 if early else 0.0) + noise, "R_net": 0.1})
        V.mark_hold(rows)
        tb = V.split_test(rows, key="long_hold")
        ta = V.split_test(rows)
        self.assertLess(tb["p_one_sided"], 0.001)
        self.assertGreater(ta["p_one_sided"], 0.05)


def crypto_candles(n_days, start=datetime.date(2022, 1, 1), bars=288):
    """Complete UTC days with a slow uptrend; the zig-zag amplitude switches every 7 days (volatility regimes)."""
    out, px = [], 100.0
    for k in range(n_days):
        d = start + datetime.timedelta(days=k)
        step = 0.0004 if (k // 7) % 2 else 0.0001
        prev = px * (1 - step)
        for j in range(bars):
            c = px * (1 + step * (1 if j % 2 else -1))
            t = datetime.datetime(d.year, d.month, d.day, tzinfo=UTC) + datetime.timedelta(minutes=5 * j)
            out.append({"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "open": prev, "high": max(prev, c),
                        "low": min(prev, c), "close": c})
            prev = c
        px *= 1.001
    return out


def flat_cost(t_in, t_out, stat="median"):
    return 0.001


class Crypto(unittest.TestCase):
    def test_rows_are_costed_labelled_and_vr_is_point_in_time(self):
        c = crypto_candles(175)
        rows, counts = V.crypto_rows("X", c, UTC, "2099-01-01T00:00:00Z", flat_cost)
        self.assertTrue(rows)
        self.assertEqual({r["rule"] for r in rows}, {"H7", "G9"})
        self.assertTrue({True, False} <= {r["high"] for r in rows})
        self.assertTrue(all(r["cost_R"] > 0 and r["R_net"] < r["R_gross"] for r in rows))
        last = max(r["day"] for r in rows)
        cut = [x for x in c if x["time"] < last.isoformat()]
        rows_t, _ = V.crypto_rows("X", cut, UTC, "2099-01-01T00:00:00Z", flat_cost)
        before = {(r["rule"], r["day"]): r["vr"] for r in rows if r["day"] < last - datetime.timedelta(days=1)}
        after = {(r["rule"], r["day"]): r["vr"] for r in rows_t if (r["rule"], r["day"]) in before}
        self.assertEqual(before, after)

    def test_no_cost_model_is_refused(self):
        with self.assertRaises(ValueError):
            V.crypto_rows("X", crypto_candles(40), UTC, "2099-01-01T00:00:00Z", None)

    def test_group_b_start_day_drops_earlier_events_but_keeps_their_vr_history(self):
        c = crypto_candles(175)
        full, _ = V.crypto_rows("X", c, UTC, "2099-01-01T00:00:00Z", flat_cost)
        start = datetime.date(2022, 6, 1)
        late, counts = V.crypto_rows("X", c, UTC, "2099-01-01T00:00:00Z", flat_cost, start_day=start)
        self.assertTrue(late)
        self.assertTrue(all(r["day"] >= start for r in late))
        self.assertEqual({(r["rule"], r["day"]): r["vr"] for r in late},
                         {(r["rule"], r["day"]): r["vr"] for r in full if r["day"] >= start})


class CxClosure(unittest.TestCase):
    AMEND = {"tag": "[CX-P1]", "end": "2026-12-31", "members": {"A": ["ADAUSD", "DOTUSD"], "B": ["BTCUSD"]}}

    def read(self, group, name, advances):
        return {"meta": {"tag": "[CX-P1]", "group": group, "read": name}, "verdicts": {"T1": {"advances": advances}}}

    def test_every_scheduled_read_is_required(self):
        with self.assertRaises(SystemExit):
            V.cx_closure(self.AMEND, [self.read("A", "discovery", True), self.read("B", "single", False)])
        with self.assertRaises(SystemExit):
            V.cx_closure(self.AMEND, [self.read("A", "discovery", False)])          # group B missing

    def test_a_failed_gate_retires_later_windows_and_they_are_disclosed(self):
        groups, end, retired = V.cx_closure(self.AMEND, [self.read("A", "discovery", False),
                                                         self.read("B", "single", False)])
        self.assertEqual(retired, ["A|confirmation", "A|exposed"])
        self.assertEqual(end, datetime.date(2026, 12, 31))
        self.assertEqual(groups, {"A": ["ADAUSD", "DOTUSD"], "B": ["BTCUSD"]})

    def test_wrong_tag_or_duplicate_is_refused(self):
        bad = dict(self.read("A", "discovery", False), meta={"tag": "[H7X]", "group": "A", "read": "discovery"})
        with self.assertRaises(SystemExit):
            V.cx_closure(self.AMEND, [bad, self.read("B", "single", False)])
        with self.assertRaises(SystemExit):
            V.cx_closure(self.AMEND, [self.read("A", "discovery", False)] * 2 + [self.read("B", "single", False)])
        with self.assertRaises(SystemExit):
            V.cx_closure(dict(self.AMEND, tag="x"), [])


class DryRun(unittest.TestCase):
    def test_counts_only_from_the_real_detectors(self):
        EC = V._ec()
        s = EC.Series("XAUUSD", crypto_candles(175, start=datetime.date(2016, 1, 1)), UTC, end="9999-12-31T00:00:00Z")
        out = V.dry_counts(series_fn=lambda sym: s, zone=UTC)
        self.assertEqual(set(out), set(V.GOLD + V.SILVER))
        for c in out.values():
            self.assertTrue(set(c) <= {"high", "low", "no_vr", "before_pa_span", "long_hold", "short_hold",
                                       "median_entry_slot"})
            self.assertFalse(any(isinstance(v, float) for k, v in c.items() if k != "median_entry_slot"))
        self.assertGreater(out["H7_XAUUSD_eod"].get("high", 0) + out["H7_XAUUSD_eod"].get("low", 0)
                           + out["H7_XAUUSD_eod"].get("no_vr", 0), 0)


class Forward(unittest.TestCase):
    def test_forward_rows_filter_gross_r_and_slot(self):
        days = weekdays(datetime.date(2026, 1, 5), 300)
        sig = sigma_pattern(days)
        s = fake_series(days, sig)
        seal = days[200]
        log = [{"component": "H7_XAUUSD_eod", "status": "closed", "stop_k": 1.4, "entry_time": s.T[k], "side": 1,
                "entry": 100.0, "exit": 101.0, "stop_distance": 2.0, "R": 0.45} for k in (150, 210, 250)]
        log.append(dict(log[1], stop_k=2.0))
        log.append(dict(log[1], status="open"))
        log.append(dict(log[1], component="E5_XAUUSD_24"))
        rows, missing = V.forward_rows(log, s, seal, UTC)
        self.assertEqual(len(rows) + missing, 2)
        self.assertTrue(all(abs(r["R_gross"] - 0.5) < 1e-12 and r["R_net"] == 0.45 and r["entry_slot"] == 600
                            for r in rows))

    def test_forward_tests_only_what_passed_and_use_recorded_medians(self):
        rows = [{"component": "H7_XAUUSD_eod", "day": f"d{k}", "high": bool(k % 2), "side": 1 if k % 3 else -1,
                 "entry_slot": 100 + 10 * (k % 7), "R_gross": 0.3 * (k % 2) + ((k * 7919) % 13 - 6) / 20.0,
                 "R_net": 0.2} for k in range(300)]
        out = V.forward_tests(rows, {"a"}, {"H7_XAUUSD_eod": 130})
        self.assertEqual(set(out), {"a"})
        self.assertTrue(out["a"]["passed"])
        b = V.forward_tests(rows, {"b"}, {"H7_XAUUSD_eod": 50})        # every forward entry is later than 50
        self.assertEqual(b["b"]["n_high"], 0)
        self.assertFalse(b["b"]["passed"])

    def test_forward_due(self):
        seal = datetime.date(2026, 10, 10)
        self.assertFalse(V.forward_due(149, seal, seal + datetime.timedelta(days=364)))
        self.assertTrue(V.forward_due(150, seal, seal))
        self.assertTrue(V.forward_due(0, seal, seal + datetime.timedelta(days=365)))


class Guard(unittest.TestCase):
    def test_draft_is_refused(self):
        with self.assertRaises(SystemExit):
            V.G.require_sealed(ROOT, "docs/plans/2026-10-04-vc-volatility-condition-preregistration-DRAFT.md", V.TAG)

    def test_prereg_constant_is_the_sealed_name(self):
        self.assertFalse(V.PREREG.endswith("-DRAFT.md"))
        self.assertTrue(os.path.exists(os.path.join(ROOT, V.PREREG.replace(".md", "-DRAFT.md"))))

    def test_draft_text_does_not_pass_the_sealed_check(self):
        with open(os.path.join(ROOT, V.PREREG.replace(".md", "-DRAFT.md")), encoding="utf-8") as fh:
            text = fh.read()
        with self.assertRaises(SystemExit):
            V.G.check_sealed_text(text, V.PREREG, V.TAG)

    def test_code_files_exist(self):
        self.assertEqual(len(V.CODE), len(set(V.CODE)))
        for p in V.CODE:
            self.assertTrue(os.path.exists(os.path.join(ROOT, p)), p)

    def test_code_lists_every_module_a_read_loads(self):
        """Every repository module the three reads load (fresh, under the trace) is in CODE -- the guard's runtime check
        would otherwise refuse the read."""
        V.G.trace_start(ROOT)
        V._load("edge_census", "scripts/research/edge_census.py")
        V._load("book_sim", "scripts/research/book_sim.py")
        FF = V._load("fvg_forward", "scripts/research/fvg_forward.py")
        FF.live_path("XAUUSD")
        V.server_zone()
        import history_store  # noqa: F401
        import real_costs  # noqa: F401
        V.G.require_covered(V.CODE)
        loaded = set()
        for m in list(sys.modules.values()):
            f = getattr(m, "__file__", None)
            if not f:
                continue
            rel = os.path.relpath(os.path.abspath(f), ROOT).replace(os.sep, "/")
            if rel.startswith("scripts/") and not rel.startswith("scripts/tests/") and rel.endswith(".py"):
                loaded.add(rel)
        self.assertEqual(sorted(loaded - set(V.CODE)), [])


if __name__ == "__main__":
    unittest.main()
