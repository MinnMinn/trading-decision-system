"""scripts/research/wyckoff_forward.py (WY-F1) on SYNTHETIC and HAND-BUILT bars only: no real bar after any seal, no
outcome on market data. The one real input is real_costs' recorded spread table and price_ref (cost model inputs), as in
test_edge_wyckoff's Costs tests. Pre-registration: docs/plans/2026-10-04-wyckoff-forward-wc15-preregistration-DRAFT.md.

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_wyckoff_forward
"""
import base64
import contextlib
import datetime
import hashlib
import importlib.util
import io
import json
import math
import os
import random
import shlex
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


def read(d, seal, look=1, prior=None, **kw):
    """read_core at one look of the canary's synthetic plan (WF.canary_plan), with the stand-in cost."""
    kw.setdefault("cost_r", fake_cost_r)
    return WF.read_core(d, seal, "fp", look=look, plan=WF.canary_plan(seal), prior=prior, **kw)


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


def shim_python(where, version):
    """A test interpreter at `where`/python<major>.<minor>: THIS Python, presenting itself as `version` (sys.version_info
    and sys.version) to what it runs -- a script with its arguments, or `-c` code. It lets the pin's patch / minor rule
    run end to end without installing another Python (WY-F1 §5)."""
    major, minor, micro = (int(x) for x in version.split("."))
    os.makedirs(where, exist_ok=True)
    boot = os.path.join(where, "boot.py")
    with open(boot, "w") as fh:
        fh.write("import collections, runpy, sys\n"
                 "V = collections.namedtuple('version_info', 'major minor micro releaselevel serial')\n"
                 f"sys.version_info = V({major}, {minor}, {micro}, 'final', 0)\n"
                 f"sys.version = {version!r} + sys.version[sys.version.index(' '):]\n"
                 "args = sys.argv[1:]\n"
                 "if args[:1] == ['-c']:\n"
                 "    sys.argv = ['-c'] + args[2:]\n"
                 "    exec(compile(args[1], '<string>', 'exec'), {'__name__': '__main__'})\n"
                 "else:\n"
                 "    sys.argv = args\n"
                 "    runpy.run_path(args[0], run_name='__main__')\n")
    exe = os.path.join(where, f"python{major}.{minor}")
    with open(exe, "w") as fh:
        fh.write("#!/bin/sh\n"
                 'while [ "$1" = "-B" ] || [ "$1" = "-E" ] || [ "$1" = "-s" ]; do shift; done\n'
                 f'exec {shlex.quote(sys.executable)} -B -E -s {shlex.quote(boot)} "$@"\n')
    os.chmod(exe, 0o755)
    return exe


# ------------------------------------------------------------------------------------------------ registration
class Registration(unittest.TestCase):
    def test_symbols_are_the_retests_seven_and_the_three_cheap_replication_indices(self):
        dense = WF.r0_dense()
        self.assertEqual(WF.RT_SYMBOLS, tuple(s for s in E.TRADEABLE if (dense.get(f"{s}|15m") or {}).get("start")))
        self.assertNotIn("FRA40", WF.SYMBOLS)                                # no R0 15m dense start (§14)
        replication = [s for g in E.REPLICATION.values() for s in g]
        self.assertEqual(WF.ADDED_SYMBOLS, ("US2000", "UK100", "JP225"))     # lead decision 2026-10-04 (WY-X1 §12.2 a)
        self.assertTrue(set(WF.ADDED_SYMBOLS) <= set(replication))
        self.assertTrue(all((dense.get(f"{s}|15m") or {}).get("start") for s in WF.ADDED_SYMBOLS))
        for metal in ("XPTUSD", "XPDUSD"):                                    # spread about 0.9R: out
            self.assertNotIn(metal, WF.SYMBOLS)
        self.assertEqual(WF.SYMBOLS, WF.RT_SYMBOLS + WF.ADDED_SYMBOLS)

    def test_the_added_symbols_dense_starts_are_the_retests_rule_outcome_blind(self):
        """US2000, UK100, JP225 start at R0's 15m dense start, which RT §4's rule (edge_wyckoff.dense_table /
        dense_start, unmodified) gives again on the committed history: bar counts per server day only, no price.
        R0 is fingerprinted, so its starts are pinned by its sha256 at the seal."""
        pinned = {"US2000": "2018-01-01", "UK100": "2021-09-01", "JP225": "2021-09-01"}
        dense = WF.r0_dense()
        self.assertEqual({s: dense[f"{s}|15m"]["start"] for s in WF.ADDED_SYMBOLS}, pinned)
        if sealed_here():
            self.skipTest("WY-F1 is sealed: the extract's R0 is the pin; the working tree's history may be re-exported")

        def counts_only(sym, tf):                                           # the loader, with every price removed
            candles, prov = E.load_ftmo(sym, tf)
            return [{"time": c["time"]} for c in candles], prov
        got = E.dense_table([(s, "15m") for s in WF.ADDED_SYMBOLS], counts_only, "ftmo")
        for s in WF.ADDED_SYMBOLS:
            r0 = dense[f"{s}|15m"]
            self.assertEqual({k: got[f"{s}|15m"][k] for k in ("start", "ref_median", "holes")},
                             {k: r0[k] for k in ("start", "ref_median", "holes")}, s)

    def test_detection_and_horizon_are_the_sealed_retests_own(self):
        cfg, P, sob = WF.det_ctx()
        self.assertEqual(cfg, E.BASE_CFG)
        self.assertEqual(P, E.det_params(E.BASE_CFG))
        self.assertEqual((sob, WF.horizon()), (BT.P["15m"]["sob"], BT.P["15m"]["H"]))
        self.assertEqual(WF.horizon(), 96)

    def test_the_read_rule_is_the_fixed_one(self):
        self.assertEqual((WF.LOOK_MONTHS, WF.ALPHA, WF.PLAN_RATE, WF.N_REST_PLAN), ((12, 36), 0.10, 14, 28))
        self.assertEqual((WF.GRACE_MONTHS, WF.NEVER_DUE_MONTHS), (3, 48))
        self.assertEqual((WF.ALPHA, WF.LOOK_MONTHS[0]), (E.FORWARD_P, E.FORWARD_MONTHS))  # RT R4's alpha, in total
        self.assertEqual(WF.LOOK_OUT, {1: WF.REC_DIR + "/wyckoff-forward-look1.json",
                                       2: WF.REC_DIR + "/wyckoff-forward-look2.json"})

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
        got, note = WF.live_source(d, "AUS200")
        self.assertIsNone(got)                                             # MISSING, never an empty bar list
        self.assertIn("STALLED, no live 15m file", note)

    def test_init_takes_the_sealed_history_from_ninety_days_before_the_seal(self):
        bars = mk_bars(TEW.rising(96 * 100))
        seal = t_at(96 * 95)
        got = WF.plan_init(bars, seal, "now")
        self.assertEqual(got[0]["t"], t_at(96 * 5))
        self.assertTrue(all(b["src"] == "history" for b in got))

    def test_a_source_appends_only_on_the_stores_last_bars_and_a_revised_bar_is_a_revision(self):
        bars = mk_bars(TEW.rising(40))
        store, src = bars[:30], [dict(b, src="live") for b in bars[20:]]
        new, why, revs = WF.plan_append(store, src, "live", "now")
        self.assertEqual((why, revs), (None, []))
        self.assertEqual([b["t"] for b in new], [b["t"] for b in bars[30:]])
        # A bar the source shows at another price is a REVISION: the new bars are appended, the store keeps its bar,
        # and the caller gets (store bar, source bar) to log (WY-F1 §4; the old rule appended nothing here).
        revised = [dict(b, c=b["c"] + 0.5) if b["t"] == store[-2]["t"] else b for b in src]
        new, why, revs = WF.plan_append(store, revised, "live", "now")
        self.assertEqual((why, [b["t"] for b in new]), (None, [b["t"] for b in bars[30:]]))
        self.assertEqual([(a["t"], a["c"], b["c"]) for a, b in revs],
                         [(store[-2]["t"], store[-2]["c"], store[-2]["c"] + 0.5)])
        # Too few agreeing bars, or more differing than agreeing, is no revision: a shifted clock or another series.
        shifted = [dict(b, t=WF._iso(WF._utc(b["t"]) + datetime.timedelta(hours=1))) for b in src]   # v1.02 after DST
        new, why, revs = WF.plan_append(store, shifted, "live", "now")
        self.assertEqual((new, revs), ([], []))
        self.assertIn("disagrees", why)
        other = [dict(b, o=b["o"] + 1, h=b["h"] + 1, l=b["l"] + 1, c=b["c"] + 1) for b in src]       # same times, another series
        new, why, revs = WF.plan_append(store, other, "live", "now")
        self.assertEqual((new, revs), ([], []))
        self.assertIn("revisions need at least", why)
        hole = [b for b in src if b["t"] > bars[33]["t"]]
        new, why, revs = WF.plan_append(store, hole, "live", "now")
        self.assertEqual(new, [])
        self.assertIn("hole", why)
        gap = [b for b in src if b["t"] != store[-2]["t"]]                                    # lacks a bar of the store's tail
        new, why, _revs = WF.plan_append(store, gap, "live", "now")
        self.assertEqual(new, [])
        self.assertIn("lacks the store's bar", why)
        self.assertEqual(WF.plan_append(store, src[:5], "live", "now"), ([], None, []))        # behind: silent
        one = [dict(b, src="live") for b in bars[29:]]                                          # holds only the last bar
        self.assertEqual([b["t"] for b in WF.plan_append(store, one, "live", "now")[0]], [b["t"] for b in bars[30:]])
        one_bad = [dict(one[0], c=one[0]["c"] + 0.5)] + one[1:]                                 # and it differs: cannot tell
        new, why, _revs = WF.plan_append(store, one_bad, "live", "now")
        self.assertEqual(new, [])
        self.assertIn("disagrees", why)

    def test_a_revised_bar_never_wedges_a_store(self):
        """The review's wedge: the broker revises a bar AFTER the store took it, while it is among the store's last bars.
        Every later source (a live file, a history export) shows the revised bar, so the old rule never appended again.
        Now each appends, and the bar stays as first stored (WY-F1 §4)."""
        def bar(j, p):
            return {"t": t_at(j), "o": p, "h": p + 1, "l": p - 1, "c": p + 0.5, "v": 1}
        store = [bar(j, 100 + j) for j in range(10)]
        truth = [dict(b) for b in store] + [bar(j, 100 + j) for j in range(10, 120)]
        truth[8] = dict(truth[8], h=truth[8]["h"] + 0.25)                    # the server later revises bar 8
        first = dict(store[8])
        for live, hist in ((truth[5:25], truth[:30]), (truth[12:20 + 60], truth[:33]), (truth[60:100], truth[:50])):
            for src, source in (("live", live), ("history", hist)):
                new, why, revs = WF.plan_append(store, source, src, "now")
                if source[0]["t"] > store[-1]["t"]:
                    self.assertIn("hole", why)                               # a live file that starts after the store's end
                    continue
                self.assertIsNone(why, (src, why))
                self.assertTrue(new, src)
                self.assertEqual([(a["t"], b["h"] - a["h"]) for a, b in revs], [(t_at(8), 0.25)])
        new, _why, _revs = WF.plan_append(store, truth[:60], "history", "now")
        store = store + new                                                  # progress, and the store keeps its bar:
        self.assertEqual(store[8], first)
        new, why, revs = WF.plan_append(store, truth[:90], "history", "now")  # still revised there: still not wedged
        self.assertEqual((why, len(new), len(revs)), (None, 30, 1))

    def test_after_downtime_the_history_export_bridges_the_hole_then_the_live_file_continues(self):
        d = tempfile.mkdtemp()
        bars = mk_bars(TEW.rising(400))
        store = bars[:100]
        write_history(d, "XAUUSD", bars[:300])                   # a re-export: its final bar 299 is dropped
        write_live(d, "XAUUSD", bars[250:])                      # the live file starts after the store's end
        acc = WF.accumulate_symbol("XAUUSD", store, d, d, {"instant": t_at(50)}, "now")
        add = acc["add"]
        self.assertEqual((acc["notes"], acc["stalled"], acc["not_advancing"]), ([], False, None))
        self.assertEqual([b["t"] for b in add], [b["t"] for b in bars[100:399]])
        self.assertEqual({b["src"] for b in add[:199]}, {"history"})
        self.assertEqual({b["src"] for b in add[199:]}, {"live"})
        self.assertEqual(acc["last"], bars[398]["t"])

    def test_a_shifted_live_clock_appends_nothing_and_says_why(self):
        d = tempfile.mkdtemp()
        bars = mk_bars(TEW.rising(200))
        shifted = [dict(b, t=WF._iso(WF._utc(b["t"]) + datetime.timedelta(hours=1))) for b in bars[90:]]
        write_live(d, "XAUUSD", shifted, jitter=False)
        acc = WF.accumulate_symbol("XAUUSD", bars[:100], d, d, {"instant": t_at(50)}, "now")
        self.assertEqual((acc["add"], acc["stalled"]), ([], False))      # the feed is there; it does not connect
        self.assertTrue(any("disagrees" in n for n in acc["notes"]))
        self.assertIn("disagrees", acc["not_advancing"])                 # flagged, with the store's last bar
        self.assertIn(bars[99]["t"], acc["not_advancing"])

    def test_a_missing_or_unusable_live_file_is_stalled_never_an_empty_market(self):
        """CLAUDE.md §20: MISSING is never EMPTY. A symbol whose live 15m file is missing (JP225 and AUS200 today), or
        unusable, is STALLED: nothing is appended from it, the cycle and status list it, its store does not advance, so
        no look counts it complete -- it is dropped whole only by the registered per-look fallback, by name."""
        d = tempfile.mkdtemp()
        bars = mk_bars(TEW.rising(200))
        store = bars[:100]
        acc = WF.accumulate_symbol("JP225", store, d, d, {"instant": t_at(50)}, "now")
        self.assertEqual((acc["add"], acc["stalled"], acc["not_advancing"]), ([], True, None))
        self.assertTrue(any(n.startswith("JP225: STALLED, no live 15m file") for n in acc["notes"]), acc["notes"])
        for bad in ([], [dict(c, time="2026-06-01T00:07:00Z") for c in candles(bars[90:92])], candles(bars[150:151])):
            WF._write_json(os.path.join(d, WF.LIVE_DIR, "ohlcv.JP225.cash.15m.json"),
                           {"symbol": "JP225.cash", "timeframe": "15m", "candles": bad})     # empty / off-grid / forming
            got, note = WF.live_source(d, "JP225")
            self.assertIsNone(got)
            self.assertIn("STALLED", note)
            acc = WF.accumulate_symbol("JP225", store, d, d, {"instant": t_at(50)}, "now")
            self.assertEqual((acc["add"], acc["stalled"]), ([], True))
        write_history(d, "JP225", bars[:180])                    # a history re-export still bridges bars, and says
        acc = WF.accumulate_symbol("JP225", store, d, d, {"instant": t_at(50)}, "now")
        self.assertEqual(([b["t"] for b in acc["add"]], acc["stalled"]), ([b["t"] for b in bars[100:179]], True))   # feed down
        # The cycle lists it and adds nothing for it; status says STALLED; its store is never complete.
        root, seal = canary_root()
        os.remove(os.path.join(root, WF.LIVE_DIR, "ohlcv.JP225.cash.15m.json"))
        before = WF.read_chain(WF._rt(root, "bars", "JP225.15m.jsonl"))[0]
        res = WF.cycle_core(root, seal, "fp", "2026-07-02T00:00:00Z", init_root=root)
        self.assertEqual((res["summary"]["stalled"], res["summary"]["added_bars"]["JP225"]), (["JP225"], 0))
        WF.commit(res["writes"])
        self.assertEqual(WF.read_chain(WF._rt(root, "bars", "JP225.15m.jsonl"))[0], before)
        st = WF.status(root)
        self.assertEqual((st["stalled"], st["symbols"]["JP225"]["stalled"]), (["JP225"], True))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            WF._print_status(st)
        self.assertIn("STALLED", buf.getvalue())

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


