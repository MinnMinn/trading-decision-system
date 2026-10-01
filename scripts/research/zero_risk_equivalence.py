#!/usr/bin/env python3
"""BEFORE-vs-AFTER trade-list equivalence for the planned-risk admission rule (docs/audits/2026-10-01-zero-risk.md).

Run the SAME file from two code trees (BEFORE = a `git archive` of the parent commit, AFTER = the checkout with the
rule): it builds the fund-search harness engine (`BtEngine`, real scan + real simulate + real FTMO costs) on a slice of
one (symbol, timeframe) series and prints, per value set, the number of ADMITTED trades and the sha256 of the canonical
JSON of the whole admitted trade list. No R / expectancy / performance figure is read or printed.

  * unaffected slice (no zero-risk candidate): BEFORE sha == AFTER sha is the proof that the rule changes no trade that
    has a valid stop distance.
  * affected slice: BEFORE aborts (`CostRefused: stop distance is zero`). `--drop-zero-risk` wraps `bt.scan` in the
    BEFORE tree to drop the candidates whose entry == stop (what the AFTER rule refuses), the only way the old code can run
    there; AFTER on the unmodified path must then give the same sha, and its `zero_risk` count must equal the number
    dropped.

    python3 scripts/research/zero_risk_equivalence.py job '{"method":"ict","symbol":"XAUUSD","tf":"1m","last_bars":20000,
        "sets":["baseline","B-EX=fill"]}' [--drop-zero-risk]
    python3 scripts/research/zero_risk_equivalence.py job '{"method":"ict","symbol":"US500","tf":"1m",
        "start":"2023-03-01T00:00:00Z","end":"2023-03-15T00:00:00Z","sets":["B-EX=fill"]}' [--drop-zero-risk]
Needs BT_HISTORY_ROOT=<data/history/ftmo>. Output: ONE JSON line on stdout.
"""
import bisect
import datetime
import hashlib
import importlib.util
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
os.environ.setdefault("BT_HISTORY_ROOT", os.path.join(ROOT, "data", "history", "ftmo"))
WARMUP_DAYS = 14
FORWARD_DAYS = 5


def _fs():
    spec = importlib.util.spec_from_file_location("fund_search", os.path.join(ROOT, "scripts", "fund-search.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fund_search"] = mod
    spec.loader.exec_module(mod)
    return mod


def _shift(iso, days):
    d = datetime.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")
    return (d + datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def named_sets(grid):
    """{label: values}: 'baseline', then 'ITEM=value' for every non-baseline value, and 'B-EX=fill+ITEM=value'."""
    base = grid.baseline()
    out = {"baseline": dict(base)}
    for it in grid.items:
        for v in it["values"][1:]:
            out[f"{it['id']}={v}"] = dict(base, **{it["id"]: v})
    if "B-EX" in grid.by_id:
        for it in grid.items:
            if it["id"] != "B-EX":
                for v in it["values"][1:]:
                    out[f"B-EX=fill+{it['id']}={v}"] = dict(base, **{"B-EX": "fill", it["id"]: v})
    return out


def run_job(job, drop_zero_risk):
    fs = _fs()
    method, sym, tf = job["method"], job["symbol"], job["tf"]
    grids, _ = fs.load_grids()
    grid = grids[method].runnable()
    runner = fs.METHODS[method]
    bt = fs._load_bt()
    real_load = bt.load
    start, end, last_bars = job.get("start"), job.get("end"), job.get("last_bars")

    def sliced(s, t):
        c, src = real_load(s, t)
        if (s, t) != (sym, tf) or not c:
            return c, src
        if last_bars:
            return c[-last_bars:], src
        times = [x["time"] for x in c]
        spec_bars = bt.lr.scan_spec(tf)[0] if method == "ict" else bt._wy_window(sym, tf, len(c))
        i0 = max(bisect.bisect_left(times, _shift(start, -WARMUP_DAYS)) - spec_bars, 0)
        i1 = max(bisect.bisect_left(times, _shift(end, FORWARD_DAYS)), i0 + 1)
        return c[i0:i1], src

    bt.load = sliced
    dropped = {"n": 0}
    if drop_zero_risk:
        real_scan = bt.scan

        def scan_dropping(*a, **k):
            res = real_scan(*a, **k)
            for m, trades in res["trades"].items():
                keep = [t for t in trades if t["entry"] != t["stop"]]
                dropped["n"] += len(trades) - len(keep)
                res["trades"][m] = keep
            return res
        bt.scan = scan_dropping
    sets = named_sets(grid)
    labels = job.get("sets") or ["baseline"]
    out = {}
    for label in labels:
        dropped["n"] = 0
        eng = fs.BtEngine(grid, runner, tf, [sym], bt=bt, workers=1)
        t0 = time.time()
        taken = eng.trades_for(sets[label])
        row = {"admitted": len(taken),
               "sha256": hashlib.sha256(json.dumps(taken, sort_keys=True).encode()).hexdigest(),
               "seconds": round(time.time() - t0, 1)}
        if drop_zero_risk:
            row["dropped_entry_equals_stop"] = dropped["n"]
        if hasattr(eng, "admission_stats") and eng._admission:
            st = eng.admission_stats(sets[label])
            if "refused_zero_risk" in st:
                row["refused_zero_risk"] = st["refused_zero_risk"]
                row["candidates"] = st["candidates"]
        out[label] = row
    return dict(job, status="OK", drop_zero_risk=drop_zero_risk, results=out)


def main(argv):
    if len(argv) >= 2 and argv[0] == "job":
        print(json.dumps(run_job(json.loads(argv[1]), "--drop-zero-risk" in argv)))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
