#!/usr/bin/env python3
"""Edge family F3 (docs/plans/2026-10-02-edge-f3-preregistration.md): new low-parameter hypotheses on the five cheapest
allowlisted CFDs, judged in three reads -- discovery (first 60 % of dense development days), confirmation (last 40 %), and the
exposed window (2024-03-01 -> end of data) -- each read once.

    python3 scripts/research/edge_f3.py run    --out docs/audits/2026-10-02-edge-f3.json
    python3 scripts/research/edge_f3.py report --json docs/audits/2026-10-02-edge-f3.json --out <md>

Machinery reused unchanged from scripts/research/edge_census.py (Series, Costs, outcome, CR1, BH, summarise). All trades are
intraday (flat before the broker rollover: no swap)."""
import argparse
import collections
import importlib.util
import json
import math
import os
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_spec = importlib.util.spec_from_file_location("edge_census", os.path.join(ROOT, "scripts", "research", "edge_census.py"))
EC = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(EC)

SYMBOLS = ("XAUUSD", "US30", "DE40", "USTEC", "US500")
EXPOSED_START = "2024-03-01T00:00:00Z"
END = "9999-12-31T00:00:00Z"
FDR_Q, CONFIRM_P, EXPOSED_P = 0.10, 0.05, 0.10
MOM_DAYS, SHOCK_SD, SHOCK_DAYS = 20, 2.0, 20
MR_BARS, MR_SIGMA = 12, 3.0
REGIME_DAYS = 250

HYPOTHESES = {
    "H1_daily_momentum": "sign of the previous 20 dense days' close-to-close return; trade it from the first bar of the server "
                         "day to the last (intraday, no swap)",
    "H2_daily_shock_reversal": "previous day's return beyond 2 x its 20-day SD: trade the OPPOSITE sign over the next server day",
    "H3_hour_shock_fade": "a 12-bar (1 h) return beyond 3 x sigma_5m x sqrt(12): fade it (first per day per side)",
    "H5_fvg_high_vol": "E5 FVG retrace (census definition) only when the day's sigma_5m is above the median of the previous 250 "
                       "dense days' sigma; continuation",
    "H7_breakout_with_trend": "first close beyond the previous day's high (low) when the 20-day momentum has the same sign; hold "
                              "to the end of the server day",
}
#: (hypothesis, hold) -- hold "eod" = last bar of the entry's server day; ints = bars
HOLDS = {"H1_daily_momentum": ("eod",), "H2_daily_shock_reversal": ("eod",), "H3_hour_shock_fade": (12, 24),
         "H5_fvg_high_vol": (24,), "H7_breakout_with_trend": ("eod",)}
FAMILY = [(h, s, hold) for h in HYPOTHESES for s in SYMBOLS for hold in HOLDS[h]]


def daily(s):
    """[(server day, first index, last index, close)] for every DENSE server day, in order."""
    out = []
    for d, rows in s.day_rows.items():
        if s.dense[rows[0]]:
            out.append((d, rows[0], rows[-1], s.C[rows[-1]]))
    return out


def ev_daily(s, kind):
    """H1 / H2 events at the first bar of a server day, known from PREVIOUS days only (the previous days' density is known)."""
    import bisect
    days = daily(s)
    keys = [x[0] for x in days]
    out = []
    for d, rows in s.day_rows.items():
        first = rows[0]
        if not s.prev_dense[first]:
            continue
        k = bisect.bisect_left(keys, d)                  # dense days strictly before d
        prev = days[max(0, k - (max(MOM_DAYS, SHOCK_DAYS) + 2)):k]
        if len(prev) < max(MOM_DAYS, SHOCK_DAYS) + 2:
            continue
        closes = [x[3] for x in prev]
        if kind == "mom":
            r = closes[-1] / closes[-1 - MOM_DAYS] - 1.0
            if r != 0:
                out.append(EC._ev(s, first - 1 if first > 0 else first, +1 if r > 0 else -1, entry_i=first))
        else:
            rets = [closes[k] / closes[k - 1] - 1.0 for k in range(1, len(closes))]
            last, hist = rets[-1], rets[-1 - SHOCK_DAYS:-1]
            sd = statistics.pstdev(hist)
            if sd > 0 and abs(last) > SHOCK_SD * sd:
                out.append(EC._ev(s, first - 1 if first > 0 else first, -1 if last > 0 else +1, entry_i=first))
    return out


