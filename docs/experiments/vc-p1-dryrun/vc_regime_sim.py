"""VC-P1 §4, §7: what a regime-level effect in R_bar does to T1a's error rate and power, on the REAL window-B layout.

    python3 -W ignore vc_regime_sim.py <out json> [<repo root>] [--reps N]

OUTCOME-BLIND: the layout is the decisive window's events (entry day, side, VR half, VR run, entry slot, planned bars: no exit,
cost or R is read or computed); every outcome below is SYNTHETIC (Gaussian noise of sd SD_R x sqrt(NB_REF / nb) in R_bar units,
the draft's per-trade sd 0.75 at k = 1.4), plus an optional block effect and an optional T1a / T1b effect:
* block effect: one draw ~ N(0, tau^2) per calendar YEAR ("year") or per VR RUN ("run") -- the HIGH / LOW halves are runs of
  consecutive days, and year effects are what a trend system's mean R shows --, added to every trade of the block, in R_bar
  units (R at a 144-bar hold: T1a's own unit). "none": tau = 0.
* effect: "T1a": +delta / 2 on HIGH days and -delta / 2 on LOW days (equal in both gold components); "T1b": the same on
  long-hold / short-hold entries; "null": none. delta = 0.2.
Each replication runs the read's own tests (edge_vc.split_test, R_bar, nb weights, side-balanced, CR1 by day, Student-t,
one-sided): T1a by day, T1a with the VR runs as clusters (`T1a_run_clustered`), T1b by day. `rejection_at_0.025` is the
share of replications whose one-sided p <= 0.025 (the first Holm step): the size under "null", the power under the effect.
`option_C` (lead decision 2026-10-05: T1a passes only if its by-day test passes AND its run-clustered p <= 0.05): the share
whose run-clustered p <= 0.05, and the share whose by-day p <= 0.025 (the first Holm step) AND run-clustered p <= 0.05 --
T1a's pass rule without its two sign conditions. For a T1a effect, `full_rule` adds the gate's component condition (the
balanced difference > 0 in BOTH gold components; the True half's net R taken as met, as edge_vc.rule_power does): `by_day`
(the first Holm step) and `option_C`. Besides the equal 0.20 effect at every block level, three more T1a effects of
edge_vc.POWER_SHAPES run without a block effect (`effect` = the shape's name: per-component half-split differences). The
draws of the first version's cells are unchanged (same seeds, same order), so their `rejection_at_0.025` figures are too.
The result file records the code sha256 of edge_vc.py it ran with."""
import hashlib
import importlib.util
import json
import os
import random
import statistics
import sys

args = [a for a in sys.argv[1:] if not a.startswith("--")]
OUT = os.path.abspath(args[0])
REPS = int(sys.argv[sys.argv.index("--reps") + 1]) if "--reps" in sys.argv else 2000


def _find_root():
    if len(args) > 1:
        return os.path.abspath(args[1])
    d = os.path.dirname(os.path.abspath(__file__))
    while d != os.path.dirname(d):
        if os.path.exists(os.path.join(d, "scripts", "research", "edge_vc.py")):
            return d
        d = os.path.dirname(d)
    return os.getcwd()


ROOT = _find_root()
sys.path.insert(0, os.path.join(ROOT, "scripts"))
EDGE_VC = os.path.join(ROOT, "scripts", "research", "edge_vc.py")
spec = importlib.util.spec_from_file_location("edge_vc", EDGE_VC)
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)
BS = V._load("book_sim", "scripts/research/book_sim.py")
zone = V.server_zone()
s = V._pit_series("XAUUSD")
vr = V.pit_vr_by_day(s)
runs = V.vr_runs(vr)
layout = []
for c in V.GOLD:
    _sym, det, _hold = BS.COMPONENTS[c]
    evs, _ = V.pit_events(s, det, V.LOAD_END)
    for ev in evs:
        d = ev["day"]
        if d < V.HOLDOUT_END and vr.get(d) is not None:
            layout.append({"component": c, "day": d, "side": ev["side"], "high": vr[d] > 1.0, "run": runs[d],
                           "year": d.year, "entry_slot": V.slot_of(s.dt[ev["e"]], zone),
                           "nb_planned": V.bars_to_day_end(s.dt[ev["e"]], zone)})
med = {c: statistics.median(t["entry_slot"] for t in layout if t["component"] == c) for c in V.GOLD}
for t in layout:
    t["long_hold"] = t["entry_slot"] < med[t["component"]]
years = sorted({t["year"] for t in layout})
run_ids = sorted({t["run"] for t in layout})
print(f"layout: {len(layout)} trades, years {years}, {len(run_ids)} VR runs", flush=True)

