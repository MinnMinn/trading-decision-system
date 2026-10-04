"""scripts/research/wyckoff_wcx.py on SYNTHETIC and HAND-BUILT bars only (no real history, no outcome on market data).
Pre-registration: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md [WY-X1] (§14).

LIFECYCLE-PROOF: this file is in the sealed code manifest (wyckoff_wcx.CODE), so editing it after the seal blocks the read
until a re-seal. No test may depend on the seal state: every guard test checks its rule on a sealed name, an output, a
ledger and a counts record that the test itself makes absent or builds in a temporary root. The suite passes before the
seal, after it, and after the read.

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_wyckoff_wcx
"""
import contextlib
import datetime
import hashlib
import importlib.util
import io
import json
import math
import os
import random
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


X = _load("wyckoff_wcx", "scripts/research/wyckoff_wcx.py")
EW = X.EW
BT = EW.engine()
UTC = datetime.timezone.utc
START = "2023-05-07T21:00:00Z"            # server midnight (UTC+3, US DST active: no clock change inside the books)


# ------------------------------------------------------------------------------------------------ synthetic bars
def leg(start, end, n, vol=10.0):
    """n bars ramping start -> end with a 0.05 wick each side (test_edge_wyckoff's shape)."""
    out = []
    for i in range(n):
        c = start + (end - start) * (i + 1) / n
        o = start + (end - start) * i / n
        out.append((o, max(o, c) + 0.05, min(o, c) - 0.05, c, vol))
    return out


def rising(n, a=100.0, b=104.0):
    """A rising zigzag (never a downtrend, so never a selling climax)."""
    out, p = [], a
    for i in range(n):
        q = a + (b - a) * (i + 1) / n + (0.3 if i % 2 else -0.3)
        out.append((p, max(p, q) + 0.1, min(p, q) - 0.1, q, 10.0))
        p = q
    return out


def base():
    """Downtrend -> SC 79.95 -> AR 110.05 -> ST -> CHoBEV up-swings -> Phase-B swings (cause gate passes, not sloped)."""
    b = leg(104, 102, 5) + leg(102, 99, 5) + leg(99, 101, 5) + leg(101, 97, 5)
    b += leg(97, 100, 5) + leg(100, 90, 5) + leg(90, 96, 5) + leg(96, 80, 5)
    b += leg(80, 110, 6) + leg(110, 85, 6) + leg(85, 108, 6) + leg(108, 88, 6) + leg(88, 106, 6)
    return b + leg(106, 90, 6) + leg(90, 100, 6) + leg(100, 92, 6)


def scenario(kind):
    """spring: break and reclaim on one bar (SPRING); shakeout: two closes below, reclaim at s+2, Test next bar (SHAKEOUT);
    cancelled: a Shakeout whose next bar makes a lower low (no event)."""
    b = base() + leg(92, 82, 4)
    if kind == "spring":
        b += [(82, 82.5, 78, 81, 20.0)] + leg(81, 86, 3, vol=5.0)
    elif kind == "shakeout":
        b += [(82, 82.5, 78, 79.0, 20.0), (79.0, 79.6, 77.5, 79.2, 20.0), (79.2, 81.2, 79.0, 80.9, 10.0),
              (80.9, 82.4, 80.2, 82.2, 5.0)] + leg(82.2, 86, 2)
    elif kind == "cancelled":
        b += [(82, 82.5, 78, 79.0, 20.0), (79.0, 79.6, 77.5, 79.2, 20.0), (79.2, 81.2, 79.0, 80.9, 10.0),
              (80.9, 81.0, 77.0, 78.5, 5.0), (78.5, 84, 78.4, 83.8, 5.0)] + leg(83.8, 86, 2)
    return b + leg(86, 108, 6) + [(108, 114, 107.5, 113.5, 30.0), (113.5, 114.5, 112, 114, 10.0)] + leg(114, 118, 5)


def walk_bars(n, seed, p=100.0):
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        q = p * math.exp(rnd.gauss(0, 0.003))
        out.append((p, max(p, q) * (1 + abs(rnd.gauss(0, 0.001))), min(p, q) * (1 - abs(rnd.gauss(0, 0.001))), q, 10.0))
        p = q
    return out


def book(seed, kinds=("spring", "shakeout", "cancelled", "spring")):
    bars = rising(400)
    for kind in kinds:
        bars += scenario(kind) + leg(118, 101, 6) + rising(60, 100.5, 104.0)
    bars += walk_bars(500, seed, bars[-1][3])
    off = 1.0 + 0.01 * (seed % 7)
    return [(o * off, h * off, lo * off, c * off, v) for (o, h, lo, c, v) in bars]


def candles(bars, start=START, minutes=15):
    t0 = datetime.datetime.fromisoformat(start.replace("Z", "+00:00"))
    return [{"time": (t0 + datetime.timedelta(minutes=minutes * i)).strftime("%Y-%m-%dT%H:%M:%SZ"), "open": o, "high": h,
             "low": lo, "close": c, "volume": v} for i, (o, h, lo, c, v) in enumerate(bars)]


def daily(c15):
    out = {}
    for c in c15:
        d = c["time"][:10] + "T00:00:00Z"
        o = out.get(d)
        if o is None:
            out[d] = dict(c, time=d)
        else:
            o.update(high=max(o["high"], c["high"]), low=min(o["low"], c["low"]), close=c["close"])
    return list(out.values())


class FakeLoader:
    """15m books (and their 1D companions) for any symbol name; records every call."""

    def __init__(self, kinds=("spring", "shakeout", "cancelled", "spring")):
        self.calls, self._c, self.kinds = [], {}, kinds

    def __call__(self, sym, tf):
        self.calls.append((sym, tf))
        if sym not in self._c:
            self._c[sym] = candles(book(sum(map(ord, sym)), self.kinds))
        if tf == "15m":
            return self._c[sym], {"path": "synthetic", "bars": len(self._c[sym])}
        if tf == "1D":
            return daily(self._c[sym]), {"path": "synthetic"}
        return [], {"path": None}


def dense_for(*syms):
    return {f"{s}|15m": {"start": START[:10]} for s in syms}


def boom(*a, **k):
    raise AssertionError("market data or an outcome function was touched")


def fake_cost_r(entry, stop, t_in, t_out, sym, side, profile, stat="median"):
    assert profile == EW.COST_PROFILE
    spread = 0.02 if stat == "median" else 0.03
    return {"total_R": spread + 0.01, "swap_R": 0.01, "spread_R": spread, "commission_R": 0.0}


class EntryHourCost:
    """A cost_r stand-in for the counts: it refuses any call whose exit differs from its entry (an exit-dependent cost is
    an outcome) and records the calls."""

    def __init__(self):
        self.calls = []

    def __call__(self, entry, stop, t_in, t_out, sym, side, profile, stat="median"):
        if t_in != t_out:
            raise AssertionError("the counts priced a trade's exit")
        self.calls.append((sym, t_in, stat))
        return {"spread_R": 0.05 if stat == "median" else 0.08, "swap_R": 0.0, "total_R": 0.05, "commission_R": 0.0}