# ------------------------------------------------------------------------------------------------ torn writes (WY-F1 §4)
class TornWrites(unittest.TestCase):
    """A worker killed during `commit` (the cycle's 120 s cap) leaves an UNTERMINATED last line: bytes that were never
    part of the chain. The next cycle drops exactly those bytes, after logging them in repairs.jsonl. A terminated line
    is never dropped, and a live writer is never cut."""

    def tear(self, d):
        """The XAUUSD store and the log as a killed `commit` leaves them: part of a bar line, and a whole resolve line
        but its newline (its R is what status must never show). Returns the paths, the clean bytes, the torn bytes and
        each chain's (records, head)."""
        bp, lp = WF._rt(d, "bars", "XAUUSD.15m.jsonl"), WF._rt(d, "log.jsonl")
        bars, heads = WF.read_chain(bp)
        log, lheads = WF.read_chain(lp)
        clean = {p: open(p, "rb").read() for p in (bp, lp)}
        nxt = dict(bars[-1], t="2099-01-01T00:00:00Z")
        fake = {"kind": "resolve", "id": log[0]["id"] + "|torn", "R": 123.456789, "outcome": "win"}
        torn = {bp: WF._canon(dict(nxt, ch=WF._link(heads[-1], nxt))).encode()[:37],
                lp: WF._canon(dict(fake, ch=WF._link(lheads[-1], fake))).encode()}
        for p in (bp, lp):
            with open(p, "ab") as fh:
                fh.write(torn[p])
        return bp, lp, clean, torn, {bp: (len(bars), heads[-1]), lp: (len(log), lheads[-1])}

    def test_an_unterminated_last_line_is_dropped_and_logged_and_a_terminated_one_never(self):
        d, seal = canary_root()
        bp, lp, clean, torn, kept = self.tear(d)
        for p in (bp, lp):
            with self.assertRaises(SystemExit) as cm:
                WF.read_chain(p)                                                  # every reader refuses it
            self.assertIn("unterminated", str(cm.exception))
        with self.assertRaises(SystemExit) as cm:
            WF.append_chain(bp, [{"x": 1}], kept[bp][1])                          # nothing is glued onto it
        self.assertIn("unterminated", str(cm.exception))
        self.assertEqual(open(bp, "rb").read(), clean[bp] + torn[bp])
        for call in (lambda: read(d, seal), lambda: WF.cmd_anchor(d)):
            with self.assertRaises(SystemExit) as cm:
                call()                                                            # the read and an anchor wait for a cycle
            self.assertIn("unterminated", str(cm.exception))
        st = WF.status(d)                                                         # status names the files, no bytes
        self.assertEqual(st["repairs"]["pending"], ["bars/XAUUSD.15m.jsonl", "log.jsonl"])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            WF._print_status(st)
        self.assertIn("pending, dropped by the next cycle", buf.getvalue())
        for text in (json.dumps(st), buf.getvalue()):
            self.assertNotIn("123.456789", text)
        res = WF.cycle_core(d, seal, "fp", "2026-07-02T00:00:00Z", init_root=d)
        self.assertEqual([w[0] for w in res["writes"]], ["repair", "json"])
        self.assertEqual(res["summary"]["repaired"], ["bars/XAUUSD.15m.jsonl", "log.jsonl"])
        self.assertNotIn("123.456789", json.dumps(res["summary"]))
        WF.commit(res["writes"])
        for p in (bp, lp):
            self.assertEqual(open(p, "rb").read(), clean[p])                      # exactly the torn bytes are gone
        rep, _ = WF.read_chain(WF._rt(d, WF.REPAIRS))
        self.assertEqual([(r["file"], r["offset"], r["kept_records"], r["kept_head"], r["dropped_bytes"],
                           r["dropped_sha256"], r["complete_record"]) for r in rep],
                         [("bars/XAUUSD.15m.jsonl", len(clean[bp]), *kept[bp], 37,
                           hashlib.sha256(torn[bp]).hexdigest(), False),
                          ("log.jsonl", len(clean[lp]), *kept[lp], len(torn[lp]),
                           hashlib.sha256(torn[lp]).hexdigest(), True)])
        self.assertEqual([base64.b64decode(r["dropped_b64"]) for r in rep], [torn[bp], torn[lp]])
        self.assertTrue(all(r["seal"] == seal["sha"] and r["fingerprint"] == "fp" for r in rep))
        out = read(d, seal)                                                       # never part of a chain: the read
        self.assertEqual((out["sample"], out["repairs"]["records"], out["repairs"]["files"]),   # passes, and says so
                         (10, 2, {"bars/XAUUSD.15m.jsonl": 1, "log.jsonl": 1}))
        self.assertNotIn("dropped_b64", json.dumps(out["repairs"]))
        self.assertEqual(WF.status(d)["repairs"]["pending"], [])
        # A TERMINATED line is never dropped: torn bytes that got a newline, or a duplicated last line, refuse every
        # step, and the file stays byte for byte as it is.
        for bad in (torn[bp] + b"\n", clean[bp].splitlines(keepends=True)[-1]):
            with open(bp, "ab") as fh:
                fh.write(bad)
            before = open(bp, "rb").read()
            with self.assertRaises(SystemExit) as cm:
                WF.cycle_core(d, seal, "fp", "2026-07-03T00:00:00Z", init_root=d)
            self.assertRegex(str(cm.exception), "not a JSON record|breaks the hash chain")
            self.assertEqual(open(bp, "rb").read(), before)
            with open(bp, "wb") as fh:
                fh.write(clean[bp])

    def test_a_live_writer_is_never_cut_and_the_repair_log_heals_itself(self):
        d, seal = canary_root()
        bp, lp, clean, torn, _kept = self.tear(d)
        rp = WF._rt(d, WF.REPAIRS)
        if WF.fcntl is not None:
            with open(bp, "ab") as writer:                                        # a writer still alive, mid-append
                WF.fcntl.flock(writer.fileno(), WF.fcntl.LOCK_EX)
                res = WF.cycle_core(d, seal, "fp", "2026-07-02T00:00:00Z", init_root=d)
                with self.assertRaises(SystemExit) as cm:
                    WF.commit(res["writes"])
                self.assertIn("a writer still holds", str(cm.exception))
                with self.assertRaises(SystemExit) as cm:
                    WF.append_chain(bp, [{"x": 1}], "x")                         # nor is anything appended under it
                self.assertIn("another writer holds", str(cm.exception))
            self.assertEqual(open(bp, "rb").read(), clean[bp] + torn[bp])         # not cut, and nothing logged
            self.assertFalse(os.path.exists(rp))
        res = WF.cycle_core(d, seal, "fp", "2026-07-02T00:00:00Z", init_root=d)
        with open(lp, "ab") as fh:
            fh.write(b"\n")                                                       # the line was finished after the plan
        with self.assertRaises(SystemExit) as cm:
            WF.commit(res["writes"])
        self.assertIn("changed while this cycle ran", str(cm.exception))
        self.assertEqual(open(bp, "rb").read(), clean[bp] + torn[bp])
        self.assertFalse(os.path.exists(rp))
        with open(lp, "wb") as fh:
            fh.write(clean[lp] + torn[lp])
        with open(rp, "wb") as fh:                                                # a repair record that never completed
            fh.write(b'{"complete_record":false,"dropped_b64":"eyJhdCI')
        res = WF.cycle_core(d, seal, "fp", "2026-07-02T00:00:00Z", init_root=d)
        WF.commit(res["writes"])
        rep, _ = WF.read_chain(rp)
        self.assertEqual([(r["file"], r["offset"]) for r in rep],
                         [("bars/XAUUSD.15m.jsonl", len(clean[bp])), ("log.jsonl", len(clean[lp])), (WF.REPAIRS, 0)])
        for p in (bp, lp):
            self.assertEqual(open(p, "rb").read(), clean[p])


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
        self.assertTrue(set(WF.LOG_ONLY_KEYS) <= set(r))                       # logged, None where they do not apply
        self.assertEqual((r["mfe_r"], r["planned_rr"]), (None, None))

    def test_the_log_only_fields_use_no_bar_beyond_the_walk_and_the_gate_none_after_the_signal(self):
        """WY-F1 §6: MFE / MAE in R, bars to MFE, the planned R:R, the entry-hour spread and the HTF gate flag come from
        bars the resolve already reads -- the walk's bars e..exit, and the store up to the signal bar k for the gate --
        so a store cut right after the exit, or with every later bar changed, logs the same record."""
        k, e = self.d["store_index"], self.d["store_index"] + 1
        full = self.resolve(len(self.bars))
        S = WF.series_of("XAUUSD", self.bars)
        x = S.T.index(full["exit_time"])
        entry, stop = S.O[e], self.d["stop"]
        risk = entry - stop
        self.assertEqual(full["planned_rr"], (self.d["target"] - entry) / risk)
        self.assertEqual(full["mfe_r"], (max(S.H[e:x + 1]) - entry) / risk)
        self.assertEqual(full["mae_r"], (entry - min(S.L[e:x + 1])) / risk)
        self.assertEqual(full["bars_to_mfe"], S.H[e:x + 1].index(max(S.H[e:x + 1])))
        self.assertEqual(set(full["spread_r_entry"]), {"median", "p90"})
        self.assertIn(full["htf_gate"], (True, False, None))
        self.assertEqual(self.resolve(x + 1), full)                                   # cut right after the exit
        moved = self.bars[:x + 1] + [dict(b, o=b["o"] * 1.1, h=b["h"] * 1.2, l=b["l"] * 0.8, c=b["c"] * 0.9)
                                     for b in self.bars[x + 1:]]
        self.assertEqual(WF.resolve_record(WF.series_of("XAUUSD", moved), self.rec, self.seal, "fp", "now"), full)
        after_k = self.bars[:k + 1] + [dict(b, h=b["h"] + 5.0, c=b["c"] + 1.0) for b in self.bars[k + 1:]]
        self.assertEqual(WF.htf_gate(WF.series_of("XAUUSD", after_k), k), WF.htf_gate(S, k))
        hours = WF.htf_candles(S, k, 60)
        self.assertLessEqual(WF._utc(hours[-1]["time"]) + datetime.timedelta(hours=1), S.avail[k])

    def test_the_htf_gate_is_the_engines_own_function_as_the_a3_arm_applies_it(self):
        k = self.d["store_index"]
        S = WF.series_of("XAUUSD", self.bars)
        if not sealed_here():                       # the pin is what the engine's scan resolves for the seven symbols
            self.assertEqual({BT._auto.market_of(s) for s in WF.RT_SYMBOLS}, {"cfd"})
            self.assertEqual(BT.lr.htf.engaged_methods_for_market("cfd"), WF.HTF_METHODS)
            self.assertIsNone(BT.OPTS["methods"])
            self.assertEqual({BT.resolve_methods(s) for s in WF.RT_SYMBOLS}, {WF.HTF_METHODS})
        seen = []
        real_load, real_opts = BT.load, BT.OPTS

        def gate(sym, tf, side, decision_time, methods, h=None):
            seen.append((sym, tf, side, decision_time, methods, BT.OPTS["htf"], BT.load(sym, "1H")[0]))
            return True
        with mock.patch.object(BT, "htf_bias_gate", gate):
            self.assertEqual(WF.htf_gate(S, k), (True, None))
        (call,) = seen
        self.assertEqual(call[:6], ("XAUUSD", "15m", "long", WF._iso(S.avail[k]), WF.HTF_METHODS, True))
        self.assertEqual(call[6], WF.htf_candles(S, k, 60))                    # the store's own hours, up to bar k
        self.assertIs(BT.load, real_load)
        self.assertIs(BT.OPTS, real_opts)

        def boom(*_a, **_k):
            raise ValueError("synthetic")
        with mock.patch.object(BT, "htf_bias_gate", boom):
            flag, err = WF.htf_gate(S, k)                                         # logged, never raised
        self.assertEqual((flag, "ValueError" in err), (None, True))
        self.assertIs(BT.load, real_load)

    def test_the_log_only_fields_never_reach_status_or_a_cycle_summary(self):
        d, seal = canary_root()
        log, _ = WF.read_chain(WF._rt(d, "log.jsonl"))
        resolves = [r for r in log if r["kind"] == "resolve"]
        self.assertEqual(len(resolves), 10)
        self.assertTrue(all(set(WF.LOG_ONLY_KEYS) <= set(r) and r["mfe_r"] is not None for r in resolves))
        values = {repr(r[k]) for r in resolves for k in ("mfe_r", "mae_r", "planned_rr")}
        res = WF.cycle_core(d, seal, "fp", "2026-07-02T00:00:00Z", init_root=d)
        with mock.patch.object(WF, "seal_info", lambda root=None: dict(seal, date="x")), \
                mock.patch.object(WF, "committed_anchors", lambda root: []):
            st = WF.status(d)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            WF._print_status(st)
        for text in (json.dumps(res["summary"]), json.dumps(st), buf.getvalue()):
            for key in WF.LOG_ONLY_KEYS + ("spread_r", "mfe", "mae"):
                self.assertNotIn(key, text)
            for v in values:
                self.assertNotIn(v, text)

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
        self.assertEqual(st["rule"]["counted_events"], 10)
        self.assertEqual(st2["rule"]["counted_events"], 10)
        self.assertEqual(st2["symbols"]["XAUUSD"]["unresolved_past_walk"], 1)
        r = st["rule"]
        plan = WF.look_plan(seal["instant"])
        self.assertEqual([r["looks"][n]["t_cutoff"] for n in ("1", "2")], [WF._iso(c) for c, _g in plan])
        self.assertEqual((r["next_look"], r["read_due"], r["records"]), ("1", False, {"1": False, "2": False}))
        self.assertEqual(r["never_due_close"], WF._iso(WF.add_months(WF._utc(seal["instant"]), 48)))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            WF._print_status(st)
        self.assertIn("never-due close", buf.getvalue())
        self.assertIn("look 2: cutoff", buf.getvalue())


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

    @staticmethod
    def through(day):
        """A FakeS complete through `day` (UTC midnight): 96 bars after it are stored."""
        days = (WF._utc(day + "T00:00:00Z") - WF._utc(ReadRule.SEAL)).days
        return FakeS(96 * days + 96)

    def test_each_look_cuts_at_its_month_on_data_complete_for_every_symbol(self):
        plan = WF.look_plan(self.SEAL)
        self.assertEqual([(WF._iso(c), WF._iso(g)) for c, g in plan],
                         [("2027-10-05T00:00:00Z", "2028-01-05T00:00:00Z"), ("2029-10-05T00:00:00Z", "2030-01-05T00:00:00Z")])
        a = self.through("2027-10-05")
        r = WF.due({"A": a, "B": a}, self.SEAL, 96, 1)
        self.assertEqual((r["cutoff"], r["rule"][:3], r["dropped"]), ("2027-10-05T00:00:00Z", "T1:", []))
        self.assertIsNone(WF.due({"A": a, "B": a}, self.SEAL, 96, 2)["cutoff"])        # look 2 waits for its month
        short = self.through("2027-10-04")
        self.assertIsNone(WF.due({"A": a, "B": short}, self.SEAL, 96, 1)["cutoff"])     # every symbol must be complete
        b = self.through("2029-10-05")
        r = WF.due({"A": b, "B": b}, self.SEAL, 96, 2)
        self.assertEqual((r["cutoff"], r["rule"][:3]), ("2029-10-05T00:00:00Z", "T2:"))

    def test_a_symbol_stalled_three_months_past_a_looks_cutoff_is_dropped_whole_from_that_look(self):
        """The fallback drops symbols only when at least DROP_MIN_COMPLETE (5) of the 10 are complete through the
        cutoff; with fewer the look WAITS (WY-F1 §7, decision 2026-10-04)."""
        names = "ABCDEFGHIJ"
        full, stalled = self.through("2028-01-05"), self.through("2027-04-01")

        def ten(complete, other=stalled):
            return {n: (full if i < complete else other) for i, n in enumerate(names)}
        for n_complete in (9, 6, 5):
            r = WF.due(ten(n_complete), self.SEAL, 96, 1)
            drop = list(names[n_complete:])
            self.assertEqual((r["cutoff"], r["dropped"], r["rule"][:8]), ("2027-10-05T00:00:00Z", drop, "T1-drop:"))
            self.assertEqual((r["complete_at_cutoff"], r["min_complete"]), (n_complete, 5))
            self.assertIn(f"{n_complete} of 10 symbols complete", r["rule"])
        self.assertEqual(WF.due(ten(5), self.SEAL, 96, 1)["grace_cutoff"], "2028-01-05T00:00:00Z")
        for n_complete in (4, 1, 0):                         # fewer than 5 of the 10: the look waits, no one is dropped
            r = WF.due(ten(n_complete), self.SEAL, 96, 1)
            self.assertEqual((r["cutoff"], r["dropped"], r["rule"], r["complete_at_cutoff"]),
                             (None, [], None, n_complete))
        early = self.through("2028-01-04")                                       # 12 months done, the grace not over
        grace_not_over = {n: (early if i < 6 else stalled) for i, n in enumerate(names)}
        self.assertIsNone(WF.due(grace_not_over, self.SEAL, 96, 1)["cutoff"])
        never = ten(7) | {"J": None}                                                 # a symbol that never had a store
        self.assertEqual(WF.due(never, self.SEAL, 96, 1)["dropped"], ["H", "I", "J"])
        no_grace = WF.look_plan(self.SEAL, grace_months=None)
        self.assertIsNone(WF.due(ten(9), self.SEAL, 96, 1, no_grace)["cutoff"])
        # Per look: a symbol complete for look 1 and stalled before look 2 is read at look 1, dropped from look 2 only.
        late, mid = self.through("2030-01-05"), self.through("2028-06-01")
        two = {n: (late if i < 6 else mid) for i, n in enumerate(names)}
        self.assertEqual(WF.due(two, self.SEAL, 96, 1)["dropped"], [])
        r = WF.due(two, self.SEAL, 96, 2)
        self.assertEqual((r["cutoff"], r["dropped"], r["rule"][:8]), ("2029-10-05T00:00:00Z", list("GHIJ"), "T2-drop:"))
        self.assertIsNone(WF.due(dict(two, A=self.through("2030-01-04"), B=self.through("2030-01-04"),
                                      C=self.through("2030-01-04"), D=self.through("2030-01-04"),
                                      E=self.through("2030-01-04"), F=self.through("2030-01-04")),
                                 self.SEAL, 96, 2)["cutoff"])

    def test_the_never_due_close_is_procedural_and_the_code_does_not_refuse_a_later_look(self):
        """WY-F1 §7: seal + 48 months is a date the coordinator acts on (status shows it); nothing in the code refuses
        a look after it -- a look whose stores are complete later still computes its cutoff."""
        names = "ABCDEFGHIJ"
        late = self.through("2031-03-01")                                         # complete far past seal + 48 months
        r = WF.due({n: late for n in names}, self.SEAL, 96, 2)
        self.assertEqual((r["cutoff"], r["dropped"]), ("2029-10-05T00:00:00Z", []))
        close = WF.add_months(WF._utc(self.SEAL), WF.NEVER_DUE_MONTHS)
        self.assertEqual(WF._iso(close), "2030-10-05T00:00:00Z")
        self.assertGreater(WF._utc("2031-03-01T00:00:00Z"), close)

    def test_an_early_look_refuses_before_any_walk_or_cost_is_computed(self):
        # The canary root's log already holds resolve records (gross R): what this proves is that a look computes
        # no walk, no placebo and no cost before its rule is met -- not that no outcome exists anywhere (WY-F1 §6).
        d, seal = canary_root()
        prior = read(d, seal)

        def boom(*a, **k):
            raise AssertionError("an outcome was computed before the look was due")
        for look, pr in ((1, None), (2, prior)):
            with mock.patch.object(E, "walk_from", boom), mock.patch.object(E, "score", boom), \
                    mock.patch.object(E, "Pricer", boom), self.assertRaises(SystemExit) as cm:
                WF.read_core(d, seal, "fp", look=look, prior=pr, cost_r=fake_cost_r)   # the registered 12 / 36 months
            self.assertIn(f"look {look} is not due", str(cm.exception))


