"""Scaling / cProfile harness for the backtest Wyckoff (and ICT) scan on the FIRST N bars of a PIT-truncated series.
Profiling only: changes no engine logic. Usage:
  BT_HISTORY_ROOT=data/history/ftmo python3 scripts/research/profile_wyckoff_1m.py METHOD N [--fixed] [--cprofile] [--sym XAUUSD] [--tf 1m] [--hash]
--fixed : overlay = fund-search fixed_opts() (flat_before_rollover + ADOPTED_F_KEYS), as the fund-search BtEngine runs it.
Default path: scan_many(workers=1) with one overlay (what prefetch runs per worker chunk) over bars 0..N.
--serial-scan : bt.scan instead."""
import argparse
import cProfile
import hashlib
import importlib.util
import json
import os
import pstats
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCR = os.path.dirname(HERE)
sys.path.insert(0, SCR)
ap = argparse.ArgumentParser()
ap.add_argument("method")
ap.add_argument("n", type=int)
ap.add_argument("--fixed", action="store_true")
ap.add_argument("--cprofile", action="store_true")
ap.add_argument("--sym", default="XAUUSD")
ap.add_argument("--tf", default="1m")
ap.add_argument("--hash", action="store_true")
ap.add_argument("--keys", default="", help="comma list of fx_/OPTS keys to set True (single-key ablation)")
ap.add_argument("--prof-out", default="")
ap.add_argument("--no-w7", action="store_true", help="with --fixed: drop fx_w7_htf_target from the overlay")
ap.add_argument("--time-htf", action="store_true", help="record every _htf_wyckoff_target call (secs, HTF prefix bars)")
ap.add_argument("--serial-scan", action="store_true")
a = ap.parse_args()
import scan_many as SM  # noqa: E402

spec = importlib.util.spec_from_file_location("bt", os.path.join(SCR, "backtest-methods.py"))
bt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bt)
bt.pit_cutoff("2024-03-01T00:00:00Z")
real_load = bt.load


def load(s, t):
    c, src = real_load(s, t)
    return (c[:a.n] if (s, t) == (a.sym, a.tf) else c), src


bt.load = load
overlay = {}
if a.fixed:
    fs = importlib.util.spec_from_file_location("fs", os.path.join(SCR, "fund-search.py"))
    F = importlib.util.module_from_spec(fs)
    fs.loader.exec_module(F)
    overlay = F.fixed_opts()


if a.no_w7:
    overlay.pop("fx_w7_htf_target", None)
htf_log = []
if a.time_htf:
    _orig = bt._htf_wyckoff_target

    def _timed(sym, tf, side, decision_time):
        t = time.time()
        r = _orig(sym, tf, side, decision_time)
        htf_log.append((decision_time, round(time.time() - t, 2)))
        return r
    bt._htf_wyckoff_target = _timed
for k in [x for x in a.keys.split(",") if x]:
    overlay[k] = True


def run():
    if a.serial_scan:
        return [bt.scan(a.sym, a.tf, only=(a.method,), opts=overlay)]
    return SM.scan_many(bt, a.sym, a.tf, a.method, [overlay], workers=1)


tl = time.time()
bt.load(a.sym, a.tf)          # warm the load cache so the timing below is the scan only
load_secs = time.time() - tl
t0 = time.time()
if a.cprofile:
    pr = cProfile.Profile()
    res = pr.runcall(run)
else:
    res = run()
dt = time.time() - t0
tr = res[0]["trades"][a.method]
out = dict(method=a.method, n=a.n, fixed=a.fixed, load_secs=round(load_secs, 1), secs=round(dt, 2), s_per_bar=dt / a.n, trades=len(tr))
if a.hash:
    out["sha256"] = hashlib.sha256(json.dumps(tr, sort_keys=True, default=str).encode()).hexdigest()
if htf_log:
    out["htf_calls"] = len(htf_log)
    out["htf_secs"] = round(sum(x[1] for x in htf_log), 1)
    out["htf_first_last"] = [htf_log[0], htf_log[-1]]
print(json.dumps(out), flush=True)
if a.cprofile:
    if a.prof_out:
        pr.dump_stats(a.prof_out)
    st = pstats.Stats(pr)
    st.sort_stats("cumulative").print_stats(25)
    st.sort_stats("tottime").print_stats(25)
