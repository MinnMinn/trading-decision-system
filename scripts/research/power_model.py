#!/usr/bin/env python3
"""MODEL-based power analysis of the fund-search lower-bound rule (2026-10-01). Reads NO data and NO performance.

Everything here is a simulation on synthetic trades. The only inputs are (a) the trade RATES per cell quoted in
docs/audits/2026-10-01-trade-rates.md (counts only), (b) the owner's fixed spans / N / confidence rule, and (c) labelled
ASSUMPTIONS (see ASSUMPTIONS below). Deterministic: every random stream is seeded from crc32(label) + BASE_SEED.

The harness functions are IMPORTED and CALLED, never reimplemented:
  * scripts/fund_stats.py robust_lower_bound (line 224) = min(iid Student-t bound (lower_bound, 163), CR1 by UTC entry
    date, 30-day window, calendar quarter, half-year (_block_bound, 182)) at confidence n_adjusted_confidence(N) (152);
    t_quantile (130); pass rule = check_lower_bound (497): value is not None and value > 0.
  * scripts/performance.py metrics (405) -> prop_pass_probability, called with scripts/prop-search.py's own FUNDS,
    CHALLENGE_HORIZON_DAYS (120) and account profiles (_AP.get(fund)).
The only wrapper is a pure memo on fund_stats.ts (ISO-string -> datetime), cleared every replication; `selfcheck`
asserts the memoised bound equals the un-memoised one.

Usage:  python3 scripts/research/power_model.py --out /tmp/power.json [--quick] [--procs 4]
"""
import argparse
import datetime
import functools
import importlib.util
import json
import math
import os
import sys
import time
import zlib
from multiprocessing import Pool

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import fund_stats as FS          # noqa: E402  the harness's own bound functions
_ORIG_TS = FS.ts
FS.ts = functools.lru_cache(maxsize=None)(_ORIG_TS)   # pure memo; cleared per replication

BASE_SEED = 20261001
CUTOFF = np.datetime64("2024-03-01")      # fund_stats.DEV_CUTOFF (line 42): test folds are 365-day blocks ending here
FOLD_DAYS = 365                           # fund_stats.TEST_FOLD_DAYS (line 52)

# ---- owner-fixed inputs (dispatch + coordinator updates 2026-10-01: the cells keep their original data start, so
# 1m-metals 9 folds, 1m-indices 4, 5m-metals 17 (all six cells use dev_start from data; the dispatch's 4 / 2 / 14 were
# withdrawn the same day) -----------------------------------------------------------------------------------------------
# cell -> (folds F, symbols k0 in the cell, ICT trades/yr pooled, Wyckoff trades/yr pooled)
CELLS = {
    "1m-metals":   (9, 2, 676, 449),
    "1m-indices":  (4, 5, 1850, 1213),
    "5m-metals":   (17, 2, 112, 113),
    "5m-indices":  (4, 5, 335, 258),
    "15m-metals":  (17, 2, 35, 45),
    "15m-indices": (4, 5, 100, 93),
}
N_COMP = {"ICT": 174, "WYCKOFF": 96}
N_GRID = {"ICT": [174, 120, 96, 75, 50], "WYCKOFF": [96, 75, 50, 30]}
EGRID = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.80, 1.00, 1.50]
E_REQUIRED = [0.10, 0.15, 0.20, 0.30, 0.40]          # the dispatch's required curve points
SENS_E = [0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.60, 1.00]   # reduced e grid of the assumption-sensitivity runs
PROP_TRADES = 20000                                  # target length of the synthetic stream of the prop link
E_OWNER = 0.20                                        # owner-decisions doc: e set to 0.20R (pre-declaration default)
WIN_R, LOSS_R = 2.5, -1.0                             # binary outcome: +2.5R with prob p, -1R otherwise

# ---- ASSUMPTIONS (every one is a model choice, NOT a measurement) ---------------------------------------------
BASE = {"cost": 0.07,    # A1 cost c in R subtracted from every trade (dispatch: 0.05-0.10R)
        "sigma": 0.75,   # A2 month-level lognormal sigma of the arrival-rate multiplier (dispatch: 0.5-1.0)
        "tau": 0.03,     # A3 month-level regime shift in win probability p (sd, in p units; = 0.105R sd of the monthly mean at +2.5/-1)
        "rho": 0.30}     # A4 cross-symbol correlation of the monthly regime (rate AND outcome)
