"""scripts/research/wyckoff_forward.py (WY-F1) on SYNTHETIC and HAND-BUILT bars only: no real bar after any seal, no
outcome on market data. The one real input is real_costs' recorded spread table and price_ref (cost model inputs), as in
test_edge_wyckoff's Costs tests. Pre-registration: docs/plans/2026-10-04-wyckoff-forward-wc15-preregistration-DRAFT.md.

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_wyckoff_forward
"""
import contextlib
import datetime
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
_spec = importlib.util.spec_from_file_location("wyckoff_forward", os.path.join(ROOT, "scripts", "research",
                                                                               "wyckoff_forward.py"))
WF = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(WF)
E = WF.ew()
BT = E.engine()
import broker_symbols as BS  # noqa: E402
import test_edge_wyckoff as TEW  # noqa: E402 -- its synthetic Wyckoff shapes only (a module: its TestCases do not run here)

UTC = datetime.timezone.utc
START = "2026-06-01T00:00:00Z"


def fake_cost_r(entry, stop, t_in, t_out, sym, side, profile, stat="median"):
    """A deterministic cost_r stand-in (test_edge_wyckoff's): spread 0.02R (0.03R at p90) plus swap 0.01R."""
    s = 0.02 if stat == "median" else 0.03
    return {"total_R": s + 0.01, "swap_R": 0.01, "spread_R": s, "commission_R": 0.0}


def t_at(j, start=START, jitter=0):
    return WF._iso(WF._utc(start) + datetime.timedelta(minutes=15 * j, seconds=jitter))


def mk_bars(tuples, start=START, src="history"):
    return [{"t": t_at(j, start), "o": o, "h": h, "l": lo, "c": c, "v": v, "src": src, "at": "2026-01-01T00:00:00Z"}
            for j, (o, h, lo, c, v) in enumerate(tuples)]


def candles(bars, jitter=False):
    return [{"time": WF._iso(WF._utc(b["t"]) + datetime.timedelta(seconds=(j % 2 if jitter else 0))),
             "open": b["o"], "high": b["h"], "low": b["l"], "close": b["c"], "volume": b["v"]}
            for j, b in enumerate(bars)]


def spring_tuples(pre=400, post=200):
    """A rising prefix, test_edge_wyckoff's Spring accumulation (signal at pre + 92), a rising tail."""
    return TEW.rising(pre) + TEW.scenario("spring") + TEW.rising(post, 118, 120)


def write_history(root, sym, bars):
    WF._write_json(os.path.join(root, WF.HIST_DIR, f"ohlcv.{sym}.15m.json"),
                   {"symbol": sym, "timeframe": "15m", "candles": candles(bars)})


def write_live(root, sym, bars, jitter=True):
    WF._write_json(os.path.join(root, WF.LIVE_DIR, f"ohlcv.{BS.to_broker(sym)}.15m.json"),
                   {"symbol": BS.to_broker(sym), "timeframe": "15m", "candles": candles(bars, jitter)})


def scan_all(S, bars, seal, cache=None, logged=None):
    return WF.scan_symbol(S, bars, WF.link_all(WF.GENESIS, bars), cache, seal, WF.det_ctx(),
                          set() if logged is None else logged)


@contextlib.contextmanager
def quiet():
    with contextlib.redirect_stdout(io.StringIO()):
        yield


_CANARY = {}


def canary_root():
    """A copy of one canary data root after one full cycle (built once per module run)."""
    if "dir" not in _CANARY:
        d = tempfile.mkdtemp(prefix="wyf1-canary-")
        seal = WF.canary_data(d)
        res = WF.cycle_core(d, seal, "fp", "2026-07-01T00:00:00Z", init_root=d)
        WF.commit(res["writes"])
        _CANARY.update(dir=d, seal=seal)
    d = tempfile.mkdtemp(prefix="wyf1-case-")
    shutil.copytree(_CANARY["dir"], d, dirs_exist_ok=True)
    return d, dict(_CANARY["seal"])


def tearDownModule():
    if "dir" in _CANARY:
        shutil.rmtree(_CANARY["dir"], ignore_errors=True)


_FP = {}


def working_fingerprint():
    """The fingerprint of the working tree (cmd_fingerprint, require_clean off), built once per module run in a FRESH
    process, as a real one is: this process loaded edge_wyckoff at import, so a trace here would miss its import chain
    (the `load` set)."""
    if "fp" not in _FP:
        out = os.path.join(tempfile.mkdtemp(prefix="wyf1-fp-"), "fp.json")
        code = ("import importlib.util\n"
                f"spec = importlib.util.spec_from_file_location('wyckoff_forward', {os.path.join(ROOT, WF.SCRIPT)!r})\n"
                "m = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(m)\n"
                f"m.cmd_fingerprint({out!r}, require_clean=False)\n")
        p = subprocess.run([sys.executable, "-B", "-W", "ignore", "-c", code], capture_output=True, text=True)
        if p.returncode != 0:
            raise AssertionError("cmd_fingerprint failed: " + (p.stderr or p.stdout)[-2000:])
        with open(out) as fh:
            _FP["fp"] = json.load(fh)
    return _FP["fp"]


def sealed_here():
    """True once the repository holds the WY-F1 seal: from then on the forward path runs the sealed extract and the
    working tree may change, so the working-tree pins below no longer apply."""
    return WF.seal_info(ROOT) is not None


def rewrite_chain(path, recs):
    """Replace a chain file with `recs`, re-chained from GENESIS (a test building a store or log variant)."""
    if os.path.exists(path):
        os.remove(path)
    if recs:
        WF.append_chain(path, recs, WF.GENESIS)


# ------------------------------------------------------------------------------------------------ registration
class Registration(unittest.TestCase):
    def test_symbols_are_the_retest_tradeable_ones_with_a_15m_dense_start(self):
        dense = WF.r0_dense()
        self.assertEqual(WF.SYMBOLS, tuple(s for s in E.TRADEABLE if (dense.get(f"{s}|15m") or {}).get("start")))
        self.assertNotIn("FRA40", WF.SYMBOLS)

    def test_detection_and_horizon_are_the_sealed_retests_own(self):
        cfg, P, sob = WF.det_ctx()
        self.assertEqual(cfg, E.BASE_CFG)
        self.assertEqual(P, E.det_params(E.BASE_CFG))
        self.assertEqual((sob, WF.horizon()), (BT.P["15m"]["sob"], BT.P["15m"]["H"]))
        self.assertEqual(WF.horizon(), 96)

    def test_the_read_rule_is_the_fixed_one(self):
        self.assertEqual((WF.N_EVENTS, WF.MONTHS, WF.P_PASS), (100, 12, 0.10))
        self.assertEqual((WF.N_EVENTS, WF.MONTHS, WF.P_PASS), (E.FORWARD_EVENTS, E.FORWARD_MONTHS, E.FORWARD_P))

    def test_every_fingerprinted_input_is_what_the_sealed_retest_ran(self):
        if sealed_here():
            self.skipTest("WY-F1 is sealed: the forward path runs the sealed extract; the working tree may change")
        code = json.load(open(os.path.join(ROOT, WF.R0)))["meta"]["code_sha256"]
        for p in (WF.EW_PATH, "scripts/wyckoff_rules.py", "scripts/backtest-methods.py", "scripts/real_costs.py"):
            self.assertEqual(WF._sha256(os.path.join(ROOT, p)), code[p], p)
        fp = working_fingerprint()                      # cmd_fingerprint itself refuses on any drift (r0_drift)
        pinned = set(fp["r0_pinned"])
        self.assertTrue({"scripts/real_costs.py", "docs/architecture/instruments.json",
                         "data/history/costs/ftmo/symbolspec.XAUUSD.json", "scripts/broker_symbols.py"} <= pinned)
        self.assertEqual(WF.r0_drift(ROOT, pinned), [])

    def test_a_fingerprinted_input_that_drifted_from_r0_refuses_the_fingerprint(self):
        code, head = WF.r0_code()
        bad = dict(code, **{"scripts/real_costs.py": "0" * 64})
        out = os.path.join(tempfile.mkdtemp(), "fp.json")
        with mock.patch.object(WF, "r0_code", lambda root=None: (bad, head)), quiet(), \
                self.assertRaises(SystemExit) as cm:
            WF.cmd_fingerprint(out, require_clean=False)
        self.assertIn("scripts/real_costs.py: differs from R0", str(cm.exception))
        self.assertFalse(os.path.exists(out))
        root = tempfile.mkdtemp()                       # a path R0 does not name must be R0's git_head blob
        with mock.patch.object(WF, "r0_code", lambda r=None: ({}, head)):
            self.assertIn("not in R0's git_head", WF.r0_drift(root, ["scripts/x.py"])[0])

    def test_the_extract_holds_every_adapter_the_provider_registry_checks_for(self):
        doc = json.load(open(os.path.join(ROOT, "docs", "architecture", "providers.json")))
        named = [p[k] for p in doc["providers"].values() for k in ("adapter", "market_data_adapter") if p.get(k)]
        self.assertTrue(named)
        self.assertEqual([p for p in named if not WF._wanted(p)], [])          # providers._validate stat()s them

    def test_decision_keys_are_what_decision_builds(self):
        S = WF.series_of("XAUUSD", mk_bars(spring_tuples()))
        bars = mk_bars(spring_tuples())
        (ev,) = WF.fire(S, 0, len(S), 0, WF.det_ctx(), None)
        self.assertEqual(tuple(WF.decision(S, ev, bars, WF.link_all(WF.GENESIS, bars), 300)), WF.DECISION_KEYS)


