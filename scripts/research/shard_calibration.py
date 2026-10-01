#!/usr/bin/env python3
"""Cost-structure measurement of a fund-search scan shard (docs/audits/2026-10-01-shard-calibration.md).

COUNTS, SECONDS, BYTES ONLY. Nothing here prints, stores or reads R / expectancy / any performance figure. The harness
engine (`BtEngine` of scripts/fund-search.py, `scan_many`, the harness's own wave functions) is used unmodified.

Jobs (each one OS process; JSON line on stdout):

    job '{"kind":"scan", "method":"ict|wyckoff", "symbol":"XAUUSD", "tf":"1m", "slice":"S3", "sets":[...]}'
        times ONE `BtEngine.scan_symbol` (= what an Actions shard persists) over a one-year slice of the decision series
        (the cut `scripts/research/trade_rates.py` uses). `sets` names the value sets: "base", "w1:<i>" (i-th wave-1 set
        in discovery order), or a literal {item: value} dict.
    job '{"kind":"groups", "method":..., "tf":...}'
        the wave-1 value sets of the real grid, their `scan_many` detection-group key, and the group sizes -- computed with
        the harness's own functions, no data read.
    job '{"kind":"load", "symbol":"XAUUSD", "tf":"1m"}'
        time + RSS of loading the FULL PIT-truncated decision series and building the engine (no scan).
    job '{"kind":"wave2", "method":..., "symbols":[...], "tf":..., "dev_start":"..."}'
        wave-1 scan + the harness's `wave2_values` on a small real span: how many NEW value sets wave 2 asks for per fold.
    job '{"kind":"trades_for", ...}', '{"kind":"cache_io", ...}'
        post-processing and cache-verification cost per value set.

Needs BT_HISTORY_ROOT=data/history/ftmo (set here when absent).
"""
import argparse
import bisect
import collections
import datetime
import json
import os
import resource
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, HERE)
os.environ.setdefault("BT_HISTORY_ROOT", os.path.join(ROOT, "data", "history", "ftmo"))

import trade_rates as TR  # noqa: E402  (slices, warm-up and the module loader)


def rss_mib():
    """Peak resident set of THIS process so far, MiB (macOS reports bytes, Linux KiB)."""
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / 2 ** 20 if sys.platform == "darwin" else r / 1024


def cur_rss_mib():
    out = subprocess.run(["ps", "-o", "rss=", "-p", str(os.getpid())], capture_output=True, text=True).stdout.strip()
    return int(out) / 1024


def install_slice(bt, sym, tf, method, start, end, info):
    """Same cut as trade_rates.run_job: [start - warm-up - scan window, end + forward]. Returns the real `bt.load`."""
    real_load = bt.load

    def sliced(s, t):
        c, src = real_load(s, t)
        if (s, t) != (sym, tf) or not c:
            return c, src
        times = [x["time"] for x in c]
        spec_bars = bt.lr.scan_spec(tf)[0] if method == "ict" else bt._wy_window(sym, tf, len(c))
        i0 = max(bisect.bisect_left(times, TR._shift(start, -TR.WARMUP_DAYS)) - spec_bars, 0)
        i1 = max(bisect.bisect_left(times, TR._shift(end, TR.FORWARD_DAYS)), i0 + 1)
        info["slice_bars"] = i1 - i0
        info["first_bar"] = times[0]
        return c[i0:i1], src

    bt.load = sliced
    return real_load


def slice_bounds(sl):
    """"S1".."S3" (trade_rates) or [start, end] ISO strings (a one-year slice anywhere in the history)."""
    return TR.SLICES[sl] if isinstance(sl, str) else tuple(sl)


def wave1_list(fs, engine, grid, tf):
    cell = {"development_start": "2012-05-03T05:38:00Z", "timeframe": tf}      # the wave-1 list needs only the grid
    return fs.wave1_values(engine, grid, cell)


def resolve_sets(fs, grid, wave1, specs):
    out = []
    for sp in specs:
        if sp == "base":
            out.append(dict(grid.baseline()))
        elif isinstance(sp, str) and sp.startswith("w1:"):
            out.append(dict(wave1[int(sp[3:])]))
        elif isinstance(sp, dict):
            out.append(dict(sp))
        else:
            raise SystemExit(f"bad set spec {sp!r}")
    return out


