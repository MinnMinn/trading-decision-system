#!/usr/bin/env python3
"""Markdown count tables from the JSONL written by zero_risk_count.py (counts only; identical rows are grouped).

    python3 scripts/research/zero_risk_table.py /tmp/zr-ict.jsonl /tmp/zr-wy.jsonl > table.md
"""
import collections
import json
import sys

CELL = {("1m", "XAUUSD"): "1m-metals", ("1m", "XAGUSD"): "1m-metals", ("5m", "XAUUSD"): "5m-metals",
        ("5m", "XAGUSD"): "5m-metals", ("5m", "XPTUSD"): "5m-metals", ("5m", "XPDUSD"): "5m-metals"}
CATS = ("zero", "wrong_side", "sub_tick", "invalid_price", "bad_planned_r", "non_finite", "negative")


def main(paths):
    rows = []
    for p in paths:
        rows += [json.loads(l) for l in open(p) if l.strip()]
    order = {"1m-metals": 0, "1m-indices": 1, "5m-metals": 2}
    rows.sort(key=lambda r: (r["method"], order.get(CELL.get((r["tf"], r["symbol"]), "1m-indices"), 1), r["symbol"]))
    print("| method | cell | symbol | category | value sets (count of sets) | per-year counts (year: n) | total per set |")
    print("|---|---|---|---|---|---|---|")
    for r in rows:
        cell = CELL.get((r["tf"], r["symbol"]), "1m-indices")
        counts = r["counts"]
        nsets = len(counts)
        found = False
        for cat in CATS:
            groups = collections.defaultdict(list)
            for label, ys in counts.items():
                per = {y: c[cat] for y, c in sorted(ys.items()) if c.get(cat)}
                if per:
                    groups[json.dumps(per)].append(label)
            for per_json, labels in sorted(groups.items(), key=lambda kv: -sum(json.loads(kv[0]).values())):
                per = json.loads(per_json)
                short = ", ".join(labels[:3]) + (f", ... ({len(labels)} sets)" if len(labels) > 3 else f" ({len(labels)})")
                print(f"| {r['method']} | {cell} | {r['symbol']} | {cat} | {short} | "
                      f"{', '.join(f'{y}: {n}' for y, n in per.items())} | {sum(per.values())} |")
                found = True
        if not found:
            print(f"| {r['method']} | {cell} | {r['symbol']} | (none) | all {nsets} sets | 0 in every year | 0 |")


if __name__ == "__main__":
    main(sys.argv[1:])
