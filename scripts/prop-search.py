#!/usr/bin/env python3
"""The owner's PRE-REGISTERED prop-challenge setup search (docs/plans/2026-09-27-prop-setup-search-
preregistration.md, CLAUDE.md §42-§45). Research integrity is the product here: a candidate space is
enumerated and committed BEFORE any candidate is evaluated (`plan`), every evaluated candidate -- pass or
fail -- is recorded as an immutable §42 experiment record (`run`), and the report lists every one of them
(`report`), never only the winners.

Usage:
    python scripts/prop-search.py plan
    python scripts/prop-search.py run [--only id1,id2] [--workers N]
    python scripts/prop-search.py report

Pass definition, budget and windows are the pre-registration's own (§2-§4), restated only as constants below
-- this file does not choose them. Candidate space (§5): the runnable methods (docs/architecture/methods.json
via scripts/methods.py) x configs A/B/C (scripts/stability-report.py CONFIGS) x timeframes 15m/1H/4H, per CFD
instrument (docs/architecture/instruments.json analysis.cfd) AND pooled per asset class
(docs/architecture/instruments.json display.<sym>.asset_class -- metals, indices).

Reused, not duplicated: scripts/backtest-methods.py (`scan`, `simulate`, `pit_cutoff`/`limit_bars` as the
load-time PIT seam), scripts/performance.py (`metrics`, the day-block bootstrap that reads each fund's
`max_daily_loss`), scripts/stability-report.py (`CONFIGS`, `config_opts`, `config_fee`,
`entry_order_type_for`), scripts/experiment.py (`Record`, `seal`, `write`, `load`), scripts/snapshot.py
(§10/§11 snapshots), scripts/account_profile.py (the two fund profiles), scripts/isolated_pool.py (one
process per candidate when `--workers` > 1).
"""
import argparse
import concurrent.futures
import datetime
import hashlib
import importlib.util
import json
import os
import random
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import experiment as X          # CLAUDE.md §42: the ONE reader/writer of the experiment store
import instruments as _I        # docs/architecture/instruments.json: analysis.cfd, display().asset_class
import methods as _M            # docs/architecture/methods.json: the runnable RUNNER_METHODS set
import account_profile as _AP   # the two fund profiles (research-only, docs/architecture/account-profiles.json)
import performance as _perf     # CLAUDE.md §39: the ONE computer for the twenty-three metrics
import snapshot as _snap        # CLAUDE.md §10/§11: dataset + configuration snapshots
import trading_system as _TS    # CLAUDE.md §35/§47: which Trading System (market, tf) resolves to
import isolated_pool as _pool   # one process per candidate, matching stability-report.py's own convention

PREREG_DOC = "docs/plans/2026-09-27-prop-setup-search-preregistration.md"
EXPERIMENT_DIR = os.path.join(ROOT, "docs", "experiments", "prop-search-2026-09-27")
# PLAN_PATH is always INSIDE the checkout -- it is the pre-registered, git-committed artifact `run` is
# checked against, and it stays exactly where a reviewer would look for it (never redirected by an env var).
PLAN_PATH = os.path.join(EXPERIMENT_DIR, "plan.json")
# RECORDS_DIR / SKIPPED_PATH / REPORT_PATH default inside the checkout for local use, but are overridable via
# environment variables (CLAUDE.md §58 "config via environment variables") so CI can write them OUTSIDE the
# work tree, matching .github/workflows/stability-full.yml's own reason for doing so: a file written inside
# the checkout makes the run's own code_version read dirty=true (snapshot.code_version), and a dirty run is
# not reproducible from its SHA alone (CLAUDE.md §46).
RECORDS_DIR = os.environ.get("PROP_SEARCH_RECORDS_DIR") or os.path.join(EXPERIMENT_DIR, "records")
SKIPPED_PATH = os.environ.get("PROP_SEARCH_SKIPPED_PATH") or os.path.join(EXPERIMENT_DIR, "skipped.json")
REPORT_PATH = os.environ.get("PROP_SEARCH_REPORT_PATH") or os.path.join(
    ROOT, "docs", "backtests", "2026-09-27-prop-setup-search.md")

# ---------------------------------------------------------------- the pre-registration's own numbers (§2-§4)
# Restated here as constants because every candidate's record needs them; NOT re-derived or re-decided --
# see PREREG_DOC for the owner decision behind each one.
VALIDATION_START = "2024-03-01T00:00:00Z"     # development ends here (exclusive)
VALIDATION_END = "2025-03-01T00:00:00Z"       # validation ends here (exclusive); history is truncated here (§4)
BUDGET_MAX = 200                              # §3: at most this many candidates evaluated on validation
TARGET_PASSES = 5                             # §3: a goal, not a stopping rule beyond the budget
PASS_PROB_THRESHOLD = 0.70                    # §2.1
FUNDS = ("ftmo-challenge-phase1", "the5ers-high-stakes-step1")
MIN_TRADING_DAYS = {"ftmo-challenge-phase1": 4, "the5ers-high-stakes-step1": 3}   # §2.2
TIMEFRAMES = ("15m", "1H", "4H")               # §5

