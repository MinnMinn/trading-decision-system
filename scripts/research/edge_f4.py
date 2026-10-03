#!/usr/bin/env python3
"""Edge family F4 (docs/plans/2026-10-02-edge-f4-preregistration.md): published, method-agnostic effects as candidate
INDEPENDENT book components, on all eight allowlisted CFDs, judged in the same three reads as F3 (discovery = first 60 % of
dense development days, confirmation = last 40 %, exposed = 2024-03-01 -> end of data), each read once.

    python3 scripts/research/edge_f4.py run    --out docs/audits/2026-10-02-edge-f4.json
    python3 scripts/research/edge_f4.py report --json docs/audits/2026-10-02-edge-f4.json --out <md>

Intraday tests (G3, G4, G5, G7, G9) exit on the last bar of the entry's server day (flat before the rollover). G1 is the one
overnight test: entry at the last bar of day d, exit at the last bar of the next dense day, priced with the broker's swap
(scaled by entry / price_ref like the relative spread; today's swap points stand in for history's -- disclosed)."""
import argparse
import bisect
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


F3 = _load("edge_f3", "scripts/research/edge_f3.py")
EC = F3.EC
SYMBOLS = ("XAUUSD", "XAGUSD", "US500", "US30", "USTEC", "DE40", "FRA40", "AUS200")
INDICES = ("US500", "US30", "USTEC", "DE40", "FRA40", "AUS200")
END = "9999-12-31T00:00:00Z"
FDR_Q, CONFIRM_P, EXPOSED_P = 0.10, 0.05, 0.10
TSMOM_DAYS, NR_DAYS, VB_K = 60, 7, 0.5

HYPOTHESES = {
    "G1_tsmom_overnight": ("sign of the 60-dense-day return at the close of day d's second-to-last bar; long/short from the open of d's last "
                           "bar to the close of the next day's last bar (swap paid)"),
    "G3_h7_new_symbols": "F3's H7 (prev-day breakout with the 20-day momentum, to the end of day) on the symbols F3 did not test",
    "G4_prev_week_breakout_trend": "first close beyond the previous server WEEK's high (low) with the 20-day momentum; to end of day",
    "G5_nr7_breakout": "after a day whose range is the narrowest of the last 7, the first close beyond that day's range; to end of day",
    "G7_turn_of_month_long": "indices: long from the first to the last bar of the last trading day and the first 3 of each month",
    "G9_volatility_breakout": "first close beyond day open +/- 0.5 x the previous day's range; to end of day",
}
FAMILY = ([("G1_tsmom_overnight", s) for s in SYMBOLS] + [("G3_h7_new_symbols", s) for s in ("XAGUSD", "FRA40", "AUS200")]
          + [("G4_prev_week_breakout_trend", s) for s in SYMBOLS] + [("G5_nr7_breakout", s) for s in SYMBOLS]
          + [("G7_turn_of_month_long", s) for s in INDICES] + [("G9_volatility_breakout", s) for s in SYMBOLS])


def _days(s):
    return F3.daily(s)          # [(server day, first i, last i, close)] of DENSE days (density of PAST days is known)


def _mom(days, keys, d, n):
    """n-dense-day close-to-close return known at the start of server day d (dense days strictly before d), or None."""
    k = bisect.bisect_left(keys, d)
    return days[k - 1][3] / days[k - 1 - n][3] - 1.0 if k - 1 - n >= 0 else None


def overnight_pairs(s):
    """[(day, signal i, entry i, exit i)] for every server day d with a dense previous day and >= 3 bars, followed by a DENSE
    server day: signal at the close of d's second-to-last bar, entry at the OPEN of d's last bar, exit at the CLOSE of the next
    server day's last bar (the next day's density is an outcome-side data filter, not a decision input -- disclosed)."""
    keys = list(s.day_rows)
    out = []
    for j, d in enumerate(keys[:-1]):
        rows, nxt = s.day_rows[d], s.day_rows[keys[j + 1]]
        if len(rows) >= 3 and s.prev_dense[rows[0]] and s.dense[nxt[0]]:
            out.append((d, rows[-2], rows[-1], nxt[-1]))
    return out


