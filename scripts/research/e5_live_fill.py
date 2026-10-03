#!/usr/bin/env python3
"""E5 live-fill re-simulation (docs/plans/2026-10-03-e5-live-fill-preregistration.md). DESCRIPTIVE / EXPOSED: every bar was
already read to design E5; this checks whether the E5 LONG order the demo actually sends (a BUY LIMIT at the bid-derived edge,
triggered on the ASK -- scripts/fvg_demo.py) trades the population the research measured (filled when the BID touches).

    python3 scripts/research/e5_live_fill.py --out docs/audits/2026-10-03-e5-live-fill.json

Rules (longs; shorts always use the research rule): `research` (bid low <= edge, one spread charged), `live` (bid low +
spread <= edge, ask paid), `plus_spread` (a buy limit at edge + the placement-hour spread, ask paid). Spread = the median
relative spread of the bar's UTC hour (ftmo_demo_2026_09_relspread) x price x sx, sx in {0.5, 1, 2}. Trade mechanics are
scripts/research/book_sim.py's, unchanged; the v2 book is replayed with scripts/research/pass_policy.py's own functions."""
import argparse
import collections
import importlib.util
import json
import math
import os
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


BS = _load("book_sim", "scripts/research/book_sim.py")
PP = _load("pass_policy", "scripts/research/pass_policy.py")
EC = BS.EC
RULES = ("research", "live", "plus_spread")
SPREAD_X = (0.5, 1.0, 2.0)
E5 = {"E5_XAUUSD_24": ("XAUUSD", 24), "E5_US500_48": ("US500", 48)}
V2 = ["H7_XAUUSD_eod", "G9_XAUUSD_eod", "E5_XAUUSD_24", "E5_US500_48"]
BOOK_SPAN_FROM = "2021-10-12"


def fill(s, costs, m, side, edge, rule, sx):
    """(bar j, entry price, cost mode) of the gap with middle bar m under `rule`, or None. cost mode 'spread' = one round-trip
    spread charged on top (research convention); 'paid' = the ask was paid at entry, the exit is at the bid."""
    n = len(s.C)
    if m + 2 >= n:
        return None
    sp_p = costs.med[s.dt[m + 2].hour] * edge * sx
    for j in range(m + 2, min(n, m + 2 + EC.FVG_TOUCH_BARS)):
        if s.sday[j] != s.sday[m]:
            return None
        if side < 0 or rule == "research":
            if (side > 0 and s.L[j] <= edge) or (side < 0 and s.H[j] >= edge):
                return j, (min(edge, s.O[j]) if side > 0 else max(edge, s.O[j])), "spread"
            continue
        sp_j = costs.med[s.dt[j].hour] * edge * sx
        lim = edge if rule == "live" else edge + sp_p
        if s.L[j] + sp_j <= lim:
            return j, min(lim, s.O[j] + sp_j), "paid"
    return None


def outcome(s, costs, e, px, side, hold, sig, mode, sx):
    """book_sim.trades' mechanics for one entry: stop 2 x sigma x sqrt(hold) from px, time exit, same server day."""
    x = e + hold - 1
    if x >= len(s.C) or s.sday[x] != s.sday[e]:
        return None
    dist = 2.0 * sig * math.sqrt(x - e + 1) * px
    stop = px - side * dist
    exit_px, how, j_exit, worst = s.C[x], "time", x, 0.0
    for j in range(e, x + 1):
        if (s.L[j] <= stop) if side > 0 else (s.H[j] >= stop):
            exit_px = (min(stop, s.O[j]) if side > 0 else max(stop, s.O[j])) if j > e else stop
            how, j_exit = "stop", j
            worst = min(worst, side * (exit_px - px))
            break
        worst = min(worst, side * ((s.L[j] if side > 0 else s.H[j]) - px))
    cost = costs.round_trip(s.dt[e].hour, s.dt[j_exit].hour) * px * sx if mode == "spread" else 0.0
    return {"entry_time": s.T[e], "exit_time": s.T[j_exit], "server_day": str(s.sday[j_exit]), "side": side,
            "R": (side * (exit_px - px) - cost) / dist, "mae_R": (worst - cost) / dist, "exit": how,
            "net_bp": (side * (exit_px - px) - cost) / px * 1e4}


def trades(s, costs, hold, rule, sx):
    """First FILLED gap per (server day, side) -- the demo executor's selection (siblings cancel on the first fill)."""
    best = {}
    eligible = collections.Counter()
    for m in range(1, len(s.C) - 2):
        g = EC.fvg_gap_at(s, m)
        if g is None:
            continue
        side, edge, _far = g
        sig = s.sigma(m + 1)
        if not sig:
            continue
        eligible[side] += 1
        f = fill(s, costs, m, side, edge, rule, sx)
        if f is None:
            continue
        key = (s.sday[m], side)
        if key not in best or (f[0], m) < (best[key][0], best[key][3]):
            best[key] = (f[0], f[1], f[2], m, sig)
    out = []
    for (_d, side), (j, px, mode, _m, sig) in sorted(best.items(), key=lambda kv: kv[1][0]):
        o = outcome(s, costs, j, px, side, hold, sig, mode, sx)
        if o is not None:
            out.append(o)
    return out, dict(eligible)


