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


def sim_trade(rng, nb, mu, k=1.4):
    """Synthetic trade (no market data): Gaussian 1-sigma bars with per-bar drift `mu` in the trade's direction, stop at
    k x sqrt(nb) (filled at the stop), time exit after nb bars. R in stop units."""
    dist, x = k * math.sqrt(nb), 0.0
    for _ in range(nb):
        x += mu + rng.gauss(0.0, 1.0)
        if x <= -dist:
            return -1.0
    return x / dist


def sim_rows(seed, mu_of_nb, n=4000, late_share=0.1):
    """Synthetic VC rows: planned bars uniform 20-260, except `late_share` of entries in the last bars (1-19); 60 / 40 long /
    short; one day per trade."""
    import random
    rng = random.Random(seed)
    rows = []
    for k in range(n):
        nb = rng.randint(1, 19) if rng.random() < late_share else rng.randint(20, 260)
        side = 1 if rng.random() < 0.6 else -1
        r = sim_trade(rng, nb, mu_of_nb(nb))
        rows.append({"component": "H7_XAUUSD_eod", "day": f"d{k}", "side": side, "entry_slot": 1440 - 5 * nb,
                     "nb_planned": nb, "R_gross": r, "R_bar": V.per_bar(r, nb), "R_net": r})
    V.mark_hold(rows)
    return rows


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
        """R under a constant MARKET drift: side x c x sqrt(bars left). Early entries of the majority (long) side earn more R
        with no conditional effect; the side-balanced statistic must not reject, the pooled one (report-only) would."""
        rows = []
        for k in range(1200):
            side = -1 if k % 4 == 0 else 1                       # 75 % long, as in an XAUUSD bull market
            nb = 20 + (k * 37) % 250                             # bars from entry to the end of the day
            noise = ((k * 7919) % 13 - 6) / 20.0
            g = side * 0.02 * math.sqrt(nb) + noise
            rows.append({"component": "H7_XAUUSD_eod", "day": f"d{k}", "side": side, "entry_slot": 1440 - 5 * nb,
                         "nb_planned": nb, "R_gross": g, "R_bar": V.per_bar(g, nb), "R_net": 0.0})
        V.mark_hold(rows)
        t = V.split_test(rows, key="long_hold")
        self.assertGreater(t["pooled_report_only"]["diff"] / t["pooled_report_only"]["se"], 3.0)
        self.assertAlmostEqual(t["diff"], 0.0, delta=0.05)
        self.assertGreater(t["p_one_sided"], 0.05)
        self.assertGreater(V.split_test(rows, key="long_hold", value="R_bar", row_weight=V.nb_weight)["p_one_sided"], 0.05)

    def test_constant_edge_does_not_pass_t1b(self):
        """R under a constant per-bar EDGE in the trade's direction: c x sqrt(bars left) for BOTH sides (the review's
        item 11). Side balancing cannot remove it: the raw-R T1b rejects with no conditional effect. T1b's nb-weighted
        R_bar (R x sqrt(NB_REF / bars)) has the same mean at every entry time and must not reject; the gold read uses it."""
        rows = []
        for k in range(1200):
            side = -1 if k % 3 == 0 else 1
            nb = 20 + (k * 37) % 250
            noise = ((k * 7919) % 13 - 6) / 20.0
            g = 0.03 * math.sqrt(nb) + noise
            rows.append({"component": "H7_XAUUSD_eod", "day": f"d{k}", "side": side, "entry_slot": 1440 - 5 * nb,
                         "nb_planned": nb, "R_gross": g, "R_bar": V.per_bar(g, nb), "R_net": 0.1})
        V.mark_hold(rows)
        raw = V.split_test(rows, key="long_hold")
        self.assertLess(raw["p_one_sided"], 0.001)               # the mechanical gradient
        self.assertGreater(raw["mean_bars_high"], raw["mean_bars_low"])
        per = V.split_test(rows, key="long_hold", value="R_bar", row_weight=V.nb_weight)
        self.assertEqual((per["statistic"], per["weight"]), ("R_bar", "nb_weight"))
        self.assertGreater(per["p_one_sided"], 0.05)
        t = V._tests_on({"H7_XAUUSD_eod": rows, "G9_XAUUSD_eod": []})
        self.assertEqual((t["T1b_xau_hold_length"]["statistic"], t["T1b_xau_hold_length"]["weight"]),
                         ("R_bar", "nb_weight"))
        self.assertEqual(t["per_component_hold_length"]["H7_XAUUSD_eod"]["weight"], "nb_weight")
        self.assertEqual((t["T1b_raw_R_report_only"]["statistic"], t["T1b_raw_R_report_only"]["weight"]), ("R_gross", None))
        self.assertEqual((t["T1a_xau_volatility"]["statistic"], t["T1a_xau_volatility"]["weight"]), ("R_gross", None))

    def test_late_entries_do_not_rule_t1b(self):
        """Review (2026-10-04, fix round): Var(R_bar) grows like 1 / nb, so with entries in the last bars an UNWEIGHTED mean
        of R_bar is noisy and, under the stop, biased against early entries. Synthetic trades with stops, a constant
        per-bar edge (pooled mean R ~0.09) and 10 % of entries at 1-19 bars: the nb-weighted T1b stays near 0 with a much
        smaller SE; a per-bar edge three times as large for early entries is found (expected t ~6 at 4,000 trades)."""
        mu = 0.0116
        rows = sim_rows(11, lambda nb: mu)
        w = V.split_test(rows, key="long_hold", value="R_bar", row_weight=V.nb_weight)
        u = V.split_test(rows, key="long_hold", value="R_bar")
        self.assertGreater(sum(r["R_gross"] for r in rows) / len(rows), 0.05)
        self.assertLess(abs(w["diff"]), 2.5 * w["se"])
        self.assertGreater(w["p_one_sided"], 0.01)                   # (a null draw: p < 0.05 would come 1 seed in ~30)
        self.assertGreater(u["se"], 1.3 * w["se"])                  # the late entries rule the unweighted mean
        early = sim_rows(12, lambda nb: 3 * mu if nb > 140 else mu)
        self.assertLess(V.split_test(early, key="long_hold", value="R_bar", row_weight=V.nb_weight)["p_one_sided"], 0.01)

    def test_weighted_cell_mean_and_its_se(self):
        """The weighted cell mean is sqrt(NB_REF) x sum(R x sqrt(nb)) / sum(nb); equal weights give the unweighted test; the
        CR1 SE agrees with the analytic SE of the weighted means under independent noise of known sd."""
        import random
        rng = random.Random(5)
        rows = []
        for k in range(4000):
            nb = 1 + (k * 37) % 288
            rows.append({"day": f"d{k}", "long_hold": bool(k % 2), "side": 1 if k % 5 else -1, "nb_planned": nb,
                         "R_bar": rng.gauss(0.0, 1.0), "R_net": 0.0})
        t = V.split_test(rows, key="long_hold", value="R_bar", row_weight=V.nb_weight)
        cells = {}
        for r in rows:
            cells.setdefault((r["side"], r["long_hold"]), []).append(r)
        var = 0.0
        for rs in cells.values():
            a = [V.nb_weight(r) for r in rs]
            var += 0.25 * sum(x * x for x in a) / sum(a) ** 2               # sd 1
        self.assertAlmostEqual(t["se"] / math.sqrt(var), 1.0, delta=0.06)
        hi = [r for r in rows if r["long_hold"]]
        r_gross = [r["R_bar"] / math.sqrt(V.NB_REF / r["nb_planned"]) for r in hi]
        direct = math.sqrt(V.NB_REF) * sum(g * math.sqrt(r["nb_planned"]) for g, r in zip(r_gross, hi)) / \
            sum(r["nb_planned"] for r in hi)
        self.assertAlmostEqual(t["mean_high"], direct)
        flat = [dict(r, nb_planned=144) for r in rows]
        a = V.split_test(flat, key="long_hold", value="R_bar", row_weight=V.nb_weight)
        b = V.split_test(flat, key="long_hold", value="R_bar")
        self.assertAlmostEqual(a["diff"], b["diff"])
        self.assertAlmostEqual(a["se"], b["se"])

    def test_per_bar_scale_does_not_change_the_p_value(self):
        rows = split_rows(0.3, 0.0, key="long_hold")
        for k, r in enumerate(rows):
            r["nb_planned"] = 10 + k % 200
            r["R_bar"] = V.per_bar(r["R_gross"], r["nb_planned"])
            r["R_half"] = r["R_bar"] / 2.0                          # another NB_REF: a common factor
        a = V.split_test(rows, key="long_hold", value="R_bar")
        b = V.split_test(rows, key="long_hold", value="R_half")
        self.assertAlmostEqual(a["p_one_sided"], b["p_one_sided"])
        self.assertAlmostEqual(V.per_bar(0.5, V.NB_REF), 0.5)
        self.assertAlmostEqual(V.per_bar(0.5, 4 * V.NB_REF), 0.25)

    def test_rows_without_a_key_value_are_left_out(self):
        rows = split_rows(0.3, 0.0, key="long_hold")
        t0 = V.split_test(rows, key="long_hold")
        t1 = V.split_test(rows + [dict(rows[0], long_hold=None, R_gross=99.0)], key="long_hold")
        self.assertEqual((t0["diff"], t0["n_high"], t0["n_low"]), (t1["diff"], t1["n_high"], t1["n_low"]))

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
        self.days = weekdays(datetime.date(2007, 6, 4), 420)            # crosses 2008-12-10 (window B's end)
        self.sig = sigma_pattern(self.days)
        vr = V.vr_by_day(self.sig)
        self.high = {d: v > 1 for d, v in vr.items()}
        self.s = fake_series(self.days, self.sig)

    def read(self, r_high=0.5, r_low=-0.1):
        return V.xau_read(1.4, trades_fn=lambda *a, **k: fake_trades(self.days, self.high, r_high, r_low, sig=self.sig),
                           series_fn=lambda sym: self.s, zone=UTC)

    def test_window_constants(self):
        """Lead decision 2026-10-04: window B is decisive, window A report-only."""
        self.assertEqual(V.HOLDOUT_WINDOWS, {"A": datetime.date(2018, 1, 1), "B": datetime.date(2008, 12, 10)})
        self.assertEqual((V.HOLDOUT, V.REPORT_WINDOW), ("B", "A"))
        self.assertEqual(V.HOLDOUT_END, V.HOLDOUT_WINDOWS[V.HOLDOUT])
        self.assertEqual(V.REPORT_END, datetime.date(2018, 1, 1))
        self.assertEqual(V.LOAD_END, datetime.date(2018, 1, 1))
        self.assertEqual(V.PA_SPAN_START, datetime.date(2008, 12, 10))

    def test_only_entries_before_the_holdout_end_and_vr_by_entry_day(self):
        rows, info = V.holdout_rows("H7_XAUUSD_eod", 1.4,
                                    trades_fn=lambda *a, **k: fake_trades(self.days, self.high, sig=self.sig),
                                    series_fn=lambda sym: self.s, zone=UTC)
        self.assertTrue(rows)
        self.assertTrue(all(r["day"] < V.HOLDOUT_END for r in rows))
        self.assertTrue(all(r["high"] == self.high[r["day"]] for r in rows))
        self.assertTrue(all(abs(r["R_gross"] - r["R_net"] - 0.01) < 1e-12 for r in rows))
        self.assertTrue(all(r["entry_slot"] == 600 and r["nb_planned"] == 1 for r in rows))
        self.assertTrue(all(abs(r["R_bar"] - r["R_gross"] * math.sqrt(V.NB_REF)) < 1e-9 for r in rows))
        self.assertEqual(info["without_vr"], len(info["no_vr_days"]))

    def test_xau_read_passes_on_a_gradient_and_fails_without(self):
        good = self.read()
        self.assertTrue(good["T1_verdict"]["T1a_volatility"])
        self.assertFalse(good["T1_verdict"]["T1b_hold_length"])      # every entry at one slot: no early half
        self.assertEqual(good["hold_medians"]["H7_XAUUSD_eod"], 600)
        flat = self.read(0.1, 0.1)
        self.assertFalse(flat["T1_verdict"]["T1a_volatility"])
        self.assertIn("stop_quartiles", good["diagnostics"]["xau"])
        rep = good["report_only_window_A"]                          # window A: report-only, the wider window
        self.assertEqual(rep["end"], "2018-01-01")
        c = "H7_XAUUSD_eod"
        self.assertGreater(rep["counts"][c]["with_vr"], good["counts"][c]["with_vr"])
        self.assertEqual(good["T1b_xau_hold_length"]["statistic"], "R_bar")
        self.assertIn("T1b_raw_R_report_only", good)

    def test_decisive_rows_end_before_window_b_and_report_rows_reuse_its_medians(self):
        out = V.xau_read(1.4, trades_fn=lambda *a, **k: fake_trades(self.days, self.high, sig=self.sig),
                          series_fn=lambda sym: self.s, zone=UTC, keep_rows=True)
        rows = out["rows"]["H7_XAUUSD_eod"]
        late = [r for r in rows if r["day"] >= V.HOLDOUT_END]
        self.assertTrue(late)
        self.assertTrue(all(r["long_hold"] is (r["entry_slot"] < out["hold_medians"]["H7_XAUUSD_eod"]) for r in rows))
        self.assertEqual(out["counts"]["H7_XAUUSD_eod"]["with_vr"], sum(1 for r in rows if r["day"] < V.HOLDOUT_END))

    def test_silver_without_a_vr_in_window_b_is_not_run(self):
        """Silver's history starts 2008-11-07: no trade has the 125 days of sigma a VR needs before 2008-12-10."""
        ag_days = [d for d in self.days if d >= datetime.date(2008, 11, 10)]
        ag_sig = {d: (2.0 if k % 2 else 0.5) for k, d in enumerate(ag_days)}
        ag = fake_series(ag_days, ag_sig)
        ag_high = {d: v > 1 for d, v in V.vr_by_day(ag_sig).items()}

        def trades(sym, *a, **k):
            return fake_trades(ag_days, ag_high, sig=ag_sig) if sym == "XAGUSD" else \
                fake_trades(self.days, self.high, sig=self.sig)

        out = V.xau_read(1.4, trades_fn=trades, series_fn=lambda sym: ag if sym == "XAGUSD" else self.s, zone=UTC)
        self.assertIn("not_run", out["T2_silver"])
        self.assertEqual(out["T2_silver"]["p_one_sided"], 1.0)
        self.assertEqual(V.secondary_verdict(out["T2_silver"]["p_one_sided"], 0.03)["T3_crypto"], False)
        self.assertEqual(V.secondary_verdict(out["T2_silver"]["p_one_sided"], 0.02)["T3_crypto"], True)

    def test_high_half_must_be_net_positive(self):
        neg = self.read(-0.2, -0.8)
        self.assertLess(neg["T1a_xau_volatility"]["p_one_sided"], 0.05)
        self.assertFalse(neg["T1_verdict"]["T1a_volatility"])

    def test_entry_on_the_first_bar_of_a_day_is_flagged(self):
        days = weekdays(datetime.date(2008, 1, 7), 3)
        s = types.SimpleNamespace()
        s.T, s.dt, s.sday, s.day_rows = [], [], [], {}
        for d in days:                                              # two bars a day, 10:00 and 10:05 UTC
            for m in (0, 5):
                s.day_rows.setdefault(d, []).append(len(s.T))
                s.T.append(f"{d.isoformat()}T10:{m:02d}:00Z")
                s.dt.append(datetime.datetime(d.year, d.month, d.day, 10, m, tzinfo=UTC))
                s.sday.append(d)
        tr = [{"symbol": "XAUUSD", "entry_time": s.T[k], "R": 0.1, "cost_R": 0.0, "stop_bp": 50.0, "side": 1, "exit": "time"}
              for k in (0, 1, 2, 3)]
        rows = V.book_rows(tr, s, UTC)
        self.assertEqual([r["entry_next_day"] for r in rows], [False, False, True, False])   # bar 0 has no signal before it
        self.assertEqual([r["nb_planned"] for r in rows], [2, 1, 2, 1])

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
    KEYS = {"high", "low", "no_vr", "entry_next_day", "no_research_sigma", "high_long_hold", "high_short_hold",
            "low_long_hold", "low_short_hold", "window", "end", "planned_bars", "cells"}

    def test_counts_only_from_the_real_detectors(self):
        EC = V._ec()
        s = EC.Series("XAUUSD", crypto_candles(400, start=datetime.date(2007, 11, 1)), UTC, end="9999-12-31T00:00:00Z")
        out = V.dry_counts(series_fn=lambda sym: s, zone=UTC)
        self.assertEqual(set(out), set(V.GOLD + V.SILVER) | {"xau_pooled"})
        for c in (out[x] for x in V.GOLD + V.SILVER):
            self.assertEqual(set(c), {"median_entry_slot", "decisive", "report_only"})
            self.assertEqual((c["decisive"]["window"], c["report_only"]["window"]), ("B", "A"))
            for w in ("decisive", "report_only"):
                self.assertTrue(set(c[w]) <= self.KEYS, set(c[w]) - self.KEYS)
                self.assertFalse(any(isinstance(v, float) for v in c[w].values()))
                self.assertIn("no_research_sigma", c[w])
                self.assertTrue(all(isinstance(v, int) for v in c[w]["planned_bars"].values()))
                for cell in c[w]["cells"].values():
                    self.assertTrue(all(isinstance(v, int) for v in cell.values()))
                n_vr = c[w].get("high", 0) + c[w].get("low", 0)
                self.assertEqual(c[w]["planned_bars"].get("n", 0), n_vr)
                self.assertEqual(sum(v["n"] for k, v in c[w]["cells"].items() if k.endswith(("|high", "|low"))), n_vr)
            n_dec = sum(c["decisive"].get(k, 0) for k in ("high", "low", "no_vr"))
            n_rep = sum(c["report_only"].get(k, 0) for k in ("high", "low", "no_vr"))
            self.assertGreaterEqual(n_rep, n_dec)                   # A contains B
        h7 = out["H7_XAUUSD_eod"]["decisive"]
        self.assertGreater(h7.get("high", 0) + h7.get("low", 0) + h7.get("no_vr", 0), 0)
        held = sum(h7.get(k, 0) for k in ("high_long_hold", "high_short_hold", "low_long_hold", "low_short_hold"))
        self.assertEqual(held, h7.get("high", 0) + h7.get("low", 0))
        for w in ("decisive", "report_only"):                       # pooled XAUUSD = H7 + G9, cell by cell
            p = out["xau_pooled"][w]
            for k, cell in p["cells"].items():
                parts = [out[c][w]["cells"].get(k, {"n": 0, "bars": 0, "days": 0}) for c in V.GOLD]
                self.assertEqual((cell["n"], cell["bars"]), (sum(x["n"] for x in parts), sum(x["bars"] for x in parts)))
                self.assertLessEqual(cell["days"], sum(x["days"] for x in parts))
            self.assertEqual(set(p), {"mean_bars", "vr_halves_bars_gap", "se_per_sd", "window", "end", "cells",
                                      "planned_bars"})

    def test_power_inputs_formula(self):
        """se_per_sd = the balanced contrast's SE per unit sd of R (trades independent): T1a over the VR cells with 1 / n,
        T1b over the hold cells with NB_REF / bars; equal at a mean hold of NB_REF bars, larger for T1b when the short-hold
        half holds fewer bars."""
        cells = {f"side={s}|{h}": {"n": 100, "bars": 100 * V.NB_REF, "days": 100} for s in V.SIDES
                 for h in ("high", "low", "long_hold", "short_hold")}
        p = V.power_inputs(cells)
        self.assertAlmostEqual(p["se_per_sd"]["T1a"], 0.1)
        self.assertAlmostEqual(p["se_per_sd"]["T1b"], 0.1)
        self.assertAlmostEqual(p["se_per_sd"]["T1b_raw_R"], 0.1)
        self.assertAlmostEqual(p["vr_halves_bars_gap"], 0.0)
        for s in V.SIDES:
            cells[f"side={s}|short_hold"]["bars"] = 100 * V.NB_REF // 4
            cells[f"side={s}|low"]["bars"] = 100 * 120
        p = V.power_inputs(cells)
        self.assertAlmostEqual(p["se_per_sd"]["T1b"], math.sqrt(0.25 * (2 / 100 + 2 * 4 / 100)))
        self.assertAlmostEqual(p["vr_halves_bars_gap"], (144 - 120) / 120)
        self.assertIsNone(V.power_inputs({})["se_per_sd"]["T1a"])