# ------------------------------------------------------------------------------------------------ two looks (§7)
def _phi(x):
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def _phi_inv(p):
    lo, hi = -12.0, 12.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if _phi(mid) < p else (lo, mid)
    return 0.5 * (lo + hi)


def bvn_simpson(a, b, r, steps=4000, lo=-12.0):
    """An INDEPENDENT P(Z1 <= a, Z2 <= b) for the standard bivariate normal with correlation r: composite Simpson on
    the conditional form, the integral from lo to a of phi(x) Phi((b - r x) / sqrt(1 - r^2)) dx -- not the code's
    Gauss-Legendre / Drezner-Wesolowsky branches."""
    s, h, tot = math.sqrt(1.0 - r * r), (a - lo) / steps, 0.0
    for i in range(steps + 1):
        x = lo + i * h
        tot += (1 if i in (0, steps) else 4 if i % 2 else 2) * math.exp(-0.5 * x * x) * _phi((b - r * x) / s)
    return tot * h / 3.0 / math.sqrt(2.0 * math.pi)


def two_look_simpson(t1, alpha):
    """(z1, z2) of a one-sided two-look Lan-DeMets O'Brien-Fleming-type design at information fraction t1, computed
    independently of the code: the spending alpha(t) = 2 (1 - Phi(z_{1-alpha/2} / sqrt(t))) with this file's own Phi
    and its inverse, and z2 from P0(Z1 < z1, Z2 < z2) = 1 - alpha by bisection on `bvn_simpson`."""
    a1 = 2.0 * (1.0 - _phi(_phi_inv(1.0 - alpha / 2.0) / math.sqrt(t1)))
    z1 = _phi_inv(1.0 - a1)
    lo, hi = -8.0, 8.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if bvn_simpson(z1, mid, math.sqrt(t1)) < 1.0 - alpha else (lo, mid)
    return z1, 0.5 * (lo + hi)


def poisson(rnd, lam):
    """A Poisson draw (Knuth), for the simulated event counts."""
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rnd.random()
        if p <= limit:
            return k
        k += 1


class TwoLooks(unittest.TestCase):
    """WY-F1 §7: two looks, Lan-DeMets O'Brien-Fleming-type spending, one-sided alpha 0.10 in total, the boundaries
    from the looks' ACTUAL event counts -- checked against an independent computation and by simulating the type-I
    error under the null with event rates that are not steady."""

    def test_the_spending_and_both_boundaries_match_an_independent_computation(self):
        for a, b, r in ((2.62, 1.29, 0.577), (-0.5, 2.0, 0.2), (1.0, -1.0, -0.6), (3.0, 1.3, 0.95), (0.3, 0.1, 0.99)):
            self.assertAlmostEqual(WF.bvn_lower(a, b, r), bvn_simpson(a, b, r), places=10)
        self.assertEqual((WF.obf_spend(0.0), WF.obf_spend(1.0)), (0.0, WF.ALPHA))
        for t in (0.1, 1 / 3, 0.5, 0.9):
            self.assertAlmostEqual(WF.obf_spend(t), 2.0 * (1.0 - _phi(_phi_inv(1 - WF.ALPHA / 2) / math.sqrt(t))),
                                   places=12)
        # The registered design at the planning rate (14 a year): look 1 at 14 events is t = 1/3 -- one-sided p below
        # 0.0044 (z 2.62) -- and look 2 at 42 events p below 0.0986 (z 1.29), as the WY-X1 draft's §12.2 (b) has them.
        b1 = WF.look1_boundary(14)
        self.assertEqual((b1["n"], b1["t"]), (14, 1 / 3))
        b2 = WF.look2_boundary(b1, 42, 14)
        z1, z2 = two_look_simpson(1 / 3, WF.ALPHA)
        self.assertAlmostEqual(b1["z"], z1, places=7)
        self.assertAlmostEqual(b2["z"], z2, places=6)
        self.assertEqual((round(b1["p_threshold"], 4), round(b1["z"], 2)), (0.0044, 2.62))
        self.assertEqual((round(b2["p_threshold"], 4), round(b2["z"], 2)), (0.0986, 1.29))
        # The classic case, one-sided 0.025 at t = 0.5 and 1: the independent computation gives 2.963 and 1.969, the
        # commonly tabulated two-look OBF-type boundaries; the code's functions give the same.
        z1, z2 = two_look_simpson(0.5, 0.025)
        self.assertEqual((round(z1, 3), round(z2, 3)), (2.963, 1.969))
        c1 = WF.look1_boundary(10, n_rest=10, alpha=0.025)
        self.assertAlmostEqual(c1["z"], z1, places=7)
        self.assertAlmostEqual(WF.look2_boundary(c1, 20, 10, alpha=0.025)["z"], z2, places=6)
        # The total false-pass probability is alpha for any counts, steady or not (Simpson, independent of the code).
        for n1, n2 in ((14, 42), (3, 60), (40, 46), (1, 2), (25, 26)):     # P0(Z1 >= z1 or Z2 >= z2)
            b1 = WF.look1_boundary(n1)
            b2 = WF.look2_boundary(b1, n2, n1)
            self.assertAlmostEqual(1.0 - bvn_simpson(b1["z"], b2["z"], b2["rho"]), WF.ALPHA, places=7)

    def test_look_two_spends_what_look_one_left_and_an_empty_look_one_spends_nothing(self):
        b1 = WF.look1_boundary(0)
        self.assertEqual((b1["t"], b1["alpha_spent"], b1["z"], b1["p_threshold"]), (0.0, 0.0, None, 0.0))
        b2 = WF.look2_boundary(b1, 30, 0)
        self.assertAlmostEqual(b2["p_threshold"], WF.ALPHA, places=12)          # one look at the full alpha
        b1 = WF.look1_boundary(20)
        self.assertAlmostEqual(WF.look2_boundary(b1, 50, 20)["alpha_spent"] + b1["alpha_spent"], WF.ALPHA, places=15)
        self.assertGreater(WF.look1_boundary(60)["alpha_spent"], WF.look1_boundary(14)["alpha_spent"])   # actual n1
        self.assertLess(WF.look1_boundary(60)["t"], 1.0)
        for s, want in (({"n": 0}, False), ({"n": 5, "net_excess": 0.4, "p_one_sided": 0.001}, True),
                        ({"n": 5, "net_excess": -0.1, "p_one_sided": 0.001}, False),
                        ({"n": 5, "net_excess": 0.4, "p_one_sided": 0.0044}, False)):
            self.assertEqual(WF.crossed(s, {"p_threshold": 0.0044}), want, s)

    def test_the_type_one_error_stays_at_alpha_under_a_non_steady_event_rate(self):
        """Under the null, with event counts that do not arrive at the planning rate -- a slow first year (4, then 50
        between the looks) and a fast one (30, then 6) -- the two-look rule, with its boundaries computed from the
        actual counts, falsely passes 10 % of the time: exactly for the z statistic, and to simulation precision for
        the registered Student-t p-value on normal per-event values."""
        def run(lam1, lam_rest, reps, seed, t_stat=False):
            rnd, cache, hits = random.Random(seed), {}, 0
            for _ in range(reps):
                n1 = poisson(rnd, lam1)
                n2 = n1 + poisson(rnd, lam_rest)
                b1 = WF.look1_boundary(n1)
                if (n1, n2) not in cache:
                    cache[(n1, n2)] = WF.look2_boundary(b1, n2, n1)
                b2 = cache[(n1, n2)]
                if t_stat:
                    xs = [rnd.gauss(0.0, 1.0) for _ in range(n2)]

                    def summary(v):
                        if len(v) < 2:
                            return {"n": len(v), "net_excess": 0.0, "p_one_sided": 1.0}
                        m = sum(v) / len(v)
                        sd = math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))
                        return {"n": len(v), "net_excess": m,
                                "p_one_sided": E.EC.t_sf(m / (sd / math.sqrt(len(v))), len(v) - 1) if sd else 1.0}
                    hits += WF.crossed(summary(xs[:n1]), b1) or WF.crossed(summary(xs), b2)
                else:
                    s1 = math.sqrt(n1) * rnd.gauss(0.0, 1.0)
                    s2 = s1 + math.sqrt(n2 - n1) * rnd.gauss(0.0, 1.0)
                    hits += (bool(n1) and b1["z"] is not None and s1 / math.sqrt(n1) >= b1["z"]) \
                        or (bool(n2) and s2 / math.sqrt(n2) >= b2["z"])
            return hits / reps
        for lam1, lam_rest in ((4, 50), (30, 6)):
            reps = 30000
            rate = run(lam1, lam_rest, reps, 20261004)
            self.assertLess(abs(rate - WF.ALPHA), 3.5 * math.sqrt(WF.ALPHA * (1 - WF.ALPHA) / reps), (lam1, rate))
        rate = run(4, 50, 8000, 11, t_stat=True)
        self.assertLess(abs(rate - WF.ALPHA), 0.012, rate)