def stats(rows, eligible=None):
    if not rows:
        return {"n": 0}
    r = [t["R"] for t in rows]
    by_year = collections.defaultdict(list)
    for t in rows:
        by_year[t["entry_time"][:4]].append(t["R"])
    out = {"n": len(r), "mean_R": statistics.mean(r), "sd_R": statistics.pstdev(r),
           "mean_net_bp": statistics.mean(t["net_bp"] for t in rows) if "net_bp" in rows[0] else None,
           "stop_share": sum(t["exit"] == "stop" for t in rows) / len(rows),
           "by_year_mean_R": {y: round(statistics.mean(v), 4) for y, v in sorted(by_year.items())}}
    if eligible:
        out["fill_rate"] = len(rows) / eligible
    return out


def per_side(rows, elig, span_from=None):
    out = {}
    for side, name in ((1, "long"), (-1, "short")):
        rs = [t for t in rows if t["side"] == side and (span_from is None or t["entry_time"] >= span_from)]
        out[name] = stats(rs, None if span_from else elig.get(side))
    return out


def run(out_path, boot=True):
    res = {"meta": {"script": "scripts/research/e5_live_fill.py", "status": "DESCRIPTIVE / EXPOSED",
                    "preregistration": "docs/plans/2026-10-03-e5-live-fill-preregistration.md", "rules": RULES,
                    "spread_x": SPREAD_X, "book_span_from": BOOK_SPAN_FROM, "cost_profile": EC.COST_PROFILE},
           "components": {}, "book": {}}
    e5 = {}
    for comp, (sym, hold) in E5.items():
        s = EC.load(sym, end=BS.END)
        costs = EC.Costs(sym)
        ref = BS.trades(*BS.COMPONENTS[comp])               # both sides together (book_sim rows carry no side)
        res["components"][comp] = {"book_sim_reference": {"all": stats(ref), "span": stats([t for t in ref if t["entry_time"] >= BOOK_SPAN_FROM])}}
        for rule in RULES:
            for sx in SPREAD_X:
                rows, elig = trades(s, costs, hold, rule, sx)
                res["components"][comp][f"{rule}|x{sx}"] = {"all": per_side(rows, elig), "span": per_side(rows, elig, BOOK_SPAN_FROM),
                                                            "both_sides_span": stats([t for t in rows if t["entry_time"] >= BOOK_SPAN_FROM])}
                if sx == 1.0:
                    e5[(comp, rule)] = rows
                L = res["components"][comp][f"{rule}|x{sx}"]["span"]["long"]
                S_ = res["components"][comp][f"{rule}|x{sx}"]["span"]["short"]
                print(f"{comp} {rule:12s} x{sx}: span long n {L.get('n')} mean R {L.get('mean_R', 0):+.4f} "
                      f"bp {L.get('mean_net_bp', 0):+.2f} | short n {S_.get('n')} mean R {S_.get('mean_R', 0):+.4f}", flush=True)
    base = {k: BS.trades(*BS.COMPONENTS[k]) for k in ("H7_XAUUSD_eod", "G9_XAUUSD_eod")}
    for rule in ("book_sim_reference",) + RULES:
        raw = dict(base)
        for comp in E5:
            raw[comp] = BS.trades(*BS.COMPONENTS[comp]) if rule == "book_sim_reference" else e5[(comp, rule)]
        span_from = max(min(t["entry_time"] for t in raw[c]) for c in V2)
        raw = {c: [t for t in v if t["entry_time"] >= span_from] for c, v in raw.items()}
        book = PP.prepare(raw, V2)
        mu, sd, sh = BS.daily_profile([t for c in V2 for t in raw[c]])
        row = {"span_from": span_from, "daily_mean_R": mu, "daily_sd_R": sd, "daily_sharpe": sh,
               "R_by_component": {c: round(sum(t["R"] for t in raw[c]), 2) for c in V2}}
        for fl in ("mae", "realised"):
            pol = dict(book="v2", risk=0.01, throttle="dd3", day_stop=None, floating=fl)
            row[fl] = {"selection": PP.evaluate_hist(book, pol, "2000-01-01", PP.SELECT_END),
                       "confirmation": PP.evaluate_hist(book, pol, PP.SELECT_END, "2100-01-01")}
            if boot and fl == "mae":
                row[fl]["bootstrap"] = PP.evaluate_boot(book, pol, PP.prepare(raw, V2, PP.HAIRCUT))
        res["book"][rule] = row
        c = row["mae"]["confirmation"]
        print(f"v2 with E5={rule}: Sharpe {sh:.2f} | conf funded<=122d {c['funded_le_122d']:.3f} fail {c['first_attempt_fail']:.3f}"
              + (f" | boot {row['mae']['bootstrap']['edge_as_measured']['funded_le_122d']:.3f} / haircut "
                 f"{row['mae']['bootstrap']['edge_haircut_50pct']['funded_le_122d']:.3f}" if boot else ""), flush=True)
    json.dump(res, open(out_path, "w"), indent=1)
    print(f"wrote {out_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-bootstrap", action="store_true")
    a = ap.parse_args()
    run(a.out, boot=not a.no_bootstrap)


if __name__ == "__main__":
    main()
