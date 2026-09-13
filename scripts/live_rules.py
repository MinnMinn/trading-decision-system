#!/usr/bin/env python3
"""Point-in-time adapter: run the LIVE analysis rules over stored candles, one bar at a time.

Why this exists: scripts/backtest-methods.py used to reimplement the ICT rules and the giảm-khung filter with
simplified proxies, so a backtest measured a system nobody trades (audit 2026-09-13). This module is the seam
that lets the backtest call the real thing — scripts/ict-scan.py for the structures and scripts/htf_context.py
for the bias — without the backtest having to know how either works.

The contract is point-in-time: read_at(candles, i, tf) may look at candles[:i+1] and nothing later. The live
scanner reads a fixed trailing window per timeframe (scripts/automation.py SCAN_WINDOW), so this reproduces that
window rather than the whole history — a backtest that fed the scanner 105,000 bars would not be reproducing
anything live ever does.
"""
import importlib.util, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name, mod):
    spec = importlib.util.spec_from_file_location(mod, os.path.join(ROOT, "scripts", name))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


ict_scan = _load("ict-scan.py", "ict_scan")      # public on purpose: backtest-methods.py calls setup_candidate
htf = _load("htf_context.py", "htf_context")     # public on purpose: backtest-methods.py calls bias_of
_auto = _load("automation.py", "automation")

MIN_BARS = 60   # below this a window has no median range worth trusting; the scanner never runs that thin


def spec(tf):
    """(bars, recent) the live scanner uses for this timeframe. KeyError for a timeframe live never scans —
    deliberately loud: a backtest on such a timeframe cannot claim to reproduce live."""
    w = _auto.SCAN_WINDOW[tf]
    return w["bars"], w["recent"]


def window(candles, i, tf):
    """The trailing window the live scanner would have seen at bar i, inclusive. Short near the start, never padded."""
    bars, _ = spec(tf)
    return candles[max(0, i - bars + 1):i + 1]


def read_at(candles, i, tf, methods=("ict",)):
    """The live scanner's facts for bar i, or None when there are too few bars. Depends only on candles[:i+1]."""
    w = window(candles, i, tf)
    if len(w) < MIN_BARS:
        return None
    _, recent = spec(tf)
    return ict_scan.analyze(w, recent, tf=tf, methods=methods)


def setup_lookback(tf):
    """The window a setup's sweep must sit inside, as LIVE defaults it: ict-scan.py:466 uses
    `args.setup_lookback or max(12, args.recent * 6)`. The backtest must not substitute a parameter of its own —
    reproducing live is the whole point (user decision 2026-09-13: live defaults for everything)."""
    _, recent = spec(tf)
    return max(12, recent * 6)


def bias_at(candles, i, tf, methods=("ict",)):
    """(bias, basis) at bar i, from htf_context — the same function the pages and the checkers use."""
    facts = read_at(candles, i, tf, methods)
    if facts is None:
        return "unknown", "chưa đủ nến trong cửa sổ quét"
    return htf.bias_of(None, facts, methods=methods)