# ------------------------------------------------------------------------------------------------ bars (WY-F1 §4)
class Bars(unittest.TestCase):
    def test_snap_takes_the_bridge_second_and_refuses_minutes(self):
        self.assertEqual(WF.snap("2026-09-29T15:00:01Z"), "2026-09-29T15:00:00Z")
        self.assertEqual(WF.snap("2026-09-29T14:59:59Z"), "2026-09-29T15:00:00Z")
        self.assertIsNone(WF.snap("2026-09-29T15:02:00Z"))

    def test_one_bad_bar_or_a_duplicate_label_makes_a_source_unusable(self):
        good = candles(mk_bars(TEW.rising(5)))
        self.assertEqual(len(WF.clean(good, "x")[0]), 5)
        bars, note = WF.clean(good + [dict(good[-1], time="2026-06-01T02:07:00Z")], "x")
        self.assertEqual(bars, [])
        self.assertIn("off the 15-minute grid", note)
        bars, note = WF.clean(good + [dict(good[0], time="2026-06-01T00:00:01Z")], "x")
        self.assertEqual((bars, "1 duplicate" in note), ([], True))

    def test_the_live_file_drops_its_forming_bar_and_is_read_in_the_brokers_spelling(self):
        d = tempfile.mkdtemp()
        bars = mk_bars(TEW.rising(10))
        write_live(d, "DE40", bars)
        self.assertTrue(os.path.exists(os.path.join(d, WF.LIVE_DIR, "ohlcv.GER40.cash.15m.json")))
        got, note = WF.live_source(d, "DE40")
        self.assertIsNone(note)
        self.assertEqual([b["t"] for b in got], [b["t"] for b in bars[:-1]])
        self.assertTrue(all(b["t"].endswith(":00Z") for b in got))
        self.assertIn("no live 15m file", WF.live_source(d, "AUS200")[1])

    def test_init_takes_the_sealed_history_from_ninety_days_before_the_seal(self):
        bars = mk_bars(TEW.rising(96 * 100))
        seal = t_at(96 * 95)
        got = WF.plan_init(bars, seal, "now")
        self.assertEqual(got[0]["t"], t_at(96 * 5))
        self.assertTrue(all(b["src"] == "history" for b in got))

    def test_a_source_appends_only_on_the_stores_last_bars_at_the_same_prices(self):
        bars = mk_bars(TEW.rising(40))
        store, src = bars[:30], [dict(b, src="live") for b in bars[20:]]
        new, why = WF.plan_append(store, src, "live", "now")
        self.assertIsNone(why)
        self.assertEqual([b["t"] for b in new], [b["t"] for b in bars[30:]])
        revised = [dict(b, c=b["c"] + 0.5) if b["t"] == store[-2]["t"] else b for b in src]
        self.assertEqual(WF.plan_append(store, revised, "live", "now")[0], [])
        self.assertIn("disagrees", WF.plan_append(store, revised, "live", "now")[1])
        shifted = [dict(b, t=WF._iso(WF._utc(b["t"]) + datetime.timedelta(hours=1))) for b in src]   # v1.02 after DST
        self.assertEqual(WF.plan_append(store, shifted, "live", "now")[0], [])
        hole = [b for b in src if b["t"] > bars[33]["t"]]
        new, why = WF.plan_append(store, hole, "live", "now")
        self.assertEqual(new, [])
        self.assertIn("hole", why)
        self.assertEqual(WF.plan_append(store, src[:5], "live", "now"), ([], None))           # behind: silent

    def test_after_downtime_the_history_export_bridges_the_hole_then_the_live_file_continues(self):
        d = tempfile.mkdtemp()
        bars = mk_bars(TEW.rising(400))
        store = bars[:100]
        write_history(d, "XAUUSD", bars[:300])                   # a re-export: its final bar 299 is dropped
        write_live(d, "XAUUSD", bars[250:])                      # the live file starts after the store's end
        add, notes = WF.accumulate_symbol("XAUUSD", store, d, d, {"instant": t_at(50)}, "now")
        self.assertEqual(notes, [])
        self.assertEqual([b["t"] for b in add], [b["t"] for b in bars[100:399]])
        self.assertEqual({b["src"] for b in add[:199]}, {"history"})
        self.assertEqual({b["src"] for b in add[199:]}, {"live"})

    def test_a_shifted_live_clock_appends_nothing_and_says_why(self):
        d = tempfile.mkdtemp()
        bars = mk_bars(TEW.rising(200))
        shifted = [dict(b, t=WF._iso(WF._utc(b["t"]) + datetime.timedelta(hours=1))) for b in bars[90:]]
        write_live(d, "XAUUSD", shifted, jitter=False)
        add, notes = WF.accumulate_symbol("XAUUSD", bars[:100], d, d, {"instant": t_at(50)}, "now")
        self.assertEqual(add, [])
        self.assertTrue(any("disagrees" in n for n in notes))

    def test_the_chain_refuses_an_edit_a_removal_and_a_concurrent_writer(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "x.jsonl")
        bars = mk_bars(TEW.rising(5))
        head = WF.append_chain(p, bars[:3], WF.GENESIS)
        WF.append_chain(p, bars[3:], head)
        recs, heads = WF.read_chain(p)
        self.assertEqual((len(recs), heads[-1]), (5, WF.link_all(WF.GENESIS, bars)[-1]))
        with self.assertRaises(SystemExit):
            WF.append_chain(p, bars[:1], head)                    # someone appended since `head` was read
        lines = open(p).read().splitlines()
        for bad in (lines[:1] + [lines[1].replace(str(bars[1]["c"]), str(bars[1]["c"] + 1))] + lines[2:],
                    lines[:2] + lines[3:]):
            with open(p, "w") as fh:
                fh.write("\n".join(bad) + "\n")
            with self.assertRaises(SystemExit):
                WF.read_chain(p)


