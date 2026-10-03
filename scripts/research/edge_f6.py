#!/usr/bin/env python3
"""Edge families F6 (US500, US30, USTEC) and F7 (XAUUSD): overnight reversal after a US cash-session sell-off.
Pre-registrations: docs/plans/2026-10-03-edge-f6-overnight-reversal-preregistration.md and
docs/plans/2026-10-03-edge-f7-gold-overnight-reversal-preregistration.md. Each read ONCE, in order, each in its own commit:

    python3 scripts/research/edge_f6.py run --read discovery    --out docs/audits/2026-10-03-edge-f6-discovery.json
    python3 scripts/research/edge_f6.py run --read confirmation --after docs/audits/2026-10-03-edge-f6-discovery.json --out ...
    python3 scripts/research/edge_f6.py run --read exposed      --after <confirmation json> --out ...

A read computes outcome rows ONLY for events of its own period. Trigger: New York 09:30-16:00 session return / SD of the
previous 20 complete sessions <= theta. Entry: OPEN of the first bar >= 19:00 New York in the NEXT server day (FTMO server day
= 17:00 -> 17:00 New York). Exit: CLOSE of the last bar closing <= 09:00 Berlin (W1) or <= 09:30 New York (W2) the next
morning, same server day. Long only. Placebo: the same window on the period's eligible NON-trigger days."""
import argparse
import bisect
import collections
import datetime
import importlib.util
import json
import math
import os
import statistics
import zoneinfo

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


F3 = _load("edge_f3", "scripts/research/edge_f3.py")
EC = F3.EC
NY, BERLIN = zoneinfo.ZoneInfo("America/New_York"), zoneinfo.ZoneInfo("Europe/Berlin")
END = "9999-12-31T00:00:00Z"
BAR = datetime.timedelta(minutes=5)
FAMILIES = {"F6": ("US500", "US30", "USTEC"), "F7": ("XAUUSD",)}
THETAS = (-0.5, -1.0)
WINDOWS = {"W1_berlin_0900": (BERLIN, 9, 0), "W2_newyork_0930": (NY, 9, 30)}
SESSION_OPEN, SESSION_CLOSE = 9 * 60 + 30, 16 * 60          # New York minutes
SESSION_MIN_BARS, SD_SESSIONS = 70, 20
ENTRY_NY, ENTRY_LATEST_NY = (19, 0), (21, 0)
HOLE = datetime.timedelta(minutes=30)
FDR_Q, CONFIRM_P, EXPOSED_P = 0.10, 0.05, 0.10
READS = ("discovery", "confirmation", "exposed")


def family_tests(fam):
    return [(sym, th, w) for sym in FAMILIES[fam] for th in THETAS for w in WINDOWS]


# ------------------------------------------------------------------------------------------------ detection
def sessions(s):
    """{server day: (session return, index of its last bar)} for every COMPLETE New York cash session (09:30 bar and 15:55
    bar present, >= SESSION_MIN_BARS bars, one New York date)."""
    out = {}
    for d, rows in s.day_rows.items():
        sess = []
        for i in rows:
            t = s.dt[i].astimezone(NY)
            m = t.hour * 60 + t.minute
            if SESSION_OPEN <= m < SESSION_CLOSE:
                sess.append((m, i))
        if len(sess) < SESSION_MIN_BARS:
            continue
        mins = {m for m, _ in sess}
        if SESSION_OPEN not in mins or SESSION_CLOSE - 5 not in mins:
            continue
        first, last = min(sess)[1], max(sess)[1]
        if s.dt[first].astimezone(NY).date() != s.dt[last].astimezone(NY).date():
            continue
        out[d] = (s.C[last] / s.O[first] - 1.0, last)
    return out


def session_z(s):
    """{server day: (z, last session bar)} -- the session return over the SD of the previous SD_SESSIONS complete sessions
    (strictly earlier; point-in-time)."""
    sess = sessions(s)
    days = sorted(sess)
    out = {}
    for k, d in enumerate(days):
        if k < SD_SESSIONS:
            continue
        sd = statistics.stdev(sess[x][0] for x in days[k - SD_SESSIONS:k])
        if sd > 0:
            out[d] = (sess[d][0] / sd, sess[d][1])
    return out