def ev_tsmom(s):
    days = _days(s)
    keys = [x[0] for x in days]
    out = []
    for d, sig_i, e, x in overnight_pairs(s):
        k = bisect.bisect_left(keys, d)
        if k - TSMOM_DAYS < 0:
            continue
        m = s.C[sig_i] / days[k - TSMOM_DAYS][3] - 1.0
        if m != 0:
            out.append({"i": sig_i, "side": 1 if m > 0 else -1, "entry_i": e, "exit_i": x, "overnight": True})
    return out


def _first_close_beyond(s, rows, hi, lo, want=None):
    """First bar of `rows` closing above hi / below lo. Research (complete days): never the day's LAST bar, whose next bar is
    the next day. Live / paper (`sigma_every_day`, the current day is never complete): its last row is just the latest closed
    bar, so it counts; the executor and the paper log refuse an entry that would fall in the next server day."""
    for i in (rows if getattr(s, "_sigma_every_day", False) else rows[:-1]):
        if s.C[i] > hi and want in (None, 1):
            return i, 1
        if s.C[i] < lo and want in (None, -1):
            return i, -1
    return None


def prev_week_levels(s):
    """{server day: (high, low) over the dense days of the latest earlier ISO week that has any} -- known at the day's start."""
    wk = {}
    for d, rows in s.day_rows.items():
        if s.dense[rows[0]]:
            w = d.isocalendar()[:2]
            hi, lo = max(s.H[j] for j in rows), min(s.L[j] for j in rows)
            a = wk.get(w)
            wk[w] = (max(a[0], hi), min(a[1], lo)) if a else (hi, lo)
    weeks = sorted(wk)
    out = {}
    for d in s.day_rows:
        k = bisect.bisect_left(weeks, d.isocalendar()[:2])
        if k:
            out[d] = wk[weeks[k - 1]]
    return out


def ev_prev_week(s):
    days = _days(s)
    keys = [x[0] for x in days]
    lv = prev_week_levels(s)
    out = []
    for d, rows in s.day_rows.items():
        if not s.prev_dense[rows[0]] or d not in lv:
            continue
        m = _mom(days, keys, d, F3.MOM_DAYS)
        if not m:
            continue
        hit = _first_close_beyond(s, rows, lv[d][0], lv[d][1], 1 if m > 0 else -1)
        if hit:
            out.append(EC._ev(s, hit[0], hit[1]))
    return out


def ev_nr7(s):
    days = _days(s)
    keys = [x[0] for x in days]
    rng = {x[0]: max(s.H[j] for j in s.day_rows[x[0]]) - min(s.L[j] for j in s.day_rows[x[0]]) for x in days}
    out = []
    for d, rows in s.day_rows.items():
        if not s.prev_dense[rows[0]]:
            continue
        k = bisect.bisect_left(keys, d)
        if k < NR_DAYS:
            continue
        last7 = keys[k - NR_DAYS:k]
        y = last7[-1]
        if rng[y] > min(rng[x] for x in last7):
            continue
        hi, lo = max(s.H[j] for j in s.day_rows[y]), min(s.L[j] for j in s.day_rows[y])
        hit = _first_close_beyond(s, rows, hi, lo)
        if hit:
            out.append(EC._ev(s, hit[0], hit[1]))
    return out


def tom_days(s):
    """Turn-of-the-month server days among weekdays with bars: each month's last one and first three (the trading calendar is
    published in advance, so knowing tomorrow's month is point-in-time)."""
    keys = [d for d in s.day_rows if d.weekday() < 5]
    out = set()
    for k, d in enumerate(keys):
        if k + 1 < len(keys) and keys[k + 1].month != d.month:
            out.add(d)
        if sum(1 for x in keys[max(0, k - 3):k + 1] if (x.year, x.month) == (d.year, d.month)) <= 3:
            out.add(d)
    return out


