#!/usr/bin/env python3
"""Empirical check of the Minimum Backtest Length (Bailey, Borwein, Lopez de Prado, Zhu, Notices AMS 2014) on THIS
project's own data: N skill-less random strategies (random entries, random side, fixed 2-hour hold) on the
development window (< 2024-03-01) of one symbol, and the best annualised in-sample Sharpe that luck alone produces,
by years of data and by timeframe. Owner request 2026-09-29: verify old knowledge against our data, do not trust it.

usage: python scripts/research/minbtl_check.py [--symbol XAUUSD] [--n 328] [--reps 5] [--tfs 15m,1H]
"""
import argparse, datetime, json, math, os, random, statistics

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CUTOFF = "2024-03-01"
HOLD_MIN = 120   # the same 2-hour economic horizon on every timeframe
TF_MIN = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1H": 60}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="XAUUSD"); ap.add_argument("--n", type=int, default=328)
    ap.add_argument("--reps", type=int, default=5); ap.add_argument("--tfs", default="15m,1H")
    ap.add_argument("--seed", type=int, default=20260928)
    a = ap.parse_args(); rng = random.Random(a.seed)
    print(f"symbol {a.symbol}, N={a.n} random strategies, {a.reps} random windows per cell, data < {CUTOFF}")
    print("tf    years  maxSR_IS(mean)  Bailey sqrt(2 ln N / y)")
    for tf in a.tfs.split(","):
        c = [x for x in json.load(open(os.path.join(ROOT, "data", "history", f"ohlcv.{a.symbol}.{tf}.json")))["candles"]
             if x["time"] < CUTOFF]
        C = [x["close"] for x in c]
        days = (datetime.date.fromisoformat(c[-1]["time"][:10]) - datetime.date.fromisoformat(c[0]["time"][:10])).days
        per_year = len(c) / (days / 365.25); hold = max(1, HOLD_MIN // TF_MIN[tf])
        for y in (1, 2, 3, 5):
            n = int(per_year * y)
            if n + hold >= len(C):
                print(f"{tf:4} {y:>6}  (not enough history)"); continue
            reps = []
            for _ in range(a.reps):
                start = rng.randrange(0, len(C) - n - hold); best = float("-inf")
                for _k in range(a.n):
                    p = rng.random() * 0.05 + 0.01; rets = []; i = start
                    while i < start + n - hold:
                        if rng.random() < p:
                            s = 1 if rng.random() < 0.5 else -1
                            rets.append(s * (C[i + hold] / C[i] - 1)); i += hold
                        else:
                            i += 1
                    if len(rets) > 10 and statistics.pstdev(rets) > 0:
                        best = max(best, statistics.mean(rets) / statistics.pstdev(rets) * math.sqrt(len(rets) / y))
                reps.append(best)
            print(f"{tf:4} {y:>6}  {statistics.mean(reps):6.2f}          {math.sqrt(2 * math.log(a.n) / y):.2f}")


if __name__ == "__main__":
    main()
