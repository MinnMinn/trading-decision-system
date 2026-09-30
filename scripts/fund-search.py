#!/usr/bin/env python3
"""The FUND-SETUP evaluation harness (docs/plans/2026-09-28-methodology-improvement-plan.md §1.4, §3, §4, §6
items 2-8; docs/plans/2026-09-29-execution-plan.md Batch 2(b)). Research integrity is the product: the cell
space is enumerated and committed BEFORE anything is evaluated (`plan`), the final cell count is recorded in
docs/architecture/research-ledger.json BEFORE any evaluation (`declare`) and `run` REFUSES without it, every
evaluated candidate -- pass or fail -- is an immutable §42 record, and the report lists every one of them, the
FULL count, and states plainly when there are zero passes.

Usage:
    python3 scripts/fund-search.py plan --dry-run [--grid-dir DIR]     # cells, N, confidence; evaluates NOTHING
    python3 scripts/fund-search.py plan [--grid-dir DIR]               # commit docs/experiments/fund-search/plan.json
    python3 scripts/fund-search.py declare                             # record the cell count in the research ledger
    python3 scripts/fund-search.py list-cells                          # JSON cell list (the CI matrix)
    python3 scripts/fund-search.py run --cell <id> [--method ict|wyckoff] [--workers N]
    python3 scripts/fund-search.py run ... [--scan-cache DIR ...]      # load verified Actions scan shards (docs/audits/2026-09-30-actions-sharding.md)
    python3 scripts/fund-search.py scan --cell <id> --symbol <S> --method ict|wyckoff --out DIR [--wave 1|2] [--slice I/N]
    python3 scripts/fund-search.py list-scan-shards [--wave 1|2] [--explain]   # the scan-shard matrix (JSON)
    python3 scripts/fund-search.py report

The statistics are scripts/fund_stats.py (pure, separately tested). This file only orchestrates: cells, the
engine adapter (scripts/backtest-methods.py scan + simulate, unmodified), sealed records (scripts/experiment.py),
the ledger declaration (scripts/research_ledger.py), one scan pool per candidate (scripts/scan_many.py, whose
processes come from scripts/isolated_pool.py).

FIXED IN EVERY CELL (plan §6 items 3, 7): real FTMO costs (`COST_PROFILE`, data/history/costs/ftmo/) and
flat-before-rollover (no overnight holding). A grid item that tries to override either is refused
(`validate_grid`). The FTMO commission is UNKNOWN (symbolspec commission.status == "no_deals"): it is taken from
the cost data only -- scripts/real_costs.py returns 0.0 with its status -- and disclosed in every record.

Nothing here evaluates real history unless `run` is invoked, and `run` needs the plan, the ledger declaration
and an implemented grid. Batch 3 (owner sign-off) is the only place that happens.
"""
import argparse
import contextlib
import datetime
import hashlib
import importlib.util
import json
import os
import re
import sys
import time
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from repo_paths import repo_rel
import fund_stats as FS               # the statistics: pure, separately importable and tested
import experiment as X                # CLAUDE.md §42: the ONE reader/writer of the experiment store
import research_ledger as RL          # CLAUDE.md §43/§44: periods + the cell-count declaration
import history_store as _HS           # the shared history reader / HISTORY_ROOT (single-file or split-gz)
import instruments as _I              # asset_class of each symbol
import scan_many as SM                # N value sets in one pass over a series, chunk-parallel (byte-identical to scan())

PLAN_DOC = "docs/plans/2026-09-28-methodology-improvement-plan.md"
EXPERIMENT_DIR = os.path.join(ROOT, "docs", "experiments", "fund-search")
PLAN_PATH = os.path.join(EXPERIMENT_DIR, "plan.json")     # committed artifact: never redirected by an env var
RECORDS_DIR = os.environ.get("FUND_SEARCH_RECORDS_DIR") or os.path.join(EXPERIMENT_DIR, "records")
REPORT_PATH = os.environ.get("FUND_SEARCH_REPORT_PATH") or os.path.join(
    ROOT, "docs", "backtests", "fund-search-report.md")
GRID_DIR = os.environ.get("FUND_SEARCH_GRID_DIR") or os.path.join(ROOT, "docs", "architecture")
FTMO_HISTORY_ROOT = os.path.join(ROOT, "data", "history", "ftmo")

# ------------------------------------------------------------------ scope, all pre-declared (plan §6 items 7, 8)
FUND_SYMBOLS = ("XAUUSD", "XAGUSD", "US500", "US30", "USTEC", "DE40", "FRA40")   # §6 item 8: AUS200 dropped, no data
FUND_TIMEFRAMES = ("1m", "5m", "15m", "30m")                                    # §6 item 7
ASSET_CLASSES = ("metals", "indices")                                           # §6 item 7
METHODS = {"ict": "ICT", "wyckoff": "WYCKOFF-BOOK"}                             # grid `method` -> bt runner method
GRID_FILES = {"ict": "v-grid-ict.json", "wyckoff": "v-grid-wyckoff.json"}
COST_PROFILE = "ftmo_demo_2026_09"                                              # §6 item 3: REAL costs, fixed on
DEV_PERIOD_ID = "cfd-development-pre-2024-03"                                   # research-ledger.json period
LEDGER_SECTION = "fund_search"                                                  # the declaration lives here
#: The nine F (fidelity) items the owner adopted for the evaluation baseline (docs/plans/2026-09-30-owner-decisions.md):
#: ON in every cell of every candidate, never varied, never settable by a grid item. Live/pilot keep v1.
#: Plus O1 (owner-approved 2026-09-30): `fx_admission_entry_cost` -- min_rr admission uses only entry-knowable costs
#: (scripts/backtest-methods.py simulate()). It is a fixed engine rule, not an F item; it lives in this tuple so it
#: is ON in every cell, in the plan hash and declaration config, and can never be set by a grid item.
ADOPTED_F_KEYS = ("fx_b2a_fvg_in_leg", "fx_b2b_ce_fail", "fx_b1_pivot1", "fx_braid_optional",
                  "fx_w1_tr_low_st", "fx_w2_st_below_sc", "fx_w3_mSOW_spring", "fx_w5_vp_abandon", "fx_w7_htf_target",
                  "fx_admission_entry_cost")
FIXED_KEYS = ("flat_before_rollover", "rollover_provider") + ADOPTED_F_KEYS       # a grid item may never set these

#: O2 (owner-approved 2026-09-30): walk-forward training embargo = EMBARGO_H_MULTIPLE x H bars of the cell's
#: timeframe (H = the engine's own bt.P[tf]["H"]). 2H is the largest FINITE time stop of the declared V grids; a
#: "none" time stop cannot be embargoed by any finite window and is covered only by this same 2H.
EMBARGO_H_MULTIPLE = 2
_ENGINE_P = None


def embargo_for(tf, bt=None):
    """The training embargo of a `tf` cell as a timedelta, from the engine's own P table (`bt.P`); `bt` defaults to
    one shared, lazily loaded engine instance. Fails loud (KeyError/ValueError) on an unknown timeframe."""
    global _ENGINE_P
    if bt is None:
        if _ENGINE_P is None:
            _ENGINE_P = _load_bt()
        bt = _ENGINE_P
    return EMBARGO_H_MULTIPLE * int(bt.P[tf]["H"]) * FS.bar_delta(tf)


#: Disclosed, never folded into N (plan §1.4): earlier searches on the same history.
PRIOR_COUNTS = {"prop_search_records": 180, "diagnosis_slices": 30}


def fixed_opts():
    """The OPTS overlay applied in EVERY cell: flat before the broker's daily rollover, priced by the profile's
    own server clock (scripts/real_costs.py PROFILES)."""
    import real_costs as _RC
    out = {"flat_before_rollover": True, "rollover_provider": _RC.PROFILES[COST_PROFILE]["provider"]}
    out.update({k: True for k in ADOPTED_F_KEYS})
    return out


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


class GridRefused(SystemExit):
    """The V grid cannot be used (missing, malformed, unimplemented items, or it tries to unfix a fixed rule)."""


class LedgerDeclarationMissing(SystemExit):
    """`run` refused: the cell count was not recorded in the research ledger (plan §6 item 7)."""


# ------------------------------------------------------------------------------------------------- the grids
def load_grids(grid_dir=None):
    grid_dir = grid_dir or GRID_DIR
    grids, paths = {}, {}
    for m, fn in GRID_FILES.items():
        p = os.path.join(grid_dir, fn)
        if not os.path.exists(p):
            raise GridRefused(f"grid file missing: {p} -- N is read from the pre-declared V grid, never typed "
                              f"here (plan §3); refusing to guess it")
        try:
            g = FS.load_grid(p)
        except (FS.GridError, ValueError) as exc:
            raise GridRefused(f"{p}: {exc}")
        validate_grid(g, p)
        grids[m], paths[m] = g, p
    return grids, paths


#: Existing (non-fx_) OPTS keys a grid item may drive. Everything else must be a new `fx_` key (execution plan
#: "Shared contract"). An ALLOW-LIST, not a deny-list (fix round 1, S1): a key nobody listed cannot be set.
#: Extending it is a deliberate, reviewed edit -- e.g. B-MGMT / W-MGMT use `mgmt`.
ALLOWED_EXISTING_OPTS = ("mgmt",)


def validate_grid(grid, where="grid"):
    """Only grid-declared item keys plus the listed existing OPTS keys may be set, and never a FIXED rule (real
    costs / flat-before-rollover stay on in every cell)."""
    for it in grid.items:
        key = grid.opts_key(it["id"])
        if key in FIXED_KEYS:
            raise GridRefused(f"{where}: item {it['id']!r} sets OPTS key {key!r}, which is FIXED in every fund cell "
                              f"(plan §6 item 7): refusing")
        if not (key.startswith("fx_") or key in ALLOWED_EXISTING_OPTS):
            raise GridRefused(f"{where}: item {it['id']!r} sets OPTS key {key!r}, which is neither an `fx_` key nor "
                              f"in the allow-list {ALLOWED_EXISTING_OPTS} (fix round 1, S1): refusing")


_TIME_STOP_RE = re.compile(r"time[_\- ]?stop", re.I)


def grid_has_no_time_stop_value(grid):
    """True when a time-stop item (id or key names it) declares the value "none" (no time exit)."""
    return any(_TIME_STOP_RE.search(f"{it['id']} {it['key']} {it.get('existing_opts_key') or ''}")
               and "none" in it["values"] for it in grid.items)


def assert_grid_runnable(grid):
    """Merge-time guards (round 2, item 5): (a) no unimplemented item; (b) a grid that can remove the time stop
    runs only with flat_before_rollover fixed on."""
    # Items declared but not implemented (implemented:false: B4, W4b) are NEVER evaluated -- selection and the
    # engine see grid.runnable() -- yet they stay counted in N (n_per_method on the FULL grid), which only makes
    # the bound stricter. They are listed in `plan` and in every record.
    if grid_has_no_time_stop_value(grid.runnable()):
        assert_flat_overlay(fixed_opts())


def build_overlay(grid, values):
    """The OPTS overlay for one full V assignment: fixed rules + ONLY the keys the grid declares, each at a value
    the grid declares (a V value nobody pre-declared is refused BEFORE any scan -- item 5c)."""
    allowed = {grid.opts_key(i["id"]) for i in grid.items}
    unknown = [i for i in values if i not in grid.by_id]
    if unknown:
        raise GridRefused(f"V assignment names items not in the grid: {unknown}")
    for i, v in values.items():
        if v not in grid.by_id[i]["values"]:
            raise GridRefused(f"V assignment sets item {i!r} to {v!r}, which the grid does not declare "
                              f"({grid.by_id[i]['values']}): refusing before scanning (plan §3: the value sets are "
                              f"the whole grid)")
    overlay = grid.overlay(values)
    extra = set(overlay) - allowed
    if extra:
        raise GridRefused(f"overlay keys {sorted(extra)} are not declared by the grid")
    out = dict(overlay, **fixed_opts())
    if grid_has_no_time_stop_value(grid):
        assert_flat_overlay(out)
    return out


