#!/usr/bin/env python3
"""END-TO-END power simulation of the SEALED fund-search verdict (b23, 2026-10-02) and the re-application of the pre-stated
cell-inclusion rule at the FINAL pre-registration parameters. SYNTHETIC trades only: no outcome figure of any real trade is read, computed or stored (inputs: admitted-trade COUNTS and recorded spreads).

What is real (imported and CALLED, never reimplemented):
  * scripts/fund_stats.py: robust_lower_bound / check_lower_bound, check_fold_sufficiency, check_stability, check_frequency,
    check_regime_split, check_perturbation (one neighbour at a time), check_stress, stressed_net_r / stress_commission_r,
    prop_shift_r, check_prop_pass, check_prop_pass_shifted, verdict_from, evaluate_cell (full mode), make_folds,
    n_adjusted_confidence (family 6 -> 0.98333).
  * scripts/performance.py metrics() with prop-search's own FUNDS / horizon / account profiles (power_model.prop_pass_value logic),
    scripts/fund-search.py prop_row_from_metric.  The harness engine's simulate()/live-parity sizing is NOT run (needs a real
    engine); like the tests' SynthEngine and the earlier power model (A8) the prop link reads net_R and entry_time only.
  * scripts/research/power_model.py: p_from_edge, seed_for, run_prop (e*), wilson_upper; scripts/research/dev_start_decision.py:
    folds_for, fold_rate, build_rates (the measured admitted-trade COUNTS per symbol and calendar year).
What is a model (every one labelled in ASSUMPTIONS below): the trade stream, the covariate, the neighbours, the stress repricing.

Commands (deterministic; every random stream is seeded by power_model.seed_for(label, ...) + BASE_SEED 20261001):
    python3 scripts/research/e2e_power.py run    --out /tmp/e2e.json [--procs 4] [--quick]
    python3 scripts/research/e2e_power.py report --json /tmp/e2e.json --out /tmp/e2e-tables.md
    python3 scripts/research/e2e_power.py selfcheck
"""
import argparse
import functools
import importlib.util
import json
import math
import os
import sys
import time
from multiprocessing import Pool

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "research"))
import power_model as PM            # noqa: E402  (also memoises fund_stats.ts: pure memo, cleared per replication)
import dev_start_decision as DS     # noqa: E402
FS = PM.FS

COUNTS_JSONL = os.path.join(ROOT, "docs", "audits", "2026-10-02-dev-start-counts.jsonl")
RATES_JSON = os.path.join(ROOT, "docs", "audits", "2026-10-01-cell-selection-rates.json")
COST_PROFILE = "ftmo_demo_2026_09_relspread"

FAMILY = 6
CONF = FS.n_adjusted_confidence(FAMILY)              # 1 - 0.10/6 = 0.98333
METHODS = ("ict", "wyckoff")
MNAME = {"ict": "ICT", "wyckoff": "Wyckoff"}
CELLS = {   # symbols; dev_start used ONLY to derive the fold windows (FS.make_folds); folds asserted below
    "1m-metals": {"symbols": ["XAUUSD", "XAGUSD"], "dev_start": "2012-05-03T00:00:00Z", "folds": 9, "rates": "pooled"},
    "1m-indices": {"symbols": ["US500", "US30", "USTEC", "DE40", "FRA40"], "dev_start": "2020-03-01T00:00:00Z", "folds": 2,
                   "rates": "counts"},
    "5m-metals": {"symbols": ["XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD"], "dev_start": "2015-01-07T00:00:00Z", "folds": 7,
                  "rates": "counts"},
}
CANDS = [(c, m) for c in CELLS for m in METHODS]
BASE = {"cost": 0.07, "sigma": 0.75, "tau": 0.03, "rho": 0.30, "delta_max": 0.05, "kappa": 0.7}
#: n_nb = number of distinct (item, component, direction) neighbour sets of fund_stats.PERTURBATION_AXES when the chosen value is
#: interior on every ordinal component: ICT stop_buffer 2 + entry_model 2 + target 2 + time_stop 2 + lookback 2 + expiry 1 = 11;
#: Wyckoff structure_window 1 + test_window 2 + phase_b_swings 1 + linger_closes 1 = 5.
N_NB = {"ict": 11, "wyckoff": 5}
HOUR_W = np.array([0.8] * 6 + [1.2] * 2 + [1.8] * 4 + [2.2] * 5 + [1.4] * 4 + [0.5] * 3, dtype=float)
HOUR_W = HOUR_W / HOUR_W.sum()
ADX_BLOCK_DAYS = 20
EGRID = [round(0.05 * i, 2) for i in range(0, 13)]           # 0 .. 0.60 step 0.05 (the task's grid)
EGRID_EXT = [0.70, 0.80, 1.00]                               # only when 0.60 is not enough
EGRID_FINE = [0.05, 0.075, 0.10, 0.125, 0.15, 0.175, 0.20, 0.225, 0.25, 0.275, 0.30, 0.325, 0.35, 0.375, 0.40, 0.50, 0.60,
              0.80, 1.00]                                    # cell_selection.EGRID: the earlier rule's own grid
#: variant -> (rate mode, discount rho, regime rho). sum03 = the MEASURED pooled rate (sum over symbols), regime rho 0.3: the e2e PRIMARY
#: (every pooled trade the harness would see; the cross-symbol correlation enters only through the regime). disc03 = the earlier rule's
#: 'base' (rate discounted by 1/(1+(k-1)*0.3) AND regime rho 0.3: counts the correlation twice, conservative). sum0 / disc06 = the earlier
#: 'rho0' / 'rho06' sensitivities. sum06 = measured rate with regime rho 0.6.
VARIANTS = {"sum03": ("sum", 0.0, 0.3), "disc03": ("disc", 0.3, 0.3), "sum0": ("sum", 0.0, 0.0), "disc06": ("disc", 0.6, 0.6),
            "sum06": ("sum", 0.0, 0.6)}
PRIMARY = "sum03"
RULE_VARIANTS = ("disc03", "sum03", "sum0", "disc06")
K_LIST = (1.5, 2.0, 2.5, 3.0)
K_RULE = 2.0

