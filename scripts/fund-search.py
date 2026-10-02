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

THE CELLS ARE DECLARED, NOT COMPUTED: docs/architecture/fund-search-cells.json lists the cells (owner 2026-10-01: three,
1m-metals, 1m-indices, 5m-metals; no 15m or 30m cell) and each cell's optional history start (`dev_start`, null = from data); it is hashed into the plan core and pinned in
the declaration (`evaluation_config.cells_sha256`) like the V grids, and `run`/`scan` refuse a changed one.

FIXED IN EVERY CELL (plan §6 items 3, 7): real FTMO costs (`COST_PROFILE`, data/history/costs/ftmo/; since 2026-10-02 the
relative-spread profile, pre-registration item 13b) and flat-before-rollover (no overnight holding); `simulate()` always runs
under the fixed OPTS (`simulate_context`, item 13a) and `walk()` fills gapped stops at the bar open (`fx_gap_fill`, item 13c). A grid item that tries to override either is refused
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
import math
import os
import platform
import re
import sys
import time
import types

ROOT =os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from repo_paths import repo_rel
import fund_stats as FS               # the statistics: pure, separately importable and tested
import experiment as X                # CLAUDE.md §42: the ONE reader/writer of the experiment store
import research_ledger as RL          # CLAUDE.md §43/§44: periods + the cell-count declaration
import history_store as _HS           # the shared history reader / HISTORY_ROOT (single-file or split-gz)
import instruments as _I              # asset_class of each symbol
import trading_env as _TE        # the ONE reader of the planned-R:R floor (analysis-params.json project_defined.ict.min_rr)
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
#: Pinned. The original seven FTMO symbols + XPTUSD XPDUSD + UK100 EU50 JP225 HK50 AUS200 US2000 SPN35 N25 (owner 2026-10-01,
#: symbol universe: docs/plans/2026-09-30-owner-decisions.md; AUS200 was dropped by §6 item 8 for lack of data and is back with the
#: owner's new export). Which cell gets which symbol is DECLARED per cell in docs/architecture/fund-search-cells.json (after the
#: cell-selection decision of 2026-10-01 only XPTUSD XPDUSD, in 5m-metals, draw on the additions; UK100 EU50 JP225 HK50 AUS200 US2000
#: SPN35 N25 are parked: kept here, in the registry and in the data, used by no cell, ignored by the readiness gate); this tuple is
#: a pinned superset, the universe a cell may draw from, deliberately not shrunk. Nine of them are research-only registry
#: symbols (instruments.json `research_only`, never orderable); XCUUSD and DXY were dropped: no history before the 2024-03-01 cutoff.
FUND_SYMBOLS = ("XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD", "US500", "US30", "USTEC", "DE40", "FRA40",
                "UK100", "EU50", "JP225", "HK50", "AUS200", "US2000", "SPN35", "N25")
FUND_TIMEFRAMES = ("1m", "5m", "15m")                                           # §6 item 7; 30m removed by the owner 2026-10-01
ASSET_CLASSES = ("metals", "indices")                                           # §6 item 7
#: Higher-timeframe context series a cell needs besides its own decision timeframe (gates, W7): see `data_readiness`.
CONTEXT_TIMEFRAMES = ("30m", "1H", "4H", "1D", "1W")
METHODS = {"ict": "ICT", "wyckoff": "WYCKOFF-BOOK"}                             # grid `method` -> bt runner method
GRID_FILES = {"ict": "v-grid-ict.json", "wyckoff": "v-grid-wyckoff.json"}
CELLS_FILE = "fund-search-cells.json"      # the declared cell list + each cell's history start (pinned like the grids)
#: §6 item 3: REAL costs, fixed on. C2 (red-team 2026-10-02): the RELATIVE-spread profile -- the recorded absolute spread is
#: scaled by entry / price_ref (scripts/real_costs.py "ABSOLUTE vs RELATIVE SPREAD"), because 2022-2026 absolute spreads
#: applied to 2004-2024 price levels overstate spread_R: measured 1.5-2.1x for most gold/silver folds, 6.0x XAUUSD 2004, 2.9x
#: XAGUSD 2008 (draft item 13b). `ftmo_demo_2026_09` (absolute, byte-identical to before) stays selectable in real_costs as
#: a comparison baseline (tests, scripts/research/reprice_real_costs.py); NO fund-search code or report prices a trade with it.
COST_PROFILE = "ftmo_demo_2026_09_relspread"
COST_PROFILE_ABSOLUTE = "ftmo_demo_2026_09"                                    # comparison baseline only, not used by a cell
DEV_PERIOD_ID = "cfd-development-pre-2024-03"                                   # research-ledger.json period
LEDGER_SECTION = "fund_search"                                                  # the declaration lives here
#: The nine F (fidelity) items the owner adopted for the evaluation baseline (docs/plans/2026-09-30-owner-decisions.md):
#: ON in every cell of every candidate, never varied, never settable by a grid item. Live/pilot keep v1.
#: Plus O1 (owner-approved 2026-09-30): `fx_admission_entry_cost` -- min_rr admission uses only entry-knowable costs
#: (scripts/backtest-methods.py simulate()). It is a fixed engine rule, not an F item; it lives in this tuple so it
#: is ON in every cell, in the plan hash and declaration config, and can never be set by a grid item.
#: Plus C3 (red-team 2026-10-02, coordinator decision, owner to ack before declare): `fx_gap_fill` -- walk() fills a stop at
#: the WORSE of the stop and the bar open when the bar opens beyond it (no more stop fills at a price the market never
#: traded). Fixed ON in every cell like O1; it is read at SCAN time (walk), so it travels with the scan overlay, and
#: simulate() never reads it (it is outside SIMULATE_TIME_OPTS).
ADOPTED_F_KEYS = ("fx_b2a_fvg_in_leg", "fx_b2b_ce_fail", "fx_b1_pivot1", "fx_braid_optional",
                  "fx_w1_tr_low_st", "fx_w2_st_below_sc", "fx_w3_mSOW_spring", "fx_w5_vp_abandon", "fx_w7_htf_target",
                  "fx_admission_entry_cost", "fx_gap_fill")
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


#: Disclosed, never folded into N (plan §1.4): earlier outcome reads on the same development history. Extended
#: 2026-10-02 (red-team C5); the paths and what each read showed are listed in the pre-registration draft, section 0.1
#: (docs/plans/2026-09-29-fund-search-preregistration-DRAFT.md). Counts are table rows / runs, not de-duplicated:
#: fidelity_funnel_rows_ict = 9 re-run + 9 carried rows of docs/audits/2026-09-29-ict-fidelity-funnel.md;
#: fidelity_funnel_rows_wyckoff = the 11 rows of the table in ...-wyckoff-fidelity-funnel.md; real_cost_reprice_runs = the
#: one disclosed A0 re-pricing; min_rr_values_tried = 3.0, 2.0, 2.5. Not in the plan hash (plan core excludes it).
PRIOR_COUNTS = {"prop_search_records": 180, "diagnosis_slices": 30, "fidelity_funnel_rows_ict": 18,
                "fidelity_funnel_rows_wyckoff": 11, "real_cost_reprice_runs": 1, "min_rr_values_tried": 3}


def cost_profile_pin(symbols):
    """What the plan and the declaration pin about the cost profile (C2): the profile name, how it scales the spread and,
    for the relative profile, every symbol's `price_ref` plus the sha256 of the provenance (window, bar count, closes hash)
    it was derived from -- so a changed history or spec shows up as drift, not as a silently different cost."""
    import real_costs as _RC
    snap = _RC.profile_snapshot(COST_PROFILE, sorted(set(symbols)))
    return {"profile": COST_PROFILE, "spread_scaling": snap.get("spread_scaling", _RC.ABSOLUTE),
            "price_ref": snap.get("price_ref"), "price_ref_provenance_sha256": snap.get("price_ref_provenance_sha256")}


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


class CellsRefused(SystemExit):
    """The declared cell list (docs/architecture/fund-search-cells.json) is missing or malformed."""


_CELL_KEYS = {"id", "timeframe", "asset_class", "symbols", "dev_start", "rationale", "decision"}


def load_cells_file(grid_dir=None):
    """(spec, path, sha256): the declared cells + per-cell `dev_start` override + warm-up days. Nothing is defaulted:
    a missing file, an unknown key, a 30m (or any undeclared) timeframe, a symbol outside FUND_SYMBOLS or of another
    asset class, a duplicate id, an override that is not a canonical `...Z` instant before DEV_CUTOFF, or an empty
    rationale/decision is refused (a cell list is pre-registered, never guessed)."""
    path = os.path.join(grid_dir or GRID_DIR, CELLS_FILE)
    if not os.path.exists(path):
        raise CellsRefused(f"cells file missing: {path} -- the cell list and each cell's history start are declared "
                           f"there (owner 2026-10-01), never typed here; refusing to guess them")
    try:
        with open(path, encoding="utf-8") as fh:
            spec = json.load(fh)
    except ValueError as exc:
        raise CellsRefused(f"{path}: not valid JSON: {exc}")
    cells = spec.get("cells") if isinstance(spec, dict) else None
    if not isinstance(cells, list) or not cells:
        raise CellsRefused(f"{path}: `cells` must be a non-empty list")
    wd = spec.get("warmup_days")
    if isinstance(wd, bool) or not isinstance(wd, int) or wd < 1:
        raise CellsRefused(f"{path}: `warmup_days` must be an integer >= 1 (got {wd!r})")
    seen, cutoff = set(), FS.ts(FS.DEV_CUTOFF)
    for c in cells:
        if not isinstance(c, dict) or set(c) != _CELL_KEYS:
            raise CellsRefused(f"{path}: every cell needs exactly the keys {sorted(_CELL_KEYS)}; got "
                               f"{sorted(c) if isinstance(c, dict) else c!r}")
        cid, tf, ac = c["id"], c["timeframe"], c["asset_class"]
        if cid != f"{tf}-{ac}":
            raise CellsRefused(f"{path}: cell id {cid!r} must be '<timeframe>-<asset_class>' ({tf}-{ac})")
        if cid in seen:
            raise CellsRefused(f"{path}: duplicate cell id {cid!r}")
        seen.add(cid)
        if tf not in FUND_TIMEFRAMES:
            raise CellsRefused(f"{path}: cell {cid!r}: timeframe {tf!r} is not a fund timeframe {FUND_TIMEFRAMES}")
        if ac not in ASSET_CLASSES:
            raise CellsRefused(f"{path}: cell {cid!r}: asset class {ac!r} not in {ASSET_CLASSES}")
        syms = c["symbols"]
        if not isinstance(syms, list) or not syms or len(set(syms)) != len(syms):
            raise CellsRefused(f"{path}: cell {cid!r}: `symbols` must be a non-empty list without duplicates")
        for sy in syms:
            if sy not in FUND_SYMBOLS or (_I.display(sy).get("asset_class") or "cfd") != ac:
                raise CellsRefused(f"{path}: cell {cid!r}: symbol {sy!r} is not a {ac} symbol of FUND_SYMBOLS")
        ds = c["dev_start"]
        if ds is not None:
            try:
                ok = isinstance(ds, str) and FS.iso(FS.ts(ds)) == ds and FS.ts(ds) < cutoff
            except ValueError:
                ok = False
            if not ok:
                raise CellsRefused(f"{path}: cell {cid!r}: dev_start {ds!r} must be null or a canonical UTC instant "
                                   f"'YYYY-MM-DDTHH:MM:SSZ' before {FS.DEV_CUTOFF}")
        for k in ("rationale", "decision"):
            if not (isinstance(c[k], str) and c[k].strip()):
                raise CellsRefused(f"{path}: cell {cid!r}: `{k}` must be a non-empty string")
    return spec, path, _sha256_file(path)


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
    # engine see grid.runnable() -- yet their number stays disclosed on the FULL grid (n_per_method; since family A the grid
    # values are not hypotheses of the multiple-testing family). They are listed in `plan` and in every record.
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


# ------------------------------------------------------------------------------------------- data readiness
class DataNotReady(SystemExit):
    """A declared cell needs history or a real-cost spec that does not exist yet (the owner exports them from MT5).
    Raised with the readiness table as its message: a precise report and a non-zero exit, never a stack trace."""


def _spec_present(sym):
    """(present, path) of `sym`'s real-cost symbolspec under COST_PROFILE (scripts/real_costs.py spec_path)."""
    import real_costs as _RC
    path = _RC.spec_path(COST_PROFILE, sym)
    return os.path.exists(path), path


def data_readiness(cells_spec, first_bar=None, spec_present=None):
    """Per declared cell: which symbols lack history (decision timeframe or a CONTEXT_TIMEFRAMES series) or a real-cost
    spec, and whether the cell would have any development data. Pure over its inputs (`first_bar(sym, tf)` -> ISO or None,
    `spec_present(sym)` -> (bool, path)); reads nothing else. Nothing is fabricated: a missing series is reported missing.

    `ready` is the HARD condition (every declared symbol has its series and spec): `plan`/`run`/`scan`/`declare` refuse
    without it. A symbol whose first bar is not before DEV_CUTOFF is not a readiness failure (plan §6 item 7: it is left out
    of m and disclosed). A cell in which NO symbol has development data is dropped from the plan's candidates by that same
    rule (the family size, counted on the DECLARED cells, still includes it); it does not block planning, but `complete` is
    False so `--check-data` exits non-zero: the owner declared this cell and should see that the plan would silently shrink."""
    first_bar = first_bar or _first_bar
    spec_present = spec_present or _spec_present
    cutoff = FS.ts(FS.DEV_CUTOFF)
    out, ready, complete = [], True, True
    for decl in cells_spec["cells"]:
        tf = decl["timeframe"]
        need = (tf,) + CONTEXT_TIMEFRAMES
        no_history, partial, no_spec, no_dev, late = [], {}, [], [], {}
        for sy in decl["symbols"]:
            have = {t: first_bar(sy, t) for t in need}
            miss = [t for t in need if have[t] is None]
            if len(miss) == len(need):
                no_history.append(sy)
            elif miss:
                partial[sy] = miss
            if not spec_present(sy)[0]:
                no_spec.append(sy)
            fb = have[tf]
            if fb is not None and FS.ts(fb) >= cutoff:
                no_dev.append(sy)
        cell_ready = not (no_history or partial or no_spec)
        with_data = [sy for sy in decl["symbols"] if sy not in no_history and sy not in no_dev
                     and (tf not in partial.get(sy, ()))]
        ready = ready and cell_ready
        complete = complete and cell_ready and bool(with_data)
        out.append({"id": decl["id"], "timeframe": tf, "symbols": list(decl["symbols"]),
                    "m_effective": len(with_data), "ready": cell_ready and bool(with_data),
                    "no_history": no_history, "partial_history": partial, "no_spec": no_spec,
                    "no_development_data": no_dev, "has_development_symbol": bool(with_data)})
    return {"ready": ready, "complete": complete, "cells": out}


def format_readiness(rep):
    """The readiness table: one row per declared cell, then the exact symbols/timeframes behind every gap."""
    rows = [("cell", "declared", "m", "no history", "partial", "no spec", "dev data", "ready")]
    for c in rep["cells"]:
        rows.append((c["id"], str(len(c["symbols"])), str(c["m_effective"]), str(len(c["no_history"])), str(len(c["partial_history"])),
                     str(len(c["no_spec"])), "yes" if c["has_development_symbol"] else "NONE",
                     "yes" if c["ready"] else "NO"))
    w = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    L = ["fund-search DATA READINESS (declared = symbols in the cells file; m = those with development data before the cutoff "
         "on the cell's timeframe, the stability denominator; decision timeframe + context series " + ",".join(CONTEXT_TIMEFRAMES)
         + "; real-cost spec per symbol under profile " + COST_PROFILE + ")",
         "  ".join(h.ljust(w[i]) for i, h in enumerate(rows[0]))]
    L += ["  ".join(v.ljust(w[i]) for i, v in enumerate(r)) for r in rows[1:]]
    for c in rep["cells"]:
        if c["ready"]:
            continue
        L.append(f"{c['id']}:")
        both = [x for x in c["no_history"] if x in c["no_spec"]]
        if both:
            L.append(f"  no history at all and no real-cost spec ({len(both)}): {', '.join(both)}")
        only_h = [x for x in c["no_history"] if x not in both]
        if only_h:
            L.append(f"  no history at all ({len(only_h)}): {', '.join(only_h)}")
        for sy, miss in c["partial_history"].items():
            L.append(f"  incomplete history: {sy} lacks {', '.join(miss)}")
        only_s = [x for x in c["no_spec"] if x not in both]
        if only_s:
            L.append(f"  no real-cost spec ({len(only_s)}): {', '.join(only_s)}")
        if c["no_development_data"]:
            L.append(f"  first bar not before {FS.DEV_CUTOFF} (left out of m by the plan rule): "
                     f"{', '.join(c['no_development_data'])}")
        if not c["has_development_symbol"]:
            L.append("  NO symbol has development data: the cell would be dropped from the plan (the family size still counts it)")
    bad = [c["id"] for c in rep["cells"] if not c["ready"]]
    L.append("READY: every declared cell has its history and real-cost specs" if rep["complete"] else
             f"NOT READY: {len(bad)} of {len(rep['cells'])} cells ({', '.join(bad)}). Nothing was evaluated or planned; "
             f"export the missing history (history.<RAW>.<TF>.json) and specs (symbolspec.<RAW>.json -> data/history/costs/ftmo/) "
             f"from MT5, import them, and re-run `fund-search.py plan --check-data`.")
    return "\n".join(L)


