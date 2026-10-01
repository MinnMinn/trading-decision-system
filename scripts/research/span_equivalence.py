#!/usr/bin/env python3
"""Equivalence proof for a cell's declared history start (docs/architecture/fund-search-cells.json `dev_start`).

For one (method, symbol, timeframe, dev_start) it runs the harness's own BtEngine (scripts/fund-search.py) TWICE on the
baseline value set: once over the whole PIT-truncated series (no cut), once with `dev_start` (the decision series
starts `warmup_days` + the method's window before it, trades entered before dev_start are dropped), and compares the
admitted trades with entry >= dev_start field by field (sha256 of the canonical JSON of the trade lists). It reads,
prints and stores ONLY counts, timestamps and hashes -- never R or any performance figure. Evaluates nothing, selects
nothing, writes nothing inside the checkout.

    BT_HISTORY_ROOT=data/history/ftmo python3 scripts/research/span_equivalence.py \\
        --method ict --symbol US500 --tf 5m --dev-start 2021-03-01T00:00:00Z [--warmup-days 14]
"""
import argparse
import hashlib
import importlib.util
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def _fs():
    spec = importlib.util.spec_from_file_location("fund_search", os.path.join(ROOT, "scripts", "fund-search.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fund_search"] = mod
    spec.loader.exec_module(mod)
    return mod


#: Fields of a simulated trade that depend on WHERE the series starts, not on the market: `exit` is the exit bar's INDEX
#: into the loaded series (shifted by the cut), `pnl` is dollars on the simulated account that compounds from the first
#: trade of the run (START equity). Neither is read by the fund statistics (they use `net_R` and the time labels); every
#: other field, including `adx14` and `net_R`, must be byte-identical.
START_DEPENDENT = ("exit", "pnl")


def sha(trades, drop=()):
    rows = [{k: v for k, v in t.items() if k not in drop} for t in trades]
    return hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()


def _key(t):
    return (t["entry_time"], t["symbol"], t["side"])


def run(method, symbol, tf, dev_start, warmup_days):
    os.environ.setdefault("BT_HISTORY_ROOT", os.path.join(ROOT, "data", "history", "ftmo"))
    fs = _fs()
    grids, _ = fs.load_grids()
    grid = grids[method].runnable()
    runner = fs.METHODS[method]
    t0 = time.time()
    full_engine = fs.BtEngine(grid, runner, tf, [symbol], workers=1)
    full_all = full_engine.trades_for(grid.baseline())
    t_full = time.time() - t0
    t0 = time.time()
    cut_engine = fs.BtEngine(grid, runner, tf, [symbol], workers=1, dev_start=dev_start, warmup_days=warmup_days)
    cut = cut_engine.trades_for(grid.baseline())
    t_cut = time.time() - t0
    ds = fs.FS.ts(dev_start)
    full = [t for t in full_all if fs.FS.ts(t["entry_time"]) >= ds]
    kf, kc = {_key(t): t for t in full}, {_key(t): t for t in cut}
    only_full = sorted(set(kf) - set(kc))
    only_cut = sorted(set(kc) - set(kf))
    differing = sorted(k for k in set(kf) & set(kc)
                       if any(kf[k][f] != kc[k].get(f) for f in kf[k] if f not in START_DEPENDENT))
    n_pre = sum(1 for t in cut if fs.FS.ts(t["entry_time"]) < ds)
    first_bad = min(only_full + only_cut + differing, default=None, key=lambda k: k[0])
    return {"method": method, "symbol": symbol, "tf": tf, "dev_start": dev_start, "warmup_days": warmup_days,
            "series_bars_full": full_engine._series[symbol]["bars"], "series_bars_cut": cut_engine._series[symbol]["bars"],
            "span": cut_engine.span, "trades_full_series_total": len(full_all),
            "trades_full_series_from_dev_start": len(full), "trades_cut_run": len(cut),
            "cut_trades_with_entry_before_dev_start": n_pre,
            "sha256_full_from_dev_start_all_fields": sha(full), "sha256_cut_run_all_fields": sha(cut),
            "identical_all_fields": sha(full) == sha(cut),
            "start_dependent_fields_excluded": list(START_DEPENDENT),
            "sha256_full_from_dev_start": sha(full, START_DEPENDENT), "sha256_cut_run": sha(cut, START_DEPENDENT),
            "identical": sha(full, START_DEPENDENT) == sha(cut, START_DEPENDENT),
            "only_in_full": len(only_full), "only_in_cut": len(only_cut), "same_key_different_fields": len(differing),
            "first_difference_entry": first_bad[0] if first_bad else None,
            "first_difference_days_after_dev_start": (round((fs.FS.ts(first_bad[0]) - ds).total_seconds() / 86400, 3)
                                                      if first_bad else None),
            "differing_fields_outside_start_dependent": sorted({f for k in differing for f in kf[k]
                                                                if f not in START_DEPENDENT and kf[k][f] != kc[k].get(f)}),
            "differing_fields_all": sorted({f for k in set(kf) & set(kc) for f in kf[k] if kf[k][f] != kc[k].get(f)}),
            "seconds_full": round(t_full), "seconds_cut": round(t_cut)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", required=True, choices=("ict", "wyckoff"))
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--tf", required=True)
    ap.add_argument("--dev-start", required=True)
    ap.add_argument("--warmup-days", type=int, default=14)
    a = ap.parse_args(argv)
    print(json.dumps(run(a.method, a.symbol, a.tf, a.dev_start, a.warmup_days), indent=1))


if __name__ == "__main__":
    main()