ASSUMPTIONS = [
    "E1 [measured counts, final starts] per-symbol yearly admitted-trade rates = the calendar-year counts of docs/audits/2026-10-02-dev-start-counts.jsonl "
    "(5m-metals, 1m-indices), pro rata per fold window (dev_start_decision.fold_rate); a symbol with no bars in a fold has rate 0 (availability-aware: XPT/XPD "
    "absent-ish before 2017, 1m-indices late symbols). 1m-metals has no per-year counts: b10's pooled rate (ICT 675.7, Wyckoff 448.7 /yr) split equally over the 2 symbols, constant over the 9 folds.",
    "E2 PRIMARY variant sum03 = the measured pooled rate (the sum over symbols: every admitted trade the harness would pool) with month-level regime correlation rho 0.3. The earlier rule's "
    "convention disc03 (rate x 1/(1+(k-1)*0.3) AND rho 0.3: the correlation is counted twice, conservative) is run in parallel (curves, e_min, e*), and is the variant the inclusion rule is "
    "re-applied under (it was the earlier PRIMARY); sum0 / disc06 are the earlier rho sensitivities, sum06 = measured rate with regime rho 0.6.",
    "E3 [model, as power_model A1-A5] cost c = 0.07R (sensitivity 0.10); binary +2.5R / -1R, net_R = outcome - c_i; p = (e + 1 + c)/3.5 so the mean net R is the true net edge e; "
    "month-level lognormal arrival multiplier sigma 0.75 (mean 1) and month-level win-probability shift tau 0.03 (sd, in p), cross-symbol correlation rho on both; weekday-only Poisson arrivals.",
    "E4 [declared shape, NOT measured] entry hour-of-day (UTC): weights 0.8 (00-05), 1.2 (06-07), 1.8 (08-11), 2.2 (12-16), 1.4 (17-20), 0.5 (21-23), minute/second uniform; same for every symbol. "
    "The hour only matters through the cost multipliers of E7 and the entry date/month blocks.",
    "E5 [declared, INDEPENDENT of outcome] D1 ADX covariate adx14_d1 = 10 + 40 U with U redrawn per (symbol, 20-day block): persistent within a block, independent of win/loss, so the regime split "
    "(<= pooled median vs > median, BOTH halves must have mean net R > 0) is a pure power cost (a real regime effect could only make it worse or better).",
    "E6 [declared, the MOST ARBITRARY part] perturbation neighbours: n_nb distinct (item, component, direction) sets (ICT 11, Wyckoff 5: chosen value interior on every ordinal component; fewer if a chosen value "
    "sits on an edge). Each neighbour pools the same trade entries as the chosen value (same timestamps, same costs) with edge e - delta_j, delta_j ~ U(0, delta_max) drawn per neighbour (base delta_max 0.05, "
    "sensitivity 0 / 0.10); each trade's outcome is SHARED with the chosen stream with probability kappa (base 0.7; sensitivity 1.0 / 0.0), else an independent redraw at the neighbour's p. "
    "A neighbour passes iff pooled mean > 0 AND its primary bound > 0 at the floor (fund_stats.check_perturbation).",
    "E7 [real spread statistics, declared anchor] stress repricing: per symbol the REAL by-UTC-hour median / p90 recorded spreads of data/history/costs/ftmo (real_costs.spec). Anchored so that the "
    "EXPECTED median spread cost is c: c_i = c * med(sym,h) / E_w[med(sym)], stress cost_i = c * p90(sym,h) / E_w[med(sym)] (hour h of the entry, both legs at the entry hour, swap 0 because "
    "flat_before_rollover is on), the representative stop distance dist_sym = rel_median_spread(sym) / c with rel_median_spread = overall median points * point / real_costs.price_ref(sym). Commission margin "
    "via fund_stats.stress_commission_r(entry, stop), stressed net R via fund_stats.stressed_net_r. Gate = mean > 0 (fund_stats.check_stress).",
    "E8 [as power_model A8, NOT the engine] prop_pass: performance.metrics(trades, account, horizon 120) per fund, net_R + entry_time only (no simulate()/live-parity sizing: the 2-consecutive-loss "
    "halving and any trade the engine would refuse are NOT modelled). Unshifted AND shifted by (pooled mean - primary bound) as in evaluate_with_engine; both funds >= 0.70 (+ the low-confidence rule of fund_stats._prop_row).",
    "E9 [as the harness] verdict = fund_stats.verdict_from: insufficient if any fold has < 30 trades; otherwise PASS iff all nine checks are ok. Replications: 200 per (candidate, e) on the primary grid "
    "(stop early at >= 98.5 % pass after >= 50), 60 on the disc03 grid, 40 on sensitivity points, 80 on attribution, 3000 at e = 0 (type I), 300 (800 for 5m-metals) per floor-only point of the inclusion rule. "
    "Monte-Carlo SE of a power estimate near 0.8: 0.028 (200), 0.052 (60), 0.063 (40). 'e80' = smallest grid e (step 0.05) with power >= 0.80, read from the estimated curve (no smoothing).",
    "E10 the nested walk-forward is NOT simulated: the pooled TEST trades of the candidate are drawn directly at the true edge e (a procedure that picks a good value in training and then tests it can only do "
    "WORSE than a fixed value at edge e, so these power figures are an upper bound on the sealed procedure; a selection-induced shrinkage is outside this model).",
]


# ====================================================================================================== static inputs
_RC = None
_FSMOD = None
_PS = None


def real_costs():
    global _RC
    if _RC is None:
        import real_costs as rc
        _RC = rc
    return _RC


def fund_search_mod():
    global _FSMOD
    if _FSMOD is None:
        spec = importlib.util.spec_from_file_location("fund_search_e2e", os.path.join(ROOT, "scripts", "fund-search.py"))
        _FSMOD = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_FSMOD)
    return _FSMOD


def prop_search():
    global _PS
    if _PS is None:
        _PS = PM._prop_search()
    return _PS


@functools.lru_cache(maxsize=None)
def symbol_costs(sym):
    """Real spread statistics of one symbol (no outcome): by-hour median / p90 points, point, price_ref."""
    rc = real_costs()
    d = rc.spec(COST_PROFILE, sym)
    rec = d["recorded_spread_m15"]
    by = {r["h"]: r for r in rec["by_utc_hour"]}
    med = np.array([rc.spread_price(COST_PROFILE, sym, h, "median")[0] for h in range(24)])
    p90 = np.array([rc.spread_price(COST_PROFILE, sym, h, "p90")[0] for h in range(24)])
    overall_med = rec["median_points"] * d["point"]
    pr = rc.price_ref(COST_PROFILE, sym)
    return {"point": d["point"], "median_price_by_hour": med, "p90_price_by_hour": p90, "overall_median_price": overall_med,
            "price_ref": pr, "rel_median": overall_med / pr, "median_points": rec["median_points"], "p90_points": rec["p90_points"],
            "hours_n0": [h for h in range(24) if by.get(h, {}).get("n", 0) == 0]}


def stress_table(cell, c):
    """Per symbol: c_i multipliers (24,), stress cost multipliers (24,) [both in R once multiplied by c], commission_R, dist."""
    out = {}
    for s in CELLS[cell]["symbols"]:
        sc = symbol_costs(s)
        ew = float((HOUR_W * sc["median_price_by_hour"]).sum())
        dist = sc["rel_median"] / c
        entry = sc["price_ref"]
        stop = entry * (1.0 - dist)
        out[s] = {"c_mult": sc["median_price_by_hour"] / ew, "p90_mult": sc["p90_price_by_hour"] / ew, "dist": dist, "entry": entry,
                  "stop": stop, "commission_R": FS.stress_commission_r(entry, stop)}
    return out


@functools.lru_cache(maxsize=None)
def counts_rates():
    return DS.build_rates(COUNTS_JSONL)


@functools.lru_cache(maxsize=None)
def pooled_1m():
    return json.load(open(RATES_JSON))["pooled_1m_b10"]


