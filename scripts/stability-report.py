#!/usr/bin/env python3
"""Rank entry methods by CONSISTENCY over time, not by total return.

Runs scripts/backtest-methods.py's engine over several timeframes and configurations, books every closed trade on a
compounding account at bt.RISK per trade (= the live per-trade ceiling), and reports per method: trades, annualised %, max drawdown, share of positive quarters,
worst quarter, median quarter, quarter mean/σ (a t-like stability ratio), share of positive years, per-year returns.

Usage: stability-report.py [--tf 15m,30m,1H,2H,4H,1D] [--symbols ...] [--out docs/backtests/<file>.md] [--json PATH]
Configurations (all long AND short):
  A  taker fee 0.05 %, no management, no HTF filter               (the raw rule)
  B  maker fee 0.02 % (limit entries), breakeven at +1R (WMT p272)  (book-style management)
  C  as B + higher-timeframe boundary filter (htf_context rule)     (giảm khung)
"""
import argparse, concurrent.futures, contextlib, datetime, importlib.util, io, json, os, statistics, sys
import concurrent.futures.process  # BrokenProcessPool lives here; `import concurrent.futures` does not load it

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("bt", os.path.join(ROOT, "scripts", "backtest-methods.py")); bt = importlib.util.module_from_spec(spec); spec.loader.exec_module(bt)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import snapshot          # CLAUDE.md §10: every research run identifies the dataset it read
import isolated_pool as _pool  # one process per scan: a hardware crash costs that scan, not the batch
import scan_cache as _sc       # a scan computed once on disk is reused by every account / job (--scan-cache)
import instruments as _I  # §35: the run's own symbols name the market, and (market, tf) names the system
import performance as _perf  # CLAUDE.md §39: the ONE computer for the twenty-three metrics
import providers as _P       # §4: which venue this market's orders go to -- and therefore what a fill costs
import importlib.util as _iu
_rs = _iu.spec_from_file_location("risk_model", os.path.join(ROOT, "scripts", "risk_model.py"))
_RM = _iu.module_from_spec(_rs); _rs.loader.exec_module(_RM)   # THE fee source (risk-config.json `costs`)
METHODS = bt.RUNNER_METHODS   # ONE source (scripts/backtest-methods.py); WYCKOFF, COMBINED and PARTIAL were
                              # removed 2026-09-19 (docs/audits/2026-09-19-knowledge-fidelity.md finding 6) --
                              # this used to be a second, hand-kept copy of the same tuple, which is exactly
                              # how it stayed stale.
# A config's fee is a SIDE of the venue's declared cost, never a literal. Until 2026-09-18 these carried
# 0.0005 / 0.0002 / 0.0002 outright -- the Binance taker/maker schedule -- and every market got them, so a CFD
# row in config B or C was priced at 0.02 %/side when the MT5 account pays 0.05 %. The ranking then SELECTED
# two of those rows (cfd-day-combined-1h-border-b, cfd-swing-wyckoff-4h-border-b), i.e. the pilot was about to
# be handed setups whose edge was measured 2.5x cheaper than the venue charges.
#
# `taker` vs `maker` is the config's real claim -- "this rule enters at market" vs "this rule enters on a
# limit" -- and what THAT costs is the venue's business. On MT5 the broker prices CFDs in the spread and both
# sides are equal, so B and C correctly stop claiming a rebate that does not exist there and differ from A only
# by the management rule and the HTF filter, which is what they actually are.
CONFIGS = {"A": dict(side="taker", mgmt="none", htf=False),
           "B": dict(side="maker", mgmt="be", htf=False),
           "C": dict(side="maker", mgmt="be", htf=True)}


def config_opts(cfg, ict_target):
    """The full `bt.OPTS` overlay one CONFIGS entry applies -- ONE definition, used both to actually run a
    config (main()'s `bt.OPTS.update(**config_opts(...))`, replacing the inline dict literal that used to be
    typed out at the call site) and, before anything runs, to recognise which configs will make `bt.scan()`
    produce the same trades (see `_scan_cache_key` below). `combined_entry` is included even though `scan()`
    never reads it, so this dict is always the complete, honest overlay a config applies to `bt.OPTS` -- not a
    hand-picked subset that could quietly drift from what `bt.OPTS.update()` sets.

    `range_touches` is NOT in this dict (A0b, 2026-09-28): it used to be included here at a hard-coded 0 for
    the same "complete overlay" reason, but `range_touches` itself was never a real `bt.OPTS` key that
    `scan()`/`simulate()` read at ANY value (see the note where `OPTS` is defined in backtest-methods.py) --
    including a dead key in an "honest overlay" was the opposite of honest, so the key and its CLI/OPTS default
    were removed rather than kept here.

    `ict_target` is accepted, not returned in the overlay: `scripts/ict-scan.py`'s `setup_candidate()` reads no
    target-model choice at all -- the six-way switch (`bt.ict_target()`) was deleted from the engine
    2026-09-13 (`scripts/strategy-runner.py:22`) -- so folding it into `bt.OPTS` would plant the same kind of
    dead key `range_touches` was. It is validated here (only "range", the scanner's one actual behaviour, is
    accepted) so a caller asking for an unimplemented target model fails loudly instead of silently getting
    ignored; callers pass it straight through to `snapshot.backtest_config_snapshot(ict_target=...)` for the
    system-naming label (`scripts/rank-setups.py:156`)."""
    if ict_target != "range":
        raise ValueError(f"config_opts: ict_target={ict_target!r} is not implemented -- "
                         f"scripts/ict-scan.py's setup_candidate() only ever targets -2sigma-then-range-edge "
                         f"(A0b, docs/plans/2026-09-28-methodology-improvement-plan.md); pass 'range'")
    return dict(mgmt=cfg["mgmt"], htf=cfg["htf"], sides=("long", "short"), types=(1, 2, 3),
                entry="book", sloped_gate=False, st_gate=False, phase_b_gate=False, st_min=None, phase_d=True,
                combined_entry="limit",
                # A0: the v1 defaults, stated so the scan cache key always sees them (_SCAN_RELEVANT_KEYS).
                flat_before_rollover=False, rollover_provider=None,
                # B1/Batch-1a (docs/plans/2026-09-29-execution-plan.md "Shared contract"): the v1 default
                # (False) for every ICT fx_ key (scripts/backtest-methods.py FX_ICT_KEYS), stated here for the
                # same "always the complete, honest overlay" reason as every other key in this dict.
                fx_b2a_fvg_in_leg=False, fx_b2b_ce_fail=False, fx_b1_pivot1=False, fx_braid_optional=False,
                # Batch 1(b) F items (docs/plans/2026-09-28-methodology-improvement-plan.md §3; the shared fx_
                # key contract, docs/plans/2026-09-29-execution-plan.md): the v1 defaults, stated so this stays
                # the COMPLETE, honest bt.OPTS overlay a config applies -- not a hand-picked subset that could
                # silently omit a scan-cache-relevant key (see _SCAN_RELEVANT_KEYS below).
                fx_w1_tr_low_st=False, fx_w2_st_below_sc=False, fx_w3_mSOW_spring=False, fx_w5_vp_abandon=False,
                fx_w7_htf_target=False,
                # O1 (2026-09-30): v1 default; True = min_rr admission uses entry-knowable costs only.
                fx_admission_entry_cost=False,
                # C3 (2026-10-02): v1 default; True = walk() fills a stop at the worse of the stop and the bar open.
                fx_gap_fill=False,
                # D3 (2026-10-02): v1 default; True = the ICT fill scans start after the FVG's third candle closed.
                fx_fvg_formed_start=False,
                # Batch 2(a) Wyckoff V items (plan §3 V grid; docs/architecture/v-grid-wyckoff.json): the baseline
                # (= v1) of each key, stated for the same "complete overlay" reason. W-MGMT is `mgmt` above.
                fx_w_stop="current", fx_w4a_linger_closes=None, fx_w6_window=300, fx_w_spt="AR", fx_w_touch="off",
                fx_w_tw=(12, 2),
                # A2b decision side (plan §2): v1 default, stated so the overlay stays complete.
                fx_a2b_stale_htf_block=False,
                # Batch 2(a) ICT V items (docs/plans/2026-09-28-methodology-improvement-plan.md §3): each key's
                # declared BASELINE value = v1 (scripts/ict-scan.py V_ICT), stated so the overlay stays complete.
                fx_b_ex="iofed", fx_b_pd="r15", fx_b_pool="off", fx_b_buf="0", fx_b_exit="-2.0|H|floor",
                fx_b_lb="12|K", fx_b6="no", fx_b3="entry_tf", fx_b7="all_hours")