def check_data(grid_dir=None, first_bar=None, spec_present=None, out=None):
    """`plan --check-data`: print the readiness table; return 0 when complete, 1 when anything is missing."""
    spec, path, sha = load_cells_file(grid_dir)
    rep = data_readiness(spec, first_bar, spec_present)
    print(format_readiness(rep), file=out or sys.stdout)
    print(declared_n_line(spec, sha, grid_dir), file=out or sys.stdout)
    return 0 if rep["complete"] else 1


def family_size_of(cells_spec):
    """Family A (pre-registration 0.2): the multiple-testing family is the CANDIDATE PROCEDURES = declared cells x methods
    (3 x 2 = 6). Counted on the DECLARED cells, so a cell that later turns out to lack development history still counts
    (stricter, never looser)."""
    return len(cells_spec["cells"]) * len(METHODS)


def declared_n_line(cells_spec, cells_sha, grid_dir=None):
    """The family and its floor confidence of the DECLARED cells (no data needed), and the grid sizes disclosed beside them
    (grid values are NOT hypotheses of the family: the nested walk-forward handles value selection)."""
    grids, _ = load_grids(grid_dir)
    n_cells = len(cells_spec["cells"])
    size = family_size_of(cells_spec)
    per = ", ".join(f"{m} {FS.n_per_method(g)} per cell" for m, g in grids.items())
    return (f"declared cells: {n_cells}; family = {size} candidate procedures ({n_cells} cells x {len(METHODS)} methods); "
            f"floor confidence 1 - {FS.FAMILY_ALPHA}/{size} = {FS.n_adjusted_confidence(size):.6f} (Holm step-down at "
            f"FWER {FS.FAMILY_ALPHA} at report time); grid values disclosed, not in the family: {per}; "
            f"cells file sha256 {cells_sha}")


def require_data_ready(cells_spec, first_bar=None, spec_present=None):
    rep = data_readiness(cells_spec, first_bar, spec_present)
    if not rep["ready"]:
        raise DataNotReady(format_readiness(rep))
    return rep


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


def build_cells(first_bar=None, spec=None):
    """The DECLARED cells (`spec`, docs/architecture/fund-search-cells.json; default: the committed file), minus any cell
    without development history before DEV_CUTOFF (plan §6 item 7). Decided from DATA AVAILABILITY only -- never from a
    result. A symbol without development history is listed (with the reason) and is not part of m, the stability
    denominator; it is not silently forgotten. A cell's development start is its declared `dev_start` or, when that is
    null, the first bar the data has; a declared start needs at least one symbol with data at or before it (a symbol
    that begins later is kept and disclosed in `symbol_first_bar`: fewer early bars, never invented ones)."""
    first_bar = first_bar or _first_bar
    spec = spec if spec is not None else load_cells_file()[0]
    cells, excluded = [], []
    cutoff = FS.ts(FS.DEV_CUTOFF)
    for decl in spec["cells"]:
        tf, ac, cid = decl["timeframe"], decl["asset_class"], decl["id"]
        with_dev, without = [], {}
        for s in decl["symbols"]:
            fb = first_bar(s, tf)
            if fb is None:
                without[s] = "no history file"
            elif FS.ts(fb) >= cutoff:
                without[s] = f"first bar {fb} is not before {FS.DEV_CUTOFF}"
            else:
                with_dev.append((s, fb))
        if not with_dev:
            excluded.append({"id": cid, "timeframe": tf, "asset_class": ac,
                             "reason": "no symbol has development history before " + FS.DEV_CUTOFF,
                             "symbols_without_development": without})
            continue
        data_start = min((fb for _, fb in with_dev), key=FS.ts)
        override = decl["dev_start"]
        if override is not None and FS.ts(data_start) > FS.ts(override):
            raise CellsRefused(f"cell {cid!r}: declared dev_start {override} is before the first bar its data has "
                               f"({data_start}): no symbol can cover the start of the declared span")
        dev_start = override or data_start
        nf = len(FS.make_folds(dev_start))
        if override is not None and nf < FS.MIN_TEST_FOLDS:
            raise CellsRefused(f"cell {cid!r}: declared dev_start {override} yields {nf} test fold(s), fewer than "
                               f"MIN_TEST_FOLDS = {FS.MIN_TEST_FOLDS}: a walk-forward needs at least that many "
                               f"(folds end at {FS.DEV_CUTOFF}, each {FS.TEST_FOLD_DAYS} days, after >= "
                               f"{FS.MIN_TRAIN_DAYS} days of training)")
        cells.append({"id": cid, "timeframe": tf, "asset_class": ac,
                      "symbols": [s for s, _ in with_dev],
                      "symbols_without_development": without,
                      "symbol_first_bar": {s: fb for s, fb in with_dev},
                      "dev_start_override": override, "development_start": dev_start,
                      "span_source": "declared" if override else "from data",
                      "rationale": decl["rationale"], "decision": decl["decision"],
                      "n_folds": nf, "frequency_rule": FS.fold_arithmetic(nf)})
    return cells, excluded


def _hash(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def build_plan(grid_dir=None, first_bar=None, check_ready=None):
    """The plan. With the real data (no `first_bar` injected) every declared cell's history and real-cost specs must
    exist, else DataNotReady carries the readiness table (the N of a plan over missing data would be a silent shrink)."""
    grids, paths = load_grids(grid_dir)
    cells_spec, cells_path, cells_sha = load_cells_file(grid_dir)
    if check_ready is None:
        check_ready = first_bar is None
    if check_ready:
        require_data_ready(cells_spec, first_bar)
    cells, excluded = build_cells(first_bar, cells_spec)
    n_cells = len(cells)
    grids_info = {}
    for m, g in grids.items():
        per_cell = FS.n_per_method(g)
        grids_info[m] = {"file": repo_rel(paths[m], ROOT) if paths[m].startswith(ROOT) else paths[m],
                         "sha256": _sha256_file(paths[m]), "method": g.method, "items": len(g.items),
                         "non_baseline_values": per_cell - 2, "n_per_cell": per_cell,
                         "unimplemented": g.unimplemented}
    fam_size = family_size_of(cells_spec)
    floor_conf = FS.n_adjusted_confidence(fam_size)
    candidates = []
    for c in cells:
        for m in METHODS:
            candidates.append({"id": f"{m}-{c['id']}", "method": m, "runner_method": METHODS[m], "cell": c["id"],
                               "timeframe": c["timeframe"], "asset_class": c["asset_class"],
                               "symbols": list(c["symbols"]), "family_size": fam_size,
                               "floor_confidence": floor_conf})
    family = {"size": fam_size, "alpha": FS.FAMILY_ALPHA, "floor_confidence": floor_conf,
              "members": [f"{m}-{c['id']}" for c in cells_spec["cells"] for m in METHODS],
              "rule": FS.FAMILY_DEFINITION,
              "grid_values_disclosed_not_in_family": {m: g["n_per_cell"] for m, g in grids_info.items()}}
    embargo = {"rule": f"training trades need exit_label < test_start - {EMBARGO_H_MULTIPLE} x H bars (H = bt.P[tf]['H'])"
                       f", on top of the one-bar purge; 'none' time stops are covered only by this same window",
               "h_multiple": EMBARGO_H_MULTIPLE,
               "minutes_by_timeframe": {tf: int(embargo_for(tf) / datetime.timedelta(minutes=1))
                                        for tf in FUND_TIMEFRAMES}}
    cells_info = {"file": repo_rel(cells_path, ROOT) if cells_path.startswith(ROOT) else cells_path,
                  "sha256": cells_sha, "warmup_days": cells_spec["warmup_days"],
                  "removed_cells": cells_spec.get("removed_cells", [])}
    core = {"cells": cells, "cells_file": cells_info, "excluded_cells": excluded, "grids": grids_info, "candidates": candidates,
            "family": family, "cost_profile": COST_PROFILE,
            "cost_profile_pin": cost_profile_pin(s for c in cells for s in c["symbols"]), "dev_cutoff": FS.DEV_CUTOFF,
            "adopted_f_keys": list(ADOPTED_F_KEYS), "embargo": embargo,
            "perturbation_axes": FS.PERTURBATION_AXES,
            "constants": {k: getattr(FS, k) for k in (
                "FAMILY_ALPHA", "MIN_FOLD_TRADES", "MIN_TRAIN_TRADES", "MAX_TRADE_SHARE", "MAX_GAP_DAYS",
                "MIN_FOLD_SHARE_OK", "PASS_PROB_MIN", "ADX_PERIOD", "TEST_FOLD_DAYS", "MIN_TRAIN_DAYS",
                "MIN_TEST_FOLDS", "STRESS_SPREAD_STAT", "STRESS_COMMISSION_FRACTION", "MDE_POWER")}}
    plan = dict(core, _source=PLAN_DOC, cell_count=n_cells, candidate_count=len(candidates),
                fund_symbols=list(FUND_SYMBOLS), prior_counts_disclosed=PRIOR_COUNTS, plan_hash=_hash(core))
    return plan


def format_dry_run(plan, grid_note=""):
    L = [f"fund-search plan --dry-run: NOTHING is evaluated; no file is written{grid_note}",
         f"cells ({plan['cell_count']}), cost profile {plan['cost_profile']}, development cutoff {plan['dev_cutoff']}:"]
    for c in plan["cells"]:
        fr = c["frequency_rule"]
        L.append(f"  {c['id']:<14} m={len(c['symbols'])} symbols {','.join(c['symbols'])}  "
                 f"dev start {c['development_start']} ({c['span_source']})  folds {c['n_folds']} (frequency rule: >= "
                 f"{fr['folds_required_within_gap']} of {fr['n_folds']} folds with every gap <= "
                 f"{fr['max_gap_days']}d; {fr['folds_allowed_to_fail']} may fail)")
        for s, why in c["symbols_without_development"].items():
            L.append(f"      not in m: {s} ({why})")
    for e in plan["excluded_cells"]:
        L.append(f"  EXCLUDED {e['id']:<10} {e['reason']}")
    cf = plan["cells_file"]
    L.append(f"cells file {cf['file']} sha256 {cf['sha256'][:16]}, warm-up {cf['warmup_days']} d; removed: "
             f"{', '.join(r['id'] for r in cf['removed_cells']) or 'none'}")
    L.append(f"candidates: {plan['candidate_count']} (method x cell)")
    fam = plan["family"]
    L.append(f"multiple-testing family (family A): the {fam['size']} candidate procedures ({', '.join(fam['members'])}); "
             f"floor confidence for every candidate 1 - {fam['alpha']}/{fam['size']} = {fam['floor_confidence']:.6f}; "
             f"Holm step-down at FWER {fam['alpha']} over the {fam['size']} at report time (NOT RUN candidates count)")
    for m, g in plan["grids"].items():
        L.append(f"  {m:<8} grid values disclosed, NOT in the family: N per cell {g['n_per_cell']} "
                 f"(grid values are not hypotheses; the nested walk-forward handles value selection)"
                 + (f"; declared, not runnable: {g['unimplemented']}" if g["unimplemented"] else ""))
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
            "cells": [c["id"] for c in plan["cells"]], "family_size": plan["family"]["size"],
            "floor_confidence": plan["family"]["floor_confidence"]}
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


def _git(*a, root=None, cfg=()):
    """Run `git -C root [-c key=value ...] a...`; stdout stripped, or None when git fails. `cfg` = ("key=value", ...)."""
    import subprocess
    try:
        out = subprocess.run(["git", "-C", root or ROOT, *[x for kv in cfg for x in ("-c", kv)], *a],
                             capture_output=True, text=True, timeout=20)
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


# Every module the evaluation imports (statically or by spec_from_file_location) from fund-search.py: the engine, the
# metrics, the PIT / quality / validity layer, the account + environment readers, the history reader, the scan cache
# and the ledger. The git TREE pins below (`PINNED_TREES`) cover the whole of scripts/ as well; this per-file list
# stays because it names WHICH file moved in a drift message. Excluded on purpose (not imported by fund-search.py or by
# the listed modules' computation, so a change cannot alter a result; still covered by the scripts/ tree pin): htf_context,
# i18n (NOTE: i18n.py IS imported, by methods.py, for display strings only; the scripts/ tree pin covers it),
# selection_criteria, method_purity, setup_version, cron-templates, rank-setups, win_services, get_secret.
FINGERPRINT_FILES = ("scripts/fund_stats.py", "scripts/fund-search.py", "scripts/prop-search.py",
                     "scripts/backtest-methods.py", "scripts/real_costs.py", "scripts/performance.py",
                     "scripts/mt5_time.py", "scripts/ict-scan.py", "scripts/wyckoff_rules.py",
                     "scripts/live_rules.py", "scripts/scan_many.py", "scripts/structures.py",
                     "scripts/history_store.py", "scripts/normalized.py", "scripts/pit.py", "scripts/quality.py",
                     "scripts/research_validity.py", "scripts/account_profile.py", "scripts/trading_env.py",
                     "scripts/instruments.py", "scripts/event_risk.py", "scripts/isolated_pool.py",
                     "scripts/experiment.py",
                     # also imported on the path (backtest-methods / prop-search / fund-search headers):
                     "scripts/sessions.py", "scripts/methods.py", "scripts/snapshot.py",
                     "scripts/trader_constraints.py", "scripts/providers.py", "scripts/risk_model.py",
                     "scripts/trading_system.py", "scripts/scan_cache.py", "scripts/research_ledger.py",
                     "scripts/repo_paths.py", "scripts/automation.py", "scripts/stability-report.py")

# Git TREE pins (2026-10-02 red-team I5): `git rev-parse HEAD:<path>` of every directory a result depends on. scripts/ is
# the code; docs/architecture/ holds analysis-params.json, account-profiles.json, the symbol map and the other
# readers' inputs; data/history/costs/ftmo the symbolspec files; data/history/ftmo the committed candles. They need
# only git OBJECTS (no history), so they also work in a shallow clone. docs/architecture/ is pinned WITHOUT
# research-ledger.json: that file holds the declaration itself (and every later ledger event), so a tree hash that
# included it could never equal itself after `declare`. It is pinned as a sha256 over `git ls-tree -r HEAD` of the
# directory minus that one file (a blob-hash listing: any other file's change moves it).
LEDGER_REL = "docs/architecture/research-ledger.json"
PINNED_TREES = ("scripts", "docs/architecture", "data/history/costs/ftmo", "data/history/ftmo")
# a tracked-file change or an UNTRACKED file under these refuses declare / run / scan; config/, .claude/ etc. never block
DIRTY_SCOPE = ("scripts", "docs/architecture", "data/history")
_ALLOW_DIRTY_HELP = ("TESTS / DRY RUNS ONLY: proceed although the pinned tree is modified or has untracked files; a "
                     "WARNING is printed and the result says so (run: every record stamped drifted=true; declare: "
                     "`allow_dirty` in the declaration; scan: the dirty list is part of the cache stamp)")


def tree_pins(root=None):
    """{path: tree hash} for PINNED_TREES at HEAD (None = git could not answer: never a guess)."""
    out = {}
    for path in PINNED_TREES:
        if path == "docs/architecture":
            listing = _git("ls-tree", "-r", "HEAD", "--", path, root=root)
            if listing is None:
                out[path] = None
                continue
            kept = [ln for ln in listing.splitlines() if not ln.endswith("\t" + LEDGER_REL)]
            out[path] = "ls-tree-sha256:" + _sha_text("\n".join(kept))
        else:
            out[path] = _git("rev-parse", f"HEAD:{path}", root=root)
    return out


def repo_pins(root=None):
    return {"head": _git("rev-parse", "HEAD", root=root), "trees": tree_pins(root),
            "tree_note": "docs/architecture is pinned without research-ledger.json (it holds the declaration itself)"}


def runtime_env():
    """Informational: the interpreter and platform that made the declaration. A different one is a drift NOTE, never a
    refusal (CI runs Python 3.12 on Linux, the owner's machine 3.14 on macOS)."""
    return {"python": platform.python_version(), "implementation": platform.python_implementation(),
            "platform": platform.platform(), "machine": platform.machine()}


