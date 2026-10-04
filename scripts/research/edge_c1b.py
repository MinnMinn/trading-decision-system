#!/usr/bin/env python3
"""C1b -- ONE post-publication read of the frozen C1 crypto trend book
(docs/plans/2026-10-04-edge-c1b-post-publication-preregistration.md, tag [C1b-P1]). A second stage chosen AFTER seeing C1's
discovery read (disclosed there). Every rule, cost, fill, funding and placebo detail is scripts/research/edge_c1.py's, reused
UNCHANGED (this file never edits it); the read is C1's EXPOSED window 2025-03-20 -> 2026-09-30; one test (T1), no BH.

    python3 scripts/research/edge_c1b.py run --out docs/audits/2026-10-04-edge-c1b.json

PASS iff T1 Newey-West one-sided p < 0.05 AND mean net > 0 AND mean net at 2x slippage > 0 AND placebo p_P <= 0.10. Also
reported: alpha with a 90 % CI, a shrunk alpha (normal prior N(0, (10 %/yr)^2)), the regime flag, N2-N6."""
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


C1 = _load("edge_c1", "scripts/research/edge_c1.py")
SCRIPT = "scripts/research/edge_c1b.py"
PREREG = "docs/plans/2026-10-04-edge-c1b-post-publication-preregistration.md"
TAG = "[C1b-P1]"
READ = "exposed"                                   # C1's EXPOSED window, the only post-publication data
P_MAX, P_PLACEBO_MAX = 0.05, 0.10
PRIOR_SD_ANNUAL = 0.10                             # shrinkage prior N(0, (10 %/yr)^2), pre-registered
Z90 = 1.6448536269514722
GUARDED = (SCRIPT, "scripts/tests/test_edge_c1b.py", PREREG) + tuple(C1.GUARDED)


def shrink(alpha, se, prior_sd=PRIOR_SD_ANNUAL):
    """Posterior mean of a normal alpha under the prior N(0, prior_sd^2) with a normal likelihood of SE `se` (annual units)."""
    if alpha is None or not se:
        return None
    w = prior_sd ** 2 / (prior_sd ** 2 + se ** 2)
    return w * alpha


def ci90(alpha, se):
    return None if alpha is None or not se else [alpha - Z90 * se, alpha + Z90 * se]


def passes(reg, net, net2x, p_pl):
    """C1b §2: p < 0.05, net > 0, net at 2x slippage > 0, placebo p_P <= 0.10 (a missing number never passes)."""
    p = reg.get("p_one_sided")
    return bool(p is not None and p < P_MAX and net is not None and net > 0 and net2x is not None and net2x > 0
                and p_pl is not None and p_pl <= P_PLACEBO_MAX)


def label(ok, regime_driven):
    base = ("single post-publication read PASSED; never read for this hypothesis; bars are development-state; price path "
            "public" if ok else "single post-publication read FAILED -> C1 closed")
    return base + ("; regime-driven" if regime_driven else "")


def _guard():
    committed = C1._require_committed(list(GUARDED))
    with open(os.path.join(ROOT, PREREG), encoding="utf-8") as fh:
        if TAG not in fh.read():
            raise SystemExit(f"refusing: {PREREG} lacks {TAG}")
    return committed