# ------------------------------------------------------------------------------------------------ the read (§7-§8)
class Read(unittest.TestCase):
    def test_the_read_measures_with_the_sealed_section_5(self):
        d, seal = canary_root()
        out = read(d, seal)
        s = out["statistic"]["summary"]
        self.assertEqual((out["sample"], s["n"], out["probe"]["violations"]), (10, 10, 0))
        self.assertTrue(out["cutoff"]["rule"].startswith("T1:"))
        for r in out["statistic"]["rows"]:
            self.assertAlmostEqual(r["net_excess"], r["excess"] - r["cost"]["median_swap"])
            self.assertEqual(r["tf"], "15m")
            self.assertEqual(r["set"], "added" if r["symbol"] in WF.ADDED_SYMBOLS else "rt")
        self.assertEqual(s, E.summarise(out["statistic"]["rows"], E.FTMO_LINES))
        self.assertEqual(set(out["statistic"]["by_set"]), {"rt", "added"})
        v, b = out["verdict"], out["boundary"]
        self.assertEqual(b, WF.look1_boundary(s["n"]))                       # from the ACTUAL count
        self.assertEqual(v["pass"], bool(s["n"]) and v["net_excess"] > 0 and v["p_one_sided"] < b["p_threshold"])
        self.assertEqual(v["label"], "PASS" if v["pass"] else "CONTINUE")      # never NOT PASSED at look 1
        self.assertEqual(out["statistic_sha256"], WF.statistic_sha256(out["statistic"]))
        self.assertEqual(set(out["history_check"]), set(WF.SYMBOLS))
        for h in out["history_check"].values():
            self.assertEqual((h["coverage"], h["agreement"], h["missing"], h["spans_end"], h["spans_checked"],
                              h["differences"], h["span_differences"]), (1.0, 1.0, 0, True, 1, [], 0))
            self.assertEqual((h["replay"]["ok"], h["replay"]["events"], h["replay"]["logged"]), (True, 1, 1))
            self.assertEqual((h["walks"]["compared"], h["walks"]["differ"]), (1, 0))
            self.assertEqual(len(h["export"]["files"]), 1)                    # the export's files, hashed
        self.assertEqual((out["symbols_read"], out["symbols_dropped"]), (list(WF.SYMBOLS), []))
        self.assertIsNotNone(out["anchors"]["note"])                          # no committed anchor: disclosed

    def test_a_look_one_that_does_not_cross_is_blinded_and_look_two_reproduces_its_commitment(self):
        d, seal = canary_root()
        one = read(d, seal)
        self.assertEqual(one["verdict"]["label"], "CONTINUE")                # the canary's ten events share one week
        rec = json.loads(json.dumps(WF.blind(dict(one, meta={"study": WF.STUDY, "seal": seal,
                                                               "fingerprint_digest": "fp"})), default=str))
        text = json.dumps(rec)
        for leak in ("net_excess", "p_one_sided", "upper_95", "mean_R", "mean_excess", '"rows"', '"R"', "placebo",
                     "outcome", "mfe_r"):
            self.assertNotIn(leak, text)                                      # no estimate, no p, no trade
        self.assertEqual(set(rec["verdict"]), set(WF.BLIND_VERDICT_KEYS))
        self.assertEqual(rec["statistic_sha256"], one["statistic_sha256"])
        self.assertEqual(WF.require_prior(rec, seal, "fp"), rec)
        two = read(d, seal, look=2, prior=rec)
        self.assertEqual(two["look1"]["statistic_sha256"], rec["statistic_sha256"])
        self.assertEqual(WF.statistic_sha256(two["look1"]["statistic"]), rec["statistic_sha256"])   # disclosed now
        n1, n2 = one["statistic"]["summary"]["n"], two["statistic"]["summary"]["n"]
        self.assertEqual(two["boundary"], WF.look2_boundary(WF.look1_boundary(n1), n2, n1))
        self.assertAlmostEqual(two["verdict"]["alpha_spent"] + two["verdict"]["alpha_spent_look1"], WF.ALPHA, places=12)
        self.assertIn(two["verdict"]["label"], ("PASS", "NOT PASSED"))
        self.assertTrue(two["verdict"]["final"])
        for bad, why in ((dict(rec, statistic_sha256="0" * 64), "does not reproduce its committed sha256"),
                         (dict(rec, boundary=dict(rec["boundary"], alpha_spent=0.05)), "does not follow from"),
                         (dict(rec, boundary=None), "needs look 1's record")):
            with self.assertRaises(SystemExit) as cm:
                read(d, seal, look=2, prior=bad)
            self.assertIn(why, str(cm.exception))

    def test_the_look_files_round_trip_a_blinded_look_one_into_look_two_and_a_pass_ends_it(self):
        """What `worker_read` writes (WF.look_record, edge_wyckoff._dump) and what look 2 reads back from the file."""
        d, seal = canary_root()
        meta = {"study": WF.STUDY, "seal": seal, "fingerprint_digest": "fp"}
        tmp = tempfile.mkdtemp()
        one = dict(read(d, seal), meta=meta)
        p1 = os.path.join(tmp, "look1.json")
        E._dump(WF.look_record(one), p1)
        text1 = open(p1).read()
        rec1 = json.loads(text1)
        self.assertEqual((rec1["verdict"]["label"], "rows" in rec1, "statistic" in rec1), ("CONTINUE", False, False))
        for leak in ("net_excess", "p_one_sided", "mean_R", '"R"'):
            self.assertNotIn(leak, text1)
        line = WF.look_line(one)
        self.assertIn("BLINDED", line)
        self.assertNotIn(repr(one["verdict"]["net_excess"]), line)
        two = dict(read(d, seal, look=2, prior=WF.require_prior(rec1, seal, "fp")), meta=meta)
        p2 = os.path.join(tmp, "look2.json")
        E._dump(WF.look_record(two), p2)
        rec2 = json.load(open(p2))
        rows1 = rec2["rows"][f"{WF.CELL}@look1"]
        self.assertEqual(set(rec2["rows"]), {f"{WF.CELL}@look1", f"{WF.CELL}@look2"})
        self.assertNotIn("rows", rec2["statistic"])
        self.assertNotIn("rows", rec2["look1"]["statistic"])
        self.assertEqual(WF.statistic_sha256({"rows": rows1, "summary": rec2["look1"]["statistic"]["summary"]}),
                         rec1["statistic_sha256"])                  # the disclosed look-1 rows are the committed ones
        self.assertEqual(len(rec2["rows"][f"{WF.CELL}@look2"]), rec2["statistic"]["summary"]["n"])
        self.assertIn("one-sided p", WF.look_line(two))
        with mock.patch.object(WF, "crossed", lambda s, b: True):    # a look 1 that crosses: the verdict, written whole
            won = dict(read(d, seal), meta=meta)
        self.assertEqual((won["verdict"]["label"], won["verdict"]["final"]), ("PASS", True))
        p3 = os.path.join(tmp, "pass.json")
        E._dump(WF.look_record(won), p3)
        rec3 = json.load(open(p3))
        self.assertEqual(len(rec3["rows"][f"{WF.CELL}@look1"]), won["statistic"]["summary"]["n"])
        self.assertIn("net_excess", rec3["verdict"])
        with self.assertRaises(SystemExit) as cm:
            WF.require_prior(rec3, seal, "fp")
        self.assertIn("a look-1 PASS ends WY-F1", str(cm.exception))

    def test_look_two_needs_look_ones_committed_continue_record_of_this_seal(self):
        seal = {"sha": "s" * 40, "instant": "2026-10-05T00:00:00Z"}
        ok = {"look": 1, "meta": {"study": WF.STUDY, "seal": seal, "fingerprint_digest": "fp"},
              "verdict": {"label": "CONTINUE", "pass": False}}
        self.assertIs(WF.require_prior(ok, seal, "fp"), ok)
        for bad, why in ((None, "needs look 1's committed record"),
                         (dict(ok, look=2), "is not WY-F1's look-1 record"),
                         (dict(ok, meta=dict(ok["meta"], fingerprint_digest="other")), "another seal or code"),
                         (dict(ok, meta=dict(ok["meta"], seal=dict(seal, sha="t" * 40))), "another seal or code"),
                         (dict(ok, verdict={"label": "PASS", "pass": True}), "a look-1 PASS ends WY-F1")):
            with self.assertRaises(SystemExit) as cm:
                WF.require_prior(bad, seal, "fp")
            self.assertIn(why, str(cm.exception))
        root = tempfile.mkdtemp()                                             # the record comes from git HEAD
        git(root, "init", "-q")
        self.assertIsNone(WF.committed_record(root, WF.LOOK_OUT[1]))
        p = os.path.join(root, WF.LOOK_OUT[1])
        WF._write_json(p, ok)
        self.assertIsNone(WF.committed_record(root, WF.LOOK_OUT[1]))             # on disk only: no record
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "look 1")
        self.assertEqual(WF.committed_record(root, WF.LOOK_OUT[1]), ok)
        WF._write_json(p, dict(ok, verdict={"label": "CONTINUE", "pass": False, "edited": True}))
        with self.assertRaises(SystemExit) as cm:
            WF.committed_record(root, WF.LOOK_OUT[1])
        self.assertIn("differs from its committed version", str(cm.exception))

    def test_the_replay_must_match_the_log(self):
        d, seal = canary_root()
        log, heads = WF.read_chain(WF._rt(d, "log.jsonl"))
        ghost = dict(next(r for r in log if r["kind"] == "event"), id="XAUUSD|15m|ghost")
        WF.append_chain(WF._rt(d, "log.jsonl"), [ghost], heads[-1])
        with self.assertRaises(SystemExit) as cm:
            read(d, seal)
        self.assertIn("replay does not match", str(cm.exception))

    def test_a_record_under_another_fingerprint_or_seal_refuses(self):
        d, seal = canary_root()
        with self.assertRaises(SystemExit) as cm:
            WF.read_core(d, seal, "another-fp", plan=WF.canary_plan(seal), cost_r=fake_cost_r)
        self.assertIn("another seal or code fingerprint", str(cm.exception))

    def test_bars_the_history_export_does_not_confirm_refuse(self):
        d, seal = canary_root()
        p = os.path.join(d, WF.HIST_DIR, "ohlcv.XAGUSD.15m.json")
        doc = json.load(open(p))
        for c in doc["candles"][WF.CANARY_SEAL_BAR:WF.CANARY_SEAL_BAR + 20]:
            c["close"] += 0.01
        WF._write_json(p, doc)
        with self.assertRaises(SystemExit) as cm:
            read(d, seal)
        self.assertIn("cannot be verified", str(cm.exception))
        self.assertIn("XAGUSD", str(cm.exception))

    def test_a_scored_trade_must_equal_its_logged_resolve(self):
        d, seal = canary_root()
        real = E.score

        def drift(*a, **k):
            r, why = real(*a, **k)
            return (dict(r, R=r["R"] + 1e-6), why) if r else (r, why)
        with self.assertRaises(SystemExit) as cm:
            read(d, seal, score_fn=drift)
        self.assertIn("disagree with their logged resolve", str(cm.exception))

    def test_an_export_taken_too_early_refuses_even_when_its_coverage_passes(self):
        d, seal = canary_root()
        wl = read(d, seal)["history_check"]["XAGUSD"]["window_last"]
        p = os.path.join(d, WF.HIST_DIR, "ohlcv.XAGUSD.15m.json")
        doc = json.load(open(p))
        doc["candles"] = [c for c in doc["candles"] if c["time"] < wl]           # ends 2 bars before the window's end
        WF._write_json(p, doc)
        with self.assertRaises(SystemExit) as cm:
            read(d, seal)
        self.assertIn("XAGUSD", str(cm.exception))
        self.assertIn("taken too early", str(cm.exception))                       # coverage alone is 0.986 here

    # (the export replay and walk tests of a changed bar are in `ExportCheck`)

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
        self.assertEqual((h["spans_checked"], h["span_differences"], h["differences"]), (1, 0, []))

    def test_a_dropped_symbol_leaves_the_sample_whole(self):
        d, seal = canary_root()
        real = WF.due

        def drop(*a, **k):
            return dict(real(*a, **k), dropped=["XAGUSD"], rule="T-drop: test")
        with mock.patch.object(WF, "due", drop):
            out = read(d, seal)
        self.assertEqual((out["sample"], out["symbols_dropped"]), (9, ["XAGUSD"]))
        self.assertNotIn("XAGUSD", out["history_check"])
        self.assertNotIn("XAGUSD", out["probe"]["per_symbol"])
        self.assertFalse(any(r["symbol"] == "XAGUSD" for r in out["statistic"]["rows"]))

    def test_anchors_come_from_git_history_and_must_sit_on_the_chains(self):
        d, seal = canary_root()
        git(d, "init", "-q")
        WF.cmd_anchor(d)
        git(d, "add", WF.ANCHORS)
        git(d, "commit", "-q", "-m", "anchor")
        anchors = WF.committed_anchors(d)
        out = read(d, seal, anchors=anchors)
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
            read(d, seal, anchors=WF.committed_anchors(d))
        self.assertIn("does not sit on the XAUUSD chain", str(cm.exception))

    def test_an_anchor_never_joins_a_torn_line_and_a_committed_non_record_refuses_by_its_commit(self):
        d, _seal = canary_root()
        git(d, "init", "-q")
        p = os.path.join(d, WF.ANCHORS)
        WF.cmd_anchor(d)
        good = open(p, "rb").read()
        self.assertTrue(good.endswith(b"\n") and len(WF.anchor_lines(good, "x")) == 1)
        for bad, why in ((good + good[:40], "ends with an unterminated line"),     # a killed `anchor`: never glued onto
                         (good + b'{"at":"x"}\n', "is not an anchor record")):     # a terminated non-record
            with open(p, "wb") as fh:
                fh.write(bad)
            with self.assertRaises(SystemExit) as cm:
                WF.cmd_anchor(d)
            self.assertIn(why, str(cm.exception))
            self.assertEqual(open(p, "rb").read(), bad)                            # nothing appended
        with open(p, "wb") as fh:                                                  # what the old `anchor` wrote after
            fh.write(good.rstrip(b"\n") + good)                                    # a lost newline: one glued line
        git(d, "add", WF.ANCHORS)
        git(d, "commit", "-q", "-m", "a glued anchor line")
        sha = git(d, "rev-parse", "HEAD")
        with self.assertRaises(SystemExit) as cm:                                  # git keeps it: every read refuses,
            WF.committed_anchors(d)                                                # by its commit, never a crash
        self.assertIn(f"line 1 (commit {sha[:12]}) is not an anchor record", str(cm.exception))


