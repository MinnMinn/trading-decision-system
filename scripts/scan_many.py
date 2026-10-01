"""`scan_many()`: N `bt.scan(sym, tf, only=(method,), opts=overlay)` calls for ONE (symbol, timeframe, method) in a
single pass, byte-identical to the N independent calls.

Why (docs/audits/2026-09-30-engine-speed-profile.md): a fund-search candidate scores ~41 (ICT) / ~16 (Wyckoff) V value
sets per symbol, and one scan costs minutes to tens of minutes -- but 97 % of an ICT scan is `ict-scan.analyze()`
run once per bar, and (measured) ~76 % of a Wyckoff scan is `wyckoff_rules.swings()` inside per-window detection.
Neither depends on most V keys, so value sets that agree on the keys that DO reach them are given ONE analysis:

  * ICT: an "analysis group" = the overlays that agree on `ict-scan.ANALYZE_OPT_KEYS` (the keys analyze() reads;
    derived from analyze()'s source and pinned by scripts/tests/test_speed_equivalence.py) and on the bias-reading
    `methods`. Per bar the analysis is computed once and each overlay in the group runs its own downstream half
    (`bt._ict_candidate` / `bt._ict_trade`, the SAME code `ict_setups_live()` runs).
  * WYCKOFF-BOOK: a group = the overlays that agree on the window length and on `bt._wy_detection_ck()` (the keys
    that change DETECTION). Per window the candidates are computed once and each overlay runs its own gates
    (`bt._fires_from`) and per-fire body (`bt._wy_fire`).

Nothing is cached across bars, so memory does not grow with the number of overlays (a whole-history cache of 450 000
analyses would not fit).

Parallelism is over BAR CHUNKS of a group (any partition gives the same answer, so the worker count never changes a
result). Both engines dedupe a setup on its first bar (`seen`); everything AFTER that check is a pure function of
(bar, setup), so a chunk records the first occurrence of every key inside it -- with the result computed for it,
`None` included -- and `_merge` replays the records in bar order, keeping the first occurrence of each key: exactly
what the sequential loop does. Tasks run in `isolated_pool.IsolatedExecutor` (one spawned process per task, a
crashed process fails only its own task, retried up to MAX_RETRIES). Results are merged in (group, chunk) order,
never in completion order.

Memory: every worker loads the full (symbol, timeframe) series -- forward walks need all later bars -- so a worker
holds roughly WORKER_BASE_BYTES + WORKER_BYTES_PER_BAR * bars (`worker_memory_estimate`, measured in
docs/audits/2026-09-30-engine-speed-profile.md). `clamp_workers` lowers the worker count so the estimate for all
workers plus this process stays under MEMORY_FRACTION of physical RAM; the clamp never changes a result, only the
wall time.

Anything that is not ICT / WYCKOFF-BOOK falls back to a plain loop of `bt.scan()` (correct by definition).
Validation (`_check_fx_registered`, the V-set checks, the W6 window check) runs for EVERY overlay before any work, so
a bad overlay raises the same error `bt.scan()` would, just before rather than after the earlier overlays' scans.
"""
import collections
import concurrent.futures
import contextlib
import importlib.util
import io
import math
import os
import sys

import isolated_pool as _pool

ICT, WYCKOFF = "ICT", "WYCKOFF-BOOK"
FAST_METHODS = (ICT, WYCKOFF)
MAX_RETRIES = 2
MEMORY_FRACTION = 0.6
#: Per-worker resident memory = base (interpreter + the engine's modules) + per-bar (the loaded candle dicts, the
#: O/H/L/C/V/time arrays, the id-of-time index). Measured on the real FTMO development series (docs/audits/
#: 2026-09-30-engine-speed-profile.md, "Memory"): XAUUSD 15m 453 893 bars = 346 MiB, 5m 1.32 M bars = 971 MiB, 1m
#: 4.10 M bars = 3 045 MiB, i.e. ~741 B/bar; a real chunk run peaked at 391 MiB on the 15m series. The constants below
#: are those figures rounded UP (~15 %).
WORKER_BASE_BYTES = 128 * 2 ** 20
WORKER_BYTES_PER_BAR = 850
MIN_CHUNK_BARS = 4000


def default_workers():
    return max(1, min((os.cpu_count() or 2) - 2, 10))


def physical_memory_bytes():
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, ValueError, OSError):    # Windows has no sysconf: no clamp rather than a guess
        return None


def worker_memory_estimate(n_bars):
    return WORKER_BASE_BYTES + WORKER_BYTES_PER_BAR * n_bars


