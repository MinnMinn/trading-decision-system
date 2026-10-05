"""scripts/research/edge_vc.py on hand-built series and trades (no history, no outcome).

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_edge_vc
(docs/plans/2026-10-04-vc-volatility-condition-preregistration-DRAFT.md [VC-P1])
"""
import collections
import contextlib
import datetime
import importlib.util
import io
import json
import math
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

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
        # VC-P1 §4 switch (the sealing dry run's gap 0.149 > 0.10): T1a on the nb-weighted R_bar; T2 keeps R_gross
        self.assertEqual((t["T1a_xau_volatility"]["statistic"], t["T1a_xau_volatility"]["weight"]), ("R_bar", "nb_weight"))
        self.assertEqual(t["per_component_volatility"]["H7_XAUUSD_eod"]["weight"], "nb_weight")
        self.assertEqual((t["T1a_raw_R_report_only"]["statistic"], t["T1a_raw_R_report_only"]["weight"]), ("R_gross", None))
        self.assertEqual((t["T2_silver"]["statistic"], t["T2_silver"]["weight"]), ("R_gross", None))

    def test_a_timing_gap_does_not_pass_t1a(self):
        """VC-P1 §4 switch, applied at the seal (dry-run gap 0.149 > 0.10): HIGH days enter earlier (more planned bars) and
        a constant per-bar edge lifts R by sqrt(bars) on both sides. The R_gross T1a (report-only now) rejects with no
        conditional effect; T1a's statistic, the nb-weighted R_bar, must not."""
        rows, evs = [], []
        for k in range(1200):
            high = bool(k % 2)
            nb = (100 if high else 20) + (k * 37) % 160
            noise = ((k * 7919) % 13 - 6) / 20.0
            g = 0.03 * math.sqrt(nb) + noise
            side = -1 if k % 3 == 0 else 1
            rows.append({"day": f"d{k}", "high": high, "side": side, "nb_planned": nb, "R_gross": g,
                         "R_bar": V.per_bar(g, nb), "R_net": 0.1})
            evs.append({"day": f"d{k}", "high": high, "long_hold": None, "side": side, "nb": nb})
        self.assertEqual((V.T1A_GAP_RULE, V.T1A_VALUE, V.T1A_WEIGHT), (0.10, "R_bar", V.nb_weight))
        self.assertGreater(V.power_inputs(V._cells(evs))["vr_halves_bars_gap"], V.T1A_GAP_RULE)   # the rule's trigger
        self.assertLess(V.split_test(rows)["p_one_sided"], 0.001)                                 # R_gross: mechanical
        t1a = V.split_test(rows, value=V.T1A_VALUE, row_weight=V.T1A_WEIGHT)
        self.assertGreater(t1a["p_one_sided"], 0.05)
        self.assertEqual((t1a["statistic"], t1a["weight"]), ("R_bar", "nb_weight"))

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
        """The research-mode rows (book_sim.trades-shaped, report-only since the lead decision of 2026-10-04): the tests
        below exercise the shared statistics and windows; the decisive rows are tested in PointInTime."""
        return V.xau_read(1.4, mode="research",
                          trades_fn=lambda *a, **k: fake_trades(self.days, self.high, r_high, r_low, sig=self.sig),
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
        self.assertEqual(good["mode"], "research")
        self.assertTrue(good["T1_verdict"]["T1a_volatility"])
        self.assertFalse(good["T1_verdict"]["T1b_hold_length"])      # every entry at one slot: no early half
        self.assertTrue(good["T1_verdict"]["reading"].startswith("PASS: DISCOVERY-GRADE"))
        self.assertEqual(good["hold_medians"]["H7_XAUUSD_eod"], 600)
        flat = self.read(0.1, 0.1)
        self.assertFalse(flat["T1_verdict"]["T1a_volatility"])
        self.assertTrue(flat["T1_verdict"]["reading"].startswith("NOT SHOWN (inconclusive"))    # never "lead closed"
        self.assertIn("stop_quartiles", good["diagnostics"]["xau"])
        rep = good["report_only_window_A"]                          # window A: report-only, the wider window
        self.assertEqual(rep["end"], "2018-01-01")
        c = "H7_XAUUSD_eod"
        self.assertGreater(rep["counts"][c]["with_vr"], good["counts"][c]["with_vr"])
        self.assertEqual(good["T1b_xau_hold_length"]["statistic"], "R_bar")
        self.assertIn("T1b_raw_R_report_only", good)

    def test_decisive_rows_end_before_window_b_and_report_rows_reuse_its_medians(self):
        out = V.xau_read(1.4, mode="research", trades_fn=lambda *a, **k: fake_trades(self.days, self.high, sig=self.sig),
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

        out = V.xau_read(1.4, mode="research", trades_fn=trades,
                         series_fn=lambda sym: ag if sym == "XAGUSD" else self.s, zone=UTC)
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


class FlatCosts:
    """edge_census.Costs-shaped: a fixed round trip (no cost table is read)."""
    def __init__(self, sym=None):
        self.sym = sym

    def round_trip_at(self, t_in, t_out, stat="median"):
        return 0.0001


def ftmo_candles(start, n_days, seed=1, px0=680.0):
    """Complete FTMO-shaped server days: 288 bars from 00:00 to 23:55 server time, weekdays only; a random walk with
    volatility regimes and slow trends (synthetic, no market data)."""
    import random
    zone = V.server_zone()
    rng = random.Random(seed)
    out, px, k, d = [], px0, 0, start
    while k < n_days:
        if d.weekday() < 5:
            sig = 0.0007 * math.exp(0.6 * math.sin(2 * math.pi * k / 47.0) + 0.25 * rng.gauss(0, 1))
            drift = 0.00004 * math.sin(2 * math.pi * k / 130.0)
            for m in range(0, 1440, 5):
                t = datetime.datetime(d.year, d.month, d.day, m // 60, m % 60, tzinfo=zone).astimezone(UTC)
                o = px
                px = px * math.exp(drift + sig * rng.gauss(0, 1))
                out.append({"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "open": o, "high": max(o, px) * 1.0001,
                            "low": min(o, px) * 0.9999, "close": px})
            k += 1
        d += datetime.timedelta(days=1)
    return out


class PointInTime(unittest.TestCase):
    """The decisive rows (lead decision 2026-10-04, VC-P1 §1-§2): point-in-time events and VR, the stop on the CLOCK bar
    count, book_sim's exit walk through fvg_forward.resolve_row. Synthetic FTMO-shaped bars only."""
    FAR = datetime.date(2100, 1, 1)

    @classmethod
    def setUpClass(cls):
        cls.zone = V.server_zone()
        cls.candles = ftmo_candles(datetime.date(2007, 1, 1), 320)
        EC = V._ec()
        cls.research = EC.Series("XAUUSD", cls.candles, cls.zone, end=V.HIST_END)
        cls.pit = EC.Series("XAUUSD", cls.candles, cls.zone, end=V.HIST_END, sigma_every_day=True)
        cls.causal = V.causal_density(EC.Series("XAUUSD", cls.candles, cls.zone, end=V.HIST_END, sigma_every_day=True))
        cls.BS = V._load("book_sim", "scripts/research/book_sim.py")
        cls.FF = V._load("fvg_forward", "scripts/research/fvg_forward.py")

    def rows(self, component, s, k=1.4):
        return V.pit_holdout_rows(component, k, end_day=self.FAR, series_fn=lambda sym: s, zone=self.zone,
                                  costs_fn=FlatCosts, resolve=self.FF.resolve_row)

    def test_on_complete_days_the_decisive_rows_are_book_sims_trades(self):
        """Every day dense and stored to 23:55: the clock count equals the stored one, so each decisive row IS book_sim's
        trade (same entry, bars, stop and R). Only a signal on a day's last bar differs: book_sim enters it on the next
        server day, the decisive rows drop it (the paper log's rule)."""
        last_day = self.pit.sday[-1]
        vr = V.pit_vr_by_day(self.pit)
        for c in V.GOLD:
            sym, det, hold = self.BS.COMPONENTS[c]
            with mock.patch.object(self.BS.EC, "load", lambda s, end=None: self.research), \
                    mock.patch.object(self.BS.EC, "Costs", FlatCosts):
                ref = {r["entry_time"]: r for r in V.book_rows(self.BS.trades(sym, det, hold, stop_k=1.4), self.research,
                                                                self.zone)}
            rows, info = self.rows(c, self.pit)
            self.assertGreater(len(rows), 20, c)
            for r in rows:
                b = ref[r["entry_time"]]
                self.assertEqual((r["nb_planned"], r["nb_stored"]), (b["nb_planned"], b["nb_planned"]))
                self.assertAlmostEqual(r["R_net"], b["R_net"], places=12)
                self.assertAlmostEqual(r["R_gross"], b["R_gross"], places=12)
                self.assertAlmostEqual(r["stop_bp"], b["stop_bp"], places=9)
            mine = {r["entry_time"] for r in rows}
            missing = [t for t, b in ref.items() if t not in mine and b["day"] in vr and b["day"] != last_day]
            self.assertTrue(all(ref[t]["entry_next_day"] for t in missing), c)
            self.assertTrue(set(info["unresolved_days"]) <= {last_day})

    def test_a_day_that_proves_sparse_keeps_its_event_and_the_stop_counts_the_clock(self):
        """The stored entry days of three events end 20 bars after the entry: those days turn out sparse and short of the
        rollover. Research mode loses the events (no sigma on a day that turns out sparse); the decisive rows keep them,
        with their VR, nb on the clock (more than the 21 stored bars) and the stop sized on the clock count."""
        det = self.BS.COMPONENTS["G9_XAUUSD_eod"][1]
        evs, _ = V.pit_events(self.pit, det, self.FAR)
        vr = V.pit_vr_by_day(self.pit)
        early = [ev for ev in evs if ev["day"] in vr and ev["e"] - self.pit.day_rows[ev["day"]][0] < 150]
        pick = early[3:30:10]                                            # days far apart: each one's previous day stays dense
        self.assertEqual(len(pick), 3)
        self.assertTrue(all((b["day"] - a["day"]).days > 3 for a, b in zip(pick, pick[1:])))
        cut = {ev["day"]: self.pit.T[ev["e"] + 20] for ev in pick}
        zone = self.zone
        kept = [b for b in self.candles if V.server_day_of(b["time"], zone) not in cut
                or b["time"] <= cut[V.server_day_of(b["time"], zone)]]
        EC = V._ec()
        res2 = EC.Series("XAUUSD", kept, zone, end=V.HIST_END)
        pit2 = EC.Series("XAUUSD", kept, zone, end=V.HIST_END, sigma_every_day=True)
        keys, no_sig = V.research_events(res2, det, self.FAR)
        for d in cut:
            self.assertNotIn(d, res2.dense_days)
            self.assertIn(d, no_sig)                                     # research mode drops the event
            self.assertNotIn(d, set(keys.values()))
        rows, _info = self.rows("G9_XAUUSD_eod", pit2)
        got = {r["day"]: r for r in rows if r["day"] in cut}
        self.assertEqual(set(got), set(cut))                             # the decisive rows keep it, with a VR
        for d, r in got.items():
            i = pit2.T.index(r["entry_time"])
            self.assertEqual(r["nb_stored"], 21)
            self.assertEqual(r["nb_planned"], V.bars_to_day_end(pit2.dt[i], zone))
            self.assertGreater(r["nb_planned"], r["nb_stored"])
            sig = next(pit2.sigma(ev["i"]) for ev in V.pit_events(pit2, det, self.FAR)[0] if ev["e"] == i)
            self.assertAlmostEqual(r["stop_bp"], 1.4 * sig * math.sqrt(r["nb_planned"]) * 1e4, places=6)
        with mock.patch.object(V, "POWER_REPS", 100):                    # the dry run discloses both effects
            g9 = V.dry_counts(series_fn=lambda sym: res2, pit_series_fn=lambda sym: pit2, zone=zone,
                              causal_series_fn=lambda sym: pit2)["G9_XAUUSD_eod"]
        dec = g9["decisive"]
        self.assertGreaterEqual(dec["research_mode"]["only_point_in_time"], 3)
        self.assertEqual(dec["research_mode"]["only_research"], 0)
        self.assertGreaterEqual(dec["nb_clock_vs_stored"]["all"]["early_end_gt2"], 3)
        self.assertGreaterEqual(dec["nb_clock_vs_stored"]["all"]["short_gt12"], 3)
        self.assertEqual(dec["nb_clock_vs_stored"]["all"]["with_holes"], 0)

    def test_the_day_view_walks_what_the_whole_series_walks(self):
        det = self.BS.COMPONENTS["H7_XAUUSD_eod"][1]
        evs, _ = V.pit_events(self.pit, det, self.FAR)
        self.assertGreater(len(evs), 40)
        for ev in evs[-30:-20]:
            r = V.pit_trade(self.pit, ev, 1.4, FlatCosts(), self.zone, self.FF.resolve_row)
            e, px = ev["e"], self.pit.O[ev["e"]]
            dist = 1.4 * self.pit.sigma(ev["i"]) * math.sqrt(V.bars_to_day_end(self.pit.dt[e], self.zone)) * px
            whole = self.FF.resolve_row(self.pit, {"entry_time": self.pit.T[e], "status": "open", "h": "eod",
                                                   "side": ev["side"], "entry": px, "stop": px - ev["side"] * dist,
                                                   "stop_distance": dist}, FlatCosts())
            self.assertEqual((r["exit_time"], r["exit"]), (whole["exit_time"], whole["exit_reason"]))
            self.assertAlmostEqual(r["R_net"], whole["R"], places=12)

    def test_pit_events_drop_a_last_bar_signal_and_a_day_without_sigma(self):
        s = self.pit
        days = list(s.day_rows)
        d0, d1 = days[200], days[201]
        rows = s.day_rows[d0]

        def det(_s):
            return [{"i": rows[10], "entry_i": rows[11], "side": 1},          # kept
                    {"i": rows[-1], "entry_i": rows[-1] + 1, "side": -1},    # the day's last bar: entry on the next day
                    {"i": 3, "entry_i": 4, "side": 1},                       # the first day: no sigma yet
                    {"i": len(s.C) - 1, "entry_i": len(s.C), "side": 1}]     # no entry bar
        evs, dropped = V.pit_events(s, det, self.FAR)
        self.assertEqual([(ev["e"], ev["side"], ev["day"]) for ev in evs], [(rows[11], 1, d0)])
        self.assertEqual(dropped, {"last_bar": [d1], "no_sigma": [days[0]]})
        evs, dropped = V.pit_events(s, det, d0)                              # entries on d0 or later are outside
        self.assertEqual((evs, dropped["last_bar"], len(dropped["no_sigma"])), ([], [], 1))

    def test_pit_vr_is_the_research_vr_on_dense_days_exists_on_a_sparse_day_and_is_point_in_time(self):
        days = weekdays(datetime.date(2016, 1, 4), 220)
        sig = sigma_pattern(days)
        s = fake_series(days, sig)
        sparse = days[180]
        s.dense_days = [d for d in days if d != sparse]
        vr = V.pit_vr_by_day(s)
        research = types.SimpleNamespace(dense_days=s.dense_days, _vol={d: v for d, v in sig.items() if d != sparse})
        ref = V.vr_by_day(V.research_sig_by_day(research))
        self.assertTrue(all(vr.get(d) == ref.get(d) for d in s.dense_days))
        self.assertIn(sparse, vr)
        self.assertNotIn(sparse, ref)
        sig2 = dict(sig)
        for d in days[195:]:
            sig2[d] = 50.0
        s2 = fake_series(days, sig2)
        s2.dense_days = [d for d in s.dense_days if d != days[200]]
        vr2 = V.pit_vr_by_day(s2)
        self.assertTrue(all(vr.get(d) == vr2.get(d) for d in days[:195]))

    def test_the_read_defaults_to_the_point_in_time_rows(self):
        """xau_read's decisive mode is "pit"; the research rows are a separate, report-only call."""
        out = V.xau_read(1.4, series_fn=lambda sym: self.pit, zone=self.zone, costs_fn=FlatCosts,
                         resolve=self.FF.resolve_row, keep_rows=True)
        self.assertEqual(out["mode"], "pit")
        rows = out["rows"]["H7_XAUUSD_eod"]
        self.assertTrue(rows)
        self.assertTrue(all(r["nb_planned"] == V.bars_to_day_end(self.pit.dt[self.pit.T.index(r["entry_time"])],
                                                                  self.zone) for r in rows[:20]))
        self.assertEqual(out["counts"]["H7_XAUUSD_eod"]["with_vr"],
                         sum(1 for r in rows if r["day"] < V.HOLDOUT_END))
        self.assertIn("last_bar_dropped", out["counts"]["G9_XAUUSD_eod"])
        self.assertEqual(set(out["counts"]["G9_XAUUSD_eod"]["paper_log_refusable"]), {"hole", "stale_vol"})

    def test_the_point_in_time_read_carries_the_run_clustered_t1a_and_the_report_only_block(self):
        """The run-clustered T1a (clusters = VR runs, fewer than the days; part of T1a's pass rule, lead decision 2026-10-05)
        and, report-only, every test without the trades the paper log would have refused sit beside the by-day tests; the
        refusal-excluded block changes none of their numbers. The research rows carry the run-clustered T1a, not the block."""
        kw = dict(series_fn=lambda sym: self.pit, zone=self.zone, costs_fn=FlatCosts, resolve=self.FF.resolve_row)
        flag = lambda s, evs, ff=None: {ev["e"]: ("hole" if k % 3 == 0 else "stale_vol") for k, ev in enumerate(evs) if k % 5 == 0}
        with mock.patch.object(V, "paper_log_refusals", flag):     # (the real rule: test_the_paper_logs_signals_agree...)
            out = V.xau_read(1.4, keep_rows=True, **kw)
        runs = out["T1a_run_clustered"]
        self.assertEqual((runs["statistic"], runs["weight"]), ("R_bar", "nb_weight"))
        v = out["T1_verdict"]
        self.assertEqual(v["T1a_run_clustered_p"], runs["p_one_sided"] if runs["t"] is not None else None)
        self.assertEqual(v["T1a_volatility"], bool(v["T1a_by_day"] and v["T1a_run_clustered_p"] is not None
                                                   and v["T1a_run_clustered_p"] <= V.ALPHA_T1))
        self.assertEqual((runs["n_high"], runs["n_low"]), (out["T1a_xau_volatility"]["n_high"],
                                                          out["T1a_xau_volatility"]["n_low"]))
        self.assertLess(runs["days_high"], out["T1a_xau_volatility"]["days_high"])         # a cluster is a whole run
        rows = [r for c in V.GOLD for r in out["rows"][c] if r["day"] < V.HOLDOUT_END]
        self.assertEqual(runs["days_high"], len({r["run"] for r in rows if r["high"]}))
        ex = out["excluding_paper_log_refusals_report_only"]
        kept = sum(1 for r in rows if not r["refusal"])
        self.assertEqual(sum(ex["trades"][c] for c in V.GOLD), kept)
        self.assertLess(kept, len(rows))                                                   # flagged rows are left out
        self.assertEqual(sum(out["counts"][c]["paper_log_refusable"][w] for c in V.GOLD for w in ("hole", "stale_vol")),
                         len(rows) - kept)
        for c in V.GOLD:                                                                    # by reason, per component
            mine = [r for r in out["rows"][c] if r["day"] < V.HOLDOUT_END]
            self.assertEqual(out["counts"][c]["paper_log_refusable"],
                             {"hole": sum(1 for r in mine if r["refusal"] == "hole"),
                              "stale_vol": sum(1 for r in mine if r["refusal"] == "stale_vol")})
            holes = sum(1 for r in mine if r["refusal"] == "hole")
            stale = sum(1 for r in mine if r["refusal"] == "stale_vol")
            self.assertTrue(holes > 0 and stale > 0 and holes != stale, (c, holes, stale))   # a swap of the two would show
        self.assertEqual(ex["T1a_xau_volatility"]["n_high"] + ex["T1a_xau_volatility"]["n_low"], kept)
        self.assertEqual(out["T1_verdict"]["T1a_volatility"], V.xau_read(1.4, **kw)["T1_verdict"]["T1a_volatility"])
        self.assertEqual(out["T1a_xau_volatility"]["diff"], V.xau_read(1.4, **kw)["T1a_xau_volatility"]["diff"])
        res = V.xau_read(1.4, mode="research", trades_fn=lambda *a, **k: [], series_fn=lambda sym: self.pit, zone=self.zone)
        self.assertIsNone(res["T1a_run_clustered"]["t"])                                  # no row: not computable
        self.assertEqual((res["T1_verdict"]["T1a_volatility"], res["T1_verdict"]["T1a_run_clustered_p"]), (False, None))
        self.assertNotIn("excluding_paper_log_refusals_report_only", res)

    def test_a_failure_in_a_report_only_block_is_recorded_and_the_decisive_tests_stand(self):
        """The refusal-excluded block and window A's run-clustered T1a are `_guarded`: an exception there lands in their place
        in the JSON (never raised: it would stop the run-once read); the decisive tests and the rest of the window-A block
        are unchanged. The decisive run-clustered T1a is part of T1a's pass rule (lead decision 2026-10-05): its failure is
        raised like any decisive test's, never turned into a verdict."""
        kw = dict(series_fn=lambda sym: self.pit, zone=self.zone, costs_fn=FlatCosts, resolve=self.FF.resolve_row)
        base = V.xau_read(1.4, **kw)
        real_split, real_tests, calls, run_calls = V.split_test, V._tests_on, [], []

        def split(rows, *a, **k):
            if k.get("day_key") == "run":
                run_calls.append(1)
                if len(run_calls) == 2:                           # the decisive window's, then window A's
                    raise KeyError("run")
            return real_split(rows, *a, **k)

        def tests(rows_by_c):
            calls.append(1)
            if len(calls) == 2:                                   # primary, then the refusal-excluded block, then window A
                raise ValueError("boom")
            return real_tests(rows_by_c)
        with mock.patch.object(V, "split_test", split), mock.patch.object(V, "_tests_on", tests):
            out = V.xau_read(1.4, **kw)
        self.assertEqual(len(run_calls), 2)
        self.assertEqual(out["report_only_window_A"]["T1a_run_clustered"], {"error": "KeyError: 'run'"})
        self.assertEqual(out["excluding_paper_log_refusals_report_only"], {"error": "ValueError: boom"})
        self.assertEqual(out["T1a_xau_volatility"]["diff"], base["T1a_xau_volatility"]["diff"])
        self.assertEqual(out["T1a_run_clustered"], base["T1a_run_clustered"])
        self.assertEqual(out["T1_verdict"], base["T1_verdict"])
        self.assertEqual(out["report_only_window_A"]["T1a_xau_volatility"]["diff"],
                         base["report_only_window_A"]["T1a_xau_volatility"]["diff"])
        self.assertNotIn("error", base["report_only_window_A"]["T1a_run_clustered"])

        def decisive(rows, *a, **k):
            if k.get("day_key") == "run":
                raise KeyError("run")
            return real_split(rows, *a, **k)
        with mock.patch.object(V, "split_test", decisive), self.assertRaises(KeyError):
            V.xau_read(1.4, **kw)

    def test_the_causal_density_mode_reads_the_causal_series(self):
        """On a feed whose first 100 days carry fewer bars a day (dense against their own era, sparse against the whole
        history), the causal series has the earlier sigma and VR, so more labelled trades; the decisive rows are untouched."""
        EC = V._ec()
        candles = short_start_candles(300, thin_days=100)
        whole = EC.Series("XAUUSD", candles, self.zone, end=V.HIST_END, sigma_every_day=True)
        causal = V.causal_density(EC.Series("XAUUSD", candles, self.zone, end=V.HIST_END, sigma_every_day=True))
        kw = dict(zone=self.zone, costs_fn=FlatCosts, resolve=self.FF.resolve_row)
        out = V.xau_read(1.4, mode="pit_causal", series_fn=lambda sym: causal, **kw)
        base = V.xau_read(1.4, series_fn=lambda sym: whole, **kw)
        self.assertEqual((out["mode"], base["mode"]), ("pit_causal", "pit"))
        n = lambda o: sum(o["counts"][c]["with_vr"] for c in V.GOLD)
        self.assertGreater(n(out), n(base))
        self.assertGreater(n(base), 0)
        self.assertEqual(set(out["T1_verdict"]), {"T1a_volatility", "T1b_hold_length", "holm_rejected", "T1a_by_day",
                                                  "T1a_run_clustered_p", "reading"})

    def test_pit_series_builds_the_causal_variant_beside_the_whole_history_one(self):
        doc = {"candles": self.candles}
        with mock.patch("history_store.read_doc", lambda sym, tf, root=None: (doc, "x")), \
                mock.patch.dict(V._PIT, clear=True):
            a, b = V._pit_series("XAUUSD"), V._pit_series("XAUUSD", causal=True)
            self.assertIs(V._pit_series("XAUUSD"), a)
            self.assertIs(V._pit_series("XAUUSD", causal=True), b)
        self.assertIsNot(a, b)
        self.assertEqual(b.dense_days, a.dense_days[V.CAUSAL_MIN_DAYS:])      # complete days: the same rule, 20 days later

    def test_the_paper_logs_signals_agree_with_pit_events_stops_and_refusals(self):
        """fvg_forward.signals (stop_k and the forward start patched for the synthetic years) against pit_events /
        pit_trade / paper_log_refusals on a series with a missing-days hole and a stretch of sparse days: every event the
        decisive rows keep is a signal of the paper log, with the same stop distance when the log accepts it and a
        matching refusal reason when it does not."""
        FF, EC = self.FF, V._ec()
        days = sorted({V.server_day_of(b["time"], self.zone) for b in self.candles})
        hole, sparse = set(days[100:104]), set(days[170:182])
        per_day = {}
        kept = []
        for b in self.candles:
            d = V.server_day_of(b["time"], self.zone)
            if d in hole:
                continue
            if d in sparse:
                per_day[d] = per_day.get(d, 0) + 1
                if per_day[d] > 100:
                    continue
            kept.append(b)
        s = EC.Series("XAUUSD", kept, self.zone, end=V.HIST_END, sigma_every_day=True)
        seen = collections.Counter()
        with mock.patch.object(FF, "stop_k_at", lambda name, at: 1.4), \
                mock.patch.object(FF, "FORWARD_START", "2000-01-01T00:00:00Z"):
            for comp in V.GOLD:
                sym, det, _hold = self.BS.COMPONENTS[comp]
                log = {(r["entry_time"], r["side"]): r for r in FF.signals(s, sym, "eod", comp.split("_")[0], comp)}
                evs, _ = V.pit_events(s, det, self.FAR)
                ref = V.paper_log_refusals(s, evs, FF)
                self.assertGreater(len(evs), 20, comp)
                for ev in evs:
                    row = log[(s.T[ev["e"]], ev["side"])]
                    self.assertEqual(row["status"] == "refused", ev["e"] in ref, (comp, row))
                    if row["status"] == "refused":
                        why = "hole" if "data hole" in row["reason"] else "stale_vol"
                        self.assertEqual(ref[ev["e"]], why)
                        seen[why] += 1
                        continue
                    t = V.pit_trade(s, ev, 1.4, FlatCosts(), self.zone, FF.resolve_row)
                    if t is not None:
                        self.assertEqual((t["entry"], t["stop_distance"]), (row["entry"], row["stop_distance"]))
                        seen["accepted"] += 1
        self.assertGreater(seen["accepted"], 20)
        self.assertGreater(seen["hole"], 0)
        self.assertGreater(seen["stale_vol"], 0)

    def test_paper_log_refusal_edges_and_precedence(self):
        """The paper log's window is inclusive at both ends (`t_sig - HOLE_LOOKBACK <= hole end <= t_sig`) and a hole is
        reported before stale volatility when both apply."""
        FF = self.FF
        t_sig = FF._dt("2007-06-01T10:00:00Z")
        look = datetime.timedelta(days=35)
        fmt = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")
        s = types.SimpleNamespace(T=["2007-06-01T10:00:00Z"])
        evs = [{"i": 0, "e": 5}]
        for end, hole in ((t_sig - look, True), (t_sig - look - datetime.timedelta(seconds=1), False),
                          (t_sig, True), (t_sig + datetime.timedelta(seconds=1), False)):
            ff = types.SimpleNamespace(HOLE_LOOKBACK=look, _dt=FF._dt, holes=lambda times, e=end: [("x", fmt(e))],
                                       _vol_fresh=lambda series, i: True)
            self.assertEqual(V.paper_log_refusals(s, evs, ff), {5: "hole"} if hole else {}, end)
        both = types.SimpleNamespace(HOLE_LOOKBACK=look, _dt=FF._dt, holes=lambda times: [("x", fmt(t_sig))],
                                     _vol_fresh=lambda series, i: False)
        self.assertEqual(V.paper_log_refusals(s, evs, both), {5: "hole"})            # the hole is checked first

    def test_a_day_with_exactly_the_minimum_bars_counts_in_the_causal_median(self):
        """CAUSAL_FULL_MIN is inclusive (edge_census.py:105 `v >= 50`): twenty 50-bar days give the next day a median to
        compare with (0.8 x 50 = 40 bars), a 41-bar day is dense, a 39-bar day is not."""
        def build(last):
            rows = collections.OrderedDict((datetime.date(2005, 1, 3) + datetime.timedelta(days=k), list(range(50)))
                                           for k in range(V.CAUSAL_MIN_DAYS))
            rows[datetime.date(2005, 3, 1)] = list(range(last))
            sday = [d for d, r in rows.items() for _ in r]
            return types.SimpleNamespace(day_rows=rows, sday=sday, _vol_by_day=lambda: {})
        for last, dense in ((41, True), (40, True), (39, False)):
            s = V.causal_density(build(last))
            self.assertEqual(datetime.date(2005, 3, 1) in s.dense_days, dense, last)
            self.assertEqual(len(s.dense_days), 1 if dense else 0)

    def test_paper_log_refusal_rules_on_hand_built_bars(self):
        """A hole refuses the signals whose time is 0-35 days after the hole's end; else fewer than 20 dense days refuse; a
        hole that ends after the signal, or more than 35 days before it, does not."""
        FF = self.FF
        stamps = [f"2007-{m:02d}-{d:02d}T10:00:00Z" for m, d in ((1, 3), (2, 6), (3, 1), (3, 20), (4, 12), (5, 15))]
        s = types.SimpleNamespace(T=stamps)
        ff = types.SimpleNamespace(HOLE_LOOKBACK=datetime.timedelta(days=35), _dt=FF._dt,
                                   holes=lambda times: [("2007-02-01T00:00:00Z", "2007-02-05T00:00:00Z")],
                                   _vol_fresh=lambda series, i: i != 4)
        evs = [{"i": i, "e": i + 10} for i in range(len(stamps))]
        # signal 0 (01-03): the hole ends after it; 1 (02-06) and 2 (03-01): within 35 days of the hole's end (02-05);
        # 3 (03-20): 43 days after it, and fresh; 4 (04-12): no hole in range, stale volatility; 5 (05-15): neither
        self.assertEqual(V.paper_log_refusals(s, evs, ff), {11: "hole", 12: "hole", 14: "stale_vol"})


def short_start_candles(n_days, thin_days, thin_bars=150, seed=3):
    """FTMO-shaped weekday bars; the first `thin_days` days carry only their first `thin_bars` bars (an early feed with fewer
    bars a day): dense against their own era, sparse against the whole history's median."""
    per_day, out = collections.Counter(), []
    zone = V.server_zone()
    for k, b in enumerate(ftmo_candles(datetime.date(2005, 1, 3), n_days, seed=seed)):
        d = V.server_day_of(b["time"], zone)
        per_day[d] += 1
        if (d - datetime.date(2005, 1, 3)).days < thin_days * 7 // 5 and per_day[d] > thin_bars:
            continue
        out.append(b)
    return out


def alternating_candles(n_days, start=datetime.date(2007, 6, 4)):
    """Complete FTMO-shaped weekdays in which every day repeats ONE 288-bar pattern (open 100 / close 101, then 101 / 100, ...):
    every day's sigma is the same float, so VR = sigma / median is exactly 1.0 (the HIGH / LOW boundary: LOW), and the first
    bar of each day closes beyond the day's open + 0.5 x yesterday's range (a G9 event every day)."""
    zone = V.server_zone()
    out, d, k = [], start, 0
    while k < n_days:
        if d.weekday() < 5:
            for m in range(0, 1440, 5):
                t = datetime.datetime(d.year, d.month, d.day, m // 60, m % 60, tzinfo=zone).astimezone(UTC)
                o, c = (100.0, 101.0) if (m // 5) % 2 == 0 else (101.0, 100.0)
                out.append({"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "open": o, "high": 101.0, "low": 100.0, "close": c})
            k += 1
        d += datetime.timedelta(days=1)
    return out


class Sensitivities(unittest.TestCase):
    """Lead decision D2 (2026-10-04): the pre-registered report-only blocks, and the reviewer's regime-block finding."""

    @classmethod
    def setUpClass(cls):
        cls.zone = V.server_zone()
        cls.EC = V._ec()

    def series(self, candles, causal):
        s = self.EC.Series("XAUUSD", candles, self.zone, end=V.HIST_END, sigma_every_day=True)
        return V.causal_density(s) if causal else s

    def test_causal_density_counts_an_early_thin_era_as_dense_and_matches_whole_history_on_complete_days(self):
        candles = short_start_candles(160, thin_days=60)
        g, c = self.series(candles, False), self.series(candles, True)
        thin = [d for d in g.day_rows if len(g.day_rows[d]) < 200]
        self.assertEqual(len(thin), 60)
        self.assertFalse(any(d in set(g.dense_days) for d in thin))                       # whole history: all sparse
        self.assertTrue(all(d in set(c.dense_days) for d in thin[V.CAUSAL_MIN_DAYS:]))    # causal: dense in their own era
        self.assertFalse(any(d in set(c.dense_days) for d in thin[:V.CAUSAL_MIN_DAYS]))   # no history for a median yet
        full = short_start_candles(100, thin_days=0)
        g2, c2 = self.series(full, False), self.series(full, True)
        days = list(g2.day_rows)
        self.assertEqual(c2.dense_days, g2.dense_days[V.CAUSAL_MIN_DAYS:])
        # the sigma history is rebuilt on the causal days (20 dense days before a day has a sigma) and so are the flags
        self.assertEqual((min(g2._vol), min(c2._vol)), (days[20], days[40]))
        self.assertIs(g2.prev_dense[g2.day_rows[days[20]][0]], True)
        self.assertIs(c2.prev_dense[c2.day_rows[days[20]][0]], False)
        self.assertIs(c2.prev_dense[c2.day_rows[days[21]][0]], True)
        self.assertEqual(c2.split_day, c2.dense_days[int(len(c2.dense_days) * self.EC.DISCOVERY_SHARE)])

    def test_causal_density_is_point_in_time_and_the_whole_history_rule_is_not(self):
        """The dense flags, previous-day flags and sigma of every day before a cut do not move when the later days' bars
        and prices are altered; the whole-history rule's flags of those days do (the median moves)."""
        candles = short_start_candles(160, thin_days=60)
        cut_day = sorted({V.server_day_of(b["time"], self.zone) for b in candles})[120]
        late = []
        for k, b in enumerate(candles):
            if V.server_day_of(b["time"], self.zone) >= cut_day:
                f = 1 + 0.01 * ((k % 7) - 3)
                b = dict(b, open=b["open"] * f, high=b["high"] * f, low=b["low"] * f, close=b["close"] * f)
            late.append(b)
        thinner = [b for k, b in enumerate(late) if not (V.server_day_of(b["time"], self.zone) >= cut_day and k % 2)]
        a, b = self.series(candles, True), self.series(thinner, True)
        before = [d for d in a.day_rows if d < cut_day]
        self.assertEqual(len(before), 120)
        da, db = set(a.dense_days), set(b.dense_days)
        self.assertEqual([d in da for d in before], [d in db for d in before])
        self.assertEqual([a._vol.get(d) for d in before], [b._vol.get(d) for d in before])
        self.assertTrue(any(a._vol.get(d) for d in before))
        first = {d: a.day_rows[d][0] for d in before}
        self.assertEqual([a.prev_dense[first[d]] for d in before], [b.prev_dense[b.day_rows[d][0]] for d in before])
        ga, gb = self.series(candles, False), self.series(thinner, False)
        self.assertNotEqual([d in set(ga.dense_days) for d in before], [d in set(gb.dense_days) for d in before])

    def test_causal_density_rewrites_every_flag_the_detectors_read(self):
        """The detectors read `dense`, `prev_dense`, `dense_days` and `_vol` (edge_census / edge_f3 / edge_f4): all four follow
        the causal rule, none is left at the whole-history one."""
        c = self.series(short_start_candles(160, thin_days=60), True)
        dset, days = set(c.dense_days), list(c.day_rows)
        self.assertEqual(c.dense, [d in dset for d in c.sday])
        prev = {d: days[k - 1] in dset for k, d in enumerate(days) if k}
        self.assertEqual(c.prev_dense, [prev.get(d, False) for d in c.sday])
        self.assertEqual(set(c._vol), set(c._vol_by_day()))

    def test_the_causal_median_of_an_even_number_of_earlier_days_is_the_mean_of_the_middle_two(self):
        """22 earlier days, 11 of 240 and 11 of 280 bars: median 260, threshold 208. A 215-bar day is dense (an upper-middle
        median, 280, would put the threshold at 224)."""
        by_day = {}
        for b in ftmo_candles(datetime.date(2005, 1, 3), 40):
            by_day.setdefault(V.server_day_of(b["time"], self.zone), []).append(b)
        out = []
        for k, (d, bars) in enumerate(by_day.items()):
            keep = 215 if k == 22 else (240 if k % 2 == 0 else 280)
            out += bars[:keep] if k <= 22 else bars
        c = self.series(out, True)
        d22 = list(c.day_rows)[22]
        self.assertEqual(len(c.day_rows[d22]), 215)
        self.assertIn(d22, c.dense_days)

    def test_xau_read_asks_for_the_causal_series_only_in_the_causal_mode_and_refuses_an_unknown_mode(self):
        s = self.series(ftmo_candles(datetime.date(2007, 1, 1), 200), False)
        seen = []

        def spy(sym, causal=False):
            seen.append((sym, causal))
            return s
        kw = dict(zone=self.zone, costs_fn=FlatCosts, resolve=V._load("fvg_forward", "scripts/research/fvg_forward.py").resolve_row)
        with mock.patch.object(V, "_pit_series", spy):
            V.xau_read(1.4, **kw)
            plain = list(seen)
            seen.clear()
            V.xau_read(1.4, mode="pit_causal", **kw)
            causal = list(seen)
        self.assertTrue(plain and not any(c for _sym, c in plain), plain)
        self.assertTrue(causal and all(c for _sym, c in causal), causal)
        with self.assertRaises(ValueError):
            V.xau_read(1.4, mode="causal", **kw)

    def test_the_dry_run_asks_for_the_whole_history_series_and_the_causal_one_by_default(self):
        candles = short_start_candles(300, thin_days=100)
        whole, causal = self.series(candles, False), self.series(candles, True)
        seen = []

        def spy(sym, causal_flag=None, **kw):
            flag = kw.get("causal", causal_flag) or False
            seen.append((sym, flag))
            return causal if flag else whole
        BS = V._load("book_sim", "scripts/research/book_sim.py")
        with mock.patch.object(V, "_pit_series", spy), mock.patch.object(V, "POWER_REPS", 50):
            out = V.dry_counts(series_fn=lambda sym: whole, zone=self.zone)
        self.assertIn(("XAUUSD", False), seen)
        self.assertIn(("XAUUSD", True), seen)
        c = V.GOLD[1]
        self.assertEqual(out["causal_density"][c]["decisive"]["events"],
                         len(V.pit_events(causal, BS.COMPONENTS[c][1], V.LOAD_END)[0]))
        self.assertEqual(out[c]["decisive"]["high"] + out[c]["decisive"]["low"] + out[c]["decisive"]["no_vr"],
                         len(V.pit_events(whole, BS.COMPONENTS[c][1], V.LOAD_END)[0]))

    def test_a_vr_of_exactly_one_is_a_low_day_in_the_dry_run(self):
        sp = self.series(alternating_candles(220), False)
        vr = V.pit_vr_by_day(sp)
        self.assertGreater(len(vr), 20)
        self.assertEqual(set(vr.values()), {1.0})
        with mock.patch.object(V, "POWER_REPS", 50):
            out = V.dry_counts(series_fn=lambda sym: sp, pit_series_fn=lambda sym: sp, zone=self.zone,
                               causal_series_fn=lambda sym: sp)
        g9 = out[V.GOLD[1]]["decisive"]
        self.assertGreater(g9["low"], 20)
        self.assertEqual(g9.get("high", 0), 0)
        self.assertEqual(out["xau_pooled"]["decisive"]["regime_blocks"]["runs"], {"high": 0, "low": 1})

    def test_the_dry_runs_causal_block_counts_the_causal_series(self):
        candles = short_start_candles(300, thin_days=100)
        whole, causal = self.series(candles, False), self.series(candles, True)
        BS = V._load("book_sim", "scripts/research/book_sim.py")
        with mock.patch.object(V, "POWER_REPS", 50):
            out = V.dry_counts(series_fn=lambda sym: whole, pit_series_fn=lambda sym: whole, zone=self.zone,
                               causal_series_fn=lambda sym: causal)
        cvr = V.pit_vr_by_day(causal)
        for c in V.GOLD:
            det = BS.COMPONENTS[c][1]
            evs, dropped = V.pit_events(causal, det, V.LOAD_END)
            self.assertNotEqual(len(evs), len(V.pit_events(whole, det, V.LOAD_END)[0]))
            blk = out["causal_density"][c]
            self.assertEqual(blk["decisive"]["events"], len(evs))
            self.assertEqual(blk["first_vr_day"], str(min(cvr)))
            self.assertEqual(blk["decisive"]["no_sigma"], len(dropped["no_sigma"]))
            self.assertEqual((blk["decisive"]["high"], blk["decisive"]["low"], blk["decisive"]["no_vr"]),
                             (sum(1 for e in evs if cvr.get(e["day"], 0) > 1.0),
                              sum(1 for e in evs if e["day"] in cvr and cvr[e["day"]] <= 1.0),
                              sum(1 for e in evs if e["day"] not in cvr)))
        dd = out["causal_density"]["XAUUSD_dense_days"]["decisive"]
        self.assertEqual((dd["whole_history_rule"], dd["causal_rule"]),
                         (len(whole.dense_days), len(causal.dense_days)))

    def test_vr_runs_and_regime_blocks(self):
        d = [datetime.date(2006, 1, 2) + datetime.timedelta(days=k) for k in range(8)]
        vr = {d[0]: 1.2, d[1]: 1.1, d[2]: 0.9, d[3]: 0.8, d[4]: 0.7, d[5]: 1.5, d[6]: 1.4, d[7]: 0.5}
        self.assertEqual(V.vr_runs(vr), {d[0]: 0, d[1]: 0, d[2]: 1, d[3]: 1, d[4]: 1, d[5]: 2, d[6]: 2, d[7]: 3})
        self.assertEqual(V.vr_runs(vr, end=d[6]), {d[0]: 0, d[1]: 0, d[2]: 1, d[3]: 1, d[4]: 1, d[5]: 2})
        evs = [{"day": d[0], "high": True}, {"day": d[1], "high": True}, {"day": d[1], "high": True}, {"day": d[3], "high": False},
               {"day": d[5], "high": True}, {"day": d[6], "high": None}, {"day": d[7], "high": False}]
        rb = V.regime_blocks(vr, d[7], evs)
        self.assertEqual(rb["runs"], {"high": 2, "low": 1})
        self.assertEqual([(b["half"], b["days"], b["trades"]) for b in rb["blocks"]],
                         [("high", 2, 3), ("low", 3, 1), ("high", 2, 1)])
        self.assertEqual((rb["days_with_vr"], rb["run_days_max"], rb["run_days_median"]), (7, 3, {"high": 2, "low": 3}))
        self.assertEqual(rb["run_days"], {"high": [2, 2], "low": [3]})
        # a median of an even number of runs is the mean of the middle two (not the upper one); VR == 1.0 is LOW
        long_vr = {datetime.date(2006, 1, 2) + datetime.timedelta(days=k): v for k, v in enumerate(
            [1.2, 0.9, 1.2, 1.2, 0.9, 1.2, 1.2, 1.2, 0.9, 1.2, 1.2, 1.2, 1.2])}
        rb2 = V.regime_blocks(long_vr, datetime.date(2007, 1, 1), [])
        self.assertEqual((rb2["run_days"], rb2["run_days_median"]), ({"high": [1, 2, 3, 4], "low": [1, 1, 1]},
                                                                     {"high": 2.5, "low": 1}))
        one = {datetime.date(2006, 1, 2): 1.0, datetime.date(2006, 1, 3): 1.0000001}
        self.assertEqual(V.vr_runs(one), {datetime.date(2006, 1, 2): 0, datetime.date(2006, 1, 3): 1})
        self.assertEqual(V.regime_blocks(one, datetime.date(2007, 1, 1), [])["runs"], {"high": 1, "low": 1})
        self.assertEqual(rb["trades_by_year"], {"2006": {"high": 4, "low": 1}})
        self.assertNotIn("blocks", V.regime_blocks(vr, d[7], evs, blocks=False))
        self.assertEqual(V.regime_blocks(vr, d[7], evs, blocks=False)["runs"], rb["runs"])
        self.assertTrue(all(isinstance(v, int) for v in (rb["days_with_vr"], rb["run_days_max"])))

    def verdict_inputs(self, p_a=0.001, p_b=0.9, net=0.1, diffs=(0.2, 0.3)):
        t = lambda p: {"p_one_sided": p, "net_mean_high": net}
        per = {c: {"diff": x} for c, x in zip(V.GOLD, diffs)}
        return t(p_a), t(p_b), per, per

    RUNS_OK = {"diff": 0.2, "p_one_sided": 0.01, "t": 4.0}

    def test_t1a_passes_only_when_its_run_clustered_companion_passes_too(self):
        """Lead decision 2026-10-05 (option C): T1a passes iff its by-day Holm rule passes AND the run-clustered one-sided
        p <= ALPHA_T1 (inclusive); a companion that is not computable fails T1a; T1b is untouched; the reading says why."""
        a = self.verdict_inputs()
        strong = V.t1_verdict(*a, t1a_runs=self.RUNS_OK)
        self.assertEqual((strong["T1a_volatility"], strong["T1a_by_day"], strong["T1b_hold_length"],
                          strong["T1a_run_clustered_p"]), (True, True, False, 0.01))
        self.assertTrue(strong["reading"].startswith("PASS: DISCOVERY-GRADE"))
        self.assertNotIn("companion did not", strong["reading"])
        weak = V.t1_verdict(*a, t1a_runs={"diff": 0.2, "p_one_sided": 0.2, "t": 0.9})
        self.assertEqual((weak["T1a_volatility"], weak["T1a_by_day"], weak["T1b_hold_length"],
                          weak["T1a_run_clustered_p"]), (False, True, False, 0.2))
        self.assertEqual(weak["holm_rejected"], strong["holm_rejected"])                  # Holm is the by-day rule's
        self.assertTrue(weak["reading"].startswith("NOT SHOWN (inconclusive"))
        self.assertIn("run-clustered companion did not (p = 0.200 > 0.05)", weak["reading"])
        self.assertIn("lead decision 2026-10-05", weak["reading"])
        for broken in ({"diff": None, "p_one_sided": 1.0, "t": None},                  # an empty cell
                       {"diff": 0.2, "p_one_sided": 0.001, "t": None},                 # df <= 0: a diff but no t
                       {"error": "KeyError: 'run'"}):                                  # no statistic at all
            r = V.t1_verdict(*a, t1a_runs=broken)
            self.assertEqual((r["T1a_volatility"], r["T1a_by_day"], r["T1a_run_clustered_p"]), (False, True, None))
            self.assertIn("run-clustered companion did not (not computable)", r["reading"])
        for p, passes in ((0.04, True), (0.05, True), (0.0501, False)):           # ALPHA_T1 = 0.05, inclusive
            r = V.t1_verdict(*a, t1a_runs={"diff": 0.2, "p_one_sided": p, "t": 2.0})
            self.assertEqual(r["T1a_volatility"], passes, p)
        for kw in (dict(p_a=0.5), dict(net=-0.1), dict(diffs=(0.2, -0.01))):      # the companion rescues no by-day fail
            r = V.t1_verdict(*self.verdict_inputs(**kw), t1a_runs={"diff": 0.2, "p_one_sided": 0.001, "t": 5.0})
            self.assertEqual((r["T1a_volatility"], r["T1a_by_day"]), (False, False), kw)
            self.assertNotIn("companion did not", r["reading"])
        both = V.t1_verdict(*self.verdict_inputs(p_b=0.001), t1a_runs={"diff": 0.2, "p_one_sided": 0.9, "t": 0.1})
        self.assertEqual((both["T1a_volatility"], both["T1b_hold_length"], both["T1a_by_day"]), (False, True, True))
        self.assertTrue(both["reading"].startswith("PASS: DISCOVERY-GRADE"))               # T1b's pass stands
        self.assertIn("run-clustered companion did not (p = 0.900 > 0.05)", both["reading"])
        none = V.t1_verdict(*self.verdict_inputs(p_a=0.5), t1a_runs={"diff": 0.2, "p_one_sided": 0.9, "t": 0.1})
        self.assertTrue(none["reading"].startswith("NOT SHOWN (inconclusive"))
        self.assertNotIn("companion did not", none["reading"])                             # no by-day pass: no note

    def test_data_sensitive_when_a_sensitivity_gives_another_t1_verdict(self):
        base = V.t1_verdict(*self.verdict_inputs(), t1a_runs=self.RUNS_OK)
        same = {"T1_verdict": dict(base)}
        other = {"T1_verdict": dict(base, T1b_hold_length=True)}
        out = V.with_sensitivities(base, {"research_mode": same, "causal_density": same})
        self.assertEqual((out["data_sensitive"], out["sensitivity_unavailable"]), (False, []))
        self.assertEqual(out["reading"], base["reading"])
        self.assertEqual((out["T1a_volatility"], out["T1b_hold_length"]), (True, False))
        out = V.with_sensitivities(base, {"research_mode": same, "causal_density": other})
        self.assertTrue(out["data_sensitive"])
        self.assertIn("DATA-SENSITIVE: not decisive (causal_density give another T1 verdict", out["reading"])
        self.assertEqual((out["T1a_volatility"], out["T1b_hold_length"]), (True, False))   # the decisive verdict is unchanged
        self.assertEqual(out["sensitivities"]["causal_density"], {"T1a_volatility": True, "T1b_hold_length": True})
        out = V.with_sensitivities(base, {"research_mode": {"error": "KeyError: x"}, "causal_density": same})
        self.assertEqual((out["data_sensitive"], out["sensitivity_unavailable"]), (False, ["research_mode"]))
        self.assertIn("SENSITIVITY UNAVAILABLE: research_mode", out["reading"])

    def test_a_report_only_failure_is_recorded_not_raised(self):
        self.assertEqual(V._guarded(lambda: 7), 7)
        out = V._guarded(lambda: {}["x"])
        self.assertEqual(out, {"error": "KeyError: 'x'"})


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
    KEYS = {"high", "low", "no_vr", "last_bar_signal", "no_sigma", "high_long_hold", "high_short_hold",
            "low_long_hold", "low_short_hold", "window", "end", "research_mode", "nb_clock_vs_stored", "refusable",
            "planned_bars", "cells", "power_inputs"}

    def series(self, n_days=400):
        EC = V._ec()
        c = crypto_candles(n_days, start=datetime.date(2007, 11, 1))
        return (EC.Series("XAUUSD", c, UTC, end=V.HIST_END),
                EC.Series("XAUUSD", c, UTC, end=V.HIST_END, sigma_every_day=True),
                V.causal_density(EC.Series("XAUUSD", c, UTC, end=V.HIST_END, sigma_every_day=True)))

    def test_counts_only_from_the_real_detectors(self):
        s, sp, sc = self.series()
        with mock.patch.object(V, "POWER_REPS", 300):
            out = V.dry_counts(series_fn=lambda sym: s, pit_series_fn=lambda sym: sp, zone=UTC,
                               causal_series_fn=lambda sym: sc)
        self.assertEqual(set(out), set(V.GOLD + V.SILVER) | {"xau_pooled", "causal_density"})
        for c in (out[x] for x in V.GOLD + V.SILVER):
            self.assertEqual(set(c), {"median_entry_slot", "first_vr_day", "decisive", "report_only"})
            self.assertEqual(c["first_vr_day"], str(min(V.pit_vr_by_day(sp))))
            self.assertEqual((c["decisive"]["window"], c["report_only"]["window"]), ("B", "A"))
            for w in ("decisive", "report_only"):
                self.assertTrue(set(c[w]) <= self.KEYS, set(c[w]) - self.KEYS)
                self.assertFalse(any(isinstance(v, float) for v in c[w].values()))
                rm = c[w]["research_mode"]
                self.assertEqual(set(rm), {"events", "no_research_sigma", "only_point_in_time", "only_research"})
                self.assertTrue(all(isinstance(v, int) for v in rm.values()))
                self.assertEqual(rm["only_point_in_time"], 0)               # complete days: no same-day selection
                nbs = c[w]["nb_clock_vs_stored"]
                self.assertEqual(set(nbs), {"all"} | set(V.HALVES))
                for h in nbs.values():
                    self.assertTrue(all(isinstance(v, int) for v in h.values()))
                    self.assertEqual(h["nb_clock"], h["nb_stored"])        # complete days: the clock is the store
                    self.assertEqual((h["short_gt12"], h["with_holes"], h["holes_bars"], h["early_end_gt2"],
                                      h["early_end_bars"]), (0, 0, 0, 0, 0))
                self.assertEqual(nbs["all"]["n"], c[w].get("high", 0) + c[w].get("low", 0))
                rf = c[w]["refusable"]
                self.assertEqual(set(rf), {"hole", "stale_vol", "high", "low", "long_hold", "short_hold"})
                self.assertTrue(all(isinstance(v, int) for v in rf.values()))
                self.assertEqual(rf["hole"] + rf["stale_vol"], rf["high"] + rf["low"])
                self.assertLessEqual(rf["high"], c[w].get("high", 0))
                self.assertLessEqual(rf["low"], c[w].get("low", 0))
                self.assertTrue(all(isinstance(v, int) for v in c[w]["planned_bars"].values()))
                for cell in c[w]["cells"].values():
                    self.assertTrue(all(isinstance(v, int) for v in cell.values()))
                    self.assertGreaterEqual(cell["n2_days"], cell["n"])
                self.assertEqual(c[w]["power_inputs"], V.power_inputs(c[w]["cells"]))
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
            self.assertEqual(set(p), {"mean_bars", "vr_halves_bars_gap", "se_per_sd", "se_per_sd_same_day", "window", "end",
                                      "cells", "planned_bars", "nb_clock_vs_stored", "regime_blocks"}
                             | ({"rule_power"} if w == "decisive" else set()))
            n_xau = sum(out[c][w].get("high", 0) + out[c][w].get("low", 0) for c in V.GOLD)
            rb = p["regime_blocks"]                                  # the VR runs and the trades in them / by year
            self.assertEqual(sum(sum(y.values()) for y in rb["trades_by_year"].values()), n_xau)
            self.assertEqual("blocks" in rb, w == "decisive")        # the run list only for the decisive window
            if "blocks" in rb:
                self.assertEqual(sum(b["trades"] for b in rb["blocks"]), n_xau)
                self.assertEqual(rb["runs"]["high"] + rb["runs"]["low"], len(rb["blocks"]))
                self.assertEqual(sum(b["days"] for b in rb["blocks"]), rb["days_with_vr"])
        rp = out["xau_pooled"]["decisive"]["rule_power"]
        self.assertEqual((rp["sd_R"], rp["reps"], rp["seed"], set(rp["effects_R_bar"])),
                         (V.SD_R, 300, V.POWER_SEED, set(V.POWER_SHAPES)))
        self.assertEqual(set(rp["T1a"]), set(V.POWER_SHAPES))
        cd = out["causal_density"]                                   # the causal-density sensitivity's sample
        self.assertEqual(set(cd), set(V.GOLD) | {"XAUUSD_dense_days"})
        for c in V.GOLD:
            self.assertEqual(set(cd[c]), {"first_vr_day", "decisive", "report_only"})
            for w in ("decisive", "report_only"):
                x = cd[c][w]
                self.assertEqual(set(x), {"events", "high", "low", "no_vr", "no_sigma"})
                self.assertTrue(all(isinstance(v, int) for v in x.values()))
                self.assertEqual(x["events"], x["high"] + x["low"] + x["no_vr"])
        for w in ("decisive", "report_only"):
            dd = cd["XAUUSD_dense_days"][w]
            self.assertEqual(set(dd), {"days", "whole_history_rule", "causal_rule"})
            self.assertEqual(dd["causal_rule"], dd["whole_history_rule"] - V.CAUSAL_MIN_DAYS)   # complete days
        yrs = cd["XAUUSD_dense_days"]["by_year"]
        self.assertEqual(sum(y["days"] for y in yrs.values()), cd["XAUUSD_dense_days"]["report_only"]["days"])
        self.assertEqual(sum(y["causal_rule"] for y in yrs.values()), cd["XAUUSD_dense_days"]["report_only"]["causal_rule"])

    def test_the_refusable_counts_equal_an_independent_recount(self):
        """With a deterministic stand-in for the paper log's rule, the dry run's `refusable` block (reason, VR half, hold half;
        decisive and report-only windows) equals a recount done here from pit_events, the VR and the recorded hold median,
        on FTMO-shaped bars that cross the decisive window's end (events at many entry slots)."""
        EC, zone = V._ec(), V.server_zone()
        candles = ftmo_candles(datetime.date(2007, 6, 4), 520)
        s = EC.Series("XAUUSD", candles, zone, end=V.HIST_END)
        sp = EC.Series("XAUUSD", candles, zone, end=V.HIST_END, sigma_every_day=True)
        sc = V.causal_density(EC.Series("XAUUSD", candles, zone, end=V.HIST_END, sigma_every_day=True))
        rule = lambda ser, evs, ff=None: {ev["e"]: ("hole" if ev["e"] % 3 == 0 else "stale_vol") for ev in evs if ev["e"] % 2 == 0}
        BS = V._load("book_sim", "scripts/research/book_sim.py")
        with mock.patch.object(V, "POWER_REPS", 50), mock.patch.object(V, "paper_log_refusals", rule):
            out = V.dry_counts(series_fn=lambda sym: s, pit_series_fn=lambda sym: sp, zone=zone,
                               causal_series_fn=lambda sym: sc)
        vr, total = V.pit_vr_by_day(sp), collections.Counter()
        for c in V.GOLD + V.SILVER:
            evs, _ = V.pit_events(sp, BS.COMPONENTS[c][1], V.LOAD_END)
            slots = [V.slot_of(sp.dt[e["e"]], zone) for e in evs if e["day"] < V.HOLDOUT_END and e["day"] in vr]
            med = statistics.median(slots) if slots else None
            ref = rule(sp, evs)
            for w, end in (("decisive", V.HOLDOUT_END), ("report_only", V.REPORT_END)):
                want = collections.Counter()
                for e in evs:
                    if e["day"] >= end or e["day"] not in vr or e["e"] not in ref:
                        continue
                    want[ref[e["e"]]] += 1
                    want["high" if vr[e["day"]] > 1.0 else "low"] += 1
                    if med is not None:
                        want["long_hold" if V.slot_of(sp.dt[e["e"]], zone) < med else "short_hold"] += 1
                keys = ("hole", "stale_vol", "high", "low", "long_hold", "short_hold")
                self.assertEqual(out[c][w]["refusable"], {k: want.get(k, 0) for k in keys}, (c, w))
                if w == "decisive":
                    total.update({k: want.get(k, 0) for k in keys})
        self.assertTrue(all(total[k] > 0 for k in ("hole", "stale_vol", "high", "low", "long_hold", "short_hold")), total)
        self.assertGreater(out["H7_XAUUSD_eod"]["report_only"]["high"] + out["H7_XAUUSD_eod"]["report_only"]["low"],
                           out["H7_XAUUSD_eod"]["decisive"]["high"] + out["H7_XAUUSD_eod"]["decisive"]["low"])

    def test_nb_split_counts_holes_and_an_early_end(self):
        evs = [{"high": True, "long_hold": True, "nb": 168, "nb_stored": 150, "holes": 5, "early_end": 13},
               {"high": False, "long_hold": False, "nb": 40, "nb_stored": 39, "holes": 0, "early_end": 1},
               {"high": None, "long_hold": None, "nb": 10, "nb_stored": 1, "holes": 9, "early_end": 0}]   # no VR: out
        out = V._nb_split(evs)
        self.assertEqual(out["all"], {"n": 2, "nb_clock": 208, "nb_stored": 189, "short_gt12": 1, "with_holes": 1,
                                      "holes_bars": 5, "early_end_gt2": 1, "early_end_bars": 14})
        self.assertEqual((out["low"]["n"], out["long_hold"]["holes_bars"], out["short_hold"]["early_end_bars"]), (1, 5, 1))

    def test_the_dry_run_never_walks_a_trade(self):
        """Outcome-blind by construction (the sealing probe also traces the real run, VC-P1 §7): with every function that
        walks, prices or tests a trade replaced by a tripwire, the dry run completes."""
        def trip(*a, **k):
            raise AssertionError("the dry run reached an outcome")
        orig = V._load

        def load(name, rel):
            m = orig(name, rel)
            if name == "book_sim":
                m.trades = trip
            return m
        s, sp, sc = self.series(300)
        EC = V._ec()
        FF = V._load("fvg_forward", "scripts/research/fvg_forward.py")
        # the dry run may use the paper log's data-quality helpers (holes, _vol_fresh, _dt) and nothing else of it
        only_helpers = types.SimpleNamespace(holes=FF.holes, _vol_fresh=FF._vol_fresh, _dt=FF._dt,
                                             HOLE_LOOKBACK=FF.HOLE_LOOKBACK, resolve_row=trip, signals=trip)
        with mock.patch.object(V, "_load", load), mock.patch.object(V, "pit_trade", trip), \
                mock.patch.object(V, "pit_holdout_rows", trip), mock.patch.object(V, "xau_read", trip), \
                mock.patch.object(V, "_ff", lambda: only_helpers), mock.patch.object(V, "split_test", trip), \
                mock.patch.object(V, "diagnostics", trip), mock.patch.object(EC, "Costs", trip), \
                mock.patch.object(EC, "outcome", trip), mock.patch.object(EC, "t_sf", trip), \
                mock.patch.object(V, "POWER_REPS", 100):
            out = V.dry_counts(series_fn=lambda sym: s, pit_series_fn=lambda sym: sp, zone=UTC,
                               causal_series_fn=lambda sym: sc)
        self.assertIn("rule_power", out["xau_pooled"]["decisive"])
        self.assertIn("causal_density", out)

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
        # T1a on the nb-weighted R_bar (the VC-P1 §4 switch): NB_REF / bars over the VR cells; R_gross (T2, T3): 1 / n
        self.assertAlmostEqual(p["se_per_sd"]["T1a"], math.sqrt(0.25 * (2 / 100 + 2 * V.NB_REF / 12000)))
        self.assertAlmostEqual(p["se_per_sd"]["T1a_raw_R"], 0.1)
        self.assertIsNone(p["se_per_sd_same_day"]["T1a"])                    # cells without the same-day sums
        self.assertIsNone(V.power_inputs({})["se_per_sd"]["T1a"])

    def test_same_day_bound(self):
        """se_per_sd_same_day: the trades of one day in one cell perfectly correlated. Two trades on every day: the SE grows
        by sqrt(2) on both statistics; one trade a day: the bound is the independent SE."""
        def events(per_day, nb=144):
            out = []
            for k in range(800):
                ev = {"day": f"d{k}", "high": bool(k % 2), "long_hold": bool((k // 2) % 2),
                      "side": 1 if (k // 4) % 2 else -1, "nb": nb}
                out += [dict(ev) for _ in range(per_day)]
            return out
        two = V.power_inputs(V._cells(events(2)))
        for key in ("T1a", "T1b", "T1a_raw_R", "T1b_raw_R"):
            self.assertAlmostEqual(two["se_per_sd_same_day"][key], math.sqrt(2) * two["se_per_sd"][key], places=9)
        one = V.power_inputs(V._cells(events(1, nb=37)))
        for key in ("T1a", "T1b", "T1a_raw_R", "T1b_raw_R"):
            self.assertAlmostEqual(one["se_per_sd_same_day"][key], one["se_per_sd"][key], places=3)
        cell = V._cells(events(2, nb=37))["side=1|high"]
        self.assertEqual((cell["n"], cell["days"], cell["n2_days"], cell["rootnb2_days"]), (400, 200, 800, 200 * 4 * 37))


class Power(unittest.TestCase):
    """T1's full-rule power (VC-P1 §7, lead decision 2026-10-04): arithmetic on cell counts, no outcome."""

    def test_t_critical_values(self):
        """Against the Student-t quantiles of edge_census.t_sf (bisection): 1.993943, 1.666600, 1.976811, 2.228139."""
        for alpha, df, exact, tol in ((0.025, 71, 1.993943, 1e-5), (0.05, 71, 1.666600, 1e-5),
                                      (0.025, 142, 1.976811, 1e-5), (0.025, 10, 2.228139, 1e-4)):
            self.assertAlmostEqual(V._t_crit(alpha, df), exact, delta=tol)

    @staticmethod
    def cells(n_days=300, shared=False):
        """H7 and G9 events, one per component per day, on the same days (shared) or on alternate days; nb 144; sides and
        both splits balanced."""
        out = {c: [] for c in V.GOLD}
        for k in range(n_days):
            for j, c in enumerate(V.GOLD):
                day = f"d{k}" if shared else f"d{2 * k + j}"
                out[c].append({"day": day, "high": bool(k % 2), "long_hold": bool((k // 2) % 2),
                               "side": 1 if (k // 4) % 2 else -1, "nb": 144})
        return {c: V._cells(v) for c, v in out.items()}, V._cells(out[V.GOLD[0]] + out[V.GOLD[1]])

    def test_the_gate_costs_power_only_when_one_component_carries_the_effect(self):
        comp, pooled = self.cells()
        eq = V.rule_power(comp, pooled, "a", {c: 0.25 for c in V.GOLD}, reps=3000)
        self.assertGreater(eq["full_rule"], 0.95 * eq["holm"])
        self.assertAlmostEqual(eq["holm"], eq["pooled_alone"], delta=0.03)
        g9 = V.rule_power(comp, pooled, "a", {"H7_XAUUSD_eod": 0.0, "G9_XAUUSD_eod": 0.5}, reps=3000)
        self.assertLess(g9["full_rule"], 0.75 * g9["holm"])                  # H7's difference is > 0 only by chance
        null = V.rule_power(comp, pooled, "b", {c: 0.0 for c in V.GOLD}, reps=3000)
        self.assertLess(null["holm"], 0.06)
        self.assertEqual(V.rule_power(comp, pooled, "a", {c: 0.25 for c in V.GOLD}, reps=3000), eq)    # seeded

    def test_the_same_day_bound_lowers_power(self):
        comp, pooled = self.cells(shared=True)
        eff = {c: 0.25 for c in V.GOLD}
        ind = V.rule_power(comp, pooled, "b", eff, reps=3000)
        dep = V.rule_power(comp, pooled, "b", eff, same_day=True, reps=3000)
        self.assertLess(dep["full_rule"], ind["full_rule"] - 0.05)
        self.assertIsNone(V.rule_power(comp, {}, "a", eff, reps=10))


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
        self.assertEqual((out["a"]["statistic"], out["a"]["weight"]), ("R_bar", "nb_weight"))   # T1a's statistic, VC-P1 §4
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
        ref = snap["cost_profile"]["price_ref_info"]["XAUUSD"]                 # real_costs.price_ref_info (review item 4)
        self.assertEqual(len(ref["closes_sha256"]), 64)
        self.assertGreater(ref["price_ref"], 0)

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

    def test_the_dataset_is_pinned(self):
        """Review item 4 (lead decision 2026-10-04): the xau-holdout read refuses unless the stored 5m XAUUSD / XAGUSD history
        is the one the sealed text's dataset-sha256 lines and the ledger entry pin."""
        snap = {"XAUUSD|5m": "a" * 64, "XAGUSD|5m": "b" * 64}
        self.assertEqual(V.dataset_lines(snap), [f"dataset-sha256 {'b' * 64} XAGUSD|5m",
                                                 f"dataset-sha256 {'a' * 64} XAUUSD|5m"])
        text = "x\n```\n" + "\n".join(V.dataset_lines(snap)) + "\n```\n"
        self.assertEqual(V.require_dataset(text, snap, {"dataset": dict(snap)}), snap)
        cases = (("x\n", snap, {"dataset": dict(snap)}, "does not pin the dataset"),
                 (text + V.dataset_lines(snap)[0] + "\n", snap, {"dataset": dict(snap)}, "pinned twice"),
                 (text, {"XAUUSD|5m": "c" * 64, "XAGUSD|5m": "b" * 64}, {"dataset": dict(snap)}, "changed since the seal"),
                 (text, {"XAUUSD|5m": "a" * 64}, {"dataset": dict(snap)}, "snapshot covers"),
                 (text, snap, {}, "does not carry the sealed dataset"))
        for t, s, entry, msg in cases:
            with self.assertRaises(SystemExit) as cm:
                V.require_dataset(t, s, entry)
            self.assertIn(msg, str(cm.exception))

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


class SealRehearsal(unittest.TestCase):
    """VC-P1 §10 end to end in a temporary git repository that holds copies of the CODE files: every refusal before the
    seal, in the order the CLI checks them, then one read (its body stubbed: no history exists there, and nothing here
    reads any), then the read-once and code-change refusals. The stubs record whether a read body was ever reached."""
    OUT = "docs/audits/2026-10-05-edge-vc-xau-holdout.json"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        for args in (("init", "-q"), ("config", "user.email", "t@example.invalid"), ("config", "user.name", "t"),
                     ("config", "commit.gpgsign", "false"), ("config", "core.excludesFile", os.devnull)):
            self.git(*args)
        for p in V.CODE:
            dst = os.path.join(self.tmp, p)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(os.path.join(ROOT, p), dst)
        self.calls = []
        self.snap = {"XAUUSD|5m": "a" * 64, "XAGUSD|5m": "b" * 64}       # the stored history's digests (stubbed)

    def tearDown(self):
        V.G._TRACE["on"] = False
        shutil.rmtree(self.tmp, ignore_errors=True)

    def git(self, *args):
        subprocess.run(["git", "-C", self.tmp, *args], check=True, capture_output=True, text=True)

    def write(self, rel, text):
        p = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)

    def commit(self, *rels):
        self.git("add", "-f", *rels)
        self.git("commit", "-q", "-m", "x")

    def cli(self, *argv):
        def body(*a, **k):
            self.calls.append("xau_read")
            return {"T1_verdict": {"T1a_volatility": False, "T1b_hold_length": False, "holm_rejected": [False, False],
                                   "reading": "NOT SHOWN (stub)"}, "hold_medians": {}}
        with mock.patch.object(V, "ROOT", self.tmp), mock.patch.object(V, "xau_read", body), \
                mock.patch.object(V, "cost_profile", lambda syms: {}), \
                mock.patch.object(V.G, "dataset_snapshot", lambda root, pairs: dict(self.snap)), \
                mock.patch.object(V, "_forward", lambda a, res: self.calls.append("forward")), \
                mock.patch.object(V, "_crypto", lambda a, res: self.calls.append("crypto")), \
                mock.patch.object(sys, "argv", ["edge_vc.py", *argv]), contextlib.redirect_stdout(io.StringIO()):
            V.main()

    def refused(self, *argv):
        with self.assertRaises(SystemExit) as cm:
            self.cli(*argv)
        return str(cm.exception)

    def test_every_step_refuses_until_the_seal_is_complete(self):
        out = os.path.join(self.tmp, self.OUT)
        run = ("run", "--read", "xau-holdout", "--out", out)
        head = f"# VC {V.TAG}\n\nStatus: SEALED\n"
        man = "\n```\n" + "\n".join(V.G.manifest_lines(self.tmp, V.CODE)) + "\n```\n"
        pinned = "\n```\n" + "\n".join(V.dataset_lines(self.snap)) + "\n```\n"
        entry = {"preregistration": V.PREREG, "tag": V.TAG}
        self.assertIn("does not exist", self.refused(*run))                    # 0. before the seal
        self.write(V.PREREG, head + man)
        self.assertIn("not tracked", self.refused(*run))                       # 1. sealed text not committed
        self.commit(V.PREREG)
        self.assertIn("not tracked", self.refused(*run))                       # 2. the code not committed
        self.write(V.PREREG, head)
        self.commit(V.PREREG, *V.CODE)
        self.assertIn("does not list", self.refused(*run))                     # 3. no manifest pasted
        self.write(V.PREREG, head + man)
        self.commit(V.PREREG)
        self.assertIn(V.LEDGER, self.refused(*run))                            # 4. no research ledger
        self.write(V.LEDGER, json.dumps({"oos": {}}))
        self.commit(V.LEDGER)
        self.assertIn(V.LEDGER_KEY, self.refused(*run))                        # 5. ledger without the study entry
        self.write(V.LEDGER, json.dumps({V.LEDGER_KEY: entry}))
        self.commit(V.LEDGER)
        self.assertIn("does not pin the dataset", self.refused(*run))          # 6. no dataset-sha256 lines (§7)
        sealed = head + man + pinned
        self.write(V.PREREG, sealed)
        self.commit(V.PREREG)
        self.assertIn("does not carry the sealed dataset", self.refused(*run))  # 7. ledger entry without `dataset`
        self.write(V.LEDGER, json.dumps({V.LEDGER_KEY: dict(entry, dataset=dict(self.snap))}))
        self.commit(V.LEDGER)
        real = dict(self.snap)
        self.snap["XAUUSD|5m"] = "c" * 64                                      # 8. the history re-imported
        self.assertIn("changed since the seal", self.refused(*run))
        self.snap = real
        with mock.patch.object(sys, "pycache_prefix", os.path.join(self.tmp, "pyc")):
            self.assertIn("pycache_prefix", self.refused(*run))               # 9. bytecode outside the repository
        self.assertEqual((self.calls, os.path.exists(out)), ([], False))      # no read body reached, nothing written
        self.cli(*run)                                                         # 10. sealed and registered: one read
        self.assertEqual(self.calls, ["xau_read"] * 4)                         # k 1.4; k 2.0, research, causal reports
        with open(out, encoding="utf-8") as fh:
            meta = json.load(fh)["meta"]
        self.assertEqual((meta["read"], meta["code_sha256"]), ("xau-holdout", V.G.manifest(sealed)))
        self.assertEqual(meta["ledger"]["sha256"], V.G.file_sha256(os.path.join(self.tmp, V.LEDGER)))
        self.assertEqual(meta["dataset"], self.snap)
        again = os.path.join(self.tmp, "docs/audits/2026-10-06-edge-vc-xau-holdout.json")
        self.assertIn("already ran", self.refused("run", "--read", "xau-holdout", "--out", again))     # 11. read once
        with open(os.path.join(self.tmp, "scripts/research/edge_census.py"), "a", encoding="utf-8") as fh:
            fh.write("\n# edited after the seal\n")
        self.commit("scripts/research/edge_census.py")
        fwd = os.path.join(self.tmp, "docs/audits/2026-11-01-edge-vc-forward.json")
        self.assertIn("code changed since the seal",                           # 12. code edited after the seal
                      self.refused("run", "--read", "forward", "--xau", "x.json", "--out", fwd))
        self.assertEqual(self.calls, ["xau_read"] * 4)

    def test_a_dry_run_never_takes_a_read_name(self):
        """A dry-run file at a read's output name would make require_read_once refuse that read for good (once committed)."""
        with mock.patch.object(V, "dry_counts", lambda *a, **k: self.calls.append("dry_counts") or {}):
            for read in V.READS:
                out = os.path.join(self.tmp, f"docs/audits/2026-10-05-edge-vc-{read}.json")
                self.assertIn("a read's output name", self.refused("dry-run", "--out", out))
                self.assertFalse(os.path.exists(out))
            self.assertEqual(self.calls, [])
            self.cli("dry-run", "--out", os.path.join(self.tmp, "dry.json"))
            self.assertEqual(self.calls, ["dry_counts"])


if __name__ == "__main__":
    unittest.main()