# ------------------------------------------------------------------------------------------------ events (WY-F1 §2-§4)
class Detection(unittest.TestCase):
    def test_fire_is_detect_series_on_the_wc_leg(self):
        tuples = (TEW.rising(300) + TEW.scenario("shakeout") + TEW.leg(118, 101, 6) + TEW.rising(30, 100.5, 104.0)
                  + TEW.scenario("spring") + TEW.rising(200, 118, 120))
        S = WF.series_of("XAUUSD", mk_bars(tuples))
        cfg, P, sob = WF.det_ctx()
        ref = E.detect_series(S, cfg, P, sob, None)["W-C"]
        got = WF.fire(S, 0, len(S), 0, WF.det_ctx(), E.W.pivot_index(S.H, S.L, P["pivot"]))
        self.assertEqual(len(ref), 2)
        self.assertEqual([(e["k"], e["key"], e["type"]) for e in got], [(e["k"], e["key"], e["type"]) for e in ref])

    def test_an_event_is_logged_once_with_its_decision_inputs(self):
        bars = mk_bars(spring_tuples())
        S = WF.series_of("XAUUSD", bars)
        seal = {"sha": "s", "instant": t_at(450)}
        decs, through = scan_all(S, bars, seal)
        (d,) = decs
        self.assertEqual((d["store_index"], d["type"], d["signal_time"], through), (492, "SPRING", t_at(492), t_at(len(bars) - 1)))
        self.assertEqual(d["window_first"], t_at(492 - 299))
        self.assertEqual(d["window_sha256"], WF.window_sha256(bars, 193, 492))
        self.assertEqual(d["chain_at_signal"], WF.link_all(WF.GENESIS, bars)[492])
        self.assertEqual(d["target"], d["tr_hi"])
        self.assertAlmostEqual(d["stop"], d["spring_low"] * (1 - BT.STOP_BUFFER_PCT))
        self.assertEqual(scan_all(S, bars, seal, cache=through)[0], [])                 # nothing new after the cache
        self.assertEqual(scan_all(S, bars, seal, logged={d["id"]})[0], [])              # a lost cache re-scans, no dup

    def test_only_a_signal_bar_closing_at_or_after_the_seal_is_forward(self):
        bars = mk_bars(spring_tuples())
        S = WF.series_of("XAUUSD", bars)
        close = t_at(493)                                                                # bar 492 closes here
        self.assertEqual(len(scan_all(S, bars, {"sha": "s", "instant": close})[0]), 1)
        later = WF._iso(WF._utc(close) + datetime.timedelta(seconds=1))
        self.assertEqual(scan_all(S, bars, {"sha": "s", "instant": later})[0], [])      # decided before the seal

    def test_bar_by_bar_scans_equal_one_full_replay(self):
        bars = mk_bars(TEW.rising(300) + TEW.scenario("shakeout") + TEW.leg(118, 101, 6) + TEW.rising(30, 100.5, 104.0)
                       + TEW.scenario("spring") + TEW.rising(150, 118, 120))
        seal = {"sha": "s", "instant": t_at(310)}
        heads = WF.link_all(WF.GENESIS, bars)
        inc, cache, logged = [], None, set()
        for n in list(range(320, len(bars), 37)) + [len(bars)]:
            S = WF.series_of("XAUUSD", bars[:n])
            decs, cache = WF.scan_symbol(S, bars[:n], heads[:n], cache, seal, WF.det_ctx(), logged)
            inc += decs
        S = WF.series_of("XAUUSD", bars)
        full = [WF.decision(S, ev, bars, heads, 300) for ev in WF.fire(S, 0, len(S), 0, WF.det_ctx(), None)
                if S.avail[ev["k"]] >= WF._utc(seal["instant"])]
        self.assertEqual(len(full), 2)
        self.assertEqual([WF._canon(d) for d in inc], [WF._canon(d) for d in full])

    def test_a_store_starting_ninety_days_before_the_seal_decides_as_the_full_history(self):
        tuples = TEW.rising(96 * 120) + TEW.scenario("spring") + TEW.rising(150, 118, 120)
        bars = mk_bars(tuples, start="2026-02-01T00:00:00Z")
        k_ev = 96 * 120 + 92
        seal = {"sha": "s", "instant": bars[k_ev - 50]["t"]}
        tail = WF.plan_init(bars, seal["instant"], "x")
        self.assertGreater(len(bars) - len(tail), 96 * 25)
        off = len(bars) - len(tail)
        Sf, St = WF.series_of("XAUUSD", bars), WF.series_of("XAUUSD", tail)
        for k in range(k_ev - 60, len(bars)):
            self.assertEqual((Sf.prev_dense[k], Sf.atr[k]), (St.prev_dense[k - off], St.atr[k - off]))
        (df,), _ = scan_all(Sf, bars, seal)
        (dt,), _ = scan_all(St, tail, seal)
        skip = ("store_index", "chain_at_signal")
        self.assertEqual({k: v for k, v in df.items() if k not in skip}, {k: v for k, v in dt.items() if k not in skip})


# ------------------------------------------------------------------------------------------------ probe (WY-F1 §8)
class TruncationProbe(unittest.TestCase):
    def setUp(self):
        self.bars = mk_bars(spring_tuples())
        self.heads = WF.link_all(WF.GENESIS, self.bars)
        self.S = WF.series_of("XAUUSD", self.bars)
        self.seal = {"sha": "s", "instant": t_at(450)}

    def test_every_event_re_detects_identically_on_the_store_cut_at_its_signal_bar(self):
        decs, _ = scan_all(self.S, self.bars, self.seal)
        pr = WF.probe("XAUUSD", self.bars, self.heads, decs, WF.det_ctx())
        self.assertEqual((pr["checked"], pr["violations"], pr["ok"]), (1, 0, True))

    def test_a_detector_that_reads_the_next_bar_is_caught(self):
        real = E.window_fire

        def leaky(S, k, cfg, P, sob, pidx=None):
            evs, logs = real(S, k, cfg, P, sob, pidx)
            nxt = S.C[k + 1] if k + 1 < len(S) else 0.0                     # look-ahead: the bar after the signal
            return [dict(e, stop=e["stop"] + 1e-9 * nxt) for e in evs], logs
        with mock.patch.object(E, "window_fire", leaky):
            decs, _ = scan_all(self.S, self.bars, self.seal)
        pr = WF.probe("XAUUSD", self.bars, self.heads, decs, WF.det_ctx(), fire_fn=leaky)
        self.assertEqual((pr["violations"], pr["ok"]), (1, False))

    def test_an_empty_probe_is_not_a_pass(self):
        self.assertFalse(WF.probe("XAUUSD", self.bars, self.heads, [], WF.det_ctx())["ok"])


