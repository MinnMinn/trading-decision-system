#!/usr/bin/env python3
"""IC post-evaluation descriptives promised by amendment 2 (docs/plans/2026-10-05-claude-ict-amendment-2.md §1-§3).

Run AFTER the single `claude_ict_eval.py evaluate`, from the same committed decisions and the same simulator. Nothing
here can change the verdict: the evaluator does not import this file, and every number is descriptive.

    python3 scripts/research/claude_ict_post.py --out docs/experiments/claude-ict/post-evaluation.json

- §1: per instrument x order kind, C's filled trades, mean R of C, of the R-control's opposite trade at C's fill instant
  (`control_pair`), and mean(R_C - R_opp); the primary and mirror p-values are the evaluation's (global).
- §2: the arm-M 15m series end per instrument and the decision points (killzones) it could not scan.
- §3: C's orders re-simulated with the spread doubled (fills, mean net R).
"""
import argparse
import collections
import datetime
import importlib.util
import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "research"))
_spec = importlib.util.spec_from_file_location("claude_ict_eval", os.path.join(ROOT, "scripts", "research",
                                                                              "claude_ict_eval.py"))
E = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(E)
K = E.K
TD = datetime.timedelta
EXP = os.path.join(ROOT, "docs", "experiments", "claude-ict")
#: amendment 2 §2, measured by the pre-registration's reviewer on the frozen 15m history
M_SERIES_END = {"US500": "2026-09-28T17:00:00Z", "XAUUSD": "2026-10-01T02:00:00Z"}


def _mean(xs):
    return statistics.mean(xs) if xs else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if not os.path.exists(os.path.join(EXP, "evaluation.json")):
        raise SystemExit("refused: run claude_ict_eval.py evaluate first -- these descriptives come after the verdict")
    with open(os.path.join(EXP, "manifest.json")) as fh:
        man = json.load(fh)
    with open(os.path.join(EXP, "evaluation.json")) as fh:
        ev = json.load(fh)
    final = {}
    with open(os.path.join(EXP, "decisions.jsonl")) as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("record") == "decision":
                final[r["decision_id"]] = r
    start, end = K.parse_z(man["window"]["start"]), K.parse_z(man["window"]["end_close_of_last_bar"])
    points = man["decision_points"]
    books = {s: E.Book(s, K.load_bars(s, None, since=start - TD(days=2), until=end + TD(days=1)))
             for s in K.INSTRUMENTS}
    rows = E.arm_c(points, final, books)
    filled = [r for r in rows if r["outcome"] == "filled"]
    # the arm-C rows must be the evaluation's
    ev_rows = {r["id"]: r for r in ev["arms"]["C"]["decisions"]}
    mism = [r["id"] for r in rows if r.get("R") != ev_rows[r["id"]].get("R") or r["outcome"] != ev_rows[r["id"]]["outcome"]]
    if mism:
        raise SystemExit(f"refused: the re-simulated arm C differs from evaluation.json on {mism[:5]}")
    # §1 control asymmetry by order kind
    cells = collections.defaultdict(lambda: {"R_C": [], "R_opp": []})
    for r in filled:
        _same, opp = E.control_pair(books[r["instrument"]], r, r["_order"])
        for key in ((r["instrument"], r["order"]), ("all", r["order"]), (r["instrument"], "all"), ("all", "all")):
            cells[key]["R_C"].append(r["R"])
            cells[key]["R_opp"].append(opp)
    by_kind = {}
    for (inst, kind), v in sorted(cells.items()):
        by_kind[f"{inst}|{kind}"] = {"filled": len(v["R_C"]), "mean_R_C": _mean(v["R_C"]), "mean_R_opp": _mean(v["R_opp"]),
                                     "mean_R_C_minus_R_opp": _mean([c - o for c, o in zip(v["R_C"], v["R_opp"])])}
    kinds = collections.Counter(r["order"] for r in filled)
    # §2 arm M's shortened series
    m_cut = {}
    for sym, cut in M_SERIES_END.items():
        late = [p["id"] for p in points if p["instrument"] == sym and p["kz_open_utc"] >= cut]
        m_cut[sym] = {"series_end_utc": cut, "decision_points_after_end": len(late),
                      "days": sorted({i.split("|")[0] for i in late})}
    # §3 spread doubled
    sim2 = []
    for r in rows:
        if "_order" not in r:
            continue
        o = dict(r["_order"], spread=2 * r["_order"]["spread"])
        s = E.simulate(books[r["instrument"]], o)
        sim2.append((r["instrument"], s["status"], s.get("R")))
    f2 = [x for x in sim2 if x[1] == "filled"]
    spread2 = {"orders": len(sim2), "filled": len(f2), "mean_net_R": _mean([x[2] for x in f2]),
               "by_instrument": {s: {"filled": sum(1 for x in f2 if x[0] == s),
                                     "mean_net_R": _mean([x[2] for x in f2 if x[0] == s])} for s in K.INSTRUMENTS}}
    out = {"made_after": "evaluation.json (run once); descriptive only, no verdict effect (amendment 2)",
           "verdict": ev["verdict"]["status"],
           "primary_p": ev["verdict"]["primary_test"]["p_one_sided"],
           "mirror_p": ev["verdict"]["mirror_control"]["p_one_sided"],
           "filled_by_order_kind": dict(kinds),
           "mostly_stop_orders": kinds.get("stop", 0) > len(filled) / 2,
           "control_asymmetry_by_kind": by_kind,
           "arm_M_shortened_series": m_cut,
           "spread_doubled": spread2,
           "spread_as_run": {"filled": len(filled), "mean_net_R": _mean([r["R"] for r in filled])}}
    with open(a.out, "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(json.dumps({k: out[k] for k in ("verdict", "primary_p", "mirror_p", "filled_by_order_kind",
                                          "mostly_stop_orders", "spread_doubled", "spread_as_run")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