TAU = {"none": (0.0,), "year": (0.05, 0.10, 0.20), "run": (0.05, 0.10, 0.20)}
DELTA = 0.20
EQUAL = {c: DELTA for c in V.GOLD}
SHAPES = ("equal_0.10", "shape_2018_G9_0.21_H7_0.04", "G9_only_0.21")
plan = [(level, tau, effect) for level, taus in TAU.items() for tau in taus for effect in ("null", "T1a", "T1b")]
plan += [("none", 0.0, name) for name in SHAPES]
cells = []
for level, tau, effect in plan:
    if effect == "T1a":
        split, size = "high", EQUAL
    elif effect == "T1b":
        split, size = "long_hold", EQUAL
    elif effect in SHAPES:
        split, size = "high", V.POWER_SHAPES[effect]
    else:
        split, size = None, None
    seed = int(hashlib.sha256(f"{level}|{tau}|{effect}".encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    rej = {"T1a_day": 0, "T1a_run": 0, "T1b_day": 0}
    opt = {"T1a_run_at_0.05": 0, "T1a_day_0.025_and_run_0.05": 0}
    full = {"by_day": 0, "option_C": 0}
    gated = split == "high"
    diffs, ses = [], []
    for _ in range(REPS):
        eff = {y: rng.gauss(0, tau) for y in years} if level == "year" else \
              ({k: rng.gauss(0, tau) for k in run_ids} if level == "run" else {})
        rows = []
        for t in layout:
            y = V.SD_R * (V.NB_REF / t["nb_planned"]) ** 0.5 * rng.gauss(0, 1)
            if level == "year":
                y += eff[t["year"]]
            elif level == "run":
                y += eff[t["run"]]
            if split:
                y += size[t["component"]] / 2 if t[split] else -size[t["component"]] / 2
            rows.append(dict(t, R_bar=y, R_net=y))
        a = V.split_test(rows, key="high", value="R_bar", row_weight=V.nb_weight)
        r = V.split_test(rows, key="high", value="R_bar", row_weight=V.nb_weight, day_key="run")
        b = V.split_test(rows, key="long_hold", value="R_bar", row_weight=V.nb_weight)
        rej["T1a_day"] += a["p_one_sided"] <= 0.025
        rej["T1a_run"] += r["p_one_sided"] <= 0.025
        rej["T1b_day"] += b["p_one_sided"] <= 0.025
        run_ok = r["t"] is not None and r["p_one_sided"] <= 0.05
        opt["T1a_run_at_0.05"] += run_ok
        opt["T1a_day_0.025_and_run_0.05"] += a["p_one_sided"] <= 0.025 and run_ok
        if gated and a["p_one_sided"] <= 0.025:
            comps = all((V.split_test([x for x in rows if x["component"] == c], key="high", value="R_bar",
                                      row_weight=V.nb_weight)["diff"] or 0) > 0 for c in V.GOLD)
            full["by_day"] += comps
            full["option_C"] += comps and run_ok
        if effect == "null" and a["se"]:
            diffs.append(a["diff"])
            ses.append(a["se"])
    cell = {"block_level": level, "tau": tau, "effect": effect, "reps": REPS,
            "rejection_at_0.025": {k: round(v / REPS, 3) for k, v in rej.items()},
            "option_C": {k: round(v / REPS, 3) for k, v in opt.items()}}
    if gated:
        cell["full_rule"] = {k: round(v / REPS, 3) for k, v in full.items()}
        cell["effect_R_bar"] = size
    if diffs:
        cell["T1a_null_sd_of_diff_over_mean_se"] = round(statistics.pstdev(diffs) / statistics.mean(ses), 2)
    cells.append(cell)
    print(level, tau, effect, cell["rejection_at_0.025"], cell["option_C"], cell.get("full_rule", ""),
          cell.get("T1a_null_sd_of_diff_over_mean_se", ""), flush=True)
res = {"what": __doc__.split("\n\n")[0], "code_sha256": {"scripts/research/edge_vc.py": hashlib.sha256(
           open(EDGE_VC, "rb").read()).hexdigest()},
       "layout": {"trades": len(layout), "years": years, "vr_runs": len(run_ids),
                  "by_component": {c: sum(1 for t in layout if t["component"] == c) for c in V.GOLD}},
       "sd_R": V.SD_R, "nb_ref": V.NB_REF, "delta_R_bar": DELTA, "reps": REPS, "cells": cells}
with open(OUT, "w") as fh:
    json.dump(res, fh, indent=1)
print("wrote", OUT)
