#!/usr/bin/env python3
"""Edge family AMD (docs/plans/2026-10-03-edge-amd-preregistration.md): the session Power-of-Three -- Asia accumulation,
London manipulation, New York distribution -- operationalised from the repository's own sources ONLY:
knowledge/ict/models.md §2.5.6 (TTrades daily profiles) and knowledge/ict/core-b.md §2.11 (PO3 / AMD). Windows from
docs/architecture/sessions.json (exchange-local, DST-aware): Asia 20:00-24:00 New York (the evening before), London 08:00-11:00
London, New York from 08:30 New York; every trade exits at the last bar before 16:00 New York (intraday, no swap).

    python3 scripts/research/edge_amd.py run    --out docs/audits/2026-10-03-edge-amd.json
    python3 scripts/research/edge_amd.py report --json docs/audits/2026-10-03-edge-amd.json --out <md>

Rules (direction fixed by the source, so every read is one-sided):
  AMD1 London Reversal  -- London takes ONE Asia extreme (not both) and, at the close of the last bar before 08:30 NY, price is
                           back on the other side of the London open: trade the reversal direction into New York (§2.5.6 "If
                           London reverses, then seek New York continuations").
  AMD2 New York Reversal -- London stays inside the Asia range (consolidation): the first NY bar (08:30-11:00) that trades beyond
                           the Asia+London high (low) and CLOSES back inside -> trade the reversal (§2.5.6 "If London
                           consolidates ... seek a New York reversal"; the sweep-and-close-back is core-a §2.14's failure to
                           displace). London EXPANSION days are never traded ("avoid New York participation").
  AMD3 PO3 daily open   -- at the close of the last bar before 08:30 NY: the day's excursion against the side price is now on
                           (below the server-day open for a close above it) is the LARGER excursion -> trade toward the close's
                           side into New York (core-b §2.11: manipulation beyond the open against the eventual direction, then
                           distribution). Parameter-free.
Three reads, each once, as F5 (discovery / confirmation / exposed)."""
import argparse
import collections
import datetime
import importlib.util
import json
import os
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


F5 = _load("edge_f5", "scripts/research/edge_f5.py")
F3, EC = F5.F3, F5.EC
NY, LDN = ZoneInfo("America/New_York"), ZoneInfo("Europe/London")
SYMBOLS = ("XAUUSD", "XAGUSD", "US500", "US30", "USTEC", "DE40", "FRA40", "AUS200")
END = "9999-12-31T00:00:00Z"
FDR_Q, CONFIRM_P, EXPOSED_P = 0.10, 0.05, 0.10
ASIA = (20.0, 24.0)            # New York local, the evening BEFORE the New York date
LONDON = (8.0, 11.0)           # London local
NY_OPEN, NY_AM_END, NY_EXIT = 8.5, 11.0, 16.0     # New York local
RULES = ("AMD1_london_reversal", "AMD2_ny_reversal", "AMD3_po3_open")
FAMILY = [(r, s) for r in RULES for s in SYMBOLS]


def _hour(t, zone):
    lt = t.astimezone(zone)
    return lt.date(), lt.hour + lt.minute / 60.0


def ny_days(s):
    """{New York date D: {'asia': [i], 'london': [i], 'pre': [i before 08:30 NY on D], 'am': [i 08:30-11:00 NY],
    'exit': i of the last bar before 16:00 NY}} for weekdays D."""
    out = collections.defaultdict(lambda: {"asia": [], "london": [], "pre": [], "am": [], "exit": None})
    for i, t in enumerate(s.dt):
        d, h = _hour(t, NY)
        ld, lh = _hour(t, LDN)
        if h >= ASIA[0]:
            nxt = d + datetime.timedelta(days=1)
            out[nxt]["asia"].append(i)
        if LONDON[0] <= lh < LONDON[1]:
            out[ld]["london"].append(i)
        if h < NY_OPEN:
            out[d]["pre"].append(i)
        elif h < NY_AM_END:
            out[d]["am"].append(i)
        if h < NY_EXIT:
            out[d]["exit"] = i
    return {d: v for d, v in out.items() if d.weekday() < 5}


def _ok(s, i_sig, i_entry, x):
    return (i_entry is not None and x is not None and i_sig < i_entry <= x and s.prev_dense[i_entry]
            and s.sday[i_entry] == s.sday[x] == s.sday[i_sig])


def classify(s, v):
    """'reversal_up' | 'reversal_down' | 'expansion' | 'consolidation' | None (incomplete) for one New York date."""
    if not v["asia"] or not v["london"] or not v["pre"]:
        return None
    ah, al = max(s.H[j] for j in v["asia"]), min(s.L[j] for j in v["asia"])
    lh, ll = max(s.H[j] for j in v["london"]), min(s.L[j] for j in v["london"])
    sig = v["pre"][-1]
    if sig < v["london"][0]:
        return None
    up, down = lh > ah, ll < al
    if not up and not down:
        return "consolidation"
    if up and down:
        return "both"
    lo_open = s.O[v["london"][0]]
    if down and s.C[sig] > lo_open:
        return "reversal_up"
    if up and s.C[sig] < lo_open:
        return "reversal_down"
    return "expansion"


def ev_amd1(s, days=None):
    out = []
    for d, v in (days or ny_days(s)).items():
        c = classify(s, v)
        if c in ("reversal_up", "reversal_down") and v["am"]:
            sig, e = v["pre"][-1], v["am"][0]
            if _ok(s, sig, e, v["exit"]):
                out.append(EC._ev(s, sig, 1 if c == "reversal_up" else -1, entry_i=e, fixed_exit=v["exit"]))
    return out