def _ignored_by_repo_gitignore(path, root=None):
    """True iff `path` (repo-relative) is ignored by a `.gitignore` OF THE REPO (`git check-ignore -v` names the source rule;
    a developer's global excludes file or .git/info/exclude does not count: those could hide a file the code reads)."""
    # the developer's GLOBAL excludes file is switched off for this question (a global `docs/*` would be reported as the
    # deciding rule and hide the repo's own line); .git/info/exclude is rejected below by the source check
    out = _git("check-ignore", "-v", "--", path, root=root, cfg=(f"core.excludesFile={os.devnull}",))
    if not out:
        return False
    source = out.split("\t", 1)[0].split(":", 1)[0]
    return os.path.basename(source) == ".gitignore"


def _hidden_change_flags(root=None):
    """Tracked files under DIRTY_SCOPE that carry the skip-worktree ('S') or assume-unchanged (lowercase tag) flag: `git
    status` never reports their modifications, so the ordinary dirty check cannot see them. None if git cannot answer."""
    out = _git("ls-files", "-v", "--", *DIRTY_SCOPE, root=root)
    if out is None:
        return None
    rows = []
    for ln in out.splitlines():
        if len(ln) > 2 and ln[1] == " " and (ln[0] == "S" or ln[0].islower()):
            rows.append(f"hidden-change-flag[{ln[0]}] {ln[2:]}")
    return rows


def scoped_dirty(root=None):
    """Lines of `git status` for tracked modifications AND untracked files under DIRTY_SCOPE only (config/env.example,
    .claude/worktrees/ and every other path are ignored), plus tracked files under DIRTY_SCOPE flagged skip-worktree or
    assume-unchanged (their edits are invisible to `git status`). None if git cannot answer (treated as dirty by the caller)."""
    out = _git("status", "--porcelain", "--untracked-files=all", "--", *DIRTY_SCOPE, root=root)
    # `status` hides files a (global) ignore rule matches -- e.g. a developer's `docs/*` -- yet the code may still read
    # them: list every untracked file in scope, ignored or not, except interpreter / OS cruft and a `.lock` file that the
    # repo's OWN .gitignore ignores (scripts/automation.py's 0-byte config lock). A stray `.lock` that is tracked or not
    # ignored by the repo still blocks.
    other = _git("ls-files", "--others", "--", *DIRTY_SCOPE, root=root)
    flagged = _hidden_change_flags(root)
    if out is None or other is None or flagged is None:
        return None
    cruft = ("__pycache__/", ".pyc", ".DS_Store")

    def benign(path):
        return any(c in path for c in cruft) or (path.endswith(".lock") and _ignored_by_repo_gitignore(path, root))
    lines = {ln.strip() for ln in out.splitlines() if ln.strip() and not any(c in ln for c in cruft)}
    lines |= {"?? " + ln.strip() for ln in other.splitlines() if ln.strip() and not benign(ln.strip())}
    lines |= set(flagged)
    return sorted(lines)


class DirtyTreeRefused(SystemExit):
    """declare / run / scan refused: pinned code / config / history is modified or untracked in the working tree."""


def check_clean_tree(allow_dirty=False, root=None):
    """Refuse (DirtyTreeRefused) unless the scoped tree is clean. With allow_dirty (tests / dry runs only) return the
    dirty lines after a loud WARNING so the caller can stamp them; never silent."""
    dirty = scoped_dirty(root)
    if dirty == []:
        return []
    shown = ["git status unavailable (cannot prove the tree clean)"] if dirty is None else dirty
    if allow_dirty:
        print("WARNING: --allow-dirty: the pinned tree is NOT clean; this run is not reproducible evidence:\n  "
              + "\n  ".join(shown[:20]), file=sys.stderr, flush=True)
        return shown
    raise DirtyTreeRefused(
        "refusing: tracked files are modified or untracked files exist under " + ", ".join(DIRTY_SCOPE) + ":\n  "
        + "\n  ".join(shown[:20]) + ("\n  ..." if len(shown) > 20 else "")
        + "\nCommit (or remove) them so the declaration pins exactly the code that runs. `--allow-dirty` exists for "
          "tests and dry runs only.")



def code_fingerprint(files=FINGERPRINT_FILES):
    """I4: the last-commit SHA of each file that decides a result, plus whether it has uncommitted changes. A
    missing git yields None, never a guess."""
    out = {}
    for f in files:
        sha = _git("log", "-1", "--format=%H", "--", f)
        status = _git("status", "--porcelain", "--", f)
        out[f] = {"git_sha": sha or None, "dirty": (bool(status) if status is not None else None)}
    return out


def min_trading_days_required():
    """{fund: declared `min_trading_days` | None} for the prop gate's funds (prop-search FUNDS), read from the account profiles
    (scripts/account_profile.py: THE one source, as prop-search `_required_days`). None when ANY profile is unreadable or
    malformed -- `FS.check_min_trading_days` then fails closed. A fund declaring `min_profitable_days` instead has None."""
    try:
        ps = _prop_search()
        out = {}
        for f in ps.FUNDS:
            d = ps._AP.get(f)["rules"].get("min_trading_days")
            if d is not None and (not isinstance(d, int) or isinstance(d, bool) or d < 1):
                return None
            out[f] = d
        return out or None
    except Exception:  # noqa: BLE001 -- an unreadable profile is a failed check, never a crash or a skipped gate
        return None


def min_trading_days_config():
    """The pinned definition of the minimum-trading-days check: the text, the declared minimum per fund, the source profile id
    and the profiles' own 'flagged for verification' note (None values when the profile is unreadable -> drift)."""
    req = min_trading_days_required()
    src = [f for f, d in (req or {}).items() if d is not None]
    notes = {}
    for f in src:
        try:
            notes[f] = _prop_search()._AP.get(f)["rules"].get("_min_trading_days_why")
        except Exception:  # noqa: BLE001
            notes[f] = None
    return {"definition": FS.MIN_TRADING_DAYS_DEFINITION, "declared_by_fund": req, "source_profile_ids": src,
            "source_file": "docs/architecture/account-profiles.json", "profile_note_flagged_for_verification": notes}


def evaluation_config(plan):
    """I4: every setting that decides a verdict, stated once so the declaration pins it."""
    ps = _prop_search()
    return {"stability_fraction": list(FS.STABILITY_FRACTION), "block_days": FS.BLOCK_DAYS,
            "live_parity_sizing": {"trades_for": False, "prop_pass": True}, "spread_stat": "median",
            "prop_funds": list(ps.FUNDS), "prop_horizon_days": ps.CHALLENGE_HORIZON_DAYS,
            "prop_pass_min": FS.PASS_PROB_MIN, "verdict_precedence": FS.VERDICT_PRECEDENCE,
            "regime_split": FS.REGIME_SPLIT_DEFINITION,
            "family": plan["family"],
            "perturbation": {"definition": FS.PERTURBATION_DEFINITION, "axes": FS.PERTURBATION_AXES},
            "stress": {"definition": FS.STRESS_DEFINITION, "spread_stat": FS.STRESS_SPREAD_STAT,
                       "commission_fraction": FS.STRESS_COMMISSION_FRACTION},
            "prop_shift": FS.PROP_SHIFT_DEFINITION, "mde_power": FS.MDE_POWER,
            "min_trading_days": min_trading_days_config(),
            "ruin_handling": "bt.RUIN_FRAC = 0.0 on the harness's own bt instance; post_ruin trades fail loud",
            "adopted_f_keys": list(ADOPTED_F_KEYS), "embargo": plan["embargo"],
            "cost_profile": plan["cost_profile"], "cost_profile_pin": plan["cost_profile_pin"],
            # owner 2026-09-30: planned R:R floor at entry (net of fees), both methods; None = unreadable -> drift
            "min_rr": _TE.min_rr(),
            "grid_sha256": {m: g["sha256"] for m, g in plan["grids"].items()},
            "cells_sha256": plan["cells_file"]["sha256"],
            "dev_start_by_cell": {c["id"]: c.get("dev_start_override") for c in plan["cells"]},
            "span_warmup_days": plan["cells_file"]["warmup_days"]}


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
    pins = decl.get("repo_pins")
    if not isinstance(pins, dict) or not isinstance(pins.get("trees"), dict) or not pins["trees"]:
        out.append("declaration has no `repo_pins.trees` (git tree hashes of scripts/, docs/architecture, "
                   "data/history/costs/ftmo, data/history/ftmo)")
    else:
        now = tree_pins()
        for path in sorted(set(pins["trees"]) | set(now)):
            if pins["trees"].get(path) != now.get(path) or now.get(path) is None:
                out.append(f"tree {path}: declared {pins['trees'].get(path)!r}, now {now.get(path)!r}")
    return out


def drift_notes(decl):
    """Differences that are reported but never refuse: the interpreter / platform (CI uses Python 3.12 on Linux, the
    owner's machine 3.14 on macOS; the declaration records what made it) and a declared HEAD that is not an ancestor
    of the current one (the binding pins are the tree hashes; HEAD moves with every commit, the declaration's own
    included)."""
    notes = []
    rt, now = decl.get("runtime"), runtime_env()
    if not isinstance(rt, dict):
        notes.append("NOTE: the declaration records no Python version / platform")
    else:
        for k in ("python", "implementation", "platform", "machine"):
            if rt.get(k) != now[k]:
                notes.append(f"NOTE (not a refusal): runtime {k}: declared {rt.get(k)!r}, now {now[k]!r}")
    head = (decl.get("repo_pins") or {}).get("head")
    if head and _git("merge-base", "--is-ancestor", head, "HEAD") is None and _git("rev-parse", "HEAD") != head:
        # `is-ancestor` exits 1 when it is not an ancestor (or the object is missing): _git() maps both to None
        notes.append(f"NOTE (not a refusal): the declared HEAD {head[:12]} is not an ancestor of the current HEAD "
                     f"(shallow clone, or another branch); the tree pins above are what bind")
    return notes


def check_drift(decl, plan, allow_drift=False):
    for n in drift_notes(decl):
        print(n, file=sys.stderr, flush=True)
    drift = detect_drift(decl, plan)
    if drift and not allow_drift:
        raise DeclarationDrift(
            "refusing to run: the code or evaluation settings differ from what `declare` recorded in the ledger:\n  "
            + "\n  ".join(drift) + "\nRe-declare through a ledger event, or pass --allow-drift to proceed with "
            "every record stamped drifted=true.")
    return drift


RUNNER_BENCHMARK_PATH = os.path.join(ROOT, "docs", "audits", "2026-10-01-runner-benchmark.json")


def runner_benchmark_status():
    """Whether `SHARD_MODEL["layout_factor"]` comes from a RECORDED hosted-runner benchmark: the committed
    docs/audits/2026-10-01-runner-benchmark.json (the artifact of .github/workflows/fund-search-benchmark.yml, committed by
    the owner) whose `layout_factor` equals the model's. `declare` records its sha256 and prints a NOTE when it is missing
    or differs; it never refuses (the owner decides: the layout only affects job sizing, never a result)."""
    want = SHARD_MODEL["layout_factor"]
    if not os.path.exists(RUNNER_BENCHMARK_PATH):
        return {"recorded": False, "layout_factor": want, "sha256": None,
                "note": f"layout_factor {want:g} is an ASSUMPTION: no recorded runner benchmark at "
                        f"{repo_rel(RUNNER_BENCHMARK_PATH, ROOT)}. Run .github/workflows/fund-search-benchmark.yml, commit its "
                        f"JSON there and set SHARD_MODEL['layout_factor'] to its layout_factor BEFORE declaring "
                        f"(docs/audits/2026-10-01-shard-calibration.md section 6)."}
    doc = json.load(open(RUNNER_BENCHMARK_PATH, encoding="utf-8"))
    # the layout factor is DERIVED from the measured per-job factors (worst job, rounded up to 0.25): the shards run with
    # 4 workers, so the 4-worker jobs count (the artifact's own `layout_factor` field used the single-process rule only)
    fs = [float(r["factor"]) for r in doc.get("factors", []) if r.get("status") == "OK" and r.get("factor")]
    got = math.ceil(max(fs) / 0.25) * 0.25 if fs and doc.get("all_ok") else None
    ok = got == want
    return {"recorded": ok, "layout_factor": want, "sha256": _sha256_file(RUNNER_BENCHMARK_PATH),
            "note": "" if ok else f"the recorded benchmark says layout_factor {got} but SHARD_MODEL has {want:g}: make them equal"}


def cmd_declare(allow_dirty=False):
    """Record the final cell count in the ledger. Refuses if any evaluation record already exists (the count must
    precede evaluation), if the pinned tree (scripts/, docs/architecture/, data/history/) is not clean, or if a
    different declaration is already there (a ledger event, not an overwrite)."""
    dirty = check_clean_tree(allow_dirty)
    plan = load_plan()
    if os.path.isdir(RECORDS_DIR) and any(f.endswith(".json") for f in os.listdir(RECORDS_DIR)):
        raise SystemExit(f"refusing to declare: records already exist under {RECORDS_DIR}; the cell count must be "
                         f"recorded BEFORE any evaluation")
    data = _read_ledger()
    new = {"plan_hash": plan["plan_hash"], "cell_count": plan["cell_count"],
           "cells": [c["id"] for c in plan["cells"]],
           # family A (2026-10-02): the family is the candidate procedures, not the grid values; `cell_count` stays the number of
           # cells. Replaces `n_by_method` / `confidence_by_method` (per-method N 87 / 48).
           "family_size": plan["family"]["size"], "floor_confidence": plan["family"]["floor_confidence"],
           "family_members": plan["family"]["members"], "family_rule": plan["family"]["rule"],
           "excluded_cells": plan["excluded_cells"],
           "code": code_fingerprint(), "evaluation_config": evaluation_config(plan),
           "repo_pins": repo_pins(), "runtime": runtime_env(),
           "source": PLAN_DOC + " §6 items 2, 7", "declared_at": _now_iso()}
    if dirty:
        new["allow_dirty"] = dirty                      # never silent: the declaration says it was made on a dirty tree
    old = data.get(LEDGER_SECTION)
    if old:
        if all(old.get(k) == new[k] for k in ("plan_hash", "cell_count", "cells")):
            print("declaration unchanged")
            return old
        raise SystemExit(f"refusing to overwrite the existing `{LEDGER_SECTION}` declaration with a different "
                         f"one: changing it after the fact is a ledger event, not an edit")
    new["runner_benchmark"] = runner_benchmark_status()
    if not new["runner_benchmark"]["recorded"]:
        print("NOTE (does not stop the declaration): " + new["runner_benchmark"]["note"], file=sys.stderr, flush=True)
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


#: C1 (red-team 2026-10-02): the OPTS keys `bt.simulate()` (and every function it calls: planned_risk_refusal,
#: _risk_scale, _account_stop, _venue_for_symbol, real_costs.*) reads from the MODULE-GLOBAL `OPTS` -- AUDITED by reading
#: scripts/backtest-methods.py (`grep OPTS` over simulate and its callees) and PINNED by
#: scripts/tests/test_simulate_time_opts.py, which re-derives the set from the source and fails if it changes:
#:   * `min_rr`                   -- the planned-R:R admission floor (not a V item; ALLOWED_EXISTING_OPTS is only `mgmt`)
#:   * `fx_admission_entry_cost`  -- O1, ON in every cell (ADOPTED_F_KEYS)
#:   * `fx_b_exit`                -- only its 2R-FLOOR token ("floor" | "no_floor") is read at simulate time; the grid
#:                                   (B-EXIT) declares only "...|floor" values, so the token is a fixed constant
#: `mgmt` is NOT read by simulate(): it is read by `walk()` (scan time) and therefore travels with the scan overlay.
#: simulate() is fold-independent, which `prop_pass` relies on (it pools trades of folds that chose different V values):
#: it must run under the FIXED simulate-time set only, never under any one candidate's V overlay.
SIMULATE_TIME_OPTS = ("min_rr", "fx_admission_entry_cost", "fx_b_exit")
SIMULATE_FLOOR_TOKEN = "floor"


def _floor_token(v):
    parts = v.split("|") if isinstance(v, str) else []
    return parts[2] if len(parts) == 3 else None


