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
import contextlib
import datetime
import hashlib
import importlib.util
import json
import os
import random
import sys
import time
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import experiment as X          # CLAUDE.md §42: the ONE reader/writer of the experiment store
import instruments as _I        # docs/architecture/instruments.json: analysis.cfd, display().asset_class
import methods as _M            # docs/architecture/methods.json: the runnable RUNNER_METHODS set
import account_profile as _AP   # the two fund profiles (research-only, docs/architecture/account-profiles.json)
import performance as _perf     # CLAUDE.md §39: the ONE computer for the twenty-three metrics
import snapshot as _snap        # CLAUDE.md §11: configuration snapshot (dataset snapshot is PIT-truncated below)
import normalized as _N         # CLAUDE.md §7/§10: provenance() + SNAPSHOT_INPUTS_VERSION, reused for the
                                # PIT-truncated dataset snapshot (fix round 1, review item B)
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
TIMEFRAMES = ("15m", "1H", "4H")               # §5

EXPECTANCY_BOOTSTRAP_ITERATIONS = 2000
EXPECTANCY_BOOTSTRAP_SEED = 20260927           # the pre-registration's own date; fixed, reproducible (§46)
EXPECTANCY_LOWER_BOUND_CI = 0.90               # one-sided 90% CI lower bound (§2.3)
EXPECTANCY_MIN_N = 5                           # same floor as performance.py's own bootstrap metrics (§2.2:
                                                # "the bootstrap has the sample it needs to run at all")


def _weekday_count(start_iso, end_iso):
    """Calendar weekdays (Mon-Fri) in [start, end)."""
    start = datetime.date.fromisoformat(start_iso[:10])
    end = datetime.date.fromisoformat(end_iso[:10])
    n = (end - start).days
    return sum(1 for i in range(n) if (start + datetime.timedelta(days=i)).weekday() < 5)


# Owner decision, addendum §8.1 (2026-09-28), SUPERSEDING the first implementer reading ("horizon = every
# weekday in the validation window", ~261): the GATING horizon for prop_pass_probability is 120 trading days
# (~6 months, the owner's maximum acceptable wait -- neither fund imposes its own time limit today), for BOTH
# funds. 30, 60 and the full validation-window weekday count are computed too and carried on every record
# under `informational_horizons`, but NEVER read by `evaluate_pass` -- see CHALLENGE_HORIZON_DAYS's own use
# below and `evaluate_pass`'s docstring for where the boundary between "gates" and "reported" is drawn.
CHALLENGE_HORIZON_DAYS = 120
VALIDATION_TRADING_DAYS = _weekday_count(VALIDATION_START, VALIDATION_END)   # ~261; informational only now
INFORMATIONAL_HORIZON_DAYS = (30, 60, VALIDATION_TRADING_DAYS)   # §8.1: "REPORTED for information, never gate"


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
        "challenge_horizon_days": CHALLENGE_HORIZON_DAYS,
        "informational_horizon_days": list(INFORMATIONAL_HORIZON_DAYS),
        "funds": {f: dict(zip(("day_requirement_count", "day_requirement_kind"), _required_days(f)))
                 for f in FUNDS},
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


def split_unfinished(trades, horizon_bars):
    """Addendum §8.2 (owner decision 2026-09-28): a validation trade whose exit (stop, target, or the H-bar
    time stop) would need a bar after the PIT cutoff is excluded from the pass decision, not marked to market
    at the truncated last bar.

    A trade's own outcome (`scripts/backtest-methods.py walk()`) is "timeout" exactly when neither stop nor
    target was touched within its H-bar window -- and `walk()` falls back to `outcome="timeout"` in BOTH of
    two different situations that its own `bars_held` field distinguishes:
      * a GENUINE time-stop: the full H-bar window existed in the (possibly truncated) series and neither
        level was touched in it -- `bars_held == horizon_bars`, a real, fully-observed outcome.
      * data RAN OUT before the window finished (`walk()`'s own `min(len(C_), start + horizon)` clipped the
        scan short) -- `bars_held < horizon_bars`, and the trade's true fate beyond the truncated data is
        UNKNOWN, exactly the "would need a bar after the cutoff" case this rule excludes.
    A win/loss/breakeven outcome is never excluded: the stop/target touch that produced it happened on some
    bar INSIDE the (already truncated) series that walk() actually scanned, so it needs no bar beyond the
    cutoff to be known, however close to the cutoff that bar sits.

    Returns `(finished, excluded)`.
    """
    finished, excluded = [], []
    for t in trades:
        bars_held = t.get("bars_held")
        if (t.get("outcome") == "timeout" and isinstance(bars_held, (int, float))
                and bars_held < horizon_bars):
            excluded.append(t)
        else:
            finished.append(t)
    return finished, excluded