# ------------------------------------------------------------------------------------------------ resolve (WY-F1 §6)
class Resolve(unittest.TestCase):
    def setUp(self):
        self.bars = mk_bars(spring_tuples())
        self.seal = {"sha": "s", "instant": t_at(450)}
        S = WF.series_of("XAUUSD", self.bars)
        (self.d,), _ = scan_all(S, self.bars, self.seal)
        self.rec = WF.stamp(self.d, self.seal, "fp", "now")

    def resolve(self, n, rec=None):
        return WF.resolve_record(WF.series_of("XAUUSD", self.bars[:n]), rec or self.rec, self.seal, "fp", "now")

    def test_nothing_before_the_entry_bar_or_the_exit_then_the_engine_walk(self):
        k = self.d["store_index"]
        self.assertIsNone(self.resolve(k + 1))                       # the entry bar is not stored yet
        self.assertIsNone(self.resolve(k + 3))                       # entered, neither stop nor target yet, < H bars
        r = self.resolve(len(self.bars))
        S = WF.series_of("XAUUSD", self.bars)
        with E.walk_opts(BT):
            w = E.walk_from(BT, "long", S.O[k + 1], self.d["stop"], self.d["target"], S, k + 1, 96)
        self.assertEqual((r["outcome"], r["R"], r["exit_time"], r["entry_time"]), (w["outcome"], w["R"],
                                                                                  S.T[w["exit"]], S.T[k + 1]))
        self.assertEqual((r["placeable"], r["skip"]), (True, None))

    def test_an_entry_open_beyond_the_stop_is_a_recorded_skip(self):
        k = self.d["store_index"]
        rec = dict(self.rec, stop=self.bars[k + 1]["o"] + 1.0)
        r = self.resolve(k + 2, rec)
        self.assertEqual((r["placeable"], r["skip"]), (False, "entry_beyond_stop_or_target"))
        self.assertNotIn("R", r)

    def test_status_never_prints_an_outcome(self):
        d, _seal = canary_root()
        log, heads = WF.read_chain(WF._rt(d, "log.jsonl"))
        rec = next(r for r in log if r["kind"] == "event")
        WF.append_chain(WF._rt(d, "log.jsonl"), [{"kind": "resolve", "id": rec["id"] + "x", "R": 123.456789,
                                                  "outcome": "win", "entry_time": START, "placeable": True,
                                                  "skip": None}], heads[-1])
        st = WF.status(d)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            WF._print_status(st)
        for text in (json.dumps(st), buf.getvalue()):
            self.assertNotIn("123.456789", text)
            self.assertNotIn("outcome", text)
            self.assertNotIn('"R"', text)
        x = st["symbols"]["XAUUSD"]
        self.assertEqual((x["events"], x["entered"], x["past_walk"], x["unresolved_past_walk"]), (1, 1, 1, 0))
        self.assertNotIn("resolved", x)                              # a resolve count times each exit (§6)
        self.assertNotIn("records", st["log"])                       # records - events = resolves
        self.assertFalse(st["rule"]["read_due"])                     # no seal in a plain directory

    def test_status_counts_the_rule_from_the_entry_open_as_the_read_does(self):
        d, seal = canary_root()
        with mock.patch.object(WF, "seal_info", lambda root=None: dict(seal, date="x")), \
                mock.patch.object(WF, "committed_anchors", lambda root: []):
            st = WF.status(d)
        log, heads = WF.read_chain(WF._rt(d, "log.jsonl"))
        rewrite_chain(WF._rt(d, "log.jsonl"), [{k: v for k, v in r.items()} for r in log if r["kind"] == "event"])
        with mock.patch.object(WF, "seal_info", lambda root=None: dict(seal, date="x")), \
                mock.patch.object(WF, "committed_anchors", lambda root: []):
            st2 = WF.status(d)                                       # the same with every resolve record gone
        self.assertEqual(st["rule"]["counted_events"], 7)
        self.assertEqual(st2["rule"]["counted_events"], 7)
        self.assertEqual(st2["symbols"]["XAUUSD"]["unresolved_past_walk"], 1)


# ------------------------------------------------------------------------------------------------ the read rule (§7)
class FakeS:
    """Only what `due` reads: len and avail (bar closes)."""

    def __init__(self, n, start="2026-10-05T00:00:00Z"):
        self.avail = [WF._utc(start) + datetime.timedelta(minutes=15 * (j + 1)) for j in range(n)]

    def __len__(self):
        return len(self.avail)


class ReadRule(unittest.TestCase):
    SEAL = "2026-10-05T00:00:00Z"

    def test_months(self):
        d = WF._utc("2026-10-05T10:23:11Z")
        self.assertEqual(WF._iso(WF.add_months(d, 12)), "2027-10-05T10:23:11Z")
        self.assertEqual(WF.add_months(WF._utc("2028-02-29T00:00:00Z"), 12).day, 28)

    def test_the_n_rule_cuts_at_the_nth_counted_entry_inside_the_common_complete_span(self):
        a, b = FakeS(5000), FakeS(5000)
        closes = [a.avail[10 * j] for j in range(1, 121)]
        r = WF.due({"A": a, "B": b}, closes, self.SEAL, 96, n_events=100)
        self.assertEqual((r["cutoff"], r["rule"][:2]), (WF._iso(closes[99]), "N:"))
        lag = FakeS(900)                                              # complete through bar 803 only
        r = WF.due({"A": a, "B": lag}, closes, self.SEAL, 96, n_events=100)
        self.assertIsNone(r["cutoff"])
        self.assertEqual(r["counted_events"], 80)

    def test_the_t_rule_cuts_at_twelve_months_and_the_earlier_rule_wins(self):
        year = 96 * 366 + 200
        a = FakeS(year)
        r = WF.due({"A": a}, [a.avail[100]] * 3, self.SEAL, 96, n_events=100)
        self.assertEqual((r["cutoff"], r["rule"][:2]), ("2027-10-05T00:00:00Z", "T:"))
        late = [a.avail[96 * 366 + 50]] * 100                         # the 100th event comes after the 12 months
        self.assertEqual(WF.due({"A": a}, late, self.SEAL, 96)["rule"][:2], "T:")
        self.assertIsNone(WF.due({"A": FakeS(96 * 300)}, [], self.SEAL, 96)["cutoff"])

    def test_a_symbol_still_stalled_three_months_after_the_t_cutoff_is_dropped_whole(self):
        year = 96 * 366 + 200
        full, stalled = FakeS(96 * (366 + 92) + 200), FakeS(96 * 200)       # 15 months + / stalled after ~6 months
        r = WF.due({"A": full, "B": stalled}, [], self.SEAL, 96, n_events=100)
        self.assertEqual((r["cutoff"], r["dropped"], r["rule"][:7]), ("2027-10-05T00:00:00Z", ["B"], "T-drop:"))
        self.assertEqual(r["grace_cutoff"], "2028-01-05T00:00:00Z")
        early = FakeS(year)                                                  # 12 months done, the grace not over
        r = WF.due({"A": early, "B": stalled}, [], self.SEAL, 96, n_events=100)
        self.assertEqual((r["cutoff"], r["dropped"]), (None, []))
        r = WF.due({"A": full, "B": None}, [], self.SEAL, 96, n_events=100)  # B never had a store
        self.assertEqual(r["dropped"], ["B"])
        r = WF.due({"A": full, "B": stalled}, [], self.SEAL, 96, n_events=100, grace_months=None)
        self.assertIsNone(r["cutoff"])                                       # option B: no fallback
        r = WF.due({"A": full, "B": full}, [], self.SEAL, 96, n_events=100)
        self.assertEqual((r["rule"][:2], r["dropped"]), ("T:", []))         # nothing stalled: the plain T rule

    def test_an_early_read_refuses_before_any_walk_or_cost_is_computed(self):
        # The canary root's log already holds resolve records (gross R): what this proves is that the read computes
        # no walk, no placebo and no cost before its rule is met -- not that no outcome exists anywhere (WY-F1 §6).
        d, seal = canary_root()

        def boom(*a, **k):
            raise AssertionError("an outcome was computed before the read rule was met")
        with mock.patch.object(E, "walk_from", boom), mock.patch.object(E, "score", boom), \
                mock.patch.object(E, "Pricer", boom):
            with self.assertRaises(SystemExit) as cm:
                WF.read_core(d, seal, "fp", cost_r=fake_cost_r)                # the registered 100 / 12 months
        self.assertIn("not due", str(cm.exception))


