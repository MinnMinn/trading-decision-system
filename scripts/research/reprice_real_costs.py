#!/usr/bin/env python3
"""A0 one-off re-pricing measurement (docs/plans/2026-09-28-methodology-improvement-plan.md §2 A0, item 4).

Re-prices the development-data diagnosis baseline ONCE under the FTMO real-cost profile, for INFORMATION
ONLY: XAUUSD, US500, DE40 x 15m config A (side=taker, mgmt=none, htf=False), ICT and WYCKOFF-BOOK, with
BT_HISTORY_ROOT=data/history/ftmo, pit_cutoff 2024-03-01T00:00:00Z, flat_before_rollover on and off.

Must run BEFORE `BT_HISTORY_ROOT` is read by any other import in this process -- set the env var first, then
import backtest-methods.py fresh (module-level `HISTORY_ROOT = _HS.history_root()` freezes it at exec time).

Efficiency note: scan() returns BOTH ICT and WYCKOFF-BOOK trades in one call, so each (symbol, flatten-mode)
pair is scanned EXACTLY ONCE (not once per method) -- 6 scans total (3 symbols x 2 flatten-modes), not 9. A
full run over this dataset still takes on the order of an hour (XAUUSD 15m alone is ~500k FTMO-Demo bars).

Output: `docs/audits/2026-09-29-real-costs-reprice.json` (small, committed -- the raw data behind
`docs/audits/2026-09-29-real-costs-reprice.md`'s table), plus a copy on stdout. `ROOT` is derived from
`__file__` (code review 2026-09-29, fix round 1, item 2 -- this used to be a hardcoded worktree path), so the
script runs correctly from any checkout/worktree, not only the one it was first written in.
"""
import importlib.util
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["BT_HISTORY_ROOT"] = os.path.join(ROOT, "data", "history", "ftmo")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

spec = importlib.util.spec_from_file_location("bt", os.path.join(ROOT, "scripts", "backtest-methods.py"))
bt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bt)
import real_costs as RC
import methods as _M

PIT_CUTOFF = "2024-03-01T00:00:00Z"
bt.pit_cutoff(PIT_CUTOFF)

SYMBOLS = ["XAUUSD", "US500", "DE40"]
TF = "15m"
PROFILE = "ftmo_demo_2026_09"
FEE = 0.05 / 100  # config A: taker fee 0.05% (docs/architecture/risk-config.json costs.mt5.taker_pct_per_side)
PROVIDER = RC.PROFILES[PROFILE]["provider"]

CONFIG_A = dict(mgmt="none", htf=False, sides=("long", "short"), types=(1, 2, 3),
                entry="book", sloped_gate=False, st_gate=False, phase_b_gate=False, st_min=None, phase_d=True,
                combined_entry="limit")


def _log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def _cost_breakdown(trades, cost_profile):
    """(spread_R_sum, swap_R_sum, commission_R_sum, refused) over `trades`, recomputed directly from
    real_costs.cost_r (informational only -- simulate() itself only needs the summed total_R)."""
    spread = swap = commission = 0.0
    refused = 0
    for t in trades:
        try:
            d = RC.cost_r(t["entry"], t["stop"], t["entry_time"], t["exit_time"], t["symbol"], t["side"],
                          cost_profile)
        except RC.CostRefused:
            refused += 1
            continue
        spread += d["spread_R"]; swap += d["swap_R"]; commission += d["commission_R"]
    return spread, swap, commission, refused


def _cell(method, trades, *, cost_profile):
    entry_order_type = "maker" if _M.RUNNER_METHODS[method]["entry"] == "limit" else "taker"
    bt.reset_opts()
    eq, curve, taken = bt.simulate(trades, FEE, entry_order_type=entry_order_type, live_parity_sizing=False,
                                   cost_profile=cost_profile)
    gross_R = sum(t["R"] for t in taken)
    net_R = sum(t["net_R"] for t in taken)
    spread_R = swap_R = commission_R = 0.0
    refused = 0
    if cost_profile:
        spread_R, swap_R, commission_R, refused = _cost_breakdown(taken, cost_profile)
    last_exit = max((t["exit_time"] for t in taken), default=None)
    return {"n": len(taken), "gross_R": gross_R, "net_R": net_R, "spread_R": spread_R, "swap_R": swap_R,
            "commission_R": commission_R, "cost_R_total": gross_R - net_R, "refused": refused,
            "last_exit_time": last_exit}


def main():
    rows = []
    latest_bar_seen = None
    for sym in SYMBOLS:
        _log(f"scanning {sym} {TF} (flat_before_rollover=False) ...")
        bt.reset_opts()
        bt.OPTS.update(CONFIG_A)
        s0 = bt.scan(sym, TF, opts=CONFIG_A)
        _log(f"  done: ICT={len(s0['trades']['ICT']) if s0 else 0} "
             f"WYCKOFF-BOOK={len(s0['trades']['WYCKOFF-BOOK']) if s0 else 0} trades")

        _log(f"scanning {sym} {TF} (flat_before_rollover=True) ...")
        flat_opts = dict(CONFIG_A, flat_before_rollover=True, rollover_provider=PROVIDER)
        s1 = bt.scan(sym, TF, opts=flat_opts)
        _log(f"  done: ICT={len(s1['trades']['ICT']) if s1 else 0} "
             f"WYCKOFF-BOOK={len(s1['trades']['WYCKOFF-BOOK']) if s1 else 0} trades")

        for method in ("ICT", "WYCKOFF-BOOK"):
            t0 = s0["trades"][method] if s0 else []
            t1 = s1["trades"][method] if s1 else []
            baseline = _cell(method, t0, cost_profile=None)
            real_no_flat = _cell(method, t0, cost_profile=PROFILE)
            real_flat = _cell(method, t1, cost_profile=PROFILE)
            for cell in (baseline, real_no_flat, real_flat):
                if cell["last_exit_time"] and (latest_bar_seen is None or cell["last_exit_time"] > latest_bar_seen):
                    latest_bar_seen = cell["last_exit_time"]
            rows.append({"symbol": sym, "method": method, "baseline": baseline,
                        "real_no_flat": real_no_flat, "real_flat": real_flat})
        _log(f"{sym} done")

    # Recorded as the relative form (matches every other --history-root/HISTORY_ROOT string this repo prints
    # or snapshots) so a committed copy of this file does not embed one machine's absolute worktree path.
    out = {"pit_cutoff": PIT_CUTOFF, "history_root": "data/history/ftmo", "profile": PROFILE,
           "latest_trade_exit_time_seen": latest_bar_seen, "rows": rows}
    out_path = os.path.join(ROOT, "docs", "audits", "2026-09-29-real-costs-reprice.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print(json.dumps(out, indent=2))
    _log(f"ALL DONE -- wrote {out_path}")


if __name__ == "__main__":
    main()