def ev_tom(s):
    tom = tom_days(s)
    out = []
    for d, rows in s.day_rows.items():
        first = rows[0]
        if d in tom and first > 0 and s.prev_dense[first]:
            out.append(EC._ev(s, first - 1, 1, entry_i=first))      # known before the day opens; long from its first bar
    return out


def ev_vol_breakout(s):
    days = _days(s)
    keys = [x[0] for x in days]
    out = []
    for d, rows in s.day_rows.items():
        if not s.prev_dense[rows[0]]:
            continue
        k = bisect.bisect_left(keys, d)
        if k < 1:
            continue
        y = keys[k - 1]
        r = max(s.H[j] for j in s.day_rows[y]) - min(s.L[j] for j in s.day_rows[y])
        o = s.O[rows[0]]
        hit = _first_close_beyond(s, rows, o + VB_K * r, o - VB_K * r)
        if hit:
            out.append(EC._ev(s, hit[0], hit[1]))
    return out


DETECTORS = {"G1_tsmom_overnight": ev_tsmom, "G3_h7_new_symbols": F3.ev_breakout_trend,
             "G4_prev_week_breakout_trend": ev_prev_week, "G5_nr7_breakout": ev_nr7, "G7_turn_of_month_long": ev_tom,
             "G9_volatility_breakout": ev_vol_breakout}


def run(out_path):
    import real_costs as RC
    rows = collections.defaultdict(list)
    meta = {}
    for sym in SYMBOLS:
        dev = EC.load(sym)
        s = EC.load(sym, end=END)
        s.split_day = dev.split_day
        costs = EC.Costs(sym)
        ref = RC.price_ref(EC.COST_PROFILE, sym)
        eod = F3._eod(s)
        # placebos: intraday, same period / time of day, to the end of day; overnight, the mean close-to-close of the period
        plc = collections.defaultdict(lambda: [0.0, 0])
        for e in range(len(s.C)):
            if s.dense[e] and s.sday[eod[e]] == s.sday[e]:
                a = plc[(F3.period_of(s, e), s.dt[e].hour * 60 + s.dt[e].minute)]
                a[0] += s.C[eod[e]] / s.O[e] - 1.0
                a[1] += 1
        on = collections.defaultdict(lambda: [0.0, 0])
        for _d, _sig, e, x in overnight_pairs(s):
            a = on[F3.period_of(s, _sig)]
            a[0] += s.C[x] / s.O[e] - 1.0
            a[1] += 1
        meta[sym] = {"split_day": str(dev.split_day), "last_bar": s.T[-1]}
        for h, det in DETECTORS.items():
            if (h, sym) not in FAMILY:
                continue
            for ev in det(s):
                per = F3.period_of(s, ev["i"])
                sig = s.sigma(ev["i"])
                if not sig:
                    continue
                if ev.get("overnight"):
                    e, x = ev["entry_i"], ev["exit_i"]
                    px = s.O[e]
                    r = ev["side"] * (s.C[x] / px - 1.0)
                    sw, _n, _ = RC.swap_price(EC.COST_PROFILE, sym, "long" if ev["side"] > 0 else "short", s.T[e], s.T[x])
                    swap_frac = -sw / ref                         # a debit (negative points) is a positive cost
                    cost = costs.round_trip(s.dt[e].hour, s.dt[x].hour) + swap_frac
                    cost90 = costs.round_trip(s.dt[e].hour, s.dt[x].hour, "p90") + swap_frac
                    base = on.get(per)
                    if not base or not base[1]:
                        continue
                    o = {"symbol": sym, "date": s.dt[ev["i"]].date().isoformat(), "period": per, "side": ev["side"], "r": r,
                         "cost": cost, "cost90": cost90, "scale": sig * (x - e + 1) ** 0.5,
                         "excess": r - ev["side"] * base[0] / base[1]}
                else:
                    if h != "G7_turn_of_month_long" and s.sday[min(ev["entry_i"], len(s.C) - 1)] != s.sday[ev["i"]]:
                        continue                                  # a signal on the day's last bar: no same-day trade
                    ev = dict(ev, fixed_exit=eod.get(ev["entry_i"]) if ev["entry_i"] < len(s.C) else None)
                    if ev["fixed_exit"] is None:
                        continue
                    o, _w = EC.outcome(s, ev, 1, costs)
                    if o is None:
                        continue
                    base = plc.get((per, o["tod"]))
                    if not base or not base[1]:
                        continue
                    o["period"] = per
                    o["excess"] = o["r"] - o["side"] * base[0] / base[1]
                rows[(h, sym)].append(o)
        print(f"{sym}: split {dev.split_day}", flush=True)
    tests = []
    for key in FAMILY:
        rs = rows.get(key, [])
        disc = [r for r in rs if r["period"] == "discovery"]
        raw = EC.summarise(disc)
        direction = 1 if (raw.get("excess_z") or 0) >= 0 else -1
        if key[0] == "G7_turn_of_month_long":
            direction = 1                                   # a long-only seasonal: never flipped
        tests.append({"hypothesis": key[0], "symbol": key[1], "direction": direction, "discovery_raw": raw,
                      "discovery": EC.summarise(disc, direction),
                      "confirmation": EC.summarise([r for r in rs if r["period"] == "confirmation"], direction),
                      "exposed": EC.summarise([r for r in rs if r["period"] == "exposed"], direction)})
    rej = EC.bh([t["discovery_raw"].get("p_two_sided", 1.0) if t["discovery_raw"].get("n") else 1.0 for t in tests], FDR_Q)
    for k, t in enumerate(tests):
        d, c, x = t["discovery"], t["confirmation"], t["exposed"]
        cand = k in rej and d.get("n", 0) > 0 and d["net_bp"] > 0
        conf = cand and c.get("n", 0) > 0 and c["p_one_sided"] < CONFIRM_P and c["net_bp"] > 0 and c["net_bp_p90"] > 0
        surv = conf and x.get("n", 0) > 0 and x["p_one_sided"] < EXPOSED_P and x["net_bp"] > 0
        t["verdict"] = {"bh_rejected": k in rej, "candidate": bool(cand), "confirmed": bool(conf), "survives_exposed": bool(surv)}
    json.dump({"meta": {"script": "scripts/research/edge_f4.py", "family_size": len(FAMILY), "symbols": meta,
                        "hypotheses": HYPOTHESES}, "tests": tests}, open(out_path, "w"), indent=1, default=str)
    v = [t["verdict"] for t in tests]
    print(f"wrote {out_path}: {sum(x['candidate'] for x in v)} candidates, {sum(x['confirmed'] for x in v)} confirmed, "
          f"{sum(x['survives_exposed'] for x in v)} survive, of {len(tests)}")