def ev_hour_shock(s):
    out = []
    for i in range(MR_BARS, len(s.C) - 1):
        if not s.prev_dense[i] or s.sday[i - MR_BARS] != s.sday[i]:
            continue
        sig = s.sigma(i)
        if not sig:
            continue
        r = math.log(s.C[i] / s.C[i - MR_BARS])
        if abs(r) > MR_SIGMA * sig * math.sqrt(MR_BARS):
            out.append(EC._ev(s, i, -1 if r > 0 else +1))
    return EC._first_per_day(out)


def ev_fvg_high_vol(s):
    sig_by_day = {}
    for d in s.dense_days:
        v = s._vol.get(d)
        if v:
            sig_by_day[d] = v
    import bisect
    days = sorted(sig_by_day)
    out = []
    for ev in EC.ev_fvg(s):
        d = s.sday[ev["i"]]
        if d not in sig_by_day:
            continue
        k = bisect.bisect_left(days, d)
        hist = [sig_by_day[x] for x in days[max(0, k - REGIME_DAYS):k]]
        if len(hist) >= REGIME_DAYS // 2 and sig_by_day[d] > statistics.median(hist):
            out.append(ev)
    return out


def ev_breakout_trend(s):
    import bisect
    days = daily(s)
    mom = {}
    for k in range(MOM_DAYS, len(days)):
        mom[days[k][0]] = days[k - 1][3] / days[k - 1 - MOM_DAYS][3] - 1.0 if k - 1 - MOM_DAYS >= 0 else None
    if getattr(s, "_sigma_every_day", False):
        # live / paper (point-in-time): the momentum of ANY day from the previous dense days -- the current day is never
        # complete, so it is never in `days`. The research default above keys dense days only (as pre-registered).
        keys = [x[0] for x in days]
        for d in s.day_rows:
            k = bisect.bisect_left(keys, d)
            if k - 1 - MOM_DAYS >= 0:
                mom[d] = days[k - 1][3] / days[k - 1 - MOM_DAYS][3] - 1.0
    out = []
    for ev in EC.ev_prev_day(s, "accept"):
        m = mom.get(s.sday[ev["i"]])
        if m and (m > 0) == (ev["side"] > 0):
            out.append(ev)
    return out


DETECTORS = {"H1_daily_momentum": lambda s: ev_daily(s, "mom"), "H2_daily_shock_reversal": lambda s: ev_daily(s, "shock"),
             "H3_hour_shock_fade": ev_hour_shock, "H5_fvg_high_vol": ev_fvg_high_vol,
             "H7_breakout_with_trend": ev_breakout_trend}


def _eod(s):
    last = {}
    for d, rows in s.day_rows.items():
        for i in rows:
            last[i] = rows[-1]
    return last


def period_of(s, i):
    if s.T[i] >= EXPOSED_START:
        return "exposed"
    return "discovery" if s.sday[i] < s.split_day else "confirmation"