# -------------------------------------------------------------------------------------------- cell enumeration
def _first_bar(sym, tf):
    """ISO time of the series' first bar, or None. Split series carry it in index.json (no full read)."""
    root = _HS.history_root()
    path, shape = _HS.resolve(sym, tf, root=root)
    if path is None:
        return None
    if shape == "split":
        with open(os.path.join(path, "index.json"), encoding="utf-8") as fh:
            first = json.load(fh).get("first")
        return first
    d = _HS.read_at(path, shape)
    c = d.get("candles") or []
    return c[0]["time"] if c else None


def build_cells(first_bar=None):
    """{tf} x {metals, indices}, minus any cell without development history before DEV_CUTOFF (plan §6 item 7).
    Decided from DATA AVAILABILITY only -- never from a result. A symbol without development history is listed
    (with the reason) and is not part of m, the stability denominator; it is not silently forgotten."""
    first_bar = first_bar or _first_bar
    cells, excluded = [], []
    cutoff = FS.ts(FS.DEV_CUTOFF)
    for tf in FUND_TIMEFRAMES:
        for ac in ASSET_CLASSES:
            syms = [s for s in FUND_SYMBOLS if (_I.display(s).get("asset_class") or "cfd") == ac]
            with_dev, without = [], {}
            for s in syms:
                fb = first_bar(s, tf)
                if fb is None:
                    without[s] = "no history file"
                elif FS.ts(fb) >= cutoff:
                    without[s] = f"first bar {fb} is not before {FS.DEV_CUTOFF}"
                else:
                    with_dev.append((s, fb))
            cid = f"{tf}-{ac}"
            if not with_dev:
                excluded.append({"id": cid, "timeframe": tf, "asset_class": ac,
                                 "reason": "no symbol has development history before " + FS.DEV_CUTOFF,
                                 "symbols_without_development": without})
                continue
            dev_start = min((fb for _, fb in with_dev), key=FS.ts)
            nf = len(FS.make_folds(dev_start))
            cells.append({"id": cid, "timeframe": tf, "asset_class": ac,
                          "symbols": [s for s, _ in with_dev],
                          "symbols_without_development": without,
                          "development_start": dev_start,
                          "n_folds": nf, "frequency_rule": FS.fold_arithmetic(nf)})
    return cells, excluded


def _hash(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def build_plan(grid_dir=None, first_bar=None):
    grids, paths = load_grids(grid_dir)
    cells, excluded = build_cells(first_bar)
    n_cells = len(cells)
    grids_info, n_by_method, conf = {}, {}, {}
    for m, g in grids.items():
        per_cell = FS.n_per_method(g)
        n_total = per_cell * n_cells
        grids_info[m] = {"file": repo_rel(paths[m], ROOT) if paths[m].startswith(ROOT) else paths[m],
                         "sha256": _sha256_file(paths[m]), "method": g.method, "items": len(g.items),
                         "non_baseline_values": per_cell - 2, "n_per_cell": per_cell,
                         "unimplemented": g.unimplemented}
        n_by_method[m] = n_total
        conf[m] = FS.n_adjusted_confidence(n_total) if n_total >= 1 else None
    candidates = []
    for c in cells:
        for m in METHODS:
            candidates.append({"id": f"{m}-{c['id']}", "method": m, "runner_method": METHODS[m], "cell": c["id"],
                               "timeframe": c["timeframe"], "asset_class": c["asset_class"],
                               "symbols": list(c["symbols"]), "n_comparisons": n_by_method[m]})
    embargo = {"rule": f"training trades need exit_label < test_start - {EMBARGO_H_MULTIPLE} x H bars (H = bt.P[tf]['H'])"
                       f", on top of the one-bar purge; 'none' time stops are covered only by this same window",
               "h_multiple": EMBARGO_H_MULTIPLE,
               "minutes_by_timeframe": {tf: int(embargo_for(tf) / datetime.timedelta(minutes=1))
                                        for tf in FUND_TIMEFRAMES}}
    core = {"cells": cells, "excluded_cells": excluded, "grids": grids_info, "candidates": candidates,
            "n_by_method": n_by_method, "cost_profile": COST_PROFILE, "dev_cutoff": FS.DEV_CUTOFF,
            "adopted_f_keys": list(ADOPTED_F_KEYS), "embargo": embargo,
            "constants": {k: getattr(FS, k) for k in (
                "FAMILY_ALPHA", "MIN_FOLD_TRADES", "MIN_TRAIN_TRADES", "MAX_TRADE_SHARE", "MAX_GAP_DAYS",
                "MIN_FOLD_SHARE_OK", "PASS_PROB_MIN", "ADX_PERIOD", "TEST_FOLD_DAYS", "MIN_TRAIN_DAYS",
                "MIN_TEST_FOLDS")}}
    plan = dict(core, _source=PLAN_DOC, cell_count=n_cells, candidate_count=len(candidates),
                confidence_by_method=conf, fund_symbols=list(FUND_SYMBOLS), prior_counts_disclosed=PRIOR_COUNTS,
                plan_hash=_hash(core))
    return plan


def format_dry_run(plan, grid_note=""):
    L = [f"fund-search plan --dry-run: NOTHING is evaluated; no file is written{grid_note}",
         f"cells ({plan['cell_count']}), cost profile {plan['cost_profile']}, development cutoff {plan['dev_cutoff']}:"]
    for c in plan["cells"]:
        fr = c["frequency_rule"]
        L.append(f"  {c['id']:<14} m={len(c['symbols'])} symbols {','.join(c['symbols'])}  "
                 f"dev start {c['development_start']}  folds {c['n_folds']} (frequency rule: >= "
                 f"{fr['folds_required_within_gap']} of {fr['n_folds']} folds with every gap <= "
                 f"{fr['max_gap_days']}d; {fr['folds_allowed_to_fail']} may fail)")
        for s, why in c["symbols_without_development"].items():
            L.append(f"      not in m: {s} ({why})")
    for e in plan["excluded_cells"]:
        L.append(f"  EXCLUDED {e['id']:<10} {e['reason']}")
    L.append(f"candidates: {plan['candidate_count']} (method x cell)")
    for m, g in plan["grids"].items():
        n = plan["n_by_method"][m]
        conf = plan["confidence_by_method"][m]
        L.append(f"  {m:<8} N per cell {g['n_per_cell']} x {plan['cell_count']} cells = N {n}; one-sided "
                 f"confidence 1 - {FS.FAMILY_ALPHA}/{n} = {conf:.6f}"
                 + (f"; declared, not runnable, counted in N: {g['unimplemented']}" if g["unimplemented"] else ""))
    L.append(f"plan_hash {plan['plan_hash'][:16]}")
    return "\n".join(L)


def cmd_plan(dry_run=False, grid_dir=None):
    plan = build_plan(grid_dir)
    if dry_run:
        note = f" (grid: {grid_dir})" if grid_dir else ""
        print(format_dry_run(plan, note))
        return plan
    if os.path.exists(PLAN_PATH):
        existing = json.load(open(PLAN_PATH, encoding="utf-8"))
        if existing.get("plan_hash") == plan["plan_hash"]:
            print(f"plan unchanged: {plan['candidate_count']} candidates, hash {plan['plan_hash'][:12]}")
            return existing
        raise SystemExit(
            f"refusing to change the committed plan at {PLAN_PATH}: the recomputed space differs "
            f"(hash {plan['plan_hash'][:12]} vs committed {existing.get('plan_hash', '?')[:12]}). Changing a "
            f"pre-registration after the first evaluation is an experiment event that needs a ledger entry "
            f"({PLAN_DOC} §3: 'Nothing is added after data is seen without a ledger event').")
    os.makedirs(EXPERIMENT_DIR, exist_ok=True)
    with open(PLAN_PATH, "w", encoding="utf-8") as fh:
        json.dump(dict(plan, generated_at=_now_iso()), fh, ensure_ascii=False, indent=1)
    print(f"wrote {PLAN_PATH}: {plan['cell_count']} cells, {plan['candidate_count']} candidates, "
          f"hash {plan['plan_hash'][:12]}")
    return plan


def load_plan(grid_dir=None):
    if not os.path.exists(PLAN_PATH):
        raise SystemExit(f"no plan at {PLAN_PATH}; run `python3 scripts/fund-search.py plan` first")
    committed = json.load(open(PLAN_PATH, encoding="utf-8"))
    fresh = build_plan(grid_dir)
    if fresh["plan_hash"] != committed.get("plan_hash"):
        raise SystemExit(f"{PLAN_PATH} no longer matches the recomputed cell space (committed "
                         f"{committed.get('plan_hash', '?')[:12]} != recomputed {fresh['plan_hash'][:12]}); "
                         f"refusing to run against an altered plan")
    return committed


# ------------------------------------------------------------------------------- the research-ledger declaration
def _ledger_path():
    return RL.PATH


def _read_ledger():
    with open(_ledger_path(), encoding="utf-8") as fh:
        return json.load(fh)


def require_declaration(plan):
    """`run` refuses unless the research ledger records THIS plan's final cell count (plan §6 item 7: 'recorded in
    research-ledger.json before any evaluation'), and the development period is still `development`."""
    decl = (_read_ledger().get(LEDGER_SECTION) or {})
    if not decl:
        raise LedgerDeclarationMissing(
            f"refusing to run: {_ledger_path()} has no `{LEDGER_SECTION}` declaration. The final cell count must "
            f"be recorded in the research ledger BEFORE any evaluation (plan §6 item 7): run "
            f"`python3 scripts/fund-search.py declare` (after `plan`), then commit it.")
    want = {"plan_hash": plan["plan_hash"], "cell_count": plan["cell_count"],
            "cells": [c["id"] for c in plan["cells"]]}
    for k, v in want.items():
        if decl.get(k) != v:
            raise LedgerDeclarationMissing(
                f"refusing to run: the ledger's `{LEDGER_SECTION}.{k}` is {decl.get(k)!r} but the plan says {v!r} "
                f"-- the declaration does not match the committed plan (plan §3: nothing is added after data is "
                f"seen without a ledger event)")
    try:
        state = RL.state_of(DEV_PERIOD_ID)
    except RL.NotDeclared as exc:
        raise LedgerDeclarationMissing(f"refusing to run: {exc}")
    if state != RL.DEVELOPMENT:
        raise LedgerDeclarationMissing(f"refusing to run: period {DEV_PERIOD_ID!r} is {state}, not development")
    return decl


def _git(*a):
    import subprocess
    try:
        out = subprocess.run(["git", "-C", ROOT, *a], capture_output=True, text=True, timeout=20)
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


FINGERPRINT_FILES = ("scripts/fund_stats.py", "scripts/fund-search.py", "scripts/prop-search.py",
                     "scripts/backtest-methods.py", "scripts/real_costs.py", "scripts/performance.py",
                     "scripts/mt5_time.py", "scripts/ict-scan.py", "scripts/wyckoff_rules.py",
                     "scripts/live_rules.py", "scripts/scan_many.py", "scripts/structures.py")


def code_fingerprint(files=FINGERPRINT_FILES):
    """I4: the last-commit SHA of each file that decides a result, plus whether it has uncommitted changes. A
    missing git yields None, never a guess."""
    out = {}
    for f in files:
        sha = _git("log", "-1", "--format=%H", "--", f)
        status = _git("status", "--porcelain", "--", f)
        out[f] = {"git_sha": sha or None, "dirty": (bool(status) if status is not None else None)}
    return out


def evaluation_config(plan):
    """I4: every setting that decides a verdict, stated once so the declaration pins it."""
    ps = _prop_search()
    return {"stability_fraction": list(FS.STABILITY_FRACTION), "block_days": FS.BLOCK_DAYS,
            "live_parity_sizing": {"trades_for": False, "prop_pass": True}, "spread_stat": "median",
            "prop_funds": list(ps.FUNDS), "prop_horizon_days": ps.CHALLENGE_HORIZON_DAYS,
            "prop_pass_min": FS.PASS_PROB_MIN, "verdict_precedence": FS.VERDICT_PRECEDENCE,
            "regime_split": FS.REGIME_SPLIT_DEFINITION,
            "ruin_handling": "bt.RUIN_FRAC = 0.0 on the harness's own bt instance; post_ruin trades fail loud",
            "adopted_f_keys": list(ADOPTED_F_KEYS), "embargo": plan["embargo"],
            "grid_sha256": {m: g["sha256"] for m, g in plan["grids"].items()}}


class DeclarationDrift(SystemExit):
    """`run` refused: the code or evaluation settings differ from what `declare` recorded (fix round 2, item 3)."""


def detect_drift(decl, plan):
    """Every difference between the declaration and the code/settings that would run NOW. Empty = no drift."""
    out = []
    dc = decl.get("code")
    if not isinstance(dc, dict) or not dc:
        out.append("declaration has no `code` fingerprint")
    else:
        now = code_fingerprint(tuple(sorted(set(dc) | set(FINGERPRINT_FILES))))
        for f in sorted(now):
            if dc.get(f) != now[f]:
                out.append(f"code {f}: declared {dc.get(f)!r}, now {now[f]!r}")
    dcfg = decl.get("evaluation_config")
    if not isinstance(dcfg, dict) or not dcfg:
        out.append("declaration has no `evaluation_config`")
    else:
        cfg = evaluation_config(plan)
        for k in sorted(set(dcfg) | set(cfg)):
            if dcfg.get(k) != cfg.get(k):
                out.append(f"evaluation_config.{k}: declared {dcfg.get(k)!r}, now {cfg.get(k)!r}")
    return out


def check_drift(decl, plan, allow_drift=False):
    drift = detect_drift(decl, plan)
    if drift and not allow_drift:
        raise DeclarationDrift(
            "refusing to run: the code or evaluation settings differ from what `declare` recorded in the ledger:\n  "
            + "\n  ".join(drift) + "\nRe-declare through a ledger event, or pass --allow-drift to proceed with "
            "every record stamped drifted=true.")
    return drift


def cmd_declare():
    """Record the final cell count in the ledger. Refuses if any evaluation record already exists (the count must
    precede evaluation) or if a different declaration is already there (a ledger event, not an overwrite)."""
    plan = load_plan()
    if os.path.isdir(RECORDS_DIR) and any(f.endswith(".json") for f in os.listdir(RECORDS_DIR)):
        raise SystemExit(f"refusing to declare: records already exist under {RECORDS_DIR}; the cell count must be "
                         f"recorded BEFORE any evaluation")
    data = _read_ledger()
    new = {"plan_hash": plan["plan_hash"], "cell_count": plan["cell_count"],
           "cells": [c["id"] for c in plan["cells"]], "n_by_method": plan["n_by_method"],
           "confidence_by_method": plan["confidence_by_method"], "excluded_cells": plan["excluded_cells"],
           "code": code_fingerprint(), "evaluation_config": evaluation_config(plan),
           "source": PLAN_DOC + " §6 items 2, 7", "declared_at": _now_iso()}
    old = data.get(LEDGER_SECTION)
    if old:
        if all(old.get(k) == new[k] for k in ("plan_hash", "cell_count", "cells")):
            print("declaration unchanged")
            return old
        raise SystemExit(f"refusing to overwrite the existing `{LEDGER_SECTION}` declaration with a different "
                         f"one: changing it after the fact is a ledger event, not an edit")
    data[LEDGER_SECTION] = new
    with open(_ledger_path(), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(f"declared {new['cell_count']} cells in {_ledger_path()}")
    return new


# ---------------------------------------------------------------------------------- the engine adapter (real)
_PROP = None


def _prop_search():
    """scripts/prop-search.py (FUNDS, the 120-day gating horizon): reused, not copied."""
    global _PROP
    if _PROP is None:
        spec = importlib.util.spec_from_file_location("prop_search", os.path.join(ROOT, "scripts", "prop-search.py"))
        _PROP = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_PROP)
    return _PROP


def _load_bt():
    spec = importlib.util.spec_from_file_location("bt", os.path.join(ROOT, "scripts", "backtest-methods.py"))
    bt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bt)
    return bt