# scan()-relevant keys: everything `bt.scan()` / `ict_setups_live()` / `_fires_from()` / `walk()` actually read
# from `bt.OPTS`, audited against scripts/backtest-methods.py 2026-09-27 (grep `OPTS\[` there before trusting
# this list again -- if a future change makes another key scan()-relevant and it is not added here, two
# configs that should produce DIFFERENT trades would collide in the scan cache and silently share one wrong
# answer). `min_rr`/`combined_entry`/`ict_target` are simulate()-only or dead and stay excluded.
#
# `mgmt` belongs here even though it READS like a simulate()-only trade-management knob: `walk()` (called from
# both the WYCKOFF-BOOK/COMBINED-BOOK leg and ict_setups_live(), i.e. from inside scan() itself) applies the
# breakeven-at-+1R rule to the bar-by-bar outcome (backtest-methods.py:364) BEFORE the trade record ever
# reaches simulate() -- R, outcome and exit_time all depend on it. First cut of this file omitted `mgmt` on
# the mistaken belief that it was simulate()-only, which the acceptance run (D:/tmp-tests/speed/accept.log)
# caught immediately: CONFIGS' A/B/C rows differ in (mgmt, htf) on every one of the three pairs (A: none/False,
# B: be/False, C: be/True), so for THIS CONFIGS matrix no two configs actually share a scan() -- the dedup in
# build_scan_tasks() is correct infrastructure that currently happens to be a no-op for these three rows, and
# the real, unaffected speed win is the parallel pool across the (now three, not two) distinct scans.
#
# `methods` (the bias-reading dimensions `bt.resolve_methods(sym)` resolves) is scan()-relevant too but is
# carried as `_scan_cache_key()`'s own separate parameter, not a member of this tuple: it comes from
# /automation per-SYMBOL, not from a CONFIGS overlay, so it has no `overlay[k]` to read here -- folding it into
# this list would make every lookup site pass a fake key into `overlay` just to satisfy the loop.
_SCAN_RELEVANT_KEYS = ("mgmt", "htf", "sides", "st_gate", "phase_b_gate", "sloped_gate", "st_min", "types", "entry", "phase_d",
                       # A0 (2026-09-29): walk() closes a position before the server's daily rollover when these are
                       # set, so they change R/outcome/exit_time inside scan() and MUST separate cache entries.
                       "flat_before_rollover", "rollover_provider",
                       # B1/Batch-1a (2026-09-29): ict_setups_live() (called from inside scan()) reads these
                       # four directly off OPTS (backtest-methods.py FX_ICT_KEYS) and passes them into
                       # ict-scan.py's analyze()/setup_candidate(), which can change which ICT setups fire --
                       # MUST separate cache entries, same reasoning as every other key above.
                       "fx_b2a_fvg_in_leg", "fx_b2b_ce_fail", "fx_b1_pivot1", "fx_braid_optional",
                       # Batch 1(b) F items (2026-09-29, docs/plans/2026-09-28-methodology-improvement-plan.md
                       # §3): fx_w1/w2/w3/w5 change `_wyckoff_candidates` detection itself (bridged into
                       # wyckoff_rules.PARAMS -- see backtest-methods._FX_WYCKOFF_DETECTION_KEYS and the
                       # `_WY_CANDIDATES` cache key in scan()); fx_w7 changes `_fires_from`'s Phase-D
                       # target/placeability. All five change scan()'s trades and MUST separate cache entries.
                       "fx_w1_tr_low_st", "fx_w2_st_below_sc", "fx_w3_mSOW_spring", "fx_w5_vp_abandon",
                       "fx_w7_htf_target",
                       # O1 (2026-09-30): changes which candidates simulate() admits (min_rr) -> must separate cache
                       # entries / config identity.
                       "fx_admission_entry_cost",
                       # C3 (2026-10-02): changes the R / outcome of trades whose stop bar opened beyond the stop (walk()).
                       "fx_gap_fill",
                       # D3 (2026-10-02): changes which ICT setups are refused as already triggered / when they fill.
                       "fx_fvg_formed_start",
                       # Batch 2(a) Wyckoff V items: fx_w4a_linger_closes / fx_w_tw change DETECTION (per-call P=
                       # overrides, `_WY_CANDIDATES` key); fx_w6_window changes the window scan() walks;
                       # fx_w_stop / fx_w_spt / fx_w_touch change `_fires_from`'s stop / target / gate. All six
                       # change scan()'s trades and MUST separate cache entries.
                       "fx_w_stop", "fx_w4a_linger_closes", "fx_w6_window", "fx_w_spt", "fx_w_touch", "fx_w_tw",
                       # A2b decision side: htf_bias_gate refuses a stale HTF tier, so scans with it on/off differ.
                       "fx_a2b_stale_htf_block",
                       # Batch 2(a) ICT V items: fx_b_ex/pd/pool/buf/exit(target)/lb/b6/b3/b7 all change which ICT
                       # trades scan() emits (entry/stop/target, setups, expiry, fills, horizon), so all nine
                       # separate scan-cache entries. (fx_b_exit's 2R-floor component acts in simulate(), but it
                       # is one joint key, so it is keyed here whole.)
                       "fx_b_ex", "fx_b_pd", "fx_b_pool", "fx_b_buf", "fx_b_exit", "fx_b_lb", "fx_b6", "fx_b3",
                       "fx_b7")


def _hashable(v):
    return tuple(v) if isinstance(v, list) else v


def _scan_cache_key(sym, tf, overlay, methods):
    """The cache key two (sym, tf, config) calls share iff `bt.scan(sym, tf)` would produce byte-identical
    trades for both -- see `_SCAN_RELEVANT_KEYS`'s docstring for what "relevant" means here and why the list
    must be re-audited whenever scan()'s own OPTS reads change. `methods` is `bt.resolve_methods(sym)`'s
    result, passed in rather than recomputed here so every caller derives it the same one way."""
    return (sym, tf) + tuple(_hashable(overlay[k]) for k in _SCAN_RELEVANT_KEYS) + (methods,)


