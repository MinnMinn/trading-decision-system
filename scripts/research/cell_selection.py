#!/usr/bin/env python3
"""Cell-selection (b16): trade-RATE pooling + power-model run for the 8 candidate fund-search cells, then the pre-stated
inclusion rule (docs/audits/2026-10-01-cell-selection.md). COUNTS and MODEL outputs only: no performance figure is
read, computed from data, printed or stored. Nothing here edits any harness, engine, threshold or cells file.

Inputs
  * docs/audits/2026-10-01-trade-rates.md   per-symbol admitted-trade counts of b10 (old symbols: 1m/5m/15m)
  * RESULTS jsonl + COVERAGE json           counts-only runs of scripts/research/trade_rates.py for the b16 job set
                                            (10 new symbols at 5m/15m/30m, 7 old symbols at 30m)
  * scripts/research/power_model.py         the harness's own lower-bound rule + prop link (imported, called, not reimplemented)

Commands (all deterministic; seeds = power_model.seed_for)
  rates   --results R --coverage C --out rates.json [--report rates.md]
  power   --rates rates.json --out power.json [--procs 4] [--reps 200] [--pass 1|2 --final-n-ict X --final-n-wyckoff Y]
  report  --rates rates.json --power power.json --out tables.md
Needs BT_HISTORY_ROOT=data/history/ftmo for `rates` (first-bar dates only).

RULE (owner approved BEFORE these measurements; k = 2 chosen AFTER seeing the earlier ratios -- disclosed):
  cell INCLUDED iff e_min <= k * e_star for at least one of {ICT, WYCKOFF-BOOK}, k = 2.
  e_min  = first grid edge (R/trade net of cost, binary +2.5/-1) with harness-rule power >= 0.80 at the cell's N-adjusted confidence
  e_star = smallest net edge with prop_pass_probability >= 0.70 on the BINDING fund (max over ftmo / the5ers).
"""
import argparse
import datetime
import json
import math
import os
import re
import sys
import time
from multiprocessing import Pool

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "research"))

CELLS8 = {   # cell -> (timeframe, asset class, symbols)
    "1m-metals": ("1m", "metals", ["XAUUSD", "XAGUSD"]),
    "1m-indices": ("1m", "indices", ["US500", "US30", "USTEC", "DE40", "FRA40"]),
    "5m-metals": ("5m", "metals", ["XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD"]),
    "5m-indices": ("5m", "indices", ["US500", "US30", "USTEC", "DE40", "FRA40", "UK100", "EU50", "JP225", "HK50", "AUS200",
                                     "US2000", "SPN35", "N25"]),
    "15m-metals": ("15m", "metals", ["XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD"]),
    "15m-indices": ("15m", "indices", ["US500", "US30", "USTEC", "DE40", "FRA40", "UK100", "EU50", "JP225", "HK50", "AUS200",
                                       "US2000", "SPN35", "N25"]),
    "30m-metals": ("30m", "metals", ["XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD"]),
    "30m-indices": ("30m", "indices", ["US500", "US30", "USTEC", "DE40", "FRA40", "UK100", "EU50", "JP225", "HK50", "AUS200",
                                       "US2000", "SPN35", "N25"]),
}
FOLDS = {"1m-metals": 9, "1m-indices": 4, "5m-metals": 17, "5m-indices": 4, "15m-metals": 17, "15m-indices": 4,
         "30m-metals": 17, "30m-indices": 4}   # plan --dry-run (6 cells) + make_folds on the 30m earliest symbol (verified, doc)
METHODS = ("ict", "wyckoff")
MNAME = {"ict": "ICT", "wyckoff": "WYCKOFF"}
SLICES = ("S1", "S2", "S3")
N_PER_CELL = {"ICT": 29, "WYCKOFF": 16}
K_LIST = (1.5, 2.0, 2.5, 3.0)
K_RULE = 2.0
RHOS = (0.0, 0.3, 0.6)
BASE_RHO = 0.3
B10_DOC = os.path.join(ROOT, "docs", "audits", "2026-10-01-trade-rates.md")
EGRID = [0.05, 0.075, 0.10, 0.125, 0.15, 0.175, 0.20, 0.225, 0.25, 0.275, 0.30, 0.325, 0.35, 0.375, 0.40, 0.50, 0.60, 0.80, 1.00]
REQ_E = (0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40)