# ------------------------------------------------------------------------------------------------ cycle (§4, §6)
class Cycle(unittest.TestCase):
    def test_one_cycle_logs_each_event_and_its_resolve_and_a_second_adds_nothing(self):
        d, seal = canary_root()
        log, _ = WF.read_chain(WF._rt(d, "log.jsonl"))
        self.assertEqual(sorted(r["kind"] for r in log), ["event"] * 10 + ["resolve"] * 10)
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
        self.assertEqual(set(fp["exec"]), need | {                          # 17 files, 15 of the sealed re-test's 52:
            "scripts/research/edge_census.py", "scripts/history_store.py", "scripts/instruments.py",
            "scripts/mt5_time.py", "scripts/normalized.py", "scripts/providers.py", "scripts/broker_symbols.py",
            "scripts/live_rules.py",                                        # the HTF gate's bias reader (WY-F1 §6) and,
            "scripts/ict-scan.py", "scripts/structures.py", "scripts/htf_context.py", "scripts/i18n.py"})   # what it
        self.assertEqual(len(fp["exec"]), 17)                               # runs on a FULL 1H window (the canary does)
        self.assertNotIn("docs/architecture/automation-config.json", fp["data"])     # HTF_METHODS is pinned
        self.assertLess(len(fp["exec"]), len(E.CODE) // 2)                 # vs the sealed re-test's 52 files
        self.assertNotIn("docs/architecture/instruments.json", fp["exec"])
        self.assertIn(WF.R0, fp["data"])
        self.assertTrue(all(WF._wanted(p) for s in ("exec", "load", "data") for p in fp[s]))
        self.assertEqual(set(fp["price_ref"]), set(WF.SYMBOLS))
        self.assertEqual((fp["canary"]["events"], fp["canary"]["rows"]), (len(WF.SYMBOLS), {"1": 10, "2": 10}))
        self.assertEqual(set(fp["canary"]["htf_gate"]), {"True", "False"} & set(fp["canary"]["htf_gate"]))
        self.assertNotIn("None", fp["canary"]["htf_gate"])                    # the gate judged: never "unknown"
        self.assertEqual(fp["digest"], WF.fp_digest(fp))
        self.assertEqual(fp["tz"], WF.tz_pin())                               # the DST instants as computed at the seal
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

    def test_a_patch_upgrade_passes_the_worker_check_and_a_minor_change_refuses(self):
        major, minor, micro = sys.version_info[:3]
        fp = {"interpreter": {"command": f"/x/python{major}.{minor}", "version": f"{major}.{minor}.{micro}",
                              "minor": f"{major}.{minor}"}}
        with mock.patch.object(WF.sys, "version_info", (major, minor, micro + 1, "final", 0)):
            WF.require_interpreter(fp)                                           # e.g. 3.14.5 -> 3.14.6: collects
        with mock.patch.object(WF.sys, "version_info", (major, minor + 1, 0, "final", 0)), \
                self.assertRaises(SystemExit) as cm:
            WF.require_interpreter(fp)                                           # 3.14 -> 3.15: refuses
        self.assertIn(f"runs Python {major}.{minor + 1}", str(cm.exception))
        self.assertIn(f"pins {major}.{minor}", str(cm.exception))

    def test_the_pin_names_a_stable_versioned_interpreter(self):
        self.assertIsNone(WF.stable_interpreter("/opt/homebrew/opt/python@3.14/bin/python3.14", "3.14.5", "3.14"))
        for bad, why in (("/opt/homebrew/Cellar/python@3.14/3.14.5/Frameworks/Python.framework/Versions/3.14/bin/"
                          "python3.14", "names the patch release 3.14.5"),      # deleted by brew's next patch upgrade
                         ("/Users/u/.pyenv/versions/3.14.5/bin/python3.14", "names the patch release 3.14.5"),
                         ("/opt/homebrew/Cellar/python@3.14/current/bin/python3.14", "Homebrew's Cellar"),
                         ("/opt/homebrew/bin/python3", "is not named python3.14"),  # follows the default minor
                         ("python3.14", "is not an absolute path")):
            self.assertIn(why, WF.stable_interpreter(bad, "3.14.5", "3.14") or "", bad)
        pin = WF.interpreter_pin(require_stable=False)
        self.assertEqual((pin["command"], pin["version"], pin["minor"]),
                         (sys.executable, WF.platform.python_version(), "%d.%d" % sys.version_info[:2]))
        root = tempfile.mkdtemp(prefix="wyf1-pin-")          # a code root without a fingerprint: never skipped, also
        canonical = os.path.join(root, WF.FINGERPRINT)       # after the seal commits the real one

        def nope(*_a, **_k):
            raise AssertionError("cmd_fingerprint traced the canary before it checked the interpreter")
        major, minor, micro = sys.version_info[:3]
        other = shim_python(tempfile.mkdtemp(prefix="wyf1-shim-"), f"{major}.{minor}.{micro + 1}")
        for exe, why in ((f"/opt/homebrew/Cellar/python@{major}.{minor}/{major}.{minor}.{micro}/bin/"
                          f"python{major}.{minor}", "names the patch release"),
                         (other, f"runs Python {major}.{minor}.{micro + 1}, this process runs")):
            with mock.patch.object(WF, "CODE_ROOT", root), mock.patch.object(WF.sys, "executable", exe), \
                    mock.patch.object(WF, "Tracer", nope), self.assertRaises(SystemExit) as cm:
                WF.cmd_fingerprint(canonical)                                    # the sealing run refuses first
            self.assertIn(why, str(cm.exception))
            self.assertFalse(os.path.exists(canonical))

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

    def test_a_fingerprint_whose_time_zone_pin_differs_cannot_run(self):
        """A worker refuses when the system computes other DST instants than the fingerprint pinned (WY-F1 §5)."""
        fp = json.loads(json.dumps(self.fp))
        fp["tz"][WF.TZ_PIN_ZONE][0]["utc"] = "2025-03-16T07:00:00Z"
        with self.assertRaises(SystemExit) as cm:
            WF.extract_check(fp, self.clone, self.rev)
        self.assertIn("time zone", str(cm.exception))
        self.assertIn("computes other DST instants", str(cm.exception))

    def test_a_patch_upgrade_keeps_collecting_and_a_minor_change_refuses_loudly(self):
        """The pinned command, after a patch upgrade, runs every forward step to the sealed canary digest; after a minor
        change it refuses. Shim interpreters present this Python as the next patch and the next minor release."""
        major, minor, micro = sys.version_info[:3]
        tmp = tempfile.mkdtemp(prefix="wyf1-shim-")
        fp = json.loads(json.dumps(self.fp))
        fp["interpreter"]["command"] = shim_python(os.path.join(tmp, "patch"), f"{major}.{minor}.{micro + 1}")
        self.assertGreater(WF.extract_check(fp, self.clone, self.rev), 400)
        fp["interpreter"]["command"] = shim_python(os.path.join(tmp, "minor"), f"{major}.{minor + 1}.0")
        with self.assertRaises(SystemExit) as cm:
            WF.extract_check(fp, self.clone, self.rev)
        self.assertIn(f"this worker runs Python {major}.{minor + 1}", str(cm.exception))
        self.assertIn(f"pins {major}.{minor}", str(cm.exception))


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
            WF.cmd_read(os.path.join(root, WF.LOOK_OUT[1]), 1, data_root=root)

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

    def test_a_minor_python_change_fails_every_cycle_loudly(self):
        """A sealed repository whose pinned command now runs the next minor Python: the worker refuses, the cycle is a
        recorded FAILURE, the next spawn puts it in the cycle log, and status flags the interpreter."""
        major, minor, micro = sys.version_info[:3]
        root = tempfile.mkdtemp()
        git(root, "init", "-q")
        wf = os.path.join(root, WF.SCRIPT)
        os.makedirs(os.path.dirname(wf))
        shutil.copyfile(os.path.join(ROOT, WF.SCRIPT), wf)
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "code")
        nxt = shim_python(tempfile.mkdtemp(prefix="wyf1-shim-"), f"{major}.{minor + 1}.0")
        WF._write_json(os.path.join(root, WF.FINGERPRINT),
                       {"exec": {WF.SCRIPT: WF._sha256(wf)}, "load": {}, "data": {}, "canary_sha256": "c",
                        "interpreter": {"command": nxt, "version": f"{major}.{minor}.{micro}",
                                        "minor": f"{major}.{minor}"}})
        os.makedirs(os.path.join(root, os.path.dirname(WF.PREREG)), exist_ok=True)
        with open(os.path.join(root, WF.PREREG), "w") as fh:
            fh.write("sealed")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "seal")
        want = f"pins {major}.{minor}"
        with self.assertRaises(SystemExit) as cm:
            WF.cmd_cycle(data_root=root)
        self.assertIn("worker failed", str(cm.exception))
        self.assertIn(want, str(cm.exception))
        last = json.load(open(WF._rt(root, "last_cycle.json")))
        self.assertEqual((last["ok"], want in last["error"]), (False, True))

        class P:
            pid = 4242
        with self.assertRaises(SystemExit) as cm:                         # the next spawn: an EXIT line in the cycle log
            WF.cmd_spawn(root, popen=lambda cmd, **kw: P())
        self.assertIn("the previous cycle FAILED", str(cm.exception))
        self.assertIn(want, str(cm.exception))
        st = WF.status(root)
        self.assertEqual((st["interpreter"]["now"], st["interpreter"]["ok"]), (f"{major}.{minor + 1}.0", False))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            WF._print_status(st)
        self.assertIn("NOT the pinned minor version", buf.getvalue())

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


# ------------------------------------------------------------------------------------------------ canary helpers
def canary_t(j, jitter=0):
    """The canary's bar-open label j (WF.CANARY_START + 15 minutes x j)."""
    return WF._iso(WF._utc(WF.CANARY_START) + datetime.timedelta(minutes=15 * j, seconds=jitter))


def hist_path(d, sym):
    return os.path.join(d, WF.HIST_DIR, f"ohlcv.{sym}.15m.json")


def edit_history(d, sym, fn):
    """Edit one symbol's history export (the file shape of `canary_data`): fn(candles dict list, doc)."""
    p = hist_path(d, sym)
    doc = json.load(open(p))
    fn(doc["candles"], doc)
    WF._write_json(p, doc)


def canary_events(d):
    log, _ = WF.read_chain(WF._rt(d, "log.jsonl"))
    return {r["symbol"]: r for r in log if r["kind"] == "event"}


def fresh_canary(doctor=None):
    """A canary data root after one full cycle, built here (not copied), with `doctor(root)` applied to the files the
    STORES are built from -- what a doctored bridge would have fed them."""
    d = tempfile.mkdtemp(prefix="wyf1-fresh-")
    seal = WF.canary_data(d)
    if doctor:
        doctor(d)
    res = WF.cycle_core(d, seal, "fp", "2026-07-01T00:00:00Z", init_root=d)
    WF.commit(res["writes"])
    return d, seal


def synthetic_rows(n=24, weeks=12):
    """Fixed scored-row stand-ins with `weeks` ISO weeks: enough clusters for the Student-t tail."""
    rows = []
    for i in range(n):
        r, plc = ((i * 7) % 13 - 5) / 4.0, ((i * 5) % 7 - 3) / 10.0
        rows.append({"id": f"e{i}", "week": f"2027-W{10 + i * weeks // n:02d}", "R": r, "placebo": plc,
                     "excess": r - plc, "cost": {"median_swap": 0.03, "median_noswap": 0.02, "p90_swap": 0.05,
                                                 "p90_noswap": 0.04}})
    return rows


def ulp_up(f):
    """A libm-like perturbation: the value one ulp up (a probability stays below 1 where it is not 1)."""
    return lambda *a, **k: math.nextafter(f(*a, **k), math.inf)


# ------------------------------------------------------------------------------------------------ numbers (WY-F1 §5)
class Numbers(unittest.TestCase):
    """Item 1 of the 2026-10-04 review: no look may depend on a last-ulp value of the OS math library. Rows, counts and
    labels are hashed exactly (no OS math function computes them); a derived float enters a hash or a comparison rounded
    to 10 significant digits."""

    def test_sig10_rounds_to_ten_significant_digits_with_pythons_own_formatting(self):
        self.assertEqual(WF.sig10(1.234567890123), 1.23456789)
        self.assertEqual(WF.sig10(-0.000123456789012), -0.000123456789)
        self.assertEqual(WF.sig10(123456789012.0), 123456789000.0)
        self.assertEqual((WF.sig10(0.0), WF.sig10(7), WF.sig10("x")), (0.0, 7, "x"))
        self.assertIsNone(WF.sig10(None))
        self.assertIs(WF.sig10(True), True)
        self.assertTrue(math.isinf(WF.sig10(math.inf)))
        x = 0.123456789012345
        self.assertEqual(WF.sig10(WF.sig10(x)), WF.sig10(x))                              # idempotent
        self.assertEqual(WF.rounded({"a": [1.5, {"b": 2.123456789012}], "n": 3}),
                         {"a": [1.5, {"b": 2.123456789}], "n": 3})

    def test_one_ulp_on_a_derived_float_never_changes_what_a_commitment_verifies(self):
        rnd = random.Random(20261004)
        for _ in range(3000):
            x = rnd.choice((1e-9, 1e-4, 1.0, 12.0, 3e5)) * rnd.uniform(0.1, 9.99)
            for y in (math.nextafter(x, math.inf), math.nextafter(x, -math.inf)):
                self.assertIn(WF.split_sha256({"rows": [1.5]}, {"p": x}), WF.split_digests({"rows": [1.5]}, {"p": y}))

    def test_a_float_on_a_rounding_midpoint_verifies_under_either_rounding(self):
        x = 1.0000000005                        # the 10-digit midpoint between 1.000000000 and 1.000000001
        up, down = math.nextafter(x, math.inf), math.nextafter(x, -math.inf)
        self.assertEqual({WF.sig10(x), WF.sig10(up), WF.sig10(down)}, {1.0, 1.000000001})   # one ulp flips the rounding
        digests = {w: WF.split_sha256({}, {"p": w}) for w in (x, up, down)}
        self.assertEqual(len(set(digests.values())), 2)
        for w in (x, up, down):                                                              # ... and both are accepted
            self.assertEqual(WF.split_digests({}, {"p": w}), set(digests.values()))
        self.assertEqual(len(WF.tie_variants({"p": x})), 2)
        self.assertEqual(len(WF.tie_variants({"p": 0.5, "q": 1.0})), 1)
        with self.assertRaises(SystemExit):                                                  # the cap: never silent
            WF.tie_variants({f"p{i}": x for i in range(WF.TIE_CAP + 1)})

    def test_a_changed_row_never_verifies_and_a_real_change_of_a_derived_float_does_not_either(self):
        rows, summary = [{"id": "a", "R": 1.25, "excess": 0.5}], {"p": 0.01, "upper_95": 0.7}
        sha = WF.statistic_sha256({"rows": rows, "summary": summary})
        self.assertTrue(WF.statistic_verifies({"rows": rows, "summary": summary}, sha))
        for k in ("R", "excess"):                                       # one ulp of a ROW value: refused (exact part)
            moved = [dict(rows[0], **{k: math.nextafter(rows[0][k], math.inf)})]
            self.assertFalse(WF.statistic_verifies({"rows": moved, "summary": summary}, sha), k)
        self.assertFalse(WF.statistic_verifies({"rows": rows + rows, "summary": summary}, sha))     # a row more
        self.assertFalse(WF.statistic_verifies({"rows": [dict(rows[0], id="b")], "summary": summary}, sha))
        for k in summary:                                                # an ulp of a derived float: verified
            nudged = dict(summary, **{k: math.nextafter(summary[k], math.inf)})
            self.assertTrue(WF.statistic_verifies({"rows": rows, "summary": nudged}, sha), k)
            real = dict(summary, **{k: summary[k] * (1 + 1e-6)})         # a real change: refused
            self.assertFalse(WF.statistic_verifies({"rows": rows, "summary": real}, sha), k)

    def test_the_registered_p_value_under_an_ulp_different_student_t_still_verifies(self):
        """edge_census.t_sf and t_quantile use lgamma, exp and log (the OS library): a statistic computed with a tail
        one ulp off commits to the same sha256 as the real one (WF.statistic_verifies)."""
        rows = synthetic_rows()
        real = {"rows": rows, "summary": E.summarise(rows, E.FTMO_LINES)}
        self.assertEqual(real["summary"]["weeks"], 12)
        t_sf = E.EC.t_sf
        with mock.patch.object(E.EC, "t_sf", ulp_up(t_sf)):
            nudged = {"rows": rows, "summary": E.summarise(rows, E.FTMO_LINES)}
        self.assertNotEqual(real["summary"]["p_one_sided"], nudged["summary"]["p_one_sided"])   # the ulp is there
        self.assertTrue(WF.statistic_verifies(real, WF.statistic_sha256(nudged)))
        self.assertTrue(WF.statistic_verifies(nudged, WF.statistic_sha256(real)))
        with mock.patch.object(E.EC, "t_sf", lambda t, df: t_sf(t, df) * (1 + 1e-6)):           # a real change
            moved = {"rows": rows, "summary": E.summarise(rows, E.FTMO_LINES)}
        self.assertFalse(WF.statistic_verifies(real, WF.statistic_sha256(moved)))

    def test_the_pass_test_compares_rounded_floats_and_look_ones_boundary_with_isclose(self):
        thr, base = 0.0044, {"n": 5, "net_excess": 0.4}
        self.assertFalse(WF.crossed(dict(base, p_one_sided=thr * (1 - 1e-13)), {"p_threshold": thr}))   # equal at 10 digits
        self.assertTrue(WF.crossed(dict(base, p_one_sided=thr * (1 - 1e-6)), {"p_threshold": thr}))
        self.assertFalse(WF.crossed(dict(base, net_excess=0.0, p_one_sided=0.0001), {"p_threshold": thr}))
        b = WF.look1_boundary(14)
        near = dict(b, z=math.nextafter(b["z"], math.inf), p_threshold=b["p_threshold"] * (1 + 1e-12),
                    alpha_spent=math.nextafter(b["alpha_spent"], 0.0))
        self.assertTrue(WF.boundary_matches(b, near))
        self.assertFalse(WF.boundary_matches(b, dict(b, z=b["z"] * (1 + 1e-6))))
        self.assertFalse(WF.boundary_matches(b, dict(b, n=15)))
        self.assertFalse(WF.boundary_matches(b, None))
        empty = WF.look1_boundary(0)
        self.assertTrue(WF.boundary_matches(empty, dict(empty)))
        self.assertFalse(WF.boundary_matches(empty, dict(empty, z=1.0)))
        self.assertEqual(WF.BOUNDARY_REL_TOL, 1e-9)

    def test_a_look_two_verifies_a_look_one_made_under_an_ulp_different_math_library(self):
        d, seal = canary_root()
        meta = {"study": WF.STUDY, "seal": seal, "fingerprint_digest": "fp"}
        cdf = WF.norm_cdf
        with mock.patch.object(WF, "norm_cdf", ulp_up(cdf)):                                # look 1, an ulp-off library
            one = read(d, seal)
        plain = read(d, seal)
        self.assertNotEqual(one["boundary"]["alpha_spent"], plain["boundary"]["alpha_spent"])    # the ulp is there
        self.assertTrue(WF.boundary_matches(plain["boundary"], one["boundary"]))
        rec = json.loads(json.dumps(WF.blind(dict(one, meta=meta)), default=str))
        two = read(d, seal, look=2, prior=WF.require_prior(rec, seal, "fp"))                 # look 2, the real one
        self.assertEqual(two["look1"]["statistic_sha256"], rec["statistic_sha256"])
        self.assertIn(two["verdict"]["label"], ("PASS", "NOT PASSED"))
        self.assertEqual(two["look1"]["boundary"], rec["boundary"])           # look 2 uses look 1's COMMITTED boundary
        # a row perturbed by one ulp refuses: look 1 committed to rows whose `excess` differs from the recomputation
        real = E.score

        def drift(*a, **k):
            r, why = real(*a, **k)
            return (dict(r, excess=math.nextafter(r["excess"], math.inf)), why) if r else (r, why)
        bad = json.loads(json.dumps(WF.blind(dict(read(d, seal, score_fn=drift), meta=meta)), default=str))
        with self.assertRaises(SystemExit) as cm:
            read(d, seal, look=2, prior=bad)
        self.assertIn("does not reproduce its committed sha256", str(cm.exception))

    def test_the_canary_digest_survives_an_ulp_and_refuses_a_real_numeric_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            digest, _looks, body = WF.canary(tmp)
        fp = {"canary_sha256": digest}
        self.assertTrue(WF.canary_verifies(fp, body))
        self.assertEqual(body["derived"]["numerics"]["summary"]["weeks"], 12)   # the fixed probe has a Student-t tail
        t_sf, cdf = E.EC.t_sf, WF.norm_cdf
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(E.EC, "t_sf", ulp_up(t_sf)), \
                mock.patch.object(WF, "norm_cdf", ulp_up(cdf)):
            nudged_digest, _l, nudged = WF.canary(tmp)
        self.assertTrue(WF.canary_verifies(fp, nudged))                        # a last-ulp library: every look still runs
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(E.EC, "t_sf", lambda t, df: t_sf(t, df) * 1.001):
            _d, _l, moved = WF.canary(tmp)
        self.assertFalse(WF.canary_verifies(fp, moved))                        # a real change: refused
        exact = json.loads(json.dumps(body))
        exact["exact"]["log"][0]["atr"] = math.nextafter(exact["exact"]["log"][0]["atr"], math.inf)
        self.assertFalse(WF.canary_verifies(fp, exact))                        # the exact part is exact