def window_bars(s, next_day, window):
    """(entry i, exit i) inside server day `next_day`, or None. The server day starts 17:00 New York on the previous
    calendar date (FTMO: server = New York + 7 h in every week)."""
    rows = s.day_rows[next_day]
    start = next_day - datetime.timedelta(days=1)
    e_from = datetime.datetime(start.year, start.month, start.day, *ENTRY_NY, tzinfo=NY)
    e_to = datetime.datetime(start.year, start.month, start.day, *ENTRY_LATEST_NY, tzinfo=NY)
    e = next((i for i in rows if e_from <= s.dt[i] < e_to), None)
    if e is None:
        return None
    zone, hh, mm = WINDOWS[window]
    nxt = start + datetime.timedelta(days=1)
    target = datetime.datetime(nxt.year, nxt.month, nxt.day, hh, mm, tzinfo=zone)
    x = None
    for j in rows:
        if j > e and s.dt[j] + BAR <= target:
            x = j
    if x is None or target - (s.dt[x] + BAR) > HOLE:
        return None
    return e, x


def events(s):
    """[{server day of the trade, z, entry i, exit i, window}] for every eligible (session, next server day, window): the
    previous server day dense, a complete session with a z, an entry and an exit. Trigger membership is decided later."""
    zs = session_z(s)
    keys = list(s.day_rows)
    pos = {d: k for k, d in enumerate(keys)}
    out = []
    for d, (z, _last) in zs.items():
        k = pos[d]
        if k + 1 >= len(keys):
            continue
        nd = keys[k + 1]
        for w in WINDOWS:
            ex = window_bars(s, nd, w)
            if ex is None or not s.prev_dense[ex[0]]:
                continue
            out.append({"session_day": d, "day": nd, "z": z, "entry_i": ex[0], "exit_i": ex[1], "window": w, "side": 1,
                        "i": _last})
    return out


# ------------------------------------------------------------------------------------------------ outcomes
def outcome(s, ev, costs):
    e, x = ev["entry_i"], ev["exit_i"]
    sig = s.sigma(e)
    if not sig:
        return None
    r = s.C[x] / s.O[e] - 1.0
    c = costs.round_trip(s.dt[e].hour, s.dt[x].hour)
    return {"symbol": s.sym, "date": s.dt[e].date().isoformat(), "server_day": str(ev["day"]), "window": ev["window"],
            "z": ev["z"], "side": 1, "r": r, "cost": c, "cost90": costs.round_trip(s.dt[e].hour, s.dt[x].hour, "p90"),
            "cost2x": 2.0 * c, "scale": sig * math.sqrt(x - e + 1), "entry_time": s.T[e], "exit_time": s.T[x]}


def _cr1_t(values, dates):
    mu, se, df = EC.cr1(values, dates)
    return {"n": len(values), "mean": mu, "t": (mu / se) if se else None,
            "p_one_sided": EC.t_sf(mu / se, df) if se else None} if values else {"n": 0}


def summarise(trig, placebo_mean):
    for r in trig:
        r["excess"] = r["r"] - placebo_mean
    out = EC.summarise(trig, +1)
    if trig:
        out["net_bp_2x"] = sum((r["r"] - r["cost2x"]) * 1e4 for r in trig) / len(trig)
        ex_bp = [r["excess"] * 1e4 for r in trig]
        sd = statistics.pstdev(ex_bp) if len(ex_bp) > 1 else None
        out["mde_bp_80pct_alpha0.10"] = (1.2816 + 0.8416) * sd / math.sqrt(len(ex_bp)) if sd else None
    return out


def _book_daily(kind):
    BS = _load("book_sim", "scripts/research/book_sim.py")
    comps = {"h7_g9": ["H7_XAUUSD_eod", "G9_XAUUSD_eod"],
             "v2_pit": ["H7_XAUUSD_eod", "G9_XAUUSD_eod", "E5_XAUUSD_24", "E5_US500_48"]}[kind]
    return BS.daily_r([t for c in comps for t in BS.trades(*BS.COMPONENTS[c])]), BS.corr