# ------------------------------------------------------------------ simulate() guards (fix round 1: I1, I2, I6, S1)
def neutralise_ruin(bt):
    """I1: simulate()'s account=None path stops at RUIN_FRAC and silently moves later trades to
    SIM_LAST["post_ruin"]. R does not depend on equity, so a research run turns the ruin stop off on ITS OWN
    freshly-loaded `bt` instance (RUIN_FRAC = 0.0); no other caller's v1 output changes."""
    bt.RUIN_FRAC = 0.0


def assert_flat_overlay(overlay):
    """Item 5(b): every candidate is simulated under flat_before_rollover=True. A grid value that removes the time
    stop ("none") is only safe because no position may then be held overnight; refuse if the overlay says otherwise."""
    if not isinstance(overlay, dict) or overlay.get("flat_before_rollover") is not True:
        raise GridRefused("flat_before_rollover is not True in the candidate's OPTS overlay: refusing to simulate "
                          "(no overnight holding is a FIXED rule, plan §6 item 7)")


def checked_simulate(bt, trades, fee, *, overlay, **kw):
    """`bt.simulate` that FAILS LOUD when the run ended in ruin / dropped trades (I1), so a lost trade is never a
    silent outcome, and when the candidate's overlay does not have flat_before_rollover on (round 2, item 5b).
    Returns simulate's own (equity, curve, taken)."""
    assert_flat_overlay(overlay)
    out = bt.simulate(trades, fee, **kw)
    last = getattr(bt, "SIM_LAST", None) or {}
    post = last.get("post_ruin") or []
    if post or last.get("ruin") is not None:
        raise RuntimeError(f"simulate() stopped the account (ruin={last.get('ruin')!r}, failed_by="
                           f"{last.get('failed_by')!r}) and moved {len(post)} later trade(s) to post_ruin: a "
                           f"research run must never lose trades silently (fix round 1, I1)")
    return out


def assert_no_rollover_crossing(taken, provider, tf):
    """S1 (round 2 corrected): flat-before-rollover is FIXED on. `entry_time`/`exit_time` are bar OPEN labels and
    the engine checks the rollover only AFTER each walked bar, never between the entry bar and the first walked
    bar. So the comparison is on the walked-bar basis: from the entry bar's CLOSE (entry label + one bar) to the
    exit label. A trade whose exit label is not after that close has no walked-bar span to cross."""
    import real_costs as _RC
    dt = FS.bar_delta(tf)
    bad = []
    for t in taken:
        start = FS.ts(t["entry_time"]) + dt
        if FS.ts(t["exit_time"]) >= start and _RC.crosses_rollover(FS.iso(start), t["exit_time"], provider):
            bad.append(t)
    if bad:
        raise RuntimeError(f"{len(bad)} taken trade(s) cross the server rollover although flat_before_rollover is "
                           f"fixed on (first: {bad[0]['symbol']} {bad[0]['entry_time']} -> {bad[0]['exit_time']})")


def last_bar_entry_times(taken, tf, provider):
    """Entry labels whose entry bar is the LAST bar of a server day (the next bar opens on a new server date).
    Recorded, never raised on: the Wyckoff entry there is legitimate, but an ICT fill INSIDE that bar can be held
    past midnight because the engine never asks about the entry bar -- OPEN owner item O8."""
    import real_costs as _RC
    dt = FS.bar_delta(tf)
    return [t["entry_time"] for t in taken
            if _RC.crosses_rollover(t["entry_time"], FS.iso(FS.ts(t["entry_time"]) + dt), provider)]


def rollover_edge_stats(times, fold=None):
    if fold is not None:
        a, b = FS.ts(fold["test_start"]), FS.ts(fold["test_end"])
        times = [x for x in times if a <= FS.ts(x) < b]
    return {"entries_on_last_bar_of_server_day": len(times)}


NEAR_FLOOR_MARGIN = 0.25


def admission_stats(rows, min_rr, fold=None):
    """I2: simulate()'s admission test is `R_planned - fee_R < min_rr` with fee_R INCLUDING the exit-hour spread,
    i.e. admission depends on the future exit time (plan §37 look-ahead). simulate() is not changed (v1 stays
    byte-identical); this only MEASURES it: candidates, how many the filter refused, and the margin
    (R_planned - fee_R - min_rr) near the floor."""
    if fold is not None:
        a, b = FS.ts(fold["test_start"]), FS.ts(fold["test_end"])
        rows = [r for r in rows if a <= FS.ts(r["entry_time"]) < b]
    margins = [r["R_planned"] - r["fee_R"] - min_rr for r in rows]
    near = sorted(m for m in margins if abs(m) < NEAR_FLOOR_MARGIN)
    return {"candidates": len(rows), "refused_min_rr": sum(1 for m in margins if m < 0),
            "min_rr": min_rr, "near_floor_margin": NEAR_FLOOR_MARGIN, "near_floor_n": len(near),
            "near_floor_refused": sum(1 for m in near if m < 0),
            "near_floor_margin_min": near[0] if near else None,
            "near_floor_margin_median": near[len(near) // 2] if near else None,
            "near_floor_margin_max": near[-1] if near else None}


def prop_row_from_metric(p):
    """I6: a performance.metrics prop_pass_probability entry -> {value, reason, low_confidence, spread_min}."""
    if isinstance(p, dict) and isinstance(p.get("value"), (int, float)):
        spread = (p.get("spread") or {}).get("prop_pass_probability")
        return {"value": p["value"], "low_confidence": bool(p.get("low_confidence")),
                "spread_min": spread[0] if isinstance(spread, (list, tuple)) and spread else None}
    reason = p.get("unavailable") if isinstance(p, dict) else None
    return {"value": None, "reason": reason or "metric absent"}


# ------------------------------------------------------------------ scan cache (GitHub Actions sharding, audit
# docs/audits/2026-09-30-actions-sharding.md). The expensive, SYMBOL-LOCAL unit of a candidate is the raw output of
# one `scan_many` for one (value set, symbol): the trade list `bt.scan` returns BEFORE `trades_for` post-processes it.
# A shard job computes and persists those; the evaluating job loads them into `BtEngine._raw` and runs the unchanged
# `trades_for` (pooling, timeout exclusion, admission/rollover rows, simulate, adx14) on them -- so the result is the
# one a cache-less run computes. An entry is only ever used when its whole identity matches THIS run; anything else
# is REFUSED loudly, never skipped, never "close enough".
SCAN_CACHE_FORMAT = 1


class ScanCacheRefused(SystemExit):
    """A scan-cache entry cannot be trusted (different code / plan / settings / data, or torn or tampered file)."""


def _canon(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def scan_cache_stamp(plan):
    """What every entry of one cache must share: the plan, the code (last-commit SHAs, dirty flags AND file content
    hashes, so two dirty trees never look alike) and the evaluation settings -- the same three things `declare`
    pins. The FTMO history is covered per entry by `scope.series` (bar count, first and last bar of the PIT-truncated
    series the scan read)."""
    return {"format": SCAN_CACHE_FORMAT, "plan_hash": plan["plan_hash"], "code": code_fingerprint(),
            "code_sha256": {f: _sha256_file(os.path.join(ROOT, f)) for f in FINGERPRINT_FILES},
            "evaluation_config": evaluation_config(plan)}


def scan_cache_scope(cell_id, runner_method, tf, symbol, value_key, series):
    return {"cell": cell_id, "runner_method": runner_method, "timeframe": tf, "symbol": symbol,
            "value_key": value_key, "series": dict(series)}


def scan_cache_key(stamp, scope):
    return _sha_text(_canon({"stamp": stamp, "scope": scope}))


def _diff_lines(want, got, prefix=""):
    out = []
    if isinstance(want, dict) and isinstance(got, dict):
        for k in sorted(set(want) | set(got)):
            out += _diff_lines(want.get(k), got.get(k), f"{prefix}{k}.")
    elif _canon(want) != _canon(got):
        out.append(f"{prefix.rstrip('.') or 'value'}: this run {want!r}, entry {got!r}")
    return out


def write_scan_entry(out_dir, stamp, scope, trades):
    """Persist one (value set, symbol) raw scan. Deterministic bytes (no timestamp); written atomically. Fails loud if
    the trades do not survive a JSON round trip unchanged (types, key order, float text) -- a cache that altered a
    trade would break byte-identity, so it is never written."""
    body = json.dumps(trades, ensure_ascii=False, separators=(",", ":"))
    if repr(json.loads(body)) != repr(trades):
        raise ScanCacheRefused(f"scan cache: the trades of {scope['symbol']} / {scope['value_key']} are not JSON "
                               f"round-trippable unchanged; refusing to write an entry that could alter a result")
    key = scan_cache_key(stamp, scope)
    entry = {"format": SCAN_CACHE_FORMAT, "key": key, "stamp": stamp, "scope": scope, "n_trades": len(trades),
             "trades_sha256": _sha_text(body), "trades": trades}
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, key + ".json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")))
    os.replace(tmp, path)
    return path