class Forward(unittest.TestCase):
    def test_forward_rows_filter_gross_r_and_slot(self):
        days = weekdays(datetime.date(2026, 1, 5), 300)
        sig = sigma_pattern(days)
        s = fake_series(days, sig)
        first = days[200]
        log = [{"component": "H7_XAUUSD_eod", "status": "closed", "stop_k": 1.4, "entry_time": s.T[k],
                "exit_time": s.T[k].replace("T10:00", "T20:00"), "side": 1, "entry": 100.0, "exit": 101.0,
                "stop_distance": 2.0, "R": 0.45} for k in (150, 200, 210, 250)]
        log.append(dict(log[2], stop_k=2.0))
        log.append(dict(log[2], status="open"))
        log.append(dict(log[2], component="E5_XAUUSD_24"))
        seen = []
        costs = types.SimpleNamespace(round_trip_at=lambda t_in, t_out, stat="median": seen.append((t_in, t_out)) or 0.0002)
        rows, missing = V.forward_rows(log, s, first, UTC, costs)
        self.assertEqual(len(rows) + missing, 3)                    # days[200] (the first forward day) onwards
        nb = V.bars_to_day_end(s.dt[210], UTC)                     # 10:00 UTC -> 14 h to midnight -> 168 bars
        self.assertEqual(nb, 168)
        # R_net re-priced at the read's cost model: (gross - round trip x entry) / stop distance; the log's R kept apart
        self.assertTrue(all(abs(r["R_gross"] - 0.5) < 1e-12 and abs(r["R_net"] - 0.49) < 1e-12 and r["R_net_log"] == 0.45
                            and abs(r["cost_R"] - 0.01) < 1e-12 and r["entry_slot"] == 600 and r["nb_planned"] == nb
                            and abs(r["R_bar"] - V.per_bar(0.5, nb)) < 1e-12 for r in rows))
        self.assertTrue(all(t_in.hour == 10 and t_out.hour == 20 and t_in.tzinfo is not None for t_in, t_out in seen))

    def test_the_first_forward_day_is_a_server_day(self):
        """A row entering in the last bar of the seal's server day is not forward; the next server day's first bar is."""
        z = V.server_zone()
        row = {"component": "G9_XAUUSD_eod", "status": "closed", "stop_k": 1.4}
        first = datetime.date(2026, 10, 6)
        self.assertFalse(V.is_forward_row(dict(row, entry_time="2026-10-05T20:55:00Z"), first, z))  # 23:55 server, 10-05
        self.assertTrue(V.is_forward_row(dict(row, entry_time="2026-10-05T21:00:00Z"), first, z))   # 00:00 server, 10-06
        self.assertFalse(V.is_forward_row(dict(row, entry_time="2026-10-05T21:00:00Z", stop_k=2.0), first, z))
        self.assertFalse(V.is_forward_row({"component": "G9_XAUUSD_eod", "status": "refused"}, first, z))

    def test_the_xau_read_must_be_window_b_with_a_verdict(self):
        good = {"meta": {"tag": V.TAG, "read": "xau-holdout", "holdout": V.HOLDOUT},
                "primary": {"T1_verdict": {"T1a_volatility": True}, "hold_medians": {"H7_XAUUSD_eod": 600}}}
        self.assertEqual(V.xau_primary(good), good["primary"])
        for bad in (dict(good, meta=dict(good["meta"], holdout="A")), dict(good, primary={"T1_verdict": {}}),
                    {"meta": {}, "primary": good["primary"]}):
            with self.assertRaises(SystemExit):
                V.xau_primary(bad)

    def test_bars_to_day_end_is_the_paper_logs_count(self):
        FF = V._load("fvg_forward", "scripts/research/fvg_forward.py")
        z = V.server_zone()
        s = types.SimpleNamespace(dt=[datetime.datetime(2026, 1, 6, h, m, tzinfo=UTC) for h, m in
                                      ((0, 0), (8, 35), (13, 5), (21, 55), (22, 0))] +
                                     [datetime.datetime(2026, 7, 7, 20, 55, tzinfo=UTC)])
        for i, t in enumerate(s.dt):
            self.assertEqual(V.bars_to_day_end(t, z), FF.bars_to_day_end(s, i), t)

    def test_forward_tests_only_what_passed_and_use_recorded_medians(self):
        rows = []
        for k in range(300):
            g = 0.3 * (k % 2) + ((k * 7919) % 13 - 6) / 20.0
            rows.append({"component": "H7_XAUUSD_eod", "day": f"d{k}", "high": bool(k % 2), "side": 1 if k % 3 else -1,
                         "entry_slot": 100 + 10 * (k % 7), "nb_planned": V.NB_REF, "R_gross": g,
                         "R_bar": V.per_bar(g, V.NB_REF), "R_net": 0.2})
        out = V.forward_tests(rows, {"a"}, {"H7_XAUUSD_eod": 130})
        self.assertEqual(set(out), {"a"})
        self.assertTrue(out["a"]["passed"])
        self.assertEqual(out["a"]["statistic"], "R_gross")
        b = V.forward_tests(rows, {"b"}, {"H7_XAUUSD_eod": 50})        # every forward entry is later than 50
        self.assertEqual(b["b"]["n_high"], 0)
        self.assertFalse(b["b"]["passed"])
        self.assertEqual(b["b"]["statistic"], "R_bar")

    def test_forward_snapshot_records_log_candles_sources_and_cost_profile(self):
        import tempfile
        from unittest import mock
        log_bytes = b'{"component": "H7_XAUUSD_eod"}\n\n{"component": "G9_XAUUSD_eod"}\n'
        candles = [{"time": "2026-10-05T00:00:00Z", "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5},
                   {"time": "2026-10-05T00:05:00Z", "open": 1.5, "high": 2.5, "low": 1.0, "close": 2.0}]
        with tempfile.TemporaryDirectory() as tmp, mock.patch("history_store.digest", return_value="h" * 64):
            store = os.path.join(tmp, "XAUUSD.5m.json")
            with open(store, "w") as fh:
                fh.write("[]")
            ff = types.SimpleNamespace(STORE_DIR=tmp, live_path=lambda sym: os.path.join(tmp, "absent.json"))
            snap = V.forward_snapshot(os.path.join(ROOT, "data", "live", "forward", "fvg-paper.jsonl"), log_bytes, candles,
                                      ff=ff)
            store_sha = V.G.file_sha256(store)
        self.assertEqual(snap["paper_log"]["rows"], 2)
        self.assertEqual(snap["paper_log"]["path"], "data/live/forward/fvg-paper.jsonl")
        self.assertEqual(len(snap["paper_log"]["sha256"]), 64)
        self.assertEqual(snap["candles"]["sha256"], V.G.candles_digest(candles))
        self.assertEqual((snap["candles"]["bars"], snap["candles"]["first"]), (2, "2026-10-05T00:00:00Z"))
        self.assertEqual(snap["sources"]["history"], "h" * 64)
        self.assertEqual(snap["sources"], {"history": "h" * 64, "forward_store": store_sha, "live_bridge": None})
        self.assertEqual(snap["cost_profile"]["name"], V._ec().COST_PROFILE)
        self.assertIn("XAUUSD", snap["cost_profile"]["spec_sha256"])

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

    def test_a_read_writes_only_its_one_output_name(self):
        """Review item 18: a read to any other path is refused before the seal is even checked (each read runs once:
        prereg_guard.require_read_once also refuses when that read's output exists or was ever committed)."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            argv = sys.argv
            sys.argv = ["edge_vc.py", "run", "--read", "xau-holdout", "--out", os.path.join(tmp, "x.json")]
            try:
                with self.assertRaises(SystemExit) as cm:
                    V.main()
            finally:
                sys.argv = argv
            self.assertIn("edge-vc-xau-holdout.json", str(cm.exception))
            self.assertFalse(os.path.exists(os.path.join(tmp, "x.json")))

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