def simulate_time_opts(bt, overlay=None):
    """The OPTS dict `bt.simulate()` must run under: `dict(bt._OPTS_BASE, **fixed_opts())` -- the frozen engine baseline plus
    the fixed fund rules, never the process-global OPTS (which is the v1 baseline unless a scan is running). Refuses
    loudly when a candidate's V overlay tries to change a simulate-time key (a V key that became simulate-time would make
    simulate() fold-dependent), or when the fixed set is not what the pre-registration says (O1 on, floor token 'floor')."""
    sim = dict(bt._OPTS_BASE, **fixed_opts())
    if sim.get("fx_admission_entry_cost") is not True:
        raise GridRefused("fx_admission_entry_cost is not True in the simulate-time OPTS: O1 is a fixed fund rule "
                          "(the harness would run the v1 exit-hour admission)")
    if _floor_token(sim.get("fx_b_exit")) != SIMULATE_FLOOR_TOKEN:
        raise GridRefused(f"simulate-time fx_b_exit={sim.get('fx_b_exit')!r}: the 2R-floor token must be "
                          f"{SIMULATE_FLOOR_TOKEN!r} in every fund cell (owner 2026-09-30)")
    if not isinstance(sim.get("min_rr"), (int, float)) or isinstance(sim.get("min_rr"), bool):
        raise GridRefused(f"simulate-time min_rr={sim.get('min_rr')!r} is not a number")
    for k, v in (overlay or {}).items():
        if k not in SIMULATE_TIME_OPTS:
            continue
        if k == "fx_b_exit":
            if _floor_token(v) != SIMULATE_FLOOR_TOKEN:
                raise GridRefused(f"a V value sets fx_b_exit={v!r}: its 2R-floor token is read by simulate() and must "
                                  f"be {SIMULATE_FLOOR_TOKEN!r} (a fold-dependent simulate-time key is refused)")
        elif v != sim[k]:
            raise GridRefused(f"the candidate overlay sets simulate-time OPTS key {k!r}={v!r} (fixed: {sim[k]!r}): a V "
                              f"key may never become simulate-time -- prop_pass pools trades of different folds")
    return sim


@contextlib.contextmanager
def simulate_context(bt, overlay=None):
    """Run `bt.simulate()` under `simulate_time_opts` and restore the module OPTS afterwards (exception-safe)."""
    sim = simulate_time_opts(bt, overlay)
    saved = bt.OPTS
    bt.OPTS = sim
    try:
        yield sim
    finally:
        bt.OPTS = saved


