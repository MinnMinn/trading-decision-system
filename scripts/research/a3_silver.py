#!/usr/bin/env python3
"""A3 -- add G9 XAGUSD to fvg-book v3? (docs/plans/2026-10-04-a3-silver-preregistration.md, tag [A3-P1]). DESCRIPTIVE /
EXPOSED: every trade sequence was already read. Reuses scripts/research/vol_schedule.py (challenge2, value, the aligned-day
bootstrap) and scripts/research/pass_policy.py unchanged; both books are replayed on the SAME sampled days.

    python3 scripts/research/a3_silver.py run --out docs/audits/2026-10-04-a3-silver.json"""
import argparse
import collections
import datetime
import importlib.util
import json
import os
import random
import statistics
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


VS = _load("vol_schedule", "scripts/research/vol_schedule.py")
BS, PP = VS.BS, VS.PP
PREREG = "docs/plans/2026-10-04-a3-silver-preregistration.md"
TAG = "[A3-P1]"
SCRIPT = "scripts/research/a3_silver.py"
GUARDED = (SCRIPT, "scripts/tests/test_a3_silver.py", PREREG, "scripts/research/vol_schedule.py",
           "scripts/research/pass_policy.py", "scripts/research/book_sim.py", "scripts/research/edge_f4.py",
           "scripts/research/edge_f3.py", "scripts/research/edge_census.py")
SILVER = "G9_XAGUSD_eod"
BOOKS = {"v3": ["H7_XAUUSD_eod", "G9_XAUUSD_eod"], "v3+ag": ["H7_XAUUSD_eod", "G9_XAUUSD_eod", SILVER]}
EDGE_MULTS = (1.0, 0.5, 0.0)
MAX_FAIL, GAP_TOLERANCE = 0.10, 1.2              # % of the balance (A1's tolerance)


def decide(d_half, d_zero, conf_fail, boot_half_fail, worst_silver_pct):
    """[A3-P1] §3."""
    ok = (d_half is not None and d_half > 0 and conf_fail <= MAX_FAIL and boot_half_fail <= MAX_FAIL
          and worst_silver_pct <= GAP_TOLERANCE)
    return {"PROPOSED": bool(ok), "variance_not_edge": bool(ok and d_zero is not None and d_zero > 0)}


def bootstrap_books(views, p, paths=None, seed=None):
    """{book: summary} -- weekdays resampled ONCE per path, every book replayed on those days (vol_schedule's helpers)."""
    paths = paths or VS.BOOT_PATHS
    any_v = views[next(iter(views))]
    d0 = min(v[0]["entry"].date() for v in views.values())
    d1 = max(v[-1]["entry"].date() for v in views.values())
    weekdays = [d0 + datetime.timedelta(days=i) for i in range((d1 - d0).days + 1)]
    weekdays = [d for d in weekdays if d.weekday() < 5]
    by_day = {b: collections.defaultdict(list) for b in views}
    for b, v in views.items():
        for t in v:
            by_day[b][t["entry"].date()].append(t)
    rng = random.Random(VS.SEED if seed is None else seed)
    base = datetime.datetime(2001, 1, 1, tzinfo=datetime.timezone.utc)
    acc = {b: collections.defaultdict(list) for b in views}
    for _ in range(paths):
        src = VS.sample_days(weekdays, rng)
        for b in views:
            path = VS.build_path(by_day[b], src, base)
            c = VS.challenge2(path, path, base, p)
            v = VS.value(path, path, path, base, p)
            a = acc[b]
            a["funded_122"].append(c["funded_at"] is not None and (c["funded_at"] - base).days <= 122)
            a["first_fail"].append(c["first_fail"])
            for k in ("net", "paid", "fees"):
                a[k].append(v[k])
            a["funded_h"].append(v["funded"])
    del any_v
    return {b: {"funded_le_122d": statistics.mean(a["funded_122"]), "first_attempt_fail": statistics.mean(a["first_fail"]),
                "E_net_pct": 100 * statistics.mean(a["net"]), "E_paid_pct": 100 * statistics.mean(a["paid"]),
                "E_fees_pct": 100 * statistics.mean(a["fees"]), "funded_within_horizon": statistics.mean(a["funded_h"])}
            for b, a in acc.items()}


def historical(views, p, lo, hi):
    starts = list(PP.mondays(views["v3+ag"], lo, hi))
    out = {}
    for b, v in views.items():
        cs = [VS.challenge2(v, v, s, p) for s in starts]
        fd = [None if c["funded_at"] is None else (c["funded_at"] - s).days for c, s in zip(cs, starts)]
        out[b] = {"n": len(cs), "funded_le_122d": sum(d is not None and d <= 122 for d in fd) / len(cs),
                  "funded_ever": sum(d is not None for d in fd) / len(cs),
                  "median_days_to_funded": statistics.median([d for d in fd if d is not None]) if any(d is not None for d in fd) else None,
                  "first_attempt_fail": sum(c["first_fail"] for c in cs) / len(cs)}
    return out