_ENTRY_KEYS = ("format", "key", "stamp", "scope", "n_trades", "trades_sha256", "trades")
_SCOPE_KEYS = ("cell", "runner_method", "timeframe", "symbol", "value_key", "series")


def read_scan_entry(path, stamp):
    """One entry, fully verified against `stamp` (this run's plan / code / settings). Raises ScanCacheRefused."""
    def bad(why):
        raise ScanCacheRefused(f"scan cache REFUSED: {path}: {why}")
    try:
        with open(path, encoding="utf-8") as fh:
            entry = json.loads(fh.read())
    except (OSError, ValueError) as exc:
        bad(f"unreadable, torn or partial file ({type(exc).__name__}: {exc})")
    if not isinstance(entry, dict) or any(k not in entry for k in _ENTRY_KEYS):
        bad(f"not a complete entry (missing {[k for k in _ENTRY_KEYS if not isinstance(entry, dict) or k not in entry]})")
    if entry["format"] != SCAN_CACHE_FORMAT:
        bad(f"format {entry['format']!r}, this code reads {SCAN_CACHE_FORMAT}")
    diff = _diff_lines(stamp, entry["stamp"])
    if diff:
        bad("made by a different plan / code / evaluation settings than this run:\n  " + "\n  ".join(diff[:12]))
    scope = entry["scope"]
    if not isinstance(scope, dict) or any(k not in scope for k in _SCOPE_KEYS):
        bad("incomplete scope")
    if entry["key"] != scan_cache_key(entry["stamp"], scope) or os.path.basename(path) != entry["key"] + ".json":
        bad("the content hash does not match the file's key/name (renamed, edited or foreign file)")
    trades = entry["trades"]
    if not isinstance(trades, list) or len(trades) != entry["n_trades"]:
        bad(f"trade count {len(trades) if isinstance(trades, list) else 'n/a'} != recorded {entry['n_trades']}")
    if _sha_text(json.dumps(trades, ensure_ascii=False, separators=(",", ":"))) != entry["trades_sha256"]:
        bad("trades do not match their recorded sha256 (tampered or corrupted)")
    return entry


def iter_scan_files(dirs):
    """Every `*.json` under `dirs` (recursively: a downloaded artifact may or may not add a sub-directory), sorted.
    `*.tmp` (an interrupted atomic write) is never an entry and never read."""
    out = []
    for d in dirs:
        if not os.path.isdir(d):
            raise ScanCacheRefused(f"scan cache directory {d!r} does not exist")
        for base, _dirs, files in os.walk(d):
            out += [os.path.join(base, f) for f in files if f.endswith(".json")]
    return sorted(out)


def load_scan_entries(dirs, stamp, cell_id, runner_method, tf, series_by_symbol):
    """{(value_key, symbol): raw trades} for THIS candidate. EVERY `*.json` under `dirs` must verify against `stamp`
    (an entry of another cell is still refused when its code/plan differs: a cache directory is homogeneous or it is
    wrong); only entries of this cell / method / timeframe / a symbol of the cell are returned, and those must also
    match the series the engine itself loaded (a changed history file is refused, not used)."""
    got, sha = {}, {}
    for path in iter_scan_files(dirs):
        e = read_scan_entry(path, stamp)
        sc = e["scope"]
        if (sc["cell"], sc["runner_method"], sc["timeframe"]) != (cell_id, runner_method, tf):
            continue
        if sc["symbol"] not in series_by_symbol:
            continue
        if _canon(sc["series"]) != _canon(series_by_symbol[sc["symbol"]]):
            raise ScanCacheRefused(f"scan cache REFUSED: {path}: recorded series {sc['series']} but this run loaded "
                                   f"{series_by_symbol[sc['symbol']]} for {sc['symbol']} {tf} (history differs)")
        k = (sc["value_key"], sc["symbol"])
        if k in got:
            if sha[k] != e["trades_sha256"]:
                raise ScanCacheRefused(f"scan cache REFUSED: two entries for {k} disagree (non-deterministic scan?)")
            continue
        got[k], sha[k] = e["trades"], e["trades_sha256"]
    return got


class BtEngine:
    """scripts/backtest-methods.py `scan` + `simulate`, unmodified, truncated at DEV_CUTOFF (`bt.pit_cutoff`,
    the load-time PIT seam), with REAL costs and flat-before-rollover fixed on. `trades_for(values)` returns the
    simulated trades of the whole development span for one full V assignment; the folds slice them by time."""

    def __init__(self, grid, runner_method, tf, symbols, bt=None, workers=1):
        self.grid, self.method, self.tf, self.symbols = grid, runner_method, tf, list(symbols)
        self.workers = max(1, int(workers))          # process budget of scan_many's chunk pool (1 = in-process)
        self._raw, self._done = {}, {}               # prefetched raw scans / finished trades_for results, by value key
        self.bt = bt or _load_bt()
        missing = [grid.opts_key(i["id"]) for i in grid.items if grid.opts_key(i["id"]) not in self.bt._OPTS_BASE]
        if grid.unimplemented or missing:
            raise GridRefused(f"grid items not implemented in the engine (unimplemented={grid.unimplemented}, "
                              f"keys absent from bt._OPTS_BASE={missing}): refusing to evaluate a partial grid "
                              f"(N counts every declared item)")
        self.bt.pit_cutoff(FS.DEV_CUTOFF)
        neutralise_ruin(self.bt)
        self._admission, self._edge = {}, {}
        self._adx, self._last = {}, {}
        self._part = {}                              # value key -> {symbol: raw trades} held from a scan cache, incomplete
        self._series = {}                            # symbol -> what the PIT-truncated series looks like (scan-cache identity)
        for s in self.symbols:
            candles, _src = self.bt.load(s, tf)
            if not candles:
                raise RuntimeError(f"{s} {tf}: no candles under {_HS.history_root()} (the plan said it has some)")
            self._adx[s] = FS.adx_index(candles)
            self._last[s] = candles[-1]["time"]
            self._series[s] = {"bars": len(candles), "first_open": candles[0]["time"], "last_open": candles[-1]["time"]}

    def has(self, values):
        key = FS.CountingSource._key(values)
        return key in self._done or key in self._raw

    def prefetch(self, values_list):
        """Scan every value set in `values_list` that is not held yet, ONE `scan_many` per symbol (byte-identical to
        one `bt.scan` per value set: scripts/scan_many.py). This is a cache fill only: `trades_for` still performs
        the post-processing, and the CountingSource in front of it still counts a value set the first time it is
        SCORED -- prefetching a set no one later scores would not touch N, and a set is only prefetched because the
        probe in `prefetch_waves` saw the selection ask for it."""
        todo = {}
        for v in values_list:
            overlay = build_overlay(self.grid, v)      # a V value nobody declared is refused before any scan
            key = FS.CountingSource._key(v)
            if not (key in self._done or key in self._raw or key in todo):
                todo[key] = overlay
        if not todo:
            return
        keys = list(todo)
        t0 = time.time()
        part = getattr(self, "_part", {})
        scanned = {}                                   # (key, symbol) -> raw trades scanned NOW
        for s in self.symbols:                         # a (set, symbol) a scan cache already holds is not scanned again
            need = [k for k in keys if s not in part.get(k, {})]
            if need:
                res = SM.scan_many(self.bt, s, self.tf, self.method, [todo[k] for k in need], workers=self.workers)
                for k, r in zip(need, res):
                    scanned[(k, s)] = [t for t in r["trades"][self.method]]
        for key in keys:
            raw = []
            for s in self.symbols:                     # symbol order: what trades_for always did
                raw += scanned[(key, s)] if (key, s) in scanned else part[key][s]
            self._raw[key] = raw
            part.pop(key, None)
        print(f"fund-search: prefetched {len(keys)} value set(s) x {len(self.symbols)} symbol(s) "
              f"[{self.method} {self.tf}] in {time.time() - t0:.0f}s", file=sys.stderr, flush=True)

    def scan_symbol(self, symbol, values_list):
        """{value key: raw trades} of ONE symbol for every value set in `values_list`, ONE `scan_many` (the unit an
        Actions scan shard persists). Same overlays, same call as `prefetch`, so the trades are the ones a run holds."""
        keys, overlays = [], []
        for v in values_list:
            overlays.append(build_overlay(self.grid, v))
            keys.append(FS.CountingSource._key(v))
        if not keys:
            return {}
        res = SM.scan_many(self.bt, symbol, self.tf, self.method, overlays, workers=self.workers)
        return {k: [t for t in r["trades"][self.method]] for k, r in zip(keys, res)}

    def load_scan_cache(self, stamp, dirs, cell_id, only_keys=None):
        """Load every verified entry of this cell/method/timeframe from `dirs` (ScanCacheRefused on any doubt). A value
        set with ALL this engine's symbols cached becomes `_raw[key]` (exactly what `prefetch` would have produced); a
        set with only some symbols is kept in `_part` and scanned only for the missing symbols. `only_keys` (a set of
        value keys) keeps just those sets after verification. Returns (complete sets, entries kept)."""
        got = load_scan_entries(dirs, stamp, cell_id, self.method, self.tf, self._series)
        by_key = {}
        for (key, sym), trades in got.items():
            if only_keys is None or key in only_keys:
                by_key.setdefault(key, {})[sym] = trades
        full = 0
        for key, per in sorted(by_key.items()):
            if key in self._done or key in self._raw:
                continue
            if all(s in per for s in self.symbols):
                self._raw[key] = [t for s in self.symbols for t in per[s]]
                full += 1
            else:
                self._part[key] = per
        return full, sum(len(per) for per in by_key.values())

    def trades_for(self, values):
        overlay = build_overlay(self.grid, values)
        key = FS.CountingSource._key(values)
        if key in self._done:
            return list(self._done[key])         # a copy: a caller cannot mutate the memo (the trade dicts stay shared)
        raw = self._raw.pop(key, None)
        if raw is None:
            raw = []
            part = getattr(self, "_part", {}).pop(key, {})
            for s in self.symbols:
                if s in part:
                    raw += part[s]
                    continue
                scan = self.bt.scan(s, self.tf, only=(self.method,), opts=overlay)
                raw += [t for t in scan["trades"][self.method]]
        # a timeout trade whose walk was cut by the end of the (PIT-truncated) series has an UNKNOWN outcome:
        # excluded, exactly as prop-search excludes it (addendum §8.2) -- horizon-independent, because the
        # time-stop H is itself a V item.
        raw = [t for t in raw if not (t.get("outcome") == "timeout" and t["exit_time"] >= self._last[t["symbol"]])]
        import real_costs as _RC
        self._admission[key] = [
            {"entry_time": t["entry_time"], "R_planned": t.get("R_planned", 99),
             "fee_R": _RC.cost_r(t["entry"], t["stop"], t["entry_time"], t["exit_time"], t["symbol"], t["side"],
                                 COST_PROFILE)["total_R"]} for t in raw]
        taken = checked_simulate(self.bt, raw, 0.0, overlay=overlay, cost_profile=COST_PROFILE,
                                 live_parity_sizing=False)[2]
        provider = fixed_opts()["rollover_provider"]
        assert_no_rollover_crossing(taken, provider, self.tf)
        self._edge[key] = last_bar_entry_times(taken, self.tf, provider)
        self._done[key] = [dict(t, adx14=FS.adx_before(self._adx[t["symbol"]], t["entry_time"])) for t in taken]
        return list(self._done[key])

    def admission_stats(self, values, fold=None):
        """I2: how many candidates the simulate() min_rr filter refused for this V assignment (optionally inside
        one fold's test window), and how the R_planned margin behaves near the floor."""
        rows = self._admission.get(FS.CountingSource._key(values), [])
        return admission_stats(rows, self.bt.OPTS["min_rr"], fold)

    def rollover_edge_stats(self, values, fold=None):
        return rollover_edge_stats(self._edge.get(FS.CountingSource._key(values), []), fold)

    def prop_pass(self, pooled):
        """prop_pass_probability per fund at the pre-registration's gating horizon, over the pooled test trades,
        as explicit rows: value, status/reason when unavailable, low_confidence and the bootstrap spread minimum."""
        ps = _prop_search()
        if not pooled:
            return {f: {"value": None, "reason": "no pooled test trades"} for f in ps.FUNDS}
        _final, curve, taken = checked_simulate(self.bt, list(pooled), 0.0, overlay=fixed_opts(),
                                                cost_profile=COST_PROFILE, live_parity_sizing=True)
        out = {}
        for f in ps.FUNDS:
            m = ps._perf.metrics(taken, equity=curve, account=ps._AP.get(f), horizon=ps.CHALLENGE_HORIZON_DAYS)
            out[f] = prop_row_from_metric(m.get("prop_pass_probability"))
        return out

    def dataset_snapshot(self):
        rows = []
        for s in self.symbols:
            candles, _ = self.bt.load(s, self.tf)
            rows.append({"symbol": s, "timeframe": self.tf, "bars": len(candles), "first_open": candles[0]["time"],
                         "last_open": candles[-1]["time"], "history_root": repo_rel(self.bt.HISTORY_ROOT, ROOT),
                         "sha256": hashlib.sha256(json.dumps(candles, sort_keys=True).encode()).hexdigest(),
                         "quality_flags": [dict(f) for f in self.bt.QUALITY_FLAGS
                                           if f["symbol"] == s and f["tf"] == self.tf],
                         "_pit_truncated": True, "_pit_cutoff": FS.DEV_CUTOFF})
        ident = hashlib.sha256("|".join(f"{r['symbol']}:{r['timeframe']}:{r['sha256']}" for r in rows)
                               .encode()).hexdigest()[:16]
        return {"snapshot_format": 1, "snapshot_id": ident, "created_at": _now_iso(), "series": rows,
                "_note": "the PIT-truncated series the scan actually read (bt.pit_cutoff at DEV_CUTOFF)"}