# ------------------------------------------------------------------------------------------------ revisions (WY-F1 §4)
class Revisions(unittest.TestCase):
    """Item 2: a bar the broker revises after the store took it is logged (chained), the store keeps its bar as first
    stored, decisions and resolves use it, and every look reports the revisions."""

    def single(self):
        """One symbol (XAUUSD): history to bar 480, a live file bars 420-544 -> store 0..543, the Spring event at 492
        logged and resolved from the entry bar 493 as first stored."""
        d = tempfile.mkdtemp(prefix="wyf1-rev-")
        bars = mk_bars(spring_tuples())
        write_history(d, "XAUUSD", bars[:480])
        write_live(d, "XAUUSD", bars[420:545])
        seal = {"sha": "s", "instant": t_at(450)}
        return d, bars, seal

    def cycle(self, d, seal, now):
        res = WF.cycle_core(d, seal, "fp", now, init_root=d, symbols=("XAUUSD",))
        WF.commit(res["writes"])
        return res["summary"]

    def test_a_revised_bar_is_logged_once_per_price_the_store_keeps_it_and_resolves_stay_point_in_time(self):
        d, bars, seal = self.single()
        s1 = self.cycle(d, seal, "2026-06-20T00:00:00Z")
        self.assertEqual((s1["new_events"], s1["revisions"]), (1, 0))
        log, _ = WF.read_chain(WF._rt(d, "log.jsonl"))
        (ev,) = [r for r in log if r["kind"] == "event"]
        (rs,) = [r for r in log if r["kind"] == "resolve"]
        e = ev["store_index"] + 1
        self.assertEqual((e, rs["entry_time"]), (493, t_at(493)))
        stored, _h = WF.read_chain(WF._rt(d, "bars", "XAUUSD.15m.jsonl"))
        self.assertEqual(len(stored), 544)
        # The broker revises the ENTRY bar's open (and later its high); every later live file shows it.
        for upto, o_add, h_add, n_rev in ((560, 0.5, 0.0, 1), (580, 0.5, 0.0, 0), (588, 0.7, 0.2, 1)):
            live = [dict(b, o=b["o"] + o_add, h=b["h"] + h_add) if b["t"] == t_at(493) else b for b in bars[480:upto]]
            write_live(d, "XAUUSD", live)
            s = self.cycle(d, seal, "2026-06-21T00:00:00Z")
            self.assertEqual(s["revisions"], n_rev, (upto, s))              # once per distinct revised price
        log, heads = WF.read_chain(WF._rt(d, "log.jsonl"))
        revs = [r for r in log if r["kind"] == "revision"]
        self.assertEqual(len(revs), 2)                                          # chained records, in the log's chain
        r0 = revs[0]
        self.assertEqual((r0["symbol"], r0["t"], r0["src"], r0["fields"]), ("XAUUSD", t_at(493), "live", ["o"]))
        self.assertEqual((r0["store"]["o"], r0["source"]["o"]), (bars[493]["o"], bars[493]["o"] + 0.5))
        self.assertEqual((r0["seal"], r0["fingerprint"]), (seal["sha"], "fp"))
        self.assertEqual(revs[1]["fields"], ["o", "h"])
        again, _ = WF.read_chain(WF._rt(d, "bars", "XAUUSD.15m.jsonl"))
        self.assertEqual(len(again), 587)                                       # the store advanced past the revision
        self.assertEqual(again[493]["o"], bars[493]["o"])                       # and kept the bar as first stored
        self.assertEqual(again[:544], stored)
        # Point in time: the resolve the log holds equals a recomputation from the store; the REVISED bar would give
        # another entry and another R (so this proves something).
        S = WF.series_of("XAUUSD", again)
        redo = WF.resolve_record(S, ev, seal, "fp", rs["resolved_at"])
        self.assertEqual({k: v for k, v in redo.items() if k not in WF.RESOLVE_STAMPS},
                         {k: v for k, v in rs.items() if k not in WF.RESOLVE_STAMPS})
        moved = [dict(b, o=b["o"] + 0.5) if b["t"] == t_at(493) else b for b in again]
        other = WF.resolve_record(WF.series_of("XAUUSD", moved), ev, seal, "fp", "x")
        self.assertNotEqual((other["entry"], other["R"]), (rs["entry"], rs["R"]))
        # And the chain still verifies end to end (an edited revision record would break it).
        self.assertEqual(len(heads), len(log))

    def test_the_old_wedge_a_revised_bar_among_the_last_four_does_not_stop_the_store(self):
        d, bars, seal = self.single()
        self.cycle(d, seal, "2026-06-20T00:00:00Z")
        live = [dict(b, h=b["h"] + 0.25) if b["t"] == t_at(541) else b for b in bars[480:600]]   # bar 541: in the last 4
        write_live(d, "XAUUSD", live)
        s = self.cycle(d, seal, "2026-06-21T00:00:00Z")
        stored, _h = WF.read_chain(WF._rt(d, "bars", "XAUUSD.15m.jsonl"))
        self.assertEqual((s["added_bars"]["XAUUSD"], len(stored), s["revisions"], s["not_advancing"]),
                         (55, 599, 1, {}))                                       # the old rule appended nothing, forever
        self.assertEqual(stored[541]["h"], bars[541]["h"])

    def test_every_look_reports_the_revision_records(self):
        d, seal = canary_root()
        events = canary_events(d)
        ev = events["XAGUSD"]
        bars, heads = WF.read_chain(WF._rt(d, "bars", "XAGUSD.15m.jsonl"))
        inside = bars[ev["store_index"] - 250]                        # a bar of the event's 300-bar window, far from
        #                                                               its structure and from ATR20: a harmless one
        outside = bars[len(bars) - 20]                                # a bar far after every span
        recs = [WF.revision_record("XAGUSD", b, dict(b, h=b["h"] + 0.01), "live", seal, "fp", "2026-06-29T00:00:00Z")
                for b in (inside, outside)]
        log, lheads = WF.read_chain(WF._rt(d, "log.jsonl"))
        WF.append_chain(WF._rt(d, "log.jsonl"), recs, lheads[-1])
        out = read(d, seal)
        rv = out["revisions"]
        self.assertEqual((rv["records"], rv["per_symbol"]), (2, {"XAGUSD": 2}))
        self.assertEqual([(x["symbol"], x["t"], x["fields"], x["in_a_sampled_span"]) for x in rv["list"]],
                         [("XAGUSD", inside["t"], ["h"], True), ("XAGUSD", outside["t"], ["h"], False)])
        self.assertIn("point in time", rv["note"])
        # the look's bar-by-bar check says which differences a logged revision explains (the export is the truth here,
        # so no difference exists in this file; the flag is set where one does)
        self.assertEqual(out["history_check"]["XAGUSD"]["revised_differences"], 0)
        edit_history(d, "XAGUSD", lambda cs, doc: [c.update(high=c["high"] + 0.01) for c in cs
                                                   if c["time"] == inside["t"]])
        out = read(d, seal)
        diffs = out["history_check"]["XAGUSD"]["differences"]
        self.assertEqual([(x["t"], x["kind"], x["fields"], x["revised"], x["spans"]) for x in diffs],
                         [(inside["t"], "price", ["h"], True, [ev["id"]])])
        # a blinded look 1 reports them too
        self.assertEqual(WF.blind(dict(out, meta={}))["revisions"]["records"], 2)


# ------------------------------------------------------------------------------------------------ NOT ADVANCING (§4)
class NotAdvancing(unittest.TestCase):
    """Item 4: a store that does not advance while its live file exists, and a stale live file, are flagged -- in the
    cycle summary and in `status` -- with plan_append's reason and the store's last bar."""

    def setUp(self):
        self.d, self.seal = canary_root()
        self.n = len(WF.canary_bars(0))
        self.now = canary_t(self.n + 4)

    def status(self, now=None):
        with mock.patch.object(WF, "seal_info", lambda root=None: dict(self.seal, date="x")), \
                mock.patch.object(WF, "committed_anchors", lambda root: []):
            return WF.status(self.d, now=now or self.now)

    def printed(self, st):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            WF._print_status(st)
        return buf.getvalue()

    def test_a_healthy_store_is_not_flagged_and_a_missing_file_is_stalled_not_advancing(self):
        st = self.status()
        self.assertEqual((st["not_advancing"], st["stalled"]), ({}, []))
        self.assertNotIn("NOT ADVANCING", self.printed(st))
        os.remove(os.path.join(self.d, WF.LIVE_DIR, "ohlcv.JP225.cash.15m.json"))
        st = self.status()
        self.assertEqual((st["stalled"], st["not_advancing"]), (["JP225"], {}))        # listed as STALLED, not twice

    def test_a_hole_before_the_live_file_is_flagged_with_the_reason_and_the_stores_last_bar(self):
        bars, _h = WF.read_chain(WF._rt(self.d, "bars", "DE40.15m.jsonl"))
        rewrite_chain(WF._rt(self.d, "bars", "DE40.15m.jsonl"), bars[:2400])         # the store ends at bar 2399
        live = os.path.join(self.d, WF.LIVE_DIR, "ohlcv.GER40.cash.15m.json")
        doc = json.load(open(live))
        WF._write_json(live, dict(doc, candles=[c for c in doc["candles"] if c["time"] >= canary_t(2500)]))
        res = WF.cycle_core(self.d, self.seal, "fp", self.now, init_root=self.d)
        why = res["summary"]["not_advancing"]
        self.assertEqual(list(why), ["DE40"])
        self.assertIn("hole: the store ends " + canary_t(2399), why["DE40"])
        self.assertIn("the store's last bar is " + canary_t(2399), why["DE40"])
        self.assertEqual((res["summary"]["added_bars"]["DE40"], res["summary"]["stalled"]), (0, []))
        st = self.status()
        self.assertEqual(list(st["not_advancing"]), ["DE40"])
        self.assertEqual((st["symbols"]["DE40"]["next_cycle_adds"], st["symbols"]["DE40"]["stalled"]), (0, False))
        self.assertIn("NOT ADVANCING DE40: " + why["DE40"], self.printed(st))
        # ... and the export that bridges it is taken in: the history file reaches past the store's end
        WF._write_json(live, doc)
        res = WF.cycle_core(self.d, self.seal, "fp", self.now, init_root=self.d)
        WF.commit(res["writes"])
        self.assertEqual((res["summary"]["not_advancing"], res["summary"]["added_bars"]["DE40"] > 0), ({}, True))

    def test_a_stale_live_file_is_flagged_only_when_older_than_the_threshold(self):
        live = os.path.join(self.d, WF.LIVE_DIR, "ohlcv.XAUUSD.15m.json")
        doc = json.load(open(live))
        WF._write_json(live, dict(doc, candles=[c for c in doc["candles"] if c["time"] < canary_t(2450)]))
        last = canary_t(2448)                                                         # its newest CLOSED bar
        quiet = self.status(now=canary_t(2449 + 4 * 8))                               # about 8 hours later: a quiet market
        self.assertEqual(quiet["not_advancing"], {})
        late = self.status(now=canary_t(2449 + 4 * 80))                               # 80 hours later: stale
        self.assertEqual(list(late["not_advancing"]), ["XAUUSD"])
        self.assertIn("the live 15m file is stale: its newest closed bar " + last, late["not_advancing"]["XAUUSD"])
        self.assertIn("the store's last bar is " + canary_t(self.n - 2), late["not_advancing"]["XAUUSD"])
        self.assertIn("NOT ADVANCING XAUUSD", self.printed(late))
        res = WF.cycle_core(self.d, self.seal, "fp", canary_t(2449 + 4 * 80), init_root=self.d)
        self.assertEqual(list(res["summary"]["not_advancing"]), ["XAUUSD"])

    def test_a_feed_that_advances_the_store_is_not_flagged_even_when_stale(self):
        """The store took bars this cycle (from the history export), so it is advancing: no flag."""
        live = os.path.join(self.d, WF.LIVE_DIR, "ohlcv.XAGUSD.15m.json")
        doc = json.load(open(live))
        WF._write_json(live, dict(doc, candles=[c for c in doc["candles"] if c["time"] < canary_t(2250)]))
        bars, _h = WF.read_chain(WF._rt(self.d, "bars", "XAGUSD.15m.jsonl"))
        rewrite_chain(WF._rt(self.d, "bars", "XAGUSD.15m.jsonl"), bars[:2200])          # behind the history export's end
        res = WF.cycle_core(self.d, self.seal, "fp", canary_t(2700), init_root=self.d)    # the others' files are fresh
        self.assertEqual(res["summary"]["not_advancing"], {})
        self.assertGreater(res["summary"]["added_bars"]["XAGUSD"], 0)