class GroupSpy:
    """Records what scan_many grouped (its own `_assemble` argument), without changing it."""

    def __init__(self, SM):
        self.SM, self.rows = SM, []
        self.real = SM._assemble

        def spy(bt, sym, tf, method, src, S, groups, results, n_overlays):
            self.rows.append({"groups": len(groups), "sizes": [len(m) for m in groups.values()],
                              "chunks": len({ci for (_g, ci) in results})})
            return self.real(bt, sym, tf, method, src, S, groups, results, n_overlays)

        SM._assemble = spy

    def last(self):
        return self.rows[-1]


def job_scan(j):
    fs = TR._fs()
    method, sym, tf = j["method"], j["symbol"], j["tf"]
    start, end = slice_bounds(j.get("slice", "S3"))
    grids, _ = fs.load_grids()
    grid = grids[method].runnable()
    bt = fs._load_bt()
    info = {}
    install_slice(bt, sym, tf, method, start, end, info)
    spy = GroupSpy(fs.SM)
    l0 = os.getloadavg()[0]
    t0 = time.time()
    eng = fs.BtEngine(grid, fs.METHODS[method], tf, [sym], bt=bt, workers=1)
    t_build = time.time() - t0
    rss_build = cur_rss_mib()
    wave1 = wave1_list(fs, eng, grid, tf)
    sets = resolve_sets(fs, grid, wave1, j["sets"])
    t1 = time.time()
    got = eng.scan_symbol(sym, sets)
    secs = time.time() - t1
    n_tr = sum(len(v) for v in got.values())
    sp = spy.last()
    return dict(j, status="OK", seconds=round(secs, 2), build_s=round(t_build, 2), bars=info["slice_bars"],
                n_sets=len(sets), n_distinct_sets=len(got), groups=sp["groups"], group_sizes=sp["sizes"], trades=n_tr,
                rss_peak_mib=round(rss_mib()), rss_after_build_mib=round(rss_build), load_start=round(l0, 1),
                load_end=round(os.getloadavg()[0], 1))


def group_keys(fs, method, tf, sym, overlays, bt):
    """The scan_many group key of every overlay, computed exactly as scan_many does but without data."""
    SM = fs.SM
    keys = []
    for o in overlays:
        full = dict(bt._OPTS_BASE, **o)
        with SM._opts(bt, full):
            if method == "ict":
                m = bt.resolve_methods(sym)
                x = bt._ict_ctx(sym, tf, [], [], bt.P[tf]["H"], [], [], [], m, idx_of_time={})
                keys.append(SM.ict_group_key(bt, x))
            else:
                keys.append(SM.wy_group_key(bt, bt._wy_window(sym, tf, 10 ** 9)))
    return keys


class _NoDataEngine:
    """Holds nothing: enough for `wave1_values` (it needs only `has` and the engine's `bt`)."""

    def __init__(self, bt):
        self.bt = bt

    def has(self, values):
        return False


def job_scan_dev(j):
    """Like `scan`, but the one-year span is cut by the harness's OWN `dev_start` (bt.series_start), which spawned scan
    workers inherit -- so `workers` > 1 can be timed on a one-year span. dev_start must be >= 2023-03-01 (cutoff 2024-03-01)."""
    fs = TR._fs()
    method, sym, tf, w = j["method"], j["symbol"], j["tf"], int(j["workers"])
    grids, _ = fs.load_grids()
    grid = grids[method].runnable()
    bt = fs._load_bt()
    spy = GroupSpy(fs.SM)
    t0 = time.time()
    eng = fs.BtEngine(grid, fs.METHODS[method], tf, [sym], bt=bt, workers=w, dev_start=j["dev_start"], warmup_days=14)
    t_build = time.time() - t0
    wave1 = wave1_list(fs, eng, grid, tf)
    sets = resolve_sets(fs, grid, wave1, j["sets"])
    t1 = time.time()
    got = eng.scan_symbol(sym, sets)
    secs = time.time() - t1
    sp = spy.last()
    return dict(j, status="OK", seconds=round(secs, 2), build_s=round(t_build, 2), bars=eng._series[sym]["bars"],
                n_sets=len(sets), groups=sp["groups"], chunks=sp["chunks"], trades=sum(len(v) for v in got.values()),
                rss_peak_mib=round(rss_mib()), load_start=round(os.getloadavg()[0], 1))


