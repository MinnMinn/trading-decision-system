#!/usr/bin/env python3
"""A1 -- phase-aware volatility through the stop width (docs/plans/2026-10-03-vol-schedule-preregistration.md).
DESCRIPTIVE / EXPOSED: the H7 / G9 XAUUSD trade sequences were already read. Base = fvg-book v3 (H7 + G9 XAUUSD, 1 % of the
initial balance at the stop, dd3). A policy (k_P1, k_P2) runs Phase 1 with the protective stop at k_P1 x sigma_5m x
sqrt(hold) and Phase 2 at k_P2; the funded stage always at the reference k = 2.0.

    python3 scripts/research/vol_schedule.py --out docs/audits/2026-10-03-vol-schedule.json

Measured per policy: pass_policy's historical starts (selection < 2024, confirmation >= 2024; floating `mae` and realised),
a stationary block bootstrap that resamples weekdays ONCE per path and replays every k on the same days, the value objective
E[payouts + fee refund - fees] inside a 252-weekday horizon at edge x {1, 0.5, 0}, and the stop-gap tails per k."""
import argparse
import bisect
import collections
import datetime
import heapq
import importlib.util
import json
import os
import random
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


BS = _load("book_sim", "scripts/research/book_sim.py")
PP = _load("pass_policy", "scripts/research/pass_policy.py")
COMPS = ["H7_XAUUSD_eod", "G9_XAUUSD_eod"]
KS = (2.0, 1.4, 1.0)
POLICIES = [(2.0, 2.0), (2.0, 1.4), (2.0, 1.0), (1.4, 2.0), (1.4, 1.4), (1.4, 1.0)]
REFERENCE = (2.0, 2.0)
EDGE_MULTS = (1.0, 0.5, 0.0)                    # haircut = 1 - mult
HORIZON_DAYS = 353                              # 252 weekdays in calendar days (bootstrap paths have no holidays)
FEE, SPLIT, PAYOUT_DAYS = 0.006, 0.80, 30       # NAMED owner inputs with stated defaults (pre-registration §3.2)
BOOT_PATHS, BOOT_DAYS, BOOT_BLOCK, SEED = PP.BOOT_PATHS, PP.BOOT_DAYS, PP.BOOT_BLOCK, PP.SEED
GAP_TOLERANCE = 0.012                            # worst single-trade loss, % of the initial balance (decision rule)
MAX_FAIL = 0.10


def pol(fl):
    return dict(book="v3", risk=0.01, throttle="dd3", day_stop=None, floating=fl)


# ------------------------------------------------------------------------------------------------ trades
def raw_trades():
    """{k: {component: [book_sim rows]}} -- same events for every k, only the stop (and so size, exit and R) differs."""
    out = {k: {c: BS.trades(*BS.COMPONENTS[c], stop_k=k) for c in COMPS} for k in KS}
    for c in COMPS:
        ents = {k: [t["entry_time"] for t in out[k][c]] for k in KS}
        if len({tuple(v) for v in ents.values()}) != 1:
            raise SystemExit(f"{c}: the entries differ between stop widths -- the stop must not change which trades exist")
    return out


def views(raw, haircut):
    return {k: PP.prepare(raw[k], COMPS, haircut) for k in KS}


# ------------------------------------------------------------------------------------------------ challenge, two stops
def challenge2(t1, t2, start, p, retry_horizon=None, end=None):
    """PP.challenge with Phase 1 on `t1` and Phase 2 on `t2`. -> {funded_at, attempts, first_fail, fees}."""
    attempts, t0 = 0, start
    while True:
        if end is not None and t0 >= end:
            return {"funded_at": None, "attempts": attempts, "first_fail": attempts > 1}
        attempts += 1
        o1, e1, _ = PP.run_phase(t1, 0, t0, PP.P1_TARGET, p)
        if o1 == "pass":
            o2, e2, _ = PP.run_phase(t2, 0, e1 + datetime.timedelta(days=PP.P2_DELAY_DAYS), PP.P2_TARGET, p)
            if o2 == "pass" and (end is None or e2 < end):
                return {"funded_at": e2, "attempts": attempts, "first_fail": attempts > 1}
            stop_at, failed = e2, o2 == "fail"
        else:
            stop_at, failed = e1, o1 == "fail"
        if not failed or stop_at is None or retry_horizon is None or (stop_at - start).days >= retry_horizon:
            return {"funded_at": None, "attempts": attempts, "first_fail": attempts > 1 or failed}
        t0 = stop_at + datetime.timedelta(days=1)


