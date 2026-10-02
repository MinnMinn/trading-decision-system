#!/usr/bin/env python3
"""dev_start decision by AVAILABILITY (docs/audits/2026-10-02-dev-start-decision.md; rule: draft section 0.3).

Outcome-free: reads ADMITTED-TRADE COUNTS (scripts/research/trade_rates.py, year slices) and bar COUNTS only. No trade
outcome or performance figure is read, computed or stored here. (power_model.gen_stream draws synthetic streams; the
synthetic edge only affects synthetic wins and never the per-fold trade counts this script reads.)

    census  --out census.json                 bar counts per symbol-month from the stored history (< DEV_CUTOFF)
    rates   --results R.jsonl --out rates.json  per (method, symbol, year) admitted-trade counts
    decide  --census census.json --rates rates.json --out decision.json   P(all folds >= 30) per candidate, dense condition
    report  --census ... --rates ... --decision ... --out tables.md
Needs BT_HISTORY_ROOT=data/history/ftmo only for `census` (reads data/history/ftmo by path; no engine).
"""
import argparse
import datetime
import gzip
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "research"))

HIST = os.path.join(ROOT, "data", "history", "ftmo")
CUTOFF = "2024-03-01"
FOLD_DAYS = 365
MIN_TRAIN_DAYS = 730
RHO = 0.3
REPS = 2000
EDGE = 0.20                  # synthetic edge: only the synthetic wins depend on it; per-fold counts do not
THRESH = 0.80
CELLS = {
    "5m-metals": {"tf": "5m", "symbols": ["XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD"],
                  "candidates": ["2004-06-11", "2009-03-01", "2015-01-07"]},
    "1m-indices": {"tf": "1m", "symbols": ["US500", "US30", "USTEC", "DE40", "FRA40"],
                   "candidates": ["2017-12-27", "2020-03-01"]},
}
DENSE_SHARE = 0.50
REF_START, REF_END = "2023-03", "2024-02"     # reference months (the last dev year) that define 'expected bars'


def _d(s):
    return datetime.date.fromisoformat(s[:10])


