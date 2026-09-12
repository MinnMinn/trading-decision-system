"""THE reader for docs/architecture/instruments.json -- the single source of truth for the instrument
allowlist (SYSTEM-DESIGN.md §1). Import this; never hard-code a symbol list anywhere else.

    import instruments as I
    I.analysis("crypto")    -> ['BTCUSDT', ...]   # scannable / analysable
    I.execution("crypto")   -> ['BTCUSDT', ...]   # orderable (always a subset of analysis)
    I.ALL_ANALYSIS          -> every allowlisted symbol, crypto + cfd

Loading enforces the one invariant that keeps the split honest: every execution list is a subset of its
analysis list. A violation raises at import time rather than letting an unvetted symbol reach a connector.
"""
import json, os

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "docs", "architecture", "instruments.json")
MARKETS = ["crypto", "cfd"]


def _load():
    with open(PATH, encoding="utf-8") as fh:
        d = json.load(fh)
    for m in MARKETS:
        a, e = d["analysis"][m], d["execution"][m]
        extra = [s for s in e if s not in a]
        if extra:
            raise ValueError(f"{PATH}: execution.{m} has symbols absent from analysis.{m}: {extra}. "
                             f"An orderable symbol must always be analysable first (SYSTEM-DESIGN.md §1).")
    return d


_DATA = _load()
ANALYSIS = {m: list(_DATA["analysis"][m]) for m in MARKETS}
EXECUTION = {m: list(_DATA["execution"][m]) for m in MARKETS}
ALL_ANALYSIS = ANALYSIS["crypto"] + ANALYSIS["cfd"]
ALL_EXECUTION = EXECUTION["crypto"] + EXECUTION["cfd"]


def analysis(market=None):
    return list(ANALYSIS[market]) if market else list(ALL_ANALYSIS)


def execution(market=None):
    return list(EXECUTION[market]) if market else list(ALL_EXECUTION)


def market_of(symbol):
    for m in MARKETS:
        if symbol in ANALYSIS[m]:
            return m
    return None