# ------------------------------------------------------------------------------------- one candidate (pure glue)
ADMISSION_LIMITATION = ("O1 DECIDED 2026-09-30: every fund cell runs with fx_admission_entry_cost ON, so simulate()'s min_rr "
                        "admission subtracts only entry-knowable costs (entry-hour half-spread + an exit-leg half-spread "
                        "estimated at the entry hour, no swap); the reported net R still uses the real entry+exit costs. "
                        "Under v1 (key off) admission would include the EXIT-hour spread, a look-ahead against plan §37. "
                        "The refusal counts and near-floor margins are still disclosed here.")


ROLLOVER_EDGE_NOTE = ("entries whose entry bar is the LAST bar of a server day. The engine asks about the rollover only "
                      "after each WALKED bar, never for the entry bar itself, so an ICT limit fill inside that bar "
                      "can be held past midnight. Wyckoff enters at the previous bar's label and is legitimate. "
                      "Recorded, not raised on -- OPEN owner item O8 (option: an engine fix behind an fx_ key; "
                      "docs/plans/2026-09-29-fund-search-preregistration-DRAFT.md).")


class _WaveProbe:
    """A `trades_for` stand-in that records which value sets a stage of the evaluation asks for. A set the engine
    already holds is answered for real (so the stage's own choices -- which values a fold selects -- are the real
    ones); any other set is recorded and answered with NO trades, which cannot change what a stage selects: selection
    reads only sets held from the earlier wave, and the trades of the CHOSEN sets feed nothing that the next
    request depends on. The probe never counts, scores or stores anything: N is counted by the CountingSource of
    the real run only."""

    def __init__(self, engine):
        self.engine, self.missing = engine, {}

    def __call__(self, values):
        if self.engine.has(values):
            return self.engine.trades_for(values)
        self.missing.setdefault(FS.CountingSource._key(values), dict(values))
        return []


def prefetch_waves(engine, grid, cell):
    """Fill the engine's scan cache in two waves, each ONE `scan_many` per symbol (plan §1.4's search, unchanged):
    wave 1 = the baseline and every single-factor candidate (every fold's selection asks for exactly these);
    wave 2 = what only exists once selection has run -- each fold's combined chosen set and every perturbation set.
    Both lists are DISCOVERED by running the real selection / perturbation code against the probe, not restated
    here, so they cannot drift from what the evaluation later requests; a request the probes missed is still
    served (by a plain scan) when it happens, so a wrong probe costs time, never a result."""
    engine.prefetch(wave1_values(engine, grid, cell))
    engine.prefetch(wave2_values(engine, grid, cell))


def wave1_values(engine, grid, cell):
    """The value sets wave 1 still needs (in discovery order): the baseline and every single-factor candidate the
    engine does not hold yet. Needs no trades at all -- a scan shard calls this on an engine that holds nothing."""
    folds = FS.make_folds(cell["development_start"])
    emb = embargo_for(cell["timeframe"], getattr(engine, "bt", None))
    p1 = _WaveProbe(engine)
    FS.nested_walk_forward(grid, p1, folds, FS.bar_delta(cell["timeframe"]), embargo=emb)
    return list(p1.missing.values())


def wave2_values(engine, grid, cell):
    """The value sets wave 2 needs: what the selection made on the HELD wave-1 trades of ALL the cell's symbols asks for
    (each fold's combined chosen set, every perturbation set). Not symbol-local: selection pools the symbols."""
    folds = FS.make_folds(cell["development_start"])
    delta = FS.bar_delta(cell["timeframe"])
    emb = embargo_for(cell["timeframe"], getattr(engine, "bt", None))
    p2 = _WaveProbe(engine)
    fold_results = FS.nested_walk_forward(grid, p2, folds, delta, embargo=emb)
    FS.perturbation_trade_sets(grid, p2, fold_results)
    return list(p2.missing.values())


def evaluate_with_engine(engine, grid, cell, n_comparisons):
    """Nested walk-forward -> perturbation sets -> every §1.4 rule. `engine` needs `trades_for(values)` and
    `prop_pass(pooled)`; nothing else touches data, so the whole path is testable with a synthetic engine. An engine
    that also offers `prefetch`/`has` (BtEngine) is filled in two waves first (`prefetch_waves`): faster, same trades,
    same order of scoring, same N."""
    if callable(getattr(engine, "prefetch", None)) and callable(getattr(engine, "has", None)):
        prefetch_waves(engine, grid, cell)
    src = FS.CountingSource(engine.trades_for)
    folds = FS.make_folds(cell["development_start"])
    emb = embargo_for(cell["timeframe"], getattr(engine, "bt", None))
    fold_results = FS.nested_walk_forward(grid, src, folds, FS.bar_delta(cell["timeframe"]), embargo=emb)
    perturbs = FS.perturbation_trade_sets(grid, src, fold_results)
    prop = engine.prop_pass(FS.pooled_test_trades(fold_results))
    res = FS.evaluate_cell(fold_results, perturbs, cell["symbols"], n_comparisons, prop, runs=src.runs)
    res["folds_geometry"] = folds
    res["embargo_minutes"] = int(emb / datetime.timedelta(minutes=1))       # O2: recorded with the result
    if hasattr(engine, "admission_stats"):             # I2: measured, disclosed, never used to change a verdict
        res["admission"] = {
            "by_fold_chosen": [dict(engine.admission_stats(fr["chosen"], fr["fold"]), test_start=fr["fold"]["test_start"])
                               for fr in fold_results],
            "by_value_set": {k: engine.admission_stats(v) for k, v in src.evaluated()},
            "limitation": ADMISSION_LIMITATION}
    if hasattr(engine, "rollover_edge_stats"):         # round 2: the ICT engine gap, visible (OPEN owner item O8)
        res["rollover_edge"] = {
            "by_fold_chosen": [engine.rollover_edge_stats(fr["chosen"], fr["fold"]) for fr in fold_results],
            "by_value_set": {k: engine.rollover_edge_stats(v) for k, v in src.evaluated()},
            "note": ROLLOVER_EDGE_NOTE}
    return res


def _commission_status(symbols):
    import real_costs as _RC
    out = {}
    for s in symbols:
        try:
            out[s] = (_RC.spec(COST_PROFILE, s).get("commission") or {}).get("status", "UNKNOWN")
        except Exception as exc:  # noqa: BLE001 -- disclosure must not crash the candidate
            out[s] = f"UNKNOWN ({type(exc).__name__})"
    return out


def _evaluate_candidate(candidate, plan_hash, grid_dir=None, scan_workers=1, scan_cache_dirs=()):
    """Real path: evaluates one candidate. Loads its own engine; `scan_workers` is the process budget of the scan
    pool inside it (`--workers`). `scan_cache_dirs` (`--scan-cache`): verified raw scans from Actions shards are loaded
    into the engine first (anything absent is scanned on demand, as without a cache)."""
    grids, paths = load_grids(grid_dir)
    full_grid = grids[candidate["method"]]
    grid = full_grid.runnable()          # N (candidate["n_comparisons"]) was fixed on the FULL grid at plan time
    plan = load_plan(grid_dir)
    cell = next(c for c in plan["cells"] if c["id"] == candidate["cell"])
    engine = BtEngine(grid, candidate["runner_method"], candidate["timeframe"], candidate["symbols"],
                      workers=scan_workers)
    if scan_cache_dirs:
        full, n = engine.load_scan_cache(scan_cache_stamp(plan), scan_cache_dirs, candidate["cell"])
        print(f"fund-search: scan cache: {n} verified (value set, symbol) entries, {full} value set(s) complete for "
              f"{candidate['id']}", file=sys.stderr, flush=True)
    result = evaluate_with_engine(engine, grid, cell, candidate["n_comparisons"])
    result["declared_not_run"] = full_grid.unimplemented
    return {"record": dict(build_record(candidate, plan_hash, grid, paths[candidate["method"]], result,
                                        engine.dataset_snapshot(), cell))}


def _drift_from_env():
    try:
        return json.loads(os.environ.get(DRIFT_ENV) or "[]")
    except ValueError:
        return ["unreadable drift stamp"]