def rate_matrix(cand, mode, rho_disc):
    """(k, F) yearly admitted-trade rate per symbol and fold, discounted per E2. Also returns the fold windows."""
    cell, method = cand
    c = CELLS[cell]
    syms = c["symbols"]
    k = len(syms)
    folds = FS.make_folds(c["dev_start"])
    assert len(folds) == c["folds"], (cell, len(folds))
    F = len(folds)
    if c["rates"] == "pooled":
        tot = pooled_1m()[f"{method}|{cell}"]
        m = np.full((k, F), tot / k)
    else:
        rates = counts_rates()
        pairs = DS.folds_for(c["dev_start"])
        assert len(pairs) == F
        m = np.zeros((k, F))
        for j, s in enumerate(syms):
            for i, (a, b) in enumerate(pairs):
                m[j, i] = DS.fold_rate(rates, method, s, a, b)
    if mode == "disc":
        m = m / (1.0 + (k - 1) * rho_disc)
    return m, folds


# ============================================================================================================ the world
class World:
    """Everything of one (candidate, configuration) that does not change between replications."""

    def __init__(self, cand, cfg):
        self.cand, self.cfg = cand, dict(cfg)
        cell, method = cand
        self.cell, self.method = cell, method
        self.syms = CELLS[cell]["symbols"]
        self.k = len(self.syms)
        mode, rho_disc, rho = VARIANTS[cfg.get("variant", PRIMARY)]
        self.rho = rho
        self.rate_kf, self.folds = rate_matrix(cand, mode, rho_disc)
        self.F = len(self.folds)
        self.n_days = self.F * FS.TEST_FOLD_DAYS
        self.day0 = np.datetime64(self.folds[0]["test_start"][:10])
        days = self.day0 + np.arange(self.n_days).astype("timedelta64[D]")
        dow = (days.astype(np.int64) + 3) % 7
        self.wd = (dow < 5).astype(float)
        months = days.astype("datetime64[M]").astype(np.int64)
        _, self.m_idx = np.unique(months, return_inverse=True)
        self.n_m = int(self.m_idx.max()) + 1
        self.fold_of_day = np.arange(self.n_days) // FS.TEST_FOLD_DAYS
        self.lam_base = self.rate_kf[:, self.fold_of_day] / (FS.TEST_FOLD_DAYS * 5.0 / 7.0) * self.wd[None, :]
        self.n_blocks = self.n_days // ADX_BLOCK_DAYS + 1
        self.st = stress_table(cell, cfg["cost"])
        self.cmult = np.stack([self.st[s]["c_mult"] for s in self.syms])
        self.p90mult = np.stack([self.st[s]["p90_mult"] for s in self.syms])
        self.comm = np.array([self.st[s]["commission_R"] for s in self.syms])
        self.n_nb = N_NB[method]

    def _mixed(self, rng):
        zc = rng.standard_normal(self.n_m)
        zs = rng.standard_normal((self.k, self.n_m))
        return math.sqrt(self.rho) * zc[None, :] + math.sqrt(1.0 - self.rho) * zs

    def draw(self, rng, e):
        """One synthetic pooled TEST stream at true net edge e. Consumes the rng identically for every e / mode."""
        cfg = self.cfg
        c, sigma, tau = cfg["cost"], cfg["sigma"], cfg["tau"]
        p = PM.p_from_edge(e, c)
        z_rate, z_out = self._mixed(rng), self._mixed(rng)
        mult = np.exp(sigma * z_rate - 0.5 * sigma * sigma)
        lam = self.lam_base * mult[:, self.m_idx]
        counts = rng.poisson(lam)
        sym_i, day_i = np.nonzero(counts)
        reps = counts[sym_i, day_i]
        sym, day = np.repeat(sym_i, reps), np.repeat(day_i, reps)
        n = len(sym)
        hour = rng.choice(24, size=n, p=HOUR_W)
        sec = hour * 3600 + rng.integers(0, 3600, size=n)
        u = rng.random(n)
        u_adx = 10.0 + 40.0 * rng.random((self.k, self.n_blocks))
        nb_seed = int(rng.integers(0, 2 ** 32))
        p_tr = np.clip(p + tau * z_out[sym, self.m_idx[day]], 0.0, 1.0)
        win = u < p_tr
        order = np.lexsort((sec, day))
        sym, day, sec, hour, u, win, p_tr = sym[order], day[order], sec[order], hour[order], u[order], win[order], p_tr[order]
        gross = np.where(win, PM.WIN_R, PM.LOSS_R)
        c_i = c * self.cmult[sym, hour]
        net = gross - c_i
        stress_cost = c * self.p90mult[sym, hour]
        stressed = gross - stress_cost - self.comm[sym]
        adx = u_adx[sym, day // ADX_BLOCK_DAYS]
        t64 = (self.day0 + day.astype("timedelta64[D]")).astype("datetime64[s]") + sec.astype("timedelta64[s]")
        et = [s + "Z" for s in np.datetime_as_string(t64, unit="s")]
        names = [self.syms[i] for i in sym]
        trades = [{"entry_time": a, "net_R": r, "symbol": s, "adx14_d1": x}
                  for a, r, s, x in zip(et, net.tolist(), names, adx.tolist())]
        fold = day // FS.TEST_FOLD_DAYS
        bounds = np.searchsorted(fold, np.arange(self.F + 1))
        fold_results = []
        for i in range(self.F):
            fold_results.append({"fold": {"index": i, "test_start": self.folds[i]["test_start"], "test_end": self.folds[i]["test_end"]},
                                 "test_trades": trades[bounds[i]:bounds[i + 1]], "chosen": {"item": "v"}, "changed": False})
        return {"fold_results": fold_results, "trades": trades, "stressed": stressed, "et": et, "u": u, "p_tr": p_tr, "c_i": c_i,
                "nb_seed": nb_seed, "per_fold": np.diff(bounds)}

    def stress_trades(self, d):
        return [dict(t, net_R=float(r)) for t, r in zip(d["trades"], d["stressed"])]

    def neighbours(self, d):
        """The E6 neighbour sets (list of check_perturbation inputs), deterministic given the draw."""
        cfg = self.cfg
        rng = np.random.default_rng(d["nb_seed"])
        n = len(d["u"])
        out = []
        for j in range(self.n_nb):
            delta = float(rng.uniform(0.0, cfg["delta_max"])) if cfg["delta_max"] > 0 else 0.0
            shared = rng.random(n) < cfg["kappa"]
            u2 = rng.random(n)
            p_nb = np.clip(d["p_tr"] - delta / (PM.WIN_R - PM.LOSS_R), 0.0, 1.0)
            win = np.where(shared, d["u"] < p_nb, u2 < p_nb)
            net = np.where(win, PM.WIN_R, PM.LOSS_R) - d["c_i"]
            out.append({"item": f"n{j}", "component": "c", "direction": 1, "folds": self.F,
                        "trades": [{"entry_time": a, "net_R": r} for a, r in zip(d["et"], net.tolist())]})
        return out


# ============================================================================================================ verdicts
def prop_rows(trades, shift=0.0):
    ps, fs = prop_search(), fund_search_mod()
    taken = trades if not shift else [dict(t, net_R=t["net_R"] - shift) for t in trades]
    out = {}
    for f in ps.FUNDS:
        m = ps._perf.metrics(taken, account=ps._AP.get(f), horizon=ps.CHALLENGE_HORIZON_DAYS)
        out[f] = fs.prop_row_from_metric(m.get("prop_pass_probability"))
    return out


def eval_lazy(world, d):
    """The verdict with every check computed by the harness's own function, cheap first, stopping at the first failing check
    (the verdict of verdict_from is the same: one failing check fails the conjunction). Returns dict(verdict, floor_ok, fail=first failing)."""
    fr, pooled = d["fold_results"], d["trades"]
    skipped = {"ok": False, "skipped": True}
    checks = {k: skipped for k in FS.REQUIRED_CHECKS}
    res = {"floor_ok": False, "fail": None}

    def done(name):
        res["fail"] = name
        res["verdict"] = FS.verdict_from(checks)
        return res

    checks["folds_sufficient"] = FS.check_fold_sufficiency(fr)
    lb = FS.check_lower_bound(pooled, CONF)
    checks["lower_bound_positive"] = lb
    res["floor_ok"] = bool(lb["ok"])
    res["all_folds_ok"] = bool(checks["folds_sufficient"]["ok"])
    if not checks["folds_sufficient"]["ok"]:
        return done("folds_sufficient")
    if not lb["ok"]:
        return done("lower_bound_positive")
    for name, fn in (("stability", lambda: FS.check_stability(pooled, world.syms)),
                     ("frequency", lambda: FS.check_frequency(fr)),
                     ("regime_split", lambda: FS.check_regime_split(pooled)),
                     ("stress", lambda: FS.check_stress(world.stress_trades(d), CONF))):
        checks[name] = fn()
        if not checks[name]["ok"]:
            return done(name)
    rows, ok = [], True
    for nb in world.neighbours(d):
        r = FS.check_perturbation([nb], CONF)
        rows.extend(r["rows"])
        if not r["ok"]:
            ok = False
            break
    checks["perturbation"] = {"ok": ok, "rows": rows}
    if not ok:
        return done("perturbation")
    shift = FS.prop_shift_r(lb["bound"])
    pr = prop_rows(pooled)
    checks["prop_pass_probability"] = FS.check_prop_pass(pr)
    if not checks["prop_pass_probability"]["ok"]:
        return done("prop_pass_probability")
    checks["prop_pass_shifted"] = FS.check_prop_pass_shifted(prop_rows(pooled, shift), shift)
    if not checks["prop_pass_shifted"]["ok"]:
        return done("prop_pass_shifted")
    res["verdict"] = FS.verdict_from(checks)
    return res


def eval_full(world, d):
    """FS.evaluate_cell with every input (all checks computed, never short-circuited): the attribution run."""
    pooled = d["trades"]
    lb = FS.robust_lower_bound(pooled, CONF)
    shift = FS.prop_shift_r(lb)
    perturbs = world.neighbours(d)
    prop = prop_rows(pooled)
    prop_sh = prop_rows(pooled, shift) if shift is not None else None
    r = FS.evaluate_cell(d["fold_results"], perturbs, world.syms, FAMILY, prop, stress=world.stress_trades(d),
                         prop_shifted=prop_sh, shift_r=shift)
    return {"verdict": r["verdict"], "failed": list(r["failed_checks"]), "floor_ok": r["checks"]["lower_bound_positive"]["ok"],
            "all_folds_ok": r["checks"]["folds_sufficient"]["ok"]}


# ================================================================================================================ jobs
def _seed(*labels):
    return PM.seed_for("e2e", *labels)


def cfg_of(over=None):
    cfg = dict(BASE)
    cfg["variant"] = PRIMARY
    cfg.update(over or {})
    return cfg


def cfg_key(cfg):
    return "|".join(f"{k}={cfg[k]}" for k in sorted(cfg))


def run_curve_point(job):
    """P(PASS) and floor-only power at one (candidate, cfg, e): lazy evaluation, early stop at >= 98.5 % pass after >= 50 reps."""
    cand, cfg, e, reps = tuple(job["cand"]), job["cfg"], job["e"], job["reps"]
    w = World(cand, cfg)
    rng = np.random.default_rng(_seed("curve", cand, cfg_key(cfg), e))
    n = npass = nfloor = nall = ninsuff = 0
    fails = {}
    min_reps = job.get("min_reps", 50)
    while n < reps:
        for _ in range(min(25, reps - n)):
            d = w.draw(rng, e)
            r = eval_lazy(w, d)
            FS.ts.cache_clear()
            n += 1
            npass += int(r["verdict"] == FS.PASS)
            nfloor += int(r["floor_ok"])
            nall += int(r["all_folds_ok"])
            ninsuff += int(r["verdict"] == FS.INSUFFICIENT)
            fails[r["fail"] or "none"] = fails.get(r["fail"] or "none", 0) + 1
        if job.get("early", True) and n >= min_reps and npass >= 0.985 * n:
            break
    return {"kind": "curve", "cand": list(cand), "cfg": cfg, "e": e, "n": n, "pass": npass, "floor": nfloor, "all_folds": nall,
            "insufficient": ninsuff, "first_fail": fails}


def run_attrib(job):
    """FULL evaluation (FS.evaluate_cell, nothing short-circuited) at one e: which check fails how often."""
    cand, cfg, e, reps = tuple(job["cand"]), job["cfg"], job["e"], job["reps"]
    w = World(cand, cfg)
    rng = np.random.default_rng(_seed("attrib", cand, cfg_key(cfg), e))
    cnt, sole, combos, n, npass = {}, {}, {}, 0, 0
    for _ in range(reps):
        d = w.draw(rng, e)
        r = eval_full(w, d)
        FS.ts.cache_clear()
        n += 1
        npass += int(r["verdict"] == FS.PASS)
        f = r["failed"]
        for k in f:
            cnt[k] = cnt.get(k, 0) + 1
        if len(f) == 1:
            sole[f[0]] = sole.get(f[0], 0) + 1
        key = "+".join(f) if f else "none"
        combos[key] = combos.get(key, 0) + 1
    return {"kind": "attrib", "cand": list(cand), "cfg": cfg, "e": e, "n": n, "pass": npass, "fail_counts": cnt, "sole": sole,
            "combos": combos}


def run_fp(job):
    """Type I at true edge 0: floor-only and conjunction (the same lazy rule), `reps` replications."""
    cand, cfg, reps = tuple(job["cand"]), job["cfg"], job["reps"]
    w = World(cand, cfg)
    rng = np.random.default_rng(_seed("fp", cand, cfg_key(cfg)))
    n = npass = nfloor = 0
    for _ in range(reps):
        d = w.draw(rng, 0.0)
        r = eval_lazy(w, d)
        FS.ts.cache_clear()
        n += 1
        npass += int(r["verdict"] == FS.PASS)
        nfloor += int(r["floor_ok"])
    return {"kind": "fp", "cand": list(cand), "cfg": cfg, "n": n, "pass": npass, "floor": nfloor,
            "wilson_pass": PM.wilson_upper(npass, n), "wilson_floor": PM.wilson_upper(nfloor, n), "family_level": 0.10 / FAMILY}


def run_floor_point(job):
    """Floor-only power (the earlier rule's e_min notion: primary bound > 0 at the floor confidence) at one e."""
    cand, cfg, e, reps = tuple(job["cand"]), job["cfg"], job["e"], job["reps"]
    w = World(cand, cfg)
    rng = np.random.default_rng(_seed("floor", cand, cfg_key(cfg), e))
    n = nfl = 0
    for _ in range(reps):
        d = w.draw(rng, e)
        nfl += int(FS.check_lower_bound(d["trades"], CONF)["ok"])
        FS.ts.cache_clear()
        n += 1
    return {"kind": "floor", "cand": list(cand), "cfg": cfg, "e": e, "n": n, "floor": nfl}


def run_prop_job(job):
    """e* of the candidate at the final trade rate of the variant, with power_model.run_prop (9-step bisection, population stream)."""
    cand, vname = tuple(job["cand"]), job["variant"]
    mode, rho_disc, rho = VARIANTS[vname]
    m, _ = rate_matrix(cand, mode, rho_disc)
    k = m.shape[0]
    total = float(m.sum(axis=0).mean())                   # pooled trades / year, averaged over the final folds
    years = max(20, math.ceil(PM.PROP_TRADES / total))
    r = PM.run_prop(dict(label=f"e2e|{vname}|{cand[1]}|{cand[0]}", method=MNAME[cand[1]], cell=cand[0], years=years, k=k,
                         rate_sym=total / k, cost=BASE["cost"], sigma=BASE["sigma"], tau=BASE["tau"], rho=rho))
    es = [r["by_fund"][f]["e_for_pass_070"] for f in r["by_fund"]]
    return {"kind": "prop", "cand": list(cand), "variant": vname, "rate_total": total, "years": years,
            "by_fund": {f: r["by_fund"][f] for f in r["by_fund"]}, "e_star": None if any(x is None for x in es) else max(es),
            "trades_per_active_day": r["trades_per_active_day"]}


def _dispatch(item):
    return {"curve": run_curve_point, "attrib": run_attrib, "fp": run_fp, "floor": run_floor_point, "prop": run_prop_job}[item["kind"]](item)


# ============================================================================================================ scheduler
def pmap(jobs, procs, tag):
    t0 = time.time()
    out = []
    with Pool(min(procs, 4)) as pool:
        for i, r in enumerate(pool.imap_unordered(_dispatch, jobs, chunksize=1)):
            out.append(r)
            if (i + 1) % 20 == 0 or i + 1 == len(jobs):
                print(f"  [{tag}] {i + 1}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
    return out


def weight(j):
    base = {"ict": 2.0, "wyckoff": 1.0}[j["cand"][1]]
    return base * (3.0 if j["cand"][0] != "5m-metals" else 1.0) * j.get("reps", 100) * (1.0 + j.get("e", 0.3))


def e80_of(points, grid):
    """Smallest grid e with P >= 0.80 among evaluated points {e: (pass, n)}; None if never."""
    for e in grid:
        if e in points and points[e][1] and points[e][0] / points[e][1] >= 0.80:
            return e
    return None


def points_of(cur, cfgd):
    pts = {}
    for r in cur:
        if r["cfg"] == cfgd:
            pts.setdefault(tuple(r["cand"]), {})[round(r["e"], 4)] = (r["pass"], r["n"])
    return pts


COARSE = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60, 0.80, 1.00]     # subset of EGRID_FINE; the 0.025 midpoints refine


def run_all(a):
    t0 = time.time()
    quick = a.quick
    R_MAIN, R_DISC, R_SENS, R_ATT, R_FP = (30, 20, 20, 20, 300) if quick else (200, 60, 40, 80, 3000)
    R_FLOOR = {"1m-metals": 40, "1m-indices": 40, "5m-metals": 40} if quick else {"1m-metals": 300, "1m-indices": 300, "5m-metals": 800}
    res = {"meta": {"script": "scripts/research/e2e_power.py", "base_seed": PM.BASE_SEED, "quick": quick, "conf": CONF, "family": FAMILY,
                    "base": BASE, "primary_variant": PRIMARY, "variants": VARIANTS, "n_nb": N_NB,
                    "cells": {c: {"symbols": v["symbols"], "dev_start": v["dev_start"], "folds": v["folds"]} for c, v in CELLS.items()},
                    "assumptions": ASSUMPTIONS, "egrid": EGRID, "egrid_fine": EGRID_FINE}}
    # ---- stage 1: e* (prop link) per candidate and rule variant, and the type-I runs (independent of everything else)
    jobs = [dict(kind="prop", cand=list(c), variant=v) for c in CANDS for v in RULE_VARIANTS]
    jobs += [dict(kind="fp", cand=list(c), cfg=cfg_of(), reps=R_FP) for c in CANDS]
    jobs.sort(key=lambda j: -(weight(j) if j["kind"] != "prop" else 400))
    s1 = pmap(jobs, a.procs, "stage1 e*/type-I")
    res["prop"] = [r for r in s1 if r["kind"] == "prop"]
    res["fp"] = [r for r in s1 if r["kind"] == "fp"]
    estar = {(tuple(r["cand"]), r["variant"]): r["e_star"] for r in res["prop"]}
    # ---- stage 2: the main curves (conjunction + floor-only on the 0.05 grid): primary at R_MAIN, disc03 at R_DISC; plus e = e*
    cfg_p, cfg_d = cfg_of(), cfg_of({"variant": "disc03"})
    jobs = [dict(kind="curve", cand=list(c), cfg=cfg_p, e=e, reps=R_MAIN) for c in CANDS for e in EGRID]
    jobs += [dict(kind="curve", cand=list(c), cfg=cfg_d, e=e, reps=R_DISC) for c in CANDS for e in EGRID]
    jobs += [dict(kind="curve", cand=list(c), cfg=cfg_p, e=round(estar[(c, PRIMARY)], 4), reps=R_MAIN, early=False)
             for c in CANDS if estar[(c, PRIMARY)] is not None and round(estar[(c, PRIMARY)], 4) not in EGRID]
    jobs.sort(key=lambda j: -weight(j))
    cur = [r for r in pmap(jobs, a.procs, "stage2 main curves") if r["kind"] == "curve"]
    ext = []
    for cfgx, rep in ((cfg_p, R_MAIN), (cfg_d, R_DISC)):
        pts = points_of(cur, cfgx)
        ext += [dict(kind="curve", cand=list(c), cfg=cfgx, e=e, reps=rep) for c in CANDS if e80_of(pts[c], EGRID) is None for e in EGRID_EXT]
    if ext:
        cur += [r for r in pmap(ext, a.procs, "stage2b extension") if r["kind"] == "curve"]
    res["curve"] = cur
    e80 = {}
    for vname, cfgx in (("primary", cfg_p), ("disc03", cfg_d)):
        pts = points_of(cur, cfgx)
        e80[vname] = {f"{c[0]}|{c[1]}": e80_of(pts[c], EGRID + EGRID_EXT) for c in CANDS}
    res["e80"] = e80
    # ---- stage 3: floor-only (the earlier rule's e_min notion), coarse grid then the 0.025 midpoint below the first crossing
    jobs = [dict(kind="floor", cand=list(c), cfg=cfg_of({"variant": v}), e=e, reps=R_FLOOR[c[0]]) for c in CANDS for v in RULE_VARIANTS for e in COARSE]
    jobs.sort(key=lambda j: -weight(j))
    fl = [r for r in pmap(jobs, a.procs, "stage3 floor-only coarse") if r["kind"] == "floor"]
    ref = []
    for c in CANDS:
        for v in RULE_VARIANTS:
            pts = sorted((r["e"], r["floor"] / r["n"]) for r in fl if tuple(r["cand"]) == c and r["cfg"]["variant"] == v)
            for (e0, p0), (e1, p1) in zip(pts, pts[1:]):
                if p0 < 0.80 <= p1 and e1 <= 0.40:
                    ref.append(dict(kind="floor", cand=list(c), cfg=cfg_of({"variant": v}), e=round((e0 + e1) / 2, 4), reps=R_FLOOR[c[0]]))
                    break
    fl += [r for r in pmap(ref, a.procs, "stage3b floor-only refine") if r["kind"] == "floor"] if ref else []
    res["floor"] = fl
    # ---- stage 4: attribution (full evaluate_cell) at e80/2 and e80
    jobs = []
    for c in CANDS:
        x = e80["primary"][f"{c[0]}|{c[1]}"]
        for e in ([0.30, 0.60] if x is None else sorted({nearest_grid(x / 2.0), x})):      # e80 not reached: 0.30 and 0.60 instead
            jobs.append(dict(kind="attrib", cand=list(c), cfg=cfg_p, e=e, reps=R_ATT))
    res["attrib"] = [r for r in pmap(jobs, a.procs, "stage4 attribution") if r["kind"] == "attrib"]
    # ---- stage 5: sensitivity of the full-conjunction e80 (primary variant), points around the base e80
    sens_cfgs = {"delta0": {"delta_max": 0.0}, "delta10": {"delta_max": 0.10}, "kappa0": {"kappa": 0.0}, "sigma05": {"sigma": 0.5},
                 "rho0": {"variant": "sum0"}, "rho06": {"variant": "sum06"}, "cost10": {"cost": 0.10}}
    jobs = []
    for c in CANDS:
        x = e80["primary"][f"{c[0]}|{c[1]}"]
        for name, over in sens_cfgs.items():
            for e in sens_points(x):
                jobs.append(dict(kind="curve", cand=list(c), cfg=cfg_of(over), e=e, reps=R_SENS, min_reps=30))
    jobs.sort(key=lambda j: -weight(j))
    sens = pmap(jobs, a.procs, "stage5 sensitivity")
    nm = {cfg_key(cfg_of(o)): n for n, o in sens_cfgs.items()}
    for r in sens:
        r["sens"] = nm[cfg_key(r["cfg"])]
    res["sens"] = sens
    res["meta"]["seconds"] = round(time.time() - t0, 1)
    json.dump(res, open(a.out, "w"), indent=1, sort_keys=True)
    print(f"wrote {a.out} in {time.time() - t0:.0f}s")


def nearest_grid(x, step=0.05):
    return round(max(step, round(x / step) * step), 2)


def sens_points(e80):
    """Sensitivity evaluation points: the base e80 -0.05, +0, +0.05 on the 0.05 grid (the sensitivity e80 is read among them); a
    candidate whose base e80 was not reached (None) is scanned at 0.40 / 0.60 / 0.80."""
    if e80 is None:
        return [0.40, 0.60, 0.80]
    return [x for x in (round(e80 + d, 2) for d in (-0.05, 0.0, 0.05)) if x >= 0.05]


# ================================================================================================================ report
def pct(x, nd=2):
    return "n/a" if x is None else f"{x:.{nd}f}"


def curves_from(doc, cfgd):
    P = {}
    for r in doc["curve"]:
        if r["cfg"] == cfgd:
            P.setdefault(tuple(r["cand"]), {})[round(r["e"], 4)] = r
    return P


def floor_emin(doc, c, variant, kind="grid"):
    pts = sorted(((r["e"], r["floor"] / r["n"]) for r in doc["floor"] if tuple(r["cand"]) == c and r["cfg"]["variant"] == variant))
    if kind == "grid":
        for e, p in pts:
            if p >= 0.80:
                return e
        return None
    for (e0, p0), (e1, p1) in zip(pts, pts[1:]):
        if p0 < 0.80 <= p1:
            return e0 + (0.80 - p0) * (e1 - e0) / (p1 - p0)
    return pts[0][0] if pts and pts[0][1] >= 0.80 else None


def curve_table(L, P, cands, grid, e80d, title):
    L.append(title)
    L.append("| candidate | n/point | " + " | ".join(f"{e:.2f}" for e in grid) + " | e80 |")
    L.append("|---|---|" + "---|" * (len(grid) + 1))
    for c, m in cands:
        row = [("-" if P[(c, m)].get(e) is None else f"{P[(c, m)][e]['pass'] / P[(c, m)][e]['n']:.2f}") for e in grid]
        ns = sorted({r["n"] for r in P[(c, m)].values()})
        L.append(f"| {c} {MNAME[m]} | {ns[-1]} | " + " | ".join(row) + f" | **{pct(e80d[f'{c}|{m}'])}** |")


def report(doc):
    L = []
    cells = list(CELLS)
    cfg_p, cfg_d = cfg_of(), cfg_of({"variant": "disc03"})
    P, PD = curves_from(doc, cfg_p), curves_from(doc, cfg_d)
    estar = {(r["cand"][0], r["cand"][1], r["variant"]): r for r in doc["prop"]}
    e80 = doc["e80"]
    fp = {tuple(r["cand"]): r for r in doc["fp"]}
    grid = sorted({e for c in P for e in P[c] if e in EGRID or e in EGRID_EXT})
    L.append("### T0. Summary per candidate (PRIMARY = measured pooled rate; disc03 = the earlier rule's conservative convention)\n")
    L.append("| candidate | folds | e* (prop, binding) | e_min floor-bound-only | e80 whole conjunction | e80 / e* | e80 under disc03 | type I at e = 0 (conjunction, Wilson upper) | binding check at e80/2 | binding check at e80 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for c, m in CANDS:
        es = estar[(c, m, "sum03")]["e_star"]
        e8 = e80["primary"][f"{c}|{m}"]
        em = floor_emin(doc, (c, m), "sum03")
        ats = sorted((x for x in doc["attrib"] if tuple(x["cand"]) == (c, m)), key=lambda x: x["e"])

        def lead(r):
            if not r["fail_counts"]:
                return "none fails"
            k, v = max(r["fail_counts"].items(), key=lambda kv: kv[1])
            return f"{k} ({v / r['n']:.0%})"
        b_half = lead(ats[0]) if ats else "n/a"
        b_e80 = lead(ats[-1]) if len(ats) > 1 else "n/a"
        r0 = fp[(c, m)]
        L.append(f"| {c} {MNAME[m]} | {CELLS[c]['folds']} | {pct(es, 3)} | {pct(em, 3)} | **{pct(e8)}** | {pct(None if (e8 is None or not es) else e8 / es)} | "
                 f"{pct(e80['disc03'][f'{c}|{m}'])} | {r0['pass']}/{r0['n']} ({r0['wilson_pass']:.4f}) | {b_half} | {b_e80} |")
    L.append("\n### T1. Final inputs per candidate (counts and model only): pooled trades per year per fold, and e*\n")
    L.append("Primary variant `sum03` = the measured pooled rate (sum over symbols). `disc03` = the earlier rule's convention (rate / (1 + (k-1) 0.3)).\n")
    L.append("| cell | method | symbols | folds | measured pooled rate /yr per fold (oldest first) | mean /yr | disc03 mean /yr | e* sum03 (FTMO / The5ers / binding) | e* disc03 (binding) |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for c, m in CANDS:
        rm, folds = rate_matrix((c, m), "sum", 0.0)
        rd, _ = rate_matrix((c, m), "disc", 0.3)
        er = estar[(c, m, "sum03")]
        f = er["by_fund"]
        L.append(f"| {c} | {MNAME[m]} | {len(CELLS[c]['symbols'])} | {len(folds)} | {' '.join(f'{x:.0f}' for x in rm.sum(axis=0))} | {rm.sum(axis=0).mean():.0f} | "
                 f"{rd.sum(axis=0).mean():.0f} | {pct(f['ftmo-challenge-phase1']['e_for_pass_070'], 3)} / {pct(f['the5ers-high-stakes-step1']['e_for_pass_070'], 3)} / **{pct(er['e_star'], 3)}** | "
                 f"{pct(estar[(c, m, 'disc03')]['e_star'], 3)} |")
    curve_table(L, P, CANDS, grid, e80["primary"],
                "\n### T2. P(PASS) of the WHOLE verdict conjunction vs true net edge e, PRIMARY (measured pooled rate, rho 0.3); n = replications run (early stop at >= 98.5 % pass)\n")
    gridd = sorted({e for c in PD for e in PD[c] if e in EGRID or e in EGRID_EXT})
    curve_table(L, PD, CANDS, gridd, e80["disc03"],
                "\n### T2b. Same, earlier-rule convention disc03 (rate discounted AND regime rho 0.3; conservative), 100 replications\n")
    L.append("\n### T3. Floor-only power (primary bound > 0 at 0.98333; same replications as T2) and P(every fold >= 30 trades), PRIMARY\n")
    L.append("| candidate | " + " | ".join(f"{e:.2f}" for e in grid) + " | P(all folds >= 30) |")
    L.append("|---|" + "---|" * (len(grid) + 1))
    for c, m in CANDS:
        row = [("-" if P[(c, m)].get(e) is None else f"{P[(c, m)][e]['floor'] / P[(c, m)][e]['n']:.2f}") for e in grid]
        ra = P[(c, m)][0.2]
        L.append(f"| {c} {MNAME[m]} | " + " | ".join(row) + f" | {ra['all_folds'] / ra['n']:.3f} |")
    L.append("\nSame P(every fold >= 30 trades) under disc03: " + "; ".join(
        f"{c} {MNAME[m]} {PD[(c, m)][0.2]['all_folds'] / PD[(c, m)][0.2]['n']:.3f}" for c, m in CANDS))
    L.append("\n### T4. Type I error at true edge 0 (PRIMARY; family level 0.10/6 = 0.0167)\n")
    L.append("| candidate | n | floor-only passes | rate | Wilson 95 % upper | conjunction passes | rate | Wilson 95 % upper | conjunction <= family level? |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for c, m in CANDS:
        r = fp[(c, m)]
        L.append(f"| {c} {MNAME[m]} | {r['n']} | {r['floor']} | {r['floor'] / r['n']:.4f} | {r['wilson_floor']:.4f} | {r['pass']} | "
                 f"{r['pass'] / r['n']:.4f} | {r['wilson_pass']:.4f} | {'yes' if r['wilson_pass'] <= r['family_level'] else ('point estimate yes, Wilson upper bound no' if r['pass'] / r['n'] <= r['family_level'] else 'NO')} |")
    L.append("\n### T5. Binding check at e = e80/2 and e = e80 (PRIMARY; FULL evaluation with FS.evaluate_cell, nothing short-circuited)\n")
    L.append("`fail %` = share of replications in which the check fails (several can fail together); `sole` = share where it is the ONLY failing check; "
             "top combination = the most frequent set of failing checks. `lower_bound_positive` is the floor bound; `folds_sufficient` is the insufficient guard.\n")
    L.append("| candidate | e | reps | P(PASS) | checks failing most often (fail %) | sole failing check (share of reps) | top combination |")
    L.append("|---|---|---|---|---|---|---|")
    for c, m in CANDS:
        for r in sorted((x for x in doc["attrib"] if tuple(x["cand"]) == (c, m)), key=lambda x: x["e"]):
            fc = sorted(r["fail_counts"].items(), key=lambda kv: -kv[1])[:4]
            so = sorted(r["sole"].items(), key=lambda kv: -kv[1])[:2]
            tc = max(r["combos"].items(), key=lambda kv: kv[1])
            L.append(f"| {c} {MNAME[m]} | {r['e']:.2f} | {r['n']} | {r['pass'] / r['n']:.2f} | " + (", ".join(f"{k} {v / r['n']:.0%}" for k, v in fc) or "none") +
                     " | " + (", ".join(f"{k} {v / r['n']:.0%}" for k, v in so) or "none") + f" | {tc[0]} ({tc[1] / r['n']:.0%}) |")
    L.append("\n### T6. Sensitivity of the full-conjunction e80 (PRIMARY base e80 in column 2; points base-0.05, base, base+0.05 (0.40 / 0.60 / 0.80 when the base is n/a), 40 replications; '>' = not reached on the scanned points)\n")
    names = ["delta0", "delta10", "kappa0", "sigma05", "rho0", "rho06", "cost10"]
    L.append("| candidate | base e80 | " + " | ".join(names) + " |")
    L.append("|---|---|" + "---|" * len(names))
    S = {}
    for r in doc["sens"]:
        S.setdefault((tuple(r["cand"]), r["sens"]), {})[round(r["e"], 4)] = r
    for c, m in CANDS:
        row = []
        for nme in names:
            pts = S.get(((c, m), nme), {})
            hit = next((e for e in sorted(pts) if pts[e]["pass"] / pts[e]["n"] >= 0.80), None)
            if not pts:
                row.append("-")
            elif hit is None:
                row.append(f">{max(pts):.2f}")
            else:
                row.append(f"{hit:.2f}" + (" (at first scanned point)" if hit == min(pts) else ""))
        L.append(f"| {c} {MNAME[m]} | {pct(e80['primary'][f'{c}|{m}'])} | " + " | ".join(row) + " |")
    L.append("\n### T7. P(PASS) when every candidate has its OWN prop-relevant edge e* (true net edge = e*, PRIMARY)\n")
    L.append("| candidate | e* (binding) | n | P(PASS at e*) | floor-only power at e* |")
    L.append("|---|---|---|---|---|")
    tot = 0.0
    for c, m in CANDS:
        es = estar[(c, m, "sum03")]["e_star"]
        pe = [r for r in doc["curve"] if tuple(r["cand"]) == (c, m) and r["cfg"] == cfg_p and es is not None and abs(r["e"] - round(es, 4)) < 1e-9]
        if es is None or not pe:
            L.append(f"| {c} {MNAME[m]} | {pct(es, 3)} | - | - | - |")
            continue
        r = max(pe, key=lambda x: x["n"])
        tot += r["pass"] / r["n"]
        L.append(f"| {c} {MNAME[m]} | {es:.3f} | {r['n']} | {r['pass'] / r['n']:.2f} | {r['floor'] / r['n']:.2f} |")
    L.append(f"\nExpected number of the six candidates that pass if each had true net edge exactly e*: **{tot:.2f}**.")
    # ---- the rule
    L.append("\n### T8. The pre-stated inclusion rule re-applied (cell INCLUDED iff e_min <= k * e*, for at least one method; e_min = floor-bound-only power >= 0.80 on the earlier fine grid)\n")
    L.append("Variant `disc03` = the earlier PRIMARY variant (rate discounted at rho 0.3, regime rho 0.3). Final folds (9 / 2 / 7), availability-aware per-fold counts, floor confidence 0.98333 (family 6). 300 replications per point (800 for 5m-metals).\n")
    L.append("| cell | method | folds | e_min (floor-only, grid) | e_min (interp) | e* (binding) | ratio e_min/e* | <= 2 ? | full-conjunction e80 (disc03) | e80 / e* |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    ratios = {}
    for c, m in CANDS:
        em = floor_emin(doc, (c, m), "disc03")
        emi = floor_emin(doc, (c, m), "disc03", "interp")
        es = estar[(c, m, "disc03")]["e_star"]
        ratio = None if (em is None or not es) else em / es
        e8 = e80["disc03"][f"{c}|{m}"]
        L.append(f"| {c} | {MNAME[m]} | {CELLS[c]['folds']} | {pct(em, 3)} | {pct(emi, 3)} | {pct(es, 3)} | {pct(ratio)} | {'yes' if ratio is not None and ratio <= K_RULE else 'no'} | "
                 f"{pct(e8, 2)} | {pct(None if (e8 is None or not es) else e8 / es)} |")
    L.append("\n### T9. Inclusion verdict per cell and its robustness (best ratio over the two methods; `n/a` = e_min or e* not reached on the grid up to 1.0)\n")
    L.append("| cell | variant | best ratio | k=1.5 | k=2 (RULE) | k=2.5 | k=3 |")
    L.append("|---|---|---|---|---|---|---|")
    for c in cells:
        for v in RULE_VARIANTS:
            rs = []
            for m in METHODS:
                em = floor_emin(doc, (c, m), v)
                es = estar[(c, m, v)]["e_star"]
                ratios[(c, m, v)] = None if (em is None or not es) else em / es
                rs.append(ratios[(c, m, v)])
            ok = [x for x in rs if x is not None]
            best = min(ok) if ok else None
            L.append(f"| {c} | {v}{' (earlier primary)' if v == 'disc03' else (' (measured rate)' if v == 'sum03' else '')} | {pct(best)} | " +
                     " | ".join(("INCLUDED" if best is not None and best <= k else "NOT SATISFIED") for k in K_LIST) + " |")
    L.append("\nPer method and variant (ratio e_min / e*; e_min and e* in brackets):\n")
    L.append("| cell | method | " + " | ".join(RULE_VARIANTS) + " |")
    L.append("|---|---|" + "---|" * len(RULE_VARIANTS))
    for c, m in CANDS:
        row = []
        for v in RULE_VARIANTS:
            em, es = floor_emin(doc, (c, m), v), estar[(c, m, v)]["e_star"]
            row.append(f"{pct(ratios[(c, m, v)])} ({pct(em, 3)} / {pct(es, 3)})")
        L.append(f"| {c} | {MNAME[m]} | " + " | ".join(row) + " |")
    return "\n".join(L) + "\n"


# =============================================================================================================== selfcheck
def selfcheck(n=60):
    """(1) the lazy verdict equals FS.evaluate_cell's verdict (every check computed) on random streams; (2) the vectorised stress
    repricing equals fund_stats.stressed_net_r; (3) memoised ts changes nothing."""
    out = {}
    for cand in (("5m-metals", "wyckoff"), ("1m-indices", "ict")):
        w = World(cand, cfg_of())
        rng = np.random.default_rng(_seed("selfcheck", cand))
        agree = passes = 0
        for i in range(n):
            e = (0.20, 0.35, 0.50, 0.70)[i % 4]
            d = w.draw(rng, e)
            a = eval_lazy(w, d)["verdict"]
            FS.ts.cache_clear()
            b = eval_full(w, d)["verdict"]
            FS.ts.cache_clear()
            agree += int(a == b)
            passes += int(a == FS.PASS)
        out[f"{cand[0]}|{cand[1]}"] = {"n": n, "agree": agree, "lazy_pass": passes}
        assert agree == n, (cand, agree, n)
        if cand[0] == "5m-metals":
            d = w.draw(np.random.default_rng(5), 0.3)
            for i in range(0, len(d["trades"]), max(1, len(d["trades"]) // 20)):
                t, sy = d["trades"][i], d["trades"][i]["symbol"]
                gross = d["stressed"][i]
                st = w.st[sy]
                hour = int(t["entry_time"][11:13])
                cost_i = w.cfg["cost"] * w.cmult[w.syms.index(sy), hour]
                g = t["net_R"] + cost_i
                sc = w.cfg["cost"] * w.p90mult[w.syms.index(sy), hour]
                ref = FS.stressed_net_r(g, sc, st["entry"], st["stop"])
                assert abs(ref - gross) < 1e-9, (ref, gross)
            out["stress_equal"] = True
    return out


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--out", required=True)
    r.add_argument("--procs", type=int, default=4)
    r.add_argument("--quick", action="store_true")
    q = sub.add_parser("report")
    q.add_argument("--json", required=True)
    q.add_argument("--out", required=True)
    sub.add_parser("selfcheck")
    a = ap.parse_args()
    if a.cmd == "selfcheck":
        print(json.dumps(selfcheck(), indent=1))
    elif a.cmd == "report":
        open(a.out, "w").write(report(json.load(open(a.json))))
    else:
        print(json.dumps(selfcheck(8 if a.quick else 24)), flush=True)
        run_all(a)


if __name__ == "__main__":
    main()