# ----------------------------------------------------------------------------------------------------------- rates
def parse_b10(path=B10_DOC):
    """{(method, symbol, tf): {"counts": {S1,S2,S3}, "partial": {S1: bool..}}} from the per-symbol tables, plus the published
    1m pooled rates {(method, cell): rate} from the derived table."""
    txt = open(path).read()
    sym = {}
    for m, head in (("ict", "#### ICT"), ("wyckoff", "#### WYCKOFF")):
        i = txt.index(head)
        j = txt.index("#### ", i + 5)
        for line in txt[i:j].splitlines():
            r = re.match(r"\| (\d+m)-(metals|indices) \| ([A-Z0-9]+) \| (\d+) \| (\d+) \| (\d+) \| ([^|]*)\|", line)
            if r:
                tf, _, s, a, b, c, cov = r.groups()
                part = {sl: (sl + "*") in cov for sl in SLICES}
                sym[(m, s, tf)] = {"counts": {"S1": int(a), "S2": int(b), "S3": int(c)}, "partial": part}
    pooled = {}
    for line in txt.splitlines():
        r = re.match(r"\| (ict|wyckoff) \| (1m-(?:metals|indices)) \| [^|]*\| [^|]*\| ([0-9.]+) \|", line)
        if r:
            pooled[(r.group(1), r.group(2))] = float(r.group(3))
    return sym, pooled


def first_bars():
    """First bar (PIT-cut series) per (symbol, tf) for the cell timeframes 5m/15m/30m, via the harness loader (reads dates only)."""
    import importlib.util
    import fund_stats as FS
    spec = importlib.util.spec_from_file_location("fund_search_cs", os.path.join(ROOT, "scripts", "fund-search.py"))
    fs = importlib.util.module_from_spec(spec)
    sys.modules["fund_search_cs"] = fs
    spec.loader.exec_module(fs)
    bt = fs._load_bt()
    bt.pit_cutoff(FS.DEV_CUTOFF)
    out = {}
    for tf in ("5m", "15m", "30m"):
        for ac, syms in (("metals", CELLS8["5m-metals"][2]), ("indices", CELLS8["5m-indices"][2])):
            for s in syms:
                c, _ = bt.load(s, tf)
                out[f"{s}|{tf}"] = c[0]["time"]
    return out


def build_rates(results_path, cov_path):
    old, pooled1m = parse_b10()
    cov = json.load(open(cov_path))
    new = {}
    for line in open(results_path):
        if line.strip():
            r = json.loads(line)
            new.setdefault((r["method"], r["symbol"], r["tf"]), {})[r["slice"]] = r

    def complete(sym, tf, sl):                       # >= 90 % of the best-covered slice (same rule as trade_rates.report)
        best = max(cov[f"{sym}|{tf}|{s}"] for s in SLICES)
        return cov[f"{sym}|{tf}|{sl}"] >= 0.9 * best

    per_sym = {}
    for m in METHODS:
        for cell, (tf, ac, syms) in CELLS8.items():
            if tf == "1m":
                continue
            for s in syms:
                key = f"{m}|{s}|{tf}"
                if key in per_sym:
                    continue
                if (m, s, tf) in new and all(new[(m, s, tf)].get(sl, {}).get("status") for sl in SLICES):
                    rows = new[(m, s, tf)]
                    counts = {sl: (rows[sl]["trades"] if rows[sl]["status"] == "OK" else None) for sl in SLICES}
                    status = {sl: rows[sl]["status"] for sl in SLICES}
                    comp = {sl: counts[sl] is not None and complete(s, tf, sl) for sl in SLICES}
                    src = "b16"
                    fb = next((rows[sl].get("first_bar") for sl in SLICES if rows[sl].get("first_bar")), None)
                    bars = {sl: cov[f"{s}|{tf}|{sl}"] for sl in SLICES}
                elif (m, s, tf) in old:
                    d = old[(m, s, tf)]
                    counts, status = d["counts"], {sl: "OK" for sl in SLICES}
                    comp = {sl: not d["partial"][sl] for sl in SLICES}
                    src, fb, bars = "b10", None, None
                else:
                    per_sym[key] = {"method": m, "symbol": s, "tf": tf, "rate": None, "reason": "NOT MEASURED (missing)"}
                    continue
                used = [sl for sl in SLICES if comp[sl]]
                rate = (sum(counts[sl] for sl in used) / len(used)) if used else None
                per_sym[key] = {"method": m, "symbol": s, "tf": tf, "counts": counts, "status": status, "complete": comp,
                                "used": used, "rate": rate, "source": src, "first_bar_in_run": fb, "slice_bars": bars}
    return {"per_symbol": per_sym, "pooled_1m_b10": {f"{m}|{c}": v for (m, c), v in pooled1m.items()},
            "first_bar": first_bars()}