def job_groups(j):
    """Wave-1 value sets of the real grids and their scan_many detection groups (no data read)."""
    fs = TR._fs()
    grids, _ = fs.load_grids()
    bt = fs._load_bt()
    out = {}
    for method in ("ict", "wyckoff"):
        grid = grids[method].runnable()
        for tf in ("1m", "5m", "15m"):
            cell = {"development_start": "2012-05-03T05:38:00Z", "timeframe": tf}
            w1 = fs.wave1_values(_NoDataEngine(bt), grid, cell)
            keys = group_keys(fs, method, tf, "XAUUSD", [fs.build_overlay(grid, v) for v in w1], bt)
            distinct = list(dict.fromkeys(keys))
            out[f"{method}-{tf}"] = {"n_sets": len(w1), "n_groups": len(distinct),
                                     "set_group_index": [distinct.index(k) for k in keys],
                                     "group_sizes": [keys.count(k) for k in distinct],
                                     "baseline_group_size": keys.count(keys[0])}
    return dict(j, status="OK", result=out)


def job_load(j):
    fs = TR._fs()
    sym, tf = j["symbol"], j["tf"]
    grids, _ = fs.load_grids()
    grid = grids["ict"].runnable()
    bt = fs._load_bt()
    r0 = cur_rss_mib()
    t0 = time.time()
    bt.pit_cutoff(fs.FS.DEV_CUTOFF)
    c, _src = bt.load(sym, tf)
    t_load = time.time() - t0
    r_load = cur_rss_mib()
    t1 = time.time()
    eng = fs.BtEngine(grid, "ICT", tf, [sym], bt=bt, workers=1)
    t_eng = time.time() - t1
    r_eng = cur_rss_mib()
    import scan_many as SM
    t2 = time.time()
    S = SM._series(c)
    idx = {t: i for i, t in enumerate(S["Tm"])}
    t_chunk = time.time() - t2
    r_chunk = cur_rss_mib()
    return dict(j, status="OK", bars=len(c), rss_start_mib=round(r0), rss_after_load_mib=round(r_load),
                load_s=round(t_load, 2), engine_build_s=round(t_eng, 2), rss_after_engine_mib=round(r_eng),
                chunk_arrays_s=round(t_chunk, 2), rss_after_chunk_arrays_mib=round(r_chunk), rss_peak_mib=round(rss_mib()),
                est_worker_mib=round(SM.worker_memory_estimate(len(c)) / 2 ** 20), bytes_per_bar_after_chunk=round(
                    (r_chunk - r0) * 2 ** 20 / len(c)), idx_len=len(idx))


def job_wave2(j):
    """Wave 1 for `symbols` over the span [dev_start, DEV_CUTOFF] with the harness's own engine and wave functions, then
    how many NEW value sets wave 2 asks for (counts only: selection runs for real inside the harness's own function; its
    inputs and outputs other than the NUMBER of requested sets and their detection groups are neither printed nor kept)."""
    fs = TR._fs()
    method, tf, symbols = j["method"], j["tf"], j["symbols"]
    grids, _ = fs.load_grids()
    grid = grids[method].runnable()
    bt = fs._load_bt()
    spy = GroupSpy(fs.SM)
    ds = j["dev_start"]
    cell = {"development_start": ds, "timeframe": tf}
    t0 = time.time()
    eng = fs.BtEngine(grid, fs.METHODS[method], tf, symbols, bt=bt, workers=1, dev_start=ds, warmup_days=14)
    build_s = time.time() - t0
    n_bars = {s: eng._series[s]["bars"] for s in symbols}
    w1 = fs.wave1_values(eng, grid, cell)
    t1 = time.time()
    eng.prefetch(w1)
    scan1_s = time.time() - t1
    w1_scans = [dict(r) for r in spy.rows]
    t2 = time.time()
    for v in w1:
        eng.trades_for(v)
    post_s = time.time() - t2
    folds = fs.FS.make_folds(ds)
    t3 = time.time()
    w2 = fs.wave2_values(eng, grid, cell)
    probe_s = time.time() - t3
    n_trades_held = sum(len(eng._done[k]) for k in eng._done)
    # which fold asked for what: re-run the stages with a recording probe is NOT needed for the totals; per-fold counts:
    per_fold, per_fold_groups, per_fold_w600 = [], [], []
    emb = fs.embargo_for(tf, bt)
    for fr_i in range(len(folds)):
        sub = [folds[fr_i]]
        p = fs._WaveProbe(eng)
        frs = fs.FS.nested_walk_forward(grid, p, sub, fs.FS.bar_delta(tf), embargo=emb)
        pert = fs.FS.perturbation_trade_sets(grid, p, frs)
        per_fold.append(len(p.missing))
        fk = group_keys(fs, method, tf, symbols[0], [fs.build_overlay(grid, v) for v in p.missing.values()], bt)
        per_fold_groups.append(len(set(fk)))
        per_fold_w600.append(len({k for k in fk if method == "wyckoff" and k[0] != 300}))
    keys = group_keys(fs, method, tf, symbols[0], [fs.build_overlay(grid, v) for v in w2], bt)
    w1_keys = group_keys(fs, method, tf, symbols[0], [fs.build_overlay(grid, v) for v in w1], bt)
    return dict(j, status="OK", folds=len(folds), bars=n_bars, wave1_sets=len(w1), wave1_groups=len(set(w1_keys)),
                wave2_sets=len(w2), wave2_groups=len(set(keys)), wave2_groups_new=len(set(keys) - set(w1_keys)),
                wave2_sets_per_fold_alone=per_fold, wave2_groups_per_fold_alone=per_fold_groups,
                wave2_w600_groups_per_fold_alone=per_fold_w600, build_s=round(build_s, 1), wave1_scan_s=round(scan1_s, 1),
                trades_for_total_s=round(post_s, 1), wave2_probe_s=round(probe_s, 1), held_trades=n_trades_held,
                rss_peak_mib=round(rss_mib()))


