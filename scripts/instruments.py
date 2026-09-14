"""THE reader for docs/architecture/instruments.json -- the single source of truth for the instrument
allowlist (SYSTEM-DESIGN.md §1). Import this; never hard-code a symbol list anywhere else.

    import instruments as I
    I.analysis("crypto")    -> ['BTCUSDT', ...]   # scannable / analysable
    I.execution("crypto")   -> ['BTCUSDT', ...]   # orderable (always a subset of analysis)
    I.backtested("crypto")  -> ['BTCUSDT', ...]   # actually validated by the pilot backtest (subset of execution)
    I.ALL_ANALYSIS          -> every allowlisted symbol, crypto + cfd

Loading enforces two invariants:
  - every execution list is a subset of its analysis list -- a violation raises at import time rather than
    letting an unvetted symbol reach a connector;
  - every backtested list is a subset of its execution list -- a symbol cannot be claimed validated if it
    cannot even be traded.
A symbol absent from backtested.<market> -- or the field missing from instruments.json entirely -- reads as
NOT backtested (I.backtested() fails loud). This is a warning field: silently treating an unlisted/unreadable
symbol as validated would hide the one caveat this field exists to surface.
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
        b = [s for s in (d.get("backtested") or {}).get(m, []) if s not in e]
        if b:
            raise ValueError(f"{PATH}: backtested.{m} claims validation for symbols absent from execution.{m}: "
                             f"{b}. A symbol cannot be backtest-validated if it cannot be traded.")
    return d


_DATA = _load()
ANALYSIS = {m: list(_DATA["analysis"][m]) for m in MARKETS}
EXECUTION = {m: list(_DATA["execution"][m]) for m in MARKETS}
BACKTESTED = {m: list((_DATA.get("backtested") or {}).get(m, [])) for m in MARKETS}
ALL_ANALYSIS = ANALYSIS["crypto"] + ANALYSIS["cfd"]
ALL_EXECUTION = EXECUTION["crypto"] + EXECUTION["cfd"]
ALL_BACKTESTED = BACKTESTED["crypto"] + BACKTESTED["cfd"]


def analysis(market=None):
    return list(ANALYSIS[market]) if market else list(ALL_ANALYSIS)


def execution(market=None):
    return list(EXECUTION[market]) if market else list(ALL_EXECUTION)


def backtested(market=None):
    """Symbols the pilot rule set was actually validated on (docs/architecture/instruments.json ->
    backtested, checked against docs/architecture/pilot-top5.json -> backtest.source). A symbol absent here
    is NOT backtested -- there is no separate 'unknown' state; fail loud, per the field's own purpose."""
    return list(BACKTESTED[market]) if market else list(ALL_BACKTESTED)


def market_of(symbol):
    for m in MARKETS:
        if symbol in ANALYSIS[m]:
            return m
    return None


_DISPLAY = {k: v for k, v in (_DATA.get("display") or {}).items() if not k.startswith("_")}


def display(symbol):
    """Presentation metadata, with a derived default so adding a symbol needs no second edit anywhere."""
    over = _DISPLAY.get(symbol, {})
    base = symbol[:-4].lower() if symbol.endswith("USDT") else symbol.lower()
    return {"id": over.get("id", base),
            "label": over.get("label", symbol),
            "price_decimals": int(over.get("price_decimals", 2))}
