#!/usr/bin/env python3
"""FTMO pass-POLICY study (docs/plans/2026-10-02-pass-policy-preregistration.md): how the risk policy -- not the edge -- changes
the probability of being FUNDED (Phase 1 +10 %, then Phase 2 +5 %) within 3-4 months, on the real trade sequences of the
already-validated components (scripts/research/book_sim.py), never above the 1 % per-trade ceiling.

    python3 scripts/research/pass_policy.py run --out docs/audits/2026-10-02-pass-policy.json

Evidence, three ways (the policy is SELECTED on the first, CONFIRMED on the second, stress-tested on the third):
  1. historical replay, a challenge starting every Monday 2021-10 -> 2023-12 (selection starts),
  2. historical replay, starts 2024-01 -> end (confirmation starts; never used to choose),
  3. stationary block bootstrap of whole weekdays (mean block 20 weekdays), at the edge as measured AND with a 50 % haircut of
     every component's mean R (out-of-sample edges shrink; a policy that only works at full edge is not robust)."""
import argparse
import bisect
import collections
import datetime
import heapq
import importlib.util
import itertools
import json
import os
import random
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CEILING = 0.01
P1_TARGET, P2_TARGET, MAX_LOSS, DAILY_LOSS, MIN_DAYS = 0.10, 0.05, 0.10, 0.05, 4
HORIZONS = (91, 122)                     # calendar days: 3 and 4 months
RETRY_HORIZON = 122
P2_DELAY_DAYS = 1                        # Phase 2 starts the day after Phase 1 is passed
SELECT_END = "2024-01-01"
MAX_FAIL = 0.10                          # admissibility: first-attempt fail rate on the selection starts
BOOT_PATHS, BOOT_DAYS, BOOT_BLOCK, SEED = 3000, 300, 20, 20261002
HAIRCUT = 0.5

BOOKS = {
    "base3": ["H7_XAUUSD_eod", "E5_XAUUSD_24", "E5_US500_48"],
    "base3+G9au": ["H7_XAUUSD_eod", "E5_XAUUSD_24", "E5_US500_48", "G9_XAUUSD_eod"],
    "base3+G9au+G9ag": ["H7_XAUUSD_eod", "E5_XAUUSD_24", "E5_US500_48", "G9_XAUUSD_eod", "G9_XAGUSD_eod"],
}
RISKS = (0.005, 0.0075, 0.01)
THROTTLES = ("none", "dd3")              # dd3: x1 above 97 % of the initial balance, x0.5 down to 94 %, x0.25 below
DAY_STOPS = (None, 0.02)                 # no new entry on a server day whose realised P&L is <= -2 %
POLICIES = [dict(book=b, risk=r, throttle=t, day_stop=d) for b, r, t, d in itertools.product(BOOKS, RISKS, THROTTLES, DAY_STOPS)]


def policy_id(p):
    return f"{p['book']}|r{p['risk']}|{p['throttle']}|stop{p['day_stop']}"


def throttle_mult(kind, balance):
    if kind == "none":
        return 1.0
    if kind == "dd3":
        return 1.0 if balance > 0.97 else 0.5 if balance > 0.94 else 0.25
    raise ValueError(kind)


def _ts(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))


_ENTRIES = {}


def _entries(trades):
    key = id(trades)
    if key not in _ENTRIES or len(_ENTRIES[key][0]) != len(trades):
        _ENTRIES.clear() if len(_ENTRIES) > 64 else None
        _ENTRIES[key] = ([t["entry"] for t in trades], trades)
    return _ENTRIES[key][0]


def run_phase(trades, k, start, target, pol):
    """One phase on `trades` (sorted by entry, dicts with entry/exit datetimes, day keys, R) from index k / time `start`.
    Returns (outcome 'pass'|'fail'|'open', end datetime or None, next index). Balance in units of the initial balance;
    P&L realised at each trade's exit; fail on balance <= 1 - MAX_LOSS or a server day's realised loss <= -DAILY_LOSS.
    pol['floating'] == 'mae' (FTMO counts FLOATING P&L in both limits): at every entry, every open position -- the new one
    included -- is assumed to sit at its own worst excursion (mae_R) at the same moment; a breach of either limit by that
    bound fails the phase. An upper bound on fails (the worst points of different trades rarely coincide; gaps through a stop
    are already in mae_R)."""
    bal, days, day_pnl, pend = 1.0, set(), collections.defaultdict(float), []
    k = max(k, bisect.bisect_left(_entries(trades), start))

    def realise(until):
        nonlocal bal
        while pend and pend[0][0] <= until:
            x, _n, pnl, day, _m = heapq.heappop(pend)
            bal += pnl
            day_pnl[day] += pnl
            if bal <= 1.0 - MAX_LOSS or day_pnl[day] <= -DAILY_LOSS:
                return "fail", x
            if bal >= 1.0 + target and len(days) >= MIN_DAYS:
                return "pass", x
        return None

    n = 0
    while k < len(trades):
        t = trades[k]
        hit = realise(t["entry"])
        if hit:
            return hit[0], hit[1], k
        if pol["day_stop"] is None or day_pnl[t["entry_day"]] > -pol["day_stop"]:
            r = min(CEILING, pol["risk"] * throttle_mult(pol["throttle"], bal))
            n += 1
            heapq.heappush(pend, (t["exit"], n, r * t["R"], t["exit_day"], r * t.get("mae", min(0.0, t["R"]))))
            days.add(t["entry_day"])
            if pol.get("floating", "realised") == "mae":
                fl = sum(q[4] for q in pend)
                if bal + fl <= 1.0 - MAX_LOSS or day_pnl[t["exit_day"]] + fl <= -DAILY_LOSS:
                    return "fail", t["entry"], k + 1
        k += 1
    hit = realise(datetime.datetime.max.replace(tzinfo=datetime.timezone.utc))
    return (hit[0], hit[1], k) if hit else ("open", None, k)


