#!/usr/bin/env python3
"""M4 (red-team 2026-10-02): a COUNTS-ONLY census of the bars the declared fund cells read -- flat bars (open == high == low ==
close), zero-volume bars, and gaps longer than 4 days between consecutive bars -- per symbol, timeframe and year, over the
development span (bars before FS.DEV_CUTOFF). Why: a flat bar is the sweep extreme / first FVG candle that produced the
zero-risk candidates (docs/audits/2026-10-01-zero-risk.md), and a gap in the series is a place where `walk()` and the
flat-before-rollover rule act on a price jump the engine cannot see in between.

Reads data/history/ftmo year parts one at a time (never a whole 1m series in memory). No price, return, R, expectancy or
win rate is computed or printed: only counts.

  python3 scripts/research/engine_realism_census.py [--out docs/audits/2026-10-02-engine-realism-census.md]
"""
import argparse
import datetime
import gzip
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import fund_stats as FS  # noqa: E402

HIST = os.path.join(ROOT, "data", "history", "ftmo")
GAP_DAYS = 4


def _ts(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))


def census(sym, tf, cutoff):
    """{year: {"bars", "flat", "zero_volume", "gaps_gt_4d", "max_gap_days"}} over bars before `cutoff`. A gap is credited to
    the year of the bar that ENDS it."""
    d = os.path.join(HIST, f"ohlcv.{sym}.{tf}")
    with open(os.path.join(d, "index.json"), encoding="utf-8") as fh:
        years = sorted(json.load(fh)["years"])
    out, prev = {}, None
    for y in years:
        if f"{y}-01-01T00:00:00Z" >= cutoff:
            break
        with gzip.open(os.path.join(d, f"{y}.json.gz"), "rt", encoding="utf-8") as fh:
            candles = json.load(fh)["candles"]
        for c in candles:
            if c["time"] >= cutoff:
                break
            t = _ts(c["time"])
            row = out.setdefault(c["time"][:4], {"bars": 0, "flat": 0, "zero_volume": 0, "gaps_gt_4d": 0, "max_gap_days": 0.0})
            row["bars"] += 1
            if c["open"] == c["high"] == c["low"] == c["close"]:
                row["flat"] += 1
            if not c.get("volume"):
                row["zero_volume"] += 1
            if prev is not None:
                gap = (t - prev).total_seconds() / 86400.0
                if gap > GAP_DAYS:
                    row["gaps_gt_4d"] += 1
                row["max_gap_days"] = max(row["max_gap_days"], round(gap, 2))
            prev = t
    return out


def declared_pairs():
    spec = json.load(open(os.path.join(ROOT, "docs", "architecture", "fund-search-cells.json"), encoding="utf-8"))
    pairs = []
    for c in spec["cells"]:
        for s in c["symbols"]:
            if (s, c["timeframe"]) not in pairs:
                pairs.append((s, c["timeframe"]))
    return pairs, [c["id"] for c in spec["cells"]]


def render(results, cells):
    L = ["# Engine-realism census (counts only), 2026-10-02", "",
         "Scope: the symbols and decision timeframes of the declared cells (" + ", ".join(cells) + "), bars BEFORE the "
         f"development cutoff {FS.DEV_CUTOFF}, read from `data/history/ftmo` by `scripts/research/engine_realism_census.py`. "
         "Counts only: no price, return, R, expectancy or win rate appears here.", "",
         "Definitions: **flat** = open == high == low == close; **zero-vol** = `volume` is 0 or absent; **gap > 4d** = two "
         "consecutive bars more than 4 days apart (credited to the year of the bar that ends the gap; the weekend is ~2 days, "
         "so a count here is a holiday closure or a hole in the series).", ""]
    for metric, title in (("flat", "Flat bars (O == H == L == C)"), ("zero_volume", "Zero-volume bars"),
                          ("gaps_gt_4d", "Gaps longer than 4 days"), ("bars", "Bars (denominator)")):
        years = sorted({y for r in results.values() for y in r})
        L += [f"## {title}", "", "| symbol | tf | total | " + " | ".join(years) + " |",
              "|---|---|---:|" + "---:|" * len(years)]
        for (s, tf), r in results.items():
            tot = sum(v[metric] for v in r.values())
            L.append(f"| {s} | {tf} | {tot} | " + " | ".join(str(r[y][metric]) if y in r else "" for y in years) + " |")
        L.append("")
    L += ["## Largest gap per symbol and timeframe (days)", "", "| symbol | tf | max gap (d) | year |", "|---|---|---:|---|"]
    for (s, tf), r in results.items():
        y, v = max(((y, v["max_gap_days"]) for y, v in r.items()), key=lambda x: x[1])
        L.append(f"| {s} | {tf} | {v} | {y} |")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    pairs, cells = declared_pairs()
    results = {}
    for s, tf in pairs:
        results[(s, tf)] = census(s, tf, FS.DEV_CUTOFF)
        print(f"census {s} {tf}: {sum(v['bars'] for v in results[(s, tf)].values())} bars", file=sys.stderr, flush=True)
    md = render(results, cells)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(md)
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
