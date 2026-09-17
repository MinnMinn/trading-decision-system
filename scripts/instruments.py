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


# Where a market's live candles land, and whether its feed reports REAL traded volume.
#
# Both facts were spelled as a hard-coded symbol set in eight places -- `MT5 = {"XAUUSD","XAGUSD","USOIL",
# "UKOIL"}` in build-artifact.py, ict-scan.py, event-ledger.py, measure-spring-ict.py, local-eval-brief.py
# (+ check-narrative.py via import) and `DATA_DIR = {...}` in automation.py and method-panel.py -- in a repo
# whose rule is "never hard-code a symbol list anywhere else" (this module's own docstring, SYSTEM-DESIGN.md
# §1). method-panel.py even carried a comment explaining that its copy was deliberate. Eight copies is eight
# edits per new market, and test_instruments_sync.py already asserted some of those files must not hard-code
# symbols, so the duplication was an open invariant violation, not merely untidy.
#
# Keyed by MARKET, not by symbol: the directory and the volume semantics are properties of the FEED, so a new
# symbol in an existing market needs no edit here at all.
DATA_DIR = {"crypto": "market-data", "cfd": "mt5-bridge"}

# Markets whose feed reports TICK COUNT where a volume field is expected. Not a permission statement -- the
# Forex prohibition was lifted 2026-09-17 -- but a data-quality one, and the reason
# analysis-params.json carries tick_volume_credit_multiplier: a tick count must never be scored as traded
# volume (knowledge/08 §7, the source's own warning).
TICK_VOLUME_MARKETS = ("cfd",)

if set(DATA_DIR) != set(MARKETS):
    raise ValueError(f"scripts/instruments.py: DATA_DIR covers {sorted(DATA_DIR)} but MARKETS is "
                     f"{sorted(MARKETS)}. Every market needs exactly one live data directory -- a market "
                     f"without one makes every reader guess, and a directory without a market is dead wiring.")
if not set(TICK_VOLUME_MARKETS) <= set(MARKETS):
    raise ValueError(f"scripts/instruments.py: TICK_VOLUME_MARKETS names markets that do not exist: "
                     f"{sorted(set(TICK_VOLUME_MARKETS) - set(MARKETS))}.")


def _market_or_raise(symbol):
    m = market_of(symbol)
    if m is None:
        raise KeyError(f"{symbol} is on no analysis list in {PATH} -- refusing to guess its feed. "
                       f"An unknown symbol has no known data directory and no known volume semantics.")
    return m


def data_dir(symbol):
    """The data/live/<dir> a symbol's candles are written to, by market. Raises on an unknown symbol."""
    return DATA_DIR[_market_or_raise(symbol)]


def is_tick_volume(symbol):
    """True when this symbol's volume field is a TICK COUNT, not traded size. Raises on an unknown symbol.

    Raising is the fail-closed direction: returning False for something unrecognised would credit a tick feed
    with real traded volume, which is exactly the error the multiplier exists to prevent."""
    return _market_or_raise(symbol) in TICK_VOLUME_MARKETS


_DISPLAY = {k: v for k, v in (_DATA.get("display") or {}).items() if not k.startswith("_")}


def display(symbol):
    """Presentation metadata, with a derived default so adding a symbol needs no second edit anywhere.

    `asset_class` drives the killzone weighting in scripts/chart.js (KZ_WEIGHT) -- metals trade the London and
    both NY sessions at full weight, oil differs, crypto discounts all three. It defaults to the symbol's
    MARKET, so only a market that contains more than one asset class (cfd: metals + oil) needs an override."""
    over = _DISPLAY.get(symbol, {})
    base = symbol[:-4].lower() if symbol.endswith("USDT") else symbol.lower()
    return {"id": over.get("id", base),
            "label": over.get("label", symbol),
            "asset_class": over.get("asset_class", market_of(symbol) or "crypto"),
            "price_decimals": int(over.get("price_decimals", 2))}