def challenge(trades, start, pol, retry_horizon=None):
    """P1 then P2 from `start` -> {'funded_days' (None = not funded), 'attempts', 'first_fail'}. With retry: attempts restart the day after a
    fail until funded or `retry_horizon` days have passed."""
    attempts, t0 = 0, start
    while True:
        attempts += 1
        o1, e1, k = run_phase(trades, 0, t0, P1_TARGET, pol)
        if o1 == "pass":
            o2, e2, _ = run_phase(trades, 0, e1 + datetime.timedelta(days=P2_DELAY_DAYS), P2_TARGET, pol)
            if o2 == "pass":
                return {"funded_days": (e2 - start).days, "attempts": attempts, "first_fail": attempts > 1}
            end, failed_now = e2, o2 == "fail"
        else:
            end, failed_now = e1, o1 == "fail"
        if not failed_now or retry_horizon is None or (end - start).days >= retry_horizon:
            return {"funded_days": None, "attempts": attempts, "first_fail": attempts > 1 or failed_now}
        t0 = end + datetime.timedelta(days=1)


def summarise(results, retried):
    n = len(results)
    if not n:
        return {"n": 0}
    fd = [r["funded_days"] for r in results]
    out = {"n": n, "first_attempt_fail": sum(r["first_fail"] for r in results) / n,
           "median_days_to_funded": statistics.median([d for d in fd if d is not None]) if any(d is not None for d in fd) else None,
           "funded_ever": sum(d is not None for d in fd) / n}
    for h in HORIZONS:
        out[f"funded_le_{h}d"] = sum(d is not None and d <= h for d in fd) / n
    for h in HORIZONS:
        out[f"funded_le_{h}d_with_retry"] = sum(d is not None and d <= h for d in (r["funded_days"] for r in retried)) / n
    out["mean_attempts_within_retry_horizon"] = sum(r["attempts"] for r in retried) / n
    return out


def mondays(trades, lo, hi, tail_days=200):
    first = max(trades[0]["entry"].date(), datetime.date.fromisoformat(lo))
    last = min(trades[-1]["entry"].date() - datetime.timedelta(days=tail_days), datetime.date.fromisoformat(hi))
    d = first + datetime.timedelta(days=(7 - first.weekday()) % 7)
    while d <= last:
        yield datetime.datetime(d.year, d.month, d.day, tzinfo=datetime.timezone.utc)
        d += datetime.timedelta(days=7)


def prepare(raw, comps, haircut=0.0):
    """raw: {component: [book_sim trade rows]} -> one sorted list for the book; R shifted down by haircut x component mean."""
    out = []
    for c in comps:
        rows = raw[c]
        mu = sum(t["R"] for t in rows) / len(rows)
        for t in rows:
            e, x = _ts(t["entry_time"]), _ts(t["exit_time"])
            out.append({"entry": e, "exit": x, "entry_day": t["entry_time"][:10], "exit_day": t["server_day"],
                        "R": t["R"] - haircut * mu, "mae": t.get("mae_R", min(0.0, t["R"])), "c": c})
    out.sort(key=lambda t: (t["entry"], t["c"]))
    return out