def weekdays_in_month(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    d = datetime.date(y, m, 1)
    n = 0
    while d.month == m:
        n += d.weekday() < 5
        d += datetime.timedelta(days=1)
    return n


def months_between(a, b):
    """YYYY-MM list for months fully or partly inside [a, b) (dates)."""
    out, d = [], datetime.date(a.year, a.month, 1)
    while d < b:
        out.append(f"{d.year:04d}-{d.month:02d}")
        d = datetime.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return out


# ----------------------------------------------------------------------------------------------------- census
def census(out):
    res = {}
    for cell, c in CELLS.items():
        for s in c["symbols"]:
            d = os.path.join(HIST, f"ohlcv.{s}.{c['tf']}")
            months, first = {}, None
            for f in sorted(os.listdir(d)):
                if not f.endswith(".json.gz"):
                    continue
                for cd in json.load(gzip.open(os.path.join(d, f)))["candles"]:
                    t = cd["time"]
                    if t >= CUTOFF + "T00:00:00Z":
                        continue
                    months[t[:7]] = months.get(t[:7], 0) + 1
                    if first is None or t < first:
                        first = t
            res[f"{s}|{c['tf']}"] = {"first_bar": first, "months": months}
            print(s, c["tf"], first, sum(months.values()), flush=True)
    json.dump(res, open(out, "w"), indent=1, sort_keys=True)


def per_weekday_expected(cen, key):
    """bars per weekday in the reference year (the symbol's own full-density behaviour)."""
    ms = [m for m in months_between(_d(REF_START + "-01"), _d(CUTOFF)) if REF_START <= m <= REF_END]
    bars = sum(cen[key]["months"].get(m, 0) for m in ms)
    wd = sum(weekdays_in_month(m) for m in ms)
    return bars / wd


def dense(cen, key, a, b):
    """Symbol dense over [a, b): total bars >= 50 % of expected (per-weekday reference x weekdays) over the months of the
    window clipped to the symbol's own first bar's absence counting as ZERO bars (a not-yet-existing symbol is not dense)."""
    exp_pd = per_weekday_expected(cen, key)
    ms = months_between(a, b)
    got = sum(cen[key]["months"].get(m, 0) for m in ms)
    exp = sum(weekdays_in_month(m) for m in ms) * exp_pd
    return (got / exp if exp else 0.0), got >= DENSE_SHARE * exp


def folds_for(start, n_cap=None):
    """make_folds geometry: 365-day test folds ending at the cutoff, stepping back while >= 730 d of training precede."""
    cut = _d(CUTOFF)
    st = _d(start)
    out, end = [], cut
    while True:
        fs = end - datetime.timedelta(days=FOLD_DAYS)
        if (fs - st).days < MIN_TRAIN_DAYS:
            break
        out.append((fs, end))
        end = fs
    return list(reversed(out))


# ----------------------------------------------------------------------------------------------------- rates
def build_rates(results_path):
    """{method|symbol|year: admitted trades} from trade_rates.py year-slice JSONL (statuses kept)."""
    res = {}
    for line in open(results_path):
        if not line.strip():
            continue
        r = json.loads(line)
        res[f"{r['method']}|{r['symbol']}|{r['slice'][1:]}"] = {"status": r["status"], "trades": r.get("trades"),
                                                                 "reason": r.get("reason"), "seconds": r.get("seconds")}
    return res


def year_count(rates, method, sym, year, cen, tf):
    r = rates.get(f"{method}|{sym}|{year}")
    return r


def fold_rate(rates, method, sym, a, b):
    """Admitted trades per fold for (symbol, method) = sum over the calendar years of the fold, each year scaled by the
    fraction of the year inside [a, b). Calendar years absent from the results (before the symbol's first bar) count 0."""
    tot = 0.0
    for y in range(a.year, b.year + 1):
        y0, y1 = datetime.date(y, 1, 1), datetime.date(y + 1, 1, 1)
        lo, hi = max(a, y0), min(b, y1)
        if hi <= lo:
            continue
        r = rates.get(f"{method}|{sym}|{y}")
        if r is None or r["status"] != "OK":
            continue
        tot += r["trades"] * (hi - lo).days / (y1 - y0).days
    return tot


# ----------------------------------------------------------------------------------------------------- decision
def k_eff_scale(k, rho):
    """discounted/sum = k_eff / k with k_eff = k / (1 + (k - 1) rho) (cell_selection.k_eff, applied to the SUM rate)."""
    return 1.0 / (1.0 + (k - 1) * rho)


def p_all_folds(cell, start, method, rates, cen, scale_mode):
    """Monte-Carlo P(every test fold >= MIN_FOLD_TRADES admitted trades) with power_model.gen_stream (same machinery,
    availability-aware: per-symbol per-fold rate, a symbol is absent before its first bar because its measured count is 0)."""
    import numpy as np
    import power_model as PM
    import fund_stats as FS
    c = CELLS[cell]
    syms = c["symbols"]
    k = len(syms)
    folds = folds_for(start)
    F = len(folds)
    rate = np.zeros((k, F))
    for j, s in enumerate(syms):
        for i, (a, b) in enumerate(folds):
            rate[j, i] = fold_rate(rates, method, s, a, b)
    # discount for cross-symbol correlation at RHO: 'cell' = the cell's full k (the existing T3-avail convention),
    # 'present' = k_eff of the symbols with a positive rate in that fold (sensitivity)
    sc = np.ones(F)
    for i in range(F):
        kk = k if scale_mode == "cell" else max(1, int((rate[:, i] > 0).sum()))
        sc[i] = k_eff_scale(kk, RHO)
    rate = rate * sc[None, :]
    seed_label = f"dev-start|{cell}|{start}|{method}|{scale_mode}"
    rng = np.random.default_rng(PM.seed_for(seed_label, F, k, RHO))
    p = PM.p_from_edge(EDGE, 0.07)
    ok, mins = 0, []
    per_fold_mean = np.zeros(F)
    for _ in range(REPS):
        _, pf = gen_stream_by_fold(PM, rng, rate, k, F, p, RHO)
        ok += int(pf.min() >= FS.MIN_FOLD_TRADES)
        per_fold_mean += pf
    return {"folds": F, "p_all": ok / REPS, "mean_per_fold": [round(x / REPS, 1) for x in per_fold_mean],
            "expected_per_fold_model": [round(float(rate[:, i].sum()), 1) for i in range(F)],
            "fold_bounds": [[a.isoformat(), b.isoformat()] for a, b in folds]}


def gen_stream_by_fold(PM, rng, rate_kf, k, F, p, rho):
    """power_model.gen_stream with a per-(symbol, fold) yearly rate (k, F) instead of a per-symbol constant: the same
    month-level lognormal regime (sigma 0.75), the same cross-symbol correlation rho, weekday-only Poisson arrivals.
    Implemented by temporarily mapping rows of rate_kf to days; gen_stream itself is NOT modified."""
    import numpy as np
    n_days = F * PM.FOLD_DAYS
    day0 = PM.CUTOFF - np.timedelta64(n_days, "D")
    days = day0 + np.arange(n_days).astype("timedelta64[D]")
    dow = (days.astype("datetime64[D]").astype(np.int64) + 3) % 7
    wd = (dow < 5).astype(float)
    months = days.astype("datetime64[M]").astype(np.int64)
    _, m_idx = np.unique(months, return_inverse=True)
    n_m = int(m_idx.max()) + 1
    sigma = 0.75

    def mixed():
        zc = rng.standard_normal(n_m)
        zs = rng.standard_normal((k, n_m))
        return math.sqrt(rho) * zc[None, :] + math.sqrt(1.0 - rho) * zs

    z_rate = mixed()
    mult = np.exp(sigma * z_rate - 0.5 * sigma * sigma)
    fold_of_day = np.arange(n_days) // PM.FOLD_DAYS
    lam = rate_kf[:, fold_of_day] / (PM.FOLD_DAYS * 5.0 / 7.0) * mult[:, m_idx] * wd[None, :]
    counts = rng.poisson(lam)
    per_fold = np.zeros(F, dtype=int)
    for i in range(F):
        per_fold[i] = counts[:, fold_of_day == i].sum()
    return None, per_fold


def dense_condition(cell, start, cen):
    c = CELLS[cell]
    syms, tf = c["symbols"], c["tf"]
    m = len(syms)
    need = math.ceil(2 * m / 3)
    st = _d(start)
    rows, ok_all = [], True
    for i, (a, b) in enumerate(folds_for(start)):
        fold_d, train_d = [], []
        for s in syms:
            key = f"{s}|{tf}"
            _, df = dense(cen, key, a, b)
            _, dt = dense(cen, key, st, a)
            fold_d.append(df)
            train_d.append(dt)
        n_fold = sum(fold_d)
        n_either = sum(1 for x, y in zip(fold_d, train_d) if x or y)
        ok = n_either >= need
        ok_all &= ok
        rows.append({"fold": i + 1, "start": a.isoformat(), "end": b.isoformat(), "dense_in_fold": n_fold,
                     "dense_in_fold_or_train": n_either, "need": need, "ok": ok,
                     "fold_dense_symbols": [s for s, x in zip(syms, fold_d) if x],
                     "train_dense_symbols": [s for s, x in zip(syms, train_d) if x]})
    return {"need": need, "rows": rows, "ok": ok_all}


def decide(cen_path, rates_path, out):
    cen = json.load(open(cen_path))
    rates = json.load(open(rates_path))
    res = {}
    for cell, c in CELLS.items():
        res[cell] = {}
        for start in c["candidates"]:
            ent = {"folds": len(folds_for(start)), "dense": dense_condition(cell, start, cen) if cell == "1m-indices" else None,
                   "P": {}}
            for method in ("ict", "wyckoff"):
                ent["P"][method] = {}
                for mode in ("cell", "present"):
                    ent["P"][method][mode] = p_all_folds(cell, start, method, rates, cen, mode)
            res[cell][start] = ent
            print(cell, start, {m: ent["P"][m]["cell"]["p_all"] for m in ent["P"]}, flush=True)
    json.dump(res, open(out, "w"), indent=1)


def verdict(cell, dec):
    """Earliest candidate with P >= 0.80 for BOTH methods (primary model) AND (1m-indices) the dense condition; else the last
    candidate; `none` flag records that no candidate qualified."""
    for start, e in dec[cell].items():
        p_ok = all(e["P"][m]["cell"]["p_all"] >= THRESH for m in e["P"])
        d_ok = e["dense"]["ok"] if e["dense"] else True
        if p_ok and d_ok:
            return start, True
    return list(dec[cell])[-1], False


def report(cen_path, rates_path, dec_path, out):
    cen = json.load(open(cen_path))
    rates = json.load(open(rates_path))
    dec = json.load(open(dec_path))
    L = []
    L.append("### T1. Admitted baseline trades per symbol, method and calendar year (counts only)\n")
    for cell, c in CELLS.items():
        years = sorted({k.split("|")[2] for k in rates if k.split("|")[1] in c["symbols"]})
        L.append(f"\n**{cell}** (`-` = no bars that year)\n")
        L.append("| method | symbol | " + " | ".join(years) + " |")
        L.append("|---|---|" + "---|" * len(years))
        for m in ("ict", "wyckoff"):
            for s in c["symbols"]:
                L.append(f"| {m} | {s} | " + " | ".join(str(rates[f"{m}|{s}|{y}"]["trades"]) if f"{m}|{s}|{y}" in rates else "-"
                                                           for y in years) + " |")
    L.append("\n### T2. Bar counts per symbol-year (full per-month table: `docs/audits/2026-10-02-dev-start-density.json`)\n")
    for cell, c in CELLS.items():
        keys = [f"{s}|{c['tf']}" for s in c["symbols"]]
        years = sorted({m[:4] for k in keys for m in cen[k]["months"]})
        L.append(f"\n**{cell}**; expected bars/weekday (reference {REF_START}..{REF_END}) in the last column\n")
        L.append("| symbol | first bar | " + " | ".join(years) + " | exp/weekday |")
        L.append("|---|---|" + "---|" * (len(years) + 1))
        for s, k in zip(c["symbols"], keys):
            ys = {y: sum(n for m, n in cen[k]["months"].items() if m[:4] == y) for y in years}
            L.append(f"| {s} | {cen[k]['first_bar'][:10]} | " + " | ".join(str(ys[y]) for y in years)
                     + f" | {per_weekday_expected(cen, k):.0f} |")
    L.append("\n### T3. 1m-indices: dense symbols per test fold (dense = bars >= 50 % of expected over the window)\n")
    for start, e in dec["1m-indices"].items():
        d = e["dense"]
        L.append(f"\nCandidate {start} ({e['folds']} folds), need >= {d['need']} of 5 dense in the fold OR its preceding "
                 f"training window [{start}, fold start): **{'PASS' if d['ok'] else 'FAIL'}**\n")
        L.append("| fold | test window | dense in fold | dense in fold or training | ok | dense symbols in fold | dense in training |")
        L.append("|---|---|---|---|---|---|---|")
        for r in d["rows"]:
            L.append(f"| {r['fold']} | {r['start']} .. {r['end']} | {r['dense_in_fold']} | {r['dense_in_fold_or_train']} | "
                     f"{'yes' if r['ok'] else 'NO'} | {' '.join(r['fold_dense_symbols']) or '-'} | "
                     f"{' '.join(r['train_dense_symbols']) or '-'} |")
    L.append(f"\n### T4. P(every test fold >= 30 admitted trades), {REPS} replications, threshold {THRESH}\n")
    L.append("`cell` = the T3-avail convention (rho-0.3 discount with the cell's full k); `present` = discount with the symbols "
             "that have trades in that fold (sensitivity). Both models use the SAME seeds per (cell, start, method, mode).\n")
    L.append("| cell | candidate start | folds | ICT P (cell) | Wyckoff P (cell) | ICT P (present) | Wyckoff P (present) | "
             "both >= 0.80 | dense condition | admissible |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for cell in dec:
        for start, e in dec[cell].items():
            p = e["P"]
            both = all(p[m]["cell"]["p_all"] >= THRESH for m in p)
            dn = "n/a" if e["dense"] is None else ("PASS" if e["dense"]["ok"] else "FAIL")
            L.append(f"| {cell} | {start} | {e['folds']} | {p['ict']['cell']['p_all']:.3f} | {p['wyckoff']['cell']['p_all']:.3f} | "
                     f"{p['ict']['present']['p_all']:.3f} | {p['wyckoff']['present']['p_all']:.3f} | {'yes' if both else 'no'} | "
                     f"{dn} | {'yes' if both and dn != 'FAIL' else 'no'} |")
    L.append("\n### T5. Model-expected pooled trades per fold (primary model, mean of the synthetic folds)\n")
    L.append("| cell | start | method | per fold, oldest first |")
    L.append("|---|---|---|---|")
    for cell in dec:
        for start, e in dec[cell].items():
            for m in ("ict", "wyckoff"):
                L.append(f"| {cell} | {start} | {m} | {' '.join(str(x) for x in e['P'][m]['cell']['mean_per_fold'])} |")
    L.append("\n### T6. Verdict\n")
    for cell in dec:
        v, found = verdict(cell, dec)
        L.append(f"- {cell}: dev_start = **{v}** ({'earliest admissible candidate' if found else 'NO candidate satisfied the rule; the LAST candidate by rule'})")
    open(out, "w").write("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("census")
    a.add_argument("--out", required=True)
    a = sub.add_parser("rates")
    a.add_argument("--results", required=True)
    a.add_argument("--out", required=True)
    a = sub.add_parser("decide")
    a.add_argument("--census", required=True)
    a.add_argument("--rates", required=True)
    a.add_argument("--out", required=True)
    a = sub.add_parser("report")
    a.add_argument("--census", required=True)
    a.add_argument("--rates", required=True)
    a.add_argument("--decision", required=True)
    a.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "report":
        report(a.census, a.rates, a.decision, a.out)
    elif a.cmd == "census":
        census(a.out)
    elif a.cmd == "rates":
        json.dump(build_rates(a.results), open(a.out, "w"), indent=1, sort_keys=True)
    else:
        decide(a.census, a.rates, a.out)


if __name__ == "__main__":
    main()