# INTERPRETATION (no line in PREREG_DOC fixes this number): §2.1 asks for `prop_pass_probability` with
# "horizon = the number of trading days in the validation window", and CLAUDE.md §21 makes sessions/DST a
# first-class concern rather than something to eyeball. Read as calendar weekdays (Mon-Fri) in
# [VALIDATION_START, VALIDATION_END) -- deterministic, reproducible, and independent of any one instrument's
# own holiday calendar (which this repo does not carry for CFDs). If this undercounts a given venue's actual
# trading-day count by a holiday or two, the effect on the bootstrap's horizon is second-order.
EXPECTANCY_BOOTSTRAP_ITERATIONS = 2000
EXPECTANCY_BOOTSTRAP_SEED = 20260927           # the pre-registration's own date; fixed, reproducible (§46)
EXPECTANCY_LOWER_BOUND_CI = 0.90               # one-sided 90% CI lower bound (§2.3)
EXPECTANCY_MIN_N = 5                           # same floor as performance.py's own bootstrap metrics (§2.2:
                                                # "the bootstrap has the sample it needs to run at all")


def _weekday_count(start_iso, end_iso):
    """Calendar weekdays (Mon-Fri) in [start, end) -- see EXPECTANCY_BOOTSTRAP_ITERATIONS block above for why
    this, and not a per-venue trading calendar, is what `horizon` is computed from."""
    start = datetime.date.fromisoformat(start_iso[:10])
    end = datetime.date.fromisoformat(end_iso[:10])
    n = (end - start).days
    return sum(1 for i in range(n) if (start + datetime.timedelta(days=i)).weekday() < 5)


VALIDATION_TRADING_DAYS = _weekday_count(VALIDATION_START, VALIDATION_END)


# ---------------------------------------------------------------------------------------- candidate space (§5)

def _asset_class_groups():
    """{asset_class: [symbols]} over the CFD analysis list, in instruments.json's own declared order."""
    groups = {}
    for sym in _I.analysis("cfd"):
        ac = _I.display(sym).get("asset_class") or "cfd"
        groups.setdefault(ac, []).append(sym)
    return groups


def build_candidate_space():
    """The full pre-registered candidate list, in a STABLE, deterministic order (§5): method (alphabetical
    over the runnable set) x config (A, B, C) x timeframe (15m, 1H, 4H) x group (each instrument, in
    instruments.json's own order, THEN each asset class pooled group, alphabetically).

    `sr.CONFIGS` supplies the config letters in ITS OWN dict order (A, B, C) -- not re-sorted here, so a future
    reordering of CONFIGS is reflected rather than silently overridden by an alphabetical assumption that
    happens to agree with it today."""
    sr = _sr()
    methods_order = sorted(_M.runnable())
    config_names = list(sr.CONFIGS.keys())
    instruments = _I.analysis("cfd")
    classes = _asset_class_groups()
    groups = [("instrument", sym, [sym]) for sym in instruments]
    groups += [("asset_class", ac, list(classes[ac])) for ac in sorted(classes)]
    candidates = []
    for method in methods_order:
        for cfg_name in config_names:
            for tf in TIMEFRAMES:
                for group_kind, group_id, symbols in groups:
                    cid = f"{method}-{cfg_name}-{tf}-{group_id}"
                    candidates.append({
                        "id": cid, "method": method, "config": cfg_name, "timeframe": tf,
                        "group_kind": group_kind, "group_id": group_id, "symbols": symbols,
                    })
    return candidates