def checked_simulate(bt, trades, fee, *, overlay, **kw):
    """`bt.simulate` that FAILS LOUD when the run ended in ruin / dropped trades (I1), so a lost trade is never a
    silent outcome, and when the candidate's overlay does not have flat_before_rollover on (round 2, item 5b).
    It runs under `simulate_context` (C1): simulate() reads the module-global OPTS, which is NOT the candidate's
    overlay (that only reaches `bt.scan(opts=...)`), so without this the harness simulated with the v1 admission.
    Returns simulate's own (equity, curve, taken)."""
    assert_flat_overlay(overlay)
    with simulate_context(bt, overlay):
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
    Recorded and counted, never raised on. O8 is CLOSED (2026-10-02, pre-registration draft section B): `walk()` with
    flat_before_rollover on already asks about the boundary between the ENTRY (fill) bar and the first walked bar
    (commit 2869c35) and, when it is crossed, closes the trade flat at the entry bar's own close (`rollover_flat`, zero
    bars walked), so a fill inside the last bar of a server day is NOT held past midnight. This count is therefore the
    number of entries that rule acts on -- information, not a leak."""
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
    (R_planned - fee_R - min_rr) near the floor.

    Pre-registration item 12 (planned-risk admission): a row with a `zero_risk` cause is a candidate whose planned
    risk is zero / wrong-side / below one tick / not a finite price (`bt.planned_risk_refusal`). It is counted in
    `candidates` and in `refused_zero_risk` and has no R_planned / fee_R, so it never enters the min_rr margins:
    every min_rr figure is over the risk-valid candidates only, exactly as before for a value set that has none."""
    if fold is not None:
        a, b = FS.ts(fold["test_start"]), FS.ts(fold["test_end"])
        rows = [r for r in rows if a <= FS.ts(r["entry_time"]) < b]
    refused_zr = [r for r in rows if r.get("zero_risk")]
    valid = [r for r in rows if not r.get("zero_risk")]
    margins = [r["R_planned"] - r["fee_R"] - min_rr for r in valid]
    near = sorted(m for m in margins if abs(m) < NEAR_FLOOR_MARGIN)
    return {"candidates": len(rows), "refused_zero_risk": len(refused_zr),
            "refused_min_rr": sum(1 for m in margins if m < 0),
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
    pins. The FTMO history is covered per entry by `scope.series` (bar count, first and last bar, and a sha256 of the
    PIT-truncated candle series the scan read). 2026-10-02 (I5): also the repo HEAD, the git tree hashes of scripts/,
    docs/architecture/, data/history/costs/ftmo and data/history/ftmo, and the scoped dirty list (empty on a clean
    tree), so a cache made from other code, config or data -- or on a dirty tree -- is refused. The Python version is
    NOT in the stamp (CI 3.12 and the owner's 3.14 must share a cache); it is a declaration NOTE."""
    return {"format": SCAN_CACHE_FORMAT, "plan_hash": plan["plan_hash"], "code": code_fingerprint(),
            "code_sha256": {f: _sha256_file(os.path.join(ROOT, f)) for f in FINGERPRINT_FILES},
            "evaluation_config": evaluation_config(plan),
            "repo_head": _git("rev-parse", "HEAD"), "repo_trees": tree_pins(), "scoped_dirty": scoped_dirty()}


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
    """One entry, verified against `stamp` (this run's plan / code / settings) and for self-consistency (key, counts,
    trades sha256). The sha256s detect accidental corruption and casual edits; they are NOT authentication -- anyone who
    can rewrite a file can rewrite its hashes too, so a cache directory is trusted only as far as its provenance
    (a same-run artifact). Raises ScanCacheRefused."""
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
        bad("trades do not match their recorded sha256 (edited or corrupted)")
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
    got, sha, ekeys = {}, {}, {}
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
        got[k], sha[k], ekeys[k] = e["trades"], e["trades_sha256"], e["key"]
    return got, ekeys


def _series_sha256(candles, chunk=50000):
    """sha256 over the PIT-truncated candle series, streamed in chunks (a 4 M-bar series is never one string). Same
    serialisation as `dataset_snapshot` per chunk; it identifies the bars the scan read, so a changed history file
    cannot be paired with a cache made from another one."""
    h = hashlib.sha256()
    for i in range(0, len(candles), chunk):
        h.update(json.dumps(candles[i:i + chunk], sort_keys=True).encode())
    return h.hexdigest()


def span_args(plan, cell):
    """The BtEngine keywords that carry a cell's DECLARED history start: `dev_start` (None = from data: nothing is cut)
    and the plan's `warmup_days`. Only what the pinned cells file said reaches the engine."""
    ds = cell.get("dev_start_override")
    return {"dev_start": ds, "warmup_days": (plan.get("cells_file") or {}).get("warmup_days") if ds else None}


class BtEngine:
    """scripts/backtest-methods.py `scan` + `simulate`, unmodified, truncated at DEV_CUTOFF (`bt.pit_cutoff`,
    the load-time PIT seam), with REAL costs and flat-before-rollover fixed on. `trades_for(values)` returns the
    simulated trades of the whole development span for one full V assignment; the folds slice them by time.

    `dev_start` (a cell's DECLARED history start, docs/architecture/fund-search-cells.json; None = from data, nothing is
    cut): the decision series is loaded from `dev_start - warmup_days` (minus the method's own window) onward -- compute
    drops with the span -- and every trade entered before `dev_start` is discarded after `simulate()`, so none exists in
    any fold. Higher-timeframe series keep their full PIT history (`bt.series_start` cuts one (symbol, timeframe) only).
    Equivalence with the full-series run is proved by scripts/research/span_equivalence.py and EngineDevStart."""

    def __init__(self, grid, runner_method, tf, symbols, bt=None, workers=1, dev_start=None, warmup_days=None):
        self.grid, self.method, self.tf, self.symbols = grid, runner_method, tf, list(symbols)
        self.dev_start = dev_start                   # a cell's DECLARED span start (None = from data: nothing is cut)
        self._dev_start_ts = None
        if dev_start is not None:
            if not (isinstance(warmup_days, int) and warmup_days >= 1):
                raise ValueError("dev_start needs warmup_days (the plan's cells_file.warmup_days): refusing to guess it")
            self._dev_start_ts = FS.ts(dev_start)
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
        self.span = None
        if dev_start is None:                        # an injected bt may carry a stale cut from an earlier engine
            for s in self.symbols:
                self.bt.series_start(s, tf, None)
        if dev_start is not None:
            # the DECISION series only (bt.series_start is keyed by (symbol, tf)): scan from `dev_start - warmup_days`
            # minus the method's own window; every higher-timeframe series a gate / the W7 target reads keeps its full
            # PIT history (past data, no leakage). Trades entered before dev_start are dropped in trades_for.
            lead = self._lead_bars()
            start = FS.iso(self._dev_start_ts - datetime.timedelta(days=warmup_days))
            for s in self.symbols:
                self.bt.series_start(s, tf, start, lead)
            self.span = {"dev_start": dev_start, "warmup_days": warmup_days, "scan_start": start, "lead_bars": lead}
        self._admission, self._edge = {}, {}
        self._adx, self._last = {}, {}
        self._d1, self._d1_series = {}, {}           # symbol -> D1 ADX index of the symbol's OWN D1 series (regime split), its identity
        self._part = {}                              # value key -> {symbol: raw trades} held from a scan cache, incomplete
        self._series = {}                            # symbol -> what the PIT-truncated series looks like (scan-cache identity)
        for s in self.symbols:
            candles, _src = self.bt.load(s, tf)
            if not candles:
                raise RuntimeError(f"{s} {tf}: no candles under {_HS.history_root()} (the plan said it has some)")
            self._adx[s] = FS.adx_index(candles)      # the decision-timeframe ADX: REPORTING only (trade field `adx14`)
            self._last[s] = candles[-1]["time"]
            self._series[s] = {"bars": len(candles), "first_open": candles[0]["time"], "last_open": candles[-1]["time"],
                               "sha256": _series_sha256(candles)}
            # the REGIME SPLIT reads the D1 ADX(14) of the symbol's own stored D1 series (pre-registration 0.7), PIT-truncated
            # like every series (bt.pit_cutoff cuts on open + one bar). A symbol with no D1 series gets no value: its trades
            # fail the regime check (never dropped, never filled from another timeframe).
            d1, _src = self.bt.load(s, "1D")
            if d1:
                self._d1[s] = FS.d1_adx_index(d1)
                self._d1_series[s] = {"bars": len(d1), "first_open": d1[0]["time"], "last_open": d1[-1]["time"],
                                      "sha256": _series_sha256(d1)}
            else:
                self._d1[s], self._d1_series[s] = None, None

    def _lead_bars(self):
        """Bars the method reads BEFORE a decision bar: ICT's live scan window, or the LONGEST Wyckoff window any V
        value of the grid can ask for (W6), so the first decision bar after the warm-up sees a full window."""
        if self.method == "ICT":
            return int(self.bt.lr.scan_spec(self.tf)[0])
        wins = [int(self.bt.WYCKOFF_WINDOW)]
        for it in self.grid.items:
            if it["key"] == "fx_w6_window":
                wins += [int(v) for v in it["values"] if isinstance(v, int) and not isinstance(v, bool)]
        return max(wins)

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
        if getattr(self, "no_scan", False):
            gap = [(k, s) for k in keys for s in self.symbols if s not in part.get(k, {})]
            raise ScanCacheRefused(f"--require-complete-scan-cache: {len(gap)} (value set, symbol) scan(s) are not in the "
                                   f"cache and would have to run on demand (e.g. {gap[0][1]} {gap[0][0][:80]}...)")
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
        got, ekeys = load_scan_entries(dirs, stamp, cell_id, self.method, self.tf, self._series)
        by_key, used = {}, []
        for (key, sym), trades in got.items():
            if only_keys is None or key in only_keys:
                by_key.setdefault(key, {})[sym] = trades
                used.append(ekeys[(key, sym)])
        full = 0
        for key, per in sorted(by_key.items()):
            if key in self._done or key in self._raw:
                continue
            if all(s in per for s in self.symbols):
                self._raw[key] = [t for s in self.symbols for t in per[s]]
                full += 1
            else:
                self._part[key] = per
        self.scan_cache_info = {"entries": len(used), "complete_value_sets": full,
                                "sha256_of_sorted_entry_keys": _sha_text("\n".join(sorted(used)))}
        return full, len(used)

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
                if getattr(self, "no_scan", False):
                    raise ScanCacheRefused(f"--require-complete-scan-cache: {s} {key[:80]}... is not in the cache and "
                                           f"would have to be scanned on demand")
                scan = self.bt.scan(s, self.tf, only=(self.method,), opts=overlay)
                raw += [t for t in scan["trades"][self.method]]
        # a timeout trade whose walk was cut by the end of the (PIT-truncated) series has an UNKNOWN outcome:
        # excluded, exactly as prop-search excludes it (addendum §8.2) -- horizon-independent, because the
        # time-stop H is itself a V item.
        raw = [t for t in raw if not (t.get("outcome") == "timeout" and t["exit_time"] >= self._last[t["symbol"]])]
        import real_costs as _RC
        # Item 12 (planned-risk admission): a candidate with no valid stop distance is NOT priced (cost_r would raise on
        # it) and NOT entered; it is a counted `zero_risk` admission row. The rule is `bt.planned_risk_refusal`, the
        # SAME function simulate() applies, so both sides refuse exactly the same candidates (asserted below).
        rows = []
        # the admission cost the SIMULATE-TIME opts apply (O1: entry-hour, no swap) -- not the exit-hour cost v1 charged
        adm_entry_only = simulate_time_opts(self.bt, overlay)["fx_admission_entry_cost"]
        for t in raw:
            why = self.bt.planned_risk_refusal(t.get("side"), t.get("entry"), t.get("stop"),
                                               _RC.tick_size(COST_PROFILE, t["symbol"]))
            if why is not None:
                rows.append({"entry_time": t["entry_time"], "zero_risk": why})
                continue
            rows.append({"entry_time": t["entry_time"], "R_planned": t.get("R_planned", 99),
                         "fee_R": _RC.cost_r(t["entry"], t["stop"], t["entry_time"],
                                             t["entry_time"] if adm_entry_only else t["exit_time"], t["symbol"],
                                             t["side"], COST_PROFILE)["total_R"]})
        self._admission[key] = rows
        taken = checked_simulate(self.bt, raw, 0.0, overlay=overlay, cost_profile=COST_PROFILE,
                                 live_parity_sizing=False)[2]
        sim_zr = ((getattr(self.bt, "SIM_LAST", None) or {}).get("refused") or {}).get(self.bt.ZERO_RISK_REASON)
        if sim_zr != sum(1 for r in rows if r.get("zero_risk")):
            raise RuntimeError(f"planned-risk admission disagrees: simulate() refused {sim_zr!r} candidates as "
                               f"{self.bt.ZERO_RISK_REASON!r}, the harness' admission rows hold "
                               f"{sum(1 for r in rows if r.get('zero_risk'))}")
        if self._dev_start_ts is not None:     # warm-up trades settled simulate()'s state; none of them is a cell trade
            taken = [t for t in taken if FS.ts(t["entry_time"]) >= self._dev_start_ts]
            self._admission[key] = [r for r in self._admission[key] if FS.ts(r["entry_time"]) >= self._dev_start_ts]
        provider = fixed_opts()["rollover_provider"]
        assert_no_rollover_crossing(taken, provider, self.tf)
        self._edge[key] = last_bar_entry_times(taken, self.tf, provider)
        self._done[key] = [dict(t, adx14=FS.adx_before(self._adx[t["symbol"]], t["entry_time"]),
                                adx14_d1=(FS.d1_adx_at(self._d1[t["symbol"]], t["entry_time"])
                                          if self._d1.get(t["symbol"]) is not None else None))
                           for t in taken]
        return list(self._done[key])

    def admission_stats(self, values, fold=None):
        """I2: how many candidates the simulate() min_rr filter refused for this V assignment (optionally inside
        one fold's test window), and how the R_planned margin behaves near the floor."""
        rows = self._admission.get(FS.CountingSource._key(values), [])
        return admission_stats(rows, self.bt.OPTS["min_rr"], fold)

    def rollover_edge_stats(self, values, fold=None):
        return rollover_edge_stats(self._edge.get(FS.CountingSource._key(values), []), fold)

    def prop_pass(self, pooled, r_shift=0.0):
        """prop_pass_probability per fund at the pre-registration's gating horizon, over the pooled test trades,
        as explicit rows: value, status/reason when unavailable, low_confidence and the bootstrap spread minimum.

        `r_shift` (pre-registration A8b, default 0.0 = the unshifted gate, byte-identical to before): every ADMITTED trade's
        net R is reduced by `r_shift` AFTER simulate() (the admitted list, the sizing and the horizon are exactly those of the
        unshifted run) and before the metric's bootstrap reads it. Nothing shared with prop-search changes: the shift is
        applied here, not in scripts/performance.py."""
        ps = _prop_search()
        if not pooled:
            return {f: {"value": None, "reason": "no pooled test trades"} for f in ps.FUNDS}
        _final, curve, taken = checked_simulate(self.bt, list(pooled), 0.0, overlay=fixed_opts(),
                                                cost_profile=COST_PROFILE, live_parity_sizing=True)
        if r_shift:
            taken = [dict(t, net_R=t["net_R"] - r_shift) for t in taken]
        out = {}
        for f in ps.FUNDS:
            m = ps._perf.metrics(taken, equity=curve, account=ps._AP.get(f), horizon=ps.CHALLENGE_HORIZON_DAYS)
            out[f] = prop_row_from_metric(m.get("prop_pass_probability"))
        return out

    def stress_trades(self, pooled):
        """The SAME admitted trades re-priced under stress (pre-registration A8a): gross R - the real round-turn cost with the
        p90 spread on both legs (`real_costs.cost_r(..., spread_stat='p90')`: price-scaled by the relative-spread profile, swap
        unchanged) - the commission stress margin 0.00003 * entry / |entry - stop| in R (a margin, NOT an estimate). No trade is
        added or removed and admission is not re-run: only `net_R` changes (`net_R_median` keeps the unstressed value). Returns
        None when any trade's margin is not computable; the stress gate then FAILS (`check_stress`)."""
        import real_costs as _RC
        out = []
        for t in pooled:
            cr = _RC.cost_r(t["entry"], t["stop"], t["entry_time"], t["exit_time"], t["symbol"], t["side"], COST_PROFILE,
                            spread_stat=FS.STRESS_SPREAD_STAT)
            net = FS.stressed_net_r(t["R"], cr["total_R"], t["entry"], t["stop"])
            if net is None:        # the commission margin is not computable (no valid stop distance): FAIL CLOSED, not a raise
                return None
            out.append(dict(t, net_R_median=t["net_R"], net_R=net))
        return out

    def mean_spread_r(self, trades):
        """Mean spread_R (the spread cost in R) of `trades` under the fund profile -- the per-fold cost report (section C item 4)."""
        import real_costs as _RC
        return _RC.mean_spread_r(trades, COST_PROFILE)["mean_spread_R"]

    def dataset_snapshot(self):
        rows = []
        for s in self.symbols:
            candles, _ = self.bt.load(s, self.tf)
            rows.append({"symbol": s, "timeframe": self.tf, "bars": len(candles), "first_open": candles[0]["time"],
                         "last_open": candles[-1]["time"], "history_root": repo_rel(self.bt.HISTORY_ROOT, ROOT),
                         "sha256": hashlib.sha256(json.dumps(candles, sort_keys=True).encode()).hexdigest(),
                         "quality_flags": [dict(f) for f in self.bt.QUALITY_FLAGS
                                           if f["symbol"] == s and f["tf"] == self.tf],
                         "_pit_truncated": True, "_pit_cutoff": FS.DEV_CUTOFF,
                         "_series_start": dict(self.span) if self.span else None})
        ident = hashlib.sha256("|".join(f"{r['symbol']}:{r['timeframe']}:{r['sha256']}" for r in rows)
                               .encode()).hexdigest()[:16]
        return {"snapshot_format": 1, "snapshot_id": ident, "created_at": _now_iso(), "series": rows,
                "regime_series": [dict(symbol=s, timeframe="1D", **(self._d1_series.get(s) or {"bars": 0}))
                                  for s in self.symbols],
                "_note": "the PIT-truncated series the scan actually read (bt.pit_cutoff at DEV_CUTOFF); regime_series = the "
                         "symbols' own D1 series the regime split reads (D1 ADX(14), last completed bar), PIT-truncated alike"}


# ------------------------------------------------------------------------------------- one candidate (pure glue)
ADMISSION_LIMITATION = ("O1 DECIDED 2026-09-30: every fund cell runs with fx_admission_entry_cost ON, so simulate()'s min_rr "
                        "admission subtracts only entry-knowable costs (entry-hour half-spread + an exit-leg half-spread "
                        "estimated at the entry hour, no swap); the reported net R still uses the real entry+exit costs. "
                        "Under v1 (key off) admission would include the EXIT-hour spread, a look-ahead against plan §37. "
                        "ENFORCED IN THE HARNESS (C1, 2026-10-02): simulate() reads the module-global OPTS, not the scan "
                        "overlay, so `checked_simulate` runs it under `simulate_context` = dict(bt._OPTS_BASE, **fixed_opts()) "
                        "for BOTH trades_for and prop_pass (fixed simulate-time keys: min_rr, fx_admission_entry_cost, the "
                        "fx_b_exit floor token); the admission rows below use the same entry-hour cost. "
                        "The refusal counts and near-floor margins are still disclosed here.")


ROLLOVER_EDGE_NOTE = ("entries whose entry bar is the LAST bar of a server day. With flat_before_rollover on (fixed in "
                      "every fund cell) walk() also asks about the boundary between the entry (fill) bar and the first "
                      "walked bar (commit 2869c35) and, if it is crossed, closes the trade flat at the entry bar's own "
                      "close ('rollover_flat', zero bars walked), so such a fill is NOT held past midnight. The count is "
                      "kept as information (the entries that check acts on). Closed item O8 (2026-10-02; "
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
    FS.perturbation_trade_sets(grid, p2, fold_results)         # the gated ordinal neighbours ...
    FS.categorical_flip_sets(grid, p2, fold_results)           # ... and the report-only categorical flips
    return list(p2.missing.values())


def evaluate_with_engine(engine, grid, cell, family_size, axes=None):
    """Nested walk-forward -> perturbation sets -> every rule. `family_size` = the number of CANDIDATE procedures (family A,
    the plan's `family.size`: 6), which fixes the FLOOR confidence 1 - 0.10/family_size of every candidate. `engine` needs
    `trades_for(values)` and `prop_pass(pooled, r_shift=0.0)`; it MAY offer `stress_trades(pooled)` (the stress gate fails
    closed without it) and `mean_spread_r(trades)`; nothing else touches data, so the whole path is testable with a synthetic
    engine. An engine that also offers `prefetch`/`has` (BtEngine) is filled in two waves first (`prefetch_waves`): faster,
    same trades, same order of scoring. `axes` overrides `FS.PERTURBATION_AXES` (tests with synthetic grids only)."""
    if callable(getattr(engine, "prefetch", None)) and callable(getattr(engine, "has", None)):
        prefetch_waves(engine, grid, cell)
    src = FS.CountingSource(engine.trades_for)
    folds = FS.make_folds(cell["development_start"])
    emb = embargo_for(cell["timeframe"], getattr(engine, "bt", None))
    fold_results = FS.nested_walk_forward(grid, src, folds, FS.bar_delta(cell["timeframe"]), embargo=emb)
    perturbs = FS.perturbation_trade_sets(grid, src, fold_results, axes)
    skips = FS.perturbation_skips(grid, fold_results, axes)
    flips = FS.categorical_flip_sets(grid, src, fold_results, axes)
    pooled = FS.pooled_test_trades(fold_results)
    conf = FS.n_adjusted_confidence(family_size)
    prop = engine.prop_pass(pooled)
    shift = FS.prop_shift_r(FS.robust_lower_bound(pooled, conf))               # A8b: mean - primary bound at the floor
    prop_shifted = engine.prop_pass(pooled, r_shift=shift) if (shift is not None and pooled) else None
    stress = engine.stress_trades(pooled) if (pooled and callable(getattr(engine, "stress_trades", None))) else None
    res = FS.evaluate_cell(fold_results, perturbs, cell["symbols"], family_size, prop, runs=src.runs, stress=stress,
                           prop_shifted=prop_shifted, shift_r=shift, categorical=flips, skips=skips, grid=grid, axes=axes,
                           min_days_required=min_trading_days_required())
    res["fold_cost_report"] = [        # section C item 4: per test fold, the chosen values' mean net R and mean spread_R
        {"test_start": fr["fold"]["test_start"], "n_trades": len(fr["test_trades"]),
         "mean_net_R": FS.mean([t["net_R"] for t in fr["test_trades"]]),
         "mean_spread_R": (engine.mean_spread_r(fr["test_trades"])
                           if fr["test_trades"] and callable(getattr(engine, "mean_spread_r", None)) else None)}
        for fr in fold_results]
    res["folds_geometry"] = folds
    res["embargo_minutes"] = int(emb / datetime.timedelta(minutes=1))       # O2: recorded with the result
    if hasattr(engine, "admission_stats"):             # I2: measured, disclosed, never used to change a verdict
        res["admission"] = {
            "by_fold_chosen": [dict(engine.admission_stats(fr["chosen"], fr["fold"]), test_start=fr["fold"]["test_start"])
                               for fr in fold_results],
            "by_value_set": {k: engine.admission_stats(v) for k, v in src.evaluated()},
            "limitation": ADMISSION_LIMITATION}
    if hasattr(engine, "rollover_edge_stats"):         # O8 (CLOSED 2026-10-02): the entries the rollover-flat rule acts on, counted
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


def _evaluate_candidate(candidate, plan_hash, grid_dir=None, scan_workers=1, scan_cache_dirs=(),
                        require_complete_scan_cache=False):
    """Real path: evaluates one candidate. Loads its own engine; `scan_workers` is the process budget of the scan
    pool inside it (`--workers`). `scan_cache_dirs` (`--scan-cache`): verified raw scans from Actions shards are loaded
    into the engine first (anything absent is scanned on demand, as without a cache)."""
    grids, paths = load_grids(grid_dir)
    full_grid = grids[candidate["method"]]
    grid = full_grid.runnable()          # the family (candidate["family_size"]) counts candidate procedures, not grid values
    plan = load_plan(grid_dir)
    cell = next(c for c in plan["cells"] if c["id"] == candidate["cell"])
    engine = BtEngine(grid, candidate["runner_method"], candidate["timeframe"], candidate["symbols"],
                      workers=scan_workers, **span_args(plan, cell))
    if scan_cache_dirs:
        full, n = engine.load_scan_cache(scan_cache_stamp(plan), scan_cache_dirs, candidate["cell"])
        print(f"fund-search: scan cache: {n} verified (value set, symbol) entries, {full} value set(s) complete for "
              f"{candidate['id']}", file=sys.stderr, flush=True)
        engine.no_scan = bool(require_complete_scan_cache)   # any on-demand scan now fails loud (ScanCacheRefused)
    result = evaluate_with_engine(engine, grid, cell, candidate["family_size"])
    result["declared_not_run"] = full_grid.unimplemented
    return {"record": dict(build_record(candidate, plan_hash, grid, paths[candidate["method"]], result,
                                        engine.dataset_snapshot(), cell,
                                        scan_cache=getattr(engine, "scan_cache_info", None) if scan_cache_dirs else None))}


def _drift_from_env():
    try:
        return json.loads(os.environ.get(DRIFT_ENV) or "[]")
    except ValueError:
        return ["unreadable drift stamp"]


def build_record(candidate, plan_hash, grid, grid_path, result, dataset_snapshot, cell, scan_cache=None):
    import real_costs as _RC
    import snapshot as _snap
    cid = candidate["id"]
    r = X.Record(
        hypothesis=(f"{candidate['runner_method']} on {candidate['timeframe']} ({candidate['asset_class']}, symbols "
                    f"{candidate['symbols']}), V values chosen by nested walk-forward on development data, passes "
                    f"every {PLAN_DOC} §1.4 rule at the floor confidence 1 - {FS.FAMILY_ALPHA}/{candidate['family_size']} "
                    f"(family A: {candidate['family_size']} candidate procedures, Holm step-down at report time) -- "
                    f"falsified if any rule fails or a test fold has < "
                    f"{FS.MIN_FOLD_TRADES} trades."),
        motivation=(f"Owner decisions 2026-09-28/29 ({PLAN_DOC} §6 items 2-8): search fund-account setups on 1m/5m/"
                    f"15m under real FTMO costs and no overnight holding, without loosening any check."),
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
        "lower_bound": ("primary bound = min(iid t, CR1 by UTC date, by 30-day window, by calendar quarter, by half-year) at "
                        f"the floor confidence 1 - {FS.FAMILY_ALPHA}/{candidate['family_size']} (family A)"),
        "family": FS.FAMILY_DEFINITION, "perturbation": FS.PERTURBATION_DEFINITION,
        "perturbation_axes": FS.PERTURBATION_AXES, "stress": FS.STRESS_DEFINITION, "prop_shift": FS.PROP_SHIFT_DEFINITION,
        "regime_split": FS.REGIME_SPLIT_DEFINITION, "min_trading_days": min_trading_days_config(),
        "verdict_precedence": FS.VERDICT_PRECEDENCE,
        "constants": dict({k: getattr(FS, k) for k in ("FAMILY_ALPHA", "MIN_FOLD_TRADES", "MIN_TRAIN_TRADES",
                                                        "MAX_TRADE_SHARE", "MAX_GAP_DAYS", "MIN_FOLD_SHARE_OK",
                                                        "PASS_PROB_MIN", "TEST_FOLD_DAYS", "MIN_TRAIN_DAYS",
                                                        "STRESS_COMMISSION_FRACTION", "MDE_POWER")},
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
                         "symbols_evaluated": list(cell["symbols"]), "family_size": candidate["family_size"],
                         "floor_confidence": candidate["floor_confidence"],
                         "plan_hash": plan_hash,
                         "development_start": cell.get("development_start"),
                         "dev_start_override": cell.get("dev_start_override"),     # the declared span start (null = from data)
                         "drifted": bool(_drift_from_env()), "drift": _drift_from_env(),
                         **({"scan_cache": scan_cache} if scan_cache else {})})   # provenance only; no statistic reads it
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
                                 "perturbation": result["checks"]["perturbation"],
                                 "stress": result["checks"]["stress"],
                                 "prop_pass_shifted": result["checks"]["prop_pass_shifted"],
                                 "min_trading_days": result["checks"]["min_trading_days"],
                                 "categorical_flips": result.get("categorical_flips")})
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


def cmd_run(cell_id, method=None, workers=1, grid_dir=None, allow_drift=False, scan_cache_dirs=(),
            require_complete_scan_cache=False, allow_dirty=False):
    if require_complete_scan_cache and not scan_cache_dirs:
        raise SystemExit("--require-complete-scan-cache needs --scan-cache")
    dirty = check_clean_tree(allow_dirty)           # refuses on a modified / untracked pinned tree (tests: --allow-dirty)
    plan = load_plan(grid_dir)
    decl = require_declaration(plan)                # refuses BEFORE anything is evaluated
    drift = check_drift(decl, plan, allow_drift)    # refuses on code / settings drift unless --allow-drift
    if dirty:                                       # --allow-dirty: every record says so
        drift = drift + [f"--allow-dirty: the pinned tree was not clean: {dirty[:20]}"]
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
        _cmd_run_inner(plan, cell_id, method, workers, grid_dir, scan_cache_dirs, require_complete_scan_cache)
    finally:
        os.environ.pop(DRIFT_ENV, None)


DRIFT_ENV = "FUND_SEARCH_DRIFT"


def _cmd_run_inner(plan, cell_id, method, workers, grid_dir, scan_cache_dirs=(), require_complete=False):
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
        if require_complete:
            kw["require_complete_scan_cache"] = True
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
           "FRA40": 174454, "XPTUSD": 494217, "XPDUSD": 480765},
    "15m": {"XAUUSD": 453893, "XAGUSD": 357694, "US500": 62776, "US30": 116405, "USTEC": 62766, "DE40": 55219,
            "FRA40": 62283}}    # (the 30m rows were removed with the 30m cells, owner 2026-10-01)