def _required_days(fund):
    """(count, kind) for `fund`'s own §33 minimum-days requirement, read from account-profiles.json -- THE
    one source (replaces a hand-typed copy this file carried before addendum §8.3). `kind` is
    "trading_days" (FTMO: any day a trade was INITIATED) or "profitable_days" (The5ers: a day whose closed
    profit reached the fund's own threshold) -- account_profile._validate_rules refuses a profile declaring
    both, so exactly one of the two rule keys is ever non-null on a real fund profile."""
    prof = _AP.get(fund)
    mtd = prof["rules"].get("min_trading_days")
    if mtd is not None:
        return mtd, "trading_days"
    mpd = prof["rules"].get("min_profitable_days")
    if mpd is not None:
        return mpd["count"], "profitable_days"
    return None, None


def _profitable_day_threshold_pct(fund):
    mpd = _AP.get(fund)["rules"].get("min_profitable_days")
    return mpd["profit_threshold_pct"] if mpd else None


def _inactivity_threshold_days(fund):
    """The fund's own §33 `custom_failure_conditions` inactivity threshold, or None when it declares none
    (FTMO today). THE one source -- addendum §8.3's "30 consecutive calendar days" lives in account-
    profiles.json, not as a second, separately-typed constant here."""
    for item in _AP.get(fund)["rules"].get("custom_failure_conditions") or ():
        if item["kind"] == "inactivity_days":
            return item["threshold"]
    return None


def _profitable_days_count(taken, threshold_dollar):
    """Distinct EXIT days ("closed profit ... that day", addendum §8.3) whose summed `pnl` (backtest
    dollars, `bt.simulate()`'s own `taken` records) reaches `threshold_dollar`. Grouped by EXIT day, matching
    `simulate()`'s own `profit_by_day` bucketing (`t2["exit_time"][:10]`) -- not the ENTRY-day convention
    `performance._day_blocks` uses for the UNRELATED max_daily_loss rule."""
    by_day = {}
    for t in taken:
        d = t["exit_time"][:10]
        by_day[d] = by_day.get(d, 0.0) + t.get("pnl", 0.0)
    return sum(1 for pnl in by_day.values() if pnl >= threshold_dollar)


def day_counts_for(fund, val_taken, bt):
    """This fund's OWN qualifying-day count (addendum §8.3): FTMO counts distinct ENTRY days (any day a
    trade was initiated); The5ers counts distinct EXIT days whose closed profit reached its own
    `profit_threshold_pct` of the account's starting balance.

    The profitable-day threshold is expressed as a dollar amount ON THE BACKTEST'S OWN `bt.START`-scaled
    account, not the fund's real $100,000 -- and that is exactly right, not an approximation:
    fixed-fractional risk sizing is scale-invariant, so "day's pnl >= pct * fund_initial_balance" and "day's
    pnl (in backtest dollars) >= pct * bt.START" are the SAME comparison once the linear rescaling
    `account_profile._basis_value`/`backtest-methods._account_stop` apply elsewhere is done out algebraically
    -- both sides carry the same `fund_initial_balance / bt.START` factor, which cancels.
    """
    _, kind = _required_days(fund)
    if kind == "profitable_days":
        threshold_dollar = _profitable_day_threshold_pct(fund) * bt.START
        return _profitable_days_count(val_taken, threshold_dollar)
    return len({t["entry_time"][:10] for t in val_taken})   # FTMO: days a trade was INITIATED


