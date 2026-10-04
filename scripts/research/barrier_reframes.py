#!/usr/bin/env python3
"""Synthetic FTMO barrier study for the reframes (docs/plans/2026-10-03-reframes.md). Reads NO market data: every number here
comes from a stdlib Monte Carlo of an idealised book, so it is a statement about the CHALLENGE, not about any edge.

    python3 scripts/research/barrier_reframes.py --out docs/audits/2026-10-03-barrier-reframes.json

Model (each choice is a simplification, disclosed in the reframes document):
* The book's daily P&L, in % of the INITIAL balance (sizing_basis initial_balance, as fvg-book v2), is i.i.d. Normal with an
  annual Sharpe S and an annual volatility sigma: mu_d = S * sigma / 252, sd_d = sigma / sqrt(252). Fat tails, volatility
  clustering and regime persistence are NOT modelled -- the real books are worse on all three.
* FTMO 2-Step: Phase 1 +10 %, then Phase 2 +5 % from a fresh initial balance the next weekday; fail when the day's intraday low
  (Brownian-bridge minimum between the day's start and its close) is <= -5 % of the initial balance from the day's start, or
  when equity at that low is <= 90 %; target judged on the day's close; >= 4 trading days per phase; no time limit.
* Horizon T = 87 weekdays (~122 calendar days, the pass-policy study's primary horizon). "With retry" = a new attempt (a new
  fee) the weekday after a fail, until T.
* State-dependent policies scale the WHOLE book (mean and volatility together, i.e. position size): `dd3` mirrors fvg-book
  v2's throttle; `taper` halves size within 2 % of the phase target.
Also: two accounts on two streams vs one account carrying both; the 12-month payout value of a FUNDED account at a given
edge and volatility (what an edge buys that volatility cannot); and the forward-stage power of the live components (normal
approximation on their reported per-trade mean and sd)."""
import argparse
import json
import math
import random
import statistics

SEED = 20261003
T_DAYS = 87
P1, P2, DAILY, TOTAL, MIN_DAYS = 0.10, 0.05, 0.05, 0.10, 4
SHARPES = (0.0, 0.68, 1.0, 1.37, 1.8, 2.2)
VOLS = (0.04, 0.06, 0.08, 0.10, 0.12, 0.15, 0.18, 0.22, 0.26, 0.30, 0.35, 0.40)
POLICIES = ("const", "dd3", "taper")
PATHS = 3000


def day_low(r, sd, u):
    """Minimum of a Brownian bridge from 0 to r over one day with daily sd (exact reflection formula)."""
    return 0.5 * (r - math.sqrt(r * r - 2.0 * sd * sd * math.log(u)))


def scale(policy, eq, target):
    if policy == "dd3":
        return 1.0 if eq > -0.03 else 0.5 if eq > -0.06 else 0.25
    if policy == "taper":
        return 0.5 if eq >= target - 0.02 else 1.0
    return 1.0


def phase(rng, mu, sd, target, days_left, policy):
    """('pass' | 'fail' | 'open', trading days used)."""
    eq, n = 0.0, 0
    while n < days_left:
        k = scale(policy, eq, target)
        m, s = mu * k, sd * k
        r = rng.gauss(m, s)
        low = day_low(r, s, 1.0 - rng.random())
        n += 1
        if low <= -DAILY or eq + low <= -TOTAL:
            return "fail", n
        eq += r
        if eq >= target and n >= MIN_DAYS:
            return "pass", n
    return "open", n


def attempt(rng, mu, sd, days_left, policy):
    a, n1 = phase(rng, mu, sd, P1, days_left, policy)
    if a != "pass":
        return a, n1
    left = days_left - n1 - 1                       # Phase 2 starts the next weekday
    if left <= 0:
        return "open", days_left
    b, n2 = phase(rng, mu, sd, P2, left, policy)
    return ("funded" if b == "pass" else b), n1 + 1 + n2