def _worker_scan(sym, tf, overlay):
    """One (symbol, timeframe, config-overlay) scan, run in a `ProcessPoolExecutor` worker. Windows has no
    fork(): each worker is a fresh interpreter that re-imports this file as `__main__` (the `if __name__ ==
    "__main__"` guard at the bottom stops it from recursing into main() again, but every top-level statement
    above that guard -- including the `bt = importlib.util.module_from_spec(...)` a few lines up -- still runs,
    so the worker already has its OWN independent `bt` module by the time this function is called; no separate
    per-worker import is needed). `opts=overlay` is `bt.scan()`'s own OPTS-isolation parameter
    (docs/audits/2026-09-24-system-audit.md "OPTS isolation"), so this call depends on nothing the worker's
    global `bt.OPTS` happens to hold and mutates nothing either -- required for correctness here since nothing
    in this process ever calls `bt.OPTS.update()` before dispatching work to the pool.

    INVARIANT this relies on (see `dataset_last_bar()`'s own docstring for the other half): `bt.QUALITY_FLAGS`
    / `bt.assess_run()` correctness under `--workers > 1` depends ENTIRELY on `dataset_last_bar()` having
    already called `bt.load()` for every requested (symbol, timeframe) in the MAIN process before any task is
    dispatched here -- a worker's own `bt.load()` call (inside `bt.scan()`) always re-runs the §20/§38 quality
    assessment fresh, because this is a SEPARATE process with an empty `bt._ASSESSED` cache, but the result
    only needs to reach the MAIN process's `bt.QUALITY_FLAGS` once, and it already did.

    What is suppressed here, and why it is safe to suppress: the worker's OWN `print(..., file=sys.stderr)`
    inside `bt.load()` -- never the assessment itself (`bt._ASSESSED`/`bt.QUALITY_FLAGS` inside the WORKER'S
    OWN process still run normally; only that process's copy is ever discarded, exactly as it already was
    before this function existed). Without suppression, a single flagged (sym, tf) prints once per WORKER that
    happens to scan it (baseline, one process, prints it exactly once) -- observed as 1 line in the sequential
    run vs 4 in a 3-worker run for crypto_1h_noacct (D:/tmp-tests/speed/accept.log fix-round-1 note). Anything
    else a worker call ever writes to stderr (there is nothing else on scan()'s call path today, per the
    `OPTS\\[` audit `_SCAN_RELEVANT_KEYS` cites -- this stays a filter, not a blanket redirect, so a FUTURE
    stderr write on that path is not silently swallowed) passes through unchanged.

    Returns `(scan result, loads)`: `loads` is every (symbol, timeframe) `bt.load()` was first asked for during
    this scan, in call order -- including series the scan reaches on its own (the HTF companion
    `htf_bias_gate()` loads for `htf=True`), which `dataset_last_bar()` never loaded. The main process replays
    exactly these `bt.load()` calls at the point in its loop where the sequential engine would have run this
    scan (see `_scan_for()` in main), so `bt.QUALITY_FLAGS`, `bt.PROVIDERS_SEEN` and the DATA-QUALITY stderr
    lines end up with the same content in the same order as a one-process run -- the §38 verdict does not
    depend on which process happened to scan a series.
    """
    loads, seen, real_load = [], set(), bt.load

    def traced(s, t):
        if (s, t) not in seen:
            seen.add((s, t)); loads.append((s, t))
        return real_load(s, t)

    buf = io.StringIO()
    bt.load = traced          # scan() and everything it calls reach load() through bt's module globals
    try:
        with contextlib.redirect_stderr(buf):
            result = bt.scan(sym, tf, opts=overlay)
        return result, loads
    finally:
        # In `finally`, so whatever the scan printed before an exception still reaches stderr -- the failed
        # attempt's diagnostics are exactly what a run that exhausts its retries needs to be explainable.
        bt.load = real_load
        for line in buf.getvalue().splitlines(keepends=True):
            if not line.startswith("DATA-QUALITY FLAG"):
                sys.stderr.write(line)


def build_scan_tasks(tfs, syms, cfg_overlays, methods_by_sym):
    """Every (symbol, timeframe, config) this run needs a `bt.scan()` for, DEDUPED to the distinct scans that
    will actually differ (see `_scan_cache_key`/`_SCAN_RELEVANT_KEYS`) -- computed BEFORE any scan runs, so a
    caller can dispatch every distinct one in parallel instead of the main loop discovering cache hits one at
    a time. Deterministic order (tf outer, config middle -- `cfg_overlays` must be an ordered mapping, i.e. a
    plain dict in CONFIGS' own iteration order -- symbol inner, first-occurrence wins a repeated key): given
    the same three arguments this always returns the same list in the same order, which is what makes it
    unit-testable without running any scan at all. Returns a list of (sym, tf, overlay, key) tuples."""
    tasks, seen = [], set()
    for tf in tfs:
        for overlay in cfg_overlays.values():
            for sym in syms:
                key = _scan_cache_key(sym, tf, overlay, methods_by_sym[sym])
                if key in seen:
                    continue
                seen.add(key); tasks.append((sym, tf, overlay, key))
    return tasks