def _max_inactivity_gap_days(taken, window_start_iso, window_end_iso):
    """Largest gap, in calendar days, between consecutive trade-ENTRY days within [window_start, window_end)
    -- including window_start -> first trade and last trade -> window_end. ENTRY day (not exit), matching
    FTMO's own "days a trade was initiated" convention for the sibling min_trading_days rule: an evaluation
    account is inactive from the moment it stops OPENING new trades, not from when its last one happens to
    close.

    Deliberately NOT computed inside performance.py's day-block bootstrap (`_bootstrap_days`): that function
    resamples TRADING-day blocks with replacement and has no representation of the CALENDAR GAP between one
    trading day and the next -- every simulated "day" in a bootstrap path is, by construction, a day that had
    a trade, so "N consecutive calendar days with none" cannot be expressed inside it. This is evaluated once,
    directly, against the REAL (non-resampled) validation trade timeline instead -- a deterministic
    house-keeping fact about THIS candidate's actual trade cadence, not a probability.
    """
    days = sorted({t["entry_time"][:10] for t in taken})
    window_start = datetime.date.fromisoformat(window_start_iso[:10])
    window_end = datetime.date.fromisoformat(window_end_iso[:10])
    if not days:
        return (window_end - window_start).days
    dates = [datetime.date.fromisoformat(d) for d in days]
    gaps = [(dates[0] - window_start).days]
    gaps += [(b - a).days for a, b in zip(dates, dates[1:])]
    gaps.append((window_end - dates[-1]).days)
    return max(gaps)


def inactivity_breach_for(fund, val_taken):
    """True when `fund`'s own inactivity rule (addendum §8.3, account-profiles.json custom_failure_conditions
    kind="inactivity_days") is breached somewhere in the validation window's REAL trade timeline. False for a
    fund that declares no such rule (FTMO today) -- absence of a rule is never a breach.

    NOT routed through `account_profile.account_state()`/`halt_check()` (fix round 2, item 4), even though the
    `inactivity_days` KIND is registered there (`account_profile.FAILURE_KINDS`) and IS the evaluator a live
    order path or a running backtest would use. The two ask different questions over different time shapes:
    `account_state()` answers "is the account breached RIGHT NOW", from a single scalar fact
    (`days_since_last_trade`, as of one instant) the CALLER must already have computed -- exactly right for a
    live tick or a bar-by-bar backtest loop, which has a "now". This function answers "did the rule EVER
    breach anywhere in the whole validation window", a retrospective scan over the complete, already-known
    trade timeline -- there is no single "now" to hand `account_state()` a `days_since_last_trade` for; the
    quantity it would need (the running gap at every point in time) is exactly what `_max_inactivity_gap_days`
    computes by walking the whole timeline, which `account_state()`'s single-fact interface has no way to
    express. Using the shared evaluator here would mean re-deriving this same walk just to produce the one
    scalar it wants, at every candidate point in time, for no benefit over calling `_max_inactivity_gap_days`
    directly once. `account_state()` remains the ONE evaluator for the ONLINE question (§33); this is the
    OFFLINE, whole-window question, and it belongs in the research script that actually has the whole window.
    """
    threshold = _inactivity_threshold_days(fund)
    if threshold is None:
        return False
    return _max_inactivity_gap_days(val_taken, VALIDATION_START, VALIDATION_END) >= threshold


