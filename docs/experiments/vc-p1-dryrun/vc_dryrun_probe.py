"""Outcome-blindness probe for `scripts/research/edge_vc.py dry-run` (VC-P1 §7, sealing step 3).

    python3 -W ignore vc_dryrun_probe.py <dry-run out json> <trace out json> [<repo root>]

The repository root defaults to the nearest parent of this file that holds scripts/research/edge_vc.py (this file is
committed beside the dry-run JSON, docs/experiments/vc-p1-dryrun/), else the current directory.

Before edge_vc is loaded, two tracers are installed in this fresh interpreter:
1. sys.monitoring PY_START: every code object of a repository file that STARTS (first start recorded, then the event is
   disabled for that object: near-zero overhead);
2. an audit hook on "open": every repository file the process opens.
Then the CLI itself runs (`runpy.run_path(edge_vc.py, run_name="__main__")` with argv `dry-run --out <json>`).

ALLOWLIST (fix round 3, 2026-10-04: the earlier version was a list of forbidden names, some of which did not exist):
a code object may start only if its file is listed in ALLOWED_CODE and its qualified name is listed there (a trailing ".*"
allows a class's members; a nested function, lambda or comprehension is covered by its enclosing allowed function; a
module-level <genexpr> / <lambda> by its file). Everything that walks an exit, prices a cost or computes an R lives under a
name that is NOT in the list (book_sim.trades, fvg_forward.resolve_row, edge_census.Costs / outcome / t_sf, the real_costs
pricing functions, edge_vc.pit_trade / split_test / per_bar / diagnostics ...), so any call to one is a VIOLATION, and so is
any function nobody listed. Opened files: only the allowed configuration files and the 5m XAUUSD / XAGUSD history; no cost
table, no 15m history, no live or paper-log file, and every Python file opened is in edge_vc.CODE.
The probe FAILS (exit 3) on a violation. The trace JSON lists every code object that started and every file opened, so a
reviewer can check the list by inspection."""
import datetime
import hashlib
import json
import os
import runpy
import sys
import time

OUT, TRACE = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])


def _find_root():
    if len(sys.argv) > 3:
        return os.path.abspath(sys.argv[3])
    d = os.path.dirname(os.path.abspath(__file__))
    while d != os.path.dirname(d):
        if os.path.exists(os.path.join(d, "scripts", "research", "edge_vc.py")):
            return d
        d = os.path.dirname(d)
    return os.getcwd()


ROOT = _find_root()

ALLOWED_CODE = {
    "scripts/history_store.py": {"<module>", "_file_sha256", "_read_split", "_split_identity", "digest", "read_at",
                                 "read_doc", "resolve"},
    "scripts/instruments.py": {"<module>", "_load", "_read", "market_types"},
    "scripts/mt5_time.py": {"<module>", "Refused", "UsDatesFixedOffsetZone.*", "UsDatesFixedOffsetZone", "_convention_zone",
                            "server_zone"},
    "scripts/providers.py": {"<module>", "_load", "_validate", "provider"},
    "scripts/real_costs.py": {"<module>", "CostRefused", "server_zone"},
    "scripts/research/book_sim.py": {"<module>", "_load"},
    "scripts/research/fvg_book_sim.py": {"<module>"},
    "scripts/research/pit_trend.py": {"<module>", "Bars", "SpecCost"},
    "scripts/research/prereg_guard.py": {"<module>", "Refused", "_git", "dataset_snapshot", "file_sha256", "git_head",
                                         "read_name", "refuse_overwrite"},
    # the detectors and the data model (edge_census.Costs is a class BODY only: no member may start)
    "scripts/research/edge_census.py": {"<module>", "Costs", "Series", "Series.*", "_ev", "_first_per_day", "ev_prev_day",
                                        "load", "prev_day_levels"},
    "scripts/research/edge_f3.py": {"<module>", "daily", "ev_breakout_trend"},
    "scripts/research/edge_f4.py": {"<module>", "_days", "_first_close_beyond", "_load", "ev_vol_breakout"},
    # the paper log's data-quality helpers only (paper_log_refusals): never resolve_row, signals, scan, accumulate, ...
    "scripts/research/fvg_forward.py": {"<module>", "holes", "_dt", "_vol_fresh"},
    "scripts/research/edge_vc.py": {"<module>", "_cells", "_dump", "_ec", "_ff", "_in_half", "_load", "_meta", "_nb_split",
                                    "_pit_series", "_quantiles", "_rel", "_t_crit", "_uncommitted", "_xau_series",
                                    "bars_to_day_end", "causal_density", "dry_counts", "main", "paper_log_refusals",
                                    "pit_events", "pit_vr_by_day", "power_inputs", "regime_blocks", "research_events",
                                    "rule_power", "rule_power_table", "server_zone", "slot_of", "vr_runs"},
}
GENERIC = ("<genexpr>", "<lambda>", "<listcomp>", "<dictcomp>", "<setcomp>")
ALLOWED_FILES = {"docs/architecture/instruments.json", "docs/architecture/providers.json"}
ALLOWED_PREFIXES = ("data/history/ftmo/ohlcv.XAUUSD.5m/", "data/history/ftmo/ohlcv.XAGUSD.5m/")

