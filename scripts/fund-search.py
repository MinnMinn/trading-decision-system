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
    python3 scripts/fund-search.py report

The statistics are scripts/fund_stats.py (pure, separately tested). This file only orchestrates: cells, the
engine adapter (scripts/backtest-methods.py scan + simulate, unmodified), sealed records (scripts/experiment.py),
the ledger declaration (scripts/research_ledger.py), one process per candidate (scripts/isolated_pool.py).

FIXED IN EVERY CELL (plan §6 items 3, 7): real FTMO costs (`COST_PROFILE`, data/history/costs/ftmo/) and
flat-before-rollover (no overnight holding). A grid item that tries to override either is refused
(`validate_grid`). The FTMO commission is UNKNOWN (symbolspec commission.status == "no_deals"): it is taken from
the cost data only -- scripts/real_costs.py returns 0.0 with its status -- and disclosed in every record.

Nothing here evaluates real history unless `run` is invoked, and `run` needs the plan, the ledger declaration
and an implemented grid. Batch 3 (owner sign-off) is the only place that happens.
"""
import argparse
import concurrent.futures
import contextlib
import datetime
import hashlib
import importlib.util
import json
import os
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
import isolated_pool as _pool         # one process per candidate

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
FIXED_KEYS = ("flat_before_rollover", "rollover_provider")                      # a grid item may never set these

#: Disclosed, never folded into N (plan §1.4): earlier searches on the same history.
PRIOR_COUNTS = {"prop_search_records": 180, "diagnosis_slices": 30}


def fixed_opts():
    """The OPTS overlay applied in EVERY cell: flat before the broker's daily rollover, priced by the profile's
    own server clock (scripts/real_costs.py PROFILES)."""
    import real_costs as _RC
    return {"flat_before_rollover": True, "rollover_provider": _RC.PROFILES[COST_PROFILE]["provider"]}


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


def validate_grid(grid, where="grid"):
    """A grid item may not touch a FIXED rule (real costs / flat-before-rollover stay on in every cell)."""
    for it in grid.items:
        key = grid.opts_key(it["id"])
        if key in FIXED_KEYS:
            raise GridRefused(f"{where}: item {it['id']!r} sets OPTS key {key!r}, which is FIXED in every fund cell "
                              f"(plan §6 item 7): refusing")


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
            cells.append({"id": cid, "timeframe": tf, "asset_class": ac,
                          "symbols": [s for s, _ in with_dev],
                          "symbols_without_development": without,
                          "development_start": min((fb for _, fb in with_dev), key=FS.ts)})
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
    core = {"cells": cells, "excluded_cells": excluded, "grids": grids_info, "candidates": candidates,
            "n_by_method": n_by_method, "cost_profile": COST_PROFILE, "dev_cutoff": FS.DEV_CUTOFF,
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
        L.append(f"  {c['id']:<14} m={len(c['symbols'])} symbols {','.join(c['symbols'])}  "
                 f"dev start {c['development_start']}")
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
                 + (f"; UNIMPLEMENTED items: {g['unimplemented']}" if g["unimplemented"] else ""))
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


class BtEngine:
    """scripts/backtest-methods.py `scan` + `simulate`, unmodified, truncated at DEV_CUTOFF (`bt.pit_cutoff`,
    the load-time PIT seam), with REAL costs and flat-before-rollover fixed on. `trades_for(values)` returns the
    simulated trades of the whole development span for one full V assignment; the folds slice them by time."""

    def __init__(self, grid, runner_method, tf, symbols, bt=None):
        self.grid, self.method, self.tf, self.symbols = grid, runner_method, tf, list(symbols)
        self.bt = bt or _load_bt()
        missing = [grid.opts_key(i["id"]) for i in grid.items if grid.opts_key(i["id"]) not in self.bt._OPTS_BASE]
        if grid.unimplemented or missing:
            raise GridRefused(f"grid items not implemented in the engine (unimplemented={grid.unimplemented}, "
                              f"keys absent from bt._OPTS_BASE={missing}): refusing to evaluate a partial grid "
                              f"(N counts every declared item)")
        self.bt.pit_cutoff(FS.DEV_CUTOFF)
        self._adx, self._last = {}, {}
        for s in self.symbols:
            candles, _src = self.bt.load(s, tf)
            if not candles:
                raise RuntimeError(f"{s} {tf}: no candles under {_HS.history_root()} (the plan said it has some)")
            self._adx[s] = FS.adx_index(candles)
            self._last[s] = candles[-1]["time"]

    def trades_for(self, values):
        overlay = dict(self.grid.overlay(values), **fixed_opts())
        raw = []
        for s in self.symbols:
            scan = self.bt.scan(s, self.tf, only=(self.method,), opts=overlay)
            raw += [t for t in scan["trades"][self.method]]
        # a timeout trade whose walk was cut by the end of the (PIT-truncated) series has an UNKNOWN outcome:
        # excluded, exactly as prop-search excludes it (addendum §8.2) -- horizon-independent, because the
        # time-stop H is itself a V item.
        raw = [t for t in raw if not (t.get("outcome") == "timeout" and t["exit_time"] >= self._last[t["symbol"]])]
        _final, _curve, taken = self.bt.simulate(raw, 0.0, cost_profile=COST_PROFILE, live_parity_sizing=False)
        out = []
        for t in taken:
            out.append(dict(t, adx14=FS.adx_before(self._adx[t["symbol"]], t["entry_time"])))
        return out

    def prop_pass(self, pooled):
        """prop_pass_probability per fund at the pre-registration's gating horizon, over the pooled test trades."""
        ps = _prop_search()
        if not pooled:
            return {f: None for f in ps.FUNDS}
        _final, curve, taken = self.bt.simulate(list(pooled), 0.0, cost_profile=COST_PROFILE,
                                                live_parity_sizing=True)
        out = {}
        for f in ps.FUNDS:
            m = ps._perf.metrics(taken, equity=curve, account=ps._AP.get(f), horizon=ps.CHALLENGE_HORIZON_DAYS)
            p = m.get("prop_pass_probability")
            out[f] = p["value"] if isinstance(p, dict) and "value" in p else None
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
def evaluate_with_engine(engine, grid, cell, n_comparisons):
    """Nested walk-forward -> perturbation sets -> every §1.4 rule. `engine` needs `trades_for(values)` and
    `prop_pass(pooled)`; nothing else touches data, so the whole path is testable with a synthetic engine."""
    src = FS.CountingSource(engine.trades_for)
    folds = FS.make_folds(cell["development_start"])
    fold_results = FS.nested_walk_forward(grid, src, folds)
    perturbs = FS.perturbation_trade_sets(grid, src, fold_results)
    prop = engine.prop_pass(FS.pooled_test_trades(fold_results))
    res = FS.evaluate_cell(fold_results, perturbs, cell["symbols"], n_comparisons, prop, runs=src.runs)
    res["folds_geometry"] = folds
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


