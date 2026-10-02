#!/usr/bin/env python3
"""Edge follow-up F2 (docs/plans/2026-10-02-edge-followup-preregistration.md): the census's replicating primitives, per cheap
symbol, with longer holds -- stage (b) on the EXPOSED window [2024-03-01, end of data), stage (a) forward on bars exported after
the pre-registration.

    python3 scripts/research/edge_followup.py run --stage exposed --out docs/audits/2026-10-02-edge-followup-exposed.json
    python3 scripts/research/edge_followup.py run --stage forward --since 2026-09-29T00:00:00Z --out <json>
    python3 scripts/research/edge_followup.py report --json <json> --out <md>

Reuses the census machinery unchanged (scripts/research/edge_census.py: detectors, costs, placebo idea, CR1, BH). What is new:
fixed directions (decided by the census discovery period), per-SYMBOL tests (cost differs ~7x between symbols), horizons 24 / 48
bars and "eod" (exit at the last bar of the entry's server day, i.e. flat before the broker rollover), and a window instead of
the census's 60/40 split. Bars before the window are loaded only for the 20-day volatility history and the previous-day levels."""
import argparse
import collections
import datetime
import importlib.util
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_spec = importlib.util.spec_from_file_location("edge_census", os.path.join(ROOT, "scripts", "research", "edge_census.py"))
EC = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(EC)

EXPOSED_START = "2024-03-01T00:00:00Z"
SYMBOLS = ("XAUUSD", "US30", "DE40", "USTEC", "US500")      # the five cheapest allowlisted CFDs (census meta: cost bp)
#: event -> fixed direction relative to the census detector's own side (+1 = as detected, -1 = reversed), from the census
#: DISCOVERY period (docs/audits/2026-10-02-edge-census.md): E1 continuation (= reversed), E2 fade (= reversed), E5 as detected.
DIRECTION = {"E1_prev_day_sweep_reclaim": -1, "E2_prev_day_acceptance": -1, "E5_fvg_retrace": +1}
HORIZONS = (24, 48, "eod")
FAMILY = [(e, s, h) for e in DIRECTION for s in SYMBOLS for h in HORIZONS]
FDR_Q = 0.10
GATE_P = 0.05


def _eod_index(s):
    """{entry index: last index of its server day}."""
    last = {}
    for d, rows in s.day_rows.items():
        for i in rows:
            last[i] = rows[-1]
    return last


def window_rows(s, events, h, costs, start, end, eod):
    """Outcome rows for events signalled in [start, end), with direction already applied; plus the window placebo."""
    out, skipped = [], collections.Counter()
    for ev in events:
        t = s.T[ev["i"]]
        if not (start <= t < end):
            continue
        ev = dict(ev)
        if h == "eod":
            ev["fixed_exit"] = eod.get(ev["entry_i"])
            if ev["fixed_exit"] is None:
                skipped["end_of_data"] += 1
                continue
        o, why = EC.outcome(s, ev, h if h != "eod" else 1, costs)
        if o is None:
            skipped[why] += 1
            continue
        o["key"] = ("eod" if h == "eod" else o["nb"])
        out.append(o)
    return out, skipped


def placebo(s, start, end, keys, eod):
    """{(tod, key): mean C[x]/O[e]-1} over dense days in [start, end); key = nb (fixed horizon) or 'eod'."""
    acc = collections.defaultdict(lambda: [0.0, 0])
    for e in range(len(s.C)):
        if not s.dense[e] or not (start <= s.T[e] < end):
            continue
        tod = s.dt[e].hour * 60 + s.dt[e].minute
        for k in keys:
            x = eod.get(e) if k == "eod" else e + k - 1
            if x is not None and x < len(s.C) and s.sday[x] == s.sday[e]:
                a = acc[(tod, k)]
                a[0] += s.C[x] / s.O[e] - 1.0
                a[1] += 1
    return {k: v[0] / v[1] for k, v in acc.items() if v[1]}