def run(out_path):
    rows = collections.defaultdict(list)
    meta = {}
    for sym in SYMBOLS:
        dev = EC.load(sym)                               # the census's own split day (development window only)
        s = EC.load(sym, end=END)
        s.split_day = dev.split_day
        costs = EC.Costs(sym)
        eod = _eod(s)
        plc = collections.defaultdict(lambda: [0.0, 0])
        for e in range(len(s.C)):
            if not s.dense[e]:
                continue
            per, tod = period_of(s, e), s.dt[e].hour * 60 + s.dt[e].minute
            for k in (12, 24, "eod"):
                x = eod[e] if k == "eod" else e + k - 1
                if x < len(s.C) and s.sday[x] == s.sday[e]:
                    a = plc[(per, tod, k)]
                    a[0] += s.C[x] / s.O[e] - 1.0
                    a[1] += 1
        meta[sym] = {"split_day": str(dev.split_day), "last_bar": s.T[-1]}
        for h, det in DETECTORS.items():
            evs = det(s)
            for hold in HOLDS[h]:
                for ev in evs:
                    ev = dict(ev)
                    if hold == "eod":
                        ev["fixed_exit"] = eod.get(ev["entry_i"])
                    if ev["entry_i"] >= len(s.C):
                        continue
                    o, _why = EC.outcome(s, ev, hold if hold != "eod" else 1, costs)
                    if o is None:
                        continue
                    per = period_of(s, ev["i"])
                    base = plc.get((per, o["tod"], hold))
                    if not base or not base[1]:
                        continue
                    o["period"] = per
                    o["excess"] = o["r"] - o["side"] * base[0] / base[1]
                    rows[(h, sym, hold)].append(o)
        print(f"{sym}: split {dev.split_day}, last bar {s.T[-1]}", flush=True)
    tests = []
    for key in FAMILY:
        rs = rows.get(key, [])
        disc = [r for r in rs if r["period"] == "discovery"]
        raw = EC.summarise(disc)
        direction = 1 if (raw.get("excess_z") or 0) >= 0 else -1
        tests.append({"hypothesis": key[0], "symbol": key[1], "hold": key[2], "direction": direction,
                      "discovery": EC.summarise(disc, direction), "discovery_raw": raw,
                      "confirmation": EC.summarise([r for r in rs if r["period"] == "confirmation"], direction),
                      "exposed": EC.summarise([r for r in rs if r["period"] == "exposed"], direction)})
    rej = EC.bh([t["discovery_raw"].get("p_two_sided", 1.0) if t["discovery_raw"].get("n") else 1.0 for t in tests], FDR_Q)
    for k, t in enumerate(tests):
        d, c, x = t["discovery"], t["confirmation"], t["exposed"]
        cand = k in rej and d.get("n", 0) > 0 and d["net_bp"] > 0
        conf = cand and c.get("n", 0) > 0 and c["p_one_sided"] < CONFIRM_P and c["net_bp"] > 0 and c["net_bp_p90"] > 0
        surv = conf and x.get("n", 0) > 0 and x["p_one_sided"] < EXPOSED_P and x["net_bp"] > 0
        t["verdict"] = {"bh_rejected": k in rej, "candidate": bool(cand), "confirmed": bool(conf), "survives_exposed": bool(surv)}
    out = {"meta": {"script": "scripts/research/edge_f3.py", "family_size": len(FAMILY), "symbols": meta,
                    "hypotheses": HYPOTHESES}, "tests": tests}
    json.dump(out, open(out_path, "w"), indent=1, default=str)
    v = [t["verdict"] for t in tests]
    print(f"wrote {out_path}: {sum(x['candidate'] for x in v)} candidates, {sum(x['confirmed'] for x in v)} confirmed, "
          f"{sum(x['survives_exposed'] for x in v)} survive the exposed window, of {len(tests)}")


def report(json_path, out_path):
    d = json.load(open(json_path))
    f = lambda v, p=3: "n/a" if v is None else f"{v:.{p}f}"
    L = ["| hypothesis | symbol | hold | dir | disc n | disc excess z | disc p (2s) | BH | disc net bp | conf n | conf p (1s) | "
         "conf net bp | conf net p90 | exp n | exp p (1s) | exp net bp | verdict |", "|" + "---|" * 17]
    for t in d["tests"]:
        a, c, x, v = t["discovery"], t["confirmation"], t["exposed"], t["verdict"]
        verdict = ("SURVIVES" if v["survives_exposed"] else "confirmed, fails exposed" if v["confirmed"]
                   else "candidate, not confirmed" if v["candidate"] else "-")
        L.append(f"| {t['hypothesis']} | {t['symbol']} | {t['hold']} | {'+' if t['direction'] > 0 else '-'} | {a.get('n', 0)} | "
                 f"{f(a.get('excess_z'))} | {f(t['discovery_raw'].get('p_two_sided'), 4)} | {'yes' if v['bh_rejected'] else 'no'} | "
                 f"{f(a.get('net_bp'), 2)} | {c.get('n', 0)} | {f(c.get('p_one_sided'), 4)} | {f(c.get('net_bp'), 2)} | "
                 f"{f(c.get('net_bp_p90'), 2)} | {x.get('n', 0)} | {f(x.get('p_one_sided'), 4)} | {f(x.get('net_bp'), 2)} | {verdict} |")
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