def run_scans(tasks, workers, executor_cls=_pool.IsolatedExecutor, max_retries=2,
              max_pool_rebuilds=6, max_crashes_per_task=5, disk=None, require_cached=False):
    """Execute every (sym, tf, overlay, key) in `tasks` (from `build_scan_tasks`), in parallel across
    `executor_cls` when `workers > 1` and there is more than one task, sequentially in THIS process otherwise
    (same `bt.scan(sym, tf, opts=overlay)` call either way -- see `_worker_scan`'s docstring for why the
    isolated call is required for correctness, not just for the parallel path). `executor_cls` defaults to
    `ProcessPoolExecutor` for real runs; tests inject a stand-in so pool-merge-order AND retry-after-failure
    can be exercised in-process, deterministically, without OS process spawn.

    Returns {key: scan result}. Correct regardless of the ORDER results complete in: each future is looked up
    by the key captured at SUBMISSION time (`futures = {ex.submit(...): key for ...}`), never by completion
    order or position, so a fast task finishing after a slow one cannot land under the wrong key.

    RETRY (this machine's RAM is documented as flaky -- a worker can segfault/get OOM-killed mid-scan and take
    the WHOLE pool down with it: the observed failure was `_wyckoff_candidates` -> `scan()` ->
    `_worker_scan()` dying inside a real 27-task run, D:/tmp-tests/speed-full/run.attempt1.log). `bt.scan()` is
    a deterministic, side-effect-free function of (sym, tf, opts) and the on-disk history files, which do not
    change for the duration of one run -- a retried task therefore produces the IDENTICAL result, so retrying
    is recovering from a hardware/OS event, never masking a correctness bug (contrast: CLAUDE.md §38 governs
    what to do about a RESULT that looks wrong, which this is not). On any exception from a future's
    `.result()` -- `BrokenProcessPool` (the whole pool died) or an ordinary exception from one worker -- the
    task is left OUT of the returned cache, logged to stderr, and retried against a FRESH pool (a new
    `executor_cls(...)` instance; a pool that lost a worker cannot be reused). Every OTHER task in the same
    batch that already produced a real result keeps it -- only tasks without one are resubmitted. A task still
    failing after `max_retries` retries (default 2, i.e. 3 total attempts) re-raises its last exception and
    the run fails loudly, exactly as an unretried failure always has.

    A RETRY round always goes back through `executor_cls`, even when exactly one task remains (the common
    shape of the failure this exists for: N-1 of N tasks already succeeded, 1 needs retrying) -- `round_num`
    below tracks this: only the very FIRST round (round_num == 0) may take the no-pool shortcut for a single
    task, matching the existing "a one-task RUN never pays pool-startup cost" behaviour for the ordinary,
    nothing-failed case, while every subsequent round honours "recreate the pool and resubmit" for a retry
    even down to a single straggler.

    TWO budgets, because the two failures mean different things. An ordinary exception from one task is that
    task's own failure: `max_retries` per task. A `BrokenProcessPool` is NOT: one segfaulting worker marks
    EVERY pending future of that pool broken, so charging it to each task spent all 27 tasks' retries on three
    unrelated hardware events (observed: D:/tmp-tests/speed-full/run2.attempt1.log, 27 x "attempt 2/3" and the
    run died). A broken pool is charged once to the RUN (`max_pool_rebuilds`), its unfinished tasks are
    resubmitted without spending their own budget, and past that budget the run fails loudly.

    The default executor is `isolated_pool.IsolatedExecutor` (one process per task), where a hardware crash
    fails only the crashed task's future with `WorkerCrashed`. That is charged to THAT task
    (`max_crashes_per_task`, default 5 -- generous, because on this machine a crash says nothing about the
    task) and it is resubmitted; a task that crashes every time is a deterministic fault, and after five it
    ends the run loudly rather than looping forever.

    `disk` (a `scan_cache.ScanCache`, `--scan-cache`): every task is looked up there first and only the misses
    are scanned; each fresh result is written back the moment it arrives, so a run that dies later keeps what
    it paid for. A hit is the stored `(result, loads)` pair `_worker_scan` itself returns, so the caller's
    replay of `loads` works unchanged. `require_cached=True` makes any miss fatal instead: a report job that
    expected every scan to be precomputed must not silently spend hours recomputing one."""
    cache = {}
    disk_keys = {}
    if disk is not None:
        todo = []
        for t in tasks:
            sym, tf, overlay, key = t
            disk_keys[key] = _sc.full_key(ROOT, bt, sym, key)
            hit = disk.get(disk_keys[key])
            if hit is not None:
                cache[key] = hit
            else:
                todo.append(t)
        if todo and require_cached:
            raise SystemExit(f"--require-cached: {len(todo)} scan(s) not in {disk.dir}: "
                             + ", ".join(f"{t[0]} {t[1]}" for t in todo))
        tasks = todo

    def _keep(key, res):
        cache[key] = res
        if disk is not None:
            disk.put(disk_keys[key], *res)
    pool_breaks = 0
    crashes = {t[3]: 0 for t in tasks}
    remaining = list(tasks)
    attempts = {t[3]: 0 for t in tasks}
    round_num = 0
    while remaining:
        if workers > 1 and (len(remaining) > 1 or round_num > 0):
            still_remaining = []
            broken = None
            with executor_cls(max_workers=min(workers, len(remaining))) as ex:
                futures = {ex.submit(_worker_scan, sym, tf, overlay): (sym, tf, overlay, key)
                          for sym, tf, overlay, key in remaining}
                for fut in futures:
                    sym, tf, overlay, key = futures[fut]
                    try:
                        _keep(key, fut.result())
                    except concurrent.futures.process.BrokenProcessPool as exc:
                        broken = exc                        # charged to the run below, not to this task
                        still_remaining.append((sym, tf, overlay, key))
                    except _pool.WorkerCrashed as exc:
                        crashes[key] += 1
                        if crashes[key] > max_crashes_per_task:
                            raise
                        print(f"run_scans: {sym} {tf} worker crashed ({exc}); crash {crashes[key]}/"
                              f"{max_crashes_per_task} for this task -- retrying in a fresh process",
                              file=sys.stderr)
                        still_remaining.append((sym, tf, overlay, key))
                    except Exception as exc:
                        attempts[key] += 1
                        if attempts[key] > max_retries:
                            raise
                        print(f"run_scans: {sym} {tf} failed (attempt {attempts[key]}/{max_retries + 1}): "
                              f"{type(exc).__name__}: {exc} -- retrying against a fresh pool", file=sys.stderr)
                        still_remaining.append((sym, tf, overlay, key))
            if broken is not None:
                pool_breaks += 1
                if pool_breaks > max_pool_rebuilds:
                    raise broken
                print(f"run_scans: worker pool died ({broken}); rebuild {pool_breaks}/{max_pool_rebuilds}, "
                      f"resubmitting {len(still_remaining)} unfinished task(s) "
                      f"({', '.join(f'{t[0]} {t[1]}' for t in still_remaining)}) -- retrying against a fresh pool",
                      file=sys.stderr)
            remaining = still_remaining
        else:
            still_remaining = []
            for sym, tf, overlay, key in remaining:
                try:
                    _keep(key, _worker_scan(sym, tf, overlay))
                except Exception as exc:
                    attempts[key] += 1
                    if attempts[key] > max_retries:
                        raise
                    print(f"run_scans: {sym} {tf} failed (attempt {attempts[key]}/{max_retries + 1}): "
                          f"{type(exc).__name__}: {exc} -- retrying", file=sys.stderr)
                    still_remaining.append((sym, tf, overlay, key))
            remaining = still_remaining
        round_num += 1
    return cache


def config_fee(cfg, market):
    """The per-side fee this config implies ON THIS MARKET, from risk-config.json's `costs` -- THE one source.

    Raises rather than defaulting: a market whose venue declares no cost cannot be priced, and guessing a fee
    is how a backtest comes to describe an account nobody has (CLAUDE.md §34, §38).
    """
    venue = _P.unattended_venue_for(market)
    costs = _RM._config()["costs"]
    if venue not in costs or not isinstance(costs[venue], dict):
        raise SystemExit(f"risk-config.json declares no costs for venue {venue!r} ({market}); refusing to "
                         f"price a backtest at a guessed fee")
    return costs[venue][f"{cfg['side']}_pct_per_side"]


def entry_order_type_for(cfg, method):
    """INT-4/PAR-2 (docs/audits/2026-09-24-system-audit.md): the ENTRY order type `simulate()` should price
    for this (config, method) pair -- and it is no longer simply `cfg["side"]`.

    Config A prices every method taker/taker on purpose (the "raw rule" baseline, unaffected by how any method
    actually enters). Configs B/C used to price EVERY method "maker" on both sides, which is right for ICT (a
    resting limit) but wrong for WYCKOFF-BOOK/COMBINED-BOOK (methods.json runner_methods[method].entry ==
    "market", i.e. taker) -- a CFD/crypto WYCKOFF-BOOK row in B/C was priced at the maker rate on both legs
    though its real entry is a market order and its exit (this file's own `simulate()` call) is ALWAYS taker.
    So for B/C the entry side comes from the METHOD's own declared entry, never from the config letter; only
    the EXIT side (always "taker", applied inside `simulate()` itself) is unconditional.
    """
    if cfg["side"] == "taker":
        return "taker"
    return "maker" if bt._M.RUNNER_METHODS[method]["entry"] == "limit" else "taker"