def funded_stage(trades, start, end, p):
    """Payouts of a funded account from `start` to `end` on `trades` (reference stop): monthly SPLIT x profit above the
    initial balance, balance reset; ends at the first -5 % day / -10 % total (floating `mae` bound at entries as run_phase).
    -> (payouts, breached)."""
    bal, day_pnl, pend, paid, n = 1.0, collections.defaultdict(float), [], 0.0, 0
    next_pay = start + datetime.timedelta(days=PAYOUT_DAYS)
    k = bisect.bisect_left(PP._entries(trades), start)

    def settle(until):
        nonlocal bal, paid, next_pay
        while True:
            x = pend[0][0] if pend else None
            if next_pay <= until and (x is None or next_pay <= x):
                if bal > 1.0:
                    paid += SPLIT * (bal - 1.0)
                    bal = 1.0
                next_pay += datetime.timedelta(days=PAYOUT_DAYS)
                continue
            if x is None or x > until:
                return False
            _x, _n, pnl, day, _m = heapq.heappop(pend)
            bal += pnl
            day_pnl[day] += pnl
            if bal <= 1.0 - PP.MAX_LOSS or day_pnl[day] <= -PP.DAILY_LOSS:
                return True

    while k < len(trades) and trades[k]["entry"] < end:
        t = trades[k]
        if settle(t["entry"]):
            return paid, True
        r = min(PP.CEILING, p["risk"] * PP.throttle_mult(p["throttle"], bal))
        n += 1
        heapq.heappush(pend, (t["exit"], n, r * t["R"], t["exit_day"], r * t.get("mae", min(0.0, t["R"]))))
        fl = sum(q[4] for q in pend)
        if bal + fl <= 1.0 - PP.MAX_LOSS or day_pnl[t["exit_day"]] + fl <= -PP.DAILY_LOSS:
            return paid, True
        k += 1
    return paid, settle(end)


def value(t1, t2, tf, start, p):
    """One horizon: challenge (retries cost fees) then funded stage on the reference stop until the horizon ends."""
    end = start + datetime.timedelta(days=HORIZON_DAYS)
    c = challenge2(t1, t2, start, p, retry_horizon=HORIZON_DAYS, end=end)
    fees = FEE * c["attempts"]
    paid, breached = (0.0, False) if c["funded_at"] is None else funded_stage(tf, c["funded_at"] + datetime.timedelta(days=1), end, p)
    refund = FEE if paid > 0 else 0.0
    return {"net": paid + refund - fees, "paid": paid, "fees": fees, "funded": c["funded_at"] is not None,
            "funded_days": None if c["funded_at"] is None else (c["funded_at"] - start).days, "breached": breached}


# ------------------------------------------------------------------------------------------------ bootstrap, aligned days
def sample_days(weekdays, rng):
    out, j = [], rng.randrange(len(weekdays))
    for pos in range(BOOT_DAYS):
        if pos and rng.random() < 1.0 / BOOT_BLOCK:
            j = rng.randrange(len(weekdays))
        out.append(weekdays[j % len(weekdays)])
        j += 1
    return out


def build_path(by_day, src_days, base):
    path = []
    for pos, src in enumerate(src_days):
        week, wd = divmod(pos, 5)
        day = base + datetime.timedelta(days=7 * week + wd)
        for t in by_day.get(src, ()):
            off = t["entry"] - datetime.datetime(src.year, src.month, src.day, tzinfo=datetime.timezone.utc)
            e = day + off
            x = e + (t["exit"] - t["entry"])
            path.append(dict(t, entry=e, exit=x, entry_day=e.date().isoformat(), exit_day=x.date().isoformat()))
    path.sort(key=lambda t: (t["entry"], t["c"]))
    return path


def bootstrap(views_by_k, p):
    """{policy: summary} with every policy replayed on the SAME sampled days."""
    any_k = views_by_k[KS[0]]
    d0, d1 = any_k[0]["entry"].date(), any_k[-1]["entry"].date()
    weekdays = [d0 + datetime.timedelta(days=i) for i in range((d1 - d0).days + 1)]
    weekdays = [d for d in weekdays if d.weekday() < 5]
    by_day = {k: collections.defaultdict(list) for k in KS}
    for k in KS:
        for t in views_by_k[k]:
            by_day[k][t["entry"].date()].append(t)
    rng = random.Random(SEED)
    base = datetime.datetime(2001, 1, 1, tzinfo=datetime.timezone.utc)
    acc = {pp: collections.defaultdict(list) for pp in POLICIES}
    for _ in range(BOOT_PATHS):
        src = sample_days(weekdays, rng)
        paths = {k: build_path(by_day[k], src, base) for k in KS}
        for (k1, k2) in POLICIES:
            c = challenge2(paths[k1], paths[k2], base, p)
            v = value(paths[k1], paths[k2], paths[2.0], base, p)
            a = acc[(k1, k2)]
            a["funded_122"].append(c["funded_at"] is not None and (c["funded_at"] - base).days <= 122)
            a["first_fail"].append(c["first_fail"])
            for key in ("net", "paid", "fees"):
                a[key].append(v[key])
            a["funded_h"].append(v["funded"])
            a["breached"].append(v["breached"])
    out = {}
    for pp, a in acc.items():
        out[f"{pp[0]}/{pp[1]}"] = {"funded_le_122d": statistics.mean(a["funded_122"]),
                                    "first_attempt_fail": statistics.mean(a["first_fail"]),
                                    "E_net_pct": 100 * statistics.mean(a["net"]), "E_paid_pct": 100 * statistics.mean(a["paid"]),
                                    "E_fees_pct": 100 * statistics.mean(a["fees"]),
                                    "funded_within_horizon": statistics.mean(a["funded_h"]),
                                    "funded_breach_within_horizon": statistics.mean(a["breached"])}
    return out