def run(out_path, draws=None, require_clean=True):
    """The one C1b read (pre-registration §2-§3). Tests pass require_clean=False on synthetic files."""
    if os.path.exists(out_path):
        raise SystemExit(f"refusing: {out_path} exists -- C1b is read ONCE")
    if draws not in (None, C1.PLACEBO_DRAWS) and require_clean:
        raise SystemExit(f"refusing: the registered read uses {C1.PLACEBO_DRAWS} placebo draws")
    committed = _guard() if require_clean else None
    head = C1._git_head()
    syms = C1.symbols()
    start, end = C1.WINDOWS[READ]
    coins = {s: C1.load_coin(s, end) for s in syms}
    problems = C1.coverage(coins, start, end)
    if problems:
        raise SystemExit("data not ready (nothing computed):\n  " + "\n  ".join(problems))
    try:
        book = C1._book_daily()
    except Exception as exc:                                    # noqa: BLE001 -- N5 only
        raise SystemExit(f"N5 book unavailable ({exc!r}); nothing computed")
    snap = C1.snapshot(syms)
    grid, arrs = C1.build(coins, end)
    j0, j1 = (start - grid[0]).days, (end - grid[0]).days
    if j0 < 0 or grid[j0] != start:
        raise SystemExit(f"data not ready: first eligible day {grid[0]} is after {start}")
    days = grid[j0:j1 + 1]
    held = C1.held_at(arrs, syms, j0)
    inp = C1.window_inputs(arrs, syms, j0, j1, held)
    cost, cost2 = C1.TAKER + C1.SLIPPAGE, C1.TAKER + 2 * C1.SLIPPAGE
    sim, sim2 = C1.simulate(days, inp, cost), C1.simulate(days, inp, cost2)
    pl = C1.placebo(days, inp, cost, draws)
    reg = C1.regress(sim["r"], sim["bench"])
    net = C1.net_line(sim["date"], sim["r"])
    net2 = sum(sim2["r"]) / len(sim2["r"]) if sim2["r"] else None
    p_pl = C1.p_placebo(reg.get("alpha"), pl["sleeve"] if pl else None)
    rg = C1.regime(sim["date"], sim["r"], sim["bench"], reg)
    a_ann = reg.get("alpha_annual")
    se_ann = reg["se_nw"] * C1.ANNUAL_DAYS if reg.get("se_nw") else None
    ok = passes(reg, net["mean"], net2, p_pl)
    coins_rep = {}
    for s in syms:
        c = sim["coin"][s]
        g = C1.regress(c["r"], c["rc"])
        coins_rep[s] = {"regression": g, "net": C1.net_line(c["date"], c["r"]), "report_only": True}
    held2 = C1.held_at(arrs, syms, j0, n2=True)
    sim_n2 = C1.simulate(days, C1.window_inputs(arrs, syms, j0, j1, held2), cost, n2=True)
    diag = {"N2": C1.n2_report(sim_n2, C1.exit_ratios(arrs, syms, j0, j1)), "N3": C1.n3_report(sim, sim2),
            "N4": C1.n4_report(sim["date"], sim["r"], sim["bench"], reg) if reg.get("alpha") is not None else {},
            "N5": C1.n5(sim["date"], sim["r"], book), "N6": C1.regress(sim["r"], sim["bench_funded"])}
    res = {"meta": {"script": SCRIPT, "reuses": C1.SCRIPT, "preregistration": PREREG, "tag": TAG,
                    "guarded": bool(require_clean), "git_head": head, "committed_sha256": committed,
                    "window": [str(start), str(end)], "window_days": len(days), "symbols": syms,
                    "pre_window_pnl_computed": False, "placebo_draws": len(pl["k"]) if pl else 0,
                    "second_stage_after_discovery": True, "snapshot": snap,
                    "data": {s: coins[s].info for s in syms}},
           "T1": {"regression": reg, "alpha_annual": a_ann, "alpha_se_annual": se_ann, "alpha_ci90_annual": ci90(a_ann, se_ann),
                  "alpha_shrunk_annual": shrink(a_ann, se_ann), "net": net, "net_mean_2x_slippage": net2,
                  "p_placebo": p_pl, "regime": rg, "pass": ok},
           "label": label(ok, rg.get("regime_driven")), "coins": coins_rep, "diagnostics": diag,
           "daily": [{"date": str(d), "r": r, "bench": b} for d, r, b in zip(sim["date"], sim["r"], sim["bench"])]}
    with open(out_path, "x") as fh:
        json.dump(res, fh, indent=1, default=str)
    f = lambda v, p=4: "n/a" if v is None else f"{v:+.{p}f}"
    print(f"T1 sleeve n {reg.get('n')} alpha/yr {f(a_ann)} (90% CI {[round(x, 4) for x in (ci90(a_ann, se_ann) or [])]}) "
          f"shrunk {f(shrink(a_ann, se_ann))} p1(NW) {f(reg.get('p_one_sided'))} net/day {f(net['mean'], 6)} "
          f"2x {f(net2, 6)} p_P {f(p_pl)} -> {'PASS' if ok else 'FAIL'}")
    print(f"label: {res['label']}\nwrote {out_path}")
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
