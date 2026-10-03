#!/usr/bin/env python3
"""Multi-day holding of the surviving trend rules (docs/plans/2026-10-03-edge-hold-preregistration.md). FTMO allows overnight
holding in the Challenge and Verification (docs/audits/2026-10-03-ftmo-rules-audit.md); the only cost is the swap. Question:
does the trade keep paying AFTER the server day ends, net of swap?

    python3 scripts/research/edge_hold.py run    --out docs/audits/2026-10-03-edge-hold.json
    python3 scripts/research/edge_hold.py report --json docs/audits/2026-10-03-edge-hold.json --out <md>

Unit = the INCREMENT: from the close of the entry day's last bar to the close of the last bar of the k-th following dense server
day (k = 1, 2, 3), in the trade's direction, minus the broker's swap for the nights held (current FTMO-Demo swap points, scaled
by close / price_ref like the spread). The intraday part is already measured (F3 / F4); the increment is what holding adds.
Placebo = the same increment from EVERY dense day's close in the same period, signed by the trade's side."""
import argparse
import collections
import importlib.util
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


F4 = _load("edge_f4", "scripts/research/edge_f4.py")
F3, EC = F4.F3, F4.EC
END = "9999-12-31T00:00:00Z"
FDR_Q, CONFIRM_P, EXPOSED_P = 0.10, 0.05, 0.10
COMPONENTS = {"H7_XAUUSD": ("XAUUSD", F3.ev_breakout_trend), "G9_XAUUSD": ("XAUUSD", F4.ev_vol_breakout),
              "G9_XAGUSD": ("XAGUSD", F4.ev_vol_breakout)}
EXTRA_DAYS = (1, 2, 3)
FAMILY = [(c, k) for c in COMPONENTS for k in EXTRA_DAYS]


def forward_ends(s):
    """{dense server day d: [last index of the 1st, 2nd, 3rd following DENSE server day]} (shorter near the data's end)."""
    days = [(d, rows[-1]) for d, rows in s.day_rows.items() if s.dense[rows[0]]]
    return {d: [x for _d, x in days[j + 1:j + 1 + max(EXTRA_DAYS)]] for j, (d, _x) in enumerate(days)}


def increment(s, ev, k, ends, eod):
    """(entry-day last index, exit index) of the k-day increment for an intraday event, or None."""
    e = ev["entry_i"]
    if e >= len(s.C) or s.sday[e] != s.sday[ev["i"]]:
        return None
    d = s.sday[e]
    nxt = ends.get(d)
    if nxt is None or len(nxt) < k:
        return None
    return eod[e], nxt[k - 1]