seen, opened = {}, set()


def _rel(p):
    return os.path.relpath(p, ROOT).replace(os.sep, "/")


def _audit(event, args):
    if event != "open" or not args or not isinstance(args[0], (str, os.PathLike)):
        return
    p = os.path.abspath(os.fspath(args[0]))
    if isinstance(p, str) and p.startswith(ROOT + os.sep):
        opened.add(_rel(p))


sys.addaudithook(_audit)
MON = sys.monitoring
TOOL = next(t for t in (3, 4, 1, 2) if MON.get_tool(t) is None)
MON.use_tool_id(TOOL, "vc-dryrun-probe")
CO_NEWLOCALS = 0x2          # set on function code objects; a class body or a module has no new locals


def _start(code, _offset):
    f = code.co_filename
    if f.startswith(ROOT + os.sep):
        kind = "function" if code.co_flags & CO_NEWLOCALS else ("module" if code.co_name == "<module>" else "class body")
        seen.setdefault((_rel(f), code.co_qualname), (code.co_firstlineno, kind))
    return MON.DISABLE


MON.register_callback(TOOL, MON.events.PY_START, _start)
MON.set_events(TOOL, MON.events.PY_START)

t0 = time.time()
sys.argv = ["scripts/research/edge_vc.py", "dry-run", "--out", OUT]
g = runpy.run_path(os.path.join(ROOT, "scripts/research/edge_vc.py"), run_name="__main__")
wall = time.time() - t0
MON.set_events(TOOL, 0)
MON.free_tool_id(TOOL)


def allowed(f, q):
    names = ALLOWED_CODE.get(f)
    if names is None:
        return False
    root = q.split(".<locals>")[0]
    if root in names or root in GENERIC:
        return True
    return any(n.endswith(".*") and root.startswith(n[:-1]) for n in names)


bad = [f"{f}:{line} {q}" for (f, q), (line, _kind) in sorted(seen.items()) if not allowed(f, q)]
code_list = list(g.get("CODE") or ())
bad_files = []
for p in sorted(opened):
    if p.endswith((".py", ".pyc")) or "__pycache__" in p:
        src = p if p.endswith(".py") else None
        if src and src not in code_list and not src.startswith("scripts/tests/"):
            bad_files.append(p)
        continue
    if p not in ALLOWED_FILES and not p.startswith(ALLOWED_PREFIXES):
        bad_files.append(p)

with open(OUT, "rb") as fh:
    sha = hashlib.sha256(fh.read()).hexdigest()
by_file = {}
for (f, q), (line, kind) in sorted(seen.items()):
    by_file.setdefault(f, []).append(f"{q}:{line}" + ("" if kind == "function" else f" ({kind})"))
trace = {"probe": "vc_dryrun_probe.py", "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
         "python": sys.version, "wall_seconds": round(wall, 1), "dry_run_json": os.path.basename(OUT),
         "dry_run_sha256": sha, "functions_started_by_file": by_file, "n_functions": len(seen),
         "opened_repo_files": sorted(opened),
         "allowlist": {f: sorted(v) for f, v in sorted(ALLOWED_CODE.items())},
         "forbidden_functions_that_ran": bad, "forbidden_files_opened": bad_files,
         "verdict": "OUTCOME-BLIND" if not bad and not bad_files else "VIOLATION"}
with open(TRACE, "w") as fh:
    json.dump(trace, fh, indent=1)
print(f"dry-run json sha256 {sha}  wall {wall:.1f}s  functions {len(seen)}  verdict {trace['verdict']}")
if bad or bad_files:
    print("VIOLATION:", bad, bad_files)
    sys.exit(3)
