"""Byte-identity + timing harness for the W7 (`fx_w7_htf_target`) backtest path, run on a slice of one series.
Research tooling only (docs/audits/2026-10-01-w7-speed.md): changes no engine logic, reads no R / expectancy.

  BT_HISTORY_ROOT=<root>/data/history/ftmo python3 scripts/research/w7_equiv.py N [--start S] [--sym XAUUSD] [--tf 1m]
                                                                      [--overlay fixed|w7only|none]

Runs scan_many(workers=1) with ONE overlay (the path `BtEngine.prefetch` runs per worker chunk) over bars [S, S+N) of the
PIT-truncated (`pit_cutoff("2024-03-01T00:00:00Z")`) LTF series; the higher-timeframe series is NOT truncated, as in the
real run. Prints ONE json line: seconds, trade count, sha256 of `json.dumps(trades, sort_keys=True)`, and the log of every
`_htf_wyckoff_target(sym, tf, side, decision_time)` call the scan made -- count, non-None count, and a sha256 over the
ordered (decision_time, side, result) triples, so two code versions are compared on the W7 answers themselves and not only
on the (few) trades they end up in. Run it in a BASE tree and in the working tree and diff the lines.

  --overlay fixed  : fund-search.fixed_opts() (flat_before_rollover + ADOPTED_F_KEYS, W7 included), as fund-search runs it
  --overlay w7only : {"fx_w7_htf_target": True}
  --overlay none   : {}  (no W7: control)"""
import argparse
import hashlib
import importlib.util
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCR = os.path.dirname(HERE)
sys.path.insert(0, SCR)
ap = argparse.ArgumentParser()
ap.add_argument("n", type=int)
ap.add_argument("--start", type=int, default=0)
ap.add_argument("--sym", default="XAUUSD")
ap.add_argument("--tf", default="1m")
ap.add_argument("--overlay", default="fixed", choices=("fixed", "w7only", "none"))
ap.add_argument("--method", default="WYCKOFF-BOOK")
a = ap.parse_args()
import scan_many as SM  # noqa: E402

spec = importlib.util.spec_from_file_location("bt", os.path.join(SCR, "backtest-methods.py"))
bt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bt)
bt.pit_cutoff("2024-03-01T00:00:00Z")
real_load = bt.load


def load(s, t):
    c, src = real_load(s, t)
    return (c[a.start:a.start + a.n] if (s, t) == (a.sym, a.tf) else c), src


bt.load = load
if a.overlay == "fixed":
    fs = importlib.util.spec_from_file_location("fs", os.path.join(SCR, "fund-search.py"))
    F = importlib.util.module_from_spec(fs)
    fs.loader.exec_module(F)
    overlay = F.fixed_opts()
elif a.overlay == "w7only":
    overlay = {"fx_w7_htf_target": True}
else:
    overlay = {}

calls = []
_orig = bt._htf_wyckoff_target
htf_secs = [0.0]


def _logged(sym, tf, side, decision_time):
    t = time.time()
    r = _orig(sym, tf, side, decision_time)
    htf_secs[0] += time.time() - t
    calls.append((decision_time, side, r))
    return r


bt._htf_wyckoff_target = _logged
bt.load(a.sym, a.tf)          # warm the load cache so the timing below is the scan only
t0 = time.time()
res = SM.scan_many(bt, a.sym, a.tf, a.method, [overlay], workers=1)
dt = time.time() - t0
tr = res[0]["trades"][a.method]
out = dict(method=a.method, sym=a.sym, tf=a.tf, start=a.start, n=a.n, overlay=a.overlay, secs=round(dt, 2),
           s_per_bar=round(dt / a.n, 6), htf_secs=round(htf_secs[0], 2), trades=len(tr),
           trades_sha256=hashlib.sha256(json.dumps(tr, sort_keys=True, default=str).encode()).hexdigest(),
           htf_calls=len(calls), htf_non_none=sum(1 for x in calls if x[2] is not None),
           htf_distinct_decisions=len({(x[0], x[1]) for x in calls}),
           htf_memo_entries=len(getattr(bt, "_HTF_TR_CACHE", ())),     # new code: distinct (series, side, prefix length) answers
           htf_calls_sha256=hashlib.sha256(json.dumps(calls, default=repr).encode()).hexdigest())
print(json.dumps(out), flush=True)
