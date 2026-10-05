#!/usr/bin/env python3
"""How OFTEN does a trade lose more than its planned 1 % of the balance? (DESCRIPTIVE, post hoc, on already-read trade
sequences; decides nothing.) Asked for by the session "Khám phá hệ thống FTMO" (2026-10-04) so that the owner can choose a gap
tolerance as "once every N years" rather than from one extreme trade (docs/audits/2026-10-03-vol-schedule.md,
docs/audits/2026-10-04-a3-silver.json).

    python3 scripts/research/gap_tail_counts.py --out docs/audits/2026-10-04-gap-tail-counts.json

Loss in % of the balance = -1 % x R (1 % at the stop, no throttle: the dd3 throttle only ever makes it smaller). A stop exit
costs a hair more than 1 % (half the spread), so "> 1 %" counts every stop exit; "> 1.05 %" and above count real gaps."""
import argparse
import datetime
import importlib.util
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


BS = _load("book_sim", "scripts/research/book_sim.py")
THRESHOLDS = (1.0, 1.05, 1.2, 1.5, 2.0)          # % of the balance
CASES = {
    "v3 (H7+G9 gold, k=2.0)": [("H7_XAUUSD_eod", 2.0), ("G9_XAUUSD_eod", 2.0)],
    "A1 k=1.4 (H7+G9 gold)": [("H7_XAUUSD_eod", 1.4), ("G9_XAUUSD_eod", 1.4)],
    "A1 k=1.0 (H7+G9 gold)": [("H7_XAUUSD_eod", 1.0), ("G9_XAUUSD_eod", 1.0)],
    "A3 silver alone (G9 XAGUSD, k=2.0)": [("G9_XAGUSD_eod", 2.0)],
    "A3 v3 + G9 XAGUSD (k=2.0)": [("H7_XAUUSD_eod", 2.0), ("G9_XAUUSD_eod", 2.0), ("G9_XAGUSD_eod", 2.0)],
}


def years(rows):
    a = datetime.datetime.fromisoformat(min(t["entry_time"] for t in rows).replace("Z", "+00:00"))
    b = datetime.datetime.fromisoformat(max(t["entry_time"] for t in rows).replace("Z", "+00:00"))
    return (b - a).days / 365.25


def tail(rows):
    yrs = years(rows)
    out = {"trades": len(rows), "years": round(yrs, 1)}
    for th in THRESHOLDS:
        n = sum(1 for t in rows if -t["R"] > th + 1e-12)
        out[f"loss_gt_{th}pct"] = {"n": n, "share": n / len(rows), "per_year": n / yrs,
                                   "once_every_years": (yrs / n) if n else None}
    worst = sorted(rows, key=lambda t: t["R"])[:5]
    out["worst5"] = [{"entry_time": t["entry_time"], "loss_pct": round(-t["R"], 3)} for t in worst]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    cache, res = {}, {"meta": {"script": "scripts/research/gap_tail_counts.py", "status": "DESCRIPTIVE, post hoc",
                               "loss_unit": "% of the balance at 1 % risk at the stop, unthrottled"}, "cases": {}}
    for name, comps in CASES.items():
        rows = []
        for c, k in comps:
            if (c, k) not in cache:
                cache[(c, k)] = BS.trades(*BS.COMPONENTS[c], stop_k=k)
            rows += cache[(c, k)]
        res["cases"][name] = tail(rows)
        r = res["cases"][name]
        print(name, r["trades"], "trades,", r["years"], "yr |",
              " | ".join(f">{th}%: {r[f'loss_gt_{th}pct']['n']} (1 per "
                         f"{'-' if not r[f'loss_gt_{th}pct']['once_every_years'] else round(r[f'loss_gt_{th}pct']['once_every_years'], 1)} yr)"
                         for th in THRESHOLDS))
    json.dump(res, open(a.out, "w"), indent=1)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
