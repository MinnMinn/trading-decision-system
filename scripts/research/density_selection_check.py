#!/usr/bin/env python3
"""How much does the research mode's same-day completeness selection move the gold book? (DESCRIPTIVE, 2026-10-04)

edge_census.Series in research mode (sigma_every_day=False) gives a day a sigma -- and F3's MOM20 -- only when that day
turns out dense (>= 80 % of the median bars per day), so an event on a day that LATER proves sparse is dropped: a same-day
completeness selection (edge_census.py Series docstring). The demo executor and the paper twin run point in time
(sigma_every_day=True). This replays the book components both ways on the same bars and compares them.

    python3 scripts/research/density_selection_check.py --out docs/audits/2026-10-04-density-selection-check.json"""
import argparse
import importlib.util
import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
_spec = importlib.util.spec_from_file_location("book_sim", os.path.join(ROOT, "scripts", "research", "book_sim.py"))
BS = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(BS)
EC = BS.EC
COMPONENTS = ("H7_XAUUSD_eod", "G9_XAUUSD_eod", "G9_XAGUSD_eod")
STOP_KS = (2.0, 1.4)


def _pit_load(orig):
    import real_costs as RC

    def load(sym, end=EC.DEV_CUTOFF):
        s = orig(sym, end=end)
        candles = [{"time": t, "open": o, "high": h, "low": l, "close": c} for t, o, h, l, c in zip(s.T, s.O, s.H, s.L, s.C)]
        return EC.Series(sym, candles, RC.server_zone(EC.PROVIDER)[1], end="9999-12-31T00:00:00Z", sigma_every_day=True)
    return load


def run(out_path):
    orig, rows = EC.load, {}
    try:
        for mode in ("research", "point_in_time"):
            EC.load = orig if mode == "research" else _pit_load(orig)
            for c in COMPONENTS:
                for k in STOP_KS:
                    rows[(mode, c, k)] = {t["entry_time"]: t for t in BS.trades(*BS.COMPONENTS[c], stop_k=k)}
    finally:
        EC.load = orig
    out = {"meta": {"script": "scripts/research/density_selection_check.py", "status": "DESCRIPTIVE", "end": BS.END},
           "components": {}}
    for c in COMPONENTS:
        for k in STOP_KS:
            a, b = rows[("research", c, k)], rows[("point_in_time", c, k)]
            extra = [b[t] for t in b if t not in a]
            common = [t for t in a if t in b]
            out["components"][f"{c} stop_k={k}"] = {
                "n_research": len(a), "n_point_in_time": len(b), "only_point_in_time": len(extra),
                "only_research": sum(1 for t in a if t not in b),
                "mean_R_research": statistics.mean(t["R"] for t in a.values()),
                "mean_R_point_in_time": statistics.mean(t["R"] for t in b.values()),
                "mean_R_only_point_in_time": statistics.mean(t["R"] for t in extra) if extra else None,
                "max_abs_R_change_on_common_trades": max((abs(b[t]["R"] - a[t]["R"]) for t in common), default=0.0),
                "worst_R_research": min(t["R"] for t in a.values()), "worst_R_point_in_time": min(t["R"] for t in b.values())}
    with open(out_path, "w") as fh:
        json.dump(out, fh, indent=1)
    for key, v in out["components"].items():
        print(key, {a: (round(x, 4) if isinstance(x, float) else x) for a, x in v.items()})
    print(f"wrote {out_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    run(ap.parse_args().out)


if __name__ == "__main__":
    main()