def bootstrap_paths(trades, n_paths, n_days, block, seed):
    """Stationary block bootstrap of WEEKDAYS (empty weekdays included): each path is a list of synthetic trades on consecutive
    synthetic weekdays from 2001-01-01, every trade keeping its time of day and holding time."""
    by_day = collections.defaultdict(list)
    for t in trades:
        by_day[t["entry"].date()].append(t)
    d0, d1 = trades[0]["entry"].date(), trades[-1]["entry"].date()
    weekdays = [d0 + datetime.timedelta(days=i) for i in range((d1 - d0).days + 1)]
    weekdays = [d for d in weekdays if d.weekday() < 5]
    rng = random.Random(seed)
    base = datetime.datetime(2001, 1, 1, tzinfo=datetime.timezone.utc)          # a Monday
    for _ in range(n_paths):
        path, j, pos = [], rng.randrange(len(weekdays)), 0
        while pos < n_days:
            if pos and rng.random() < 1.0 / block:
                j = rng.randrange(len(weekdays))
            src = weekdays[j % len(weekdays)]
            week, wd = divmod(pos, 5)
            day = base + datetime.timedelta(days=7 * week + wd)
            for t in by_day.get(src, ()):
                off = t["entry"] - datetime.datetime(src.year, src.month, src.day, tzinfo=datetime.timezone.utc)
                e = day + off
                x = e + (t["exit"] - t["entry"])
                path.append(dict(t, entry=e, exit=x, entry_day=e.date().isoformat(), exit_day=x.date().isoformat()))
            j += 1
            pos += 1
        path.sort(key=lambda t: (t["entry"], t["c"]))
        yield base, path


def evaluate_hist(trades, pol, lo, hi):
    starts = list(mondays(trades, lo, hi))
    plain = [challenge(trades, s, pol) for s in starts]
    retried = [challenge(trades, s, pol, RETRY_HORIZON) for s in starts]
    return summarise(plain, retried)


def evaluate_boot(trades, pol, haircut_trades=None):
    out = {}
    for name, tr in (("edge_as_measured", trades), ("edge_haircut_50pct", haircut_trades)):
        if tr is None:
            continue
        plain, retried = [], []
        for base, path in bootstrap_paths(tr, BOOT_PATHS, BOOT_DAYS, BOOT_BLOCK, SEED):
            plain.append(challenge(path, base, pol))
            retried.append(challenge(path, base, pol, RETRY_HORIZON))
        out[name] = summarise(plain, retried)
    return out


def load_raw():
    spec = importlib.util.spec_from_file_location("book_sim", os.path.join(ROOT, "scripts", "research", "book_sim.py"))
    BS = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(BS)
    names = sorted({c for v in BOOKS.values() for c in v})
    return {k: BS.trades(*BS.COMPONENTS[k]) for k in names}


def run(out_path, raw=None, floating="realised"):
    raw = raw or load_raw()
    span_from = max(min(t["entry_time"] for t in raw[c]) for c in raw)
    raw = {c: [t for t in v if t["entry_time"] >= span_from] for c, v in raw.items()}
    res = {"meta": {"floating": floating, "span_from": span_from, "select_end": SELECT_END, "policies": len(POLICIES), "max_fail": MAX_FAIL,
                    "bootstrap": {"paths": BOOT_PATHS, "days": BOOT_DAYS, "block": BOOT_BLOCK, "seed": SEED, "haircut": HAIRCUT}},
           "selection": {}, "confirmation": {}, "bootstrap": {}}
    books = {b: prepare(raw, c) for b, c in BOOKS.items()}
    for p in POLICIES:
        p = dict(p, floating=floating)
        pid = policy_id(p)
        res["selection"][pid] = evaluate_hist(books[p["book"]], p, "2000-01-01", SELECT_END)
        res["confirmation"][pid] = evaluate_hist(books[p["book"]], p, SELECT_END, "2100-01-01")
        print(pid, "sel 122d", round(res["selection"][pid]["funded_le_122d"], 3), "fail", round(res["selection"][pid]["first_attempt_fail"], 3),
              "| conf 122d", round(res["confirmation"][pid]["funded_le_122d"], 3), flush=True)
    admissible = [p for p in POLICIES if res["selection"][policy_id(p)]["first_attempt_fail"] <= MAX_FAIL]
    best = max(admissible, key=lambda p: (res["selection"][policy_id(p)]["funded_le_122d"], -res["selection"][policy_id(p)]["first_attempt_fail"]))
    best_retry = max(POLICIES, key=lambda p: res["selection"][policy_id(p)]["funded_le_122d_with_retry"])
    admissible = [dict(p, floating=floating) for p in admissible]
    best = dict(best, floating=floating)
    best_retry = dict(best_retry, floating=floating)
    reference = dict(book="base3", risk=0.01, throttle="none", day_stop=None, floating=floating)
    res["chosen"] = {"no_retry": policy_id(best), "with_retry": policy_id(best_retry), "reference": policy_id(reference)}
    for p in {policy_id(x): x for x in (best, best_retry, reference)}.values():
        res["bootstrap"][policy_id(p)] = evaluate_boot(books[p["book"]], p, prepare(raw, BOOKS[p["book"]], HAIRCUT))
        print("bootstrap", policy_id(p), json.dumps(res["bootstrap"][policy_id(p)]), flush=True)
    json.dump(res, open(out_path, "w"), indent=1)
    print(f"wrote {out_path}; chosen {res['chosen']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--out", required=True)
    r.add_argument("--floating", choices=("realised", "mae"), default="realised")
    a = ap.parse_args()
    run(a.out, floating=a.floating)


if __name__ == "__main__":
    main()