def job_trades_for(j):
    """Cost of `trades_for` (simulate + admission rows + adx) per value set on a span, with raw scans held."""
    fs = TR._fs()
    method, sym, tf = j["method"], j["symbol"], j["tf"]
    grids, _ = fs.load_grids()
    grid = grids[method].runnable()
    bt = fs._load_bt()
    info = {}
    start, end = j["start"], j["end"]
    install_slice(bt, sym, tf, method, start, end, info)
    eng = fs.BtEngine(grid, fs.METHODS[method], tf, [sym], bt=bt, workers=1)
    wave1 = wave1_list(fs, eng, grid, tf)
    sets = resolve_sets(fs, grid, wave1, j["sets"])
    t0 = time.time()
    eng.prefetch(sets)
    scan_s = time.time() - t0
    raw_n = [len(eng._raw[fs.FS.CountingSource._key(v)]) for v in sets]
    t1 = time.time()
    for v in sets:
        eng.trades_for(v)
    post_s = time.time() - t1
    return dict(j, status="OK", bars=info["slice_bars"], scan_s=round(scan_s, 1), trades_for_s=round(post_s, 2),
                trades_for_s_per_set=round(post_s / len(sets), 3), raw_trades=raw_n)


def job_cache_io(j):
    """Write and read-verify scan-cache entries of the real size distribution of a slice scan (entry bytes, seconds)."""
    fs = TR._fs()
    method, sym, tf = j["method"], j["symbol"], j["tf"]
    start, end = slice_bounds(j.get("slice", "S3"))
    grids, _ = fs.load_grids()
    grid = grids[method].runnable()
    bt = fs._load_bt()
    info = {}
    install_slice(bt, sym, tf, method, start, end, info)
    eng = fs.BtEngine(grid, fs.METHODS[method], tf, [sym], bt=bt, workers=1)
    wave1 = wave1_list(fs, eng, grid, tf)
    sets = resolve_sets(fs, grid, wave1, j["sets"])
    got = eng.scan_symbol(sym, sets)
    import hashlib  # noqa: F401
    plan = fs.build_plan()
    stamp = fs.scan_cache_stamp(plan)
    d = tempfile.mkdtemp(prefix="b14-cache-")
    cand = next(c for c in plan["candidates"] if c["method"] == method)
    t0 = time.time()
    paths = []
    for v in sets:
        key = fs.FS.CountingSource._key(v)
        scope = fs.scan_cache_scope("calib", cand["runner_method"], tf, sym, key, eng._series[sym])
        paths.append(fs.write_scan_entry(d, stamp, scope, got[key]))
    w_s = time.time() - t0
    t1 = time.time()
    for p in paths:
        fs.read_scan_entry(p, stamp)
    r_s = time.time() - t1
    sizes = [os.path.getsize(p) for p in paths]
    n_tr = [len(got[fs.FS.CountingSource._key(v)]) for v in sets]
    return dict(j, status="OK", entries=len(paths), trades=n_tr, bytes=sizes, write_s=round(w_s, 3),
                read_verify_s=round(r_s, 3), series_sha_s_per_bar=None)