def _guard():
    st = subprocess.run(["git", "-C", ROOT, "status", "--porcelain", "--", *GUARDED], capture_output=True, text=True).stdout
    tracked = subprocess.run(["git", "-C", ROOT, "ls-files", "--", *GUARDED], capture_output=True, text=True).stdout.split()
    missing = [g for g in GUARDED if g not in tracked]
    if st.strip() or missing:
        raise SystemExit(f"refusing: commit first (dirty: {st.strip() or '-'}; untracked: {missing or '-'})")
    if TAG not in open(os.path.join(ROOT, PREREG), encoding="utf-8").read():
        raise SystemExit(f"refusing: {PREREG} lacks {TAG}")
    return subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


def run(out_path, require_clean=True, paths=None):
    if os.path.exists(out_path):
        raise SystemExit(f"refusing: {out_path} exists (read once)")
    head = _guard() if require_clean else None
    comps = sorted({c for v in BOOKS.values() for c in v})
    raw = {c: BS.trades(*BS.COMPONENTS[c]) for c in comps}
    span_from = min(t["entry_time"] for t in raw[SILVER])
    raw = {c: [t for t in v if t["entry_time"] >= span_from] for c, v in raw.items()}
    p = VS.pol("mae")
    base_views = {b: PP.prepare(raw, cs) for b, cs in BOOKS.items()}
    res = {"meta": {"script": SCRIPT, "preregistration": PREREG, "tag": TAG, "git_head": head, "span_from": span_from,
                    "status": "DESCRIPTIVE / EXPOSED", "books": BOOKS, "fee": VS.FEE, "split": VS.SPLIT,
                    "horizon_days": VS.HORIZON_DAYS, "bootstrap_paths": paths or VS.BOOT_PATHS, "seed": VS.SEED},
           "historical": {"selection": historical(base_views, p, "2000-01-01", PP.SELECT_END),
                          "confirmation": historical(base_views, p, PP.SELECT_END, "2100-01-01")},
           "bootstrap": {}}
    for m in EDGE_MULTS:
        views = {b: PP.prepare(raw, cs, 1.0 - m) for b, cs in BOOKS.items()}
        res["bootstrap"][f"edge_x{m}"] = bootstrap_books(views, p, paths)
    v3_daily = BS.daily_r([t for c in BOOKS["v3"] for t in raw[c]])
    res["corr_daily_silver_vs_v3"] = BS.corr(BS.daily_r(raw[SILVER]), v3_daily)
    res["components"] = {c: {"n": len(v), "mean_R": statistics.mean(t["R"] for t in v),
                             "worst_trade_loss_pct": -100 * PP.CEILING * min(t["R"] for t in v),
                             "by_year_mean_R": {y: round(statistics.mean(t["R"] for t in v if t["entry_time"][:4] == y), 4)
                                                for y in sorted({t["entry_time"][:4] for t in v})}} for c, v in raw.items()}
    b = res["bootstrap"]
    d_half = b["edge_x0.5"]["v3+ag"]["E_net_pct"] - b["edge_x0.5"]["v3"]["E_net_pct"]
    d_zero = b["edge_x0.0"]["v3+ag"]["E_net_pct"] - b["edge_x0.0"]["v3"]["E_net_pct"]
    d_one = b["edge_x1.0"]["v3+ag"]["E_net_pct"] - b["edge_x1.0"]["v3"]["E_net_pct"]
    dec = decide(d_half, d_zero, res["historical"]["confirmation"]["v3+ag"]["first_attempt_fail"],
                 b["edge_x0.5"]["v3+ag"]["first_attempt_fail"], res["components"][SILVER]["worst_trade_loss_pct"])
    res["decision"] = dict(dec, delta_E_net_pct_edge1=d_one, delta_E_net_pct_haircut50=d_half, delta_E_net_pct_edge0=d_zero)
    with open(out_path, "x") as fh:
        json.dump(res, fh, indent=1, default=str)
    for per in ("selection", "confirmation"):
        print(per, {k: {a: (round(x, 3) if isinstance(x, float) else x) for a, x in v.items()} for k, v in res["historical"][per].items()})
    for m, v in b.items():
        print(m, {k: {a: round(x, 3) for a, x in s.items()} for k, s in v.items()})
    print("corr", res["corr_daily_silver_vs_v3"], "worst silver", round(res["components"][SILVER]["worst_trade_loss_pct"], 2))
    print("decision", res["decision"])
    print(f"wrote {out_path}")
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--out", required=True)
    a = ap.parse_args()
    run(a.out)


if __name__ == "__main__":
    main()