def run(stage, out_path, since=None):
    # "history" (owner 2026-10-02): REPORT-ONLY per-year stability over every stored year; never a gate (the years were read).
    start = {"exposed": EXPOSED_START, "history": "1990-01-01T00:00:00Z"}.get(stage, since)
    if not start:
        raise SystemExit("--since is required for the forward stage")
    end = "9999-12-31T00:00:00Z"
    tests, skipped_all, meta = [], {}, {}
    for sym in SYMBOLS:
        s = EC.load(sym, end=end)
        costs = EC.Costs(sym)
        eod = _eod_index(s)
        keys = [h for h in HORIZONS]
        plc = placebo(s, start, end, keys, eod)
        meta[sym] = {"first_bar_in_window": next((t for t in s.T if t >= start), None), "last_bar": s.T[-1] if s.T else None}
        for ev_name, direction in DIRECTION.items():
            evs = EC.DETECTORS[ev_name](s)
            for h in HORIZONS:
                rows, sk = window_rows(s, evs, h, costs, start, end, eod)
                kept = []
                for r in rows:
                    base = plc.get((r["tod"], r["key"]))
                    if base is None:
                        sk["no_placebo"] += 1
                        continue
                    r["excess"] = r["r"] - r["side"] * base
                    kept.append(r)
                summ = EC.summarise(kept, direction)
                tests.append({"event": ev_name, "symbol": sym, "h": h, "direction": direction, "stats": summ,
                              "by_year": {y: EC.summarise([r for r in kept if r["date"][:4] == y], direction)
                                          for y in sorted({r["date"][:4] for r in kept})}})
                skipped_all[f"{ev_name}|{sym}|{h}"] = dict(sk)
        print(f"{sym}: window from {meta[sym]['first_bar_in_window']} to {meta[sym]['last_bar']}", flush=True)
    p1 = [t["stats"].get("p_one_sided", 1.0) if t["stats"].get("n") else 1.0 for t in tests]
    rej = EC.bh(p1, FDR_Q)
    for k, t in enumerate(tests):
        st = t["stats"]
        ok = (k in rej and st.get("n", 0) > 0 and st["p_one_sided"] < GATE_P and st["net_bp"] > 0 and st["net_bp_p90"] > 0)
        t["verdict"] = {"bh_rejected": k in rej, "passes_stage": bool(ok) and stage != "history"}
    out = {"meta": {"script": "scripts/research/edge_followup.py", "stage": stage, "window_start": start,
                    "family_size": len(FAMILY), "fdr_q": FDR_Q, "gate_p": GATE_P, "symbols": meta,
                    "directions": DIRECTION, "cost_profile": EC.COST_PROFILE},
           "skipped": skipped_all, "tests": tests}
    with open(out_path, "w") as fh:
        json.dump(out, fh, indent=1, default=str)
    print(f"wrote {out_path}: {sum(t['verdict']['passes_stage'] for t in tests)} of {len(tests)} pass stage {stage}")


def report(json_path, out_path):
    d = json.load(open(json_path))
    f = lambda v, p=3: "n/a" if v is None else f"{v:.{p}f}"
    L = [f"Stage `{d['meta']['stage']}`, window from {d['meta']['window_start']}.", "",
         "| event | symbol | h | dir | n | days | excess z | p (1s) | BH | gross bp | cost bp | net bp | net bp p90 | win % net | pass |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for t in d["tests"]:
        s, v = t["stats"], t["verdict"]
        L.append(f"| {t['event']} | {t['symbol']} | {t['h']} | {'+' if t['direction'] > 0 else '-'} | {s.get('n', 0)} | "
                 f"{s.get('days', 0)} | {f(s.get('excess_z'))} | {f(s.get('p_one_sided'), 4)} | "
                 f"{'yes' if v['bh_rejected'] else 'no'} | {f(s.get('gross_bp'), 2)} | {f(s.get('cost_bp'), 2)} | "
                 f"{f(s.get('net_bp'), 2)} | {f(s.get('net_bp_p90'), 2)} | "
                 f"{f(100 * s['win_rate_net'], 1) if s.get('n') else 'n/a'} | {'PASS' if v['passes_stage'] else '-'} |")
    passed = [t for t in d["tests"] if t["verdict"]["passes_stage"]]
    if passed:
        L += ["", "Per-year (report-only) for the tests that pass:", ""]
        for t in passed:
            yrs = ", ".join(f"{y}: n {v.get('n', 0)}, net {f(v.get('net_bp'), 2)} bp" for y, v in t["by_year"].items())
            L.append(f"- {t['event']} {t['symbol']} h={t['h']}: {yrs}")
    open(out_path, "w").write("\n".join(L) + "\n")
    print(f"wrote {out_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--stage", choices=("exposed", "forward", "history"), required=True)
    r.add_argument("--since")
    r.add_argument("--out", required=True)
    q = sub.add_parser("report")
    q.add_argument("--json", required=True)
    q.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.stage, a.out, a.since)
    else:
        report(a.json, a.out)


if __name__ == "__main__":
    main()