def job_entry_eq_stop(j):
    """Finding, not a cost: raw trades whose entry price equals their stop price (real_costs.cost_r REFUSES those: "stop
    distance is zero"), per value set, on a one-year slice. COUNTS and prices-free summary only."""
    fs = TR._fs()
    method, sym, tf = j["method"], j["symbol"], j["tf"]
    start, end = slice_bounds(j.get("slice", "S3"))
    grids, _ = fs.load_grids()
    grid = grids[method].runnable()
    bt = fs._load_bt()
    info = {}
    install_slice(bt, sym, tf, method, start, end, info)
    eng = fs.BtEngine(grid, fs.METHODS[method], tf, [sym], bt=bt, workers=1)
    wave1 = wave1_list(fs, eng, grid, tf)
    sets = resolve_sets(fs, grid, wave1, j["sets"])
    t0 = time.time()
    got = eng.scan_symbol(sym, sets)
    base = grid.baseline()
    rows = []
    for v in sets:
        tr = got[fs.FS.CountingSource._key(v)]
        rows.append({"diff": {k: x for k, x in v.items() if base.get(k) != x}, "raw_trades": len(tr),
                     "entry_eq_stop": sum(1 for t in tr if t["entry"] == t["stop"])})
    return dict(j, status="OK", seconds=round(time.time() - t0, 1), bars=info["slice_bars"], per_set=rows,
                sets_with_zero_stop=sum(1 for r in rows if r["entry_eq_stop"]))


def job_bars(j):
    """PIT-truncated development bar count (bars before DEV_CUTOFF) of every (symbol, timeframe): the numbers DEV_BARS of
    scripts/fund-search.py holds. Prints the committed DEV_BARS value next to the measured one. Loads each series (a few
    seconds for 4 M bars); scans nothing."""
    fs = TR._fs()
    bt = fs._load_bt()
    bt.pit_cutoff(fs.FS.DEV_CUTOFF)
    out = {}
    for tf in j["tfs"]:
        for sym in j["symbols"]:
            c, _src = bt.load(sym, tf)
            out.setdefault(tf, {})[sym] = {"bars": len(c), "first_bar": c[0]["time"] if c else None,
                                           "DEV_BARS": fs.DEV_BARS.get(tf, {}).get(sym)}
    return dict(j, status="OK", result=out)


def run_job(j):
    return {"scan": job_scan, "groups": job_groups, "load": job_load, "wave2": job_wave2,
            "trades_for": job_trades_for, "cache_io": job_cache_io, "scan_dev": job_scan_dev,
            "entry_eq_stop": job_entry_eq_stop, "bars": job_bars}[j["kind"]](j)


def drive(jobs_file, out, workers):
    import concurrent.futures
    jobs = [json.loads(l) for l in open(jobs_file) if l.strip() and not l.startswith("#")]

    def one(j):
        t0 = time.time()
        p = subprocess.run([sys.executable, os.path.abspath(__file__), "job", json.dumps(j)], capture_output=True, text=True)
        line = [l for l in p.stdout.splitlines() if l.startswith("{")]
        if p.returncode != 0 or not line:
            return dict(j, status="ERROR", seconds=round(time.time() - t0, 1), reason=p.stderr.strip()[-600:])
        return json.loads(line[-1])

    with open(out, "a") as fh, concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        for r in ex.map(one, jobs):
            fh.write(json.dumps(r) + "\n")
            fh.flush()
            print(json.dumps(r), flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    j = sub.add_parser("job")
    j.add_argument("spec")
    d = sub.add_parser("drive")
    d.add_argument("--jobs", required=True)
    d.add_argument("--out", required=True)
    d.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    if a.cmd == "job":
        print(json.dumps(run_job(json.loads(a.spec))))
    else:
        assert a.workers <= 4, "at most 4 processes"
        drive(a.jobs, a.out, a.workers)


if __name__ == "__main__":
    main()