ASSUMPTIONS = [
    "A1 cost c = 0.07R per trade (sensitivity 0.05 / 0.10). e is the NET edge: net_R = (+2.5 | -1) - c, so p = (e + 1 + c)/3.5.",
    "A2 arrivals: Poisson per UTC weekday (weekends 0); the per-symbol daily rate is multiplied by a lognormal month multiplier "
    "exp(sigma*z - sigma^2/2) (mean 1), sigma = 0.75 (sensitivity 0 / 0.5 / 1.0). Intraday time uniform. No session structure.",
    "A3 regime-dependent outcome: the win probability of a trade in month m is p + tau*z_m (clipped to [0,1]), tau = 0.03 "
    "(sensitivity 0 / 0.06); mean p, hence the mean edge e, is unchanged. This, not the rate multiplier alone, is what the "
    "block bounds can penalise (rate variation with iid outcomes only costs them degrees of freedom).",
    "A4 cross-symbol correlation rho = 0.30 of the monthly regime z (z_sym = sqrt(rho) z_common + sqrt(1-rho) z_idio), applied to "
    "both the rate and the outcome shift (sensitivity 0 / 0.6). Symbols in a cell are assumed exchangeable (same per-symbol rate).",
    "A5 binary +2.5R / -1R outcomes: no time-stops, partials, breakevens or realised-R shrinkage; realised R of real trades differs.",
    "A6 trade rates are the 2021-2023 slice rates of docs/audits/2026-10-01-trade-rates.md (pooled ADMITTED trades/yr per cell), "
    "taken as the expected long-run rate over all F folds; the real rate over older history may differ (index S1 is a lower bound).",
    "A7 folds are 365-day blocks ending 2024-03-01, F per cell as fixed by the owner; pooled TEST trades = all trades in those F years.",
    "A8 prop link: pooled synthetic stream of max(20 years, 20000 trades) (population answer: removes the small-sample noise of the real F-year stream, whose realised mean has sd ~1.6/sqrt(n) R), "
    "performance.metrics(..., horizon=120) with each fund's own account profile (1% risk/trade via effective_risk_pct, 5% daily loss "
    "on day-start equity, 10% max DD, profit target 10%/8%, FTMO min 4 trading days, The5ers 3 profitable days >= 0.5%). The "
    "harness's live_parity_sizing changes only pnl/size of `taken` trades, not net_R; performance.metrics reads net_R only "
    "(_r, performance.py:142), so it is not reproducible nor needed here; the 2-consecutive-loss risk halving is therefore NOT modelled.",
    "A9 replications: 200 per (method, cell, e) on the main grid, 100 on sensitivity / option grids; Monte-Carlo SE of a power "
    "estimate <= 0.035 (0.05 at 100). e_min is 'the first grid value with estimated power >= 0.80'.",
]


def seed_for(*labels):
    return (zlib.crc32("|".join(str(x) for x in labels).encode()) + BASE_SEED) % (2 ** 32)


def p_from_edge(e, cost):
    p = (e + 1.0 + cost) / (WIN_R - LOSS_R)
    if not 0.0 < p < 1.0:
        raise ValueError(f"edge {e} with cost {cost} gives p={p}")
    return p


