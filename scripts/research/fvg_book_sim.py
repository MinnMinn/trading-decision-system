#!/usr/bin/env python3
"""Book design for the two F2 survivors (docs/audits/2026-10-02-edge-followup-exposed.md): turn the displacement-FVG retrace
(E5) on XAUUSD (hold 24 bars) and US500 (hold 48 bars) into trades WITH A STOP, and replay FTMO challenges on the real trade
sequence. DESIGN on already-read history (owner 2026-10-02): this chooses a stop rule and a risk level; it validates nothing --
the forward stage (a) does.

    python3 scripts/research/fvg_book_sim.py --out docs/audits/2026-10-02-fvg-book-sim.json

Trade: entry at the FVG near edge on the touch bar (as the census), exit at the close of bar entry+h-1 (time exit, flat before
the rollover) or at the stop, whichever first; a bar that OPENS beyond the stop fills at its open; the touch bar itself is
checked for the stop (pessimistic: a same-bar touch-and-stop is a loss). Cost: the census's relative spread round trip.
Stop variants (both reported, chosen before looking): `far_edge` = the gap's far edge (the source's 'FVG end', core-a.md R22),
`sigma2` = 2 x sigma_5m x sqrt(h) away. R = net P&L / stop distance.

FTMO replay (no bootstrap): a challenge starts on every Monday; trades of the book are applied in time order at risk r of the
INITIAL balance per trade (FTMO-style fixed money risk); fail on equity <= 90 % (closed trades) or a server-day loss >= 5 % of
the initial balance; pass on >= +10 % (Phase 1) / +5 % (Phase 2) with >= 4 trading days; a start still open after 120
weekdays (Phase 1) counts as not passed (FTMO itself has no limit; the unlimited figure is reported too)."""
import argparse
import collections
import datetime
import importlib.util
import json
import math
import os
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_spec = importlib.util.spec_from_file_location("edge_census", os.path.join(ROOT, "scripts", "research", "edge_census.py"))
EC = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(EC)

COMPONENTS = {"XAUUSD": 24, "US500": 48}
STOPS = ("far_edge", "sigma2")
RISKS = (0.0025, 0.005, 0.01)
END = "9999-12-31T00:00:00Z"


def trades_for(sym, h, stop_rule):
    s = EC.load(sym, end=END)
    costs = EC.Costs(sym)
    out = []
    for ev in EC.ev_fvg(s):
        e, side = ev["entry_i"], ev["side"]
        x = e + h - 1
        if x >= len(s.C) or s.sday[x] != s.sday[e]:
            continue
        sig = s.sigma(ev["i"])
        if not sig:
            continue
        px = ev["entry_px"]
        if stop_rule == "far_edge":
            dist = abs(px - ev["far"])
        else:
            dist = 2.0 * sig * math.sqrt(h) * px
        if dist <= 0:
            continue
        stop = px - side * dist
        exit_px, how, j_exit = s.C[x], "time", x
        for j in range(e, x + 1):
            hit = (s.L[j] <= stop) if side > 0 else (s.H[j] >= stop)
            if hit:
                o = s.O[j]
                exit_px = (min(stop, o) if side > 0 else max(stop, o)) if j > e else stop
                how, j_exit = "stop", j
                break
        cost = costs.round_trip(s.dt[e].hour, s.dt[j_exit].hour) * px
        R = (side * (exit_px - px) - cost) / dist
        out.append({"symbol": sym, "entry_time": s.T[e], "exit_time": s.T[j_exit], "server_day": str(s.sday[j_exit]),
                    "R": R, "exit": how, "stop_bp": dist / px * 1e4})
    return out