def cell(S, vol, policy, paths=PATHS, seed=SEED):
    rng = random.Random(f"{seed}|{S}|{vol}|{policy}")
    mu, sd = S * vol / 252.0, vol / math.sqrt(252.0)
    funded = fail1 = funded_retry = 0
    fees, days_to = [], []
    long_funded = 0
    for _ in range(paths):
        out, n = attempt(rng, mu, sd, T_DAYS, policy)
        funded += out == "funded"
        fail1 += out == "fail"
        if out == "funded":
            days_to.append(n)
        # with retry until T
        left, k, got = T_DAYS - n, 1, out == "funded"
        o = out
        while o == "fail" and left > 1:
            o, m = attempt(rng, mu, sd, left - 1, policy)
            k += 1
            left -= m + 1
            got = o == "funded"
        funded_retry += got
        fees.append(k)
        # eventual (no retry, 4 x T) -- the 'no time limit' reading
        o2, _ = attempt(rng, mu, sd, 4 * T_DAYS, policy)
        long_funded += o2 == "funded"
    return {"sharpe": S, "vol": vol, "policy": policy, "funded_T": funded / paths, "fail_first": fail1 / paths,
            "funded_T_retry": funded_retry / paths, "mean_fees_T_retry": statistics.mean(fees),
            "funded_4T": long_funded / paths, "median_days_if_funded_T": statistics.median(days_to) if days_to else None}


def accounts(S, vol, rho, paths=PATHS, seed=SEED):
    """Two challenges on two streams with daily-P&L correlation rho, each at (S, vol): P(at least one funded <= T), mean funded.
    Against ONE account carrying both streams at the same per-stream size: Sharpe S*sqrt(2/(1+rho)), vol vol*sqrt(2(1+rho))."""
    rng = random.Random(f"{seed}|acc|{S}|{vol}|{rho}")
    mu, sd = S * vol / 252.0, vol / math.sqrt(252.0)
    one_or_more = both = 0
    for _ in range(paths):
        res = []
        st = [[0.0, 0, "p1"], [0.0, 0, "p1"]]       # equity, days in phase, phase
        done = [None, None]
        for day in range(T_DAYS):
            z0 = rng.gauss(0, 1)
            z1 = rho * z0 + math.sqrt(max(0.0, 1 - rho * rho)) * rng.gauss(0, 1)
            for a, z in ((0, z0), (1, z1)):
                if done[a] is not None:
                    continue
                eq, n, ph = st[a]
                if ph == "gap":
                    st[a] = [0.0, 0, "p2"]
                    continue
                r = mu + sd * z
                low = day_low(r, sd, 1.0 - rng.random())
                n += 1
                if low <= -DAILY or eq + low <= -TOTAL:
                    done[a] = "fail"
                    continue
                eq += r
                tgt = P1 if ph == "p1" else P2
                if eq >= tgt and n >= MIN_DAYS:
                    if ph == "p1":
                        st[a] = [0.0, 0, "gap"]
                    else:
                        done[a] = "funded"
                    continue
                st[a] = [eq, n, ph]
        k = sum(1 for d in done if d == "funded")
        one_or_more += k >= 1
        both += k == 2
    comb = cell(S * math.sqrt(2.0 / (1.0 + rho)), vol * math.sqrt(2.0 * (1.0 + rho)), "const", paths, seed)
    return {"sharpe": S, "vol_each": vol, "rho": rho, "two_accounts_at_least_one": one_or_more / paths,
            "two_accounts_both": both / paths, "two_accounts_mean_funded": (one_or_more + both) / paths,
            "one_account_both_streams": {"sharpe": comb["sharpe"], "vol": comb["vol"], "funded_T": comb["funded_T"],
                                         "fail_first": comb["fail_first"]}}


