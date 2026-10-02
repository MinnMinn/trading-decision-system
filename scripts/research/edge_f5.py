#!/usr/bin/env python3
"""Edge family F5 (docs/plans/2026-10-02-edge-f5-preregistration.md): TRANSFER of the three rule types that survived F2-F4 (E5
FVG retrace, H7 breakout with trend, G9 volatility breakout) to the nine RESEARCH-ONLY symbols, whose returns no edge family has
read. Direction is fixed in advance (+1 = the rule's own sign), so every read is one-sided. Three reads, each once: discovery
(first 60 % of dense development days < 2024-03-01), confirmation (last 40 %), holdout (2024-03-01 -> end of data).

    python3 scripts/research/edge_f5.py run    --out docs/audits/2026-10-02-edge-f5.json
    python3 scripts/research/edge_f5.py report --json docs/audits/2026-10-02-edge-f5.json --out <md>"""
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
METALS = ("XPTUSD", "XPDUSD")
INDICES = ("JP225", "HK50", "UK100", "EU50", "US2000", "SPN35", "N25")
SYMBOLS = METALS + INDICES
END = "9999-12-31T00:00:00Z"
FDR_Q, CONFIRM_P, HOLDOUT_P = 0.10, 0.05, 0.10
DETECTORS = {"E5": EC.ev_fvg, "H7": F3.ev_breakout_trend, "G9": F4.ev_vol_breakout}


def hold_of(rule, sym):
    """E5 keeps its surviving holds (metals 24 bars as XAUUSD, indices 48 as US500); H7 / G9 to the end of the server day."""
    if rule == "E5":
        return 24 if sym in METALS else 48
    return "eod"


FAMILY = [(r, s, hold_of(r, s)) for r in DETECTORS for s in SYMBOLS]


def run(out_path):
    rows = collections.defaultdict(list)
    meta = {}
    for sym in SYMBOLS:
        dev = EC.load(sym)
        s = EC.load(sym, end=END)
        s.split_day = dev.split_day
        costs = EC.Costs(sym)
        eod = F3._eod(s)
        holds = {hold_of(r, sym) for r in DETECTORS}
        plc = collections.defaultdict(lambda: [0.0, 0])
        for e in range(len(s.C)):
            if not s.dense[e]:
                continue
            per, tod = F3.period_of(s, e), s.dt[e].hour * 60 + s.dt[e].minute
            for k in holds:
                x = eod[e] if k == "eod" else e + k - 1
                if x < len(s.C) and s.sday[x] == s.sday[e]:
                    a = plc[(per, tod, k)]
                    a[0] += s.C[x] / s.O[e] - 1.0
                    a[1] += 1
        meta[sym] = {"split_day": str(dev.split_day), "last_bar": s.T[-1], "dense_days": len(s.dense_days)}
        for rule, det in DETECTORS.items():
            hold = hold_of(rule, sym)
            for ev in det(s):
                ev = dict(ev)
                if ev["entry_i"] >= len(s.C) or s.sday[ev["entry_i"]] != s.sday[ev["i"]]:
                    continue                                          # no same-day trade after a last-bar signal
                if hold == "eod":
                    ev["fixed_exit"] = eod[ev["entry_i"]]
                o, _why = EC.outcome(s, ev, hold if hold != "eod" else 1, costs)
                if o is None:
                    continue
                per = F3.period_of(s, ev["i"])
                base = plc.get((per, o["tod"], hold))
                if not base or not base[1]:
                    continue
                o["period"] = per
                o["excess"] = o["r"] - o["side"] * base[0] / base[1]
                rows[(rule, sym, hold)].append(o)
        print(f"{sym}: split {dev.split_day}, last bar {s.T[-1]}", flush=True)
    tests = []
    for key in FAMILY:
        rs = rows.get(key, [])
        tests.append({"rule": key[0], "symbol": key[1], "hold": key[2],
                      "discovery": EC.summarise([r for r in rs if r["period"] == "discovery"]),
                      "confirmation": EC.summarise([r for r in rs if r["period"] == "confirmation"]),
                      "holdout": EC.summarise([r for r in rs if r["period"] == "exposed"])})
    rej = EC.bh([t["discovery"].get("p_one_sided", 1.0) if t["discovery"].get("n") else 1.0 for t in tests], FDR_Q)
    for k, t in enumerate(tests):
        d, c, x = t["discovery"], t["confirmation"], t["holdout"]
        cand = k in rej and d.get("n", 0) > 0 and d["net_bp"] > 0
        conf = cand and c.get("n", 0) > 0 and c["p_one_sided"] < CONFIRM_P and c["net_bp"] > 0 and c["net_bp_p90"] > 0
        surv = conf and x.get("n", 0) > 0 and x["p_one_sided"] < HOLDOUT_P and x["net_bp"] > 0
        t["verdict"] = {"bh_rejected": k in rej, "candidate": bool(cand), "confirmed": bool(conf), "survives_holdout": bool(surv)}
    json.dump({"meta": {"script": "scripts/research/edge_f5.py", "family_size": len(FAMILY), "symbols": meta}, "tests": tests},
              open(out_path, "w"), indent=1, default=str)
    v = [t["verdict"] for t in tests]
    print(f"wrote {out_path}: {sum(x['candidate'] for x in v)} candidates, {sum(x['confirmed'] for x in v)} confirmed, "
          f"{sum(x['survives_holdout'] for x in v)} survive, of {len(tests)}")


def report(json_path, out_path):
    d = json.load(open(json_path))
    f = lambda v, p=3: "n/a" if v is None else f"{v:.{p}f}"
    L = ["| rule | symbol | hold | disc n | disc p (1s) | BH | disc net bp | conf n | conf p (1s) | conf net bp | conf p90 | "
         "hold n | hold p (1s) | hold net bp | verdict |", "|" + "---|" * 15]
    for t in d["tests"]:
        a, c, x, v = t["discovery"], t["confirmation"], t["holdout"], t["verdict"]
        verdict = ("SURVIVES" if v["survives_holdout"] else "confirmed, fails holdout" if v["confirmed"]
                   else "candidate, not confirmed" if v["candidate"] else "-")
        L.append(f"| {t['rule']} | {t['symbol']} | {t['hold']} | {a.get('n', 0)} | {f(a.get('p_one_sided'), 4)} | "
                 f"{'yes' if v['bh_rejected'] else 'no'} | {f(a.get('net_bp'), 2)} | {c.get('n', 0)} | {f(c.get('p_one_sided'), 4)} | "
                 f"{f(c.get('net_bp'), 2)} | {f(c.get('net_bp_p90'), 2)} | {x.get('n', 0)} | {f(x.get('p_one_sided'), 4)} | "
                 f"{f(x.get('net_bp'), 2)} | {verdict} |")
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