def fake_price_ref(profile, sym):
    """A real_costs.price_ref_info stand-in (the real one reads committed history)."""
    assert profile == EW.COST_PROFILE
    return {"price_ref": 100.0 + len(sym), "n_bars": 10, "window_utc": ["2022-07-01T00:00:00Z", "2026-10-01T00:00:00Z"],
            "first_bar": "2022-07-01T00:00:00Z", "last_bar": "2026-09-30T23:45:00Z", "timeframe": "15m",
            "closes_sha256": f"{sum(map(ord, sym)):064x}"}


def walk(o):
    """Every dict / list nested in o."""
    yield o
    if isinstance(o, dict):
        for v in o.values():
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)


def quiet():
    return contextlib.redirect_stdout(io.StringIO())


# ------------------------------------------------------------------------------------------------ registration
class Registration(unittest.TestCase):
    def test_the_cell_and_the_measurement_are_the_retests_unchanged(self):
        self.assertEqual(X.CFG, EW.BASE_CFG)
        self.assertEqual((X.CELL, X.TF, X.LEG, X.SIDE), ("W-C-long-15m", "15m", "W-C", "long"))
        self.assertEqual(X.LINES, EW.FTMO_LINES)
        self.assertEqual(X.PRIMARY, "median_swap")
        self.assertEqual((X.DELTA, X.AGAINST_P), (EW.DELTA, EW.AGAINST_P))
        self.assertEqual(X.HYPOTHESES, ("W-C-long-15m",))            # WY-X1 §4: no variant is supported by the records
        self.assertIn(X.ALPHA, (0.05, 0.10))
        self.assertEqual(X.DECISION, "gross")                        # WY-X1 §6 registered; "net" = RT's H-WC
        self.assertEqual(X.decision_lines("gross"), ("gross",) + EW.FTMO_LINES)
        self.assertEqual(X.decision_lines("net"), EW.FTMO_LINES + ("gross",))
        self.assertEqual(X.SD_PLAN, (2.2, 2.8))                      # WY-X1 §7: this pool's planned R:R, not R1's
        self.assertAlmostEqual(math.sqrt(4.23), 2.06, places=2)      # RT §8's rule at X0's mean planned R:R
        self.assertAlmostEqual(2.09 / math.sqrt(2.39) * math.sqrt(4.23), 2.78, places=2)   # x R1's measured ratio
        self.assertEqual(X.replicated_label("gross"), "REPLICATED (gross, history)")
        self.assertEqual(X.replicated_label("net"), "REPLICATED (net, history)")
        self.assertIn("discovery grade", X.__doc__.splitlines()[0])  # RD §0: UNREAD-FOR-H is "valid as discovery"
        self.assertNotIn("confirmatory", X.__doc__.split("\n\n")[0])

    def test_the_pool_is_rt_replication_symbols_with_a_15m_dense_start_and_never_an_exposed_one(self):
        rt = {s for c in EW.REPLICATION.values() for s in c}
        self.assertTrue(set(X.POOL) <= rt)
        self.assertFalse(set(X.POOL) & set(EW.TRADEABLE))
        self.assertFalse(set(X.OPTIONAL) & set(EW.TRADEABLE))
        self.assertEqual(set(X.EXPOSED), set(EW.TRADEABLE))
        with open(os.path.join(ROOT, X.R0_PATH), encoding="utf-8") as fh:
            dense = json.load(fh)["dense"]
        for s in X.POOL:
            self.assertTrue(dense[f"{s}|15m"]["start"], s)
        for s in ("EU50", "HK50"):                                   # why they are optional, not pool (WY-X1 §3)
            self.assertIsNone(dense[f"{s}|15m"]["start"])
        self.assertEqual(sorted(rt - set(X.POOL)), ["EU50", "HK50"])

    def test_the_clusters_are_rt_r2s(self):
        for c, syms in EW.REPLICATION.items():
            for s in syms:
                self.assertEqual(X.CLUSTER_OF[s], c)
        self.assertEqual((X.CLUSTER_OF["N25"], X.CLUSTER_OF["SPN35"]), ("EU", "EU"))

    def test_code_is_ew_code_without_tests_plus_this_script_its_tests_the_guard_and_extra_code(self):
        self.assertEqual(len(X.CODE), len(set(X.CODE)))
        self.assertEqual(set(X.R0_PINNED), {p for p in EW.CODE if not p.startswith("scripts/tests/")})
        self.assertEqual(set(X.CODE), {X.SCRIPT, X.TESTS_FILE, X.GUARD} | set(X.R0_PINNED) | set(X.EXTRA_CODE))
        self.assertFalse(set(X.EXTRA_CODE) & set(EW.CODE))           # R0 does not fingerprint them: blob-pinned
        self.assertEqual([p for p in X.CODE if p.startswith("scripts/tests/")], [X.TESTS_FILE])
        for p in (X.SCRIPT, X.TESTS_FILE, X.GUARD, "scripts/research/edge_wyckoff.py", "scripts/wyckoff_rules.py",
                  "scripts/backtest-methods.py", "scripts/real_costs.py", "docs/architecture/instruments.json",
                  "scripts/method_purity.py"):
            self.assertIn(p, X.CODE)
        for p in X.CODE:
            self.assertTrue(os.path.exists(os.path.join(ROOT, p)), p)
        self.assertNotIn(X.LEDGER, X.CODE)                            # other studies append to the ledger

    def test_the_r0_pin_covers_what_a_read_runs_and_not_other_studies_tests(self):
        cur = {p: X._sha256(os.path.join(ROOT, p)) for p in X.R0_PINNED}
        r0 = {"meta": {"code_sha256": dict(cur, **{"scripts/tests/test_edge_wyckoff.py": "f" * 64})}}
        self.assertEqual(X.r0_drift(r0), [])
        r0["meta"]["code_sha256"]["scripts/wyckoff_rules.py"] = "0" * 64
        self.assertEqual(X.r0_drift(r0), ["scripts/wyckoff_rules.py"])

    def test_every_module_this_process_imported_is_in_code(self):
        self.assertEqual(sorted(p for p in EW._loaded_code() if p not in X.CODE), [])

    def test_a_traced_read_path_executes_only_code_files(self):
        """A fresh interpreter starts the guard's trace BEFORE loading WX (stricter than the read, whose trace starts after
        the imports), then runs the read's core on synthetic bars and builds the read's meta. Every repository .py file it
        opened (source or bytecode, by import or by file location) must be in CODE: this is the check that found
        scripts/method_purity.py (htf_context.py loads it by file location, outside sys.modules)."""
        prog = "\n".join([
            "import importlib.util, json, os, sys",
            "root = sys.argv[1]",
            "def load(name, rel):",
            "    spec = importlib.util.spec_from_file_location(name, os.path.join(root, rel))",
            "    m = importlib.util.module_from_spec(spec)",
            "    spec.loader.exec_module(m)",
            "    return m",
            "g = load('guard_trace_probe', 'scripts/research/prereg_guard.py')",
            "g.trace_start(root)",
            "T = load('t_wcx_trace_probe', 'scripts/tests/test_wyckoff_wcx.py')",
            "syms = ('XPTUSD', 'XPDUSD')",
            "res = T.X.read_core(syms, T.FakeLoader(), T.dense_for(*syms), T.EW.Pricer('ftmo', cost_r=T.fake_cost_r),",
            "                    window=(None, '2023-06-30T00:00:00Z'))",
            "T.X.meta('read')",
            "print(json.dumps({'executed': sorted(g.executed_code()), 'loaded': sorted(T.EW._loaded_code()),",
            "                  'n': res['summary']['n']}))"])
        p = subprocess.run([sys.executable, "-B", "-W", "ignore", "-c", prog, ROOT], capture_output=True, text=True,
                           timeout=600, cwd=os.path.join(ROOT, "scripts", "tests"))
        self.assertEqual(p.returncode, 0, p.stderr[-2000:])
        got = json.loads(p.stdout.strip().splitlines()[-1])
        self.assertEqual(got["n"], 6)
        self.assertIn("scripts/research/edge_wyckoff.py", got["executed"])        # the trace saw the imports
        self.assertIn("scripts/method_purity.py", got["executed"])
        self.assertEqual(sorted(set(got["executed"]) - set(X.CODE)), [])
        self.assertEqual(sorted(set(got["loaded"]) - set(X.CODE)), [])

    def test_the_window_end_is_a_fixed_saturday_midnight_before_any_forward_bar(self):
        end = datetime.datetime.fromisoformat(X.WINDOW_END.replace("Z", "+00:00"))
        self.assertEqual((end.weekday(), end.hour, end.minute), (5, 0, 0))
        self.assertLess(X.WINDOW_END, "2026-10-04T00:00:00Z")       # WY-F1's forward window cannot start earlier
        self.assertEqual(X.WINDOW, (None, X.WINDOW_END))

    def test_the_sealed_name_is_not_the_draft_and_the_draft_is_not_sealed(self):
        self.assertFalse(X.PREREG.endswith("-DRAFT.md"))
        self.assertEqual(X.PREREG_DRAFT, X.PREREG.replace(".md", "-DRAFT.md"))
        draft = os.path.join(ROOT, X.PREREG_DRAFT)
        if not os.path.exists(draft):                               # sealing may drop the draft, never before the seal
            self.assertTrue(os.path.exists(os.path.join(ROOT, X.PREREG)))
            return
        with open(draft, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn(X.TAG, text)
        with self.assertRaises(SystemExit):
            X.G.check_sealed_text(text, X.PREREG, X.TAG)

    def test_every_public_docstring_cites_the_preregistration(self):
        for name in dir(X):
            f = getattr(X, name)
            if callable(f) and getattr(f, "__module__", None) == X.__name__ and not name.startswith("_") \
                    and f.__doc__ and len(f.__doc__) > 120:
                self.assertIn("WY-X1", f.__doc__, name)


# ------------------------------------------------------------------------------------------------ X0: counts
class Counts(unittest.TestCase):
    def run_counts(self, loader, pool=("XPTUSD", "XPDUSD"), cost=None, **kw):
        kw.setdefault("price_ref", fake_price_ref)
        with tempfile.TemporaryDirectory() as d, quiet():
            out = os.path.join(d, "x0.json")
            rec = X.counts(out, loader=loader, pool=pool, optional=(), exposed=(), corr=False,
                           dense=dense_for(*pool), cost_r=cost or EntryHourCost(), **kw)
            with open(out, encoding="utf-8") as fh:
                disk = json.load(fh)
        return rec, disk

    def test_counts_pin_the_price_reference_and_refuse_another_hour_frame(self):
        rec, disk = self.run_counts(FakeLoader())
        self.assertEqual(disk["price_ref"], {s: fake_price_ref(EW.COST_PROFILE, s) for s in ("XPTUSD", "XPDUSD")})
        self.assertNotIn("price_ref", self.run_counts(FakeLoader(), price_ref=None)[1])
        with tempfile.TemporaryDirectory() as d, mock.patch.object(X.RC, "HOUR_FRAME", "utc_legacy"), \
                self.assertRaises(SystemExit) as cm:
            X.counts(os.path.join(d, "x.json"), loader=boom, price_ref=boom, cost_r=boom)
        self.assertIn("HOUR_FRAME", str(cm.exception))

    def test_counts_find_every_event_and_compute_no_outcome(self):
        loader, cost = FakeLoader(), EntryHourCost()
        with mock.patch.object(EW, "score", boom), mock.patch.object(EW, "walk_from", boom), \
                mock.patch.object(BT, "walk", boom), mock.patch.object(X.RC, "cost_r", boom), \
                mock.patch.object(EW, "score_campaign", boom), mock.patch.object(EW, "placebo_draw", boom):
            rec, disk = self.run_counts(loader, cost=cost)
        for s in ("XPTUSD", "XPDUSD"):
            w = rec["symbols"][s]["window"]
            self.assertEqual((w["placeable"], w["by_type"]), (3, {"SPRING": 2, "SHAKEOUT": 1}), s)
            self.assertEqual(rec["symbols"][s]["pre"]["placeable"], 3)      # 2023: all before 2024-03-01
            self.assertEqual(rec["symbols"][s]["post"]["placeable"], 0)
            self.assertEqual(rec["symbols"][s]["spread_r_entry"]["median"]["median"], 0.05)
        self.assertEqual(rec["pool"]["placeable"], 6)
        self.assertEqual(len(cost.calls), 12)                              # 6 events x {median, p90}, entry hour only
        for o in walk(disk):
            if isinstance(o, dict):
                self.assertFalse(set(o) & set(X.OUTCOME_KEYS), sorted(set(o) & set(X.OUTCOME_KEYS)))
        self.assertIn("outcome_blind", disk)

    def test_the_counted_events_are_ew_detect_series_events(self):
        loader = FakeLoader()
        rec, _ = self.run_counts(loader, pool=("XPTUSD",))
        S = EW.make_series("XPTUSD", "15m", loader, dense_for("XPTUSD"), X.CFG)
        ref = EW.detect_series(S, X.CFG, EW.det_params(X.CFG), BT.P["15m"]["sob"], None)["W-C"]
        ref = [e for e in ref if EW.kept(S, e, *X.WINDOW) and EW.placeable("long", S.O[e["e"]], e["stop"], e["target"])]
        self.assertEqual([f["signal_time"] for f in rec["events"]["XPTUSD"]], [S.T[e["k"]] for e in ref])
        self.assertEqual([f["type"] for f in rec["events"]["XPTUSD"]], [e["type"] for e in ref])

    def test_an_alt_pool_symbol_is_counted_with_the_ref_year_2025_start_and_an_exposed_one_never_joins(self):
        loader = FakeLoader()
        start = {"start": START[:10], "ref_median": 96, "holes": 0, "last_hole_end": None, "months": {}}

        def fake_dense_start(sday, dts, ref_year=EW.DENSE_REF_YEAR):
            return dict(start) if ref_year == X.ALT_REF_YEAR else dict(start, start=None)
        with mock.patch.object(EW, "dense_start", fake_dense_start):
            rec, _ = self.run_counts(loader, pool=("XPTUSD",), alt_pool=("XPDUSD",))
        self.assertEqual(rec["pool"]["symbols"], ["XPTUSD", "XPDUSD"])
        self.assertEqual(rec["symbols"]["XPDUSD"]["window"]["placeable"], 3)
        self.assertIn("ALT_POOL", rec["symbols"]["XPDUSD"]["dense_rule"])
        self.assertEqual(rec["dense_alt_pool"]["XPDUSD|15m"]["start"], START[:10])
        self.assertEqual(rec["probe"]["checked"], 6)
        self.assertEqual(X.ALT_POOL, ())                                         # registered default: RT §4's rule only
        with tempfile.TemporaryDirectory() as d, self.assertRaises(SystemExit):
            X.counts(os.path.join(d, "x.json"), loader=boom, pool=("XPTUSD",), alt_pool=("DE40",), price_ref=boom)

    def test_the_probe_passes_on_the_counted_events(self):
        rec, _ = self.run_counts(FakeLoader())
        self.assertEqual((rec["probe"]["checked"], rec["probe"]["violations"], rec["probe"]["ok"]), (6, 0, True),
                         rec["probe"]["first_violation"])

    def test_the_report_renders_counts_and_power_and_no_outcome(self):
        rec, disk = self.run_counts(FakeLoader())
        md = X.report(disk)
        self.assertIn("# WY-X1 counts (X0, outcome-blind)", md)
        self.assertIn("| XPTUSD | pool |", md)
        self.assertIn("Pool: 6 events", md)
        self.assertNotIn("# WY-X1 read", md)
        x1 = {"summary": {"n": 6, "net_excess": 0.1, "p_one_sided": 0.2, "upper_95": 0.9,
                          "lines": {"median_swap": {"mean": 0.05}}},
              "verdict": {"label": "NOT REPLICATED"}, "decision": "gross"}
        self.assertIn("Label: **NOT REPLICATED** (decision line: gross)", X.report(disk, x1))

    def test_counts_refuse_to_overwrite(self):
        with tempfile.NamedTemporaryFile(suffix=".json") as fh, self.assertRaises(SystemExit):
            X.counts(fh.name, loader=boom, price_ref=boom)

    def test_window_membership_is_the_entry_bar_and_the_split_is_2024_03_01(self):
        S = EW.Series("XPTUSD", "15m", candles(rising(400), start="2024-02-28T00:00:00Z"), UTC,
                      datetime.date(2024, 2, 28))
        k = next(i for i, t in enumerate(S.T) if t == "2024-02-29T23:30:00Z")
        ev = {"k": k, "e": k + 1}                                   # entry bar 23:45 -> closes at 2024-03-01T00:00Z
        self.assertTrue(X.in_window(S, ev, None, X.DEV_CUTOFF))
        self.assertFalse(X.in_window(S, dict(ev, e=k + 2), None, X.DEV_CUTOFF))
        self.assertTrue(X.in_window(S, dict(ev, e=k + 2), X.DEV_CUTOFF, None))
        self.assertFalse(X.in_window(S, dict(ev, e=len(S)), None, None))       # no entry bar: never counted

    def test_tally_is_r0s_rule(self):
        f = [dict(prev_dense=False, placeable=True, type="SPRING", entry_time="2020-01-01"),
             dict(prev_dense=True, placeable=False, type="SPRING", entry_time="2020-01-01"),
             dict(prev_dense=True, placeable=True, type="SHAKEOUT", entry_time="2021-05-01")]
        t = X.tally(f)
        self.assertEqual((t["signals"], t["kept"], t["placeable"]), (3, 2, 1))
        self.assertEqual(t["skips"], {"previous_server_day_not_dense": 1, "entry_beyond_stop_or_target": 1})
        self.assertEqual((t["by_type"], t["by_year"]), ({"SHAKEOUT": 1}, {"2021": 1}))

    def test_the_data_pin_moves_with_a_revised_bar_and_not_with_an_appended_one(self):
        c = candles(rising(200), start="2026-09-24T00:00:00Z")
        d0 = X.window_digest(c)
        self.assertEqual(d0["bars"], sum(1 for x in c if x["time"] < "2026-09-25T23:45:00Z") + 1)
        appended = c + candles(rising(10), start="2026-10-10T00:00:00Z")
        self.assertEqual(X.window_digest(appended)["sha256"], d0["sha256"])
        revised = [dict(x) for x in c]
        revised[3]["close"] += 0.01
        self.assertNotEqual(X.window_digest(revised)["sha256"], d0["sha256"])
        late = [dict(x) for x in c]
        late[-1]["close"] += 0.01                                    # after the window end: not pinned
        self.assertEqual(X.window_digest(late)["sha256"], d0["sha256"])

    def test_overlap_and_years(self):
        facts = [dict(prev_dense=True, placeable=True, week="2023-W19", server_day="2023-05-10"),
                 dict(prev_dense=True, placeable=True, week="2023-W20", server_day="2023-05-17"),
                 dict(prev_dense=True, placeable=False, week="2023-W19", server_day="2023-05-10")]
        o = X.overlap(facts, {"2023-W19"}, {"2023-05-17"})
        self.assertEqual((o["n"], o["same_week"], o["same_server_day"]), (2, 1, 1))
        self.assertAlmostEqual(X.years_between("2020-01-01", "2030-01-01T00:00:00Z"),
                               (datetime.datetime.fromisoformat(X.WINDOW_END.replace("Z", "+00:00"))
                                - datetime.datetime(2020, 1, 1, tzinfo=UTC)).days / 365.25, places=2)

    def test_daily_correlation(self):
        loader = FakeLoader()
        d = loader("XPTUSD", "1D")[0]
        inv = [dict(x, close=1e4 / x["close"]) for x in d]                    # log returns exactly negated

        def two(sym, tf):
            return (d if sym == "XPTUSD" else inv), {}
        self.assertGreater(len(d), 10)
        self.assertAlmostEqual(X.daily_corr(two, "XPTUSD", "XPTUSD", frm="2023-01-01", min_days=5)["corr"], 1.0,
                               places=9)
        self.assertAlmostEqual(X.daily_corr(two, "XPTUSD", "XPDUSD", frm="2023-01-01", min_days=5)["corr"], -1.0,
                               places=9)
        self.assertIsNone(X.daily_corr(two, "XPTUSD", "XPDUSD", frm="2023-01-01", min_days=10_000)["corr"])

    def test_the_r0_crosscheck_lists_every_difference(self):
        per = {"XAUUSD": {"pre": {"placeable": 20}, "rt_post": {"placeable": 4}},
               "XPTUSD": {"pre": {"placeable": 11}}}
        r0 = {"dense": {"XPTUSD|15m": {"start": "2017-04-01"}},
              "reads": {"R1": {X.CELL: {"by_symbol": {"XAUUSD": 20}}}, "R3": {X.CELL: {"by_symbol": {"XAUUSD": 4}}},
                        "R2": {X.CELL: {"by_symbol": {"XPTUSD": 12}}}}}
        self.assertEqual(X.r0_crosscheck(r0, per, {"XPTUSD|15m": {"start": "2017-04-01"}}), ["R2 XPTUSD: R0 12 != 11"])
        self.assertEqual(X.r0_crosscheck(r0, per, {"XPTUSD|15m": {"start": "2018-01-01"}})[0],
                         "dense XPTUSD|15m: R0 2017-04-01 != 2018-01-01")


# ------------------------------------------------------------------------------------------------ the truncation probe
class TruncationProbe(unittest.TestCase):
    def setUp(self):
        self.loader = FakeLoader()
        self.dense = dense_for("XPTUSD")
        self.S = EW.make_series("XPTUSD", "15m", self.loader, self.dense, X.CFG)
        self.P = EW.det_params(X.CFG)

    def events(self, fire):
        out, seen = [], set()
        for k in range(X.CFG["window"] - 1, len(self.S)):
            for e in fire(self.S, k, X.CFG, self.P, BT.P["15m"]["sob"])[0]:
                if e["leg"] == "W-C" and (e["leg"], e["key"]) not in seen:
                    seen.add((e["leg"], e["key"]))
                    out.append(EW.enrich(e, self.S, None))
        return out

    def test_every_counted_event_re_detects_identically_on_the_cut_series(self):
        evs = [e for e in X.detect(self.S)["W-C"]]
        self.assertEqual(len(evs), 3)
        rep = EW.probe(evs, self.loader, self.dense, X.CFG, "W")
        self.assertEqual((rep["checked"], rep["violations"], rep["ok"]), (3, 0, True), rep["first_violation"])

    def test_a_detector_that_reads_the_next_bar_is_caught(self):
        def leaky(S, k, cfg, P, sob, pidx=None):
            evs, logs = EW.window_fire(S, k, cfg, P, sob, pidx)
            for e in evs:
                e["stop"] = S.L[k + 1] if k + 1 < len(S) else S.L[k]          # look-ahead
            return evs, logs
        evs = self.events(leaky)
        self.assertTrue(evs)
        rep = EW.probe(evs, self.loader, self.dense, X.CFG, "W", fire=leaky)
        self.assertGreater(rep["violations"], 0)
        self.assertFalse(rep["ok"])

    def test_an_empty_probe_is_not_a_pass(self):
        self.assertFalse(EW.probe([], self.loader, self.dense, X.CFG, "W")["ok"])


# ------------------------------------------------------------------------------------------------ X1: the read
class Reached(Exception):
    """Raised by a stand-in at the first step after the checks under test: the read got that far."""


def reach(*a, **k):
    raise Reached()


class Pins(unittest.TestCase):
    def test_cost_and_extra_code_blobs_are_compared_byte_for_byte(self):
        files = X.cost_files(("XPTUSD",))
        self.assertEqual(files[0], "data/history/costs/ftmo/symbol-map.json")
        r0 = {"meta": {"git_head": "abc123"}}
        calls = []

        def same(*args):
            calls.append(args)
            with open(os.path.join(ROOT, args[1].split(":", 1)[1]), "rb") as fh:
                return 0, fh.read()
        self.assertEqual(X.cost_drift(("XPTUSD",), r0, git=same), [])
        self.assertEqual(calls[0], ("show", f"abc123:{files[0]}"))
        self.assertEqual(X.blob_drift(X.EXTRA_CODE, r0, git=same), [])

        def edited(*args):
            rc, blob = same(*args)
            return rc, blob + b" "
        self.assertEqual(X.cost_drift(("XPTUSD",), r0, git=edited), files)
        self.assertEqual(X.blob_drift(X.EXTRA_CODE, r0, git=edited), list(X.EXTRA_CODE))
        self.assertEqual(X.cost_drift(("XPTUSD",), r0, git=lambda *a: (128, b"")), files)      # git cannot show it
        self.assertEqual(X.blob_drift(X.EXTRA_CODE, {"meta": {}}, git=same), list(X.EXTRA_CODE))  # no R0 commit
        self.assertEqual(X.blob_drift(("docs/absent-file.json",), r0, git=lambda *a: (0, b"{}")),
                         ["docs/absent-file.json"])                                     # deleted since R0's commit

    def test_the_x0_line_pins_the_counts_record_by_content(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(X.x0_line(d))
            p = os.path.join(d, X.X0_OUT)
            os.makedirs(os.path.dirname(p))
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("{}\n")
            line = X.x0_line(d)
        self.assertEqual(X.X0_LINE.findall(line), [(hashlib.sha256(b"{}\n").hexdigest(), X.X0_OUT)])
        self.assertEqual(X.G.manifest(line), {})                     # never read as a code-sha256 manifest line


class ReadHarness:
    """A temporary root holding what the read opens before it computes anything: a minimal R0, the ledger and a synthetic
    X0 (pool = X.POOL on FakeLoader books, its data pin and price pin taken on those books). Stand-ins replace what a
    temporary root cannot hold (the sealed text, a committed tree, the sealed manifest, the R0 code pin, the R0-commit
    blobs: `Pins` tests those), the trace, real_costs' price reference (it reads real history), and `EW.Pricer`, the first
    step of the computation, which raises `Reached`. Each test breaks ONE check and expects its refusal."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.x0_path = os.path.join(self.root, X.X0_OUT)            # taken before any test patches X0_OUT / X1_OUT
        self.out = os.path.join(self.root, X.X1_OUT)
        self.loader = FakeLoader()
        self.man = {p: "0" * 64 for p in X.CODE}
        self.x0 = self.make_x0()
        self.write(X.R0_PATH, {"meta": {"git_head": "r0head", "code_sha256": {}}})
        self.write(X.LEDGER, {X.LEDGER_KEY: {"preregistration": X.PREREG}})
        self.write(X.X0_OUT, self.x0)
        self.git = mock.Mock(return_value=(0, b""))

    def make_x0(self):
        dense = dense_for(*X.POOL)
        syms = {}
        for s in X.POOL:
            S = EW.make_series(s, "15m", self.loader, dense, X.CFG, "ftmo", until=X.WINDOW_END)
            syms[s] = {"data": X.window_digest(S.src)}
        return {"meta": {"script": X.SCRIPT, "kind": "counts", "code_sha256": dict(self.man),
                         "design": json.loads(json.dumps(X.meta("read")["design"], default=str))},
                "probe": {"ok": True, "violations": 0, "checked": 5}, "pool": {"symbols": list(X.POOL)},
                "r0_crosscheck": [], "r0_code_drift": [], "dense": dense, "dense_alt_pool": {}, "symbols": syms,
                "overlap": {"exposed_weeks": []}, "price_ref": {s: fake_price_ref(EW.COST_PROFILE, s) for s in X.POOL}}

    def write(self, rel, obj):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(obj, fh)

    def sealed(self, x0_sha=None):
        sha = x0_sha or X.G.file_sha256(self.x0_path)
        return f"{X.TAG}\nStatus: SEALED\nx0-sha256 {sha} {X.X0_OUT}\n"

    def patches(self, text=None, **over):
        std = dict(require_sealed=mock.patch.object(X.G, "require_sealed", return_value=text or self.sealed()),
                   require_committed=mock.patch.object(X.G, "require_committed", return_value=None),
                   require_fingerprint=mock.patch.object(X.G, "require_fingerprint", return_value=dict(self.man)),
                   r0_drift=mock.patch.object(X, "r0_drift", return_value=[]),
                   cost_drift=mock.patch.object(X, "cost_drift", return_value=[]),
                   blob_drift=mock.patch.object(X, "blob_drift", return_value=[]),
                   trace_start=mock.patch.object(X.G, "trace_start", return_value=None),
                   price_ref_info=mock.patch.object(X.RC, "price_ref_info", fake_price_ref),
                   pricer=mock.patch.object(EW, "Pricer", reach))
        std.update(over)
        return [p for p in std.values() if p is not None]

    def read(self, loader=None, text=None, git=None, **over):
        with contextlib.ExitStack() as st:
            for p in self.patches(text, **over):
                st.enter_context(p)
            X.cmd_read(self.x0_path, self.out, loader=loader or self.loader, root=self.root, git=git or self.git)

    def close(self):
        self.tmp.cleanup()


class ReadGuard(unittest.TestCase):
    def setUp(self):
        self.h = ReadHarness()
        self.addCleanup(self.h.close)

    def refused(self, **kw):
        with self.assertRaises(SystemExit) as cm:
            self.h.read(**kw)
        self.assertFalse(os.path.exists(self.h.out))
        return str(cm.exception)

    def test_the_read_refuses_before_the_seal_and_before_any_data(self):
        # Lifecycle-proof: the rule is checked on a sealed name and an output that do not exist, whatever the repo's state.
        absent, out = "docs/plans/absent-wyckoff-wcx-replication-preregistration.md", "docs/experiments/absent/X1.json"
        loader = mock.Mock(side_effect=boom)
        with mock.patch.object(X, "PREREG", absent), mock.patch.object(X, "X1_OUT", out), \
                self.assertRaises(SystemExit) as cm:
            X.cmd_read(os.path.join(ROOT, X.X0_OUT), os.path.join(ROOT, out), loader=loader)
        self.assertIn("does not exist", str(cm.exception))
        loader.assert_not_called()
        self.assertFalse(os.path.exists(os.path.join(ROOT, out)))

    def test_the_harness_reaches_the_computation_when_every_pin_holds(self):
        with self.assertRaises(Reached):
            self.h.read()
        self.assertGreater(len(self.h.loader.calls), 0)

    def test_every_check_refuses_before_market_data_is_loaded(self):
        loader = mock.Mock(side_effect=boom)

        def status_dirty(*args):
            return (0, b" M scripts/research/other.py\n") if args[0] == "status" else (0, b"")
        cases = [
            ("writes", dict(loader=loader), {"X1_OUT": "docs/elsewhere.json"}),
            ("git history", dict(loader=loader, git=mock.Mock(return_value=(0, b"abc\n"))), {}),
            ("register the study", dict(loader=loader), {"LEDGER_KEY": "another_study"}),
            ("committed and clean", dict(loader=loader, git=status_dirty), {}),
            ("R0-pinned code", dict(loader=loader, r0_drift=mock.patch.object(X, "r0_drift",
                                                                              return_value=["scripts/pit.py"])), {}),
            ("cost tables", dict(loader=loader, cost_drift=mock.patch.object(X, "cost_drift",
                                                                             return_value=["x.json"])), {}),
            ("outside R0's fingerprint", dict(loader=loader, blob_drift=mock.patch.object(
                X, "blob_drift", return_value=list(X.EXTRA_CODE))), {}),
            ("HOUR_FRAME", dict(loader=loader), {"RC.HOUR_FRAME": "utc_legacy"}),
            ("exactly one", dict(loader=loader, text=f"{X.TAG}\nStatus: SEALED\n{X.X0_OUT}\n"), {}),
            ("is not the counts record the sealed text pins", dict(loader=loader, text=self.h.sealed("e" * 64)), {}),
        ]
        for msg, kw, attrs in cases:
            with contextlib.ExitStack() as st:
                for name, val in attrs.items():
                    obj, attr = (X.RC, name[3:]) if name.startswith("RC.") else (X, name)
                    st.enter_context(mock.patch.object(obj, attr, val))
                self.assertIn(msg, self.refused(**kw), msg)
        loader.assert_not_called()

    def test_the_ledger_must_be_valid_and_name_the_sealed_text(self):
        self.h.write(X.LEDGER, {X.LEDGER_KEY: {"preregistration": X.PREREG_DRAFT}})
        self.assertIn("register the study", self.refused(loader=boom))
        with open(os.path.join(self.h.root, X.LEDGER), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        self.assertIn("not valid JSON", self.refused(loader=boom))

    def test_the_data_pin_refuses_a_revised_bar_and_ignores_an_appended_one(self):
        def edited(change):
            ld = FakeLoader()
            ld._c = {s: [dict(c) for c in cs] for s, cs in self.h.loader._c.items()}   # X0's bars, copied
            change(ld._c["UK100"])
            return ld

        def revise(cs):
            cs[700]["close"] += 0.5                                   # a bar inside the window
        msg = self.refused(loader=edited(revise))
        self.assertIn("UK100 15m bars inside the window differ from X0's", msg)

        def append(cs):
            cs.append(dict(cs[-1], time="2026-09-28T00:00:00Z"))      # a later export: after WINDOW_END
        with self.assertRaises(Reached):
            self.h.read(loader=edited(append))
        x0 = json.loads(json.dumps(self.h.x0))
        x0["symbols"]["JP225"]["data"]["sha256"] = "f" * 64            # or a record that names other bars
        self.h.write(X.X0_OUT, x0)
        self.assertIn("JP225 15m bars inside the window differ from X0's", self.refused())

    def test_the_price_pin_refuses_a_revised_recording_window(self):
        def moved(profile, sym):
            return dict(fake_price_ref(profile, sym), closes_sha256="9" * 64) if sym == "JP225" \
                else fake_price_ref(profile, sym)
        msg = self.refused(price_ref_info=mock.patch.object(X.RC, "price_ref_info", moved))
        self.assertIn("JP225 real_costs price reference differs from X0's", msg)

    def test_an_uncommitted_sealed_text_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            p = os.path.join(d, X.PREREG)
            os.makedirs(os.path.dirname(p))
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(f"# {X.TAG}\nStatus: SEALED\n")
            with self.assertRaises(SystemExit) as cm:
                X.cmd_read(os.path.join(d, X.X0_OUT), os.path.join(d, X.X1_OUT), loader=boom, root=d)
            self.assertIn("not tracked", str(cm.exception))

    def test_the_counts_record_checks(self):
        man = {p: "a" * 64 for p in X.CODE}
        design = json.loads(json.dumps(X.meta("read")["design"], default=str))
        good = {"meta": {"script": X.SCRIPT, "kind": "counts", "code_sha256": dict(man), "design": design},
                "probe": {"ok": True, "violations": 0, "checked": 5}, "pool": {"symbols": list(X.POOL)},
                "r0_crosscheck": [], "r0_code_drift": [],
                "price_ref": {s: fake_price_ref(EW.COST_PROFILE, s) for s in X.POOL}}
        sha = "c" * 64
        pinned = f"x0-sha256 {sha} {X.X0_OUT}\n"
        X._require_x0(good, pinned, X.X0_OUT, man, design, sha)
        bad = [("exactly one", lambda r: r, "names " + X.X0_OUT + " by path only\n"),
               ("exactly one", lambda r: r, pinned + pinned),
               ("exactly one", lambda r: r, f"x0-sha256 {sha} docs/experiments/other-X0.json\n"),
               ("is not the counts record", lambda r: r, f"x0-sha256 {'d' * 64} {X.X0_OUT}\n"),
               ("other code", lambda r: r["meta"]["code_sha256"].update({X.SCRIPT: "b" * 64}), pinned),
               ("another registered design", lambda r: r["meta"]["design"].update(alpha=0.2), pinned),
               ("probe", lambda r: r["probe"].update(ok=False), pinned),
               ("pool", lambda r: r["pool"].update(symbols=["XPTUSD"]), pinned),
               ("reproduce R0", lambda r: r.update(r0_crosscheck=["R2 XPTUSD: R0 12 != 11"]), pinned),
               ("reproduce R0", lambda r: r.pop("r0_code_drift"), pinned),
               ("price reference of UK100", lambda r: r["price_ref"].pop("UK100"), pinned),
               ("price reference of XPTUSD, XPDUSD, US2000, UK100, JP225", lambda r: r.pop("price_ref"), pinned)]
        for why, edit, text in bad:
            rec = json.loads(json.dumps(good))
            edit(rec)
            with self.assertRaises(SystemExit) as cm:
                X._require_x0(rec, text, X.X0_OUT, man, design, sha)
            self.assertIn(why, str(cm.exception), why)


class ReadCore(unittest.TestCase):
    def test_every_event_is_scored_with_rt_section_5_and_labelled(self):
        loader = FakeLoader()
        syms = ("XPTUSD", "XPDUSD")
        pricer = EW.Pricer("ftmo", cost_r=fake_cost_r)
        res = X.read_core(syms, loader, dense_for(*syms), pricer, window=(None, "2023-06-30T00:00:00Z"))
        self.assertEqual(res["summary"]["n"], 6)
        r = res["rows"][0]
        for k in ("R", "placebo", "n_placebo", "excess", "net_excess", "cost", "stop_atr", "target_atr", "excess_trend"):
            self.assertIn(k, r)
        self.assertEqual(set(r["cost"]), set(X.LINES))
        self.assertAlmostEqual(r["net_excess"], r["excess"] - 0.03)               # median spread 0.02 + swap 0.01
        self.assertEqual(res["holm"]["m"], 1)
        self.assertIn(res["verdict"]["label"], (X.replicated_label(), "AGAINST THE BOOK", "NOT REPLICATED"))
        self.assertEqual(res["descriptive"]["flatten"]["n"], 6)
        self.assertEqual(res["descriptive"]["ceiling_target"]["n"], 6)
        self.assertEqual(res["descriptive"]["truncated"], 0)
        self.assertEqual(sorted(res["descriptive"]["by_type"]), ["SHAKEOUT", "SPRING"])
        self.assertEqual(res["summary"], EW.summarise(X.with_gross(res["rows"]), X.decision_lines()))
        self.assertEqual(res["lines"], ["gross"] + list(EW.FTMO_LINES))
        mean_excess = sum(r["excess"] for r in res["rows"]) / len(res["rows"])
        self.assertAlmostEqual(res["summary"]["net_excess"], mean_excess)          # the decision line is the gross excess
        self.assertAlmostEqual(res["summary"]["lines"]["median_swap"]["mean"], mean_excess - 0.03)
        self.assertEqual(res["summary"]["lines"]["median_swap"], EW.summarise(res["rows"], EW.FTMO_LINES)["lines"]
                         ["median_swap"])                                            # RT's net line, unchanged

    def test_the_series_is_cut_at_the_window_end(self):
        loader = FakeLoader()
        pricer = EW.Pricer("ftmo", cost_r=fake_cost_r)
        S = EW.make_series("XPTUSD", "15m", loader, dense_for("XPTUSD"), X.CFG)
        k_last = [e["k"] for e in X.detect(S)["W-C"]][-1]
        cut = S.T[k_last]                                                          # the last event's signal bar opens
        res = X.read_core(("XPTUSD",), loader, dense_for("XPTUSD"), pricer, window=(None, cut))
        self.assertEqual(res["summary"]["n"], 2)                                   # its entry bar closes after the cut
        self.assertTrue(all(r["exit_time"] < cut for r in res["rows"]))


class Verdicts(unittest.TestCase):
    def summary(self, mean, p1, lines=None):
        lines = lines or {ln: {"mean": mean} for ln in ("gross",) + X.LINES}
        return {"n": 40, "net_excess": mean, "p_one_sided": p1, "p_two_sided": 2 * min(p1, 1 - p1), "upper_95": mean + 0.4,
                "lines": lines}

    def test_labels(self):
        br_ok, br_no = {"breadth": True}, {"breadth": False}
        for d in ("gross", "net"):
            self.assertEqual(X.verdict(self.summary(0.3, 0.01), br_ok, True, d)["label"], f"REPLICATED ({d}, history)")
            self.assertEqual(X.verdict(self.summary(0.3, 0.01), br_no, True, d)["label"], "NOT REPLICATED")
            self.assertEqual(X.verdict(self.summary(-0.4, 0.99), br_ok, False, d)["label"], "AGAINST THE BOOK")
            self.assertEqual(X.verdict(self.summary(0.1, 0.2), br_ok, False, d)["label"], "NOT REPLICATED")
            self.assertEqual(X.verdict({"n": 0}, br_ok, False, d)["label"], "NOT REPLICATED")
        neg_line = {ln: {"mean": 0.3} for ln in ("gross",) + X.LINES}
        neg_line["p90_swap"] = {"mean": -0.01}                         # a cost line below zero: gates the net design only
        self.assertEqual(X.verdict(self.summary(0.3, 0.01, neg_line), br_ok, True, "net")["label"], "NOT REPLICATED")
        v = X.verdict(self.summary(0.3, 0.01, neg_line), br_ok, True, "gross")
        self.assertEqual((v["label"], v["all_cost_lines_positive"], v["cost_lines_gate"]),
                         ("REPLICATED (gross, history)", False, False))

    def test_holm(self):
        self.assertEqual(X.holm([0.04], 0.05), {0})
        self.assertEqual(X.holm([0.06], 0.05), set())
        self.assertEqual(X.holm([0.01, 0.04], 0.05), {0, 1})
        self.assertEqual(X.holm([0.03, 0.04], 0.05), set())
        self.assertEqual(X.holm([0.04, 0.001], 0.05), {0, 1})
        self.assertEqual(X.holm([0.10], 0.10), {0})                  # Holm's "p <= alpha", as EC `bh` (WY-X1 §6)

    def test_the_breadth_gate_is_rt_gate_3_metals_and_indices(self):
        def rows(sym, n, net):
            return [{"symbol": sym, "week": f"2021-W{i % 50 + 1:02d}", "excess": net + 0.03, "R": net, "placebo": 0.0,
                     "cost": {ln: 0.03 for ln in X.LINES}} for i in range(n)]
        ok = rows("XPTUSD", 12, 0.2) + rows("XPDUSD", 8, 0.1) + rows("UK100", 10, 0.3) + rows("JP225", 10, -0.1)
        b = X.breadth_groups(ok)
        self.assertEqual((b["meetable"], b["breadth"]), (True, True))
        self.assertEqual((b["groups"]["metals"]["n"], b["groups"]["indices"]["n"]), (20, 20))
        neg = ok[:20] + rows("UK100", 10, -0.3) + rows("JP225", 10, -0.1)
        self.assertEqual(X.breadth_groups(neg)["breadth"], False)
        few = ok[:20] + rows("UK100", 19, 0.3)
        self.assertEqual((X.breadth_groups(few)["meetable"], X.breadth_groups(few)["breadth"]), (False, False))
        dear = rows("XPTUSD", 20, 0.2) + rows("UK100", 20, 0.2)                 # gross > 0, net < 0 on metals:
        for r in dear[:20]:                                                      # breadth on the decision line only
            r["cost"] = {ln: 0.9 for ln in X.LINES}
        self.assertFalse(X.breadth_groups(dear)["breadth"])                     # RT's net line
        self.assertTrue(X.breadth_groups(X.with_gross(dear), lines=X.decision_lines("gross"))["breadth"])
        self.assertEqual(X.GROUP_OF["US2000"], "indices")
        self.assertEqual({s for s, g in X.GROUP_OF.items() if g == "metals"}, {"XPTUSD", "XPDUSD"})

    def test_breadth_is_rt_r2_pass_on_rt_clusters(self):
        rnd = random.Random(7)
        rt = {s: c for c, syms in EW.REPLICATION.items() for s in syms}
        for trial in range(25):
            rows = []
            for i in range(rnd.randint(20, 90)):
                s = rnd.choice(sorted(rt))
                net = rnd.gauss(0.1 * (trial % 3 - 1), 1.0)
                rows.append({"symbol": s, "week": f"2020-W{i % 50 + 1:02d}", "excess": net + 0.03, "R": net,
                             "placebo": 0.0, "cost": {ln: 0.03 for ln in X.LINES}})
            mine, theirs = X.breadth(rows, rt), EW.r2_pass(rows)
            self.assertEqual((sorted(mine["evaluable"]), sorted(mine["agree"])),
                             (sorted(theirs["evaluable"]), sorted(theirs["agree"])))
            self.assertEqual(mine["breadth"], len(theirs["evaluable"]) >= EW.R2_EVALUABLE_MIN
                             and len(theirs["agree"]) >= min(EW.R2_AGREE, len(theirs["evaluable"])))


# ------------------------------------------------------------------------------------------------ power (no outcome)
class Power(unittest.TestCase):
    def test_it_reproduces_wy_f1_section_9(self):
        rows = {(11, 1.4): (0.95, 0.23, 0.43), (11, 2.2): (1.49, 0.17, 0.28), (100, 1.4): (0.30, 0.69, 0.99),
                (50, 2.2): (0.67, 0.31, 0.62)}
        for (n, sd), (mde, p25, p50) in rows.items():
            self.assertAlmostEqual(X.mde_t(n, sd, 0.10), mde, delta=0.011)
            self.assertAlmostEqual(X.power_t(n, sd, 0.25, 0.10), p25, delta=0.011)
            self.assertAlmostEqual(X.power_t(n, sd, 0.50, 0.10), p50, delta=0.011)

    def test_obf_spending_and_two_looks(self):
        self.assertAlmostEqual(X.obf_spend(1.0, 0.10), 0.10, places=9)
        self.assertAlmostEqual(X.obf_spend(1 / 3, 0.10), 0.00439, places=4)
        c1, c2, a1 = X.two_look(1 / 3, 0.10)
        self.assertAlmostEqual(1 - X.bvn_cdf(c1, c2, math.sqrt(1 / 3)), 0.10, places=4)
        self.assertGreater(c2, X._phi_inv(0.90))
        self.assertLess(c2, 1.32)
        self.assertAlmostEqual(X.two_look_power(11, 33, 1.4, 0.0, c1, c2), 0.10, places=4)

    def test_bvn_cdf(self):
        self.assertAlmostEqual(X.bvn_cdf(0.3, -0.5, 0.0), X._phi(0.3) * X._phi(-0.5), places=6)
        self.assertAlmostEqual(X.bvn_cdf(0.0, 0.0, 0.5), 0.25 + math.asin(0.5) / (2 * math.pi), places=6)

    def test_pass_power(self):
        null = X.pass_power(30, 28, 2.0, 0.0, 0.10)
        self.assertAlmostEqual(null["significant"], 0.10, delta=0.01)
        self.assertLess(null["replicated"], null["significant"])
        big = X.pass_power(30, 28, 1.4, 1.5, 0.10)
        self.assertGreater(big["replicated"], 0.99)
        self.assertEqual(X.pass_power(40, 10, 1.4, 1.5, 0.10)["replicated"], 0.0)   # indices < 20: breadth unmeetable
        self.assertEqual(X.pass_power(30, 28, 2.2, 0.25, 0.10), X.pass_power(30, 28, 2.2, 0.25, 0.10))  # fixed seed
        drag = X.pass_power(30, 28, 1.4, 0.35 - 0.93, 0.10, effect_indices=0.35 - 0.15)   # PGM-sized cost on metals
        self.assertLess(drag["replicated"], 0.05)

    def test_design_effect_bound(self):
        f = [{"week": "W1"}, {"week": "W1"}, {"week": "W2"}]
        self.assertAlmostEqual(X.design_effect(f)["n_eff_week_bound"], 9 / 5)


if __name__ == "__main__":
    unittest.main()