def k_eff(k, rho):
    return k / (1.0 + (k - 1) * rho)


def cell_rates(rates, cell, method):
    """Pooled rate per cell and method: SUM of per-symbol yearly rates (complete slices only), the effective-symbol discounted
    pooled rate for rho in RHOS (design-effect formula k_eff = k / (1 + (k - 1) rho), applied to the sum), per-symbol detail."""
    tf, ac, syms = CELLS8[cell]
    if tf == "1m":
        tot = rates["pooled_1m_b10"][f"{method}|{cell}"]
        per = None
    else:
        per = {s: rates["per_symbol"][f"{method}|{s}|{tf}"]["rate"] for s in syms}
        tot = None if any(v is None for v in per.values()) else sum(per.values())
    k = len(syms)
    disc = None if tot is None else {str(r): tot * k_eff(k, r) / k for r in RHOS}
    return {"k": k, "sum": tot, "disc": disc, "per_symbol": per}


# ---------------------------------------------------------------------------------------------------------- power
def day_offset(first_bar_iso, folds):
    import numpy as np
    from power_model import CUTOFF, FOLD_DAYS
    day0 = CUTOFF - np.timedelta64(folds * FOLD_DAYS, "D")
    fb = np.datetime64(first_bar_iso[:10])
    return int(max(0, (fb - day0).astype(int)))


def n_of(method, cells_count):
    return N_PER_CELL[MNAME[method]] * cells_count