# ---- synthetic stream -------------------------------------------------------------------------------------------
def gen_stream(rng, rate_per_sym_year, k, folds, p, sigma, tau, rho, cost, sym_first_day=None):
    """One synthetic pooled TEST-trade stream over `folds` 365-day folds ending 2024-03-01.
    Returns trades [{entry_time, net_R, symbol}] sorted by time, and trades-per-fold counts.
    b16 extension (defaults reproduce the original streams bit for bit): `rate_per_sym_year` may be a length-k sequence
    (per-symbol rates) and `sym_first_day` a length-k sequence of day offsets from the stream start before which that
    symbol has no trades (late-starting data)."""
    n_days = folds * FOLD_DAYS
    day0 = CUTOFF - np.timedelta64(n_days, "D")
    days = day0 + np.arange(n_days).astype("timedelta64[D]")
    dow = (days.astype("datetime64[D]").astype(np.int64) + 3) % 7        # Monday = 0
    wd = (dow < 5).astype(float)
    months = days.astype("datetime64[M]").astype(np.int64)
    _, m_idx = np.unique(months, return_inverse=True)
    n_m = int(m_idx.max()) + 1

    def mixed():
        zc = rng.standard_normal(n_m)
        zs = rng.standard_normal((k, n_m))
        return math.sqrt(rho) * zc[None, :] + math.sqrt(1.0 - rho) * zs

    z_rate = mixed()
    z_out = mixed()
    mult = np.exp(sigma * z_rate - 0.5 * sigma * sigma)                 # (k, months), mean 1
    lam_year = np.asarray(rate_per_sym_year, dtype=float).reshape(-1, 1) / (FOLD_DAYS * 5.0 / 7.0)   # per weekday
    lam = lam_year * mult[:, m_idx] * wd[None, :]                      # (k, days)
    if sym_first_day is not None:
        lam = lam * (np.arange(n_days)[None, :] >= np.asarray(sym_first_day)[:, None])
    counts = rng.poisson(lam)
    sym_i, day_i = np.nonzero(counts)
    reps = counts[sym_i, day_i]
    sym = np.repeat(sym_i, reps)
    day = np.repeat(day_i, reps)
    n = len(sym)
    sec = rng.integers(0, 86400, size=n)
    p_tr = np.clip(p + tau * z_out[sym, m_idx[day]], 0.0, 1.0)
    win = rng.random(n) < p_tr
    net = np.where(win, WIN_R, LOSS_R) - cost
    order = np.lexsort((sec, day))
    sym, day, sec, net = sym[order], day[order], sec[order], net[order]
    t64 = (day0 + day.astype("timedelta64[D]")).astype("datetime64[s]") + sec.astype("timedelta64[s]")
    strs = np.datetime_as_string(t64, unit="s")
    trades = [{"entry_time": s + "Z", "net_R": float(r), "symbol": int(y)} for s, r, y in zip(strs, net, sym)]
    per_fold = np.bincount(day // FOLD_DAYS, minlength=folds)
    return trades, per_fold


COMPONENTS = ("iid", "block_date", "block_30d", "block_quarter", "block_half")
VARIANTS = {"full": COMPONENTS, "iid_only": ("iid",),
            "drop_iid": COMPONENTS[1:], "drop_date": ("iid", "block_30d", "block_quarter", "block_half"),
            "drop_30d": ("iid", "block_date", "block_quarter", "block_half"),
            "drop_quarter": ("iid", "block_date", "block_30d", "block_half"),
            "drop_half": ("iid", "block_date", "block_30d", "block_quarter")}


def variant_pass(lb, comps):
    vals = [lb[c] for c in comps]
    return all(v is not None for v in vals) and min(vals) > 0


# ---- power job ----------------------------------------------------------------------------------------------
def run_power(job):
    """Power of the harness rule over `reps` synthetic streams for each e in job['e_list'] and each N in job['N_list'].
    Returns per-e: power per N (the real rule, FS.check_lower_bound semantics), variant powers at the first N
    (each bound dropped in turn, information only), mean trades, P(every fold >= 30), effective-n."""
    cost, sigma, tau, rho = job["cost"], job["sigma"], job["tau"], job["rho"]
    confs = [FS.n_adjusted_confidence(n) for n in job["N_list"]]
    out = {}
    for e in job["e_list"]:
        p = p_from_edge(e, cost)
        rng = np.random.default_rng(seed_for(job["label"], e, job["folds"], job["k"], sigma, tau, rho, cost))
        hits = {n: 0 for n in job["N_list"]}
        var_hits = {v: 0 for v in VARIANTS}
        ns, folds_ok, means, sds = [], 0, [], []
        for _ in range(job["reps"]):
            tr, per_fold = gen_stream(rng, job["rate_sym"], job["k"], job["folds"], p, sigma, tau, rho, cost,
                                      job.get("sym_first_day"))
            ns.append(len(tr))
            folds_ok += int(per_fold.min() >= FS.MIN_FOLD_TRADES)
            if len(tr) >= 2:
                rs = [t["net_R"] for t in tr]
                means.append(sum(rs) / len(rs))
                sds.append(float(np.std(rs, ddof=1)))
            for n, conf in zip(job["N_list"], confs):
                chk = FS.check_lower_bound(tr, conf)         # the harness's own pass test (fund_stats.py:497)
                lb = chk["bound"]
                hits[n] += int(chk["ok"])
                if n == job["N_list"][0]:
                    for v, comps in VARIANTS.items():
                        var_hits[v] += int(variant_pass(lb, comps))
            FS.ts.cache_clear()
        reps = job["reps"]
        var_m = float(np.var(means, ddof=1)) if len(means) > 1 else float("nan")
        out[str(e)] = {"power": {str(n): hits[n] / reps for n in job["N_list"]},
                       "variants": {v: c / reps for v, c in var_hits.items()},
                       "n_mean": float(np.mean(ns)), "p_all_folds_ge_min": folds_ok / reps,
                       "n_eff": (float(np.mean(sds)) ** 2 / var_m) if var_m and var_m > 0 else None}
    return {"job": {k: job[k] for k in ("label", "method", "cell", "folds", "k", "reps", "N_list", "cost", "sigma", "tau", "rho", "rate_sym")},
            "by_e": out}


FSCAN = [2, 3, 4, 5, 6, 8, 10, 12, 15, 17, 20, 25, 30, 40, 60]
FSCAN_MAX_TRADES = 30000          # do not scan a fold count whose expected pooled trades exceed this (runtime guard)


def run_fscan(job):
    """Power vs number of test folds at the cell's own rate, for every e in job['e_list']; ascending F, stops once every e
    has reached power >= 0.80 or the expected trade count exceeds FSCAN_MAX_TRADES (then the remaining F are not scanned)."""
    by_f = {}
    need = set(job["e_list"])
    for f in FSCAN:
        if job["rate_sym"] * job["k"] * f > FSCAN_MAX_TRADES and by_f:
            break
        sub = dict(job, folds=f, e_list=sorted(need), label=f"fscan|{f}|{job['method']}|{job['cell']}")
        r = run_power(sub)["by_e"]
        by_f[str(f)] = r
        for e in list(need):
            if r[str(e)]["power"][str(job["N_list"][0])] >= 0.80:
                need.discard(e)
        if not need:
            break
    return {"job": {k: job[k] for k in ("label", "method", "cell", "k", "reps", "N_list", "cost", "sigma", "tau", "rho", "rate_sym")},
            "by_f": by_f}


# ---- false-positive sanity check -------------------------------------------------------------------------------
def run_fp(job):
    """True net edge 0: fraction of replications where the harness rule returns bound > 0, at confidence 1-0.10/N."""
    rng = np.random.default_rng(seed_for("fp", job["label"], job["N"], job["sigma"], job["tau"]))
    p = p_from_edge(0.0, job["cost"])
    conf = FS.n_adjusted_confidence(job["N"])
    hit = 0
    for _ in range(job["reps"]):
        tr, _ = gen_stream(rng, job["rate_sym"], job["k"], job["folds"], p, job["sigma"], job["tau"], job["rho"], job["cost"])
        hit += int(FS.check_lower_bound(tr, conf)["ok"])
        FS.ts.cache_clear()
    return {"job": {k: job[k] for k in ("label", "method", "cell", "N", "reps", "sigma", "tau")}, "fp": hit, "reps": job["reps"],
            "nominal": 0.10 / job["N"], "wilson_upper95": wilson_upper(hit, job["reps"])}


def wilson_upper(x, n, z=1.6449):      # one-sided 95 %
    ph = x / n
    d = 1 + z * z / n
    c = ph + z * z / (2 * n)
    a = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))
    return (c + a) / d