def _hash_candidates(candidates):
    payload = json.dumps(candidates, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------------------------------- `plan`

def cmd_plan():
    """Enumerate the candidate space and commit it to PLAN_PATH -- BEFORE any evaluation (§42/§43). Refuses to
    silently change an already-committed plan: per PREREG_DOC's own preamble, changing the pre-registration
    after the first evaluation is itself an experiment event that must be recorded with a reason, not a file
    this command may quietly overwrite."""
    candidates = build_candidate_space()
    plan_hash = _hash_candidates(candidates)
    if os.path.exists(PLAN_PATH):
        existing = json.load(open(PLAN_PATH, encoding="utf-8"))
        if existing.get("plan_hash") == plan_hash:
            print(f"plan unchanged: {len(candidates)} candidates, hash {plan_hash[:12]} "
                  f"(matches the committed {PLAN_PATH})")
            return existing
        raise SystemExit(
            f"refusing to change the committed plan at {PLAN_PATH}: the recomputed candidate space "
            f"({len(candidates)} candidates, hash {plan_hash[:12]}) differs from the committed one "
            f"({len(existing.get('candidates', []))} candidates, hash {existing.get('plan_hash', '?')[:12]}). "
            f"{PREREG_DOC}: changing the pre-registration after the first evaluation is itself an experiment "
            f"event and must be recorded in the ledger with the reason -- this command will not silently "
            f"regenerate plan.json.")
    os.makedirs(EXPERIMENT_DIR, exist_ok=True)
    payload = {
        "_source": PREREG_DOC,
        "generated_at": _now_iso(),
        "development_window": {"end": VALIDATION_START,
                               "note": "everything before this is development: free exploration (§4)"},
        "validation_window": {"start": VALIDATION_START, "end": VALIDATION_END},
        "budget_max": BUDGET_MAX, "target_passes": TARGET_PASSES,
        "pass_probability_threshold": PASS_PROB_THRESHOLD,
        "funds": {f: {"min_trading_days": MIN_TRADING_DAYS[f]} for f in FUNDS},
        "candidate_count": len(candidates),
        "plan_hash": plan_hash,
        "candidates": candidates,
    }
    with open(PLAN_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print(f"wrote {PLAN_PATH}: {len(candidates)} candidates, hash {plan_hash[:12]}")
    return payload


def load_plan():
    """The committed plan, refusing to run against one that no longer matches the recomputed candidate space
    (a drifted registry, an edited instruments.json, ...) -- `run` must never silently evaluate a different
    space than the one that was pre-registered."""
    if not os.path.exists(PLAN_PATH):
        raise SystemExit(f"no plan at {PLAN_PATH}; run `python scripts/prop-search.py plan` first")
    existing = json.load(open(PLAN_PATH, encoding="utf-8"))
    candidates = build_candidate_space()
    h = _hash_candidates(candidates)
    if h != existing.get("plan_hash"):
        raise SystemExit(
            f"{PLAN_PATH} no longer matches the recomputed candidate space (committed hash "
            f"{existing.get('plan_hash', '?')[:12]} != recomputed {h[:12]}); refusing to run against a stale "
            f"or altered plan. Re-run `plan` to see whether the registry drifted or the plan was edited.")
    return existing


# ---------------------------------------------------------------------------------- backtest-methods.py seam

_SR_CACHE = None


def _load_sr():
    """A fresh `scripts/stability-report.py` module -- which itself loads its OWN fresh `scripts/
    backtest-methods.py` at module-import time (see stability-report.py's own top-level `spec = ...` block).
    One `importlib` load gives us both: `sr.bt` (backtest-methods.py) and `sr.CONFIGS`/`sr.config_opts`/
    `sr.config_fee`/`sr.entry_order_type_for` (stability-report.py), always from the SAME `bt` instance, so
    `bt.pit_cutoff(...)` set here is the one `sr.config_opts`-driven `bt.scan()` calls read."""
    spec = importlib.util.spec_from_file_location("sr", os.path.join(ROOT, "scripts", "stability-report.py"))
    sr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sr)
    return sr


def _sr():
    """The MAIN PROCESS's cached `sr` -- used by `plan`/`load_plan`/`report`, which never scan and so may
    safely share one instance across calls. `_evaluate_candidate` (below) does NOT use this cache: it loads
    its own fresh instance so that `bt.pit_cutoff` / the load caches are the SAME predictable state whichever
    process (this one, sequentially, or a spawned worker) runs it."""
    global _SR_CACHE
    if _SR_CACHE is None:
        _SR_CACHE = _load_sr()
    return _SR_CACHE


# --------------------------------------------------------------------------------------- statistics not in performance.py

def expectancy_lower_bound(net_rs, *, iterations=EXPECTANCY_BOOTSTRAP_ITERATIONS,
                           seed=EXPECTANCY_BOOTSTRAP_SEED, min_n=EXPECTANCY_MIN_N):
    """PREREG_DOC §2.3: the one-sided 90% bootstrap lower bound of mean net R on the validation trades.

    Not one of CLAUDE.md §39's twenty-three (scripts/performance.py has no confidence-bound-on-expectancy
    metric), so this is a small, dedicated bootstrap rather than a repurposed one -- same style as
    performance.py's own probability bootstraps (fixed seed, percentile method, an explicit `min_n` floor
    below which the answer is `unavailable()` rather than a number nobody should trust). The floor matches
    performance.py's own `risk_of_ruin`/`prop_pass_probability` floor (5): PREREG_DOC §2.2 explicitly ties
    this rule to "the engine's own floor", not a separately invented one.

    Returns `{"value": ..., "method": ..., "iterations": ..., "seed": ..., "sample": n}` or
    `performance.unavailable(reason)` below `min_n`.
    """
    n = len(net_rs)
    if n < min_n:
        return _perf.unavailable(
            f"sample size {n} is below the {min_n} a bootstrap needs to resample at all -- the same floor "
            f"scripts/performance.py uses for risk_of_ruin/prop_pass_probability ({PREREG_DOC} §2.2)",
            owner="prop-search §2.3")
    rng = random.Random(seed)
    means = []
    for _ in range(iterations):
        means.append(sum(net_rs[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    idx = min(int(round((1.0 - EXPECTANCY_LOWER_BOUND_CI) * iterations)), iterations - 1)
    return {"value": means[idx],
           "method": f"bootstrap over the observed per-trade net R ({n} trades), resampled with replacement; "
                     f"one-sided {EXPECTANCY_LOWER_BOUND_CI:.0%} CI lower bound = the "
                     f"{(1 - EXPECTANCY_LOWER_BOUND_CI) * 100:.0f}th percentile of the resampled means",
           "iterations": iterations, "seed": seed, "sample": n}


def split_windows(trades):
    """(development, validation) by ENTRY time only (§4): development = entry_time < VALIDATION_START;
    validation = VALIDATION_START <= entry_time < VALIDATION_END. A trade AT exactly VALIDATION_START is
    validation (matching scripts/stability-report.py split_in_out's own boundary convention: "a trade exactly
    AT the cutoff is OOS"). A trade at/after VALIDATION_END would be exposed-reporting-only and is excluded
    from both; the engine's own PIT truncation at VALIDATION_END (bt.pit_cutoff) should make that case
    impossible for a candidate's own trades, but the boundary is written explicitly rather than relying on it.
    """
    dev = [t for t in trades if t["entry_time"] < VALIDATION_START]
    val = [t for t in trades if VALIDATION_START <= t["entry_time"] < VALIDATION_END]
    return dev, val


def evaluate_pass(metrics_by_fund, trading_days, expectancy_lb):
    """PREREG_DOC §2, all three criteria, evaluated together (a candidate must clear every one). Pure and
    side-effect-free so `run` (fresh evaluation) and `report`/resume (re-deriving PASS/FAIL from a previously
    sealed record's own `metrics` field) always agree -- there is no separate stored boolean to drift from the
    numbers that justify it.

    Returns `(passed: bool, detail: dict)` -- `detail` is written into the experiment record's `metrics` field
    so a reader can see exactly which sub-condition decided the outcome, per fund.
    """
    detail = {}
    ok = True
    for fund in FUNDS:
        m = metrics_by_fund[fund]
        p = m.get("prop_pass_probability")
        p_val = p.get("value") if isinstance(p, dict) and "value" in p else None
        p_ok = isinstance(p_val, (int, float)) and p_val >= PASS_PROB_THRESHOLD
        days_ok = trading_days >= MIN_TRADING_DAYS[fund]
        detail[fund] = {
            "prop_pass_probability": p, "threshold": PASS_PROB_THRESHOLD, "meets_threshold": p_ok,
            "min_trading_days_required": MIN_TRADING_DAYS[fund], "trading_days_observed": trading_days,
            "meets_min_trading_days": days_ok,
        }
        ok = ok and p_ok and days_ok
    expectancy_ok = isinstance(expectancy_lb, dict) and isinstance(expectancy_lb.get("value"), (int, float)) \
        and expectancy_lb["value"] > 0
    detail["expectancy_lower_bound"] = expectancy_lb
    detail["expectancy_positive"] = expectancy_ok
    return (ok and expectancy_ok), detail


# ------------------------------------------------------------------------------------------- one candidate

def _has_predevelopment_history(sym, tf):
    """§5: 'An instrument without history before 2024-03 cannot be developed on and is skipped, stated.'"""
    path = os.path.join(ROOT, "data", "history", f"ohlcv.{sym}.{tf}.json")
    if not os.path.exists(path):
        return False
    try:
        d = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return False
    candles = d.get("candles") or []
    return bool(candles) and candles[0]["time"] < VALIDATION_START


def _system_version_for(tf):
    try:
        sysd = _TS.for_market_tf("cfd", tf)
        full = _TS.get(sysd["id"])
        return {"id": sysd["id"], "version": full.get("version"),
               "source": "docs/architecture/trading-systems.json"}
    except (KeyError, Exception):
        return None


def _evaluate_candidate(candidate, sr=None):
    """Runs the existing engine (bt.scan + bt.simulate, unmodified semantics) over ONE candidate's symbols,
    truncated at the validation boundary (bt.pit_cutoff), and returns either `{"skip": reason}` (no history,
    doesn't count against budget) or `{"record": <plain dict, a sealed §42 record's fields>}`.

    `sr=None` (the default, and always the value used by a spawned worker -- see `_load_sr`'s own docstring)
    loads a fresh `sr`/`bt` here; `cmd_run`'s sequential (`--workers 1`) path passes the cached one so repeated
    calls in the SAME process reuse `bt`'s own load/detection caches for speed, matching stability-report.py's
    own dedup philosophy. `bt.pit_cutoff` is reset to the SAME constant (VALIDATION_END) on every call
    regardless of which `bt` instance is used, so cache reuse changes nothing about what is measured.
    """
    sr = sr or _load_sr()
    bt = sr.bt
    method, cfg_name, tf = candidate["method"], candidate["config"], candidate["timeframe"]
    symbols = list(candidate["symbols"])
    usable = [s for s in symbols if _has_predevelopment_history(s, tf)]
    skipped_syms = [s for s in symbols if s not in usable]
    if not usable:
        return {"skip": f"no instrument in {candidate['id']} has history before {VALIDATION_START} at {tf} "
                        f"-- {symbols} all lack pre-development-window history ({PREREG_DOC} §5)"}

    bt.pit_cutoff(VALIDATION_END)   # CLAUDE.md §8 / PREREG_DOC §4: nothing after validation reaches this run
    bt.limit_bars(None)
    cfg = sr.CONFIGS[cfg_name]
    overlay = sr.config_opts(cfg, ict_target="range")
    scans = [s for s in (bt.scan(sym, tf, only=(method,), opts=overlay) for sym in usable) if s]
    if not scans:
        return {"skip": f"{candidate['id']}: bt.scan() produced no series for {usable} at {tf}"}
    trades = [t for s in scans for t in s["trades"][method]]
    fee = sr.config_fee(cfg, "cfd")
    entry_order_type = sr.entry_order_type_for(cfg, method)

    dev_trades, val_trades = split_windows(trades)

    def _population(trs):
        # No `account=` here on purpose (matching scripts/stability-report.py's own `metrics()` helper):
        # `simulate(account=...)` STOPS the run at the account's first breach, which would bootstrap a
        # population already conditioned on failure. The account's RULES still gate the bootstrap itself
        # (passed as `account=` to performance.metrics below); only the POPULATION it resamples is the full,
        # unconstrained one.
        return bt.simulate(trs, fee, entry_order_type=entry_order_type, live_parity_sizing=True)

    dev_final, dev_curve, dev_taken = _population(dev_trades)
    val_final, val_curve, val_taken = _population(val_trades)

    trading_days = len({t["entry_time"][:10] for t in val_taken})
    net_rs = [t["net_R"] for t in val_taken]
    exp_lb = expectancy_lower_bound(net_rs)

    metrics_by_fund = {f: _perf.metrics(val_taken, equity=val_curve, account=_AP.get(f),
                                        horizon=VALIDATION_TRADING_DAYS) for f in FUNDS}
    passed, pass_detail = evaluate_pass(metrics_by_fund, trading_days, exp_lb)
    development_metrics = {f: _perf.metrics(dev_taken, equity=dev_curve, account=_AP.get(f)) for f in FUNDS}

    dataset_pairs = [(s, tf) for s in usable]
    try:
        dataset_snap = _snap.dataset_snapshot(dataset_pairs, base=os.path.join(ROOT, "data", "history"))
        dataset_snapshot_id = dataset_snap.get("snapshot_id")
    except (OSError, ValueError, KeyError) as exc:
        dataset_snap = X.unavailable(f"{type(exc).__name__}: {exc}")
        dataset_snapshot_id = None
    try:
        cfg_snap = _snap.backtest_config_snapshot(
            bt, timeframes=[tf], methods=(method,), configs={cfg_name: cfg}, fee_pct=fee * 100,
            market="cfd", dataset_snapshot_id=dataset_snapshot_id)
    except (OSError, ValueError, KeyError, AttributeError) as exc:
        cfg_snap = X.unavailable(f"{type(exc).__name__}: {exc}")

    account_cfg = {}
    for f in FUNDS:
        try:
            account_cfg[f] = _AP.snapshot(_AP.get(f))
        except Exception as exc:   # noqa: BLE001 -- an account-config snapshot must not crash the candidate
            account_cfg[f] = X.unavailable(f"{type(exc).__name__}: {exc}")

    cid = candidate["id"]
    r = X.Record(
        hypothesis=(
            f"{method} config {cfg_name} on {tf} ({candidate['group_kind']}={candidate['group_id']}) passes "
            f"BOTH FTMO Challenge Phase 1 and The5ers High Stakes Step 1 on the pre-registered validation "
            f"window ({VALIDATION_START}..{VALIDATION_END}): prop_pass_probability >= {PASS_PROB_THRESHOLD} "
            f"for EACH fund, each fund's own min_trading_days is met, and the one-sided 90% bootstrap lower "
            f"bound of mean net R on the validation trades is > 0 -- falsified if any one of the three fails "
            f"({PREREG_DOC} §2)."),
        motivation=(
            f"Owner pre-registration 2026-09-27 ({PREREG_DOC} §1): find at least 5 setups the EXISTING engine "
            f"already produces that would pass both prop challenges, without relaxing any criterion to reach "
            f"that count."),
        parent_trading_system_version=X.unavailable(
            "this is a pre-registered space search over the existing runnable methods x configs x timeframes "
            "x instruments, not a change TO an existing approved Trading System (§47) -- see system_version "
            "for the registry this candidate was scanned against"),
        candidate_version=f"prop-search-candidate:{cid}",
        experiment_id=cid,
    )
    r.set("failure_pattern", X.unavailable(
        f"this candidate answers no §41 failure cluster -- it is a pre-registered parameter-space search "
        f"({PREREG_DOC} §5), not a response to an observed trading failure"))
    r.set("dataset_snapshot", dataset_snap)
    r.set("configuration_snapshot", cfg_snap)
    r.set("account_configuration", account_cfg)
    r.set("risk_configuration", {
        "max_risk_pct": bt.RISK, "fee_pct_per_side": fee, "entry_order_type": entry_order_type,
        "source": "docs/architecture/risk-config.json via scripts/trading_env.py and "
                 "scripts/stability-report.py config_fee()"})
    r.set("news_configuration", X.unavailable(
        f"this run applies no --calendar / news filter; {PREREG_DOC} §2's pass rule does not require one"))
    r.set("session_configuration", X.unavailable(
        f"this run applies no --sessions filter; {PREREG_DOC} §2's pass rule does not require one"))
    r.set("parameters", {
        "method": method, "config": cfg_name, "timeframe": tf,
        "group_kind": candidate["group_kind"], "group_id": candidate["group_id"],
        "symbols_planned": candidate["symbols"], "symbols_used": usable,
        "symbols_skipped_no_predevelopment_history": skipped_syms})
    r.set("random_seed", {"performance_bootstrap": _perf.BOOTSTRAP_SEED,
                          "expectancy_lower_bound_bootstrap": EXPECTANCY_BOOTSTRAP_SEED})
    r.set("test_periods", {
        "development": {"end": VALIDATION_START, "note": "everything before this: free exploration (§4)"},
        "validation": {"start": VALIDATION_START, "end": VALIDATION_END,
                      "note": "evaluated ONCE for the pass decision; EXPOSED as of this record (§4)"},
        "exposed_reporting_only_after": VALIDATION_END,
        "source": f"{PREREG_DOC} §4"})
    r.set("validation_method",
         "day-block bootstrap over validation-window trades under each fund's account rules "
         "(scripts/performance.py _bootstrap_days, CLAUDE.md §39), plus a one-sided 90% bootstrap lower bound "
         "of mean net R (scripts/prop-search.py expectancy_lower_bound) -- development/validation partition "
         f"only, no further walk-forward/OOS split ({PREREG_DOC} §4)")
    r.set("metrics", {
        "validation": {
            "ftmo-challenge-phase1": metrics_by_fund["ftmo-challenge-phase1"],
            "the5ers-high-stakes-step1": metrics_by_fund["the5ers-high-stakes-step1"],
            "trading_days_observed": trading_days,
            "expectancy_lower_bound": exp_lb,
            "pass_detail": pass_detail,
            "passed": passed,
            "n_trades": len(val_taken),
        },
        "development": {
            "ftmo-challenge-phase1": development_metrics["ftmo-challenge-phase1"],
            "the5ers-high-stakes-step1": development_metrics["the5ers-high-stakes-step1"],
            "n_trades": len(dev_taken),
            "_note": "informational only (CLAUDE.md §9/§37): never used for the pass decision or candidate "
                     "selection",
        },
    })
    r.set("robustness_results", X.unavailable(
        f"§45 sensitivity/perturbation/regime testing is out of scope for this pre-registered pass/fail "
        f"search -- {PREREG_DOC} defines exactly one evaluation per candidate"))
    sv = _system_version_for(tf)
    r.set("system_version", sv if sv else X.unavailable(
        f"no Trading System resolves for (cfd, {tf}) in docs/architecture/trading-systems.json"))
    sealed = r.seal()
    return {"record": dict(sealed)}


# --------------------------------------------------------------------------------------------------- `run`

def _existing_counts(store):
    """(evaluated, passed) re-derived from disk -- the source of truth for budget/pass tracking across
    restarts (§42/§43: the running count must be visible and must survive a crash)."""
    if not os.path.isdir(store):
        return 0, 0
    evaluated = passed = 0
    for f in sorted(os.listdir(store)):
        if not f.endswith(".json"):
            continue
        rec = X.load(f[:-5], store=store)   # Tampered propagates -- a search whose own evidence has been
                                            # altered must stop, not silently continue past it (§42 immutable)
        evaluated += 1
        if rec["metrics"]["validation"]["passed"]:
            passed += 1
    return evaluated, passed


def _record_skip(cid, reason):
    skipped = []
    if os.path.exists(SKIPPED_PATH):
        skipped = json.load(open(SKIPPED_PATH, encoding="utf-8"))
    if any(s["id"] == cid for s in skipped):
        return
    skipped.append({"id": cid, "reason": reason})
    os.makedirs(EXPERIMENT_DIR, exist_ok=True)
    with open(SKIPPED_PATH, "w", encoding="utf-8") as fh:
        json.dump(skipped, fh, ensure_ascii=False, indent=1)


def cmd_run(only=None, workers=1):
    plan = load_plan()
    os.makedirs(RECORDS_DIR, exist_ok=True)
    evaluated, passed = _existing_counts(RECORDS_DIR)
    print(f"resuming: {evaluated} already evaluated, {passed} already passed "
          f"(budget {BUDGET_MAX}, target {TARGET_PASSES})")
    if evaluated >= BUDGET_MAX:
        print("budget already spent; nothing to do")
        return
    if passed >= TARGET_PASSES:
        print(f"already found {passed} passes; nothing to do")
        return

    candidates = plan["candidates"]
    if only:
        wanted = set(only)
        candidates = [c for c in candidates if c["id"] in wanted]
    existing_ids = {f[:-5] for f in os.listdir(RECORDS_DIR) if f.endswith(".json")}
    todo = [c for c in candidates if c["id"] not in existing_ids]
    todo = todo[: max(0, BUDGET_MAX - evaluated)]   # never evaluate past the budget, even across restarts
    if not todo:
        print("nothing left to evaluate (all planned candidates already recorded, or --only matched none)")
        return

    workers = max(1, workers)
    sr = _sr() if workers == 1 else None   # sequential: reuse one bt instance's caches; parallel: each
                                           # spawned worker loads its own (see _load_sr's docstring)
    idx = 0
    while idx < len(todo) and evaluated < BUDGET_MAX and passed < TARGET_PASSES:
        chunk = todo[idx: idx + workers]
        idx += len(chunk)
        if workers == 1:
            results = [(chunk[0]["id"], _evaluate_candidate(chunk[0], sr=sr))]
        else:
            results = []
            with _pool.IsolatedExecutor(max_workers=workers) as ex:
                futs = {ex.submit(_evaluate_candidate, c): c["id"] for c in chunk}
                for fut in concurrent.futures.as_completed(futs):
                    results.append((futs[fut], fut.result()))
        for cid, outcome in results:
            if "skip" in outcome:
                print(f"SKIP {cid}: {outcome['skip']}")
                _record_skip(cid, outcome["skip"])
                continue
            sealed = types.MappingProxyType(outcome["record"])
            X.write(sealed, store=RECORDS_DIR)
            evaluated += 1
            this_passed = outcome["record"]["metrics"]["validation"]["passed"]
            passed += 1 if this_passed else 0
            print(f"{'PASS' if this_passed else 'fail'} {cid} "
                  f"({evaluated}/{BUDGET_MAX} evaluated, {passed}/{TARGET_PASSES} passes)")
            if evaluated >= BUDGET_MAX or passed >= TARGET_PASSES:
                break
    print(f"stopped: {evaluated} evaluated, {passed} passed")


# ------------------------------------------------------------------------------------------------ `report`

def cmd_report():
    plan = load_plan()
    recs = []
    if os.path.isdir(RECORDS_DIR):
        for f in sorted(os.listdir(RECORDS_DIR)):
            if f.endswith(".json"):
                recs.append(X.load(f[:-5], store=RECORDS_DIR))
    skipped = json.load(open(SKIPPED_PATH, encoding="utf-8")) if os.path.exists(SKIPPED_PATH) else []
    evaluated = len(recs)
    passes = [r for r in recs if r["metrics"]["validation"]["passed"]]

    def fund_cell(pass_detail, fund):
        d = pass_detail.get(fund, {})
        p = d.get("prop_pass_probability")
        val = p.get("value") if isinstance(p, dict) and "value" in p else None
        return f"{val:.2f}" if isinstance(val, (int, float)) else "n/a"

    lines = [
        "# Prop-challenge pre-registered setup search -- report", "",
        f"_Source: `{PREREG_DOC}`. Plan: `docs/experiments/prop-search-2026-09-27/plan.json` "
        f"({plan['candidate_count']} candidates, hash {plan['plan_hash'][:12]})._", "",
        f"Budget spent: **{evaluated} / {BUDGET_MAX}** candidates evaluated. "
        f"Passes found: **{len(passes)} / {TARGET_PASSES}** "
        f"(the target is a goal, not a stopping rule beyond whichever of the two comes first).", "",
        "## Pass criteria (verbatim from the pre-registration, §2)", "",
        f"1. `prop_pass_probability` >= {PASS_PROB_THRESHOLD} under BOTH `ftmo-challenge-phase1` AND "
        f"`the5ers-high-stakes-step1`, each fund judged on its own.",
        "2. Trades on at least the fund's own `min_trading_days` (FTMO 4, The5ers 3) within the validation "
        "window, and the bootstrap has the sample it needs to run at all (n >= 5).",
        "3. The one-sided 90% bootstrap lower bound of mean net R on the validation trades is > 0. There is "
        "NO fixed minimum trade count beyond that.", "",
        "## Multiple-testing caveat", "",
        f"{evaluated} candidates were evaluated on the SAME validation window in the search for these passes "
        f"(CLAUDE.md §43/§45: repeated selection over one window inflates the apparent hit rate above what "
        f"any single candidate's own numbers suggest). A PASS here is a candidate that cleared the "
        f"pre-registered bar on the first and only look this search grants the validation window -- it is "
        f"NOT yet forward-confirmed (`{PREREG_DOC}` §4: forward confirmation on live demo is required before "
        f"any funded attempt), and the validation window is EXPOSED as of the first evaluation recorded here.",
        "",
        "## Every evaluated candidate", "",
        "| # | id | method | config | tf | group | prop_pass_probability (FTMO / The5ers) | trading days | "
        "expectancy LB (net R) | PASS |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(recs, 1):
        v = r["metrics"]["validation"]
        pd = v["pass_detail"]
        params = r["parameters"]
        lb = v["expectancy_lower_bound"]
        lb_val = lb.get("value") if isinstance(lb, dict) and "value" in lb else None
        lines.append(
            f"| {i} | {r['experiment_id']} | {params['method']} | {params['config']} | "
            f"{params['timeframe']} | {params['group_kind']}={params['group_id']} | "
            f"{fund_cell(pd, FUNDS[0])} / {fund_cell(pd, FUNDS[1])} | {v['trading_days_observed']} | "
            f"{f'{lb_val:+.3f}' if isinstance(lb_val, (int, float)) else 'n/a'} | "
            f"{'**PASS**' if v['passed'] else 'fail'} |")
    if skipped:
        lines += ["", "## Skipped candidates (no pre-development history, §5)", ""]
        for s in skipped:
            lines.append(f"- `{s['id']}`: {s['reason']}")
    if passes:
        lines += ["", "## Passing candidates in detail", ""]
        for r in passes:
            lines.append(f"- `{r['experiment_id']}`: {r['hypothesis']}")
    else:
        lines += ["", "## Passing candidates in detail", "",
                  f"None of the {evaluated} evaluated candidates passed. Reported as found -- no criterion "
                  f"was relaxed to manufacture a pass ({PREREG_DOC} §3)."]
    md = "\n".join(lines) + "\n"
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write(md)
    print(f"-> {REPORT_PATH} ({evaluated} candidates, {len(passes)} passes)")
    return md


# ------------------------------------------------------------------------------------------------------ CLI

def main():
    ap = argparse.ArgumentParser(description=(
        "Pre-registered prop-challenge setup search -- docs/plans/2026-09-27-prop-setup-search-"
        "preregistration.md"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan", help="enumerate and commit the candidate space (must run before `run`)")
    rp = sub.add_parser("run", help="evaluate planned candidates on the validation window")
    rp.add_argument("--only", help="comma-separated candidate ids to (re)run instead of the whole plan")
    rp.add_argument("--workers", type=int, default=1, help="parallel candidate-evaluation worker processes")
    sub.add_parser("report", help="write the markdown report listing every evaluated candidate")
    a = ap.parse_args()
    if a.cmd == "plan":
        cmd_plan()
    elif a.cmd == "run":
        only = [x.strip() for x in a.only.split(",") if x.strip()] if a.only else None
        cmd_run(only=only, workers=a.workers)
    elif a.cmd == "report":
        cmd_report()


if __name__ == "__main__":
    main()