# ------------------------------------------------------------------------------------------------ canary gate (§5, §6)
class CanaryGate(unittest.TestCase):
    """Item 5: the canary runs the ICT HTF gate on a real-length window, so the fingerprint, the canary digest and
    `extract_check` cover the gate's whole bias path."""

    def test_every_canary_signal_has_a_full_live_1h_window_and_the_gate_judges(self):
        d, _seal = canary_root()
        log, _ = WF.read_chain(WF._rt(d, "log.jsonl"))
        need = BT.lr.scan_spec("1H")[0]
        self.assertEqual(need, 480)                                          # automation.SCAN_WINDOW["1H"]
        events = [r for r in log if r["kind"] == "event"]
        self.assertEqual(len(events), len(WF.SYMBOLS))
        for r in events:
            bars, _h = WF.read_chain(WF._rt(d, "bars", f"{r['symbol']}.15m.jsonl"))
            S = WF.series_of(r["symbol"], bars)
            c = WF.htf_candles(S, r["store_index"], 60)
            self.assertGreaterEqual(len(c), need, r["symbol"])
            self.assertIsNotNone(BT.lr.read_at(c, len(c) - 1, "1H", WF.HTF_METHODS), r["symbol"])   # not "unknown"
            self.assertIn(WF.htf_gate(S, r["store_index"]), ((True, None), (False, None)))
        resolves = [r for r in log if r["kind"] == "resolve"]
        self.assertTrue(resolves and all(r["htf_gate"] in (True, False) and r["htf_gate_error"] is None
                                         for r in resolves))

    def test_the_gate_files_run_in_the_canary_so_the_fingerprint_names_them_as_executed(self):
        if sealed_here():
            self.skipTest("WY-F1 is sealed: its fingerprint is the committed one")
        fp = working_fingerprint()
        for f in ("scripts/ict-scan.py", "scripts/structures.py", "scripts/htf_context.py", "scripts/i18n.py"):
            self.assertIn(f, fp["exec"])
            self.assertNotIn(f, fp["load"])
        self.assertEqual(sum(fp["canary"]["htf_gate"].values()), len(WF.SYMBOLS))


# ------------------------------------------------------------------------------------------------ blinded look 1 (§7)
class BlindRecord(unittest.TestCase):
    def test_a_blinded_look_one_gives_no_resolve_count_and_no_estimate(self):
        """Item 7: `blind` keeps an allowlist. The log's record count (records - events = the resolves, which `status`
        hides on purpose), the anchored log length, the repair list and the log-only recomputation are dropped."""
        d, seal = canary_root()
        one = read(d, seal)
        self.assertGreater(one["log"]["records"], one["replay"]["logged"])         # the full result gives it away
        rec = json.loads(json.dumps(WF.blind(dict(one, meta={"study": WF.STUDY, "seal": seal,
                                                               "fingerprint_digest": "fp"})), default=str))
        self.assertEqual(rec["log"], {"head": one["log"]["head"]})                  # ... the blinded one does not
        self.assertEqual(set(rec["anchors"]), {"verified", "last_committed", "note"})
        self.assertEqual(set(rec["repairs"]), {"records", "files", "note"})
        text = json.dumps(rec)
        for leak in ("log_only_check", "log_records_anchored", "kept_records", "mismatches", '"statistic"', "net_excess",
                     "p_one_sided", "upper_95", '"R"', "mean_R"):
            self.assertNotIn(leak, text)
        self.assertEqual(set(rec) - set(WF.BLIND_KEEP) - {"blinded"}, set())          # only the allowlist
        self.assertTrue({"statistic", "log_only_check"} <= set(one) - set(rec))
        self.assertEqual(rec["statistic_sha256"], one["statistic_sha256"])
        self.assertEqual(rec["verdict"]["n"], one["verdict"]["n"])                    # the decision facts stay
        for key in ("history_check", "revisions", "exports", "attempts", "late_logged", "boundary"):
            self.assertIn(key, rec)                                                    # and what a reader audits with
        for h in rec["history_check"].values():
            self.assertEqual(h["walks"]["differ"], 0)                                  # counts of walks, never an R
            self.assertNotIn("R", h["walks"])


# ------------------------------------------------------------------------------------------------ time zone (§5)
class TimeZonePin(unittest.TestCase):
    """Item 8: the fingerprint pins the DST instants of America/New_York for 2025-2030 as computed at the seal (and the
    FTMO server zone built on them); every cycle and look refuses when the running system computes others."""

    def test_the_pin_is_the_dst_instants_not_file_bytes(self):
        pin = WF.tz_pin()
        ny = pin[WF.TZ_PIN_ZONE]
        self.assertEqual(pin["years"], [2025, 2030])
        self.assertEqual(len(ny), 12)                                                  # two a year, six years
        self.assertIn({"utc": "2026-03-08T07:00:00Z", "before": -18000, "after": -14400}, ny)
        self.assertIn({"utc": "2026-11-01T06:00:00Z", "before": -14400, "after": -18000}, ny)
        server = pin["ftmo_server"]                                                    # the same instants, EET-sized steps
        self.assertEqual([x["utc"] for x in server], [x["utc"] for x in ny])
        self.assertEqual({(x["before"], x["after"]) for x in server}, {(7200, 10800), (10800, 7200)})
        json.dumps(pin)                                                                # plain JSON: ints and strings
        self.assertEqual(WF.tz_pin(), pin)

    def test_a_system_that_computes_other_instants_refuses(self):
        pin = WF.tz_pin()
        WF.require_tz({"tz": pin})
        moved = json.loads(json.dumps(pin))
        moved[WF.TZ_PIN_ZONE][2]["utc"] = "2026-03-15T07:00:00Z"                       # the US rule moved a transition
        with self.assertRaises(SystemExit) as cm:
            WF.require_tz({"tz": moved})
        self.assertIn(WF.TZ_PIN_ZONE, str(cm.exception))
        self.assertIn("2026-03-08T07:00:00Z", str(cm.exception))
        short = json.loads(json.dumps(pin))
        del short["ftmo_server"][-1]
        with self.assertRaises(SystemExit) as cm:
            WF.require_tz({"tz": short})
        self.assertIn("ftmo_server", str(cm.exception))
        for none in ({}, {"tz": {}}, {"tz": None}):
            with self.assertRaises(SystemExit) as cm:
                WF.require_tz(none)
            self.assertIn("pins no time-zone behaviour", str(cm.exception))
        # behaviour, not bytes: a zone database that never moves the clock gives other instants whatever its files say
        import zoneinfo
        flat = lambda name: datetime.timezone(datetime.timedelta(hours=-5))            # noqa: E731
        with mock.patch.object(zoneinfo, "ZoneInfo", flat), self.assertRaises(SystemExit) as cm:
            WF.require_tz({"tz": pin})
        self.assertIn(WF.TZ_PIN_ZONE, str(cm.exception))

    def test_the_pin_is_part_of_the_fingerprints_identity(self):
        pin = WF.tz_pin()
        fp = {"exec": {}, "load": {}, "data": {}, "canary_sha256": "c", "tz": pin}
        moved = json.loads(json.dumps(fp))
        moved["tz"][WF.TZ_PIN_ZONE][0]["utc"] = "2025-03-16T07:00:00Z"
        self.assertNotEqual(WF.fp_digest(fp), WF.fp_digest(moved))
        self.assertEqual(WF.fp_digest(fp), WF.fp_digest(json.loads(json.dumps(fp))))


# ------------------------------------------------------------------------------------------------ the look's export (§7, §8)
class LookExport(unittest.TestCase):
    """Items 3 and 11: every look needs a history export of ALL 10 symbols taken after its window; a stalled symbol the
    export fills is read, its events late-logged and disclosed; the owner's case end to end on synthetic bars."""

    HOLE = ("US500", "US30", "USTEC", "DE40")

    def test_every_look_needs_an_export_of_all_ten_symbols_taken_after_the_window_and_into_the_stores(self):
        d, seal = canary_root()
        out = read(d, seal)
        self.assertEqual(out["export_required_at"], canary_t(2100 + 1 + 96))            # the close of cutoff bar + 96
        self.assertEqual({s: m["exported_at_utc"] for s, m in out["exports"].items()},
                         {s: canary_t(WF.CANARY_HIST_END) for s in WF.SYMBOLS})
        self.assertTrue(all(len(m["files"]) == 1 for m in out["exports"].values()))
        # one symbol never exported: no look (nobody can leave a symbol out by not exporting it)
        p = hist_path(d, "JP225")
        os.rename(p, p + ".bak")
        with self.assertRaises(SystemExit) as cm:
            read(d, seal)
        self.assertIn("needs a FTMO 15m history export of all 10 symbols", str(cm.exception))
        self.assertIn("JP225: no 15m history export", str(cm.exception))
        os.rename(p + ".bak", p)
        # an export taken before the window's last bar closed
        edit_history(d, "XAGUSD", lambda cs, doc: doc.update(_exported_at_utc=canary_t(2150)))
        with self.assertRaises(SystemExit) as cm:
            read(d, seal)
        self.assertIn("XAGUSD: its export was taken at " + canary_t(2150), str(cm.exception))
        edit_history(d, "XAGUSD", lambda cs, doc: doc.update(_exported_at_utc=canary_t(WF.CANARY_HIST_END)))
        # an export the store has not taken in yet: one `cycle` first
        bars, _h = WF.read_chain(WF._rt(d, "bars", "XAGUSD.15m.jsonl"))
        rewrite_chain(WF._rt(d, "bars", "XAGUSD.15m.jsonl"), bars[:2290])
        with self.assertRaises(SystemExit) as cm:
            read(d, seal)
        self.assertIn("XAGUSD: the export still extends its store by 9 bar(s) after " + canary_t(2289), str(cm.exception))
        self.assertIn("run one `cycle` first", str(cm.exception))
        res = WF.cycle_core(d, seal, "fp", "2026-07-02T00:00:00Z", init_root=d)
        WF.commit(res["writes"])
        self.assertEqual(read(d, seal)["sample"], 10)

    def test_a_stalled_symbol_is_filled_by_the_looks_export_and_read_with_its_events_late(self):
        """JP225 has no live file (STALLED today) and a sealed history that ends just after the seal. Its store does not
        advance, so look 1 is not due. The look's export of all symbols reaches past the cutoff: the next cycle takes
        it in, JP225 is then complete, READ (not dropped), and its event is late-logged and disclosed."""
        d = tempfile.mkdtemp(prefix="wyf1-fill-")
        seal = WF.canary_data(d)
        full = json.load(open(hist_path(d, "JP225")))
        WF._write_json(hist_path(d, "JP225"), dict(full, candles=full["candles"][:WF.CANARY_SEAL_BAR + 10],
                                                   _exported_at_utc=canary_t(WF.CANARY_SEAL_BAR + 10)))
        os.remove(os.path.join(d, WF.LIVE_DIR, "ohlcv.JP225.cash.15m.json"))
        res = WF.cycle_core(d, seal, "fp", "2026-07-01T00:00:00Z", init_root=d)
        WF.commit(res["writes"])
        self.assertEqual(res["summary"]["stalled"], ["JP225"])
        self.assertEqual(res["summary"]["new_events"], 9)                                # JP225's event is not there yet
        with self.assertRaises(SystemExit) as cm:
            read(d, seal)
        self.assertIn("look 1 is not due", str(cm.exception))                            # a stalled symbol is never complete
        WF._write_json(hist_path(d, "JP225"), full)                                      # the look's export of JP225
        res = WF.cycle_core(d, seal, "fp", "2026-07-10T00:00:00Z", init_root=d)
        WF.commit(res["writes"])
        self.assertEqual((res["summary"]["stalled"], res["summary"]["new_events"]), (["JP225"], 1))   # the feed is down
        self.assertGreater(res["summary"]["added_bars"]["JP225"], 200)                  # ... and the export fills it
        out = read(d, seal)
        self.assertEqual((out["symbols_read"], out["symbols_dropped"]), (list(WF.SYMBOLS), []))
        self.assertEqual(out["sample"], 10)
        late = canary_events(d)["JP225"]
        self.assertEqual(late["logged_at"], "2026-07-10T00:00:00Z")
        self.assertIn(late["id"], out["late_logged"]["ids"])
        self.assertEqual(out["history_check"]["JP225"]["replay"]["ok"], True)

    def test_the_owners_case_a_seal_on_history_that_ends_before_the_live_files_then_a_later_export_bridges_it(self):
        """The coordinator's case (2026-10-04) on synthetic bars: US500, US30, USTEC and DE40 have a sealed history that
        ends BEFORE the seal and a live file that starts later (a hole). Cycles report it (NOT ADVANCING) and log nothing
        for them. Days later a re-exported history reaches past the look's window: the next cycle bridges it, their
        post-seal events are logged LATE, and both looks read them with the lag disclosed (late-logged count and ids,
        the lag's median and maximum, the events whose window holds history-sourced bars)."""
        d = tempfile.mkdtemp(prefix="wyf1-owner-")
        seal = WF.canary_data(d)                              # phase A: what the seal commit and the live files hold
        for sym in WF.SYMBOLS:
            doc = json.load(open(hist_path(d, sym)))
            cut = 2000 if sym in self.HOLE else 2101
            WF._write_json(hist_path(d, sym), dict(doc, candles=doc["candles"][:cut], _exported_at_utc=canary_t(cut)))
            if sym not in self.HOLE:
                os.remove(os.path.join(d, WF.LIVE_DIR, f"ohlcv.{BS.to_broker(sym)}.15m.json"))
        a = WF.cycle_core(d, seal, "fp", canary_t(2101), init_root=d)
        WF.commit(a["writes"])
        self.assertEqual(sorted(a["summary"]["not_advancing"]), sorted(self.HOLE))     # the hole: flagged, with the reason
        for sym in self.HOLE:
            self.assertIn("hole: the store ends " + canary_t(1998), a["summary"]["not_advancing"][sym])
        self.assertEqual(sorted(a["summary"]["stalled"]), sorted(set(WF.SYMBOLS) - set(self.HOLE)))
        self.assertEqual(a["summary"]["new_events"], 6)                                 # the six logged theirs ON TIME
        self.assertEqual(set(canary_events(d)), set(WF.SYMBOLS) - set(self.HOLE))
        WF.canary_data(d)                                    # phase B: the re-exported history (to bar 2300) is imported
        b = WF.cycle_core(d, seal, "fp", canary_t(2520), init_root=d)
        WF.commit(b["writes"])
        self.assertEqual(b["summary"]["not_advancing"], {})
        self.assertEqual(b["summary"]["new_events"], 4)                                 # the four bridged: events logged LATE
        self.assertEqual(set(canary_events(d)), set(WF.SYMBOLS))
        out = read(d, seal)
        late = sorted(canary_events(d)[s]["id"] for s in self.HOLE)
        self.assertEqual(out["late_logged"]["ids"], late)
        self.assertEqual(out["late_logged"]["events"], 4)
        self.assertEqual(out["sample"], 10)                                              # the late events are READ
        self.assertEqual(out["symbols_dropped"], [])
        lag = out["log_lag_seconds"]
        self.assertLess(lag["median"], WF.LATE_LOG_S)                                    # six on time ...
        self.assertGreater(lag["max"], 100 * 3600)                                       # ... four about 106 hours late
        self.assertGreaterEqual(out["events_with_post_seal_history_bars"], 4)
        self.assertTrue(all(h["replay"]["ok"] and h["walks"]["differ"] == 0 for h in out["history_check"].values()))
        meta = {"study": WF.STUDY, "seal": seal, "fingerprint_digest": "fp"}
        rec = json.loads(json.dumps(WF.blind(dict(out, meta=meta)), default=str))
        self.assertEqual(rec["late_logged"]["ids"], late)                                # a blinded look 1 discloses them
        two = read(d, seal, look=2, prior=WF.require_prior(rec, seal, "fp"))
        self.assertEqual((two["late_logged"]["events"], two["look1"]["statistic_sha256"]),
                         (4, rec["statistic_sha256"]))                                   # and look 2 reproduces look 1