def clamp_workers(requested, n_bars, mem_fraction=MEMORY_FRACTION, physical=None):
    """`requested` lowered so that the workers AND this process (which holds the series too: bt.load caches it) each
    fit `worker_memory_estimate(n_bars)` inside `mem_fraction` of RAM; never below 1 (= in-process). Unknown RAM
    (no sysconf, e.g. Windows) means no clamp -- an unknown is not turned into a guess. Wall time only, never a result."""
    requested = max(1, int(requested))
    phys = physical if physical is not None else physical_memory_bytes()
    if not phys:
        return requested
    return max(1, min(requested, int((phys * mem_fraction) // worker_memory_estimate(n_bars)) - 1))


@contextlib.contextmanager
def _opts(bt, o):
    saved = bt.OPTS
    bt.OPTS = o
    try:
        yield
    finally:
        bt.OPTS = saved


def _series(c):
    return dict(O=[x["open"] for x in c], H=[x["high"] for x in c], L=[x["low"] for x in c],
                C=[x["close"] for x in c], V=[x.get("volume", 0) for x in c], Tm=[x["time"] for x in c])


# ------------------------------------------------------------------------------------------------ grouping
def ict_group_key(bt, x):
    """What the per-bar ICT analysis depends on: the analyze()-reading keys of this overlay's `fx_opts`, and the
    bias-reading methods."""
    return (tuple(x.methods), tuple((k, x.fx_opts.get(k)) for k in bt.lr.ict_scan.ANALYZE_OPT_KEYS))


def wy_group_key(bt, win):
    """What the per-window Wyckoff candidates depend on (read under the overlay's OPTS)."""
    return (win,) + tuple(bt._wy_detection_ck())


# ------------------------------------------------------------------------------------------------ chunk kernels
def _chunk_ict(bt, sym, tf, c, S, idx, opts_list, lo, hi):
    """Bars [lo, hi) for the overlays of ONE analysis group. -> per overlay, ordered [(i, key, trade|None)], the
    first occurrence of each key inside this chunk."""
    HZ = bt.P[tf]["H"]
    xs = []
    for o in opts_list:
        with _opts(bt, o):
            methods = bt.resolve_methods(sym)
            xs.append(bt._ict_ctx(sym, tf, c, S["Tm"], HZ, S["H"], S["L"], S["C"], methods, idx_of_time=idx))
    gk = ict_group_key(bt, xs[0])
    if any(ict_group_key(bt, x) != gk for x in xs):
        raise AssertionError("scan_many: overlays of one ICT analysis group disagree on the analyze()-reading keys")
    rep = xs[0]
    read_at = bt.lr.read_at
    events = [[] for _ in xs]
    seen = [set() for _ in xs]
    saved = bt.OPTS
    try:
        for i in range(lo, hi):
            a = read_at(c, i, tf, rep.methods, opts=rep.fx_opts)
            if a is None:
                continue
            for j, x in enumerate(xs):
                bt.OPTS = opts_list[j]
                su = bt._ict_candidate(x, i, a)
                if su is None:
                    continue
                key = (su["side"], su["sweep"]["time"], su["mss"]["time"])
                if key in seen[j]:
                    continue
                seen[j].add(key)
                events[j].append((i, key, bt._ict_trade(x, i, su)))
    finally:
        bt.OPTS = saved
    return events


def _chunk_wy(bt, sym, tf, c, S, opts_list, win, lo, hi):
    """Windows k in [lo, hi) for the overlays of ONE detection group. -> per overlay, ordered
    [(key, {method: [trade, ...]})], the first occurrence of each key inside this chunk."""
    p = bt.P[tf]
    K, HZ = p["K"], p["H"]
    O, H, L, C, V, Tm = S["O"], S["H"], S["L"], S["C"], S["V"], S["Tm"]
    n = len(c)
    want = {WYCKOFF}
    xs = []
    for o in opts_list:
        with _opts(bt, o):
            methods = bt.resolve_methods(sym)
            xs.append(bt._wy_ctx(sym, tf, c, O, H, L, C, Tm, n, K, HZ, None, None, want, methods))
    events = [[] for _ in xs]
    seen = [set() for _ in xs]
    sides_needed = []
    for o in opts_list:
        for side in o["sides"]:
            if side not in sides_needed:
                sides_needed.append(side)
    with _opts(bt, opts_list[0]):            # detection reads only the group's shared detection keys
        kk = bt._wy_params(p["sob"])["pivot"]
    pidx = bt.W.pivot_index(H, L, kk)        # every k-bar pivot of the series, once (see wyckoff_rules.swings)
    saved = bt.OPTS
    try:
        for k in range(lo, hi):
            a = k - win
            bt.OPTS = opts_list[0]
            cands = {side: bt._wyckoff_candidates(side, O[a:k], H[a:k], L[a:k], C[a:k], V[a:k], tf, sym,
                                                  pivots=bt.W.window_pivots(pidx, a, win, kk, swap=(side == "short")))
                     for side in sides_needed}
            for j, x in enumerate(xs):
                o = opts_list[j]
                bt.OPTS = o
                for side in o["sides"]:
                    cs = cands[side]
                    if not cs:
                        continue
                    for f in bt._fires_from(side, cs, C[a:k], Tm[a:k], sym=sym, tf=tf):
                        key = (side, f["t0"], f["leg"])
                        if key in seen[j]:
                            continue
                        seen[j].add(key)
                        tr = collections.defaultdict(list)
                        bt._wy_fire(x, side, f, a, k - 1, tr)
                        events[j].append((key, dict(tr)))
    finally:
        bt.OPTS = saved
    return events


# ------------------------------------------------------------------------------------------------ worker entry
def load_bt(scripts_dir):
    spec = importlib.util.spec_from_file_location("bt", os.path.join(scripts_dir, "backtest-methods.py"))
    bt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bt)
    return bt


def _worker(task):
    """One chunk in a fresh process (module-level so the spawn context can import it). Rebuilds the parent's
    process-global load state (history root, PIT cutoff, bars limit, per-series start) explicitly rather than trusting
    inheritance."""
    sys.path.insert(0, task["scripts_dir"])
    err = io.StringIO()
    with contextlib.redirect_stderr(err):          # the parent already printed this series' data-quality flags
        bt = load_bt(task["scripts_dir"])
        bt.HISTORY_ROOT = task["history_root"]
        bt._PIT_CUTOFF = task["pit_cutoff"]
        bt._BARS_LIMIT = task["bars_limit"]
        bt._SERIES_START = dict(task.get("series_start") or {})     # the decision series' declared start (fund-search cells)
        loads, seen, real_load = [], set(), bt.load

        def traced(s, t):
            if (s, t) not in seen:
                seen.add((s, t)); loads.append((s, t))
            return real_load(s, t)

        bt.load = traced
        events = run_chunk(bt, task)
    return dict(events=events, loads=loads)


def run_chunk(bt, task):
    """The one chunk implementation, used in-process and by `_worker`."""
    sym, tf = task["sym"], task["tf"]
    c, _src = bt.load(sym, tf)
    S = _series(c)
    if task["method"] == ICT:
        idx = {t: j for j, t in enumerate(S["Tm"])}
        return _chunk_ict(bt, sym, tf, c, S, idx, task["opts"], task["lo"], task["hi"])
    return _chunk_wy(bt, sym, tf, c, S, task["opts"], task["win"], task["lo"], task["hi"])


# ------------------------------------------------------------------------------------------------ merge
def _merge_ict(chunk_events):
    out, seen = [], set()
    for ev in chunk_events:                          # chunk order == bar order
        for _i, key, trade in ev:
            if key in seen:
                continue
            seen.add(key)
            if trade is not None:
                out.append(trade)
    return out


def _merge_wy(chunk_events):
    trades, seen = collections.defaultdict(list), set()
    for ev in chunk_events:
        for key, tr in ev:
            if key in seen:
                continue
            seen.add(key)
            for m, lst in tr.items():
                trades[m].extend(lst)
    return trades


# ------------------------------------------------------------------------------------------------ public
def _plan_chunks(lo, hi, n_chunks, min_chunk_bars=MIN_CHUNK_BARS):
    """[lo, hi) cut into <= n_chunks contiguous, non-empty ranges of >= min_chunk_bars (a pure function of its
    arguments)."""
    total = hi - lo
    if total <= 0:
        return []
    n_chunks = max(1, min(n_chunks, math.ceil(total / min_chunk_bars)))
    step = math.ceil(total / n_chunks)
    return [(a, min(hi, a + step)) for a in range(lo, hi, step)]


def scan_many(bt, sym, tf, method, overlays, workers=1, chunks=None, min_chunk_bars=None, memory_fraction=MEMORY_FRACTION):
    """== [bt.scan(sym, tf, only=(method,), opts=o) for o in overlays], byte-identical, faster (module docstring).

    `workers` <= 1 runs everything in this process. `chunks` (tests) forces the number of bar chunks per group;
    the default is what keeps `workers` busy. Returns one scan() result dict (or None: no candles) per overlay."""
    overlays = [dict(o) for o in overlays]
    full = [dict(bt._OPTS_BASE, **o) for o in overlays]
    if method not in FAST_METHODS or not full:
        return [bt.scan(sym, tf, only=(method,), opts=o) for o in overlays]
    for o in full:
        bt._check_fx_registered(o)
    c, src = bt.load(sym, tf)
    if not c:
        return [None] * len(overlays)
    S = _series(c)
    n = len(c)
    Tm = S["Tm"]
    methods_of, wins = [], []
    for o in full:
        with _opts(bt, o):
            methods_of.append(bt.resolve_methods(sym))
    if method == ICT:
        HZ = bt.P[tf]["H"]
        keys = []
        for o, m in zip(full, methods_of):
            with _opts(bt, o):       # grouping only reads x.methods / x.fx_opts; the id-of-time index is built per chunk
                x = bt._ict_ctx(sym, tf, c, Tm, HZ, S["H"], S["L"], S["C"], m, idx_of_time={})
            keys.append(ict_group_key(bt, x))
        bars, _recent = bt.lr.scan_spec(tf)
        lo, hi = bars - 1, n
    else:
        for o in full:
            with _opts(bt, o):
                wins.append(bt._wy_window(sym, tf, n))
        keys = []
        for o, w in zip(full, wins):
            with _opts(bt, o):
                keys.append(wy_group_key(bt, w))
        # every overlay's window may differ (W6): each group has its own [WIN, n] range
    groups = collections.OrderedDict()
    for j, k in enumerate(keys):
        groups.setdefault(k, []).append(j)

    workers = clamp_workers(workers, n, memory_fraction) if workers > 1 else 1
    min_chunk = MIN_CHUNK_BARS if min_chunk_bars is None else min_chunk_bars
    tasks = []                                       # (group index, chunk index, task spec)
    for gi, (gk, members) in enumerate(groups.items()):
        if method == ICT:
            g_lo, g_hi = lo, hi
        else:
            g_lo, g_hi = gk[0], n + 1
        n_chunks = chunks if chunks is not None else (1 if workers <= 1 else math.ceil(2 * workers / len(groups)))
        for ci, (a, b) in enumerate(_plan_chunks(g_lo, g_hi, n_chunks, min_chunk)):
            tasks.append((gi, ci, dict(method=method, sym=sym, tf=tf, opts=[full[j] for j in members],
                                       lo=a, hi=b, win=(gk[0] if method == WYCKOFF else None))))

    results = {}                                     # (gi, ci) -> events per member
    extra_loads = []
    if workers <= 1 or len(tasks) <= 1:
        for gi, ci, t in tasks:
            results[(gi, ci)] = run_chunk(bt, t)
    else:
        scripts_dir = os.path.dirname(os.path.abspath(bt.__file__))
        common = dict(scripts_dir=scripts_dir, history_root=bt.HISTORY_ROOT, pit_cutoff=bt._PIT_CUTOFF,
                      bars_limit=bt._BARS_LIMIT, series_start=dict(getattr(bt, "_SERIES_START", None) or {}))
        pending = {(gi, ci): dict(t, **common) for gi, ci, t in tasks}
        attempts = collections.Counter()
        with _pool.IsolatedExecutor(max_workers=workers) as ex:
            futs = {ex.submit(_worker, spec): key for key, spec in pending.items()}
            while futs:
                done, _ = concurrent.futures.wait(futs, return_when=concurrent.futures.FIRST_COMPLETED)
                for fut in done:
                    key = futs.pop(fut)
                    try:
                        out = fut.result()
                    except _pool.WorkerCrashed:
                        attempts[key] += 1
                        if attempts[key] > MAX_RETRIES:
                            raise
                        futs[ex.submit(_worker, pending[key])] = key
                        continue
                    results[key] = out["events"]
                    extra_loads.extend(out["loads"])
        for s, t in extra_loads:                     # keep §20/§38 quality flags what an in-process scan leaves
            bt.load(s, t)
    return _assemble(bt, sym, tf, method, src, S, groups, results, len(full))


def _assemble(bt, sym, tf, method, src, S, groups, results, n_overlays):
    """Merge in (group, chunk) order -- never completion order -- into one scan()-shaped dict per overlay."""
    Tm = S["Tm"]
    n = len(Tm)
    out = [None] * n_overlays
    for gi, (gk, members) in enumerate(groups.items()):
        chunk_ids = sorted(ci for (g, ci) in results if g == gi)
        for pos, j in enumerate(members):
            evs = [results[(gi, ci)][pos] for ci in chunk_ids]
            trades = collections.defaultdict(list)
            if method == ICT:
                trades["ICT"] = _merge_ict(evs)
            else:
                for m, lst in _merge_wy(evs).items():
                    trades[m] = lst
            out[j] = dict(symbol=sym, tf=tf, source=src, bars=n, first=Tm[0], last=Tm[-1], trades=trades)
    return out