# ---- prop link ----------------------------------------------------------------------------------------------------
_PS = None


def _prop_search():
    global _PS
    if _PS is None:
        spec = importlib.util.spec_from_file_location("ps_pm", os.path.join(ROOT, "scripts", "prop-search.py"))
        _PS = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_PS)
    return _PS


_FSM = None


def _fund_search():
    global _FSM
    if _FSM is None:
        spec = importlib.util.spec_from_file_location("fs_pm", os.path.join(ROOT, "scripts", "fund-search.py"))
        _FSM = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_FSM)
    return _FSM


def prop_pass_value(ps, fund, trades, years=None):
    """`years` (D4/D5): the stream's span in 365-day folds ending at the cutoff; given, the prop pass counts its horizon in
    weekdays and sizes risk by the frequency rule exactly as the harness does (fund-search.prop_kwargs)."""
    acct = ps._AP.get(fund)
    kw = {}
    if years is not None:
        import fund_stats as _FS
        end = datetime.datetime(2024, 3, 1, tzinfo=datetime.timezone.utc)
        span = [{"test_start": (end - datetime.timedelta(days=365 * int(years))).isoformat(), "test_end": end.isoformat()}]
        kw = _fund_search().prop_kwargs(ps, acct, trades, _FS.test_weekdays(span))
    m = ps._perf.metrics(trades, account=acct, horizon=ps.CHALLENGE_HORIZON_DAYS, **kw)
    v = m.get("prop_pass_probability")
    return v.get("value") if isinstance(v, dict) else None


def run_prop(job):
    ps = _prop_search()
    cost, sigma, tau, rho = job["cost"], job["sigma"], job["tau"], job["rho"]
    years = job["years"]

    def stream(e):      # common random numbers across e: same seed, only the win threshold p changes
        rng = np.random.default_rng(seed_for("prop", job["label"], sigma, tau, rho, cost))
        tr, _ = gen_stream(rng, job["rate_sym"], job["k"], years, p_from_edge(e, cost), sigma, tau, rho, cost)
        return tr

    res = {"job": {k: job[k] for k in ("label", "method", "cell", "years", "cost", "sigma", "tau", "rho", "rate_sym", "k")},
           "by_fund": {}}
    cache = {}

    def value(fund, e):
        key = (fund, round(e, 4))
        if key not in cache:
            tr = stream(e)
            cache[key] = prop_pass_value(ps, fund, tr, years=years)
        return cache[key]

    tr0 = stream(0.2)
    res["n_trades"] = len(tr0)
    res["trades_per_active_day"] = len(tr0) / len({t["entry_time"][:10] for t in tr0})
    for fund in ps.FUNDS:
        curve = {str(e): value(fund, e) for e in (0.0, 0.05, 0.10, 0.20)}
        lo, hi = 0.0, 1.0
        v_hi = value(fund, hi)
        if v_hi is None or v_hi < ps.PASS_PROB_THRESHOLD:
            e_star = None
        else:
            for _ in range(9):
                mid = (lo + hi) / 2
                v = value(fund, mid)
                if v is not None and v >= ps.PASS_PROB_THRESHOLD:
                    hi = mid
                else:
                    lo = mid
            e_star = hi
        res["by_fund"][fund] = {"curve": curve, "e_for_pass_070": e_star}
    return res


# ---- scheduling -----------------------------------------------------------------------------------------------------
def _dispatch(item):
    kind, job = item
    return kind, {"power": run_power, "fp": run_fp, "prop": run_prop, "fscan": run_fscan}[kind](job)


def make_job(method, cell, *, folds=None, k=None, e_list, reps, N_list=None, label=None, **over):
    F0, k0, ict, wy = CELLS[cell]
    rate = ict if method == "ICT" else wy
    cfg = dict(BASE)
    cfg.update(over)
    return dict(label=label or f"{method}|{cell}", method=method, cell=cell, folds=folds or F0, k=k or k0,
                rate_sym=rate / k0, e_list=e_list, reps=reps, N_list=N_list or [N_COMP[method]], **cfg)