# ------------------------------------------------------------------------------------------------ export replay (§8)
class ExportCheck(unittest.TestCase):
    """Item 10: the history check replays the detector on the export and requires the logged events; a difference inside
    an event span is tolerated only when it changes no decision field and no trade; every difference is reported."""

    def setUp(self):
        self.d, self.seal = canary_root()
        self.ev = canary_events(self.d)["XAGUSD"]
        self.k = self.ev["store_index"]                                  # the spring bar is the signal bar (2092)

    def edit(self, fn, d=None):
        edit_history(d or self.d, "XAGUSD", lambda cs, doc: fn({c["time"]: c for c in cs}))

    def test_a_harmless_difference_inside_an_events_span_is_reported_and_not_invalid(self):
        sig, far = canary_t(self.k), canary_t(self.k - 250)
        self.edit(lambda m: (m[sig].update(close=m[sig]["close"] + 0.01), m[far].update(high=m[far]["high"] + 0.0001)))
        out = read(self.d, self.seal)
        h = out["history_check"]["XAGUSD"]
        self.assertEqual([(x["t"], x["kind"], x["fields"], x["spans"], x["revised"]) for x in h["differences"]],
                         [(far, "price", ["h"], [self.ev["id"]], False), (sig, "price", ["c"], [self.ev["id"]], False)])
        self.assertEqual((h["span_differences"], h["revised_differences"]), (2, 0))
        self.assertEqual((h["replay"]["ok"], h["replay"]["only_in_export"], h["replay"]["only_in_log"],
                          h["replay"]["changed"], h["walks"]["differ"]), (True, [], [], [], 0))
        self.assertEqual((out["sample"], out["verdict"]["label"]), (10, "CONTINUE"))     # not INVALID: the look runs
        self.assertIsNone(WF.history_problem(h))

    def test_a_difference_in_a_bar_the_store_or_the_export_lacks_is_reported_by_kind(self):
        gone = canary_t(self.k - 40)
        d, seal = canary_root()
        edit_history(d, "XAGUSD", lambda cs, doc: cs.__setitem__(slice(None), [c for c in cs if c["time"] != gone]))
        bars, _h = WF.read_chain(WF._rt(d, "bars", "XAGUSD.15m.jsonl"))
        S = WF.series_of("XAGUSD", bars)
        h = WF.history_check("XAGUSD", bars, S, WF._utc(seal["instant"]), WF.canary_plan(seal)[0][0], 96, d,
                             [(self.ev["id"], self.k - 299, self.k + 97)])
        self.assertEqual([(x["t"], x["kind"], x["spans"]) for x in h["differences"]],
                         [(gone, "export_lacks", [self.ev["id"]])])
        self.assertLess(h["coverage"], 1.0)

    def test_a_difference_that_changes_a_decision_makes_the_look_invalid(self):
        spring = canary_t(self.k)
        self.edit(lambda m: m[spring].update(low=m[spring]["low"] - 0.5))                  # spring_low and the stop move
        with self.assertRaises(SystemExit) as cm:
            read(self.d, self.seal)
        self.assertIn("the detector replayed on the export does not give the logged events", str(cm.exception))
        self.assertIn(self.ev["id"], str(cm.exception))
        self.assertIn("a bar difference suppressed, created or changed an event", str(cm.exception))

    def test_an_export_that_suppresses_an_event_is_caught(self):
        spring = canary_t(self.k)
        self.edit(lambda m: m[spring].update(low=min(m[spring]["open"], m[spring]["close"])))      # no spring any more
        with self.assertRaises(SystemExit) as cm:
            read(self.d, self.seal)
        self.assertIn("only in the log", str(cm.exception))
        self.assertIn(self.ev["id"], str(cm.exception))

    def test_a_store_that_suppressed_an_event_is_caught_by_the_export(self):
        """The review's case: bars doctored BEFORE they entered the store hide an event, so the log has none and no span
        exists. One bar differs from the true export, which the old check (agreement >= 0.99, spans of logged events
        only) passed. The detector replayed on the export finds the event the log lacks."""
        spring = canary_t(self.k)

        def hide(root):
            self.edit(lambda m: m[spring].update(low=min(m[spring]["open"], m[spring]["close"])), d=root)
        d, seal = fresh_canary(hide)
        self.assertNotIn("XAGUSD", canary_events(d))                                        # the doctored store: no event
        WF.canary_data(d)                                                                   # the later export is the truth
        bars, _h = WF.read_chain(WF._rt(d, "bars", "XAGUSD.15m.jsonl"))
        h = WF.history_check("XAGUSD", bars, WF.series_of("XAGUSD", bars), WF._utc(seal["instant"]),
                             WF.canary_plan(seal)[0][0], 96, d, ())
        self.assertGreaterEqual(h["agreement"], WF.HIST_AGREE_MIN)                          # the old rule's tests pass
        self.assertEqual((h["span_differences"], len(h["differences"])), (0, 1))
        self.assertIsNone(WF.history_problem(h))
        with self.assertRaises(SystemExit) as cm:
            read(d, seal)
        self.assertIn("only in the export", str(cm.exception))
        self.assertIn("XAGUSD|15m|", str(cm.exception))

    def test_a_difference_that_changes_a_trade_makes_the_look_invalid_after_its_attempt(self):
        """The exit bar of the event's trade lies after the look's cutoff, so no decision can change -- only the walk
        does. That is an OUTCOME comparison, so it runs after the look-attempt record: the look is spent."""
        log, _ = WF.read_chain(WF._rt(self.d, "log.jsonl"))
        (rs,) = [r for r in log if r["kind"] == "resolve" and r["symbol"] == "XAGUSD"]
        exit_t = rs["exit_time"]
        self.assertGreater(WF._utc(exit_t), WF.canary_plan(self.seal)[0][0])
        self.edit(lambda m: m[exit_t].update(open=100.0, high=100.0, low=100.0, close=100.0))     # the target is not hit
        done = []
        with self.assertRaises(SystemExit) as cm:
            read(self.d, self.seal, attempt=lambda info: done.append(WF.append_attempt(
                self.d, self.seal, "fp", 1, WF.LOOK_OUT[1], info, "2026-07-02T00:00:00Z")))
        self.assertIn("walked on the history export differs from the store's (XAGUSD: 1 trade(s))", str(cm.exception))
        self.assertEqual(len(done), 1)                                  # the attempt was recorded before the comparison
        with self.assertRaises(SystemExit) as cm:
            WF.require_no_attempt(self.d, 1)
        self.assertIn("already attempted", str(cm.exception))


# ------------------------------------------------------------------------------------------------ look attempts (§7)
class LookAttempts(unittest.TestCase):
    """Item 9: a chained look-attempt record is appended before the first outcome is computed; a second attempt of the
    same look refuses even when the first one's output file is gone."""

    def hook(self, d, seal, look=1, flag=None):
        def attempt(info):
            if flag is not None:
                flag["done"] = True
            return WF.append_attempt(d, seal, "fp", look, WF.LOOK_OUT[look], info, "2026-07-02T00:00:00Z")
        return attempt

    def test_the_attempt_comes_before_any_outcome_and_a_second_attempt_refuses_though_no_file_exists(self):
        d, seal = canary_root()
        flag = {"done": False}

        def guard(real):
            def wrapped(*a, **k):
                if not flag["done"]:
                    raise AssertionError("an outcome was computed before the look-attempt record")
                return real(*a, **k)
            return wrapped
        with mock.patch.object(E, "walk_from", guard(E.walk_from)), mock.patch.object(E, "score", guard(E.score)), \
                mock.patch.object(E, "Pricer", guard(E.Pricer)):
            out = read(d, seal, attempt=self.hook(d, seal, 1, flag))
        self.assertTrue(flag["done"])
        log, heads = WF.read_chain(WF._rt(d, "log.jsonl"))
        (att,) = WF.look_attempts(log)
        self.assertEqual((att["kind"], att["look"], att["out"], att["seal"], att["fingerprint"]),
                         ("look_attempt", 1, WF.LOOK_OUT[1], seal["sha"], "fp"))
        self.assertEqual((att["symbols_read"], att["symbols_dropped"], att["cutoff"]),
                         (list(WF.SYMBOLS), [], out["cutoff"]["cutoff"]))
        self.assertEqual(att["exports"], {s: canary_t(WF.CANARY_HIST_END) for s in WF.SYMBOLS})
        self.assertEqual(out["attempt"]["ch"], heads[-1])                  # chained: the log's last record
        self.assertFalse(os.path.exists(os.path.join(d, WF.LOOK_OUT[1])))  # no output file was ever written ...
        for call in (lambda: WF.require_no_attempt(d, 1),
                     lambda: WF.append_attempt(d, seal, "fp", 1, WF.LOOK_OUT[1], {}, "t")):
            with self.assertRaises(SystemExit) as cm:
                call()                                                     # ... and the look still refuses
            self.assertIn("already attempted", str(cm.exception))
        WF.require_no_attempt(d, 2)                                       # look 2 is not blocked by look 1's attempt
        WF.append_attempt(d, seal, "fp", 2, WF.LOOK_OUT[2], {"cutoff": "x"}, "t")
        with self.assertRaises(SystemExit):
            WF.require_no_attempt(d, 1)                                    # a later look ran: look 1 can never run
        with self.assertRaises(SystemExit):
            WF.require_no_attempt(d, 2)
        # a cycle and the next look still read the log (the attempt records are part of its chain and stamps)
        res = WF.cycle_core(d, seal, "fp", "2026-07-03T00:00:00Z", init_root=d)
        self.assertEqual(res["summary"]["new_events"], 0)

    def test_a_look_that_refuses_after_its_attempt_never_runs_again_and_status_says_so(self):
        d, seal = canary_root()
        real = E.score

        def drift(*a, **k):
            r, why = real(*a, **k)
            return (dict(r, R=r["R"] + 1e-6), why) if r else (r, why)
        with self.assertRaises(SystemExit) as cm:
            read(d, seal, score_fn=drift, attempt=self.hook(d, seal))
        self.assertIn("disagree with their logged resolve", str(cm.exception))
        with self.assertRaises(SystemExit) as cm:
            WF.require_no_attempt(d, 1)
        self.assertIn("already attempted", str(cm.exception))
        with mock.patch.object(WF, "seal_info", lambda root=None: dict(seal, date="x")), \
                mock.patch.object(WF, "committed_anchors", lambda root: []):
            st = WF.status(d, now=canary_t(len(WF.canary_bars(0)) + 4))
        self.assertEqual((st["rule"]["spent_without_record"], st["rule"]["read_due"]), (["1"], False))
        self.assertIn("1", st["rule"]["attempted"])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            WF._print_status(st)
        self.assertIn("look 1 was attempted without a record on disk: it never runs again", buf.getvalue())

    def test_a_look_that_refuses_before_its_checks_pass_leaves_no_attempt_and_may_run_later(self):
        d, seal = canary_root()
        edit_history(d, "XAGUSD", lambda cs, doc: doc.update(_exported_at_utc=canary_t(2150)))      # an early export
        with self.assertRaises(SystemExit):
            read(d, seal, attempt=self.hook(d, seal))
        self.assertEqual(WF.look_attempts(WF.read_chain(WF._rt(d, "log.jsonl"))[0]), [])
        edit_history(d, "XAGUSD", lambda cs, doc: doc.update(_exported_at_utc=canary_t(WF.CANARY_HIST_END)))
        out = read(d, seal, attempt=self.hook(d, seal))                                               # the right one
        self.assertEqual(out["sample"], 10)
        self.assertEqual(len(WF.look_attempts(WF.read_chain(WF._rt(d, "log.jsonl"))[0])), 1)


# ------------------------------------------------------------------------------------------------ the type-I error (§7, §11)
class TypeOneError(unittest.TestCase):
    """Item 6: the boundaries are exact for normal z statistics (`TwoLooks`); the REGISTERED statistic (CR1 by ISO week,
    a Student-t p applied as a nominal threshold) is not exactly alpha under same-week clustering, heavy tails or left
    skew. A reduced version of the review's simulation, and the draft's disclosure of its numbers."""

    @staticmethod
    def value(rnd, dist):
        if dist == "normal":
            return rnd.gauss(0.0, 2.2)
        if dist == "left":                      # R:R 0.5: win 0.5 w.p. 2/3, lose 1 w.p. 1/3 -- mean 0, left-skewed
            return 0.5 if rnd.random() < 2 / 3 else -1.0
        raise ValueError(dist)

    @staticmethod
    def p_one(vals, weeks):
        mu, se, df = E.EC.cr1(vals, weeks)
        return mu, (1.0 if not se else E.EC.t_sf(mu / se, df))

    def rate(self, reps, seed, dist, burst_p, rho):
        """Share of null runs that PASS at either look: 14 events a year for three years (Poisson), `burst_p` of them in
        same-week bursts of 2-4 whose values share a common draw with probability `rho`; the production boundaries and
        pass test (`look1_boundary`, `look2_boundary`, `crossed`), the production CR1 / Student-t p."""
        rnd, hits, cache = random.Random(seed), 0, {}
        for _ in range(reps):
            ev = []                                                         # (ISO week, value, in look 1)
            for t0, t1 in ((0.0, 52.0), (52.0, 156.0)):
                lam = 14 * (t1 - t0) / 52.0
                for _i in range(poisson(rnd, lam * (1 - burst_p))):
                    w = rnd.uniform(t0, t1)
                    ev.append((int(w), self.value(rnd, dist), w < 52.0))
                for _i in range(poisson(rnd, lam * burst_p / 3.0)):
                    w, common = rnd.uniform(t0, t1), self.value(rnd, dist)
                    for _j in range(rnd.choice((2, 3, 4))):
                        ev.append((int(w), common if rnd.random() < rho else self.value(rnd, dist), w < 52.0))
            e1 = [(w, v) for w, v, first in ev if first]
            n1, n2 = len(e1), len(ev)
            b1 = WF.look1_boundary(n1)
            if n1:
                mu, p = self.p_one([v for _w, v in e1], [w for w, _v in e1])
                if WF.crossed({"n": n1, "net_excess": mu, "p_one_sided": p}, b1):
                    hits += 1
                    continue
            if (n1, n2) not in cache:
                cache[(n1, n2)] = WF.look2_boundary(b1, n2, n1)
            if n2:
                mu, p = self.p_one([v for _w, v, _f in ev], [w for w, _v, _f in ev])
                hits += WF.crossed({"n": n2, "net_excess": mu, "p_one_sided": p}, cache[(n1, n2)])
        return hits / reps

    def test_the_registered_statistic_is_near_alpha_on_iid_normal_values_and_above_it_under_clustering_and_left_skew(self):
        reps = 4000
        normal = self.rate(reps, 20261004, "normal", 0.0, 0.0)
        self.assertLess(abs(normal - WF.ALPHA), 0.017, normal)                           # the review: 0.1025
        clustered = self.rate(reps, 20261004, "normal", 0.4, 0.6)
        self.assertGreater(clustered, 0.10, clustered)                                   # the review: 0.111
        left = self.rate(reps, 20261004, "left", 0.0, 0.0)
        self.assertGreater(left, 0.105, left)                                            # the review: 0.122
        left_clustered = self.rate(reps, 20261004, "left", 0.4, 0.6)
        self.assertGreater(left_clustered, 0.115, left_clustered)                        # the review: 0.136

    def test_the_draft_discloses_the_simulated_inflation_and_no_longer_claims_exactly_alpha(self):
        path = os.path.join(ROOT, WF.PREREG_DRAFT)
        if not os.path.exists(path):
            self.skipTest("the draft was retired after the seal; the sealed file carries the text")
        text = open(path, encoding="utf-8").read()
        for number in ("0.1025", "0.111", "0.113", "0.122", "0.136", "0.077", "0.074", "0.008"):
            self.assertIn(number, text, number)                                          # the review's simulated rates
        for stale in ("So the false-pass probability over both looks is exactly 0.10 for any n1 and n2",
                      "a fluke reaches about 1 time in 230",
                      "Simulated: 0.100-0.101 on normal values, conservative on skewed R values"):
            self.assertNotIn(stale, text, stale)
        for word in ("same-week", "heavy tails", "left-skewed"):
            self.assertIn(word, text, word)


if __name__ == "__main__":
    unittest.main()
