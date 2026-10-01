#!/usr/bin/env python3
"""Zero-risk trade COUNTS for the fund-search pre-registration (docs/audits/2026-10-01-zero-risk.md).

Counts ONLY: how many RAW scanned trades (the output of `bt.scan` / `scan_many`, exactly what BtEngine.trades_for feeds
to `real_costs.cost_r` and `simulate()`) have a planned risk |entry - stop| that is zero, negative (stop on the wrong
side), non-finite, or positive but below the symbol's tick (`tick_size` of its real-cost spec) -- per (method, symbol,
timeframe, value set, year). It never reads, prints or stores R, expectancy or any performance figure, and it never
calls `simulate()`/`cost_r` (that is what aborts on a zero-risk trade). Nothing here selects, evaluates or changes any
engine/harness/grid/threshold.

Value sets (ICT): the baseline, every single-factor candidate (one item moved to one non-baseline value: the 27 sets the
harness's wave 1 asks for) and, because the root cause is the B-EX=fill entry model (see the audit), every
`B-EX=fill` + one other single-factor value (the combined / perturbation sets the harness builds later are such
mixtures). Value sets (Wyckoff): the baseline and every single-factor candidate.

    python3 scripts/research/zero_risk_count.py job '{"method":"ict","symbol":"US500","tf":"1m","start":"2023-03-01T00:00:00Z","end":"2023-04-01T00:00:00Z"}' [--workers 4]
    python3 scripts/research/zero_risk_count.py job '{"method":"ict","symbol":"US500","tf":"1m"}'        # whole development span
Needs BT_HISTORY_ROOT=data/history/ftmo (set here when absent). Output: ONE JSON line on stdout.
"""
import bisect
import collections
import datetime
import importlib.util
import json
import math
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


def single_factor_sets(grid):
    """[(label, values)]: baseline, then one item moved to one non-baseline value (the harness's wave-1 sets)."""
    base = grid.baseline()
    out = [("baseline", dict(base))]
    for it in grid.items:
        for v in it["values"][1:]:
            out.append((f"{it['id']}={v}", dict(base, **{it["id"]: v})))
    return out


def fill_combo_sets(grid):
    """B-EX=fill plus every other single-factor value (ICT only)."""
    base = grid.baseline()
    out = []        # B-EX=fill alone is already in single_factor_sets()
    for it in grid.items:
        if it["id"] == "B-EX":
            continue
        for v in it["values"][1:]:
            out.append((f"B-EX=fill+{it['id']}={v}", dict(base, **{"B-EX": "fill", it["id"]: v})))
    return out


def classify(t, tick, refusal):
    """The category of ONE raw trade (no R is read). `refusal` is `backtest-methods.planned_risk_refusal` -- the SAME
    function simulate() and the harness apply -- so zero / wrong_side / sub_tick / invalid_price are the rule's own refusals.
    Two extra, non-refusal categories: `strict_below_tick_admitted` (0 < risk < tick in plain floating point but within the
    rule's slack of exactly one tick: float noise, ADMITTED) and `bad_target_or_planned_r` (not a rule refusal)."""
    why = refusal(t.get("side"), t.get("entry"), t.get("stop"), tick)
    if why is not None:
        return why
    e, s = t["entry"], t["stop"]
    risk = (e - s) if t["side"] == "long" else (s - e)
    if tick is not None and risk < tick:
        return "strict_below_tick_admitted"
    tg, rp = t.get("target"), t.get("R_planned")
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in (tg, rp)):
        return "bad_target_or_planned_r"
    return "ok"


def run_job(job, workers=1):
    fs = _fs()
    method, sym, tf = job["method"], job["symbol"], job["tf"]
    start, end = job.get("start"), job.get("end")
    grids, _ = fs.load_grids()
    grid = grids[method].runnable()
    bt = fs._load_bt()
    runner = fs.METHODS[method]
    import real_costs as _RC
    point = _RC.tick_size(fs.COST_PROFILE, sym)     # the tick the rule uses
    real_load = bt.load
    info = {}

    def sliced(s, t):
        c, src = real_load(s, t)
        if (s, t) != (sym, tf) or not c or not (start and end):
            return c, src
        times = [x["time"] for x in c]
        spec_bars = bt.lr.scan_spec(tf)[0] if method == "ict" else bt._wy_window(sym, tf, len(c))
        i0 = max(bisect.bisect_left(times, _shift(start, -WARMUP_DAYS)) - spec_bars, 0)
        i1 = max(bisect.bisect_left(times, _shift(end, FORWARD_DAYS)), i0 + 1)
        info["slice_bars"] = i1 - i0
        return c[i0:i1], src

    bt.load = sliced
    t0 = time.time()
    eng = fs.BtEngine(grid, runner, tf, [sym], bt=bt, workers=workers)
    sets = single_factor_sets(grid) + (fill_combo_sets(grid) if method == "ict" else [])
    if job.get("labels"):          # restrict to named sets (e.g. the Wyckoff sets sharing the baseline detection group)
        sets = [x for x in sets if x[0] in job["labels"]]
    eng.prefetch([v for _l, v in sets])
    counts = collections.defaultdict(collections.Counter)      # label -> Counter(("year", category) | ("n", year))
    for label, values in sets:
        raw = eng._raw[fs.FS.CountingSource._key(values)]
        for t in raw:
            if start and end and not (start <= t["entry_time"] < end):
                continue
            if t["entry_time"] >= fs.FS.DEV_CUTOFF:
                continue
            y = t["entry_time"][:4]
            counts[label][(y, "n")] += 1
            cat = classify(t, point, bt.planned_risk_refusal)
            if cat != "ok":
                counts[label][(y, cat)] += 1
    out = {}
    for label, c in counts.items():
        for (y, cat), n in c.items():
            out.setdefault(label, {}).setdefault(y, {})[cat] = n
    return dict(job, status="OK", point=point, bars=info.get("slice_bars"), seconds=round(time.time() - t0, 1),
                sets=len(sets), counts=out)


def main(argv):
    if len(argv) >= 2 and argv[0] == "job":
        workers = int(argv[argv.index("--workers") + 1]) if "--workers" in argv else 1
        print(json.dumps(run_job(json.loads(argv[1]), workers)))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