#: The shard time model (docs/audits/2026-10-01-shard-calibration.md; supersedes the owner's one-run 581 s / 213 s model of
#: docs/audits/2026-09-30-actions-sharding.md section 3). It exists to LAY OUT shards (how many slices each wave of each
#: symbol gets) and to size the run; it never changes a result. Every rate is seconds per DECISION bar on the REFERENCE
#: machine (an M-series Mac, ONE process, in-process `scan_many`), fitted to real scans of the harness's own engine on
#: real FTMO history; `shard_seconds(.., factor)` scales the compute by the runner-speed factor (a hosted runner's core
#: relative to the reference core: UNKNOWN, so layouts and reports are given at 1.0, 1.5 and 2.0).
#: MEASURED vs ASSUMED is listed in `SHARD_MODEL["measured"]` / `["assumed"]` and printed under `list-scan-shards --explain`.
SHARD_MODEL = {
    # ---- MEASURED (doc sections 3.1-3.9): cost of ONE scan_many call = call_fixed_s + bars x (sum over detection groups of
    #      group_s_per_bar x window factor + (value sets - groups) x extra_set_s_per_bar); history-position averaged
    #      for the metals (a Wyckoff scan is dearer late in the history: the W7 target reads a growing HTF prefix)
    "group_s_per_bar": {          # [method][timeframe][asset class]; the doc's sections 3.1-3.4 (metals: fit x position factor)
        "ict": {"1m": {"metals": 0.000646, "indices": 0.000704}, "5m": {"metals": 0.00125, "indices": 0.00115},
                "15m": {"metals": 0.00135, "indices": 0.00115}},
        "wyckoff": {"1m": {"metals": 0.000749, "indices": 0.000369}, "5m": {"metals": 0.000211, "indices": 0.00018},
                    "15m": {"metals": 0.000186, "indices": 0.000161}}},
    "extra_set_s_per_bar": {      # one more value set INSIDE a detection group (indices: ASSUMED from the metals' ratio)
        "ict": {"1m": {"metals": 8.49e-05, "indices": 8.96e-05}, "5m": {"metals": 6.94e-05, "indices": 6.4e-05},
                "15m": {"metals": 3.98e-05, "indices": 3.41e-05}},
        "wyckoff": {"1m": {"metals": 0.0, "indices": 0.0}, "5m": {"metals": 1.07e-06, "indices": 8.21e-07},
                    "15m": {"metals": 4.49e-06, "indices": 3.48e-06}}},
    "call_fixed_s": {"ict": {"1m": 0.0, "5m": 0.0, "15m": 0.0}, "wyckoff": {"1m": 70.0, "5m": 2.11, "15m": 0.646}},
    "w600_group_factor": {"1m": 1.33, "5m": 1.74, "15m": 1.88},       # a W6 = 600 Wyckoff group costs this much more than a default-window group
    "max_groups": {"ict": 2, "wyckoff": 36},          # distinct detection groups the method can have at all (ICT: B-POOL only)
    "parallel_efficiency": {"ict": {1: 1.0, 2: 0.95, 3: 0.9, 4: 0.88}, "wyckoff": {1: 1.0, 2: 0.83, 3: 0.8, 4: 0.77}},
    "task_overhead_s_per_bar": 3.5e-6,    # a spawned scan worker reloads the full series (load + arrays), per bar of that series
    "engine_build_s_per_bar": 5.0e-6,     # BtEngine construction: load + adx index + series sha256, per held bar
    "trades_per_bar": {"ict": {"1m": 2.8e-3, "5m": 1.7e-3, "15m": 1.4e-3}, "wyckoff": {"1m": 1.7e-3, "5m": 1.6e-3, "15m": 1.3e-3}},
    "cache_verify_s_per_trade": 1.0e-5,   # read + verify one cache entry, per trade in it
    "trades_for_s_per_trade": 1.0e-4,     # trades_for (simulate + admission rows + adx) per raw trade
    # ---- ASSUMED (not measured here; doc section 7)
    "runner_vcpu": 4, "runner_ram_bytes": 16 * 2 ** 30,         # GitHub-hosted ubuntu-latest, PUBLIC repo (not verified)
    "job_fixed_s": 360.0,                 # checkout, Python setup, artifact up/download, per job (not scaled by the factor)
    "plan_job_min": 5,                    # the `plan` job in front of every wave
    "cache_entry_s": 0.05,                # fixed cost of one cache entry (open, hash)
    "select_s_per_fold": 1.0,             # the nested walk-forward replay per fold (measured < 0.1 s; 1 s kept as a margin)
    "layout_factor": 3.0,                 # the slow-runner factor the SLICE COUNTS are laid out for: the hosted-runner benchmark of
                                          # 2026-10-01 (docs/audits/2026-10-01-runner-benchmark.json) measured 1.57-2.84 over all jobs,
                                          # the 4-worker jobs being the slowest (2.64-2.84: 4 vCPU = 2 cores), worst rounded up to 0.25
    "report_factors": (1.0, 2.0, 3.0),
    "budget_s": 300 * 60,                 # no shard may be modelled above this at the layout factor (the job timeout is 355 min;
    "job_timeout_min": 355,               #  GitHub's hard cap is 360)
    "measured": ("group_s_per_bar", "extra_set_s_per_bar", "call_fixed_s", "w600_group_factor", "max_groups",
                 "parallel_efficiency", "task_overhead_s_per_bar", "engine_build_s_per_bar", "trades_per_bar",
                 "cache_verify_s_per_trade", "trades_for_s_per_trade"),
    "assumed": ("runner_vcpu", "runner_ram_bytes", "job_fixed_s", "plan_job_min", "cache_entry_s", "select_s_per_fold",
                "layout_factor", "report_factors", "budget_s", "job_timeout_min"),
}
SHARD_MODEL_LABEL = (f"MEASURED ({', '.join(SHARD_MODEL['measured'])}, WAVE2_SETS_PER_FOLD, WAVE2_SETS_FIXED, WAVE2_GROUPS_PER_SET, "
                     f"WAVE2_W600_GROUP_SHARE; docs/audits/2026-10-01-shard-calibration.md) | ASSUMED "
                     f"({', '.join(SHARD_MODEL['assumed'])}; the runner-speed factor is a parameter, never a measurement)")
#: Wave-2 shape under the SEALED perturbation definition (the fold's combined chosen set + the ORDINAL one-component
#: neighbours + the categorical flips: `FS.perturbation_trade_sets`, `FS.categorical_flip_sets`), MEASURED 2026-10-02 on the
#: real folds of two declared cells (docs/audits/2026-10-01-shard-calibration.md section 10; raw rows
#: docs/audits/2026-10-02-shard-recalibration-data/res-wave2.jsonl): 5m-metals (7 folds, XAUUSD + XPTUSD) and 1m-indices
#: (2 folds, US30). NEW value sets after de-duplication across folds are AFFINE in the fold count (the folds share chosen
#: values, so the union grows slower than linearly): ICT 69 at 7 folds / 29 at 2, Wyckoff 50 / 16 -> slope and intercept
#: below, times WAVE2_SAFETY_MARGIN (a layout ESTIMATE: the real list exists only once selection has run; the tripwire
#: `wave2_size_warning` fires beyond +10 %). 9 folds (1m-metals) is an EXTRAPOLATION beyond the measured 7.
WAVE2_SETS_PER_FOLD = {"ict": 8.0, "wyckoff": 6.8}
WAVE2_SETS_FIXED = {"ict": 13.0, "wyckoff": 2.4}           # the intercept of the affine fit (sets that no fold count scales)
WAVE2_SAFETY_MARGIN = 1.10                                # stated margin over the fit (the old model's 11.25 / 7.75 had none)
#: detection groups per wave-2 set and the W6 = 600 share: the WORST of the two measured cells (rounded up), pooled over the
#: folds taken alone (the way slices of consecutive sets meet them): ICT is capped at its 2 B-POOL groups however many sets.
WAVE2_GROUPS_PER_SET = {"ict": 1.0, "wyckoff": 0.52}      # 5m 38 groups / 74 sets (0.51), 1m 7 / 16 (0.44); pooled 0.50
WAVE2_W600_GROUP_SHARE = {"ict": 0.0, "wyckoff": 0.82}     # 5m 31 of 38 groups (0.82), 1m 2 of 7 (0.29); pooled 0.73


#: Bars one shard really scans for a cell with a DECLARED later start, measured with the harness's own `dev_start` cut
#: (BtEngine: series loaded from dev_start - warmup_days minus the method's own window, PIT-truncated at DEV_CUTOFF), per
#: (timeframe, symbol, dev_start): the larger of the ICT and Wyckoff counts (they differ by < 0.03 %). Raw rows:
#: docs/audits/2026-10-02-shard-recalibration-data/res-bars.jsonl (scripts/research/shard_calibration.py job `bars_span`).
#: Time-scaling DEV_BARS by the share of the span is WRONG for these cells: the 1m index series are sparse before late 2021
#: (US30: 1,418,201 measured vs 1,367,919 scaled; US500: 852,695 vs 552,680), so the layout would be too small. Counts only; sizing, never a result.
SPAN_BARS = {
    ("1m", "US500", "2020-03-01T00:00:00Z"): 852695, ("1m", "US30", "2020-03-01T00:00:00Z"): 1418201,
    ("1m", "USTEC", "2020-03-01T00:00:00Z"): 867342, ("1m", "DE40", "2020-03-01T00:00:00Z"): 747188,
    ("1m", "FRA40", "2020-03-01T00:00:00Z"): 801548,
    ("5m", "XAUUSD", "2015-01-07T00:00:00Z"): 645119, ("5m", "XAGUSD", "2015-01-07T00:00:00Z"): 644621,
    ("5m", "XPTUSD", "2015-01-07T00:00:00Z"): 494217, ("5m", "XPDUSD", "2015-01-07T00:00:00Z"): 480765}


def cell_bars(cell, sym):
    """Bars one shard of (`cell`, `sym`) scans (a sizing figure; it never changes a result). A cell that starts from data
    (dev_start_override null) is the audit's whole-development-span count (DEV_BARS). A cell with a DECLARED later start
    uses the MEASURED count of the cut series incl. its warm-up (SPAN_BARS, keyed by timeframe, symbol and the declared
    start); a declared start with no measured row falls back to DEV_BARS scaled by the share of the symbol's span it keeps
    (an ESTIMATE that ignores the warm-up and under-counts sparse early history: add the row instead)."""
    try:
        bars = DEV_BARS[cell["timeframe"]][sym]
    except KeyError:
        raise SystemExit(f"DEV_BARS has no row for {sym} {cell['timeframe']}: the shard layout needs that series' "
                         f"PIT-truncated development bar count (measure it: scripts/research/shard_calibration.py job "
                         f"'{{\"kind\":\"bars\",\"symbols\":[\"{sym}\"],\"tfs\":[\"{cell['timeframe']}\"]}}') and add it above")
    ov = cell.get("dev_start_override")
    if ov is None:
        return bars
    measured = SPAN_BARS.get((cell["timeframe"], sym, ov))
    if measured is not None:
        return measured
    end = FS.ts(FS.DEV_CUTOFF)
    first = FS.ts(cell["symbol_first_bar"][sym])
    return int(bars * ((end - max(FS.ts(ov), first)) / (end - first)))


def runner_workers(bars):
    """Effective scan workers on the assumed runner: its vCPUs, lowered by scan_many's own memory clamp."""
    m = SHARD_MODEL
    return max(1, min(m["runner_vcpu"], SM.clamp_workers(m["runner_vcpu"], bars, physical=m["runner_ram_bytes"])))


class _DataFreeEngine:
    """Holds nothing and reads no data: enough for `wave1_values` (it needs only `has` and the engine's `bt`)."""

    def __init__(self, bt):
        self.bt = bt

    def has(self, values):
        return False


def detection_group_keys(bt, method, tf, symbol, overlays):
    """The `scan_many` detection-group key of every overlay, computed with scan_many's OWN key functions
    (`ict_group_key`, `wy_group_key`) and no data: two value sets with the same key share ONE analysis pass, so a shard
    pays the group cost once for them and only `extra_set_s_per_bar` for each further set. ICT: the analyze()-reading
    keys (only B-POOL varies in the grid); Wyckoff: window x detection keys (W6, W4a, W-TW vary). Pinned equal to what
    scan_many really groups by a test on real scans."""
    keys = []
    for o in overlays:
        full = dict(bt._OPTS_BASE, **o)
        with SM._opts(bt, full):
            if method == "ict":
                x = bt._ict_ctx(symbol, tf, [], [], bt.P[tf]["H"], [], [], [], bt.resolve_methods(symbol), idx_of_time={})
                keys.append(SM.ict_group_key(bt, x))
            else:
                keys.append(SM.wy_group_key(bt, bt._wy_window(symbol, tf, 10 ** 9)))
    return keys


def wave1_group_info(grid, method, cell, symbol, bt=None):
    """[(group index, window or None)] per wave-1 value set, in the order `scan` slices them. Data-free: the wave-1 list
    is the harness's own `wave1_values` on an engine that holds nothing, the groups are `detection_group_keys`."""
    bt = bt or _load_bt()
    tf = cell["timeframe"]
    sets = wave1_values(_DataFreeEngine(bt), grid, cell)
    keys = detection_group_keys(bt, method, tf, symbol, [build_overlay(grid, v) for v in sets])
    order = list(dict.fromkeys(keys))
    return [(order.index(k), (k[0] if method == "wyckoff" else None)) for k in keys]


def _window_factor(method, tf, window, bt_window=300):
    """Cost of a group relative to a default-window group: only a non-default Wyckoff window (W6 = 600) costs more."""
    if method != "wyckoff" or window is None or window == bt_window:
        return 1.0
    return SHARD_MODEL["w600_group_factor"][tf]


def scan_seconds(method, tf, asset_class, bars, group_factors, n_sets):
    """Modelled seconds of ONE `scan_many` call on the REFERENCE machine (factor 1.0, one process): the per-call fixed
    term + bars x (sum of the groups' costs + the extra value sets inside those groups). `group_factors` = one window
    factor per detection group the call contains."""
    m = SHARD_MODEL
    per_bar = (m["group_s_per_bar"][method][tf][asset_class] * sum(group_factors)
               + max(n_sets - len(group_factors), 0) * m["extra_set_s_per_bar"][method][tf][asset_class])
    return m["call_fixed_s"][method][tf] + bars * per_bar


def _held_trades(method, tf, bars):
    return SHARD_MODEL["trades_per_bar"][method][tf] * bars


def fixed_seconds(wave, cell, method, symbol, n_wave1):
    """Per-shard compute that is not the scan itself (reference machine, factor 1.0). Every shard builds its engine
    (loads, indexes and hashes the candle series of every symbol the engine holds: ONE symbol in wave 1, ALL the cell's
    in wave 2). A wave-2 shard also verifies the cell's whole wave-1 cache, runs `trades_for` on every wave-1 set (the
    pooled selection needs their trades) and replays the nested walk-forward before it scans anything."""
    m = SHARD_MODEL
    tf = cell["timeframe"]
    if wave == 1:
        return m["engine_build_s_per_bar"] * cell_bars(cell, symbol)
    syms = cell["symbols"]
    build = sum(m["engine_build_s_per_bar"] * cell_bars(cell, s) for s in syms)
    trades = sum(_held_trades(method, tf, cell_bars(cell, s)) for s in syms)         # pooled trades of ONE value set
    cache = n_wave1 * (len(syms) * m["cache_entry_s"] + trades * m["cache_verify_s_per_trade"])
    post = n_wave1 * trades * m["trades_for_s_per_trade"]
    probe = cell["n_folds"] * m["select_s_per_fold"]
    return build + cache + post + probe