def _evaluate_candidate(candidate, plan_hash, grid_dir=None):
    """Real path: the worker entry point (one process per candidate). Loads its own engine."""
    grids, paths = load_grids(grid_dir)
    grid = grids[candidate["method"]]
    plan = load_plan(grid_dir)
    cell = next(c for c in plan["cells"] if c["id"] == candidate["cell"])
    engine = BtEngine(grid, candidate["runner_method"], candidate["timeframe"], candidate["symbols"])
    result = evaluate_with_engine(engine, grid, cell, candidate["n_comparisons"])
    return {"record": dict(build_record(candidate, plan_hash, grid, paths[candidate["method"]], result,
                                        engine.dataset_snapshot(), cell))}


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
        "fixed": {"cost_profile": COST_PROFILE, "flat_before_rollover": True,
                  "cost_profile_snapshot": _RC.profile_snapshot(COST_PROFILE, candidate["symbols"])},
        "grid": {"file": os.path.basename(grid_path), "sha256": _sha256_file(grid_path),
                 "items": [{k: it.get(k) for k in ("id", "key", "existing_opts_key", "values", "joint_group",
                                                   "source")} for it in grid.items]},
        "code_version": _snap.code_version(), "plan_hash": plan_hash,
        "constants": {k: getattr(FS, k) for k in ("FAMILY_ALPHA", "MIN_FOLD_TRADES", "MIN_TRAIN_TRADES",
                                                   "MAX_TRADE_SHARE", "MAX_GAP_DAYS", "MIN_FOLD_SHARE_OK",
                                                   "PASS_PROB_MIN", "TEST_FOLD_DAYS", "MIN_TRAIN_DAYS")}})
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
                         "plan_hash": plan_hash})
    r.set("random_seed", {"lower_bound": "none: closed-form Student-t bound, no resampling",
                          "prop_pass_probability_bootstrap": "scripts/performance.py BOOTSTRAP_SEED"})
    r.set("test_periods", {"development": {"end": FS.DEV_CUTOFF, "period_id": DEV_PERIOD_ID},
                           "folds": result.get("folds_geometry"),
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


def cmd_run(cell_id, method=None, workers=1, grid_dir=None):
    plan = load_plan(grid_dir)
    require_declaration(plan)                       # refuses BEFORE anything is evaluated
    grids, _paths = load_grids(grid_dir)
    for m, g in grids.items():
        if g.unimplemented:
            raise GridRefused(f"{m} grid has unimplemented items {g.unimplemented}: refusing to evaluate a partial "
                              f"grid (N counts every declared item)")
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
        if workers <= 1:
            for c in todo:
                try:
                    results.append((c["id"], _evaluate_candidate(c, plan["plan_hash"], grid_dir)))
                except Exception as exc:  # noqa: BLE001
                    errors.append((c["id"], exc))
        else:
            with _pool.IsolatedExecutor(max_workers=workers) as ex:
                futs = {ex.submit(_evaluate_candidate, c, plan["plan_hash"], grid_dir): c["id"] for c in todo}
                for fut in concurrent.futures.as_completed(futs):
                    try:
                        results.append((futs[fut], fut.result()))
                    except Exception as exc:  # noqa: BLE001
                        errors.append((futs[fut], exc))
        for cid, out in results:                    # every finished candidate is written BEFORE any failure raises
            X.write(types.MappingProxyType(out["record"]), store=RECORDS_DIR)
            print(f"{out['record']['metrics']['evaluation']['verdict'].upper():<12} {cid}")
        if errors:
            raise RuntimeError("fund-search: candidate(s) raised -- FAILING LOUD (an exception is never recorded "
                               "as a fail): " + "; ".join(f"{c}: {type(e).__name__}: {e}" for c, e in errors))
    print(f"cell {cell_id}: {len(results)} evaluated, {len(done)} already recorded")


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
         "- No symbol was dropped after its result was seen: each candidate's symbols equal the plan's "
         "(`validate_record`).", ""]
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
          "- The lower bound is a Student-t bound on pooled trades treated as independent; it is backed by the "
          "single-trade cap and the perturbation check, not trusted alone.",
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
    rp = sub.add_parser("run", help="evaluate one cell (refuses without the ledger declaration)")
    rp.add_argument("--cell", required=True)
    rp.add_argument("--method", choices=sorted(METHODS))
    rp.add_argument("--workers", type=int, default=1)
    rp.add_argument("--grid-dir")
    sub.add_parser("report", help="write the markdown report over every record")
    a = ap.parse_args(argv)
    os.environ.setdefault("BT_HISTORY_ROOT", FTMO_HISTORY_ROOT)     # the fund search reads the FTMO feed (§6 item 8)
    if a.cmd == "plan":
        cmd_plan(dry_run=a.dry_run, grid_dir=a.grid_dir)
    elif a.cmd == "declare":
        cmd_declare()
    elif a.cmd == "list-cells":
        print(json.dumps([{"cell": c["id"]} for c in load_plan()["cells"]]))
    elif a.cmd == "run":
        cmd_run(a.cell, method=a.method, workers=a.workers, grid_dir=a.grid_dir)
    elif a.cmd == "report":
        cmd_report()


if __name__ == "__main__":
    main()