def build_record(candidate, plan_hash, grid, grid_path, result, dataset_snapshot, cell):
    import real_costs as _RC
    import snapshot as _snap
    cid = candidate["id"]
    r = X.Record(
        hypothesis=(f"{candidate['runner_method']} on {candidate['timeframe']} ({candidate['asset_class']}, symbols "
                    f"{candidate['symbols']}), V values chosen by nested walk-forward on development data, passes "
                    f"every {PLAN_DOC} §1.4 rule at N = {candidate['n_comparisons']} (one-sided confidence "
                    f"1 - {FS.FAMILY_ALPHA}/N) -- falsified if any rule fails or a test fold has < "
                    f"{FS.MIN_FOLD_TRADES} trades."),
        motivation=(f"Owner decisions 2026-09-28/29 ({PLAN_DOC} §6 items 2-8): search fund-account setups on 1m/5m/"
                    f"15m/30m under real FTMO costs and no overnight holding, without loosening any check."),
        parent_trading_system_version=X.unavailable(
            "a pre-registered space search over the pre-declared V grid, not a change to an approved Trading System"),
        candidate_version=f"fund-search-candidate:{cid}", experiment_id=cid)
    r.set("failure_pattern", X.unavailable("answers no §41 failure cluster: a pre-registered grid search"))
    r.set("dataset_snapshot", dataset_snapshot)
    r.set("configuration_snapshot", {
        "fixed": {"cost_profile": COST_PROFILE, "flat_before_rollover": True, "adopted_f_keys": list(ADOPTED_F_KEYS),
                  "cost_profile_snapshot": _RC.profile_snapshot(COST_PROFILE, candidate["symbols"])},
        "grid": {"file": os.path.basename(grid_path), "sha256": _sha256_file(grid_path),
                 "items": [{k: it.get(k) for k in ("id", "key", "existing_opts_key", "values", "joint_group",
                                                   "source")} for it in grid.items]},
        "code_version": _snap.code_version(), "plan_hash": plan_hash,
        "ruin_handling": "bt.RUIN_FRAC = 0.0 (R does not depend on equity); post_ruin trades fail loud",
        "min_rr_semantics": ADMISSION_LIMITATION,
        "lower_bound": "min(iid t, CR1 block by UTC date, CR1 block by 30-day window) at 1 - 0.10/N",
        "regime_split": FS.REGIME_SPLIT_DEFINITION, "verdict_precedence": FS.VERDICT_PRECEDENCE,
        "constants": dict({k: getattr(FS, k) for k in ("FAMILY_ALPHA", "MIN_FOLD_TRADES", "MIN_TRAIN_TRADES",
                                                        "MAX_TRADE_SHARE", "MAX_GAP_DAYS", "MIN_FOLD_SHARE_OK",
                                                        "PASS_PROB_MIN", "TEST_FOLD_DAYS", "MIN_TRAIN_DAYS")},
                          embargo_h_multiple=EMBARGO_H_MULTIPLE)})
    r.set("account_configuration", X.unavailable("prop_pass_probability uses the two fund profiles of prop-search "
                                                 "(scripts/account_profile.py); no separate account is configured"))
    r.set("risk_configuration", {"cost_profile": COST_PROFILE, "spread_stat": "median",
                                 "commission_status_by_symbol": _commission_status(candidate["symbols"]),
                                 "commission_note": "FTMO commission is UNKNOWN (no deals on the export account): "
                                                    "taken from the cost data only, never guessed -- the net R is "
                                                    "NOT net of commission",
                                 "flat_before_rollover": True})
    r.set("news_configuration", X.unavailable("no news filter applied in this search"))
    r.set("session_configuration", X.unavailable("no session filter applied in this search"))
    r.set("parameters", {"method": candidate["method"], "runner_method": candidate["runner_method"],
                         "cell": candidate["cell"], "timeframe": candidate["timeframe"],
                         "asset_class": candidate["asset_class"], "symbols_planned": candidate["symbols"],
                         "symbols_evaluated": list(cell["symbols"]), "n_comparisons": candidate["n_comparisons"],
                         "plan_hash": plan_hash,
                         "drifted": bool(_drift_from_env()), "drift": _drift_from_env()})
    r.set("random_seed", {"lower_bound": "none: closed-form Student-t bound, no resampling",
                          "prop_pass_probability_bootstrap": "scripts/performance.py BOOTSTRAP_SEED"})
    r.set("test_periods", {"development": {"end": FS.DEV_CUTOFF, "period_id": DEV_PERIOD_ID},
                           "folds": result.get("folds_geometry"),
                           "training_embargo_minutes": result.get("embargo_minutes"),
                           "note": "nothing at or after the development cutoff is read (bt.pit_cutoff)"})
    r.set("validation_method",
          "nested rolling-origin walk-forward over the development span; V values chosen on each training fold "
          "only; lower bound on pooled test-fold trades only (scripts/fund_stats.py, plan §1.4)")
    r.set("metrics", {"evaluation": result})
    r.set("robustness_results", {"regime_split": result["checks"]["regime_split"],
                                 "perturbation": result["checks"]["perturbation"]})
    try:
        import trading_system as _TS
        sysd = _TS.for_market_tf("cfd", candidate["timeframe"])
        sv = {"id": sysd["id"], "version": _TS.get(sysd["id"]).get("version")}
    except Exception:  # noqa: BLE001
        sv = X.unavailable(f"no Trading System resolves for (cfd, {candidate['timeframe']})")
    r.set("system_version", sv)
    return r.seal()


# ------------------------------------------------------------------------------------------------------ `run`
class RecordMismatch(RuntimeError):
    """A record under RECORDS_DIR does not belong to the loaded plan."""


class AlreadyRunning(RuntimeError):
    pass


RUN_LOCK_STALE_SECONDS = 6 * 3600


