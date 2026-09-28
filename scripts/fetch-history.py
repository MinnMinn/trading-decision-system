#!/usr/bin/env python3
"""Paginated Binance public klines for backtests: data/history/ohlcv.<SYM>.<TF>.json (same shape as the live files).

Usage: fetch-history.py <SYMBOL> <TF> <BARS>      TF in 1W 1D 4H 2H 1H 30m 15m 5m 1m; BARS up to ~20000 (1000 per request)
Separate directory from data/live/market-data on purpose: the launchd scanner is the single writer there
(SYSTEM-DESIGN §13 rule 3); history files are research inputs only. Public endpoint, no key.
"""
import json, os, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys as _sys; _sys.path.insert(0, os.path.join(ROOT, "scripts"))  # importable when loaded by path from anywhere
from repo_paths import repo_rel
INTERVAL = {"1W": "1w", "1D": "1d", "4H": "4h", "2H": "2h", "1H": "1h", "30m": "30m", "15m": "15m", "5m": "5m", "1m": "1m"}
MS = {"1W": 604800000, "1D": 86400000, "4H": 14400000, "2H": 7200000, "1H": 3600000, "30m": 1800000, "15m": 900000, "5m": 300000, "1m": 60000}


def main():
    sym, tf, bars = sys.argv[1], sys.argv[2], int(sys.argv[3])
    out = []
    end = None
    while len(out) < bars:
        limit = min(1000, bars - len(out))
        url = f"https://api.binance.com/api/v3/klines?symbol={sym}&interval={INTERVAL[tf]}&limit={limit}" + (f"&endTime={end}" if end else "")
        with urllib.request.urlopen(url, timeout=20) as r:
            rows = json.load(r)
        if not rows:
            break
        out = rows + out
        end = rows[0][0] - 1
        if len(rows) < limit:
            break
        time.sleep(0.25)
    candles = [{"time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(r[0] / 1000)), "open": float(r[1]), "high": float(r[2]),
                "low": float(r[3]), "close": float(r[4]), "volume": float(r[5])} for r in out]
    os.makedirs(f"{ROOT}/data/history", exist_ok=True)
    path = f"{ROOT}/data/history/ohlcv.{sym}.{tf}.json"
    json.dump({"symbol": sym, "timeframe": tf, "candles": candles, "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "_source": "binance_public_rest_history"}, open(path, "w"))
    print(f"{sym} {tf}: {len(candles)} candles {candles[0]['time']} .. {candles[-1]['time']} -> {repo_rel(path, ROOT)}")


if __name__ == "__main__":
    main()