def run(out_path):
    import real_costs as RC
    rows = collections.defaultdict(list)
    meta = {}
    for name, (sym, det) in COMPONENTS.items():
        dev = EC.load(sym)
        s = EC.load(sym, end=END)
        s.split_day = dev.split_day
        ref = RC.price_ref(EC.COST_PROFILE, sym)
        eod = F3._eod(s)
        ends = forward_ends(s)
        plc = collections.defaultdict(lambda: [0.0, 0])
        for d, rows_d in s.day_rows.items():
            if not s.dense[rows_d[0]] or d not in ends:
                continue
            a0 = rows_d[-1]
            for k in EXTRA_DAYS:
                if len(ends[d]) >= k:
                    a = plc[(F3.period_of(s, a0), k)]
                    a[0] += s.C[ends[d][k - 1]] / s.C[a0] - 1.0
                    a[1] += 1
        swap_cache = {}
        for ev in det(s):
            sig = s.sigma(ev["i"])
            if not sig:
                continue
            for k in EXTRA_DAYS:
                inc = increment(s, ev, k, ends, eod)
                if inc is None:
                    continue
                a0, x = inc
                side = ev["side"]
                key = (side, s.T[a0], s.T[x])
                if key not in swap_cache:
                    swap_cache[key] = RC.swap_price(EC.COST_PROFILE, sym, "long" if side > 0 else "short", s.T[a0], s.T[x])[0]
                swap_frac = -swap_cache[key] / ref                  # a debit (negative points) is a positive cost
                per = F3.period_of(s, ev["i"])
                base = plc.get((per, k))
                if not base or not base[1]:
                    continue
                r = side * (s.C[x] / s.C[a0] - 1.0)
                rows[(name, k)].append({"symbol": sym, "date": s.dt[ev["i"]].date().isoformat(), "period": per, "side": side,
                                        "r": r, "cost": swap_frac, "cost90": swap_frac, "scale": sig * (x - a0) ** 0.5,
                                        "excess": r - side * base[0] / base[1]})
        meta[name] = {"split_day": str(dev.split_day), "last_bar": s.T[-1]}
        print(f"{name}: {sum(len(rows[(name, k)]) for k in EXTRA_DAYS)} increments", flush=True)
    tests = []
    for key in FAMILY:
        rs = rows.get(key, [])
        tests.append({"component": key[0], "extra_days": key[1],
                      "discovery": EC.summarise([r for r in rs if r["period"] == "discovery"]),
                      "confirmation": EC.summarise([r for r in rs if r["period"] == "confirmation"]),
                      "exposed": EC.summarise([r for r in rs if r["period"] == "exposed"])})
    rej = EC.bh([t["discovery"].get("p_one_sided", 1.0) if t["discovery"].get("n") else 1.0 for t in tests], FDR_Q)
    for k, t in enumerate(tests):
        d, c, x = t["discovery"], t["confirmation"], t["exposed"]
        cand = k in rej and d.get("n", 0) > 0 and d["net_bp"] > 0
        conf = cand and c.get("n", 0) > 0 and c["p_one_sided"] < CONFIRM_P and c["net_bp"] > 0
        surv = conf and x.get("n", 0) > 0 and x["p_one_sided"] < EXPOSED_P and x["net_bp"] > 0
        t["verdict"] = {"bh_rejected": k in rej, "candidate": bool(cand), "confirmed": bool(conf), "survives_exposed": bool(surv)}
    json.dump({"meta": {"script": "scripts/research/edge_hold.py", "family_size": len(FAMILY), "components": meta},
               "tests": tests}, open(out_path, "w"), indent=1, default=str)
    v = [t["verdict"] for t in tests]
    print(f"wrote {out_path}: {sum(x['candidate'] for x in v)} candidates, {sum(x['confirmed'] for x in v)} confirmed, "
          f"{sum(x['survives_exposed'] for x in v)} survive, of {len(tests)}")


def report(json_path, out_path):
    d = json.load(open(json_path))
    f = lambda v, p=3: "n/a" if v is None else f"{v:.{p}f}"
    L = ["| component | +days | disc n | disc p (1s) | BH | disc gross bp | disc swap bp | disc net bp | conf n | conf p | conf net bp | "
         "exp n | exp p | exp net bp | verdict |", "|" + "---|" * 15]
    for t in d["tests"]:
        a, c, x, v = t["discovery"], t["confirmation"], t["exposed"], t["verdict"]
        verdict = ("SURVIVES" if v["survives_exposed"] else "confirmed, fails exposed" if v["confirmed"]
                   else "candidate, not confirmed" if v["candidate"] else "-")
        L.append(f"| {t['component']} | {t['extra_days']} | {a.get('n', 0)} | {f(a.get('p_one_sided'), 4)} | "
                 f"{'yes' if v['bh_rejected'] else 'no'} | {f(a.get('gross_bp'), 2)} | {f(a.get('cost_bp'), 2)} | {f(a.get('net_bp'), 2)} | "
                 f"{c.get('n', 0)} | {f(c.get('p_one_sided'), 4)} | {f(c.get('net_bp'), 2)} | {x.get('n', 0)} | "
                 f"{f(x.get('p_one_sided'), 4)} | {f(x.get('net_bp'), 2)} | {verdict} |")
    open(out_path, "w").write("\n".join(L) + "\n")
    print(f"wrote {out_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("--out", required=True)
    q = sub.add_parser("report"); q.add_argument("--json", required=True); q.add_argument("--out", required=True)
    a = ap.parse_args()
    run(a.out) if a.cmd == "run" else report(a.json, a.out)


if __name__ == "__main__":
    main()