MIN_TRADES = 30

# INT-5 (docs/audits/2026-09-24-system-audit.md): setups used to be SELECTED on the same last-365-day window
# they were then judged on, so the pilot's "evidence" was the window the choice was fitted to. Every row now
# also carries an in-sample / out-of-sample split around a cutoff DERIVED FROM THE DATA (never typed):
#   cutoff     = the dataset's last bar DATE minus OOS_MONTHS calendar months, at 00:00Z
#   in-sample  = trades whose ENTRY is in [cutoff - IS_LOOKBACK_DAYS, cutoff)  -- selection gate 1 (ADR 0008 criteria)
#   OOS        = trades whose ENTRY is on/after the cutoff                      -- selection gate 2 (same criteria, held out)
# A trade opened before the cutoff belongs to in-sample even when it closes after it: membership is decided
# by the moment the decision was made (CLAUDE.md §8), never by an outcome. IS_LOOKBACK_DAYS keeps the
# in-sample basis the same length as the `--window 1y` ranking it replaces, shifted back to end at the cutoff.
# Each side is simulated as its OWN fresh START account (as `w1y` already was), so an OOS number never carries
# equity -- or a ruin -- earned in-sample. Consumer: scripts/rank-setups.py (ADR 0008 criteria selection).
OOS_MONTHS = 6
IS_LOOKBACK_DAYS = 365


def months_before(d, months):
    """`d` minus `months` CALENDAR months, clamped to the target month's last day (Aug 31 - 6 -> Feb 28/29)."""
    y, m = d.year, d.month - months
    while m <= 0:
        m += 12; y -= 1
    import calendar as _cal
    return datetime.date(y, m, min(d.day, _cal.monthrange(y, m)[1]))


def oos_cutoff(last_bar_time, months=OOS_MONTHS):
    """The OOS cutoff for a dataset whose last bar is `last_bar_time` (ISO string): its DATE minus `months`
    calendar months, as the same 'YYYY-MM-DDT00:00:00Z' string form the engine's bar times compare against."""
    return months_before(datetime.date.fromisoformat(last_bar_time[:10]), months).isoformat() + "T00:00:00Z"


def is_since_for(cutoff, lookback_days=IS_LOOKBACK_DAYS):
    return (datetime.date.fromisoformat(cutoff[:10]) - datetime.timedelta(days=lookback_days)).isoformat() + "T00:00:00Z"


def split_in_out(trades, cutoff, is_since=None):
    """(in_sample, oos) by ENTRY time only: in-sample = is_since <= entry < cutoff; OOS = entry >= cutoff.
    A trade exactly AT the cutoff is OOS; one opened before and closed after is in-sample."""
    ins = [t for t in trades if t["entry_time"] < cutoff and (is_since is None or t["entry_time"] >= is_since)]
    oos = [t for t in trades if t["entry_time"] >= cutoff]
    return ins, oos


def dataset_last_bar(symbols, tfs):
    """(last bar time across every series this run reads, [(sym, tf) actually present]). The cutoff is derived
    from THIS, so it moves with the data and is never a typed date.

    INVARIANT (relied on by `run_scans()`/`_worker_scan()` -- see their own docstrings for the other half):
    this loop calls `bt.load()`, in the MAIN process, for every REQUESTED (symbol, timeframe) BEFORE any
    `--workers > 1` scan is dispatched. `bt.load()` is where CLAUDE.md §20/§38 data-quality assessment happens
    (`bt._ASSESSED`/`bt.QUALITY_FLAGS`, module-level state), so by the time `main()` later builds `cfg_snap`/
    `validity = bt.assess_run(...)`, the MAIN process's own `bt.QUALITY_FLAGS` already carries every flag any
    requested series would produce -- regardless of whether the ACTUAL trade-detection scan for that series
    later runs here or in a worker process (whose own copy of that state is discarded when the worker
    returns; only its `bt.scan()` RESULT is ever collected, never its module globals). Without this call
    happening first, `assess_run()`'s §38 verdict would silently miss any quality fault whose series was only
    ever loaded inside a worker. This is NOT a general guarantee for every possible (sym, tf) `bt.scan()` can
    reach internally (e.g. an HTF companion series `htf_bias_gate()` loads only when a config sets
    `htf=True`) -- only for the REQUESTED set this function iterates. `--tf`/`--symbols` runs that cover the
    same rungs their own HTF companions live on (the common case: the default `--tf 15m,30m,1H,2H,4H,1D`
    ladder) are fully covered; a narrower ad hoc subset is covered for everything this function itself loads.
    """
    last, present = None, []
    for tf in tfs:
        for sym in symbols:
            c, _src = bt.load(sym, tf)
            if not c:
                continue
            present.append((sym, tf))
            if last is None or c[-1]["time"] > last:
                last = c[-1]["time"]
    return last, present


def _plain(v):
    """A §39 value as a plain float, or None when it is an unavailable() marker (never a fake 0)."""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict) and "unavailable" not in v:
        for k in ("value", "fraction"):
            if isinstance(v.get(k), (int, float)):
                return float(v[k])
    return None


def window_block(trades, fee, account, entry_type, since, until):
    """One side of the IS/OOS split: simulated as a fresh START account, summarised with the same metrics()
    the `w1y` block uses, plus the four numbers the OOS gate reads, as plain values."""
    f, c, tk = bt.simulate(trades, fee, account=account, entry_order_type=entry_type, live_parity_sizing=True)
    w = metrics(c, since, until, tk, f, bt.max_dd(c)); w.pop("years", None); w.pop("quarters", None)
    w.update(since=since[:10], until=until[:10], net_pnl=f - bt.START,
             expectancy_R=_plain(w["perf"].get("expectancy")), profit_factor=_plain(w["perf"].get("profit_factor")))
    w.update(monthly_block(c, since, until, f))
    return w


def calendar_months(since, until):
    """Every calendar month 'YYYY-MM' touched by [since, until], in order -- including months with no trade."""
    y, m = int(since[:4]), int(since[5:7]); ey, em = int(until[:4]), int(until[5:7]); out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}"); m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def monthly_block(curve, since, until, final):
    """ADR 0008 / selection-criteria.json inputs for one window. Each CALENDAR month's return is the equity at
    that month's last booked point vs the previous month's, so a month with no trade is a 0% month, never a
    missing one (period_returns() skips such months). The first and last months are partial when the window does
    not start/end on a month boundary, and are flagged. `m_mean_geo` is the geometric mean monthly return over the
    window's exact length (30.4375-day months), so partial months cannot distort it."""
    eq_end = {}
    for t, e in curve:
        eq_end[t[:7]] = e
    months, prev = [], bt.START
    for k in calendar_months(since, until):
        e = eq_end.get(k, prev)
        months.append(dict(month=k, ret_pct=round((e / prev - 1) * 100, 4))); prev = e
    if months:
        months[0]["partial"] = since[8:10] != "01"
        months[-1]["partial"] = True  # a window ends at a cutoff or at the dataset's last bar, never on a month end we can assert
    days = max((datetime.date.fromisoformat(until[:10]) - datetime.date.fromisoformat(since[:10])).days, 1)
    rets = [x["ret_pct"] for x in months]
    return dict(months=months,
                m_mean_geo=((final / bt.START) ** (30.4375 / days) - 1) * 100,
                m_losing=sum(1 for v in rets if v < 0),
                m_worst=min(rets) if rets else 0.0)