def funded_value(S, vol, policy, months=12, split=0.80, paths=PATHS, seed=SEED):
    """Expected payouts (in % of the initial balance) of a FUNDED account over `months` x 21 weekdays: at each month end the
    trader withdraws `split` x the profit above the initial balance and the balance resets to it; the account ends at the first
    -5 % day or -10 % total (same Brownian-bridge lows). Payout timing and split are FTMO-like assumptions (not verified at the
    source); the point is the CONTRAST between edges at the same volatility, not the level."""
    rng = random.Random(f"{seed}|fv|{S}|{vol}|{policy}")
    mu, sd = S * vol / 252.0, vol / math.sqrt(252.0)
    tot, alive_end = [], 0
    for _ in range(paths):
        eq, paid, alive = 0.0, 0.0, True
        for d in range(months * 21):
            k = scale(policy, eq, 1e9)
            r = rng.gauss(mu * k, sd * k)
            low = day_low(r, sd * k, 1.0 - rng.random())
            if low <= -DAILY or eq + low <= -TOTAL:
                alive = False
                break
            eq += r
            if (d + 1) % 21 == 0 and eq > 0:
                paid += split * eq
                eq = 0.0
        tot.append(paid)
        alive_end += alive
    return {"sharpe": S, "vol": vol, "policy": policy, "mean_payout_pct": 100 * statistics.mean(tot),
            "survives_12m": alive_end / paths}


def norm_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def forward_power():
    """Stage (a) of the F2 rule (docs/plans/2026-10-02-edge-followup-preregistration.md §4): one read at >= 100 events,
    one-sided p < 0.10, Holm over the survivors. Per-trade mean / sd from docs/audits/2026-10-02-book-variants.json
    components (span 2021-10 -> 2026-09, R units) -- the edge AS MEASURED, i.e. the optimistic case."""
    comps = {"H7_XAUUSD_eod": (0.0458, 0.5709, 652), "E5_XAUUSD_24": (0.0108, 0.4251, 2558),
             "E5_US500_48": (0.0085, 0.2917, 2547), "G9_XAUUSD_eod": (0.0264, 0.5938, 918)}
    years = 4.96                                   # 2021-10-12 -> 2026-09-28
    out = {}
    z10, z80 = 1.2816, 0.8416
    for k, (m, s, n_span) in comps.items():
        per_year = n_span / years
        row = {"mean_R": m, "sd_R": s, "trades_per_year": round(per_year, 1)}
        for n in (100, 250):
            snr = m / s * math.sqrt(n)
            row[f"power_n{n}_alpha0.10"] = round(norm_sf(z10 - snr), 3)
            row[f"power_n{n}_holm4_alpha0.025"] = round(norm_sf(1.96 - snr), 3)
        n80 = ((z10 + z80) * s / m) ** 2
        row["n_for_80pct_power_alpha0.10"] = round(n80)
        row["years_for_80pct_power"] = round(n80 / per_year, 1)
        out[k] = row
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--paths", type=int, default=PATHS)
    a = ap.parse_args()
    grid = [cell(S, v, p, a.paths) for S in SHARPES for v in VOLS for p in POLICIES]
    best = {}
    for S in SHARPES:
        for p in POLICIES:
            rows = [g for g in grid if g["sharpe"] == S and g["policy"] == p]
            b = max(rows, key=lambda g: g["funded_T"])
            b10 = max([g for g in rows if g["fail_first"] <= 0.10] or [rows[0]], key=lambda g: g["funded_T"])
            best[f"{S}|{p}"] = {"argmax_vol": b["vol"], "funded_T": b["funded_T"], "fail_first": b["fail_first"],
                                "argmax_vol_fail<=0.10": b10["vol"], "funded_T_fail<=0.10": b10["funded_T"]}
    acc = [accounts(S, v, rho, a.paths) for S in (1.0, 1.37) for v in (0.12, 0.18) for rho in (0.0, 0.5, 0.9)]
    fv = [funded_value(S, v, p, paths=a.paths) for S in (0.0, 0.68, 1.37) for v in (0.12, 0.18, 0.26) for p in ("const", "dd3")]
    out = {"meta": {"script": "scripts/research/barrier_reframes.py", "seed": SEED, "paths": a.paths, "T_weekdays": T_DAYS,
                    "reads_market_data": False},
           "grid": grid, "best_vol": best, "two_accounts": acc, "funded_value_12m": fv, "forward_power": forward_power()}
    for r in fv:
        print(r)
    json.dump(out, open(a.out, "w"), indent=1)
    for k, v in best.items():
        print(k, v)
    for r in acc:
        print(r)
    for k, v in out["forward_power"].items():
        print(k, v)


if __name__ == "__main__":
    main()