@contextlib.contextmanager
def _run_lock(path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        age = time.time() - os.path.getmtime(path)
        if age < RUN_LOCK_STALE_SECONDS:
            raise AlreadyRunning(f"{path} exists ({age:.0f}s old): another run appears to use {RECORDS_DIR}")
        print(f"WARNING: reclaiming a stale lock {path}", file=sys.stderr)
        os.remove(path)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(fd, "w") as fh:
        fh.write(f"pid={os.getpid()} started={_now_iso()}\n")
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            os.remove(path)


def validate_record(rec, plan):
    cid = rec["experiment_id"]
    cand = next((c for c in plan["candidates"] if c["id"] == cid), None)
    if cand is None:
        raise RecordMismatch(f"record {cid!r} is not a candidate of the loaded plan ({plan['plan_hash'][:12]})")
    p = rec.get("parameters") or {}
    if p.get("plan_hash") != plan["plan_hash"]:
        raise RecordMismatch(f"record {cid!r} was sealed against plan {str(p.get('plan_hash'))[:12]!r}, "
                             f"not {plan['plan_hash'][:12]}")
    cell = next(c for c in plan["cells"] if c["id"] == cand["cell"])
    if sorted(p.get("symbols_evaluated") or []) != sorted(cell["symbols"]):
        raise RecordMismatch(f"record {cid!r} evaluated symbols {p.get('symbols_evaluated')} but the plan fixed "
                             f"{cell['symbols']}: no symbol may be added or dropped after the plan (plan §1.7)")


def cmd_run(cell_id, method=None, workers=1, grid_dir=None, allow_drift=False, scan_cache_dirs=()):
    plan = load_plan(grid_dir)
    decl = require_declaration(plan)                # refuses BEFORE anything is evaluated
    drift = check_drift(decl, plan, allow_drift)    # refuses on code / settings drift unless --allow-drift
    grids, _paths = load_grids(grid_dir)
    for m, g in grids.items():
        assert_grid_runnable(g)
    if drift:
        print("WARNING: --allow-drift: every record will be stamped drifted=true:\n  " + "\n  ".join(drift),
              file=sys.stderr)
        os.environ[DRIFT_ENV] = json.dumps(drift)
    else:
        os.environ.pop(DRIFT_ENV, None)
    try:
        _cmd_run_inner(plan, cell_id, method, workers, grid_dir, scan_cache_dirs)
    finally:
        os.environ.pop(DRIFT_ENV, None)


DRIFT_ENV = "FUND_SEARCH_DRIFT"


def _cmd_run_inner(plan, cell_id, method, workers, grid_dir, scan_cache_dirs=()):
    todo = [c for c in plan["candidates"] if c["cell"] == cell_id and (method is None or c["method"] == method)]
    if not todo:
        raise SystemExit(f"no candidate for cell {cell_id!r}"
                         f"{' method ' + method if method else ''}; cells: {[c['id'] for c in plan['cells']]}")
    os.makedirs(RECORDS_DIR, exist_ok=True)
    with _run_lock(os.path.join(os.path.dirname(RECORDS_DIR), ".fund-search-run.lock")):
        for f in sorted(os.listdir(RECORDS_DIR)):
            if f.endswith(".json"):
                validate_record(X.load(f[:-5], store=RECORDS_DIR), plan)
        done = {f[:-5] for f in os.listdir(RECORDS_DIR) if f.endswith(".json")}
        todo = [c for c in todo if c["id"] not in done]
        errors, results = [], []

        def _persist(cid, out):        # S2: written the moment a candidate completes -- a CI timeout keeps it
            X.write(types.MappingProxyType(out["record"]), store=RECORDS_DIR)
            results.append(cid)
            print(f"{out['record']['metrics']['evaluation']['verdict'].upper():<12} {cid}", flush=True)

        # `workers` is the process budget of the SCAN pool inside each candidate (scripts/scan_many.py: bar chunks of
        # one series, one spawned process per chunk via scripts/isolated_pool.py) -- candidates themselves run one at a
        # time, so the budget is never multiplied. The candidate call keeps its 3-argument shape when workers <= 1.
        kw = {"scan_cache_dirs": list(scan_cache_dirs)} if scan_cache_dirs else {}
        for c in todo:
            try:
                out = (_evaluate_candidate(c, plan["plan_hash"], grid_dir, **kw) if workers <= 1
                       else _evaluate_candidate(c, plan["plan_hash"], grid_dir, scan_workers=workers, **kw))
            except Exception as exc:  # noqa: BLE001
                errors.append((c["id"], exc))
                continue
            _persist(c["id"], out)
        if errors:
            raise RuntimeError("fund-search: candidate(s) raised -- FAILING LOUD (an exception is never recorded "
                               "as a fail): " + "; ".join(f"{c}: {type(e).__name__}: {e}" for c, e in errors))
    print(f"cell {cell_id}: {len(results)} evaluated, {len(done)} already recorded")


# ------------------------------------------------------------------------- `scan` (one Actions shard) + its layout
#: Development-span bar counts (PIT-truncated at DEV_CUTOFF), parsed from the year files -- copied from
#: docs/audits/2026-09-30-engine-speed-profile.md (header table; that doc is the source). Used ONLY to size shards:
#: they change how the work is laid out over jobs, never a result.
DEV_BARS = {
    "1m": {"XAUUSD": 4096182, "XAGUSD": 4097904, "US500": 852695, "US30": 1729779, "USTEC": 867342, "DE40": 747188,
           "FRA40": 801548},
    "5m": {"XAUUSD": 1316783, "XAGUSD": 1054081, "US500": 177185, "US30": 346651, "USTEC": 177192, "DE40": 155214,
           "FRA40": 174454},
    "15m": {"XAUUSD": 453893, "XAGUSD": 357694, "US500": 62776, "US30": 116405, "USTEC": 62766, "DE40": 55219,
            "FRA40": 62283},
    "30m": {"XAUUSD": 229853, "XAGUSD": 180535, "US500": 33705, "US30": 58257, "USTEC": 33701, "DE40": 29812,
            "FRA40": 33467}}

#: The time model (docs/audits/2026-09-30-actions-sharding.md section 3). MEASURED by the owner on 10 local workers:
#: ICT XAUUSD 1m wave 1 (39 value sets) = 581 s for the first set + ~213 s per further set (= 2.41 h). Everything else
#: is an ASSUMPTION, stated there: cost linear in bars, linear in worker count, no per-core speed adjustment for a
#: hosted runner, Wyckoff = `wyckoff_factor` x ICT per set (the audit projects ~2.1x on 1m metals; not measured here).
SHARD_MODEL = {"first_set_s": 581.0, "extra_set_s": 213.0, "ref_bars": 4096182, "ref_workers": 10,
               "runner_vcpu": 4, "runner_ram_bytes": 16 * 2 ** 30, "wyckoff_factor": 2.0,
               "budget_s": 300 * 60,        # target per shard; the job timeout is 355 min (GitHub's hard cap is 360)
               "job_timeout_min": 355}
#: Wave-2 value sets per fold, an UPPER-typical bound from the audit's zero-edge run of the real waves (ICT 148 sets @17
#: folds, 100 @10, 43 @4; Wyckoff 29-93): wave 2 depends on the selection, so its true size is only known at run time.
WAVE2_SETS_PER_FOLD = {"ict": 11, "wyckoff": 8}


def runner_workers(bars):
    """Effective scan workers on the assumed runner: its vCPUs, lowered by scan_many's own memory clamp."""
    m = SHARD_MODEL
    return max(1, min(m["runner_vcpu"], SM.clamp_workers(m["runner_vcpu"], bars, physical=m["runner_ram_bytes"])))


def shard_seconds(k_sets, bars, method):
    """Modelled wall seconds of ONE shard that scans `k_sets` value sets of one symbol of `bars` bars."""
    m = SHARD_MODEL
    scale = (bars / m["ref_bars"]) * (m["ref_workers"] / runner_workers(bars)) * (
        m["wyckoff_factor"] if method == "wyckoff" else 1.0)
    return (m["first_set_s"] + max(k_sets - 1, 0) * m["extra_set_s"]) * scale


def max_sets_per_shard(bars, method):
    """Most value sets one shard can scan inside the budget; 0 = even a single set is modelled over budget."""
    b = SHARD_MODEL["budget_s"]
    one = shard_seconds(1, bars, method)
    if one > b:
        return 0
    return 1 + int((b - one) // (shard_seconds(2, bars, method) - one))


def slice_bounds(n, i, slices):
    """[lo, hi) of contiguous, near-equal slice `i` of `n` items in discovery order (contiguous keeps value sets that
    share an analysis group together)."""
    return i * n // slices, (i + 1) * n // slices


def take_slice(items, i, slices):
    lo, hi = slice_bounds(len(items), i, slices)
    return list(items)[lo:hi]


def parse_slice(text):
    try:
        a, b = str(text).split("/")
        i, n = int(a), int(b)
    except ValueError:
        raise SystemExit(f"--slice must look like I/N (e.g. 0/3), got {text!r}")
    if not (n >= 1 and 0 <= i < n):
        raise SystemExit(f"--slice I/N needs N >= 1 and 0 <= I < N, got {text!r}")
    return i, n


def shard_plan(plan, grid_dir=None):
    """The scan shards of the committed plan: one row per (cell, method, symbol, wave, slice). Wave 1 (baseline + every
    single-factor candidate) is symbol-local. Wave 2 (each fold's combined chosen set + every perturbation set) is
    discovered from the selection on the POOLED wave-1 trades of every symbol of the cell, so its shards run only after
    all of wave 1 exists; each still scans ONE symbol. Slice counts follow the time model above and the sets estimate
    for wave 2 -- a layout decision made from the plan and data availability only, never from a result."""
    grids, _paths = load_grids(grid_dir)
    rows = []
    for cell in plan["cells"]:
        for method in METHODS:
            g = grids[method].runnable()
            n1 = 1 + sum(len(x["candidates"]) for x in g.groups)
            n2 = WAVE2_SETS_PER_FOLD[method] * cell["n_folds"]
            for wave, n in ((1, n1), (2, n2)):
                for sym in cell["symbols"]:
                    bars = DEV_BARS[cell["timeframe"]][sym]
                    cap = max_sets_per_shard(bars, method)
                    slices = -(-n // max(cap, 1))
                    for i in range(slices):
                        lo, hi = slice_bounds(n, i, slices)
                        est = shard_seconds(hi - lo, bars, method)
                        rows.append({"cell": cell["id"], "method": method, "symbol": sym, "wave": wave,
                                     "slice": f"{i}/{slices}", "sets": hi - lo, "bars": bars, "est_min": round(est / 60),
                                     "over_timeout": est / 60 > SHARD_MODEL["job_timeout_min"],
                                     "name": f"{cell['id']}-{method}-{sym}-w{wave}-s{i}"})
    return rows


def format_shard_table(rows):
    """Per (cell, method, symbol, wave): slices, sets, the longest modelled shard, and whether any is over the timeout."""
    groups = {}
    for r in rows:
        groups.setdefault((r["cell"], r["method"], r["symbol"], r["wave"]), []).append(r)
    L = [f"{'cell':<12}{'method':<8}{'symbol':<8}{'wave':<5}{'slices':>6}{'sets':>6}{'unsliced':>10}{'longest shard':>15}"
         f"  shard over {SHARD_MODEL['job_timeout_min']} min?"]
    for (c, m, s, w), rs in groups.items():
        longest = max(r["est_min"] for r in rs)
        sets = sum(r["sets"] for r in rs)
        whole = round(shard_seconds(sets, rs[0]["bars"], m) / 60)      # the same symbol/wave in ONE job, no slicing
        L.append(f"{c:<12}{m:<8}{s:<8}{w:<5}{len(rs):>6}{sets:>6}{whole:>7} min{longest:>10} min   "
                 f"{'YES' if any(r['over_timeout'] for r in rs) else 'no'}")
    L.append(f"total shards: {len(rows)}; modelled runner minutes: {sum(r['est_min'] for r in rows)}")
    return "\n".join(L)


def cmd_scan(cell_id, symbol, method, out_dir, workers=1, wave=1, slice_spec="0/1", scan_cache_dirs=(), grid_dir=None):
    """One Actions scan shard. `--wave 1`: the wave-1 value sets (the same list `run` would prefetch first) for ONE
    symbol -- needs no other symbol's data. `--wave 2`: the wave-2 sets, which only exist once selection has run on the
    pooled wave-1 trades of ALL the cell's symbols, so it needs the complete wave-1 cache (`--scan-cache`) and REFUSES
    without it; it still scans ONE symbol. `--slice I/N` takes the I-th of N contiguous parts of the list. Every
    (value set, symbol) result is persisted the moment its scan returns, as a verified cache entry under `out_dir`
    (outside the checkout, CLAUDE.md section 46). Like `run`, refuses without the ledger declaration and on code drift."""
    real_out = os.path.realpath(out_dir)
    if real_out == ROOT or real_out.startswith(ROOT + os.sep):
        raise SystemExit(f"--out {out_dir} is inside the checkout: outputs must land outside it (a file written in the "
                         f"work tree makes the run's own code_version read dirty=true, CLAUDE.md section 46)")
    i, n = parse_slice(slice_spec)
    if wave not in (1, 2):
        raise SystemExit("--wave must be 1 or 2")
    plan = load_plan(grid_dir)
    decl = require_declaration(plan)
    check_drift(decl, plan, False)
    cell = next((c for c in plan["cells"] if c["id"] == cell_id), None)
    if cell is None:
        raise SystemExit(f"no cell {cell_id!r}; cells: {[c['id'] for c in plan['cells']]}")
    if symbol not in cell["symbols"]:
        raise SystemExit(f"{symbol!r} is not a symbol of cell {cell_id!r} ({cell['symbols']}): no symbol may be added "
                         f"or dropped after the plan (plan section 1.7)")
    cand = next(c for c in plan["candidates"] if c["cell"] == cell_id and c["method"] == method)
    grids, _paths = load_grids(grid_dir)
    for g in grids.values():
        assert_grid_runnable(g)
    grid = grids[method].runnable()
    stamp = scan_cache_stamp(plan)
    engine = BtEngine(grid, cand["runner_method"], cell["timeframe"], [symbol] if wave == 1 else cell["symbols"],
                      workers=workers)
    if wave == 1:
        values = wave1_values(engine, grid, cell)
    else:
        if not scan_cache_dirs:
            raise SystemExit("--wave 2 needs --scan-cache: the wave-2 value sets are chosen from the pooled wave-1 "
                             "trades of every symbol of the cell")
        # the wave-2 list must not depend on which wave-2 entries a directory happens to hold (a shard rerun, a merged
        # directory): only the wave-1 sets are loaded, so every shard derives the SAME list and its slice is stable
        w1_keys = {FS.CountingSource._key(v) for v in wave1_values(engine, grid, cell)}     # engine holds nothing yet
        engine.load_scan_cache(stamp, scan_cache_dirs, cell_id, only_keys=w1_keys)
        incomplete = wave1_values(engine, grid, cell)
        if incomplete:
            raise SystemExit(f"--wave 2 refused: the wave-1 cache of {cell_id}/{method} is incomplete for "
                             f"{len(incomplete)} value set(s) of {cell['symbols']}; wave-2 sets would be chosen from "
                             f"an incomplete pool. Re-run the missing wave-1 shards.")
        values = wave2_values(engine, grid, cell)
    mine = take_slice(values, i, n)
    todo, skipped = [], 0
    for v in mine:
        key = FS.CountingSource._key(v)
        scope = scan_cache_scope(cell_id, cand["runner_method"], cell["timeframe"], symbol, key, engine._series[symbol])
        path = os.path.join(out_dir, scan_cache_key(stamp, scope) + ".json")
        if os.path.exists(path):
            read_scan_entry(path, stamp)              # a present entry must verify; it is not rescanned
            skipped += 1
        else:
            todo.append((v, key, scope))
    print(f"scan {cell_id} {method} {symbol} wave {wave} slice {i}/{n}: {len(values)} value set(s) in the wave, "
          f"{len(mine)} in this slice, {skipped} already present, {len(todo)} to scan", flush=True)
    t0 = time.time()
    written = 0
    if todo:
        got = engine.scan_symbol(symbol, [v for v, _k, _s in todo])
        for _v, key, scope in todo:
            path = write_scan_entry(out_dir, stamp, scope, got[key])
            written += 1
            print(f"  wrote {os.path.basename(path)[:12]} {symbol} {len(got[key])} trades", flush=True)
    print(f"scan done: {written} written, {skipped} present, {time.time() - t0:.0f}s", flush=True)
    return {"wave_sets": len(values), "slice_sets": len(mine), "written": written, "skipped": skipped}


# ---------------------------------------------------------------------------------------------------- `report`
def _fmt(v, spec="+.3f"):
    return format(v, spec) if isinstance(v, (int, float)) else "n/a"


def cmd_report(grid_dir=None):
    plan = load_plan(grid_dir)
    recs = []
    if os.path.isdir(RECORDS_DIR):
        for f in sorted(os.listdir(RECORDS_DIR)):
            if f.endswith(".json"):
                rec = X.load(f[:-5], store=RECORDS_DIR)
                validate_record(rec, plan)
                recs.append(rec)
    by_id = {r["experiment_id"]: r for r in recs}
    verdicts = {}
    for cid, r in by_id.items():                     # re-derived from the stored checks, not a stored boolean
        ev = r["metrics"]["evaluation"]
        verdicts[cid] = FS.verdict_from(ev["checks"])
    planned = plan["candidates"]
    not_run = [c["id"] for c in planned if c["id"] not in by_id]
    passes = [cid for cid, v in verdicts.items() if v == FS.PASS]
    counts = {v: sum(1 for x in verdicts.values() if x == v) for v in (FS.PASS, FS.FAIL, FS.INSUFFICIENT)}
    runs = sum((r["metrics"]["evaluation"].get("runs_evaluated") or 0) for r in recs)
    L = ["# Fund-setup search -- report", "",
         f"_Source: `{PLAN_DOC}` §1.4, §3, §6. Plan hash `{plan['plan_hash'][:12]}`; cost profile "
         f"`{plan['cost_profile']}` (real costs, flat before rollover, FIXED in every cell)._", "",
         "## Full count (disclosed, nothing dropped)", "",
         f"- Cells: **{plan['cell_count']}**; excluded before any result (no development history): "
         f"{[e['id'] for e in plan['excluded_cells']] or 'none'}.",
         f"- Candidates planned (method x cell): **{plan['candidate_count']}**; evaluated: **{len(recs)}**; "
         f"NOT RUN: **{len(not_run)}**" + (f" -- {not_run}" if not_run else "") + ".",
         f"- Verdicts over the evaluated candidates: pass **{counts[FS.PASS]}**, fail **{counts[FS.FAIL]}**, "
         f"insufficient **{counts[FS.INSUFFICIENT]}**. Engine evaluations (every distinct V assignment scored, "
         f"selection + combined + perturbations): **{runs}**.",
         "- N per method = (1 + non-baseline V values + 1 combined) x cells: "
         + ", ".join(f"{m} {plan['grids'][m]['n_per_cell']} x {plan['cell_count']} = **{plan['n_by_method'][m]}** "
                     f"(confidence {plan['confidence_by_method'][m]:.5f})" for m in plan["grids"]) + ".",
         f"- Prior searches on the same history, disclosed and NOT folded into N: {plan['prior_counts_disclosed']}.",
         f"- Walk-forward training embargo (O2): {plan['embargo']['rule']}; minutes by timeframe "
         f"{plan['embargo']['minutes_by_timeframe']}.",
         "- No symbol was dropped after its result was seen: each candidate's symbols equal the plan's "
         "(`validate_record`).", ""]
    drifted = [r["experiment_id"] for r in recs if (r.get("parameters") or {}).get("drifted")]
    if drifted:
        L[2:2] = [f"**WARNING: DRIFTED RECORDS -- {len(drifted)} record(s) were produced with code or settings that "
                  f"differ from the ledger declaration (`--allow-drift`): {drifted}. They are not evidence under the "
                  f"declared pre-registration.**", ""]
    if not recs:
        L += ["**No candidate has been evaluated yet.** Zero results, zero passes.", ""]
    elif not passes:
        L += [f"**Zero passes.** None of the {len(recs)} evaluated candidates passed every §1.4 rule. Reported as "
              f"found; no threshold was relaxed to manufacture a pass ({PLAN_DOC} §1.4, §6 item 2).", ""]
    else:
        L += [f"**{len(passes)} of {len(recs)} evaluated candidates passed:** {passes}", ""]
    if not_run:
        L += [f"**Incomplete:** {len(not_run)} planned candidate(s) have no record yet; the counts above are "
              f"over what was evaluated, not over the plan.", ""]
    cv = {}
    for r in recs:
        c = r.get("code_version")
        key = (c.get("commit"), bool(c.get("dirty"))) if isinstance(c, dict) and "commit" in c else ("unavailable", True)
        cv.setdefault(key, []).append(r["experiment_id"])
    if len(cv) > 1 or any(k[1] for k in cv):
        L += ["## WARNING: records sealed under different code versions or a dirty tree", ""]
        for (commit, dirty), ids in sorted(cv.items(), key=lambda kv: str(kv[0])):
            L.append(f"- commit `{str(commit)[:12]}` dirty={dirty}: {ids}")
        L += ["", "Records from different code, or from a dirty tree, are not reproducible from one SHA "
              "(CLAUDE.md §46) and must not be pooled as one evaluation.", ""]
    L += ["## Folds per cell and the frequency-rule arithmetic", "",
          "| cell | folds | folds required with every gap <= 30d | may fail |", "|---|---|---|---|"]
    for c in plan["cells"]:
        fr = c["frequency_rule"]
        L.append(f"| {c['id']} | {c['n_folds']} | {fr['folds_required_within_gap']} | {fr['folds_allowed_to_fail']} |")
    L += ["", "## What a PASS certifies", "",
          "A PASS certifies a SELECTION PROCEDURE (choose V values on each training fold, score them on the next "
          "test fold), NOT a fixed configuration. The values differ from fold to fold (see the per-item stability "
          "below). PROPOSED, NOT DECIDED: deploy the values chosen in the FINAL fold -- a pre-registration item "
          "for the owner (docs/plans/2026-09-29-fund-search-preregistration-DRAFT.md).", "",
          f"Regime split, as pre-registered: {FS.REGIME_SPLIT_DEFINITION}.", ""]
    L += ["## Every evaluated candidate", "",
          "| candidate | verdict | test trades | pooled mean net R | lower bound (conf) | failed checks |",
          "|---|---|---|---|---|---|"]
    for r in recs:
        ev = r["metrics"]["evaluation"]
        lb = ev["checks"]["lower_bound_positive"]["bound"]
        L.append(f"| {r['experiment_id']} | {verdicts[r['experiment_id']]} | {ev['pooled']['n_trades']} | "
                 f"{_fmt(ev['pooled']['mean_R'])} | {_fmt(lb['value'])} ({lb['confidence']:.5f}) | "
                 f"{', '.join(ev['failed_checks']) or '-'} |")
    L += ["", "## Per symbol (pooled test trades) and per volume_kind", ""]
    for r in recs:
        ev = r["metrics"]["evaluation"]
        L.append(f"### {r['experiment_id']}")
        L.append("| symbol | trades | mean net R |")
        L.append("|---|---|---|")
        for s, v in ev["per_symbol"].items():
            L.append(f"| {s} | {v['n']} | {_fmt(v['mean_R'])} |")
        L.append("")
        cs = ev.get("chosen_value_stability") or {}
        if cs:
            changed = {i: v for i, v in cs.items() if v["changes"]}
            L.append(f"Chosen-value stability across folds: {len(changed)} of {len(cs)} items changed value at "
                     f"least once; changes per item: "
                     + (", ".join(f"{i} {v['changes']}/{v['transitions']}" for i, v in sorted(changed.items()))
                        or "none") + ".")
        pp = ev["checks"]["prop_pass_probability"]["funds"]
        L.append("prop_pass_probability: " + "; ".join(
            f"{f} {row['status']}" + (f" ({_fmt(row['value'], '.2f')})" if row.get("value") is not None else "")
            + (f" -- {row['reason']}" if row.get("reason") else "") for f, row in pp.items()))
        adm = ev.get("admission")
        if adm:
            byf = adm["by_fold_chosen"]
            L.append(f"min_rr admission (chosen values, per test fold): refused "
                     f"{[f['refused_min_rr'] for f in byf]} of candidates {[f['candidates'] for f in byf]}; "
                     f"near-floor (|margin| < {NEAR_FLOOR_MARGIN}) counts {[f['near_floor_n'] for f in byf]}, of which "
                     f"refused {[f['near_floor_refused'] for f in byf]}. LIMITATION: {adm['limitation']}")
        re_ = ev.get("rollover_edge")
        if re_:
            L.append("Entries on the last bar of a server day (chosen values, per test fold): "
                     f"{[f['entries_on_last_bar_of_server_day'] for f in re_['by_fold_chosen']]}. NOTE: {re_['note']}")
        vk = ev.get("by_volume_kind")
        if vk:
            L.append("")
            L.append("volume_kind split (LIMITATION: tick volume is a count of price changes, not real traded "
                     "volume):")
            for k, v in vk.items():
                if not k.startswith("_"):
                    L.append(f"- `{k}`: {v['n']} trades, mean {_fmt(v['mean_R'])}, lower bound {_fmt(v['lower_bound'])}")
        L.append("")
    L += ["## Limitations, stated", "",
          "- FTMO commission is UNKNOWN; net R is net of the recorded spread and swap only.",
          "- Wyckoff on CFD uses TICK volume (see the per-volume_kind rows).",
          "- The lower bound is the MINIMUM of an iid Student-t bound and two cluster-robust (CR1) bounds (by UTC "
          "entry date, by 30-day window, by calendar quarter and by half-year). It is not backed by the "
          "single-trade cap or the perturbation check: those are separate gates, each required on its own. "
          "DISCLOSED PRICE: the quarter and half-year bounds cost power -- measured on 20 seeds of iid +0.30R at "
          "n=600, the bound passed 20/20 over 6 years, 17/20 over 4 years and 9/20 over 2 years; persistent-regime "
          "edges fare worse. This is accepted as the tightening the owner chose.",
          "- The min_rr admission filter uses a cost that includes the exit-hour spread (see the per-candidate "
          "admission lines): a look-ahead already present in v1 that this harness measures and discloses but does not change.",
          "- The development span is exposed by this search; only the forward demo is pristine "
          f"({PLAN_DOC} §1.1)."]
    md = "\n".join(L) + "\n"
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write(md)
    print(f"-> {REPORT_PATH} ({len(recs)} evaluated, {len(passes)} passes, {len(not_run)} not run)")
    return md


# ------------------------------------------------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description="Pre-registered fund-setup search (plan §1.4, §3, §6)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("plan", help="enumerate cells/candidates and N; --dry-run prints and writes nothing")
    pp.add_argument("--dry-run", action="store_true")
    pp.add_argument("--grid-dir", help="directory holding v-grid-ict.json / v-grid-wyckoff.json")
    sub.add_parser("declare", help="record the final cell count in the research ledger (before any run)")
    sub.add_parser("list-cells", help="print the committed plan's cell ids as JSON (the CI matrix)")
    lp = sub.add_parser("list-scan-shards", help="print the scan-shard matrix (cell x method x symbol x wave x slice) "
                                                 "as JSON; --explain prints the time model's table instead")
    lp.add_argument("--wave", type=int, choices=(1, 2), help="only this wave's shards")
    lp.add_argument("--explain", action="store_true")
    sp = sub.add_parser("scan", help="one Actions scan shard: raw scans of ONE symbol into a verified cache directory")
    sp.add_argument("--cell", required=True)
    sp.add_argument("--symbol", required=True)
    sp.add_argument("--method", required=True, choices=sorted(METHODS))
    sp.add_argument("--out", required=True, help="cache directory to write (must be outside the checkout)")
    sp.add_argument("--workers", type=int, default=None, help="scan pool budget (default min(cpu_count - 2, 10))")
    sp.add_argument("--wave", type=int, choices=(1, 2), default=1)
    sp.add_argument("--slice", default="0/1", help="I/N: the I-th of N contiguous parts of the wave's value sets")
    sp.add_argument("--scan-cache", action="append", default=[], metavar="DIR",
                    help="(--wave 2) cache directory holding the cell's complete wave 1; repeatable")
    sp.add_argument("--grid-dir")
    rp = sub.add_parser("run", help="evaluate one cell (refuses without the ledger declaration)")
    rp.add_argument("--cell", required=True)
    rp.add_argument("--method", choices=sorted(METHODS))
    rp.add_argument("--workers", type=int, default=None,
                    help="process budget of the scan pool inside each candidate (default min(cpu_count - 2, 10); "
                         "lowered further so the per-worker memory estimate fits in RAM); 1 = in-process")
    rp.add_argument("--scan-cache", action="append", default=[], metavar="DIR",
                    help="directory of scan-shard cache entries (repeatable): verified entries are loaded instead of "
                         "scanned; an entry of another code/plan/settings/history REFUSES the run; missing ones are "
                         "scanned on demand")
    rp.add_argument("--grid-dir")
    rp.add_argument("--allow-drift", action="store_true",
                    help="proceed although the code/settings differ from the declaration; every record is "
                         "stamped drifted=true and the report says so")
    sub.add_parser("report", help="write the markdown report over every record")
    a = ap.parse_args(argv)
    os.environ.setdefault("BT_HISTORY_ROOT", FTMO_HISTORY_ROOT)     # the fund search reads the FTMO feed (§6 item 8)
    if a.cmd == "plan":
        cmd_plan(dry_run=a.dry_run, grid_dir=a.grid_dir)
    elif a.cmd == "declare":
        cmd_declare()
    elif a.cmd == "list-cells":
        print(json.dumps([{"cell": c["id"]} for c in load_plan()["cells"]]))
    elif a.cmd == "list-scan-shards":
        rows = shard_plan(load_plan())
        if a.wave:
            rows = [r for r in rows if r["wave"] == a.wave]
        if a.explain:
            print(format_shard_table(rows))
        else:
            print(json.dumps(rows))
    elif a.cmd == "scan":
        cmd_scan(a.cell, a.symbol, a.method, a.out, workers=a.workers if a.workers is not None else SM.default_workers(),
                 wave=a.wave, slice_spec=a.slice, scan_cache_dirs=a.scan_cache, grid_dir=a.grid_dir)
    elif a.cmd == "run":
        cmd_run(a.cell, method=a.method, workers=a.workers if a.workers is not None else SM.default_workers(),
                grid_dir=a.grid_dir, allow_drift=a.allow_drift, scan_cache_dirs=a.scan_cache)
    elif a.cmd == "report":
        cmd_report()


if __name__ == "__main__":
    main()