def replay(book, risk, target, max_days):
    """[(start, outcome, weekdays_used)] for a challenge starting every Monday."""
    book = sorted(book, key=lambda t: t["exit_time"])
    times = [t["exit_time"] for t in book]
    first = datetime.date.fromisoformat(book[0]["entry_time"][:10])
    last = datetime.date.fromisoformat(book[-1]["entry_time"][:10])
    d = first + datetime.timedelta(days=(7 - first.weekday()) % 7)
    res = []
    import bisect
    while d <= last - datetime.timedelta(days=30):
        k = bisect.bisect_left(times, d.isoformat())
        eq, days, day_pnl, outcome, used = 1.0, set(), collections.defaultdict(float), "open", None
        limit = d + datetime.timedelta(days=int(max_days * 7 / 5) + 2) if max_days else None
        for t in book[k:]:
            td = datetime.date.fromisoformat(t["exit_time"][:10])
            if limit and td >= limit:
                break
            eq += risk * t["R"]
            days.add(t["entry_time"][:10])
            day_pnl[t["server_day"]] += risk * t["R"]
            if eq <= 0.90 or day_pnl[t["server_day"]] <= -0.05:
                outcome, used = "fail", td
                break
            if eq >= 1.0 + target and len(days) >= 4:
                outcome, used = "pass", td
                break
        res.append({"start": d.isoformat(), "outcome": outcome, "end": used.isoformat() if used else None})
        d += datetime.timedelta(days=7)
    return res


def summarise_replay(rs):
    n = len(rs)
    c = collections.Counter(r["outcome"] for r in rs)
    durs = [(datetime.date.fromisoformat(r["end"]) - datetime.date.fromisoformat(r["start"])).days
            for r in rs if r["outcome"] == "pass"]
    by_year = collections.defaultdict(collections.Counter)
    for r in rs:
        by_year[r["start"][:4]][r["outcome"]] += 1
    return {"starts": n, "pass": c["pass"] / n if n else None, "fail": c["fail"] / n if n else None,
            "open": c["open"] / n if n else None, "median_days_to_pass": statistics.median(durs) if durs else None,
            "pass_by_start_year": {y: round(v["pass"] / sum(v.values()), 3) for y, v in sorted(by_year.items())}}


def stats(tr):
    rs = [t["R"] for t in tr]
    n = len(rs)
    mu = sum(rs) / n
    sd = statistics.pstdev(rs)
    days = len({t["entry_time"][:10] for t in tr})
    return {"n": n, "mean_R": mu, "sd_R": sd, "win_rate": sum(r > 0 for r in rs) / n,
            "stop_share": sum(t["exit"] == "stop" for t in tr) / n, "median_stop_bp": statistics.median(t["stop_bp"] for t in tr),
            "trades_per_active_day": n / days,
            "by_year_mean_R": {y: round(statistics.mean(t["R"] for t in tr if t["entry_time"][:4] == y), 4)
                               for y in sorted({t["entry_time"][:4] for t in tr})}}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = {"meta": {"script": "scripts/research/fvg_book_sim.py", "components": COMPONENTS, "stops": STOPS, "risks": RISKS},
           "components": {}, "books": {}}
    trades = {}
    for stop in STOPS:
        for sym, h in COMPONENTS.items():
            tr = trades_for(sym, h, stop)
            trades[(stop, sym)] = tr
            out["components"][f"{sym}|{stop}"] = stats(tr)
            print(sym, stop, {k: v for k, v in out["components"][f"{sym}|{stop}"].items() if k != "by_year_mean_R"}, flush=True)
        for label, syms in (("XAUUSD", ["XAUUSD"]), ("US500", ["US500"]), ("book", list(COMPONENTS))):
            book = [t for s_ in syms for t in trades[(stop, s_)]]
            if label == "book":            # the book only over the span where both components trade
                lo = max(min(t["entry_time"] for t in trades[(stop, s_)]) for s_ in syms)
                book = [t for t in book if t["entry_time"] >= lo]
            for r in RISKS:
                key = f"{label}|{stop}|{r}"
                out["books"][key] = {"phase1_120d": summarise_replay(replay(book, r, 0.10, 120)),
                                     "phase1_unlimited": summarise_replay(replay(book, r, 0.10, None)),
                                     "phase2_unlimited": summarise_replay(replay(book, r, 0.05, None))}
                p = out["books"][key]
                print(key, "P1/120d pass", round(p["phase1_120d"]["pass"], 3), "P1 unlimited pass",
                      round(p["phase1_unlimited"]["pass"], 3), "P2 pass", round(p["phase2_unlimited"]["pass"], 3), flush=True)
    json.dump(out, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