def build_jobs(rates, reps, n_final=None, quick=False):
    """Jobs for power_model.run_power / run_prop.
    variants (rate used, regime rho, availability):
      base      = discounted rate at rho 0.3, regime rho 0.3, exchangeable symbols present in every fold   (PRIMARY)
      sum03     = undiscounted SUM rate, regime rho 0.3
      rho0      = sum rate (discount 1), regime rho 0
      rho06     = rate discounted at 0.6, regime rho 0.6
      avail     = base rates/rho but late symbols absent before their first bar (per-symbol rates)  (sensitivity)
    N list: candidate set (8 cells) and, if given, the final included-set N."""
    jobs = []
    for m in METHODS:
        M = MNAME[m]
        Ns = [n_of(m, 8)] + ([n_final[m]] if n_final and n_final[m] != n_of(m, 8) else [])
        for cell, (tf, ac, syms) in CELLS8.items():
            cr = cell_rates(rates, cell, m)
            if cr["sum"] is None:
                continue
            k, F = cr["k"], FOLDS[cell]
            variants = {"base": (cr["disc"]["0.3"], 0.3), "sum03": (cr["sum"], 0.3), "rho0": (cr["sum"], 0.0),
                        "rho06": (cr["disc"]["0.6"], 0.6)}
            for vn, (rate, rho) in variants.items():
                jobs.append(("power", dict(label=f"cs|{vn}|{M}|{cell}", method=M, cell=cell, folds=F, k=k, rate_sym=rate / k,
                                           e_list=EGRID, reps=reps, N_list=Ns, cost=0.07, sigma=0.75, tau=0.03, rho=rho)))
                jobs.append(("prop", dict(label=f"cs|{vn}|{M}|{cell}", method=M, cell=cell, k=k, rate_sym=rate / k,
                                          years=max(20, math.ceil(20000 / rate)), cost=0.07, sigma=0.75, tau=0.03, rho=rho)))
            if cr["per_symbol"] is not None:       # availability-aware variant (late-starting symbols)
                fscale = cr["disc"]["0.3"] / cr["sum"]
                fb = [rates["first_bar"][f"{s}|{tf}"] for s in syms]
                jobs.append(("power", dict(label=f"cs|avail|{M}|{cell}", method=M, cell=cell, folds=F, k=k,
                                           rate_sym=[cr["per_symbol"][s] * fscale for s in syms],
                                           sym_first_day=[day_offset(x, F) for x in fb], e_list=EGRID, reps=reps,
                                           N_list=Ns, cost=0.07, sigma=0.75, tau=0.03, rho=0.3)))

    def weight(it):
        j = it[1]
        rate = sum(j["rate_sym"]) if isinstance(j["rate_sym"], list) else j["rate_sym"] * j["k"]
        if it[0] == "prop":
            return rate * j["years"] * 4
        return rate * j["folds"] * j["reps"] * len(j["e_list"]) * max(1, len(j["N_list"]) * 0.6)
    jobs.sort(key=weight, reverse=True)
    return jobs


def _run(item):
    import power_model as PM
    kind, job = item
    return kind, {"power": PM.run_power, "prop": PM.run_prop}[kind](job)