def build_jobs(quick):
    R_MAIN, R_OPT = (40, 25) if quick else (200, 100)
    jobs = []
    methods = ("ICT", "WYCKOFF")
    # 1. main power grid (base assumptions) with the N sensitivity on the same streams + per-bound variants
    for m in methods:
        for c in CELLS:
            jobs.append(("power", make_job(m, c, e_list=EGRID, reps=R_MAIN, N_list=N_GRID[m], label=f"main|{m}|{c}")))
    # 2. assumption sensitivity (one at a time), reduced e grid
    e_s = SENS_E
    for m in methods:
        for c in CELLS:
            for name, vals in (("sigma", (0.0, 0.5, 1.0)), ("tau", (0.0, 0.06)), ("rho", (0.0, 0.6)), ("cost", (0.05, 0.10))):
                for v in vals:
                    jobs.append(("power", make_job(m, c, e_list=e_s, reps=R_OPT, label=f"sens|{name}={v}|{m}|{c}", **{name: v})))
    # 3. more symbols in a cell (k0+{1,2,4}) x rho {0,0.3,0.6}; e = 0.10 / 0.20 / 0.30
    for m in methods:
        for c in CELLS:
            k0 = CELLS[c][1]
            for extra in (1, 2, 4):
                for rho in (0.0, 0.3, 0.6):
                    jobs.append(("power", make_job(m, c, k=k0 + extra, e_list=[0.10, 0.20, 0.30], reps=R_OPT,
                                                   label=f"sym|+{extra}|{m}|{c}", rho=rho)))
            for rho in (0.0, 0.6):      # base composition at the other rho (0.3 is the main grid)
                jobs.append(("power", make_job(m, c, e_list=[0.10, 0.20, 0.30], reps=R_OPT, label=f"sym|+0|{m}|{c}", rho=rho)))
    # 4. more folds (longer history): F0+{1,2,4}; e = 0.10 / 0.20 / 0.30
    for m in methods:
        for c in CELLS:
            F0 = CELLS[c][0]
            fl = [F0 + 1, F0 + 2, F0 + 4]
            for f in fl:
                jobs.append(("power", make_job(m, c, folds=f, e_list=[0.10, 0.20, 0.30], reps=R_OPT, label=f"folds|{f}|{m}|{c}")))
    # 5. n_req vs e: power vs folds scan (cell's own trade rate), e in E_REQUIRED
    for m in methods:
        for c in CELLS:
            jobs.append(("fscan", make_job(m, c, e_list=E_REQUIRED, reps=R_OPT, label=f"fscan|{m}|{c}")))
    # 6. false-positive sanity (true net edge 0)
    for m in methods:
        for c in CELLS:
            F0, k0, ict, wy = CELLS[c]
            base = dict(label=f"{m}|{c}", method=m, cell=c, folds=F0, k=k0, rate_sym=(ict if m == "ICT" else wy) / k0,
                        cost=BASE["cost"], rho=BASE["rho"])
            jobs.append(("fp", dict(base, N=N_COMP[m], reps=300 if quick else 2000, sigma=BASE["sigma"], tau=BASE["tau"])))
            jobs.append(("fp", dict(base, N=1, reps=150 if quick else 1500, sigma=BASE["sigma"], tau=BASE["tau"])))
            jobs.append(("fp", dict(base, N=N_COMP[m], reps=150 if quick else 600, sigma=0.0, tau=0.0)))
    # 7. prop link
    for m in methods:
        for c in CELLS:
            F0, k0, ict, wy = CELLS[c]
            rate_total = ict if m == "ICT" else wy
            # population answer: a stream of ~PROP_TRADES trades (>= 20 years), so the realised mean of the synthetic stream is
            # within ~0.012R of e and the pass probability is the model's, not that of one lucky/unlucky small sample
            years = 6 if quick else max(20, math.ceil(PROP_TRADES / rate_total))
            jobs.append(("prop", dict(label=f"{m}|{c}", method=m, cell=c, years=years, k=k0,
                                      rate_sym=rate_total / k0, **BASE)))
    # heavy jobs first for load balance
    def weight(it):
        j = it[1]
        if it[0] == "prop":
            return j["rate_sym"] * j["k"] * j["years"] * 4
        if it[0] == "fp":
            return j["rate_sym"] * j["k"] * j["folds"] * j["reps"]
        if it[0] == "fscan":
            return j["rate_sym"] * j["k"] * 20 * j["reps"] * len(j["e_list"])
        return j["rate_sym"] * j["k"] * j["folds"] * j["reps"] * len(j["e_list"]) * max(1, len(j["N_list"]) * 0.6)
    jobs.sort(key=weight, reverse=True)
    return jobs


def selfcheck():
    """(1) the memoised ts gives the same robust_lower_bound as the un-memoised harness ts; (2) the harness rule on a known
    toy stream is what this file thinks it is."""
    rng = np.random.default_rng(1)
    tr, _ = gen_stream(rng, 100.0, 2, 3, p_from_edge(0.3, 0.07), BASE["sigma"], BASE["tau"], BASE["rho"], BASE["cost"])
    conf = FS.n_adjusted_confidence(174)
    a = FS.robust_lower_bound(tr, conf)
    FS.ts = _ORIG_TS
    b = FS.robust_lower_bound(tr, conf)
    FS.ts = functools.lru_cache(maxsize=None)(_ORIG_TS)
    assert a == b, "memoised ts changed robust_lower_bound"
    return {"n": a["n"], "value": a["value"], "components": {c: a[c] for c in COMPONENTS}, "memo_equal": True}


def aggregate(results):
    agg = {"power": [], "fp": [], "prop": [], "fscan": []}
    for kind, r in results:
        agg[kind].append(r)
    return agg