def report(json_path, out_path):
    d = json.load(open(json_path))
    f = lambda v, p=3: "n/a" if v is None else f"{v:.{p}f}"
    L = ["| hypothesis | symbol | dir | disc n | disc p (2s) | BH | disc net bp | conf n | conf p (1s) | conf net bp | conf p90 | "
         "exp n | exp p (1s) | exp net bp | verdict |", "|" + "---|" * 15]
    for t in d["tests"]:
        a, c, x, v = t["discovery"], t["confirmation"], t["exposed"], t["verdict"]
        verdict = ("SURVIVES" if v["survives_exposed"] else "confirmed, fails exposed" if v["confirmed"]
                   else "candidate, not confirmed" if v["candidate"] else "-")
        L.append(f"| {t['hypothesis']} | {t['symbol']} | {'+' if t['direction'] > 0 else '-'} | {a.get('n', 0)} | "
                 f"{f(t['discovery_raw'].get('p_two_sided'), 4)} | {'yes' if v['bh_rejected'] else 'no'} | {f(a.get('net_bp'), 2)} | "
                 f"{c.get('n', 0)} | {f(c.get('p_one_sided'), 4)} | {f(c.get('net_bp'), 2)} | {f(c.get('net_bp_p90'), 2)} | "
                 f"{x.get('n', 0)} | {f(x.get('p_one_sided'), 4)} | {f(x.get('net_bp'), 2)} | {verdict} |")
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