# ------------------------------------------------------------------------------------------------ the read (§7-§8)
class Read(unittest.TestCase):
    def test_the_read_measures_with_the_sealed_section_5(self):
        d, seal = canary_root()
        out = WF.read_core(d, seal, "fp", cost_r=fake_cost_r, n_events=1)
        self.assertEqual((out["sample"], out["summary"]["n"], out["probe"]["violations"]), (7, 7, 0))
        self.assertTrue(out["cutoff"]["rule"].startswith("N:"))
        for r in out["rows"]:
            self.assertAlmostEqual(r["net_excess"], r["excess"] - r["cost"]["median_swap"])
            self.assertEqual(r["tf"], "15m")
        v = out["verdict"]
        self.assertEqual(v["pass"], bool(out["summary"]["n"]) and v["net_excess"] > 0 and v["p_one_sided"] < 0.10)
        self.assertEqual(set(out["history_check"]), set(WF.SYMBOLS))
        for h in out["history_check"].values():
            self.assertEqual((h["coverage"], h["agreement"], h["missing"], h["spans_end"], h["spans_checked"],
                              h["span_mismatches"]), (1.0, 1.0, 0, True, 1, 0))
            self.assertEqual(len(h["export"]["files"]), 1)                    # the export's files, hashed
        self.assertEqual((out["symbols_read"], out["symbols_dropped"]), (list(WF.SYMBOLS), []))
        self.assertIsNotNone(out["anchors"]["note"])                          # no committed anchor: disclosed

    def test_the_replay_must_match_the_log(self):
        d, seal = canary_root()
        log, heads = WF.read_chain(WF._rt(d, "log.jsonl"))
        ghost = dict(next(r for r in log if r["kind"] == "event"), id="XAUUSD|15m|ghost")
        WF.append_chain(WF._rt(d, "log.jsonl"), [ghost], heads[-1])
        with self.assertRaises(SystemExit) as cm:
            WF.read_core(d, seal, "fp", cost_r=fake_cost_r, n_events=1)
        self.assertIn("replay does not match", str(cm.exception))

    def test_a_record_under_another_fingerprint_or_seal_refuses(self):
        d, seal = canary_root()
        with self.assertRaises(SystemExit) as cm:
            WF.read_core(d, seal, "another-fp", cost_r=fake_cost_r, n_events=1)
        self.assertIn("another seal or code fingerprint", str(cm.exception))

    def test_bars_the_history_export_does_not_confirm_refuse(self):
        d, seal = canary_root()
        p = os.path.join(d, WF.HIST_DIR, "ohlcv.XAGUSD.15m.json")
        doc = json.load(open(p))
        for c in doc["candles"][WF.CANARY_SEAL_BAR:WF.CANARY_SEAL_BAR + 20]:
            c["close"] += 0.01
        WF._write_json(p, doc)
        with self.assertRaises(SystemExit) as cm:
            WF.read_core(d, seal, "fp", cost_r=fake_cost_r, n_events=1)
        self.assertIn("cannot be verified", str(cm.exception))
        self.assertIn("XAGUSD", str(cm.exception))

    def test_a_scored_trade_must_equal_its_logged_resolve(self):
        d, seal = canary_root()
        real = E.score

        def drift(*a, **k):
            r, why = real(*a, **k)
            return (dict(r, R=r["R"] + 1e-6), why) if r else (r, why)
        with self.assertRaises(SystemExit) as cm:
            WF.read_core(d, seal, "fp", cost_r=fake_cost_r, n_events=1, score_fn=drift)
        self.assertIn("disagree with their logged resolve", str(cm.exception))

    def test_an_export_taken_too_early_refuses_even_when_its_coverage_passes(self):
        d, seal = canary_root()
        wl = WF.read_core(d, seal, "fp", cost_r=fake_cost_r, n_events=1)["history_check"]["XAGUSD"]["window_last"]
        p = os.path.join(d, WF.HIST_DIR, "ohlcv.XAGUSD.15m.json")
        doc = json.load(open(p))
        doc["candles"] = [c for c in doc["candles"] if c["time"] < wl]           # ends 2 bars before the window's end
        WF._write_json(p, doc)
        with self.assertRaises(SystemExit) as cm:
            WF.read_core(d, seal, "fp", cost_r=fake_cost_r, n_events=1)
        self.assertIn("XAGUSD", str(cm.exception))
        self.assertIn("taken too early", str(cm.exception))                       # coverage alone is 0.986 here

    def test_one_changed_bar_inside_an_events_span_refuses_though_agreement_passes(self):
        d, seal = canary_root()
        log, _ = WF.read_chain(WF._rt(d, "log.jsonl"))
        sig = next(r["signal_time"] for r in log if r["kind"] == "event" and r["symbol"] == "XAGUSD")
        p = os.path.join(d, WF.HIST_DIR, "ohlcv.XAGUSD.15m.json")
        doc = json.load(open(p))
        for c in doc["candles"]:
            if c["time"] == sig:
                c["close"] += 0.01
        WF._write_json(p, doc)
        with self.assertRaises(SystemExit) as cm:
            WF.read_core(d, seal, "fp", cost_r=fake_cost_r, n_events=1)
        self.assertIn("1 sampled event span(s) differ from the export, first XAGUSD", str(cm.exception))

    def test_bars_the_store_lacks_are_missing_not_empty(self):
        root = tempfile.mkdtemp()
        bars = mk_bars(TEW.rising(700))
        store = bars[:300] + bars[303:]                                             # a hole the live file skipped
        WF._write_json(os.path.join(root, WF.HIST_DIR, "ohlcv.XAUUSD.15m.json"),
                       {"symbol": "XAUUSD", "timeframe": "15m", "_exported_at_utc": "2026-07-01T00:00:00Z",
                        "candles": candles(bars)})
        S = WF.series_of("XAUUSD", store)
        h = WF.history_check("XAUUSD", store, S, WF._utc(store[250]["t"]), S.avail[400], 96, root)
        self.assertEqual((h["coverage"], h["agreement"], h["missing"], h["first_missing"]),
                         (1.0, 1.0, 3, bars[300]["t"]))                            # the old check passed this
        self.assertIn("the store lacks 3 of the export's", WF.history_problem(h))
        self.assertEqual(h["export"]["exported_at_utc"], "2026-07-01T00:00:00Z")
        self.assertEqual(list(h["export"]["files"]), [f"{WF.HIST_DIR}/ohlcv.XAUUSD.15m.json"])
        h = WF.history_check("XAUUSD", bars[:-1], WF.series_of("XAUUSD", bars[:-1]), WF._utc(bars[250]["t"]),
                             WF.series_of("XAUUSD", bars[:-1]).avail[400], 96, root, spans=[("e", 200, 520)])
        self.assertIsNone(WF.history_problem(h))
        self.assertEqual((h["spans_checked"], h["span_mismatches"]), (1, 0))

    def test_a_dropped_symbol_leaves_the_sample_whole(self):
        d, seal = canary_root()
        real = WF.due

        def drop(*a, **k):
            return dict(real(*a, **k), dropped=["XAGUSD"], rule="T-drop: test")
        with mock.patch.object(WF, "due", drop):
            out = WF.read_core(d, seal, "fp", cost_r=fake_cost_r, n_events=1)
        self.assertEqual((out["sample"], out["symbols_dropped"]), (6, ["XAGUSD"]))
        self.assertNotIn("XAGUSD", out["history_check"])
        self.assertNotIn("XAGUSD", out["probe"]["per_symbol"])
        self.assertFalse(any(r["symbol"] == "XAGUSD" for r in out["rows"]))

    def test_anchors_come_from_git_history_and_must_sit_on_the_chains(self):
        d, seal = canary_root()
        git(d, "init", "-q")
        WF.cmd_anchor(d)
        git(d, "add", WF.ANCHORS)
        git(d, "commit", "-q", "-m", "anchor")
        anchors = WF.committed_anchors(d)
        out = WF.read_core(d, seal, "fp", cost_r=fake_cost_r, n_events=1, anchors=anchors)
        self.assertEqual((out["anchors"]["verified"], out["anchors"]["note"]), (1, None))
        p = os.path.join(d, WF.ANCHORS)
        with open(p, "a") as fh:
            fh.write("\n")
        with self.assertRaises(SystemExit) as cm:                                  # the working file is not HEAD's
            WF.committed_anchors(d)
        self.assertIn("differs from its committed version", str(cm.exception))
        git(d, "rm", "-q", "-f", WF.ANCHORS)
        git(d, "commit", "-q", "-m", "drop the anchors")
        self.assertEqual(len(WF.committed_anchors(d)), 1)                          # a deletion does not drop a pin
        a = dict(anchors[0])
        a["bars"] = dict(a["bars"], XAUUSD=dict(a["bars"]["XAUUSD"], head="0" * 64))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as fh:
            fh.write(json.dumps({k: v for k, v in a.items() if k not in ("commit", "committed")}) + "\n")
        git(d, "add", WF.ANCHORS)
        git(d, "commit", "-q", "-m", "a rewritten anchor")
        with self.assertRaises(SystemExit) as cm:
            WF.read_core(d, seal, "fp", cost_r=fake_cost_r, n_events=1, anchors=WF.committed_anchors(d))
        self.assertIn("does not sit on the XAUUSD chain", str(cm.exception))


