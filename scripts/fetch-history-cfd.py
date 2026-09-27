#!/usr/bin/env python3
"""Research-only history for the CFD instruments, from Yahoo Finance's public chart endpoint (no key), into
data/history/ohlcv.<SYM>.<TF>.json with the same shape as the Binance history files.

Why: the MT5 EA exports 300 bars per timeframe (docs/architecture/mt5-bridge.md), far too few to rank setups over years.
Mapping (futures front-month continuous, NOT the CFD itself):  XAUUSD -> GC=F  XAGUSD -> SI=F  USOIL -> CL=F  UKOIL -> BZ=F
Differences to state in every report built on this: exchange session hours (not 24/5 CFD quotes), real contract volume
(the MT5 bridge gives tick volume), roll gaps, and prices in futures terms (basis to spot). Yahoo serves 1h bars for ~730 days
and daily bars for years; 2H and 4H are aggregated here from 1H on UTC boundaries (a session gap simply shortens a bar).

Usage: fetch-history-cfd.py [XAUUSD XAGUSD USOIL UKOIL]
"""
import json, os, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from repo_paths import repo_rel
# Symbol -> Yahoo ticker. This is a PROVIDER mapping, not an allowlist copy: the four keys happen to be the
# cfd list today, but the values are Yahoo's own contract codes and only Yahoo can say what they are. A symbol
# with no entry is refused below rather than guessed -- fetching the wrong contract would write plausible,
# wrong history into the research store.
MAP = {"XAUUSD": "GC=F", "XAGUSD": "SI=F", "USOIL": "CL=F", "UKOIL": "BZ=F"}
UA = {"User-Agent": "Mozilla/5.0"}


def yahoo(ticker, interval, rng):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval={interval}&range={rng}"
    d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30))["chart"]["result"][0]
    q = d["indicators"]["quote"][0]; out = []
    for i, ts in enumerate(d["timestamp"]):
        if q["open"][i] is None or q["close"][i] is None:
            continue
        out.append(dict(time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)), open=float(q["open"][i]), high=float(q["high"][i]),
                        low=float(q["low"][i]), close=float(q["close"][i]), volume=float(q["volume"][i] or 0)))
    return out


def aggregate(c1h, hours):
    """Group 1H bars into `hours`-hour UTC buckets."""
    out = {}
    for x in c1h:
        t = time.strptime(x["time"], "%Y-%m-%dT%H:%M:%SZ")
        key = time.strftime("%Y-%m-%dT%H:00:00Z", time.gmtime(time.mktime(t) - time.timezone - (t.tm_hour % hours) * 3600)) if False else \
            f"{x['time'][:11]}{(t.tm_hour // hours) * hours:02d}:00:00Z"
        b = out.get(key)
        if b is None:
            out[key] = dict(time=key, open=x["open"], high=x["high"], low=x["low"], close=x["close"], volume=x["volume"])
        else:
            b["high"] = max(b["high"], x["high"]); b["low"] = min(b["low"], x["low"]); b["close"] = x["close"]; b["volume"] += x["volume"]
    return [out[k] for k in sorted(out)]


def save(sym, tf, candles):
    os.makedirs(f"{ROOT}/data/history", exist_ok=True)
    p = f"{ROOT}/data/history/ohlcv.{sym}.{tf}.json"
    json.dump(dict(symbol=sym, timeframe=tf, candles=candles, last_updated=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   _source=f"yahoo_finance_{MAP[sym]}_research_only"), open(p, "w"))
    print(f"{sym} {tf}: {len(candles)} candles {candles[0]['time'][:10]} .. {candles[-1]['time'][:10]} -> {repo_rel(p, ROOT)}")


def main():
    syms = sys.argv[1:] or list(MAP)
    unmapped = [s for s in syms if s not in MAP]
    if unmapped:
        sys.exit(f"no Yahoo ticker known for {', '.join(unmapped)} -- add it to MAP in this file. "
                 f"Refusing rather than guessing a contract code.")
    for sym in syms:
        c1h = yahoo(MAP[sym], "1h", "730d")
        save(sym, "1H", c1h); save(sym, "2H", aggregate(c1h, 2)); save(sym, "4H", aggregate(c1h, 4))
        save(sym, "1D", yahoo(MAP[sym], "1d", "10y"))
        time.sleep(1)


if __name__ == "__main__":
    main()