# ---- report (markdown tables from the JSON; every number in docs/audits/2026-10-01-power-model.md comes from here) -------
def _fmt(x, nd=2):
    return "n/a" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))


def emin_of(by_e, key):
    """First grid value whose estimated power >= 0.80 (None when never reached on the grid)."""
    for e in sorted(by_e, key=float):
        if by_e[e]["power"][key] >= 0.80:
            return float(e)
    return None


def report(doc):
    P = {}
    for r in doc["power"]:
        j = r["job"]
        P[(j["label"], j["rho"], j["k"], j["folds"], j["sigma"], j["tau"], j["cost"])] = r
    B = doc["meta"]["base"]
    cells = doc["meta"]["cells"]
    N = doc["meta"]["N"]
    eg = doc["meta"]["egrid"]
    L = []

    def main(m, c):
        return P[(f"main|{m}|{c}", B["rho"], cells[c][1], cells[c][0], B["sigma"], B["tau"], B["cost"])]

    methods = ("ICT", "WYCKOFF")
    L.append("## R0 Critical values the rule applies (FS.t_quantile, one-sided; blocks counted as if every block holds a trade)\n")
    L.append("| cell | folds | n (ICT) | t iid (df n-1) | blocks half-year 2F+1 -> t | blocks quarter 4F+1 -> t | blocks 30-day ~365F/30+1 -> t |   |")
    L.append("|---|---|---|---|---|---|---|---|")
    for c, (F0, k0, ict, wy) in cells.items():
        conf = FS.n_adjusted_confidence(N["ICT"])
        gh, gq, gw = 2 * F0 + 1, 4 * F0 + 1, int(365 * F0 / 30) + 1
        L.append(f"| {c} | {F0} | {ict * F0} | {FS.t_quantile(conf, ict * F0 - 1):.2f} | {gh} -> {FS.t_quantile(conf, gh - 1):.2f} | "
                 f"{gq} -> {FS.t_quantile(conf, gq - 1):.2f} | {gw} -> {FS.t_quantile(conf, gw - 1):.2f} | (ICT, N={N['ICT']}) |")
    L.append("\n## R1 Power of the harness lower-bound rule, base assumptions (sigma %.2f, tau %.2f, rho %.2f, c %.2f R)" % (B["sigma"], B["tau"], B["rho"], B["cost"]))
    for m in methods:
        reps = main(m, "1m-metals")["job"]["reps"]
        L.append(f"\n### {m}, N = {N[m]}, confidence {1 - 0.10 / N[m]:.6f} (P(rule returns > 0); {reps} replications per cell and e)\n")
        L.append("| cell | folds | E[n] | " + " | ".join(f"e={e:.2f}" for e in eg) + " | e_min |")
        L.append("|---|---|---|" + "---|" * (len(eg) + 1))
        for c in cells:
            by = main(m, c)["by_e"]
            row = [f"{by[str(e)]['power'][str(N[m])]:.2f}" for e in eg]
            em = emin_of(by, str(N[m]))
            L.append(f"| {c} | {cells[c][0]} | {by['0.2']['n_mean']:.0f} | " + " | ".join(row) + f" | {'>1.50' if em is None else f'{em:.2f}'} |")

    L.append("\n## R2 e_min (first grid e with power >= 0.80) under each assumption set\n")
    hdr = ["base", "sigma=0", "sigma=0.5", "sigma=1.0", "tau=0", "tau=0.06", "rho=0", "rho=0.6", "c=0.05", "c=0.10"]
    sens = [None, ("sigma", 0.0), ("sigma", 0.5), ("sigma", 1.0), ("tau", 0.0), ("tau", 0.06), ("rho", 0.0), ("rho", 0.6), ("cost", 0.05), ("cost", 0.10)]
    for m in methods:
        L.append(f"\n### {m}  (reduced grid e in {SENS_E} for every column, including base)\n")
        L.append("| cell | " + " | ".join(hdr) + " |")
        L.append("|---|" + "---|" * len(hdr))
        for c in cells:
            row = []
            for sv in sens:
                if sv is None:
                    by = {e: v for e, v in main(m, c)["by_e"].items() if float(e) in SENS_E}
                else:
                    name, v = sv
                    cfg = dict(rho=B["rho"], sigma=B["sigma"], tau=B["tau"], cost=B["cost"])
                    cfg[name] = v
                    by = P[(f"sens|{name}={v}|{m}|{c}", cfg["rho"], cells[c][1], cells[c][0], cfg["sigma"], cfg["tau"], cfg["cost"])]["by_e"]
                em = emin_of(by, str(N[m]))
                row.append(">1.00" if em is None else f"{em:.2f}")
            L.append(f"| {c} | " + " | ".join(row) + " |")

    L.append("\n## R3 False-positive sanity (true net edge 0; rule returns > 0)\n")
    L.append("| method | cell | N | sigma/tau | reps | false positives | rate | nominal 0.10/N | Wilson 95% upper |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for r in sorted(doc["fp"], key=lambda r: (r["job"]["method"], list(cells).index(r["job"]["cell"]), r["job"]["N"], -r["job"]["sigma"])):
        j = r["job"]
        L.append(f"| {j['method']} | {j['cell']} | {j['N']} | {j['sigma']}/{j['tau']} | {r['reps']} | {r['fp']} | {r['fp'] / r['reps']:.4f} | {r['nominal']:.5f} | {r['wilson_upper95']:.4f} |")

    L.append("\n## R4 Prop-pass link: net edge e at which prop_pass_probability (120-day horizon) first reaches 0.70 (bisection on e in [0,1], 9 steps; population stream of max(20 years, 20000 trades); the 120 'days' are 120 resampled ACTIVE days)\n")
    L.append("| method | cell | trades/yr | trades per active day | e* FTMO | e* The5ers | binding e* (max) | pass prob FTMO at e=0/0.05/0.10/0.20 | pass prob The5ers at e=0/0.05/0.10/0.20 |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for r in sorted(doc["prop"], key=lambda r: (r["job"]["method"], list(cells).index(r["job"]["cell"]))):
        j = r["job"]
        f1, f2 = r["by_fund"]["ftmo-challenge-phase1"], r["by_fund"]["the5ers-high-stakes-step1"]
        es = [f1["e_for_pass_070"], f2["e_for_pass_070"]]
        bind = None if any(x is None for x in es) else max(es)

        def cv(f):
            return "/".join(_fmt(f["curve"][k]) for k in ("0.0", "0.05", "0.1", "0.2"))
        L.append(f"| {j['method']} | {j['cell']} | {j['rate_sym'] * j['k']:.0f} | {r['trades_per_active_day']:.2f} | {_fmt(es[0], 3)} | {_fmt(es[1], 3)} | {_fmt(bind, 3)} | {cv(f1)} | {cv(f2)} |")

    L.append("\n## R5a N sensitivity: power at e = 0.20 and e_min per N (same streams)\n")
    for m in methods:
        L.append(f"\n### {m}\n")
        Nl = [str(x) for x in main(m, "1m-metals")["job"]["N_list"]]
        L.append("| cell | " + " | ".join(f"P@0.20 N={n}" for n in Nl) + " | " + " | ".join(f"e_min N={n}" for n in Nl) + " |")
        L.append("|---|" + "---|" * (2 * len(Nl)))
        for c in cells:
            by = main(m, c)["by_e"]
            L.append(f"| {c} | " + " | ".join(f"{by['0.2']['power'][n]:.2f}" for n in Nl) + " | " + " | ".join(
                (">1.50" if emin_of(by, n) is None else f"{emin_of(by, n):.2f}") for n in Nl) + " |")

    L.append("\n## R5b Which bound costs the power (information only; power at e = 0.20 and e = 0.30, base N)\n")
    for m in methods:
        L.append(f"\n### {m}\n")
        names = list(VARIANTS)
        L.append("| cell | e | " + " | ".join(names) + " |")
        L.append("|---|---|" + "---|" * len(names))
        for c in cells:
            by = main(m, c)["by_e"]
            for e in ("0.2", "0.3"):
                L.append(f"| {c} | {e} | " + " | ".join(f"{by[e]['variants'][v]:.2f}" for v in names) + " |")

    L.append("\n## R5c More symbols in a cell: power at e = 0.10 / 0.20 / 0.30 and effective n (sd^2 / Var(mean), e=0.20 streams)\n")
    for m in methods:
        L.append(f"\n### {m}\n")
        L.append("| cell | +symbols | rho | E[n] | P@0.10 | P@0.20 | P@0.30 | n_eff | n_eff/n |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for c in cells:
            k0 = cells[c][1]
            for extra in (0, 1, 2, 4):
                for rho in (0.0, 0.3, 0.6):
                    if extra == 0:
                        key = (f"main|{m}|{c}", rho, k0, cells[c][0], B["sigma"], B["tau"], B["cost"]) if rho == B["rho"] else \
                              (f"sym|+0|{m}|{c}", rho, k0, cells[c][0], B["sigma"], B["tau"], B["cost"])
                    else:
                        key = (f"sym|+{extra}|{m}|{c}", rho, k0 + extra, cells[c][0], B["sigma"], B["tau"], B["cost"])
                    by = P[key]["by_e"]
                    ne = by["0.2"]["n_eff"]

                    def pw(e):
                        return by[e]["power"][str(N[m])]
                    L.append(f"| {c} | +{extra} | {rho} | {by['0.2']['n_mean']:.0f} | {pw('0.1'):.2f} | {pw('0.2'):.2f} | {pw('0.3'):.2f} | {_fmt(ne, 0)} | {_fmt(None if ne is None else ne / by['0.2']['n_mean'])} |")

    L.append("\n## R5d More test folds (longer history): power at e = 0.10 / 0.20 / 0.30\n")
    for m in methods:
        L.append(f"\n### {m}\n")
        L.append("| cell | folds | E[n] | P@0.10 | P@0.20 | P@0.30 |")
        L.append("|---|---|---|---|---|---|")
        for c in cells:
            F0 = cells[c][0]
            for f in (F0, F0 + 1, F0 + 2, F0 + 4):
                key = (f"main|{m}|{c}" if f == F0 else f"folds|{f}|{m}|{c}", B["rho"], cells[c][1], f, B["sigma"], B["tau"], B["cost"])
                by = P[key]["by_e"]

                def pw(e):
                    return by[e]["power"][str(N[m])]
                L.append(f"| {c} | {f} | {by['0.2']['n_mean']:.0f} | {pw('0.1'):.2f} | {pw('0.2'):.2f} | {pw('0.3'):.2f} |")

    L.append("\n## R5e Test folds (years) needed for power >= 0.80 vs the minimum edge of interest e, at each cell's trade rate\n")
    FS_ = {(r["job"]["method"], r["job"]["cell"]): r for r in doc["fscan"]}
    for m in methods:
        L.append(f"\n### {m}  (first scanned fold count F with power >= 0.80 / expected pooled trades at that F = n_req; scan F = {FSCAN}; "
                 f"'>X' = not reached within the scan, X = last F scanned)\n")
        L.append("| cell | trades/yr | " + " | ".join(f"e={e:.2f}: F / n_req" for e in (0.10, 0.15, 0.20, 0.30, 0.40)) + " |")
        L.append("|---|---|" + "---|" * 5)
        for c in cells:
            rate = cells[c][2] if m == "ICT" else cells[c][3]
            r = FS_[(m, c)]
            row = []
            for e in ("0.1", "0.15", "0.2", "0.3", "0.4"):
                got = None
                for f in sorted(r["by_f"], key=int):
                    cell_e = r["by_f"][f].get(e)
                    if cell_e and cell_e["power"][str(N[m])] >= 0.80:
                        got = (f, cell_e["n_mean"])
                        break
                last = max(r["by_f"], key=int)
                row.append(f">{last}" if got is None else f"{got[0]} / {got[1]:.0f}")
            L.append(f"| {c} | {rate} | " + " | ".join(row) + " |")

    mft = doc["meta"]["fund_stats_min_fold_trades"]
    L.append(f"\n## R6 Per-fold sufficiency side check (fund_stats.MIN_FOLD_TRADES = {mft}, not part of the lower bound): P(every test fold has >= {mft} pooled trades), base model\n")
    L.append("| cell | ICT trades/yr | P(all folds >= min) | Wyckoff trades/yr | P(all folds >= min) |")
    L.append("|---|---|---|---|---|")
    for c in cells:
        L.append(f"| {c} | {cells[c][2]} | {main('ICT', c)['by_e']['0.2']['p_all_folds_ge_min']:.2f} | {cells[c][3]} | {main('WYCKOFF', c)['by_e']['0.2']['p_all_folds_ge_min']:.2f} |")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--quick", action="store_true", help="small replication counts (smoke test only)")
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--report", help="also write the markdown tables (R1..R6) to this path")
    ap.add_argument("--from-json", help="skip the simulation and only (re)build --report from this JSON")
    ap.add_argument("--only", help="comma list of job kinds to run (power,fp,prop,fscan); default all")
    ap.add_argument("--merge-into", help="with --only: replace those sections inside this existing JSON and write --out")
    a = ap.parse_args()
    if a.from_json:
        with open(a.from_json) as fh:
            doc = json.load(fh)
        with open(a.report, "w") as fh:
            fh.write(report(doc))
        return
    procs = min(max(a.procs, 1), 4)
    t0 = time.time()
    sc = selfcheck()
    jobs = build_jobs(a.quick)
    if a.only:
        keep = set(a.only.split(","))
        jobs = [j for j in jobs if j[0] in keep]
    print(f"{len(jobs)} jobs, {procs} processes", flush=True)
    with Pool(procs) as pool:
        results = []
        for i, r in enumerate(pool.imap_unordered(_dispatch, jobs, chunksize=1)):
            results.append(r)
            if (i + 1) % 100 == 0:
                print(f"  {i + 1}/{len(jobs)}  {time.time() - t0:.0f}s", flush=True)
    if a.only and a.merge_into:
        with open(a.merge_into) as fh:
            doc = json.load(fh)
        agg = aggregate(results)
        for kind in set(a.only.split(",")):
            doc[kind] = agg[kind]
        doc["meta"].setdefault("merged_runs", []).append({"only": a.only, "seconds": round(time.time() - t0, 1)})
        with open(a.out, "w") as fh:
            json.dump(doc, fh, indent=1, sort_keys=True)
        print(f"wrote {a.out} (merged {a.only}) in {time.time() - t0:.0f}s")
        if a.report:
            with open(a.report, "w") as fh:
                fh.write(report(doc))
            print(f"wrote {a.report}")
        return
    doc = {"meta": {"script": "scripts/research/power_model.py", "base_seed": BASE_SEED, "quick": a.quick, "base": BASE,
                    "cells": CELLS, "N": N_COMP, "egrid": EGRID, "assumptions": ASSUMPTIONS, "selfcheck": sc,
                    "fund_stats_min_fold_trades": FS.MIN_FOLD_TRADES, "seconds": round(time.time() - t0, 1)},
           **aggregate(results)}
    with open(a.out, "w") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
    print(f"wrote {a.out} in {time.time() - t0:.0f}s")
    if a.report:
        with open(a.report, "w") as fh:
            fh.write(report(doc))
        print(f"wrote {a.report}")


if __name__ == "__main__":
    main()