def run(read, out_path, after=None):
    if read not in READS:
        raise SystemExit(f"unknown read {read}")
    prior = json.load(open(after)) if after else None
    if read != "discovery" and (prior is None or prior["meta"]["read"] != READS[READS.index(read) - 1]):
        raise SystemExit(f"--read {read} needs --after <the {READS[READS.index(read) - 1]} json>")
    books = {k: _book_daily(k) for k in ("h7_g9", "v2_pit")}
    res = {"meta": {"script": "scripts/research/edge_f6.py", "read": read, "families": FAMILIES, "thetas": THETAS,
                    "windows": {w: [str(z), h, m] for w, (z, h, m) in WINDOWS.items()}, "cost_profile": EC.COST_PROFILE,
                    "preregistrations": ["docs/plans/2026-10-03-edge-f6-overnight-reversal-preregistration.md",
                                         "docs/plans/2026-10-03-edge-f7-gold-overnight-reversal-preregistration.md"]},
           "symbols": {}, "families": {}}
    rows = {}
    for fam, syms in FAMILIES.items():
        for sym in syms:
            dev = EC.load(sym)
            s = EC.load(sym, end=END)
            s.split_day = dev.split_day
            costs = EC.Costs(sym)
            elig = collections.defaultdict(list)
            for ev in events(s):
                if F3.period_of(s, ev["entry_i"]) != read:
                    continue                                   # this read touches its own period only
                o = outcome(s, ev, costs)
                if o is not None:
                    elig[ev["window"]].append(o)
            res["symbols"][sym] = {"split_day": str(dev.split_day), "eligible": {w: len(v) for w, v in elig.items()}}
            for w, es in elig.items():
                net = [(r["r"] - r["cost"]) * 1e4 for r in es]
                res["symbols"][sym][f"unconditional|{w}"] = _cr1_t(net, [r["date"] for r in es])
                for th in THETAS:
                    trig = [dict(r) for r in es if r["z"] <= th]
                    rest = [r["r"] for r in es if r["z"] > th]
                    pm = statistics.mean(rest) if rest else 0.0
                    summ = summarise(trig, pm)
                    summ["placebo_non_trigger_days"] = len(rest)
                    lo, hi = (min(r["server_day"] for r in es), max(r["server_day"] for r in es)) if es else ("", "")
                    daily = collections.defaultdict(float)
                    for r in trig:
                        daily[r["server_day"]] += (r["r"] - r["cost"]) / r["scale"]
                    for k, (bd, corr) in books.items():
                        b = {d: v for d, v in bd.items() if lo <= d <= hi}
                        summ[f"corr_daily_with_{k}"] = corr(dict(daily), b) if daily else None
                    rows[(sym, th, w)] = summ
    for fam in FAMILIES:
        tests = []
        for (sym, th, w) in family_tests(fam):
            t = {"symbol": sym, "theta": th, "window": w, read: rows.get((sym, th, w), {"n": 0})}
            tests.append(t)
        if read == "discovery":
            rej = EC.bh([t[read].get("p_one_sided", 1.0) if t[read].get("n") else 1.0 for t in tests], FDR_Q)
            for k, t in enumerate(tests):
                d = t[read]
                t["verdict"] = {"bh_rejected": k in rej, "candidate": bool(k in rej and d.get("n") and d["net_bp"] > 0)}
        else:
            before = {(x["symbol"], x["theta"], x["window"]): x for x in prior["families"][fam]}
            for t in tests:
                prev = before[(t["symbol"], t["theta"], t["window"])]["verdict"]
                d = t[read]
                if read == "confirmation":
                    ok = (prev["candidate"] and d.get("n") and d["p_one_sided"] < CONFIRM_P and d["net_bp"] > 0
                          and d["net_bp_p90"] > 0 and d["net_bp_2x"] > 0)
                    t["verdict"] = dict(prev, confirmed=bool(ok))
                else:
                    ok = prev.get("confirmed") and d.get("n") and d["p_one_sided"] < EXPOSED_P and d["net_bp"] > 0
                    t["verdict"] = dict(prev, survives=bool(ok))
        res["families"][fam] = tests
    json.dump(res, open(out_path, "w"), indent=1, default=str)
    for fam, tests in res["families"].items():
        for t in tests:
            d = t[read]
            print(f"{fam} {t['symbol']:6s} theta {t['theta']:+.1f} {t['window']:16s} n {d.get('n', 0):4d} "
                  f"excess z {d.get('excess_z', float('nan')):+.3f} p1 {d.get('p_one_sided', float('nan')):.4f} "
                  f"net {d.get('net_bp', float('nan')):+.2f} bp | {t['verdict']}")
    print(f"wrote {out_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--read", required=True, choices=READS)
    r.add_argument("--out", required=True)
    r.add_argument("--after")
    a = ap.parse_args()
    run(a.read, a.out, a.after)


if __name__ == "__main__":
    main()