def historical(v, p, lo, hi):
    starts = list(PP.mondays(v[KS[0]], lo, hi))
    res = {}
    for (k1, k2) in POLICIES:
        cs = [challenge2(v[k1], v[k2], s, p) for s in starts]
        fd = [None if c["funded_at"] is None else (c["funded_at"] - s).days for c, s in zip(cs, starts)]
        res[f"{k1}/{k2}"] = {"n": len(cs), "funded_le_122d": sum(d is not None and d <= 122 for d in fd) / len(cs),
                             "funded_ever": sum(d is not None for d in fd) / len(cs),
                             "median_days_to_funded": statistics.median([d for d in fd if d is not None]) if any(d is not None for d in fd) else None,
                             "first_attempt_fail": sum(c["first_fail"] for c in cs) / len(cs)}
    return res


def tails(raw):
    out = {}
    for k in KS:
        rows = [t for c in COMPS for t in raw[k][c]]
        out[str(k)] = {"trades": len(rows), "mean_R": statistics.mean(t["R"] for t in rows),
                       "sd_R": statistics.pstdev(t["R"] for t in rows),
                       "stop_share": sum(t["exit"] == "stop" for t in rows) / len(rows),
                       "gap_beyond_1R_share": sum(t["mae_R"] < -1.0 for t in rows) / len(rows),
                       "worst_trade_loss_pct_of_initial": -100 * PP.CEILING * min(t["R"] for t in rows)}
    return out


def run(out_path):
    raw = raw_trades()
    res = {"meta": {"script": "scripts/research/vol_schedule.py", "status": "DESCRIPTIVE / EXPOSED",
                    "preregistration": "docs/plans/2026-10-03-vol-schedule-preregistration.md", "components": COMPS,
                    "policies": [f"{a}/{b}" for a, b in POLICIES], "fee": FEE, "split": SPLIT, "payout_days": PAYOUT_DAYS,
                    "horizon_days": HORIZON_DAYS, "bootstrap": {"paths": BOOT_PATHS, "days": BOOT_DAYS, "block": BOOT_BLOCK,
                                                               "seed": SEED}},
           "tails": tails(raw), "historical": {}, "bootstrap": {}}
    base_views = views(raw, 0.0)
    for fl in ("mae", "realised"):
        res["historical"][fl] = {"selection": historical(base_views, pol(fl), "2000-01-01", PP.SELECT_END),
                                 "confirmation": historical(base_views, pol(fl), PP.SELECT_END, "2100-01-01")}
    for m in EDGE_MULTS:
        res["bootstrap"][f"edge_x{m}"] = bootstrap(views(raw, 1.0 - m), pol("mae"))
        print(f"edge x{m}:", {k: (round(v['funded_le_122d'], 3), round(v['first_attempt_fail'], 3), round(v['E_net_pct'], 2))
                              for k, v in res["bootstrap"][f"edge_x{m}"].items()}, flush=True)
    ref = f"{REFERENCE[0]}/{REFERENCE[1]}"
    conf = res["historical"]["mae"]["confirmation"]
    decisions = {}
    for (k1, k2) in POLICIES:
        key = f"{k1}/{k2}"
        if key == ref:
            continue
        b5, b0, b1 = (res["bootstrap"][f"edge_x{m}"][key] for m in (0.5, 0.0, 1.0))
        worst = max(res["tails"][str(k)]["worst_trade_loss_pct_of_initial"] for k in (k1, k2))
        d_half = b5["E_net_pct"] - res["bootstrap"]["edge_x0.5"][ref]["E_net_pct"]
        d_zero = b0["E_net_pct"] - res["bootstrap"]["edge_x0.0"][ref]["E_net_pct"]
        ok = d_half > 0 and conf[key]["first_attempt_fail"] <= MAX_FAIL and b5["first_attempt_fail"] <= MAX_FAIL and worst <= 100 * GAP_TOLERANCE
        decisions[key] = {"delta_E_net_pct_haircut50": d_half, "delta_E_net_pct_edge0": d_zero,
                          "delta_E_net_pct_edge1": b1["E_net_pct"] - res["bootstrap"]["edge_x1.0"][ref]["E_net_pct"],
                          "confirmation_first_fail": conf[key]["first_attempt_fail"], "haircut_boot_first_fail": b5["first_attempt_fail"],
                          "worst_trade_loss_pct": worst, "PROPOSED": bool(ok), "variance_not_edge": bool(ok and d_zero > 0)}
    res["decisions"] = decisions
    json.dump(res, open(out_path, "w"), indent=1, default=str)
    for k, v in decisions.items():
        print(k, {a: (round(b, 3) if isinstance(b, float) else b) for a, b in v.items()})
    print(f"wrote {out_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    run(a.out)


if __name__ == "__main__":
    main()
