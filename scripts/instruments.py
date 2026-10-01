"""THE reader for docs/architecture/instruments.json -- the single source of truth for the instrument
allowlist (SYSTEM-DESIGN.md §1). Import this; never hard-code a symbol list anywhere else.

    import instruments as I
    I.analysis("crypto")    -> ['BTCUSDT', ...]   # scannable / analysable
    I.execution("crypto")   -> ['BTCUSDT', ...]   # orderable (always a subset of analysis)
    I.backtested("crypto")  -> ['BTCUSDT', ...]   # actually validated by the pilot backtest (subset of execution)
    I.ALL_ANALYSIS          -> every allowlisted symbol, every market
    I.MARKETS               -> the registered markets, in order -- derived from the file's `markets` object
    I.data_dir(sym) / I.is_tick_volume(sym) / I.default_enabled(market)   -> that market's feed facts

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


def _read():
    with open(PATH, encoding="utf-8") as fh:
        return json.load(fh)


_DATA = _read()

# The market vocabulary is DATA, not a literal. It was `["crypto", "cfd"]` here and again in automation.py, with
# each market's feed facts copied into eight further files -- so "add a market" meant ten edits and any two of
# them could disagree. The keys of instruments.json -> markets are now the definition, and the per-market
# sections must match them exactly (checked below), which makes a half-registered market impossible.
MARKET_META = {k: v for k, v in (_DATA.get("markets") or {}).items() if not k.startswith("_")}
if not MARKET_META:
    raise ValueError(f"{PATH}: no markets registered. The `markets` object defines which markets exist; "
                     f"without it every reader would have to guess, and guessing is how a symbol reaches a "
                     f"venue nobody vetted.")
MARKETS = list(MARKET_META)

# The feed facts every market must state, checked HERE rather than with the market-type checks further down,
# because DATA_DIR / TICK_VOLUME_MARKETS / CONTINUOUS_MARKETS are derived a few lines below and a derivation
# reaches a missing key first: the reader would get a bare `KeyError: 'continuous'` instead of a sentence
# saying which market is incomplete and why guessing is not an option.
for _m, _meta in MARKET_META.items():
    _missing = [k for k in ("data_dir", "tick_volume", "continuous", "default_enabled") if k not in _meta]
    if _missing:
        raise ValueError(f"{PATH}: markets.{_m} is missing {_missing}. Every registered market must state where "
                         f"its candles land, whether its volume field is a tick count, whether its tape runs "
                         f"without scheduled closures, and whether it is on by default -- none of the four has "
                         f"a safe guess.")
    for _k in ("tick_volume", "continuous", "default_enabled"):
        if not isinstance(_meta[_k], bool):
            raise ValueError(f"{PATH}: markets.{_m}.{_k} must be a boolean.")


def _load():
    d = _DATA
    for section in ("analysis", "execution"):
        if set(d.get(section) or {}) != set(MARKETS):
            raise ValueError(f"{PATH}: {section} covers {sorted(d.get(section) or {})} but the market registry "
                             f"is {sorted(MARKETS)}. Every registered market needs a list in every section -- a "
                             f"market with no analysis list resolves no symbols, and a list with no registered "
                             f"market has no feed, no style and no config node.")
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
        ro = [x for x in ((d.get("research_only") or {}).get(m) or [])]
        bad = [x for x in ro if x not in a or x in e]
        if bad:
            raise ValueError(f"{PATH}: research_only.{m} has symbols that are not analysis-only: {bad}. A "
                             f"research-only symbol must be on analysis.{m} and must NOT be on execution.{m} "
                             f"(it can never be orderable).")
    return d


_load()
ANALYSIS = {m: list(_DATA["analysis"][m]) for m in MARKETS}
EXECUTION = {m: list(_DATA["execution"][m]) for m in MARKETS}
BACKTESTED = {m: list((_DATA.get("backtested") or {}).get(m, [])) for m in MARKETS}
# Summed over MARKETS, not over a hand-written pair of market names: naming them here meant a new market was
# silently absent from every "all symbols" reader (the allowlist message, the safety hook) while being present
# in the per-market ones -- a half-registered market is worse than an unregistered one.
ALL_ANALYSIS = [s for m in MARKETS for s in ANALYSIS[m]]
ALL_EXECUTION = [s for m in MARKETS for s in EXECUTION[m]]
ALL_BACKTESTED = [s for m in MARKETS for s in BACKTESTED[m]]
# Symbols on analysis for the fund search only (owner decision 2026-10-01): history/costs/cells, never orderable.
# Optional section; a missing one reads as none. Readers that must stay on the pre-2026-10-01 symbol set
# (scripts/prop-search.py candidate space) subtract it.
RESEARCH_ONLY = {m: list(((_DATA.get("research_only") or {}).get(m)) or []) for m in MARKETS}
ALL_RESEARCH_ONLY = [s for m in MARKETS for s in RESEARCH_ONLY[m]]


def analysis(market=None):
    return list(ANALYSIS[market]) if market else list(ALL_ANALYSIS)


def execution(market=None):
    return list(EXECUTION[market]) if market else list(ALL_EXECUTION)


def live_analysis(market=None):
    """analysis() MINUS the research-only symbols: what the LIVE surfaces (scanner config, live page, method
    panel) iterate. A research-only symbol has no live feed, ever; listing it there would change the live
    path's behaviour (default config, 'no feed' footer) for a research-only decision."""
    ro = set(ALL_RESEARCH_ONLY)
    return [s for s in analysis(market) if s not in ro]