def shard_seconds(wave, cell, method, symbol, groups, n_sets, factor, n_wave1=0):
    """Modelled wall seconds of ONE shard on a runner `factor` x slower than the reference machine (`factor` scales the
    compute only; `job_fixed_s` -- checkout, setup, artifact transfer -- is an assumed constant). `groups` = the
    window factors of the shard's detection groups. With more than one effective worker (`runner_workers`) the call is
    cut into bar chunks (scan_many: ceil(2w / groups) per group), each a fresh process that reloads the series and, for
    Wyckoff, repeats the per-call set-up."""
    m = SHARD_MODEL
    tf, ac = cell["timeframe"], cell["asset_class"]
    bars = cell_bars(cell, symbol)
    cpu = scan_seconds(method, tf, ac, bars, groups, n_sets)
    w = runner_workers(bars)
    if w > 1:
        g = max(len(groups), 1)
        tasks = g * -(-2 * w // g)
        extra = (tasks - 1) * m["call_fixed_s"][method][tf] + tasks * m["task_overhead_s_per_bar"] * bars
        cpu = (cpu + extra) / (w * m["parallel_efficiency"][method][w])
    return factor * (cpu + fixed_seconds(wave, cell, method, symbol, n_wave1)) + m["job_fixed_s"]


def evaluate_seconds(cell, method, n_wave1, n_wave2, factor):
    """The per-(cell, method) evaluate step with a complete cache: no scan, but the engine build, the cache verification
    and `trades_for` of EVERY value set (wave 1 + wave 2) and the statistics (modelled as the wave-2 replay)."""
    m = SHARD_MODEL
    tf = cell["timeframe"]
    syms = cell["symbols"]
    build = sum(m["engine_build_s_per_bar"] * cell_bars(cell, s) for s in syms)
    trades = sum(_held_trades(method, tf, cell_bars(cell, s)) for s in syms)
    n = n_wave1 + n_wave2
    return factor * (build + n * (len(syms) * m["cache_entry_s"] + trades * (m["cache_verify_s_per_trade"]
                                                                       + m["trades_for_s_per_trade"]))
                     + cell["n_folds"] * m["select_s_per_fold"]) + m["job_fixed_s"]


def wave2_groups_in_slice(method, n_in_slice):
    """Distinct detection groups among `n_in_slice` CONSECUTIVE wave-2 sets: wave 2 is only known at run time, so this
    is the measured groups-per-set ratio (WAVE2_GROUPS_PER_SET), capped by what the method can have at all (ICT: 2)."""
    cap = SHARD_MODEL["max_groups"][method]
    want = -int(-(n_in_slice * WAVE2_GROUPS_PER_SET[method]) // 1)           # ceil
    return max(1, min(n_in_slice, cap, want))


def wave2_set_count(method, n_folds):
    """Wave-2 value sets of a cell: the measured affine fit (WAVE2_SETS_FIXED + WAVE2_SETS_PER_FOLD x the cell's folds) times
    WAVE2_SAFETY_MARGIN, rounded up (a layout ESTIMATE: the real list is only known once the selection has run)."""
    return -int(-(WAVE2_SAFETY_MARGIN * (WAVE2_SETS_FIXED[method] + WAVE2_SETS_PER_FOLD[method] * n_folds)) // 1)


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


def _slice_groups(method, wave, info, lo, hi, tf):
    """Window factors of the detection groups inside sets [lo, hi) of a wave."""
    if wave == 1:
        seen = {}
        for gid, win in info[lo:hi]:
            seen.setdefault(gid, win)
        return [_window_factor(method, tf, w) for w in seen.values()]
    g = wave2_groups_in_slice(method, hi - lo)
    share = WAVE2_W600_GROUP_SHARE[method]
    return [SHARD_MODEL["w600_group_factor"][tf] if (method == "wyckoff" and k < round(g * share)) else 1.0
            for k in range(g)]


def shard_plan(plan, grid_dir=None, factor=None):
    """The scan shards of the committed plan: one row per (cell, method, symbol, wave, slice). Wave 1 (baseline + every
    single-factor candidate) is symbol-local. Wave 2 (each fold's combined chosen set + every perturbation set) is
    discovered from the selection on the POOLED wave-1 trades of every symbol of the cell, so its shards run only after
    all of wave 1 exists; each still scans ONE symbol. The slice count of every (cell, method, symbol, wave) is the
    smallest one for which NO slice is modelled over `budget_s` at the LAYOUT factor (`layout_factor`, default the slow
    runner 2.0), from the plan, the grids and data availability only -- never from a result. A shard that is over the
    budget even at one value set (the irreducible unit) is flagged `over_cap`/`over_timeout`, not hidden. Each row also
    carries the modelled minutes at every reported factor (`est_min_by_factor`)."""
    m = SHARD_MODEL
    lay = m["layout_factor"] if factor is None else factor
    grids, _paths = load_grids(grid_dir)
    bt = _load_bt()
    rows = []
    for cell in plan["cells"]:
        tf = cell["timeframe"]
        for method in METHODS:
            g = grids[method].runnable()
            info = wave1_group_info(g, method, cell, cell["symbols"][0], bt)
            n1 = len(info)
            assert n1 == 1 + sum(len(x["candidates"]) for x in g.groups), "wave-1 list != baseline + candidates"
            n2 = wave2_set_count(method, cell["n_folds"])
            for wave, n in ((1, n1), (2, n2)):
                for sym in cell["symbols"]:
                    bars = cell_bars(cell, sym)

                    def secs(lo, hi, f):
                        return shard_seconds(wave, cell, method, sym, _slice_groups(method, wave, info, lo, hi, tf),
                                             hi - lo, f, n_wave1=n1)

                    slices = n
                    for s in range(1, n + 1):
                        if max(secs(*slice_bounds(n, i, s), lay) for i in range(s)) <= m["budget_s"]:
                            slices = s
                            break
                    for i in range(slices):
                        lo, hi = slice_bounds(n, i, slices)
                        est = secs(lo, hi, lay)
                        by = {f"{f:g}": round(secs(lo, hi, f) / 60) for f in m["report_factors"]}
                        rows.append({"cell": cell["id"], "method": method, "symbol": sym, "wave": wave,
                                     "slice": f"{i}/{slices}", "sets": hi - lo,
                                     "groups": len(_slice_groups(method, wave, info, lo, hi, tf)), "bars": bars,
                                     "est_min": round(est / 60), "est_min_by_factor": by,
                                     "over_cap": est > m["budget_s"],
                                     "over_timeout": est / 60 > m["job_timeout_min"],
                                     "name": f"{cell['id']}-{method}-{sym}-w{wave}-s{i}"})
    return rows


def flat_shard_row(row):
    """A shard row for the CI matrix (`include: ${{ fromJSON(...) }}`): scalars only, so no job reads a nested object.
    `est_min_by_factor` {"1": m, "2": m, "3": m} becomes `est_min_f1`, `est_min_f2`, `est_min_f3`."""
    out = {k: v for k, v in row.items() if k != "est_min_by_factor"}
    for f, minutes in row["est_min_by_factor"].items():
        out["est_min_f" + f.replace(".", "_")] = minutes
    return out


def format_shard_table(rows):
    """Per (cell, method, symbol, wave): slices, sets, the longest modelled shard (at the layout factor), and whether any
    shard is over the cap / the job timeout."""
    groups = {}
    for r in rows:
        groups.setdefault((r["cell"], r["method"], r["symbol"], r["wave"]), []).append(r)
    cap = SHARD_MODEL["budget_s"] // 60
    L = [f"{'cell':<12}{'method':<8}{'symbol':<8}{'wave':<5}{'slices':>6}{'sets':>6}{'groups':>7}{'longest shard':>15}"
         f"  over {cap} min?"]
    for (c, m, s, w), rs in groups.items():
        longest = max(r["est_min"] for r in rs)
        L.append(f"{c:<12}{m:<8}{s:<8}{w:<5}{len(rs):>6}{sum(r['sets'] for r in rs):>6}{sum(r['groups'] for r in rs):>7}"
                 f"{longest:>11} min   {'YES' if any(r['over_cap'] for r in rs) else 'no'}")
    L.append(f"total shards: {len(rows)}; modelled runner minutes at factor {SHARD_MODEL['layout_factor']:g}: "
             f"{sum(r['est_min'] for r in rows)}")
    L.append("model constants: " + SHARD_MODEL_LABEL)
    return "\n".join(L)


def shard_summary(plan, rows, grid_dir=None):
    """Totals at every reported runner factor: shards, runner-hours, longest shard, critical path and the per
    (cell, method) breakdown. Critical path = plan + longest wave-1 shard + longest wave-2 shard + longest evaluate
    (the workflow's `needs` are per JOB, so every cell waits for the slowest cell of the previous stage), assuming
    unlimited concurrent runners (hosted-runner concurrency limits are NOT verified)."""
    m = SHARD_MODEL
    grids, _paths = load_grids(grid_dir)
    bt = _load_bt()
    cells = {c["id"]: c for c in plan["cells"]}
    out = {}
    for f in m["report_factors"]:
        key = f"{f:g}"
        tot = sum(r["est_min_by_factor"][key] for r in rows)
        w1 = max((r["est_min_by_factor"][key] for r in rows if r["wave"] == 1), default=0)
        w2 = max((r["est_min_by_factor"][key] for r in rows if r["wave"] == 2), default=0)
        ev, per = 0, {}
        for cid, cell in cells.items():
            for method in METHODS:
                n1 = len(wave1_group_info(grids[method].runnable(), method, cell, cell["symbols"][0], bt))
                n2 = wave2_set_count(method, cell["n_folds"])
                e = round(evaluate_seconds(cell, method, n1, n2, f) / 60)
                ev = max(ev, e)
                rs = [r for r in rows if r["cell"] == cid and r["method"] == method]
                per[f"{cid}/{method}"] = {"shards": len(rs), "runner_hours": round(sum(r["est_min_by_factor"][key] for r in rs) / 60, 1),
                                          "longest_min": max(r["est_min_by_factor"][key] for r in rs), "evaluate_min": e}
        out[key] = {"shards": len(rows), "runner_hours": round(tot / 60, 1), "longest_shard_min": max(
            r["est_min_by_factor"][key] for r in rows), "critical_path_min": m["plan_job_min"] + w1 + w2 + ev,
                    "longest_wave1_min": w1, "longest_wave2_min": w2, "longest_evaluate_min": ev, "by_cell_method": per}
    return out


def format_shard_summary(summary):
    L = ["factor  shards  runner-h  longest shard  critical path (plan + w1 + w2 + evaluate)"]
    for k, v in summary.items():
        L.append(f"{k:>6}{v['shards']:>8}{v['runner_hours']:>10}{v['longest_shard_min']:>10} min{v['critical_path_min']:>12} min "
                 f"({v['longest_wave1_min']} + {v['longest_wave2_min']} + {v['longest_evaluate_min']})")
    return "\n".join(L)


def wave2_size_warning(cell_id, method, symbol, n_slices, real, est):
    """The wave-2 tripwire: None, or the WARNING text when the real wave-2 list (`real` value sets) is more than 10 % longer
    than the layout's estimate `est` (`wave2_set_count`), with the slice count N that restores the layout's per-slice size."""
    if real <= 1.1 * est:
        return None
    need = -(-n_slices * real // est)
    return (f"WARNING: wave 2 of {cell_id}/{method} has {real} value sets, {100 * (real / est - 1):.0f} % more than the "
            f"{est} the shard layout assumed (WAVE2_SETS_FIXED / WAVE2_SETS_PER_FOLD); this slice may run longer than modelled. Re-run EVERY "
            f"wave-2 slice of {cell_id}/{method}/{symbol} with --slice I/{need} (I = 0..{need - 1}) if the time limit is at "
            f"risk; entries are keyed per value set, so any N gives the same cache.")


def cmd_scan(cell_id, symbol, method, out_dir, workers=1, wave=1, slice_spec="0/1", scan_cache_dirs=(), grid_dir=None,
             allow_dirty=False):
    """One Actions scan shard. `--wave 1`: the wave-1 value sets (the same list `run` would prefetch first) for ONE
    symbol -- needs no other symbol's data. `--wave 2`: the wave-2 sets, which only exist once selection has run on the
    pooled wave-1 trades of ALL the cell's symbols, so it needs the complete wave-1 cache (`--scan-cache`) and REFUSES
    without it; it still scans ONE symbol. `--slice I/N` takes the I-th of N contiguous parts of the list. The slice's
    value sets are scanned in ONE `scan_many` call (the analysis of a detection group is shared between them, so scanning
    them one by one would multiply the cost) and each result is then written as a verified cache entry under `out_dir`
    (atomic, outside the checkout, CLAUDE.md section 46): a shard killed at the job timeout therefore keeps NOTHING of
    its slice (the slice sizing is what bounds the loss; entries already present in `out_dir` are verified and skipped on
    a local re-run). Wave 2: if the real list is more than 10 % longer than the layout's estimate (`wave2_set_count`) a
    WARNING with the `--slice I/N` to re-run with is printed to stderr. Like `run`, refuses without the ledger declaration and on code drift."""
    real_out, real_root = os.path.realpath(out_dir), os.path.realpath(ROOT)
    if real_out == real_root or real_out.startswith(real_root + os.sep):
        raise SystemExit(f"--out {out_dir} is inside the checkout: outputs must land outside it (a file written in the "
                         f"work tree makes the run's own code_version read dirty=true, CLAUDE.md section 46)")
    i, n = parse_slice(slice_spec)
    if wave not in (1, 2):
        raise SystemExit("--wave must be 1 or 2")
    check_clean_tree(allow_dirty)       # the dirty list is also part of the cache stamp, so a dirty cache is never reused
    plan = load_plan(grid_dir)
    decl = require_declaration(plan)
    check_drift(decl, plan, False)
    cell = next((c for c in plan["cells"] if c["id"] == cell_id), None)
    if cell is None:
        raise SystemExit(f"no cell {cell_id!r}; cells: {[c['id'] for c in plan['cells']]}")
    if symbol not in cell["symbols"]:
        raise SystemExit(f"{symbol!r} is not a symbol of cell {cell_id!r} ({cell['symbols']}): no symbol may be added "
                         f"or dropped after the plan (plan section 1.7)")
    cand = next((c for c in plan["candidates"] if c["cell"] == cell_id and c["method"] == method), None)
    if cand is None:
        raise SystemExit(f"the plan has no candidate for cell {cell_id!r} method {method!r}; candidates: "
                         f"{[c['id'] for c in plan['candidates']]}")
    grids, _paths = load_grids(grid_dir)
    for g in grids.values():
        assert_grid_runnable(g)
    grid = grids[method].runnable()
    stamp = scan_cache_stamp(plan)
    engine = BtEngine(grid, cand["runner_method"], cell["timeframe"], [symbol] if wave == 1 else cell["symbols"],
                      workers=workers, **span_args(plan, cell))
    if wave == 1:
        values = wave1_values(engine, grid, cell)
    else:
        if not scan_cache_dirs:
            raise SystemExit("--wave 2 needs --scan-cache: the wave-2 value sets are chosen from the pooled wave-1 "
                             "trades of every symbol of the cell")
        # the wave-2 list must not depend on which wave-2 entries a directory happens to hold (a shard rerun, a merged
        # directory): only the wave-1 sets are loaded, so every shard derives the SAME list and its slice is stable
        w1_keys = [FS.CountingSource._key(v) for v in wave1_values(engine, grid, cell)]     # engine holds nothing yet
        engine.load_scan_cache(stamp, scan_cache_dirs, cell_id, only_keys=set(w1_keys))
        # completeness is judged against the wave-1 KEY LIST, not by re-running the selection: with real trades held, a
        # fold's combined set (>= 2 changed factors) is legitimately not a wave-1 set and would look "missing"
        missing = [k for k in w1_keys if k not in engine._raw and k not in engine._done]
        if missing:
            raise SystemExit(f"--wave 2 refused: the wave-1 cache of {cell_id}/{method} is incomplete for "
                             f"{len(missing)} of {len(w1_keys)} value set(s) of {cell['symbols']}; wave-2 sets would be "
                             f"chosen from an incomplete pool. Re-run the missing wave-1 shards.")
        values = wave2_values(engine, grid, cell)
        warn = wave2_size_warning(cell_id, method, symbol, n, len(values), wave2_set_count(method, cell["n_folds"]))
        if warn:
            print(warn, file=sys.stderr, flush=True)
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


def build_id():
    """Which build the report runs under: the git sha of HEAD and whether the pinned tree is dirty (None = git unavailable)."""
    sha = _git("rev-parse", "HEAD")
    dirty = scoped_dirty()
    return {"git_sha": sha, "scoped_dirty": bool(dirty) if dirty is not None else None}


def report_holm_lines(planned, verdicts, holm, fam, holm_only, pass_not_holm):
    """The Holm table over the whole family (one row per PLANNED candidate; NOT RUN and insufficient ones enter with p = 1)."""
    L = [f"## Holm step-down over the family of {fam['size']} (FWER {fam['alpha']})", "",
         f"Candidates are ranked by their primary p (`p_robust` = the MAX of the five one-sided p-values, i.e. a candidate is "
         f"significant at level a only if all five bounds are above 0 at 1 - a). Rank k is rejected iff p <= "
         f"{fam['alpha']}/({fam['size']} - k + 1) and every smaller p was rejected. NOT RUN, insufficient and not-computable "
         f"candidates enter with p = 1 and still count in the family. The floor confidence {fam['floor_confidence']:.5f} is "
         f"Holm's strictest step (rank 1).", "",
         "| rank | candidate | verdict | p_robust | Holm threshold | Holm decision |", "|---|---|---|---|---|---|"]
    for row in sorted(holm.values(), key=lambda r: r["rank"]):
        cid = row["id"]
        v = verdicts.get(cid, "NOT RUN")
        p = row["p"]
        L.append(f"| {row['rank']} | {cid} | {v} | {_fmt(p, '.5f') if p is not None else 'n/a (counts as 1)'} | "
                 f"{row['threshold']:.5f} | {'rejected' if row['reject'] else 'not rejected'} |")
    L += ["", "How Holm and the floor relate (stated, not hidden): rank 1's Holm threshold equals the floor, and every later "
          "rank's threshold is LOOSER. A candidate whose primary bound is above 0 at the floor confidence is therefore always "
          "Holm-rejected; but Holm can also reject a rank-k candidate that FAILS the floor when a smaller p was rejected "
          "before it. This harness does not turn that into a PASS: the verdict is the conjunction of every check, the floor "
          "test among them, and Holm only confirms it. A candidate that fails the floor is never reported as a pass, "
          "whatever Holm says about it.", ""]
    if holm_only:
        L += [f"**Holm would reject, but the floor fails (NOT a pass):** {holm_only}", ""]
    if pass_not_holm:
        L += [f"**Anomaly: floor PASS not confirmed by Holm (numerical edge; NOT counted as a pass):** {pass_not_holm}", ""]
    return L


def report_candidate_lines(ev):
    """Section C items 1-5 for one candidate, from the stored record only (nothing is recomputed from data)."""
    L = []
    pr = ev.get("primary") or {}
    comps = pr.get("components") or {}
    if comps:
        L.append(f"Primary bound (floor confidence {pr['confidence']:.5f}; pre-registration A2): mean {_fmt(pr.get('mean'))}, "
                 f"primary bound (min of five) {_fmt(pr.get('primary_bound'))}, p_robust (max of five) "
                 f"{_fmt(pr.get('p_robust'), '.5f') if pr.get('p_robust') is not None else 'n/a'}.")
        L.append("")
        L.append("| bound | value | se | df / blocks | one-sided p |")
        L.append("|---|---|---|---|---|")
        for k in FS.PRIMARY_COMPONENTS:
            c = comps[k]
            pv = (pr.get("p_values") or {}).get(k)
            L.append(f"| {k} | {_fmt(c.get('value'))} | {_fmt(c.get('se'), '.4f')} | {c.get('df', 'n/a')} / "
                     f"{c.get('blocks', 'n/a')} | {_fmt(pv, '.5f')} |")
        h = pr.get("binding_half_year")
        if h:
            L.append(f"Minimum detectable edge (binding half-year CR1 bound: se {h['se']:.4f}, df {h['df']}): "
                     f"(t_crit {h['t_crit']:.3f} + t_0.80 {h['t_power']:.3f}) x se = **{h['mde']:+.3f} R per trade** -- the true mean "
                     f"at which that bound clears 0 with probability {h['power']:.2f}. Upper confidence bound on the edge "
                     f"(one-sided, {h['confidence']:.5f}, same blocks): **{h['upper']:+.3f} R** (lower {h['lower']:+.3f}).")
        else:
            L.append("Minimum detectable edge and upper bound: not computable (the half-year CR1 bound has no standard error).")
        o = pr.get("smallest_bound_interval")
        if o:
            L.append(f"The numerically smallest bound is `{o['component']}` (se {o['se']:.4f}, df {o['df']}): its minimum "
                     f"detectable edge is {o['mde']:+.3f} R, upper bound {o['upper']:+.3f} R.")
    mg = ev.get("margins") or []
    if mg:
        L.append("")
        L.append("Every check, with its margin (a negative margin is the distance by which it fails):")
        L.append("")
        L.append("| check | measure | measured | threshold | margin | unit | ok |")
        L.append("|---|---|---|---|---|---|---|")
        for m in mg:
            L.append(f"| {m['check']} | {m['measure']} | {_fmt(m['measured'], '.4g')} | {_fmt(m['threshold'], '.4g')} | "
                     f"{_fmt(m['margin'], '+.4g')} | {m['unit']} | {'yes' if m['ok'] else 'NO'} |")
    fc = ev.get("fold_cost_report") or []
    if fc:
        L.append("")
        L.append("Fold by fold (chosen values; test trades): trades, mean net R, mean spread_R (the spread cost in R).")
        L.append("")
        L.append("| test fold start | trades | mean net R | mean spread_R |")
        L.append("|---|---|---|---|")
        for f in fc:
            L.append(f"| {f['test_start'][:10]} | {f['n_trades']} | {_fmt(f['mean_net_R'])} | {_fmt(f['mean_spread_R'], '.4f')} |")
    cs = ev.get("component_stability") or {}
    if cs:
        L.append("")
        L.append("Stability of the chosen values per perturbation component (changes between consecutive folds): "
                 + ", ".join(f"{k} {v['changes']}/{v['transitions']}" for k, v in sorted(cs.items())) + ".")
    pt = ev["checks"].get("perturbation") or {}
    if pt.get("rows"):
        L.append("")
        L.append(f"Ordinal perturbation (gated; neighbour needs pooled mean > 0 AND primary bound > 0 at "
                 f"{pt.get('confidence', 0):.5f}):")
        L.append("")
        L.append("| item.component | direction | folds | trades | pooled mean net R | bound | ok |")
        L.append("|---|---|---|---|---|---|---|")
        for r in pt["rows"]:
            L.append(f"| {r['item']}.{r.get('component')} | {r['direction']:+d} | {r.get('folds')} | {r['n']} | "
                     f"{_fmt(r.get('mean_R'))} | {_fmt(r['lower_bound'])} | {'yes' if r['ok'] else 'NO'} |")
    if pt.get("skipped_folds"):
        L.append("Not perturbed (the chosen value is not on the component's ordinal order, e.g. the v1-typed W4a baseline): "
                 + "; ".join(f"{s['item']}.{s['component']} in fold {s['test_start'][:10]} (chose {s['chosen']!r})"
                             for s in pt["skipped_folds"]) + ".")
    cat = ev.get("categorical_flips") or []
    if cat:
        L.append("")
        L.append("Categorical flips (REPORTED, never gated): value A -> value B, pooled test trades of the folds that chose A.")
        L.append("")
        L.append("| item | A -> B | folds | trades | pooled mean net R | bound |")
        L.append("|---|---|---|---|---|---|")
        for f in cat:
            L.append(f"| {f['item']} | {f['from']!r} -> {f['to']!r} | {f['folds']} | {f['n']} | {_fmt(f['mean_R'])} | "
                     f"{_fmt(f['lower_bound'])} |")
    st = ev["checks"].get("stress") or {}
    if st.get("n"):
        L.append("")
        L.append(f"Stress gate (the same {st['n']} admitted trades re-priced with the p90 spread on both legs and the "
                 f"{st['commission_fraction'] * 100:.3f} % commission stress margin, a margin NOT an estimate): pooled mean net R "
                 f"{_fmt(st['mean_R_stressed'])} (gate: > 0); stressed primary bound {_fmt(st['stressed_primary_bound'])} "
                 f"(reported, not gated).")
    sh = ev["checks"].get("prop_pass_shifted") or {}
    if sh.get("shift_R") is not None:
        pps = sh.get("funds") or {}
        L.append(f"prop_pass_probability with R shifted down by {sh['shift_R']:.4f} R (mean - primary bound): "
                 + "; ".join(f"{f} {row['status']}" + (f" ({_fmt(row['value'], '.2f')})" if row.get("value") is not None else "")
                             for f, row in pps.items()) + ".")
    md = ev["checks"].get("min_trading_days") or {}
    if md:
        L.append("Minimum trading days (distinct UTC entry days per test fold; funds checked: "
                 + (", ".join(f"{f} >= {row['required']}" for f, row in (md.get("funds") or {}).items() if row.get("checked"))
                    or "none") + "): per fold " + str([x["entry_days"] for x in md.get("folds", [])])
                 + f", margin {_fmt(md.get('margin'), '.0f')} day(s)" + (f" -- {md['reason']}" if md.get("reason") else "") + ".")
    return L


def report_statement_lines(plan, recs):
    """Section C items 6-9: placebo, overlap, scope, window statements and the build."""
    b = build_id()
    cell_ids = [c["id"] for c in plan["cells"]]
    both = "1m-metals" in cell_ids and "5m-metals" in cell_ids
    removed = [r["id"] for r in plan["cells_file"].get("removed_cells", [])]
    L = ["## Statements (section C of the pre-registration)", "",
         f"- **Build:** git `{(b['git_sha'] or 'unavailable')[:12]}`, pinned tree dirty = {b['scoped_dirty']}. This build implements "
         f"family A (six candidates, Holm at report time), the ordinal perturbation, the D1-ADX regime split, the stress gate, "
         f"the shifted prop pass and section C items 1-5, 7-9.",
         "- **placebo: NOT IMPLEMENTED in this build.** Section C item 6 (a random-entry benchmark per test trade: same symbol, "
         "same UTC hour, same fold, side 50/50, same stop distance and R_planned, run through the same walk, costs and "
         "fills, with a pinned seed) is a DEFINITION only; no placebo figure exists and no verdict reads one."]
    if both:
        shared = sorted(set(next(c for c in plan["cells"] if c["id"] == "1m-metals")["symbols"])
                        & set(next(c for c in plan["cells"] if c["id"] == "5m-metals")["symbols"]))
        spans = {c["id"]: c["development_start"] for c in plan["cells"] if c["id"] in ("1m-metals", "5m-metals")}
        L.append(f"- **Overlap:** `1m-metals` and `5m-metals` share {shared} over the same calendar span up to "
                 f"{plan['dev_cutoff']} (development starts {spans}); a pass in both is NOT independent evidence.")
    L += [f"- **Scope:** zero passes say nothing about the cells removed from the plan ({', '.join(removed) or 'none'}), about "
          f"other timeframes, symbols or methods, or about the live configuration; a pass says something only about its own "
          f"cell, method and the searched specification (deployment rule, item 11).",
          f"- **Window:** the development window (before {plan['dev_cutoff']}) is NOT a pristine holdout; a PASS here is a "
          f"NOMINATION for a separately pre-registered forward demo, not out-of-sample validation. Prior outcome reads on this "
          f"window (`prior_counts_disclosed`): {plan['prior_counts_disclosed']}; the full list is in section 0.1 of "
          f"docs/plans/2026-09-29-fund-search-preregistration-DRAFT.md.", ""]
    return L


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
    # Family A: Holm over the candidate procedures. NOT RUN and insufficient candidates enter with p = 1 (they still count in the
    # family); a record without a computable p enters with p = 1 as well.
    fam = plan["family"]
    holm_p = {}
    for c in planned:
        r = by_id.get(c["id"])
        p = ((r["metrics"]["evaluation"].get("primary") or {}).get("p_robust") if r is not None else None)
        holm_p[c["id"]] = None if (r is None or verdicts[c["id"]] == FS.INSUFFICIENT) else p
    holm = {row["id"]: row for row in FS.holm_stepdown(holm_p, fam["size"], fam["alpha"])}
    # a PASS needs the floor verdict (every check, the primary bound at the floor confidence among them) AND Holm's rejection.
    # A floor PASS is always Holm-rejected (its p is under every Holm threshold), so Holm can only ever confirm here.
    passes = [cid for cid, v in verdicts.items() if v == FS.PASS and holm[cid]["reject"]]
    holm_only = [cid for cid, v in verdicts.items() if v != FS.PASS and holm[cid]["reject"]
                 and (by_id[cid]["metrics"]["evaluation"]["checks"]["lower_bound_positive"]["ok"] is False)]
    pass_not_holm = [cid for cid, v in verdicts.items() if v == FS.PASS and not holm[cid]["reject"]]
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
         f"- Multiple-testing family (family A): the **{fam['size']} candidate procedures** (cells x methods), floor confidence "
         f"1 - {fam['alpha']}/{fam['size']} = **{fam['floor_confidence']:.5f}** for every candidate; Holm step-down at FWER "
         f"{fam['alpha']} over the {fam['size']} below (NOT RUN candidates count in the family). Grid values are not "
         f"hypotheses of the family (the nested walk-forward handles value selection); their number is disclosed: "
         + ", ".join(f"{m} {plan['grids'][m]['n_per_cell']} per cell" for m in plan["grids"]) + ".",
         f"- Prior searches on the same history, disclosed and NOT folded into the family: {plan['prior_counts_disclosed']}.",
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
          "below). Deployment rule (pre-registration item 11, replaced 2026-10-02; the earlier 'values of the FINAL fold' "
          "proposal is WITHDRAWN): the SAME selection rule is re-run once on the training data through "
          f"{plan['dev_cutoff'][:10]} and yields one configuration per passing candidate; if several pass, the one with the "
          "highest primary bound at the floor confidence is listed first and EVERY pass goes to a separately "
          "pre-registered forward demo. The deployable specification differs from the searched one (adopted F keys ON in "
          "the search, O1 admission, gap-fill and relative spread, the zero-risk refusal, NO news filter in the search); a "
          "PASS is evidence about the SEARCHED specification.", "",
          f"Regime split, as pre-registered: {FS.REGIME_SPLIT_DEFINITION}.", ""]
    L += ["## Every evaluated candidate", "",
          "| candidate | verdict | test trades | pooled mean net R | primary bound (conf) | p_robust | failed checks |",
          "|---|---|---|---|---|---|---|"]
    for r in recs:
        ev = r["metrics"]["evaluation"]
        lb = ev["checks"]["lower_bound_positive"]["bound"]
        pr = (ev.get("primary") or {}).get("p_robust")
        L.append(f"| {r['experiment_id']} | {verdicts[r['experiment_id']]} | {ev['pooled']['n_trades']} | "
                 f"{_fmt(ev['pooled']['mean_R'])} | {_fmt(lb['value'])} ({lb['confidence']:.5f}) | "
                 f"{_fmt(pr, '.5f') if pr is not None else 'n/a'} | {', '.join(ev['failed_checks']) or '-'} |")
    L += [""] + report_holm_lines(planned, verdicts, holm, fam, holm_only, pass_not_holm)
    L += report_statement_lines(plan, recs)
    L += ["## Per symbol (pooled test trades) and per volume_kind", ""]
    for r in recs:
        ev = r["metrics"]["evaluation"]
        L.append(f"### {r['experiment_id']}")
        L += report_candidate_lines(ev)
        L.append("")
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
            L.append(f"planned-risk admission (item 12; chosen values, per test fold): refused as zero_risk "
                     f"{[f.get('refused_zero_risk', 'n/a') for f in byf]} of candidates {[f['candidates'] for f in byf]} "
                     f"(zero / wrong-side / below one tick / non-finite stop distance: no position size exists).")
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
          "- FTMO commission is UNKNOWN; net R is net of the recorded spread and swap only. The stress gate charges a 0.003 % "
          "of notional commission MARGIN per round turn (a stress margin, NOT an estimate).",
          "- Wyckoff on CFD uses TICK volume (see the per-volume_kind rows).",
          "- The primary bound is the MINIMUM of an iid Student-t bound and four cluster-robust (CR1) bounds (by UTC "
          "entry date, by 30-day window, by calendar quarter and by half-year). It is not backed by the "
          "single-trade cap or the perturbation check: those are separate gates, each required on its own. "
          "DISCLOSED PRICE: the quarter and half-year bounds cost power -- measured on 20 seeds of iid +0.30R at "
          "n=600, the bound passed 20/20 over 6 years, 17/20 over 4 years and 9/20 over 2 years; persistent-regime "
          "edges fare worse. This is accepted as the tightening the owner chose.",
          "- The min_rr admission uses only entry-knowable costs (O1, `fx_admission_entry_cost`, fixed ON); the reported net R "
          "keeps the real entry+exit cost. Refusal counts and near-floor margins are in the per-candidate admission lines.",
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
    pp.add_argument("--check-data", action="store_true",
                    help="print the per-cell readiness table (history + real-cost specs) and exit 1 if anything is "
                         "missing, 0 if complete; plans nothing, writes nothing")
    pp.add_argument("--grid-dir", help="directory holding v-grid-ict.json / v-grid-wyckoff.json")
    dp = sub.add_parser("declare", help="record the final cell count in the research ledger (before any run)")
    dp.add_argument("--allow-dirty", action="store_true", help=_ALLOW_DIRTY_HELP)
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
    sp.add_argument("--allow-dirty", action="store_true", help=_ALLOW_DIRTY_HELP)
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
    rp.add_argument("--require-complete-scan-cache", action="store_true",
                    help="with --scan-cache: fail loud (ScanCacheRefused) if any scan would have to run on demand")
    rp.add_argument("--allow-drift", action="store_true",
                    help="proceed although the code/settings differ from the declaration; every record is "
                         "stamped drifted=true and the report says so")
    rp.add_argument("--allow-dirty", action="store_true", help=_ALLOW_DIRTY_HELP)
    sub.add_parser("report", help="write the markdown report over every record")
    a = ap.parse_args(argv)
    os.environ.setdefault("BT_HISTORY_ROOT", FTMO_HISTORY_ROOT)     # the fund search reads the FTMO feed (§6 item 8)
    if a.cmd == "plan":
        if a.check_data:
            return check_data(a.grid_dir)
        cmd_plan(dry_run=a.dry_run, grid_dir=a.grid_dir)
    elif a.cmd == "declare":
        cmd_declare(allow_dirty=a.allow_dirty)
    elif a.cmd == "list-cells":
        print(json.dumps([{"cell": c["id"]} for c in load_plan()["cells"]]))
    elif a.cmd == "list-scan-shards":
        rows = shard_plan(load_plan())
        if a.wave:
            rows = [r for r in rows if r["wave"] == a.wave]
        if a.explain:
            print(format_shard_table(rows))
        else:
            print(json.dumps([flat_shard_row(r) for r in rows]))
    elif a.cmd == "scan":
        cmd_scan(a.cell, a.symbol, a.method, a.out, workers=a.workers if a.workers is not None else SM.default_workers(),
                 wave=a.wave, slice_spec=a.slice, scan_cache_dirs=a.scan_cache, grid_dir=a.grid_dir,
                 allow_dirty=a.allow_dirty)
    elif a.cmd == "run":
        cmd_run(a.cell, method=a.method, workers=a.workers if a.workers is not None else SM.default_workers(),
                grid_dir=a.grid_dir, allow_drift=a.allow_drift, scan_cache_dirs=a.scan_cache,
                require_complete_scan_cache=a.require_complete_scan_cache, allow_dirty=a.allow_dirty)
    elif a.cmd == "report":
        cmd_report()


if __name__ == "__main__":
    sys.exit(main())
