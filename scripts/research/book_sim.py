#!/usr/bin/env python3
"""Book design for every component that has survived its pre-registered reads (DESIGN on already-read history; the forward
stage validates): F2 E5 FVG retrace (XAUUSD 24 bars, US500 48 bars) and F3 H7 breakout-with-trend (XAUUSD, to the end of the
server day). Same trade mechanics and FTMO replay as scripts/research/fvg_book_sim.py (whose functions it reuses): protective
stop 2 x sigma_5m x sqrt(hold bars), time exit, flat before the rollover, relative spread cost, R = net P&L / stop distance.

    python3 scripts/research/book_sim.py --out docs/audits/2026-10-02-book-sim.json
    python3 scripts/research/book_sim.py compare --variant NAME=COMP+COMP ... --out <json>

`compare` replays the BASELINE book (docs/architecture/book-baseline.json) and every variant on the SAME common span (the latest
first trade among all the components involved), at the baseline's risk, and reports each added component's daily-R correlation
with the baseline book (independence is what shortens the time to pass without raising per-trade risk)."""
import argparse
import collections
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
F4 = _load("edge_f4", "scripts/research/edge_f4.py")
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
    # F4 survivors (docs/audits/2026-10-02-edge-f4.md): volatility breakout, to the end of the server day
    "G9_XAUUSD_eod": ("XAUUSD", F4.ev_vol_breakout, "eod"),
    "G9_XAGUSD_eod": ("XAGUSD", F4.ev_vol_breakout, "eod"),
}
BOOKS = {"H7_XAUUSD": ["H7_XAUUSD_eod"], "gold_both": ["H7_XAUUSD_eod", "E5_XAUUSD_24"],
         "all_three": ["H7_XAUUSD_eod", "E5_XAUUSD_24", "E5_US500_48"]}


BASELINE_PATH = os.path.join(ROOT, "docs", "architecture", "book-baseline.json")


def daily_r(tr):
    out = collections.defaultdict(float)
    for t in tr:
        out[t["server_day"]] += t["R"]
    return out


def corr(a, b):
    """Pearson correlation of two daily-R maps over the union of their days (a day without trades is 0 R)."""
    days = sorted(set(a) | set(b))
    if len(days) < 3:
        return None
    x, y = [a.get(d, 0.0) for d in days], [b.get(d, 0.0) for d in days]
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sxy = sum((u - mx) * (v - my) for u, v in zip(x, y))
    sx, sy = sum((u - mx) ** 2 for u in x) ** 0.5, sum((v - my) ** 2 for v in y) ** 0.5
    return sxy / (sx * sy) if sx and sy else None


def daily_profile(book):
    """(mean, sd, annualised Sharpe) of the book's per-server-day R sum over its ACTIVE days -- the drift / volatility that
    sets the FTMO barrier race (pass speed at a fixed fail rate)."""
    v = list(daily_r(book).values())
    if len(v) < 2:
        return None, None, None
    mu = sum(v) / len(v)
    sd = (sum((x - mu) ** 2 for x in v) / (len(v) - 1)) ** 0.5
    return mu, sd, (mu / sd * 252 ** 0.5 if sd else None)


def book_result(tr, comps, lo, risk):
    book = [t for c in comps for t in tr[c] if t["entry_time"] >= lo]
    mu, sd, sh = daily_profile(book)
    p1, pc, p2 = (FB.summarise_replay(FB.replay(book, risk, 0.10, None)), FB.summarise_replay(FB.replay(book, risk, 0.10, 120)),
                  FB.summarise_replay(FB.replay(book, risk, 0.05, None)))
    return {"components": comps, "risk_pct": risk, "trades": len(book), "daily_mean_R": mu, "daily_sd_R": sd, "daily_sharpe": sh,
            "phase1_unlimited": p1, "phase1_120d": pc, "phase2_unlimited": p2}


def compare(variants, out_path):
    base = json.load(open(BASELINE_PATH))
    risk, bcomps = base["risk_pct"], base["components"]
    names = sorted({c for v in variants.values() for c in v} | set(bcomps))
    tr = {k: trades(*COMPONENTS[k]) for k in names}
    lo = max(min(t["entry_time"] for t in tr[c]) for c in names)
    span = {k: [t for t in v if t["entry_time"] >= lo] for k, v in tr.items()}
    bd = daily_r([t for c in bcomps for t in span[c]])
    out = {"baseline": dict(book_result(tr, bcomps, lo, risk), name=base["name"]), "span_from": lo, "risk_pct": risk,
           "components": {k: dict(FB.stats(v), corr_with_baseline=None if k in bcomps else corr(daily_r(v), bd))
                          for k, v in span.items()},
           "variants": {n: book_result(tr, c, lo, risk) for n, c in variants.items()}}
    # the SAME risk budget: per-trade risk scaled so the variant's daily-R volatility equals the baseline's (never above it)
    bsd = out["baseline"]["daily_sd_R"]
    out["variants_vol_matched"] = {}
    for n, c in variants.items():
        vsd = out["variants"][n]["daily_sd_R"]
        r = min(risk, risk * bsd / vsd) if vsd else risk
        out["variants_vol_matched"][n] = book_result(tr, c, lo, round(r, 5))
    line = lambda n, r: (f"{n:28s} risk {r['risk_pct']:.4f} trades {r['trades']:5d} | Sharpe/d {r['daily_sharpe']:.2f} | P1 {r['phase1_unlimited']['pass']:.2f} fail "
                         f"{r['phase1_unlimited']['fail']:.2f} median {r['phase1_unlimited']['median_days_to_pass']} d | "
                         f"P1<=120d {r['phase1_120d']['pass']:.2f} | P2 {r['phase2_unlimited']['pass']:.2f}")
    print(f"span from {lo}, risk {risk}")
    print(line("BASELINE " + base["name"], out["baseline"]))
    for n, r in out["variants"].items():
        print(line(n, r))
    print("vol-matched (same daily risk as the baseline):")
    for n, r in out["variants_vol_matched"].items():
        print(line(n, r))
    for k, v in out["components"].items():
        print(f"  {k:24s} n {v['n']:5d} mean R {v['mean_R']:+.4f} corr {v['corr_with_baseline']}")
    json.dump(out, open(out_path, "w"), indent=1)


def main():
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "compare":
        ap = argparse.ArgumentParser(description="compare variant books with the baseline")
        ap.add_argument("cmd")
        ap.add_argument("--variant", action="append", required=True, help="NAME=COMP+COMP")
        ap.add_argument("--out", required=True)
        a = ap.parse_args()
        compare({v.split("=", 1)[0]: v.split("=", 1)[1].split("+") for v in a.variant}, a.out)
        return
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