def research_only(market=None):
    """Analysis-only symbols added for the fund search (instruments.json -> research_only). Never in execution()."""
    return list(RESEARCH_ONLY[market]) if market else list(ALL_RESEARCH_ONLY)


def backtested(market=None):
    """Symbols the pilot rule set was actually validated on (docs/architecture/instruments.json ->
    backtested, checked against docs/architecture/pilot-selection.json -> backtest.source). A symbol absent here
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
# symbol in an existing market needs no edit here at all -- and they are read from the registry, so a new
# MARKET needs no edit here either.
DATA_DIR = {m: MARKET_META[m]["data_dir"] for m in MARKETS}

# Markets whose feed reports TICK COUNT where a volume field is expected. Not a permission statement -- the
# blanket Forex prohibition was lifted 2026-09-17 -- but a data-quality one, and the reason
# analysis-params.json carries tick_volume_credit_multiplier: a tick count must never be scored as traded
# volume (knowledge/wyckoff/modern-tools.md §7, the source's own warning).
TICK_VOLUME_MARKETS = tuple(m for m in MARKETS if MARKET_META[m]["tick_volume"])

# Markets whose tape runs without scheduled closures. This is what lets scripts/quality.py tell a HOLE from a
# WEEKEND when it computes CLAUDE.md §20's PARTIAL state: a gap inside a 24/7 series is a fetch fault, the same
# gap in a CFD series is Friday night. Keyed by market for the same reason as the two above -- it is a property
# of when the VENUE trades, not of the symbol.
CONTINUOUS_MARKETS = tuple(m for m in MARKETS if MARKET_META[m]["continuous"])

# ---------------------------------------------------------------- canonical market model (CLAUDE.md §5)
#
# Two vocabularies that must not be conflated, which is the whole point of §5 ("Do not use provider-specific
# market terminology as the canonical domain identity"):
#   MARKET TYPE  -- what a contract IS: SPOT / FUTURES / PERPETUAL / CFD / OTHER.
#   VENUE ALIAS  -- where it trades: `futures` / `spot` / `mt5` (docs/architecture/providers.json).
# Binance calls its USDT-M product "futures"; the contract is a PERPETUAL. The venue alias keeps the
# provider's word because that is what the state files and logs are tagged with; the market type does not.
MARKET_TYPES = tuple(k for k in _DATA["market_types"] if not k.startswith("_"))

_CANONICAL = {k: v for k, v in _DATA["canonical"].items() if not k.startswith("_")}


def market_types(market):
    """The canonical types this market can be traded as. Note this is a LIST: crypto is both SPOT (via
    /execute) and PERPETUAL (via the futures pilot). Which one a given order is depends on the venue, so ask
    providers.market_type_of(<provider>) when you have one -- a symbol alone cannot answer it."""
    return list(MARKET_META[market]["market_types"])


def canonical(symbol):
    """Provider-independent identity for a provider-spelled symbol ('BTCUSDT' -> 'BTC/USDT').

    Why this exists rather than reusing display(sym)["label"], which happens to hold the same string today:
    a label is presentation and may be changed for readability; an identity may not. Keeping them in one
    field would mean a page-styling edit silently re-identified an instrument.
    """
    return _CANONICAL[symbol]


for _m, _meta in MARKET_META.items():
    _types = _meta.get("market_types")
    if not isinstance(_types, list) or not _types:
        raise ValueError(f"{PATH}: markets.{_m} declares no `market_types`. Every market must say what kind of "
                         f"contract it holds (CLAUDE.md §5); guessing SPOT for an instrument that is actually "
                         f"a perpetual would misstate funding, expiry and leverage semantics at once.")
    _unknown = [t for t in _types if t not in MARKET_TYPES]
    if _unknown:
        raise ValueError(f"{PATH}: markets.{_m} names market type(s) {_unknown}; the canonical vocabulary is "
                         f"{list(MARKET_TYPES)}.")

# Identity is only identity if it is total and unique. A symbol with no canonical id would silently fall back
# to its provider spelling somewhere downstream (which is the thing §5 exists to stop), and two symbols
# sharing one id would merge two instruments' history the first time anything grouped by it.
for _m in MARKETS:
    for _sym in ANALYSIS[_m]:
        if _sym not in _CANONICAL:
            raise ValueError(f"{PATH}: {_sym} is on the analysis list with no `canonical` id. Every tradeable "
                             f"symbol needs a provider-independent identity (CLAUDE.md §5).")
_dupes = {v: [k for k in _CANONICAL if _CANONICAL[k] == v] for v in set(_CANONICAL.values())}
_dupes = {v: ks for v, ks in _dupes.items() if len(ks) > 1}
if _dupes:
    raise ValueError(f"{PATH}: canonical ids are not unique: {_dupes}. Two symbols sharing one identity would "
                     f"merge two instruments wherever anything groups by it.")


def default_enabled(market):
    """Whether a market is ON for a config that does not mention it (scripts/automation.py _market_default).

    forex ships False: the MT5 EA only exports symbols with an attached chart, and no FX chart is attached, so
    enabling it would set a flag over an empty directory."""
    return bool(MARKET_META[market]["default_enabled"])


def _market_or_raise(symbol):
    m = market_of(symbol)
    if m is None:
        raise KeyError(f"{symbol} is on no analysis list in {PATH} -- refusing to guess its feed. "
                       f"An unknown symbol has no known data directory and no known volume semantics.")
    return m


# Per-instrument estate capacity (docs/architecture/instruments.json estate_capacity). ONE reader:
# scripts/exposure.py _declared_capacity(). Empty is the normal state and means UNDECLARED, not unlimited --
# nothing here reads order-book depth, so a capacity cannot be measured yet and exposure.py turns the unknown
# into a refusal once the estate on that symbol grows past risk-config.json capacity_required_above_accounts.
CAPACITY = dict((_DATA.get("estate_capacity") or {}).get("max_estate_notional_usd") or {})
for _sym in CAPACITY:
    if _sym not in ANALYSIS:
        raise ValueError(f"docs/architecture/instruments.json: estate_capacity declares {_sym!r}, which is not "
                         f"on the analysis allowlist. A capacity for an instrument nobody trades is a number "
                         f"nobody checks.")


def data_dir(symbol):
    """The data/live/<dir> a symbol's candles are written to, by market. Raises on an unknown symbol."""
    return DATA_DIR[_market_or_raise(symbol)]


def is_tick_volume(symbol):
    """True when this symbol's volume field is a TICK COUNT, not traded size. Raises on an unknown symbol.

    Raising is the fail-closed direction: returning False for something unrecognised would credit a tick feed
    with real traded volume, which is exactly the error the multiplier exists to prevent."""
    return _market_or_raise(symbol) in TICK_VOLUME_MARKETS


def is_continuous(symbol):
    """True when this symbol's tape has no scheduled closures, so a missing bar is a FAULT and not a weekend.

    Raises on an unknown symbol, and that is again the fail-closed direction -- but note which way closed is
    here: guessing True would report every session break as CLAUDE.md §20 PARTIAL and gate a market on
    correct data, while guessing False would hide a real hole in a 24/7 feed. Neither guess is safe, so
    quality.py asks and this refuses to answer for something it does not know."""
    return _market_or_raise(symbol) in CONTINUOUS_MARKETS


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
