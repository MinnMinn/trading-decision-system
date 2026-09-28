#!/usr/bin/env python3
"""Point-in-time adapter: run the LIVE analysis rules over stored candles, one bar at a time.

Why this exists: scripts/backtest-methods.py used to reimplement the ICT rules and the giảm-khung filter with
simplified proxies, so a backtest measured a system nobody trades (audit 2026-09-13). This module is the seam
that will let the backtest call the real thing — scripts/ict-scan.py for the structures and scripts/htf_context.py
for the bias — without the backtest having to know how either works (backtest-methods.py is wired to this in a
later task).

The contract is point-in-time: read_at(candles, i, tf) may look at candles[:i+1] and nothing later. The live
scanner reads a fixed trailing window per timeframe (scripts/automation.py SCAN_WINDOW), so this reproduces that
window rather than the whole history — a backtest that fed the scanner 105,000 bars would not be reproducing
anything live ever does.

Code-quality review of the first cut (commit acd65c5) found two Critical defects, both now fixed:
- read_at used to accept a PARTIAL window (>= 60 bars) as good enough. Live never scans on a partial window --
  it always has the full SCAN_WINDOW bars or it doesn't scan. A partial window has a different median range,
  different pivots, different equilibrium: exactly the look-ahead-shaped failure this file exists to prevent,
  just moved to the front of every series instead of the future. read_at now requires len(window) == bars.
- window() used to silently produce a plausible-looking wrong window for an out-of-range i (negative i, or
  i >= len(candles)). In a 105,000-iteration backtest loop that fails silently instead of loudly. window() now
  raises IndexError for any i outside [0, len(candles)).
"""
import importlib.util, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name, mod):
    spec = importlib.util.spec_from_file_location(mod, os.path.join(ROOT, "scripts", name))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


ict_scan = _load("ict-scan.py", "ict_scan")      # will be called by backtest-methods.py (Task 4), not yet
htf = _load("htf_context.py", "htf_context")     # will be called by backtest-methods.py (Task 4), not yet
_auto = _load("automation.py", "automation")
# A1 (docs/plans/2026-09-28-methodology-improvement-plan.md §2, ADR 0009): read_at() below is routed through
# the one structure source. A regular `import` (not `_load()`) -- structures.py has no dash in its filename, so
# it does not need the spec_from_file_location workaround `_load()` exists for, and a regular import is cached
# in sys.modules for this process: every caller that already put scripts/ on sys.path before loading this
# module (scripts/backtest-methods.py, scripts/strategy-runner.py, every test that loads live_rules.py) shares
# ONE `structures` instance instead of each `_load()` call re-executing structures.py's own module-level
# `_load("ict-scan.py", ...)`/`_load("htf_context.py", ...)` a second time (A1 code review round 1, item 4:
# reduces the redundant per-process import cost this file's OWN `ict_scan`/`htf` `_load()` calls above already
# accept, without adding a third and fourth redundant copy of the same two modules).
import structures as _structures


def scan_spec(tf):
    """(bars, recent) the live scanner uses for this timeframe. KeyError for a timeframe live never scans --
    deliberately loud: a backtest on such a timeframe cannot claim to reproduce live."""
    w = _auto.SCAN_WINDOW[tf]
    return w["bars"], w["recent"]


def window(candles, i, tf):
    """The trailing window the live scanner would have seen at bar i, inclusive. Short near the start, never
    padded. Raises IndexError for any i outside [0, len(candles)) -- an out-of-range i must fail loudly, not
    silently produce a plausible-looking wrong window (a negative i or an i past the end of a shorter series
    both slice to SOMETHING in Python; neither is a window live could ever have seen)."""
    if not (0 <= i < len(candles)):
        raise IndexError(f"live_rules.window: i={i} out of range for candles of length {len(candles)}")
    bars, _ = scan_spec(tf)
    return candles[max(0, i - bars + 1):i + 1]


def read_at(candles, i, tf, methods):
    """The live scanner's facts for bar i, or None unless the trailing window is the FULL live window for `tf`
    (len(window) == bars from scan_spec). Live never scans on a partial window, so neither does this. Depends
    only on candles[:i+1].

    `methods` is required, not defaulted: it must be exactly the methods live has engaged for the run being
    reproduced (scripts/htf_context.py's engaged_methods(style), resolved from /automation), not an
    independently-guessed default. analyze()'s own default is ("wyckoff","ict"); bias_of()'s is ("wyckoff",);
    a third default here would be the same silent-mismatch bug this whole module exists to kill."""
    bars, recent = scan_spec(tf)
    w = window(candles, i, tf)
    if len(w) != bars:
        return None
    # A1: routed through scripts/structures.py, the one structure source (ADR 0009). `ict_analysis()` IS
    # `ict_scan.analyze(w, recent, tf=tf, methods=methods)` -- see structures.py's module docstring, "Hot-path
    # / cold-path split" (A1 code review round 1, item 4): this runs once per bar of a backtest, so it must not
    # pay to build the enriched structure envelope (pivots/pools/MSS/FVGs/dealing range/bias) that nothing on
    # this path reads. Byte-identical to the pre-A1 direct call.
    return _structures.ict_analysis(w, recent, tf, methods=methods)


def setup_lookback(tf):
    """The window a setup's sweep must sit inside, as LIVE defaults it: ict-scan.py:466 uses
    `args.setup_lookback or max(12, args.recent * 6)`. The backtest must not substitute a parameter of its own --
    reproducing live is the whole point (user decision 2026-09-13: live defaults for everything)."""
    _, recent = scan_spec(tf)
    return max(12, recent * 6)


def bias_at(candles, i, tf, methods, facts=None):
    """(bias, basis) at bar i, from htf_context -- the same function the pages and the checkers use.

    `methods` is required, for the same reason as read_at's. `facts` is optional: a caller that already called
    read_at for this bar (the backtest loop needs both facts and bias per bar, across ~105,000 bars, and
    analyze()'s scans are the expensive part) passes them straight through instead of paying for a second
    analyze() call. This is NOT caching -- the caller still computed facts itself; bias_at just avoids
    recomputing what it was handed."""
    if facts is None:
        facts = read_at(candles, i, tf, methods)
    if facts is None:
        return "unknown", "chưa đủ nến trong cửa sổ quét"
    return htf.bias_of(None, facts, methods=methods)