def evaluate_pass(metrics_by_fund, day_counts, inactivity_breach, expectancy_lb):
    """PREREG_DOC §2 + addendum §8.3, all criteria evaluated together (a candidate must clear every one) at
    the SINGLE GATING horizon (CHALLENGE_HORIZON_DAYS) -- the informational 30/60/full-window horizons a
    record also carries are never read here. Pure and side-effect-free so `run` (fresh evaluation) and
    `report`/resume (re-deriving PASS/FAIL from a previously sealed record's own `metrics` field) always
    agree -- there is no separate stored boolean to drift from the numbers that justify it.

    `metrics_by_fund[fund]` -- performance.metrics() computed with `horizon=CHALLENGE_HORIZON_DAYS`.
    `day_counts[fund]`      -- this fund's OWN qualifying-day count (day_counts_for): trading days for FTMO,
                               profitable days for The5ers.
    `inactivity_breach[fund]` -- whether the fund's own inactivity rule (The5ers only) was breached.

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
        required, kind = _required_days(fund)
        days_ok = required is not None and day_counts.get(fund, 0) >= required
        breach = bool(inactivity_breach.get(fund, False))
        inactivity_ok = not breach
        detail[fund] = {
            "prop_pass_probability": p, "threshold": PASS_PROB_THRESHOLD, "meets_threshold": p_ok,
            "day_requirement_kind": kind, "day_requirement_count": required,
            "days_observed": day_counts.get(fund, 0), "meets_day_requirement": days_ok,
            "inactivity_breach": breach, "meets_inactivity_rule": inactivity_ok,
        }
        ok = ok and p_ok and days_ok and inactivity_ok
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


def _pit_series_snapshot(symbol, tf, bt):
    """One input series' identity, but for the PIT-TRUNCATED view `bt.scan()` actually read (fix round 1,
    review item B, CRITICAL): `snapshot.series_snapshot()` reads the FULL FILE FROM DISK via
    `normalized.load()` -- correct for every OTHER research script here (none of which truncate), wrong for
    this one, where the candidate's own dataset_snapshot must describe what the engine actually consumed
    after `bt.pit_cutoff()`, not whatever now sits on disk after 2025-03-01.

    `bt.load(symbol, tf)` already applies the process's current `_PIT_CUTOFF` (backtest-methods.py's own
    load-time seam), so the candle list this reads IS the truncated series. Static provenance facts (provider,
    canonical_symbol, market, market_type, aggregation_scope, ...) are still correctly derived via
    `normalized.provenance()` -- fed the TRUNCATED candle list instead of the full file's, so the DATA-
    DEPENDENT fields it computes (`event_time`, `available_time`, `data_scope`, `quality`) describe the
    truncated view too, not the archive.

    Returns None when `bt.load()` finds nothing (should not happen here -- the caller already filtered to
    `_has_predevelopment_history` symbols -- but a None is a cleaner failure than an IndexError on an empty
    candle list).
    """
    truncated, _src = bt.load(symbol, tf)
    if not truncated:
        return None
    # bt.load() reads data/history/ohlcv.<sym>.<tf>.json (the research archive) -- normalized.load()'s OWN
    # default reads data/live/<data_dir>/... (the live feed) instead, so `base` must be passed explicitly to
    # point at the SAME file bt.load() just read, or provenance() would describe a different series.
    hist_base = os.path.join(ROOT, "data", "history")
    full = _N.load(symbol, tf, base=hist_base)        # for static provenance facts + the raw file header only
    raw_for_prov = dict(full["raw_header"], candles=truncated)
    path = _N.path_for(symbol, tf, base=hist_base)
    prov = _N.provenance(raw_for_prov, symbol, tf, path)
    digest = hashlib.sha256(json.dumps(truncated, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    quality_flags = [dict(f) for f in bt.QUALITY_FLAGS if f["symbol"] == symbol and f["tf"] == tf]
    return {
        "symbol": symbol, "canonical_symbol": prov["canonical_symbol"], "market": prov["market"],
        "market_type": prov["market_type"], "timeframe": tf, "provider": prov["provider"],
        "source_venue": prov["source_venue"], "aggregation_scope": prov["aggregation_scope"],
        "underlying_venues": prov["underlying_venues"], "source_identifier": prov["source_identifier"],
        "retrieval_state": prov["quality"], "received_time": prov["received_time"],
        "bars": len(truncated), "first_open": truncated[0]["time"], "last_open": truncated[-1]["time"],
        "sha256": digest,
        # CLAUDE.md §20/§38 (fix round 1, review item C1): every data-quality fault `bt.load()` flagged for
        # THIS (symbol, timeframe) in this process, folded directly into the snapshot -- see
        # `_ASSESSED`/`QUALITY_FLAGS`'s own module docstring in backtest-methods.py for the per-process,
        # per-(symbol, tf) cache this reads from, and the cutoff-stability assumption it relies on (§8.3/D).
        "quality_flags": quality_flags,
        "_pit_truncated": True,
        "_pit_cutoff": VALIDATION_END,
        "_note": "bars/first_open/last_open/sha256/quality_flags describe the PIT-TRUNCATED series bt.scan() "
                 "actually read (CLAUDE.md §8), not the full on-disk file -- last_open is always <= the "
                 "cutoff by construction (bt.pit_cutoff() / pit.series_as_of()).",
    }


def dataset_snapshot_truncated(symbols, tf, bt):
    """CLAUDE.md §10, PIT-TRUNCATED variant (fix round 1, review item B): the dataset snapshot for a
    candidate's own set of symbols, built ONLY from what `bt.scan()` actually read (see
    `_pit_series_snapshot`), never from the raw archive file."""
    rows = [r for r in (_pit_series_snapshot(s, tf, bt) for s in symbols) if r is not None]
    ident = hashlib.sha256("|".join(sorted(f"{r['symbol']}:{r['timeframe']}:{r['sha256']}"
                                           for r in rows)).encode()).hexdigest()[:16]
    return {
        "snapshot_format": 1, "snapshot_id": ident, "created_at": _now_iso(),
        "code_version": _snap.code_version(), "preprocessing_version": _N.SNAPSHOT_INPUTS_VERSION,
        "series": rows,
        "_note": "CLAUDE.md §10, PIT-TRUNCATED variant (fix round 1, review item B): series[*].bars/"
                 "first_open/last_open/sha256/quality_flags describe the validation-truncated candle list "
                 "bt.scan() actually consumed for this candidate, not the raw on-disk file.",
    }


def _system_version_for(tf):
    try:
        sysd = _TS.for_market_tf("cfd", tf)
        full = _TS.get(sysd["id"])
        return {"id": sysd["id"], "version": full.get("version"),
               "source": "docs/architecture/trading-systems.json"}
    except (KeyError, Exception):
        return None


def _evaluate_candidate(candidate, sr=None, plan_hash=None):
    """Runs the existing engine (bt.scan + bt.simulate, unmodified semantics) over ONE candidate's symbols,
    truncated at the validation boundary (bt.pit_cutoff), and returns either `{"skip": reason}` (no history,
    doesn't count against budget) or `{"record": <plain dict, a sealed §42 record's fields>}`.

    `sr=None` (the default, and always the value used by a spawned worker -- see `_load_sr`'s own docstring)
    loads a fresh `sr`/`bt` here; `cmd_run`'s sequential (`--workers 1`) path passes the cached one so repeated
    calls in the SAME process reuse `bt`'s own load/detection caches for speed, matching stability-report.py's
    own dedup philosophy. `bt.pit_cutoff` is reset to the SAME constant (VALIDATION_END) on every call
    regardless of which `bt` instance is used, so cache reuse changes nothing about what is measured.

    `plan_hash` (fix round 2, item 2) is stamped into the sealed record's `parameters` field -- the ONE thing
    that lets a LATER run (possibly on a different machine, after a restore from a results branch) tell
    whether a record on disk was sealed against the plan currently loaded, or a stale/foreign one. Not one of
    §42's 22 top-level fields (that list is fixed); folded into `parameters`, which already carries this
    candidate's own identity, rather than inventing a 23rd top-level field.
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
    # (no bt.limit_bars() reset here: prop-search.py never sets it itself in production -- nothing in this
    # file's own CLI calls it -- so resetting it would only ever undo a CALLER's deliberate choice, e.g. a
    # test that wants a small, fast real run via bt.limit_bars(N) before invoking this function directly.)
    cfg = sr.CONFIGS[cfg_name]
    overlay = sr.config_opts(cfg, ict_target="range")
    scans = [s for s in (bt.scan(sym, tf, only=(method,), opts=overlay) for sym in usable) if s]
    if not scans:
        return {"skip": f"{candidate['id']}: bt.scan() produced no series for {usable} at {tf}"}
    trades = [t for s in scans for t in s["trades"][method]]
    fee = sr.config_fee(cfg, "cfd")
    entry_order_type = sr.entry_order_type_for(cfg, method)

    dev_trades, val_trades = split_windows(trades)
    # Addendum §8.2 (owner decision 2026-09-28): a validation trade whose true outcome would need a bar past
    # the PIT cutoff is excluded from the pass decision entirely -- BEFORE simulate() ever sees it, so it
    # never occupies a symbol's one-open-position slot, is never booked onto the equity curve, and cannot
    # distort the drawdown/pnl/bootstrap numbers with an outcome nobody actually knows.
    horizon_bars = bt.P[tf]["H"]
    val_trades, excluded_unfinished = split_unfinished(val_trades, horizon_bars)

    def _population(trs):
        # No `account=` here on purpose (matching scripts/stability-report.py's own `metrics()` helper):
        # `simulate(account=...)` STOPS the run at the account's first breach, which would bootstrap a
        # population already conditioned on failure. The account's RULES still gate the bootstrap itself
        # (passed as `account=` to performance.metrics below); only the POPULATION it resamples is the full,
        # unconstrained one.
        return bt.simulate(trs, fee, entry_order_type=entry_order_type, live_parity_sizing=True)

    dev_final, dev_curve, dev_taken = _population(dev_trades)
    val_final, val_curve, val_taken = _population(val_trades)

    net_rs = [t["net_R"] for t in val_taken]
    exp_lb = expectancy_lower_bound(net_rs)

    # Addendum §8.1: prop_pass_probability is GATED at CHALLENGE_HORIZON_DAYS (120) for both funds; 30, 60
    # and the full validation-window weekday count are computed too and carried for information, never read
    # by evaluate_pass.
    metrics_by_fund = {f: _perf.metrics(val_taken, equity=val_curve, account=_AP.get(f),
                                        horizon=CHALLENGE_HORIZON_DAYS) for f in FUNDS}
    informational_horizons = {
        f: {str(h): _perf.metrics(val_taken, equity=val_curve, account=_AP.get(f), horizon=h)
                    .get("prop_pass_probability")
           for h in INFORMATIONAL_HORIZON_DAYS}
        for f in FUNDS
    }
    day_counts = {f: day_counts_for(f, val_taken, bt) for f in FUNDS}
    inactivity_breach = {f: inactivity_breach_for(f, val_taken) for f in FUNDS}
    passed, pass_detail = evaluate_pass(metrics_by_fund, day_counts, inactivity_breach, exp_lb)
    development_metrics = {f: _perf.metrics(dev_taken, equity=dev_curve, account=_AP.get(f)) for f in FUNDS}

    dataset_snap = dataset_snapshot_truncated(usable, tf, bt)
    dataset_snapshot_id = dataset_snap.get("snapshot_id")
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
        "symbols_skipped_no_predevelopment_history": skipped_syms,
        # fix round 2, item 2: which committed plan this candidate was drawn from -- _existing_counts()
        # refuses to trust a record whose plan_hash does not match the CURRENTLY loaded plan.
        "plan_hash": plan_hash})
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
            "gating_horizon_days": CHALLENGE_HORIZON_DAYS,
            "ftmo-challenge-phase1": metrics_by_fund["ftmo-challenge-phase1"],
            "the5ers-high-stakes-step1": metrics_by_fund["the5ers-high-stakes-step1"],
            "informational_horizons": {
                "_note": "addendum §8.1: 30/60/full-validation-window-weekday prop_pass_probability at each "
                         "fund, REPORTED for information -- never read by evaluate_pass, never gate",
                "days": list(INFORMATIONAL_HORIZON_DAYS), **informational_horizons,
            },
            "day_counts": day_counts,
            "inactivity_breach": inactivity_breach,
            "excluded_unfinished_trades": len(excluded_unfinished),
            "_excluded_unfinished_trades_note": "addendum §8.2: validation trades whose true outcome would "
                "need a bar after the PIT cutoff, excluded from every number above (not marked to market)",
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

class RecordMismatch(RuntimeError):
    """A record under RECORDS_DIR does not belong to the CURRENTLY LOADED plan -- either its `experiment_id`
    is not one of the plan's own candidates, or its recorded `parameters.plan_hash` does not match the plan's
    own hash (fix round 2, item 2). Raised rather than silently skipped or counted: a record restored from a
    DIFFERENT search's results branch, or left over from before the candidate space changed, would otherwise
    inflate (or misdirect) this plan's budget/pass count with evidence that is not evidence FOR this plan.
    """


def _validate_record_against_plan(rec, plan):
    cid = rec["experiment_id"]
    valid_ids = {c["id"] for c in plan["candidates"]}
    if cid not in valid_ids:
        raise RecordMismatch(
            f"record {cid!r} under {RECORDS_DIR} is not one of the {len(valid_ids)} candidates in the "
            f"currently loaded plan (hash {plan['plan_hash'][:12]}) -- refusing to trust it as evidence for "
            f"this search. It may belong to a different plan revision or a different search entirely. Move "
            f"or delete it, then re-run.")
    rec_plan_hash = (rec.get("parameters") or {}).get("plan_hash")
    if rec_plan_hash != plan["plan_hash"]:
        raise RecordMismatch(
            f"record {cid!r} under {RECORDS_DIR} was sealed against plan_hash "
            f"{(rec_plan_hash[:12] + '...') if rec_plan_hash else '(none recorded)'!r}, but the currently "
            f"loaded plan's hash is {plan['plan_hash'][:12]} -- refusing to trust it as evidence for THIS "
            f"plan (fix round 2, item 2). Move or delete it, then re-run.")


def _existing_counts(store, plan):
    """(evaluated, passed) re-derived from disk -- the source of truth for budget/pass tracking across
    restarts (§42/§43: the running count must be visible and must survive a crash). Every record is validated
    against `plan` (`_validate_record_against_plan`) BEFORE it is counted -- this is the ONE place local
    resume and workflow-restored resume both pass through, so both get the same protection (fix round 2, item
    2) with no separate YAML-side check needed."""
    if not os.path.isdir(store):
        return 0, 0
    evaluated = passed = 0
    for f in sorted(os.listdir(store)):
        if not f.endswith(".json"):
            continue
        rec = X.load(f[:-5], store=store)   # Tampered propagates -- a search whose own evidence has been
                                            # altered must stop, not silently continue past it (§42 immutable)
        _validate_record_against_plan(rec, plan)   # RecordMismatch propagates -- same reasoning, see its docstring
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


# How stale a lock file must be before a NEW cmd_run() reclaims it as abandoned (fix round 1, item C4).
# A real run may legitimately occupy the lock for hours (the workflow's own timeout is 350 minutes), so this
# is deliberately generous -- it exists to recover from a CRASHED run holding a lock forever, not to bound a
# slow one.
RUN_LOCK_STALE_SECONDS = 6 * 3600


class AlreadyRunning(RuntimeError):
    """Another cmd_run() appears to already be using this RECORDS_DIR."""


@contextlib.contextmanager
def _run_lock(path):
    """Exclusive-create lock so two concurrent `cmd_run()` invocations on the SAME store cannot each dispatch
    work and jointly exceed the budget (fix round 1, item C4) -- `_existing_counts`/`todo` are computed once
    per call from what is ALREADY on disk, so two processes running that computation concurrently could both
    see "budget - 0 used" and each dispatch up to the full budget.

    Not a distributed lock (this is a local exclusive-create on one filesystem, matching every other resumable
    piece of this script, which already assumes ONE store lives on one filesystem) -- just enough to make
    "two `run` invocations on the same store" a refusal instead of a silent budget overrun. A lock older than
    `RUN_LOCK_STALE_SECONDS` is reclaimed with a loud warning rather than refused forever, so a crashed run
    cannot permanently wedge the store.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        age = time.time() - os.path.getmtime(path)
        if age < RUN_LOCK_STALE_SECONDS:
            raise AlreadyRunning(
                f"{path} exists and is {age:.0f}s old (< the {RUN_LOCK_STALE_SECONDS}s stale threshold) -- "
                f"another cmd_run() appears to be using {RECORDS_DIR}; refusing to run concurrently (two runs "
                f"could each read the same budget/pass counts and jointly exceed the budget)")
        print(f"WARNING: {path} is {age:.0f}s old (>= the stale threshold) -- reclaiming an apparently "
              f"abandoned lock from a crashed run", file=sys.stderr)
        os.remove(path)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(fd, "w") as fh:
        fh.write(f"pid={os.getpid()} started={_now_iso()}\n")
    try:
        yield
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def cmd_run(only=None, workers=1):
    lock_path = os.path.join(os.path.dirname(RECORDS_DIR) or ".", ".prop-search-run.lock")
    with _run_lock(lock_path):
        _cmd_run_locked(only=only, workers=workers)


def _cmd_run_locked(only=None, workers=1):
    """The actual `run` loop, always called with `RECORDS_DIR`'s own lock held (see `cmd_run`).

    Failure handling (fix round 1, item C5, decided and documented here): an exception raised while
    evaluating one candidate FAILS THE RUN LOUD -- it is never silently recorded as a "fail" outcome, because
    an exception means the pass/fail numbers for that candidate were never actually computed, and recording
    one anyway would misrepresent an error as a real (if negative) result (CLAUDE.md §38's "never silently
    produce a trustworthy-looking performance result" extends to a failure that isn't one). Every candidate
    that DID complete successfully before the failure -- including a sibling in the SAME parallel chunk that
    finished before another one crashed -- is written to disk first; only the run as a whole then stops with
    a clear error naming which candidate(s) failed and how. Re-running `run` afterwards is safe and correct:
    already-written records are skipped (resumable), so fixing the root cause and re-running picks up exactly
    where the run stopped.
    """
    plan = load_plan()
    os.makedirs(RECORDS_DIR, exist_ok=True)
    evaluated, passed = _existing_counts(RECORDS_DIR, plan)   # RecordMismatch propagates -- fix round 2 item 2
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
        errors = []
        if workers == 1:
            cid = chunk[0]["id"]
            try:
                results = [(cid, _evaluate_candidate(chunk[0], sr=sr, plan_hash=plan["plan_hash"]))]
            except Exception as exc:
                results = []
                errors.append((cid, exc))
        else:
            results = []
            with _pool.IsolatedExecutor(max_workers=workers) as ex:
                futs = {ex.submit(_evaluate_candidate, c, None, plan["plan_hash"]): c["id"] for c in chunk}
                for fut in concurrent.futures.as_completed(futs):
                    cid = futs[fut]
                    try:
                        results.append((cid, fut.result()))
                    except Exception as exc:
                        errors.append((cid, exc))
        # Write every result that DID succeed BEFORE deciding whether to raise -- a sibling candidate's crash
        # (or, sequentially, the one candidate that crashed) must never discard an already-computed result.
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
        if errors:
            raise RuntimeError(
                f"prop-search: {len(errors)} candidate(s) raised while evaluating -- FAILING LOUD (fix round "
                f"1, item C5: an exception is never silently recorded as a fail outcome): "
                + "; ".join(f"{cid}: {type(exc).__name__}: {exc}" for cid, exc in errors) +
                f". {evaluated} already-written record(s) under {RECORDS_DIR} are untouched (including any "
                f"successful sibling from this same chunk, already written above). Fix the root cause and "
                f"re-run `run` -- already-recorded candidates are skipped (resumable).")
    print(f"stopped: {evaluated} evaluated, {passed} passed")


# ------------------------------------------------------------------------------------------------ `report`

def cmd_report():
    plan = load_plan()
    recs = []
    if os.path.isdir(RECORDS_DIR):
        for f in sorted(os.listdir(RECORDS_DIR)):
            if f.endswith(".json"):
                rec = X.load(f[:-5], store=RECORDS_DIR)
                _validate_record_against_plan(rec, plan)   # fix round 2, item 2 -- same refusal as `run`
                recs.append(rec)
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
        "## Pass criteria (verbatim from the pre-registration, §2, and addendum §8)", "",
        f"1. `prop_pass_probability` >= {PASS_PROB_THRESHOLD} under BOTH `ftmo-challenge-phase1` AND "
        f"`the5ers-high-stakes-step1`, each fund judged on its own, at a {CHALLENGE_HORIZON_DAYS}-trading-day "
        f"horizon (addendum §8.1 -- {list(INFORMATIONAL_HORIZON_DAYS)}-day horizons are also recorded per "
        f"candidate for information and never gate).",
        "2. Each fund's OWN day-count rule: FTMO requires >= 4 days a trade was INITIATED; The5ers requires "
        ">= 3 PROFITABLE days (closed profit >= 0.5% of initial balance that day) and fails on 30 consecutive "
        "calendar days with no trade (addendum §8.3) -- and the bootstrap has the sample it needs to run at "
        "all (n >= 5).",
        "3. The one-sided 90% bootstrap lower bound of mean net R on the validation trades is > 0. There is "
        "NO fixed minimum trade count beyond that. Validation trades whose true outcome would need a bar "
        "after the PIT cutoff are excluded from this and every other criterion (addendum §8.2).", "",
        "## Multiple-testing caveat", "",
        f"{evaluated} candidates were evaluated on the SAME validation window in the search for these passes "
        f"(CLAUDE.md §43/§45: repeated selection over one window inflates the apparent hit rate above what "
        f"any single candidate's own numbers suggest). A PASS here is a candidate that cleared the "
        f"pre-registered bar on the first and only look this search grants the validation window -- it is "
        f"NOT yet forward-confirmed (`{PREREG_DOC}` §4: forward confirmation on live demo is required before "
        f"any funded attempt), and the validation window is EXPOSED as of "
        + (f"{min(recs, key=lambda r: r['timestamp'])['timestamp']} "
           f"(first record: `{min(recs, key=lambda r: r['timestamp'])['experiment_id']}`)." if recs
           else "the first evaluation recorded here (none yet)."),
        "",
        "## Every evaluated candidate", "",
        "| # | id | method | config | tf | group | prop_pass_probability (FTMO / The5ers) | day count "
        "(FTMO trading / The5ers profitable) | excluded unfinished | expectancy LB (net R) | PASS |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(recs, 1):
        v = r["metrics"]["validation"]
        pd = v["pass_detail"]
        params = r["parameters"]
        lb = v["expectancy_lower_bound"]
        lb_val = lb.get("value") if isinstance(lb, dict) and "value" in lb else None
        dc = v.get("day_counts", {})
        lines.append(
            f"| {i} | {r['experiment_id']} | {params['method']} | {params['config']} | "
            f"{params['timeframe']} | {params['group_kind']}={params['group_id']} | "
            f"{fund_cell(pd, FUNDS[0])} / {fund_cell(pd, FUNDS[1])} | "
            f"{dc.get(FUNDS[0], 'n/a')} / {dc.get(FUNDS[1], 'n/a')} | "
            f"{v.get('excluded_unfinished_trades', 0)} | "
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