# ------------------------------------------------------------------------------------------------ cycle (§4, §6)
class Cycle(unittest.TestCase):
    def test_one_cycle_logs_each_event_and_its_resolve_and_a_second_adds_nothing(self):
        d, seal = canary_root()
        log, _ = WF.read_chain(WF._rt(d, "log.jsonl"))
        self.assertEqual(sorted(r["kind"] for r in log), ["event"] * 7 + ["resolve"] * 7)
        self.assertTrue(all(r["fingerprint"] == "fp" and r["seal"] == seal["sha"] for r in log))
        res = WF.cycle_core(d, seal, "fp", "2026-07-02T00:00:00Z", init_root=d)
        self.assertEqual([w[0] for w in res["writes"]], ["json"])            # only the scan cache
        self.assertEqual(res["summary"]["new_events"], 0)
        self.assertNotIn("new_resolves", res["summary"])                     # it would time each exit (§6)

    def test_the_store_holds_closed_bars_from_history_then_live(self):
        d, _seal = canary_root()
        bars, _ = WF.read_chain(WF._rt(d, "bars", "XAUUSD.15m.jsonl"))
        n = len(WF.canary_bars(0))
        self.assertEqual(len(bars), n - 1)                                   # the live file's forming bar is not in
        self.assertEqual(bars[WF.CANARY_HIST_END - 2]["src"], "history")
        self.assertEqual(bars[WF.CANARY_HIST_END - 1]["src"], "live")
        self.assertTrue(all(b["t"].endswith(":00Z") for b in bars))

    def test_the_worker_refuses_without_the_sealed_fingerprint(self):
        with self.assertRaises(SystemExit) as cm:
            WF.verify_fingerprint(tempfile.mkdtemp())
        self.assertIn("no sealed code fingerprint", str(cm.exception))