def ev_amd2(s, days=None):
    out = []
    for d, v in (days or ny_days(s)).items():
        if classify(s, v) != "consolidation" or not v["am"]:
            continue
        hi = max(s.H[j] for j in v["asia"] + v["london"])
        lo = min(s.L[j] for j in v["asia"] + v["london"])
        for i in v["am"]:
            side = -1 if (s.H[i] > hi and s.C[i] < hi) else 1 if (s.L[i] < lo and s.C[i] > lo) else 0
            if side:
                if i + 1 < len(s.C) and _ok(s, i, i + 1, v["exit"]):
                    out.append(EC._ev(s, i, side, fixed_exit=v["exit"]))
                break                                  # the first sweep decides the day
    return out


def ev_amd3(s, days=None):
    out = []
    for d, v in (days or ny_days(s)).items():
        if not v["pre"] or not v["am"]:
            continue
        sig, e = v["pre"][-1], v["am"][0]
        rows = [j for j in s.day_rows[s.sday[sig]] if j <= sig]
        o = s.O[rows[0]]
        hi, lo = max(s.H[j] for j in rows), min(s.L[j] for j in rows)
        c = s.C[sig]
        side = 1 if (c > o and o - lo > hi - o) else -1 if (c < o and hi - o > o - lo) else 0
        if side and _ok(s, sig, e, v["exit"]):
            out.append(EC._ev(s, sig, side, entry_i=e, fixed_exit=v["exit"]))
    return out


DETECTORS = {"AMD1_london_reversal": ev_amd1, "AMD2_ny_reversal": ev_amd2, "AMD3_po3_open": ev_amd3}


def run(out_path):
    rows = collections.defaultdict(list)
    meta = {}
    for sym in SYMBOLS:
        dev = EC.load(sym)
        s = EC.load(sym, end=END)
        s.split_day = dev.split_day
        costs = EC.Costs(sym)
        days = ny_days(s)
        exit_of = {}
        for v in days.values():
            if v["exit"] is not None:
                for i in v["pre"] + v["am"]:
                    exit_of[i] = v["exit"]
        plc = collections.defaultdict(lambda: [0.0, 0])           # same period / time of day, to the same 16:00 NY exit
        for e, x in exit_of.items():
            if s.dense[e] and x >= e and s.sday[x] == s.sday[e]:
                a = plc[(F3.period_of(s, e), s.dt[e].hour * 60 + s.dt[e].minute)]
                a[0] += s.C[x] / s.O[e] - 1.0
                a[1] += 1
        counts = collections.Counter(classify(s, v) for v in days.values())
        meta[sym] = {"split_day": str(dev.split_day), "last_bar": s.T[-1], "london_profiles": dict(counts)}
        for rule, det in DETECTORS.items():
            for ev in det(s, days):
                o, _why = EC.outcome(s, ev, 1, costs)
                if o is None:
                    continue
                per = F3.period_of(s, ev["i"])
                base = plc.get((per, o["tod"]))
                if not base or not base[1]:
                    continue
                o["period"] = per
                o["excess"] = o["r"] - o["side"] * base[0] / base[1]
                rows[(rule, sym)].append(o)
        print(f"{sym}: split {dev.split_day}; profiles {dict(counts)}", flush=True)
    tests = []
    for key in FAMILY:
        rs = rows.get(key, [])
        tests.append({"rule": key[0], "symbol": key[1],
                      "discovery": EC.summarise([r for r in rs if r["period"] == "discovery"]),
                      "confirmation": EC.summarise([r for r in rs if r["period"] == "confirmation"]),
                      "exposed": EC.summarise([r for r in rs if r["period"] == "exposed"])})
    rej = EC.bh([t["discovery"].get("p_one_sided", 1.0) if t["discovery"].get("n") else 1.0 for t in tests], FDR_Q)
    for k, t in enumerate(tests):
        d, c, x = t["discovery"], t["confirmation"], t["exposed"]
        cand = k in rej and d.get("n", 0) > 0 and d["net_bp"] > 0
        conf = cand and c.get("n", 0) > 0 and c["p_one_sided"] < CONFIRM_P and c["net_bp"] > 0 and c["net_bp_p90"] > 0
        surv = conf and x.get("n", 0) > 0 and x["p_one_sided"] < EXPOSED_P and x["net_bp"] > 0
        t["verdict"] = {"bh_rejected": k in rej, "candidate": bool(cand), "confirmed": bool(conf), "survives_exposed": bool(surv)}
    json.dump({"meta": {"script": "scripts/research/edge_amd.py", "family_size": len(FAMILY), "symbols": meta}, "tests": tests},
              open(out_path, "w"), indent=1, default=str)
    v = [t["verdict"] for t in tests]
    print(f"wrote {out_path}: {sum(x['candidate'] for x in v)} candidates, {sum(x['confirmed'] for x in v)} confirmed, "
          f"{sum(x['survives_exposed'] for x in v)} survive, of {len(tests)}")


def report(json_path, out_path):
    d = json.load(open(json_path))
    f = lambda v, p=3: "n/a" if v is None else f"{v:.{p}f}"
    L = ["| rule | symbol | disc n | disc p (1s) | BH | disc net bp | conf n | conf p (1s) | conf net bp | conf p90 | exp n | "
         "exp p (1s) | exp net bp | verdict |", "|" + "---|" * 14]
    for t in d["tests"]:
        a, c, x, v = t["discovery"], t["confirmation"], t["exposed"], t["verdict"]
        verdict = ("SURVIVES" if v["survives_exposed"] else "confirmed, fails exposed" if v["confirmed"]
                   else "candidate, not confirmed" if v["candidate"] else "-")
        L.append(f"| {t['rule']} | {t['symbol']} | {a.get('n', 0)} | {f(a.get('p_one_sided'), 4)} | "
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
