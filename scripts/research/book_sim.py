#!/usr/bin/env python3
"""Book design for every component that has survived its pre-registered reads (DESIGN on already-read history; the forward
stage validates): F2 E5 FVG retrace (XAUUSD 24 bars, US500 48 bars) and F3 H7 breakout-with-trend (XAUUSD, to the end of the
server day). Same trade mechanics and FTMO replay as scripts/research/fvg_book_sim.py (whose functions it reuses): protective
stop 2 x sigma_5m x sqrt(hold bars), time exit, flat before the rollover, relative spread cost, R = net P&L / stop distance.

    python3 scripts/research/book_sim.py --out docs/audits/2026-10-02-book-sim.json"""
import argparse
import importlib.util
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


FB = _load("fvg_book_sim", "scripts/research/fvg_book_sim.py")
F3 = _load("edge_f3", "scripts/research/edge_f3.py")
EC = FB.EC
END = "9999-12-31T00:00:00Z"
RISKS = (0.0025, 0.005, 0.01)


def trades(sym, events, hold):
    """hold: int bars, or 'eod'."""
    s = EC.load(sym, end=END)
    costs = EC.Costs(sym)
    last = {}
    for d, rows in s.day_rows.items():
        for i in rows:
            last[i] = rows[-1]
    out = []
    for ev in events(s):
        e, side = ev["entry_i"], ev["side"]
        if e >= len(s.C):
            continue
        x = last[e] if hold == "eod" else e + hold - 1
        if x >= len(s.C) or s.sday[x] != s.sday[e]:
            continue
        sig = s.sigma(ev["i"])
        if not sig:
            continue
        px = ev["entry_px"] if ev.get("entry_px") is not None else s.O[e]
        dist = 2.0 * sig * math.sqrt(x - e + 1) * px
        stop = px - side * dist
        exit_px, how, j_exit = s.C[x], "time", x
        for j in range(e, x + 1):
            if (s.L[j] <= stop) if side > 0 else (s.H[j] >= stop):
                exit_px = (min(stop, s.O[j]) if side > 0 else max(stop, s.O[j])) if j > e else stop
                how, j_exit = "stop", j
                break
        cost = costs.round_trip(s.dt[e].hour, s.dt[j_exit].hour) * px
        out.append({"symbol": sym, "entry_time": s.T[e], "exit_time": s.T[j_exit], "server_day": str(s.sday[j_exit]),
                    "R": (side * (exit_px - px) - cost) / dist, "exit": how, "stop_bp": dist / px * 1e4})
    return out


COMPONENTS = {
    "E5_XAUUSD_24": ("XAUUSD", EC.ev_fvg, 24),
    "E5_US500_48": ("US500", EC.ev_fvg, 48),
    "H7_XAUUSD_eod": ("XAUUSD", F3.ev_breakout_trend, "eod"),
}
BOOKS = {"H7_XAUUSD": ["H7_XAUUSD_eod"], "gold_both": ["H7_XAUUSD_eod", "E5_XAUUSD_24"],
         "all_three": ["H7_XAUUSD_eod", "E5_XAUUSD_24", "E5_US500_48"]}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    tr = {k: trades(*v) for k, v in COMPONENTS.items()}
    out = {"components": {k: FB.stats(v) for k, v in tr.items()}, "books": {}}
    for k, v in out["components"].items():
        print(k, {x: (round(y, 4) if isinstance(y, float) else y) for x, y in v.items() if x != "by_year_mean_R"}, flush=True)
    for name, comps in BOOKS.items():
        book = [t for c in comps for t in tr[c]]
        lo = max(min(t["entry_time"] for t in tr[c]) for c in comps)
        book = [t for t in book if t["entry_time"] >= lo]
        for r in RISKS:
            res = {"phase1_120d": FB.summarise_replay(FB.replay(book, r, 0.10, 120)),
                   "phase1_unlimited": FB.summarise_replay(FB.replay(book, r, 0.10, None)),
                   "phase2_unlimited": FB.summarise_replay(FB.replay(book, r, 0.05, None)), "span_from": lo}
            out["books"][f"{name}|{r}"] = res
            p1, pu = res["phase1_120d"], res["phase1_unlimited"]
            print(f"{name} r={r}: P1<=120d {p1['pass']:.2f} | P1 unlimited {pu['pass']:.2f} (fail {pu['fail']:.2f}, median "
                  f"{pu['median_days_to_pass']} d) | P2 {res['phase2_unlimited']['pass']:.2f}", flush=True)
    json.dump(out, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