def metrics(curve, first, last, taken, final, dd, account=None, full_taken=None, full_curve=None):
    q = [v for _, v in bt.period_returns(curve, first, last, bt.quarter_key)]
    y = bt.period_returns(curve, first, last, bt.year_key)
    days = (datetime.date.fromisoformat(last[:10]) - datetime.date.fromisoformat(first[:10])).days or 1
    sd = statistics.pstdev(q) if len(q) > 1 else 0.0
    # CLAUDE.md §39's twenty-three, additively, from the ONE computer. The row's own keys are unchanged --
    # rank-setups.py reads `ann`, `q_pos`, `y_pos`, `ruin`, `stab` positionally -- but `stab` is no longer the
    # only risk-adjusted number available: it is a quarterly Sharpe-family quantity under a different name,
    # and `perf.sharpe` / `perf.sortino` are now beside it, per trade and labelled as such.
    # §39's probability metrics (risk_of_ruin, account_failure_probability, prop_pass_probability) must be
    # estimated over the FULL trade population, not over the account run's truncated one. `simulate(account=)`
    # STOPS at the first breach, so `taken` under an account is "the trades before it broke" -- on the crypto
    # demo profile that is 5-16 trades, and bootstrapping them resamples a sequence already conditioned on
    # ending in failure. The account's RULES still apply (they are what the bootstrap tests each resampled path
    # against); only the sample they are tested on is the untruncated one. `failed_by` on the row stays what it
    # was: a fact about the one real path. Fixed 2026-09-19 when ranking by prop-pass returned nothing for
    # crypto because every row's n had collapsed to the length of its own failure.
    pop, pop_curve = (full_taken, full_curve) if full_taken is not None else (taken, curve)
    pop_days = days or 1
    perf = _perf.metrics(pop, equity=pop_curve, account=account,
                         trades_per_year=(len(pop) * 365 / pop_days) if pop else None)
    return dict(n=len(pop), n_until_account_failure=len(taken), ann=((final / bt.START) ** (365 / days) - 1) * 100, dd=dd, final=final, ruin=bt.SIM_LAST["ruin"], q_pos=sum(1 for v in q if v > 0) / len(q) * 100 if q else 0, q_worst=min(q) if q else 0,
                q_med=statistics.median(q) if q else 0, q_mean=statistics.mean(q) if q else 0, q_sd=sd, stab=(statistics.mean(q) / sd * len(q) ** 0.5) if sd else 0,
                y_pos=sum(1 for _, v in y if v > 0), y_n=len(y), years=y, quarters=q, perf=perf)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="15m,30m,1H,2H,4H,1D"); ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT"); ap.add_argument("--out"); ap.add_argument("--json")
    # A0b (docs/plans/2026-09-28-methodology-improvement-plan.md): `choices` used to list six target models
    # (range/std2/std25/std4/erl_next/irl), but scripts/ict-scan.py's setup_candidate() has read none of them
    # since the six-way switch (bt.ict_target()) was deleted from the engine 2026-09-13
    # (scripts/strategy-runner.py:22; scripts/tests/test_live_rules.py test_ict_target_engine_is_gone) -- the
    # scanner always targets the -2sigma projection first, falling back to the dealing-range edge. Restricted
    # to the one value the scanner actually implements rather than removed outright, because
    # scripts/rank-setups.py:156 reads run_params.ict_target to NAME a system, and every existing pilot
    # selection was named from this default (docs/architecture/pilot-selection.json) -- keeping the label
    # "range" stable preserves those names. See the recorded `ict_target_effective` note (scripts/snapshot.py)
    # for what the scanner actually does.
    ap.add_argument("--ict-target", default="range", choices=["range"],
                    help="kept for scripts/rank-setups.py system-naming continuity only; the scanner does not "
                         "read this value (A0b) -- see setup.ict_target_effective in the config snapshot")
    # CLAUDE.md §33: a personal account and a prop account do not lose the same way, so "did this setup
    # survive?" has no answer until you say WHOSE account. Without one the only loss condition is a blown
    # balance (the personal notion) and §39's money/ruin/failure/pass metrics stay UNAVAILABLE BY NAME.
    ap.add_argument("--account", help="an §33 profile id from docs/architecture/account-profiles.json")
    ap.add_argument("--account-file", help="a JSON profile to EVALUATE against without shipping it as "
                                           "configuration -- for asking 'what would this look like under my "
                                           "prop firm's rules?' when no such account exists here (§57)")
    # Speed-only (CLAUDE.md §57: no new services/queues, stdlib concurrent.futures only): how many OS
    # processes may run bt.scan() calls in parallel. Bounded to len(distinct scans) at the call site below, so
    # a small run never pays pool-startup cost for workers it cannot use. Default is conservative (not
    # os.cpu_count()) because this machine's RAM is flaky under heavy parallel load; raise it explicitly on a
    # box known to have headroom. --workers 1 disables the pool and runs every scan in this process, exactly
    # as before this option existed.
    ap.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1),
                    help="parallel bt.scan() worker processes (default: min(4, cpu_count)); 1 = sequential, in-process")
    # Scan cache (owner-approved 2026-09-28, scripts/scan_cache.py): a scan does not depend on --account, so the
    # four accounts of one market share it. On GitHub Actions one job per scan fills the cache (--scan-only
    # --scan-configs X) and the report jobs read it (--require-cached), so no job runs 72 scans in a row.
    ap.add_argument("--scan-cache", help="directory of precomputed scans to read and extend (scripts/scan_cache.py)")
    ap.add_argument("--require-cached", action="store_true", help="fail if any scan is missing from --scan-cache")
    ap.add_argument("--scan-only", action="store_true", help="fill --scan-cache and stop; no report")
    ap.add_argument("--scan-configs", help="with --scan-only: only these CONFIGS letters, e.g. A or A,C")
    ap.add_argument("--list-scans", action="store_true",
                    help="print the distinct scans of this --tf/--symbols as JSON [{symbol, tf, config}] and stop")
    a = ap.parse_args(); today = datetime.date.today().isoformat(); rows = []
    if a.scan_configs and not a.scan_only:
        raise SystemExit("--scan-configs only restricts --scan-only: a report over some configs would be a partial "
                         "stability file that looks complete")
    if (a.scan_only or a.require_cached) and not a.scan_cache:
        raise SystemExit("--scan-only / --require-cached need --scan-cache")
    if a.list_scans:
        syms, tfs = a.symbols.split(","), a.tf.split(",")
        mbs = {sym: bt.resolve_methods(sym) for sym in syms}
        out, seen = [], set()
        for tf in tfs:
            for cname, cfg in CONFIGS.items():
                ov = config_opts(cfg, a.ict_target)
                for sym in syms:
                    k = _scan_cache_key(sym, tf, ov, mbs[sym])
                    if k not in seen:
                        seen.add(k); out.append(dict(symbol=sym, tf=tf, config=cname))
        print(json.dumps(out))
        return
    disk = _sc.ScanCache(a.scan_cache, ROOT) if a.scan_cache else None
    if a.scan_only:
        wanted = a.scan_configs.split(",") if a.scan_configs else list(CONFIGS)
        unknown = [c for c in wanted if c not in CONFIGS]
        if unknown:
            raise SystemExit(f"--scan-configs: unknown config(s) {unknown}; known {list(CONFIGS)}")
        syms, tfs = a.symbols.split(","), a.tf.split(",")
        mbs = {sym: bt.resolve_methods(sym) for sym in syms}
        tasks = build_scan_tasks(tfs, syms, {c: config_opts(CONFIGS[c], a.ict_target) for c in wanted}, mbs)
        run_scans(tasks, max(1, min(a.workers, len(tasks) or 1)), disk=disk)
        print(disk.summary(), file=sys.stderr)
        return
    # THE one loader (A3, docs/plans/2026-09-18-close-feature-gaps.md §0.3): this used to be five lines
    # duplicated inline here and again in backtest-methods.py main(); `bt.load_account` is now the only place
    # "--account and --account-file are two different answers" is enforced, so the two reports cannot drift
    # on what the flag means.
    account = bt.load_account(a)
    if account:
        print(f"account rules in force: {account['id']} ({account.get('context_type')}) -- a run ends when THIS "
              f"account would have failed, not only when the balance is gone", file=sys.stderr)
    # The market names the venue, and the venue names the fee. Derived from the run's own symbols so a CFD run
    # cannot be priced on a crypto schedule (the defect this replaced).
    market = _I.market_of(a.symbols.split(",")[0])
    if market is None:
        raise SystemExit(f"{a.symbols.split(',')[0]} is not on the instrument allowlist; refusing to guess a "
                         f"market, a venue, or a fee")
    last_bar, present_series = dataset_last_bar(a.symbols.split(","), a.tf.split(","))
    if last_bar is None:
        raise SystemExit("no history for any requested (symbol, timeframe); nothing to measure")
    cutoff = oos_cutoff(last_bar); is_since = is_since_for(cutoff)
    print(f"OOS holdout (INT-5): dataset last bar {last_bar} -> cutoff {cutoff}; in-sample from {is_since}",
          file=sys.stderr)
    tfs = a.tf.split(","); syms = a.symbols.split(",")
    # bt.resolve_methods(sym) only depends on /automation (never on --account, --ict-target or any CONFIGS
    # key) -- resolved once per symbol here rather than once per (tf, config, symbol) call below.
    methods_by_sym = {sym: bt.resolve_methods(sym) for sym in syms}
    cfg_overlays = {cname: config_opts(cfg, a.ict_target) for cname, cfg in CONFIGS.items()}
    scan_tasks = build_scan_tasks(tfs, syms, cfg_overlays, methods_by_sym)
    workers = max(1, min(a.workers, os.cpu_count() or 1, len(scan_tasks) or 1))
    print(f"scan plan: {len(scan_tasks)} distinct scan(s) across {len(tfs)} timeframe(s) x {len(cfg_overlays)} "
          f"config(s) x {len(syms)} symbol(s), {workers} worker process(es)", file=sys.stderr)
    # --workers 1 is the old engine, call for call: scans run lazily inside the loop exactly where they always
    # did, so its output (JSON, markdown AND stderr order) is the reference the parallel path is judged against.
    scan_cache = (run_scans(scan_tasks, workers, disk=disk, require_cached=a.require_cached)
                  if workers > 1 or disk is not None else None)
    if disk is not None:
        print(disk.summary(), file=sys.stderr)

    def _scan_for(sym, tf, overlay):
        if scan_cache is None:
            return bt.scan(sym, tf)
        result, loads = scan_cache[_scan_cache_key(sym, tf, overlay, methods_by_sym[sym])]
        for s, t in loads:    # replay, in this process and at this point, the loads the worker's scan made
            bt.load(s, t)
        return result
    for tf in tfs:
        for cname, cfg in CONFIGS.items():
            fee = config_fee(cfg, market)
            overlay = cfg_overlays[cname]
            bt.OPTS.update(overlay)
            scans = [s for s in (_scan_for(sym, tf, overlay) for sym in syms) if s]
            if not scans:
                continue
            first = min(s["first"] for s in scans); last = max(s["last"] for s in scans)
            since = (datetime.date.fromisoformat(last[:10]) - datetime.timedelta(days=365)).isoformat() + "T00:00:00Z"
            for m in METHODS:
                tr = [t for s in scans for t in s["trades"][m]]
                # INT-4/PAR-2, PAR-4/DEC-4 (docs/audits/2026-09-24-system-audit.md): entry priced by THIS
                # method's own declared entry (never blindly "maker" for every method in configs B/C), exit
                # always taker (inside simulate() itself); sizing matches strategy-runner's own fee-aware,
                # notional-cap-aware, loss-throttled formula.
                entry_type = entry_order_type_for(cfg, m)
                final, curve, taken = bt.simulate(tr, fee, account=account, entry_order_type=entry_type, live_parity_sizing=True)
                failed_by, acct_id = bt.SIM_LAST["failed_by"], bt.SIM_LAST["account"]
                # The same trades WITHOUT the account's stop, so the §39 probabilities have the whole
                # population to resample (see metrics() -- the account's rules still gate every path).
                f_full, c_full, t_full = (bt.simulate(tr, fee, entry_order_type=entry_type, live_parity_sizing=True) if account else (final, curve, taken))
                row = dict(tf=tf, cfg=cname, method=m, first=first[:10], last=last[:10],
                           failed_by=failed_by, account=acct_id,
                           **metrics(curve, first, last, taken, final, bt.max_dd(curve), account=account,
                                     full_taken=t_full, full_curve=c_full))
                # last-365-day window (reported only; the 1-year ranking that read it was removed by ADR 0008)
                tr1 = [t for t in tr if t["entry_time"] >= since]
                f1, c1, tk1 = bt.simulate(tr1, fee, account=account, entry_order_type=entry_type, live_parity_sizing=True)
                w = metrics(c1, max(first, since), last, tk1, f1, bt.max_dd(c1)); w.pop("years", None); w.pop("quarters", None)
                row["w1y"] = dict(w, since=since[:10])
                # INT-5: the in-sample / OOS split around the data-derived cutoff (see OOS_MONTHS above).
                t_in, t_out = split_in_out(tr, cutoff, is_since)
                row["oos6m"] = dict(cutoff=cutoff, dataset_last_bar=last_bar, split="entry_time",
                                    in_sample=window_block(t_in, fee, account, entry_type, max(first, is_since), cutoff),
                                    oos=window_block(t_out, fee, account, entry_type, max(first, cutoff), last))
                rows.append(row)
            print(f"{tf} {cname} done", file=sys.stderr)
    ok = [r for r in rows if r["n"] >= MIN_TRADES]
    ok.sort(key=lambda r: (r["ruin"] is None, r["q_pos"], r["q_worst"], r["stab"]), reverse=True)
    L = [f"# Độ ổn định theo thời gian của các phương pháp — {today} — target ICT: {a.ict_target}", "",
         "_`scripts/stability-report.py`. Xếp hạng theo: tỉ lệ quý dương → quý tệ nhất → tỉ số ổn định (trung bình quý / σ quý × √số quý). Chỉ xếp hạng dòng có ≥ 30 lệnh; tài khoản $10.000, CHÁY khi vốn ≤ $1.000 (dừng, ghi ngày, xếp cuối). Cấu hình A = phí taker 0,05 %, không quản lý; B = phí maker 0,02 % + hoà vốn tại +1R (WMT p272); C = B + lọc khung lớn (luật biên). Cả long lẫn short. Mọi số là của proxy bằng code (xem docstring của `backtest-methods.py` và `wyckoff_rules.py`)._", "",
         "## Bảng xếp hạng (mọi khung, mọi cấu hình)", "",
         f"| # | Khung | Cấu hình | Phương pháp | Lệnh | Vốn cuối (từ ${bt.START:,.0f}) | %/năm | Sụt giảm tối đa | Quý dương | Quý tệ nhất | Quý trung vị | Ổn định | Năm dương | Giai đoạn |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(ok[:30], 1):
        fin = f"CHÁY {r['ruin'][:10]}" if r["ruin"] else f"${r['final']:,.0f}"
        L.append(f"| {i} | {r['tf']} | {r['cfg']} | {r['method']} | {r['n']} | {fin} | {r['ann']:+.1f}% | −{r['dd']:.1f}% | {r['q_pos']:.0f}% | {r['q_worst']:+.1f}% | {r['q_med']:+.1f}% | {r['stab']:+.2f} | {r['y_pos']}/{r['y_n']} | {r['first']}→{r['last']} |")
    L += ["", "## Toàn bộ kết quả theo khung", ""]
    for tf in a.tf.split(","):
        sub = [r for r in rows if r["tf"] == tf]
        if not sub:
            continue
        yrs = sorted({y for r in sub for y, _ in r["years"]})
        L += [f"### {tf} ({sub[0]['first']} → {sub[0]['last']})", "", "| Cấu hình | Phương pháp | Lệnh | Vốn cuối | %/năm | Sụt giảm | Quý dương | Quý tệ nhất | Ổn định | " + " | ".join(yrs) + " |", "|---|---|---|---|---|---|---|---|---|" + "---|" * len(yrs)]
        for r in sub:
            yv = dict(r["years"]); fin = f"CHÁY {r['ruin'][:10]}" if r["ruin"] else f"${r['final']:,.0f}"
            L.append(f"| {r['cfg']} | {r['method']} | {r['n']} | {fin} | {r['ann']:+.1f}% | −{r['dd']:.1f}% | {r['q_pos']:.0f}% | {r['q_worst']:+.1f}% | {r['stab']:+.2f} | " + " | ".join(f"{yv.get(y, 0):+.1f}%" for y in yrs) + " |")
        L.append("")
    md = "\n".join(L) + "\n"; print(md)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(md); print(f"-> {a.out}", file=sys.stderr)
    if a.json:
        # CLAUDE.md §10: a result must identify the data it was computed from. Before this, the only
        # top-level key above sixty rows of metrics was `generated` -- a DATE -- so "re-run this and see if
        # it still holds" had no defined meaning. The snapshot is additive (rank-setups.py reads `rows` and
        # is unaffected) and best-effort: a research run must not FAIL because a snapshot could not be taken,
        # but it must never silently claim one, so the failure is recorded in place of the snapshot.
        try:
            # Only the series that EXIST (and were therefore read): a requested (symbol, timeframe) with no
            # history file -- USOIL/UKOIL have no 15m -- used to make the whole snapshot fail with
            # FileNotFoundError, leaving the CFD runs with no dataset identity at all. The requested-but-absent
            # pairs are listed beside it, so the omission is recorded rather than silent.
            # bt.HISTORY_ROOT (code review, 2026-09-29), not a hardcoded data/history: `present_series` above
            # was built from `bt.load()`, which already honours BT_HISTORY_ROOT/a second provider's root
            # (data/history/ftmo) -- a hardcoded base here would either raise FileNotFoundError for a
            # symbol that only exists under the alternate root, or (for one that exists under both, e.g.
            # XAUUSD/XAGUSD) silently record the WRONG provider's provenance for bars bt.load() actually read.
            snap = snapshot.dataset_snapshot(present_series, base=bt.HISTORY_ROOT)
            absent = [f"{s}:{t}" for t in a.tf.split(",") for s in a.symbols.split(",") if (s, t) not in present_series]
            if absent:
                snap["requested_but_absent"] = absent
        except (OSError, ValueError, KeyError) as exc:
            snap = {"snapshot_error": f"{type(exc).__name__}: {exc}",
                    "_note": "CLAUDE.md §10: this run's dataset could not be identified; treat the result as "
                             "not reproducible."}
        # CLAUDE.md §11, the sibling block: the CONFIGURATION behind the numbers, captured BY VALUE. `RISK`
        # and `MIN_RR` are read at import from mutable config files, so without this a re-run after an edit
        # measures a different system while the old report still claims the old figures -- which is exactly
        # what happened when the risk ceiling moved 3% -> 1% on 2026-09-17.
        try:
            cfg_snap = snapshot.backtest_config_snapshot(
                bt, timeframes=a.tf.split(","), methods=METHODS, configs=CONFIGS,
                fee_pct=getattr(a, "fee_pct", None), ict_target=a.ict_target,
                dataset_snapshot_id=snap.get("snapshot_id"),
                # §35: the (market, timeframe) pair IS the Trading System, so the market is what lets the
                # snapshot name which system's declared dependencies this run was measuring. Derived from the
                # run's own symbols rather than passed in, so it cannot disagree with them.
                market=_I.market_of(a.symbols.split(",")[0]))
        except (OSError, ValueError, KeyError, AttributeError) as exc:
            cfg_snap = {"snapshot_error": f"{type(exc).__name__}: {exc}",
                        "_note": "CLAUDE.md §11: this run's configuration could not be captured; treat the "
                                 "result as not reproducible."}
        # CLAUDE.md §38, the third block: what this run's own evidence makes the rows above worth. It is
        # written HERE and not left to the consumer because rank-setups.py reads these files to choose what
        # the pilot trades, and a selection made from an unassessed research result is exactly the outcome
        # §38's last sentence forbids. `bt.assess_run` reads the engine's data-quality flags, its declared
        # execution assumptions and the configuration snapshot above; it is not a second opinion about them.
        validity = bt.assess_run(cfg_snap, run=f"stability-report {a.symbols} {a.tf} target={a.ict_target}")
        print(validity.describe(), file=sys.stderr)
        run_params = dict(symbols=a.symbols, tf=a.tf, ict_target=a.ict_target, account=a.account,
                          account_file=a.account_file, live_parity_sizing=True, entry_pricing="per-method (INT-4/PAR-2)")
        oos_meta = dict(months=OOS_MONTHS, dataset_last_bar=last_bar, cutoff=cutoff, in_sample_since=is_since,
                        in_sample_lookback_days=IS_LOOKBACK_DAYS, split="entry_time: entry < cutoff -> in-sample, "
                        "entry >= cutoff -> OOS; each side a fresh account", source="scripts/stability-report.py (INT-5)")
        json.dump(dict(generated=today, run_params=run_params, oos_holdout=oos_meta, dataset_snapshot=snap,
                       config_snapshot=cfg_snap, research_validity=validity.stamp(), rows=rows),
                  open(a.json, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