def run_power_cmd(a):
    import power_model as PM
    rates = json.load(open(a.rates))
    nf = None
    if a.final_n_ict:
        nf = {"ict": a.final_n_ict, "wyckoff": a.final_n_wyckoff}
    t0 = time.time()
    jobs = build_jobs(rates, a.reps, nf)
    if a.only:
        jobs = [j for j in jobs if any(x in j[1]["label"] for x in a.only.split(","))]
    sc = PM.selfcheck()
    print(f"{len(jobs)} jobs, {a.procs} processes", flush=True)
    res = {"power": [], "prop": []}
    with Pool(min(a.procs, 4)) as pool:
        for i, (kind, r) in enumerate(pool.imap_unordered(_run, jobs, chunksize=1)):
            res[kind].append(r)
            if (i + 1) % 10 == 0:
                print(f"  {i + 1}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
    doc = {"meta": {"script": "scripts/research/cell_selection.py", "base_seed": PM.BASE_SEED, "reps": a.reps, "egrid": EGRID,
                    "base": PM.BASE, "folds": FOLDS, "cells": {c: list(v[2]) for c, v in CELLS8.items()}, "selfcheck": sc,
                    "final_n": nf, "seconds": round(time.time() - t0, 1)}, **res}
    json.dump(doc, open(a.out, "w"), indent=1, sort_keys=True)
    print(f"wrote {a.out} in {time.time() - t0:.0f}s")


# --------------------------------------------------------------------------------------------------------- verdict
def emin_grid(by_e, n):
    for e in sorted(by_e, key=float):
        if by_e[e]["power"][str(n)] >= 0.80:
            return float(e)
    return None


def emin_interp(by_e, n):
    pts = sorted((float(e), by_e[e]["power"][str(n)]) for e in by_e)
    for (e0, p0), (e1, p1) in zip(pts, pts[1:]):
        if p0 < 0.80 <= p1:
            return e0 + (0.80 - p0) * (e1 - e0) / (p1 - p0) if p1 > p0 else e1
    return pts[0][0] if pts and pts[0][1] >= 0.80 else None


def estar_of(prop):
    es = [prop["by_fund"][f]["e_for_pass_070"] for f in prop["by_fund"]]
    return None if any(x is None for x in es) else max(es)


def index(doc):
    P = {r["job"]["label"]: r for r in doc["power"]}
    Q = {r["job"]["label"]: r for r in doc["prop"]}
    return P, Q


def verdicts(doc, variant, N_of_method, k=K_RULE):
    """{(cell, method): dict(e_min, e_min_i, e_star, ratio, ok)} for one variant at the N given per method."""
    P, Q = index(doc)
    out = {}
    for cell in CELLS8:
        for m in METHODS:
            lab = f"cs|{variant}|{MNAME[m]}|{cell}"
            if lab not in P:
                continue
            by = P[lab]["by_e"]
            n = N_of_method[m]
            em, emi = emin_grid(by, n), emin_interp(by, n)
            # e_star always from the matching prop job when it exists (avail uses the base prop link)
            qlab = lab if lab in Q else f"cs|base|{MNAME[m]}|{cell}"
            es = estar_of(Q[qlab])
            ratio = None if (em is None or es is None or es <= 0) else em / es
            out[(cell, m)] = {"e_min": em, "e_min_i": emi, "e_star": es, "ratio": ratio, "ok": ratio is not None and ratio <= k,
                              "ratio_i": None if (emi is None or not es) else emi / es}
    return out


def included(vd, k=K_RULE):
    return [c for c in CELLS8 if any(vd.get((c, m), {}).get("ratio") is not None and vd[(c, m)]["ratio"] <= k for m in METHODS)]


def fmt(x, nd=3):
    return "n/a" if x is None else f"{x:.{nd}f}"


def report_cmd(a):
    rates = json.load(open(a.rates))
    doc = json.load(open(a.power))
    P, Q = index(doc)
    L = []
    # ---- rates
    L.append("### T1. Per-symbol admitted trades per one-year slice and per-symbol yearly rate (counts only)\n")
    L.append("S1/S2/S3 = 2021-03-01..2022-03-01 / ..2023-03-01 / ..2024-03-01. `*` = slice partly uncovered (bars < 90 % of the symbol's "
             "best slice; excluded from the rate). rate = mean over the complete slices. source b10 = docs/audits/2026-10-01-trade-rates.md, "
             "b16 = this run.\n")
    L.append("| method | tf | symbol | S1 | S2 | S3 | slices used | rate /yr | source | first bar (run) |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for m in METHODS:
        for tf in ("5m", "15m", "30m"):
            seen = []
            for cell, (ctf, ac, syms) in CELLS8.items():
                if ctf != tf:
                    continue
                for s in syms:
                    if s in seen:
                        continue
                    seen.append(s)
                    d = rates["per_symbol"][f"{m}|{s}|{tf}"]
                    if d.get("rate") is None and "counts" not in d:
                        L.append(f"| {MNAME[m]} | {tf} | {s} | NOT MEASURED | | | | | | |")
                        continue
                    cs = []
                    for sl in SLICES:
                        v = d["counts"][sl]
                        txt = "NO_DATA" if v is None else str(v)
                        cs.append(txt + ("" if d["complete"][sl] else "*"))
                    L.append(f"| {MNAME[m]} | {tf} | {s} | " + " | ".join(cs) + f" | {','.join(d['used']) or 'none'} | {fmt(d['rate'], 1)} | "
                             f"{d['source']} | {(d.get('first_bar_in_run') or '')[:10]} |")
    L.append("\n### T2. Pooled trade rate per candidate cell (trades / year, sum over symbols) and effective-symbol discount\n")
    L.append("sum = SUM of per-symbol rates (1m cells: b10's published pooled rate). Discount: k_eff = k / (1 + (k-1) rho), pooled_eff = sum x "
             "k_eff / k. rho = 0 equals the sum. Base case rho 0.3.\n")
    L.append("| method | cell | k | folds | sum /yr | rho=0 | rho=0.3 (base) | rho=0.6 | k_eff (0.3) |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for m in METHODS:
        for cell in CELLS8:
            cr = cell_rates(rates, cell, m)
            if cr["sum"] is None:
                L.append(f"| {MNAME[m]} | {cell} | {cr['k']} | {FOLDS[cell]} | NOT MEASURED | | | | |")
                continue
            L.append(f"| {MNAME[m]} | {cell} | {cr['k']} | {FOLDS[cell]} | {cr['sum']:.1f} | {cr['disc']['0.0']:.1f} | {cr['disc']['0.3']:.1f} | "
                     f"{cr['disc']['0.6']:.1f} | {k_eff(cr['k'], 0.3):.2f} |")
    nc = {m: n_of(m, 8) for m in METHODS}
    # ---- power curves
    for vname, vtitle in (("base", "PRIMARY: discounted rate (rho 0.3), regime rho 0.3"),
                          ("sum03", "undiscounted sum rate, regime rho 0.3"),
                          ("rho0", "sum rate, regime rho 0"), ("rho06", "rate discounted at rho 0.6, regime rho 0.6"),
                          ("avail", "availability-aware (late symbols absent before first bar), discounted rate, rho 0.3")):
        L.append(f"\n### T3-{vname}. Power of the harness lower-bound rule, N = candidate set ({vtitle})\n")
        for m in METHODS:
            L.append(f"\n{MNAME[m]}, N = {nc[m]}, confidence {1 - 0.10 / nc[m]:.6f}; P(rule returns > 0), {doc['meta']['reps']} replications per cell and e\n")
            L.append("| cell | E[n] at e=0.20 | " + " | ".join(f"e={e:.2f}" for e in REQ_E) + " | e_min (grid) | e_min (interp) | P(all folds >= 30) |")
            L.append("|---|---|" + "---|" * (len(REQ_E) + 3))
            for cell in CELLS8:
                lab = f"cs|{vname}|{MNAME[m]}|{cell}"
                if lab not in P:
                    continue
                by = P[lab]["by_e"]
                row = [f"{by[str(e)]['power'][str(nc[m])]:.2f}" if str(e) in by else "" for e in REQ_E]
                L.append(f"| {cell} | {by['0.2']['n_mean']:.0f} | " + " | ".join(row) +
                         f" | {fmt(emin_grid(by, nc[m]), 3)} | {fmt(emin_interp(by, nc[m]), 3)} | {by['0.2']['p_all_folds_ge_min']:.2f} |")
    # ---- e_star
    L.append("\n### T4. e_star: net edge at which prop_pass_probability (120-day horizon) first reaches 0.70 (bisection, 9 steps), per fund and binding\n")
    L.append("| variant | method | cell | trades/yr (pooled used) | e* FTMO | e* The5ers | binding e* |")
    L.append("|---|---|---|---|---|---|---|")
    for vname in ("base", "sum03", "rho0", "rho06"):
        for m in METHODS:
            for cell in CELLS8:
                lab = f"cs|{vname}|{MNAME[m]}|{cell}"
                if lab not in Q:
                    continue
                q = Q[lab]
                f1, f2 = q["by_fund"]["ftmo-challenge-phase1"]["e_for_pass_070"], q["by_fund"]["the5ers-high-stakes-step1"]["e_for_pass_070"]
                L.append(f"| {vname} | {MNAME[m]} | {cell} | {q['job']['rate_sym'] * q['job']['k']:.0f} | {fmt(f1)} | {fmt(f2)} | {fmt(estar_of(q))} |")
    # ---- verdicts
    def vtable(vname, Nmap, title, ks=(K_RULE,)):
        vd = verdicts(doc, vname, Nmap)
        L.append(f"\n### {title}\n")
        L.append("| cell | method | e_min | e_min (interp) | e_star | ratio | ratio (interp) | <= 2 ? |")
        L.append("|---|---|---|---|---|---|---|---|")
        for cell in CELLS8:
            for m in METHODS:
                d = vd.get((cell, m))
                if not d:
                    continue
                L.append(f"| {cell} | {MNAME[m]} | {fmt(d['e_min'])} | {fmt(d['e_min_i'])} | {fmt(d['e_star'])} | {fmt(d['ratio'], 2)} | "
                         f"{fmt(d['ratio_i'], 2)} | {'yes' if d['ok'] else 'no'} |")
        return vd

    vd0 = vtable("base", nc, f"T5. Rule verdict at k = 2, PRIMARY variant, N = candidate set (ICT {nc['ict']}, Wyckoff {nc['wyckoff']})")
    # inclusion + sensitivity in k
    L.append("\n### T6. Included cells by k (cell included iff min over methods of ratio <= k), N = candidate set\n")
    L.append("| variant | k=1.5 | k=2 | k=2.5 | k=3 |")
    L.append("|---|---|---|---|---|")
    for vname in ("base", "sum03", "rho0", "rho06", "avail"):
        vd = verdicts(doc, vname, nc)
        L.append(f"| {vname} | " + " | ".join((", ".join(included(vd, k)) or "none") for k in K_LIST) + " |")
    L.append("\nBest ratio per cell (min over methods), by variant, N = candidate set (n/a = e_min not reached on the grid up to 1.0)\n")
    L.append("| cell | " + " | ".join(("base", "sum03", "rho0", "rho06", "avail")) + " |")
    L.append("|---|---|---|---|---|---|")
    vds = {v: verdicts(doc, v, nc) for v in ("base", "sum03", "rho0", "rho06", "avail")}
    for cell in CELLS8:
        row = []
        for v in vds:
            rs = [vds[v][(cell, m)]["ratio"] for m in METHODS if (cell, m) in vds[v] and vds[v][(cell, m)]["ratio"] is not None]
            row.append(fmt(min(rs), 2) if rs else "n/a")
        L.append(f"| {cell} | " + " | ".join(row) + " |")
    # ---- final-N
    doc2 = json.load(open(a.power_final)) if a.power_final else None
    fn = doc2["meta"].get("final_n") if doc2 else None
    if fn:
        doc = doc2
        L.append(f"\n### T7. Same verdict at the FINAL included-set N (ICT {fn['ict']}, Wyckoff {fn['wyckoff']}), PRIMARY variant\n")
        vdf = verdicts(doc, "base", fn)
        L.append("| cell | method | e_min | e_star | ratio | <= 2 ? |")
        L.append("|---|---|---|---|---|---|")
        for cell in CELLS8:
            for m in METHODS:
                d = vdf.get((cell, m))
                if d:
                    L.append(f"| {cell} | {MNAME[m]} | {fmt(d['e_min'])} | {fmt(d['e_star'])} | {fmt(d['ratio'], 2)} | {'yes' if d['ok'] else 'no'} |")
        L.append("\nIncluded by k at the final N: " + "; ".join(f"k={k}: {', '.join(included(vdf, k)) or 'none'}" for k in K_LIST))
    open(a.out, "w").write("\n".join(L) + "\n")


def rates_cmd(a):
    rates = build_rates(a.results, a.coverage)
    json.dump(rates, open(a.out, "w"), indent=1, sort_keys=True)
    print(f"wrote {a.out}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rates")
    r.add_argument("--results", required=True)
    r.add_argument("--coverage", required=True)
    r.add_argument("--out", required=True)
    p = sub.add_parser("power")
    p.add_argument("--rates", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--procs", type=int, default=4)
    p.add_argument("--reps", type=int, default=200)
    p.add_argument("--only", help="comma list of label substrings to run (testing)")
    p.add_argument("--final-n-ict", type=int)
    p.add_argument("--final-n-wyckoff", type=int)
    q = sub.add_parser("report")
    q.add_argument("--rates", required=True)
    q.add_argument("--power", required=True)
    q.add_argument("--power-final", help="power JSON of the second pass (power --only 'cs|base|' --final-n-ict X --final-n-wyckoff Y)")
    q.add_argument("--out", required=True)
    a = ap.parse_args()
    {"rates": rates_cmd, "power": run_power_cmd, "report": report_cmd}[a.cmd](a)


if __name__ == "__main__":
    main()