# ------------------------------------------------------------------------------------------------ fingerprint (§5)
class Fingerprint(unittest.TestCase):
    def test_the_tracer_splits_import_and_run_and_records_opened_files(self):
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, "scripts"))
        with open(os.path.join(root, "data.json"), "w") as fh:
            fh.write("{}")
        src = ("import json, os\nROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\n"
               "def g():\n    return 1\nX = g()\nclass K:\n    pass\n"
               "def f():\n    return json.load(open(os.path.join(ROOT, 'data.json')))\n")
        with open(os.path.join(root, "scripts", "m.py"), "w") as fh:
            fh.write(src)
        tr = WF.Tracer(root).start()
        spec = importlib.util.spec_from_file_location("wyf1_m", os.path.join(root, "scripts", "m.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        tr.run_phase()
        m.f()
        WF._audit("open", ("data.json", None, 0))                 # a dir_fd-relative name (shutil.rmtree): ignored
        tr.stop()
        run, code, data = tr.touched()
        self.assertEqual((run, tr.exec["import"], tr.modules), ({"scripts/m.py"}, {"scripts/m.py"}, {"scripts/m.py"}))
        self.assertEqual(code, set())
        self.assertEqual(data, {"data.json"})

    def test_verify_refuses_a_changed_file_and_check_refuses_an_unnamed_one(self):
        root = tempfile.mkdtemp()
        f = os.path.join(root, "scripts", "a.py")
        os.makedirs(os.path.dirname(f))
        with open(f, "w") as fh:
            fh.write("x = 1\n")
        fp = {"exec": {"scripts/a.py": WF._sha256(f)}, "load": {}, "data": {}, "canary_sha256": "c"}
        WF._write_json(os.path.join(root, WF.FINGERPRINT), fp)
        got, digest = WF.verify_fingerprint(root)
        self.assertEqual(digest, WF.fp_digest(fp))
        with open(f, "a") as fh:
            fh.write("y = 2\n")
        with self.assertRaises(SystemExit):
            WF.verify_fingerprint(root)
        tr = WF.Tracer(root)
        tr.exec["run"] = {"scripts/a.py", "scripts/b.py"}
        with self.assertRaises(SystemExit) as cm:
            WF.check_touched(tr, fp)
        self.assertIn("scripts/b.py", str(cm.exception))
        tr.exec["run"] = {"scripts/a.py"}
        self.assertEqual(WF.check_touched(tr, fp), [])

    def test_the_fingerprint_is_the_narrow_executed_set_and_inside_the_extract(self):
        if sealed_here():
            self.skipTest("WY-F1 is sealed: its fingerprint is the committed one")
        fp = working_fingerprint()
        self.assertEqual(fp["interpreter"]["command"], sys.executable)
        self.assertEqual(fp["interpreter"]["minor"], "%d.%d" % sys.version_info[:2])
        need = {WF.SCRIPT, WF.EW_PATH, "scripts/wyckoff_rules.py", "scripts/backtest-methods.py", "scripts/real_costs.py"}
        self.assertTrue(need <= set(fp["exec"]), set(fp["exec"]))
        self.assertLess(len(fp["exec"]), len(E.CODE) // 3)                 # vs the sealed re-test's 52 files
        self.assertNotIn("docs/architecture/instruments.json", fp["exec"])
        self.assertIn(WF.R0, fp["data"])
        self.assertTrue(all(WF._wanted(p) for s in ("exec", "load", "data") for p in fp[s]))
        self.assertEqual(set(fp["price_ref"]), set(WF.SYMBOLS))
        self.assertEqual(fp["canary"]["events"], len(WF.SYMBOLS))
        self.assertEqual(fp["digest"], WF.fp_digest(fp))
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(WF.canary(tmp)[0], fp["canary_sha256"])          # deterministic
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(WF.platform, "python_version",
                                                                    lambda: "3.99.99"):
            self.assertEqual(WF.canary(tmp)[0], fp["canary_sha256"])          # a Python patch upgrade: same digest

    def test_a_run_that_touches_the_live_tree_outside_its_extract_is_refused(self):
        data = tempfile.mkdtemp()
        code = os.path.join(data, WF.RUNTIME, "code", "abc")
        tr = WF.Tracer(code)
        tr.opened = {os.path.join(data, WF.LIVE_DIR, "ohlcv.XAUUSD.15m.json"),
                     os.path.join(data, WF.HIST_DIR, "ohlcv.XAUUSD.15m", "2027.json.gz"),
                     os.path.join(data, WF.RUNTIME, "log.jsonl"), os.path.join(data, WF.ANCHORS),
                     os.path.join(data, WF.PREREG), os.path.join(code, "scripts", "real_costs.py"),
                     "/somewhere/else/site-packages/x.py"}
        WF.check_outside(tr, data)                                            # inputs, outputs, own extract: fine
        for bad in (os.path.join(data, "docs", "architecture", "instruments.json"),       # live config, unsealed
                    os.path.join(data, WF.RUNTIME, "code", "other", "scripts", "real_costs.py")):
            tr.opened.add(bad)
            with self.assertRaises(SystemExit) as cm:
                WF.check_outside(tr, data)
            self.assertIn("outside the sealed extract", str(cm.exception))
            tr.opened.discard(bad)
        mod = type(sys)("wyf1_stray")
        mod.__file__ = os.path.join(data, "scripts", "real_costs.py")         # imported from the live tree
        with mock.patch.dict(sys.modules, {"wyf1_stray": mod}), self.assertRaises(SystemExit) as cm:
            WF.check_outside(tr, data)
        self.assertIn("imported scripts/real_costs.py", str(cm.exception))

    def test_a_worker_runs_only_the_pinned_interpreter(self):
        code = tempfile.mkdtemp()
        here = {"command": sys.executable, "version": "x", "minor": "%d.%d" % sys.version_info[:2]}
        WF._write_json(os.path.join(code, WF.FINGERPRINT), {"interpreter": here})
        self.assertEqual(WF._interpreter(code), sys.executable)
        self.assertEqual(WF._worker_cmd(code, "cycle", code, {"sha": "s", "instant": "i"})[0], sys.executable)
        WF._write_json(os.path.join(code, WF.FINGERPRINT), {"interpreter": dict(here, command="/nonexistent/python3.14")})
        with self.assertRaises(SystemExit) as cm:
            WF._interpreter(code)
        self.assertIn("is missing", str(cm.exception))                       # never falls back to another Python
        WF._write_json(os.path.join(code, WF.FINGERPRINT), {})
        with self.assertRaises(SystemExit):
            WF._interpreter(code)
        WF.require_interpreter({"interpreter": here})
        with self.assertRaises(SystemExit) as cm:
            WF.require_interpreter({"interpreter": dict(here, minor="3.0")})
        self.assertIn("pins 3.0", str(cm.exception))

    def test_the_fingerprint_needs_the_committed_bytes_on_disk(self):
        root = tempfile.mkdtemp()
        git(root, "init", "-q")
        os.makedirs(os.path.join(root, "scripts"))
        f = os.path.join(root, "scripts", "a.py")
        with open(f, "wb") as fh:
            fh.write(b"x = 1\ny = 2\n")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "a")
        WF._require_clean(root, ["scripts/a.py"])
        with open(f, "wb") as fh:
            fh.write(b"x = 1\r\ny = 2\r\n")                                   # what core.autocrlf=true checks out
        with self.assertRaises(SystemExit) as cm:
            WF._require_clean(root, ["scripts/a.py"])
        self.assertIn("bytes differ", str(cm.exception))
        with self.assertRaises(SystemExit) as cm:
            WF._require_clean(root, ["scripts/untracked.py"])
        self.assertIn("not committed", str(cm.exception))


# ------------------------------------------------------------------------------------------------ seal and extract (§5)
def git(root, *args, date=None, inp=None):
    """Runs git in `root` (a test repository) and returns its stdout."""
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@t")
    if date:
        env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    return subprocess.run(["git", "-c", "core.excludesFile=/dev/null", "-C", root, *args], check=True,
                          capture_output=True, env=env, input=inp,
                          text=True).stdout.strip()             # a user's global excludes must not drop docs/ here


class ExtractCheck(unittest.TestCase):
    """`extract_check` (WY-F1 §5), the check that found the missing .mq5 adapters, on a throwaway `--shared` clone of
    this repository (no checkout; the real repository is only read) with one synthetic commit holding the working
    tree's fingerprinted files."""

    @classmethod
    def setUpClass(cls):
        if sealed_here():
            raise unittest.SkipTest("WY-F1 is sealed: extract_check ran at sealing (fingerprint.json extract_check)")
        cls.fp = working_fingerprint()
        cls.tmp = tempfile.mkdtemp(prefix="wyf1-clone-")
        cls.clone = os.path.join(cls.tmp, "repo")
        subprocess.run(["git", "clone", "-q", "--shared", "--no-checkout", ROOT, cls.clone], check=True,
                       capture_output=True)
        git(cls.clone, "read-tree", "HEAD")
        files = sorted(set(cls.fp["exec"]) | set(cls.fp["load"]) | set(cls.fp["data"]))
        blobs = git(cls.clone, "hash-object", "-w", "--no-filters", "--stdin-paths",
                    inp="\n".join(os.path.join(ROOT, p) for p in files) + "\n").split()
        git(cls.clone, "update-index", "--add", "--index-info",
            inp="".join(f"100644 {b}\t{p}\n" for b, p in zip(blobs, files)))
        cls.rev = git(cls.clone, "commit-tree", git(cls.clone, "write-tree"), "-p", "HEAD", "-m", "wyf1 test")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_the_extract_of_a_commit_runs_the_forward_path_by_itself(self):
        self.assertGreater(WF.extract_check(self.fp, self.clone, self.rev), 400)

    def test_an_extract_without_the_adapter_files_cannot_run(self):
        roots = tuple(r for r in WF.SNAPSHOT_ROOTS if not r.startswith("integrations/"))
        with mock.patch.object(WF, "SNAPSHOT_ROOTS", roots), self.assertRaises(SystemExit) as cm:
            WF.extract_check(self.fp, self.clone, self.rev)
        self.assertIn(".mq5", str(cm.exception))                         # providers._validate (scripts/providers.py:63)


class Launcher(unittest.TestCase):
    def repo(self):
        root = tempfile.mkdtemp()
        git(root, "init", "-q")
        files = ["scripts/research/x.py", "scripts/tests/t.py", "docs/architecture/a.json", "data/history/costs/c.json",
                 "data/history/ftmo/ohlcv.XAUUSD.15m/2026.json.gz", "data/history/ftmo/ohlcv.XAUUSD.15m/index.json",
                 "data/history/ftmo/ohlcv.XAUUSD.1H.json", "data/history/ftmo/ohlcv.FRA40.15m.json", WF.R0,
                 WF.FINGERPRINT, "other/z.txt", "integrations/mt5/ExportOHLCV.mq5", "integrations/mt5/OrderBridge.mq5"]
        for f in files:
            os.makedirs(os.path.dirname(os.path.join(root, f)), exist_ok=True)
            with open(os.path.join(root, f), "w") as fh:
                fh.write(f)
        WF._write_json(os.path.join(root, WF.FINGERPRINT),
                       {"interpreter": {"command": sys.executable, "minor": "%d.%d" % sys.version_info[:2]}})
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "code", date="2026-10-05T08:00:00+07:00")
        return root

    def seal(self, root, extra=(), date="2026-10-05T09:30:00+07:00"):
        """The seal commit: the sealed file (+ `extra` paths)."""
        os.makedirs(os.path.join(root, os.path.dirname(WF.PREREG)), exist_ok=True)
        with open(os.path.join(root, WF.PREREG), "w") as fh:
            fh.write("sealed")
        for p in extra:
            os.makedirs(os.path.dirname(os.path.join(root, p)), exist_ok=True)
            with open(os.path.join(root, p), "w") as fh:
                fh.write(p)
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "seal", date=date)
        return WF.seal_info(root)

    def test_the_seal_commit_is_one_commit_adding_exactly_the_sealed_file_and_the_fingerprint(self):
        def base():
            root = tempfile.mkdtemp()
            git(root, "init", "-q")
            os.makedirs(os.path.join(root, "scripts"))
            with open(os.path.join(root, "scripts", "a.py"), "w") as fh:
                fh.write("x = 1\n")
            git(root, "add", "-A")
            git(root, "commit", "-q", "-m", "code")
            head = git(root, "rev-parse", "HEAD")
            fp = {"git_head": head}
            WF._write_json(os.path.join(root, WF.FINGERPRINT), fp)
            return root, fp
        root, fp = base()
        s = self.seal(root)
        WF._require_seal(root, s, fp)
        root, fp = base()
        s = self.seal(root, extra=["scripts/b.py"])                     # something rode in with the seal
        with self.assertRaises(SystemExit) as cm:
            WF._require_seal(root, s, fp)
        self.assertIn("must add exactly", str(cm.exception))
        root, fp = base()
        s = self.seal(root)
        with self.assertRaises(SystemExit) as cm:
            WF._require_seal(root, s, dict(fp, git_head="0" * 40))       # not on the fingerprinted commit
        self.assertIn("are not the fingerprinted commit", str(cm.exception))

    def test_the_read_cites_the_sealed_text_and_discloses_later_changes(self):
        root = self.repo()
        s = self.seal(root)
        with open(os.path.join(root, WF.PREREG), "a") as fh:
            fh.write(" erratum")
        git(root, "commit", "-qam", "erratum", date="2026-10-09T09:30:00+07:00")
        rec = WF.prereg_record(root, s)
        self.assertEqual(rec["sealed_sha256"], hashlib.sha256(b"sealed").hexdigest())
        self.assertEqual(rec["head_sha256"], hashlib.sha256(b"sealed erratum").hexdigest())
        self.assertEqual(rec["changed_after_seal"], [git(root, "rev-parse", "HEAD")])

    def test_the_extracts_fingerprint_must_be_the_seal_commits(self):
        root = self.repo()
        s = self.seal(root)
        code = WF.materialize(root, s["sha"])
        WF.require_committed_fingerprint(root, s, code)
        with open(os.path.join(code, WF.FINGERPRINT), "a") as fh:
            fh.write(" ")
        with self.assertRaises(SystemExit) as cm:
            WF.require_committed_fingerprint(root, s, code)
        self.assertIn("is not the seal commit's", str(cm.exception))
        fresh = WF.materialize(root, s["sha"], fresh=True)                # the read rebuilds from git
        self.assertNotEqual(fresh, code)
        WF.require_committed_fingerprint(root, s, fresh)

    def test_a_checkout_without_the_seal_while_stores_exist_is_a_recorded_failure(self):
        root = self.repo()
        os.makedirs(WF._rt(root, "bars"))
        with self.assertRaises(SystemExit) as cm:
            WF.cmd_cycle(data_root=root)
        self.assertIn("collection is PAUSED", str(cm.exception))
        self.assertFalse(json.load(open(WF._rt(root, "last_cycle.json")))["ok"])

    def test_a_cycle_still_running_is_a_skip_not_a_failure(self):
        root = self.repo()
        self.seal(root)
        os.makedirs(WF._rt(root))
        with open(WF._rt(root, "launcher.lock"), "w") as fh:
            fh.write("1")
        self.assertIn("skipped", WF.cmd_cycle(data_root=root))
        self.assertFalse(os.path.exists(WF._rt(root, "last_cycle.json")))

    def test_spawn_detaches_returns_at_once_and_reports_the_previous_failure(self):
        root = tempfile.mkdtemp()
        calls = []

        class P:
            pid = 4242

        def popen(cmd, **kw):
            calls.append((cmd, kw))
            return P()
        self.assertIn("spawned pid 4242", WF.cmd_spawn(root, popen=popen))
        cmd, kw = calls[0]
        self.assertEqual(cmd[2:5], [os.path.join(WF.CODE_ROOT, WF.SCRIPT), "cycle", "--background"])
        self.assertEqual(cmd[-1], os.path.abspath(root))
        if os.name != "nt":
            self.assertTrue(kw["start_new_session"])                     # out of launchd's process group
        WF._write_json(WF._rt(root, "last_cycle.json"), {"at": "t", "ok": False, "error": "boom"})
        with self.assertRaises(SystemExit) as cm:                         # spawned anyway, then the cycle log says EXIT
            WF.cmd_spawn(root, popen=popen)
        self.assertIn("previous cycle FAILED at t: boom", str(cm.exception))
        self.assertEqual(len(calls), 2)

    def test_a_real_spawn_runs_the_cycle_in_the_background(self):
        root = tempfile.mkdtemp()                                         # not a repository: "not sealed"
        WF.cmd_spawn(root)
        log = WF._rt(root, "spawn.log")
        for _ in range(600):
            if os.path.exists(log) and "not sealed" in open(log).read():
                break
            time.sleep(0.1)
        self.assertIn("not sealed", open(log).read())

    def test_before_the_seal_a_cycle_collects_nothing(self):
        root = self.repo()
        self.assertIsNone(WF.seal_info(root))
        self.assertIn("not sealed", WF.cmd_cycle(data_root=root))
        with self.assertRaises(SystemExit):
            WF.cmd_read(os.path.join(root, WF.READ_OUT), data_root=root)

    def test_the_seal_is_the_adding_commits_committer_date_and_the_extract_holds_the_snapshot_roots_only(self):
        root = self.repo()
        os.makedirs(os.path.join(root, os.path.dirname(WF.PREREG)), exist_ok=True)
        with open(os.path.join(root, WF.PREREG), "w") as fh:
            fh.write("sealed")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "seal", date="2026-10-05T09:30:00+07:00")
        with open(os.path.join(root, WF.PREREG), "a") as fh:
            fh.write(" erratum")
        git(root, "commit", "-qam", "erratum", date="2026-10-09T09:30:00+07:00")
        s = WF.seal_info(root)
        sha = subprocess.run(["git", "-C", root, "rev-parse", "HEAD~1"], capture_output=True, text=True).stdout.strip()
        self.assertEqual((s["sha"], s["instant"]), (sha, "2026-10-05T02:30:00Z"))
        code = WF.materialize(root, s["sha"])
        got = sorted(os.path.relpath(os.path.join(dp, f), code) for dp, _dn, fs in os.walk(code) for f in fs)
        self.assertIn(WF.PREREG, got)
        self.assertIn("scripts/research/x.py", got)
        self.assertIn("data/history/ftmo/ohlcv.XAUUSD.15m/2026.json.gz", got)
        self.assertIn("integrations/mt5/ExportOHLCV.mq5", got)                    # stat()ed by providers._validate
        for absent in ("data/history/ftmo/ohlcv.XAUUSD.1H.json", "data/history/ftmo/ohlcv.FRA40.15m.json",
                       "other/z.txt", "integrations/mt5/OrderBridge.mq5"):
            self.assertNotIn(absent, got)
        self.assertEqual(open(os.path.join(code, WF.PREREG)).read(), "sealed")      # the seal's text, not the erratum
        mark = os.path.getmtime(os.path.join(code, ".complete"))
        self.assertEqual(WF.materialize(root, s["sha"]), code)
        self.assertEqual(os.path.getmtime(os.path.join(code, ".complete")), mark)

    def test_a_failing_worker_is_recorded_for_status_and_writes_nothing(self):
        root = self.repo()                                       # its extract has no wyckoff_forward.py to run
        os.makedirs(os.path.join(root, os.path.dirname(WF.PREREG)), exist_ok=True)
        with open(os.path.join(root, WF.PREREG), "w") as fh:
            fh.write("sealed")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "seal")
        with self.assertRaises(SystemExit) as cm:
            WF.cmd_cycle(data_root=root)
        self.assertIn("worker failed", str(cm.exception))
        last = json.load(open(WF._rt(root, "last_cycle.json")))
        self.assertFalse(last["ok"])
        self.assertFalse(os.path.exists(WF._rt(root, "log.jsonl")))

    def test_a_seal_without_a_fingerprint_is_refused(self):
        root = self.repo()
        git(root, "rm", "-q", WF.FINGERPRINT)
        os.makedirs(os.path.join(root, os.path.dirname(WF.PREREG)), exist_ok=True)
        with open(os.path.join(root, WF.PREREG), "w") as fh:
            fh.write("sealed")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "seal")
        with self.assertRaises(SystemExit) as cm:
            WF.materialize(root, WF.seal_info(root)["sha"])
        self.assertIn("has no", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
