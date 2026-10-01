#!/usr/bin/env python3
"""Fit of the shard cost model from the raw measurement rows of scripts/research/shard_calibration.py
(docs/audits/2026-10-01-shard-calibration.md). Pure Python (no numpy). COUNTS, SECONDS, BYTES only.

    python3 scripts/research/shard_calibration_fit.py --rows /tmp/b14-resA.jsonl /tmp/b14-resB.jsonl ... [--json OUT]

Model of ONE `scan_many` call over one symbol (what a shard persists), measured in-process on the reference machine:

    seconds = a + bars * ( G300 * g300 + G600 * g600 + S * (n_sets - n_groups) )

`g300` / `g600`: detection groups with the default Wyckoff window / the W6 = 600 window (ICT has no window: all groups are
`g300`), `S` = one more value set INSIDE an existing detection group, `a` = per-call fixed seconds (Wyckoff: the HTF-series
set-up of the W7 target, independent of the bar count). Coefficients are non-negative least squares on RELATIVE error.
"""
import argparse
import itertools
import json
import sys


def solve(A, b):
    """Gaussian elimination with partial pivoting (small dense systems)."""
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-12:
            return None
        M[c], M[p] = M[p], M[c]
        for r in range(c + 1, n):
            f = M[r][c] / M[c][c]
            for k in range(c, n + 1):
                M[r][k] -= f * M[c][k]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (M[i][n] - sum(M[i][k] * x[k] for k in range(i + 1, n))) / M[i][i]
    return x


def lsq(X, y, cols):
    """Weighted (1/y) least squares restricted to the columns `cols`; returns the coefficient list or None."""
    w = [1.0 / v for v in y]
    A = [[sum(w[i] ** 2 * X[i][a] * X[i][b] for i in range(len(y))) for b in cols] for a in cols]
    r = [sum(w[i] ** 2 * X[i][a] * y[i] for i in range(len(y))) for a in cols]
    return solve(A, r)


def nnls(X, y):
    """Best non-negative fit over every column subset (<= 4 columns): the subset with all coefficients >= 0 and the
    smallest weighted residual."""
    k = len(X[0])
    best = None
    live = [j for j in range(k) if any(row[j] for row in X)]       # a column that is zero everywhere is not fitted
    for m in range(1, len(live) + 1):
        for cols in itertools.combinations(live, m):
            c = lsq(X, y, list(cols))
            if c is None or any(v < -1e-9 for v in c):
                continue
            full = [0.0] * k
            for j, v in zip(cols, c):
                full[j] = max(v, 0.0)
            res = sum(((sum(full[j] * X[i][j] for j in range(k)) - y[i]) / y[i]) ** 2 for i in range(len(y)))
            if best is None or res < best[0] - 1e-12:
                best = (res, full)
    return best[1]


def design(r, method):
    """[a, G300, G600, S] columns. ICT has no fixed per-call term (a = 0: ICT's per-call set-up is negligible, and its
    one-group points cannot separate a from G) and no window column."""
    g, n = r["groups"], r["n_sets"]
    g6 = sum(1 for s in r["sets"] if s == "w1:4") if method == "wyckoff" else 0
    return [1.0 if method == "wyckoff" else 0.0, (g - g6) * r["bars"], g6 * r["bars"], (n - g) * r["bars"]]


def predict(c, r, method):
    return sum(a * b for a, b in zip(c, design(r, method)))


def fit_rows(rows, method):
    return nnls([design(r, method) for r in rows], [r["seconds"] for r in rows])


def load(paths):
    rows = []
    for p in paths:
        rows += [json.loads(l) for l in open(p) if l.strip()]
    return [r for r in rows if r.get("status") == "OK"]


def is_s3_xau(r):
    return r["kind"] == "scan" and r["symbol"] == "XAUUSD" and r["slice"] == "S3"


# held-out = the biggest designs (what a real shard looks like); everything else trains the fit
HELD = {"ict": {"C-ict-g1-n26", "C-ict-g2-n27", "D-ict-g1-n26", "D-ict-g2-n27"},
        "wyckoff": {"C-wy-g9-n14", "D-wy-g9-n14"}}


def report(rows):
    out = {"fit": {}, "heldout": [], "position": {}, "index_ratio": {}}
    xau = [r for r in rows if is_s3_xau(r)]
    for method in ("ict", "wyckoff"):
        for tf in ("1m", "5m", "15m"):
            rs = [r for r in xau if r["method"] == method and r["tf"] == tf]
            for r in rs:
                r.setdefault("tag", "A")
            train = [r for r in rs if r["tag"] not in HELD[method]]
            held = [r for r in rs if r["tag"] in HELD[method]]
            if len(train) < 3:
                continue
            c = fit_rows(train, method)
            allc = fit_rows(rs, method)
            out["fit"][f"{method}-{tf}"] = {"train_n": len(train), "train_coef": c, "all_n": len(rs), "all_coef": allc}
            for r in held:
                p = predict(c, r, method)
                rest = [x for x in rs if x is not r]
                loo = predict(fit_rows(rest, method), r, method)        # leave-one-out: every OTHER point trains
                out["heldout"].append({"method": method, "tf": tf, "tag": r["tag"], "groups": r["groups"],
                                       "sets": r["n_sets"], "measured_s": r["seconds"], "predicted_s": round(p, 1),
                                       "error_pct": round(100 * (p - r["seconds"]) / r["seconds"], 1),
                                       "loo_predicted_s": round(loo, 1),
                                       "loo_error_pct": round(100 * (loo - r["seconds"]) / r["seconds"], 1)})
    # position factor: the variable per-bar cost ((seconds - a) / bars) of ONE baseline value set at one-year slices spread over
    # the history (the late slices cost more for Wyckoff: the W7 target reads a growing HTF prefix), averaged over the
    # slices, relative to the S3 slice (the last development year, where every other measurement was taken).
    for method in ("ict", "wyckoff"):
        for tf in ("1m", "5m", "15m"):
            fk = out["fit"].get(f"{method}-{tf}")
            if not fk:
                continue
            a0 = fk["all_coef"][0]
            pts = [r for r in rows if r["kind"] == "scan" and r["symbol"] == "XAUUSD" and r["method"] == method and r["tf"] == tf
                   and r["sets"] == ["base"] and isinstance(r["slice"], list)
                   and r["slice"][1][:4] == str(int(r["slice"][0][:4]) + 1)]                 # one-year slices only
            s3 = [r for r in rows if r["kind"] == "scan" and r["symbol"] == "XAUUSD" and r["method"] == method and r["tf"] == tf
                  and r["slice"] == "S3" and r["n_sets"] == 1 and r["sets"][0] != "w1:4" and r["groups"] == 1]
            if pts and s3:
                var = lambda r: (r["seconds"] - a0) / r["bars"]
                s3v = sum(var(r) for r in s3) / len(s3)
                allv = [var(r) for r in pts] + [s3v]
                out["position"][f"{method}-{tf}"] = {"slices": len(allv), "mean_var_s_per_bar": sum(allv) / len(allv),
                                                     "s3_var_s_per_bar": s3v, "factor_vs_s3": sum(allv) / len(allv) / s3v,
                                                     "slice_var_s_per_bar": [round(v, 7) for v in allv]}
    # indices: seconds per bar of the baseline value set at S3 (US500 for every timeframe, plus US30 at 1m), a-term included
    # (conservative: the indices' own HTF set-up is smaller than the metals'), and its ratio to the metals' S3 baseline
    for method in ("ict", "wyckoff"):
        for tf in ("1m", "5m", "15m"):
            x = [r for r in rows if r["kind"] == "scan" and r["symbol"] == "XAUUSD" and r["method"] == method and r["tf"] == tf
                 and r["slice"] == "S3" and r["n_sets"] == 1 and r["sets"][0] != "w1:4" and r["groups"] == 1]
            ix = [r for r in rows if r["kind"] == "scan" and r["method"] == method and r["tf"] == tf and r["slice"] == "S3"
                  and r["symbol"] in ("US500", "US30") and r["sets"] == ["base"]]
            if x and ix:
                xr = sum(r["seconds"] for r in x) / sum(r["bars"] for r in x)
                ir = sum(r["seconds"] for r in ix) / sum(r["bars"] for r in ix)
                out["index_ratio"][f"{method}-{tf}"] = {"indices_symbols": [r["symbol"] for r in ix], "s_per_bar": ir,
                                                        "metals_s3_s_per_bar": xr, "ratio": ir / xr}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", nargs="+", required=True)
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    res = report(load(a.rows))
    print(json.dumps(res, indent=1))
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(res, fh, indent=1)


if __name__ == "__main__":
    main()
